"""Web server tests with a scripted fake model (no Ollama needed)."""
import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from paylane_agent.providers.base import LLMResponse, Provider, ProviderError, ToolCall
from paylane_agent.web.server import ChatApp, make_handler

SID = "test-session-0001"


class Fake(Provider):
    name, model = "fake", "fake-1"

    def __init__(self, replies):
        self.replies = list(replies)

    def chat(self, system, messages, tools):
        r = self.replies.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def server():
    started = []

    def start(provider, hide=False, factory=None):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(ChatApp(provider, hide, factory)))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        started.append(srv)
        return f"http://127.0.0.1:{srv.server_port}"

    yield start
    for s in started:
        s.shutdown()
        s.server_close()


def post(url, path, data):
    req = urllib.request.Request(url + path, json.dumps(data).encode(), {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.load(e)


def test_index_and_info(server):
    url = server(Fake([]))
    html = urllib.request.urlopen(url + "/").read().decode()
    assert "Paylane Support" in html
    info = json.load(urllib.request.urlopen(url + "/api/info"))
    assert info == {"provider": "fake", "model": "fake-1", "show_internals": True,
                    "local": False, "user_key": False}


def test_chat_returns_reply_tools_and_state(server):
    url = server(Fake([
        LLMResponse(tool_calls=[ToolCall("c", "verify_customer", {"email": "alice@example.com", "card_last4": "4242"})]),
        LLMResponse(text="You're verified."),
    ]))
    code, data = post(url, "/api/chat", {"session_id": SID, "message": "hi 4242 alice@example.com"})
    assert code == 200 and data["reply"] == "You're verified."
    assert [t["name"] for t in data["tools"]] == ["verify_customer", "verify_customer"]
    assert data["state"]["verified"] is True
    assert "4242" not in json.dumps(data["state"])


def test_sessions_are_isolated_and_reset_clears(server):
    url = server(Fake([
        LLMResponse(tool_calls=[ToolCall("c", "verify_customer", {"email": "alice@example.com", "card_last4": "4242"})]),
        LLMResponse(text="ok"), LLMResponse(text="other"), LLMResponse(text="again"),
    ]))
    post(url, "/api/chat", {"session_id": SID, "message": "a"})
    _, other = post(url, "/api/chat", {"session_id": "another-session-02", "message": "b"})
    assert other["state"]["verified"] is False
    post(url, "/api/reset", {"session_id": SID})
    _, fresh = post(url, "/api/chat", {"session_id": SID, "message": "c"})
    assert fresh["state"]["verified"] is False


def test_hide_internals_omits_tools_and_state(server):
    url = server(Fake([LLMResponse(text="hello")]), hide=True)
    _, data = post(url, "/api/chat", {"session_id": SID, "message": "hi"})
    assert data == {"reply": "hello"}


def test_bad_input_rejected(server):
    url = server(Fake([]))
    assert post(url, "/api/chat", {"session_id": "x", "message": "hi"})[0] == 400
    assert post(url, "/api/chat", {"session_id": SID, "message": "   "})[0] == 400
    assert post(url, "/api/chat", {"session_id": SID})[0] == 400
    assert post(url, "/api/nope", {"session_id": SID})[0] == 404


def test_model_down_gives_503_not_crash(server):
    url = server(Fake([ProviderError("Cannot reach Ollama")]))
    code, data = post(url, "/api/chat", {"session_id": SID, "message": "hi"})
    assert code == 503 and "Ollama" in data["error"]


# ---- user-supplied Anthropic key ----
KEY = "sk-ant-test-key-1234567890abcdef"


class FakeAnthropic(Fake):
    name, model = "anthropic", "claude-fake"


def test_user_key_switches_model_and_is_never_echoed(server):
    fast = FakeAnthropic([LLMResponse(text="from anthropic")])
    url = server(Fake([LLMResponse(text="from local")]), factory=lambda key: fast)
    info = json.load(urllib.request.urlopen(f"{url}/api/info?sid={SID}"))
    assert info["provider"] == "fake" and info["user_key"] is False

    code, data = post(url, "/api/provider", {"session_id": SID, "provider": "anthropic", "api_key": KEY})
    assert code == 200 and data["provider"] == "anthropic" and data["user_key"] is True
    assert KEY not in json.dumps(data)
    code, chat = post(url, "/api/chat", {"session_id": SID, "message": "hi"})
    assert chat["reply"] == "from anthropic" and KEY not in json.dumps(chat)
    got = json.load(urllib.request.urlopen(f"{url}/api/info?sid={SID}"))
    assert got["provider"] == "anthropic" and KEY not in json.dumps(got)


def test_key_is_per_session_and_reset_keeps_it(server):
    fast = FakeAnthropic([LLMResponse(text="a1"), LLMResponse(text="a2")])
    url = server(Fake([LLMResponse(text="local")]), factory=lambda key: fast)
    post(url, "/api/provider", {"session_id": SID, "provider": "anthropic", "api_key": KEY})
    other = json.load(urllib.request.urlopen(f"{url}/api/info?sid=another-session-02"))
    assert other["user_key"] is False and other["provider"] == "fake"
    post(url, "/api/reset", {"session_id": SID})
    assert json.load(urllib.request.urlopen(f"{url}/api/info?sid={SID}"))["provider"] == "anthropic"


def test_switching_mid_conversation_keeps_history_and_can_go_back(server):
    fast = FakeAnthropic([LLMResponse(text="fast reply")])
    url = server(Fake([LLMResponse(text="slow reply"), LLMResponse(text="slow again")]), factory=lambda key: fast)
    assert post(url, "/api/chat", {"session_id": SID, "message": "one"})[1]["reply"] == "slow reply"
    post(url, "/api/provider", {"session_id": SID, "provider": "anthropic", "api_key": KEY})
    assert post(url, "/api/chat", {"session_id": SID, "message": "two"})[1]["reply"] == "fast reply"
    code, back = post(url, "/api/provider", {"session_id": SID, "provider": "ollama"})
    assert code == 200 and back["user_key"] is False and back["provider"] == "fake"
    assert post(url, "/api/chat", {"session_id": SID, "message": "three"})[1]["reply"] == "slow again"


def test_bad_key_rejected_and_scrubbed_from_error(server):
    def factory(key):
        raise ProviderError(f"Anthropic rejected {key}")

    url = server(Fake([]), factory=factory)
    code, data = post(url, "/api/provider", {"session_id": SID, "provider": "anthropic", "api_key": KEY})
    assert code == 400 and KEY not in json.dumps(data)
    assert json.load(urllib.request.urlopen(f"{url}/api/info?sid={SID}"))["user_key"] is False


def test_provider_endpoint_input_validation(server):
    url = server(Fake([]), factory=lambda key: FakeAnthropic([]))
    assert post(url, "/api/provider", {"session_id": SID, "provider": "anthropic"})[0] == 400
    assert post(url, "/api/provider", {"session_id": SID, "provider": "anthropic", "api_key": "short"})[0] == 400
    assert post(url, "/api/provider", {"session_id": SID, "provider": "nope"})[0] == 400
    assert post(url, "/api/provider", {"session_id": "x", "provider": "ollama"})[0] == 400


def test_page_has_theme_toggle_key_button_and_local_speed_note(server):
    html = urllib.request.urlopen(server(Fake([])) + "/").read().decode()
    assert 'data-theme="dark"' in html and "prefers-color-scheme" in html
    assert "Add Anthropic API key for fast responses" in html
    assert "anywhere from several seconds to a couple of minutes" in html
