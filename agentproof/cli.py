from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from .models import AgentConfig, Economics, EvalPack, RunRecord, RunRequest
from .runner import evaluate
from .compare import compare_runs
from .csvpack import pack_from_csv
from .builtin_packs import builtin_pack


def main():
    parser = argparse.ArgumentParser(prog="agentproof", description="Evaluate AI agents against scenario packs")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("pack", help="Path to an eval pack JSON, or builtin:fraud-analyst-v1")
    run.add_argument("--provider", choices=["heuristic", "heuristic_v2", "openai_compatible", "webhook"], default="heuristic")
    run.add_argument("--model")
    run.add_argument("--base-url")
    run.add_argument("--api-key")
    run.add_argument("--webhook-url")
    run.add_argument("--output")
    run.add_argument("--fail-on-block", action="store_true", help="Exit non-zero if the deployment gate blocks")
    cmp = sub.add_parser("compare", help="Compare two saved run JSON files case-by-case")
    cmp.add_argument("baseline")
    cmp.add_argument("candidate")
    cmp.add_argument("--output")
    cmp.add_argument("--fail-on-reject", action="store_true", help="Exit non-zero when recommendation is reject")
    csvp = sub.add_parser("pack-csv", help="Turn a historical CSV export into an eval pack")
    csvp.add_argument("csv")
    csvp.add_argument("--id", required=True)
    csvp.add_argument("--name", required=True)
    csvp.add_argument("--target", required=True, help="Ground-truth column, e.g. decision")
    csvp.add_argument("--instruction", required=True)
    csvp.add_argument("--critical", help="Critical mismatch expected:actual, e.g. block:approve")
    csvp.add_argument("--output", required=True)

    args = parser.parse_args()

    if args.command == "compare":
        baseline = RunRecord.model_validate_json(Path(args.baseline).read_text(encoding="utf-8"))
        candidate = RunRecord.model_validate_json(Path(args.candidate).read_text(encoding="utf-8"))
        comparison = compare_runs(baseline, candidate)
        payload = comparison.model_dump_json(indent=2)
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            print(payload)
        if args.fail_on_reject and comparison.recommendation == "reject":
            raise SystemExit(2)
        return

    if args.command == "pack-csv":
        pack = pack_from_csv(args.csv, args.id, args.name, args.instruction, args.target, args.critical)
        Path(args.output).write_text(pack.model_dump_json(indent=2), encoding="utf-8")
        print(f"Wrote {len(pack.cases)} cases to {args.output}")
        return

    if args.command == "run":
        if args.pack.startswith("builtin:"):
            pack = builtin_pack(args.pack.split(":", 1)[1])
            if pack is None:
                raise SystemExit(f"Unknown built-in pack: {args.pack}")
        else:
            pack = EvalPack.model_validate_json(Path(args.pack).read_text(encoding="utf-8"))
        req = RunRequest(
            pack_id=pack.id,
            agent=AgentConfig(
                provider=args.provider,
                model=args.model,
                base_url=args.base_url,
                api_key=args.api_key,
                webhook_url=args.webhook_url,
                name=args.model or args.provider,
            ),
            economics=Economics(),
        )
        record = asyncio.run(evaluate(pack, req))
        payload = record.model_dump_json(indent=2)
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            print(payload)
        if args.fail_on_block and record.gate.status == "block":
            raise SystemExit(2)


if __name__ == "__main__":
    main()
