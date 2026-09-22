#!/usr/bin/env python3
"""Fetch a YouTube playlist index with resumable, batched metadata."""
import argparse, json, os, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen, Request

API = "https://www.googleapis.com/youtube/v3"

def api_get(resource, params):
    key = os.getenv("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not set")
    params = dict(params, key=key)
    req = Request(f"{API}/{resource}?{urlencode(params)}")
    with urlopen(req, timeout=30) as r:
        return json.load(r)

def iso8601_seconds(value):
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", value or "")
    if not m: return None
    h, mi, s = [int(x or 0) for x in m.groups()]
    return h*3600 + mi*60 + s

def fetch_playlist(playlist_id):
    videos, token = [], None
    while True:
        data = api_get("playlistItems", {
            "part": "snippet,contentDetails", "playlistId": playlist_id,
            "maxResults": 50, **({"pageToken": token} if token else {})
        })
        for item in data.get("items", []):
            sn = item.get("snippet", {})
            vid = item.get("contentDetails", {}).get("videoId") or sn.get("resourceId", {}).get("videoId")
            if not vid: continue
            videos.append({
                "playlist_index": len(videos)+1,
                "title": sn.get("title", ""),
                "description": sn.get("description", ""),
                "video_id": vid,
                "video_url": f"https://www.youtube.com/watch?v={vid}",
                "thumbnail": (sn.get("thumbnails", {}).get("high") or sn.get("thumbnails", {}).get("default", {})).get("url"),
                "published_at": sn.get("publishedAt"),
            })
        token = data.get("nextPageToken")
        if not token: break

    for i in range(0, len(videos), 50):
        ids = ",".join(v["video_id"] for v in videos[i:i+50])
        data = api_get("videos", {"part": "contentDetails,snippet", "id": ids})
        by_id = {x["id"]: x for x in data.get("items", [])}
        for v in videos[i:i+50]:
            x = by_id.get(v["video_id"], {})
            v["duration_iso8601"] = x.get("contentDetails", {}).get("duration")
            v["duration_seconds"] = iso8601_seconds(v.get("duration_iso8601"))
            v["channel_id"] = x.get("snippet", {}).get("channelId")
            v["channel_title"] = x.get("snippet", {}).get("channelTitle")
    return videos

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--playlist-id", required=True)
    p.add_argument("--output", default="data/video_playlist_index.json")
    args = p.parse_args()
    videos = fetch_playlist(args.playlist_id)
    out = {
        "schema_version": "1.0",
        "playlist_id": args.playlist_id,
        "total_videos": len(videos),
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "videos": videos,
    }
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Fetched {len(videos)} videos -> {args.output}")

if __name__ == "__main__":
    main()
