import csv
from pathlib import Path

from agentproof.csvpack import pack_from_csv


def test_csv_target_is_hidden_from_agent_input(tmp_path: Path):
    path = tmp_path / "cases.csv"
    path.write_text("ticket,amount,decision\nA-1,100,approve\nA-2,900,review\n", encoding="utf-8")
    pack = pack_from_csv(
        str(path),
        "support-v1",
        "Support",
        "Return a decision",
        "decision",
        "review:approve",
    )
    assert len(pack.cases) == 2
    assert "decision" not in pack.cases[0].input
    assert pack.cases[0].expected == {"decision": "approve"}
    assert pack.grader.critical_mismatches[0].field == "decision"


def test_csv_import_rejects_unknown_target(tmp_path: Path):
    path = tmp_path / "cases.csv"
    path.write_text("ticket,decision\nA-1,approve\n", encoding="utf-8")
    try:
        pack_from_csv(str(path), "x", "X", "Do X", "missing")
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "Target column" in str(exc)
