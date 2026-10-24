"""Objective #1 (50-question) release benchmark for the v8 AI agent.

`run_v6_objective1_benchmark.py` calls the deterministic KnowledgeQueryEngine
directly, so it cannot measure the AI agent. This runner sends the same 50
questions through the live agent path (fgf_agent.get_agent) and applies the
same hard safety gates, plus agent-specific ones.

Hard gates (any failure -> exit 1):
- answered by the AI agent (no silent fallback to the deterministic engine)
- automatic grounding/fact-check passed
- no citations to evidence the model never received
- no forbidden answer content (item.must_not_contain)
- no numbers in the answer that are absent from the cited evidence, tool
  output or the question itself
- the agent searched the knowledge base before answering

Reported for human review (not gates): latency, LLM calls, tokens, searches,
evidence count, abstentions. As with v6, this is a structural/safety benchmark,
not a gold-answer accuracy score; every answer is written to the report so a
reviewer can grade correctness.

Requires an LLM key (see AI_AGENT.md). Without one it prints SKIPPED and exits
0, unless FGF_REQUIRE_AGENT_EVAL=1, in which case it exits 2 so a release
pipeline cannot pass without actually evaluating the agent.

Usage:
    python scripts/run_v8_agent_benchmark.py [--limit N] [--out reports/v8_agent_benchmark.json]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def numeric_tokens(text: str) -> set[str]:
    out = set()
    for x in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?%?(?![A-Za-z])", text or ""):
        x = x.replace(",", "").rstrip("%")
        if x not in {"1", "2", "3", "4", "5", "6", "7", "8", "9"}:
            out.add(x)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="only run the first N questions (cost control)")
    ap.add_argument("--out", default="", help="write the full JSON report to this path")
    args = ap.parse_args()

    from fgf_agent import agent_status, get_agent

    agent = get_agent()
    if agent is None:
        status = agent_status()
        msg = {"status": "SKIPPED", "reason": status.get("reason_disabled"),
               "note": "Configure an LLM key to evaluate the v8 agent (see AI_AGENT.md)."}
        print(json.dumps(msg, indent=2))
        return 2 if os.getenv("FGF_REQUIRE_AGENT_EVAL", "").lower() in ("1", "true", "yes") else 0

    data = json.loads((ROOT / "data" / "objective_1_benchmark.json").read_text(encoding="utf-8"))
    items = data["questions"][: args.limit] if args.limit else data["questions"]

    rows, hard = [], []
    for item in items:
        q = item["question"]
        started = time.time()
        try:
            res = agent.ask(q, session_id=None)
            error = None
        except Exception as exc:  # AgentUnavailable, provider errors
            res, error = {}, f"{type(exc).__name__}: {exc}"
        answer = str(res.get("answer") or "")
        evidence_text = " ".join(str(e.get("Claim", "")) + " " + str(e.get("Notes", "")) for e in res.get("evidence") or [])
        grounding = res.get("grounding") or {}
        trace = res.get("agent_trace") or []
        searches = sum(1 for t in trace if t.get("tool") in ("search_knowledge", "check_conflicts", "core_progression", "event_strategy_planner"))
        forbidden = [t for t in item.get("must_not_contain", []) if t.lower() in answer.lower()]
        # The agent's grounding check compares every factual number against all
        # retrieved evidence, tool output (e.g. calculator) and the question.
        unsupported = list(grounding.get("unsupported_numbers") or [])
        # Reviewer aid: numbers not found in the *cited* evidence (stricter, not a gate).
        uncited_numbers = sorted(numeric_tokens(answer) - numeric_tokens(evidence_text) - numeric_tokens(q))

        row = {
            "id": item["id"], "question": q, "error": error,
            "answer_type": res.get("answer_type"),
            "grounding_passed": bool(grounding.get("passed")),
            "grounding_issues": grounding.get("issues", []),
            "unknown_refs": grounding.get("unknown_refs", []),
            "searches": searches, "evidence_count": len(res.get("evidence") or []),
            "forbidden_terms": forbidden, "unsupported_numbers": unsupported,
            "numbers_not_in_cited_evidence": uncited_numbers,
            "llm_calls": (res.get("usage") or {}).get("llm_calls"),
            "tokens": (res.get("usage") or {}).get("input_tokens", 0) + (res.get("usage") or {}).get("output_tokens", 0),
            "latency_ms": round((time.time() - started) * 1000),
            "requires_uncertainty": bool(item.get("requires_uncertainty")),
            "answer": answer,
            "evidence": [e.get("Claim") for e in res.get("evidence") or []],
        }
        rows.append(row)

        if error or row["answer_type"] != "ai_agent":
            hard.append((item["id"], "agent_not_used" if not error else "agent_error"))
            continue
        if not row["grounding_passed"]:
            hard.append((item["id"], "grounding_failed"))
        if row["unknown_refs"]:
            hard.append((item["id"], "unknown_citation"))
        if forbidden:
            hard.append((item["id"], "forbidden_content"))
        if unsupported:
            hard.append((item["id"], "unsupported_numeric"))
        if searches == 0:
            hard.append((item["id"], "answered_without_search"))

    n = max(1, len(rows))
    lat = sorted(r["latency_ms"] for r in rows)
    metrics = {
        "benchmark": "objective_1_v8_agent",
        "benchmark_version": data.get("version"),
        "provider": agent.llm.provider, "model": agent.llm.model,
        "questions": len(rows),
        "hard_failures": len(hard),
        "agent_answer_rate": round(sum(r["answer_type"] == "ai_agent" for r in rows) / n, 4),
        "grounding_pass_rate": round(sum(r["grounding_passed"] for r in rows) / n, 4),
        "numeric_safety_rate": round(sum(not r["unsupported_numbers"] for r in rows) / n, 4),
        "forbidden_content_rate": round(sum(not r["forbidden_terms"] for r in rows) / n, 4),
        "avg_searches": round(sum(r["searches"] for r in rows) / n, 2),
        "avg_llm_calls": round(sum(r["llm_calls"] or 0 for r in rows) / n, 2),
        "total_tokens": sum(r["tokens"] for r in rows),
        "latency_p50_ms": lat[len(lat) // 2] if lat else None,
        "latency_p90_ms": lat[int(len(lat) * 0.9) - 1] if lat else None,
        "note": "Structural/safety benchmark, not a gold-answer accuracy score. Review 'answer' fields for correctness.",
        "hard_failure_details": [{"id": i, "reason": r} for i, r in hard],
    }
    report = {"metrics": metrics, "results": rows}
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    return 1 if hard else 0


if __name__ == "__main__":
    raise SystemExit(main())
