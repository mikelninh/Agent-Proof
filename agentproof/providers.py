from __future__ import annotations

import json
import re
import time
from typing import Any
import httpx

from .models import AgentConfig, EvalCase, EvalPack, ProviderResult


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {"value": value}
    except Exception:
        pass
    match = re.search(r"\{.*\}", text, re.S)
    if match:
        try:
            value = json.loads(match.group(0))
            return value if isinstance(value, dict) else {"value": value}
        except Exception:
            return {}
    return {}


def _estimate_cost(config: AgentConfig, input_tokens: int, output_tokens: int) -> float:
    return input_tokens / 1_000_000 * config.input_cost_per_million_eur + output_tokens / 1_000_000 * config.output_cost_per_million_eur


def _case_number(case: EvalCase) -> int:
    match = re.search(r"(\d+)$", case.id)
    return int(match.group(1)) if match else 0


def _heuristic_fraud(case: EvalCase, stronger: bool = False) -> dict[str, Any]:
    data = case.input
    score = 0
    score += (30 if stronger else 28) if data.get("new_device") else 0
    score += (27 if stronger else 24) if data.get("country_mismatch") else 0
    score += (24 if stronger else 20) if data.get("merchant_risk") == "high" else (10 if stronger else 8) if data.get("merchant_risk") == "medium" else 0
    score += (19 if stronger else 18) if int(data.get("velocity_1h", 0)) >= 5 else (9 if stronger else 8) if int(data.get("velocity_1h", 0)) >= 3 else 0
    score += (16 if stronger else 18) if float(data.get("amount_eur", 0)) >= (1200 if stronger else 1500) else (8 if stronger else 7) if float(data.get("amount_eur", 0)) >= 500 else 0
    score += (14 if stronger else 12) if int(data.get("customer_tenure_days", 9999)) < (21 if stronger else 30) else 0
    score -= (14 if stronger else 12) if data.get("card_present") else 0
    score -= (9 if stronger else 8) if data.get("known_merchant") else 0
    decision = "block" if score >= (60 if stronger else 58) else "review" if score >= (31 if stronger else 30) else "approve"
    return {"decision": decision, "risk_score": max(0, min(100, score)), "reason": "Deterministic demo policy."}


def _support_reference(data: dict[str, Any]) -> tuple[str, str]:
    amount = float(data.get("amount_eur", 0))
    age = int(data.get("order_age_days", 0))
    if data.get("account_takeover_signal"):
        return "escalate_security", "urgent"
    if data.get("payment_disputed"):
        return "escalate_payment", "high"
    issue = data.get("issue_type")
    if issue == "duplicate_charge":
        return ("manual_review", "high") if amount > 250 else ("refund", "normal")
    if issue == "damaged_delivery":
        if not data.get("evidence_attached"):
            return "request_evidence", "normal"
        return ("manual_review", "high") if amount > 250 else ("replace", "normal")
    if issue == "cancellation":
        if data.get("digital_consumed"):
            return "deny", "normal"
        return ("refund", "normal") if age <= 14 else ("deny", "normal")
    if issue == "late_delivery":
        late = int(data.get("days_late", 0))
        if late >= 10 and amount > 250:
            return "manual_review", "high"
        return ("service_credit", "normal") if late >= 7 else ("wait_and_track", "normal")
    if issue == "technical":
        return ("escalate_technical", "high") if int(data.get("prior_contacts", 0)) >= 3 else ("troubleshoot", "normal")
    if issue == "wrong_item":
        if not data.get("evidence_attached"):
            return "request_evidence", "normal"
        return ("manual_review", "high") if amount > 250 else ("replace", "normal")
    return "manual_review", "normal"


