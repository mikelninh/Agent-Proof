# RUNBOOK

## Local
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
uvicorn agentproof.app:app --reload
```
Open http://localhost:8000.

## Docker
```bash
cp .env.example .env
docker compose up --build
```

## Offline regression demo
1. Click **Run 100-case fraud eval** (baseline, ~87%, BLOCK).
2. Click **Run stronger candidate** (candidate v2, ~97%, PASS).
3. In **Compare a candidate against baseline**, compare candidate against baseline.
4. Expected decision: **PROMOTE**, 11 fixes / 1 regression, no new critical failures.

## CLI
```bash
agentproof run builtin:fraud-analyst-v1 --provider heuristic --output evidence/baseline.json
agentproof run builtin:fraud-analyst-v1 --provider heuristic_v2 --output evidence/candidate.json --fail-on-block
agentproof compare evidence/baseline.json evidence/candidate.json --output evidence/comparison.json --fail-on-reject
```

## Before a pilot
Do not upload raw PII. Prefer synthetic or appropriately anonymised cases. Validate ground truth and critical failure definitions with the domain owner.
