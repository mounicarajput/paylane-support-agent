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

    def _verify_customer(self, args: dict) -> dict:
        result = verify(self.state, self.api, str(args["email"]), str(args["card_last4"]))
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

    def _get_transaction(self, args: dict) -> dict:
        access = guards.account_access(self.state)
        if not access.allowed:
            return _refusal(access)
        txn = self.api.get_transaction(self.state.customer_id, str(args["txn_id"]))
        if txn.get("ok") is False:
            return {"ok": False, "reason": "not_found"}
        return {"ok": True, "txn_id": args["txn_id"], **txn}

    def _issue_refund(self, args: dict) -> dict:
        txn_id, amount = str(args["txn_id"]), args["amount"]
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
