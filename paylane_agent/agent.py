"""The agent: a tool-use loop over a provider and the guarded tool registry."""
import json
import re
from pathlib import Path
from typing import Optional

from .providers.base import Provider, ToolCall
from .tools.registry import ToolRegistry
from .transcript import Transcript

PROMPT_DIR = Path(__file__).parent / "prompts"
MAX_TOOL_ROUNDS = 8
MAX_NUDGES = 2
FALLBACK = "Sorry, I hit a problem on my side. I'll pass this to a human so you're not stuck."
# Smaller open-source models sometimes end a turn with "Let's check..." instead of calling the tool.
STALLED = re.compile(
    r"\b(let's|let me|i'll|i will|i am going to|i'm going to) (now )?(check|look|verify|process|proceed|pull up|find|issue)\b",
    re.I)
NUDGE = ("(Automated reminder, not from the customer.) You said you would do something but did not call a tool. "
         "Call the tool now, then tell the customer the result. Do not announce actions.")


def load_system_prompt() -> str:
    parts = [(PROMPT_DIR / n).read_text(encoding="utf-8").strip() for n in ("system_prompt.md", "rulebook.md")]
    return "\n\n".join(p for p in parts if p)


class Agent:
    def __init__(self, provider: Provider, registry: Optional[ToolRegistry] = None,
                 system_prompt: Optional[str] = None, transcript: Optional[Transcript] = None):
        self.provider = provider
        self.registry = registry or ToolRegistry()
        self.system_prompt = system_prompt if system_prompt is not None else load_system_prompt()
        self.transcript = transcript or Transcript()
        self.messages: list = []

    def respond(self, user_text: str) -> str:
        self.messages.append({"role": "user", "content": user_text})
        self.transcript.add("user", text=user_text)

        nudges = 0
        for _ in range(MAX_TOOL_ROUNDS):
            reply = self.provider.chat(self.system_prompt, self.messages, self.registry.definitions)
            self.messages.append({"role": "assistant", "content": reply.text, "tool_calls": reply.tool_calls})
            if not reply.tool_calls:
                if nudges < MAX_NUDGES and STALLED.search(reply.text) and not self.registry.state.handed_off:
                    nudges += 1  # hide the stalled message from the customer and prompt the model to act
                    self.transcript.add("note", text=f"stalled reply suppressed: {reply.text!r}")
                    self.messages.append({"role": "user", "content": NUDGE})
                    continue
                return self._finish(reply.text)
            for call in reply.tool_calls:
                self._run_tool(call)

        # Model kept calling tools without answering: fail safe to a human.
        if not self.registry.state.handed_off:
            self.registry.execute("escalate_to_human", {
                "summary": "Agent could not finish the conversation.", "reason": "other"})
        return self._finish(FALLBACK)

    def _run_tool(self, call: ToolCall) -> None:
        self.transcript.add("tool_call", name=call.name, arguments=call.arguments)
        result = self.registry.execute(call.name, call.arguments)
        self.transcript.add("tool_result", name=call.name, result=result)
        self.messages.append({
            "role": "tool", "tool_call_id": call.id, "name": call.name,
            "content": json.dumps(result, ensure_ascii=False),
        })

    def _finish(self, text: str) -> str:
        self.transcript.add("assistant", text=text)
        return text
