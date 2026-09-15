from agentproof.graders import grade_case
from agentproof.models import CriticalMismatch, EvalCase, GraderSpec


def spec():
    return GraderSpec(
        required_fields=["decision"],
        critical_mismatches=[CriticalMismatch(field="decision", expected="block", actual="approve")],
    )


def test_exact_match_passes():
    case = EvalCase(id="1", title="x", input={}, expected={"decision": "block"})
    grade = grade_case(case, {"decision": "block"}, spec())
    assert grade.passed
    assert not grade.critical_failure


def test_dangerous_false_approval_is_critical():
    case = EvalCase(id="1", title="x", input={}, expected={"decision": "block"})
    grade = grade_case(case, {"decision": "approve"}, spec())
    assert not grade.passed
    assert grade.critical_failure
