#!/usr/bin/env python3
"""Generate an auditable candidate knowledge snapshot.

Canonical data/knowledge.json is never overwritten by this script.
"""
import argparse, json
from pathlib import Path
from datetime import datetime, timezone

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input-dir",default="data/video_claims")
    p.add_argument("--output",default="data/video_candidate_knowledge_snapshot.json")
    args=p.parse_args()
    rows=[]
    for path in sorted(Path(args.input_dir).glob("*_claims.json")):
        try:
            data=json.loads(path.read_text(encoding="utf-8"))
            for c in data.get("claims",[]):
                rows.append({**c,"video_id":data["video_id"],"video_title":data["video_title"],
                             "extracted_at":data.get("extracted_at")})
        except Exception as e:
            print(f"Skipping {path}: {e}")
    out={"schema_version":"1.0","generated_at":datetime.now(timezone.utc).isoformat(),
         "canonical_publish_required":True,"candidate_count":len(rows),"claims":rows}
    Path(args.output).write_text(json.dumps(out,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Candidate snapshot: {len(rows)} claims -> {args.output}")

if __name__=="__main__": main()
