"""Deterministic safety/measurement tests; not live-agent benchmark evidence."""
import copy
import json
import os
from pathlib import Path
import secrets
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from astra import Room, GateError, BuzzCLI, demo, digest, run_command, score_pilot, review_agentproof


def checks(**changes):
    return {"exit_code": 0, "tests": 12, "failures": 0, "scope_ok": True,
            "checks_unchanged": True, **changes}


def pilot(n=10):
    """Schema fixtures marked live ONLY to exercise parser; not actual pilot data."""
    data = {"task_ids": [f"task-{i}" for i in range(n)],
            "assumed_hourly_value_eur": 40, "records": []}
    for task in data["task_ids"]:
        for arm, human in (("baseline", 30), ("single", 20), ("buzz", 12)):
            data["records"].append({"task_id": task, "arm": arm, "evidence_kind": "live",
                "accepted": True, "critical_failure": False, "unauthorised_action": False,
                "evidence_complete": True, "watch_passed": True, "human_minutes": human,
                "wall_minutes": human + 10, "api_eur": 1, "compute_eur": .1, "rework_minutes": 1})
    return data


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.artifact = self.root / "artifact.py"
        self.artifact.write_text("verified contents")
        self.secret = secrets.token_bytes(32)
        self.room = Room(self.root / "room.sqlite", self.secret)
        self.room.create("m", "test", 100)

    def tearDown(self):
        self.room.close()
        self.tmp.cleanup()

    def ready(self):
        self.room.reserve("m", "build", 10)
        return self.room.submit_verified("m", self.artifact, checks())

    def test_state_is_authoritative_after_checkpoint(self):
        self.room.reserve("m", "build", 10)
        self.assertEqual(self.room.get("m")["state"], "running")
        self.assertEqual(self.room.submit_verified("m", self.artifact, checks())["state"], "awaiting_approval")

    def test_valid_proof_stops_before_approval(self):
        self.assertEqual(self.ready()["state"], "awaiting_approval")
        self.assertFalse(any(e["kind"] == "SHIP" for e in self.room.events()))

    def test_explicit_local_approval(self):
        self.ready()
        result = self.room.approve("m", self.artifact, self.room.authorisation("m"))
        self.assertEqual(result["state"], "approved_local")
        self.assertFalse(self.room.events()[-1]["payload"]["production_deployed"])

    def test_fake_token_blocked(self):
        self.ready()
        with self.assertRaises(GateError): self.room.approve("m", self.artifact, "fake")
        self.assertEqual(self.room.get("m")["state"], "awaiting_approval")

    def test_worker_self_approval_blocked(self):
        self.ready()
        token = self.room.authorisation("m", "builder")
        with self.assertRaises(GateError): self.room.approve("m", self.artifact, token, "builder")

    def test_changed_artifact_blocked(self):
        self.ready(); token = self.room.authorisation("m")
        self.artifact.write_text("modified after verification")
        with self.assertRaises(GateError): self.room.approve("m", self.artifact, token)

    def test_replayed_approval_blocked(self):
        self.ready(); token = self.room.authorisation("m")
        self.room.approve("m", self.artifact, token)
        with self.assertRaises(GateError): self.room.approve("m", self.artifact, token)

    def test_expired_approval_blocked(self):
        self.ready(); token = self.room.authorisation("m")
        with patch("astra.time.time", return_value=time.time() + 1000):
            with self.assertRaises(GateError): self.room.approve("m", self.artifact, token)

    def test_token_bound_to_mission(self):
        self.ready(); token = self.room.authorisation("m")
        self.room.create("m2", "other", 100); self.room.reserve("m2", "build", 10)
        self.room.submit_verified("m2", self.artifact, checks())
        with self.assertRaises(GateError): self.room.approve("m2", self.artifact, token)

    def test_no_proof_no_approval(self):
        with self.assertRaises(GateError): self.room.approve("m", self.artifact, "anything")

    def test_failed_checks_block(self):
        self.room.reserve("m", "build", 1)
        self.assertEqual(self.room.submit_verified("m", self.artifact, checks(exit_code=1))["state"], "blocked")

    def test_empty_test_suite_blocks(self):
        self.room.reserve("m", "build", 1)
        self.assertEqual(self.room.submit_verified("m", self.artifact, checks(tests=0))["state"], "blocked")

    def test_missing_failures_blocks(self):
        self.room.reserve("m", "build", 1)
        c = checks(); del c["failures"]
        self.assertEqual(self.room.submit_verified("m", self.artifact, c)["state"], "blocked")

    def test_boolean_exit_code_blocks(self):
        self.room.reserve("m", "build", 1)
        self.assertEqual(self.room.submit_verified("m", self.artifact, checks(exit_code=False))["state"], "blocked")

    def test_changed_tests_block(self):
        self.room.reserve("m", "build", 1)
        self.assertEqual(self.room.submit_verified("m", self.artifact, checks(checks_unchanged=False))["state"], "blocked")

    def test_out_of_scope_patch_blocks(self):
        self.room.reserve("m", "build", 1)
        self.assertEqual(self.room.submit_verified("m", self.artifact, checks(scope_ok=False))["state"], "blocked")

    def test_over_budget_stops_before_dispatch(self):
        with self.assertRaises(GateError): self.room.reserve("m", "build", 101)
        self.assertEqual(self.room.get("m")["reserved_cents"], 0)

    def test_budget_boundary_allowed(self):
        self.room.reserve("m", "build", 100)
        with self.assertRaises(GateError): self.room.reserve("m", "retry", 1)

    def test_duplicate_reservation_idempotent(self):
        self.room.reserve("m", "build", 60); self.room.reserve("m", "build", 60)
        self.assertEqual(self.room.get("m")["reserved_cents"], 60)
        self.assertEqual(len([e for e in self.room.events() if e["kind"] == "DELEGATE"]), 1)

    def test_conflicting_duplicate_reservation_blocks(self):
        self.room.reserve("m", "build", 60)
        with self.assertRaises(GateError): self.room.reserve("m", "build", 61)

    def test_negative_budget_rejected(self):
        with self.assertRaises(GateError): self.room.reserve("m", "build", -1)

    def test_stop_blocks_new_dispatch(self):
        self.room.stop("m")
        with self.assertRaises(GateError): self.room.reserve("m", "build", 0)

    def test_stop_blocks_pending_approval(self):
        self.ready(); token = self.room.authorisation("m"); self.room.stop("m")
        with self.assertRaises(GateError): self.room.approve("m", self.artifact, token)

    def test_state_survives_reopen(self):
        self.ready(); self.room.close()
        self.room = Room(self.root / "room.sqlite", self.secret)
        self.assertEqual(self.room.get("m")["state"], "awaiting_approval")
        self.assertTrue(self.room.verify_chain())

    def test_audit_mutation_detected(self):
        self.ready()
        self.room.db.execute("UPDATE events SET event='{}' WHERE seq=1")
        self.room.db.commit()
        self.assertFalse(self.room.verify_chain())

    def test_approval_secret_absent_from_events(self):
        self.ready()
        self.assertNotIn(self.secret.hex(), json.dumps(self.room.events()))

    def test_unknown_mission_rejected(self):
        with self.assertRaises(GateError): self.room.get("unknown")


