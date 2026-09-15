from __future__ import annotations

import asyncio
from pathlib import Path

from agentproof.support_pack import support_ops_pack
from agentproof.compare import compare_runs
from agentproof.models import AgentConfig, Economics, GatePolicy, RunRequest
from agentproof.runner import evaluate


async def main():
    out = Path("evidence/support-case-study")
    out.mkdir(parents=True, exist_ok=True)
    pack = support_ops_pack()
    economics = Economics(human_minutes_per_case=9, human_hourly_cost_eur=34, annual_case_volume=60_000, implementation_cost_eur=30_000)
    gate = GatePolicy(min_success_rate=.95, max_critical_failure_rate=0)
    runs = {}
    for provider, name in [
        ("demo_baseline", "baseline"),
        ("demo_candidate", "candidate"),
        ("demo_risky", "aggressive"),
    ]:
        run = await evaluate(pack, RunRequest(pack_id=pack.id, agent=AgentConfig(provider=provider, name=name), economics=economics, gate=gate))
        runs[name] = run
        (out / f"{name}.json").write_text(run.model_dump_json(indent=2), encoding="utf-8")
    comp = compare_runs(runs["baseline"], runs["candidate"])
    (out / "candidate-vs-baseline.json").write_text(comp.model_dump_json(indent=2), encoding="utf-8")
    print(f"baseline {runs['baseline'].metrics.success_rate:.1%} -> candidate {runs['candidate'].metrics.success_rate:.1%}; {comp.recommendation.upper()}")


if __name__ == "__main__":
    asyncio.run(main())
