# Failures found while recording live conversations, and the fixes

These come from typing the scenarios by hand in the CLI (`python -m paylane_agent record <scenario>`), not from the scripted run. A person phrases things differently from a script, and that is where the failures show up. Each entry has the real transcript.

## 1. A question about the rules was answered with a demand to verify

**Found in:** `policy_question_unverified`. Transcript of the failure: [policy_question_before.md](../transcripts/failure_and_fix/policy_question_before.md) (copied from the terminal, because the session was ended before it saved).

**What happened**
```
Customer: hey, how refund works? i need refund, what's the refund policy?
Agent:    I can help with that once I've verified you. Please send the last 4 digits of your card and the email on your account.
Customer: i need refund policy details first? i don't want to share my card details now
Agent:    Thanks. I still need the last 4 digits of your card and the email on your account before I can look at anything.
```
The customer asked twice for the rules and said plainly they did not want to share details. The agent ignored both and asked for the details again. General policy help should need no verification. Only account details do.

**Why it happened.** The agent decides some replies itself, before the model sees the message. One of those rules is "an unverified customer asking for a refund must verify first", and it matched the words "i need refund" inside a policy question. Because it runs before the model, the model never got the chance to answer sensibly, and none of the reply checks could see it.

**Why the scripted run missed it.** My scripted version of this scenario asked "How do refunds work with you guys? Is there a cap?", with no "I need a refund" in it. Real people mix a request and a question in one breath. The scripted run scored 12/12 while this was broken.

**The fix**
- The agent now recognises a question about the rules ("how do refunds work", "what's the refund policy", "is there a limit", "what are your rules") and answers it with the real rules: full refunds only, settled charges of $75 or less, under 30 days old, not refunded before; over $75 or 30 days old or more goes to a person; pending charges can't be refunded; no partial refunds. No verification is needed, even if the same message also says "I need a refund".
- If the customer says they don't want to share details, the answer starts "No problem, you don't need to share anything for this."
- The answer comes in two wordings so a repeat question doesn't get the same words twice. It says what is needed only if they want a specific charge checked.
- If the customer has already given their details, this rule steps aside and they are verified as before.
- A plain "give me refund" or "what was my last order?" still asks them to verify first.
- The scenario now also checks that the **first** reply contains the rules (`first_reply_mentions_any`), so a demand to verify in its place fails.

**Tests.** The exact two messages above are a test. So are: the answers pass the reply checker themselves, policy questions are told apart from requests, and a request or an order lookup still asks to verify.

**Lesson.** Rules that run before the model can be wrong in ways the reply checks never see, and a scripted conversation only covers the phrasing its author thought of. Typing the scenarios by hand found it.

<!-- Further failures found while recording the remaining scenarios are added below. -->
