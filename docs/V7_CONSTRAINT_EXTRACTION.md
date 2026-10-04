# V7 Stage 2 — Universal Constraint Extraction

The engine now treats explicit user constraints as structured state.

Supported first-pass signals:
- explicit owned/available Champions;
- explicit exclusions;
- requested number of combinations;
- formation/order request;
- optimization language;
- attacker/defender/rally role;
- explicit time limit;
- explicit resource limit.

Conservative rule: a Champion mentioned in a generic question is **not** treated as owned.

Aliases such as "kameni" are normalized to the canonical Champion name when known.

Unrecognized or ambiguous player-state information remains unresolved rather than being invented.
