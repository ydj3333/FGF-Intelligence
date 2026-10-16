# FGF Intelligence L0-L6 Runtime Logging Contract

Status date: 2026-10-16. This document defines required event semantics; it is not by itself proof that production is deployed or passing.

## Required levels

| Level | Category | Minimum required event coverage | Verification evidence |
|---|---|---|---|
| L0 | Project/runtime | process start, release identifier, declared level catalog, initial runtime/LLM health | production startup JSON events + health endpoint/log check |
| L1 | Observation | live observer session start/stop, incoming observation request, accepted/rejected/failed observation | authenticated observer smoke test + persistent session/event row counts |
| L2 | Evidence | evidence summary/count, evidence state, source/branch provenance, conflict/evidence governance outcomes | representative factual query and conflict-path trace |
| L3 | Learning | observation/session input into learning path, player-context update, persistence outcome, promotion remains gated | live observation round trip and database delta; no automatic canonical promotion |
| L4 | Reasoning | answer completion/abstention, orchestration branch, evidence state, uncertainty/warning counts | answer API trace for supported and unsupported questions |
| L5 | Evaluation | benchmark route invocation, duration, pass/fail and case counts, regression summary | run the original Objective #1 50-question benchmark and required 10,000+ question-bank coverage checks |
| L6 | Operations | HTTP request lifecycle, latency, route, errors, startup/health and deployment identity | deployed smoke tests plus centralized log query |

## Implementation in this change

- observability/logging_levels.py provides JSON-lines structured events with stable level codes, timestamps, release/service metadata, status, duration and bounded correlation identifiers.
- agent.py emits L0 startup/health events, L1 observation-route events, L2 evidence summaries, L3 observation-learning handoff events, L4 answer completion events, L5 benchmark-route events and L6 request lifecycle events.
- The health response exposes a process-local logging registry, per-level event counters, last event names, and an all-levels-observed flag. These counters reset on restart and must be verified on the deployed release after exercising each route.
- tests/test_logging_levels.py verifies the complete level registry, structured output, redaction, invalid-level rejection and timed success/failure events.
- Secret-like fields are redacted; request bodies, credentials, screenshots and raw video must never be logged.

## Release gates (do not mark complete until all pass)

1. Unit tests pass in CI.
2. Production deployment is identified by its deployed commit and startup emits L0.
3. A real, safe /api/ask query emits L2/L4 and an L6 request lifecycle with the same correlation ID.
4. An authenticated observer session start → observation → stop emits L1/L3 and creates expected database records.
5. Objective #1 50-question benchmark is executed against the deployed API; preserve original cases and report exact pass/fail/coverage.
6. The 10,000+ question bank is audited without silently marking unreviewed questions training-eligible.
7. Supabase logging query confirms all seven levels appear from the deployed runtime, not only from unit tests.
8. Security review resolves or explicitly accepts the existing RLS-disabled video tables and SECURITY DEFINER view finding before release.

## Important current baseline findings

The initial live database audit on 2026-10-16 found 10,051 question-bank rows, 13 approved rows, and 0 training-eligible rows. Observation sessions/events, experience candidates and video processing runs each had 0 rows at audit time. These counts must be rechecked after deployment and smoke tests. Table existence alone is not proof of a functioning runtime pipeline.
