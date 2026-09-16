# ASTRA Control Room — bounded pilot v0.1

## 01 SHAPE — the decision
Does a coordinated agent team deliver more **independently accepted work per hour of Michael's attention**, at equal or lower total cost and no quality/safety regression, than one well-equipped agent? Separately: does Buzz add value over the same team without Buzz?

No customer-demand or commercial validation is claimed. This is an internal infrastructure experiment. No new commercial product goes past the existing SHAPE demand gate on the strength of these fixture tests.

## 02 SPECIFY — what exists
- A standard-library Python mission controller: brief → builder → verifier → reviewer → human review queue.
- Operator-configured command adapters with JSON stdin/stdout. No shell interpolation; minimal inherited environment; per-worker and whole-mission deadlines; maximum three attempts (default two).
- Distinct role IDs, artifact hashes, frozen-file checks, independent verifier receipts, exact-artifact reviewer receipts, and local hash-chained events.
- A Buzz CLI **evidence publisher**, verified against the upstream CLI documentation at commit `6dfd145cde4bf0d45091de1cc5e6c7e3462d5703`. It is not yet a Buzz job dispatcher or ACP harness. One publisher signs the receipt; role labels in that receipt are not separate authenticated agent identities.
- A three-arm comparison scorer that refuses to declare a win with fixture-only results, incomplete scheduled observations, missing costs/timings, unmatched task/model/evaluator/budget versions, or unverified Buzz round trips.
- A generated, self-contained HTML evidence report. No fake live controls.

## 03 DELEGATE — trust and scope
The included workers are **deterministic fixture programs, not live LLM agents**. Their task is a tiny integer-money conversion; it is a controller smoke test, not a representative business benchmark.

Configured programs run with the host user's OS privileges. Temporary working directories, separate subprocesses, role IDs and frozen-file checks are **not a security sandbox**. A malicious worker could read or alter files beyond its intended directory. Use externally sandboxed workers/containers with read-only evaluator mounts, scoped credentials, filesystem/network limits and disk quotas before running untrusted generated code. Agent output is stored as JSON and is not executed by this controller. Only explicitly configured operator commands execute.

On POSIX, timed-out worker process groups are killed. On Windows, only the direct child is killed; use an external worker host with process-tree supervision. Output reading is capped at 1 MB; temporary output files require a host disk quota against malicious output floods. Provider credentials are not inherited automatically; a trusted external worker service needs its own secret management. There is no monetary enforcement at a model provider in this version: attempt/time caps are not guarantees about billed cost.

The local hash chain detects changed records relative to the saved checkpoint; it is not authenticated, immutable storage and can be recomputed by a writer controlling the directory. Sign/checkpoint receipts in trusted external storage for adversarial audit integrity. The operator's configuration, verifier, imported telemetry, and worker environment are trusted. Agents must never supply their own acceptance, time or cost telemetry as authoritative evidence.

## 04 PROVE — deterministic contracts
The included test suite exercises successful work, a repair loop, false success claims, critical failure, timeouts, malformed outputs, stale evidence, zero-check verification, rejected review, identity separation, evaluator modification, receipt/result tampering, secret environment filtering, ambiguous publication, and measurement edge cases.

A builder's `claims_passed` or `claimed_revenue_eur` field is ignored. A verifier must return a strictly boolean pass, positive integer check count, no critical failure, and the exact artifact hash. A reviewer must separately approve the same hash. No successful result ever means "shipped".

### Precommit the live experiment
Freeze 20 distinct representative tasks from one repository **before** seeing outputs: a mixture of bug repair, input-edge handling, regression-test work and small user-visible improvements. These are task categories, not a claim that particular repo bugs have been found. Lock initial commit, acceptance/evaluator hash, difficulty category, identical tool access, model/version policy, and total per-task budget. Keep hidden tests inaccessible to builders; do not alter the evaluator to rescue a candidate.

Run each task three times per arm, in randomised/interleaved order and fresh independent workspaces:

| Arm | Treatment | Question |
|---|---|---|
| single | One agent with the same available tools and total budget; same independent acceptance grading | What is the baseline? |
| team_local | Builder + reviewer coordinated without Buzz; same independent grader | Does division of work help? |
| team_buzz | The same team with Buzz-mediated coordination and verified write/read-back | Does Buzz add incremental value? |

This is **180 scheduled observations**, not 180 independent tasks. Repetitions are clustered within 20 tasks. Do not share solutions across arms. Log every assigned row, including timeout, crash, cancellation and budget exhaustion; those remain failures in the denominator. Human-involvement measurements include setup, prompting, clarification, supervision, approvals and repair. Report fixed setup/maintenance separately and allocate it consistently in all-in cost; do not hide it.

The current pilot implements the scorer, not automatic live three-arm scheduling, sandbox provisioning, provider metering, human timers, or Buzz round-trip verification. The operator must collect and validate that telemetry before import. `live_evidence=true` is an operator assertion, not something the program can prove by inspecting a boolean.

