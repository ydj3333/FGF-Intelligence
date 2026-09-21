"""Synchronize the canonical Supabase claims corpus into data/knowledge.json.

Supabase is the canonical claim store. This exporter is intentionally
one-directional: it does not promote claims, resolve conflicts, or delete
historical knowledge. It exports the current claim rows, preserves the richer
metadata already stored with each claim, attaches lifecycle/temporal metadata,
validates identity/duplicates, and writes a deterministic corpus manifest.

Usage:
  python scripts/sync_corpus.py
  python scripts/sync_corpus.py --check

Required environment:
  FGF_SUPABASE_URL or SUPABASE_URL
  FGF_SUPABASE_SERVICE_ROLE_KEY or SUPABASE_SERVICE_ROLE_KEY
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "data" / "knowledge.json"
MANIFEST = ROOT / "data" / "knowledge_manifest.json"


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def env_credentials():
    base = os.getenv("FGF_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key = os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        raise RuntimeError(
            "Missing Supabase credentials; set FGF_SUPABASE_URL and "
            "FGF_SUPABASE_SERVICE_ROLE_KEY."
        )
    return base.rstrip("/"), key


def fetch_rows(base: str, key: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        params = urllib.parse.urlencode({
            "select": (
                "id,claim_key,claim,category,claim_type,season,version,tier,"
                "confidence,status,canonical,metadata,created_at,updated_at"
            ),
            "order": "created_at.asc,id.asc",
            "limit": "200",
            "offset": str(offset),
        })
        req = urllib.request.Request(
            f"{base}/rest/v1/claims?{params}",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            batch = json.load(response)
        rows.extend(batch)
        if len(batch) < 200:
            return rows
        offset += 200


def build_claim(row: Dict[str, Any], old_by_key: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    from claim_lifecycle import lifecycle_metadata

    metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
    existing = old_by_key.get(str(row.get("claim_key", "")), {})
    # Supabase fields are authoritative; existing snapshot fields are retained
    # only where the canonical row has not supplied the richer representation.
    merged = dict(existing)
    merged.update(metadata)
    merged.update({
        "Claim": row.get("claim", ""),
        "Category": row.get("category", ""),
        "Source": metadata.get("Source", existing.get("Source", "")),
        "Season/Version": " / ".join(
            x for x in (row.get("season") or "", row.get("version") or "") if x
        ),
        "Evidence Type": metadata.get("Evidence Type", row.get("claim_type", "")),
        "Evidence Tier": row.get("tier", ""),
        "Confidence": row.get("confidence", ""),
        "Status": row.get("status", ""),
        "Verification Status": metadata.get(
            "Verification Status",
            "Needs Review" if str(row.get("status", "")).lower() in
            ("under review", "candidate", "needs review") else "Unknown",
        ),
        "Timestamp": metadata.get("Timestamp", existing.get("Timestamp", "")),
        "Notes": metadata.get(
            "Notes",
            existing.get("Notes", ""),
        ),
        "Claim Type": row.get("claim_type", ""),
        "claim_key": row.get("claim_key", ""),
        "supabase_id": row.get("id", ""),
    })

    # Keep lifecycle metadata additive and deterministic.
    lifecycle = lifecycle_metadata(merged)
    merged["metadata"] = {
        **(metadata if isinstance(metadata, dict) else {}),
        **lifecycle,
    }
    return merged


def validate(rows: List[Dict[str, Any]]) -> None:
    keys = [str(r.get("claim_key", "")) for r in rows]
    claims = [norm(r.get("claim")) for r in rows]

    if any(not x for x in keys):
        raise RuntimeError("Supabase export contains a claim without claim_key.")
    if len(keys) != len(set(keys)):
        raise RuntimeError("Supabase export contains duplicate claim_key values.")
    if len(claims) != len(set(claims)):
        dupes = sorted({x for x in claims if claims.count(x) > 1})[:5]
        raise RuntimeError(f"Supabase export contains duplicate normalized claims: {dupes}")

    for row in rows:
        if not row.get("claim"):
            raise RuntimeError(f"Claim {row.get('claim_key')} has empty claim text.")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def checksum(claims: List[Dict[str, Any]]) -> str:
    payload = [
        {
            "claim_key": c.get("claim_key"),
            "Claim": c.get("Claim"),
            "Category": c.get("Category"),
            "Evidence Tier": c.get("Evidence Tier"),
            "Confidence": c.get("Confidence"),
            "Status": c.get("Status"),
            "metadata": c.get("metadata", {}),
        }
        for c in sorted(claims, key=lambda x: str(x.get("claim_key")))
    ]
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def export(check_only: bool = False) -> Dict[str, Any]:
    from claim_lifecycle import summarize_states

    base, key = env_credentials()
    current = json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    old_claims = current.get("claims", [])
    old_by_key = {
        str(c.get("claim_key")): c for c in old_claims if c.get("claim_key")
    }

    rows = fetch_rows(base, key)
    validate(rows)
    claims = [build_claim(row, old_by_key) for row in rows]
    state_counts = summarize_states(claims)

    generated = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    digest = checksum(claims)
    manifest = {
        "schema_version": 1,
        "source_of_truth": "supabase.public.claims",
        "supabase_project": base.split("//", 1)[-1].split(".", 1)[0],
        "claim_count": len(claims),
        "tier1_count": sum(
            1 for c in claims
            if str(c.get("Evidence Tier", "")).lower().startswith("tier 1")
        ),
        "lifecycle_counts": state_counts,
        "checksum": digest,
        "generated": generated,
        "synced_at_utc": datetime.now(timezone.utc).isoformat(),
    }

    result = {
        "supabase_claims": len(rows),
        "snapshot_claims": len(old_claims),
        "new_claims": max(0, len(claims) - len(old_claims)),
        "checksum": digest,
        "lifecycle_counts": state_counts,
        "check": check_only,
        "changed": canonical_json(old_claims) != canonical_json(claims),
    }

    if check_only:
        return result

    output = dict(current)
    output["claims"] = claims
    output["generated"] = generated
    stats = dict(output.get("stats") or {})
    stats["total_claims"] = len(claims)
    stats["tier1_claims"] = manifest["tier1_count"]
    output["stats"] = stats

    KNOWLEDGE.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    MANIFEST.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    result = export(check_only=args.check)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.check and result["changed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
