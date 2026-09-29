# Agent Trust Audit v1

Agent Proof already measures whether an agent is accurate, safe enough for a stated deployment gate, economically worthwhile, and better or worse than a prior version.

The **Agent Trust Audit** turns that engine into a bounded commercial offer.

## Promise

> Bring one production or pre-production agent plus representative cases. We return reproducible evidence of where it works, where it fails, what could cause critical harm, and what should be fixed before authority widens.

This is an engineering assurance service, not a certification and not a legal compliance opinion.

## Starter scope

- one agent or workflow;
- 30–100 representative cases;
- current version plus one candidate when available;
- deterministic ground truth where possible;
- customer/domain-owner confirmation of critical failure rules;
- one evidence report and remediation review.

Suggested starting range: **€2,000–€10,000**, depending on case preparation, integrations and domain complexity. Price is a commercial hypothesis until real deals validate it.

## Audit-readiness contract

A pack may call itself **audit-ready** only when:

1. it has at least 30 cases; and
2. its case tags explicitly cover all five starter dimensions:
   - `risk:correctness`
   - `risk:boundary`
   - `risk:injection`
   - `risk:recovery`
   - `risk:approval`

Run:

```bash
agentproof audit-check path/to/pack.json
```

The command exits non-zero when the pack is not ready.

This does **not** prove those cases are representative. A domain owner still has to validate the scenario set, ground truth, failure costs and deployment assumptions.

## Delivery

1. **Scope** — define workflow, authority, sensitive effects and business outcome.
2. **Build evidence pack** — representative cases, hidden truth, critical mismatches, risk tags.
3. **Run baseline** — quality, critical failure, cost, latency and failure exposure.
4. **Attack boundaries** — adversarial drafts become test cases only after human confirmation.
5. **Compare candidate** — fixes, regressions, new critical failures and paired evidence.
6. **Recommend** — promote, hold or reject against the agreed gate.
7. **Remediate** — convert failures into concrete engineering changes and regression cases.

## What the buyer receives

- audit-ready scenario pack;
- run evidence;
- critical-failure list;
- weak-segment coverage map;
- cost / latency / failure-exposure summary;
- baseline-vs-candidate comparison when available;
- remediation backlog tied to individual cases;
- explicit limitations and untested surfaces.

## Non-negotiables

- Hidden truth never enters agent-visible input.
- Generated adversarial labels are not treated as truth without human confirmation.
- Critical failures are not averaged away.
- API keys are never persisted.
- A synthetic pack is never presented as production evidence.
- Audit-ready means the **pack has minimum structural coverage**, not that the agent is safe.
