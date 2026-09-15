from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path

from .adversarial import generate_adversarial_drafts
from .builtin_packs import builtin_pack
from .support_pack import support_ops_pack
from .compare import compare_runs
from .csvpack import pack_from_csv
from .models import AgentConfig, Economics, EvalPack, GatePolicy, RunRecord, RunRequest
from .runner import evaluate

PROVIDERS = ["heuristic", "heuristic_v2", "demo_baseline", "demo_candidate", "demo_risky", "openai_compatible", "webhook"]


def _load_pack(value: str) -> EvalPack:
    path = Path(value)
    if path.exists():
        return EvalPack.model_validate_json(path.read_text(encoding="utf-8"))
    if value == "support-ops-v1":
        return support_ops_pack()
    pack = builtin_pack(value)
    if pack:
        return pack
    raise SystemExit(f"Pack not found: {value}. Use a JSON path or built-in id support-ops-v1 / fraud-analyst-v1.")


def _agent(args) -> AgentConfig:
    return AgentConfig(
        provider=args.provider,
        model=getattr(args, "model", None),
        base_url=getattr(args, "base_url", None),
        api_key=getattr(args, "api_key", None),
        webhook_url=getattr(args, "webhook_url", None),
        name=getattr(args, "name", None) or getattr(args, "model", None) or args.provider,
        input_cost_per_million_eur=getattr(args, "input_cost", 0) or 0,
        output_cost_per_million_eur=getattr(args, "output_cost", 0) or 0,
    )


def _summary(run: RunRecord) -> str:
    m = run.metrics
    return (
        f"{run.gate.status.upper()} · success {m.success_rate:.1%} · critical {m.critical_failure_rate:.1%} · "
        f"failure exposure €{m.annualized_failure_exposure_eur:,.0f}/yr · risk-adjusted value €{m.risk_adjusted_annual_value_eur:,.0f}/yr"
    )


def _write_github_summary(text: str):
    path = os.getenv("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main():
    parser = argparse.ArgumentParser(prog="agentproof", description="Evaluate AI agents before production")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run an evaluation pack")
    run.add_argument("pack", help="JSON path or built-in pack id")
    run.add_argument("--provider", choices=PROVIDERS, default="demo_baseline")
    run.add_argument("--name")
    run.add_argument("--model")
    run.add_argument("--base-url")
    run.add_argument("--api-key")
    run.add_argument("--webhook-url")
    run.add_argument("--input-cost", type=float, default=0)
    run.add_argument("--output-cost", type=float, default=0)
    run.add_argument("--output")

    gate = sub.add_parser("gate", help="Run an eval and exit non-zero when deployment thresholds fail")
    gate.add_argument("pack", help="JSON path or built-in pack id")
    gate.add_argument("--provider", choices=PROVIDERS, default="demo_candidate")
    gate.add_argument("--name")
    gate.add_argument("--model")
    gate.add_argument("--base-url")
    gate.add_argument("--api-key")
    gate.add_argument("--webhook-url")
    gate.add_argument("--input-cost", type=float, default=0)
    gate.add_argument("--output-cost", type=float, default=0)
    gate.add_argument("--min-success", type=float, default=0.95)
    gate.add_argument("--max-critical", type=float, default=0.0)
    gate.add_argument("--max-failure-exposure", type=float)
    gate.add_argument("--output")
    gate.add_argument("--github-summary", action="store_true")

    compare = sub.add_parser("compare", help="Compare two saved run JSON files")
    compare.add_argument("baseline")
    compare.add_argument("candidate")
    compare.add_argument("--output")
    compare.add_argument("--require-promote", action="store_true")
    compare.add_argument("--github-summary", action="store_true")

    demo = sub.add_parser("demo-pack", help="Export a built-in deterministic pack")
    demo.add_argument("pack_id", choices=["support-ops-v1", "fraud-analyst-v1"])
    demo.add_argument("--output", required=True)

    csvp = sub.add_parser("pack-csv", help="Turn a historical CSV export into an eval pack")
    csvp.add_argument("csv")
    csvp.add_argument("--id", required=True)
    csvp.add_argument("--name", required=True)
    csvp.add_argument("--target", required=True, help="Ground-truth column")
    csvp.add_argument("--instruction", required=True)
    csvp.add_argument("--critical", help="Critical mismatch expected:actual")
    csvp.add_argument("--output", required=True)

    adv = sub.add_parser("adversarial", help="Generate adversarial drafts for human review")
    adv.add_argument("pack", help="JSON path or built-in pack id")
    adv.add_argument("--limit", type=int, default=16)
    adv.add_argument("--families", default="missing,boundary,boolean_flip,conflict")
    adv.add_argument("--output", required=True)

    args = parser.parse_args()
    if args.command == "pack-csv":
        pack = pack_from_csv(args.csv, args.id, args.name, args.instruction, args.target, args.critical)
        Path(args.output).write_text(pack.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote {len(pack.cases)} cases to {args.output}")
        return
    if args.command == "demo-pack":
        pack = support_ops_pack() if args.pack_id == "support-ops-v1" else builtin_pack(args.pack_id)
        assert pack is not None
        Path(args.output).write_text(pack.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote {len(pack.cases)} deterministic cases to {args.output}")
        return
    if args.command == "adversarial":
        pack = _load_pack(args.pack)
        families = [x.strip() for x in args.families.split(",") if x.strip()]
        drafts = generate_adversarial_drafts(pack, args.limit, families)
        payload = {"warning": "Draft labels are suggestions only. Domain-owner confirmation is required before evaluation.", "drafts": [d.model_dump() for d in drafts]}
        Path(args.output).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Wrote {len(drafts)} adversarial drafts to {args.output}")
        return
    if args.command == "compare":
        baseline = RunRecord.model_validate_json(Path(args.baseline).read_text(encoding="utf-8"))
        candidate = RunRecord.model_validate_json(Path(args.candidate).read_text(encoding="utf-8"))
        comp = compare_runs(baseline, candidate)
        text = f"# Agent Proof regression gate\n\n**{comp.recommendation.upper()}** · {comp.baseline_success_rate:.1%} → {comp.candidate_success_rate:.1%} · {comp.fixes} fixes / {comp.regressions} regressions · {comp.new_critical_failures} new critical · p={comp.mcnemar_p_value:.4f}\n"
        print(text.strip())
        if args.output:
            Path(args.output).write_text(comp.model_dump_json(indent=2), encoding="utf-8")
        if args.github_summary:
            _write_github_summary(text)
        if args.require_promote and comp.recommendation != "promote":
            raise SystemExit(2)
        return

    pack = _load_pack(args.pack)
    policy = GatePolicy()
    if args.command == "gate":
        policy = GatePolicy(min_success_rate=args.min_success, max_critical_failure_rate=args.max_critical, max_annual_failure_exposure_eur=args.max_failure_exposure)
    request = RunRequest(pack_id=pack.id, agent=_agent(args), economics=Economics(), gate=policy)
    record = asyncio.run(evaluate(pack, request))
    if args.output:
        Path(args.output).write_text(record.model_dump_json(indent=2), encoding="utf-8")
    else:
        print(record.model_dump_json(indent=2) if args.command == "run" else _summary(record))
    if args.command == "gate":
        line = f"# Agent Proof deployment gate\n\n**{_summary(record)}**\n"
        print(_summary(record))
        if args.github_summary:
            _write_github_summary(line)
        if record.gate.status != "pass":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
