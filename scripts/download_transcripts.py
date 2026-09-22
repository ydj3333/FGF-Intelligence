#!/usr/bin/env python3
"""Download YouTube transcripts with resumability and failure manifests."""
import argparse, json, time
from pathlib import Path

def fetch(video_id, languages):
    from youtube_transcript_api import YouTubeTranscriptApi
    api = YouTubeTranscriptApi()
    # Support current and older youtube-transcript-api APIs.
    if hasattr(api, "fetch"):
        return api.fetch(video_id, languages=languages)
    return YouTubeTranscriptApi.get_transcript(video_id, languages=languages)

def normalize(items):
    rows = []
    for x in items:
        if isinstance(x, dict):
            rows.append({"text": x.get("text", ""), "start": x.get("start"), "duration": x.get("duration")})
        else:
            rows.append({"text": getattr(x, "text", ""), "start": getattr(x, "start", None), "duration": getattr(x, "duration", None)})
    return rows

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--index", default="data/video_playlist_index.json")
    p.add_argument("--batch-size", type=int, default=10)
    p.add_argument("--delay-seconds", type=float, default=3)
    p.add_argument("--languages", nargs="+", default=["en"])
    args = p.parse_args()
    data = json.loads(Path(args.index).read_text(encoding="utf-8"))
    outdir = Path("data/video_transcripts"); outdir.mkdir(parents=True, exist_ok=True)
    failures = []
    videos = data["videos"]
    for i in range(0, len(videos), args.batch_size):
        batch = videos[i:i+args.batch_size]
        print(f"Batch {i//args.batch_size+1}: {i+1}-{i+len(batch)}")
        for v in batch:
            vid = v["video_id"]
            txt = outdir / f"{vid}.txt"
            meta = outdir / f"{vid}.json"
            err = outdir / f"{vid}.error.json"
            if txt.exists() and meta.exists():
                continue
            try:
                rows = normalize(fetch(vid, args.languages))
                text = "\n".join(r["text"] for r in rows).strip()
                txt.write_text(text, encoding="utf-8")
                meta.write_text(json.dumps({"video_id": vid, "language": args.languages[0], "segments": rows}, indent=2), encoding="utf-8")
                if err.exists(): err.unlink()
                print(f"  OK {vid}")
            except Exception as e:
                payload = {"video_id": vid, "error": type(e).__name__, "message": str(e)}
                err.write_text(json.dumps(payload, indent=2), encoding="utf-8")
                failures.append(payload)
                print(f"  FAIL {vid}: {e}")
            time.sleep(args.delay_seconds)
    Path("data/video_transcripts/manifest.json").write_text(json.dumps({
        "processed": len(videos)-len(failures), "failed": len(failures), "failures": failures
    }, indent=2), encoding="utf-8")

if __name__ == "__main__":
    main()
