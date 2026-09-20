"""Verify the live Supabase FGF claims corpus.

Uses the Supabase REST API and only standard-library Python.
Required environment:
  SUPABASE_URL
  SUPABASE_KEY

Never commit credentials to the repository.
"""
import json
import os
import sys
import urllib.parse
import urllib.request


def rest_count(base_url, key, params):
    query = urllib.parse.urlencode(params)
    url = base_url.rstrip("/") + "/rest/v1/claims?" + query
    request = urllib.request.Request(
        url,
        headers={
            "apikey": key,
            "Authorization": "Bearer " + key,
            "Prefer": "count=exact",
        },
        method="HEAD",
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        content_range = response.headers.get("Content-Range", "")
    total = content_range.rsplit("/", 1)[-1] if "/" in content_range else "*"
    return int(total) if total.isdigit() else None


def main():
    base_url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not base_url or not key:
        print("ERROR: set SUPABASE_URL and SUPABASE_KEY", file=sys.stderr)
        return 2

    checks = {
        "total_claims": {"select": "id", "limit": "0"},
        "tier1_claims": {"select": "id", "tier": "ilike.Tier 1%", "limit": "0"},
        "confirmed_claims": {"select": "id", "status": "ilike.confirmed", "limit": "0"},
        "under_review_claims": {"select": "id", "status": "ilike.under review", "limit": "0"},
        "conflicting_claims": {"select": "id", "status": "ilike.conflicting", "limit": "0"},
        "superseded_claims": {"select": "id", "status": "ilike.superseded", "limit": "0"},
        "rejected_claims": {"select": "id", "status": "ilike.rejected", "limit": "0"},
    }

    result = {}
    for name, params in checks.items():
        result[name] = rest_count(base_url, key, params)

    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
