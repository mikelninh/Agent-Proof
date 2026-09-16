# ASTRA Control Room — measured pilot, v0.1

**Goal: more independently accepted work per hour of human attention.**

An additive standard-library-only pilot for Agent-Proof. Existing application files are unchanged. This is a local control and measurement layer, not a Buzz fork or a deployed autonomous workforce.

## Evidence and boundaries

Local checks: 51 automated control/measurement/mocked-CLI tests passed; eight scripted scenarios behaved as expected (one reviewed artifact allowed, seven unsafe paths blocked); five deliberate source defects were caught by assertion failures; eleven browser checks passed with Playwright and system Chromium, including desktop/mobile layout and evidence export.

**Live agents: 0. Paired live tasks: 0. Live Buzz connection: unverified. Savings and revenue: unmeasured.** The full pre-existing Agent-Proof test suite was not run in this build environment. Scripted role clients are not independent AI agents. Mocked CLI tests are not live relay tests.

## Run

Python 3.10+, no pip install for this pilot. From the repository root:

```bash
python -m unittest discover -s pilots/astra -p "test_*.py" -v
python pilots/astra/mutation_check.py
python pilots/astra/control_room.py demo
python pilots/astra/control_room.py render
```

Open `pilots/astra/control-room.html`. Select **Artifact changes after approval** to inspect the stale-approval denial. The HTML is an interactive evidence snapshot, not a running agent console. Alternatively serve the directory:

```bash
python -m http.server 8765 --bind 127.0.0.1 --directory pilots/astra
```

Visit `http://127.0.0.1:8765/control-room.html`.

## Control workflow

`frozen spec → builder artifact → independent proof → independent review → human approval of exact artifact hash → local release candidate`

`ControlRoom.act(token, mission_id, action, **data)` is the integration interface. The caller role comes from its credential, not its claimed identity. Changing an artifact clears all old proof, review and approval. Failures, stale hashes, excess revisions, budget violations and terminal missions block progression. Denials exclude arbitrary input payloads.

The prover is a trusted test runner, not a model grading itself. Currently the gate accepts named boolean checks from that credential; real CI commands, immutable test manifests and signed test evidence remain integration work.

`release_candidate` is a LOCAL marker. No production deployment, merge, email-send or money-transfer executor exists. A chat reaction cannot approve anything. Keep the database/control process and human/prover credentials outside workers' writable environments. This local role scheme is not OS sandboxing.

The hash chain detects unrecomputed edits, not an attacker who can rewrite the database and recompute it. Anchor its final hash externally to detect truncation. Budget units are local accounting, not provider-enforced spending limits. Use isolated workers, provider caps and external process timeouts before granting real tools.

## Proposed success contract

Freeze 20 distinct, bounded engineering tasks from Agent-Proof's actual backlog after inspecting the code. Freeze independent acceptance criteria. Use small fixes, product changes, regression tests and handoff/recovery tasks; do not invent bugs just to fill a benchmark.

Compare a single-agent baseline with a small team on the SAME tasks. Both get the same model access, tools, repository snapshot, source material, maximum wall time and total resource caps. Randomise order; use clean worktrees; count coordinator/reviewer overhead; keep gold answers and graders outside worker environments.

| Measure | Exploratory pilot target |
|---|---|
| Human minutes per accepted task | At least 50% lower than baseline |
| Independently accepted work | At least 80%, with no lower acceptance rate than baseline |
| Cash cost per accepted task | No higher than baseline |
| Critical failures | Zero observed; any observed blocks |
| Sample | 20 complete, same-protocol, distinct task pairs |

North star: `accepted tasks / (ALL human minutes / 60)`.

Count prompting, reviewing, rescue, rework and allocated setup time, including failed work. Report one-time setup separately too. Cash cost includes all calls, compute, retries and failures. Use actual receipts, not token estimates labelled as invoices. Human time and elapsed time are different. Cash costs and an imputed value of founder time must remain separate. A costlier team may still be valuable; this deliberately strict first gate does not make that broader economic judgement.

