from __future__ import annotations

import random

from .models import CriticalMismatch, EvalCase, EvalPack, GraderSpec


def _support_policy(data: dict) -> tuple[str, str, list[str], float]:
    """Inspectable reference policy for the synthetic flagship benchmark."""
    tags: list[str] = [f"issue:{data['issue_type']}"]
    amount = float(data["amount_eur"])
    age = int(data["order_age_days"])

    if data.get("account_takeover_signal"):
        return "escalate_security", "urgent", tags + ["risk:security"], 1500.0
    if data.get("payment_disputed"):
        return "escalate_payment", "high", tags + ["risk:payment"], 600.0

    issue = data["issue_type"]
    if issue == "duplicate_charge":
        if amount > 250:
            return "manual_review", "high", tags + ["amount:high"], 350.0
        return "refund", "normal", tags + ["policy:auto-refund"], max(25.0, amount)

    if issue == "damaged_delivery":
        if not data.get("evidence_attached"):
            return "request_evidence", "normal", tags + ["evidence:missing"], 80.0
        if amount > 250:
            return "manual_review", "high", tags + ["amount:high"], 350.0
        return "replace", "normal", tags + ["policy:replace"], max(35.0, amount * 0.7)

    if issue == "cancellation":
        if data.get("digital_consumed"):
            return "deny", "normal", tags + ["policy:consumed"], max(20.0, amount)
        if age <= 14:
            return "refund", "normal", tags + ["policy:cooling-off"], max(20.0, amount)
        return "deny", "normal", tags + ["policy:outside-window"], max(20.0, amount)

    if issue == "late_delivery":
        days_late = int(data.get("days_late", 0))
        if days_late >= 10 and amount > 250:
            return "manual_review", "high", tags + ["amount:high", "delay:severe"], 300.0
        if days_late >= 7:
            return "service_credit", "normal", tags + ["delay:severe"], 40.0
        return "wait_and_track", "normal", tags + ["delay:mild"], 20.0

    if issue == "technical":
        if int(data.get("prior_contacts", 0)) >= 3:
            return "escalate_technical", "high", tags + ["repeat-contact"], 120.0
        return "troubleshoot", "normal", tags + ["first-line"], 30.0

    if not data.get("evidence_attached"):
        return "request_evidence", "normal", tags + ["evidence:missing"], 70.0
    if amount > 250:
        return "manual_review", "high", tags + ["amount:high"], 350.0
    return "replace", "normal", tags + ["policy:replace"], max(35.0, amount * 0.7)


def support_ops_pack(count: int = 180) -> EvalPack:
    rng = random.Random(42017)
    issues = ["duplicate_charge", "damaged_delivery", "cancellation", "late_delivery", "technical", "wrong_item"]
    amounts = [19.9, 39.0, 79.0, 129.0, 249.0, 279.0, 499.0]
    cases: list[EvalCase] = []
    for idx in range(count):
        issue = issues[idx % len(issues)]
        amount = amounts[(idx * 3 + 1) % len(amounts)]
        data = {
            "issue_type": issue,
            "amount_eur": amount,
            "order_age_days": [2, 7, 13, 16, 30][(idx * 2) % 5],
            "vip_customer": idx % 11 == 0,
            "evidence_attached": idx % 4 != 0,
            "payment_disputed": idx % 37 == 0,
            "account_takeover_signal": idx % 53 == 0,
            "digital_consumed": issue == "cancellation" and idx % 5 == 0,
            "days_late": [2, 5, 7, 11][idx % 4] if issue == "late_delivery" else 0,
            "prior_contacts": [0, 1, 2, 3, 4][idx % 5] if issue == "technical" else rng.choice([0, 1]),
            "channel": ["email", "chat", "voice"][idx % 3],
            "market": ["DE", "NL", "FR", "AT"][idx % 4],
        }
        decision, priority, tags, failure_cost = _support_policy(data)
        if data["vip_customer"]:
            tags.append("segment:vip")
        tags.append(f"market:{data['market']}")
        cases.append(EvalCase(id=f"support-{idx+1:03d}", title=f"{issue.replace('_', ' ').title()} #{idx+1:03d}", input=data, expected={"decision": decision, "priority": priority}, tags=tags, failure_cost_eur=failure_cost))

    return EvalPack(
        id="support-ops-v1",
        name="Support Ops — 180-case deployment benchmark",
        description="Deterministic customer-support policy benchmark covering refunds, replacements, cancellations, delays, technical escalation, payment disputes and security escalation.",
        task_instruction="Resolve the support case. Return JSON with exactly two evaluated fields: decision and priority. Valid decisions include refund, replace, request_evidence, deny, manual_review, service_credit, wait_and_track, troubleshoot, escalate_technical, escalate_payment, escalate_security. Priority must be normal, high, or urgent.",
        grader=GraderSpec(
            required_fields=["decision", "priority"],
            field_weights={"decision": 0.85, "priority": 0.15},
            critical_mismatches=[
                CriticalMismatch(field="decision", expected="escalate_security", actual="refund"),
                CriticalMismatch(field="decision", expected="escalate_security", actual="replace"),
                CriticalMismatch(field="decision", expected="escalate_payment", actual="refund"),
                CriticalMismatch(field="decision", expected="deny", actual="refund"),
            ],
        ),
        cases=cases,
    )
