#!/usr/bin/env python3
"""Screenshot inbox: turn uploaded screenshots into database facts.

Drop images (png/jpg/webp) into one of these repository folders, e.g. from the
GitHub mobile app or github.com -> Add file -> Upload files:

  inbox/official/   posts from the official Instagram, Facebook, X or Discord   -> Tier 2, live
  inbox/ingame/     screenshots of in-game screens and notices                  -> Tier 1, "Under Review"
                    (Tier 1 always needs admin confirmation: never auto-promoted)
  inbox/community/  creator / community posts                                   -> Tier 3, live

Tip: name the file after its source and date, e.g. "instagram-2026-10-20-astral-party.jpg".

The AI first copies all readable text from the image, then extracts facts. A fact is
kept only if its quote appears in that text and its numbers appear there too. Facts
already known are skipped; facts contradicting Tier 1/2 evidence are held back as
"Conflicting". Processed images move to inbox/processed/<date>/ (kept as evidence).

Usage: python scripts/ingest_screenshots.py [--apply]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harvest_sources", ROOT / "scripts/harvest_sources.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)

INBOX = ROOT / "inbox"
FOLDERS = {
    "official": {"id": "INBOX-OFFICIAL", "name": "Official post screenshot (Instagram/Facebook/X/Discord)",
                 "tier": 2, "tier_label": "Tier 2 — Official Developer", "status": "Current"},
    "ingame": {"id": "INBOX-INGAME", "name": "In-game screenshot", "tier": 1,
               "tier_label": "Tier 1 — In-game UI", "status": "Under Review"},
    "community": {"id": "INBOX-COMMUNITY", "name": "Community screenshot", "tier": 3,
                  "tier_label": "Tier 3 — Creator/Community", "status": "Current"},
}
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}
MAX_PER_RUN = 15
MAX_BYTES = 15_000_000


def published_from(name: str) -> str:
    m = re.search(r"(20\d\d)[-_.](\d\d)[-_.](\d\d)", name)
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")


def run(apply: bool) -> dict:
    h = H.Harvest(apply, {"max_claims_per_page": 25}, {"pages": {}})
    repo = os.getenv("GITHUB_REPOSITORY", "")
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    done = 0
    for folder, src in FOLDERS.items():
        srep = h.source_report(src)
        for path in sorted((INBOX / folder).glob("*")) if (INBOX / folder).exists() else []:
            if path.suffix.lower() not in MIME or not path.is_file():
                continue
            if done >= MAX_PER_RUN:
                srep["notes"].append("limit reached; remaining images next run")
                break
            if path.stat().st_size > MAX_BYTES:
                srep["notes"].append(f"{path.name}: too large (max 15 MB)")
                continue
            done += 1
            srep["pages_seen"] += 1
            dest_rel = f"inbox/processed/{today}/{folder}-{path.name}"
            url = f"https://github.com/{repo}/blob/main/{dest_rel}" if repo else dest_rel
            page = {"url": url, "title": path.stem.replace("-", " ").replace("_", " "), "text": "",
                    "published": published_from(path.name), "images": [(path.read_bytes(), MIME[path.suffix.lower()])]}
            complete, info = h.process_page(src, page, srep, "")
            if not complete:
                continue          # AI unavailable: keep the image in the inbox and retry next run
            srep["pages_changed"] += 1
            if apply and h.writing:
                dest = ROOT / dest_rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), dest)
    h.report["pages_processed"] = done
    return h.report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    report = run(args.apply)
    md = H.summary_markdown(report).replace("FGF source harvest", "FGF screenshot inbox")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"inserted={report['inserted']}\n")
    print(md)


if __name__ == "__main__":
    main()
