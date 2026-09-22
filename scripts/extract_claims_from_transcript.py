#!/usr/bin/env python3
"""Extract candidate claims from transcripts using LLM first, deterministic fallback second.

All extracted video claims are candidates/T3-style evidence and are NOT promoted
to canonical truth automatically.
"""
import argparse, json, os, re
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen

SYSTEM = """You extract evidence from FGF game-video transcripts.
Return JSON only: {"claims":[...]}.
Each claim must be atomic and traceable to the transcript.
Allowed claim_type: FACT, MECHANIC, RULE, CALCULATION, RECOMMENDATION, META ASSESSMENT, OPINION, RUMOR.
Do not upgrade authority. Creator statements are community evidence.
For each claim include: claim, category, claim_type, confidence, evidence_excerpt.
Never invent numbers, mechanics, timestamps, or conclusions not supported by the transcript."""

def llm_extract(text, title):
    key = os.getenv("FGF_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not key: return None
    endpoint = os.getenv("FGF_LLM_BASE_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("FGF_LLM_MODEL", "gpt-5.6-luna")
    body = json.dumps({
        "model": model, "temperature": 0,
        "messages": [{"role":"system","content":SYSTEM},
                     {"role":"user","content":f"Video title: {title}\n\nTranscript:\n{text}"}],
        "response_format": {"type":"json_object"}
    }).encode()
    req = Request(endpoint, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type":"application/json"})
    with urlopen(req, timeout=90) as r:
        payload = json.load(r)
    content = payload["choices"][0]["message"]["content"]
    obj = json.loads(content)
    return obj.get("claims", [])

def rule_extract(text):
    patterns = [
        (r"(.{0,80}?)(?:costs?|requires?)\s+(\d[\d,]*)\s+([A-Za-z][A-Za-z ]{1,30})", "Economy"),
        (r"(.{0,80}?)(?:provides?|gives?|adds?)\s+(\d+)%?\s+(?:bonus|boost|increase)\s+(?:to\s+)?(.{1,50})", "Champions"),
        (r"(.{0,80}?)(?:unlocks?|opens?)\s+(.{2,80})", "Progression"),
    ]
    out=[]
    for pat, cat in patterns:
        for m in re.finditer(pat, text, re.I):
            excerpt = " ".join(m.group(0).split())
            out.append({"claim": excerpt, "category":cat, "claim_type":"FACT", "confidence":0.35, "evidence_excerpt":excerpt})
    return out

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--video-id", required=True)
    p.add_argument("--index", default="data/video_playlist_index.json")
    args=p.parse_args()
    index=json.loads(Path(args.index).read_text(encoding="utf-8"))
    video=next((v for v in index["videos"] if v["video_id"]==args.video_id),None)
    if not video: raise SystemExit("Video not found in playlist index")
    text=Path(f"data/video_transcripts/{args.video_id}.txt").read_text(encoding="utf-8")
    try:
        claims=llm_extract(text, video["title"]) or []
        method="llm"
    except Exception as e:
        print(f"LLM extraction unavailable: {e}")
        claims=rule_extract(text); method="rule_fallback"
    normalized=[]
    for c in claims:
        normalized.append({
            "claim": str(c.get("claim","")).strip(),
            "category": c.get("category","Other"),
            "claim_type": c.get("claim_type","FACT"),
            "tier": 3,
            "provenance": f"YouTube video: {video['title']}",
            "source_url": video["video_url"],
            "confidence": float(c.get("confidence",0.5)),
            "status": "candidate",
            "evidence_excerpt": str(c.get("evidence_excerpt","")).strip(),
        })
    normalized=[c for c in normalized if c["claim"]]
    out={"schema_version":"1.0","video_id":args.video_id,"video_title":video["title"],
         "video_url":video["video_url"],"playlist_index":video["playlist_index"],
         "transcript_chars":len(text),"extraction_method":method,
         "claims_extracted":len(normalized),"claims":normalized,
         "extracted_at":datetime.now(timezone.utc).isoformat()}
    path=Path("data/video_claims"); path.mkdir(parents=True,exist_ok=True)
    (path/f"{args.video_id}_claims.json").write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Extracted {len(normalized)} candidate claims ({method})")

if __name__=="__main__":
    main()
