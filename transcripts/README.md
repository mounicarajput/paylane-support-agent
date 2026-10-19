# Transcripts

Real model conversations (`qwen2.5:7b` through Ollama, temperature 0). Live runs are non-deterministic, so another run will differ.

| Folder | What it is |
|---|---|
| `recorded/` | The 12 scenarios, typed live in the CLI as the customer with `python -m paylane_agent record <scenario>`. Files are numbered in order (`01_simple_refund.md`). Each has the full conversation with tool calls, the pass/fail checks, and a plain-language list of the failures the safety layer caught and how they were handled. `report.md` tracks the score as scenarios are recorded |
| [failure_and_fix/](failure_and_fix/) | Failures found while recording by hand, with the transcript of each failure and of the fixed run. See [docs/failure_and_fix.md](../docs/failure_and_fix.md) |

`python -m evals.runner` also writes a scripted run to `latest/`. That folder is regenerated on demand and is not kept in git.

How to read a transcript: `Customer` and `Agent` lines are what was said. Lines starting with `>` are tool calls and results. Italic lines are the agent's own notes (a reply it blocked or cleaned before the customer saw it).
