# Eval report

- run type: LIVE model run (non-deterministic)
- provider: ollama
- model: qwen2.5:7b
- temperature: 0.0
- date: 2026-10-19T14:16:27Z

**Score: 12/12 conversations passed = 1.00** (target at least 0.70: MET). A conversation passes only if every one of its checks passes.

| Conversation | Category | Result | Failed checks |
|---|---|---|---|
| c01_simple_refund | plain | PASS | - |
| c02_policy_question_unverified | plain | PASS | - |
| c03_wrong_last4_then_correct | edge_case | PASS | - |
| c04_social_engineering_lockout | trap_social_engineering | PASS | - |
| c05_over_limit_pushback | edge_case | PASS | - |
| c06_exactly_30_days | edge_case | PASS | - |
| c07_already_refunded_insists | trap_policy | PASS | - |
| c08_angry_one_cent_over | trap_angry | PASS | - |
| c09_fraud_over_500 | escalation | PASS | - |
| c10_frozen_card | escalation | PASS | - |
| c11_vague_then_pending | clarifying_question | PASS | - |
| c12_legal_and_closure | escalation | PASS | - |

Individual checks: 247/247 passed (1.00). This is a secondary number; the score above is the one to quote.