### Metrics and proposed advancement gates
- North star: **verified accepted tasks / total human hours**, including unsuccessful work's human time. Zero or absent human time is not infinite productivity; it is unknown/not comparable.
- Quality: independently accepted tasks / all scheduled tasks; target ≥90% with no deterioration versus baseline and no paired baseline-pass → candidate-fail regressions in this initial strict screen.
- Safety: **zero observed critical failures**; any observed critical failure blocks advancement. This is an observed test criterion, not a zero-risk guarantee.
- Effort: ≥30% reduction in total human minutes on the same cohort (equivalent to ≥1.43× throughput at identical accepted output).
- Economics: all-in cost / accepted task ≤ baseline. Costs include all attempts, reviewer/model usage, worker compute and consistently valued human effort, including failures. Missing cost remains null, never free. Fix the human hourly-rate assumption before comparison; record cash cost separately.
- Wall time: log end-to-end elapsed seconds including retries and queue wait; compare median plus the tail when live samples exist. The v0.1 scorer emits summed and median elapsed time, not a tail estimator.
- Buzz-specific: compare `team_local` with `team_buzz`, not only against the single agent. Separately test restart recovery, message duplication, lost acknowledgements and evidence retrieval. Do not retain Buzz just because a team without it already wins.

The scorer's `PILOT_PASS` applies only to `single` versus `team_buzz` on these precommitted thresholds. Consult the separate `team_local_vs_team_buzz` result before crediting Buzz with the improvement. A win on either screen is not statistical proof, production authorisation, or proof of revenue. Test the frozen candidate on a fresh held-out task cohort; record uncertainty by task, not by treating repeated runs as independent samples.

## 05 SHIP — explicit exclusions
There is **no merge, deployment, email, payment, or credential-management operation** in this pilot. `awaiting_human` is a review queue state, not an approval and not a release. Existing GitHub branch protection and an independently controlled human release process must enforce real release permissions. Do not rely on unfinished Buzz workflow approval execution.

## 06 WATCH — improvement without moving the goalposts
Failure → root-cause hypothesis → one proposed change → rerun frozen development cases → evaluate fresh holdout → human promotion or rejection. Version prompts, models, tool access, tests and budget policies. Never let the builder weaken the acceptance test. Track regressions and cost, not just fixes. No self-modifying policy loop or unsupervised agent spawning is enabled.

## Runbook
From the repository root (Python 3.11+):

```bash
python -m agentproof.controlroom doctor
python -m pytest -q tests/test_controlroom.py
python -m agentproof.controlroom demo --output evidence/astra-run-001
python -m agentproof.controlroom verify evidence/astra-run-001/repair
```

Open `evidence/astra-run-001/index.html`. Output directories must be new; reuse is deliberately rejected so reruns do not overwrite evidence or repeat a mission silently.

For your own operator-controlled worker wrappers, make a mission JSON with `id`, `brief`, `input`, `execution_kind: "operator_commands"`, distinct `builder`/`verifier`/`reviewer` objects (`id` and `argv`), optional `frozen_files`, `max_attempts`, `worker_timeout_seconds`, and `mission_timeout_seconds`. Use absolute paths to wrapper files; each worker starts in the run directory. Keep secrets outside the JSON. The fixture module demonstrates the request/response contract, but must not be presented as live intelligence.

```bash
python -m agentproof.controlroom run /absolute/path/mission.json --output evidence/real-run-001
```

### Buzz connection (not exercised in the local fixture run)
Run your own pinned and reviewed Buzz relay/CLI following the upstream production Compose guide. Configure `BUZZ_PRIVATE_KEY` through the worker host's secret manager; never put keys in Git or chat. Create a private channel through Buzz and restrict publisher membership. Then explicitly publish a non-sensitive receipt:

```bash
python -m agentproof.controlroom publish-buzz evidence/astra-run-001/repair \
  --relay https://YOUR-RELAY --channel YOUR-CHANNEL-UUID
```

The code invokes the documented command `buzz messages send --channel UUID --content -` with the body on stdin. `cli_acknowledged` means the CLI returned valid JSON and exit zero: **not independently verified relay delivery**. Use the real CLI to read the channel and match `receipt_id` to establish the round trip. A failed/ambiguous call leaves `delivery_unknown`; no automatic retry is made. Reconcile the recorded receipt ID on the relay before any manual recovery. Do not delete that publication-intent file and blindly retry. Raw CLI output and secrets are not persisted.

For trusted live telemetry, the comparison input is `{planned_tasks: [...], repetitions: 3, records: [...]}`. Every scheduled row needs `task_id`, zero-based `repetition`, `arm`, boolean `accepted`, `critical_failure`, `live_evidence`, operator-verified `evidence_ref`, matched `input_hash`, `evaluator_hash`, `model_policy_hash`, `budget_policy_hash`, numeric/nonnegative `human_minutes`, `total_cost_eur`, `elapsed_seconds`, and `buzz_roundtrip_verified: true` on the Buzz arm. Missing measurements may be null but force HOLD.

```bash
python -m agentproof.controlroom_metrics /absolute/path/live-telemetry.json
```

Exit code zero is `PILOT_PASS`; HOLD/BLOCK exits one. Fixture tests can validate this scoring logic but are never live productivity evidence.

## Source references
- https://github.com/block/buzz/blob/6dfd145cde4bf0d45091de1cc5e6c7e3462d5703/crates/buzz-cli/README.md
- https://github.com/block/buzz/blob/6dfd145cde4bf0d45091de1cc5e6c7e3462d5703/README.md
- https://github.com/block/buzz/blob/6dfd145cde4bf0d45091de1cc5e6c7e3462d5703/VISION_AGENT.md

## Current evidence boundary
The local environment had Python and pytest but no Buzz CLI, Docker, Rust, relay configuration or Buzz key. Local fixture execution is verified; live Buzz operation, real-agent quality, cost savings, security isolation, recovery under relay outages, and revenue are **not yet demonstrated**. These are unfinished deliverables, not PASS items.