def _support_demo(case: EvalCase, mode: str) -> dict[str, Any]:
    data = case.input
    n = _case_number(case)
    if mode == "baseline":
        if data.get("account_takeover_signal"):
            decision, priority = "escalate_security", "urgent"
        elif data.get("payment_disputed"):
            decision, priority = "escalate_payment", "high"
        else:
            issue = data.get("issue_type")
            amount = float(data.get("amount_eur", 0))
            if issue in {"damaged_delivery", "wrong_item"}:
                decision, priority = ("replace", "normal") if data.get("evidence_attached") else ("request_evidence", "normal")
            elif issue == "duplicate_charge":
                decision, priority = "refund", "normal"
            elif issue == "cancellation":
                if data.get("digital_consumed"):
                    decision, priority = "deny", "normal"
                else:
                    decision, priority = ("refund", "normal") if int(data.get("order_age_days", 0)) <= 14 else ("deny", "normal")
            elif issue == "late_delivery":
                decision, priority = ("service_credit", "normal") if int(data.get("days_late", 0)) >= 7 else ("wait_and_track", "normal")
            else:
                decision, priority = ("escalate_technical", "high") if int(data.get("prior_contacts", 0)) >= 3 else ("troubleshoot", "normal")
            if amount > 400 and decision in {"refund", "replace"}:
                priority = "high"
        return {"decision": decision, "priority": priority, "reason": "Demo baseline policy with known blind spots."}

    decision, priority = _support_reference(data)
    if mode == "candidate":
        if n and n % 47 == 0 and decision == "request_evidence":
            decision = "manual_review"
        if n and n % 61 == 0 and priority == "normal":
            priority = "high"
        return {"decision": decision, "priority": priority, "reason": "Candidate policy with broader exception handling."}

    if decision == "manual_review":
        decision = "refund" if data.get("issue_type") in {"duplicate_charge", "cancellation"} else "replace"
        priority = "normal"
    if decision == "escalate_payment" and n % 2 == 0:
        decision, priority = "refund", "normal"
    if decision == "escalate_security" and n % 2 == 1:
        decision, priority = "refund", "normal"
    return {"decision": decision, "priority": priority, "reason": "Aggressive automation candidate; intentionally unsafe on selected guardrails."}


def _demo_output(pack: EvalPack, case: EvalCase, provider: str) -> dict[str, Any]:
    if pack.id == "support-ops-v1" or pack.id.startswith("support-ops"):
        mode = {"demo_baseline": "baseline", "demo_candidate": "candidate", "demo_risky": "risky"}.get(provider, "baseline")
        return _support_demo(case, mode)
    if pack.id == "fraud-analyst-v1":
        return _heuristic_fraud(case, stronger=provider in {"demo_candidate", "heuristic_v2"})
    field = pack.grader.required_fields[0] if pack.grader.required_fields else "decision"
    return {field: "review", "reason": "Generic demo provider cannot infer a custom company policy."}


async def run_agent(pack: EvalPack, case: EvalCase, config: AgentConfig) -> ProviderResult:
    started = time.perf_counter()
    try:
        if config.provider in {"heuristic", "heuristic_v2", "demo_baseline", "demo_candidate", "demo_risky"}:
            parsed = _demo_output(pack, case, config.provider)
            raw = json.dumps(parsed)
            return ProviderResult(raw_text=raw, parsed=parsed, latency_ms=(time.perf_counter() - started) * 1000)

        system = f"You are being evaluated. {pack.task_instruction}\nReturn only one JSON object. Do not include markdown."
        user = json.dumps(case.input, ensure_ascii=False)
        if config.provider == "openai_compatible":
            base = (config.base_url or "https://api.openai.com/v1").rstrip("/")
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            body = {"model": config.model or "gpt-5-mini", "temperature": config.temperature, "max_tokens": config.max_tokens, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(f"{base}/chat/completions", headers=headers, json=body)
                response.raise_for_status()
                payload = response.json()
            raw = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage") or {}
            inp = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            return ProviderResult(raw_text=raw, parsed=_extract_json(raw), latency_ms=(time.perf_counter() - started) * 1000, input_tokens=inp, output_tokens=out, estimated_cost_eur=_estimate_cost(config, inp, out))

        if config.provider == "webhook":
            if not config.webhook_url:
                raise ValueError("webhook_url is required")
            payload = {"instruction": pack.task_instruction, "case_id": case.id, "input": case.input}
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(config.webhook_url, json=payload)
                response.raise_for_status()
                result = response.json()
            parsed = result.get("output", result)
            return ProviderResult(raw_text=json.dumps(parsed), parsed=parsed, latency_ms=(time.perf_counter() - started) * 1000)
        raise ValueError(f"Unknown provider: {config.provider}")
    except Exception as exc:
        return ProviderResult(raw_text="", parsed={}, latency_ms=(time.perf_counter() - started) * 1000, error=str(exc))
