from __future__ import annotations

import csv
from pathlib import Path
from .models import CriticalMismatch, EvalCase, EvalPack, GraderSpec


def pack_from_csv(path: str, pack_id: str, name: str, instruction: str, target: str, critical: str | None = None) -> EvalPack:
    cases: list[EvalCase] = []
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise ValueError("CSV has no rows")
    if target not in rows[0]:
        raise ValueError(f"Target column {target!r} not found")
    for i, row in enumerate(rows, 1):
        expected = row.pop(target)
        cases.append(EvalCase(id=f"{pack_id}-{i:04d}", title=f"Case {i}", input=row, expected={target: expected}))
    critical_rules=[]
    if critical:
        expected, actual = critical.split(":",1)
        critical_rules=[CriticalMismatch(field=target, expected=expected, actual=actual)]
    return EvalPack(
        id=pack_id,
        name=name,
        description=f"Imported from {Path(path).name}",
        task_instruction=instruction,
        grader=GraderSpec(required_fields=[target], field_weights={target:1.0}, critical_mismatches=critical_rules),
        cases=cases,
    )
