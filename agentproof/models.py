from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class CriticalMismatch(BaseModel):
    field: str
    expected: Any
    actual: Any


class GraderSpec(BaseModel):
    type: Literal["json_fields"] = "json_fields"
    required_fields: list[str] = Field(default_factory=list)
    field_weights: dict[str, float] = Field(default_factory=dict)
    critical_mismatches: list[CriticalMismatch] = Field(default_factory=list)


class EvalCase(BaseModel):
    id: str
    title: str
    input: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = Field(default_factory=list)


class EvalPack(BaseModel):
    id: str
    name: str
    description: str
    task_instruction: str
    grader: GraderSpec
    cases: list[EvalCase]


class AgentConfig(BaseModel):
    provider: Literal["heuristic", "heuristic_v2", "openai_compatible", "webhook"] = "heuristic"
    name: str = "Built-in heuristic baseline"
    model: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    webhook_url: str | None = None
    temperature: float = 0
    max_tokens: int = 300
    input_cost_per_million_eur: float = 0
    output_cost_per_million_eur: float = 0


class Economics(BaseModel):
    human_minutes_per_case: float = 8
    human_hourly_cost_eur: float = 35
    annual_case_volume: int = 50_000
    implementation_cost_eur: float = 25_000


class GatePolicy(BaseModel):
    min_success_rate: float = 0.95
    max_critical_failure_rate: float = 0.0
    max_agent_cost_per_case_eur: float | None = None


class RunRequest(BaseModel):
    pack_id: str
    agent: AgentConfig = Field(default_factory=AgentConfig)
    economics: Economics = Field(default_factory=Economics)
    gate: GatePolicy = Field(default_factory=GatePolicy)


class ProviderResult(BaseModel):
    raw_text: str
    parsed: dict[str, Any] = Field(default_factory=dict)
    latency_ms: float = 0
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_eur: float = 0
    error: str | None = None


class CaseGrade(BaseModel):
    score: float
    passed: bool
    critical_failure: bool
    reasons: list[str] = Field(default_factory=list)


class CaseResult(BaseModel):
    case_id: str
    title: str
    input: dict[str, Any]
    expected: dict[str, Any]
    output: ProviderResult
    grade: CaseGrade


class RunMetrics(BaseModel):
    total_cases: int
    success_rate: float
    average_score: float
    critical_failure_rate: float
    escalation_rate: float
    avg_latency_ms: float
    avg_cost_eur: float
    human_cost_per_case_eur: float
    agent_cost_per_case_eur: float
    annual_human_cost_eur: float
    annual_agent_cost_eur: float
    estimated_annual_savings_eur: float
    first_year_net_savings_eur: float
    roi_multiple: float | None


class GateResult(BaseModel):
    status: Literal["pass", "block"]
    reasons: list[str] = Field(default_factory=list)


class RunRecord(BaseModel):
    id: str
    created_at: str
    pack_id: str
    pack_name: str
    agent: AgentConfig
    economics: Economics
    metrics: RunMetrics
    gate: GateResult
    cases: list[CaseResult]


class CompareRequest(BaseModel):
    baseline_run_id: str
    candidate_run_id: str


class ComparisonCase(BaseModel):
    case_id: str
    title: str
    status: Literal["unchanged", "fix", "regression"]
    baseline_passed: bool
    candidate_passed: bool
    baseline_critical: bool
    candidate_critical: bool
    baseline_decision: Any | None = None
    candidate_decision: Any | None = None
    baseline_score: float
    candidate_score: float


class RunComparison(BaseModel):
    baseline_run_id: str
    candidate_run_id: str
    pack_id: str
    pack_name: str
    paired_cases: int
    baseline_agent: str
    candidate_agent: str
    baseline_success_rate: float
    candidate_success_rate: float
    baseline_success_ci: tuple[float, float]
    candidate_success_ci: tuple[float, float]
    success_rate_delta: float
    critical_failure_rate_delta: float
    cost_per_case_delta_eur: float
    latency_delta_ms: float
    annual_savings_delta_eur: float
    regressions: int
    fixes: int
    new_critical_failures: int
    resolved_critical_failures: int
    discordant_pairs: int
    mcnemar_p_value: float
    recommendation: Literal["promote", "hold", "reject"]
    reasons: list[str] = Field(default_factory=list)
    cases: list[ComparisonCase] = Field(default_factory=list)
