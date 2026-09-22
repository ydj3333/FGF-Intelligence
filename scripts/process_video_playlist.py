#!/usr/bin/env python3
"""End-to-end resumable YouTube evidence ingestion pipeline."""
import argparse, json, subprocess, sys
from pathlib import Path

def run(cmd):
    print("\n$", " ".join(cmd)); subprocess.run(cmd, check=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--playlist-id",required=True)
    p.add_argument("--batch-size",type=int,default=10)
    p.add_argument("--delay-seconds",type=float,default=3)
    p.add_argument("--start",type=int,default=0)
    p.add_argument("--count",type=int,default=None)
    p.add_argument("--apply",action="store_true",help="Persist metadata/candidates to Supabase")
    args=p.parse_args()

    run([sys.executable,"scripts/fetch_playlist_index.py","--playlist-id",args.playlist_id])
    idx=json.loads(Path("data/video_playlist_index.json").read_text(encoding="utf-8"))
    videos=idx["videos"][args.start: args.start+args.count if args.count is not None else None]
    if not videos: raise SystemExit("No videos in selected range")

    # Download selected range without modifying the canonical index.
    temp=Path("data/video_playlist_batch.json")
    temp.write_text(json.dumps({**idx,"videos":videos,"total_videos":len(videos)},indent=2),encoding="utf-8")
    run([sys.executable,"scripts/download_transcripts.py","--index",str(temp),"--batch-size",str(args.batch_size),"--delay-seconds",str(args.delay_seconds)])

    for v in videos:
        if Path(f"data/video_transcripts/{v['video_id']}.txt").exists():
            run([sys.executable,"scripts/extract_claims_from_transcript.py","--video-id",v["video_id"]])
            run([sys.executable,"scripts/cross_reference_claims.py","--video-id",v["video_id"]])
            run([sys.executable,"scripts/update_video_database.py","--video-id",v["video_id"]]+(["--apply"] if args.apply else []))
    run([sys.executable,"scripts/generate_knowledge_snapshot.py"])
    print("\nPipeline complete. Canonical knowledge was not auto-promoted.")

if __name__=="__main__": main()
