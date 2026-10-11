#!/usr/bin/env python3
"""Governed pipeline for the FGF 10k question bank.

This is deliberately not a model-weight trainer. It:
  * audits the Supabase question bank,
  * exports only explicitly approved, training-eligible, source-grounded rows,
  * optionally probes the live /api/ask route and writes an evidence-review report.

Generated wording variants remain review-gated. They must never be promoted to
canonical game truth or silently used as supervised labels.
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_SUPABASE_URL = os.getenv(
    "FGF_SUPABASE_URL", "https://qdoixzfkkmvzjfkhzups.supabase.co"
).rstrip("/")
TABLE = "fgf_question_bank"
FIELDS = (
    "id,question_key,question,ideal_answer,source_claim_id,category,claim_type,"
    "intent_type,source_tier,source_status,source_canonical,season,version,"
    "generation_method,review_status,training_eligible,expected_claim_ids,metadata,topic_label"
)
ROOT = Path(__file__).resolve().parents[1]


def _secret() -> str:
    return (
        os.getenv("FGF_SUPABASE_SECRET_KEY")
        or os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def _headers() -> dict[str, str]:
    key = _secret()
    if not key:
        raise RuntimeError(
            "Set FGF_SUPABASE_SECRET_KEY or FGF_SUPABASE_SERVICE_ROLE_KEY. "
            "Never place a service key in source control."
        )
    headers = {"apikey": key, "Accept": "application/json"}
    if not key.startswith("sb_"):
        headers["Authorization"] = "Bearer " + key
    return headers


def fetch_rows(page_size: int = 1000) -> list[dict]:
    """Fetch the complete bank using PostgREST range pagination."""
    rows: list[dict] = []
    offset = 0
    headers = _headers()
    while True:
        query = urlencode({"select": FIELDS, "order": "created_at.asc"})
        req = Request(
            f"{DEFAULT_SUPABASE_URL}/rest/v1/{TABLE}?{query}",
            headers={**headers, "Range-Unit": "items", "Range": f"{offset}-{offset + page_size - 1}"},
        )
        with urlopen(req, timeout=30) as response:
            page = json.loads(response.read().decode("utf-8") or "[]")
        if not isinstance(page, list):
            raise RuntimeError("Supabase returned an unexpected question-bank payload.")
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += len(page)
    return rows


def is_safe_training_example(row: dict) -> bool:
    """Require explicit approval plus a current canonical source and provenance."""
    status = str(row.get("source_status") or "").strip().lower()
    return bool(
        row.get("review_status") == "approved"
        and row.get("training_eligible") is True
        and row.get("source_canonical") is True
        and status in {"confirmed", "current", "verified"}
        and row.get("source_claim_id")
        and str(row.get("question") or "").strip()
        and str(row.get("ideal_answer") or "").strip()
        and "paraphrase_shell" not in str(row.get("generation_method") or "")
    )


def audit(rows: list[dict]) -> dict:
    by_review = collections.Counter(str(r.get("review_status") or "missing") for r in rows)
    by_intent = collections.Counter(str(r.get("intent_type") or "missing") for r in rows)
    by_generation = collections.Counter(str(r.get("generation_method") or "missing") for r in rows)
    eligible = [r for r in rows if is_safe_training_example(r)]
    return {
        "total_rows": len(rows),
        "distinct_questions": len({str(r.get("question") or "").strip() for r in rows}),
        "distinct_source_claims": len({r.get("source_claim_id") for r in rows if r.get("source_claim_id")}),
        "training_eligible_rows": len(eligible),
        "review_status_counts": dict(by_review),
        "intent_counts": dict(by_intent),
        "generation_method_counts": dict(by_generation),
        "synthetic_shell_variants": by_generation.get("verified_claim_template_v4_paraphrase_shell", 0),
        "canonical_training_rows": len(eligible),
        "note": (
            "A large row count is not model training. Only approved source-grounded examples "
            "are exported; generated variants are not treated as verified semantic paraphrases."
        ),
    }


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def export_training(rows: list[dict], output: Path) -> int:
    safe = [r for r in rows if is_safe_training_example(r)]
    records = [
        {
            "question": r["question"],
            "answer": r["ideal_answer"],
            "source_claim_id": r["source_claim_id"],
            "expected_claim_ids": r.get("expected_claim_ids") or [r["source_claim_id"]],
            "intent_type": r.get("intent_type"),
            "category": r.get("category"),
            "season": r.get("season"),
            "version": r.get("version"),
            "source_tier": r.get("source_tier"),
        }
        for r in safe
    ]
    write_jsonl(output, records)
    return len(records)


def call_ask(api_url: str, question: str, timeout: int = 25) -> dict:
    payload = json.dumps({"question": question}, ensure_ascii=False).encode("utf-8")
    req = Request(
        api_url.rstrip("/") + "/api/ask",
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=timeout) as response:
        body = response.read().decode("utf-8")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw_response": body[:4000]}
        return {"http_status": response.status, "payload": parsed}


def flatten_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(flatten_text(v) for v in value.values())
    if isinstance(value, list):
        return " ".join(flatten_text(v) for v in value)
    return ""


def evaluate(rows: list[dict], api_url: str, output: Path, limit: int, pause: float) -> dict:
    # Use only canonical, confirmed/current rows as candidate probes. Their generated
    # wording still needs human semantic review; this report does not auto-approve them.
    candidates = [
        r for r in rows
        if r.get("source_canonical") is True
        and str(r.get("source_status") or "").strip().lower() in {"confirmed", "current", "verified"}
        and r.get("source_claim_id")
        and str(r.get("question") or "").strip()
        and str(r.get("ideal_answer") or "").strip()
    ][:limit]
    report = []
    failures = 0
    for index, row in enumerate(candidates, 1):
        record = {
            "question_bank_id": row.get("id"),
            "question": row["question"],
            "expected_answer": row["ideal_answer"],
            "expected_claim_id": row["source_claim_id"],
            "intent_type": row.get("intent_type"),
            "generation_method": row.get("generation_method"),
            "review_status": row.get("review_status"),
        }
        try:
            result = call_ask(api_url, row["question"])
            payload = result.get("payload", {})
            response_text = flatten_text(payload)
            claim_id = str(row["source_claim_id"])
            direct_id_match = claim_id in response_text
            answer_text = flatten_text(
                payload.get("answer", payload.get("response", payload.get("text", payload)))
                if isinstance(payload, dict) else payload
            )
            expected_text = str(row["ideal_answer"]).strip().lower()
            exact_answer_in_response = bool(expected_text and expected_text in answer_text.lower())
            record.update({
                "http_status": result.get("http_status"),
                "response_excerpt": answer_text[:1800],
                "source_claim_id_visible_in_response": direct_id_match,
                "expected_answer_exactly_present": exact_answer_in_response,
                "evaluation_status": (
                    "direct_match_signal"
                    if direct_id_match or exact_answer_in_response
                    else "needs_semantic_evidence_review"
                ),
            })
            if not direct_id_match and not exact_answer_in_response:
                failures += 1
        except (HTTPError, URLError, TimeoutError, OSError, ValueError, RuntimeError) as exc:
            record.update({"evaluation_status": "request_error", "error": str(exc)[:500]})
            failures += 1
        report.append(record)
        if pause and index < len(candidates):
            time.sleep(pause)
    write_jsonl(output, report)
    return {
        "candidate_questions": len(candidates),
        "needs_review_or_request_error": failures,
        "report_path": str(output),
        "warning": (
            "Lexical/exact matching is a triage signal, not semantic proof. "
            "No rows were approved, promoted, or used to change canonical truth."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("audit", "export-training", "evaluate"))
    parser.add_argument("--output", default="artifacts/fgf_question_bank_report.jsonl")
    parser.add_argument("--api-url", default=os.getenv("FGF_API_URL", "https://fgf-intelligence.onrender.com"))
    parser.add_argument("--limit", type=int, default=100, help="Maximum live API questions to probe")
    parser.add_argument("--pause", type=float, default=0.15, help="Seconds between live API calls")
    args = parser.parse_args()
    try:
        rows = fetch_rows()
        if args.command == "audit":
            print(json.dumps(audit(rows), indent=2, ensure_ascii=False))
            return 0
        output = Path(args.output)
        if args.command == "export-training":
            count = export_training(rows, output)
            print(json.dumps({
                "exported_approved_examples": count,
                "output": str(output),
                "note": "This exports governed examples; it does not train model weights or deploy code.",
            }, indent=2))
            return 0
        result = evaluate(rows, args.api_url, output, max(0, args.limit), max(0.0, args.pause))
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        print(f"question-bank pipeline failed safely: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
