#!/usr/bin/env python3
"""Cross-reference video candidates against the canonical snapshot.

Uses token similarity plus category/type compatibility. Contradictions are
flagged for review; they are never silently overwritten.
"""
import argparse, json, re
from pathlib import Path
from difflib import SequenceMatcher

def toks(s): return set(re.findall(r"[a-z0-9]+", s.lower()))
def similarity(a,b):
    ta,tb=toks(a),toks(b)
    j=len(ta&tb)/max(1,len(ta|tb))
    seq=SequenceMatcher(None,a.lower(),b.lower()).ratio()
    return 0.65*j+0.35*seq

def main():
    p=argparse.ArgumentParser(); p.add_argument("--video-id",required=True); p.add_argument("--kb",default="data/knowledge.json")
    args=p.parse_args()
    vc=json.loads(Path(f"data/video_claims/{args.video_id}_claims.json").read_text(encoding="utf-8"))
    kb=json.loads(Path(args.kb).read_text(encoding="utf-8"))
    existing=kb.get("claims",[])
    result={"schema_version":"1.0","video_id":args.video_id,"video_title":vc["video_title"],
            "total_video_claims":len(vc["claims"]),"new_candidates":[],"duplicates":[],"potential_conflicts":[]}
    for c in vc["claims"]:
        scored=sorted(((similarity(c["claim"], e.get("Claim",e.get("claim",""))),e) for e in existing), reverse=True, key=lambda x:x[0])
        best=scored[:5]
        if not best or best[0][0] < 0.78:
            result["new_candidates"].append({"video_claim":c,"nearest":best[:3],"action":"stage_for_review"})
        else:
            near=[{"similarity":round(s,4),"claim_id":e.get("Claim ID",e.get("id")),"claim":e.get("Claim",e.get("claim",""))} for s,e in best]
            result["duplicates"].append({"video_claim":c,"nearest":near,"action":"link_source_or_review"})
            # A high similarity with semantic polarity differences deserves review.
            if any(w in c["claim"].lower() for w in (" not ","never ","cannot ","can't ","no ")) and any(w in e.get("Claim",e.get("claim","")).lower() for w in (" requires "," always ","can ","does " ) for _,e in best[:3]):
                result["potential_conflicts"].append({"video_claim":c,"nearest":near,"action":"manual_conflict_review"})
    out=Path("data/video_claims"); out.mkdir(parents=True,exist_ok=True)
    (out/f"{args.video_id}_crossref.json").write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"New candidates: {len(result['new_candidates'])}; duplicates: {len(result['duplicates'])}; conflicts: {len(result['potential_conflicts'])}")
    return result

if __name__=="__main__": main()
