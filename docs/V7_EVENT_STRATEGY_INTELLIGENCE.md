# FGF v7 — Event Strategy / Constraint Intelligence

## Purpose

Move FGF from event-specific retrieval toward reusable decision intelligence.

The engine does **not** assume that one event's strategy transfers to another.
Each event supplies its own objective, scoring factors, stages, timing rules,
tactical priorities and resource priorities.

The reusable decision pipeline is:

1. Identify event.
2. Build the event strategy model.
3. Extract explicit player constraints.
4. Hard-filter impossible/unowned actions.
5. Score remaining actions against **that event's** mechanics.
6. Rank feasible actions.
7. Separate evidence-backed facts from tactical inference.
8. Abstain or ask for missing player state when no safe recommendation exists.

## Cross-event acceptance tests

The initial test set intentionally spans structurally different events:
- Kaboom, Robots! — PvE waves / AOE.
- Shadowfront — Vault occupation / contribution scoring.
- Paths to Dominance — fortress conquest / rallies / title timing.
- Commerce Guild Duel League — Rank Points / guild + individual PvP.

A future event should be represented by data and evidence, not a new reasoning engine.

## Hard rule

**Player constraints are filters, not suggestions.**

If the user says they own Zora, Lily and Kama, a generic Jodie-based lineup
cannot be returned as their lineup merely because community evidence calls it
"best."

If a required detail is unknown, the engine must expose the unknown rather
than invent it.
