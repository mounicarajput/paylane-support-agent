"""The recorder: you type as the customer, the conversation is checked and saved. No model needed."""
import json

from evals.record import caught_failures, list_scenarios, record
from evals.runner import load_conversations
from paylane_agent.providers.base import LLMResponse, Provider


class Model(Provider):
    name, model = "fake", "fake-1"

    def __init__(self, *replies):
        self.replies = list(replies)

    def chat(self, system, messages, tools):
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def typed(*lines):
    it = iter(lines)
    return lambda prompt="": next(it)


def run(tmp_path, scenario, provider, *lines):
    shown = []
    result = record(scenario, provider, tmp_path, read=typed(*lines), show=shown.append)
    return result, "\n".join(shown)


def test_a_typed_over_limit_conversation_is_saved_checked_and_explained(tmp_path):
    result, shown = run(tmp_path, "over_limit_pushback", Model(LLMResponse(text="Okay.")),
                        "Hello, my card ends in 4242, email monika@example.com. I want my money back for txn_1002.",
                        "ok then refund $75 of it",
                        "done")
    saved = (tmp_path / "05_over_limit_pushback.md").read_text(encoding="utf-8")
    assert result["passed"] is True, result["checks"]
    for section in ("## Conversation", "## Checks", "## Failures caught and how they were handled"):
        assert section in saved
    assert "TKT-0001" in saved and "over $75" in saved and "typed live in the CLI" in saved
    assert "You were:" in saved and "Monika" in saved and "result: **PASS**" in saved
    assert "Saved to" in shown


def test_failures_the_safety_layer_caught_are_written_up_in_plain_words(tmp_path):
    # The model lies about a refund and promises timing. The layer blocks it and the saved file explains why.
    lie = LLMResponse(text="I've refunded it. Ticket 123456, someone will contact you within 24 hours.")
    run(tmp_path, "policy_question_unverified", Model(lie), "hello, can you help me with something?", "done")
    saved = (tmp_path / "02_policy_question_unverified.md").read_text(encoding="utf-8")
    assert "**Failure:**" in saved and "said a refund happened when none did" in saved
    assert "**Handled:**" in saved and "123456" in saved  # what the model tried to say is kept as evidence
    conversation = saved.split("## Conversation")[1].split("## Checks")[0]
    agent_lines = [line for line in conversation.splitlines() if line.startswith("**Agent:**")]
    assert agent_lines and not any("123456" in line or "24 hours" in line for line in agent_lines)


def test_tool_refusals_are_listed_as_guard_actions():
    events = [{"type": "tool_result", "name": "issue_refund",
               "result": {"ok": False, "reason": "over_limit", "detail": "Refunds above $75 need a human."}}]
    caught = caught_failures(events)
    assert caught and "over $75" in caught[0][0] and "guard" in caught[0][1]


def test_no_failures_says_so(tmp_path):
    run(tmp_path, "policy_question_unverified", Model(LLMResponse(text="Refunds are for charges under $75.")),
        "how do refunds work?", "done")
    saved = (tmp_path / "02_policy_question_unverified.md").read_text(encoding="utf-8")
    assert "None. Every reply the model wrote passed" in saved


def test_quit_saves_nothing_and_unknown_scenarios_are_listed(tmp_path):
    result, shown = run(tmp_path, "simple_refund", Model(LLMResponse(text="hi")), "hello", "quit")
    assert result == {} and not list(tmp_path.glob("*.md")) and "Nothing saved" in shown
    result, shown = run(tmp_path, "nope", Model(LLMResponse(text="hi")))
    assert result == {} and "legal_and_closure" in shown


def test_report_counts_recordings_and_does_not_present_a_partial_score_as_final(tmp_path):
    run(tmp_path, "policy_question_unverified", Model(LLMResponse(text="Refunds are for charges under $75.")),
        "how do refunds work?", "done")
    store = json.loads((tmp_path / "results.json").read_text(encoding="utf-8"))
    assert list(store) == ["policy_question_unverified"]
    report = (tmp_path / "report.md").read_text(encoding="utf-8")
    assert "1 of 12 recorded so far" in report and "MET" not in report


def test_every_scenario_has_a_brief_to_guide_the_person_typing():
    for c in load_conversations():
        assert c["brief"]["you_are"] and c["brief"]["goal"], c["id"]


def test_listing_shows_all_twelve_scenarios():
    shown = []
    list_scenarios(shown.append)
    assert sum(1 for line in shown if line.strip().startswith("[")) == 12


def test_if_the_model_cannot_be_reached_nothing_is_saved_and_the_user_is_told(tmp_path):
    from paylane_agent.providers.base import ProviderError

    class Down(Provider):
        name, model = "ollama", "qwen2.5:7b"

        def chat(self, system, messages, tools):
            raise ProviderError("Cannot reach Ollama at http://127.0.0.1:11434 (ConnectionRefusedError: refused).")

    result, shown = run(tmp_path, "simple_refund", Down(), "Hi, I was charged $40 and want it back", "done")
    assert result == {} and not list(tmp_path.iterdir())  # no transcript, no report, no results file
    assert "Cannot reach Ollama" in shown and "nothing was saved" in shown


def test_a_person_who_gives_their_details_one_message_at_a_time_is_not_failed_for_it(tmp_path):
    # The script gives everything in message 1; a real customer often does not. Same outcome, so it must pass.
    from paylane_agent.providers.base import ToolCall

    model = Model(LLMResponse(tool_calls=[ToolCall("c", "issue_refund", {"txn_id": "txn_1001", "amount": 40})]),
                  LLMResponse(text="Your refund went through, ID rf_0001."))
    result, _ = run(tmp_path, "simple_refund", model,
                    "Hi, I think I was charged the wrong amount for something.",
                    "It was $40 at Bean Counter Cafe. My card ends in 4242 and my email is monika@example.com, txn_1001.",
                    "done")
    failed = [c for c in result["checks"] if not c["ok"]]
    assert result["passed"] is True, failed
    assert not any(c["name"] == "tools_in_turn" for c in result["checks"])
