#!/usr/bin/env python3
"""ASTRA Control Room v0.1: local evidence loop, not an autonomous workforce.

Python 3.11+, standard library only. No production deployment implementation.
Run: python astra.py demo --out evidence
     python astra.py score pilot.json
     python astra.py buzz-publish --channel UUID --report evidence/report.json
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import hmac
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any

VERSION = "0.1.0"
STAGES = ["SHAPE", "SPECIFY", "DELEGATE", "PROVE", "SHIP", "WATCH"]


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def nonnegative(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite nonnegative number")
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a finite nonnegative number")
    return float(value)


class GateError(ValueError):
    pass


class Room:
    """Transactional local gate. Trusted host only; NOT a worker sandbox.

    Worker submissions are untrusted until the caller's trusted verifier checks
    them. Do not give workers this process, its secret, or write access to its DB.
    Hash chaining detects edits relative to a retained trusted head; an attacker
    with full DB access can rewrite the chain. It is not a Nostr signature.
    """
    def __init__(self, db: str | Path, approver_secret: bytes):
        if len(approver_secret) < 32:
            raise ValueError("Use an approver secret of at least 32 bytes")
        self.secret = approver_secret
        self.db = sqlite3.connect(str(db), timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS missions (
          id TEXT PRIMARY KEY, state TEXT NOT NULL, data TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, mission TEXT NOT NULL,
          event TEXT NOT NULL, prev TEXT NOT NULL, hash TEXT NOT NULL);
        """)

    def close(self):
        self.db.close()

    def _event(self, mid: str, kind: str, payload: dict):
        row = self.db.execute("SELECT hash FROM events ORDER BY seq DESC LIMIT 1").fetchone()
        prev = row[0] if row else "0" * 64
        event = {"mission": mid, "kind": kind, "at_unix": time.time(), "payload": payload}
        self.db.execute("INSERT INTO events(mission,event,prev,hash) VALUES (?,?,?,?)",
                        (mid, canonical(event), prev, digest({"prev": prev, "event": event})))

    def _save(self, mid: str, state: str, data: dict):
        self.db.execute("UPDATE missions SET state=?,data=? WHERE id=?",
                        (state, canonical({k: v for k, v in data.items() if k not in {"id", "state"}}), mid))

    def get(self, mid: str) -> dict:
        row = self.db.execute("SELECT * FROM missions WHERE id=?", (mid,)).fetchone()
        if row is None:
            raise GateError("Unknown mission")
        return {**json.loads(row["data"]), "id": mid, "state": row["state"]}

    def create(self, mid: str, title: str, budget_cents: int = 300):
        if not isinstance(budget_cents, int) or isinstance(budget_cents, bool) or budget_cents < 0:
            raise GateError("budget_cents must be a nonnegative integer")
        data = {"title": title, "budget_cents": budget_cents, "reserved_cents": 0,
                "reservations": {}, "proof": None}
        with self.db:
            self.db.execute("INSERT INTO missions VALUES (?,?,?)", (mid, "planned", canonical(data)))
            self._event(mid, "SHAPE", {"title": title})
            self._event(mid, "SPECIFY", {"budget_cents": budget_cents,
                "acceptance": "Trusted checks pass; unchanged artifact; human authorisation."})

    def reserve(self, mid: str, job_id: str, cents: int):
        """Reserve estimated spend BEFORE dispatch; not a provider billing meter."""
        if not isinstance(cents, int) or isinstance(cents, bool) or cents < 0:
            raise GateError("Invalid reservation")
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            m = self.get(mid)
            if m["state"] not in {"planned", "running"}:
                raise GateError("Mission cannot dispatch work in this state")
            if job_id in m["reservations"]:
                if m["reservations"][job_id] != cents:
                    raise GateError("Conflicting duplicate job")
                return
            if m["reserved_cents"] + cents > m["budget_cents"]:
                raise GateError("Budget exhausted before dispatch")
            m["reservations"][job_id] = cents
            m["reserved_cents"] += cents
            self._save(mid, "running", m)
            self._event(mid, "DELEGATE", {"job_id": job_id, "reserved_cents": cents})

    def submit_verified(self, mid: str, artifact: Path, checks: dict):
        """TRUSTED VERIFIER API: never expose directly to an agent/webhook."""
        count = checks.get("tests")
        valid = (checks.get("exit_code") == 0 and type(checks.get("exit_code")) is int
                 and type(count) is int and count > 0
                 and type(checks.get("failures")) is int and checks["failures"] == 0
                 and checks.get("scope_ok") is True
                 and checks.get("checks_unchanged") is True)
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            m = self.get(mid)
            if m["state"] != "running":
                raise GateError("No active mission")
            m["proof"] = {"artifact_sha256": file_hash(artifact), "checks": checks,
                          "nonce": secrets.token_hex(16), "expires_at": time.time() + 900}
            self._save(mid, "awaiting_approval" if valid else "blocked", m)
            self._event(mid, "PROVE", {"valid": valid, **m["proof"]})
        return self.get(mid)

    def authorisation(self, mid: str, actor: str = "michael") -> str:
        """Trusted human-side signer; never run this inside a worker."""
        m = self.get(mid)
        return hmac.new(self.secret, canonical({"mission": mid, "actor": actor,
                        "proof": m["proof"]}).encode(), hashlib.sha256).hexdigest()

    def approve(self, mid: str, artifact: Path, token: str, actor: str = "michael"):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            m = self.get(mid)
            if m["state"] != "awaiting_approval":
                raise GateError("Approval not available or already consumed")
            if actor != "michael" or not hmac.compare_digest(token, self.authorisation(mid, actor)):
                raise GateError("Invalid authorisation")
            if time.time() >= m["proof"]["expires_at"]:
                raise GateError("Approval expired")
            if file_hash(artifact) != m["proof"]["artifact_sha256"]:
                raise GateError("Artifact changed after verification")
            self._save(mid, "approved_local", m)
            self._event(mid, "SHIP", {"actor": actor, "scope": "local artifact only",
                "artifact_sha256": m["proof"]["artifact_sha256"], "production_deployed": False})
        return self.get(mid)

    def stop(self, mid: str):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            m = self.get(mid)
            if m["state"] not in {"planned", "running", "awaiting_approval"}:
                raise GateError("Mission already terminal")
            self._save(mid, "stopped", m)
            self._event(mid, "STOP", {"new_dispatch_disabled": True})

    def events(self) -> list[dict]:
        return [{"seq": r["seq"], "hash": r["hash"], "prev": r["prev"],
                 **json.loads(r["event"])} for r in self.db.execute("SELECT * FROM events ORDER BY seq")]

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for r in self.db.execute("SELECT * FROM events ORDER BY seq"):
            if r["prev"] != prev or r["hash"] != digest({"prev": prev, "event": json.loads(r["event"])}):
                return False
            prev = r["hash"]
        return True


