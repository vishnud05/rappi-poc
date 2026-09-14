"""Run live-model evaluations in an isolated database, with independent expectations."""

import argparse
import asyncio
import json
from pathlib import Path
import tempfile
import time

from backend.agent import EVIDENCE, MODEL, run_agent
from backend.store import Store, now

# Independent acceptance outcomes. Never included in the model's prompt or tools.
EXPECTED = {
    "review-800": ("modify", 400, "validated", 400),
    "accept-800": ("accept", 800, "validated", 800),
    "sufficient-stock": ("reject", 0, "validated", None),
    "late-incoming": ("modify", 600, "validated", 600),
    "budget-limit": ("investigate", 400, "needs_review", None),
    "storage-limit": ("investigate", 400, "needs_review", None),
    "missing-demand": ("investigate", 0, "needs_review", None),
    "supplier-shortfall": ("modify", 400, "needs_review", 200),
    "timeout-after-commit": ("modify", 400, "validated", 400),
    "changed-budget": ("investigate", 400, "needs_review", None),
}


async def evaluate(selected, output, delay_seconds=65):
    report = {"generated_at": now(), "model": MODEL, "mode": "live", "expected_cases": len(selected),
              "completed": False, "unrun_cases": list(selected), "stopped_reason": None, "results": [], "passed": False}
    with tempfile.TemporaryDirectory() as directory:
        store = Store(Path(directory) / "evaluation.db")
        store.initialize()
        for sid in selected:
            if report["results"]:
                delay = max(0, delay_seconds - (time.monotonic() - started))
                if delay:
                    print(f"Waiting {delay:.0f}s before the next case to respect provider request limits.", flush=True)
                    await asyncio.sleep(delay)
            expected_decision, expected_quantity, expected_status, expected_confirmed = EXPECTED[sid]
            run = store.start_run(sid, MODEL)
            started = time.monotonic()
            await run_agent(store, run["id"])
            run = store.run(run["id"])
            state = store.scenario(sid)
            tools = [event["name"] for event in run["events"] if event["kind"] == "tool_result" and "error" not in event["detail"]]
            po = run["purchase_order"]
            checks = {
                "decision": run["decision"] == expected_decision,
                "quantity": run["quantity"] == expected_quantity,
                "status": run["status"] == expected_status,
                "evidence": EVIDENCE <= set(tools),
                "action": (po["confirmed_units"] if po else None) == expected_confirmed,
                "single_order": len(state["purchase_orders"]) == (1 if expected_confirmed is not None else 0),
                "verification": bool(run["validation"]) and ("verify_outcome" in tools if po else True),
                "constraint_compliance": state["budget_cents"] >= 0,
            }
            if sid == "supplier-shortfall":
                checks["shortage_detected"] = bool(run["validation"]) and run["validation"]["shortage_units"] == 200
            if sid == "timeout-after-commit":
                checks["timeout_recovered"] = "lookup_purchase" in tools and state["budget_cents"] == 300000
            if sid == "changed-budget":
                checks["reassessed"] = tools.count("assess_purchase") >= 2
            result = {"scenario_id": sid, "passed": all(checks.values()), "checks": checks,
                      "duration_seconds": round(time.monotonic() - started, 2), "run": run}
            report["results"].append(result)
            print(f"{'PASS' if result['passed'] else 'FAIL'} {sid}: {run['decision']} {run['quantity']} -> {run['status']} ({result['duration_seconds']}s)", flush=True)
            report["completed"] = len(report["results"]) == len(selected)
            report["unrun_cases"] = list(selected[len(report["results"]):])
            report["passed"] = report["completed"] and all(result["passed"] for result in report["results"])
            quota_exhausted = bool(run["error"] and "429" in run["error"])
            if quota_exhausted:
                report["stopped_reason"] = "Provider quota blocked further live evaluation. Remaining cases were not run."
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
            if quota_exhausted:
                print(report["stopped_reason"], flush=True)
                break
    return report["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", action="append", choices=list(EXPECTED), help="Repeat to select cases; default runs all.")
    parser.add_argument("--output", type=Path, default=Path("data/evaluation-results.json"))
    parser.add_argument("--delay-seconds", type=float, default=65, help="Minimum interval between case starts; default 65 respects low provider request quotas.")
    args = parser.parse_args()
    if args.delay_seconds < 0:
        parser.error("--delay-seconds must be nonnegative")
    raise SystemExit(0 if asyncio.run(evaluate(args.scenario or list(EXPECTED), args.output, args.delay_seconds)) else 1)


if __name__ == "__main__":
    main()
