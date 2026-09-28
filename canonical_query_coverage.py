"""Deterministic canonical Tier-1/Tier-2 query coverage benchmark for FGF.

The benchmark derives entities and supported query intents from the same
canonical claims corpus used by the production query engine. It never invents
numeric/update/source/requirement/event facts: specialized queries are created
only when the supporting canonical claim contains evidence for that intent.

This is a retrieval/coverage gate, not a gold-factuality benchmark.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from knowledge_query_engine import QuestionParser, KnowledgeQueryEngine, _text


UPDATE_MARKERS = (
    "update", "hot update", "patch", "changed", "increased", "decreased",
    "added", "removed", "introduced", "reduced", "superseded",
)
SOURCE_MARKERS = (
    "obtain", "obtained", "get", "source", "sources", "drop", "drops",
    "earn", "farm", "shop", "available at", "through",
)
REQUIREMENT_MARKERS = (
    "requires", "require", "need", "needed", "prerequisite", "before",
    "condition", "unlock", "unlocks",
)
EVENT_MARKERS = (
    "event", "schedule", "day", "rewards", "reward", "traders", "gvg",
    "galactic", "shadowfront", "kaboom", "moonlight", "lunar",
)


def load_canonical_claims(path: str | Path | None = None) -> List[Dict[str, Any]]:
    path = Path(path or Path(__file__).resolve().parent / "data" / "knowledge.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    claims = data.get("claims", data if isinstance(data, list) else [])
    return [
        c for c in claims
        if "tier 1" in str(c.get("Evidence Tier", c.get("tier", ""))).lower()
        or "tier 2" in str(c.get("Evidence Tier", c.get("tier", ""))).lower()
    ]


def _contains_marker(text: str, markers: Iterable[str]) -> bool:
    low = text.lower()
    return any(marker in low for marker in markers)


def _phrase_claims(claims: List[Dict[str, Any]], phrase: str) -> List[Dict[str, Any]]:
    needle = phrase.lower()
    variants = {needle}
    words = needle.split()
    if words:
        last = words[-1]
        if last.endswith("ies"):
            variants.add(" ".join(words[:-1] + [last[:-3] + "y"]))
        elif last.endswith("ses"):
            variants.add(" ".join(words[:-1] + [last[:-2]]))
        elif len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
            variants.add(" ".join(words[:-1] + [last[:-1]]))
        elif not last.endswith("s"):
            variants.add(needle + "s")
    out = []
    for claim in claims:
        text = _text(claim).lower()
        if any(re.search(r"\b" + re.escape(v) + r"\b", text) for v in variants):
            out.append(claim)
    return out


def canonical_entities(claims: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    parser = QuestionParser(claims)
    entities = []
    for phrase in sorted(parser.canonical_phrases):
        if len(phrase.split()) < 2:
            continue
        supporting = _phrase_claims(claims, phrase)
        if supporting:
            entities.append((phrase, supporting))
    return entities


def build_query_cases(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    seen = set()

    for entity, supporting in canonical_entities(claims):
        queries = [("factual", f"what is {entity}")]
        combined = " ".join(_text(c) for c in supporting)

        if _contains_marker(combined, UPDATE_MARKERS):
            queries.append(("update", f"what changed in {entity}"))
        if _contains_marker(combined, SOURCE_MARKERS):
            queries.append(("source", f"how do i get {entity}"))
        if _contains_marker(combined, REQUIREMENT_MARKERS):
            queries.append(("requirement", f"what does {entity} require"))
        if re.search(r"\b\d[\d,.]*\b|\b\d+(?:\.\d+)?%", combined):
            queries.append(("numeric", f"how many {entity}"))
        if _contains_marker(combined, EVENT_MARKERS):
            queries.append(("event", f"{entity} event"))

        for intent, query in queries:
            key = (entity, intent, query)
            if key in seen:
                continue
            seen.add(key)
            cases.append({
                "entity": entity,
                "intent": intent,
                "query": query,
                "supporting_claims": supporting,
            })
    return cases


def run_coverage_benchmark(
    claims: List[Dict[str, Any]],
    *,
    max_failures: int | None = None,
) -> Dict[str, Any]:
    engine = KnowledgeQueryEngine(claims)
    cases = build_query_cases(claims)
    failures = []
    passed = 0

    for case in cases:
        parsed = engine.parse(case["query"])
        result = engine.compose(case["query"])
        entity_ok = parsed.entity == case["entity"]
        answer_ok = result.get("answer_type") == "knowledge_query" and bool(result.get("evidence"))
        if entity_ok and answer_ok:
            passed += 1
            continue
        failures.append({
            "entity": case["entity"],
            "intent": case["intent"],
            "query": case["query"],
            "parsed_entity": parsed.entity,
            "answer_type": result.get("answer_type"),
            "evidence_count": len(result.get("evidence") or []),
            "reasoning_mode": (result.get("reasoning") or {}).get("mode"),
        })
        if max_failures is not None and len(failures) >= max_failures:
            break

    entity_count = len(canonical_entities(claims))
    return {
        "entity_count": entity_count,
        "case_count": len(cases),
        "passed": passed,
        "failed": len(failures),
        "coverage_percent": round((passed / len(cases) * 100), 2) if cases else 0.0,
        "failures": failures,
    }


def format_failure_report(report: Dict[str, Any], limit: int = 20) -> str:
    lines = [
        "Canonical query coverage regression:",
        f"entities={report['entity_count']} cases={report['case_count']} "
        f"passed={report['passed']} failed={report['failed']} "
        f"coverage={report['coverage_percent']}%",
    ]
    for item in report["failures"][:limit]:
        lines.append(
            f"- {item['intent']}: {item['query']} | "
            f"parsed={item['parsed_entity']} | "
            f"type={item['answer_type']} | evidence={item['evidence_count']} | "
            f"mode={item['reasoning_mode']}"
        )
    return "\n".join(lines)
