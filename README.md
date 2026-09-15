# Agent Proof

> **Prove AI workflows before they touch customers, money, or production systems.**

Agent Proof is a local-first evaluation lab for AI agents and automated workflows. It runs realistic scenario packs, grades outcomes, flags dangerous failures, records latency and cost, and converts the result into a business case.

The MVP ships with a **100-case Fraud Analyst Arena** so it is useful immediately — no API key required.

## Why this exists

AI demos are easy. Deployment evidence is hard.

A team evaluating an agent usually needs to answer:

- Does it complete the task correctly across many cases?
- What are the *dangerous* failure modes, not just the average score?
- Can we inspect exactly what happened on a failed case?
- How much does each task cost and how long does it take?
- Does the economics beat the current human workflow?
- Did a prompt/model/tool change make the system better or worse?

Agent Proof makes those questions the product.

## What works today

- **100-case synthetic Fraud Analyst Arena** with hidden ground truth
- **Deterministic grading** and asymmetric critical-failure rules
- **Built-in baseline agent** so the app works immediately
- **OpenAI-compatible adapter** for hosted or local models
- **Generic webhook adapter** for evaluating your own agent
- **Bring-your-own scenario packs** by uploading JSON
- **Case-level trace replay**: input → output → ground truth → grader evidence
- **Cost, latency and ROI** from configurable human baselines
- **Run history** in SQLite for regression checks
- **CLI + web UI + API**
- **Docker + CI + tests**

## Quick start

```bash
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\\Scripts\\activate
pip install -e '.[dev]'
uvicorn agentproof.app:app --reload
```

Open **http://localhost:8000** and press **Run 100-case fraud eval**.

Or with Docker:

```bash
cp .env.example .env
docker compose up --build
```

## Evaluate a real model

Choose **OpenAI-compatible API** in the UI and provide:

- model name
- base URL
- API key
- optional token prices for accurate cost reporting

Because the adapter uses the common `/chat/completions` shape, it can work with OpenAI-compatible gateways and many local model servers.

The API key is used for the run and removed from the persisted record.

## Evaluate your own agent

Choose **Your agent webhook** and point Agent Proof at an endpoint accepting:

```json
{
  "instruction": "Review the transaction...",
  "case_id": "fraud-001",
  "input": {"amount_eur": 1290, "new_device": true}
}
```

Return either the output object directly or:

```json
{"output": {"decision": "review", "reason": "..."}}
```

## Scenario pack format

```json
{
  "id": "claims-v1",
  "name": "Claims Triage v1",
  "description": "Historical-style synthetic claims",
  "task_instruction": "Return JSON with decision...",
  "grader": {
    "type": "json_fields",
    "required_fields": ["decision"],
    "field_weights": {"decision": 1.0},
    "critical_mismatches": [
      {"field": "decision", "expected": "reject", "actual": "approve"}
    ]
  },
  "cases": [
    {
      "id": "claim-001",
      "title": "Claim 001",
      "input": {"amount": 820, "documents_complete": false},
      "expected": {"decision": "review"},
      "tags": ["missing-documents"]
    }
  ]
}
```

**Important:** expected answers are never included in the prompt sent to the agent.

## CLI

```bash
agentproof run packs/fraud-analyst-v1.json \
  --provider heuristic \
  --output evidence/demo-run.json
```

## API

- `GET /api/health`
- `GET /api/packs`
- `POST /api/packs`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{id}`

## What makes this commercially useful

The product is intentionally not "another benchmark leaderboard." A buyer can attach an agent to the same cases their human team understands, define costly failure modes, and get an evidence trail plus an ROI estimate. That is a much shorter path from demo to a paid deployment decision.

### Pilot offer

A strong first service around the software is:

> **Agent Readiness Evaluation** — turn 50–500 representative cases into an eval pack, test the current agent and one alternative, identify critical failure modes, and deliver a deployment/ROI report.

The software becomes the repeatable engine behind that service and, later, continuous regression testing for production agents.

## Roadmap

1. CSV → pack builder and field mapping
2. Pairwise run comparison with statistical confidence intervals
3. LLM-as-judge for subjective outputs, always alongside deterministic checks
4. Red-team / adversarial scenario generation
5. Approval thresholds and deployment gates in CI
6. Team workspaces, auth and hosted storage
7. PII-safe connectors for historical-case import

## Safety / data note

The bundled pack is synthetic. For real pilots, use synthetic or appropriately anonymised data and involve the domain owner in validating ground truth. Agent Proof is an evaluation tool, not a substitute for legal, compliance, medical, financial or security review.

## Build system

The repository follows:

**01 SHAPE → 02 SPECIFY → 03 DELEGATE → 04 PROVE → 05 SHIP → 06 WATCH**

See `.ai-build/` and `AGENTS.md`.

## Deployment gates

Every run can enforce explicit thresholds such as **minimum success rate** and **maximum critical-failure rate**. The result is a simple PASS/BLOCK decision with reasons, so the evaluation can become a release gate rather than a dashboard people forget to check.

## Turn an existing CSV into an eval pack

If a team already has a historical export with a ground-truth column:

```bash
agentproof pack-csv historical_cases.csv \
  --id support-v1 \
  --name "Support Resolution v1" \
  --target decision \
  --instruction "Resolve the case and return JSON with decision" \
  --critical reject:approve \
  --output packs/support-v1.json
```

This creates a portable pack where the target column is held out from the agent and used only for grading.
