"""Markdown report from eval results."""


def build_report(results: list, meta: dict) -> str:
    passed = sum(r["passed"] for r in results)
    lines = ["# Eval report", ""]
    lines += [f"- {k}: {v}" for k, v in meta.items()]
    lines += ["", f"**Score: {passed}/{len(results)} conversations passed** "
                  "(a conversation passes only if every check passes).", "",
              "| Conversation | Category | Result | Failed checks |", "|---|---|---|---|"]
    for r in results:
        failed = "; ".join(f"{c['name']}: {c['detail']}" for c in r["checks"] if not c["ok"]) or "-"
        lines.append(f"| {r['id']} | {r['category']} | {'PASS' if r['passed'] else 'FAIL'} | {failed} |")

    total = sum(len(r["checks"]) for r in results)
    ok = sum(c["ok"] for r in results for c in r["checks"])
    lines += ["", f"Individual checks: {ok}/{total} passed.", ""]
    return "\n".join(lines)
