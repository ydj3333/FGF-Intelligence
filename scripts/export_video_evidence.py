#!/usr/bin/env python3
"""Export the YouTube candidate facts (video_claim_candidates + video_database) for the app.

The old server read these live from Supabase; the app is static, so the publish
workflow exports them into data/video_evidence.json just before building. They
enter the app as Tier 3 "from a creator video, not yet verified" evidence that
ranks below core facts (core objectives: YouTube is enrichment, never canonical).

Rejected/superseded/invalid rows are left out. Nothing is written to the database.
Without a Supabase key the script keeps any existing file and exits cleanly.

Usage: python scripts/export_video_evidence.py [--out data/video_evidence.json]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BAD = {"rejected", "superseded", "invalid", "archived"}


def get_all(base: str, key: str, table: str, select: str) -> list:
    rows, offset = [], 0
    while True:
        q = urllib.parse.urlencode({"select": select, "order": "id.asc", "limit": "1000", "offset": str(offset)})
        req = urllib.request.Request(f"{base}/rest/v1/{table}?{q}", headers={"apikey": key, "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=60) as r:
            batch = json.loads(r.read().decode("utf-8") or "[]")
        rows.extend(batch)
        if len(batch) < 1000:
            return rows
        offset += 1000


def norm(s) -> str:
    return " ".join(str(s or "").lower().split())


def export(base: str, key: str) -> dict:
    videos = get_all(base, key, "video_database", "id,video_id,title,video_url,published_at,channel_title,processing_status")
    cands = get_all(base, key, "video_claim_candidates",
                    "id,video_database_id,video_id,claim_text,category,claim_type,evidence_tier,confidence,status,source_url,evidence_excerpt")
    by_id = {str(v.get("id")): v for v in videos}
    by_vid = {str(v.get("video_id")): v for v in videos if v.get("video_id")}
    out, seen = [], set()
    for c in cands:
        text = " ".join(str(c.get("claim_text") or "").split())
        if not (12 <= len(text) <= 400) or norm(c.get("status")) in BAD:
            continue
        v = by_id.get(str(c.get("video_database_id"))) or by_vid.get(str(c.get("video_id"))) or {}
        if norm(v.get("processing_status")) in BAD:
            continue
        k = norm(text)
        if k in seen:
            continue
        seen.add(k)
        try:
            tier = max(3, int(c.get("evidence_tier") or 3))   # video evidence is never above Tier 3 here
        except (TypeError, ValueError):
            tier = 3
        out.append({
            "claim": text, "category": c.get("category") or "General", "claim_type": c.get("claim_type") or "",
            "tier": tier, "confidence": c.get("confidence"),
            "url": c.get("source_url") or v.get("video_url") or (f"https://www.youtube.com/watch?v={c.get('video_id')}" if c.get("video_id") else ""),
            "video_title": v.get("title") or "", "channel": v.get("channel_title") or "",
            "published": str(v.get("published_at") or "")[:10], "excerpt": " ".join(str(c.get("evidence_excerpt") or "").split())[:300],
        })
    return {"exported_utc": datetime.now(timezone.utc).isoformat(), "videos": len(videos), "candidates": out}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data/video_evidence.json"))
    args = ap.parse_args()
    base = (os.getenv("FGF_SUPABASE_URL") or "").rstrip("/")
    key = os.getenv("FGF_SUPABASE_SECRET_KEY") or os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY") or ""
    if not base or not key:
        print("::warning::No Supabase key: building without fresh YouTube evidence.")
        return 0
    try:
        data = export(base, key)
    except Exception as e:  # the app still builds from the core facts
        print(f"::warning::YouTube evidence export failed ({type(e).__name__}: {str(e)[:160]}); building without it.")
        return 0
    Path(args.out).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Exported {len(data['candidates'])} YouTube candidate facts from {data['videos']} videos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
