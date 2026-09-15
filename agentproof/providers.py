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
    return (
        input_tokens / 1_000_000 * config.input_cost_per_million_eur
        + output_tokens / 1_000_000 * config.output_cost_per_million_eur
    )


def _heuristic_fraud(case: EvalCase) -> dict[str, Any]:
    data = case.input
    score = 0
    score += 28 if data.get("new_device") else 0
    score += 24 if data.get("country_mismatch") else 0
    score += 20 if data.get("merchant_risk") == "high" else 8 if data.get("merchant_risk") == "medium" else 0
    score += 18 if int(data.get("velocity_1h", 0)) >= 5 else 8 if int(data.get("velocity_1h", 0)) >= 3 else 0
    score += 18 if float(data.get("amount_eur", 0)) >= 1500 else 7 if float(data.get("amount_eur", 0)) >= 500 else 0
    score += 12 if int(data.get("customer_tenure_days", 9999)) < 30 else 0
    score -= 12 if data.get("card_present") else 0
    score -= 8 if data.get("known_merchant") else 0

    if score >= 58:
        decision = "block"
    elif score >= 30:
        decision = "review"
    else:
        decision = "approve"
    return {
        "decision": decision,
        "risk_score": max(0, min(100, score)),
        "reason": "Deterministic baseline using only observed transaction features.",
    }


def _heuristic_fraud_v2(case: EvalCase) -> dict[str, Any]:
    """A stronger offline candidate used to demonstrate regression comparison."""
    data = case.input
    score = 0
    score += 30 if data.get("new_device") else 0
    score += 27 if data.get("country_mismatch") else 0
    score += 24 if data.get("merchant_risk") == "high" else 10 if data.get("merchant_risk") == "medium" else 0
    score += 19 if int(data.get("velocity_1h", 0)) >= 5 else 9 if int(data.get("velocity_1h", 0)) >= 3 else 0
    score += 16 if float(data.get("amount_eur", 0)) >= 1200 else 8 if float(data.get("amount_eur", 0)) >= 500 else 0
    score += 14 if int(data.get("customer_tenure_days", 9999)) < 21 else 0
    score -= 14 if data.get("card_present") else 0
    score -= 9 if data.get("known_merchant") else 0

    if score >= 60:
        decision = "block"
    elif score >= 31:
        decision = "review"
    else:
        decision = "approve"
    return {
        "decision": decision,
        "risk_score": max(0, min(100, score)),
        "reason": "Candidate policy calibrated on the same observable feature schema.",
    }


async def run_agent(pack: EvalPack, case: EvalCase, config: AgentConfig) -> ProviderResult:
    started = time.perf_counter()
    try:
        if config.provider in {"heuristic", "heuristic_v2"}:
            parsed = _heuristic_fraud_v2(case) if config.provider == "heuristic_v2" else _heuristic_fraud(case)
            raw = json.dumps(parsed)
            elapsed = (time.perf_counter() - started) * 1000
            return ProviderResult(raw_text=raw, parsed=parsed, latency_ms=elapsed)

        system = (
            f"You are being evaluated. {pack.task_instruction}\n"
            "Return only one JSON object. Do not include markdown."
        )
        user = json.dumps(case.input, ensure_ascii=False)

        if config.provider == "openai_compatible":
            base = (config.base_url or "https://api.openai.com/v1").rstrip("/")
            headers = {"Content-Type": "application/json"}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            body = {
                "model": config.model or "gpt-5-mini",
                "temperature": config.temperature,
                "max_tokens": config.max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
            }
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(f"{base}/chat/completions", headers=headers, json=body)
                response.raise_for_status()
                payload = response.json()
            raw = payload["choices"][0]["message"]["content"]
            usage = payload.get("usage") or {}
            inp = int(usage.get("prompt_tokens") or usage.get("input_tokens") or 0)
            out = int(usage.get("completion_tokens") or usage.get("output_tokens") or 0)
            elapsed = (time.perf_counter() - started) * 1000
            return ProviderResult(
                raw_text=raw,
                parsed=_extract_json(raw),
                latency_ms=elapsed,
                input_tokens=inp,
                output_tokens=out,
                estimated_cost_eur=_estimate_cost(config, inp, out),
            )

        if config.provider == "webhook":
            if not config.webhook_url:
                raise ValueError("webhook_url is required")
            payload = {
                "instruction": pack.task_instruction,
                "case_id": case.id,
                "input": case.input,
            }
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(config.webhook_url, json=payload)
                response.raise_for_status()
                result = response.json()
            parsed = result.get("output", result)
            raw = json.dumps(parsed)
            elapsed = (time.perf_counter() - started) * 1000
            return ProviderResult(raw_text=raw, parsed=parsed, latency_ms=elapsed)

        raise ValueError(f"Unknown provider: {config.provider}")
    except Exception as exc:
        elapsed = (time.perf_counter() - started) * 1000
        return ProviderResult(raw_text="", parsed={}, latency_ms=elapsed, error=str(exc))
