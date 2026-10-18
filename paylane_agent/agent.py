"""The agent: a tool-use loop over a provider and the guarded tool registry.

Around the model sits the deterministic policy layer (policy.py). Before the model sees a
message the agent: hands off legal/fraud/closure/"get me a human" itself, checks credentials the
customer typed, looks up transactions they named, and answers the situations where the right
reply is already known (already refunded, pending, pushback after a handoff, "what's the email
on file?"). After the model replies, every reply is checked before the customer sees it.
"""
import json
import re
from pathlib import Path
from typing import Optional

from . import policy
from .providers.base import Provider, ToolCall
from .tools.registry import ToolRegistry
from .transcript import Transcript

PROMPT_DIR = Path(__file__).parent / "prompts"
MAX_TOOL_ROUNDS = 14
MAX_NUDGES = 2
MAX_CORRECTIONS = 2
FALLBACK = "Sorry, I hit a problem on my side. I'll pass this to a human so you're not stuck."
# Smaller open-source models sometimes end a turn with "Let's check..." instead of calling the tool.
STALLED = re.compile(
    r"\b(let's|let me|i'll|i will|i am going to|i'm going to) (now )?(check|look|verify|process|proceed|pull up|find|issue)\b",
    re.I)
NUDGE = ("(Automated reminder, not from the customer.) You said you would do something but did not call a tool. "
         "Call the tool now, then tell the customer the result. Do not announce actions.")
CORRECTION = ("(Automated reminder, not from the customer.) Your last reply was not sent. Problem: {problem} "
              "Write the reply again without that.")


def load_system_prompt() -> str:
    parts = [(PROMPT_DIR / n).read_text(encoding="utf-8").strip() for n in ("system_prompt.md", "rulebook.md")]
    return "\n\n".join(p for p in parts if p)


def _money(amount) -> str:
    return f"{float(amount):.2f}".rstrip("0").rstrip(".")


