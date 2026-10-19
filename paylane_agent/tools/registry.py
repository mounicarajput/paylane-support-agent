"""Executes model tool calls through trusted state and policy guards."""
from typing import Optional

from ..session.clock import Clock
from ..session.state import SessionState
from ..session.verification import verify
from . import guards
from .mock_api import MockAPI
from .schemas import ESCALATION_REASONS, TOOLS


def _refusal(decision: guards.Decision) -> dict:
    out = {"ok": False, "reason": decision.reason, "detail": decision.detail}
    if decision.escalate:
        out["next_step"] = "escalate_to_human"
    return out


class ToolRegistry:
    def __init__(self, api: Optional[MockAPI] = None, state: Optional[SessionState] = None,
                 clock: Optional[Clock] = None):
        self.api = api or MockAPI()
        self.state = state or SessionState()
        self.clock = clock or Clock()
        self.calls: list = []  # (name, args, result) for transcripts and evals
        # What the customer has typed so far. The agent fills it in. When it is set, verify_customer
        # refuses details the customer never gave (models sometimes invent an email and card digits).
        self.customer_text: Optional[list] = None
        self._handlers = {
            "verify_customer": self._verify_customer,
            "get_customer": self._get_customer,
            "get_transaction": self._get_transaction,
            "issue_refund": self._issue_refund,
            "escalate_to_human": self._escalate,
        }

    @property
    def definitions(self) -> list:
        return TOOLS

    def execute(self, name: str, args: Optional[dict]) -> dict:
        handler = self._handlers.get(name)
        if handler is None:
            result = {"ok": False, "reason": "unknown_tool"}
        elif not isinstance(args, dict):
            result = {"ok": False, "reason": "invalid_arguments"}
        else:
            try:
                result = handler(args)
            except KeyError as e:
                result = {"ok": False, "reason": "invalid_arguments", "detail": f"missing {e.args[0]}"}
        self.calls.append((name, args, result))
        return result

    def _typed_by_customer(self, email: str, last4: str) -> bool:
        if self.customer_text is None:
            return True  # no conversation attached (direct use), nothing to compare with
        typed = " ".join(self.customer_text).lower()
        return email.strip().lower() in typed and last4.strip() in typed

    def _verify_customer(self, args: dict) -> dict:
        email, last4 = str(args["email"]), str(args["card_last4"])
        if not self._typed_by_customer(email, last4):
            # Not a failed attempt: the customer never gave these details, so nothing is counted.
            return {"ok": False, "reason": "not_provided",
                    "message": "The customer has not given those details. Ask them for the last 4 digits "
                               "of their card and the email on their account. Never guess or make them up."}
        result = verify(self.state, self.api, email, last4)
        out = {"ok": result.ok, "message": result.message}
        if result.locked:
            out["locked"] = True
            if not self.state.handed_off:  # three failures force a handoff
                ticket = self._create_ticket(
                    "Customer failed identity verification three times.", "verification_failed")
                out["ticket_id"] = ticket["ticket_id"]
            else:
                out["ticket_id"] = self.state.handoff_ticket_id
        return out

    def _get_customer(self, args: dict) -> dict:
        access = guards.account_access(self.state)
        if not access.allowed:
            return _refusal(access)
        customer = self.api.get_customer(args["email"])
        if customer is None or customer["id"] != self.state.customer_id:
            return {"ok": False, "reason": "not_found"}
        # Never return email or card digits.
        return {"ok": True, "id": customer["id"], "name": customer["name"], "card_status": customer["status"]}

    def _txn_not_provided(self, txn_id: str) -> Optional[dict]:
        """Refuse a transaction ID the customer never typed (models sometimes invent or guess one)."""
        if self.customer_text is not None and txn_id.strip().lower() not in " ".join(self.customer_text).lower():
            return {"ok": False, "reason": "not_provided",
                    "message": "The customer has not given that transaction ID. Ask them for it. "
                               "Never guess or make one up."}
        return None

    def _get_transaction(self, args: dict) -> dict:
        access = guards.account_access(self.state)
        if not access.allowed:
            return _refusal(access)
        if (refused := self._txn_not_provided(str(args["txn_id"]))):
            return refused
        txn = self.api.get_transaction(self.state.customer_id, str(args["txn_id"]))
        if txn.get("ok") is False:
            return {"ok": False, "reason": "not_found"}
        path, why = guards.classify_refund(txn, self.clock)
        note = {
            "auto": "Eligible for an automatic full refund if the customer asks for one.",
            "human": f"Not eligible for an automatic refund ({why}). A human must review it. Do not call issue_refund.",
            "none": f"Cannot be refunded ({why}). Do not call issue_refund.",
        }[path]
        return {"ok": True, "txn_id": args["txn_id"], **txn,
                "refund_path": path, "refund_reason": why, "refund_note": note}

    def _issue_refund(self, args: dict) -> dict:
        txn_id, amount = str(args["txn_id"]), args["amount"]
        access = guards.account_access(self.state)
        if access.allowed and (refused := self._txn_not_provided(txn_id)):
            return refused
        decision = guards.check_refund(self.state, self.api, self.clock, txn_id, amount)
        if not decision.allowed:
            return _refusal(decision)
        result = self.api.issue_refund(txn_id, float(guards.to_decimal(amount)))
        if not result["ok"]:
            return {"ok": False, "reason": result["reason"]}
        return {"ok": True, "refund_id": result["refund_id"], "amount": amount}

    def _escalate(self, args: dict) -> dict:
        reason = args["reason"]
        if reason not in ESCALATION_REASONS:
            return {"ok": False, "reason": "invalid_arguments", "detail": "unknown escalation reason"}
        if self.state.handed_off:  # one handoff per issue; reuse the existing ticket
            return {"ok": True, "ticket_id": self.state.handoff_ticket_id, "already_escalated": True}
        high = guards.is_high_priority(reason, args.get("reported_loss_usd"))
        out = self._create_ticket(str(args["summary"]), reason, high)
        if high:
            out["priority"] = "high"
        return out

    def _create_ticket(self, summary: str, reason: str, high_priority: bool = False) -> dict:
        tag = f"[{reason}]" + (" [HIGH PRIORITY]" if high_priority else "")
        result = self.api.escalate_to_human(self.state.customer_id, f"{tag} {summary}")
        self.state.handoff_ticket_id = result["ticket_id"]
        return {"ok": True, "ticket_id": result["ticket_id"]}
