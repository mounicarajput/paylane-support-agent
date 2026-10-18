"""Common LLM interface. The agent loop only ever talks to this.

Internal message format (providers convert to their own wire format):
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}  # content is JSON text
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Model backend unreachable or returned something unusable."""


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list = field(default_factory=list)


class Provider(ABC):
    name: str = ""
    model: str = ""

    def validate(self) -> None:
        """Cheap check that the backend accepts our credentials. Raise ProviderError if not."""

    @abstractmethod
    def chat(self, system: str, messages: list, tools: list) -> LLMResponse:
        """One model turn. `tools` are the neutral definitions from tools/schemas.py."""
