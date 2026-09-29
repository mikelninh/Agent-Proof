# Acceptance — v0.5

- [x] A buyer can run a complete flagship case study with zero API keys.
- [x] Candidate v2 passes a 95% / zero-critical deployment gate.
- [x] Aggressive v3 is blocked by critical failures.
- [x] Historical CSV target values never enter agent-visible input.
- [x] Run reports include failure exposure and coverage weaknesses.
- [x] Paired comparison identifies fixes, regressions and new critical failures.
- [x] Adversarial drafts require human-confirmed expected outputs before pack creation.
- [x] CLI exits non-zero when a deployment gate fails.
- [x] GitHub Actions runs the release gate and uploads evidence.
- [x] Unit/integration tests pass locally and in CI.

## DevDay commercialisation increment — Agent Trust Audit
- [x] Audit readiness has a machine-checkable minimum case count.
- [x] Audit readiness requires explicit coverage of correctness, boundary, injection, recovery and approval behaviour.
- [x] Missing risk dimensions fail closed with a non-zero CLI exit.
- [x] Unit tests cover complete, happy-path-only, undersized and partially untagged packs.
- [x] The commercial offer explicitly states that audit-ready is not certification, legal compliance or proof of representative production safety.
- [x] CI passed on implementation commit `35036e8160fc8a6ace8aee79996d55359f272783` (workflow run `36646975325`).
- [ ] First paid external Agent Trust Audit completed.
