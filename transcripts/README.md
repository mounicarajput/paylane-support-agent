# Transcripts

Real model runs (`qwen2.5:7b` through Ollama, temperature 0). Live runs are non-deterministic, so another run will differ.

| Folder | What it is |
|---|---|
| [latest/](latest/) | The most recent full run of all 12 conversations, with `report.md` (score) and `results.json` (every check) |
| [failure_and_fix/](failure_and_fix/) | One conversation (c01) at three stages: the failure, the prompt-only fix that did not work, and the fix that did. See [docs/failure_and_fix.md](../docs/failure_and_fix.md) |

The very first run (2/12, before the policy layer existed) is not kept in the tree. It is in git history: `git show 28551a6:transcripts/live/run1_qwen2.5-7b/report.md`.

How to read a transcript: `Customer` and `Agent` lines are what was said. Lines starting with `>` are tool calls and results. Italic lines are the agent's own notes (a reply it blocked or cleaned before the customer saw it).

Regenerate the latest run: `python -m evals.runner`