def run_command(args: list[str], cwd: Path, timeout: float = 20) -> dict:
    """Explicit trusted commands only. Process timeout != OS isolation.

    Output goes to a temporary file (bounded in saved receipt, not disk quota).
    Children receive no API/approval keys. POSIX timeout kills process group;
    Windows kills direct process only. Use a VM/container for untrusted code.
    """
    if not args or timeout <= 0:
        raise ValueError("Command and positive timeout required")
    env = {k: v for k, v in os.environ.items() if k in {
        "PATH", "SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG", "LC_ALL"}}
    started = time.monotonic()
    with tempfile.TemporaryFile() as output:
        proc = subprocess.Popen(args, cwd=cwd, stdout=output, stderr=subprocess.STDOUT,
                                env=env, start_new_session=(os.name == "posix"))
        timed_out = False
        try:
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "posix":
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                proc.kill()
            proc.wait()
        output.seek(0)
        text = output.read(65536).decode("utf-8", errors="replace")
    match = re.search(r"Ran (\d+) tests?", text)
    return {"command": args, "exit_code": proc.returncode,
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "timed_out": timed_out, "tests": int(match[1]) if match else 0,
            "stdout": text, "stdout_sha256": hashlib.sha256(text.encode()).hexdigest()}


BROKEN = '''def can_release(success_rate, critical_failures):
    return success_rate >= 0.95
'''
FIXED = '''import math

def can_release(success_rate, critical_failures):
    if isinstance(success_rate, bool) or not isinstance(success_rate, (int, float)):
        return False
    if not math.isfinite(success_rate) or not 0 <= success_rate <= 1:
        return False
    if type(critical_failures) is not int or critical_failures < 0:
        return False
    return success_rate >= 0.95 and critical_failures == 0
'''
CHECKS = '''import unittest
from target import can_release
class Checks(unittest.TestCase):
    def test_valid(self): self.assertTrue(can_release(0.99, 0))
    def test_threshold(self): self.assertTrue(can_release(0.95, 0))
    def test_low_quality(self): self.assertFalse(can_release(0.94, 0))
    def test_critical(self): self.assertFalse(can_release(1.0, 1))
    def test_missing_critical(self): self.assertFalse(can_release(1.0, None))
    def test_negative_critical(self): self.assertFalse(can_release(1.0, -1))
    def test_boolean(self): self.assertFalse(can_release(True, 0))
    def test_invalid_rate(self): self.assertFalse(can_release(1.1, 0))
    def test_nan(self): self.assertFalse(can_release(float('nan'), 0))
    def test_infinity(self): self.assertFalse(can_release(float('inf'), 0))
    def test_missing_rate(self): self.assertFalse(can_release(None, 0))
    def test_boolean_critical(self): self.assertFalse(can_release(1.0, False))
if __name__ == '__main__': unittest.main(verbosity=2)
'''


