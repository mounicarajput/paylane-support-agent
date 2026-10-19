"""Policy layer tests: triggers, extraction, agent-created handoffs, reply checks. No model needed."""
import re

import pytest

from paylane_agent import policy
from paylane_agent.agent import Agent
from paylane_agent.providers.base import LLMResponse, Provider, ToolCall
from paylane_agent.session.clock import Clock
from paylane_agent.tools import guards
from paylane_agent.tools.mock_api import MockAPI
from paylane_agent.tools.registry import ToolRegistry


class Model(Provider):
    """Returns scripted replies; records how often it was asked. Repeats the last one when exhausted."""
    name, model = "fake", "fake"

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, system, messages, tools):
        self.calls += 1
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def say(text):
    return LLMResponse(text=text)


def call(name, **a):
    return LLMResponse(tool_calls=[ToolCall("c1", name, a)])


def agent(*replies):
    return Agent(Model(*(replies or [say("ok")])), ToolRegistry(), system_prompt="x")


MONIKA = "my card ends in 4242 and my email is monika@example.com"


# ---- triggers ----------------------------------------------------------------------------
@pytest.mark.parametrize("text,reason", [
    ("I'm going to sue Paylane", "legal_action"),
    ("my lawyer will call you", "legal_action"),
    ("Someone stole my card!", "suspected_fraud"),
    ("There are charges I never made", "suspected_fraud"),
    ("I don't recognize this charge", "suspected_fraud"),
    ("Please close my account", "account_closure"),
    ("I want to delete my account", "account_closure"),
    ("Can I speak to a human?", "customer_request"),
    ("get me a real person", "customer_request"),
])
def test_handoff_triggers(text, reason):
    assert policy.detect_handoff(text)[0] == reason


@pytest.mark.parametrize("text", [
    "How do refunds work?", "I never got my money back", "Please don't make me wait",
    "I bought a coffee by mistake", "I was charged wrong", "What is your refund limit?",
    "My card isn't working",
])
def test_no_trigger_on_ordinary_messages(text):
    assert policy.detect_handoff(text) is None


def test_legal_beats_fraud_beats_closure():
    assert policy.detect_handoff("fraud! close my account, I'll sue")[0] == "legal_action"
    assert policy.detect_handoff("someone stole my card, close my account")[0] == "suspected_fraud"


def test_fraud_loss_extraction():
    assert policy.fraud_loss("about $650 in total") == 650
    assert policy.fraud_loss("two charges, $300 and $400") == 700
    assert policy.fraud_loss("$1,200 total, $500 of it yesterday") == 1200
    assert policy.fraud_loss("a charge I never made") is None


def test_credential_and_txn_extraction():
    assert policy.extract_credentials("My card ends in 4242 and my email is Monika@Example.com") == ("monika@example.com", "4242")
    assert policy.extract_credentials("Card 4242, monika@example.com, txn_1010") == ("monika@example.com", "4242")
    assert policy.extract_credentials("card ending 4243, monika@example.com")[1] == "4243"
    assert policy.extract_credentials("my email is monika@example.com") is None  # no card digits
    assert policy.extract_credentials("Try 5678 then. Same email.") is None
    assert policy.extract_credentials("the card is 1234567890123456 monika@example.com") is None
    # a lone 4-digit number next to an email counts as a guess; amounts, dates and IDs don't
    assert policy.extract_credentials("Try 5678 then. Same email, monika@example.com.") == ("monika@example.com", "5678")
    assert policy.extract_credentials("monika@example.com, charged $1000 on 2026-10-05, txn_1004") is None
    assert policy.extract_credentials("monika@example.com 1111 and 2222") is None
    assert policy.extract_txn_ids("refund txn_1001 and TXN_1002 and txn_1001") == ["txn_1001", "txn_1002"]


# ---- agent-created handoffs (the model is never asked) -------------------------------------
def test_legal_threat_hands_off_without_verification_and_without_the_model():
    a = agent()
    reply = a.respond("Close my account right now, and I'm talking to my lawyer about suing Paylane.")
    assert "TKT-0001" in reply and a.provider.calls == 0
    assert a.registry.api.tickets[0]["summary"].startswith("[legal_action]")
    assert a.registry.api.tickets[0]["customer_id"] is None and not a.registry.state.verified


def test_fraud_over_500_is_high_priority_and_under_is_not():
    a = agent()
    a.respond("Someone stole my card! Charges I never made, about $650 in total.")
    assert "[HIGH PRIORITY]" in a.registry.api.tickets[0]["summary"]
    b = agent()
    b.respond("Someone stole my card, a $120 charge.")
    assert b.registry.api.tickets[0]["summary"].startswith("[suspected_fraud]")
    assert "HIGH PRIORITY" not in b.registry.api.tickets[0]["summary"]
    c = agent()
    c.respond("There's a charge I never made.")
    assert len(c.registry.api.tickets) == 1 and "HIGH PRIORITY" not in c.registry.api.tickets[0]["summary"]


