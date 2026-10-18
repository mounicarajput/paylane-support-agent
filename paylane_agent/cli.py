"""Command line: chat with the agent, or replay a scripted conversation.

    python -m paylane_agent chat [--provider anthropic] [--save out.md]
    python -m paylane_agent replay c05_over_limit_pushback
"""
import argparse
from dataclasses import replace

from .agent import Agent
from .config import Config
from .providers.base import ProviderError
from .providers.factory import get_provider
from .tools.registry import ToolRegistry
from .transcript import Transcript


def _provider(args):
    config = Config.from_env()
    if args.provider:
        config = replace(config, provider=args.provider)
    return get_provider(config)


def cmd_chat(args) -> int:
    provider = _provider(args)
    transcript = Transcript({"provider": provider.name, "model": provider.model, "mode": "interactive"})
    agent = Agent(provider, ToolRegistry(), transcript=transcript)
    print(f"Paylane support ({provider.name}: {provider.model}). Type 'quit' to exit.\n")
    try:
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if text.lower() in {"quit", "exit"}:
                break
            if not text:
                continue
            try:
                print(f"agent> {agent.respond(text)}\n")
            except ProviderError as e:
                print(f"[error] {e}")
                break
    finally:
        if args.save:
            with open(args.save, "w", encoding="utf-8") as f:
                f.write(transcript.to_markdown("Interactive chat"))
            print(f"Saved transcript to {args.save}")
    return 0


def cmd_replay(args) -> int:
    from evals.runner import evaluate, load_conversations, run_conversation

    conv = next((c for c in load_conversations() if c["id"] == args.conversation), None)
    if conv is None:
        print("Unknown conversation. Options:", ", ".join(c["id"] for c in load_conversations()))
        return 2
    run = run_conversation(conv, _provider(args))
    print(run.transcript.to_markdown(conv["title"]))
    res = evaluate(run, conv)
    print("RESULT:", "PASS" if res["passed"] else "FAIL")
    for c in res["checks"]:
        if not c["ok"]:
            print(f"  x {c['name']}: {c['detail']}")
    return 0 if res["passed"] else 1


def cmd_serve(args) -> int:
    from .web.server import serve

    serve(_provider(args), args.host, args.port, args.hide_internals)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="paylane_agent", description="Paylane support agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    chat = sub.add_parser("chat", help="talk to the agent")
    chat.add_argument("--save", help="write the transcript to this markdown file")
    replay = sub.add_parser("replay", help="run one scripted conversation and score it")
    replay.add_argument("conversation")
    serve = sub.add_parser("serve", help="web chat UI")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    serve.add_argument("--hide-internals", action="store_true",
                       help="hide the session/tool-call panel (customer-facing view)")
    for p in (chat, replay, serve):
        p.add_argument("--provider", choices=["ollama", "anthropic"])
    args = ap.parse_args(argv)
    try:
        return {"chat": cmd_chat, "replay": cmd_replay, "serve": cmd_serve}[args.cmd](args)
    except ProviderError as e:
        print(f"[error] {e}")
        return 2
