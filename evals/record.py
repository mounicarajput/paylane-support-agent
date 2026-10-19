"""Record a conversation you type yourself, then check it and save the transcript.

    python -m paylane_agent record                      # list the 12 scenarios
    python -m paylane_agent record simple_refund    # type the conversation, say "done" at the end

You play the customer in your own words (the scenario brief says who you are and what you want).
The agent answers for real. When you finish, the conversation is saved with every tool call, the
failures the agent's safety layer caught and what it did about them, and the pass/fail result.
"""
import json
import re
from pathlib import Path

from paylane_agent.agent import Agent
from paylane_agent.config import ROOT
from paylane_agent.progress import thinking
from paylane_agent.providers.base import Provider, ProviderError
from paylane_agent.tools.registry import ToolRegistry
from paylane_agent.transcript import Transcript

from .checks.common import Run
from .report import build_report
from .runner import evaluate, load_conversations, numbered_name

OUT_DIR = ROOT / "transcripts" / "recorded"
DONE = {"done", "/done", "finish", "/finish", "don", "dne", "done."}  # "don" is a typo that happened for real
QUIT = {"quit", "/quit", "exit", "/exit"}

# What each kind of caught failure means, in plain words.
FAILURES = {
    "invented_ticket_id": "the model quoted a ticket number that no tool returned",
    "invented_refund_id": "the model quoted a refund ID that no tool returned",
    "stored_value_shown": "the model repeated an email or card digits held on the account",
    "field_disclosed": "the model hinted which detail (email or card digits) was wrong",
    "timing_promise": "the model promised when, how or by whom the customer would be contacted",
    "false_handoff_claim": "the model said a human had the case before any ticket existed",
    "false_refund_claim": "the model said a refund happened when none did",
    "unfreeze_claim": "the model claimed or offered to unfreeze the card",
    "invented_freeze_reason": "the model guessed why the card is frozen",
    "unchecked_card_status": "the model stated the card status without looking it up",
    "asked_for_transaction_first": "the model asked for a transaction ID before verifying the customer",
    "corporate_filler": "the model added corporate filler",
    "empty_reply": "the model's reply was nothing but filler",
}
TOOL_REFUSALS = {
    "not_provided": "the model tried to verify with details the customer never typed (refused, not counted as a failed check)",
    "over_limit": "a refund over $75 was refused",
    "too_old": "a refund on a charge 30 days old or more was refused",
    "already_refunded": "a second refund on the same charge was refused",
    "not_settled": "a refund on a pending charge was refused",
    "amount_mismatch": "a partial or wrong-amount refund was refused",
    "not_verified": "an account action before verification was refused",
    "handed_off": "an account action after the handoff was refused",
}


def list_scenarios(show=print) -> None:
    show("The 12 scenarios. Pick one:\n")
    for c in load_conversations():
        done = "x" if (OUT_DIR / f"{numbered_name(c['id'])}.md").exists() else " "
        show(f"  [{done}] {c['id']:<34} {c['title']}")
    show("\nRecord one with:  python -m paylane_agent record <scenario id>")


def _short(text: str, n: int = 220) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def caught_failures(events: list) -> list:
    """Plain-language list of what went wrong during the conversation and what was done about it."""
    out = []
    for e in events:
        if e["type"] == "note":
            t = e["text"]
            if t.startswith("stalled reply suppressed"):
                out.append(("The model said what it was about to do instead of doing it",
                            "The agent hid that reply and told the model to act.", t.split(": ", 1)[1]))
            elif t.startswith("reply blocked"):
                name = re.search(r"\((\w+)\)", t).group(1)
                out.append((f"{FAILURES.get(name, name)}",
                            "The reply was blocked before the customer saw it; the model had to rewrite it.",
                            t.split(": ", 1)[1]))
            elif t.startswith("permission question suppressed"):
                out.append(("The model asked whether to go ahead, although the customer had already asked for the refund",
                            "The agent hid the question and told the model to issue the refund.", t.split(": ", 1)[1]))
            elif t.startswith("thin reply replaced"):
                out.append(("After cleaning, the reply was only a line of sympathy with no ticket",
                            "The agent replaced it with an answer that names the ticket.", t.split(": ", 1)[1]))
            elif t.startswith("repeated reply replaced"):
                out.append(("The model repeated something it had already said, word for word",
                            "The agent replaced the repeat with a short 'I didn't catch that'.", t.split(": ", 1)[1]))
            elif t.startswith("timing or filler removed"):
                out.append(("The model added filler or a promise about timing",
                            "That part was cut out of the reply before it was sent.", t.split(": ", 1)[1]))
        elif e["type"] == "tool_result":
            r = e["result"]
            if r.get("ok") is False and r.get("reason") in TOOL_REFUSALS:
                out.append((f"The system refused a tool call: {TOOL_REFUSALS[r['reason']]}",
                            "The code guard enforced the policy.", json.dumps(r, ensure_ascii=False)))
    return out