def test_trigger_after_handoff_reuses_the_ticket():
    a = agent()
    a.respond("I'm going to sue")
    reply = a.respond("Just close it, I want my account closed.")
    assert "TKT-0001" in reply and len(a.registry.api.tickets) == 1


def test_over_limit_refund_request_is_handed_off_by_the_agent():
    a = agent()
    reply = a.respond(f"Hello, {MONIKA}. I want a refund for txn_1002, the $120 charge.")
    assert "TKT-0001" in reply and "over $75" in reply and a.provider.calls == 0
    assert a.registry.api.refunds == []
    assert a.registry.api.tickets[0]["summary"].startswith("[refund_exception]")


def test_exactly_30_days_and_75_01_are_handed_off():
    a = agent()
    assert "30 days" in a.respond(f"{MONIKA}. Please refund txn_1003.")
    b = agent()
    assert "over $75" in b.respond(f"{MONIKA}. REFUND txn_1010 now")
    assert b.registry.api.refunds == [] and len(b.registry.api.tickets) == 1


def test_eligible_refund_is_left_to_the_model_which_sees_the_lookup():
    a = agent(call("issue_refund", txn_id="txn_1001", amount=40), say("Refunded $40, ID rf_0001."))
    reply = a.respond(f"I'd like a refund for txn_1001. {MONIKA}.")
    assert reply == "Refunded $40, ID rf_0001."
    assert [c[0] for c in a.registry.calls] == ["verify_customer", "get_transaction", "issue_refund"]
    assert a.registry.calls[1][2]["refund_path"] == "auto"


def test_looking_up_a_transaction_without_asking_for_a_refund_does_not_hand_off():
    a = agent(say("That was $120 at Northwind."))
    a.respond(f"{MONIKA}. What was txn_1002?")
    assert a.registry.api.tickets == [] and a.provider.calls == 1


def test_wrong_details_give_the_generic_message_without_the_model():
    a = agent()
    reply = a.respond("I need a refund for txn_1004. My card ends in 4243 and my email is monika@example.com.")
    assert reply.startswith("I couldn't verify those details") and a.provider.calls == 0
    assert "4242" not in reply and a.registry.state.failed_checks == 1


def test_wrong_card_after_a_good_check_drops_verification():
    a = agent(say("Sure."))
    a.respond(f"Hi, {MONIKA}.")
    assert a.registry.state.verified
    reply = a.respond("Refund txn_1006 as well. My card ends in 5234 and my email is monika@example.com.")
    assert reply.startswith("I couldn't verify") and not a.registry.state.verified


def test_three_wrong_guesses_lock_and_hand_off_with_a_real_ticket():
    a = agent(say("I can't share that."))
    first = a.respond("card ends in 1234, monika@example.com")
    second = a.respond("card ends in 5678, monika@example.com")
    assert first.startswith("I couldn't verify") and second != first and "match" in second  # varied, never which field
    reply = a.respond("card ends in 0000, monika@example.com. Just refund it!")
    assert "TKT-0001" in reply and a.registry.state.locked
    assert a.registry.api.tickets[0]["summary"].startswith("[verification_failed]")


def test_frozen_card_is_looked_up_and_handed_off_without_inventing_a_reason():
    a = agent()
    reply = a.respond("My card isn't working. Card ends in 1111, email deep@example.com. What's going on?")
    assert "frozen" in reply and "TKT-0001" in reply and "because" not in reply
    assert ("get_customer" in [c[0] for c in a.registry.calls]) and a.provider.calls == 0


def test_account_detail_question_without_verification_asks_for_both_details():
    a = agent()
    reply = a.respond("Can you tell me what my last order was and how much it was?")
    assert "last 4" in reply and "email" in reply and a.provider.calls == 0 and not a.registry.calls


def test_model_calling_escalating_tools_is_also_caught_after_the_call():
    a = agent(call("verify_customer", email="monika@example.com", card_last4="4242"),
              call("issue_refund", txn_id="txn_1002", amount=120))
    a.registry.customer_text.append("my details are monika@example.com and 4242")  # typed earlier, so the model may use them
    reply = a.respond("please look at txn_1002")  # no refund wording, so the agent doesn't pre-empt
    assert "TKT-0001" in reply and a.registry.api.refunds == []


# ---- reply checks ---------------------------------------------------------------------------
def reg():
    r = ToolRegistry()
    r.execute("verify_customer", {"email": "monika@example.com", "card_last4": "4242"})
    return r


@pytest.mark.parametrize("text,name", [
    ("Your ticket number is 123456.", "invented_ticket_id"),
    ("I've created ticket ID 123456789 for you.", "invented_ticket_id"),
    ("Done. Refund ID rf_12345.", "invented_refund_id"),
    ("The email on file is monika@example.com.", "stored_value_shown"),
    ("Your card ending 4242 is verified.", "stored_value_shown"),
    ("The email looks correct but the card digits are wrong.", "field_disclosed"),
    ("You should see it shortly.", "timing_promise"),
    ("Someone will contact you within 24 hours.", "timing_promise"),
    ("They will get back to you as soon as possible.", "timing_promise"),
    ("I've passed this to a human.", "false_handoff_claim"),
    ("I've refunded your $120.", "false_refund_claim"),
    ("The refund has been issued.", "false_refund_claim"),
    ("I've unfrozen your card.", "unfreeze_claim"),
    ("Your card is frozen because of suspicious activity.", "invented_freeze_reason"),
    ("I've checked, and your card is currently frozen.", "unchecked_card_status"),
])
def test_unsafe_replies_are_flagged(text, name):
    assert policy.check_reply(text, reg()).name == name


