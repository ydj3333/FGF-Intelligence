# FGF Intelligence v4 — V4 Foundation

Evidence-first, continuously learning Foundation: Galactic Frontier intelligence engine.

## Product layers
- **Notion:** evidence control room, source registry, claims, conflicts, verification, operating standards and human promotion decisions.
- **GitHub:** versioned application, machine-readable knowledge snapshots, source registry, schemas and regression tests.
- **Supabase:** persistent learning laboratory for evidence metadata, candidate knowledge, formulas, simulations, benchmark Q&A, media metadata, ingestion runs and evaluation results.
- **Firecrawl:** broad web discovery, crawling, extraction and change monitoring.
- **TinyFish:** interactive/dynamic source acquisition where normal crawling is insufficient.
- **Public app:** player-facing search, decision support, builders/calculators and evidence drill-down.

## Current knowledge snapshot
- S2 knowledge snapshot
- 853 claims / 46 sources / 45 changes
- **457 Tier-1 claims**
- 5 preserved conflicts
- adaptive evidence retrieval
- conflict-aware synthesis
- objective-aware recommendation retrieval

## V4 intelligence requirements
The system is being extended from retrieval into a persistent evidence and learning platform:
- level/resource/Power formulas
- prerequisites and unlock chains
- event requirements and scoring
- historical/version-specific mechanics
- candidate/adaptive knowledge
- bug/fix tracking
- simulated questions and validated answers
- continuous regression testing
- image/OCR and video/transcript evidence
- source fingerprinting and deduplication
- controlled promotion and supersession

## Evidence rule
T1 = direct current in-game evidence; T2 = official game information; T3 = strong tested/community evidence when no stronger source establishes the claim; T4+ = discovery/meta/rumour layers as defined by the evidence registry.

For YouTube, creator, player and other crowd material:
- If Tier 1 or Tier 2 evidence exists for the same claim, stronger evidence governs; the video is supporting/additional evidence.
- If no Tier 1 or Tier 2 evidence exists, the observation is retained as **Tier 3 crowd/community evidence**, status **candidate**, canonical **false**.
- A Tier 3 crowd claim must be presented as additional data suggested/reported by others and carefully evaluated before reliance.
- Contradictions are preserved and flagged for review; they never silently overwrite canonical knowledge.
- YouTube extraction never auto-promotes a claim to CURRENT or canonical truth.

A source's default tier never overrides what the specific evidence actually establishes. Images and videos are first-class evidence objects.

## Live discovery
A Firecrawl 6-hour FGF discovery monitor is configured to detect S2 changes, patches, events, mechanics, formulas, bugs, fixes, guides, testing, videos and official announcements. Discovery does not automatically promote information to canonical truth.

## Run
`python agent.py` then open `http://127.0.0.1:8000`.

## Current production status
The public application and evidence corpus are operational, but V4 persistent-learning infrastructure still requires a provisioned Supabase project and ingestion/evaluation services. The canonical evidence layer remains protected while adaptive intelligence is built around it.
