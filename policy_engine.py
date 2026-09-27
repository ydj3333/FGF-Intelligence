"""FGF v6.3 policy gate.

Authority, lifecycle, version/context and player experience are separate
dimensions. This module makes the three-branch rules executable without
rewriting the v6.0 retrieval engine.
"""

from __future__ import annotations
from typing import Any, Dict, Iterable, List


OFFICIAL_TIERS = {
    "Tier 1 — Ultimate/Official",
    "Tier 2 — Official Developer",
}
COMMUNITY_MARKERS = ("community", "creator", "youtube", "tested community")


def _tier(claim: Dict[str, Any]) -> str:
    return str(claim.get("Evidence Tier", claim.get("tier", "")) or "")


def _status(claim: Dict[str, Any]) -> str:
    return str(claim.get("Status", claim.get("status", "")) or "").lower()


def is_official(claim: Dict[str, Any]) -> bool:
    if _tier(claim) in OFFICIAL_TIERS:
        return True
    meta = claim.get("metadata")
    return bool(isinstance(meta, dict) and meta.get("official") is True)


def classify_intent(question: str, question_type: str = "") -> str:
    q = str(question or "").lower()
    if any(x in q for x in (
        "best", "optimal", "recommended", "should i", "priority",
        "most efficient", "worth it", "what should i"
    )) or question_type == "strategy":
        return "strategy"
    if any(x in q for x in (
        "interpret", "interpretation", "what does this mean",
        "implication", "what does this suggest"
    )):
        return "interpretation"
    if question_type in {"generic", ""}:
        return "ambiguous"
    return "factual"


def active_claims(claims: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [
        c for c in claims
        if _status(c) not in {"rejected", "superseded"}
    ]


def evaluate_evidence(claims: Iterable[Dict[str, Any]], intent: str) -> Dict[str, Any]:
    active = active_claims(claims)
    official = [c for c in active if is_official(c)]
    community = [c for c in active if not is_official(c)]

    if intent == "factual":
        usable = official
    else:
        usable = active

    if official:
        state = "CONFIRMED"
    elif len(community) >= 2:
        state = "COMMUNITY_CONSENSUS"
    elif community:
        state = "COMMUNITY_INTERPRETATION"
    else:
        state = "INSUFFICIENT_EVIDENCE"

    return {
        "intent": intent,
        "usable": usable,
        "official_facts": official,
        "community_evidence": community,
        "evidence_state": state,
    }


def enforce(
    answer: str,
    claims: Iterable[Dict[str, Any]],
    question: str,
    question_type: str = "",
) -> Dict[str, Any]:
    intent = classify_intent(question, question_type)
    ev = evaluate_evidence(claims, intent)
    warnings: List[str] = []

    if intent == "factual" and not ev["official_facts"]:
        return {
            "answer": (
                "The current corpus does not contain authoritative official/"
                "developer evidence sufficient to state this as a game fact."
            ),
            "intent": intent,
            "evidence_state": "INSUFFICIENT_EVIDENCE",
            "claims": [],
            "warnings": [
                "Community/YouTube/experience evidence was excluded from the factual answer."
            ],
            "abstained": True,
        }

    if intent in {"strategy", "interpretation"} and ev["community_evidence"]:
        warnings.append(
            "Community/YouTube/experience evidence is supplementary and is not official game truth."
        )

    return {
        "answer": answer,
        "intent": intent,
        "evidence_state": ev["evidence_state"],
        "claims": ev["usable"],
        "warnings": warnings,
        "abstained": False,
    }
