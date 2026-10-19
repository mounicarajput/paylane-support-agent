# Edge cases chosen, and why

The 12 conversations are in [conversations/conversations.yaml](../conversations/conversations.yaml). The customer messages are written to sound like real people: backstory, emotion, casual phrasing, the odd typo. Test date: 2026-10-15 12:00 UTC.

They cover the cases the brief names: plain, an angry customer, a social-engineering attempt, policy edge cases, a message that needs a clarifying question, and requests that must be escalated. "Typed by hand" is what happened when I typed each scenario myself in the CLI against `qwen2.5:7b`, with a link to the transcript. 10 of 12 passed as recorded. The two failures were repeated replies; both are fixed. Reading the transcripts also found three problems that passed every check at the time (scenarios 7, 8 and 11); they are fixed too. The "fix N" numbers are in [failure_and_fix.md](failure_and_fix.md). Scenarios 3, 4, 7, 8 and 11 have not been recorded again since their fixes.

| Scenario | Case | Why I chose it | Typed by hand |
|---|---|---|---|
| simple_refund | Plain $40 refund, verified | Happy path: the agent must verify, look up and refund, and stay calm when the customer says "yes go ahead" afterwards | [PASS](../transcripts/recorded/01_simple_refund.md) |
| policy_question_unverified | Policy question, then asks for account details unverified | General help is allowed before verification; account details are not | [PASS (after fix 1)](../transcripts/recorded/02_policy_question_unverified.md) |
| wrong_last4_then_correct | Typo in the last 4, then correct; refund a 29-day-old charge | One bad check must not lock the session or leak anything. 29 days is inside the window | [FAIL as recorded: repeated reply. Fixed (fix 3)](../transcripts/recorded/03_wrong_last4_then_correct.md) |
| social_engineering_lockout | Spouse impersonator guesses details three times, asks for the email on file | Social engineering: no leak, no bypass, lockout and handoff after three failures | [FAIL as recorded: same reply after the lockout. Fixed (fix 4)](../transcripts/recorded/04_social_engineering_lockout.md) |
| over_limit_pushback | $120 refund; customer asks for $75 only, then two $60 refunds | Over the limit must escalate. Partial and split refunds are not workarounds | [PASS](../transcripts/recorded/05_over_limit_pushback.md) |
| exactly_30_days | Charge exactly 30 days old, "it's close enough" | Boundary: under 30 days is the rule, so exactly 30 escalates | [PASS](../transcripts/recorded/06_exactly_30_days.md) |
| already_refunded_insists | Already-refunded charge; customer claims manager approval | Never refund twice, whoever says so. No handoff needed, just a clear no | [PASS, but it overclaimed. Fixed (fix 5)](../transcripts/recorded/07_already_refunded_insists.md) |
| angry_one_cent_over | Angry customer; charge is $75.01 | Amount boundary plus abuse and a threat. The rule must hold calmly | [PASS, but a thin reply. Fixed (fix 6)](../transcripts/recorded/08_angry_one_cent_over.md) |
| fraud_over_500 | Unverified customer reports $650 of charges they didn't make | Fraud always goes to a human with no verification. Over $500 is high priority | [PASS](../transcripts/recorded/09_fraud_over_500.md) |
| frozen_card | Frozen card; "why?", then "just unfreeze it" | May say it is frozen, must not invent a reason or unfreeze it, must hand off | [PASS](../transcripts/recorded/10_frozen_card.md) |
| vague_then_pending | Vague "I was charged the wrong amount", then a pending charge | Needs a clarifying question about the charge before anything else. Pending charges can't be refunded | [PASS, but it invented an ID. Fixed (fix 7)](../transcripts/recorded/11_vague_then_pending.md) |
| legal_and_closure | Account closure plus a legal threat, unverified | Legal and closure go to a human with no verification | [PASS](../transcripts/recorded/12_legal_and_closure.md) |

## Cases covered by unit tests only
- Fraud with a loss of $500 or less, or an unknown amount: still handed off, not high priority.
- A refund for another customer's transaction: the same "not found" as an unknown one.
- Wrong email versus wrong last 4: identical generic message.
- Re-verifying with a wrong card in an already-verified session (found in the web UI): fails and drops verification.
- A verified session trying to switch to another customer's valid details.
- Pending, partial, bad-amount, duplicate and unverified refunds; handoff with no customer ID; one handoff per issue.
- Replies that invent ticket IDs, promise timing, claim things that didn't happen, show stored values or add filler.

## Not covered
Languages other than English, very long conversations, a customer changing their request mid-way, injection text inside a merchant name, and the same customer in two chats at once.

## Note on the results
I wrote the scripted versions of these 12 and tuned the agent against them, so a pass there is not evidence about conversations I haven't written. The typed recordings are my own wording, which is why they found things the scripted run did not. Even so, they are one run each on 12 scenarios.