def demo(out: Path) -> dict:
    """Real filesystem edits and subprocess tests; SCRIPTED builder, not an LLM."""
    out.mkdir(parents=True, exist_ok=True)
    mid = "gate-repair-" + uuid.uuid4().hex[:8]
    workspace = out / mid
    workspace.mkdir()
    target, tests = workspace / "target.py", workspace / "checks.py"
    target.write_text(BROKEN)
    tests.write_text(CHECKS)
    checks_hash = file_hash(tests)
    room = Room(workspace / "mission.sqlite", secrets.token_bytes(32))
    room.create(mid, "Repair a release gate that ignores critical failures")
    room.reserve(mid, "baseline-check", 0)
    baseline = run_command([sys.executable, "-B", "checks.py"], workspace)
    room.reserve(mid, "scripted-builder", 0)
    target.write_text(FIXED)
    patch = "".join(difflib.unified_diff(BROKEN.splitlines(True), FIXED.splitlines(True),
                                        fromfile="a/target.py", tofile="b/target.py"))
    (workspace / "patch.diff").write_text(patch)
    room.reserve(mid, "trusted-verifier", 0)
    candidate = run_command([sys.executable, "-B", "checks.py"], workspace)
    checks = {**candidate, "failures": 0 if candidate["exit_code"] == 0 else 1,
              "scope_ok": True, "checks_unchanged": file_hash(tests) == checks_hash}
    mission = room.submit_verified(mid, target, checks)
    report = {"schema": "astra-report-v1", "version": VERSION, "created_at_unix": time.time(),
        "evidence_kind": "scripted_local_integration", "mission": mission,
        "baseline": baseline, "candidate": candidate, "patch": patch,
        "events": room.events(), "chain_valid": room.verify_chain(),
        "integration": {"buzz": "not_connected", "llm_workers": "not_run",
                        "agentproof_live": "not_run", "production_deployed": False},
        "measurements": {"real_pilot_tasks": 0, "human_minutes_saved": None,
                         "cost_per_accepted_task_eur": None, "revenue_eur": None,
                         "api_spend_eur": 0, "compute_cost_eur": None},
        "verdict": "LOCAL_PROOF_ONLY" if mission["state"] == "awaiting_approval" else "BLOCK",
        "limits": ["The repair is prewritten, not generated by an AI agent.",
                   "Tests validate this fixture, not general coding ability.",
                   "No human time baseline, paid inference, live relay, or customer outcome measured.",
                   "Approval is intentionally pending; no production action exists."]}
    room.close()
    (workspace / "baseline.json").write_text(json.dumps(baseline, indent=2))
    (workspace / "candidate.json").write_text(json.dumps(candidate, indent=2))
    (out / "report.json").write_text(json.dumps(report, indent=2))
    return report