class MeasurementTests(unittest.TestCase):
    def test_no_live_runs_not_measured(self):
        self.assertEqual(score_pilot({"task_ids": ["a"], "records": []})["verdict"], "NOT_MEASURED")

    def test_complete_directional_pilot(self):
        s = score_pilot(pilot())
        self.assertEqual(s["verdict"], "PROMISING_REPLICATE")
        self.assertAlmostEqual(s["human_time_reduction_vs_baseline"], .6)
        self.assertAlmostEqual(s["arms"]["buzz"]["accepted_tasks_per_human_hour"], 5)
        self.assertAlmostEqual(s["arms"]["buzz"]["cost_per_accepted_task_eur"], 9.1)

    def test_missing_arm_not_success(self):
        p = pilot(); p["records"] = p["records"][:-1]
        self.assertEqual(score_pilot(p)["verdict"], "INCOMPLETE")

    def test_duplicate_attempt_rejected(self):
        p = pilot(); p["records"].append(p["records"][0])
        with self.assertRaises(ValueError): score_pilot(p)

    def test_synthetic_cannot_be_live_evidence(self):
        p = pilot(); p["records"][0]["evidence_kind"] = "scripted"
        with self.assertRaises(ValueError): score_pilot(p)

    def test_unknown_cost_not_free(self):
        p = pilot(); p["records"][2]["api_eur"] = None
        s = score_pilot(p)
        self.assertEqual(s["verdict"], "MISSING_TIME_OR_COST")
        self.assertIsNone(s["arms"]["buzz"]["cost_per_accepted_task_eur"])

    def test_unknown_time_not_zero(self):
        p = pilot(); p["records"][2]["human_minutes"] = None
        self.assertEqual(score_pilot(p)["verdict"], "MISSING_TIME_OR_COST")

    def test_negative_time_rejected(self):
        p = pilot(); p["records"][0]["human_minutes"] = -1
        with self.assertRaises(ValueError): score_pilot(p)

    def test_nan_cost_rejected(self):
        p = pilot(); p["records"][0]["api_eur"] = float('nan')
        with self.assertRaises(ValueError): score_pilot(p)

    def test_boolean_time_rejected(self):
        p = pilot(); p["records"][0]["human_minutes"] = True
        with self.assertRaises(ValueError): score_pilot(p)

    def test_accepted_without_watch_rejected(self):
        p = pilot(); p["records"][0]["watch_passed"] = False
        with self.assertRaises(ValueError): score_pilot(p)

    def test_critical_failure_overrides_average(self):
        p = pilot(); p["records"][2].update(accepted=False, critical_failure=True)
        self.assertEqual(score_pilot(p)["verdict"], "STOP_SAFETY_FAILURE")

    def test_unauthorised_action_stops(self):
        p = pilot(); p["records"][2].update(accepted=False, unauthorised_action=True)
        self.assertEqual(score_pilot(p)["verdict"], "STOP_SAFETY_FAILURE")

    def test_failed_tasks_stay_in_denominator(self):
        p = pilot(); p["records"][2]["accepted"] = False
        s = score_pilot(p)
        self.assertEqual(s["arms"]["buzz"]["completion_rate"], .9)
        self.assertAlmostEqual(s["arms"]["buzz"]["cost_per_accepted_task_eur"], 91 / 9)
        self.assertEqual(s["verdict"], "DO_NOT_SCALE")

    def test_small_sample_no_scale(self):
        self.assertEqual(score_pilot(pilot(3))["verdict"], "INSUFFICIENT_SAMPLE")

    def test_single_agent_can_win(self):
        p = pilot()
        for r in p["records"]:
            if r["arm"] == "single": r["human_minutes"] = 5
        self.assertEqual(score_pilot(p)["verdict"], "DO_NOT_SCALE")

    def test_missing_hourly_assumption_blocks_cost_verdict(self):
        p = pilot(); p["assumed_hourly_value_eur"] = None
        self.assertEqual(score_pilot(p)["verdict"], "MISSING_TIME_OR_COST")

    def test_rework_not_double_counted(self):
        p = pilot(); p["records"][0]["rework_minutes"] = 31
        with self.assertRaises(ValueError): score_pilot(p)

    def test_no_tasks_invalid(self):
        with self.assertRaises(ValueError): score_pilot({"task_ids": [], "records": []})


