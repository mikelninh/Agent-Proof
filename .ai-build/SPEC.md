# SPEC — Agent Proof v0.3

## User problem
Teams can make impressive AI demos but struggle to prove reliability, failure risk and ROI before deployment — and after a prompt/model/tool change they often cannot tell whether the new version is actually safer.

## v0.3 job to be done
Given a scenario pack and one or more agent versions, run the same cases repeatedly and produce deployment evidence: success, critical failures, latency, cost, ROI, case-level replay, and a paired baseline-vs-candidate release decision.

## Core flows
1. Run bundled 100-case Fraud Analyst Arena against the offline baseline.
2. Run the stronger offline candidate and compare it with the baseline without an API key.
3. Connect an OpenAI-compatible model or any HTTP agent via webhook.
4. Upload a custom JSON eval pack or build one from a historical CSV.
5. Inspect failed cases and critical failures.
6. Compare two runs case-by-case: fixes, regressions, new critical failures, cost, latency and savings deltas.
7. Export run and regression reports.
8. Use CLI exit codes to block CI when a run or candidate is unsafe.

## Release recommendation
- **Reject** if candidate deployment gate blocks, it introduces a new critical failure, or paired success materially regresses.
- **Promote** when quality improves or remains non-inferior while cost/latency improves, with no new critical failure.
- **Hold** when evidence is not clearly better.

## Non-goals
No production action execution. No secret management. No claims that synthetic benchmarks equal production performance. Statistical significance is evidence, not a substitute for domain-owner review.
