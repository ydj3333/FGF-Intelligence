# FGF Intelligence — Current Development Summary

Generated: 2026-09-20 07:04:05 IST

This is the canonical working summary produced after reviewing the latest dated FGF summary artifact and the full available FGF project/chat context.

## Operating principle
FGF Intelligence is an evidence-controlled game intelligence system, not a static wiki.

Required answer pipeline:
User Question → Intent Classification → Constraint Extraction → Player Context → Relevant Evidence Retrieval → Evidence Filtering → Season/Scope Check → Reasoning/Calculation → Answer Synthesis → Quality Gate → Answer.

User intent is sovereign. Do not make the player orchestrate the system.

## Evidence hierarchy
1. Tier 1 — direct current in-game evidence / Encyclopedia Galactica
2. Tier 2 — official website, patch notes, developer communications
3. Tier 3 — strong tested technical/community evidence
4. Tier 4 — creator/video/written guides
5. Tier 5 — meta opinions/recommendations
6. Tier 6 — rumors/unverified

Never silently delete historical knowledge. Preserve conflicts, provenance, season/version, confidence and change history. Never invent missing values.

## Current architecture
Notion = human evidence/control room.
GitHub = application + machine-readable knowledge.
Supabase = persistent V4 data/learning laboratory.
Render = player-facing product.
Firecrawl/TinyFish/Web = discovery and verification.
LLM = constrained synthesis layer.

Repository: ydj3333/FGF-Intelligence
Live app: https://fgf-intelligence.onrender.com/

## Current corpus state
853 claims, 46 sources, 45 change-log entries, 5 preserved conflicts in the current application snapshot. The historical health metric of 457 Tier-1 is stale relative to the later audit that reclassified 22 community claims from Tier 1 to Tier 3; do not use the old 457 number as current canonical truth.

## Reviewed latest summary
FGF Intelligence —20 sep 340.pdf showed the live application answering a Critical Components question using evidence fallback and exposed the then-current live metrics.

Additional reviewed material included the V4 seven-layer failure analysis, the V4 quality-gate/Core-35 failure analysis, and GitHub Actions/Render deployment-state evidence.

## Critical quality requirements
### Repair
“what's the best ways to repair your fleets ad free way” must route to Fleet Damage/Repair, extract F2P + Best, reject Command Point evidence, and answer only from repair evidence.

### Core 35 cost
“How much does Core 35 cost in fusion seeds?” must route to Progression, retrieve Energy Core/Fusion Seed evidence, reject Flagship costs, and explicitly admit missing exact cost rather than substitute another cost.

### Champion recommendations
“best heroes for kinetic ship” must use Champion/Hero evidence and distinguish recommendation/meta from generic Energy-Type mechanics.

## Current benchmark history
The 100-question routing/retrieval suite previously produced 59/100 broad intent matches and 100/100 evidence retrieval. This is not an answer-quality score. Unsupported questions must become abstention tests, and multi-intent questions should eventually use an intent graph.

## Conflict desk
The UI supports confirm/reject/supersede/keep-under-review plus evidence and notes for all five conflicts. Current storage is local JSON and is not durable across Render restarts/redeploys. Supabase persistence and admin authentication remain hardening work.

## Development rules
- Execute real work, not plan-only responses.
- Reuse the existing V4/V4.1 architecture.
- After every GitHub main change: verify commit, Render auto-deploy, live health, and relevant tests.
- Do not ask for manual deployment unless auto-deploy is broken.
- S1 remains the baseline; S2/S3 are later overlays.
- Do not silently overwrite/delete evidence.
- Keep project/folder knowledge isolated.
- Do not expose secrets.
- A feature is done only when implemented → committed → deployed → live-tested → benchmarked.

## Current engineering priorities
1. Answer-quality correctness.
2. Durable conflict review persistence and admin authentication.
3. Benchmark expansion for grounding, abstention, conflicts, season scope and calculations.
4. Structured calculation/reasoning engine.
5. Player-facing builders/calculators/progression planner/evidence drill-down.

## Change made on 2026-09-20
Implemented V4.1 answer-quality hardening:
- hard topic/entity relevance requirements for high-risk questions
- stronger Energy Core/Fusion Seed routing
- repair-topic evidence gate
- Champion recommendation evidence gate
- exact-cost substitution protection
- evidence-ID validation
- final quality gate integrated into /api/ask
- /api/benchmarks/quality endpoint
- health now distinguishes synthesis configuration from runtime verification

Commit: fce557d214864befa153f6ec62bedfc8912f8ada

Live verification completed: v4.1.0-answer-quality-gate is deployed and the answer-quality regression suite is 5/5 passed. Continue with durable conflict review persistence, admin authentication, expanded grounding/abstention benchmarks, calculation engine, and player-facing builders.
