# FGF Intelligence Version Contract

## Current architecture
- Version: 6.5.0
- Name: Evidence-Safe Video Retrieval + Operational Intelligence
- Baseline: v6.2 green core plus Evidence Graph v2
- Branch: main

## v6.4 adds
1. Event day-plan generation with explicit unknowns and evidence-state labels.
2. Shop-by-shop buying matrices with USE/SAVE/AVOID guardrails.
3. Resource allocation matrices for event spending.
4. Player-facing structured operational output in Ask FGF.
5. Operational regression tests.

## v6.5 adds
1. Event-aware YouTube/community retrieval with alias resolution.
2. Candidate-to-video provenance with original video URL preserved.
3. Strategy/interpretation video enrichment even when Core already answers.
4. Factual-answer gate preventing YouTube candidates from becoming factual truth.
5. Rejection of generic/unrelated videos for event-specific queries.
6. Regression tests for event retrieval, leakage prevention, and enrichment.

## v6.4 adds
1. Core policy gate for authority, intent and lifecycle-aware evidence use.
2. Live Windows observation contract and runtime API.
3. Two-hour daily observer budget.
4. Structured observation events.
5. Repeated-pattern experience learning with promotion gates.
6. Simple human feedback ingestion.
7. YouTube remains a deferred fallback/enrichment branch.

## Non-regression contract
v6.3 must preserve:
- core-first retrieval;
- evidence provenance;
- lifecycle and conflict safety;
- safe abstention;
- numeric safety;
- existing v6.2 Objective #1 benchmark;
- Evidence Graph v2 behavior;
- no automatic promotion of community/YouTube/live observations into canonical facts.

## Next version boundary
v6.5 may add semantic OCR/UI extraction, richer action-to-outcome modeling, and validated YouTube fallback integration. It must not remove the v6.3/v6.4 rules.
