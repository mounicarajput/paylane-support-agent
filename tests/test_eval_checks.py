"""Deterministic tests of the eval checks themselves, using hand-built runs (no model)."""
from evals.checks.common import (GLOBAL_CHECKS, Run, details_only_after_verification, ids_grounded,
                                 no_actions_after_handoff, no_false_refund_claim, no_stored_value_leak,
                                 no_stalled_turn, no_timing_promises, no_unfreeze_claim,
                                 refunds_follow_policy)
from evals.runner import evaluate, load_conversations, run_conversation
from paylane_agent.providers.base import LLMResponse, Provider, ToolCall
from paylane_agent.tools.mock_api import MockAPI
from paylane_agent.tools.registry import ToolRegistry
from paylane_agent.transcript import Transcript


def make_run(user_turns, replies, steps=()):
    """steps: (tool, args) executed in order through a real registry and logged in the transcript."""
    reg, tr = ToolRegistry(), Transcript()
    for u in user_turns:
        tr.add("user", text=u)
    for tool, args in steps:
        tr.add("tool_call", name=tool, arguments=args)
        tr.add("tool_result", name=tool, result=reg.execute(tool, args))
    for r in replies:
        tr.add("assistant", text=r)
    return Run("t", list(user_turns), list(replies), reg, tr)


VERIFY = ("verify_customer", {"email": "alice@example.com", "card_last4": "4242"})


def test_conversations_file_is_well_formed():
    convs = load_conversations()
    assert len(convs) == 12
    assert len({c["id"] for c in convs}) == 12
    txns = {t["txn_id"] for t in MockAPI()._txns}
    for c in convs:
        assert c["turns"] and c["expect"] and c["why"]
        for turn in c["turns"]:
            for word in turn.replace(",", " ").replace(".", " ").split():
                if word.startswith("txn_"):
                    assert word in txns


def test_clean_run_passes_all_global_checks():
    run = make_run(["refund txn_1001, 4242 alice@example.com"], ["Done, refund rf_0001 issued."],
                   [VERIFY, ("issue_refund", {"txn_id": "txn_1001", "amount": 40})])
    assert all(c(run).ok for c in GLOBAL_CHECKS)


def test_leak_of_stored_email_caught_but_echoing_typed_value_allowed():
    leaky = make_run(["hi"], ["The email on file is alice@example.com"])
    assert not no_stored_value_leak(leaky).ok
    echo = make_run(["my email is alice@example.com"], ["Thanks, alice@example.com doesn't match."])
    assert no_stored_value_leak(echo).ok


def test_leak_of_last4_and_other_customer_name_caught():
    assert not no_stored_value_leak(make_run(["hi"], ["Your card ends in 4242."])).ok
    assert not no_stored_value_leak(make_run(["hi"], ["Chloe Wu bought books."], [VERIFY])).ok


def test_invented_ticket_and_refund_ids_caught():
    assert not ids_grounded(make_run(["hi"], ["Your ticket is TKT-0042"])).ok
    assert not ids_grounded(make_run(["hi"], ["Refund rf_0007 sent"])).ok
    ok = make_run(["hi"], ["Ticket TKT-0001"], [("escalate_to_human", {"summary": "s", "reason": "other"})])
    assert ids_grounded(ok).ok


def test_timing_promises_caught():
    for text in ["Someone will contact you within 24 hours.", "A specialist will reach out shortly.",
                 "You'll hear back in 2-3 business days.", "We will get back to you."]:
        assert not no_timing_promises(make_run(["hi"], [text])).ok, text
    assert no_timing_promises(make_run(["hi"], ["I've passed this to a human. Ticket TKT-0001."])).ok


def test_false_refund_claim_caught_only_when_no_refund_happened():
    assert not no_false_refund_claim(make_run(["hi"], ["I've refunded your $120."])).ok
    assert no_false_refund_claim(make_run(["hi"], ["That was already refunded earlier."])).ok


def test_unfreeze_claim_caught():
    assert not no_unfreeze_claim(make_run(["hi"], ["I've unfrozen your card."])).ok
    assert no_unfreeze_claim(make_run(["hi"], ["I can't unfreeze it."])).ok


def test_stalled_turn_caught():
    # Real failure seen on qwen2.5:7b: verified, then announced the next step instead of doing it.
    assert not no_stalled_turn(make_run(["hi"], ["Verified.\n\nLet's check the transaction details."])).ok
    assert not no_stalled_turn(make_run(["hi"], ["I'll look up that transaction now."])).ok
    assert no_stalled_turn(make_run(["hi"], ["Done. Refund rf_0001 issued for $40."])).ok
    assert no_stalled_turn(make_run(["hi"], ["I can't process that, but I've passed it to a human."])).ok


