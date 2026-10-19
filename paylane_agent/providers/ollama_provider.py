"""PRIMARY provider: open-source model served locally by Ollama (no API key)."""
import json
import urllib.error
import urllib.request

from .base import LLMResponse, Provider, ProviderError, ToolCall


class OllamaProvider(Provider):
    name = "ollama"

    def __init__(self, model: str, host: str, temperature: float = 0.0, seed: int = 7,
                 max_tokens: int = 1024, timeout: int = 300):
        self.model, self.host, self.timeout = model, host.rstrip("/"), timeout
        self.options = {"temperature": temperature, "seed": seed, "num_predict": max_tokens, "num_ctx": 8192}
        # Ollama runs on this machine. Never send its traffic through a (corporate) proxy.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def chat(self, system: str, messages: list, tools: list) -> LLMResponse:
        body = {
            "model": self.model,
            "stream": False,
            "options": self.options,
            "messages": [{"role": "system", "content": system}] + [self._to_wire(m) for m in messages],
            "tools": [{"type": "function", "function": t} for t in tools],
        }
        req = urllib.request.Request(
            f"{self.host}/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        try:
            with self._opener.open(req, timeout=self.timeout) as resp:
                data = json.load(resp)
        except urllib.error.HTTPError as e:
            raise ProviderError(f"Ollama error {e.code}: {e.read().decode(errors='replace')[:300]}") from e
        except (urllib.error.URLError, OSError) as e:  # refused, timed out, reset, unreachable
            reason = getattr(e, "reason", None) or e
            raise ProviderError(
                f"Cannot reach Ollama at {self.host} ({type(reason).__name__}: {reason}). "
                f"Is it running, and did you `ollama pull {self.model}`?") from e

        msg = data.get("message", {})
        calls = []
        for i, c in enumerate(msg.get("tool_calls") or []):
            fn = c.get("function", {})
            args = fn.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None  # registry reports invalid_arguments
            calls.append(ToolCall(id=f"call_{i}", name=fn.get("name", ""), arguments=args))
        return LLMResponse(text=(msg.get("content") or "").strip(), tool_calls=calls)

    @staticmethod
    def _to_wire(m: dict) -> dict:
        if m["role"] == "assistant" and m.get("tool_calls"):
            return {
                "role": "assistant",
                "content": m.get("content", ""),
                "tool_calls": [{"function": {"name": c.name, "arguments": c.arguments or {}}} for c in m["tool_calls"]],
            }
        if m["role"] == "tool":
            return {"role": "tool", "tool_name": m["name"], "content": m["content"]}
        return {"role": m["role"], "content": m["content"]}
