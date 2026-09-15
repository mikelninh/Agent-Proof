from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .adversarial import generate_adversarial_drafts
from .builtin_packs import fraud_analyst_pack
from .support_pack import support_ops_pack
from .compare import compare_runs
from .coverage import coverage_for_run
from .models import (
    AdversarialApproveRequest,
    AdversarialGenerateRequest,
    AgentConfig,
    CaseStudyResult,
    Economics,
    EvalCase,
    EvalPack,
    GatePolicy,
    RunRequest,
    CompareRequest,
)
from .runner import evaluate
from .store import Store

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
PACKS = ROOT / "packs"
store = Store()
store.seed_from_directory(PACKS)
store.upsert_pack(fraud_analyst_pack())
store.upsert_pack(support_ops_pack())

app = FastAPI(title="Agent Proof", version="0.5.0")
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "service": "agent-proof", "version": "0.5.0"}


@app.get("/api/packs")
def list_packs():
    return [
        {"id": p.id, "name": p.name, "description": p.description, "case_count": len(p.cases)}
        for p in store.list_packs()
    ]


@app.get("/api/packs/{pack_id}")
def get_pack(pack_id: str):
    pack = store.get_pack(pack_id)
    if not pack:
        raise HTTPException(404, "Pack not found")
    return pack


@app.post("/api/packs")
def upsert_pack(pack: EvalPack):
    if not pack.cases:
        raise HTTPException(400, "Pack needs at least one case")
    store.upsert_pack(pack)
    return {"ok": True, "id": pack.id, "cases": len(pack.cases)}


@app.post("/api/packs/{pack_id}/adversarial-drafts")
def adversarial_drafts(pack_id: str, request: AdversarialGenerateRequest):
    pack = store.get_pack(pack_id)
    if not pack:
        raise HTTPException(404, "Pack not found")
    drafts = generate_adversarial_drafts(pack, request.limit, list(request.families))
    return {
        "pack_id": pack.id,
        "warning": "Suggested labels are copied from seed cases and are NOT ground truth. A human/domain owner must confirm every approved case.",
        "drafts": drafts,
    }


@app.post("/api/packs/{pack_id}/adversarial-approve")
def approve_adversarial(pack_id: str, request: AdversarialApproveRequest):
    base = store.get_pack(pack_id)
    if not base:
        raise HTTPException(404, "Base pack not found")
    if not request.cases:
        raise HTTPException(400, "Approve at least one adversarial case")
    cases = [
        EvalCase(
            id=item.draft.id,
            title=item.draft.title,
            input=item.draft.input,
            expected=item.expected,
            tags=item.draft.tags,
            failure_cost_eur=item.draft.failure_cost_eur,
        )
        for item in request.cases
    ]
    pack = EvalPack(
        id=request.id,
        name=request.name,
        description=request.description,
        task_instruction=base.task_instruction,
        grader=base.grader,
        cases=cases,
    )
    store.upsert_pack(pack)
    return {"ok": True, "id": pack.id, "cases": len(pack.cases)}


@app.post("/api/runs")
async def create_run(request: RunRequest):
    pack = store.get_pack(request.pack_id)
    if not pack:
        raise HTTPException(404, "Pack not found")
    run = await evaluate(pack, request)
    store.save_run(run)
    return run


@app.get("/api/runs")
def list_runs():
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "pack_id": r.pack_id,
            "pack_name": r.pack_name,
            "agent_name": r.agent.name,
            "model": r.agent.model,
            "metrics": r.metrics,
            "gate": r.gate,
        }
        for r in store.list_runs(50)
    ]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


