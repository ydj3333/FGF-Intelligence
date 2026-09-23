#!/usr/bin/env python3
"""Acquire YouTube subtitles outside GitHub Actions and upload them to Supabase Storage."""
import argparse, json, os, re, subprocess, sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

BUCKET = os.getenv("FGF_TRANSCRIPT_BUCKET", "fgf-video-transcripts")
BASE = os.getenv("FGF_SUPABASE_URL", "https://qdoixzfkkmvzjfkhzups.supabase.co").rstrip("/")

def key():
    k = os.getenv("FGF_SUPABASE_SECRET_KEY") or os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY")
    if not k:
        raise RuntimeError("Set FGF_SUPABASE_SERVICE_ROLE_KEY.")
    return k

def request(method, path, payload=None, raw=False, content_type="application/json"):
    k = key()
    body = payload if raw else (json.dumps(payload).encode() if payload is not None else None)
    req = Request(BASE + path, data=body, method=method, headers={
        "apikey": k, "Authorization": f"Bearer {k}", "Content-Type": content_type
    })
    with urlopen(req, timeout=60) as r:
        return r.read()

def ensure_bucket():
    try:
        request("POST", "/storage/v1/bucket", {
            "id": BUCKET, "name": BUCKET, "public": False,
            "allowedMimeTypes": ["text/plain", "text/vtt", "application/json"]
        })
        print(f"Created bucket {BUCKET}")
    except Exception as e:
        if "already" not in str(e).lower() and "duplicate" not in str(e).lower():
            print(f"Bucket check notice: {e}")

def upload(path, object_path, content_type):
    encoded = "/".join(quote(p, safe="") for p in object_path.split("/"))
    request("POST", f"/storage/v1/object/{BUCKET}/{encoded}",
            Path(path).read_bytes(), raw=True, content_type=content_type)

def vtt_to_text(path):
    lines = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        s = line.strip()
        if not s or s == "WEBVTT" or "-->" in s or re.fullmatch(r"\d+", s):
            continue
        s = re.sub(r"<[^>]+>", "", s)
        if s and (not lines or lines[-1] != s):
            lines.append(s)
    return "\n".join(lines).strip()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--playlist-id", required=True)
    p.add_argument("--start", type=int, default=0)
    p.add_argument("--count", type=int, default=None)
    p.add_argument("--output-dir", default="data/acquired_transcripts")
    p.add_argument("--proxy", default=os.getenv("FGF_YTDLP_PROXY"))
    p.add_argument("--delay-seconds", type=float, default=12)
    p.add_argument("--max-retries", type=int, default=4)
    p.add_argument("--rate-limit-base", type=float, default=45)
    p.add_argument("--max-retries", type=int, default=4)
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    subprocess.run([
        sys.executable, "scripts/fetch_playlist_index.py",
        "--playlist-id", args.playlist_id
    ], check=True)

    index = json.loads(Path("data/video_playlist_index.json").read_text(encoding="utf-8"))
    videos = index["videos"][args.start:args.start + args.count if args.count is not None else None]
    if not videos:
        raise SystemExit("No videos selected.")

    batch_index = {**index, "videos": videos, "total_videos": len(videos)}
    (out / "playlist_index.json").write_text(json.dumps(batch_index, indent=2), encoding="utf-8")
    ensure_bucket()
    upload(out / "playlist_index.json", "index/playlist_index.json", "application/json")

    failures = []
    for n, video in enumerate(videos, 1):
        vid = video["video_id"]
        work = out / vid
        work.mkdir(parents=True, exist_ok=True)
        txt = work / f"{vid}.txt"

        if not txt.exists():
            cmd = [
                "yt-dlp", "--skip-download", "--write-subs", "--write-auto-subs",
                "--sub-langs", "en,en-US,en-GB", "--sub-format", "vtt",
                "--output", str(work / f"{vid}.%(ext)s"),
                f"https://www.youtube.com/watch?v={vid}"
            ]
            if args.proxy:
                cmd[1:1] = ["--proxy", args.proxy]
            success = False
            last_error = None
            for attempt in range(1, args.max_retries + 1):
                try:
                    subprocess.run(cmd, check=True)
                    success = True
                    break
                except Exception as e:
                    last_error = e
                    msg = str(e)
                    if "429" in msg or "Too Many Requests" in msg:
                        wait = min(300, args.rate_limit_base * attempt)
                    else:
                        wait = min(180, max(15, args.delay_seconds * attempt))
                    print(f"[{n}/{len(videos)}] RETRY {vid} attempt {attempt}/{args.max_retries}; waiting {wait:.0f}s")
                    if attempt < args.max_retries:
                        import random, time
                        time.sleep(wait + random.uniform(0, min(15, args.delay_seconds)))
            if not success:
                failures.append({"video_id": vid, "error": str(last_error)})
                print(f"[{n}/{len(videos)}] FAIL {vid}: {last_error}")
                continue
            candidates = list(work.glob(f"{vid}.*.vtt"))
            if not candidates:
                candidates = list(work.glob("*.vtt"))
            if not candidates:
                failures.append({"video_id": vid, "error": "No VTT subtitle file produced"})
                print(f"[{n}/{len(videos)}] FAIL {vid}: no subtitles")
                continue
            txt.write_text(vtt_to_text(candidates[0]), encoding="utf-8")

        try:
            upload(txt, f"transcripts/{vid}.txt", "text/plain")
            meta = work / f"{vid}.json"
            meta.write_text(json.dumps(video, indent=2, ensure_ascii=False), encoding="utf-8")
            upload(meta, f"metadata/{vid}.json", "application/json")
            print(f"[{n}/{len(videos)}] READY {vid}")
        except Exception as e:
            failures.append({"video_id": vid, "error": f"upload: {e}"})
            print(f"[{n}/{len(videos)}] FAIL-UPLOAD {vid}: {e}")

        import time
        import random, time
        time.sleep(max(0, args.delay_seconds) + random.uniform(0, min(10, args.delay_seconds)))

    manifest = {"playlist_id": args.playlist_id, "selected": len(videos),
                "ready": len(videos)-len(failures), "failed": len(failures),
                "failures": failures, "bucket": BUCKET}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    upload(out / "manifest.json", "manifests/latest.json", "application/json")
    print(json.dumps(manifest, indent=2))

if __name__ == "__main__":
    main()
