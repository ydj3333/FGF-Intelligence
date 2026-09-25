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

def supabase_get(path):
    k = key()
    req = Request(BASE + path, headers={"apikey": k, "Authorization": f"Bearer {k}"})
    with urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode() or "[]")

def processed_video_ids():
    try:
        rows = supabase_get("/rest/v1/video_database?select=video_id&processing_status=eq.persisted_candidates")
        return {r["video_id"] for r in rows if r.get("video_id")}
    except Exception as e:
        print(f"Processed-state check unavailable: {e}")
        return set()

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
    p.add_argument("--playlist-id", default=os.getenv("FGF_PLAYLIST_ID"), help="Playlist ID to process; omitted uses the legacy first-playlist index.")
    args = p.parse_args()

    root = Path("data/video_transcripts")
    root.mkdir(parents=True, exist_ok=True)
    index_path = Path("data/video_playlist_index.json")
    object_path = f"playlists/{args.playlist_id}/index.json" if args.playlist_id else "index/playlist_index.json"
    download(object_path, index_path)
    index = json.loads(index_path.read_text(encoding="utf-8"))

    processed = processed_video_ids()
    ready = []
    for v in index["videos"]:
        if v["video_id"] in processed:
            continue
        target = root / f"{v['video_id']}.txt"
        try:
            download(f"transcripts/{v['video_id']}.txt", target)
            ready.append(v)
        except Exception as e:
            print(f"SKIP {v['video_id']}: {e}")
        if len(ready) >= args.limit:
            break

    print(f"Downloaded {len(ready)} new transcript(s) from Supabase Storage; skipped {len(processed)} already processed.")
    failures = []
    succeeded = 0
    for v in ready:
        vid = v["video_id"]
        try:
            subprocess.run([sys.executable, "scripts/extract_claims_from_transcript.py",
                            "--video-id", vid], check=True)
            subprocess.run([sys.executable, "scripts/cross_reference_claims.py",
                            "--video-id", vid], check=True)
            cmd = [sys.executable, "scripts/update_video_database.py", "--video-id", vid]
            if args.apply:
                cmd.append("--apply")
            subprocess.run(cmd, check=True)
            succeeded += 1
            print(f"SUCCESS {vid}")
        except subprocess.CalledProcessError as e:
            failures.append({"video_id": vid, "stage": "extract/cross-reference/update", "returncode": e.returncode})
            print(f"FAILED {vid}: subprocess exit code {e.returncode}; continuing with remaining videos.", flush=True)
        except Exception as e:
            failures.append({"video_id": vid, "stage": "queue", "error": str(e)})
            print(f"FAILED {vid}: {e}; continuing with remaining videos.", flush=True)

    subprocess.run([sys.executable, "scripts/generate_knowledge_snapshot.py"], check=True)
    print(json.dumps({
        "queue_complete": True,
        "playlist_id": args.playlist_id or index.get("playlist_id"),
        "downloaded": len(ready),
        "succeeded": succeeded,
        "failed": failures,
        "apply": args.apply,
    }, indent=2))

if __name__ == "__main__":
    main()
