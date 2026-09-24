#!/usr/bin/env python3
"""Acquire YouTube subtitles outside GitHub Actions and upload them to Supabase Storage."""
import argparse, json, os, re, subprocess, sys
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import HTTPError

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
    try:
        with urlopen(req, timeout=60) as r:
            return r.read()
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"Supabase HTTP {e.code}: {detail}")
        raise RuntimeError(f"Supabase HTTP {e.code}: {detail}") from e

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

def list_remote_transcripts():
    """Return video IDs whose transcripts already exist in Supabase Storage."""
    raw = request("POST", f"/storage/v1/object/list/{BUCKET}", {
        "prefix": "transcripts/",
        "limit": 1000,
        "offset": 0,
        "sortBy": {"column": "name", "order": "asc"},
    })
    items = json.loads(raw.decode("utf-8"))
    ids = set()
    for item in items:
        name = item.get("name", "")
        if name.startswith("transcripts/") and name.endswith(".txt"):
            ids.add(name[len("transcripts/"):-4])
    return ids

def upload(path, object_path, content_type):
    encoded = "/".join(quote(p, safe="") for p in object_path.split("/"))
    k = key()
    body = Path(path).read_bytes()
    req = Request(
        BASE + "/storage/v1/object/" + BUCKET + "/" + encoded,
        data=body,
        method="POST",
        headers={
            "apikey": k,
            "Authorization": f"Bearer {k}",
            "Content-Type": content_type,
            "x-upsert": "true",
        },
    )
    try:
        with urlopen(req, timeout=60) as r:
            return r.read()
    except HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")
        print(f"Supabase upload HTTP {e.code}: {detail}")
        raise RuntimeError(f"Supabase upload HTTP {e.code}: {detail}") from e


_WHISPER_MODEL = None

def transcribe_audio_local(audio_path):
    global _WHISPER_MODEL
    from faster_whisper import WhisperModel
    if _WHISPER_MODEL is None:
        model_name = os.getenv('FGF_WHISPER_MODEL', 'small')
        device = os.getenv('FGF_WHISPER_DEVICE', 'cpu')
        compute_type = os.getenv('FGF_WHISPER_COMPUTE_TYPE', 'float32')
        print(f'Loading faster-whisper model={model_name}, device={device}, compute_type={compute_type}', flush=True)
        _WHISPER_MODEL = WhisperModel(model_name, device=device, compute_type=compute_type, cpu_threads=4, num_workers=1)
        print('Whisper model loaded. Starting transcription...', flush=True)
    else:
        print('Whisper model already loaded. Starting transcription...', flush=True)
    segments, info = _WHISPER_MODEL.transcribe(str(audio_path), language='en', vad_filter=True, beam_size=1, best_of=1, temperature=0, condition_on_previous_text=False)
    parts = []
    for segment in segments:
        text_part = segment.text.strip()
        if text_part:
            parts.append(text_part)
            print(f'Transcribed through {segment.end:.0f}s', flush=True)
    print(f'Transcription complete: {len(parts)} segments', flush=True)
    return ' '.join(parts).strip()

def acquire_audio_transcript(vid, work):
    audio = work / f'{vid}.mp3'
    cmd = ['yt-dlp', '--extract-audio', '--audio-format', 'mp3', '--output', str(work / (vid + '.%(ext)s')), f'https://www.youtube.com/watch?v={vid}']
    subprocess.run(cmd, check=True)
    if not audio.exists():
        raise RuntimeError('Audio download completed but MP3 was not found')
    text = transcribe_audio_local(audio)
    txt = work / f'{vid}.txt'
    txt.write_text(text, encoding='utf-8')
    return txt

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
    remote_transcripts = list_remote_transcripts()
    print(f"Supabase already has {len(remote_transcripts)} transcript(s); existing remote transcripts will be skipped.", flush=True)

    for n, video in enumerate(videos, 1):
        vid = video["video_id"]

        if vid in remote_transcripts:
            print(f"[{n}/{len(videos)}] ALREADY IN SUPABASE: {vid} — skipping acquisition", flush=True)
            continue

        work = out / vid
        work.mkdir(parents=True, exist_ok=True)
        txt = work / f"{vid}.txt"

        if not txt.exists():
            candidates = list(work.glob(f'{vid}.*.vtt')) + list(work.glob('*.vtt'))
            if candidates:
                text_value = vtt_to_text(candidates[0])
                if text_value:
                    txt.write_text(text_value, encoding='utf-8')
                    print(f'[{n}/{len(videos)}] Subtitle transcript found: {vid}')
                else:
                    print(f'[{n}/{len(videos)}] Empty subtitle; falling back to local audio transcription: {vid}')
                    try:
                        txt = acquire_audio_transcript(vid, work)
                    except Exception as e:
                        failures.append({'video_id': vid, 'error': f'audio transcription: {e}'})
                        print(f'[{n}/{len(videos)}] FAIL {vid}: {e}')
                        continue
            else:
                try:
                    print(f'[{n}/{len(videos)}] No usable subtitle; falling back to local audio transcription: {vid}')
                    txt = acquire_audio_transcript(vid, work)
                except Exception as e:
                    failures.append({'video_id': vid, 'error': f'audio transcription: {e}'})
                    print(f'[{n}/{len(videos)}] FAIL {vid}: {e}')
                    continue
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
