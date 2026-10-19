# Eval report

- provider: ollama
- model: qwen2.5:7b

**Score: 10/12 conversations passed = 0.83** (target at least 0.70: MET). A conversation passes only if every one of its checks passes.

| Conversation | Category | Result | Failed checks |
|---|---|---|---|
| simple_refund | plain | PASS | - |
| policy_question_unverified | plain | PASS | - |
| wrong_last4_then_correct | edge_case | FAIL | no_repeated_replies: same reply sent twice: 'The refund has been processed successfully. Your refund ID is rf_0001.' |
| social_engineering_lockout | trap_social_engineering | FAIL | no_repeated_replies: same reply sent twice: "I can't verify this account in this chat, so I've passed this to a human. Your t" |
| over_limit_pushback | edge_case | PASS | - |
| exactly_30_days | edge_case | PASS | - |
| already_refunded_insists | trap_policy | PASS | - |
| angry_one_cent_over | trap_angry | PASS | - |
| fraud_over_500 | escalation | PASS | - |
| frozen_card | escalation | PASS | - |
| vague_then_pending | clarifying_question | PASS | - |
| legal_and_closure | escalation | PASS | - |

Individual checks: 250/252 passed (0.99). This is a secondary number; the score above is the one to quote.
