import pytest

from paylane_agent.tools.registry import ToolRegistry


def verified(email="alice@example.com", last4="4242") -> ToolRegistry:
    reg = ToolRegistry()
    assert reg.execute("verify_customer", {"email": email, "card_last4": last4})["ok"]
    return reg


def refund(reg, txn_id, amount):
    return reg.execute("issue_refund", {"txn_id": txn_id, "amount": amount})


def test_unverified_refund_blocked_and_nothing_issued():
    reg = ToolRegistry()
    r = refund(reg, "txn_1001", 40)
    assert r["reason"] == "not_verified" and reg.api.refunds == []


def test_unverified_cannot_read_account():
    reg = ToolRegistry()
    assert reg.execute("get_customer", {"email": "alice@example.com"})["reason"] == "not_verified"
    assert reg.execute("get_transaction", {"txn_id": "txn_1001"})["reason"] == "not_verified"


def test_happy_path_refund():
    reg = verified()
    r = refund(reg, "txn_1001", 40)
    assert r["ok"] and r["refund_id"] == "rf_0001"


def test_exactly_75_allowed_and_75_01_escalates():
    reg = verified()
    assert refund(reg, "txn_1009", 75)["ok"]
    r = refund(reg, "txn_1010", 75.01)
    assert r["reason"] == "over_limit" and r["next_step"] == "escalate_to_human"


def test_over_75_escalates():
    r = refund(verified(), "txn_1002", 120)
    assert r["reason"] == "over_limit" and r["next_step"] == "escalate_to_human"


def test_exactly_30_days_escalates_29_days_ok():
    reg = verified()
    r = refund(reg, "txn_1003", 60)
    assert r["reason"] == "too_old" and r["next_step"] == "escalate_to_human"
    assert refund(reg, "txn_1004", 25)["ok"]


def test_never_refund_twice():
    reg = verified()
    assert refund(reg, "txn_1001", 40)["ok"]
    assert refund(reg, "txn_1001", 40)["reason"] == "already_refunded"
    assert refund(reg, "txn_1005", 30)["reason"] == "already_refunded"
    assert len(reg.api.refunds) == 1


def test_pending_cannot_be_refunded():
    assert refund(verified(), "txn_1006", 50)["reason"] == "not_settled"


@pytest.mark.parametrize("amount", [10, 39.99, 40.01, 0, -5, "abc", None])
def test_partial_or_bad_amount_rejected(amount):
    reg = verified()
    assert refund(reg, "txn_1001", amount)["reason"] == "amount_mismatch"
    assert reg.api.refunds == []


def test_other_customers_transaction_is_not_found():
    reg = verified()
    assert refund(reg, "txn_1007", 20)["reason"] == "not_found"
    assert reg.execute("get_transaction", {"txn_id": "txn_1007"})["reason"] == "not_found"


def test_three_failures_lock_and_auto_handoff():
    reg = ToolRegistry()
    for _ in range(2):
        assert not reg.execute("verify_customer", {"email": "alice@example.com", "card_last4": "0000"}).get("locked")
    r = reg.execute("verify_customer", {"email": "alice@example.com", "card_last4": "0000"})
    assert r["locked"] and r["ticket_id"] == "TKT-0001"
    # correct details no longer help; no second ticket
    r = reg.execute("verify_customer", {"email": "alice@example.com", "card_last4": "4242"})
    assert not r["ok"] and r["ticket_id"] == "TKT-0001" and len(reg.api.tickets) == 1
    assert refund(reg, "txn_1001", 40)["reason"] == "handed_off"


def test_wrong_card_on_second_check_blocks_account_access():
    # Exact UI scenario: verified, refund txn_1001, then "txn_1006 too" with a wrong card.
    reg = verified()
    assert refund(reg, "txn_1001", 40)["ok"]
    r = reg.execute("verify_customer", {"email": "alice@example.com", "card_last4": "5234"})
    assert not r["ok"] and "5234" not in str(r) and "4242" not in str(r)
    assert reg.execute("get_transaction", {"txn_id": "txn_1006"})["reason"] == "not_verified"
    assert refund(reg, "txn_1004", 25)["reason"] == "not_verified"


def test_escalate_works_unverified_with_null_customer():
    reg = ToolRegistry()
    r = reg.execute("escalate_to_human", {"summary": "legal threat", "reason": "legal_action"})
    assert r["ticket_id"] == "TKT-0001" and reg.api.tickets[0]["customer_id"] is None


def test_handoff_stops_account_actions_and_reuses_ticket():
    reg = verified()
    reg.execute("escalate_to_human", {"summary": "frozen card", "reason": "frozen_card"})
    assert refund(reg, "txn_1001", 40)["reason"] == "handed_off"
    assert reg.execute("get_transaction", {"txn_id": "txn_1001"})["reason"] == "handed_off"
    again = reg.execute("escalate_to_human", {"summary": "again", "reason": "other"})
    assert again["ticket_id"] == "TKT-0001" and len(reg.api.tickets) == 1


def test_fraud_over_500_high_priority_else_normal_but_still_handed_off():
    reg = verified()
    r = reg.execute("escalate_to_human", {"summary": "x", "reason": "suspected_fraud", "reported_loss_usd": 650})
    assert r["priority"] == "high" and "[HIGH PRIORITY]" in reg.api.tickets[0]["summary"]
    for loss in (500, 120, None):
        reg2 = verified()
        r2 = reg2.execute("escalate_to_human", {"summary": "x", "reason": "suspected_fraud", "reported_loss_usd": loss})
        assert r2["ok"] and "priority" not in r2


def test_get_customer_hides_email_and_card_digits():
    reg = verified()
    r = reg.execute("get_customer", {"email": "alice@example.com"})
    assert r["ok"] and r["card_status"] == "active"
    text = str(r)
    assert "4242" not in text and "alice@example.com" not in text


def test_get_customer_for_another_email_not_found():
    reg = verified()
    assert reg.execute("get_customer", {"email": "chloe@example.com"})["reason"] == "not_found"


def test_bad_calls_do_not_crash():
    reg = verified()
    assert reg.execute("nope", {})["reason"] == "unknown_tool"
    assert reg.execute("issue_refund", {"txn_id": "txn_1001"})["reason"] == "invalid_arguments"
    assert reg.execute("issue_refund", None)["reason"] == "invalid_arguments"
    assert reg.execute("escalate_to_human", {"summary": "x", "reason": "bogus"})["reason"] == "invalid_arguments"
