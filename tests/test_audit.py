from agentproof.audit import DEFAULT_AUDIT_DIMENSIONS, assess_audit_pack
from agentproof.models import EvalCase, EvalPack, GraderSpec
from agentproof.support_pack import support_ops_trust_audit_pack


def _pack(case_count: int = 30, dimensions=DEFAULT_AUDIT_DIMENSIONS) -> EvalPack:
    cases = []
    for index in range(case_count):
        dimension = dimensions[index % len(dimensions)]
        cases.append(
            EvalCase(
                id=f"audit-{index + 1:03d}",
                title=f"Audit case {index + 1}",
                input={"case": index + 1},
                expected={"decision": "review"},
                tags=[f"risk:{dimension}", "synthetic"],
            )
        )
    return EvalPack(
        id="trust-audit-test",
        name="Trust audit test",
        description="Synthetic test pack",
        task_instruction="Return JSON with decision.",
        grader=GraderSpec(required_fields=["decision"]),
        cases=cases,
    )


def test_audit_pack_is_ready_with_30_cases_and_all_required_dimensions():
    result = assess_audit_pack(_pack())
    assert result.ready is True
    assert result.status == "ready"
    assert result.total_cases == 30
    assert result.missing_dimensions == ()
    assert all(result.dimension_counts[dimension] > 0 for dimension in DEFAULT_AUDIT_DIMENSIONS)


def test_audit_pack_rejects_happy_path_only_coverage():
    pack = _pack(dimensions=("correctness",))
    result = assess_audit_pack(pack)
    assert result.ready is False
    assert result.status == "not_ready"
    assert set(result.missing_dimensions) == {"boundary", "injection", "recovery", "approval"}
    assert any("missing risk coverage" in reason for reason in result.reasons)


def test_audit_pack_rejects_too_small_sample_even_if_dimensions_exist():
    result = assess_audit_pack(_pack(case_count=10))
    assert result.ready is False
    assert any("case count 10" in reason for reason in result.reasons)


def test_untagged_cases_are_visible_without_hiding_valid_coverage():
    pack = _pack()
    pack.cases[0].tags = ["synthetic"]
    result = assess_audit_pack(pack)
    assert result.untagged_cases == 1
    assert result.dimension_counts["correctness"] > 0



def test_dogfood_pack_is_audit_ready_and_each_required_dimension_has_real_cases():
    pack = support_ops_trust_audit_pack()
    result = assess_audit_pack(pack)
    assert result.ready is True
    assert result.total_cases == 30
    assert set(result.dimension_counts) == set(DEFAULT_AUDIT_DIMENSIONS)
    assert all(result.dimension_counts[dimension] == 6 for dimension in DEFAULT_AUDIT_DIMENSIONS)
    injection_cases = [case for case in pack.cases if "risk:injection" in case.tags]
    assert len(injection_cases) == 6
    assert all("untrusted_customer_message" in case.input for case in injection_cases)
    assert all("synthetic" in case.tags for case in pack.cases)
