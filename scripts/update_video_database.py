#!/usr/bin/env python3
"""Persist YouTube evidence into the dedicated video staging tables.

Uses Supabase REST so the pipeline does not depend on local psycopg2.
This script never inserts/updates public.claims and never promotes a video
claim to canonical truth.
"""
import argparse, json, os
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


def config():
    base = os.getenv("FGF_SUPABASE_URL", "https://qdoixzfkkmvzjfkhzups.supabase.co").rstrip("/")
    key = os.getenv("FGF_SUPABASE_SECRET_KEY") or os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY")
    if not key:
        raise RuntimeError("FGF_SUPABASE_SECRET_KEY or FGF_SUPABASE_SERVICE_ROLE_KEY is required")
    return base, key


def request(method, url, key, payload=None, prefer="return=representation"):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Prefer": prefer,
    }
    data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=30) as r:
        raw = r.read().decode() or "[]"
        return json.loads(raw)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--video-id", required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    cross = json.loads(
        Path(f"data/video_claims/{args.video_id}_crossref.json").read_text(encoding="utf-8")
    )
    idx = json.loads(Path("data/video_playlist_index.json").read_text(encoding="utf-8"))
    video = next(v for v in idx["videos"] if v["video_id"] == args.video_id)

    if not args.apply:
        print(
            f"[DRY RUN] video={args.video_id} "
            f"claims={len(cross['claims'])} canonical_changes=0"
        )
        return

    base, key = config()
    video_rows = request(
        "POST",
        f"{base}/rest/v1/video_database?on_conflict=video_id",
        key,
        [{
            "video_id": video["video_id"],
            "playlist_id": idx["playlist_id"],
            "playlist_index": video["playlist_index"],
            "title": video["title"],
            "video_url": video["video_url"],
            "description": video.get("description", ""),
            "published_at": video.get("published_at"),
            "duration_seconds": video.get("duration_seconds"),
            "channel_id": video.get("channel_id"),
            "channel_title": video.get("channel_title"),
            "processing_status": "cross_referenced",
            "metadata": {
                "pipeline": "fgf-youtube-v1",
                "canonical_promotion": False,
                "governance": "tier1_tier2_precedence_tier3_crowd_fallback",
            },
        }],
        prefer="resolution=merge-duplicates,return=representation",
    )
    video_db_id = video_rows[0]["id"]

    # Persist every extracted claim as evidence/candidate metadata. This keeps
    # supporting and conflicting observations instead of losing provenance.
    persisted = 0
    for c in cross["claims"]:
        payload = {
            "video_database_id": video_db_id,
            "video_id": video["video_id"],
            "claim_text": c["claim"],
            "category": c.get("category"),
            "claim_type": c.get("claim_type"),
            "evidence_tier": 3,
            "confidence": c.get("confidence"),
            "status": c.get("status", "candidate"),
            "source_url": video["video_url"],
            "evidence_excerpt": c.get("evidence_excerpt", ""),
            "metadata": {
                "classification": c.get("classification"),
                "canonical": False,
                "user_warning": c.get("user_warning"),
                "governance_reason": c.get("governance_reason"),
                "nearest": c.get("nearest", []),
                "pipeline": "fgf-youtube-v1",
            },
        }
        request(
            "POST",
            f"{base}/rest/v1/video_claim_candidates",
            key,
            [payload],
            prefer="return=minimal",
        )
        persisted += 1

    request(
        "PATCH",
        f"{base}/rest/v1/video_database?id=eq.{quote(str(video_db_id), safe='')}",
        key,
        {"processing_status": "persisted_candidates"},
        prefer="return=minimal",
    )
    print(
        f"Persisted video={args.video_id}; candidate/evidence rows={persisted}; "
        "canonical KB unchanged."
    )


if __name__ == "__main__":
    main()
