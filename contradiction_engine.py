"""FGF v7 Stage 6B — contradiction detection and resolution."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Tuple
from evidence_fusion import EvidenceRecord, score_evidence

@dataclass(frozen=True)
class Conflict:
    claims: Tuple[EvidenceRecord, ...]
    conflict_type: str
    resolved: bool
    winner: str | None
    rationale: str

def _norm(text: str) -> str:
    return " ".join(text.lower().split())

def _classify(items: Tuple[EvidenceRecord, ...]) -> str:
    statuses = {_norm(x.status) for x in items}
    authorities = {_norm(x.authority) for x in items}
    if "historical" in statuses or "superseded" in statuses:
        return "temporal"
    if len(authorities) > 1:
        return "authority"
    return "interpretation"

def detect_conflicts(records: Iterable[EvidenceRecord]) -> Tuple[Conflict, ...]:
    items = tuple(records)
    conflicts = []
    for i, left in enumerate(items):
        for right in items[i + 1:]:
            if _norm(left.text) == _norm(right.text):
                continue
            # Explicit claim pairs are supplied by the caller; different text on the same topic is a conflict.
            if left.claim_id.split(":")[0] != right.claim_id.split(":")[0]:
                continue
            pair = (left, right)
            winner = max(pair, key=score_evidence)
            resolved = score_evidence(left) != score_evidence(right) or left.status != right.status
            rationale = ("Higher-authority/current evidence selected; lower-priority evidence is preserved."
                         if resolved else "No evidence-backed winner; contradiction remains unresolved.")
            conflicts.append(Conflict(pair, _classify(pair), resolved, winner.claim_id if resolved else None, rationale))
    return tuple(conflicts)

def resolve_conflict(conflict: Conflict) -> Conflict:
    """Return an auditable resolution; never delete losing/historical claims."""
    return conflict
