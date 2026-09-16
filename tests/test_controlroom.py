from __future__ import annotations
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from agentproof.controlroom import Ledger, call_worker, digest, publish_buzz, run_mission, verify_run
from agentproof.controlroom_fixtures import make_mission
from agentproof.controlroom_metrics import ARMS, evaluate


@pytest.fixture(scope="module")
def good_run(tmp_path_factory):
    directory = tmp_path_factory.mktemp("data") / "good"
    result = run_mission(make_mission("correct"), directory)
    assert result["status"] == "awaiting_human"
    return directory


@pytest.mark.parametrize("scenario,state,attempts", [
    ("repair", "awaiting_human", 2), ("correct", "awaiting_human", 1),
    ("false_success", "blocked", 2), ("critical", "blocked", 1),
    ("timeout", "blocked", 1), ("malformed", "blocked", 1),
    ("stale_proof", "blocked", 2), ("stale_review", "blocked", 2),
    ("zero_checks", "blocked", 2), ("review_rejected", "blocked", 2),
])
def test_mission_failure_injections(tmp_path, scenario, state, attempts):
    directory = tmp_path / scenario
    result = run_mission(make_mission(scenario), directory)
    assert (result["status"], result["attempts"]) == (state, attempts)
    assert result["released"] is False
    assert result["provider_cost_eur"] is None and result["human_minutes"] is None
    assert "claimed_revenue_eur" not in result
    assert verify_run(directory) == result


@pytest.mark.parametrize("attempts", [0, 4, True, 1.5])
def test_invalid_attempt_budget(tmp_path, attempts):
    mission = make_mission()
    mission["max_attempts"] = attempts
    with pytest.raises(ValueError):
        run_mission(mission, tmp_path / "run")


def test_role_separation(tmp_path):
    mission = make_mission()
    mission["reviewer"]["id"] = mission["builder"]["id"]
    with pytest.raises(ValueError, match="identities"):
        run_mission(mission, tmp_path / "run")


@pytest.mark.parametrize("timeout", [float("nan"), float("inf"), -1, True])
def test_invalid_timeout(tmp_path, timeout):
    mission = make_mission()
    mission["worker_timeout_seconds"] = timeout
    with pytest.raises(ValueError):
        run_mission(mission, tmp_path / "run")


def test_run_directory_cannot_be_reused(good_run):
    with pytest.raises(FileExistsError):
        run_mission(make_mission(), good_run)


@pytest.mark.parametrize("filename", ["result.json", "artifact-1.json", "proof-1.json", "review-1.json"])
def test_tampered_receipt_rejected(tmp_path, good_run, filename):
    import shutil
    target = tmp_path / "copy"
    shutil.copytree(good_run, target)
    path = target / filename
    data = json.loads(path.read_text())
    data["spoofed"] = True
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        verify_run(target)


def test_ledger_tampering(good_run):
    ledger = Ledger(good_run / "events.jsonl")
    altered = copy.deepcopy(ledger.events)
    altered[0]["data"]["max_attempts"] = 99
    with pytest.raises(ValueError):
        Ledger.verify(altered)


def test_frozen_evaluator_changed(tmp_path):
    frozen = tmp_path / "evaluator.txt"
    frozen.write_text("approved evaluator v1")
    mission = make_mission()
    mission["frozen_files"] = [str(frozen)]
    mission["builder"]["argv"] = [sys.executable, "-c",
        "import pathlib,json;pathlib.Path(" + repr(str(frozen)) + ").write_text('changed');print(json.dumps({'artifact':{}}))"]
    result = run_mission(mission, tmp_path / "run")
    assert result["status"] == "blocked"


@pytest.mark.parametrize("code", ["print('not JSON')", "print('[]')", "print('{\"value\": NaN}')", "raise SystemExit(7)"])
def test_invalid_worker_output(tmp_path, code):
    with pytest.raises(ValueError):
        call_worker([sys.executable, "-c", code], {}, 3, tmp_path)


