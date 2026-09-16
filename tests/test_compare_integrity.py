"""The evaluator is fixed before the scripted repair; no model judges itself."""
from copy import deepcopy

import pytest

from agentproof.compare import compare_runs, exact_mcnemar_p_value, wilson_interval
from agentproof.models import (
    AgentConfig, CaseGrade, CaseResult, Economics, GateResult, ProviderResult,
    RunMetrics, RunRecord,
)


def make_run(name="baseline", ids=("a", "b"), passed=False):
    cases = [CaseResult(
        case_id=i, title=i, input={"amount": 10}, expected={"decision": "review"},
        output=ProviderResult(raw_text="{}", parsed={"decision": "review"}),
        grade=CaseGrade(score=float(passed), passed=passed, critical_failure=False),
    ) for i in ids]
    metrics = RunMetrics(
        total_cases=len(cases), success_rate=float(passed), average_score=float(passed),
        critical_failure_rate=0, escalation_rate=0, avg_latency_ms=0, avg_cost_eur=0,
        human_cost_per_case_eur=0, agent_cost_per_case_eur=0, annual_human_cost_eur=0,
        annual_agent_cost_eur=0, estimated_annual_savings_eur=0,
        first_year_net_savings_eur=0, roi_multiple=None,
    )
    return RunRecord(id=name, created_at="2026-09-17T00:00:00Z", pack_id="integrity-v1",
                     pack_name="Integrity", agent=AgentConfig(name=name), economics=Economics(),
                     metrics=metrics, gate=GateResult(status="pass"), cases=cases)


def test_complete_improvement_still_promotes():
    result = compare_runs(make_run(), make_run("candidate", passed=True))
    assert result.recommendation == "promote"
    assert result.paired_cases == 2
    assert result.fixes == 2


def test_order_is_not_identity():
    result = compare_runs(make_run(), make_run("candidate", ids=("b", "a"), passed=True))
    assert result.paired_cases == 2


@pytest.mark.parametrize("ids", [("a",), ("a", "b", "c"), ("c", "d")])
def test_unequal_case_sets_fail_closed(ids):
    with pytest.raises(ValueError):
        compare_runs(make_run(), make_run("candidate", ids=ids, passed=True))


@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_duplicate_ids_fail_closed(side):
    baseline, candidate = make_run(), make_run("candidate", passed=True)
    run = baseline if side == "baseline" else candidate
    run.cases.append(deepcopy(run.cases[0]))
    run.metrics.total_cases += 1
    with pytest.raises(ValueError):
        compare_runs(baseline, candidate)


@pytest.mark.parametrize("field,value", [
    ("expected", {"decision": "refund"}),
    ("input", {"amount": 11}),
    ("failure_cost_eur", 100),
    ("tags", ["different-segment"]),
])
def test_changed_case_definition_fails_closed(field, value):
    baseline, candidate = make_run(), make_run("candidate", passed=True)
    setattr(candidate.cases[0], field, value)
    with pytest.raises(ValueError):
        compare_runs(baseline, candidate)


def test_boolean_is_not_integer_ground_truth():
    baseline, candidate = make_run(), make_run("candidate", passed=True)
    baseline.cases[0].expected = {"flag": True}
    candidate.cases[0].expected = {"flag": 1}
    with pytest.raises(ValueError):
        compare_runs(baseline, candidate)


@pytest.mark.parametrize("side", ["baseline", "candidate"])
def test_reported_count_must_match_cases(side):
    baseline, candidate = make_run(), make_run("candidate", passed=True)
    (baseline if side == "baseline" else candidate).metrics.total_cases = 999
    with pytest.raises(ValueError):
        compare_runs(baseline, candidate)


def test_empty_pack_rejected():
    with pytest.raises(ValueError):
        compare_runs(make_run(ids=()), make_run("candidate", ids=()))


def test_different_pack_rejected():
    candidate = make_run("candidate", passed=True)
    candidate.pack_id = "different"
    with pytest.raises(ValueError):
        compare_runs(make_run(), candidate)


def test_critical_failure_still_rejects():
    candidate = make_run("candidate", passed=True)
    candidate.cases[0].grade.critical_failure = True
    assert compare_runs(make_run(), candidate).recommendation == "reject"


def test_blocked_gate_still_rejects():
    candidate = make_run("candidate", passed=True)
    candidate.gate.status = "block"
    assert compare_runs(make_run(), candidate).recommendation == "reject"


def test_statistics_unchanged():
    assert exact_mcnemar_p_value(0, 0) == 1
    assert exact_mcnemar_p_value(6, 0) == pytest.approx(0.03125)
    low, high = wilson_interval(5, 10)
    assert 0 < low < .5 < high < 1
