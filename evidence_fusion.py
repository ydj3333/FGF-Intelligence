"""FGF v7 Stage 6A — evidence fusion.

Fuses independent evidence records without turning community interpretation into canonical fact.
Weights are deterministic and auditable; provenance is retained on every fused claim.
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import date
from typing import Iterable, Tuple

AUTHORITY_WEIGHT = {"tier 1": 1.0, "official": 1.0, "primary_in_game_ui": 1.0,
                    "tier 2": 0.75, "wiki": 0.75, "community_enrichment": 0.75,
                    "tier 3": 0.45, "community": 0.45, "youtube": 0.45}

@dataclass(frozen=True)
class EvidenceRecord:
    claim_id: str
    text: str
    authority: str
    status: str = "current"       # current | historical | superseded | unknown
    relevance: float = 1.0
    source_id: str = ""
    observed_date: str | None = None

@dataclass(frozen=True)
class FusedClaim:
    text: str
    confidence: float
    evidence_ids: Tuple[str, ...]
    source_ids: Tuple[str, ...]
    authority: str
    status: str
    explanation: str

def _recency(status: str) -> float:
    return {"current": 1.0, "unknown": 0.75, "historical": 0.5, "superseded": 0.25}.get(status.lower(), 0.5)

def _authority(value: str) -> float:
    return AUTHORITY_WEIGHT.get(value.lower(), 0.35)

def score_evidence(item: EvidenceRecord) -> float:
    relevance = max(0.0, min(1.0, item.relevance))
    return _authority(item.authority) * _recency(item.status) * relevance

def fuse_evidence(records: Iterable[EvidenceRecord]) -> Tuple[FusedClaim, ...]:
    """Group identical normalized claims and rank support; never silently merge conflicting text."""
    groups: dict[str, list[EvidenceRecord]] = {}
    for item in records:
        key = " ".join(item.text.lower().split())
        groups.setdefault(key, []).append(item)
    out = []
    for group in groups.values():
        ranked = sorted(group, key=score_evidence, reverse=True)
        top = ranked[0]
        support = min(1.0, sum(score_evidence(x) for x in ranked) / max(1.0, len(ranked)))
        out.append(FusedClaim(
            text=top.text,
            confidence=round(support, 3),
            evidence_ids=tuple(x.claim_id for x in ranked),
            source_ids=tuple(dict.fromkeys(x.source_id for x in ranked if x.source_id)),
            authority=top.authority,
            status=top.status,
            explanation=f"Weighted by authority={_authority(top.authority):.2f}, recency={_recency(top.status):.2f}, relevance={top.relevance:.2f}; provenance retained.",
        ))
    return tuple(sorted(out, key=lambda x: -x.confidence))
