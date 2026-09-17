# Agent-Proof Design Partner Pilot

## One sentence

Give us 50–500 representative historical cases plus access to your current AI workflow. We measure where it works, where it fails, what the failures cost, and whether a candidate version is actually safer to deploy.

## Best fit

Teams already using or piloting an AI workflow such as:

- customer support or ticket triage
- voice agents
- document processing
- internal copilots
- operational automation
- agentic workflows that take structured actions

This is not a generic AI strategy workshop. It is a measured before/after evaluation of a real workflow.

## What we need

1. **50–500 representative cases** — synthetic or appropriately anonymised.
2. **Expected outcome / ground truth** for each case, validated by a domain owner.
3. **Current agent or workflow endpoint** — webhook or OpenAI-compatible API.
4. **Critical failure rules** — mistakes that must never be automated.
5. **Optional business weights** — approximate cost, time or risk of each failure type.

Use `examples/design-partner-intake.csv` as the minimal data shape.

## What we run

### 1. Baseline

Run the current workflow across the fixed evaluation pack.

Measure:

- success rate
- critical failures
- weak segments
- latency
- cost per case
- escalation / abstention rate when available
- estimated failure exposure when business weights are provided

### 2. Failure analysis

For every miss we preserve:

`input -> output -> expected result -> grader evidence -> segment tags`

We identify recurring failure modes rather than averaging them away.

### 3. Candidate improvement

Test a changed prompt, model, tool policy, routing rule, or workflow version against the **same cases**.

### 4. Paired comparison

Report:

- fixes
- regressions
- new critical failures
- unchanged failures
- statistical comparison where applicable
- cost / latency delta

### 5. Deployment gate

The domain owner agrees the release policy before the candidate is judged.

Example gate:

- success >= 95%
- critical failures = 0
- no regression in protected segments
- p95 latency <= agreed limit
- unit cost <= agreed limit

Agent-Proof returns **PASS / BLOCK** from those rules.

## Deliverables

The pilot ends with four things:

1. **Baseline report** — what is happening today.
2. **Failure map** — exact cases and segments that break.
3. **Candidate comparison** — what improved and what regressed.
4. **Release recommendation** — PASS / BLOCK against pre-agreed gates.

The customer keeps the reusable evaluation pack and regression history.

## Pilot success criteria

The first design-partner pilot is successful if we can answer, with evidence:

- Is the current AI workflow good enough for the intended scope?
- Which cases should still go to a human?
- Did the candidate version improve outcomes without introducing dangerous regressions?
- What does a correct automated outcome cost compared with the current baseline?
- Can the same evaluation run again before the next release?

## 30-minute kickoff

We only need answers to these questions:

1. What decision or action does the AI make?
2. What does a correct answer look like?
3. What is the most expensive or dangerous mistake?
4. Which cases must never be automated?
5. Where can we obtain 50–500 representative examples?
6. How do we call the current workflow?
7. What would make you comfortable shipping a new version?

## Data handling

Use synthetic or appropriately anonymised data for the pilot. A domain owner must validate ground truth, critical-failure definitions and business-cost assumptions. Agent-Proof is evaluation infrastructure, not a substitute for legal, compliance, medical, financial or security review.

## Commercial shape

For the first design partner, optimise for a real measured case study rather than maximum contract value.

A simple structure:

- fixed-scope pilot
- one workflow
- one baseline + one candidate
- 50–500 cases
- final evidence report + reusable eval pack

After the first successful pilot, this can become a repeatable **Agent Readiness Evaluation** and later a continuous release gate.

## The pitch

> You already have an AI workflow. We do not ask you to trust another demo. Give us representative historical cases and your current system. We will show you exactly where it fails, whether a new version is truly better, and whether it is safe to deploy against rules you choose in advance.
