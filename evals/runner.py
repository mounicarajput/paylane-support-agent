"""Runs the scripted conversations against a provider and scores them.

    python -m evals.runner [--only c01_simple_refund c05_over_limit_pushback] [--provider anthropic]

Results from a real model are non-deterministic; label them as live runs.
"""
import argparse
import json
import re
from dataclasses import replace
from pathlib import Path

import yaml

from paylane_agent.agent import Agent
from paylane_agent.config import ROOT, Config
from paylane_agent.providers.base import Provider, ProviderError
from paylane_agent.providers.factory import get_provider
from paylane_agent.tools.registry import ToolRegistry
from paylane_agent.transcript import Transcript

from .checks.common import GLOBAL_CHECKS, Run
from .checks.specific import evaluate_expectations
from .report import TARGET, build_report, score

CONVERSATIONS = ROOT / "conversations" / "conversations.yaml"


def load_conversations(path: Path = CONVERSATIONS) -> list:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def run_conversation(conv: dict, provider: Provider, system_prompt: str = None) -> Run:
    transcript = Transcript({"conversation": conv["id"], "provider": provider.name, "model": provider.model})
    agent = Agent(provider, ToolRegistry(), system_prompt=system_prompt, transcript=transcript)
    replies, error = [], ""
    for turn in conv["turns"]:
        try:
            replies.append(agent.respond(turn))
        except ProviderError as e:
            error = str(e)
            break
    return Run(conv["id"], conv["turns"][:len(replies)] or conv["turns"], replies,
               agent.registry, transcript, error)


def evaluate(run: Run, conv: dict) -> dict:
    checks = [c(run) for c in GLOBAL_CHECKS] + evaluate_expectations(run, conv.get("expect", {}))
    return {
        "id": conv["id"], "title": conv["title"], "category": conv["category"],
        "passed": all(c.ok for c in checks), "error": run.error,
        "checks": [{"name": c.name, "ok": c.ok, "detail": c.detail} for c in checks],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", nargs="*", help="conversation ids to run")
    ap.add_argument("--provider", choices=["ollama", "anthropic"])
    ap.add_argument("--out", help="output directory (default transcripts/live/<provider>-<model>)")
    ap.add_argument("--target", type=float, default=TARGET, help="share of conversations that must pass (default 0.70)")
    args = ap.parse_args(argv)

    config = Config.from_env()
    if args.provider:
        config = replace(config, provider=args.provider)
    provider = get_provider(config)

    convs = load_conversations()
    if args.only:
        convs = [c for c in convs if c["id"] in args.only]
    slug = re.sub(r"[^\w.-]+", "_", f"{provider.name}-{provider.model}")
    out = Path(args.out) if args.out else ROOT / "transcripts" / "live" / slug
    out.mkdir(parents=True, exist_ok=True)

    results = []
    for conv in convs:
        run = run_conversation(conv, provider)
        res = evaluate(run, conv)
        results.append(res)
        (out / f"{conv['id']}.md").write_text(run.transcript.to_markdown(conv["title"]), encoding="utf-8")
        (out / f"{conv['id']}.json").write_text(run.transcript.to_json(), encoding="utf-8")
        print(f"{'PASS' if res['passed'] else 'FAIL'}  {conv['id']}")
        for c in res["checks"]:
            if not c["ok"]:
                print(f"      x {c['name']}: {c['detail']}")

    meta = {"run type": "LIVE model run (non-deterministic)", "provider": provider.name,
            "model": provider.model, "temperature": config.temperature,
            "date": Transcript.stamp()}
    (out / "results.json").write_text(json.dumps({"meta": meta, "results": results}, indent=2), encoding="utf-8")
    (out / "report.md").write_text(build_report(results, meta, args.target), encoding="utf-8")
    passed, s = sum(r["passed"] for r in results), score(results)
    print(f"\nScore: {passed}/{len(results)} = {s:.2f}  (target {args.target:.2f}: "
          f"{'MET' if s >= args.target else 'NOT MET'})  ->  {out}")
    return 0 if s >= args.target else 1


if __name__ == "__main__":
    raise SystemExit(main())
