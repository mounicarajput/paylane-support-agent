# Architecture

One idea runs through the design: **a small open-source model writes the words, and code enforces the rules.** Refund policy, verification, handoffs and "never say X" all live in code that the model cannot talk its way past.

```
customer message
      |
      v
 policy layer, before the model      (paylane_agent/policy.py, used by agent.py)
   - legal / fraud / closure / "get me a human"  -> hand off now, no verification needed
   - a question about the refund rules            -> answer with the real rules, no verification
   - email and/or last 4, in any order, any message -> remember both, verify when both are there,
                                                      ask for the missing one straight away
   - transaction ID in the message               -> look it up
   - already refunded / pending / pushback / locked -> fixed answers, new wording each time
      |
      v   (only if nothing above settled it)
 LLM  <-->  tool calls  -->  tool registry  -->  guards  -->  mock API
      |                            |                |
      |                      session state     refund rules
      v
 policy layer, after the model       (policy.check_reply)
   - cut filler and timing promises; block invented IDs, false claims, leaks
   - never repeat an earlier reply; never send a reply that says nothing useful
      |
      v
 reply to the customer
```

## The pieces
| Piece | File | What it does |
|---|---|---|
| Agent loop | [agent.py](../paylane_agent/agent.py) | Runs the turn: policy layer, model, tool calls, reply checks, safe fallbacks |
| Policy layer | [policy.py](../paylane_agent/policy.py) | Trigger detection, fixed replies, the reply checker |
| Prompt and rulebook | [prompts/](../paylane_agent/prompts/) | What the model is told: tone, verification, refunds, frozen cards, handoffs |
| Tools | [tools/](../paylane_agent/tools/) | The 4 mock API tools plus `verify_customer`, behind guards and a registry |
| Guards | [tools/guards.py](../paylane_agent/tools/guards.py) | Refund rules in code: verified, own transaction, settled, full amount, $75 or less, under 30 days, never twice |
| Session state | [session/](../paylane_agent/session/) | Verified flag, failed checks (3 = lock and handoff), handoff ticket, fixed test clock |
| Models | [providers/](../paylane_agent/providers/) | Ollama (open source, primary) and Anthropic (optional) behind one interface |
| Web UI and CLI | [web/](../paylane_agent/web/), [cli.py](../paylane_agent/cli.py) | Chat in the browser or terminal |
| Evals | [evals/](../evals/) | Scripted conversations, pass/fail checks, score. See [evals.md](evals.md) |

## Rules that are enforced in code, not left to the model
- **Verification:** the customer's email and card last 4 must both match the record. Any mismatch gives a generic message that names no field and shows no stored value. A failed check drops earlier verification. Three failures lock account actions and create a handoff.
- **Refunds:** the guard re-checks the whole policy on every `issue_refund`. Pending, partial, split, repeat, over $75 and 30-days-or-older all refuse. Exactly 30 days escalates.
- **Handoffs:** the agent creates the ticket and quotes only the ID the tool returned. After a handoff, account actions for that issue are blocked and the same ticket is reused. Fraud with a reported loss over $500 is tagged high priority; smaller or unknown losses still hand off.
- **Replies:** nothing reaches the customer if it quotes an ID no tool returned, promises timing or a contact method, claims a handoff or refund that did not happen, shows an email or card digits, hints which detail was wrong, offers to unfreeze a card or guesses why one is frozen. Corporate filler is cut. Anything still unsafe after two retries is replaced by a real handoff, or by an offer to hand off.

## Values sent to tools must come from the customer
Models sometimes invent arguments. The registry refuses any email, card digits or transaction ID that the customer did not type in this conversation (the refusal is not counted as a failed check). Ownership guards alone would not stop a model from guessing a real ID that belongs to the customer.

## Fewer model calls on purpose
On a laptop CPU each model call costs 30 to 50 seconds, mostly reading the prompt, so anything with one right answer is answered by the agent itself (pushback, half the details, a locked session, a policy question). The prompt the model reads is kept short, and a test fails if it grows.

## Tool differences from the spec
- `verify_customer(email, card_last4)` is added. The model passes what the customer typed and code decides. The model never sees the stored email or last 4.
- `get_transaction` and `issue_refund` use the verified customer from session state, not an ID from the model, so one customer cannot touch another's transactions.
- `get_transaction` also returns `refund_path` and `refund_note` so the model is told up front whether a charge can be refunded.
- `escalate_to_human` takes two extra fields, `reason` and `reported_loss_usd`, so code can set priority.