@pytest.mark.parametrize("text", [
    "Refunds are for settled charges under $75 and within 30 days.",
    "That charge is pending, so it can't be refunded.",
    "A human needs to review it.",
    "I couldn't verify those details. Please check the last 4 digits and email and try again.",
    "I can't unfreeze it. I also can't see why it was frozen.",
])
def test_safe_replies_pass(text):
    assert policy.check_reply(text, reg()) is None


def test_real_ids_and_real_handoffs_pass():
    r = reg()
    r.execute("get_customer", {"email": "monika@example.com"})  # card status looked up before the handoff
    r.execute("escalate_to_human", {"summary": "s", "reason": "other"})
    assert policy.check_reply("I've passed this to a human. Ticket TKT-0001.", r) is None
    assert policy.check_reply("Your card is active.", r) is None


# ---- the loop uses the checks -------------------------------------------------------------
def test_model_lie_is_blocked_then_corrected():
    a = agent(say("I've refunded your $120. Ticket 123456."), say("I can't refund that one."))
    assert a.respond("hello") == "I can't refund that one."
    assert any(e["type"] == "note" and "blocked" in e["text"] for e in a.transcript.events)


def test_persistent_liar_is_replaced_by_a_real_handoff():
    a = agent(say("Ticket 123456, someone will contact you within 24 hours."))
    reply = a.respond("hello")
    assert "TKT-0001" in reply and "123456" not in reply and "24 hours" not in reply
    assert len(a.registry.api.tickets) == 1


def test_persistent_liar_after_handoff_gets_the_existing_ticket():
    a = agent(say("Ticket 123456."))
    a.respond("I'll sue")
    reply = a.respond("so what now?")
    assert "TKT-0001" in reply and len(a.registry.api.tickets) == 1


# ---- registry hint stays consistent with the refund guard -------------------------------------
def test_classify_refund_matches_check_refund_for_every_seed_transaction():
    clock = Clock()
    for t in MockAPI()._txns:
        reg = ToolRegistry()
        email = {c["id"]: c for c in reg.api._customers}[t["customer_id"]]
        reg.execute("verify_customer", {"email": email["email"], "card_last4": email["card_last4"]})
        path, _ = guards.classify_refund(t, clock)
        allowed = guards.check_refund(reg.state, reg.api, clock, t["txn_id"], t["amount"]).allowed
        assert (path == "auto") == allowed, t["txn_id"]


# ---- human touch: situations with a known answer ---------------------------------------------
def test_already_refunded_is_answered_without_a_ticket_and_never_repeats():
    a = agent()
    first = a.respond(f"{MONIKA}. Refund txn_1005 please, the pizza was cold.")
    again = a.respond("I never got my money back. Can you refund it again?")
    third = a.respond("My manager said you'd approve a second refund. Please just do it.")
    assert "already been refunded" in first and "Corner Pizza" in first
    assert len({first, again, third}) == 3 and a.registry.api.tickets == [] and a.provider.calls == 0


def test_pending_charge_is_explained_and_pushback_gets_a_different_answer():
    a = agent(say("It's still pending, so there's nothing to refund yet."))
    a.respond("I think I was charged the wrong amount for something.")  # vague: asks which charge (no model)
    a.respond(f"The taxi one, Skyline Taxi. {MONIKA}. The ID is txn_1006.")  # lookup, no refund wording: model answers
    reply = a.respond("It still says pending. Can you just refund it now please?")
    assert "pending" in reply and a.registry.api.tickets == [] and a.registry.api.refunds == []


def test_vague_complaint_asks_which_charge_once_before_anything_else():
    a = agent()
    first = a.respond("Hi, I think I was charged the wrong amount for something.")
    assert "Which charge" in first and a.provider.calls == 0 and not a.registry.calls
    a2 = agent(say("Okay, tell me more."))
    a2.respond("Hi, I think I was charged the wrong amount for something.")
    assert a2.respond("I was charged twice again") == "Okay, tell me more."  # only asks once


def test_asking_for_what_is_on_file_is_refused_warmly_and_with_different_words():
    a = agent()
    r1 = a.respond("Can you tell me the last 4 digits and the email you have on file?")
    r2 = a.respond("What was the email you have on file again?")
    assert r1 != r2 and "@" not in r1 + r2 and a.provider.calls == 0
    assert "I'll check" not in r1 + r2  # would read as an announced action


