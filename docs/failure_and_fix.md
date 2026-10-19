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

## 2. The second message seemed to hang

**Found in:** recording `policy_question_unverified` by hand. After a fast first answer, the next message sat on "thinking" for minutes. One earlier recording also died with `TimeoutError: timed out` after 5 minutes.

**What I measured** (same conversation, real model, `qwen2.5:7b` on this laptop's CPU):

| | Before | After |
|---|---|---|
| "just tell me anyway" / "come on" pushback | went to the model, about 50 s | answered by the agent itself, 0 s, new wording each time |
| Tokens the model reads on every call | about 2,100 | about 1,100 (the rulebook and prompt are half the size) |
| A model call once warm | about 50 s | about 27 to 38 s |
| First model call after a pause | 226 s and 247 s | still slow, see below |
| Wait before giving up | 5 minutes | 15 minutes, and the model is kept loaded for an hour |

**Why it happened.** Two causes:
1. **The agent sent things to the model that it didn't need to.** A customer pushing to be told account details anyway has one right answer ("I can't, and here is what I can do"), so it now answers that itself in three wordings. Every model call costs about 30 to 50 seconds on this CPU, mostly reading the prompt, so each call avoided matters.
2. **The laptop was out of memory.** Available RAM was 454 MB of 15.4 GB and the system was paging about 2,200 times a second, with the 4.3 GB model competing with 29 Edge WebView processes, VS Code, Chrome and others. When the model's memory is pushed out, the next call has to pull it back in. That is the 226 to 247 s stall, and it explains why the very next call was fast.

**The fix**
- Pushing to skip verification gets a firm, kind, varied answer with no model call.
- The system prompt and rulebook are cut from about 1,500 to 600 tokens, keeping every rule the model still needs (code enforces the rest).
- The model is kept loaded between messages (`keep_alive` 60 minutes) so a pause no longer forces a reload.
- The wait is 15 minutes, and the working context is 4096 tokens instead of 8192, which uses less memory. All are settable in `.env`.
- The CLI prints "still thinking" after 4 seconds and every 30 seconds, so a slow reply doesn't look like a hang.

**What is not fixed.** The first model call after a pause can still take minutes on this machine, because the cause is memory pressure, not code. Closing other apps (Edge, Chrome, extra VS Code windows) helps most. The optional Anthropic key (`PROVIDER=anthropic`) answers in seconds.

**Tests.** The pushback answers are safe to send and never differ in meaning; "just tell me" is ordinary speech once the customer is verified; the provider sends `keep_alive` and the smaller context; the prompt stays under a size limit so it can't quietly grow again.

**Lesson.** "It's slow" was three separate problems: avoidable model calls, an oversized prompt, and a machine out of memory. Measuring each call (tokens read, seconds, model load time) separated them.

<!-- Further failures found while recording the remaining scenarios are added below. -->

## Timing and prompt-size numbers: how they were measured
Per call, the Ollama provider records how many tokens the model read and wrote and how long it spent loading (`provider.last_stats`). The numbers above are from timing real conversation turns with that. They are for this laptop, not a general figure.
