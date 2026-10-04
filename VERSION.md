## v7.0.0 — Event Strategy Intelligence / Stage 4 Tactical Optimization

1. Adds combination-level tactical optimization after constraint extraction and feasible candidate generation.
2. Ranks candidates using active-event tactical priorities, scoring factors, explicitly supplied synergy, evidence strength, and missing-priority penalties.
3. Enforces player constraints before optimization so infeasible high-scoring combinations can never win.
4. Produces auditable comparison language explaining why the top candidate outranks the next alternative.
5. Preserves event isolation: tactical priorities from one event cannot become mechanics for another.
6. Preserves evidence safety: unsupported Champion synergy or position/order mechanics are never invented.

## v6.7.0 — Current Web + Season 2 Intelligence Enrichment

1. Adds a dated current-web source registry covering current FGF Wiki event/champion data, Season 2/Siwenna, official Fleet Power mechanics, official release-note changes, and the September 2026 hot update.
2. Adds source-aware lifecycle and conflict rules so current values can supersede historical values without deleting the historical evidence.
3. Adds Season 2 schedule safety: server-specific timing must come from the in-game calendar; no dates are inferred from generic event cadence.
4. Enriches Paths to Dominance output with current 24-hour event-index corroboration, Level 9 PvP scoring, Prince Decree lifecycle changes, Siwenna context, and deterministic fleet mechanics.
5. Adds regression coverage for current-web ingestion and supersession guardrails.

## v6.6.3 — Requested-Option Verification & Roster-Aware Kaboom Output

- Explicit alternative counts (for example, 5 lineups) are detected and structurally verified against returned options.
- Kaboom five-lineup requests return one evidence-backed named combination plus roster-dependent templates rather than invented Champion names.
- Output verification exposes requested count, returned count, concrete validated options, roster-required options, and whether player roster context is required.
- No new game claims or unsupported Champion combinations are introduced.

# FGF Intelligence Version Contract

## Current release
- Version: 6.6.4
- Name: Paths to Dominance Event Intelligence
- Baseline: v6.6.3 requested-option verification plus Evidence Graph v2
- Branch: feature/path-to-dominance-event

## v6.6.4 — Paths to Dominance Event Intelligence
1. Adds structured operational intelligence for the Paths to Dominance event.
2. Encodes Trader Prince competition, appointment, Counselor application, Prince Ability, leaderboard and participation rules from primary in-game UI evidence.
3. Preserves explicit unknowns for event dates, unidentified reward icons, Traderhunt duration and other unreadable values.
4. Adds regression coverage for event routing and anti-inference guardrails.

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