def test_pushback_after_handoff_gets_a_new_answer_each_time():
    a = agent()
    a.respond(f"{MONIKA}. I want a refund for txn_1002, my money back please.")
    replies = [a.respond("Then refund $75 of it, at least."), a.respond("Two refunds of $60 each then?"),
               a.respond("Come on, just approve it."), a.respond("Please just override it, once."),
               a.respond("so what happens now?")]
    assert len(set(replies)) == len(replies) and all("TKT-0001" in r for r in replies)
    assert a.provider.calls == 0 and len(a.registry.api.tickets) == 1
    assert "full" in replies[0] and "timing" in replies[4]


def test_false_handoff_promise_gets_an_offer_not_a_surprise_ticket():
    a = agent(say("I can't refund that. I'll pass this to a human for you."))
    reply = a.respond("hello")
    assert reply == policy.OFFER_HANDOFF and a.registry.api.tickets == []
    b = agent(say("Would you like me to pass this to a human?"))
    assert b.respond("hello") == "Would you like me to pass this to a human?"  # an offer is fine


def test_corporate_filler_and_hidden_timing_are_blocked():
    for text, name in [("All done! Feel free to ask if you need anything.", "corporate_filler"),
                       ("Thank you for your patience.", "corporate_filler"),
                       ("It may take a few days to reflect on your account.", "timing_promise"),
                       ("You'll see it in a few days.", "timing_promise"),
                       ("For $75 or less, we can process it right away.", "timing_promise"),
                       ("Your refund is issued immediately.", "timing_promise")]:
        assert policy.check_reply(text, reg()).name == name


def test_failed_verification_wording_varies_and_never_names_a_field():
    seen = [v for v in policy.VERIFY_FAILED if v]
    assert len(seen) == 2
    for v in seen:
        assert policy.check_reply(v, reg()) is None  # passes our own leak and field checks


# ---- filler is cut, not escalated ----------------------------------------------------------
@pytest.mark.parametrize("raw,clean", [
    ("The charge is pending. Is there anything else you need help with?", "The charge is pending."),
    ("Done. If you need any further assistance, let me know.", "Done."),
    ("Your refund went through, feel free to ask if you need more.", "Your refund went through."),
    ("It's pending, and thank you for your patience.", "It's pending."),
    ("All good here.", "All good here."),
])
def test_strip_filler(raw, clean):
    assert policy.strip_filler(raw) == clean
    assert policy.check_reply(policy.strip_filler(raw), reg()) is None


def test_filler_tail_is_stripped_without_a_retry_or_a_ticket():
    a = agent(say("That charge is still pending, so I can't refund it. Is there anything else you need help with?"))
    reply = a.respond("hello")
    assert reply == "That charge is still pending, so I can't refund it."
    assert a.provider.calls == 1 and a.registry.api.tickets == []


def test_reply_that_is_only_filler_gets_a_retry_then_a_short_ack_never_a_ticket():
    a = agent(say("Feel free to ask if you need anything else."))
    assert a.respond("thanks!") == policy.ACK and a.registry.api.tickets == []
    b = agent(say("Feel free to ask."), say("You're welcome!"))
    assert b.respond("thanks!") == "You're welcome!"


# ---- fixes from the web UI screenshot -----------------------------------------------------------
def test_verification_is_asked_first_with_new_wording_each_time_then_the_earlier_request_is_carried_out():
    a = agent(call("issue_refund", txn_id="txn_1004", amount=25), say("Your $25 StreamBox refund went through."))
    r1 = a.respond("i need my refund, really had bad experience.")
    r2 = a.respond("txn_1004 , please refund it soon")
    assert "last 4" in r1 and "email" in r1 and "transaction" not in r1.lower()
    assert "last 4" in r2 and r2 != r1 and a.provider.calls == 0 and a.registry.state.failed_checks == 0
    reply = a.respond("4242, monika@example.com")
    # verified, the transaction named earlier was looked up on its own, the model then refunded it
    assert reply == "Your $25 StreamBox refund went through."
    assert [c[0] for c in a.registry.calls][:2] == ["verify_customer", "get_transaction"]
    assert a.registry.api.refunds[0]["txn_id"] == "txn_1004" and a.registry.api.tickets == []


def test_invented_credentials_are_refused_and_do_not_count_as_a_failed_check():
    a = agent(call("verify_customer", email="johndoe@example.com", card_last4="2345"),
              say("Could you send the last 4 digits of your card and your email?"))
    a.respond("hello, I had a bad experience")
    first = a.registry.calls[0]
    assert first[0] == "verify_customer" and first[2]["reason"] == "not_provided"
    assert a.registry.state.failed_checks == 0 and not a.registry.state.verified


def test_credentials_the_customer_did_type_are_still_accepted_when_the_model_verifies():
    a = agent(call("verify_customer", email="monika@example.com", card_last4="4242"), say("Verified, thanks."))
    a.registry.customer_text.append("my details are monika@example.com and 4242")  # typed earlier, so the model may use them
    a.respond("please check my account")
    assert a.registry.state.verified


