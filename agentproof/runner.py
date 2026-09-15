from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from uuid import uuid4

from .graders import grade_case
from .models import CaseResult, Economics, EvalPack, GateResult, RunMetrics, RunRecord, RunRequest
from .providers import run_agent


async def evaluate(pack: EvalPack, request: RunRequest, concurrency: int = 8) -> RunRecord:
    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def one(case):
        async with semaphore:
            output = await run_agent(pack, case, request.agent)
            grade = grade_case(case, output.parsed, pack.grader)
            if output.error:
                grade.passed = False
                grade.score = 0
                grade.reasons.append(f"provider error: {output.error}")
            return CaseResult(
                case_id=case.id,
                title=case.title,
                input=case.input,
                expected=case.expected,
                tags=case.tags,
                failure_cost_eur=case.failure_cost_eur,
                output=output,
                grade=grade,
            )

    cases = await asyncio.gather(*(one(c) for c in pack.cases))
    metrics = compute_metrics(cases, request.economics)
    gate = evaluate_gate(metrics, request)
    return RunRecord(
        id=str(uuid4()),
        created_at=datetime.now(timezone.utc).isoformat(),
        pack_id=pack.id,
        pack_name=pack.name,
        agent=request.agent.model_copy(update={"api_key": None}),
        economics=request.economics,
        metrics=metrics,
        gate=gate,
        cases=list(cases),
    )


def compute_metrics(cases: list[CaseResult], economics: Economics) -> RunMetrics:
    total = max(1, len(cases))
    successes = sum(1 for c in cases if c.grade.passed)
    criticals = sum(1 for c in cases if c.grade.critical_failure)
    score = sum(c.grade.score for c in cases) / total
    latency = sum(c.output.latency_ms for c in cases) / total
    avg_cost = sum(c.output.estimated_cost_eur for c in cases) / total
    escalations = sum(
        1
        for c in cases
        if any(word in str(c.output.parsed.get("decision", "")).lower() for word in ("review", "escalate"))
    )
    observed_failure_cost = sum(c.failure_cost_eur for c in cases if not c.grade.passed)
    failure_cost_per_case = observed_failure_cost / total

    human_cost_per_case = economics.human_minutes_per_case / 60 * economics.human_hourly_cost_eur
    annual_human = human_cost_per_case * economics.annual_case_volume
    annual_agent = avg_cost * economics.annual_case_volume
    annual_savings = annual_human - annual_agent
    annual_failure_exposure = failure_cost_per_case * economics.annual_case_volume
    risk_adjusted_value = annual_savings - annual_failure_exposure
    first_year = risk_adjusted_value - economics.implementation_cost_eur
    roi = first_year / economics.implementation_cost_eur if economics.implementation_cost_eur > 0 else None

    return RunMetrics(
        total_cases=len(cases),
        success_rate=successes / total,
        average_score=score,
        critical_failure_rate=criticals / total,
        escalation_rate=escalations / total,
        avg_latency_ms=latency,
        avg_cost_eur=avg_cost,
        human_cost_per_case_eur=human_cost_per_case,
        agent_cost_per_case_eur=avg_cost,
        annual_human_cost_eur=annual_human,
        annual_agent_cost_eur=annual_agent,
        estimated_annual_savings_eur=annual_savings,
        first_year_net_savings_eur=first_year,
        roi_multiple=roi,
        estimated_failure_cost_per_case_eur=failure_cost_per_case,
        annualized_failure_exposure_eur=annual_failure_exposure,
        risk_adjusted_annual_value_eur=risk_adjusted_value,
    )


def evaluate_gate(metrics: RunMetrics, request: RunRequest) -> GateResult:
    reasons: list[str] = []
    if metrics.success_rate < request.gate.min_success_rate:
        reasons.append(f"success rate {metrics.success_rate:.1%} is below required {request.gate.min_success_rate:.1%}")
    if metrics.critical_failure_rate > request.gate.max_critical_failure_rate:
        reasons.append(f"critical failure rate {metrics.critical_failure_rate:.1%} exceeds allowed {request.gate.max_critical_failure_rate:.1%}")
    if request.gate.max_agent_cost_per_case_eur is not None and metrics.agent_cost_per_case_eur > request.gate.max_agent_cost_per_case_eur:
        reasons.append(f"agent cost €{metrics.agent_cost_per_case_eur:.4f}/case exceeds €{request.gate.max_agent_cost_per_case_eur:.4f}")
    if request.gate.max_annual_failure_exposure_eur is not None and metrics.annualized_failure_exposure_eur > request.gate.max_annual_failure_exposure_eur:
        reasons.append(f"annualized failure exposure €{metrics.annualized_failure_exposure_eur:,.0f} exceeds €{request.gate.max_annual_failure_exposure_eur:,.0f}")
    return GateResult(status="block" if reasons else "pass", reasons=reasons)
