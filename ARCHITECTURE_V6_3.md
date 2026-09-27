# FGF Intelligence v6.3 Architecture

## The three live intelligence lines

### Line 1 — Core Knowledge
The existing v6.2 Knowledge Query Engine, Evidence Graph, lifecycle, authority and current-version handling remain the canonical fact layer.

### Line 2 — Live Observation and Experience
The Windows observer watches the game locally, emits structured state/event observations, and builds repeated gameplay experience. It does not directly edit canonical claims.

### Line 3 — YouTube and Community
The existing video pipeline is retained as a fallback/enrichment path. It is used only after the core corpus does not establish the requested information.

Human feedback is a separate learning signal.

## Runtime order

For a player question:

1. Parse intent.
2. Query Core.
3. Apply authority/lifecycle policy.
4. If the core answer is established, return it.
5. For strategy/interpretation, consult validated experience when it adds context.
6. If the core has a genuine knowledge gap, YouTube/community may be consulted.
7. Preserve provenance and warnings.
8. If nothing establishes the answer, abstain.

## Learning order

Observation -> validation -> deduplication -> context binding -> repeated comparable observations -> conflict check -> under review -> validated experience.

A single observation never becomes a global fact.

## Live observer

The current observer:
- targets the FGF Windows client;
- samples locally;
- detects visual changes;
- sends screen-change events;
- never uploads raw video;
- never controls the game;
- hard-stops after two hours of daily observation.

Semantic event extraction is the next layer and uses the same observation contract.

## Context

Experience is bound to available:
- game version;
- season;
- server;
- energy type;
- mode;
- event;
- relevant fleet/champion context.

If context is missing, the pattern remains less general and is not silently generalized.

## Security

- Observation tables use RLS.
- Backend uses a server-side secret key only.
- The observer uses a dedicated observer token, never a Supabase secret.
- Raw gameplay remains local unless an explicit future feature enables evidence upload.