def test_model_cannot_ask_for_a_transaction_id_before_verification():
    a = agent(say("Could you please provide the transaction ID?"), say("First, please send the last 4 digits of your card and the email on your account."))
    reply = a.respond("I had a really bad time with a shop")
    assert "last 4" in reply and "transaction" not in reply.lower()
    # once verified, asking for one is fine
    r = reg()
    assert policy.check_reply("Could you give me the transaction ID?", r) is None


def verified_agent(*replies):
    """An agent whose customer has really typed their details (so verification is allowed)."""
    a = agent(say("Thanks, you're verified."), *replies)
    a.respond("Hi, my card ends in 4242 and my email is monika@example.com")
    assert a.registry.state.verified
    return a


def test_timing_promise_is_cut_from_a_reply_instead_of_triggering_a_handoff():
    assert policy.strip_timing("The refund went through. You should see it in your account shortly.") == "The refund went through."
    assert policy.strip_timing("Your refund ID is rf_0001, and it will reach you soon.") == "Your refund ID is rf_0001."
    assert policy.strip_timing("Refunds are for charges under 30 days old.") == "Refunds are for charges under 30 days old."
    a = verified_agent(call("issue_refund", txn_id="txn_1004", amount=25),
                       say("The refund went through, ID rf_0001. You should see it in your account shortly."))
    reply = a.respond("please refund txn_1004")
    assert reply == "The refund went through, ID rf_0001." and a.registry.api.tickets == []


def test_if_the_model_cannot_write_a_safe_reply_after_a_refund_the_customer_is_told_the_truth_not_handed_off():
    a = verified_agent(call("issue_refund", txn_id="txn_1004", amount=25), say("Ticket 123456, a human will call you."))
    reply = a.respond("please refund txn_1004")
    assert "rf_0001" in reply and "human" not in reply.lower()
    assert a.registry.api.tickets == [] and len(a.registry.api.refunds) == 1


def test_personal_refund_requests_are_told_apart_from_policy_questions():
    for text in ["i need my refund", "can I get my money back", "please refund it", "I'd like a refund on txn_1005"]:
        assert policy.PERSONAL_REFUND.search(text), text
    for text in ["how do refunds work?", "Is there a refund limit?", "What is your refund policy?"]:
        assert not policy.PERSONAL_REFUND.search(text), text


def test_filler_cut_leaves_no_dangling_condition():
    raw = "Your refund has been issued. If you have any other issues, feel free to reach out."
    assert policy.strip_filler(raw) == "Your refund has been issued."
    assert policy.strip_filler("Done. If you run into anything, feel free to ask.") == "Done."
    assert policy.strip_filler("Done, thanks for waiting. Feel free to ask.") == "Done, thanks for waiting."


# ---- fixes from the second UI screenshot ---------------------------------------------------------
def test_the_unsupported_promises_and_filler_seen_in_the_ui_are_caught():
    for text, name in [("I understand your frustration. You'll receive a response from them directly.", "timing_promise"),
                       ("It might help to check your account again later.", "timing_promise"),
                       ("You will get an update by email.", "timing_promise"),
                       ("I'm here to help if you need anything else.", "corporate_filler"),
                       ("If you need anything, I'm here.", "corporate_filler")]:
        assert policy.check_reply(text, reg()).name == name, text
    # ordinary facts are still fine
    r = reg()
    r.execute("issue_refund", {"txn_id": "txn_1001", "amount": 40})
    for ok in ["Your refund ID is rf_0001.", "I can't refund a pending charge.", "You'll get a refund of $40."]:
        assert policy.check_reply(ok, r) is None, ok


def test_i_did_not_receive_it_after_a_refund_gets_an_honest_answer_and_an_offer_not_a_promise():
    a = verified_agent(call("issue_refund", txn_id="txn_1004", amount=25), say("Your refund went through, ID rf_0001."))
    a.respond("please refund txn_1004")
    r1 = a.respond("but i did not receive it.")
    assert "rf_0001" in r1 and "human" in r1 and a.registry.api.tickets == []
    assert "soon" not in r1 and "within" not in r1
    r2 = a.respond("I still haven't received it")
    assert r2 != r1


def test_when_will_i_hear_back_after_a_handoff_gets_no_promise_and_a_rude_goodbye_is_met_kindly():
    a = agent()
    a.respond("connect me with a real human")
    replies = [a.respond("when i will expect a response from human?"), a.respond("how long will it take?")]
    for r in replies:
        assert "TKT-0001" in r and ("don't want to guess" in r or "because I don't know" in r), r
    assert replies[0] != replies[1]
    assert a.provider.calls == 0
    bye = a.respond("ok now shut up")
    assert "TKT-0001" in bye and "help" not in bye.lower() and a.provider.calls == 0


