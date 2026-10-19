# Paylane support agent

A customer-support agent for Paylane (cards, transfers, refunds), built for the Fini setup exercise. A small open-source model talks to the customer and calls four mock API tools. **Code enforces the policy**, so the agent cannot refund when the rules say no, and cannot say things it shouldn't, however the customer pushes.

## Where it stands
- **Latest live run: 12/12 conversations pass (1.00), target 0.70.** Model `qwen2.5:7b`, 247/247 checks. See [transcripts/latest](transcripts/latest/).
- **How we got there:** the first run scored 2/12; the main problem was that the model never reliably handed off and invented ticket numbers. Fixing that took a code-enforced policy layer. Full story in [docs/findings.md](docs/findings.md).
- **Read this before trusting 12/12:** I built and tuned the agent against these same 12 conversations, so the score does not show how it handles conversations it has not seen. In several of them the code, not the model, decides the outcome. See [docs/tradeoffs.md](docs/tradeoffs.md).
- 158 deterministic tests pass. They use fake models and prove the code and the checks, not the model.

## Quick start
```
python -m pip install -r requirements.txt     # Python 3.10+
ollama pull qwen2.5:7b                        # primary model, open source, no API key
python -m paylane_agent serve                 # web chat at http://127.0.0.1:8000
```
Optional faster replies: paste an Anthropic API key in the web UI, or set `PROVIDER=anthropic` and `ANTHROPIC_API_KEY` (`pip install anthropic`). Nothing else needs a key. Copy `.env.example` to `.env` to change the model or host.

The 7B model on a laptop CPU takes about 25 s per reply once warm (more on the first). The UI says so while it is in use.

Test customers: Alice (card `4242`, `alice@example.com`), Ben (`1111`, `ben@example.com`, card frozen), Chloe (`9876`, `chloe@example.com`). Fixed test date: 2026-10-15 12:00 UTC. Try `txn_1001` ($40, refundable) and `txn_1002` ($120, goes to a human).

## Commands
| Command | What it does |
|---|---|
| `python -m paylane_agent serve` | Web chat. `--hide-internals` for the customer view |
| `python -m paylane_agent chat` | Terminal chat |
| `python -m paylane_agent replay c05_over_limit_pushback` | Run and score one conversation |
| `python -m evals.runner` | Run all 12, write transcripts and the score to `transcripts/latest` |
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
evals/                the pass/fail checks, runner and score
data/                 mock customers and transactions
tests/                deterministic tests
transcripts/          real model runs: latest/, first_run/, failure_and_fix/
docs/                 the write-ups below
```

## Docs
| Read this | For |
|---|---|
| [customer_note.md](docs/customer_note.md) | The email to the Paylane head of support |
| [edge_cases.md](docs/edge_cases.md) | The 12 conversations and why each edge case was chosen |
| [evals.md](docs/evals.md) | Every check, how the score is computed |
| [failure_and_fix.md](docs/failure_and_fix.md) | One failure found and how it was fixed |
| [findings.md](docs/findings.md) | Results history and what went wrong along the way |
| [architecture.md](docs/architecture.md) | How the pieces fit |
| [tradeoffs.md](docs/tradeoffs.md) | Decisions, limits, what is still open |
| [questions_for_paylane.md](docs/questions_for_paylane.md) | What the brief left open, and the safe default used |

## AI assistance disclosure
I used an AI coding assistant while building this. I can explain and change every part of it. The design choices (policy in code, verification as trusted state) and the review of the live transcripts are written up in the docs.
