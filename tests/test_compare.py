from agentproof.compare import compare_runs, exact_mcnemar_p, wilson_interval
from agentproof.models import (
    AgentConfig,
    CaseGrade,
    CaseResult,
    Economics,
    GateResult,
    ProviderResult,
    RunRecord,
)
from agentproof.runner import compute_metrics


def case(case_id: str, passed: bool, *, critical: bool = False, decision: str = "approve", cost: float = 0.1, latency: float = 100):
    return CaseResult(
        case_id=case_id,
        title=case_id,
        input={},
        expected={"decision": "approve"},
        output=ProviderResult(
            raw_text="",
            parsed={"decision": decision},
            estimated_cost_eur=cost,
            latency_ms=latency,
        ),
        grade=CaseGrade(
            score=1.0 if passed else 0.0,
            passed=passed,
            critical_failure=critical,
        ),
    )


def run(run_id: str, cases: list[CaseResult], *, gate: str = "pass", name: str = "agent") -> RunRecord:
    economics = Economics(annual_case_volume=1000, implementation_cost_eur=1000)
    metrics = compute_metrics(cases, economics)
    return RunRecord(
        id=run_id,
        created_at="2026-09-15T00:00:00+00:00",
        pack_id="pack",
        pack_name="Pack",
        agent=AgentConfig(name=name),
        economics=economics,
        metrics=metrics,
        gate=GateResult(status=gate, reasons=[]),
        cases=cases,
    )


def test_compare_promotes_candidate_with_more_fixes_than_regressions():
    baseline = run("b", [case("1", False), case("2", False), case("3", True)], name="old")
    candidate = run("c", [case("1", True), case("2", True), case("3", True)], name="new")
    comp = compare_runs(baseline, candidate)
    assert comp.recommendation == "promote"
    assert comp.fixes == 2
    assert comp.regressions == 0
    assert round(comp.success_rate_delta, 3) == round(2 / 3, 3)


def test_compare_rejects_new_critical_failure():
    baseline = run("b", [case("1", True), case("2", True)], name="old")
    candidate = run("c", [case("1", True), case("2", False, critical=True, decision="approve")], name="new")
    comp = compare_runs(baseline, candidate)
    assert comp.recommendation == "reject"
    assert comp.new_critical_failures == 1
    assert comp.regressions == 1


def test_compare_rejects_different_packs():
    baseline = run("b", [case("1", True)])
    candidate = run("c", [case("1", True)])
    candidate.pack_id = "other"
    try:
        compare_runs(baseline, candidate)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "same evaluation pack" in str(exc)


def test_statistics_are_bounded():
    lo, hi = wilson_interval(8, 10)
    assert 0 <= lo <= 0.8 <= hi <= 1
    assert exact_mcnemar_p(0, 10) < 0.01
    assert exact_mcnemar_p(0, 0) == 1.0
