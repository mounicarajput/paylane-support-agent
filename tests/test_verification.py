from paylane_agent.session.state import SessionState
from paylane_agent.session.verification import GENERIC_FAILURE, LOCKED_MESSAGE, verify
from paylane_agent.tools.mock_api import MockAPI


def test_both_match_verifies():
    s = SessionState()
    r = verify(s, MockAPI(), "alice@example.com", "4242")
    assert r.ok and s.verified and s.customer_id == "c_1001"


def test_wrong_last4_generic_and_no_leak():
    s = SessionState()
    r = verify(s, MockAPI(), "alice@example.com", "0000")
    assert not r.ok and not s.verified and s.failed_checks == 1
    assert r.message == GENERIC_FAILURE
    assert "4242" not in r.message and "alice" not in r.message.lower()


def test_wrong_email_same_message_as_wrong_last4():
    a = verify(SessionState(), MockAPI(), "alice@example.com", "0000")
    b = verify(SessionState(), MockAPI(), "nobody@example.com", "4242")
    assert a.message == b.message


def test_last4_of_another_customer_fails():
    s = SessionState()
    assert not verify(s, MockAPI(), "alice@example.com", "1111").ok


def test_reverify_with_wrong_card_fails_and_drops_verification():
    # Bug seen in the web UI: second check with a wrong card returned ok "Already verified."
    s, api = SessionState(), MockAPI()
    assert verify(s, api, "alice@example.com", "4242").ok
    r = verify(s, api, "alice@example.com", "5234")
    assert not r.ok and r.message == GENERIC_FAILURE
    assert not s.verified and s.customer_id is None and s.failed_checks == 1


def test_reverify_with_wrong_email_fails_and_drops_verification():
    s, api = SessionState(), MockAPI()
    verify(s, api, "alice@example.com", "4242")
    r = verify(s, api, "nobody@example.com", "4242")
    assert not r.ok and r.message == GENERIC_FAILURE and not s.verified


def test_reverify_with_same_correct_details_stays_verified():
    s, api = SessionState(), MockAPI()
    verify(s, api, "alice@example.com", "4242")
    assert verify(s, api, "alice@example.com", "4242").ok and s.customer_id == "c_1001"


def test_verified_session_cannot_switch_to_another_customer():
    s, api = SessionState(), MockAPI()
    verify(s, api, "alice@example.com", "4242")
    r = verify(s, api, "chloe@example.com", "9876")  # valid details, but a different customer
    assert not r.ok and not s.verified and s.customer_id is None


def test_three_failures_lock_and_block_even_correct_details():
    s, api = SessionState(), MockAPI()
    for _ in range(3):
        r = verify(s, api, "alice@example.com", "0000")
    assert s.locked and r.locked and r.message == LOCKED_MESSAGE
    r = verify(s, api, "alice@example.com", "4242")
    assert not r.ok and not s.verified
