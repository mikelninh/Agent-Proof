from agentproof.models import CaseGrade, CaseResult, Economics, ProviderResult
from agentproof.runner import compute_metrics


def result(ok=True, critical=False, cost=0.1, decision="approve"):
    return CaseResult(
        case_id="x", title="x", input={}, expected={},
        output=ProviderResult(raw_text="", parsed={"decision": decision}, estimated_cost_eur=cost, latency_ms=100),
        grade=CaseGrade(score=1 if ok else 0, passed=ok, critical_failure=critical),
    )


def test_roi_math():
    economics=Economics(human_minutes_per_case=10,human_hourly_cost_eur=30,annual_case_volume=1000,implementation_cost_eur=1000)
    m=compute_metrics([result(cost=.2), result(cost=.2)], economics)
    assert round(m.human_cost_per_case_eur,2)==5
    assert round(m.annual_agent_cost_eur,2)==200
    assert round(m.estimated_annual_savings_eur,2)==4800
    assert round(m.first_year_net_savings_eur,2)==3800
    assert round(m.roi_multiple,2)==3.8

from agentproof.models import GatePolicy, RunRequest
from agentproof.runner import evaluate_gate


def test_gate_blocks_below_threshold():
    economics=Economics(human_minutes_per_case=10,human_hourly_cost_eur=30,annual_case_volume=1000,implementation_cost_eur=1000)
    m=compute_metrics([result(ok=True), result(ok=False)], economics)
    req=RunRequest(pack_id="x", economics=economics, gate=GatePolicy(min_success_rate=.9,max_critical_failure_rate=0))
    gate=evaluate_gate(m, req)
    assert gate.status=="block"
    assert gate.reasons
