# Architecture

## Goal
Paylane support agent (cards, transfers, refunds). Policy is enforced in code; the prompt shapes behaviour, the guards make rule-breaking impossible.

## Models
- Primary: open-source `qwen2.5:7b` (Ollama, local, no key). Switched from 14B: on a CPU-only laptop 14B took ~100 s per reply.
- Optional: Anthropic Sonnet, only when `PROVIDER=anthropic` and `ANTHROPIC_API_KEY` are set.
- Both implement one interface (`providers/base.py`); agent, tools and evals are provider-agnostic.

## Flow
customer message -> agent loop -> provider (LLM) -> tool call -> registry -> guards -> mock API -> result back to LLM -> reply.
Every message, tool call and tool result is written to the transcript.

## Trusted state (never decided by the model)
- `session/state.py`: verified flag, failed-check count, handoff lock, customer id.
- `session/verification.py`: supplied email AND last 4 must both match the mock record. Any mismatch returns one generic failure message. Three failures lock account actions and force handoff.
- `session/clock.py`: fixed UTC clock for deterministic age checks.

## Guards (`tools/guards.py`)
- Account tools blocked unless verified (except guest/null-ID handoff).
- `issue_refund` allowed only if: transaction belongs to the verified customer, status settled, full original amount, amount <= $75, age < 30 days (exactly 30 escalates), never refunded before. No partial or split refunds.
- After a successful handoff, consequential actions for that issue are blocked.
- Ticket ID is only surfaced from a successful `escalate_to_human` result.

## Handoff triggers
Frozen card, suspected unauthorized charge, fraud (>$500 total loss = high priority), legal action, account closure, explicit request for a person, refund above limit or too old, three failed verifications.

## Evals
- `tests/`: deterministic unit tests (guards, verification, clock, mock API).
- `evals/`: pass/fail checks per conversation run against the live model; reported separately.