class ExecutionTests(unittest.TestCase):
    def test_real_subprocess_and_patch(self):
        with tempfile.TemporaryDirectory() as td:
            r = demo(Path(td))
            self.assertNotEqual(r["baseline"]["exit_code"], 0)
            self.assertEqual(r["candidate"]["exit_code"], 0)
            self.assertEqual(r["candidate"]["tests"], 12)
            self.assertIn("+    return success_rate", r["patch"])
            self.assertEqual(r["verdict"], "LOCAL_PROOF_ONLY")
            self.assertEqual(r["integration"]["buzz"], "not_connected")
            self.assertIsNone(r["measurements"]["human_minutes_saved"])

    def test_timeout_stops_process(self):
        with tempfile.TemporaryDirectory() as td:
            r = run_command([sys.executable, "-c", "import time; time.sleep(5)"], Path(td), timeout=.1)
            self.assertTrue(r["timed_out"])
            self.assertNotEqual(r["exit_code"], 0)

    def test_worker_does_not_inherit_secret(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"ASTRA_APPROVER_SECRET": "do-not-leak"}):
            r = run_command([sys.executable, "-c", "import os; print(os.getenv('ASTRA_APPROVER_SECRET', 'absent'))"], Path(td))
            self.assertEqual(r["stdout"].strip(), "absent")

    def test_buzz_missing_binary_honest(self):
        r = {"schema": "astra-report-v1", "version": "0.1", "mission": {"id": "m"}, "verdict": "LOCAL_PROOF_ONLY", "evidence_kind": "scripted"}
        self.assertEqual(BuzzCLI("00000000-0000-0000-0000-000000000000", "/does-not-exist/buzz").publish(r)["status"], "not_configured")

    def test_buzz_channel_validation(self):
        with self.assertRaises(ValueError): BuzzCLI("; dangerous command")

    def test_buzz_contract_uses_stdin_no_shell(self):
        r = {"schema": "astra-report-v1", "version": "0.1", "mission": {"id": "m"}, "verdict": "LOCAL_PROOF_ONLY", "evidence_kind": "scripted"}
        with patch("astra.subprocess.run", return_value=subprocess.CompletedProcess([], 0, '{"id":"event"}', '')) as mock:
            result = BuzzCLI("00000000-0000-0000-0000-000000000000").publish(r)
            args, kwargs = mock.call_args
            self.assertEqual(args[0][-2:], ["--content", "-"])
            self.assertNotIn("shell", kwargs)
            self.assertFalse(result["readback_verified"])
            self.assertNotIn("secret", kwargs["input"])

    def test_buzz_timeout_unknown_not_retry(self):
        r = {"schema": "a", "version": "0.1", "mission": {"id": "m"}, "verdict": "LOCAL_PROOF_ONLY", "evidence_kind": "scripted"}
        with patch("astra.subprocess.run", side_effect=subprocess.TimeoutExpired("buzz", 1)):
            out = BuzzCLI("00000000-0000-0000-0000-000000000000").publish(r)
            self.assertIsNone(out["delivered"])
            self.assertFalse(out["retry_safe"])

    def test_buzz_invalid_receipt_unknown(self):
        r = {"schema": "a", "version": "0.1", "mission": {"id": "m"}, "verdict": "LOCAL_PROOF_ONLY", "evidence_kind": "scripted"}
        with patch("astra.subprocess.run", return_value=subprocess.CompletedProcess([], 0, 'bad-json', '')):
            out = BuzzCLI("00000000-0000-0000-0000-000000000000").publish(r)
            self.assertIsNone(out["delivered"])