def score_pilot(data: dict) -> dict:
    """Score preregistered live tasks; all failures/aborts remain in denominator.

    Each task has one aggregate record per arm, including ALL its retries.
    Missing observations are NOT zero. Synthetic runs cannot enter this score.
    """
    tasks = data.get("task_ids", [])
    if not tasks or len(set(tasks)) != len(tasks) or not all(isinstance(t, str) and t for t in tasks):
        raise ValueError("Unique preregistered task_ids required")
    rows = data.get("records", [])
    seen = set()
    for row in rows:
        key = (row["task_id"], row["arm"])
        if row["task_id"] not in tasks or row["arm"] not in {"baseline", "single", "buzz"} or key in seen:
            raise ValueError("Unknown/duplicate task-arm record")
        seen.add(key)
        if row.get("evidence_kind") != "live":
            raise ValueError("Do not mix scripted/synthetic records into a live pilot")
        for flag in ("accepted", "critical_failure", "unauthorised_action", "evidence_complete", "watch_passed"):
            if type(row.get(flag)) is not bool:
                raise ValueError(f"{flag} requires a boolean")
        for num in ("human_minutes", "wall_minutes", "api_eur", "compute_eur", "rework_minutes"):
            if row.get(num) is not None:
                nonnegative(row[num], num)
        if row.get("human_minutes") is not None and row.get("rework_minutes") is not None:
            if row["rework_minutes"] > row["human_minutes"]:
                raise ValueError("Rework is a subset of human time, not additional")
        if row["accepted"] and (not row["evidence_complete"] or not row["watch_passed"]
                                or row["critical_failure"] or row["unauthorised_action"]):
            raise ValueError("Accepted requires proof, watch pass and no critical/unauthorised action")
    result = {"tasks_planned_per_arm": len(tasks), "arms": {}, "verdict": "NOT_MEASURED",
              "thresholds_are_pilot_choices": True}
    for arm in ("baseline", "single", "buzz"):
        rr = [r for r in rows if r["arm"] == arm]
        complete = len(rr) == len(tasks)
        accepted = sum(r["accepted"] for r in rr)
        human = sum(r["human_minutes"] for r in rr) if complete and all(r.get("human_minutes") is not None for r in rr) else None
        cash = sum(r["api_eur"] + r["compute_eur"] for r in rr) if complete and all(r.get("api_eur") is not None and r.get("compute_eur") is not None for r in rr) else None
        hourly = data.get("assumed_hourly_value_eur")
        if hourly is not None:
            nonnegative(hourly, "assumed_hourly_value_eur")
        total = cash + human / 60 * hourly if cash is not None and human is not None and hourly is not None else None
        result["arms"][arm] = {"observed": len(rr), "accepted": accepted,
            "completion_rate": accepted / len(tasks), "complete": complete,
            "human_minutes": human, "cash_cost_eur": cash,
            "total_cost_with_assumed_time_value_eur": total,
            "cost_per_accepted_task_eur": total / accepted if total is not None and accepted else None,
            "accepted_tasks_per_human_hour": accepted / (human / 60) if human is not None and human > 0 else None,
            "critical_failures": sum(r["critical_failure"] for r in rr),
            "unauthorised_actions": sum(r["unauthorised_action"] for r in rr),
            "evidence_coverage": sum(r["evidence_complete"] for r in rr) / len(tasks)}
    a = result["arms"]
    if any(v["critical_failures"] or v["unauthorised_actions"] for k, v in a.items() if k != "baseline"):
        result["verdict"] = "STOP_SAFETY_FAILURE"
        return result
    if not all(v["complete"] for v in a.values()):
        result["verdict"] = "INCOMPLETE" if rows else "NOT_MEASURED"
        return result
    if len(tasks) < 10:
        result["verdict"] = "INSUFFICIENT_SAMPLE"
        return result
    if any(v["human_minutes"] is None or v["cost_per_accepted_task_eur"] is None for v in a.values()):
        result["verdict"] = "MISSING_TIME_OR_COST"
        return result
    if a["baseline"]["human_minutes"] == 0 or a["single"]["human_minutes"] == 0:
        result["verdict"] = "UNDEFINED_BASELINE"
        return result
    savings = 1 - a["buzz"]["human_minutes"] / a["baseline"]["human_minutes"]
    vs_single = 1 - a["buzz"]["human_minutes"] / a["single"]["human_minutes"]
    result.update(human_time_reduction_vs_baseline=savings, human_time_reduction_vs_single=vs_single)
    quality = a["buzz"]["completion_rate"] >= max(.8, a["baseline"]["completion_rate"], a["single"]["completion_rate"])
    cost_ok = a["buzz"]["cost_per_accepted_task_eur"] <= a["single"]["cost_per_accepted_task_eur"]
    result["verdict"] = "PROMISING_REPLICATE" if quality and savings >= .30 and vs_single >= .15 and cost_ok and a["buzz"]["evidence_coverage"] == 1 else "DO_NOT_SCALE"
    result["caveat"] = "10 tasks are a directional pilot, not statistical proof or product-market fit. Replicate on an untouched holdout."
    return result


