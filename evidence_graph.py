"""Evidence graph for FGF claim-to-claim reasoning.

The graph is deliberately conservative: edges are created only from explicit
language in a stored claim. It never invents a relationship. Each edge keeps
the originating claim so derived answers can expose the complete evidence chain.
"""
from __future__ import annotations
from dataclasses import dataclass
import re
from typing import Dict, List, Tuple

@dataclass(frozen=True)
class Edge:
    source: str
    relation: str
    target: str
    claim_index: int
    claim: dict

def _clean(value: str) -> str:
    value = re.sub(r"^[\s\'\".,:;()\[\]]+|[\s\'\".,:;()\[\]]+$", "", value)
    return re.sub(r"\s+", " ", value).strip()

def _key(value: str) -> str:
    value = _clean(value).lower()
    value = re.sub(r"\b(the|a|an)\b", " ", value)
    return re.sub(r"\s+", " ", value).strip()

class EvidenceGraph:
    PATTERNS: Tuple[Tuple[str, str], ...] = (
        ("requires", r"(?P<src>.+?)\s+requires\s+(?P<tgt>.+?)(?:\.|$)"),
        ("requires", r"(?P<src>.+?)\s+need(?:s)?\s+(?P<tgt>.+?)(?:\.|$)"),
        ("unlocks", r"(?P<src>.+?)\s+unlock(?:s|ed)?\s+(?P<tgt>.+?)(?:\.|$)"),
        ("obtained_from", r"(?P<src>.+?)\s+(?:can be )?obtained (?:through|from)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("available_at", r"(?P<src>.+?)\s+(?:is|are) available (?:at|from|through)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("counters", r"(?P<src>.+?)\s+counters?\s+(?P<tgt>.+?)(?:\.|$)"),
        ("modifies", r"(?P<src>.+?)\s+(?:modifies|changes|affects)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("upgrades", r"(?P<src>.+?)\s+upgrad(?:es|ing)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("belongs_to", r"(?P<src>.+?)\s+(?:belongs to|is part of)\s+(?P<tgt>.+?)(?:\.|$)"),
        ("supersedes", r"(?P<src>.+?)\s+supersedes\s+(?P<tgt>.+?)(?:\.|$)"),
        ("supports", r"(?P<src>.+?)\s+supports\s+(?P<tgt>.+?)(?:\.|$)"),
    )

    def __init__(self, claims: List[dict]):
        self.claims = claims
        self.edges: List[Edge] = []
        self._adj: Dict[Tuple[str, str], List[Edge]] = {}
        self._build()

    def _add(self, source: str, relation: str, target: str, idx: int) -> None:
        source, target = _clean(source), _clean(target)
        if not source or not target or _key(source) == _key(target): return
        edge = Edge(source, relation, target, idx, self.claims[idx])
        self.edges.append(edge)
        self._adj.setdefault((_key(source), relation), []).append(edge)

    def _build(self) -> None:
        for idx, claim in enumerate(self.claims):
            text = str(claim.get("Claim", claim.get("claim", "")) or "").strip()
            for sentence in re.split(r"(?<=[.!?])\s+", text):
                for relation, pattern in self.PATTERNS:
                    m = re.match(pattern, sentence.strip(), flags=re.I)
                    if m:
                        target = m.group("tgt")
                        for part in re.split(r",\s*(?:and\s+)?|\s+and\s+", target):
                            self._add(m.group("src"), relation, part, idx)

    def outgoing(self, source: str, relation: str | None = None) -> List[Edge]:
        if relation: return list(self._adj.get((_key(source), relation), []))
        out = []
        for (src, _), edges in self._adj.items():
            if src == _key(source): out.extend(edges)
        return out

    def find_sources(self, target: str, relation: str) -> List[Edge]:
        tk = _key(target)
        return [e for e in self.edges if e.relation == relation and _key(e.target) == tk]

    def _matches(self, value: str, aliases: List[str]) -> bool:
        v = _key(value)
        return any(_key(a) == v or _key(a) in v or v in _key(a) for a in aliases)

    def edges_for_aliases(self, aliases: List[str], relation: str | None = None) -> List[Edge]:
        return [e for e in self.edges if (not relation or e.relation == relation) and (self._matches(e.source, aliases) or self._matches(e.target, aliases))]

    def derive(self, start_aliases: List[str], relations: Tuple[str, ...], max_hops: int = 2) -> List[List[Edge]]:
        frontier = [(e.target, [e]) for e in self.edges_for_aliases(start_aliases, relations[0] if relations else None) if self._matches(e.source, start_aliases)]
        if max_hops <= 1 or len(relations) <= 1: return [p for _, p in frontier]
        paths = []
        for _ in range(1, min(max_hops, len(relations))):
            nxt = []
            relation = relations[_]
            for node, path in frontier:
                for edge in self.outgoing(node, relation): nxt.append((edge.target, path + [edge]))
            frontier = nxt
        return [p for _, p in frontier if len(p) == len(relations)]

    @staticmethod
    def provenance(path: List[Edge]) -> List[dict]:
        out, seen = [], set()
        for edge in path:
            if edge.claim_index not in seen:
                seen.add(edge.claim_index); out.append(edge.claim)
        return out
