import asyncio

from agentproof.adversarial import generate_adversarial_drafts
from agentproof.support_pack import support_ops_pack
from agentproof.compare import compare_runs
from agentproof.coverage import coverage_for_run
from agentproof.models import AgentConfig, Economics, GatePolicy, RunRequest
from agentproof.runner import evaluate


def _run(provider: str):
    pack = support_ops_pack()
    return asyncio.run(
        evaluate(
            pack,
            RunRequest(
                pack_id=pack.id,
                agent=AgentConfig(provider=provider, name=provider),
                economics=Economics(annual_case_volume=60_000),
                gate=GatePolicy(min_success_rate=0.95, max_critical_failure_rate=0),
            ),
        )
    )


def test_flagship_candidate_passes_and_aggressive_agent_is_blocked():
    candidate = _run("demo_candidate")
    risky = _run("demo_risky")
    assert candidate.metrics.success_rate >= 0.95
    assert candidate.metrics.critical_failure_rate == 0
    assert candidate.gate.status == "pass"
    assert risky.metrics.critical_failure_rate > 0
    assert risky.gate.status == "block"


def test_comparison_promotes_candidate_over_baseline():
    baseline = _run("demo_baseline")
    candidate = _run("demo_candidate")
    comp = compare_runs(baseline, candidate)
    assert comp.recommendation == "promote"
    assert comp.fixes > comp.regressions
    assert comp.new_critical_failures == 0


def test_coverage_finds_real_segments():
    candidate = _run("demo_candidate")
    coverage = coverage_for_run(candidate)
    assert coverage
    assert any(x.tag.startswith("issue:") for x in coverage)
    assert all(0 <= x.success_rate <= 1 for x in coverage)


def test_adversarial_generation_keeps_labels_as_suggestions_only():
    pack = support_ops_pack(20)
    drafts = generate_adversarial_drafts(pack, 8, ["boundary", "missing", "conflict"])
    assert len(drafts) == 8
    assert all(d.suggested_expected for d in drafts)
    assert all("adversarial" in d.tags for d in drafts)
    assert any(d.input != pack.cases[0].input for d in drafts)