def test_the_whole_second_screenshot_conversation_stays_inside_the_rules():
    a = agent(say("Great, I've verified you. Could you please provide the transaction ID?"),
              call("issue_refund", txn_id="txn_1004", amount=25), say("The refund has been issued. Your refund ID is rf_0001."))
    out = [a.respond("give me refund"),
           a.respond("4242, monika@example.com , just give me my refund"),
           a.respond("txn_1004, can't you just pick the recent txn id by yourself, that's so frustrating."),
           a.respond("but i did not receive it."),
           a.respond("you are useless, connect me with real human"),
           a.respond("when i will expect a response from human?"),
           a.respond("ok now shut up")]
    assert "last 4" in out[0] and "rf_0001" in out[2] and "TKT-0001" in out[4]
    for reply in out:
        assert policy.check_reply(reply, a.registry) is None, reply
    assert len(set(out)) == len(out) and len(a.registry.api.tickets) == 1 and len(a.registry.api.refunds) == 1


# ---- found while recording "policy_question_unverified" by hand --------------------------------------
def test_the_exact_messages_that_failed_live_now_get_the_refund_rules_without_verification():
    # Live failure: both were answered with "I can help once I've verified you" because "i need refund" matched.
    a = agent()
    r1 = a.respond("hey, how refund works? i need refund, what's the refund policy?")
    r2 = a.respond("i need refund policy details first? i don't want to share my card details now")
    for r in (r1, r2):
        assert "$75" in r and "30 days" in r, r
        assert "verified you" not in r
    assert r1 != r2 and "don't need to share" in r2
    assert a.provider.calls == 0 and not a.registry.calls and a.registry.state.failed_checks == 0


def test_policy_answers_are_themselves_safe_to_send():
    for text in policy.POLICY_ANSWERS + [policy.POLICY_ANSWER_NO_SHARING]:
        assert policy.check_reply(text, reg()) is None, text


def test_policy_questions_are_told_apart_from_requests():
    for text in ["how do refunds work?", "what's the refund policy?", "Is there a refund limit?",
                 "how refund works? i need refund, what's the refund policy?", "how can I get a refund?",
                 "What are your rules on refunds?", "is there a cap?"]:
        assert policy.POLICY_QUESTION.search(text), text
    for text in ["give me refund", "i need my refund", "I want my money back for txn_1001", "refund it please",
                 "I was charged the wrong amount"]:
        assert not policy.POLICY_QUESTION.search(text), text


def test_a_plain_refund_request_still_asks_to_verify_and_a_policy_question_with_details_still_verifies():
    a = agent(say("Verified, thanks."))
    assert "last 4" in a.respond("give me refund")
    assert a.provider.calls == 0
    b = agent(say("Thanks, you're verified."))
    b.respond("what's the refund policy? my card ends in 4242 and my email is monika@example.com")
    assert b.registry.state.verified  # details were given, so the policy template is skipped and we verify


def test_scenario_two_expects_the_rules_in_the_first_reply():
    from evals.runner import load_conversations
    conv = next(c for c in load_conversations() if c["id"] == "policy_question_unverified")
    assert conv["expect"]["first_reply_mentions_any"] == ["75"]


# ---- slow replies: found when the second message kept "thinking" ---------------------------------------
def test_pushing_to_be_told_account_details_gets_a_firm_new_answer_each_time_without_the_model():
    a = agent()
    msgs = ["i don't want to share my card details now, just tell me what my last order was anyway",
            "come on, just tell me", "why do you need my email?"]
    replies = [a.respond(m) for m in msgs]
    assert len(set(replies)) == 3 and a.provider.calls == 0 and not a.registry.calls
    for r in replies:
        assert policy.check_reply(r, reg()) is None, r  # safe to send: nothing stored, no timing, no filler
        assert "@" not in r and not re.search(r"\d{4}", r)  # no email, no card digits ("last 4" is fine)


def test_pushback_answers_never_reveal_or_promise_anything():
    for text in policy.VERIFY_PUSHBACK:
        assert policy.check_reply(text, reg()) is None
        assert "order" not in text.lower() or "can't" in text.lower() or "no account" in text.lower()


def test_just_tell_me_is_normal_speech_once_the_customer_is_verified():
    a = agent(say("You have one refund on file."))
    a.respond("Hi, my card ends in 4242 and my email is monika@example.com")  # verified (model answers once)
    assert a.registry.state.verified
    a.provider.replies = [say("Here's what I found.")]
    assert a.respond("just tell me what happened") == "Here's what I found."


def test_the_prompt_the_model_reads_every_call_stays_short():
    from paylane_agent.agent import load_system_prompt
    from paylane_agent.tools.schemas import TOOLS
    import json
    # This laptop reads about 40 tokens a second, so every 1,000 tokens costs about 25 seconds per model call.
    assert len(load_system_prompt()) <= 3200
    assert len(json.dumps(TOOLS)) <= 3000