def test_worker_secret_environment_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("EXAMPLE_PROVIDER_SECRET", "never-copy-this")
    result = call_worker([sys.executable, "-c",
                         "import os,json; print(json.dumps({'leaked':'EXAMPLE_PROVIDER_SECRET' in os.environ}))"],
                         {}, 3, tmp_path)
    assert result == {"leaked": False}


def test_publish_uses_stdin_and_no_secrets_in_receipt(tmp_path, good_run, monkeypatch):
    import shutil
    target = tmp_path / "copy"
    shutil.copytree(good_run, target)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "fixture-secret-only")
    with patch("agentproof.controlroom.subprocess.run") as proc:
        proc.return_value = subprocess.CompletedProcess([], 0, '{"id":"ack"}', "")
        receipt = publish_buzz(target, "https://relay.example.test", "00000000-0000-0000-0000-000000000001")
        assert proc.call_args.args[0][-2:] == ["--content", "-"]
        assert "fixture-secret-only" not in proc.call_args.kwargs["input"]
        assert receipt["state"] == "cli_acknowledged"
        assert "fixture-secret-only" not in (target / "buzz-receipt.json").read_text()
        with pytest.raises(ValueError, match="already attempted"):
            publish_buzz(target, "https://relay.example.test", "00000000-0000-0000-0000-000000000001")
        assert proc.call_count == 1


def test_ambiguous_delivery_is_not_retried(tmp_path, good_run, monkeypatch):
    import shutil
    target = tmp_path / "copy"
    shutil.copytree(good_run, target)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "fixture-secret-only")
    with patch("agentproof.controlroom.subprocess.run", side_effect=subprocess.TimeoutExpired("buzz", 20)) as proc:
        receipt = publish_buzz(target, "https://relay.example.test", "00000000-0000-0000-0000-000000000001")
        assert receipt["state"] == "delivery_unknown"
        with pytest.raises(ValueError):
            publish_buzz(target, "https://relay.example.test", "00000000-0000-0000-0000-000000000001")
        assert proc.call_count == 1


@pytest.mark.parametrize("relay", ["http://public.example.test", "https://user:secret@relay.example.test", "https://relay.example.test?key=secret"])
def test_unsafe_relay_url_rejected(good_run, relay):
    with pytest.raises(ValueError):
        publish_buzz(good_run, relay, "00000000-0000-0000-0000-000000000001")


def test_publish_requires_key(good_run, monkeypatch):
    monkeypatch.delenv("BUZZ_PRIVATE_KEY", raising=False)
    with pytest.raises(ValueError, match="not configured"):
        publish_buzz(good_run, "https://relay.example.test", "00000000-0000-0000-0000-000000000001")


def telemetry(live=True):
    # Fabricated scorer test data; never emit these as measured productivity.
    tasks = [f"task-{n:02}" for n in range(20)]
    rows = []
    for task in tasks:
        for rep in range(3):
            for arm in ARMS:
                rows.append({"task_id": task, "repetition": rep, "arm": arm, "accepted": True,
                    "critical_failure": False, "live_evidence": live,
                    "evidence_ref": "fixture://scorer-unit-test", "buzz_roundtrip_verified": True,
                    "input_hash": task, "evaluator_hash": "frozen", "budget_policy_hash": "same-budget",
                    "model_policy_hash": "same-model", "human_minutes": 10 if arm == "single" else 5,
                    "total_cost_eur": 10 if arm == "single" else 6, "elapsed_seconds": 30})
    return tasks, rows


def test_complete_scoring_contract():
    tasks, rows = telemetry()
    result = evaluate(rows, tasks)
    assert result["verdict"] == "PILOT_PASS"
    assert result["arms"]["single"]["human_minutes"] == 600
    assert result["arms"]["team_buzz"]["accepted_per_human_hour"] == 12
    assert result["comparisons"]["single_vs_team_buzz"]["human_time_reduction"] == .5
    assert not result["comparisons"]["team_local_vs_team_buzz"]["thresholds_met"]


