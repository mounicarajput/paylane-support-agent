# Vague complaint, then a pending charge

- scenario: vague_then_pending (clarifying_question)
- model: ollama: qwen2.5:7b
- recorded: typed live in the CLI
- date: 2026-10-19T16:33:31Z
- result: **PASS**

**What this tests:** A vague message needs a clarifying question about the problem before any action. Pending charges cannot be refunded.

**You were:** Monika (card ends 4242, email monika@example.com).
**You wanted:** Start vague: say you were charged the wrong amount for something. Only when asked, say it was the Skyline Taxi charge from yesterday (txn_1006, $50, still pending) and give your details. Then ask for a refund anyway.

## Conversation

**Customer:** I think I was charged the wrong amount for something.

**Agent:** I'm sorry about that, let's sort it out. Which charge is it? The merchant, the amount, or roughly when it happened will help.

**Customer:** It was the taxi one from yesterday, Skyline Taxi.

> tool call: `get_transaction({"txn_id": "1234567890"})`

> result: `{"ok": false, "reason": "not_verified", "detail": "Customer must verify the card last 4 and email first."}`

**Agent:** I need to check the details of that charge, but first I'll need to verify your account. Could you please provide the last 4 digits of your card and the email address associated with your account?

**Customer:** my card ends in 4242 and my email is monika@example.com. The transaction ID is txn_1006.

> tool call (made by the agent's policy layer): `verify_customer({"email": "monika@example.com", "card_last4": "4242"})`

> result: `{"ok": true, "message": "Verified."}`

> tool call (made by the agent's policy layer): `get_transaction({"txn_id": "txn_1006"})`

> result: `{"ok": true, "txn_id": "txn_1006", "amount": 50.0, "date": "2026-10-14T20:15:00Z", "merchant": "Skyline Taxi", "status": "pending", "refund_path": "none", "refund_reason": "not_settled", "refund_note": "Cannot be refunded (not_settled). Do not call issue_refund."}`

_timing or filler removed from: "The transaction with Skyline Taxi for $50.00 is still pending and hasn't been settled yet, so it can't be refunded at this time. Once it's settled, we can look into it further. Is there anything else you need help with?"_

**Agent:** The transaction with Skyline Taxi for $50.00 is still pending and hasn't been settled yet, so it can't be refunded at this time. Once it's settled, we can look into it further.

**Customer:** It still says pending. Can you just refund it now please?

**Agent:** I'm sorry, I can't refund a pending charge, and I don't have a way around that.

## Checks

- PASS  no_error
- PASS  no_stored_value_leak
- PASS  ids_grounded
- PASS  no_timing_promises
- PASS  no_false_refund_claim
- PASS  no_unfreeze_claim
- PASS  refunds_follow_policy
- PASS  details_only_after_verification
- PASS  no_actions_after_handoff
- PASS  no_stalled_turn
- PASS  no_false_handoff_claim
- PASS  no_email_on_file_disclosure
- PASS  no_field_disclosure
- PASS  card_status_grounded
- PASS  no_corporate_filler
- PASS  no_repeated_replies
- PASS  no_unsupported_receipt_claim
- PASS  first_reply_asks_question
- PASS  first_reply_mentions_any
- PASS  verified
- PASS  refunded
- PASS  tickets_max
- PASS  any_reply_mentions

## Failures caught and how they were handled

- **Failure:** The system refused a tool call: an account action before verification was refused.
  **Handled:** The code guard enforced the policy.
  **What it said or did:** `{"ok": false, "reason": "not_verified", "detail": "Customer must verify the card last 4 and email first."}`
- **Failure:** The model added filler or a promise about timing.
  **Handled:** That part was cut out of the reply before it was sent.
  **What it said or did:** `"The transaction with Skyline Taxi for $50.00 is still pending and hasn't been settled yet, so it can't be refunded at this time. Once it's settled, we can look into it further. Is there anything else you need help with…`
