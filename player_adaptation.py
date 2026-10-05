"""FGF v7 Stage 6C — player-specific adaptation layer.

Global event facts remain separate from player profile constraints.
Missing profile fields are never inferred.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Mapping, Tuple

@dataclass(frozen=True)
class PlayerProfile:
    spending_profile: str | None = None
    core_level: int | None = None
    fleet_type: str | None = None
    guild_role: str | None = None
    owned_entities: Tuple[str, ...] = ()
    unavailable_entities: Tuple[str, ...] = ()
    preferences: Mapping[str, str] = field(default_factory=dict)

@dataclass(frozen=True)
class AdaptationResult:
    applicable: bool
    matched_constraints: Tuple[str, ...]
    missing_profile_fields: Tuple[str, ...]
    recommendation_notes: Tuple[str, ...]

def adapt_profile(profile: PlayerProfile, required_fields: Tuple[str, ...] = ()) -> AdaptationResult:
    values = {
        "spending_profile": profile.spending_profile,
        "core_level": profile.core_level,
        "fleet_type": profile.fleet_type,
        "guild_role": profile.guild_role,
    }
    matched = tuple(k for k, v in values.items() if v is not None)
    missing = tuple(k for k in required_fields if values.get(k) is None)
    notes = tuple(f"Use confirmed player field: {k}" for k in matched)
    if missing:
        notes += ("Do not infer missing player profile fields; request them only when material.",)
    return AdaptationResult(applicable=not missing, matched_constraints=matched, missing_profile_fields=missing, recommendation_notes=notes)
