# ASTRA // Control Room — evidence pilot

**More accepted work per hour of Michael's attention. Not more agent activity.**

A local-first laboratory inside Agent-Proof, not a new platform or a deployed autonomous workforce.

## Run

Python 3.11+, standard library only for the core lab.

```bash
cd labs/astra-control-room
mkdir -p evidence
python -m unittest test_astra -v > evidence/unit-tests.txt 2>&1
python astra.py demo --out evidence
python render.py
```

Open `control-room.html`. It is an evidence viewer, not a live agent console. Load another `report.json` to inspect a later local run. The recorded local build passed 61 unit/contract tests and the repaired fixture passed 12/12 checks. These are not live-agent performance results.

The demo creates a deliberately broken release gate, runs its unchanged tests in a separate process, applies a **prewritten patch**, reruns the tests, saves the diff/receipts, and stops at `awaiting_approval`. Real filesystem/process execution; no LLM-generated repair, no live Buzz mission, no business evidence. No production executor exists. The demo uses an in-memory signing secret; its pending approval is not actionable after the process exits. Approval tests explicitly simulate a human and are not Michael's consent to any real release.

## Existing Agent-Proof integration

```bash
agentproof run support-ops-v1 --provider demo_baseline --output baseline.json
agentproof run support-ops-v1 --provider demo_candidate --output candidate.json
python astra.py agentproof-review baseline.json candidate.json
```

The adapter validates nonempty unique cases, identical input/ground-truth populations, aggregate metrics against individual grades, and critical failures. It emits `READY_FOR_HUMAN_REVIEW` or `BLOCK`, never a production deployment. It consumes the inspected Agent-Proof RunRecord schema; it does **not** independently re-grade the report. Only use exports from a trusted evaluator, not worker-authored grades. Demo providers remain synthetic. Local adapter tests are schema/consistency tests; the complete upstream Agent-Proof runner was not executed in this build environment.

## Real Buzz relay connection

Install/configure Buzz using upstream instructions. Keep `BUZZ_PRIVATE_KEY` and `BUZZ_RELAY_URL` in the operator environment, never in this repo.

```bash
buzz channels list
python astra.py buzz-publish --channel YOUR-CHANNEL-UUID --report evidence/report.json
buzz messages get --channel YOUR-CHANNEL-UUID --limit 20
```

Choose an authorised private test channel. The adapter sends a small evidence summary/digest, not source code, approval keys or customer data. A CLI acknowledgement is not verified read-back: confirm the mission ID and report digest in the retrieved event. On ambiguous write/timeout, inspect before retrying; no automatic retries are performed. v0.1 has no inbound dispatch/approval listener. Buzz is not the production approval authority.

**Live Buzz integration is untested.** The build environment has no Buzz/Docker/Rust runtime and its shell cannot resolve GitHub. Repository inspection/writes use the authorised connector. No paid inference, customer data or external relay posts were executed.

## Success experiment

Preregister **10 representative, bounded tasks from the actual backlog** before running any arm. Do not count the already-known fixture or these unit tests. Cover bug fixes, test improvements, a UI change and failure recovery. Freeze IDs, starting commits, acceptance tests, model versions, spend caps and allowed files/tools. Keep the evaluator/hidden tests outside workers' write access. Reserve **20 additional unseen tasks** for replication.

| Arm | Configuration | Question |
|---|---|---|
| baseline | Michael's current AI-assisted workflow | Better than what we actually do? |
| single | One coding agent with the same tools/tests and task caps | Better than the simpler alternative? |
| buzz | Builder + independent verifier coordinated through Buzz | Does the coordinated workflow add value? |

Use the same eligible models and total task budget across agent arms. Randomise arm order per task; reset worktrees/context; do not share solutions; blind acceptance review where feasible. Record order and acknowledge human carryover learning. This estimates the **whole workflow's** value, not Buzz in isolation. A later same-team-with/without-Buzz comparison would isolate the transport.

### Chosen pilot thresholds — not industry benchmarks

