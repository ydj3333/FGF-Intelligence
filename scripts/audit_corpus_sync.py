"""Audit and optionally synchronize the Supabase claims corpus into data/knowledge.json.

Default behavior is read-only. Use --apply only after reviewing the audit.
Environment:
  FGF_SUPABASE_URL (or SUPABASE_URL)
  FGF_SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_SERVICE_ROLE_KEY)
"""
import argparse, json, os, re, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE = ROOT / "data" / "knowledge.json"

def norm(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()

def supabase_rows(base, key):
    rows=[]
    offset=0
    while True:
        params=urllib.parse.urlencode({
            "select":"id,claim_key,claim,category,claim_type,season,version,tier,confidence,status,canonical,metadata,created_at,updated_at",
            "order":"created_at.asc,id.asc",
            "limit":"200",
            "offset":str(offset),
        })
        req=urllib.request.Request(
            base.rstrip("/") + "/rest/v1/claims?" + params,
            headers={"apikey":key,"Authorization":"Bearer "+key},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            batch=json.load(response)
        rows.extend(batch)
        if len(batch)<200:
            return rows
        offset += 200

def to_knowledge(row):
    meta=row.get("metadata") or {}
    source=meta.get("source","")
    season=row.get("season") or ""
    version=row.get("version") or ""
    season_version=" / ".join(x for x in (season,version) if x)
    return {
        "Claim": row.get("claim",""),
        "Category": row.get("category",""),
        "Source": source,
        "Season/Version": season_version,
        "Evidence Type": row.get("claim_type",""),
        "Evidence Tier": row.get("tier",""),
        "Confidence": row.get("confidence",""),
        "Status": row.get("status",""),
        "Verification Status": "Needs Review" if str(row.get("status","")).lower() in ("under review","candidate") else "Unknown",
        "Timestamp": "",
        "Notes": "Imported from Supabase claims corpus. claim_key=%s; canonical=%s; created_at=%s; updated_at=%s" % (
            row.get("claim_key",""), row.get("canonical"), row.get("created_at",""), row.get("updated_at","")
        ),
        "Claim Type": row.get("claim_type",""),
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--apply",action="store_true")
    args=ap.parse_args()
    base=os.getenv("FGF_SUPABASE_URL") or os.getenv("SUPABASE_URL")
    key=os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not base or not key:
        raise SystemExit("Missing Supabase credentials; audit requires FGF_SUPABASE_URL and FGF_SUPABASE_SERVICE_ROLE_KEY.")
    data=json.loads(KNOWLEDGE.read_text(encoding="utf-8"))
    existing=data.get("claims",[])
    existing_keys={norm(c.get("Claim")) for c in existing}
    rows=supabase_rows(base,key)
    missing=[r for r in rows if norm(r.get("claim")) not in existing_keys]
    summary={
        "supabase_claims":len(rows),
        "production_claims":len(existing),
        "missing_claims":len(missing),
        "missing_by_tier":{},
        "missing_by_status":{},
        "missing_by_category":{},
        "apply":args.apply,
    }
    for r in missing:
        for field,keyname in (("tier","missing_by_tier"),("status","missing_by_status"),("category","missing_by_category")):
            value=r.get(field) or "NULL"
            summary[keyname][value]=summary[keyname].get(value,0)+1
    print(json.dumps(summary,indent=2,ensure_ascii=False))
    if args.apply and missing:
        existing.extend(to_knowledge(r) for r in missing)
        data["claims"]=existing
        data["generated"]="2026-09-20"
        KNOWLEDGE.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
        print("Applied %d new claims; corpus is now %d." % (len(missing),len(existing)))

if __name__=="__main__":
    main()
