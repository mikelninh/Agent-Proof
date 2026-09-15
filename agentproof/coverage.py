from __future__ import annotations

from collections import defaultdict

from .models import CoverageBucket, RunRecord


def coverage_for_run(run: RunRecord) -> list[CoverageBucket]:
    buckets: dict[str, list] = defaultdict(list)
    for case in run.cases:
        tags = case.tags or ["untagged"]
        for tag in tags:
            buckets[tag].append(case)
    result: list[CoverageBucket] = []
    for tag, cases in buckets.items():
        total = len(cases)
        failures = [c for c in cases if not c.grade.passed]
        result.append(
            CoverageBucket(
                tag=tag,
                cases=total,
                success_rate=sum(1 for c in cases if c.grade.passed) / total,
                critical_failures=sum(1 for c in cases if c.grade.critical_failure),
                failure_exposure_eur=sum(c.failure_cost_eur for c in failures),
            )
        )
    return sorted(result, key=lambda x: (x.success_rate, -x.cases, x.tag))
