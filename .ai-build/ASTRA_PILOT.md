# ASTRA pilot / Build OS

## 01 SHAPE
Problem: multi-agent orchestration can add complexity without more verified work. Decision: test a small gate and an honest paired scorecard before expanding a workforce. Success is accepted work per hour of human attention, subject to quality/safety/cost constraints.

## 02 SPECIFY
Contract and limitations: `pilots/astra/README.md`. Frozen specification and artifact hashes bind proof, review and human approval. No consequential production executor. No live performance claim from fixtures.

## 03 DELEGATE
Roles: coordinator, builder, trusted prover, reviewer, human. Role credentials are separate. The implemented pilot uses scripted clients; actual independent workers and isolated compute remain unwired. Human and prover credentials must remain outside worker environments.

## 04 PROVE
Run `python -m unittest discover -s pilots/astra -p "test_*.py" -v`, then `python pilots/astra/mutation_check.py`. Results: 51 checks passed; all five intentional defects caused assertion failures. Replay: one allowed path, seven denied paths. Local browser checks: eleven passed. Full existing Agent-Proof suite not run in the local build environment.

## 05 SHIP
Additive pilot under `pilots/astra`, with downloadable source and an interactive HTML evidence snapshot. Proposed as a reviewable change, not a production release. No merge/deploy/payment capabilities. Source and fixtures stay distinct from live receipts.

## 06 WATCH
Not yet deployed, so production monitoring is not claimed. Next: one live unmerged PR, then 20 real task pairs, then unseen tasks and a seven-day escaped-defect follow-up. Failures become independent regression tests before candidate changes. No unattended loop is running.
