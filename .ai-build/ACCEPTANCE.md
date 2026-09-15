# ACCEPTANCE

- [x] `uvicorn agentproof.app:app` serves product UI.
- [x] Bundled scenario pack contains 100 cases.
- [x] Baseline and candidate demo runs complete without external API keys.
- [x] Baseline demo is blocked (~87%) while candidate passes (~97%).
- [x] Each case exposes input, output, expected value and grading reason.
- [x] Dangerous `block -> approve` errors are separately counted.
- [x] ROI is calculated from configurable human baseline and annual volume.
- [x] Custom pack can be uploaded from browser or built from CSV.
- [x] OpenAI-compatible and webhook adapters exist.
- [x] API keys are removed before persistence.
- [x] Two runs can be compared by matching case ID.
- [x] Comparison exposes fixes, regressions, new critical failures and cost/latency/economic deltas.
- [x] Comparison includes Wilson success intervals and exact McNemar paired p-value.
- [x] Regression report can be exported as Markdown.
- [x] CLI can exit non-zero on blocked run or rejected candidate.
- [x] Automated tests cover grading, ROI math and comparison logic.
