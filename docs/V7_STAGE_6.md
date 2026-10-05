# v7 Stage 6 — Evidence Intelligence

Stage 6 provides the evidence and personalization layer above the v7 event-strategy engine.

## Pipeline
1. Evidence fusion — authority, lifecycle/status and relevance weighting with provenance retention.
2. Contradiction engine — explicit topic families classify conflicts as temporal, authority or interpretation; resolution never deletes losing evidence.
3. Player adaptation — confirmed player profile fields are applied separately from global event facts; missing fields remain missing.
4. Quality gate — unresolved contradictions make the answer uncertain and block confident recommendations.
5. Answer-surface integration — solve_question() accepts evidence and player-profile context and returns the Stage 6 result alongside the existing Stage 2–5 output.

## Conflict policy
- Official/primary evidence outranks community enrichment.
- Current evidence outranks historical/superseded evidence.
- Equal-authority current disagreements remain unresolved.
- Explicit EvidenceRecord.topic is preferred for contradiction pairing; claim-ID prefix is a compatibility fallback.
- Losing/superseded evidence is preserved for auditability.

## Player policy
Supported profile fields are spending profile, Core level, fleet type, guild role, owned/unavailable entities and preferences. Missing material fields are surfaced; the engine never invents them.

## Test contract
Stage 6 tests cover temporal resolution, unresolved same-authority interpretation conflicts, explicit topic grouping, missing player profile fields, and end-to-end wiring through solve_question().
