# Eval report

- run type: LIVE model run (non-deterministic)
- provider: ollama
- model: qwen2.5:7b
- temperature: 0.0
- date: 2026-10-18T12:40:45Z

**Score: 0/1 conversations passed** (a conversation passes only if every check passes).

| Conversation | Category | Result | Failed checks |
|---|---|---|---|
| c01_simple_refund | plain | FAIL | no_stalled_turn: turn 0 ended announcing an action instead of doing it: "Let's check"; tools_in_turn: tools not called in the expected turn: {0: ['get_transaction', 'issue_refund']} |

Individual checks: 12/14 passed.