Critical failures include unauthorised consequential action, fabricated evidence and sensitive-data escape. A critical failure cannot also be an accepted task.

### Score real runs

Input is a JSON array, one aggregate receipt per task/arm. Include all attempts, not only the best one:

```json
{
  "task_id": "real-task-001",
  "arm": "single",
  "spec_hash": "SHA256-of-frozen-task-and-acceptance",
  "protocol_hash": "SHA256-of-frozen-experiment-config",
  "artifact_hash": "SHA256-of-produced-or-null-artifact",
  "grader_ref": "immutable-independent-test-or-CI-report",
  "provenance": "live_measured",
  "accepted": false,
  "critical_failure": false,
  "cash_cost_eur": null,
  "human_minutes": null,
  "wall_seconds": null
}
```

This is a schema illustration, not observed data. Fill measurements from real records, include failed/timed-out tasks, and add a matching `team` receipt for each task.

```bash
python pilots/astra/control_room.py compare receipts.json --output comparison.json
```

Exit 0 means the exploratory targets are met; exit 2 means hold/block/insufficient evidence. Unknowns stay null. Fixtures never qualify. Duplicates and mismatched tasks/protocols are rejected. All failed work contributes to unit costs. Imported receipts are operator-supplied, not independently authenticated bills or outcomes.

Wilson intervals describe each arm's acceptance rate, not the paired causal effect. The gate uses point estimates; 20 pairs provide an early signal, not general or statistical proof. Repeat on unseen task batches before expanding autonomy.

## Buzz bridge: optional and one-way

Uses the documented command `buzz messages send --channel <uuid> --content -`. Configure a private test channel, a least-privilege bridge key via `BUZZ_PRIVATE_KEY`, and `BUZZ_RELAY_URL` locally. Remote relays require HTTPS. Never commit, print or paste the key into chat.

```bash
python pilots/astra/control_room.py buzz-publish \
  --channel YOUR-PRIVATE-CHANNEL-UUID \
  --input pilots/astra/evidence/demo.json \
  --confirm-publish
```

Only the final receipt's sequence, mission, role, action and hash are sent. Acknowledgement is labelled `CLI_ACKNOWLEDGED_NOT_READBACK_VERIFIED`. This does NOT orchestrate live agents or create separate signing identities for local roles: the bridge identity signs its publications.

Next test: read the event back using a second authorised identity; compare its ID/body; restart a worker and recover its task context; check denial for an unauthorised identity. None of those live tests have run here.

To attribute value to Buzz, subsequently compare the SAME team with and without Buzz on matched handoff/recovery tasks. Measure context recovery time, context-loss errors, duplicated work and coordination overhead. A one-way bridge alone cannot demonstrate those benefits; read/subscribe worker integration is still needed.

Upstream references inspected at search-resolved commit `6dfd145cde4bf0d45091de1cc5e6c7e3462d5703`:

- https://github.com/block/buzz
- https://github.com/block/buzz/blob/6dfd145cde4bf0d45091de1cc5e6c7e3462d5703/crates/buzz-cli/README.md
- https://github.com/block/buzz/blob/6dfd145cde4bf0d45091de1cc5e6c7e3462d5703/VISION.md

The upstream vision marks approval execution as unfinished. This pilot does not rely on that execution path. Channel membership is not a permission boundary for a worker's shell or external API tokens.

## Improvement loop and next proof

`real failure → reproduce → independent regression test → change ONE policy/model/tool → paired rerun → human decision → observe escaped defects`

Keep held-out answers separate. Never lower thresholds or rewrite ground truth to manufacture a pass. The mutation checks demonstrate regression sensitivity, not autonomous self-improvement.

Next vertical slice: one private Buzz relay, one builder, an independent verifier and a separate reviewer complete one narrow real task as an UNMERGED PR. Record human attention and actual expenditure. Then fill the paired scorecard, repeat on unseen tasks, and inspect escaped defects for seven days.

Business success is an external customer paying for an accepted outcome and returning. Revenue, repeat use and contribution margin must be observed, not extrapolated from synthetic examples.
