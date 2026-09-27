"""Local/CI Objective #1 benchmark for the deterministic v6 answer engine.

This benchmark intentionally separates hard safety checks from semantic
correctness. The current dataset has questions and constraints but does not
contain hand-authored gold answers for every item, so this runner does not
pretend that structural compliance equals factual correctness.

Hard gates:
- no quality-gate failures
- no forbidden answer content
- no unsupported numeric tokens in the answer surface
- no oversized evidence dump
- no unknown parser intent for the benchmark set

Coverage metrics are reported separately for human review.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from knowledge_query_engine import KnowledgeQueryEngine


INTENT_COMPAT = {
    "combat_mechanic": {"counter", "effect", "generic", "definition", "comparison"},
    "mechanic": {"effect", "definition", "counter", "requirement", "generic", "level_threshold", "comparison", "numeric"},
    "how_to": {"source", "requirement", "multi_hop", "effect", "generic"},
    "calculation": {"numeric", "level_threshold", "comparison", "event_schedule", "generic"},
    "strategy": {"strategy", "source", "effect", "comparison", "event_schedule", "generic", "multi_hop"},
    "definition": {"definition", "effect", "generic", "event_schedule", "source"},
    "comparison": {"comparison", "effect", "counter", "definition", "generic"},
}

def numeric_tokens(text: str) -> set[str]:
    # Ignore evidence markers and standalone list numbering. Preserve commas,
    # decimals and percentages because numeric safety is a core FGF rule.
    return {
        x.replace(",", "")
        for x in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?%?(?![A-Za-z])", text)
        if x not in {"1", "2", "3", "4"}
    }

def run() -> dict:
    data = json.loads((ROOT / "data" / "objective_1_benchmark.json").read_text(encoding="utf-8"))
    corpus = json.loads((ROOT / "data" / "knowledge.json").read_text(encoding="utf-8"))
    engine = KnowledgeQueryEngine(corpus["claims"])

    rows = []
    hard_failures = []
    for item in data["questions"]:
        q = item["question"]
        result = engine.compose(q)
        evidence_text = " ".join(str(e.get("claim", "")) for e in result.get("evidence", []))
        answer = str(result.get("answer", ""))
        parsed_type = result.get("query", {}).get("question_type", "unknown")

        forbidden = [
            term for term in item.get("must_not_contain", [])
            if term.lower() in answer.lower()
        ]
        answer_nums = numeric_tokens(answer)
        evidence_nums = numeric_tokens(evidence_text)
        unsupported_nums = sorted(answer_nums - evidence_nums)

        quality_ok = bool(result.get("quality_gate", {}).get("passes") is True)
        evidence_ok = len(result.get("evidence", [])) <= 4
        intent_ok = parsed_type in INTENT_COMPAT.get(item.get("expected_intent", ""), set())
        if parsed_type == "unknown":
            intent_ok = False

        # An item marked requires_uncertainty may legitimately abstain.
        # Otherwise, absence of evidence is a coverage miss, not a fabricated
        # failure: the corpus may genuinely not establish the answer.
        coverage_ok = bool(result.get("evidence")) or bool(item.get("requires_uncertainty"))
        row = {
            "id": item["id"],
            "question": q,
            "answer_type": result.get("answer_type"),
            "question_type": parsed_type,
            "intent_ok": intent_ok,
            "coverage_ok": coverage_ok,
            "quality_ok": quality_ok,
            "evidence_count": len(result.get("evidence", [])),
            "forbidden_terms": forbidden,
            "unsupported_numbers": unsupported_nums,
            "answer": answer,
        }
        rows.append(row)

        if not quality_ok:
            hard_failures.append((item["id"], "quality_gate"))
        if not evidence_ok:
            hard_failures.append((item["id"], "evidence_dump"))
        if forbidden:
            hard_failures.append((item["id"], "forbidden_content"))
        if unsupported_nums:
            hard_failures.append((item["id"], "unsupported_numeric"))
        if not intent_ok:
            hard_failures.append((item["id"], "unknown_or_mismatched_intent"))

    total = len(rows)
    metrics = {
        "benchmark_version": data.get("version"),
        "questions": total,
        "hard_failures": len(hard_failures),
        "intent_match_rate": round(sum(r["intent_ok"] for r in rows) / max(1, total), 4),
        "coverage_rate": round(sum(r["coverage_ok"] for r in rows) / max(1, total), 4),
        "quality_gate_rate": round(sum(r["quality_ok"] for r in rows) / max(1, total), 4),
        "numeric_safety_rate": round(sum(not r["unsupported_numbers"] for r in rows) / max(1, total), 4),
        "forbidden_content_rate": round(sum(not r["forbidden_terms"] for r in rows) / max(1, total), 4),
        "max_evidence_count": max((r["evidence_count"] for r in rows), default=0),
        "abstentions": sum(r["answer_type"] == "knowledge_abstention" for r in rows),
        "note": "This is a structural/safety benchmark, not a gold-answer accuracy score.",
        "hard_failure_details": [{"id": i, "reason": reason} for i, reason in hard_failures],
    }
    return {"metrics": metrics, "results": rows}

if __name__ == "__main__":
    report = run()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["metrics"]["hard_failures"]:
        raise SystemExit(1)
