"""FGF evidence graph for conservative multi-hop reasoning.

Edges are created only from explicit claim language. Entity resolution is
limited to exact normalized forms, safe singular/plural variants, and aliases
explicitly supplied by the caller. Derived paths can optionally enforce claim
lifecycle and authority gates so historical/rejected/under-review evidence
cannot silently become production reasoning.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple


@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    claim_index: int
    claim: dict


class EntityResolver:
    """Conservative entity normalization; never uses substring matching."""

    def __init__(self, alias_groups: Optional[Sequence[Sequence[str]]] = None):
        self._canonical: Dict[str, str] = {}
        for group in alias_groups or ():
            cleaned = [_key(x) for x in group if _key(x)]
            if not cleaned:
                continue
            canonical = cleaned[0]
            for alias in cleaned:
                self._canonical[alias] = canonical

    def canonicalize(self, value: str) -> str:
        key = _key(value)
        return self._canonical.get(key, key)

    def matches(self, left: str, right: str) -> bool:
        return bool(_variants(self.canonicalize(left)) & _variants(self.canonicalize(right)))


def _clean(value: str) -> str:
    value = re.sub(r"^[\s\'".,:;()\[\]]+|[\s\'".,:;()\[\]]+$", "", value)
    return re.sub(r"\s+", " ", value).strip()


def _key(value: str) -> str:
    value = _clean(value).lower()
    value = re.sub(r"\b(the|a|an)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _variants(value: str) -> set[str]:
    key = _key(value)
    if not key:
        return set()
    out = {key}
    if key.endswith("s") and not key.endswith("ss"):
        out.add(key[:-1])
    else:
        out.add(key + "s")
    return out


def _claim_status(claim: Mapping) -> str:
    return str(claim.get("Status", claim.get("status", "")) or "").strip().lower()


def _tier_score(claim: Mapping) -> float:
    tier = str(claim.get("Evidence Tier", claim.get("tier", "")) or "").lower()
    if "tier 1" in tier:
        return 3.0
    if "tier 2" in tier:
        return 2.0
    if "tier 3" in tier:
        return 1.0
    return 0.0


class EvidenceGraph:
    PATTERNS: Tuple[Tuple[str, str], ...] = (
        ("requires", r"(?P<src>.+?)\s+requires\s+(?P<tgt>.+?)(?:\.|$)"),
        ("requires", r"(?P<src>.+?)\s+need(?:s)?\s+(?P<tgt>.+?)(?:\.|$)"),
        ("unlocks", r"(?P<src>.+?)\s+unlock(?:s|ed)?\s+(?P<tgt>.+?)(?:\.|$)"),
        ("requires", r"to create\s+(?P<src>.+?),?\s+(?:you\s+)?need\s+(?P<tgt>.+?)(?:\.|$)"),
        ("obtained_from", r"(?P<src>.+?)\s+(?:can be )?obtained (?:through|from)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("obtained_from", r"(?P<src>.+?)\s+(?:can be )?found\s+(?:in|at|from)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("obtained_from", r"(?P<src>.+?)\s+comes\s+from\s+(?P<tgt>.+?)(?:\.|$)"),
        ("available_at", r"(?P<src>.+?)\s+(?:is|are) available (?:at|from|through|in)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("enabled_by", r"(?P<src>.+?)\s+(?:is|are) enabled by\s+(?P<tgt>.+?)(?:\.|$)"),
        ("affects", r"(?P<src>.+?)\s+affects\s+(?P<tgt>.+?)(?:\.|$)"),
        ("counters", r"(?P<src>.+?)\s+counters?\s+(?P<tgt>.+?)(?:\.|$)"),
        ("modifies", r"(?P<src>.+?)\s+(?:modifies|changes)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("upgrades", r"(?P<src>.+?)\s+upgrad(?:es|ing)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("belongs_to", r"(?P<src>.+?)\s+(?:belongs to|is part of)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("supersedes", r"(?P<src>.+?)\s+supersedes\s+(?P<tgt>.+?)(?:\.|$)"),
        ("supports", r"(?P<src>.+?)\s+supports\s+(?P<tgt>.+?)(?:\.|$)"),
    )

    RELATION_ALIASES = {
        "requires": "requires",
        "require": "requires",
        "needs": "requires",
        "need": "requires",
        "obtained": "obtained_from",
        "obtained_from": "obtained_from",
        "available": "available_at",
        "available_at": "available_at",
    }

    def __init__(
        self,
        claims: List[dict],
        alias_groups: Optional[Sequence[Sequence[str]]] = None,
    ):
        self.claims = claims
        self.resolver = EntityResolver(alias_groups)
        self.edges: List[Edge] = []
        self._adj: Dict[Tuple[str, str], List[Edge]] = {}
        self._build()

    def _add(self, source: str, relation: str, target: str, idx: int) -> None:
        source, target = _clean(source), _clean(target)
        if not source or not target:
            return
        canonical_source = self.resolver.canonicalize(source)
        canonical_target = self.resolver.canonicalize(target)
        if canonical_source == canonical_target:
            return
        relation = self.RELATION_ALIASES.get(relation, relation)
        edge = Edge(source, relation, target, idx, self.claims[idx])
        self.edges.append(edge)
        self._adj.setdefault((canonical_source, relation), []).append(edge)

    def _build(self) -> None:
        for idx, claim in enumerate(self.claims):
            text = str(claim.get("Claim", claim.get("claim", "")) or "").strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                for relation, pattern in self.PATTERNS:
                    m = re.match(pattern, sentence.strip(), flags=re.I)
                    if not m:
                        continue
                    target = m.group("tgt")
                    for part in re.split(r"(?<!\d),\s*(?:and\s+)?|\s+and\s+", target):
                        self._add(m.group("src"), relation, part, idx)

    def outgoing(self, source: str, relation: str | None = None) -> List[Edge]:
        canonical_source = self.resolver.canonicalize(source)
        if relation:
            relation = self.RELATION_ALIASES.get(relation, relation)
            return list(self._adj.get((canonical_source, relation), []))
        out: List[Edge] = []
        for (src, _), edges in self._adj.items():
            if src == canonical_source:
                out.extend(edges)
        return out

    def find_sources(self, target: str, relation: str) -> List[Edge]:
        relation = self.RELATION_ALIASES.get(relation, relation)
        return [
            e for e in self.edges
            if e.relation == relation and self.resolver.matches(e.target, target)
        ]

    def _matches(self, value: str, aliases: Iterable[str]) -> bool:
        return any(self.resolver.matches(value, alias) for alias in aliases)

    def edges_for_aliases(self, aliases: List[str], relation: str | None = None) -> List[Edge]:
        if relation:
            relation = self.RELATION_ALIASES.get(relation, relation)
        return [
            e for e in self.edges
            if (not relation or e.relation == relation)
            and (self._matches(e.source, aliases) or self._matches(e.target, aliases))
        ]

    @staticmethod
    def _eligible(
        edge: Edge,
        require_current: bool,
        min_tier_score: float,
    ) -> bool:
        if not require_current and min_tier_score <= 0:
            return True
        status = _claim_status(edge.claim)
        if status in {"rejected", "superseded"}:
            return False
        if require_current and status not in {"confirmed", "current"}:
            return False
        return _tier_score(edge.claim) >= min_tier_score

    def validate_path(
        self,
        path: List[Edge],
        *,
        require_current: bool = False,
        min_tier_score: float = 0.0,
    ) -> dict:
        eligible = all(
            self._eligible(edge, require_current, min_tier_score)
            for edge in path
        )
        return {
            "complete": bool(path),
            "eligible": eligible,
            "hops": len(path),
            "claim_indexes": [edge.claim_index for edge in path],
            "relations": [edge.relation for edge in path],
        }

    def derive(
        self,
        start_aliases: List[str],
        relations: Tuple[str, ...],
        max_hops: int = 2,
        *,
        require_current: bool = False,
        min_tier_score: float = 0.0,
    ) -> List[List[Edge]]:
        if not relations or max_hops < 1:
            return []
        normalized_relations = tuple(
            self.RELATION_ALIASES.get(r, r) for r in relations[:max_hops]
        )
        frontier = [
            (e.target, [e])
            for e in self.edges_for_aliases(start_aliases, normalized_relations[0])
            if self._matches(e.source, start_aliases)
            and self._eligible(e, require_current, min_tier_score)
        ]
        if len(normalized_relations) == 1:
            return [[e] for _, [e] in frontier]

        for relation in normalized_relations[1:]:
            nxt = []
            for node, path in frontier:
                for edge in self.outgoing(node, relation):
                    if self._eligible(edge, require_current, min_tier_score):
                        nxt.append((edge.target, path + [edge]))
            frontier = nxt

        return [
            path for _, path in frontier
            if len(path) == len(normalized_relations)
            and self.validate_path(
                path,
                require_current=require_current,
                min_tier_score=min_tier_score,
            )["eligible"]
        ]

    @staticmethod
    def provenance(path: List[Edge]) -> List[dict]:
        out, seen = [], set()
        for edge in path:
            if edge.claim_index not in seen:
                seen.add(edge.claim_index)
                out.append(edge.claim)
        return out
