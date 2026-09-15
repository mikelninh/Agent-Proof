# Evals

## Product invariant
Hidden ground truth is never sent to the evaluated agent.

## Flagship acceptance
- Support candidate v2 success >= 95%
- Support candidate v2 critical failure rate = 0
- Support aggressive v3 has >= 1 critical failure and is blocked
- Candidate comparison vs baseline recommends PROMOTE

## Regression tests
`pytest` covers grading, ROI/risk math, CSV holdout, support case study gates, paired statistics, coverage and adversarial draft generation.

## Evidence
Run `python scripts/run_case_study.py` to write reproducible JSON evidence under `evidence/support-case-study/`.