def review_agentproof(baseline: dict, candidate: dict) -> dict:
    """Review trusted Agent-Proof RunRecord exports; never trust worker grades.

    This validates consistency and compares already-graded cases. It does not
    independently rerun the grader or establish that the exporting service is
    trustworthy. No report is silently promoted into live pilot measurements.
    """
    if not baseline.get("pack_id") or baseline["pack_id"] != candidate.get("pack_id"):
        raise ValueError("Agent-Proof pack IDs must match")
    indexed = []
    for record in (baseline, candidate):
        cases = record.get("cases", [])
        if not cases or len({c["case_id"] for c in cases}) != len(cases):
            raise ValueError("Nonempty, unique Agent-Proof cases required")
        for case in cases:
            if type(case["grade"].get("passed")) is not bool or type(case["grade"].get("critical_failure")) is not bool:
                raise ValueError("Invalid Agent-Proof grade")
            if case["grade"]["passed"] and (case["grade"]["critical_failure"] or case["output"].get("error")):
                raise ValueError("Contradictory grade")
        n = len(cases)
        metrics = record["metrics"]
        success = sum(c["grade"]["passed"] for c in cases) / n
        critical = sum(c["grade"]["critical_failure"] for c in cases) / n
        for key, actual in (("success_rate", success), ("critical_failure_rate", critical)):
            reported = nonnegative(metrics.get(key), key)
            if abs(reported - actual) > 1e-8:
                raise ValueError("Aggregate metrics disagree with case receipts")
        if type(metrics.get("total_cases")) is not int or metrics["total_cases"] != n:
            raise ValueError("Case count mismatch")
        indexed.append({c["case_id"]: c for c in cases})
    a, b = indexed
    if set(a) != set(b):
        raise ValueError("Cannot compare different case populations")
    for key in a:
        if digest({"input": a[key]["input"], "expected": a[key]["expected"]}) != digest({"input": b[key]["input"], "expected": b[key]["expected"]}):
            raise ValueError("Input or ground truth changed between runs")
    fixes = sum(not a[k]["grade"]["passed"] and b[k]["grade"]["passed"] for k in a)
    regressions = sum(a[k]["grade"]["passed"] and not b[k]["grade"]["passed"] for k in a)
    new_critical = sum(not a[k]["grade"]["critical_failure"] and b[k]["grade"]["critical_failure"] for k in a)
    ready = (candidate["gate"]["status"] == "pass" and candidate["metrics"]["success_rate"] >= .95
             and candidate["metrics"]["critical_failure_rate"] == 0 and fixes >= regressions)
    demo_providers = {"heuristic", "heuristic_v2", "demo_baseline", "demo_candidate", "demo_risky"}
    synthetic = any(r["agent"]["provider"] in demo_providers for r in (baseline, candidate))
    return {"schema": "astra-agentproof-review-v1", "paired_cases": len(a),
        "baseline_sha256": digest(baseline), "candidate_sha256": digest(candidate),
        "fixes": fixes, "regressions": regressions, "new_critical_failures": new_critical,
        "evidence_kind": "synthetic_agentproof" if synthetic else "external_agentproof_report",
        "verdict": "READY_FOR_HUMAN_REVIEW" if ready else "BLOCK",
        "production_deployed": False, "economic_benefit_measured": False,
        "trust_boundary": "Case grades and ground truth must come from the trusted evaluator, not the worker."}


