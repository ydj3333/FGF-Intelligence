# FGF Video Evidence Pipeline

## Purpose
Turn a YouTube playlist into auditable candidate evidence without silently promoting creator/community statements into canonical game truth.

## Flow
Playlist index -> transcript acquisition -> LLM/rule-fallback extraction -> cross-reference -> candidate persistence -> candidate snapshot -> human/admin promotion.

## Commands
Index:
python scripts/fetch_playlist_index.py --playlist-id <PLAYLIST_ID>

Transcript batch:
python scripts/download_transcripts.py --batch-size 10 --delay-seconds 3

One playlist batch:
python scripts/process_video_playlist.py --playlist-id <PLAYLIST_ID> --start 0 --count 10

Persist candidate metadata:
python scripts/process_video_playlist.py --playlist-id <PLAYLIST_ID> --start 0 --count 10 --apply

## Required environment
- YOUTUBE_API_KEY
- FGF_LLM_API_KEY or OPENAI_API_KEY (optional; rule fallback is used if unavailable)
- SUPABASE_DB_URL or SUPABASE_CONNECTION_STRING (required only for --apply)

## Control rules
- Video evidence defaults to Tier 3 candidate evidence.
- Transcript extraction never creates Tier 1 evidence.
- Canonical data/knowledge.json is never overwritten by ingestion.
- video_claim_candidates is the staging layer.
- Duplicates are linked/flagged rather than blindly inserted.
- Potential contradictions are preserved for review.
- Exact costs, limits, timers and formulas require explicit supporting evidence.
- Creator recommendations remain recommendations/meta assessments.
- Current official/in-game evidence can supersede older video evidence through normal conflict/change-control.

## Scaling
Process the playlist in batches with --start and --count. Existing transcripts are skipped. Re-running extraction/cross-reference is idempotent for the same transcript.
