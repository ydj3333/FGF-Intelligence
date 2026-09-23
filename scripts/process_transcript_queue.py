#!/usr/bin/env python3
"""Process transcripts already stored in Supabase Storage. Never contacts YouTube."""
import argparse, json, os, subprocess, sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BUCKET = os.getenv("FGF_TRANSCRIPT_BUCKET", "fgf-video-transcripts")
BASE = os.getenv("FGF_SUPABASE_URL", "https://qdoixzfkkmvzjfkhzups.supabase.co").rstrip("/")

def key():
    k = os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("FGF_SUPABASE_SECRET_KEY")
    if not k:
        raise RuntimeError("Missing FGF_SUPABASE_SERVICE_ROLE_KEY")
    return k

def download(object_path, target):
    enc = "/".join(quote(p, safe="") for p in object_path.split("/"))
    k = key()
    req = Request(BASE + f"/storage/v1/object/{BUCKET}/{enc}",
                  headers={"apikey": k, "Authorization": f"Bearer {k}"})
    with urlopen(req, timeout=60) as r:
        target.write_bytes(r.read())

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--limit", type=int, default=10)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()

    root = Path("data/video_transcripts")
    root.mkdir(parents=True, exist_ok=True)
    index_path = Path("data/video_playlist_index.json")
    download("index/playlist_index.json", index_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))

    ready = []
    for v in index["videos"]:
        target = root / f"{v['video_id']}.txt"
        try:
            download(f"transcripts/{v['video_id']}.txt", target)
            ready.append(v)
        except Exception as e:
            print(f"SKIP {v['video_id']}: {e}")
        if len(ready) >= args.limit:
            break

    print(f"Downloaded {len(ready)} transcript(s) from Supabase Storage.")
    for v in ready:
        vid = v["video_id"]
        subprocess.run([sys.executable, "scripts/extract_claims_from_transcript.py",
                        "--video-id", vid], check=True)
        subprocess.run([sys.executable, "scripts/cross_reference_claims.py",
                        "--video-id", vid], check=True)
        cmd = [sys.executable, "scripts/update_video_database.py", "--video-id", vid]
        if args.apply:
            cmd.append("--apply")
        subprocess.run(cmd, check=True)

    subprocess.run([sys.executable, "scripts/generate_knowledge_snapshot.py"], check=True)
    print(f"Queue processing complete: processed={len(ready)}, apply={args.apply}")

if __name__ == "__main__":
    main()
