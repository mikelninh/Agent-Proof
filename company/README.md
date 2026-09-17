# ASTRA Company — actual delivery operations

One business focus: Agent Proof's Agent Readiness Evaluation. One durable cloud queue, four bounded job types, a founder-only approval inbox. The first runtime is intentionally on demand, not a claim of an unattended autonomous company.

## Who does what

- Sales produces an offer and outreach draft. It has no send or pricing authority.
- Delivery runs the existing 180-case synthetic Support Ops evaluation across the three bundled agents, returning a report and case evidence.
- Operations prepares focused priorities and founder decisions.
- Review is a separate model call, not independent human assurance. Michael accepts or rejects the exact evidence hash.

## How to work

Open the private Founder Desk delivered in chat. Assign work, open a work session, and use **Re-run all jobs** on an ASTRA Company GitHub Actions run. Up to four queued jobs are claimed, executed and returned to the cloud review inbox. An empty queue performs no generation, though this initial workflow still installs the runtime. Pausing blocks new claims, not an in-flight completion. Failed or rejected jobs require a founder-requested retry and stop after three attempts.

The `astra/company-operations` branch is the only trusted worker identity. Main remains unchanged. Do not move this workflow to another branch without deliberately updating the verified identity policy.

## Runtime and provenance

GitHub Models returned HTTP 410 in the first run; GitHub's official changelog confirms retirement on 2026-07-30. The supported entrypoint is now `python company/run_local.py --max-jobs 4`. It injects a local Ollama adapter into the same bounded worker. The legacy hosted adapter in worker.py is not selected by this entrypoint.

Ollama v0.34.1 is pinned with its official release SHA-256. Qwen3.5:2b runs on the ephemeral CI runner with no paid hosted inference key. Each run records the resolved model digest and reported token counts. The small model is for initial drafts, not independent expert advice, complex production coding or safety certification. Compute/hosting cost remains unmeasured, not free or zero. No billing plan, API key or paid service is provisioned by the workflow.

## Authority

The Supabase edge API verifies signed GitHub OIDC tokens against the exact repository, numeric repository ID, workflow, branch, issuer, audience and expiry. A worker may only claim, finish or fail a job. The founder credential may create, inspect, pause, retry and make version-bound decisions. Worker results are hashed by the server. All new tables have RLS enabled and no anon/authenticated grants. Only the service-role API calls the SECURITY INVOKER database command.

No email send, payment, invoice, purchase, deployment or merge operation exists. Approving an artifact accepts that version and does not execute any external action.

## Truth boundary

This is not a Buzz relay. It is a working first company process on existing GitHub and Supabase infrastructure. Buzz can be connected later without blocking delivery today. Synthetic delivery reports do not prove customer performance, customer acceptance, revenue or human-time savings. There is no automatic demand generation or customer acquisition.

Keep the private Founder Desk file private: it contains your workspace capability key. The public index.html must contain only a login placeholder, never a founder token. Rotate the key by changing ASTRA_FOUNDER_TOKEN_HASH in the edge environment and issuing a new private access file.
