# Runbook

## Local
```bash
pip install -e '.[dev]'
pytest
uvicorn agentproof.app:app --reload
```

## Release gate
```bash
agentproof gate support-ops-v1 --provider demo_candidate --min-success .95 --max-critical 0 --github-summary
```

## Flagship evidence
```bash
python scripts/run_case_study.py
```

## Incident principle
If ground truth may have leaked into agent-visible input, treat all affected evidence as invalid, stop the evaluation, fix the pack, and rerun from scratch.
