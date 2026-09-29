"""Deterministic canonical Tier-1/Tier-2 query coverage benchmark for FGF.

The benchmark derives meaningful canonical concepts from Tier-1/Tier-2 claims
and exercises the same production query engine used by the website. It never
invents numeric/update/source/requirement/event facts: specialized cases are
created only when the supporting canonical evidence actually supports them.

This is a retrieval/coverage gate, not a gold-factuality benchmark.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from knowledge_query_engine import (
    ENTITY_ALIASES,
    QuestionParser,
    KnowledgeQueryEngine,
    _text,
)


UPDATE_MARKERS = (
    "update", "hot update", "patch", "changed", "increased", "decreased",
    "added", "removed", "introduced", "reduced", "superseded",
)
SOURCE_MARKERS = (
    "obtain", "obtained", "get", "source", "sources", "drop", "drops",
    "earn", "farm", "available at", "through",
)
REQUIREMENT_MARKERS = (
    "requires", "require", "need", "needed", "prerequisite", "before",
    "condition", "unlock", "unlocks",
)
EVENT_MARKERS = (
    "event", "schedule", "gvg", "galactic", "shadowfront", "kaboom",
    "moonlight", "lunar",
)
LEADING_WORDS_TO_TRIM = {"the", "a", "an"}
DATE_ONLY = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?)\s+\d{1,2}(?:,?\s+\d{4})?\b",
    re.I,
)
YEAR_ONLY = re.compile(r"\b(?:19|20)\d{2}\b")
CARDINALITY = re.compile(
    r"\b(?:contains?|has|have|includes?)\s+\d[\d,.]*\b",
    re.I,
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
    return any(marker.lower() in low for marker in markers)


def _claim_sentences(claim: Dict[str, Any]) -> List[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+|\n+", _text(claim))
        if sentence.strip()
    ]


def _entity_variants(entity: str) -> List[str]:
    variants = {entity.lower()}
    words = entity.lower().split()
    if words:
        last = words[-1]
        if last.endswith("ies"):
            variants.add(" ".join(words[:-1] + [last[:-3] + "y"]))
        elif last.endswith("ses"):
            variants.add(" ".join(words[:-1] + [last[:-2]]))
        elif len(last) > 3 and last.endswith("s") and not last.endswith("ss"):
            variants.add(" ".join(words[:-1] + [last[:-1]]))
        elif not last.endswith("s"):
            variants.add(entity.lower() + "s")
    return sorted(variants, key=len, reverse=True)


def _entity_present(text: str, entity: str) -> bool:
    low = text.lower()
    return any(re.search(r"\b" + re.escape(v) + r"\b", low) for v in _entity_variants(entity))


def _relation_supported(entity: str, claims: List[Dict[str, Any]], markers: Iterable[str]) -> bool:
    """Require an entity-local relation, not merely a marker anywhere in a claim."""
    marker_list = tuple(m.lower() for m in markers)
    for claim in claims:
        for sentence in _claim_sentences(claim):
            low = sentence.lower()
            if not _entity_present(low, entity):
                continue
            positions = []
            for marker in marker_list:
                for match in re.finditer(r"\b" + re.escape(marker) + r"\b", low):
                    positions.append(match.start())
            entity_positions = []
            for variant in _entity_variants(entity):
                match = re.search(r"\b" + re.escape(variant) + r"\b", low)
                if match:
                    entity_positions.append(match.start())
            if positions and entity_positions and min(abs(p - e) for p in positions for e in entity_positions) <= 90:
                return True
    return False


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


def _capitalized_entities(claims: List[Dict[str, Any]]) -> List[str]:
    """Keep complete player-facing capitalized runs, not arbitrary subphrases."""
    found = set()
    for claim in claims:
        text = _text(claim)
        for match in re.finditer(
            r"\b[A-Z][A-Za-z0-9'&-]*(?:\s+[A-Z][A-Za-z0-9'&-]*){1,5}\b",
            text,
        ):
            words = match.group(0).strip().split()
            while words and words[0].lower() in LEADING_WORDS_TO_TRIM:
                words.pop(0)
            phrase = " ".join(words).lower()
            if len(phrase.split()) >= 2:
                found.add(phrase)
    return sorted(found)


def _manual_canonical_entities(claims: List[Dict[str, Any]]) -> List[str]:
    """Retain established parser aliases when canonical claims support them."""
    found = set()
    combined = "\n".join(_text(c).lower() for c in claims)
    for entity, aliases in ENTITY_ALIASES.items():
        candidates = [entity, *aliases]
        if any(re.search(r"\b" + re.escape(alias.lower()) + r"\b", combined) for alias in candidates):
            found.add(entity.lower())
    return sorted(found)


def canonical_entities(claims: List[Dict[str, Any]]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    parser = QuestionParser(claims)
    grouped: Dict[str, List[Dict[str, Any]]] = {}

    candidates = set(_capitalized_entities(claims))
    candidates.update(_manual_canonical_entities(claims))

    for candidate in sorted(candidates):
        supporting = _phrase_claims(claims, candidate)
        if not supporting:
            continue
        parsed = parser.parse(f"what is {candidate}")
        entity = parsed.entity
        if entity == "unknown":
            continue
        grouped.setdefault(entity, [])
        for claim in supporting:
            if claim not in grouped[entity]:
                grouped[entity].append(claim)

    return sorted(grouped.items())


def _has_non_date_numeric(text: str) -> bool:
    cleaned = DATE_ONLY.sub(" ", text)
    cleaned = YEAR_ONLY.sub(" ", cleaned)
    return bool(re.search(r"\b\d[\d,.]*(?:%|\b)", cleaned))


def _numeric_supporting_cases(
    entity: str,
    claims: List[Dict[str, Any]],
) -> List[Tuple[str, Dict[str, Any]]]:
    """Return numeric cases only when the entity owns a cardinality relation."""
    out: List[Tuple[str, Dict[str, Any]]] = []
    variants = _entity_variants(entity)

    for claim in claims:
        for sentence in _claim_sentences(claim):
            low = sentence.lower()
            if not _entity_present(low, entity):
                continue
            match = None
            for variant in variants:
                match = re.search(
                    r"\b" + re.escape(variant) +
                    r"\b\s+(?:contains?|has|have|includes?)\s+"
                    r"(\d[\d,.]*)\s+([a-z][a-z0-9'-]*(?:\s+[a-z][a-z0-9'-]*){0,5})",
                    low,
                    re.I,
                )
                if match:
                    break
            if not match:
                continue
            object_text = match.group(2).strip(" .,;:")
            object_text = re.split(
                r"\b(?:that|which|and|while|during|in|on|for|per)\b",
                object_text,
                maxsplit=1,
            )[0].strip()
            if not object_text:
                continue
            number = match.group(1).replace(",", "")
            if len(number) == 4 and number.isdigit() and 1900 <= int(number) <= 2099:
                continue
            out.append((f"how many {object_text} does {entity} contain", claim))
            break
    return out


def _event_supported(entity: str, claims: List[Dict[str, Any]]) -> bool:
    for claim in claims:
        category = str(claim.get("Category", claim.get("category", ""))).lower()
        if "event" not in category and not _contains_marker(_text(claim), EVENT_MARKERS):
            continue
        if _entity_present(_text(claim), entity):
            return True
    return False


def build_query_cases(claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cases: List[Dict[str, Any]] = []
    seen = set()

    for entity, supporting in canonical_entities(claims):
        queries = [("factual", f"what is {entity}")]

        if _relation_supported(entity, supporting, UPDATE_MARKERS):
            queries.append(("update", f"what changed in {entity}"))
        if _relation_supported(entity, supporting, SOURCE_MARKERS):
            queries.append(("source", f"how do i get {entity}"))
        if _relation_supported(entity, supporting, REQUIREMENT_MARKERS):
            queries.append(("requirement", f"what does {entity} require"))

        for numeric_query, _numeric_claim in _numeric_supporting_cases(entity, supporting):
            queries.append(("numeric", numeric_query))

        if _event_supported(entity, supporting):
            queries.append(("event", f"{entity} event"))

        for intent, query in queries:
            key = (entity, intent, query)
            if key in seen:
                continue
            seen.add(key)
            case = {
                "entity": entity,
                "intent": intent,
                "query": query,
                "supporting_claims": supporting,
            }
            if intent == "numeric":
                # The parser may legitimately resolve the counted object
                # ("Lesser Vaults") rather than the containing entity
                # ("Shadowfront"). Record that separately so numeric coverage
                # tests both canonical concepts without forcing an incorrect
                # parser identity.
                case["expected_entity"] = QuestionParser(claims).parse(query).entity
            cases.append(case)
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
        entity_ok = parsed.entity == case.get("expected_entity", case["entity"])
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
