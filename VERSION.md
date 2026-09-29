# FGF Intelligence Version Contract

## Current release
- Version: 6.6.2
- Name: Canonical Query Coverage Benchmark — Relation-Gated Hardening
- Baseline: v6.6.1 canonical query coverage benchmark plus Evidence Graph v2
- Branch: main

## v6.3 — Live + Experiential Intelligence
1. Core-first policy gate for authority, intent and lifecycle-aware evidence use.
2. Live Windows observation contract and runtime API.
3. Two-hour daily observer budget.
4. Structured observation events and repeated-pattern experience learning.
5. Human feedback ingestion as a learning signal, never canonical proof.
6. YouTube/community remains enrichment/fallback and never silently becomes canonical truth.

## v6.4 — Operational Intelligence
1. Event day-plan generation with explicit unknowns and evidence-state labels.
2. Shop-by-shop buying matrices with USE/SAVE/AVOID guardrails.
3. Resource allocation matrices for event spending.
4. Player-facing structured operational output in Ask FGF.
5. Kaboom and Shadowfront event surfaces with evidence-state guardrails.
6. Operational regression tests.

## v6.5 — Evidence-Safe Video Retrieval
1. Event-aware YouTube/community retrieval with alias resolution.
2. Candidate-to-video provenance with original video URL preserved.
3. Strategy/interpretation video enrichment even when Core already answers.
4. Factual-answer gate preventing YouTube candidates from becoming factual truth.
5. Rejection of generic/unrelated videos for event-specific queries.
6. Regression tests for event retrieval, leakage prevention and enrichment.
7. JSON-safe Ask API error handling to prevent internal exceptions becoming HTML/502 responses.

## v6.5.1 — Canonical Vocabulary Hardening
1. Tier-1/Tier-2 terminology is automatically indexed from the canonical claim corpus.
2. Multi-word canonical entities are extracted from canonical claim text instead of relying only on manual aliases.
3. Singular/plural query variants resolve to the same canonical entity.
4. Distinctive-token selection reduces generic-token entity collisions.
5. CI explicitly checks Tier-1/Tier-2 vocabulary discoverability.
6. Regression workflow YAML is syntax-correct and runs on main pushes and pull requests.

## v6.5.2 — Generic Lookup Policy Fix
1. Evidence-backed generic entity/event lookups are treated as factual by default.
2. Generic canonical queries no longer get mislabeled as orchestration abstentions.
3. Regression coverage locks the Core branch for generic lookups with official evidence.

## v6.6.0 — Canonical Vocabulary Audit & Observability
1. Production derives Tier-1/Tier-2 vocabulary directly from the canonical claim corpus.
2. Multi-word canonical entities and singular/plural variants are audited deterministically.
3. Production health exposes vocabulary coverage metrics so deployment health is observable.
4. Regression tests cover canonical vocabulary counts and common query variants.
5. Generic evidence-backed entity/event lookups remain factual and Core-first.
6. No new source or claim is introduced by the audit layer; it only measures the canonical corpus.

## v6.6.1 — Canonical Query Coverage Benchmark
1. Deterministic coverage cases are generated from the canonical Tier-1/Tier-2 vocabulary.
2. Meaningful player-facing entities are normalized through the production parser before benchmarking.
3. Factual, update, source, requirement, numeric-cardinality and event cases are generated only when supported by canonical evidence.
4. CI fails when a generated canonical query cannot be parsed to the expected entity or returns evidence-empty output.
5. Incidental dates and unrelated numeric values cannot manufacture numeric cases.
6. Benchmark measures retrieval coverage only; it does not promote YouTube/community evidence or invent facts.

## v6.6.2 — Canonical Query Coverage Relation-Gated Hardening
1. Specialized source/update/requirement cases require an entity-local relation in the canonical claim.
2. Numeric cases are generated from canonical cardinality statements instead of generic entity-number guesses.
3. Numeric questions preserve the canonical counted object, improving player-facing query realism.
4. Event cases require event evidence or an explicit event marker tied to the entity.
5. Regression tests protect against marker leakage and numeric-case distortion.

## Non-regression contract
The system must preserve:
- core-first retrieval;
- evidence provenance;
- lifecycle and conflict safety;
- safe abstention;
- numeric safety;
- existing v6.2 Objective #1 benchmark;
- Evidence Graph v2 behavior;
- no automatic promotion of community/YouTube/live observations into canonical facts;
- explicit "Not established in current evidence" instead of invented event schedules, rewards, costs, timers or requirements.
