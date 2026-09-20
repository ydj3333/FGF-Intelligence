# FGF Corpus Synchronization Audit — 2026-09-20

## Result

The production corpus was a static GitHub snapshot while Supabase contained newer claims.

| Layer | Claims | Tier 1 |
|---|---:|---:|
| GitHub/Render before sync | 930 | 435 |
| Supabase | 1,058 | 435 |
| Missing from production | 128 | 0 |

All 930 production claims matched Supabase claims by normalized claim text. The 128 additional Supabase claims were not duplicates.

## Missing claim profile

- 126 — Tier 3 — Creator/Community, status Under Review
- 1 — tier2, status candidate
- 1 — tier1, status candidate

The 128 claims were created after the last data/knowledge.json update:

- 48 at 2026-09-20 02:50:42 UTC
- 59 at 2026-09-20 02:53:53 UTC
- 19 at 2026-09-20 02:55:10 UTC
- 2 at 2026-09-20 08:08:38 UTC

GitHub history shows data/knowledge.json was last updated at 2026-09-20T02:45:41Z before those claim insertions.

## Root cause

agent.py loads data/knowledge.json at process startup and does not load the claims table from Supabase for the player knowledge corpus.

Therefore this was a **snapshot synchronization gap**, not a status-based production exclusion.

The production relevance filter excludes only rejected and superseded claims; it does not exclude Under Review claims. This is consistent with the existing production corpus already containing many Under Review claims.

## Action taken

1. Added scripts/audit_corpus_sync.py for a reproducible, read-only-by-default Supabase-to-GitHub corpus audit.
2. Added all 128 previously missing Supabase claims to data/knowledge.json.
3. Preserved their Supabase tier/status/source metadata.
4. Re-ran the full Knowledge Analyzer against all 1,058 claims.
5. Verified Render production now reports 1,058 claims.

## Full 1,058-claim analyzer result

- Excellent: 655
- Good: 131
- Acceptable: 260
- Weak: 12
- Problematic: 0
- Average quality: 86.82%
- Average confidence: 86.02%
- Preserved conflicts: 11
- Current claims: 469
- Under Review: 583

The lower average quality versus the 930-claim snapshot is now visible rather than hidden by an incomplete corpus.

## Next engineering step

The one-time synchronization is complete, but the architecture still needs an automatic Supabase-to-production knowledge-pack synchronization contract.

That should be implemented only after defining the promotion/snapshot policy. The system must explicitly distinguish candidate evidence, under-review claims, canonical/current claims, and rejected/superseded claims.

The current player retrieval code already excludes rejected/superseded claims. The next design step is to formalize that policy and automate the export rather than relying on manual GitHub snapshot updates.
