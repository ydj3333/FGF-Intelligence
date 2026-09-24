"""FGF YouTube evidence governance.

YouTube/creator/community material is discovery evidence, not canonical truth.
When no Tier-1 or Tier-2 evidence exists for a claim, the claim is retained as
Tier 3 crowd/community evidence and remains a candidate requiring evaluation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Optional


@dataclass
class EvidenceDecision:
    tier: int
    status: str
    canonical: bool
    classification: str
    user_warning: str
    reason: str


CROWD_WARNING = (
    "Additional community data: this information is suggested or reported by "
    "other players/creators. No Tier 1 or Tier 2 evidence currently verifies "
    "it. Carefully evaluate it before relying on it."
)

def _contradicts(extracted: str, existing: str) -> bool:
    """Conservative contradiction detector for high-risk numeric/polarity changes."""
    import re
    a, b = str(extracted or '').lower(), str(existing or '').lower()
    # Explicit polarity is a strong signal when the same topic is discussed.
    neg = r"\\b(?:not|no|never|cannot|can't|doesn't|does not|isn't|is not|requires no|without)\\b"
    a_neg, b_neg = bool(re.search(neg, a)), bool(re.search(neg, b))
    if a_neg != b_neg:
        return True
    # Different explicit numeric values are contradictory only when both claims
    # share a meaningful subject token. This avoids treating unrelated numbers
    # (e.g. a level and a cost) as contradictions.
    nums_a = set(re.findall(r"\\b\\d+(?:[.,]\\d+)?%?\\b", a))
    nums_b = set(re.findall(r"\\b\\d+(?:[.,]\\d+)?%?\\b", b))
    if nums_a and nums_b and nums_a != nums_b:
        stop={'the','and','for','with','from','that','this','are','you','can','has','have','into','when','then'}
        ta={x for x in re.findall(r"[a-z]{4,}",a) if x not in stop}
        tb={x for x in re.findall(r"[a-z]{4,}",b) if x not in stop}
        if len(ta & tb) >= 2:
            return True
    return False


def _tier_number(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).lower().replace("tier", "").strip()
    try:
        return int(text.split()[0])
    except (ValueError, IndexError):
        return None


def classify_against_existing(
    *,
    existing_claims: Iterable[Dict[str, Any]],
    extracted_claim: Dict[str, Any],
) -> EvidenceDecision:
    """Classify a YouTube claim without promoting it.

    Existing Tier 1/2 evidence wins for truth selection. A YouTube claim can
    corroborate, duplicate, or contradict it, but never silently replace it.
    If no Tier 1/2 evidence is present, the YouTube claim remains Tier 3.
    """
    relevant = list(existing_claims)
    strong = [
        c for c in relevant
        if (_tier_number(c.get("tier")) or _tier_number(c.get("Evidence Tier")))
        in (1, 2)
    ]

    if strong:
        # Do not assume that a semantically nearby Tier 1/2 claim is supportive.
        # If the extracted statement changes polarity or a shared numeric fact,
        # hold it back as a conflict instead of teaching the model the wrong value.
        if any(_contradicts(extracted_claim.get("claim", ""), c.get("claim", c.get("Claim", ""))) for c in strong):
            return EvidenceDecision(
                tier=3,
                status="conflict_candidate",
                canonical=False,
                classification="possible_contradiction_with_t1_t2",
                user_warning="This community/creator claim conflicts with stronger evidence and requires evaluation.",
                reason="A Tier 1/2 claim covers the same subject with incompatible polarity or numeric evidence.",
            )
        same = any(
            str(c.get("status", c.get("Status", ""))).lower()
            in {"current", "verified", "confirmed", "validated"}
            for c in strong
        )
        if same:
            return EvidenceDecision(
                tier=3,
                status="supporting_evidence",
                canonical=False,
                classification="corroborates_or_supports_existing_t1_t2",
                user_warning="YouTube evidence supports stronger existing evidence; canonical truth remains governed by the stronger evidence.",
                reason="Tier 1/2 evidence already exists.",
            )
        return EvidenceDecision(
            tier=3,
            status="conflict_candidate",
            canonical=False,
            classification="possible_contradiction_with_t1_t2",
            user_warning="This community/creator claim differs from stronger evidence and requires evaluation.",
            reason="Tier 1/2 evidence exists but does not establish the same current state.",
        )

    return EvidenceDecision(
        tier=3,
        status="candidate",
        canonical=False,
        classification="crowd_additional_data",
        user_warning=CROWD_WARNING,
        reason="No Tier 1 or Tier 2 evidence was found for the extracted claim.",
    )
