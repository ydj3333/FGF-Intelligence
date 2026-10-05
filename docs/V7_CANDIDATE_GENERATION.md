# V7 Stage 3 — Candidate Generation

## Contract

Candidate generation is now separated from event strategy scoring.

1. Take the player's **explicitly available** roster.
2. Generate feasible combinations of the requested team size.
3. Never introduce an unowned/unconfirmed Champion.
4. Remove duplicate combinations.
5. Annotate each combination with the roles/tags supported by the active event.
6. Pass candidates to the generic strategy scorer.

The generator is intentionally event-agnostic. Event differences enter through
the EventStrategyModel and role/tag mappings.

If the player asks for five combinations but fewer than five feasible unique
combinations exist, the system must return the feasible number and explain the
constraint instead of fabricating additional teams.
