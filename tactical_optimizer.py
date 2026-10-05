"""FGF v7 Stage 4 — event-specific tactical optimization.

Optimization happens only after hard player constraints have been satisfied.
The optimizer ranks feasible combinations using:
- event tactical-priority coverage,
- event scoring-factor coverage,
- combination synergy (when explicitly supplied),
- evidence strength,
- completeness / missing-priority penalty.

It never treats popularity as a game mechanic and never invents synergy or
position rules. Unsupported position/order information must be supplied by the
event adapter as derived/inference evidence, not silently assumed.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Mapping, Sequence, Tuple

from candidate_generator import GeneratedCandidate
from event_strategy_engine import EventStrategyModel, PlayerState, CandidateAction, validate_player_constraints


@dataclass(frozen=True)
class TacticalWeights:
    priority_coverage: float = 5.0
    scoring_coverage: float = 3.0
    synergy: float = 2.0
    evidence: float = 1.0
    missing_priority: float = 2.0


@dataclass(frozen=True)
class RankedCandidate:
    candidate: GeneratedCandidate
    score: float
    priority_coverage: Tuple[str, ...]
    scoring_coverage: Tuple[str, ...]
    synergy: Tuple[str, ...]
    evidence_state: str
    explanation: str


def _norm(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _matches(tag: str, fact: str) -> bool:
    a, b = _norm(tag), _norm(fact)
    return a == b or a in b or b in a


def _coverage(tags: Iterable[str], targets: Iterable[str]) -> Tuple[str, ...]:
    tags = tuple(tags)
    return tuple(target for target in targets if any(_matches(tag, target) for tag in tags))


def _evidence_score(state: str) -> float:
    value = state.lower().strip()
    if value in {"tier 1", "official", "primary_in_game_ui"}:
        return 1.0
    if value in {"tier 2", "community_enrichment"}:
        return 0.5
    return 0.0


def rank_candidates(
    event: EventStrategyModel,
    player: PlayerState,
    candidates: Sequence[GeneratedCandidate],
    *,
    synergy_map: Mapping[Tuple[str, ...], Sequence[str]] | None = None,
    evidence_map: Mapping[Tuple[str, ...], str] | None = None,
    weights: TacticalWeights = TacticalWeights(),
    limit: int = 5,
) -> Tuple[RankedCandidate, ...]:
    """Rank feasible candidates; hard constraints are applied before scoring."""
    synergy_map = synergy_map or {}
    evidence_map = evidence_map or {}
    ranked = []

    for candidate in candidates:
        action = CandidateAction(
            name=candidate.name,
            entities=candidate.entities,
            tags=candidate.tags,
            evidence_state=evidence_map.get(tuple(candidate.entities), "derived"),
            rationale="",
        )
        valid, _ = validate_player_constraints(action, player)
        if not valid:
            continue

        priorities = _coverage(candidate.tags, event.tactical_priorities)
        scoring = _coverage(candidate.tags, event.scoring_factors)
        synergy = tuple(synergy_map.get(tuple(candidate.entities), ()))
        evidence = evidence_map.get(tuple(candidate.entities), "derived")

        raw = (
            len(priorities) * weights.priority_coverage
            + len(scoring) * weights.scoring_coverage
            + len(synergy) * weights.synergy
            + _evidence_score(evidence) * weights.evidence
            - len(candidate.missing_priorities) * weights.missing_priority
        )
        explanation = (
            f"priority coverage={len(priorities)}/{len(event.tactical_priorities)}; "
            f"scoring coverage={len(scoring)}/{len(event.scoring_factors)}; "
            f"synergy={len(synergy)}; evidence={evidence}; "
            f"missing priorities={len(candidate.missing_priorities)}."
        )
        ranked.append(RankedCandidate(
            candidate=candidate,
            score=raw,
            priority_coverage=priorities,
            scoring_coverage=scoring,
            synergy=synergy,
            evidence_state=evidence,
            explanation=explanation,
        ))

    ranked.sort(key=lambda x: (-x.score, -len(x.priority_coverage), x.candidate.name))
    return tuple(ranked[:limit])


def why_first_beats_second(
    first: RankedCandidate,
    second: RankedCandidate,
) -> str:
    """Produce an auditable comparison rather than a generic 'best combo' claim."""
    deltas = []
    if len(first.priority_coverage) != len(second.priority_coverage):
        deltas.append(
            f"covers {len(first.priority_coverage)} vs {len(second.priority_coverage)} event priorities"
        )
    if len(first.scoring_coverage) != len(second.scoring_coverage):
        deltas.append(
            f"covers {len(first.scoring_coverage)} vs {len(second.scoring_coverage)} scoring factors"
        )
    if len(first.synergy) != len(second.synergy):
        deltas.append(f"has {len(first.synergy)} vs {len(second.synergy)} explicit synergy links")
    if first.evidence_state != second.evidence_state:
        deltas.append(f"uses {first.evidence_state} evidence vs {second.evidence_state}")

    if not deltas:
        return "No evidence-backed differentiator was found; the ordering is only a deterministic tie-break."
    return "It ranks higher because it " + "; ".join(deltas) + "."
