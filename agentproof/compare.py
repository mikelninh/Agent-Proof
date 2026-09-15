from __future__ import annotations

import math

from .models import ComparisonCase, RunComparison, RunRecord


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a binomial proportion."""
    if total <= 0:
        return (0.0, 0.0)
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = (
        z
        * math.sqrt((p * (1 - p) / total) + (z * z / (4 * total * total)))
        / denom
    )
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def exact_mcnemar_p(regressions: int, fixes: int) -> float:
    """Two-sided exact McNemar/binomial test over discordant paired outcomes."""
    n = regressions + fixes
    if n == 0:
        return 1.0
    k = min(regressions, fixes)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def compare_runs(baseline: RunRecord, candidate: RunRecord) -> RunComparison:
    if baseline.pack_id != candidate.pack_id:
        raise ValueError("Runs must use the same evaluation pack")

    baseline_by_id = {case.case_id: case for case in baseline.cases}
    candidate_by_id = {case.case_id: case for case in candidate.cases}
    common_ids = [case.case_id for case in baseline.cases if case.case_id in candidate_by_id]
    if not common_ids:
        raise ValueError("Runs have no overlapping case IDs")

    case_deltas: list[ComparisonCase] = []
    regressions = fixes = new_critical = resolved_critical = 0
    for case_id in common_ids:
        b = baseline_by_id[case_id]
        c = candidate_by_id[case_id]
        status = "unchanged"
        if b.grade.passed and not c.grade.passed:
            status = "regression"
            regressions += 1
        elif not b.grade.passed and c.grade.passed:
            status = "fix"
            fixes += 1

        if c.grade.critical_failure and not b.grade.critical_failure:
            new_critical += 1
        if b.grade.critical_failure and not c.grade.critical_failure:
            resolved_critical += 1

        case_deltas.append(
            ComparisonCase(
                case_id=case_id,
                title=c.title,
                status=status,
                baseline_passed=b.grade.passed,
                candidate_passed=c.grade.passed,
                baseline_critical=b.grade.critical_failure,
                candidate_critical=c.grade.critical_failure,
                baseline_decision=b.output.parsed.get("decision"),
                candidate_decision=c.output.parsed.get("decision"),
                baseline_score=b.grade.score,
                candidate_score=c.grade.score,
            )
        )

    paired = len(common_ids)
    baseline_successes = sum(1 for case_id in common_ids if baseline_by_id[case_id].grade.passed)
    candidate_successes = sum(1 for case_id in common_ids if candidate_by_id[case_id].grade.passed)
    baseline_rate = baseline_successes / paired
    candidate_rate = candidate_successes / paired
    success_delta = candidate_rate - baseline_rate

    b_critical = sum(1 for case_id in common_ids if baseline_by_id[case_id].grade.critical_failure) / paired
    c_critical = sum(1 for case_id in common_ids if candidate_by_id[case_id].grade.critical_failure) / paired

    p_value = exact_mcnemar_p(regressions, fixes)
    reasons: list[str] = []

    if candidate.gate.status == "block":
        recommendation = "reject"
        reasons.append("candidate fails its configured deployment gate")
    elif new_critical > 0:
        recommendation = "reject"
        reasons.append(f"candidate introduces {new_critical} new critical failure(s)")
    elif success_delta < -0.005:
        recommendation = "reject"
        reasons.append(f"paired success rate regresses by {abs(success_delta):.1%}")
    elif fixes > regressions and success_delta > 0:
        recommendation = "promote"
        reasons.append(f"candidate fixes {fixes} case(s) while regressing {regressions}")
    elif success_delta >= 0 and candidate.metrics.agent_cost_per_case_eur < baseline.metrics.agent_cost_per_case_eur:
        recommendation = "promote"
        reasons.append("quality is non-inferior on this pack and cost per case is lower")
    elif success_delta >= 0 and candidate.metrics.avg_latency_ms < baseline.metrics.avg_latency_ms:
        recommendation = "promote"
        reasons.append("quality is non-inferior on this pack and latency is lower")
    else:
        recommendation = "hold"
        reasons.append("candidate is not clearly better on the evidence available")

    if p_value < 0.05:
        reasons.append(f"paired outcome difference is statistically significant (p={p_value:.4f})")
    else:
        reasons.append(f"paired outcome difference is not statistically significant (p={p_value:.4f})")

    return RunComparison(
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        pack_id=baseline.pack_id,
        pack_name=baseline.pack_name,
        paired_cases=paired,
        baseline_agent=baseline.agent.name,
        candidate_agent=candidate.agent.name,
        baseline_success_rate=baseline_rate,
        candidate_success_rate=candidate_rate,
        baseline_success_ci=wilson_interval(baseline_successes, paired),
        candidate_success_ci=wilson_interval(candidate_successes, paired),
        success_rate_delta=success_delta,
        critical_failure_rate_delta=c_critical - b_critical,
        cost_per_case_delta_eur=(
            candidate.metrics.agent_cost_per_case_eur - baseline.metrics.agent_cost_per_case_eur
        ),
        latency_delta_ms=(candidate.metrics.avg_latency_ms - baseline.metrics.avg_latency_ms),
        annual_savings_delta_eur=(
            candidate.metrics.estimated_annual_savings_eur
            - baseline.metrics.estimated_annual_savings_eur
        ),
        regressions=regressions,
        fixes=fixes,
        new_critical_failures=new_critical,
        resolved_critical_failures=resolved_critical,
        discordant_pairs=regressions + fixes,
        mcnemar_p_value=p_value,
        recommendation=recommendation,
        reasons=reasons,
        cases=case_deltas,
    )
