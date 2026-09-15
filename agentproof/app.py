from __future__ import annotations

from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from .models import CompareRequest, EvalPack, RunRequest
from .runner import evaluate
from .compare import compare_runs
from .store import Store
from .builtin_packs import fraud_analyst_pack

ROOT = Path(__file__).resolve().parent.parent
WEB = Path(__file__).resolve().parent / "web"
PACKS = ROOT / "packs"
store = Store()
store.seed_from_directory(PACKS)
store.upsert_pack(fraud_analyst_pack())

app = FastAPI(title="Agent Proof", version="0.3.0")
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.get("/")
def home():
    return FileResponse(WEB / "index.html")


@app.get("/api/health")
def health():
    return {"ok": True, "service": "agent-proof", "version": "0.3.0"}


@app.get("/api/packs")
def list_packs():
    packs = store.list_packs()
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "case_count": len(p.cases),
        }
        for p in packs
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
    runs = store.list_runs(50)
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "pack_id": r.pack_id,
            "pack_name": r.pack_name,
            "agent_name": r.agent.name,
            "model": r.agent.model,
            "metrics": r.metrics,
        }
        for r in runs
    ]


@app.get("/api/runs/{run_id}")
def get_run(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    return run


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


@app.get("/api/compare/{baseline_id}/{candidate_id}/report.md", response_class=PlainTextResponse)
def comparison_report(baseline_id: str, candidate_id: str):
    baseline = store.get_run(baseline_id)
    candidate = store.get_run(candidate_id)
    if not baseline or not candidate:
        raise HTTPException(404, "Baseline or candidate run not found")
    try:
        comp = compare_runs(baseline, candidate)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    changed = [c for c in comp.cases if c.status != "unchanged"]
    lines = [
        f"# Agent Proof Regression Report — {comp.pack_name}",
        "",
        f"- Baseline: **{comp.baseline_agent}** (`{comp.baseline_run_id}`)",
        f"- Candidate: **{comp.candidate_agent}** (`{comp.candidate_run_id}`)",
        f"- Recommendation: **{comp.recommendation.upper()}**",
        f"- Paired cases: **{comp.paired_cases}**",
        f"- Success delta: **{comp.success_rate_delta:+.1%}**",
        f"- Critical-failure delta: **{comp.critical_failure_rate_delta:+.1%}**",
        f"- Cost/case delta: **€{comp.cost_per_case_delta_eur:+.4f}**",
        f"- Annual savings delta: **€{comp.annual_savings_delta_eur:+,.0f}**",
        f"- Paired exact p-value: **{comp.mcnemar_p_value:.4f}**",
        "",
        "## Decision reasons",
    ]
    lines += [f"- {reason}" for reason in comp.reasons]
    lines += ["", "## Changed cases"]
    if not changed:
        lines.append("- No pass/fail changes between runs.")
    for case in changed[:50]:
        critical = " · NEW CRITICAL" if case.candidate_critical and not case.baseline_critical else ""
        lines.append(
            f"- **{case.title}** — {case.status}: "
            f"{case.baseline_decision} → {case.candidate_decision}{critical}"
        )
    if len(changed) > 50:
        lines.append(f"- … plus {len(changed) - 50} more changed cases")
    return "\n".join(lines)


@app.get("/api/runs/{run_id}/report.md", response_class=PlainTextResponse)
def run_report(run_id: str):
    run = store.get_run(run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    m = run.metrics
    failed = [c for c in run.cases if not c.grade.passed]
    critical = [c for c in run.cases if c.grade.critical_failure]
    lines = [
        f"# Agent Proof Report — {run.pack_name}",
        "",
        f"- Run: `{run.id}`",
        f"- Agent: **{run.agent.name}**",
        f"- Gate: **{run.gate.status.upper()}**",
        f"- Success rate: **{m.success_rate:.1%}**",
        f"- Critical failure rate: **{m.critical_failure_rate:.1%}**",
        f"- Average cost/case: **€{m.agent_cost_per_case_eur:.4f}**",
        f"- Estimated annual savings: **€{m.estimated_annual_savings_eur:,.0f}**",
        f"- First-year net savings: **€{m.first_year_net_savings_eur:,.0f}**",
        "",
        "## Gate reasons",
    ]
    lines += [f"- {r}" for r in run.gate.reasons] or ["- All configured thresholds passed."]
    lines += ["", "## Failures"]
    for c in failed[:25]:
        flag = "CRITICAL" if c.grade.critical_failure else "mismatch"
        lines.append(f"- **{c.title}** — {flag}: " + "; ".join(c.grade.reasons))
    if len(failed) > 25:
        lines.append(f"- … plus {len(failed)-25} more failures")
    lines += ["", f"Critical cases: {len(critical)} / {m.total_cases}"]
    return "\n".join(lines)
