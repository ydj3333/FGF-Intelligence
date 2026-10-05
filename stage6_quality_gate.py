"""FGF v7 Stage 6D — uncertainty/quality gate."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable, Tuple
from contradiction_engine import Conflict

@dataclass(frozen=True)
class QualityGateResult:
    allowed: bool
    confidence: str
    warnings: Tuple[str, ...] = ()

def apply_quality_gate(conflicts: Iterable[Conflict], base_confidence: str = "supported") -> QualityGateResult:
    conflicts = tuple(conflicts)
    unresolved = tuple(c for c in conflicts if not c.resolved)
    if unresolved:
        return QualityGateResult(False, "uncertain", ("Unresolved evidence contradiction; do not present a confident recommendation.",))
    if conflicts and base_confidence == "certain":
        return QualityGateResult(True, "supported", ("Conflicting evidence was resolved using authority/status policy; losing evidence remains preserved.",))
    return QualityGateResult(True, base_confidence, ())