class BuzzCLI:
    """Explicit outbound report adapter. No dispatch, approval or auto-retry.

    Command contract checked against block/buzz CLI README. Live unverified.
    """
    def __init__(self, channel: str, executable: str = "buzz"):
        self.channel = str(uuid.UUID(channel))
        self.executable = executable

    def publish(self, report: dict, timeout: float = 15) -> dict:
        payload = {"schema": report["schema"], "version": report["version"],
                   "mission_id": report["mission"]["id"], "verdict": report["verdict"],
                   "evidence_kind": report["evidence_kind"], "report_sha256": digest(report),
                   "production_deployed": False}
        try:
            result = subprocess.run([self.executable, "messages", "send", "--channel", self.channel,
                                     "--content", "-"], input=canonical(payload),
                                    capture_output=True, text=True, timeout=timeout, check=False)
        except FileNotFoundError:
            return {"status": "not_configured", "delivered": False}
        except subprocess.TimeoutExpired:
            return {"status": "delivery_unknown", "delivered": None, "retry_safe": False}
        if result.returncode != 0:
            return {"status": "delivery_unknown", "exit_code": result.returncode,
                    "delivered": None, "retry_safe": False}
        try:
            receipt = json.loads(result.stdout)
        except json.JSONDecodeError:
            return {"status": "invalid_receipt", "delivered": None, "retry_safe": False}
        return {"status": "cli_acknowledged", "delivered": True,
                "readback_verified": False, "receipt": receipt}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("demo"); d.add_argument("--out", type=Path, default=Path("evidence"))
    s = sub.add_parser("score"); s.add_argument("input", type=Path)
    a = sub.add_parser("agentproof-review"); a.add_argument("baseline", type=Path); a.add_argument("candidate", type=Path)
    b = sub.add_parser("buzz-publish"); b.add_argument("--channel", required=True); b.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            r = demo(args.out)
            print(json.dumps({"report": str(args.out / "report.json"), "verdict": r["verdict"],
                              "candidate_tests": r["candidate"]["tests"], "state": r["mission"]["state"]}, indent=2))
            return 0 if r["verdict"] == "LOCAL_PROOF_ONLY" else 1
        if args.command == "score":
            r = score_pilot(json.loads(args.input.read_text())); print(json.dumps(r, indent=2))
            return 0 if r["verdict"] == "PROMISING_REPLICATE" else 2
        if args.command == "agentproof-review":
            r = review_agentproof(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
            print(json.dumps(r, indent=2)); return 0 if r["verdict"] == "READY_FOR_HUMAN_REVIEW" else 2
        r = BuzzCLI(args.channel).publish(json.loads(args.report.read_text()))
        print(json.dumps(r, indent=2)); return 0 if r.get("delivered") else 2
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2

if __name__ == "__main__":
    raise SystemExit(main())