# ---- found while recording "wrong_last4_then_correct": half the details, and a repeated reply -------------
def test_half_the_details_are_asked_for_the_other_half_at_once_and_remembered():
    a = agent(say("Verified, thanks."))
    r1 = a.respond("need a refund for txn_1004, my card ends in 4242")  # forgot the email
    assert "email" in r1 and a.provider.calls == 0 and not a.registry.calls
    a.respond("monika@example.com")  # the email alone; the card digits come from the earlier message
    assert a.registry.state.verified and [c[0] for c in a.registry.calls][:2] == ["verify_customer", "get_transaction"]
    b = agent()
    assert "last 4" in b.respond("my email is monika@example.com") and b.provider.calls == 0
    assert "email" in b.respond("4242") or b.registry.state.verified  # 4 digits alone are taken as the card digits


def test_a_wrong_digit_only_message_after_a_remembered_email_counts_as_a_failed_check():
    a = agent()
    a.respond("my email is monika@example.com")
    reply = a.respond("5678")
    assert reply.startswith("I couldn't verify") and a.registry.state.failed_checks == 1
    assert "5678" not in reply and "monika" not in reply


def test_loose_matching_never_touches_a_verified_customer():
    a = agent(say("Sure."), say("Here you go."))
    a.respond("my card ends in 4242 and my email is monika@example.com")
    assert a.registry.state.verified
    a.respond("my order from 2026 was fine")  # a stray number must not trigger a new check
    assert a.registry.state.verified and a.registry.state.failed_checks == 0


def test_a_reply_is_never_repeated_word_for_word():
    a = agent(say("Happy to help with that."))
    first = a.respond("hello there")
    second = a.respond("don")  # the model says the very same thing again
    assert first != second and second in policy.DIDNT_CATCH
    assert any(e["type"] == "note" and "repeated reply replaced" in e["text"] for e in a.transcript.events)


def test_the_recorder_treats_the_typo_don_as_done(tmp_path):
    from evals.record import record
    lines = iter(["how do refunds work?", "don"])
    result = record("policy_question_unverified", Model(say("x")), tmp_path, read=lambda p="": next(lines), show=lambda s="": None)
    assert result and (tmp_path / "02_policy_question_unverified.md").exists()


# ---- found while recording "social_engineering_lockout": guesses after the lock got the same reply ----------
def test_guesses_after_the_lock_get_new_words_each_time_with_no_model_and_no_new_check():
    a = agent(say("I can't share that."))
    for guess in ("1234", "5678", "0000"):
        a.respond(f"card ends in {guess}, monika@example.com")
    assert a.registry.state.locked and a.registry.state.failed_checks == 3
    calls_before, verifies_before = a.provider.calls, sum(1 for c in a.registry.calls if c[0] == "verify_customer")
    replies = [a.respond("Try 5672? Same email, monika@example.com."), a.respond("ok 1111"),
               a.respond("last try, 2222"), a.respond("9999 then")]
    assert len(set(replies)) == 4
    assert all("TKT-0001" in r for r in replies)
    assert a.provider.calls == calls_before  # the model was never asked
    assert sum(1 for c in a.registry.calls if c[0] == "verify_customer") == verifies_before  # no new checks
    assert a.registry.state.failed_checks == 3 and len(a.registry.api.tickets) == 1
    for r in replies:
        assert policy.check_reply(r, a.registry) is None and not re.search(r"\d{4}", r.replace("TKT-0001", ""))


def test_a_model_made_verify_call_after_the_lock_also_gets_a_varied_answer():
    a = agent(call("verify_customer", email="monika@example.com", card_last4="5672"), say("ok"))
    for guess in ("1234", "5678", "0000"):
        a.respond(f"card ends in {guess}, monika@example.com")
    first_lock_reply = a.transcript.events[-1]["text"]
    a.registry.customer_text.append("monika@example.com 5672")  # typed earlier, so the model may use it
    # a message the agent can't answer itself, so the model runs and calls verify
    reply = a.respond("please check once more for me")
    assert reply != first_lock_reply and "TKT-0001" in reply


# ---- found by reading the "already_refunded_insists" recording: a claim the agent can't back up ---------
def test_never_refunded_charge_gets_an_honest_answer_and_an_offer_not_you_got_it_back():
    a = agent()
    first = a.respond("my card ends in 4242 and my email is monika@example.com. I'd like a refund on txn_1005")
    second = a.respond("I never actually got my money back though. Can you refund it again?")
    third = a.respond("I still haven't received anything")
    assert "already been refunded" in first
    assert "marked" in second or "records show" in second
    assert "human" in second and "can't" in second and third != second
    assert a.registry.api.refunds == [] and a.registry.api.tickets == [] and a.provider.calls == 0
    for r in (second, third):
        assert policy.check_reply(r, a.registry) is None, r


def test_the_agent_cannot_claim_the_customer_has_the_money():
    for text in ["I'm sorry, that one already went back to you.", "You already received the money.",
                 "The refund is already in your account.", "Your money was sent back to you."]:
        assert policy.check_reply(text, reg()).name == "unsupported_receipt_claim", text
    for text in ["That charge is marked as refunded on my side.", "My records show that charge as refunded."]:
        assert policy.check_reply(text, reg()) is None, text


