# Paylane support agent

An AI chat assistant that answers customer support questions for Paylane, a fintech app with cards, transfers and refunds.

## What it does, in plain terms

A customer writes in, for example "I was charged $40 by a shop I never used, can I get that back?" The agent:

1. Checks who they are. It asks for the email on the account and the last 4 digits of their card, and only then talks about account details.
2. Looks up the account and the charge in Paylane's systems (here, mock versions of them).
3. Decides what happens next. If the charge qualifies, it refunds it on the spot. If it doesn't, or it's a sensitive case like a frozen card, fraud or a legal threat, it passes the customer to a human with a short summary, so nobody has to repeat themselves.
4. Replies in a short, friendly message, and never promises something the policy doesn't allow.

**How it helps.** Routine requests like small refunds and "why is my card frozen?" get answered in seconds, and the support team only sees the cases that need a person. Because the rules sit in code and not only in the AI's instructions, a customer can't talk the agent into a refund it shouldn't give by being angry, persistent or pretending to be someone else.

## Technical summary

A small open-source model (`qwen2.5:7b`, running locally) holds the conversation and calls four tools: `get_customer`, `get_transaction`, `issue_refund` and `escalate_to_human`. The tools are mock functions that take and return JSON, standing in for Paylane's real API. The refund policy is enforced in code around the model, so it can't be broken whatever the customer says.

## Where it stands

- The latest live run passes 12 of 12 conversations (247/247 checks) on `qwen2.5:7b`, against a target of 0.70. Transcripts are in [transcripts/latest](transcripts/latest/).
- My first run scored 2 of 12. The model rarely handed off when it should, and it made up ticket numbers. Fixing that meant moving the policy decisions out of the prompt and into code.
- Please don't read 12/12 as "this works on anything." I built and tuned the agent against these same 12 conversations, and in several of them the code, not the model, decides the outcome.
- There are also 158 deterministic tests. They use fake models, so they prove the code and the checks work. They say nothing about the live model. The live results are only the transcripts.

## How it works

Each turn goes through a policy layer first. It checks for things that must go to a human (legal action, account closure, frozen cards, suspected fraud, a request for a person) and replies with fixed wording when one applies. Otherwise the model gets the conversation and can call the tools. Tool calls pass through guards that refuse anything the policy forbids: refunding before verification, over $75, 30 days or older, pending, someone else's transaction, or a transaction already refunded. Replies are checked before they go out, so card numbers, the email on file and invented promises never reach the customer.

Verification is session state set by code, only after both the email and the last four digits match the mock record. The model can't mark a customer as verified. Three failed checks hand off to a human. More detail is in [docs/architecture.md](docs/architecture.md).

## What it won't do

It won't unfreeze a card, refund a pending charge, refund over $75 or at 30+ days (exactly 30 days escalates), refund the same transaction twice, give partial refunds, reveal full card numbers or the email, or handle legal, fraud or closure cases itself. These go to a human.

## Quick start

You need Python 3.10+ and [Ollama](https://ollama.com).

```
python -m pip install -r requirements.txt
ollama pull qwen2.5:7b
python -m paylane_agent serve        # web chat at http://127.0.0.1:8000
```

No API key is needed. If you want faster replies, paste an Anthropic API key in the web UI, or set `PROVIDER=anthropic` and `ANTHROPIC_API_KEY` (and `pip install anthropic`). Copy `.env.example` to `.env` to change the model or host.

On a laptop CPU the 7B model takes about 25 seconds per reply once warm, and longer on the first call. The UI says so while it waits.

If you only want to check the code without a model, `python -m pytest -q` runs everything offline.

**Test data.** The fixed test date is 2026-10-15 12:00 UTC.

| Customer | Email | Card last 4 | Notes |
|---|---|---|---|
| Monika | monika@example.com | 4242 | Active. `txn_1001` ($40) is refundable, `txn_1002` ($120) goes to a human |
| Deep | deep@example.com | 1111 | Card frozen |
| Fini | fini@example.com | 9876 | Active |

## Commands

| Command | What it does |
|---|---|
| `python -m paylane_agent serve` | Web chat. Add `--hide-internals` for the customer view |
| `python -m paylane_agent chat` | Terminal chat |
| `python -m paylane_agent replay c05_over_limit_pushback` | Run and score one conversation |
| `python -m evals.runner` | Run all 12 and write transcripts and the score to `transcripts/latest` |
| `python -m pytest -q` | The 158 deterministic tests |

## Repo map

```
paylane_agent/        the agent
  agent.py              runs a turn: policy layer, model, tools, reply checks
  policy.py             handoff triggers, fixed replies, the reply checker
  prompts/              system prompt and rulebook given to the model
  tools/                the 4 mock API tools (+ verify_customer), guards, registry
  session/              verification state, fixed test clock
  providers/            Ollama (primary) and Anthropic (optional)
  web/, cli.py          web chat and command line
conversations/        the 12 customer conversations and what each should lead to
evals/                pass/fail checks, runner and score
data/                 mock customers and transactions
tests/                deterministic tests
transcripts/          real model runs: latest/ and failure_and_fix/
docs/                 write-ups (below)
```

## Docs

- [edge_cases.md](docs/edge_cases.md): the 12 conversations and why I picked each edge case
- [evals.md](docs/evals.md): every check and how the score is computed
- [failure_and_fix.md](docs/failure_and_fix.md): one failure I found and how I fixed it
- [architecture.md](docs/architecture.md): how the pieces fit

## Known limits

- The eval set is small and was used while tuning, so the score is optimistic. A held-out set of new conversations is the first thing I'd add.
- A 7B model is slow and can phrase things oddly. The reply checker catches rule breaks, not awkward wording.
- There's no tool to void a pending authorization, no arrival estimate and no human-response SLA, because the spec didn't provide them. The agent says so and doesn't guess.
- Everything runs against mock data with a fixed clock. Real latency, retries and API errors aren't covered.

## AI assistance

I used claude to help write code and tests. I made the design decisions (policy in code, verification as trusted state, Model tuning ), wrote the 12 conversations.

