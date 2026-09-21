"""FGF claim lifecycle and temporal-scope policy.

This module is deliberately separate from the Knowledge Quality Analyzer.
Quality/confidence are diagnostic signals; lifecycle state controls whether a
claim is a candidate, current, historical, conflicting, or rejected.

Legacy corpus statuses are mapped without rewriting their meaning:
Confirmed -> CURRENT, Under Review/Candidate/Needs Review -> CANDIDATE,
Conflicting -> CONFLICTING, Superseded -> SUPERSEDED, Rejected -> REJECTED.

No claim is automatically promoted from review states merely because it is
Tier 1. Human/admin evidence review remains the authority for promotion.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Iterable, Optional


class ClaimState(str, Enum):
    DISCOVERED = "discovered"
    CANDIDATE = "candidate"
    VALIDATED = "validated"
    VERIFIED = "verified"
    CURRENT = "current"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REJECTED = "rejected"
    CONFLICTING = "conflicting"


LEGACY_STATUS_TO_STATE = {
    "confirmed": ClaimState.CURRENT,
    "current": ClaimState.CURRENT,
    "under review": ClaimState.CANDIDATE,
    "candidate": ClaimState.CANDIDATE,
    "needs review": ClaimState.CANDIDATE,
    "pending admin review": ClaimState.CANDIDATE,
    "validated": ClaimState.VALIDATED,
    "verified": ClaimState.VERIFIED,
    "superseded": ClaimState.SUPERSEDED,
    "archived": ClaimState.ARCHIVED,
    "rejected": ClaimState.REJECTED,
    "conflicting": ClaimState.CONFLICTING,
}


@dataclass(frozen=True)
class PromotionDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class TemporalScope:
    """Explicit scope only. Unknown values remain None; nothing is inferred."""

    valid_from: Optional[str] = None
    valid_until: Optional[str] = None
    server_scope: Optional[str] = None
    season_scope: Optional[str] = None
    version_scope: Optional[str] = None


def normalize_state(status: Any) -> ClaimState:
    value = str(status or "").strip().lower()
    return LEGACY_STATUS_TO_STATE.get(value, ClaimState.CANDIDATE)


def tier_number(claim: Dict[str, Any]) -> int:
    raw = str(claim.get("Evidence Tier", claim.get("tier", "")))
    import re
    m = re.search(r"tier\s*([1-6])", raw, re.I)
    if m:
        return int(m.group(1))
    return 6


def _metadata(claim: Dict[str, Any]) -> Dict[str, Any]:
    meta = claim.get("metadata")
    return dict(meta) if isinstance(meta, dict) else {}


def temporal_scope(claim: Dict[str, Any]) -> TemporalScope:
    """Read explicit temporal/server fields from the claim or its metadata."""
    meta = _metadata(claim)
    temporal = meta.get("temporal")
    if not isinstance(temporal, dict):
        temporal = {}

    def pick(name: str, *aliases: str) -> Optional[str]:
        for key in (name, *aliases):
            value = temporal.get(key)
            if value not in (None, ""):
                return str(value)
            value = meta.get(key)
            if value not in (None, ""):
                return str(value)
            value = claim.get(key)
            if value not in (None, ""):
                return str(value)
        return None

    return TemporalScope(
        valid_from=pick("valid_from", "validFrom"),
        valid_until=pick("valid_until", "validUntil"),
        server_scope=pick("server_scope", "serverScope"),
        season_scope=pick("season_scope", "seasonScope", "season"),
        version_scope=pick("version_scope", "versionScope", "version"),
    )


def lifecycle_metadata(claim: Dict[str, Any]) -> Dict[str, Any]:
    """Return non-destructive lifecycle metadata for a claim."""
    meta = _metadata(claim)
    scope = temporal_scope(claim)
    state = normalize_state(claim.get("Status", claim.get("status")))

    lifecycle = dict(meta.get("lifecycle") or {})
    lifecycle.update({
        "state": state.value,
        "legacy_status": str(claim.get("Status", claim.get("status", ""))),
        "tier": tier_number(claim),
    })

    temporal = dict(meta.get("temporal") or {})
    for key, value in {
        "valid_from": scope.valid_from,
        "valid_until": scope.valid_until,
        "server_scope": scope.server_scope,
        "season_scope": scope.season_scope,
        "version_scope": scope.version_scope,
    }.items():
        if value is not None:
            temporal[key] = value

    return {"lifecycle": lifecycle, "temporal": temporal}


def promotion_decision(
    claim: Dict[str, Any],
    target: ClaimState,
    *,
    human_approval: bool = False,
    corroborated: bool = False,
    temporal_validated: bool = False,
    conflict_resolved: bool = False,
) -> PromotionDecision:
    """Evaluate a promotion without mutating the claim.

    Safe default: review states cannot silently become production-current.
    """
    current = normalize_state(claim.get("Status", claim.get("status")))

    if target == current:
        return PromotionDecision(True, "Claim is already in the requested lifecycle state.")

    if current == ClaimState.REJECTED:
        return PromotionDecision(False, "Rejected claims cannot be promoted.")

    if current == ClaimState.CONFLICTING and not conflict_resolved:
        return PromotionDecision(False, "Open conflict must be resolved before promotion.")

    if target == ClaimState.VALIDATED:
        if current != ClaimState.CANDIDATE:
            return PromotionDecision(False, "Only candidate claims may enter validation.")
        return (
            PromotionDecision(True, "Human/admin validation recorded.")
            if human_approval
            else PromotionDecision(False, "Human/admin validation is required.")
        )

    if target == ClaimState.VERIFIED:
        if current != ClaimState.VALIDATED:
            return PromotionDecision(False, "Only validated claims may become verified.")
        if not human_approval or not corroborated:
            return PromotionDecision(False, "Verified state requires approval and corroborating evidence.")
        return PromotionDecision(True, "Validation and corroboration requirements are satisfied.")

    if target == ClaimState.CURRENT:
        if current not in (ClaimState.VERIFIED, ClaimState.VALIDATED):
            return PromotionDecision(False, "Current production state requires validated/verified evidence.")
        if not human_approval:
            return PromotionDecision(False, "Explicit promotion approval is required.")
        if not temporal_validated:
            return PromotionDecision(False, "Temporal/server/season applicability must be validated.")
        if current == ClaimState.VERIFIED and not conflict_resolved:
            return PromotionDecision(False, "Conflict state must be explicitly resolved.")
        return PromotionDecision(True, "Claim is eligible for current production truth.")

    if target == ClaimState.SUPERSEDED:
        if current != ClaimState.CURRENT:
            return PromotionDecision(False, "Only current claims can be superseded.")
        return PromotionDecision(True, "Current claim may be superseded by an explicit newer claim.")

    if target == ClaimState.ARCHIVED:
        if current not in (ClaimState.SUPERSEDED, ClaimState.REJECTED):
            return PromotionDecision(False, "Only superseded/rejected claims should be archived.")
        return PromotionDecision(True, "Historical claim may be archived.")

    return PromotionDecision(False, f"Unsupported lifecycle transition: {current.value} -> {target.value}.")


def production_eligible(claim: Dict[str, Any]) -> bool:
    """Whether a claim may participate in normal current-truth retrieval."""
    state = normalize_state(claim.get("Status", claim.get("status")))
    return state == ClaimState.CURRENT


def summarize_states(claims: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    out = {state.value: 0 for state in ClaimState}
    for claim in claims:
        out[normalize_state(claim.get("Status", claim.get("status"))).value] += 1
    return out
