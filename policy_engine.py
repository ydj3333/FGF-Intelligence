"""FGF v6.3 evidence policy.

Authority, lifecycle, and intent are separate dimensions. This layer prevents
community/YouTube material from silently becoming factual game truth while
still allowing community evidence to inform strategy and interpretation.
"""
from __future__ import annotations
import re

FACTUAL_ALLOWED = ("Tier 1 — Ultimate/Official", "Tier 2 — Official Developer")

def _tier(c):
    return str(c.get("Evidence Tier", c.get("tier", "")) or "")

def _status(c):
    return str(c.get("Status", c.get("status", "")) or "").lower()

def is_official(c):
    t=_tier(c)
    return t in FACTUAL_ALLOWED or bool((c.get("metadata") or {}).get("official"))

def classify_policy_intent(question_type: str, question: str) -> str:
    q=question.lower()
    if any(x in q for x in ("best ", "best?", "optimal", "recommended", "should i", "priority", "most efficient", "worth it", "what should i")):
        return "strategy"
    if any(x in q for x in ("why ", "what does this mean", "interpret", "how should i interpret", "what is the implication")):
        return "interpretation"
    if question_type in ("strategy",):
        return "strategy"
    if question_type in ("generic",):
        return "ambiguous"
    return "factual"

def evaluate_evidence(claims, intent):
    active=[c for c in claims if _status(c) not in ("rejected","superseded")]
    official=[c for c in active if is_official(c)]
    community=[c for c in active if not is_official(c)]
    if intent=="factual":
        # Tier 2 Tested Community is deliberately excluded from factual answers.
        usable=official
    elif intent in ("strategy","interpretation"):
        usable=active
    else:
        usable=active
    return {
        "intent": intent,
        "usable": usable,
        "official_facts": official,
        "community_evidence": community,
        "evidence_state": (
            "confirmed" if official else
            "community_consensus" if len(community)>=2 else
            "community_interpretation" if community else
            "insufficient_evidence"
        )
    }

def apply_policy(answer_text, claims, question_type, question):
    intent=classify_policy_intent(question_type, question)
    ev=evaluate_evidence(claims,intent)
    if intent=="factual" and claims and not ev["usable"]:
        return {
            "answer": "The current corpus does not contain authoritative official/developer evidence sufficient to state this as a game fact. Community/YouTube material is available, but is kept out of the factual answer.",
            "intent": intent,
            "evidence_state": "insufficient_evidence",
            "claims": [],
            "warnings": ["Community/YouTube evidence was excluded from the factual answer."],
            "abstained": True,
        }
    warnings=[]
    if intent in ("strategy","interpretation") and ev["community_evidence"]:
        warnings.append("Community/YouTube evidence is being used as strategy or interpretation, not as official game truth.")
    return {
        "answer": answer_text,
        "intent": intent,
        "evidence_state": ev["evidence_state"],
        "claims": ev["usable"],
        "warnings": warnings,
        "abstained": False,
    }
