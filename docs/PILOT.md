# Agent Readiness Evaluation — pilot package

Agent Proof is meant to answer a deployment question, not merely produce a benchmark score:

> **Should this AI workflow be allowed into production, and what evidence supports that decision?**

## Suggested first pilot

**Duration:** 5–10 working days  
**Commercial range:** €5k–€15k depending on data preparation, integrations and domain review  
**Input:** 50–500 representative, appropriately anonymised historical cases + the current agent endpoint  
**Output:** a reusable evaluation pack, deployment report, regression comparison and release gate.

## What the customer provides

1. Representative historical or synthetic cases.
2. The outcome/decision considered ground truth for each case.
3. A domain owner who can confirm ambiguous labels and dangerous failure modes.
4. Human handling time/cost and approximate annual workflow volume.
5. An agent endpoint or OpenAI-compatible model endpoint.
6. A list of actions that must never be taken automatically.

Do **not** send raw personal, medical, payment-card or other regulated data unless an appropriate data-processing setup has been agreed separately. The default pilot should use synthetic or properly anonymised data.

## What Agent Proof delivers

- data/label quality review and hidden-ground-truth eval pack
- critical-failure taxonomy agreed with the domain owner
- baseline evaluation and candidate evaluation on identical cases
- case-level traces for every miss
- paired fixes/regressions and exact McNemar comparison
- coverage map showing weak segments
- cost, labour savings and scenario-weighted failure-exposure estimates
- executive **PASS / BLOCK / PROMOTE / REJECT** recommendation
- reproducible evidence bundle
- optional GitHub Actions gate so future agent changes cannot silently regress

## Pilot success criteria

A pilot is successful when the customer can make a better deployment decision than they could from a demo alone. At minimum we want to answer:

- Is the candidate above the agreed minimum success rate?
- Are there any critical failures?
- Which exact cases got better or worse?
- Are failures concentrated in a particular segment?
- Does the candidate improve enough to justify promotion?
- What must be fixed before the next production attempt?

## Pilot workflow

**Day 1 — Shape:** define workflow, decisions, critical failures, success gate and economics.  
**Day 2 — Pack:** map/anonymise cases, hold out truth, validate distributions.  
**Day 3 — Baseline:** run current system, inspect misses with domain owner.  
**Day 4 — Candidate:** test alternative prompt/model/tools on the same cases.  
**Day 5 — Decision:** deliver regression evidence, risk/ROI report and next-release gate.

For larger pilots, repeat the evaluation after fixes and add approved adversarial cases around the failure clusters.

## The sales sentence

> Give us 100 representative cases and your agent endpoint. We will show you exactly where it fails, whether the new version is actually safer, and whether it deserves production access.
