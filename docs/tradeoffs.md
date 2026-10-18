# Tradeoffs and what is still open

## Design decisions
- **Policy in code, not only the prompt.** The refund guard re-checks everything the policy says, so a model mistake cannot move money. Cost: more code, and the model can still *say* wrong things (see findings), which needs separate checks.
- **Verification is trusted session state.** The model passes what the customer typed to `verify_customer`; code compares it and keeps the flag. The model never sees stored email or last 4. This adds a fifth tool beyond the four in the spec.
- **Two extra parameters on `escalate_to_human`:** `reason` and `reported_loss_usd`. They let code, not the model, decide the high-priority label (fraud loss over $500) and let evals check why a case was handed off. The spec's two parameters are still used.
- **Tools use the session's customer ID.** The model cannot pass another customer's ID to `get_transaction` or `issue_refund`.
- **No search by merchant or date.** Pending charges and unknown IDs mean the agent asks for a transaction ID. Adding a read-only search on the verified customer's own account is a documented extension, not built.
- **Fixed UTC test clock** (2026-10-15 12:00). Deterministic, but real use needs a real clock.
- **Stall guard in the loop.** A pragmatic fix for a small model; it hides replies from the customer, so it should be logged and monitored in production.

## Model choice
- **Open source primary:** `qwen2.5:7b` through Ollama, so anyone can reproduce results with no key. I first picked the 14B, but it took about 100 s per reply on a CPU-only laptop and I replaced it.
- **The 7B is the weakest link.** It does not reliably call the handoff tool and sometimes invents IDs (2/12 live). A bigger model or Sonnet would likely do better; I have not measured that yet.
- **Optional Anthropic** for fast replies, via env var or a key pasted in the UI. The UI key lives only in server memory for that browser session. While it is on, chat messages go to Anthropic, which the UI states.

## Evaluation limits
- Conversations are scripted, so a customer turn cannot adapt to what the agent said. I chose turns that make sense whatever the reply, but it is a limit.
- Checks are regex and state based, and my first version missed several real failures (listed in findings). Passing checks do not mean a conversation was good.
- One live run per model at temperature 0. No variance measured.
- Deterministic tests use fake models and prove the code, not the model. They are kept separate from live results in the README.

## Production gaps (this is a mock)
- Mock API and in-memory sessions only; no persistence, auth, rate limiting or audit log.
- The web UI is for local use (binds to 127.0.0.1) and is not hardened for the internet.
- English only. No handling of prompt injection hidden in merchant names or other data.
- No human-response time, arrival estimate or authorization-void tool was supplied, so the agent promises none of them.

## Next steps, in order
1. Make handoff deterministic in code and block invented IDs and unsupported claims.
2. Fix the eval gaps listed in findings, then re-run all 12 and report the new score.
3. Compare against a larger open-source model and Sonnet on the same 12.
4. Build the read-only transaction search if Paylane agrees (see questions).
