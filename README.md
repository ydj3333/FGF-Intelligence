# FGF Intelligence v3 — Live Candidate

Evidence-first, query-first Foundation: Galactic Frontier intelligence engine.

## Product layers
- **Notion:** evidence control room, source registry, claims, conflicts, verification, operating standard.
- **GitHub:** versioned application + machine-readable knowledge snapshots.
- **Public app:** player-facing search, decision support, builders/calculators and evidence drill-down.

## Current release
- S2 knowledge snapshot
- 853 claims / 46 sources / 45 changes
- 450 Tier-1 claims
- conflict-aware retrieval
- objective-aware deterministic recommendation retrieval
- knowledge search
- evidence/confidence/status display

## Run
`python agent.py` then open `http://127.0.0.1:8000`.

## Important
This release is a deployable **retrieval/decision-engine candidate**, not a claim that public hosting is already live. The final production release must add persistent storage, authenticated admin review, an LLM synthesis layer with mandatory evidence retrieval, automated regression tests, monitoring, and a connected GitHub/hosting environment.
