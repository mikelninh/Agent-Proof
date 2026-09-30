from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, asdict

from .models import EvalPack

DEFAULT_AUDIT_DIMENSIONS = (
    "correctness",
    "boundary",
    "injection",
    "recovery",
    "approval",
)


@dataclass(frozen=True)
class AuditPackAssessment:
    status: str
    total_cases: int
    min_cases: int
    required_dimensions: tuple[str, ...]
    dimension_counts: dict[str, int]
    missing_dimensions: tuple[str, ...]
    untagged_cases: int
    reasons: tuple[str, ...]

    @property
    def ready(self) -> bool:
        return self.status == "ready"

    def model_dump(self) -> dict:
        return asdict(self)


def _risk_dimensions(tags: list[str]) -> set[str]:
    dimensions: set[str] = set()
    for tag in tags:
        value = str(tag).strip().lower()
        if value.startswith("risk:"):
            dimensions.add(value.split(":", 1)[1].strip())
    return {item for item in dimensions if item}


def assess_audit_pack(
    pack: EvalPack,
    *,
    min_cases: int = 30,
    required_dimensions: tuple[str, ...] = DEFAULT_AUDIT_DIMENSIONS,
) -> AuditPackAssessment:
    if min_cases < 1:
        raise ValueError("min_cases must be at least 1")

    required = tuple(dict.fromkeys(str(item).strip().lower() for item in required_dimensions if str(item).strip()))
    counts: Counter[str] = Counter()
    untagged = 0

    for case in pack.cases:
        dimensions = _risk_dimensions(case.tags)
        if not dimensions:
            untagged += 1
        for dimension in dimensions:
            counts[dimension] += 1

    missing = tuple(dimension for dimension in required if counts[dimension] == 0)
    reasons: list[str] = []

    if len(pack.cases) < min_cases:
        reasons.append(f"case count {len(pack.cases)} is below required {min_cases}")
    if missing:
        reasons.append(f"missing risk coverage: {', '.join(missing)}")

    return AuditPackAssessment(
        status="not_ready" if reasons else "ready",
        total_cases=len(pack.cases),
        min_cases=min_cases,
        required_dimensions=required,
        dimension_counts={dimension: counts[dimension] for dimension in required},
        missing_dimensions=missing,
        untagged_cases=untagged,
        reasons=tuple(reasons),
    )
