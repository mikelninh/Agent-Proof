from __future__ import annotations

import json
import math
from typing import Any

from .models import ComparisonCase, RunComparison, RunRecord


def wilson_interval(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 0.0
    p = successes / total
    denom = 1 + z * z / total
    centre = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return max(0.0, centre - margin), min(1.0, centre + margin)


def exact_mcnemar_p_value(fixes: int, regressions: int) -> float:
    n = fixes + regressions
    if n == 0:
        return 1.0
    k = min(fixes, regressions)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2**n)
    return min(1.0, 2 * tail)


def _decision(case) -> Any | None:
    if not case.expected:
        return None
    target = next(iter(case.expected))
    return case.output.parsed.get(target)


def compare_runs(baseline: RunRecord, candidate: RunRecord) -> RunComparison:
    if baseline.pack_id != candidate.pack_id:
        raise ValueError("Runs must use the same evaluation pack")

    # Fail closed: an intersection silently drops omitted cases and duplicates.
    bmap = {c.case_id: c for c in baseline.cases}
    cmap = {c.case_id: c for c in candidate.cases}
    if len(bmap) != len(baseline.cases) or len(cmap) != len(candidate.cases):
        raise ValueError("Duplicate case IDs are not valid paired evidence")
    if set(bmap) != set(cmap):
        raise ValueError("Runs must contain exactly the same case IDs")
    ids = sorted(bmap)
    if not ids:
        raise ValueError("Runs have no paired cases")
    if (baseline.metrics.total_cases != len(baseline.cases)
            or candidate.metrics.total_cases != len(candidate.cases)):
        raise ValueError("Reported case counts do not match the evidence")
    for case_id in ids:
        # Canonical JSON distinguishes true from 1, unlike Python dict equality.
        # Stored run records do not yet retain a grader/policy-version digest;
        # this checks the case definition available in today's schema only.
        def definition(case):
            return json.dumps(
                {"input": case.input, "expected": case.expected,
                 "tags": sorted(case.tags), "failure_cost_eur": case.failure_cost_eur},
                sort_keys=True, separators=(",", ":"), allow_nan=False,
            )
        if definition(bmap[case_id]) != definition(cmap[case_id]):
            raise ValueError(f"Case definition changed for {case_id}")

    cases: list[ComparisonCase] = []
    fixes = regressions = new_critical = resolved_critical = 0
    for case_id in ids:
        b = bmap[case_id]
        c = cmap[case_id]
        if not b.grade.passed and c.grade.passed:
            status = "fix"
            fixes += 1
        elif b.grade.passed and not c.grade.passed:
            status = "regression"
            regressions += 1
        else:
            status = "unchanged"
        if not b.grade.critical_failure and c.grade.critical_failure:
            new_critical += 1
        if b.grade.critical_failure and not c.grade.critical_failure:
            resolved_critical += 1
        cases.append(
            ComparisonCase(
                case_id=case_id,
                title=c.title,
                status=status,
                baseline_passed=b.grade.passed,
                candidate_passed=c.grade.passed,
                baseline_critical=b.grade.critical_failure,
                candidate_critical=c.grade.critical_failure,
                baseline_decision=_decision(b),
                candidate_decision=_decision(c),
                baseline_score=b.grade.score,
                candidate_score=c.grade.score,
            )
        )

    total = len(ids)
    b_success = sum(1 for i in ids if bmap[i].grade.passed)
    c_success = sum(1 for i in ids if cmap[i].grade.passed)
    b_rate = b_success / total
    c_rate = c_success / total
    p_value = exact_mcnemar_p_value(fixes, regressions)

    reasons: list[str] = []
    if new_critical:
        recommendation = "reject"
        reasons.append(f"candidate introduced {new_critical} new critical failure(s)")
    elif candidate.gate.status == "block":
        recommendation = "reject"
        reasons.append("candidate fails its configured deployment gate")
    elif c_rate > b_rate and fixes > regressions:
        recommendation = "promote"
        reasons.append(f"candidate fixes {fixes} paired case(s) while regressing {regressions}")
        if p_value <= 0.05:
            reasons.append(f"paired improvement is statistically detectable (exact McNemar p={p_value:.4f})")
        else:
            reasons.append(f"paired improvement is directionally positive but not conclusive (p={p_value:.4f})")
    else:
        recommendation = "hold"
        reasons.append("candidate does not show a clear paired improvement")

    if candidate.metrics.annualized_failure_exposure_eur < baseline.metrics.annualized_failure_exposure_eur:
        reasons.append(f"estimated annual failure exposure falls by €{baseline.metrics.annualized_failure_exposure_eur - candidate.metrics.annualized_failure_exposure_eur:,.0f}")
    elif candidate.metrics.annualized_failure_exposure_eur > baseline.metrics.annualized_failure_exposure_eur:
        reasons.append(f"estimated annual failure exposure rises by €{candidate.metrics.annualized_failure_exposure_eur - baseline.metrics.annualized_failure_exposure_eur:,.0f}")

    return RunComparison(
        baseline_run_id=baseline.id,
        candidate_run_id=candidate.id,
        pack_id=baseline.pack_id,
        pack_name=baseline.pack_name,
        paired_cases=total,
        baseline_agent=baseline.agent.name,
        candidate_agent=candidate.agent.name,
        baseline_success_rate=b_rate,
        candidate_success_rate=c_rate,
        baseline_success_ci=wilson_interval(b_success, total),
        candidate_success_ci=wilson_interval(c_success, total),
        success_rate_delta=c_rate - b_rate,
        critical_failure_rate_delta=candidate.metrics.critical_failure_rate - baseline.metrics.critical_failure_rate,
        cost_per_case_delta_eur=candidate.metrics.agent_cost_per_case_eur - baseline.metrics.agent_cost_per_case_eur,
        latency_delta_ms=candidate.metrics.avg_latency_ms - baseline.metrics.avg_latency_ms,
        annual_savings_delta_eur=candidate.metrics.risk_adjusted_annual_value_eur - baseline.metrics.risk_adjusted_annual_value_eur,
        regressions=regressions,
        fixes=fixes,
        new_critical_failures=new_critical,
        resolved_critical_failures=resolved_critical,
        discordant_pairs=fixes + regressions,
        mcnemar_p_value=p_value,
        recommendation=recommendation,
        reasons=reasons,
        cases=cases,
    )
