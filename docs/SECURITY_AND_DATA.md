# Security and data handling notes

Agent Proof is an evaluation tool. Real deployment requires a data-handling design appropriate to the customer's risk and regulatory environment.

## Current product behaviour

- The bundled Support Ops and Fraud packs are synthetic.
- In Pilot Mode, the **raw CSV file is parsed in the browser**. The raw file itself is not uploaded as a file.
- When the user creates an evaluation pack, only the columns they selected as agent-visible plus the chosen hidden ground-truth values are sent to the Agent Proof backend for the evaluation pack.
- Hidden ground truth is stored separately from `case.input` and is never included in the evaluated agent request.
- OpenAI-compatible API keys are used for the current request and removed before a run record is persisted.
- Webhook evaluations send the task instruction, case ID and agent-visible `case.input` to the configured webhook endpoint.
- The default local installation stores packs and runs in SQLite.
- On serverless hosting, the bundled SQLite store should be treated as ephemeral. Production multi-user hosting should use managed persistent storage with authentication and access controls.

## PII warning

The browser importer flags likely personal-data column names, but this is a heuristic, **not a compliance guarantee or redaction system**. The safest first pilot is synthetic or properly anonymised data.

## Production hardening before regulated data

Before using sensitive or regulated customer data, add or validate:

- customer-specific data-processing agreement and legal basis
- authentication, tenant isolation and RBAC
- managed encrypted database and backups
- secrets manager rather than browser-entered shared credentials
- retention/deletion controls
- structured audit logs
- network and webhook allow-lists where appropriate
- regional/data-residency requirements
- automated PII detection/redaction plus domain review
- incident response and access-review procedures

## Evaluation integrity invariant

If hidden ground truth is accidentally exposed to an evaluated agent, **all affected evidence is invalid**. Stop the evaluation, fix the pack, and rerun from scratch.
