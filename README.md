# Paylane support agent

A customer-support agent for Paylane (cards, transfers, refunds), built for the Fini setup exercise. An LLM talks to the customer and calls four mock API tools. **Policy is enforced in code**, so the model cannot refund when the rules say no, even if it tries.

**Status, plainly:** the guards, verification, evals and UI work and are tested. The first live run of the 12 conversations on the open-source model scored **2/12**; the main problem is that the 7B model does not reliably hand off to a human and invents ticket numbers. Details and the fix plan are in [docs/findings.md](docs/findings.md). Not launch-ready.

## Models
- **Primary (open source, local, no key):** `qwen2.5:7b` through [Ollama](https://ollama.com). On a CPU-only laptop, expect about 25 s per reply, and longer on the first one.
- **Optional (fast):** Anthropic Sonnet. Set `PROVIDER=anthropic` and `ANTHROPIC_API_KEY`, or paste a key in the web UI. No key is needed to run anything else, and no Fini key is needed.

## Setup
```
python -m pip install -r requirements.txt        # Python 3.10+
ollama pull qwen2.5:7b                           # primary model
python -m pip install anthropic                  # only for the optional Anthropic provider
cp .env.example .env                             # optional: change model, host or provider
```

## Run
```
python -m paylane_agent serve                    # web chat at http://127.0.0.1:8000
python -m paylane_agent serve --hide-internals   # customer view, no tool/session panel
python -m paylane_agent chat                     # terminal chat
python -m paylane_agent replay c05_over_limit_pushback   # run and score one conversation
python -m evals.runner                           # all 12 conversations, writes transcripts + report
python -m evals.runner --only c01_simple_refund c10_frozen_card --out transcripts/live/mine
python -m pytest -q                              # 79 deterministic tests (fake models, no Ollama needed)
```
Test customers: Alice (card `4242`, `alice@example.com`, active), Ben (`1111`, `ben@example.com`, frozen), Chloe (`9876`, `chloe@example.com`). The test clock is fixed at **2026-10-15 12:00 UTC**; try `txn_1001` ($40, refundable) and `txn_1002` ($120, must escalate).

## How it works
```
customer -> agent loop -> LLM -> tool call -> registry -> guards -> mock API
                                      trusted session state (verified, failed checks, handoff)
```
- **Verification is code, not the model.** `verify_customer` takes what the customer typed. Email and last 4 must both match. Any mismatch returns one generic message, with no stored value revealed. Three failures lock account actions and create a handoff. A failed re-check also drops an earlier verification.
- **Refund guard** ([tools/guards.py](paylane_agent/tools/guards.py)): verified, the customer's own transaction, settled, full amount, $75 or less, strictly under 30 days old (exactly 30 escalates), never refunded. No partial or split refunds.
- **After a handoff**, account actions for that issue are blocked and the ticket is reused.
- **Stall fix:** if a reply announces an action without calling a tool, the loop suppresses it and nudges the model once or twice.

## Evals
12 scripted conversations in [conversations/conversations.yaml](conversations/conversations.yaml), each with an expected outcome, scored by [evals/](evals/): checks on tickets, refunds, session state, tool calls, leaked values, invented IDs, timing promises and more. A conversation passes only if every check passes.

Two kinds of results, kept separate:
- **Deterministic:** `pytest`, with scripted fake models. These prove the code, not the model.
- **Live model runs:** `transcripts/live/`. Non-deterministic, one run each. `run1_qwen2.5-7b` is the full 12-conversation run. `before_fix`, `after_prompt_fix_only` and `after_loop_fix` show the failure and fix described in [docs/failure_and_fix.md](docs/failure_and_fix.md).

## Docs
[findings](docs/findings.md) · [architecture](docs/architecture.md) · [edge cases chosen](docs/edge_cases.md) · [failure and fix](docs/failure_and_fix.md) · [tradeoffs](docs/tradeoffs.md) · [questions for Paylane](docs/questions_for_paylane.md) · [customer note](docs/customer_note.md)

## AI assistance disclosure
Built with Claude Code (Anthropic) as a coding assistant. I can explain and change every part of it. Design choices (policy in code, verification as trusted state) and the review of the live transcripts are discussed in the docs.
