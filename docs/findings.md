# Findings: how the agent went from 2/12 to 12/12, and what that does not prove

Model for every run: `qwen2.5:7b` through Ollama, temperature 0, seed 7. Live runs are non-deterministic and each was run once.

## 1. Results history
| Run | Score | What changed | Kept in the repo |
|---|---|---|---|
| First run | **2/12** (about 1/12 once its blind spots are counted) | Model only, guards in code | Git history: `git show 28551a6:transcripts/live/run1_qwen2.5-7b/report.md` |
| Policy layer added | 11/12 | Agent creates handoffs, verifies, looks up, checks replies | Git history |
| Human-touch scripts, stricter checks | 11/12 | Rewrote the 12 customer scripts, added filler and repeat checks. c11 failed: filler caused an unneeded ticket | Git history |
| Filler cut, not escalated | 11/12 | c01 repeated its refund confirmation | Git history |
| Follow-up handling, timing fix | **12/12 = 1.00**, 247/247 checks | "Yes go ahead" and "thanks" after a refund, "right away" caught | [transcripts/latest](../transcripts/latest/) |

Target was at least 0.70 (9 of 12). The scoring rule is in [evals.md](evals.md).

## 2. First run (2/12): what was wrong
The transcripts are in git history (`git show 28551a6:transcripts/live/run1_qwen2.5-7b/c05_over_limit_pushback.md` is a good one to read). The guards held: no wrong refund was ever issued, verification gave generic failures and leaked nothing. The failures were in what the model *said and did*:

1. **The 7B never called the handoff tool on its own** (7 conversations). In 5 it told the customer a human had the case, and in 4 it made up a ticket number (123456, 1234567890, 123456789).
2. **It invented results**: a refund ID and a "refund issued" with no refund (c03), a card status it never looked up (c10).
3. **It revealed the email on file** to an unverified person (c04).
4. **It asked again for details the customer had already given** (c08, c10).
5. **It added timing promises** ("soon", "as soon as possible", "will contact you") against the rulebook.
6. **It insisted on verification before handing off** legal and fraud cases (c09, c12), the opposite of the rule.

**My own checks missed several of these**: bare ticket numbers, false handoff claims, "soon", "has been issued", a confirmed email, a card status with no lookup. They are all checks now.

## 3. What fixed each problem
| Problem | Fix |
|---|---|
| Model never hands off, invents ticket IDs | The agent creates the ticket itself and quotes only the real ID. Replies with an ID no tool returned are blocked |
| Invented results and claims | Every reply is checked before it is sent: false refund or handoff claims, unchecked card status, invented freeze reason |
| Revealed the email on file | Reply checker blocks stored values. "What's on file?" gets a refusal |
| Asked again for details already given | The agent verifies credentials and looks up transactions named in the message |
| Timing promises | Blocked in replies, including "right away", "immediately", "a few days" |
| Verification before handoff | Legal, fraud, closure and "get me a human" are detected in code and need no verification |
| Stalling after verification | Loop-level fix, see [failure_and_fix.md](failure_and_fix.md) |
| Robotic, repeated and filler replies | Several wordings in rotation, filler sentences cut, "yes go ahead" after a refund gets "already done" |
| Wrong card accepted on a second check | Every check compares both details, a failure drops verification (found in the web UI) |

## 4. What I found by reading the final transcripts
Passing checks is not the same as a good conversation, so I read all 12. Remaining weaknesses:
- **The model still drifts.** In c02 it first said refunds "can be processed right away"; the reply checker caught that and the second try was fine, but the wording is a little stiff. In c04 it called the caller "Mr. Moreno". Neither breaks a rule.
- **Several answers are fixed wording**, rotated so a customer never hears the same sentence twice. They are warm and safe but not tailored.
- **In several conversations the code decided the outcome** (c04 lockout, c05, c06, c08, c09, c10, c12 handoffs, c07 and the c11 pending answer). The model mostly handled c01, c02, c03 and the small talk. So 12/12 is mostly a measure of the policy layer.

## 5. What 12/12 does not prove
- **I built the agent against these same 12 conversations.** The score says nothing about conversations it has not seen. A fair test needs fresh ones, ideally real, anonymized Paylane chats.
- **The checks are mine.** I fixed them each time a transcript showed a gap, and there are probably more gaps.
- **One run each, at temperature 0.** No variance measured.
- **Keyword triggers over-escalate.** A customer who only asks "how do I report fraud?" would be handed to a human.
- **Not compared with a bigger model or Sonnet**, so I can't say how much comes from the model and how much from the layer around it.

## 6. Other things found while building
- **Speed.** Qwen2.5 14B took about 100 s per reply on this CPU-only laptop, so I switched to the 7B (about 25 s once warm). A 3-second reply is not possible locally; the UI offers an optional Anthropic key for fast replies.
- **Two bugs in my own work, caught by tests:** the raw text "(ticket {tid})" could have reached a customer after a handoff, and one test passed vacuously because of a regex typo.

## 7. What I would do next
1. Test on 20 to 30 conversations I did not write, and report that score separately.
2. Run the same set on a larger open-source model and on Sonnet.
3. Add a tool to update a ticket, so a later, larger fraud loss reaches the human.
4. Run each conversation several times to see variance.