@app.get("/api/runs/{run_id}/coverage")
def get_coverage(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return coverage_for_run(run)


@app.post("/api/compare")
def compare(request: CompareRequest):
    baseline = store.get_run(request.baseline_run_id)
    candidate = store.get_run(request.candidate_run_id)
    if not baseline or not candidate:
        raise HTTPException(404, "Baseline or candidate run not found")
    try:
        return compare_runs(baseline, candidate)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/case-study/support", response_model=CaseStudyResult)
async def support_case_study():
    pack = support_ops_pack()
    economics = Economics(human_minutes_per_case=9, human_hourly_cost_eur=34, annual_case_volume=60_000, implementation_cost_eur=30_000)
    gate = GatePolicy(min_success_rate=0.95, max_critical_failure_rate=0.0)
    configs = [
        AgentConfig(provider="demo_baseline", name="Support Agent v1 · baseline"),
        AgentConfig(provider="demo_candidate", name="Support Agent v2 · candidate"),
        AgentConfig(provider="demo_risky", name="Support Agent v3 · aggressive automation"),
    ]
    baseline, candidate, risky = [
        await evaluate(pack, RunRequest(pack_id=pack.id, agent=config, economics=economics, gate=gate))
        for config in configs
    ]
    for run in (baseline, candidate, risky):
        store.save_run(run)
    candidate_comp = compare_runs(baseline, candidate)
    risky_comp = compare_runs(baseline, risky)
    summary = [
        f"Candidate improves success from {baseline.metrics.success_rate:.1%} to {candidate.metrics.success_rate:.1%}.",
        f"Candidate deployment gate: {candidate.gate.status.upper()}; aggressive v3 gate: {risky.gate.status.upper()}.",
        f"Candidate annualized failure exposure: €{candidate.metrics.annualized_failure_exposure_eur:,.0f} vs baseline €{baseline.metrics.annualized_failure_exposure_eur:,.0f}.",
        f"Regression recommendation: {candidate_comp.recommendation.upper()} candidate v2; {risky_comp.recommendation.upper()} aggressive v3.",
    ]
    return CaseStudyResult(
        pack_id=pack.id,
        pack_name=pack.name,
        baseline=baseline,
        candidate=candidate,
        risky=risky,
        candidate_comparison=candidate_comp,
        risky_comparison=risky_comp,
        executive_summary=summary,
    )


def _run_report_md(run) -> str:
    m = run.metrics
    failed = [c for c in run.cases if not c.grade.passed]
    coverage = coverage_for_run(run)
    lines = [
        f"# Agent Proof Executive Report — {run.pack_name}",
        "",
        f"**Deployment decision: {run.gate.status.upper()}**",
        "",
        "## Executive metrics",
        f"- Agent: **{run.agent.name}**",
        f"- Success rate: **{m.success_rate:.1%}** across {m.total_cases} cases",
        f"- Critical failure rate: **{m.critical_failure_rate:.1%}**",
        f"- Annual labour savings: **€{m.estimated_annual_savings_eur:,.0f}**",
        f"- Annualized failure exposure: **€{m.annualized_failure_exposure_eur:,.0f}**",
        f"- Risk-adjusted annual value: **€{m.risk_adjusted_annual_value_eur:,.0f}**",
        f"- First-year net value: **€{m.first_year_net_savings_eur:,.0f}**",
        "",
        "## Gate reasons",
    ]
    lines += [f"- {r}" for r in run.gate.reasons] or ["- All configured thresholds passed."]
    lines += ["", "## Weakest coverage segments"]
    for item in coverage[:8]:
        lines.append(f"- **{item.tag}** — {item.success_rate:.1%} success across {item.cases} cases; {item.critical_failures} critical")
    lines += ["", "## Highest-priority failures"]
    ranked = sorted(failed, key=lambda c: (not c.grade.critical_failure, -c.failure_cost_eur))
    for c in ranked[:20]:
        flag = "CRITICAL" if c.grade.critical_failure else "mismatch"
        lines.append(f"- **{c.title}** — {flag}; exposure €{c.failure_cost_eur:,.0f}: " + "; ".join(c.grade.reasons))
    return "\n".join(lines)


@app.get("/api/runs/{run_id}/report.md", response_class=PlainTextResponse)
def run_report(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return _run_report_md(run)


@app.get("/api/compare/{baseline_id}/{candidate_id}/report.md", response_class=PlainTextResponse)
def comparison_report(baseline_id: str, candidate_id: str):
    baseline = store.get_run(baseline_id)
    candidate = store.get_run(candidate_id)
    if not baseline or not candidate:
        raise HTTPException(404, "Baseline or candidate run not found")
    comp = compare_runs(baseline, candidate)
    changed = [c for c in comp.cases if c.status != "unchanged"]
    lines = [
        f"# Agent Proof Regression Report — {comp.pack_name}",
        "",
        f"- Baseline: **{comp.baseline_agent}**",
        f"- Candidate: **{comp.candidate_agent}**",
        f"- Recommendation: **{comp.recommendation.upper()}**",
        f"- Success: **{comp.baseline_success_rate:.1%} → {comp.candidate_success_rate:.1%}** ({comp.success_rate_delta:+.1%})",
        f"- Fixes / regressions: **{comp.fixes} / {comp.regressions}**",
        f"- New critical failures: **{comp.new_critical_failures}**",
        f"- Exact paired p-value: **{comp.mcnemar_p_value:.4f}**",
        "",
        "## Decision reasons",
        *[f"- {r}" for r in comp.reasons],
        "",
        "## Changed cases",
    ]
    for case in changed[:50]:
        critical = " · NEW CRITICAL" if case.candidate_critical and not case.baseline_critical else ""
        lines.append(f"- **{case.title}** — {case.status}: {case.baseline_decision} → {case.candidate_decision}{critical}")
    return "\n".join(lines)