| Metric | Gate |
|---|---|
| Human attention | At least 30% less total active time than current workflow |
| Team overhead | At least 15% less human time than the single-agent arm |
| Accepted work | At least 8/10 and no fewer than either comparison arm |
| Critical / unauthorised actions | Zero observed; any one stops expansion |
| Evidence coverage | 100% of attempted tasks, including failures and aborts |
| Fully loaded cost per accepted task | No higher than single agent |
| Post-review quality | Frozen checks pass and a 24-hour watch passes |

A green 10-task pilot means `PROMISING_REPLICATE`, not proof of an autonomous company. Repeat unchanged on the unseen set; inspect paired fixes/regressions, distributions and failure segments. Zero observed failures in a small selected test set does not establish zero production risk. **If one agent is as good or better, keep one agent.**

### Measurement

One aggregate record per preregistered task/arm, including all retries. Failures and aborts remain in the denominator. Human time includes active setup, clarification, supervision, review, rework and allocated maintenance; pause during unattended compute and record wall time separately. Rework is already part of human time, not an additional cost to count twice. Allocate setup/hosting costs consistently across all attempted tasks.

```text
accepted tasks per human hour = accepted tasks / (human minutes / 60)

cost per accepted task =
  (ALL API spend + compute/hosting allocation +
   ALL human minutes / 60 × explicitly assumed hourly value)
  / accepted tasks
```

Use billing/usage receipts, not an agent estimate. Reservations in this code gate estimated dispatch spend; they are **not provider-enforced billing limits**. Unknown values stay null, not zero. Cash collected is separate from time-value estimates or annualised savings.

```bash
python astra.py score pilot.json
```

Enter actual observations only. Exit 0 means `PROMISING_REPLICATE`; other verdicts exit 2. Empty/incomplete live observations correctly return `NOT_MEASURED`/`INCOMPLETE`.

## Next real mission

One bounded Agent-Proof backlog task from a pinned commit: a worker makes a branch patch, an isolated verifier runs frozen checks, both post receipts to a private Buzz channel, Michael accepts/rejects the exact artifact. Record active minutes and actual spend in all three comparison arms. No production, customer data or payment tools.

After the technical and attention gates pass: one external user repeatedly chooses the result; then one actually paid pilot with positive contribution margin. Money in the account, not an ROI prediction.

## Trust boundaries

The SQLite file and verifier process are trusted. Signer/verifier are in one class for this lab, **not production separation of duties**. Same-user filesystem/process access can bypass it. Before unattended work, separate worker OS/container credentials and deploy a separately authorised approval service. `submit_verified` is a trusted-verifier API, never an agent-facing endpoint.

Approval binds artifact/proof, expires after 15 minutes and is one-use. `approved_local` deploys nothing. The local hash chain is not Nostr-signed; externally retain a trusted head to detect edits, and do not claim prevention of whole-log rewrites.

A command timeout is not a sandbox. POSIX timeout kills the process group; Windows only the direct child. Saved output is capped at 64 KiB, not temporary disk growth. Execution needs OS-level resource/disk/network limits. Stop prevents new dispatch, not an already-running remote job. Live deployment still needs substrate kill controls, provider budgets, backups, idempotent jobs and reconnect/restart tests.

No autonomous merge, production deployment, customer messages, payments, recursive prompt promotion or customer PII.

## Source review / Build OS

Inspected 2026-09-17: Agent-Proof README, AGENTS.md, .ai-build/SPEC.md, .ai-build/AUTONOMY.md and agentproof/models.py; Buzz CLI README, ARCHITECTURE.md and VISION.md. Buzz documents incomplete approval executor wiring; this lab does not depend on it.

https://github.com/block/buzz/blob/main/crates/buzz-cli/README.md
https://github.com/block/buzz/blob/main/ARCHITECTURE.md

SHAPE → SPECIFY → DELEGATE → PROVE → SHIP → WATCH. Keep this change on a review branch and do not change existing application routes. An initial implementation bug allowed stale JSON state to shadow the authoritative SQLite state column; fixed with a dedicated regression test. Full upstream regression and live integration are not inferred from local lab tests.
