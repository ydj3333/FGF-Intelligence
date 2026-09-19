# FGF V4 Intelligence Engine

V4 is the integrated evolution of the existing v3.3 evidence assistant.

## Implemented foundation
- Persistent Supabase learning laboratory.
- Season/server-aware knowledge model: S1 baseline + S2 overlay + future overlays.
- Evidence, claims, conflicts, formulas, formula tests, events, media, transcripts, candidate knowledge, simulations, benchmarks, evaluations, learning/ingestion runs, admin reviews and change log tables.
- Source/tool registry ingestion queue.
- Canonical truth remains protected; candidates cannot silently become Tier 1.

## V4 reasoning contract
Every answer should distinguish:
1. confirmed current mechanics
2. version/season scoped mechanics
3. calculated results
4. inferred/provisional conclusions
5. recommendations/meta
6. unresolved conflicts

## Learning loop
Discover -> fingerprint/deduplicate -> extract evidence -> create/update candidate claims -> detect conflicts -> test formulas/simulations -> evaluate answers -> queue admin review -> promote/supersede with full history.

## Simulation layer
Simulations must store scenario, assumptions, result, confidence and evidence IDs. No simulation result becomes a game fact without supporting evidence.

## Calculation layer
Executable formulas require variables, units, version/season scope, evidence and tests. Failed tests remain visible.

## Release gate
V4 is not considered complete until the existing 853-claim corpus is migrated/linked, formulas and benchmarks are populated, ingestion is connected, the reasoning service uses the persistent store, and regression tests pass.

## Current build state
- Supabase project: FGF-V4-Intelligence
- Region: ap-south-1
- Core schema: deployed
- Game versions seeded: 2
- Ingestion source queues seeded: 10
- Claims/formulas/simulations/benchmarks in Supabase: pending migration from GitHub corpus
