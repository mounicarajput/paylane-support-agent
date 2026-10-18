"""Records everything in a conversation: messages, tool calls, tool results."""
import json
from datetime import datetime, timezone


class Transcript:
    def __init__(self, meta: dict = None):
        self.meta = dict(meta or {})
        self.events: list = []

    def add(self, kind: str, **data) -> None:
        self.events.append({"type": kind, **data})

    def to_json(self) -> str:
        return json.dumps({"meta": self.meta, "events": self.events}, indent=2, ensure_ascii=False)

    def to_markdown(self, title: str = "Conversation") -> str:
        lines = [f"# {title}", ""]
        for k, v in self.meta.items():
            lines.append(f"- {k}: {v}")
        lines.append("")
        for e in self.events:
            t = e["type"]
            if t == "user":
                lines.append(f"**Customer:** {e['text']}")
            elif t == "assistant":
                lines.append(f"**Agent:** {e['text']}")
            elif t == "tool_call":
                lines.append(f"> tool call: `{e['name']}({json.dumps(e['arguments'], ensure_ascii=False)})`")
            elif t == "tool_result":
                lines.append(f"> result: `{json.dumps(e['result'], ensure_ascii=False)}`")
            elif t == "note":
                lines.append(f"_{e['text']}_")
            lines.append("")
        return "\n".join(lines)

    @staticmethod
    def stamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