def test_fixture_evidence_cannot_win():
    tasks, rows = telemetry(live=False)
    assert evaluate(rows, tasks)["verdict"] == "HOLD"


def test_missing_observation_stays_in_denominator():
    tasks, rows = telemetry()
    rows.pop()
    result = evaluate(rows, tasks)
    assert result["verdict"] == "HOLD"
    assert result["missing_observations"] == 1
    assert result["arms"]["team_buzz"]["success_rate"] == 59 / 60


def test_duplicate_observations_rejected():
    tasks, rows = telemetry()
    with pytest.raises(ValueError):
        evaluate(rows + [rows[0]], tasks)


@pytest.mark.parametrize("field", ["human_minutes", "total_cost_eur", "elapsed_seconds"])
def test_unknown_is_not_zero(field):
    tasks, rows = telemetry()
    rows[-1][field] = None
    result = evaluate(rows, tasks)
    assert result["verdict"] == "HOLD"
    assert result["arms"]["team_buzz"][field] is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, True])
def test_invalid_metric_rejected(value):
    tasks, rows = telemetry()
    rows[0]["total_cost_eur"] = value
    with pytest.raises(ValueError):
        evaluate(rows, tasks)


def test_any_critical_failure_blocks():
    tasks, rows = telemetry()
    rows[-1].update(accepted=False, critical_failure=True)
    assert evaluate(rows, tasks)["verdict"] == "BLOCK"


def test_quality_regression_prevents_pass():
    tasks, rows = telemetry()
    rows[-1]["accepted"] = False
    result = evaluate(rows, tasks)
    assert result["verdict"] == "HOLD"
    assert result["comparisons"]["single_vs_team_buzz"]["regressions"] == 1


def test_unequal_model_policy_holds():
    tasks, rows = telemetry()
    rows[-1]["model_policy_hash"] = "other-model"
    assert evaluate(rows, tasks)["verdict"] == "HOLD"


def test_buzz_ack_is_not_roundtrip_evidence():
    tasks, rows = telemetry()
    rows[-1]["buzz_roundtrip_verified"] = False
    result = evaluate(rows, tasks)
    assert result["verdict"] == "HOLD"
    assert any("round trips" in reason for reason in result["reasons"])


def test_expensive_team_does_not_win():
    tasks, rows = telemetry()
    for row in rows:
        if row["arm"] == "team_buzz":
            row["total_cost_eur"] = 100
    assert evaluate(rows, tasks)["verdict"] == "HOLD"


def test_worker_output_limit(tmp_path):
    with pytest.raises(ValueError, match="limit"):
        call_worker([sys.executable, "-c", "print('x'*1000001)"], {}, 3, tmp_path)


def test_missing_operator_evidence_holds():
    tasks, rows = telemetry()
    rows[0].pop("evidence_ref")
    assert evaluate(rows, tasks)["verdict"] == "HOLD"


def test_boolean_repetition_is_not_an_integer_observation():
    tasks, rows = telemetry()
    rows[0]["repetition"] = False
    with pytest.raises(ValueError):
        evaluate(rows, tasks)


def test_concurrent_publication_reserves_only_once(tmp_path, good_run, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import shutil
    import time
    target = tmp_path / "copy"
    shutil.copytree(good_run, target)
    monkeypatch.setenv("BUZZ_PRIVATE_KEY", "fixture-secret-only")
    def acknowledge(*args, **kwargs):
        time.sleep(.05)
        return subprocess.CompletedProcess([], 0, '{}', '')
    def send():
        try:
            return publish_buzz(target, "https://relay.example.test", "00000000-0000-0000-0000-000000000001")["state"]
        except ValueError:
            return "refused"
    with patch("agentproof.controlroom.subprocess.run", side_effect=acknowledge) as proc:
        with ThreadPoolExecutor(max_workers=2) as pool:
            states = list(pool.map(lambda _: send(), range(2)))
        assert sorted(states) == ["cli_acknowledged", "refused"]
        assert proc.call_count == 1
