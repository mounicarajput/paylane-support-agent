"""Session verification: supplied email AND last 4 must both match the record."""
from dataclasses import dataclass

from .state import SessionState

GENERIC_FAILURE = (
    "I couldn't verify those details. Please check the last 4 digits of your card "
    "and the email on your account and try again."
)
LOCKED_MESSAGE = (
    "I can't verify this account in this chat. I'll pass this to a human who can help."
)


@dataclass
class VerificationResult:
    ok: bool
    message: str
    locked: bool = False


def verify(state: SessionState, api, email: str, last4: str) -> VerificationResult:
    if state.locked:
        return VerificationResult(False, LOCKED_MESSAGE, locked=True)

    # Always check what was supplied, even in an already-verified session.
    customer = api.get_customer((email or "").strip().lower())
    matched = (
        customer is not None
        and customer.get("ok", True)
        and str(last4 or "").strip() == str(customer["card_last4"])
    )
    # A verified session can't switch to a different customer's account.
    if matched and (not state.verified or customer["id"] == state.customer_id):
        state.verified = True
        state.customer_id = customer["id"]
        return VerificationResult(True, "Verified.")

    # Same message whichever field was wrong; never echo stored values.
    # A failed check also drops any earlier verification: the person typing may have changed.
    state.verified = False
    state.customer_id = None
    state.failed_checks += 1
    if state.locked:
        return VerificationResult(False, LOCKED_MESSAGE, locked=True)
    return VerificationResult(False, GENERIC_FAILURE)
