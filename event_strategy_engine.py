"""FGF v7 generic Event Strategy / Constraint Engine.

This module separates event-specific facts from reusable decision logic.

Event data describes *what the event rewards and requires*.
Player state describes *what the player can actually use*.
The engine evaluates candidate actions without assuming that one event's
strategy transfers to another event.

It deliberately distinguishes:
- evidence-backed event facts,
- player constraints,
- derived tactical recommendations,
- unresolved/unknown mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple
import re

from constraint_extractor import ExtractedConstraints, extract_constraints


@dataclass(frozen=True)
class EventStrategyModel:
    event_key: str
    objective: str
    victory_conditions: Tuple[str, ...] = ()
    scoring_factors: Tuple[str, ...] = ()
    stages: Tuple[str, ...] = ()
    tactical_priorities: Tuple[str, ...] = ()
    timing_rules: Tuple[str, ...] = ()
    resource_priorities: Tuple[str, ...] = ()
    duration: Optional[str] = None
    evidence_state: str = "unknown"

    @classmethod
    def from_mapping(cls, event_key: str, data: Mapping[str, Any]) -> "EventStrategyModel":
        def seq(key: str) -> Tuple[str, ...]:
            value = data.get(key, ())
            if isinstance(value, str):
                return (value,)
            return tuple(str(x) for x in value)

        return cls(
            event_key=event_key,
            objective=str(data.get("objective", "")),
            victory_conditions=seq("victory_conditions"),
            scoring_factors=seq("scoring_factors"),
            stages=seq("stages"),
            tactical_priorities=seq("tactical_priorities"),
            timing_rules=seq("timing_rules"),
            resource_priorities=seq("resource_priorities"),
            duration=str(data["duration"]) if data.get("duration") is not None else None,
            evidence_state=str(data.get("evidence_state", "unknown")),
        )


@dataclass(frozen=True)
class PlayerState:
    owned_entities: Tuple[str, ...] = ()
    unavailable_entities: Tuple[str, ...] = ()
    objective: Optional[str] = None
    role: Optional[str] = None
    resources: Mapping[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class CandidateAction:
    name: str
    entities: Tuple[str, ...] = ()
    tags: Tuple[str, ...] = ()
    evidence_state: str = "unknown"
    rationale: str = ""


@dataclass(frozen=True)
class StrategyDecision:
    selected: Tuple[CandidateAction, ...]
    rejected: Tuple[Tuple[str, str], ...]
    assumptions: Tuple[str, ...]
    confidence: str


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _matches(candidate: str, owned: Iterable[str]) -> bool:
    c = _norm(candidate)
    return any(c == _norm(x) or c in _norm(x) or _norm(x) in c for x in owned)


def validate_player_constraints(
    candidate: CandidateAction,
    player: PlayerState,
) -> Tuple[bool, str]:
    """Hard-filter candidate actions against explicit player constraints."""
    unavailable = set(_norm(x) for x in player.unavailable_entities)
    for entity in candidate.entities:
        if _norm(entity) in unavailable:
            return False, f"{entity} is explicitly unavailable."

    if player.owned_entities:
        missing = [x for x in candidate.entities if not _matches(x, player.owned_entities)]
        if missing:
            return False, f"Requires unavailable/unconfirmed player entities: {', '.join(missing)}."

    return True, ""


def score_candidate(
    candidate: CandidateAction,
    event: EventStrategyModel,
) -> float:
    """Score a candidate against the event model, never against another event."""
    priorities = {_norm(x) for x in event.tactical_priorities}
    scoring = {_norm(x) for x in event.scoring_factors}
    tags = {_norm(x) for x in candidate.tags}

    score = 0.0
    for tag in tags:
        if any(tag in p or p in tag for p in priorities):
            score += 3.0
        if any(tag in s or s in tag for s in scoring):
            score += 2.0

    if candidate.evidence_state.lower() in {"tier 1", "official", "primary_in_game_ui"}:
        score += 2.0
    elif candidate.evidence_state.lower() in {"tier 2", "community_enrichment"}:
        score += 1.0

    return score


def decide(
    event: EventStrategyModel,
    player: PlayerState,
    candidates: Sequence[CandidateAction],
    limit: int = 3,
) -> StrategyDecision:
    """Filter first, then score, then rank."""
    viable: List[Tuple[float, CandidateAction]] = []
    rejected: List[Tuple[str, str]] = []

    for candidate in candidates:
        valid, reason = validate_player_constraints(candidate, player)
        if not valid:
            rejected.append((candidate.name, reason))
            continue
        viable.append((score_candidate(candidate, event), candidate))

    viable.sort(key=lambda item: (-item[0], item[1].name))
    selected = tuple(item[1] for item in viable[:limit])

    assumptions: List[str] = []
    if not event.tactical_priorities:
        assumptions.append("No event-specific tactical priorities were established.")
    if any(c.evidence_state.lower() not in {"tier 1", "official", "primary_in_game_ui"} for _, c in viable[:limit]):
        assumptions.append("At least one selected recommendation uses non-canonical enrichment evidence.")
    if not selected:
        assumptions.append("No feasible candidate satisfied the player's explicit constraints.")

    if not selected:
        confidence = "insufficient"
    elif assumptions:
        confidence = "conditional"
    else:
        confidence = "supported"

    return StrategyDecision(
        selected=selected,
        rejected=tuple(rejected),
        assumptions=tuple(assumptions),
        confidence=confidence,
    )


def build_player_state_from_question(question: str) -> Tuple[PlayerState, ExtractedConstraints]:
    """Convert only explicit user constraints into PlayerState."""
    constraints = extract_constraints(question)
    return (
        PlayerState(
            owned_entities=constraints.owned_entities,
            unavailable_entities=constraints.unavailable_entities,
        ),
        constraints,
    )


def build_event_model(
    event_key: str,
    *,
    objective: str,
    scoring_factors: Sequence[str] = (),
    tactical_priorities: Sequence[str] = (),
    victory_conditions: Sequence[str] = (),
    stages: Sequence[str] = (),
    timing_rules: Sequence[str] = (),
    resource_priorities: Sequence[str] = (),
    duration: Optional[str] = None,
    evidence_state: str = "unknown",
) -> EventStrategyModel:
    """Canonical constructor used by event adapters and ingestion pipelines."""
    return EventStrategyModel(
        event_key=event_key,
        objective=objective,
        scoring_factors=tuple(scoring_factors),
        tactical_priorities=tuple(tactical_priorities),
        victory_conditions=tuple(victory_conditions),
        stages=tuple(stages),
        timing_rules=tuple(timing_rules),
        resource_priorities=tuple(resource_priorities),
        duration=duration,
        evidence_state=evidence_state,
    )


def solve_question(
    question: str,
    event: EventStrategyModel,
    *,
    team_size: int = 3,
    role_tags: Mapping[str, Sequence[str]] | None = None,
    limit: int = 5,
) -> Dict[str, Any]:
    """End-to-end Stage 2+3+4+5 path: extract, generate, optimize, validate."""
    from candidate_generator import annotate_event_coverage, generate_combinations
    from tactical_optimizer import rank_candidates, why_first_beats_second
    from answer_validator import validate_answer

    player, constraints = build_player_state_from_question(question)
    generated = generate_combinations(
        player, team_size=team_size, limit=10000, role_tags=role_tags
    )
    annotated = annotate_event_coverage(generated, event)
    ranked = rank_candidates(event, player, annotated, limit=limit)

    comparison = None
    if len(ranked) >= 2:
        comparison = why_first_beats_second(ranked[0], ranked[1])

    validation = validate_answer(
        question=question,
        event=event,
        player=player,
        constraints=constraints,
        ranked=ranked,
        generated_count=len(generated),
        requested_count=constraints.requested_count,
        team_size=team_size,
    )

    decision = decide(event, player, tuple(
        CandidateAction(
            name=item.candidate.name,
            entities=item.candidate.entities,
            tags=item.candidate.tags,
            evidence_state=item.evidence_state,
            rationale=item.explanation,
        )
        for item in ranked
    ), limit=limit)

    return {
        "constraints": constraints,
        "player_state": player,
        "generated_count": len(generated),
        "requested_count": constraints.requested_count,
        "decision": decision,
        "ranked_candidates": ranked,
        "comparison": comparison,
        "validation": validation,
    }
