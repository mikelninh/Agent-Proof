"""Pre-registered three-arm pilot scoring; no synthetic productivity claims.

Input is trusted operator-exported trial telemetry, NOT agent self-report.
All scheduled task/repetition/arm rows, including errors, must be supplied.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import statistics
from typing import Any

ARMS = ("single", "team_local", "team_buzz")


def evaluate(records: list[dict[str, Any]], planned_tasks: list[str], repetitions: int = 3) -> dict[str, Any]:
    if type(repetitions) is not int or repetitions < 1:
        raise ValueError("invalid repetitions")
    if not planned_tasks or len(set(planned_tasks)) != len(planned_tasks):
        raise ValueError("task manifest must be nonempty and unique")
    expected = {(task, rep, arm) for task in planned_tasks for rep in range(repetitions) for arm in ARMS}
    by_key = {}
    for row in records:
        if type(row.get("repetition")) is not int:
            raise ValueError("repetition must be an integer")
        key = (row["task_id"], row["repetition"], row["arm"])
        if key in by_key or key not in expected:
            raise ValueError("duplicate or unplanned observation")
        for field in ("accepted", "critical_failure", "live_evidence"):
            if type(row.get(field)) is not bool:
                raise ValueError(f"{field} must be boolean")
        for field in ("human_minutes", "total_cost_eur", "elapsed_seconds"):
            value = row.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError(f"invalid {field}")
        if row["accepted"] and row["critical_failure"]:
            raise ValueError("a critical failure cannot be accepted")
        by_key[key] = row
    missing = len(expected - by_key.keys())
    output: dict[str, Any] = {"verdict": "HOLD", "reasons": [], "planned_observations": len(expected),
                               "missing_observations": missing, "arms": {}, "comparisons": {}}
    if missing:
        output["reasons"].append("incomplete scheduled observations; never drop failures")
    if len(planned_tasks) < 20 or repetitions < 3:
        output["reasons"].append("exploratory sample: require 20 distinct tasks x 3 repetitions")
    if any(not r["live_evidence"] for r in records) or not records:
        output["reasons"].append("fixtures or absent live evidence cannot establish productivity")
    if any(not r.get("evidence_ref") for r in records):
        output["reasons"].append("operator-verified evidence references required")
    if any(r.get("buzz_roundtrip_verified") is not True for r in records if r["arm"] == "team_buzz"):
        output["reasons"].append("Buzz arm needs verified relay round trips, not just a CLI acknowledgement")
    # Compare same task snapshot and evaluator version across all repetitions/arms.
    for task in planned_tasks:
        rows = [r for r in records if r["task_id"] == task]
        for field in ("input_hash", "evaluator_hash", "budget_policy_hash", "model_policy_hash"):
            values = {r.get(field) for r in rows}
            if None in values or len(values) != 1:
                output["reasons"].append(f"unmatched {field}: {task}")
    for arm in ARMS:
        rows = [r for r in records if r["arm"] == arm]
        accepted = sum(r["accepted"] for r in rows)
        n = len(planned_tasks) * repetitions  # scheduled, not survivors
        metrics = {"scheduled": n, "observed": len(rows), "accepted": accepted,
                   "success_rate": accepted / n, "critical_failures": sum(r["critical_failure"] for r in rows)}
        for field in ("human_minutes", "total_cost_eur", "elapsed_seconds"):
            complete = len(rows) == n and all(r.get(field) is not None for r in rows)
            metrics[field] = sum(r[field] for r in rows) if complete else None
        human = metrics["human_minutes"]
        metrics["accepted_per_human_hour"] = accepted * 60 / human if human and accepted else None
        cost = metrics["total_cost_eur"]
        metrics["cost_per_accepted"] = cost / accepted if cost is not None and accepted else None
        times = [r["elapsed_seconds"] for r in rows if r.get("elapsed_seconds") is not None]
        metrics["median_elapsed_seconds"] = statistics.median(times) if len(times) == n else None
        output["arms"][arm] = metrics
    if any(r["critical_failure"] for r in records):
        output["verdict"] = "BLOCK"
        output["reasons"].append("critical failure observed")
    for base, candidate in (("single", "team_local"), ("team_local", "team_buzz"), ("single", "team_buzz")):
        before, after = output["arms"][base], output["arms"][candidate]
        fixes = regressions = 0
        for task in planned_tasks:
            for rep in range(repetitions):
                old, new = by_key.get((task, rep, base)), by_key.get((task, rep, candidate))
                if old and new:
                    fixes += not old["accepted"] and new["accepted"]
                    regressions += old["accepted"] and not new["accepted"]
        h0, h1 = before["human_minutes"], after["human_minutes"]
        reduction = 1 - h1 / h0 if h0 and h1 is not None else None
        cost0, cost1 = before["cost_per_accepted"], after["cost_per_accepted"]
        passed = (after["success_rate"] >= .9 and after["success_rate"] >= before["success_rate"]
                  and regressions == 0 and reduction is not None and reduction >= .3
                  and cost0 is not None and cost1 is not None and cost1 <= cost0)
        output["comparisons"][f"{base}_vs_{candidate}"] = {"fixes": fixes, "regressions": regressions,
                    "human_time_reduction": reduction, "thresholds_met": passed}
    if any(output["arms"][a][f] is None for a in ARMS for f in ("human_minutes", "total_cost_eur", "elapsed_seconds")):
        output["reasons"].append("cost, human time or elapsed-time measurements missing")
    output["reasons"] = list(dict.fromkeys(output["reasons"]))
    if output["verdict"] != "BLOCK" and not output["reasons"]:
        key = "single_vs_team_buzz"
        output["verdict"] = "PILOT_PASS" if output["comparisons"][key]["thresholds_met"] else "HOLD"
        if output["verdict"] == "HOLD":
            output["reasons"].append("precommitted quality/effort/cost thresholds not met")
    output["caveat"] = "Pilot thresholds are a decision screen, not statistical proof or production approval. Repetitions are clustered within tasks. Test again on fresh held-out tasks."
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text())
    result = evaluate(data["records"], data["planned_tasks"], data.get("repetitions", 3))
    print(json.dumps(result, indent=2, allow_nan=False))
    if result["verdict"] != "PILOT_PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
