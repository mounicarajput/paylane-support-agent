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
        call("verify_customer", email="monika@example.com", card_last4="4242"),
        call("issue_refund", txn_id="txn_1001", amount=40),
        LLMResponse(text="Done, refunded."),
    ])
    agent = Agent(p, ToolRegistry(), system_prompt="x")
    assert agent.respond("refund txn_1001 for monika@example.com, numbers 4242 and 1234") == "Done, refunded."
    assert [c[0] for c in agent.registry.calls] == ["verify_customer", "issue_refund"]
    assert agent.registry.api.refunds[0]["txn_id"] == "txn_1001"
    kinds = [e["type"] for e in agent.transcript.events]
    assert kinds == ["user", "tool_call", "tool_result", "tool_call", "tool_result", "assistant"]


def test_stalled_reply_is_suppressed_and_model_nudged_to_act():
    p = Scripted([
        call("verify_customer", email="monika@example.com", card_last4="4242"),
        LLMResponse(text="Verified. Let's check the transaction now."),  # stalls
        call("issue_refund", txn_id="txn_1001", amount=40),
        LLMResponse(text="Refunded $40."),
    ])
    agent = Agent(p, ToolRegistry(), system_prompt="x")
    assert agent.respond("refund txn_1001 for monika@example.com, numbers 4242 and 1234") == "Refunded $40."
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


def test_ollama_provider_ignores_proxy_settings_and_says_why_it_failed(monkeypatch):
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    import pytest
    from paylane_agent.providers.base import ProviderError
    from paylane_agent.providers.ollama_provider import OllamaProvider

    class FakeOllama(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            body = json.dumps({"message": {"role": "assistant", "content": "hello from ollama"}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), FakeOllama)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        # A dead proxy in the environment (as on some corporate laptops) must not matter for a local server.
        for name in ("HTTP_PROXY", "http_proxy", "HTTPS_PROXY", "https_proxy", "ALL_PROXY"):
            monkeypatch.setenv(name, "http://127.0.0.1:9")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        p = OllamaProvider("qwen2.5:7b", f"http://127.0.0.1:{server.server_port}", timeout=5)
        assert p.chat("x", [{"role": "user", "content": "hi"}], []).text == "hello from ollama"
    finally:
        server.shutdown()
        server.server_close()

    dead = OllamaProvider("qwen2.5:7b", "http://127.0.0.1:9", timeout=2)  # nothing listens on port 9
    with pytest.raises(ProviderError) as e:
        dead.chat("x", [{"role": "user", "content": "hi"}], [])
    assert "Cannot reach Ollama at http://127.0.0.1:9" in str(e.value) and "Error" in str(e.value)


def test_ollama_provider_keeps_the_model_loaded_and_waits_long_enough():
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from paylane_agent.config import Config
    from paylane_agent.providers.factory import get_provider

    seen = {}

    class Capture(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            out = json.dumps({"message": {"role": "assistant", "content": "ok"}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Capture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        cfg = Config(ollama_host=f"http://127.0.0.1:{server.server_port}")
        provider = get_provider(cfg)
        assert provider.timeout >= 900  # was 300, which a cold 7B model on a laptop could exceed
        provider.chat("x", [{"role": "user", "content": "hi"}], [])
        assert seen["body"]["keep_alive"] == "60m"  # otherwise Ollama unloads the model after ~5 idle minutes
        assert seen["body"]["options"]["num_ctx"] == 4096  # a smaller context uses less of a nearly full RAM
    finally:
        server.shutdown()
        server.server_close()


def test_thinking_notice_appears_only_when_the_work_is_slow():
    import time

    from paylane_agent.progress import thinking

    quick, slow = [], []
    with thinking(quick.append, after=0.3):
        pass
    time.sleep(0.5)
    with thinking(slow.append, after=0.1, every=10):
        time.sleep(0.4)
    assert quick == [] and len(slow) == 1 and "thinking" in slow[0]