class Agent:
    def __init__(self, provider: Provider, registry: Optional[ToolRegistry] = None,
                 system_prompt: Optional[str] = None, transcript: Optional[Transcript] = None):
        self.provider = provider
        self.registry = registry or ToolRegistry()
        self.system_prompt = system_prompt if system_prompt is not None else load_system_prompt()
        self.transcript = transcript or Transcript()
        self.messages: list = []
        self._auto_n = 0
        self._last_user = ""
        self._last_creds: Optional[tuple] = None
        self._blocked: Optional[dict] = None  # last transaction that can't be refunded (already refunded / pending)
        self._asked_which_charge = False
        self._used: dict = {}

    # ---- one customer turn ---------------------------------------------------------------
    def respond(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        self.transcript.add("user", text=user_text)
        self._last_user = user_text

        early = self._before_model(user_text)
        if early is not None:
            return self._finish(early, append=True)

        nudges = corrections = 0
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.provider.chat(self.system_prompt, self.messages, self.registry.definitions)
            self.messages.append({"role": "assistant", "content": reply.text, "tool_calls": reply.tool_calls})

            if reply.tool_calls:
                results = [(c.name, self._run_tool(c)) for c in reply.tool_calls]
                after = self._after_tools(results)
                if after is not None:
                    return self._finish(after, append=True)
                continue

            if nudges < MAX_NUDGES and STALLED.search(reply.text) and not self.registry.state.handed_off:
                nudges += 1  # hide the stalled message from the customer and prompt the model to act
                self.transcript.add("note", text=f"stalled reply suppressed: {reply.text!r}")
                self.messages.append({"role": "user", "content": NUDGE})
                continue

            problem = policy.check_reply(reply.text, self.registry)
            if problem is None:
                return self._finish(reply.text)
            self.transcript.add("note", text=f"reply blocked ({problem.name}): {reply.text!r}")
            if corrections < MAX_CORRECTIONS:
                corrections += 1
                self.messages.append({"role": "user", "content": CORRECTION.format(problem=problem.correction)})
                continue
            return self._finish(self._safe_fallback(problem), append=True)  # still unsafe after retries

        # Model kept calling tools without answering: fail safe to a human.
        if not self.registry.state.handed_off:
            self.registry.execute("escalate_to_human", {
                "summary": "Agent could not finish the conversation.", "reason": "other"})
        return self._finish(FALLBACK)

    # ---- deterministic steps before the model -------------------------------------------
    def _before_model(self, text: str) -> Optional[str]:
        state = self.registry.state

        trigger = policy.detect_handoff(text)
        if trigger:
            reason, loss = trigger
            if state.handed_off:
                return self._pick("already", policy.ALREADY_HANDED_OFF).format(tid=state.handoff_ticket_id)
            return self._handoff(reason, f"Customer said: {text[:300]}", loss)

        if policy.REVEAL_REQUEST.search(text):
            return self._pick("reveal", policy.NO_REVEAL)

        if state.handed_off:
            return self._after_handoff_reply(text)

        creds = policy.extract_credentials(text)
        if creds and (not state.verified or creds != self._last_creds):
            self._last_creds = creds
            res = self._auto_tool("verify_customer", {"email": creds[0], "card_last4": creds[1]})
            if not res.get("ok"):
                if res.get("locked"):
                    return policy.HANDOFF_REPLIES["verification_failed"].format(tid=res.get("ticket_id"))
                variant = policy.VERIFY_FAILED[min(state.failed_checks - 1, len(policy.VERIFY_FAILED) - 1)]
                return variant or res["message"]
        elif not state.verified and not creds and policy.ACCOUNT_DETAIL.search(text):
            return policy.ASK_TO_VERIFY

        txn_ids = policy.extract_txn_ids(text)
        wants_refund = bool(policy.REFUND_INTENT.search(text))
        if state.verified:
            for txn_id in txn_ids[:2]:
                res = self._auto_tool("get_transaction", {"txn_id": txn_id})
                if res.get("refund_path") == "none":
                    self._blocked = res
                if wants_refund and res.get("refund_path") == "human":
                    return self._refund_handoff(res)
                if wants_refund and res.get("refund_path") == "none":
                    return self._blocked_reply(res, repeat=False)
            if policy.CARD_TROUBLE.search(text):
                email = self._session_email()
                if email:
                    res = self._auto_tool("get_customer", {"email": email})
                    if res.get("card_status") == "frozen":
                        return self._handoff("frozen_card", f"Card is frozen. Customer said: {text[:300]}")

        # Customer keeps asking for a refund we already said no to (already refunded / pending).
        if self._blocked and not txn_ids and (wants_refund or policy.PUSHBACK.search(text)):
            return self._blocked_reply(self._blocked, repeat=True)

        # A vague complaint: ask which charge before asking for anything else.
        if (not self._asked_which_charge and not txn_ids and not creds and not policy.AMOUNT.search(text)
                and policy.VAGUE_CHARGE.search(text)):
            self._asked_which_charge = True
            return policy.WHICH_CHARGE
        return None

    def _after_handoff_reply(self, text: str) -> Optional[str]:
        """After a handoff the customer often pushes. The answer is always the same fact, said kindly."""
        tid = self.registry.state.handoff_ticket_id
        if policy.WHAT_NEXT.search(text):
            return self._pick("next", policy.WHAT_NEXT_AFTER_HANDOFF).format(tid=tid)
        if policy.SPLIT.search(text) and policy.REFUND_INTENT.search(text):
            return self._pick("split", policy.SPLIT_AFTER_HANDOFF).format(tid=tid)
        if policy.REFUND_INTENT.search(text) or policy.PUSHBACK.search(text):
            return self._pick("pushback", policy.PUSHBACK_AFTER_HANDOFF).format(tid=tid)
        return None  # anything else goes to the model; account actions are blocked and replies are checked

    # ---- deterministic steps after the model's tool calls -------------------------------
    def _after_tools(self, results: list) -> Optional[str]:
        state = self.registry.state
        for name, res in results:
            if name == "verify_customer" and res.get("locked") and res.get("ticket_id"):
                return policy.HANDOFF_REPLIES["verification_failed"].format(tid=res["ticket_id"])
        if state.handed_off:
            return None
        wants_refund = bool(policy.REFUND_INTENT.search(self._last_user))
        for name, res in results:
            if name == "get_transaction" and res.get("refund_path") == "none":
                self._blocked = res
            if name == "issue_refund" and res.get("reason") in ("over_limit", "too_old"):
                return self._refund_handoff({"refund_reason": res["reason"], **res})
            if name == "get_transaction" and res.get("refund_path") == "human" and wants_refund:
                return self._refund_handoff(res)
            if name == "get_customer" and res.get("card_status") == "frozen":
                return self._handoff("frozen_card", f"Card is frozen. Customer said: {self._last_user[:300]}")
        return None

    # ---- helpers -------------------------------------------------------------------------
    def _pick(self, key: str, variants: list) -> str:
        n = self._used.get(key, 0)
        self._used[key] = n + 1
        return variants[n % len(variants)]

    def _blocked_reply(self, txn: dict, repeat: bool) -> str:
        why = txn.get("refund_reason")
        if why == "already_refunded":
            if repeat:
                return self._pick("again", policy.ALREADY_REFUNDED_AGAIN)
            return policy.ALREADY_REFUNDED.format(merchant=txn.get("merchant", "that"), amount=_money(txn.get("amount", 0)))
        if repeat:
            return self._pick("pending_again", policy.PENDING_AGAIN)
        return policy.PENDING.format(merchant=txn.get("merchant", "that"), amount=_money(txn.get("amount", 0)))

    def _refund_handoff(self, txn_result: dict) -> str:
        why = txn_result.get("refund_reason", "over_limit")
        summary = (f"Refund request needs review ({why}): {txn_result.get('txn_id', 'transaction')}, "
                   f"{txn_result.get('merchant', '?')}, amount {txn_result.get('amount', '?')}, "
                   f"dated {txn_result.get('date', '?')}. Customer said: {self._last_user[:200]}")
        key = "refund_too_old" if why == "too_old" else "refund_over_limit"
        return self._handoff("refund_exception", summary, template=key)

    def _handoff(self, reason: str, summary: str, loss=None, template: Optional[str] = None) -> str:
        state = self.registry.state
        if state.handed_off:
            return self._pick("already", policy.ALREADY_HANDED_OFF).format(tid=state.handoff_ticket_id)
        args = {"summary": summary, "reason": reason}
        if loss is not None:
            args["reported_loss_usd"] = loss
        res = self._auto_tool("escalate_to_human", args)
        if not res.get("ticket_id"):
            return FALLBACK
        return policy.HANDOFF_REPLIES[template or reason].format(tid=res["ticket_id"])

    def _safe_fallback(self, problem: policy.Violation) -> str:
        state = self.registry.state
        if state.handed_off:
            return self._pick("already", policy.ALREADY_HANDED_OFF).format(tid=state.handoff_ticket_id)
        if problem.name == "false_handoff_claim":
            return policy.OFFER_HANDOFF  # don't open a ticket just because the model got ahead of itself
        return self._handoff("other", "Agent could not produce a safe reply.")

    def _session_email(self) -> Optional[str]:
        for name, args, res in reversed(self.registry.calls):
            if name == "verify_customer" and res.get("ok") and isinstance(args, dict):
                return args.get("email")
        return None

    def _auto_tool(self, name: str, args: dict) -> dict:
        """A tool call made by the agent itself, recorded in history like a model call."""
        self._auto_n += 1
        call = ToolCall(f"auto_{self._auto_n}", name, args)
        self.messages.append({"role": "assistant", "content": "", "tool_calls": [call]})
        return self._run_tool(call, auto=True)

    def _run_tool(self, call: ToolCall, auto: bool = False) -> dict:
        self.transcript.add("tool_call", name=call.name, arguments=call.arguments, **({"auto": True} if auto else {}))
        result = self.registry.execute(call.name, call.arguments)
        self.transcript.add("tool_result", name=call.name, result=result)
        self.messages.append({
            "role": "tool", "tool_call_id": call.id, "name": call.name,
            "content": json.dumps(result, ensure_ascii=False),
        })
        return result

    def _finish(self, text: str, append: bool = False) -> str:
        if append:  # replies the agent wrote itself aren't in history yet
            self.messages.append({"role": "assistant", "content": text, "tool_calls": []})
        self.transcript.add("assistant", text=text)
        return text
