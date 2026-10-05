# FGF v7 Stage 4 — Tactical Optimization

Stage 4 turns feasible candidates into **event-specific ranked strategies**.

## Decision order

1. Extract explicit player constraints.
2. Generate only feasible combinations.
3. Apply hard availability/exclusion constraints again at scoring time.
4. Score event-priority coverage.
5. Score event scoring-factor coverage.
6. Add only explicitly supplied combination synergy.
7. Add evidence strength.
8. Penalize missing event priorities.
9. Rank alternatives and explain why #1 beats #2.

## Safety contract

- A high-scoring combination cannot override an explicit player constraint.
- Event A's tactical priorities cannot become Event B's mechanics.
- Champion popularity is not a scoring factor unless an evidence-backed event adapter supplies it.
- Position/order is not invented. If an adapter lacks authoritative ordering evidence, output must label the order as tactical inference or omit it.
- Tier 2/community evidence can enrich ranking but does not silently become canonical fact.
- If two candidates are tied on all evidence-backed dimensions, the engine says so instead of manufacturing a reason.

## Acceptance target

For a request such as "give me 5 combinations using only my Champions", the system should:
- generate the feasible set from the actual roster;
- rank those combinations using the active event model;
- return up to 5 distinct alternatives;
- explain the differentiator between the top alternatives;
- never fabricate a sixth Champion or reuse another event's strategy.
