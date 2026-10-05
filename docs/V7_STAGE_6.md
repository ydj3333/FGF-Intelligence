# v7 Stage 6 — Evidence Intelligence

Stage 6 introduces four reusable layers:

1. Evidence fusion: deterministic authority, recency/status and relevance weighting with provenance retention.
2. Contradiction detection: temporal, authority and interpretation conflicts; losing evidence is preserved.
3. Player adaptation: confirmed player profile fields remain separate from global event truth; missing fields are never inferred.
4. Quality gate: unresolved contradictions downgrade confidence and block confident recommendations.

## Policy
- Official/primary evidence outranks community enrichment.
- Current evidence outranks historical/superseded evidence.
- Equal-authority current disagreements remain unresolved rather than being guessed.
- Tier-2/Tier-3 evidence can inform strategy but does not silently become canonical truth.
- Player-specific facts never mutate global game facts.

## Current scope
This first Stage 6 slice is a reusable core. Event/database adapters and full answer-surface integration are the next slice. The implementation intentionally does not invent topic relationships from free text; callers must provide compatible claim IDs/topics when requesting contradiction detection.
