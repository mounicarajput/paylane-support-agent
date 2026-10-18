# One failure I found, and how I fixed it

## The failure: the agent stops after verifying and never acts
First live test on `qwen2.5:7b`, conversation c01 (plain refund of `txn_1001`). The customer gave a card, email and transaction ID in the first message.

Transcript: [1_before](../transcripts/failure_and_fix/1_before.md)
```
tool call: verify_customer(...)  ->  ok
Agent: Verified. Let's check the transaction details. I'll look up the transaction with ID txn_1001.
(turn ends; nothing was looked up)
```
The refund only happened because my scripted second message said "yes, go ahead". With a real customer the chat would have stalled. **My own eval missed it**, since c01 still ended in the right refund. I caught it by reading the transcript.

## Fix attempt 1: prompt only (did not work)
I added a rulebook section "Act, don't announce": do verify, look up and refund in one turn, never announce an action. I also added two checks that fail on the stall (`no_stalled_turn`, and `tools_in_turn` for c01), and confirmed they fail on the saved "before" transcript.

Re-run: [2_prompt_fix_only](../transcripts/failure_and_fix/2_prompt_fix_only.md). The model still wrote "Let's check the transaction now" and stopped. The 7B model does not reliably follow this instruction.

## Fix attempt 2: loop-level guard (worked)
If a reply announces an action ("let's check", "I'll look up", ...) and calls no tool, the agent loop hides that reply from the customer and sends one automated reminder to act, at most twice. Code: `STALLED` and `NUDGE` in [agent.py](../paylane_agent/agent.py); tests in [tests/test_agent.py](../tests/test_agent.py).

Re-run: [3_loop_fix](../transcripts/failure_and_fix/3_loop_fix.md). The stalled reply is suppressed, the model then calls `get_transaction` and `issue_refund`, and c01 passes the stricter checks. In the first full run the guard fired 7 times across 6 conversations.

## Lesson
A prompt rule is a request; a check in code is a guarantee. This is the same reason refund policy lives in guards and not only in the prompt. The first full run then showed the same pattern at a worse scale (the model never calls the handoff tool), which is why handoffs are now created by code. See [findings](findings.md).

## A second failure, found by the user
In the web UI, a second verification with a wrong card number returned "Already verified" and the session stayed verified. Cause: my verification code skipped the comparison once a session was verified. Fixed so every check compares email and last 4, a failure drops verification, and a verified session cannot switch customers. Unit tests cover it ([test_verification.py](../tests/test_verification.py), [test_guards.py](../tests/test_guards.py)). I did not catch this one myself.
