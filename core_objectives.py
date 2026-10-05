"""Permanent FGF Intelligence core-objective contract.

This is a compatibility contract for every future intelligence layer.
It is derived from the repository's existing V4/V4.1, v6.3, v6.6 and v7
architecture. It does not introduce a new product objective.

Rule: a later stage may enrich an established Core answer, but may not replace,
downgrade, genericize, or erase it.
"""

from __future__ import annotations

from typing import Any, Dict


CORE_OBJECTIVES = (
    "core_first",
    "intent_sovereign",
    "evidence_provenance",
    "lifecycle_scope_safety",
    "safe_abstention_no_invention",
    "specialized_answer_preservation",
    "complete_reasoning_chains",
    "player_constraint_integrity",
    "operational_answer_integrity",
    "experience_and_community_are_additive",
    "historical_conflict_preservation",
    "regression_benchmark_preservation",
)


def core_is_established(core_result: Dict[str, Any]) -> bool:
    """True only when the existing Core produced an established answer."""
    if not core_result:
        return False
    if core_result.get("answer_type") in {"knowledge_abstention", "knowledge_policy"}:
        return False
    return bool(core_result.get("evidence")) and bool(core_result.get("answer"))


def preserve_core_answer(core_result: Dict[str, Any], enriched_answer: str) -> str:
    """Return the enriched answer without allowing an established Core answer to disappear.

    This is intentionally conservative: if Core is established, the exact Core
    answer must remain in the final player-facing answer. If Core is not
    established, later fallback/enrichment is allowed to provide a separately
    labelled answer.
    """
    baseline = str(core_result.get("answer", "") or "").strip()
    enriched = str(enriched_answer or "").strip()
    if not core_is_established(core_result):
        return enriched
    if not enriched:
        raise ValueError("Established Core answer cannot be replaced by an empty answer.")
    if baseline not in enriched:
        raise ValueError("Established Core answer was replaced or discarded by a later layer.")
    return enriched


def validate_core_preservation(core_result: Dict[str, Any], final_result: Dict[str, Any]) -> None:
    """Raise if a later layer violates the permanent Core-first contract."""
    baseline = str(core_result.get("answer", "") or "").strip()
    final = str(final_result.get("answer", "") or "").strip()
    if core_is_established(core_result):
        if not final:
            raise AssertionError("Core-established answer was erased.")
        if baseline not in final:
            raise AssertionError("Core-established answer was not preserved.")
        if final_result.get("abstained") is True:
            raise AssertionError("A later layer downgraded an established Core answer to abstention.")
