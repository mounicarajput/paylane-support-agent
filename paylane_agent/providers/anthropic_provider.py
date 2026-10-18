"""OPTIONAL provider: Anthropic Sonnet. Used only when PROVIDER=anthropic and a key is set."""
from .base import LLMResponse, Provider, ProviderError, ToolCall


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str, api_key: str, temperature: float = 0.0, max_tokens: int = 1024):
        try:
            import anthropic  # optional dependency
        except ImportError as e:
            raise ProviderError("Install the optional dependency: pip install anthropic") from e
        if not api_key:
            raise ProviderError("PROVIDER=anthropic needs ANTHROPIC_API_KEY.")
        self._anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model, self.temperature, self.max_tokens = model, temperature, max_tokens

    def validate(self) -> None:
        """Listing models is free and fails fast on a bad key."""
        try:
            self.client.models.list(limit=1)
        except self._anthropic.AuthenticationError as e:
            raise ProviderError("Anthropic rejected that API key.") from e
        except self._anthropic.APIError as e:
            raise ProviderError(f"Could not check the key with Anthropic: {e}") from e

    def chat(self, system: str, messages: list, tools: list) -> LLMResponse:
        try:
            resp = self.client.messages.create(
                model=self.model,
                system=system,
                max_tokens=self.max_tokens,
                temperature=self.temperature,
                messages=self._to_wire(messages),
                tools=[{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
                       for t in tools],
            )
        except self._anthropic.APIError as e:
            raise ProviderError(f"Anthropic API error: {e}") from e
        text = "".join(b.text for b in resp.content if b.type == "text").strip()
        calls = [ToolCall(id=b.id, name=b.name, arguments=b.input) for b in resp.content if b.type == "tool_use"]
        return LLMResponse(text=text, tool_calls=calls)

    @staticmethod
    def _to_wire(messages: list) -> list:
        wire: list = []
        for m in messages:
            if m["role"] == "tool":
                block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
                if wire and wire[-1]["role"] == "user" and isinstance(wire[-1]["content"], list):
                    wire[-1]["content"].append(block)  # parallel results share one user turn
                else:
                    wire.append({"role": "user", "content": [block]})
            elif m["role"] == "assistant" and m.get("tool_calls"):
                blocks = [{"type": "text", "text": m["content"]}] if m.get("content") else []
                blocks += [{"type": "tool_use", "id": c.id, "name": c.name, "input": c.arguments or {}}
                           for c in m["tool_calls"]]
                wire.append({"role": "assistant", "content": blocks})
            else:
                wire.append({"role": m["role"], "content": m["content"]})
        return wire
