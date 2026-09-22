#!/usr/bin/env python3
"""Cross-reference YouTube candidates against the canonical/current evidence.

Governance:
- Tier 1/2 evidence takes precedence.
- With no Tier 1/2 match, the video claim is Tier 3 crowd/community
  additional data and remains a candidate.
- Contradictions are preserved for evaluation; nothing is overwritten.
"""
import argparse, json, re
from pathlib import Path
from difflib import SequenceMatcher

from youtube_evidence_governance import classify_against_existing


def toks(s):
    return set(re.findall(r"[a-z0-9]+", s.lower()))


def similarity(a, b):
    ta, tb = toks(a), toks(b)
    j = len(ta & tb) / max(1, len(ta | tb))
    seq = SequenceMatcher(None, a.lower(), b.lower()).ratio()
    return 0.65 * j + 0.35 * seq


def tier_value(e):
    raw = e.get("tier", e.get("Evidence Tier", e.get("evidence_tier")))
    try:
        return int(str(raw).lower().replace("tier", "").strip().split()[0])
    except (ValueError, IndexError, AttributeError):
        return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--video-id", required=True)
    p.add_argument("--kb", default="data/knowledge.json")
    args = p.parse_args()

    vc = json.loads(
        Path(f"data/video_claims/{args.video_id}_claims.json").read_text(encoding="utf-8")
    )
    kb = json.loads(Path(args.kb).read_text(encoding="utf-8"))
    existing = kb.get("claims", [])

    result = {
        "schema_version": "1.1",
        "video_id": args.video_id,
        "video_title": vc["video_title"],
        "total_video_claims": len(vc["claims"]),
        "claims": [],
        "new_candidates": [],
        "duplicates": [],
        "supporting_evidence": [],
        "potential_conflicts": [],
    }

    for c in vc["claims"]:
        scored = sorted(
            (
                (similarity(c["claim"], e.get("Claim", e.get("claim", ""))), e)
                for e in existing
            ),
            reverse=True,
            key=lambda x: x[0],
        )
        best = scored[:10]
        relevant = [e for s, e in best if s >= 0.58]

        decision = classify_against_existing(
            existing_claims=[
                {
                    "tier": tier_value(e),
                    "status": e.get("Status", e.get("status")),
                    "claim": e.get("Claim", e.get("claim", "")),
                }
                for e in relevant
            ],
            extracted_claim=c,
        )

        item = {
            **c,
            "evidence_tier": 3,
            "status": decision.status,
            "canonical": False,
            "classification": decision.classification,
            "user_warning": decision.user_warning,
            "governance_reason": decision.reason,
            "nearest": [
                {
                    "similarity": round(s, 4),
                    "claim_id": e.get("Claim ID", e.get("id")),
                    "claim": e.get("Claim", e.get("claim", "")),
                    "tier": tier_value(e),
                    "status": e.get("Status", e.get("status")),
                    "canonical": e.get("Canonical", e.get("canonical")),
                }
                for s, e in best[:5]
            ],
        }
        result["claims"].append(item)

        if decision.status == "conflict_candidate":
            result["potential_conflicts"].append(item)
        elif decision.status == "supporting_evidence":
            result["supporting_evidence"].append(item)
        elif best and best[0][0] >= 0.78:
            result["duplicates"].append(item)
        else:
            result["new_candidates"].append(item)

    out = Path("data/video_claims")
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.video_id}_crossref.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(
        f"Claims={len(result['claims'])}; "
        f"new={len(result['new_candidates'])}; "
        f"supporting={len(result['supporting_evidence'])}; "
        f"duplicates={len(result['duplicates'])}; "
        f"conflicts={len(result['potential_conflicts'])}"
    )


if __name__ == "__main__":
    main()
