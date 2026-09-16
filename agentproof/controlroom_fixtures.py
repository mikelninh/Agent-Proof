"""Explicit deterministic fixtures, NOT AI agents or model benchmarks."""
from __future__ import annotations
import json
from pathlib import Path
import sys
import time
from typing import Any


def worker(role: str, scenario: str, data: dict[str, Any]) -> dict[str, Any]:
    if role == "builder":
        if scenario == "timeout":
            time.sleep(5)
        if scenario == "malformed":
            return {"claims_passed": True}  # No artifact: must be rejected.
        bad = scenario in ("false_success", "critical") or (scenario == "repair" and data["attempt"] == 1)
        return {"artifact": {"minor_units": 190 if bad else 199, "currency": "EUR"},
                "claims_passed": True, "claimed_revenue_eur": 1000000}
    if role == "verifier":
        artifact = data["artifact"]
        return {"artifact_hash": "wrong-hash" if scenario == "stale_proof" else data["artifact_hash"],
                "passed": artifact == {"minor_units": 199, "currency": "EUR"},
                "checks": 0 if scenario == "zero_checks" else 2,
                "critical": scenario == "critical"}
    if role == "reviewer":
        return {"artifact_hash": "wrong-hash" if scenario == "stale_review" else data["artifact_hash"],
                "approved": scenario != "review_rejected"}
    raise ValueError("unknown fixture role")


def make_mission(scenario: str = "repair") -> dict[str, Any]:
    script = str(Path(__file__).resolve())
    return {"id": f"money-format-{scenario}", "brief": "Convert EUR 1.99 to integer minor units. Return minor_units and currency.",
            "execution_kind": "fixture", "max_attempts": 2,
            "worker_timeout_seconds": .08 if scenario == "timeout" else 3,
            "mission_timeout_seconds": 20, "frozen_files": [script],
            **{role: {"id": f"fixture-{role}", "argv": [sys.executable, script, role, scenario]}
               for role in ("builder", "verifier", "reviewer")}}


def run_demo(directory: Path) -> dict[str, Any]:
    from agentproof.controlroom import run_mission, dashboard, atomic_json, doctor, verify_run
    directory.mkdir(parents=True, exist_ok=False)
    expected = {"repair": "awaiting_human", "correct": "awaiting_human", "false_success": "blocked",
                "critical": "blocked", "timeout": "blocked", "malformed": "blocked",
                "stale_proof": "blocked", "stale_review": "blocked", "zero_checks": "blocked",
                "review_rejected": "blocked"}
    runs = []
    for case, state in expected.items():
        result = run_mission(make_mission(case), directory / case)
        verify_run(directory / case)
        runs.append({"case": case, "expected": state, "result": result,
                     "contract_passed": result["status"] == state and result["released"] is False})
    summary = {"schema": 1, "evidence_kind": "deterministic_fixture_integration",
               "contracts_passed": all(x["contract_passed"] for x in runs),
               "productivity_verdict": "HOLD_NO_LIVE_EVIDENCE", "live_agent_runs": 0,
               "buzz_relay_runs": 0, "provider_cost_eur": None, "human_minutes": None,
               "environment": doctor(), "runs": runs}
    atomic_json(directory / "summary.json", summary)
    dashboard(summary, directory / "index.html")
    return summary


if __name__ == "__main__":
    print(json.dumps(worker(sys.argv[1], sys.argv[2], json.load(sys.stdin))))
