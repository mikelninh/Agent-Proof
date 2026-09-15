from pathlib import Path

from agentproof.csvpack import pack_from_csv


def test_csv_ground_truth_is_not_agent_visible(tmp_path: Path):
    path = tmp_path / "cases.csv"
    path.write_text("ticket,amount,decision\nA,10,approve\nB,99,review\n", encoding="utf-8")
    pack = pack_from_csv(str(path), "x", "X", "Decide", "decision")
    assert len(pack.cases) == 2
    assert "decision" not in pack.cases[0].input
    assert pack.cases[0].expected == {"decision": "approve"}
