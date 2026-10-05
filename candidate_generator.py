"""Generic feasible team/candidate generation for FGF v7.

Generates combinations only from the player's explicit available roster.
Event-specific role/tag requirements are supplied by the event model; no
single event's Champion ordering is reused for another event.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from event_strategy_engine import CandidateAction, EventStrategyModel, PlayerState


@dataclass(frozen=True)
class GeneratedCandidate:
    name: str
    entities: Tuple[str, ...]
    tags: Tuple[str, ...]
    coverage: Tuple[str, ...] = ()
    missing_priorities: Tuple[str, ...] = ()


def _canon(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def generate_combinations(
    player: PlayerState,
    *,
    team_size: int = 3,
    limit: int = 20,
    role_tags: Mapping[str, Sequence[str]] | None = None,
) -> Tuple[GeneratedCandidate, ...]:
    """Generate unique combinations from owned entities only."""
    if team_size < 1:
        raise ValueError("team_size must be >= 1")

    owned = tuple(dict.fromkeys(player.owned_entities))
    if len(owned) < team_size:
        return ()

    role_tags = role_tags or {}
    results: List[GeneratedCandidate] = []

    for combo in combinations(owned, team_size):
        tags: List[str] = []
        for entity in combo:
            tags.extend(role_tags.get(entity, ()))
        unique_tags = tuple(dict.fromkeys(tags))
        results.append(
            GeneratedCandidate(
                name=" + ".join(combo),
                entities=combo,
                tags=unique_tags,
            )
        )
        if len(results) >= limit:
            break

    return tuple(results)


def annotate_event_coverage(
    candidates: Iterable[GeneratedCandidate],
    event: EventStrategyModel,
) -> Tuple[GeneratedCandidate, ...]:
    priorities = tuple(_canon(x) for x in event.tactical_priorities)
    out = []
    for candidate in candidates:
        tags = tuple(_canon(x) for x in candidate.tags)
        coverage = tuple(
            priority for priority in priorities
            if any(priority in tag or tag in priority for tag in tags)
        )
        missing = tuple(p for p in priorities if p not in coverage)
        out.append(
            GeneratedCandidate(
                name=candidate.name,
                entities=candidate.entities,
                tags=candidate.tags,
                coverage=coverage,
                missing_priorities=missing,
            )
        )
    return tuple(out)


def to_actions(candidates: Iterable[GeneratedCandidate]) -> Tuple[CandidateAction, ...]:
    return tuple(
        CandidateAction(
            name=c.name,
            entities=c.entities,
            tags=c.tags,
            evidence_state="derived",
            rationale=(
                f"Covers: {', '.join(c.coverage) if c.coverage else 'none established'}; "
                f"missing: {', '.join(c.missing_priorities) if c.missing_priorities else 'none'}."
            ),
        )
        for c in candidates
    )
