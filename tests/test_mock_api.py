from paylane_agent.tools.mock_api import MockAPI


def test_get_customer_shape_and_unverified():
    c = MockAPI().get_customer("Monika@Example.com ")
    assert c["id"] == "c_1001" and c["verified"] is False
    assert set(c) == {"id", "name", "card_last4", "status", "verified"}


def test_get_customer_unknown():
    assert MockAPI().get_customer("nobody@example.com") is None


def test_get_transaction_scoped_to_customer():
    api = MockAPI()
    assert api.get_transaction("c_1001", "txn_1001")["amount"] == 40.00
    assert api.get_transaction("c_1001", "txn_1007") == {"ok": False, "reason": "not_found"}


def test_refund_then_duplicate_rejected():
    api = MockAPI()
    first = api.issue_refund("txn_1001", 40.00)
    assert first["ok"] and first["refund_id"].startswith("rf_")
    assert api.issue_refund("txn_1001", 40.00) == {"ok": False, "reason": "already_refunded"}


def test_refund_rejects_pending_and_partial():
    api = MockAPI()
    assert api.issue_refund("txn_1006", 50.00)["reason"] == "not_settled"
    assert api.issue_refund("txn_1001", 10.00)["reason"] == "amount_mismatch"


def test_escalate_returns_sequential_ticket_ids():
    api = MockAPI()
    assert api.escalate_to_human("c_1001", "x") == {"ticket_id": "TKT-0001"}
    assert api.escalate_to_human(None, "y") == {"ticket_id": "TKT-0002"}
