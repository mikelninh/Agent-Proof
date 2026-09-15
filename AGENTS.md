# AGENTS.md

## Mission
Build Agent Proof into the fastest credible way to answer: **"Is this AI workflow safe and economically worthwhile to deploy?"**

## Product rules
1. Evidence over demos. Every headline metric must trace to individual cases.
2. Ground truth stays separate from agent-visible input.
3. Critical failures are first-class, not hidden inside an average score.
4. Cost and latency are measured, not hand-waved.
5. A customer must be able to bring their own cases and their own agent.
6. Never persist API keys.

## Build loop
Use: **01 SHAPE → 02 SPECIFY → 03 DELEGATE → 04 PROVE → 05 SHIP → 06 WATCH**.
Read `.ai-build/` before substantial changes.

## Definition of done
A feature is done only when it has: working code, a test or deterministic evidence, documentation if user-facing, and no regression in the demo pack.
