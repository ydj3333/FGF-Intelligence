# FGF Intelligence Version Contract

## Current architecture
- Version: 6.3.0
- Name: Live Experiential Intelligence
- Baseline: v6.2 green core plus Evidence Graph v2
- Branch: feature/v6.3-live-experiential-intelligence

## v6.3 adds
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
v6.4 may add semantic OCR/UI extraction, richer action-to-outcome modeling, and validated YouTube fallback integration. It must not remove the v6.3 rules.
