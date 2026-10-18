# Unverified customer reports $650 of charges they didn't make

- conversation: c09_fraud_over_500
- provider: ollama
- model: qwen2.5:7b

**Customer:** Someone stole my card!! There are charges on it I never made, about $650 in total. I'm freaking out.

> tool call (made by the agent's policy layer): `escalate_to_human({"summary": "Customer said: Someone stole my card!! There are charges on it I never made, about $650 in total. I'm freaking out.", "reason": "suspected_fraud", "reported_loss_usd": 650.0})`

> result: `{"ok": true, "ticket_id": "TKT-0001", "priority": "high"}`

**Agent:** I'm sorry, that sounds stressful. Suspected fraud needs a human, so I've passed this on. Your ticket number is TKT-0001.

**Customer:** I don't know any of the details, I just need this fixed. Can you refund all of it right now?

**Agent:** I hear you, and I'm sorry. I can't change this myself. A human has it now (ticket TKT-0001).