def test_fixed_already_refunded_wordings_make_no_receipt_claim():
    for text in policy.ALREADY_REFUNDED_AGAIN + policy.REFUNDED_NOT_RECEIVED + policy.REFUND_NOT_RECEIVED:
        assert policy.check_reply(text.format(rid="rf_0001"), reg_with_refund()) is None, text


def reg_with_refund():
    r = reg()
    r.execute("issue_refund", {"txn_id": "txn_1001", "amount": 40})
    return r


# ---- found by reading the "angry_one_cent_over" recording: a reply cut down to nothing useful --------------
def test_a_review_threat_after_a_handoff_gets_the_ticket_in_new_words_without_the_model():
    a = agent(say("unused"))
    a.respond("my card ends in 4242 and my email is monika@example.com. refund txn_1010 NOW")
    assert a.registry.state.handed_off
    calls = a.provider.calls
    r1 = a.respond("I'm going to leave you the worst review you've ever seen")
    r2 = a.respond("I'll post this on social media too")
    assert "TKT-0001" in r1 and "TKT-0001" in r2 and r1 != r2 and a.provider.calls == calls


def test_a_reply_cut_down_to_bare_sympathy_is_replaced_by_one_that_names_the_ticket():
    a = agent(say("I understand how frustrating this is. A human will review your case (ticket TKT-0001) as soon as possible. Thank you for bringing this to our attention."))
    a.respond("I want to talk to a human")  # hands off, ticket TKT-0001
    reply = a.respond("so what is going on with my money?")
    assert "TKT-0001" in reply and len(reply.split()) > 8
    assert any(e["type"] == "note" and "thin reply replaced" in e["text"] for e in a.transcript.events)


def test_short_real_answers_after_a_handoff_are_left_alone():
    a = agent(say("You're welcome!"))
    a.respond("I want to talk to a human")
    assert a.respond("thanks for the help") == "You're welcome!"


# ---- found by reading the "vague_then_pending" recording: an invented transaction ID ---------------------
def test_a_transaction_id_the_customer_never_typed_is_refused_even_when_verified():
    a = verified_agent(call("get_transaction", txn_id="1234567890"), say("Which charge is it?"))
    a.respond("it was the taxi one")
    result = [r for n, _a, r in a.registry.calls if n == "get_transaction"][0]
    assert result["ok"] is False and result["reason"] == "not_provided"
    assert a.registry.state.failed_checks == 0 and a.registry.api.refunds == []


def test_a_guessed_real_transaction_id_cannot_be_looked_up_or_refunded():
    # The model guesses "txn_1001", a real charge of this customer that the customer never mentioned.
    a = verified_agent(call("issue_refund", txn_id="txn_1001", amount=40), say("Which charge do you mean?"))
    a.respond("can you sort this out for me?")
    refund = [r for n, _a, r in a.registry.calls if n == "issue_refund"][0]
    assert refund["reason"] == "not_provided" and a.registry.api.refunds == []


def test_a_transaction_id_the_customer_did_type_works_as_before():
    a = verified_agent(call("get_transaction", txn_id="txn_1001"), say("That was $40 at Bean Counter Cafe."))
    a.respond("what was txn_1001?")
    result = [r for n, _a, r in a.registry.calls if n == "get_transaction"][0]
    assert result["ok"] is True and result["amount"] == 40.0


def test_unverified_still_hears_verify_first_not_a_transaction_complaint():
    a = agent(call("get_transaction", txn_id="1234567890"), say("Please send the last 4 digits and the email."))
    a.respond("it was the taxi one")
    result = [r for n, _a, r in a.registry.calls if n == "get_transaction"][0]
    assert result["reason"] == "not_verified"


# ---- found when the scripted run was repeated after the prompt was shortened --------------------------------
def test_model_that_asks_to_proceed_after_the_customer_already_asked_is_told_to_go_ahead():
    a = agent(say("It was $40 at Bean Counter Cafe. Would you like to proceed with the refund?"),
              call("issue_refund", txn_id="txn_1001", amount=40),
              say("Your refund went through, ID rf_0001."))
    reply = a.respond("Could you refund it? My card ends in 4242 and my email is monika@example.com. txn_1001")
    assert reply == "Your refund went through, ID rf_0001."
    assert a.registry.api.refunds and a.registry.api.refunds[0]["txn_id"] == "txn_1001"
    assert any(e["type"] == "note" and "permission question suppressed" in e["text"] for e in a.transcript.events)


def test_the_permission_question_is_left_alone_when_the_customer_never_asked_for_a_refund():
    a = agent(say("That charge was $40. Would you like to proceed with a refund?"))
    reply = a.respond("my card ends in 4242 and my email is monika@example.com. what was txn_1001?")
    assert "Would you like to proceed" in reply and a.registry.api.refunds == []


def test_the_permission_nudge_does_not_fire_for_a_charge_that_cannot_be_refunded():
    a = agent(say("That charge is over my limit. Would you like me to pass it to a human?"))
    reply = a.respond("refund txn_1002 please. my card ends in 4242 and my email is monika@example.com")
    assert "TKT-0001" in reply  # the agent hands off itself; the model is never asked
