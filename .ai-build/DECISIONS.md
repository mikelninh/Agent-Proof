# DECISIONS

## D001 — Start with deployment proof, not generic benchmarking
Buyers care whether their workflow is safe and economically rational, not who tops a toy leaderboard.

## D002 — Fraud Analyst is the first arena
It naturally exposes costly asymmetric errors: a false approval of fraud is more dangerous than an unnecessary review.

## D003 — Deterministic graders first
LLM-as-judge can be added later, but initial metrics should be reproducible and auditable.

## D004 — Local-first storage
Makes pilots easy and reduces data exposure. Hosted multi-tenant auth comes after demand.

## D005 — Pair runs by case ID
Aggregate scores can hide dangerous swaps. A release decision must show which exact cases improved and which regressed.

## D006 — Statistical evidence without heavyweight dependencies
Use Wilson intervals and an exact McNemar/binomial paired test implemented in the standard library. Keep the local-first install small and auditable.

## D007 — Offline A/B demo
Ship a deliberately imperfect baseline and a stronger candidate so the entire regression workflow is testable without an API key.

## D008 — Audit-ready means structural risk coverage, not certification
A commercial Agent Trust Audit must not be built from happy-path accuracy cases alone. The starter contract requires at least 30 cases and explicit case-tag coverage for correctness, boundary behaviour, injection, recovery and approval. This gate proves minimum test-surface structure only; representativeness, domain truth and production safety still require human/domain validation.
