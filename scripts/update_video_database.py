#!/usr/bin/env python3
"""Persist video metadata and candidate claims to Supabase/Postgres.

This intentionally stages claims as candidate_knowledge rather than silently
publishing them into canonical claims. Use --apply to write; no auto-promotion.
"""
import argparse, json, os, sys
from pathlib import Path
from datetime import datetime, timezone

def conn():
    try:
        import psycopg2
    except ImportError:
        raise RuntimeError("Install psycopg2-binary or use the SQL schema/REST ingestion path.")
    url=os.getenv("SUPABASE_DB_URL") or os.getenv("SUPABASE_CONNECTION_STRING")
    if not url: raise RuntimeError("SUPABASE_DB_URL/SUPABASE_CONNECTION_STRING is not set")
    return psycopg2.connect(url)

def main():
    p=argparse.ArgumentParser(); p.add_argument("--video-id",required=True); p.add_argument("--apply",action="store_true")
    args=p.parse_args()
    cross=json.loads(Path(f"data/video_claims/{args.video_id}_crossref.json").read_text(encoding="utf-8"))
    idx=json.loads(Path("data/video_playlist_index.json").read_text(encoding="utf-8"))
    video=next(v for v in idx["videos"] if v["video_id"]==args.video_id)
    claims=[x["video_claim"] for x in cross["new_candidates"]]
    if not args.apply:
        print(f"[DRY RUN] video={args.video_id} candidates={len(claims)}"); return
    db=conn(); cur=db.cursor()
    cur.execute("""INSERT INTO video_database
      (video_id, playlist_id, playlist_index, title, video_url, description, published_at,
       duration_seconds, channel_id, channel_title, processing_status, metadata)
      VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
      ON CONFLICT (video_id) DO UPDATE SET
       playlist_index=EXCLUDED.playlist_index,title=EXCLUDED.title,video_url=EXCLUDED.video_url,
       description=EXCLUDED.description,published_at=EXCLUDED.published_at,
       duration_seconds=EXCLUDED.duration_seconds,channel_id=EXCLUDED.channel_id,
       channel_title=EXCLUDED.channel_title,updated_at=now(),metadata=EXCLUDED.metadata
      RETURNING id""",
      (video["video_id"],idx["playlist_id"],video["playlist_index"],video["title"],video["video_url"],
       video.get("description",""),video.get("published_at"),video.get("duration_seconds"),
       video.get("channel_id"),video.get("channel_title"),"claims_extracted",
       json.dumps({"extraction_file":f"data/video_claims/{args.video_id}_claims.json"})))
    video_db_id=cur.fetchone()[0]
    for c in claims:
        cur.execute("""INSERT INTO video_claim_candidates
          (video_database_id, video_id, claim_text, category, claim_type, evidence_tier,
           confidence, status, source_url, evidence_excerpt, metadata)
          VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
          ON CONFLICT (video_id, claim_text) DO UPDATE SET
           confidence=EXCLUDED.confidence, evidence_excerpt=EXCLUDED.evidence_excerpt,
           updated_at=now()""",
          (video_db_id,video["video_id"],c["claim"],c.get("category"),c.get("claim_type"),
           c.get("tier",3),c.get("confidence",0.5),"candidate",video["video_url"],
           c.get("evidence_excerpt",""),json.dumps({"pipeline":"youtube_transcript"})))
    db.commit(); cur.close(); db.close()
    print(f"Persisted video {video['video_id']} and {len(claims)} candidate claims; canonical KB unchanged.")

if __name__=="__main__": main()
