"""Policy enforced in code. The model cannot talk its way past these checks."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from ..session.state import SessionState

MAX_AUTO_REFUND = Decimal("75")
HIGH_PRIORITY_LOSS = Decimal("500")


@dataclass
class Decision:
    allowed: bool
    reason: str = ""
    detail: str = ""
    escalate: bool = False  # True when the right next step is a human handoff


def to_decimal(value):
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() and d > 0 else None


def account_access(state: SessionState) -> Decision:
    """Account details/actions need a verified, unlocked session that hasn't been handed off."""
    if state.handed_off:
        return Decision(False, "handed_off", "This issue is already with a human. No further account actions.")
    if state.locked:
        return Decision(False, "locked", "Verification failed too many times. Account actions are stopped.", True)
    if not state.verified:
        return Decision(False, "not_verified", "Customer must verify the card last 4 and email first.")
    return Decision(True)


def check_refund(state: SessionState, api, clock, txn_id: str, amount) -> Decision:
    access = account_access(state)
    if not access.allowed:
        return access

    txn = api.get_transaction(state.customer_id, txn_id)
    if txn.get("ok") is False:  # unknown or belongs to someone else: same answer either way
        return Decision(False, "not_found", "No matching transaction on this account.")

    original = Decimal(str(txn["amount"]))
    if txn["status"] == "refunded":
        return Decision(False, "already_refunded", "This transaction was already refunded.")
    if txn["status"] != "settled":
        return Decision(False, "not_settled", "Only settled transactions can be refunded; pending charges cannot.")

    requested = to_decimal(amount)
    if requested is None or requested != original:
        return Decision(False, "amount_mismatch", "Only the full original amount can be refunded. No partial refunds.")

    if original > MAX_AUTO_REFUND:
        return Decision(False, "over_limit", "Refunds above $75 need a human.", True)
    if not clock.within_refund_window(txn["date"]):
        return Decision(False, "too_old", "Transactions 30 days old or older need a human.", True)
    return Decision(True)


def classify_refund(txn: dict, clock) -> tuple:
    """Where a refund for this transaction would go: ('auto'|'human'|'none', reason).

    Same rules as check_refund, as a pure read of the transaction (used to tell the model up
    front and by the agent's handoff triggers).
    """
    if txn["status"] == "refunded":
        return "none", "already_refunded"
    if txn["status"] != "settled":
        return "none", "not_settled"
    if Decimal(str(txn["amount"])) > MAX_AUTO_REFUND:
        return "human", "over_limit"
    if not clock.within_refund_window(txn["date"]):
        return "human", "too_old"
    return "auto", ""


def is_high_priority(reason: str, reported_loss_usd) -> bool:
    """Fraud with a total reported loss over $500 is high priority."""
    loss = to_decimal(reported_loss_usd) if reported_loss_usd is not None else None
    return reason == "suspected_fraud" and loss is not None and loss > HIGH_PRIORITY_LOSS
