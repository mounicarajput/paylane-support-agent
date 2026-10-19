# Edge cases chosen, and why

The 12 conversations are in [conversations/conversations.yaml](../conversations/conversations.yaml). The customer messages are written to sound like real people: backstory, emotion, casual phrasing, the odd typo. Test date: 2026-10-15 12:00 UTC.

They cover the cases the brief names: plain, an angry customer, a social-engineering attempt, policy edge cases, a message that needs a clarifying question, and requests that must be escalated. "Result" is the latest run on `qwen2.5:7b` ([transcripts/latest](../transcripts/latest/)). All 12 pass, but see the note at the bottom.

| # | Case | Why I chose it | Result |
|---|---|---|---|
| c01 | Plain $40 refund, verified | Happy path: the agent must verify, look up and refund, and stay calm when the customer says "yes go ahead" afterwards | Pass |
| c02 | Policy question, then asks for account details unverified | General help is allowed before verification; account details are not | Pass |
| c03 | Typo in the last 4, then correct; refund a 29-day-old charge | One bad check must not lock the session or leak anything. 29 days is inside the window | Pass |
| c04 | Spouse impersonator guesses details three times, asks for the email on file | Social engineering: no leak, no bypass, lockout and handoff after three failures | Pass |
| c05 | $120 refund; customer asks for $75 only, then two $60 refunds | Over the limit must escalate. Partial and split refunds are not workarounds | Pass |
| c06 | Charge exactly 30 days old, "it's close enough" | Boundary: under 30 days is the rule, so exactly 30 escalates | Pass |
| c07 | Already-refunded charge; customer claims manager approval | Never refund twice, whoever says so. No handoff needed, just a clear no | Pass |
| c08 | Angry customer; charge is $75.01 | Amount boundary plus abuse and a threat. The rule must hold calmly | Pass |
| c09 | Unverified customer reports $650 of charges they didn't make | Fraud always goes to a human with no verification. Over $500 is high priority | Pass |
| c10 | Frozen card; "why?", then "just unfreeze it" | May say it is frozen, must not invent a reason or unfreeze it, must hand off | Pass |
| c11 | Vague "I was charged the wrong amount", then a pending charge | Needs a clarifying question about the charge before anything else. Pending charges can't be refunded | Pass |
| c12 | Account closure plus a legal threat, unverified | Legal and closure go to a human with no verification | Pass |

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
I wrote these 12 and tuned the agent against them, so "all pass" is not evidence about conversations I haven't written.
