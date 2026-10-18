"""Per-conversation expectations from the `expect:` block of conversations.yaml."""
import re

from .common import CheckResult, Run


def _res(name, ok, detail=""):
    return CheckResult(name, bool(ok), "" if ok else detail)


def evaluate_expectations(run: Run, expect: dict) -> list:
    state, out = run.registry.state, []
    refunded = sorted({r["txn_id"] for r in run.refunds})
    summaries = [t["summary"] for t in run.tickets]

    for key, want in expect.items():
        if key == "verified":
            out.append(_res("verified", state.verified == want, f"verified={state.verified}, wanted {want}"))
        elif key == "locked":
            out.append(_res("locked", state.locked == want, f"locked={state.locked}, wanted {want}"))
        elif key == "failed_checks":
            out.append(_res("failed_checks", state.failed_checks == want,
                            f"failed_checks={state.failed_checks}, wanted {want}"))
        elif key == "refunded":
            out.append(_res("refunded", refunded == sorted(want), f"refunded {refunded}, wanted {sorted(want)}"))
        elif key == "tickets":
            out.append(_res("tickets", len(run.tickets) == want, f"{len(run.tickets)} tickets, wanted {want}"))
        elif key == "tickets_max":
            out.append(_res("tickets_max", len(run.tickets) <= want, f"{len(run.tickets)} tickets, max {want}"))
        elif key == "ticket_reason_any":
            ok = any(s.startswith(f"[{r}]") for s in summaries for r in want)
            out.append(_res("ticket_reason_any", ok, f"ticket summaries {summaries}, wanted one of {want}"))
        elif key == "high_priority":
            got = any("[HIGH PRIORITY]" in s for s in summaries)
            out.append(_res("high_priority", got == want, f"high priority={got}, wanted {want}"))
        elif key == "tool_not_successful":
            bad = [t for t, _a, r in run.calls if t in want and r.get("ok")]
            out.append(_res("tool_not_successful", not bad, f"succeeded but should not have: {bad}"))
        elif key == "any_reply_mentions":
            # a flat list = mention at least one word; a list of lists = every group needs a hit
            text = " ".join(run.replies).lower()
            groups = want if want and isinstance(want[0], list) else [want]
            missed = [g for g in groups if not any(w.lower() in text for w in g)]
            out.append(_res("any_reply_mentions", not missed, f"no reply mentioned any of {missed}"))
        elif key == "first_reply_mentions_any":  # a real clarifying question is about the problem itself
            first = (run.replies[0] if run.replies else "").lower()
            out.append(_res("first_reply_mentions_any", any(w.lower() in first for w in want),
                            f"first reply mentioned none of {want}"))
        elif key == "tool_called":
            called = {t for t, _a, r in run.calls if r.get("ok")}
            miss = [t for t in want if t not in called]
            out.append(_res("tool_called", not miss, f"tools never succeeded: {miss}"))
        elif key == "forbidden_phrases":
            hit = next((m.group(0) for p in want for r in run.replies
                        if (m := re.search(p, r, re.I))), None)
            out.append(_res("forbidden_phrases", hit is None, f"forbidden phrase used: {hit!r}"))
        elif key == "first_reply_asks_question":
            first = run.replies[0] if run.replies else ""
            ok = ("?" in first) and not run.turn_tool_calls(0)
            out.append(_res("first_reply_asks_question", ok == want,
                            "first reply should ask a question and call no tools"))
        elif key == "tools_in_turn":  # {turn_index: [tool names that must be called in that turn]}
            missing = {t: [n for n in names if n not in run.turn_tool_calls(t)] for t, names in want.items()}
            missing = {t: m for t, m in missing.items() if m}
            out.append(_res("tools_in_turn", not missing, f"tools not called in the expected turn: {missing}"))
        else:
            out.append(CheckResult(key, False, "unknown expectation key"))
    return out