def render(conv: dict, transcript: Transcript, result: dict) -> str:
    brief = conv.get("brief", {})
    lines = [f"# {conv['title']}", "",
             f"- scenario: {conv['id']} ({conv['category']})",
             *[f"- {k}: {v}" for k, v in transcript.meta.items()],
             f"- result: **{'PASS' if result['passed'] else 'FAIL'}**", "",
             f"**What this tests:** {conv['why']}", ""]
    if brief:
        lines += [f"**You were:** {brief['you_are']}", f"**You wanted:** {brief['goal']}", ""]
    lines += ["## Conversation", "", transcript.events_markdown(), "## Checks", ""]
    for c in result["checks"]:
        lines.append(f"- {'PASS' if c['ok'] else 'FAIL'}  {c['name']}" + ("" if c["ok"] else f": {c['detail']}"))
    lines += ["", "## Failures caught and how they were handled", ""]
    caught = caught_failures(transcript.events)
    if not caught:
        lines.append("None. Every reply the model wrote passed the checks as it was.")
    for failure, handling, example in caught:
        lines += [f"- **Failure:** {failure}.", f"  **Handled:** {handling}", f"  **What it said or did:** `{_short(example)}`"]
    failed = [c for c in result["checks"] if not c["ok"]]
    if failed:
        lines += ["", "## Checks that failed (not handled)", ""]
        lines += [f"- {c['name']}: {c['detail']}" for c in failed]
    return "\n".join(lines) + "\n"


def _update_report(out_dir: Path, conv: dict, result: dict, meta: dict) -> None:
    path = out_dir / "results.json"
    store = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    store[conv["id"]] = result
    path.write_text(json.dumps(store, indent=2), encoding="utf-8")
    order = [c["id"] for c in load_conversations()]
    results = [store[i] for i in order if i in store]
    report = build_report(results, meta, total=len(order))
    (out_dir / "report.md").write_text(report, encoding="utf-8")


def record(conv_id: str, provider: Provider, out_dir: Path = OUT_DIR, read=input, show=print) -> dict:
    conv = next((c for c in load_conversations() if c["id"] == conv_id), None)
    if conv is None:
        show(f"Unknown scenario '{conv_id}'.")
        list_scenarios(show)
        return {}

    brief = conv.get("brief", {})
    show(f"\n=== {conv['title']} ===")
    show(f"You are:    {brief.get('you_are', '')}")
    show(f"You want:   {brief.get('goal', '')}")
    show("\nA suggested script, if you want one (use your own words as much as you like):")
    for i, turn in enumerate(conv["turns"], 1):
        show(f"  {i}. {turn}")
    show("\nType as the customer. Type 'done' when you've finished, or 'quit' to leave without saving.\n")

    transcript = Transcript({"model": f"{provider.name}: {provider.model}",
                             "recorded": "typed live in the CLI", "date": Transcript.stamp()})
    agent = Agent(provider, ToolRegistry(), transcript=transcript)
    typed, replies = [], []
    while True:
        try:
            text = read("you> ").strip()
        except (EOFError, KeyboardInterrupt):
            show("")
            return {}
        if text.lower() in QUIT:
            show("Nothing saved.")
            return {}
        if text.lower() in DONE:
            break
        if not text:
            continue
        typed.append(text)
        try:
            with thinking(show):
                reply = agent.respond(text)
        except ProviderError as e:
            # The model could not be reached. That says nothing about the agent, so don't save a
            # transcript (it would show a misleading FAIL). Nothing is written; run the scenario again.
            show(f"\n[error] {e}")
            show("The model could not be reached, so nothing was saved. Fix that and record this scenario again.")
            return {}
        replies.append(reply)
        show(f"agent> {reply}\n")

    if not typed:
        show("No conversation typed, nothing saved.")
        return {}
    run = Run(conv["id"], typed[: len(replies)] or typed, replies, agent.registry, transcript)
    # `tools_in_turn` says which turn a tool must be called in. That fits a script where everything is in
    # the first message, not a person who gives their details one message at a time. Outcomes still count.
    typed_conv = {**conv, "expect": {k: v for k, v in conv.get("expect", {}).items() if k != "tools_in_turn"}}
    result = evaluate(run, typed_conv)
    out_dir.mkdir(parents=True, exist_ok=True)
    saved = out_dir / f"{numbered_name(conv['id'])}.md"
    saved.write_text(render(conv, transcript, result), encoding="utf-8")
    _update_report(out_dir, conv, result, {"provider": provider.name, "model": provider.model})
    show(f"\nResult: {'PASS' if result['passed'] else 'FAIL'}")
    for c in result["checks"]:
        if not c["ok"]:
            show(f"  x {c['name']}: {c['detail']}")
    for failure, handling, _ in caught_failures(transcript.events):
        show(f"  caught: {failure}. {handling}")
    show(f"Saved to {saved}")
    return result
