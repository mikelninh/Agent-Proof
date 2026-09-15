# Agent Proof

> **Prove an AI workflow before it touches customers, money, or production.**

Agent Proof is a local-first evaluation and release-gating system for AI agents. It turns representative work into reusable eval packs, runs candidate agents against hidden ground truth, surfaces critical failures and weak segments, compares versions case-by-case, quantifies risk/ROI, and can fail CI when a candidate is unsafe.

## Why it exists

A compelling AI demo does not answer the questions a deployment owner actually has:

- Does this agent work across representative cases?
- Which misses are merely wrong, and which are dangerous?
- Did the new prompt/model/tool version fix more cases than it broke?
- Are failures concentrated in a particular market, issue type or risk class?
- What is the estimated cost of observed misses at production volume?
- Can we block a release automatically instead of hoping someone checks a dashboard?

Agent Proof makes those questions the product.

## What works now — v0.5

- **Flagship 180-case Support Ops case study** with an explicit reference policy
- **100-case Fraud Analyst Arena** retained as a second built-in pack
- **Historical CSV Pilot Mode** with browser-side mapping and hidden target separation
- **OpenAI-compatible API** and **generic agent webhook** adapters
- Three offline demo agents: baseline, safe candidate and intentionally risky candidate
- Deterministic JSON-field grading and configurable asymmetric critical failures
- Failure-cost weighting and **annualized failure-exposure** estimates
- Explicit **PASS / BLOCK** deployment gates
- Case-level trace replay: input → output → hidden truth → grader evidence
- **Coverage map** by tags / risk segments
- **Paired regression comparison** with fixes, regressions, new critical failures, Wilson intervals and exact McNemar test
- **Adversarial lab** for boundary values, missing fields, boolean flips, conflicting signals and scale tests
- Human confirmation required before adversarial draft labels become ground truth
- Executive Markdown reports
- CLI, API, web UI, Docker, tests and GitHub Actions
- **CI release gate** that exits non-zero on deployment-policy failure

## Flagship result

The bundled Support Ops study is deterministic and reproducible:

| Agent | Success | Critical | Annualized failure exposure | Gate |
|---|---:|---:|---:|---|
| baseline | 83.3% | 0.0% | €3.55m | BLOCK |
| candidate v2 | 99.4% | 0.0% | €11.7k | PASS |
| aggressive v3 | 82.2% | 2.2% | €4.62m | BLOCK |

Candidate v2 fixes 30 paired failures and introduces one regression. The paired comparison recommends **PROMOTE**. Aggressive v3 introduces critical failures and is **REJECTED**. See [`case-studies/support-ops.md`](case-studies/support-ops.md).

These numbers are synthetic decision-support evidence, not claims about a real company or model.

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e '.[dev]'
uvicorn agentproof.app:app --reload
```

Open **http://localhost:8000** and click **Run flagship Support Ops study**.

Or:

```bash
cp .env.example .env
docker compose up --build
```

## Run a deployment gate from the CLI

```bash
agentproof gate support-ops-v1 \
  --provider demo_candidate \
  --min-success .95 \
  --max-critical 0 \
  --output candidate-run.json \
  --github-summary
```

Exit code is non-zero if the gate blocks. The repository includes `.github/workflows/agent-proof-gate.yml` as a working example.

## Evaluate a real agent

### Webhook

Point Agent Proof at an endpoint accepting:

```json
{
  "instruction": "Resolve the support case...",
  "case_id": "support-001",
  "input": {"issue_type": "cancellation", "amount_eur": 79}
}
```

Return either the output object directly or:

```json
{"output": {"decision": "refund", "priority": "normal"}}
```

### OpenAI-compatible endpoint

Choose **OpenAI-compatible API** in the UI and provide model, base URL and API key. API keys are used for the run and removed from persisted run records.

## Bring historical cases in under five minutes

Click **Import historical CSV**. The browser parses the file locally, then lets the user:

1. choose the hidden ground-truth column,
2. choose exactly which columns the agent may see,
3. exclude likely PII columns,
4. define a dangerous mismatch such as `reject → approve`,
5. inspect missing labels and a preview,
6. create a reusable eval pack and run it immediately.

Headless equivalent:

```bash
agentproof pack-csv examples/support-sample.csv \
  --id support-pilot-v1 \
  --name "Support Pilot" \
  --target decision \
  --instruction "Resolve the case and return JSON with decision" \
  --critical deny:refund \
  --output support-pilot-v1.json
```

## Adversarial testing

The web **Adversarial Lab** creates draft mutations such as boundary values, missing data and conflicting signals. The software deliberately does **not** treat generated labels as truth. A domain owner must check the draft and confirm/edit the expected JSON before an adversarial pack can be created.

CLI draft generation:

```bash
agentproof adversarial support-ops-v1 --limit 20 --output adversarial-drafts.json
```

## Compare versions

```bash
agentproof run support-ops-v1 --provider demo_baseline --output baseline.json
agentproof run support-ops-v1 --provider demo_candidate --output candidate.json
agentproof compare baseline.json candidate.json --require-promote --github-summary
```

The comparison is paired by case ID and reports fixes, regressions, new critical failures and an exact McNemar p-value.

## API

- `GET /api/health`
- `GET /api/packs`
- `POST /api/packs`
- `POST /api/packs/{id}/adversarial-drafts`
- `POST /api/packs/{id}/adversarial-approve`
- `POST /api/runs`
- `GET /api/runs/{id}`
- `GET /api/runs/{id}/coverage`
- `GET /api/runs/{id}/report.md`
- `POST /api/compare`
- `GET /api/compare/{baseline}/{candidate}/report.md`
- `POST /api/case-study/support`

## Commercial pilot

> **Agent Readiness Evaluation** — provide 50–500 representative, appropriately anonymised cases plus an agent endpoint. Agent Proof turns them into an evaluation pack, defines critical failure rules with the domain owner, evaluates the current and candidate agent, and delivers a deployment/regression/ROI report.

The software is the repeatable engine; the valuable asset becomes the customer's validated scenario library, ground truth, failure taxonomy and regression history.

## Safety and data

The bundled case studies are synthetic. For real pilots, use synthetic or appropriately anonymised data and have the domain owner validate ground truth and failure costs. PII detection in Pilot Mode is only a warning heuristic. Agent Proof is decision-support infrastructure, not a substitute for legal, compliance, medical, financial or security review.

## Build system

**01 SHAPE → 02 SPECIFY → 03 DELEGATE → 04 PROVE → 05 SHIP → 06 WATCH**

See `.ai-build/` and `AGENTS.md`.
