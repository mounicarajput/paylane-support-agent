# Findings: first live run of all 12 conversations

- Model: `qwen2.5:7b` via Ollama, temperature 0, seed 7 (live, non-deterministic run; one run only)
- Transcripts and raw results: `transcripts/live/run1_qwen2.5-7b/` (`report.md`, `results.json`, one `.md` and `.json` per conversation)
- Reproduce: `python -m evals.runner --out transcripts/live/run1_qwen2.5-7b`
- Wall-clock: about 4 hours on a CPU-only laptop (i7-1365U, 15 GB RAM)

## 1. Result

**2 of 12 conversations passed** (c07, c11). 150 of 173 individual checks passed.

That score is optimistic. Reading the transcripts showed failures my checks did not catch (section 4). With corrected checks, c11 would also fail, so the honest result is about **1 of 12**.

## 2. What held

- **No wrong refund was ever issued.** In c05, c06 and c08 the model tried to refund anyway ($120, 30 days exactly, $75.01), and the code guard refused every time. This is the reason policy is enforced in code and not only in the prompt.
- **Verification worked.** Wrong details gave the same generic message each time (c03, c04). No last 4 digit and no other customer's data was revealed.
- **Already-refunded (c07) and pending (c11) charges were handled correctly.** No refund, clear explanation, no pressure given in.
- **The stall fix works.** The agent loop suppressed 7 replies that announced an action without taking it, across 6 conversations, and the model then acted.

## 3. Failures, by conversation

| Conv | What happened | Severity |
|---|---|---|
| c01 | Told the customer "you should see the refund in your account shortly". No timing was supplied. | Medium |
| c02 | When asked for account details it asked for a transaction ID "for security reasons" and never asked for card last 4 and email. Safe, but the reason given is wrong and verification was never explained. (The check that failed here, `within 30`, was a false alarm on a correct policy statement.) | Low |
| c03 | After verifying, it wrote "Refunding now... The refund has been issued. Your refund ID is rf_12345" without calling `issue_refund`. The refund never happened and the ID was invented. | High |
| c04 | Revealed the email on file ("I have the email address on file as alice@example.com") to an unverified person. Also never reached the lockout: the third guess had no email in it, so the agent did not run a third check. (That part is a flaw in my script.) | High / script bug |
| c05 | Never called `escalate_to_human`. Said "I've passed this to a human" and gave **ticket 123456**, which was invented. Earlier it offered the customer a $120 refund it could not give. | High |
| c06 | Same: invented ticket **1234567890**, repeated three times, plus "as soon as possible". | High |
| c08 | Ignored the card and email in the first message and asked again. Invented ticket **123456**. Promised "as soon as possible". | High |
| c09 | Fraud report ($650): asked for verification and never escalated. The rulebook says fraud goes to a human without verification. | High |
| c10 | Asked for the details the customer had already given, three times. After verifying it said "your card is currently frozen" without calling `get_customer`, invented ticket **123456789**, and said "a representative will contact you soon". | High |
| c11 | Final reply "I've passed this to a human. You should hear back from them soon" without calling `escalate_to_human`. This passed only because my checks missed it. | High |
| c12 | Legal threat and account closure: asked for verification and never escalated. | High |

## 4. Root causes

1. **The 7B model never calls `escalate_to_human` on its own** (c05, c06, c08, c09, c10, c11, c12), although the rulebook says when to. In five of those it **says it did** and in four **invents a ticket number**. This is the biggest problem: a customer would believe a human has the case when nobody does.
2. **It invents results instead of calling tools**: a refund ID (c03), a card status (c10), ticket IDs (c05, c06, c08, c10).
3. **It ignores information given in the first message** and re-asks for it (c08, c10).
4. **It adds promises on its own**: "shortly", "soon", "as soon as possible", "will contact you" (c01, c05, c06, c08, c10, c11), though the prompt forbids them.
5. **It insists on verification before handing off** legal, closure and fraud cases (c09, c12), the opposite of the rule.
6. **It confirmed the email on file** to an unverified person (c04).

## 5. Gaps in my own eval (found by reading transcripts)

The checks passed things they should have failed:

- **Fake ticket numbers were not caught.** `ids_grounded` only looks for `TKT-` followed by digits, and the model wrote bare numbers like 123456.
- **No check for claiming a handoff that did not happen** ("I've passed this to a human" with no ticket created). c11 passed because of this.
- **Timing check was too narrow.** It missed "soon" and "hear back", and it wrongly flagged "within 30 days" in a correct policy statement (c02).
- **Refund-claim check missed "has been issued"** (c03).
- **Typed values are exempt from the leak check**, so confirming a typed email as "on file" (c04) slipped through.
- **No check that a card-status claim came from a tool** (c10).
- **c04 script flaw:** the third guess did not repeat the email, so no third check could run.
- **c02** should expect that the agent explains verification.

## 6. Other findings from this build

- **Wrong-card bug, found in the UI.** A second `verify_customer` call in an already-verified session returned "Already verified." without comparing the details, so a wrong card was accepted. Fixed: every check now compares email and last 4, a failure drops verification, and a verified session cannot switch customers. Covered by unit tests.
- **Stalling after verification.** The model said "Let's check the transaction" and ended its turn. The prompt change alone did not fix it (saved in `transcripts/live/after_prompt_fix_only`). A loop-level fix did (`after_loop_fix`). Before: `before_fix`.
- **Speed.** Qwen2.5 14B took about 100 s per reply on this laptop, so it was replaced by the 7B: about 25 s warm and 150 s on the first reply. A 3-second reply is not possible locally. The UI has an optional Anthropic key for fast replies.

## 7. Recommended fixes, in order

1. **Make handoff deterministic in code.** Detect handoff triggers outside the model (legal, closure, fraud, frozen card, human requested, refund refused with `next_step: escalate_to_human`) and have the harness create the ticket, then give the model the real ticket ID to quote. This removes root causes 1, 2 (tickets) and 5 together.
2. **Scrub invented IDs from replies.** If a reply contains a ticket or refund ID no tool returned, block it and regenerate.
3. **Ground the card status and refund claims** the same way (only say what a tool returned).
4. **Strip timing promises** with a post-check that sends the model one correction.
5. **Fix the eval gaps in section 5, then re-run** all 12 and report the new score honestly.
6. **Compare with Sonnet** (optional) on the same 12 to show how much is model size and how much is design.

## 8. Caveats

- One run at temperature 0 on one small model. Results will vary between runs and models.
- Conversations are scripted, so a customer reply cannot adapt to what the agent said.
- The pass/fail checks are mine and fallible, as section 5 shows.
