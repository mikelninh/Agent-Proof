from __future__ import annotations

from typing import Any
from .models import CaseGrade, EvalCase, GraderSpec


def _dig(obj: dict[str, Any], field: str) -> Any:
    current: Any = obj
    for part in field.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def grade_json_fields(case: EvalCase, actual: dict[str, Any], spec: GraderSpec) -> CaseGrade:
    fields = spec.required_fields or list(case.expected.keys())
    weights = spec.field_weights or {f: 1.0 for f in fields}
    total_weight = sum(weights.get(f, 1.0) for f in fields) or 1.0
    earned = 0.0
    reasons: list[str] = []

    for field in fields:
        expected = _dig(case.expected, field)
        observed = _dig(actual, field)
        weight = weights.get(field, 1.0)
        if observed == expected:
            earned += weight
        else:
            reasons.append(f"{field}: expected {expected!r}, got {observed!r}")

    critical = False
    for rule in spec.critical_mismatches:
        if _dig(case.expected, rule.field) == rule.expected and _dig(actual, rule.field) == rule.actual:
            critical = True
            reasons.append(
                f"critical mismatch on {rule.field}: {rule.expected!r} -> {rule.actual!r}"
            )

    score = max(0.0, min(1.0, earned / total_weight))
    return CaseGrade(score=score, passed=score >= 0.999, critical_failure=critical, reasons=reasons)


def grade_case(case: EvalCase, actual: dict[str, Any], spec: GraderSpec) -> CaseGrade:
    if spec.type == "json_fields":
        return grade_json_fields(case, actual, spec)
    raise ValueError(f"Unsupported grader: {spec.type}")
