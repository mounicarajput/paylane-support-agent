"""Agent loop tests with a scripted fake provider (no model needed)."""
from paylane_agent.agent import FALLBACK, Agent
from paylane_agent.providers.base import LLMResponse, Provider, ToolCall
from paylane_agent.providers.anthropic_provider import AnthropicProvider
from paylane_agent.tools.registry import ToolRegistry


class Scripted(Provider):
    name, model = "fake", "fake"

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []

    def chat(self, system, messages, tools):
        self.seen.append(len(messages))
        return self.replies.pop(0) if self.replies else LLMResponse(tool_calls=[ToolCall("x", "get_transaction", {"txn_id": "t"})])


def call(name, **args):
    return LLMResponse(tool_calls=[ToolCall("c1", name, args)])


def test_tool_loop_runs_tools_then_answers():
    p = Scripted([
        call("verify_customer", email="alice@example.com", card_last4="4242"),
        call("issue_refund", txn_id="txn_1001", amount=40),
        LLMResponse(text="Done, refunded."),
    ])
    agent = Agent(p, ToolRegistry(), system_prompt="x")
    assert agent.respond("refund txn_1001") == "Done, refunded."
    assert [c[0] for c in agent.registry.calls] == ["verify_customer", "issue_refund"]
    assert agent.registry.api.refunds[0]["txn_id"] == "txn_1001"
    kinds = [e["type"] for e in agent.transcript.events]
    assert kinds == ["user", "tool_call", "tool_result", "tool_call", "tool_result", "assistant"]


def test_stalled_reply_is_suppressed_and_model_nudged_to_act():
    p = Scripted([
        call("verify_customer", email="alice@example.com", card_last4="4242"),
        LLMResponse(text="Verified. Let's check the transaction now."),  # stalls
        call("issue_refund", txn_id="txn_1001", amount=40),
        LLMResponse(text="Refunded $40."),
    ])
    agent = Agent(p, ToolRegistry(), system_prompt="x")
    assert agent.respond("refund txn_1001") == "Refunded $40."
    assert agent.registry.api.refunds[0]["txn_id"] == "txn_1001"
    assert [e["text"] for e in agent.transcript.events if e["type"] == "assistant"] == ["Refunded $40."]
    assert any(e["type"] == "note" for e in agent.transcript.events)


def test_persistent_staller_gives_up_after_two_nudges():
    stall = LLMResponse(text="I'll check that now.")
    agent = Agent(Scripted([stall, stall, stall]), ToolRegistry(), system_prompt="x")
    assert agent.respond("hi") == "I'll check that now."
    assert sum(e["type"] == "note" for e in agent.transcript.events) == 2


def test_guard_blocks_even_if_model_tries_refund():
    p = Scripted([call("issue_refund", txn_id="txn_1001", amount=40), LLMResponse(text="Sorry, can't.")])
    agent = Agent(p, ToolRegistry(), system_prompt="x")
    agent.respond("refund me")
    assert agent.registry.api.refunds == []


def test_runaway_tool_loop_fails_safe_to_human():
    agent = Agent(Scripted([]), ToolRegistry(), system_prompt="x")
    assert agent.respond("hi") == FALLBACK
    assert agent.registry.state.handed_off


def test_anthropic_message_conversion_groups_tool_results():
    msgs = [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "", "tool_calls": [ToolCall("a", "x", {}), ToolCall("b", "y", {})]},
        {"role": "tool", "tool_call_id": "a", "name": "x", "content": "{}"},
        {"role": "tool", "tool_call_id": "b", "name": "y", "content": "{}"},
    ]
    wire = AnthropicProvider._to_wire(msgs)
    assert [m["role"] for m in wire] == ["user", "assistant", "user"]
    assert len(wire[2]["content"]) == 2
