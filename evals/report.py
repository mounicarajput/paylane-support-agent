"""Markdown report from eval results."""

TARGET = 0.70  # required share of conversations that must pass


def score(results: list) -> float:
    return sum(r["passed"] for r in results) / len(results) if results else 0.0


def build_report(results: list, meta: dict, target: float = TARGET) -> str:
    passed, s = sum(r["passed"] for r in results), score(results)
    lines = ["# Eval report", ""]
    lines += [f"- {k}: {v}" for k, v in meta.items()]
    lines += ["", f"**Score: {passed}/{len(results)} conversations passed = {s:.2f}** "
                  f"(target at least {target:.2f}: {'MET' if s >= target else 'NOT MET'}). "
                  "A conversation passes only if every one of its checks passes.", "",
              "| Conversation | Category | Result | Failed checks |", "|---|---|---|---|"]
    for r in results:
        failed = "; ".join(f"{c['name']}: {c['detail']}" for c in r["checks"] if not c["ok"]) or "-"
        lines.append(f"| {r['id']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | {failed} |")

    total = sum(len(r["checks"]) for r in results)
    ok = sum(c["ok"] for r in results for c in r["checks"])
    lines += ["", f"Individual checks: {ok}/{total} passed ({ok / total:.2f}). "
                  "This is a secondary number; the score above is the one to quote.", ""]
    return "\n".join(lines)
