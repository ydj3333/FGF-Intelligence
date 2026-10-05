# FGF Core Objective Compatibility Contract

## Status

**Permanent architectural contract.** This document does not introduce a new rule. It makes the existing FGF V4/V4.1/v6/v7 objectives explicit so future stages cannot accidentally replace them.

## Existing objectives that every new stage must preserve

1. **Core-first retrieval** — the established Core Knowledge Query Engine remains the primary factual intelligence layer.
2. **User-intent sovereignty** — the system interprets the player's question; the player must not manually orchestrate retrieval.
3. **Evidence provenance** — answers remain traceable to the evidence that supports them.
4. **Lifecycle and scope safety** — season, server, version, event window and current/superseded status remain distinct.
5. **Safe abstention / no invention** — missing values, schedules, costs, timers, mechanics and requirements remain unknown rather than being guessed.
6. **Specialized answer preservation** — existing domain-specific handlers are part of the intelligence, not disposable formatting paths.
7. **Complete reasoning chains** — multi-hop answers require every requested link to be evidenced.
8. **Player constraints are hard constraints** — ownership, exclusions, requested counts and other explicit constraints cannot be overridden by a generic recommendation.
9. **Operational intelligence integrity** — structured event/lineup/shop outputs must retain their evidence-state and guardrails.
10. **Experience/community is additive** — validated experience and YouTube/community evidence enrich or fill genuine gaps; they do not silently overwrite Core.
11. **Historical/conflict preservation** — superseded claims and contradictions remain auditable.
12. **Regression preservation** — existing benchmarks and answer-specific tests remain release gates.

## Layering rule

The production flow is:

**Core retrieval and specialized reasoning**
→ **policy/evidence classification**
→ **validated experience / community enrichment where permitted**
→ **Stage 6 fusion/adaptation/quality metadata**
→ **player-facing answer**

A later layer may:

- add provenance;
- add currentness/conflict information;
- add player-specific context;
- add validated experience;
- add a safe recommendation;
- downgrade confidence when the evidence requires it.

A later layer may **not**:

- replace a correct Core answer with generic event facts;
- turn an established answer into an empty/irrelevant answer;
- erase specialized handler output;
- use a new generic ranking algorithm to bypass an existing domain-specific handler;
- promote weaker evidence above stronger current evidence;
- remove historical/conflicting evidence;
- invent missing mechanics to make the answer look complete.

## Regression rule

For every new stage, tests must include:

- at least one established specialized Core answer;
- at least one safe-abstention case;
- at least one conflict/lifecycle case;
- at least one player-constraint case where the generic optimum is infeasible;
- at least one event-specific case proving event isolation.

The new stage is not complete if the new tests pass while an established Core answer regresses.

## What happened in Stage 6

The Stage 6 work initially treated this existing contract as something to add rather than something to inherit. That caused the comparative-answer regression and weakened the separation between established Core answers and later policy processing.

Stage 6 is therefore being corrected to **consume the existing contract rather than redefine it**.

The compatibility implementation is in `core_objectives.py`, and the orchestration boundary now captures the original Core result before later processing and validates that an established Core answer remains present in the final answer.
