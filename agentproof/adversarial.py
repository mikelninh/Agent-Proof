from __future__ import annotations

from copy import deepcopy
from itertools import cycle
from typing import Any

from .models import AdversarialDraft, EvalPack


def _first_bool(data: dict[str, Any]) -> str | None:
    return next((k for k, v in data.items() if isinstance(v, bool)), None)


def _first_numeric(data: dict[str, Any]) -> str | None:
    return next((k for k, v in data.items() if isinstance(v, (int, float)) and not isinstance(v, bool)), None)


def _mutate(data: dict[str, Any], family: str, idx: int) -> tuple[dict[str, Any], str]:
    out = deepcopy(data)
    if family == "missing":
        keys = [k for k in out if k not in {"issue_type"}]
        key = keys[idx % len(keys)] if keys else next(iter(out), "field")
        out[key] = None
        return out, f"Remove {key} to test missing-data handling"

    if family == "boolean_flip":
        key = _first_bool(out)
        if key:
            out[key] = not out[key]
            return out, f"Flip {key} to test a policy branch"
        return out, "No boolean field available; unchanged draft"

    if family == "boundary":
        for key, pair in [
            ("amount_eur", (250, 251)),
            ("order_age_days", (14, 15)),
            ("days_late", (6, 7)),
            ("prior_contacts", (2, 3)),
        ]:
            if key in out and out[key] is not None:
                out[key] = pair[idx % 2]
                return out, f"Move {key} to a decision boundary ({out[key]})"
        key = _first_numeric(out)
        if key:
            out[key] = 0 if idx % 2 == 0 else out[key] + 1
            return out, f"Move {key} to a nearby numeric boundary"
        return out, "No numeric field available; unchanged draft"

    if family == "conflict":
        if "account_takeover_signal" in out and "payment_disputed" in out:
            out["account_takeover_signal"] = True
            out["payment_disputed"] = True
            return out, "Create conflicting high-risk signals to test precedence"
        bools = [k for k, v in out.items() if isinstance(v, bool)]
        if len(bools) >= 2:
            out[bools[0]] = True
            out[bools[1]] = True
            return out, f"Create simultaneous signals: {bools[0]} + {bools[1]}"
        return out, "Insufficient boolean signals; unchanged draft"

    if family == "scale":
        key = "amount_eur" if "amount_eur" in out else _first_numeric(out)
        if key and out[key] is not None:
            out[key] = round(float(out[key]) * 10, 2)
            return out, f"Scale {key} by 10× to probe large-value handling"
        return out, "No scalable numeric field available; unchanged draft"

    return out, "Unknown mutation family"


def generate_adversarial_drafts(pack: EvalPack, limit: int, families: list[str]) -> list[AdversarialDraft]:
    if not pack.cases:
        return []
    if not families:
        families = ["boundary"]
    drafts: list[AdversarialDraft] = []
    family_cycle = cycle(families)
    for idx in range(limit):
        base = pack.cases[(idx * 7) % len(pack.cases)]
        family = next(family_cycle)
        mutated, rationale = _mutate(base.input, family, idx)
        drafts.append(
            AdversarialDraft(
                id=f"adv-{base.id}-{idx+1:03d}",
                base_case_id=base.id,
                title=f"Adversarial · {base.title} · {family}",
                family=family,
                rationale=rationale,
                input=mutated,
                suggested_expected=deepcopy(base.expected),
                tags=list(dict.fromkeys([*base.tags, "adversarial", f"mutation:{family}"])),
                failure_cost_eur=base.failure_cost_eur,
            )
        )
    return drafts
