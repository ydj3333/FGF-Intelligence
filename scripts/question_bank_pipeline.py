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
import re
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
# source_status/source_canonical live on public.claims, not fgf_question_bank.
FIELDS = (
    "id,question_key,question,ideal_answer,source_claim_id,category,claim_type,"
    "intent_type,source_tier,season,version,generation_method,review_status,"
    "training_eligible,expected_claim_ids,metadata,topic_label,"
    "source_claim:claims!fgf_question_bank_source_claim_id_fkey(id,claim,status,canonical,tier,season,version)"
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


def normalize_source_row(row: dict) -> dict:
    """Copy linked claim lifecycle/provenance into explicit fields; fail closed."""
    source = row.get("source_claim")
    if isinstance(source, list):
        source = source[0] if source else None
    source = source if isinstance(source, dict) else {}
    row["source_status"] = source.get("status")
    row["source_canonical"] = source.get("canonical") is True
    row["source_claim_text"] = source.get("claim")
    row["source_claim_tier"] = source.get("tier")
    row["source_claim_version"] = source.get("version")
    return row


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
        for row in page:
            normalize_source_row(row)
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
    probe_rows = evaluation_candidates(rows)
    source_status_counts = collections.Counter(
        str(r.get("source_status") or "missing") for r in rows
    )
    return {
        "total_rows": len(rows),
        "distinct_questions": len({str(r.get("question") or "").strip() for r in rows}),
        "distinct_source_claims": len({r.get("source_claim_id") for r in rows if r.get("source_claim_id")}),
        "training_eligible_rows": len(eligible),
        "current_canonical_non_shell_probe_rows": len(probe_rows),
        "current_canonical_non_shell_source_claims": len({
            r.get("source_claim_id") for r in probe_rows if r.get("source_claim_id")
        }),
        "source_status_counts": dict(source_status_counts),
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
    # The deployed player ask route is GET /api/ask?q=... .
    # POST /api/ask is not implemented by the current HTTP handler.
    url = api_url.rstrip("/") + "/api/ask?" + urlencode({"q": question})
    req = Request(
        url,
        headers={"Accept": "application/json"},
        method="GET",
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


STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "does", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "to", "what", "when",
    "where", "which", "who", "why", "with", "do", "can", "could", "would",
    "should", "about", "according", "documented", "guide", "states", "state",
}


def content_tokens(value) -> set[str]:
    """Small deterministic token set for triage only, never a semantic verdict."""
    return {
        token for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if len(token) > 1 and token not in STOP_WORDS
    }


def overlap_score(left, right) -> float:
    a, b = content_tokens(left), content_tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def evaluation_candidates(rows: list[dict], limit: int | None = None) -> list[dict]:
    """Probe only current canonical claims and exclude 9,000 synthetic shell prompts."""
    candidates = [
        r for r in rows
        if r.get("source_canonical") is True
        and str(r.get("source_status") or "").strip().lower() in {"confirmed", "current", "verified"}
        and r.get("source_claim_id")
        and str(r.get("source_claim_text") or "").strip()
        and str(r.get("question") or "").strip()
        and str(r.get("ideal_answer") or "").strip()
        and "paraphrase_shell" not in str(r.get("generation_method") or "")
    ]
    return candidates if limit is None else candidates[:max(0, limit)]


def evaluate(rows: list[dict], api_url: str, output: Path, limit: int, pause: float) -> dict:
    # Generated prompts are diagnostic probes, not gold labels. No lexical score
    # can approve a row or prove semantic correctness; it only prioritizes review.
    candidates = evaluation_candidates(rows, limit)
    report = []
    failures = 0
    for index, row in enumerate(candidates, 1):
        record = {
            "question_bank_id": row.get("id"),
            "question": row["question"],
            "expected_answer": row["ideal_answer"],
            "expected_claim_id": row["source_claim_id"],
            "expected_source_claim": row.get("source_claim_text"),
            "intent_type": row.get("intent_type"),
            "generation_method": row.get("generation_method"),
            "review_status": row.get("review_status"),
            "evaluation_is_gold": False,
        }
        try:
            result = call_ask(api_url, row["question"])
            payload = result.get("payload", {})
            answer_text = flatten_text(
                payload.get("answer", payload.get("response", payload.get("text", payload)))
                if isinstance(payload, dict) else payload
            )
            evidence = payload.get("evidence", []) if isinstance(payload, dict) else []
            evidence_text = flatten_text(evidence)
            source_claim = row.get("source_claim_text") or row.get("ideal_answer") or ""
            answer_overlap = overlap_score(source_claim, answer_text)
            evidence_overlap = overlap_score(source_claim, evidence_text)
            record.update({
                "http_status": result.get("http_status"),
                "response_excerpt": answer_text[:1800],
                "evidence_excerpt": evidence_text[:1800],
                "answer_source_overlap_triage": round(answer_overlap, 4),
                "evidence_source_overlap_triage": round(evidence_overlap, 4),
                "evaluation_status": (
                    "possible_relevance_failure"
                    if result.get("http_status", 0) >= 400 or (answer_overlap < 0.12 and evidence_overlap < 0.12)
                    else "lexical_signal_for_manual_semantic_review"
                ),
            })
            if record["evaluation_status"] == "possible_relevance_failure":
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
            "Token overlap is triage only, not semantic proof. Generated prompts remain "
            "unreviewed; no rows were approved, promoted, or used to change canonical truth."
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
