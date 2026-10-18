# Tradeoffs and what is still open

## The big one: how much the code does versus the model
The first live run on `qwen2.5:7b` scored 2/12 because the model never reliably handed off and invented ticket numbers (see [findings](findings.md)). I fixed that by moving more into code: the agent now creates handoffs itself, verifies and looks things up, and checks every reply.

- **Good:** the rules hold whatever the model does, replies stay warm and varied, and the agent is far more reliable.
- **Cost:** in several conversations the code, not the model, decides the outcome, so a good score says less about the model. The honest comparison is the same 12 conversations on a bigger model or Sonnet, which I have not run.
- **Keyword triggers:** legal, fraud, closure and "get me a human" are detected by keyword. They will sometimes hand off someone who only asked a general question ("how do I report fraud?"). I chose that: over-escalating is the safe direction.
- **Fixed wording:** several replies are written wordings used in rotation, not generated text. They are short, warm and never promise timing. They are less flexible than a model would be.
- **A customer cannot add details after a fraud handoff.** The ticket is created from the first message. If they later state a bigger loss, the ticket's priority does not change, because there is no tool to update it.

## Design decisions
- **Policy in code, not only the prompt.** A prompt rule is a request; a check in code is a guarantee. Cost: more code.
- **Verification is trusted session state.** This adds a fifth tool, `verify_customer`. The model never sees the stored email or last 4.
- **Two extra `escalate_to_human` fields:** `reason` and `reported_loss_usd`, so code decides priority and evals can check why a case was handed off.
- **No search by merchant or date.** When there is no transaction ID the agent asks for one. A read-only search on the verified customer's own account is a possible extension, listed in [questions for Paylane](questions_for_paylane.md).
- **Fixed UTC test clock** (2026-10-15 12:00). Deterministic, but real use needs a real clock.

## Models
- **Open source, primary:** `qwen2.5:7b` through Ollama, so anyone can reproduce with no key. I first tried the 14B, but it took about 100 s per reply on a CPU-only laptop.
- **Optional Anthropic** for fast replies, via env var or a key pasted in the web UI. In the UI the key lives only in server memory for that browser session. While it is on, chat messages go to Anthropic, and the UI says so.
- The 7B is slow on a laptop (about 25 s per reply once warm, and much more on the first). The UI says so while it is in use.

## Evaluation limits
- Conversations are scripted, so a customer turn cannot adapt to what the agent said. Turns are written to make sense whatever the reply.
- Checks are regex and state based. My first versions missed real failures, and some checks were wrong; each was fixed and written up. Passing checks do not mean a conversation was good, so read the transcripts.
- One live run per version, at temperature 0. No variance was measured.
- Deterministic tests use fake models. They prove the code and the checks, not the model, and are reported separately from live runs.

## Production gaps (this is a mock)
- Mock API and in-memory sessions only: no persistence, auth, rate limiting or audit log.
- The web UI is for local use (binds to 127.0.0.1), not hardened for the internet.
- English only. No defence against prompt injection hidden in data such as merchant names.
- No human response time, arrival estimate or authorization-void tool was supplied, so the agent promises none of them.

## Next steps
1. Run the same 12 on a larger open-source model and on Sonnet, and compare.
2. Add a tool to update a ticket, so later information (a bigger fraud loss) reaches the human.
3. Build the read-only transaction search if Paylane agrees.
4. Measure variance: several runs per conversation, not one.
