"""After a refund went through, short follow-ups get a fresh, accurate answer without the model."""
from paylane_agent.agent import Agent
from paylane_agent.providers.base import LLMResponse, Provider, ToolCall
from paylane_agent.tools.registry import ToolRegistry


class Model(Provider):
    name, model = "fake", "fake"

    def __init__(self, *replies):
        self.replies, self.calls = list(replies), 0

    def chat(self, system, messages, tools):
        self.calls += 1
        return self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]


def refunded_agent():
    a = Agent(Model(LLMResponse(tool_calls=[ToolCall("c", "issue_refund", {"txn_id": "txn_1001", "amount": 40})]),
                    LLMResponse(text="Your refund went through.")), ToolRegistry(), system_prompt="x")
    a.respond("Refund txn_1001 please. My card ends in 4242 and my email is alice@example.com.")
    assert a.registry.api.refunds
    return a


def test_go_ahead_after_the_refund_is_answered_with_the_real_refund_id_not_a_repeat():
    a = refunded_agent()
    calls = a.provider.calls
    reply = a.respond("Yes please, go ahead :)")
    assert "rf_0001" in reply and a.provider.calls == calls and len(a.registry.api.refunds) == 1


def test_thanks_gets_a_different_answer_each_time():
    a = refunded_agent()
    replies = [a.respond("Perfect, thank you so much!"), a.respond("thanks again"), a.respond("cheers")]
    assert len(set(replies)) == 3


def test_a_new_request_after_a_refund_still_goes_to_the_normal_flow():
    a = refunded_agent()
    a.provider.replies = [LLMResponse(text="Sure, which one?")]
    assert a.respond("Can I refund another one too?") == "Sure, which one?"  # 6 words, but no go-ahead or thanks
    calls = a.provider.calls
    a.provider.replies = [LLMResponse(text="Looking at txn_1004.")]
    assert a.respond("Yes txn_1004 please") == "Looking at txn_1004."  # a transaction ID: not a follow-up
    assert a.provider.calls == calls + 1


def test_no_followup_shortcut_before_any_refund():
    a = Agent(Model(LLMResponse(text="Hello! How can I help?")), ToolRegistry(), system_prompt="x")
    assert a.respond("yes please") == "Hello! How can I help?"
