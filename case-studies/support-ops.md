# Flagship case study — Support Ops

Agent Proof ships with a deterministic **180-case Support Ops benchmark**. It is not presented as real customer data; it is a transparent, inspectable demonstration of the product workflow before a buyer supplies anonymised historical cases.

## Workflow covered

Cases span duplicate charges, damaged deliveries, cancellations, late deliveries, technical support, wrong-item claims, payment disputes and account-takeover signals. Ground truth comes from an explicit reference policy in code, not an LLM-generated label.

## Current deterministic result

| Agent | Success | Critical failures | Annualized failure exposure* | Gate |
|---|---:|---:|---:|---|
| Support Agent v1 · baseline | 83.3% | 0.0% | €3,549,333 | BLOCK |
| Support Agent v2 · candidate | 99.4% | 0.0% | €11,667 | PASS |
| Support Agent v3 · aggressive automation | 82.2% | 2.2% | €4,616,667 | BLOCK |

Candidate v2 fixes **30** baseline failures while introducing **1** regression. The paired exact McNemar p-value is approximately **3.0e-8**, and Agent Proof recommends **PROMOTE** for v2. Aggressive v3 introduces critical failures and is **REJECTED**.

\* Failure exposure is a scenario-weighted decision-support estimate based on configured miss costs and annual volume. It is not an accounting forecast.

## Why this case study matters

The point is not that “v2 is smarter.” The useful behaviour is that Agent Proof can explain *why* v2 is safer, identify the exact regression it introduces, expose the risk of v3 despite its automation goal, show weak coverage segments, and turn the result into a release gate.

## Reproduce it

```bash
pip install -e '.[dev]'
agentproof gate support-ops-v1 --provider demo_candidate --min-success .95 --max-critical 0 --github-summary
```

Or launch the web app and click **Run flagship Support Ops study**.
