"""Local web chat for the agent. Standard library only.

    python -m paylane_agent serve [--port 8000] [--provider anthropic] [--hide-internals]

One Agent (own registry, state and transcript) per browser session. Binds to 127.0.0.1.
A user can paste an Anthropic API key in the UI for faster replies. The key lives in server
memory for that browser session only: never written to disk, logged, or sent back to the browser.
"""
import json
import re
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import parse_qs, urlparse

from ..agent import Agent
from ..config import Config
from ..providers.base import Provider, ProviderError
from ..tools.registry import ToolRegistry
from ..transcript import Transcript

INDEX = Path(__file__).parent / "static" / "index.html"
SESSION_ID = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_BODY = 20_000
MAX_MESSAGE = 1_000
MAX_SESSIONS = 200


def _default_anthropic_factory(api_key: str) -> Provider:
    from ..providers.anthropic_provider import AnthropicProvider
    c = Config.from_env()
    return AnthropicProvider(c.anthropic_model, api_key, c.temperature, c.max_tokens)


class _Session:
    def __init__(self, provider: Provider):
        self.transcript = Transcript({"provider": provider.name, "model": provider.model, "mode": "web"})
        self.agent = Agent(provider, ToolRegistry(), transcript=self.transcript)
        self.lock = threading.Lock()  # one turn at a time per customer; local models are slow


class ChatApp:
    def __init__(self, provider: Provider, hide_internals: bool = False,
                 anthropic_factory: Optional[Callable[[str], Provider]] = None):
        self.default_provider, self.hide_internals = provider, hide_internals
        self._anthropic_factory = anthropic_factory or _default_anthropic_factory
        self._sessions: "OrderedDict[str, _Session]" = OrderedDict()
        self._overrides: "OrderedDict[str, Provider]" = OrderedDict()  # sid -> provider holding a user key
        self._lock = threading.Lock()

    def _provider_for(self, sid: Optional[str]) -> Provider:
        return self._overrides.get(sid, self.default_provider)

    def info(self, sid: Optional[str] = None) -> dict:
        with self._lock:
            p = self._provider_for(sid)
            return {"provider": p.name, "model": p.model, "show_internals": not self.hide_internals,
                    "local": p.name == "ollama", "user_key": sid in self._overrides}

    def _session(self, sid: str) -> _Session:
        with self._lock:
            if sid not in self._sessions:
                self._sessions[sid] = _Session(self._provider_for(sid))
                while len(self._sessions) > MAX_SESSIONS:
                    self._sessions.popitem(last=False)
            self._sessions.move_to_end(sid)
            return self._sessions[sid]

    def reset(self, sid: str) -> None:
        """New conversation. The chosen provider (and key) is kept."""
        with self._lock:
            self._sessions.pop(sid, None)

    def use_anthropic(self, sid: str, api_key: str) -> dict:
        key = (api_key or "").strip()
        if len(key) < 20:
            raise ProviderError("That doesn't look like an Anthropic API key.")
        try:
            provider = self._anthropic_factory(key)
            provider.validate()
        except ProviderError as e:
            raise ProviderError(str(e).replace(key, "[key]")) from None
        self._set_provider(sid, provider)
        return self.info(sid)

    def use_local(self, sid: str) -> dict:
        with self._lock:
            self._overrides.pop(sid, None)
        self._set_provider(sid, self.default_provider, store=False)
        return self.info(sid)

    def _set_provider(self, sid: str, provider: Provider, store: bool = True) -> None:
        with self._lock:
            if store:
                self._overrides[sid] = provider
                self._overrides.move_to_end(sid)
                while len(self._overrides) > MAX_SESSIONS:
                    self._overrides.popitem(last=False)
            session = self._sessions.get(sid)
        if session:  # keep the conversation, change the model behind it
            with session.lock:
                session.agent.provider = provider
                session.transcript.meta.update(provider=provider.name, model=provider.model)

    def chat(self, sid: str, message: str) -> dict:
        s = self._session(sid)
        with s.lock:
            start = len(s.transcript.events)
            reply = s.agent.respond(message)
            state = s.agent.registry.state
            out = {"reply": reply}
            if not self.hide_internals:
                out["tools"] = [
                    {"name": e["name"], "arguments": e["arguments"]} if e["type"] == "tool_call"
                    else {"name": e["name"], "result": e["result"]}
                    for e in s.transcript.events[start:] if e["type"] in ("tool_call", "tool_result")]
                out["state"] = {"verified": state.verified, "failed_checks": state.failed_checks,
                                "locked": state.locked, "ticket_id": state.handoff_ticket_id}
            return out


def make_handler(app: ChatApp):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # keep the console quiet; request bodies are never logged
            pass

        def _send(self, code: int, body: bytes, ctype: str = "application/json") -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, data: dict) -> None:
            self._send(code, json.dumps(data).encode())

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/index.html"):
                self._send(200, INDEX.read_bytes(), "text/html; charset=utf-8")
            elif url.path == "/api/info":
                sid = parse_qs(url.query).get("sid", [""])[0]
                self._json(200, app.info(sid if SESSION_ID.match(sid) else None))
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length > MAX_BODY:
                    return self._json(413, {"error": "request too large"})
                data = json.loads(self.rfile.read(length) or b"{}")
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "bad request"})
            sid = data.get("session_id", "") if isinstance(data, dict) else ""
            if not isinstance(sid, str) or not SESSION_ID.match(sid):
                return self._json(400, {"error": "bad session id"})

            if self.path == "/api/reset":
                app.reset(sid)
                return self._json(200, {"ok": True})
            if self.path == "/api/provider":
                return self._provider(sid, data)
            if self.path == "/api/chat":
                message = data.get("message")
                if not isinstance(message, str) or not message.strip():
                    return self._json(400, {"error": "empty message"})
                try:
                    return self._json(200, app.chat(sid, message.strip()[:MAX_MESSAGE]))
                except ProviderError as e:
                    return self._json(503, {"error": str(e)})
            self._json(404, {"error": "not found"})

        def _provider(self, sid: str, data: dict) -> None:
            choice = data.get("provider")
            try:
                if choice == "anthropic":
                    key = data.get("api_key")
                    if not isinstance(key, str):
                        return self._json(400, {"error": "api_key required"})
                    return self._json(200, app.use_anthropic(sid, key))
                if choice == "ollama":
                    return self._json(200, app.use_local(sid))
            except ProviderError as e:
                return self._json(400, {"error": str(e)})
            self._json(400, {"error": "provider must be 'anthropic' or 'ollama'"})

    return Handler


def serve(provider: Provider, host: str = "127.0.0.1", port: int = 8000, hide_internals: bool = False):
    server = ThreadingHTTPServer((host, port), make_handler(ChatApp(provider, hide_internals)))
    print(f"Paylane support chat ({provider.name}: {provider.model}) at http://{host}:{server.server_port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