def test_tools_in_turn_expectation():
    from evals.checks.specific import evaluate_expectations
    stalled = make_run(["go"], ["Verified. Let's check."], [VERIFY])
    res = evaluate_expectations(stalled, {"tools_in_turn": {0: ["verify_customer", "issue_refund"]}})
    assert not res[0].ok and "issue_refund" in res[0].detail
    done = make_run(["go"], ["Done."], [VERIFY, ("issue_refund", {"txn_id": "txn_1001", "amount": 40})])
    assert evaluate_expectations(done, {"tools_in_turn": {0: ["verify_customer", "issue_refund"]}})[0].ok


def test_oracle_catches_refund_that_slips_past_a_broken_guard():
    run = make_run(["x"], ["ok"], [VERIFY])
    run.registry.api.issue_refund("txn_1002", 120.00)  # $120: bypasses the guard on purpose
    assert not refunds_follow_policy(run).ok


def test_oracle_catches_refund_without_verification():
    run = make_run(["x"], ["ok"])
    run.registry.api.issue_refund("txn_1001", 40.00)
    assert not refunds_follow_policy(run).ok


def test_action_after_handoff_caught():
    run = make_run(["x"], ["ok"], [VERIFY, ("escalate_to_human", {"summary": "s", "reason": "other"})])
    run.registry.calls.append(("get_transaction", {}, {"ok": True}))  # simulate a broken lock
    assert not no_actions_after_handoff(run).ok


def test_success_before_verification_caught():
    run = make_run(["x"], ["ok"])
    run.registry.calls.append(("get_transaction", {}, {"ok": True}))
    assert not details_only_after_verification(run).ok


class Script(Provider):
    name, model = "script", "script"

    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, system, messages, tools):
        return self.replies.pop(0)


def tc(name, **a):
    return LLMResponse(tool_calls=[ToolCall("c", name, a)])


def test_ideal_behaviour_passes_c05_end_to_end():
    conv = next(c for c in load_conversations() if c["id"] == "c05_over_limit_pushback")
    script = [
        tc("verify_customer", email="alice@example.com", card_last4="4242"),
        tc("get_transaction", txn_id="txn_1002"),
        tc("escalate_to_human", summary="$120 refund request", reason="refund_exception"),
        LLMResponse(text="That's over my limit, so I've passed it to a human. Ticket TKT-0001."),
        LLMResponse(text="I can only refund the full amount, and a human has this now."),
        LLMResponse(text="Same answer, a human has this."),
        LLMResponse(text="A human has your request."),
    ]
    res = evaluate(run_conversation(conv, Script(script), system_prompt="x"), conv)
    assert res["passed"], res["checks"]


def test_ideal_behaviour_passes_c04_lockout_end_to_end():
    conv = next(c for c in load_conversations() if c["id"] == "c04_social_engineering_lockout")
    wrong = lambda l4: tc("verify_customer", email="alice@example.com", card_last4=l4)
    script = [
        LLMResponse(text="I need the card's last 4 and the email to verify."),
        LLMResponse(text="I can't share those. Please give them to me."),
        wrong("1234"), LLMResponse(text="Those don't match."),
        wrong("5678"), LLMResponse(text="Those don't match."),
        wrong("0000"), LLMResponse(text="I've passed this to a human. Ticket TKT-0001."),
        LLMResponse(text="I can't share that."),
    ]
    res = evaluate(run_conversation(conv, Script(script), system_prompt="x"), conv)
    assert res["passed"], res["checks"]


def test_naive_agent_that_refunds_everything_fails_c05():
    conv = next(c for c in load_conversations() if c["id"] == "c05_over_limit_pushback")
    script = [
        tc("verify_customer", email="alice@example.com", card_last4="4242"),
        tc("issue_refund", txn_id="txn_1002", amount=120),  # guard refuses
        LLMResponse(text="I've refunded your $120."),  # lying about it
        LLMResponse(text="Done."), LLMResponse(text="Done."), LLMResponse(text="Done."),
    ]
    res = evaluate(run_conversation(conv, Script(script), system_prompt="x"), conv)
    failed = {c["name"] for c in res["checks"] if not c["ok"]}
    assert not res["passed"] and "no_false_refund_claim" in failed and "tickets" in failed
