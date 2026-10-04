"""FGF v7 Stage 5 — answer validation / intelligence quality gate.

Validates the final decision surface before it is presented to a player.
This layer checks output integrity, not game mechanics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from constraint_extractor import ExtractedConstraints
from event_strategy_engine import EventStrategyModel, PlayerState
from tactical_optimizer import RankedCandidate


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    issues: tuple[ValidationIssue, ...] = ()
    checks: tuple[str, ...] = ()


def _norm(value: str) -> str:
    return " ".join(value.lower().replace("_", " ").split())


def _owned(candidate_entity: str, owned: Iterable[str]) -> bool:
    c = _norm(candidate_entity)
    return any(c == _norm(x) or c in _norm(x) or _norm(x) in c for x in owned)


def validate_answer(
    *,
    question: str,
    event: EventStrategyModel,
    player: PlayerState,
    constraints: ExtractedConstraints,
    ranked: Sequence[RankedCandidate],
    generated_count: int,
    requested_count: int | None,
    team_size: int,
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    checks: list[str] = []

    if requested_count is not None:
        if len(ranked) > requested_count:
            issues.append(ValidationIssue(
                "requested_count_exceeded", "error",
                f"Requested {requested_count} options but {len(ranked)} were selected.",
            ))
        elif len(ranked) < requested_count:
            checks.append("requested_count_partial")
            issues.append(ValidationIssue(
                "requested_count_unmet", "warning",
                f"Requested {requested_count} options; only {len(ranked)} feasible ranked options exist.",
            ))
        else:
            checks.append("requested_count_exact")
    else:
        checks.append("requested_count_not_specified")

    if generated_count == 0 and player.owned_entities:
        issues.append(ValidationIssue(
            "zero_feasible_candidates", "warning",
            "No feasible combination was generated from the explicit roster.",
        ))
    if generated_count < len(ranked):
        issues.append(ValidationIssue(
            "ranked_exceeds_generated", "error",
            "The ranked output contains more candidates than were generated.",
        ))
    checks.append("generation_bound")

    unavailable = {_norm(x) for x in player.unavailable_entities}
    seen_names: set[str] = set()
    for item in ranked:
        name_key = _norm(item.candidate.name)
        if name_key in seen_names:
            issues.append(ValidationIssue(
                "duplicate_candidate", "error",
                f"Duplicate candidate returned: {item.candidate.name}.",
            ))
        seen_names.add(name_key)

        if len(item.candidate.entities) != team_size:
            issues.append(ValidationIssue(
                "wrong_team_size", "error",
                f"{item.candidate.name} contains {len(item.candidate.entities)} entities; expected {team_size}.",
            ))

        for entity in item.candidate.entities:
            if _norm(entity) in unavailable:
                issues.append(ValidationIssue(
                    "excluded_entity_returned", "error",
                    f"{item.candidate.name} contains explicitly unavailable entity {entity}.",
                ))
            if player.owned_entities and not _owned(entity, player.owned_entities):
                issues.append(ValidationIssue(
                    "unowned_entity_returned", "error",
                    f"{item.candidate.name} contains unconfirmed entity {entity}.",
                ))
    checks.append("roster_integrity")

    for item in ranked:
        for priority in item.priority_coverage:
            if not any(
                _norm(priority) == _norm(x)
                or _norm(priority) in _norm(x)
                or _norm(x) in _norm(priority)
                for x in event.tactical_priorities
            ):
                issues.append(ValidationIssue(
                    "event_priority_leak", "error",
                    f"{item.candidate.name} contains priority coverage not established by {event.event_key}.",
                ))
    checks.append("event_isolation")

    evidence_values = {_norm(item.evidence_state) for item in ranked}
    if ranked and evidence_values == {"derived"} and event.evidence_state.lower() in {"unknown", "unverified"}:
        issues.append(ValidationIssue(
            "evidence_insufficient", "warning",
            "Selected recommendations are derived and the event model has no established evidence state.",
        ))
    checks.append("evidence_state")

    if constraints.requested_positions:
        issues.append(ValidationIssue(
            "position_order_unverified", "warning",
            "Position/order was requested, but the generic gate will not invent slot mechanics.",
        ))
    checks.append("position_order_safety")

    if event.duration and event.timing_rules:
        checks.append("timing_requires_adapter_review")
    else:
        checks.append("timing_consistency_not_applicable")

    valid = not any(issue.severity == "error" for issue in issues)
    return ValidationResult(valid=valid, issues=tuple(issues), checks=tuple(checks))
