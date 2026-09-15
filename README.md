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
- **Two built-in offline agents** (87% baseline + ~97% candidate) so regression comparison works immediately
- **OpenAI-compatible adapter** for hosted or local models
- **Generic webhook adapter** for evaluating your own agent
- **Pilot Mode CSV importer**: map a historical export into an eval from the browser, choose agent-visible fields, hold out ground truth, flag likely PII, and define a critical mismatch
- **Bring-your-own JSON scenario packs**
- **Case-level trace replay**: input → output → ground truth → grader evidence
- **Cost, latency and ROI** from configurable human baselines
- **Paired run comparison** with fixes, regressions, new critical failures, Wilson intervals and an exact McNemar test
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

Open **http://localhost:8000**. Run the baseline, then press **Run stronger candidate** and compare the two runs. The bundled demo intentionally moves from a blocked ~87% baseline to a ~97% candidate so you can see the release-decision workflow without an API key.

Or with Docker:

```bash
cp .env.example .env
docker compose up --build
```

## Pilot Mode — bring historical cases without writing JSON

Press **Import historical CSV** in the web UI. The browser parses the file locally and gives you a small import wizard:

1. choose the **hidden ground-truth column** (for example `decision`),
2. choose exactly which columns the evaluated agent may see,
3. exclude likely personal-data columns,
4. optionally define an asymmetric critical failure such as `fraud → approve`,
5. inspect label distribution, missing targets, duplicates and a five-row preview,
6. create the evaluation pack and run it immediately.

The target column is never copied into `case.input`; it is stored separately as `case.expected` and is used only after the agent returns an answer. The PII detector is deliberately conservative and is only a warning — it is not a compliance guarantee.

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
agentproof run builtin:fraud-analyst-v1 \
  --provider heuristic \
  --output evidence/demo-run.json
```

### CI-style run and regression commands

Fail a pipeline when an agent misses its deployment gate:

```bash
agentproof run builtin:fraud-analyst-v1 \
  --provider heuristic_v2 \
  --output evidence/candidate.json \
  --fail-on-block
```

Compare two saved runs and fail when the candidate should be rejected:

```bash
agentproof compare evidence/baseline.json evidence/candidate.json \
  --output evidence/comparison.json \
  --fail-on-reject
```

The comparison is paired by case ID. It reports fixes, regressions, newly introduced critical failures, cost/latency deltas and a two-sided exact McNemar p-value.

### Headless CSV import

```bash
agentproof pack-csv historical_cases.csv \
  --id support-v1 \
  --name "Support Resolution v1" \
  --target decision \
  --instruction "Resolve the case and return JSON with decision" \
  --critical reject:approve \
  --output packs/support-v1.json
```

The target column is held out from the agent and used only for grading.

## API

- `GET /api/health`
- `GET /api/packs`
- `POST /api/packs`
- `POST /api/runs`
- `GET /api/runs`
- `GET /api/runs/{id}`
- `POST /api/compare`
- `GET /api/compare/{baseline_id}/{candidate_id}/report.md`

## What makes this commercially useful

The product is intentionally not "another benchmark leaderboard." A buyer can attach an agent to the same cases their human team understands, define costly failure modes, and get an evidence trail plus an ROI estimate. That is a much shorter path from demo to a paid deployment decision.

### Pilot offer

> **Agent Readiness Evaluation** — turn 50–500 representative cases into an eval pack, test the current agent and one alternative, identify critical failure modes, and deliver a deployment/ROI report.

The software becomes the repeatable engine behind that service and, later, continuous regression testing for production agents.

## Roadmap

1. Adversarial / red-team scenario generation with human approval of ground truth
2. CI annotations / GitHub check summaries for deployment gates
3. Team workspaces, auth and hosted storage
4. PII-safe connectors for historical-case import
5. LLM-as-judge for subjective outputs, always alongside deterministic checks

## Safety / data note

The bundled pack is synthetic. For real pilots, use synthetic or appropriately anonymised data and involve the domain owner in validating ground truth. Agent Proof is an evaluation tool, not a substitute for legal, compliance, medical, financial or security review.

## Build system

The repository follows:

**01 SHAPE → 02 SPECIFY → 03 DELEGATE → 04 PROVE → 05 SHIP → 06 WATCH**

See `.ai-build/` and `AGENTS.md`.
