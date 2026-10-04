# V7 Stage 5 — Answer Validation / Intelligence Quality Gate

Stage 5 is the final deterministic gate between the strategy engine and a player-facing answer.

## Checks
1. Requested-count verification.
2. Roster and exclusion validity.
3. Team-size integrity.
4. Event-mechanic consistency.
5. Evidence/confidence state.
6. Position/order safety.
7. Duplicate detection.
8. Timing/contradiction signal.

## Failure policy
- Error issues make the validation result invalid and block a clean player-facing answer.
- Warning issues do not invalidate the result, but must remain visible to the response formatter.
- The validator does not repair missing facts or promote Tier-2/community evidence.
- It validates the decision surface; it does not replace event-specific evidence ingestion.

## Cross-event target
Apply the same gate to Kaboom, Shadowfront, Paths to Dominance, and Commerce Guild Duel League.