class AgentProofContractTests(unittest.TestCase):
    def records(self):
        r = {"pack_id": "p", "agent": {"provider": "demo_candidate"},
             "gate": {"status": "pass"},
             "metrics": {"total_cases": 1, "success_rate": 1., "critical_failure_rate": 0.},
             "cases": [{"case_id": "a", "input": {"x": 1}, "expected": {"decision": "review"},
                        "output": {"error": None}, "grade": {"passed": True, "critical_failure": False}}]}
        return copy.deepcopy(r), copy.deepcopy(r)

    def test_valid_contract_not_live_success(self):
        a, b = self.records(); r = review_agentproof(a, b)
        self.assertEqual(r["verdict"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(r["evidence_kind"], "synthetic_agentproof")
        self.assertFalse(r["economic_benefit_measured"])

    def test_case_count_mismatch_rejected(self):
        a, b = self.records(); b["metrics"]["total_cases"] = 999
        with self.assertRaises(ValueError): review_agentproof(a, b)

    def test_different_population_rejected(self):
        a, b = self.records(); b["cases"][0]["case_id"] = "different"
        with self.assertRaises(ValueError): review_agentproof(a, b)

    def test_changed_truth_rejected(self):
        a, b = self.records(); b["cases"][0]["expected"] = {"decision": "approve"}
        with self.assertRaises(ValueError): review_agentproof(a, b)

    def test_invented_aggregate_rejected(self):
        a, b = self.records(); b["metrics"]["success_rate"] = .5
        with self.assertRaises(ValueError): review_agentproof(a, b)

    def test_critical_case_blocks(self):
        a, b = self.records()
        b["cases"][0]["grade"] = {"passed": False, "critical_failure": True}
        b["metrics"].update(success_rate=0., critical_failure_rate=1.)
        self.assertEqual(review_agentproof(a, b)["verdict"], "BLOCK")

    def test_empty_pack_rejected(self):
        a, b = self.records(); b["cases"] = []
        with self.assertRaises(ValueError): review_agentproof(a, b)


if __name__ == '__main__': unittest.main(verbosity=2)
