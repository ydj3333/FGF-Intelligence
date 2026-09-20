"""FGF Knowledge Quality Analyzer.

Admin-side quality diagnostics for the evidence graph.

Important: scores are diagnostic signals, not truth labels. Authority comes from
the evidence hierarchy and explicit review state; this module never promotes,
demotes, deletes, or supersedes claims.
"""
from dataclasses import dataclass, asdict
from enum import Enum
import re
from typing import Dict, List, Optional, Tuple


class ClaimQuality(Enum):
    EXCELLENT = "excellent"
    GOOD = "good"
    ACCEPTABLE = "acceptable"
    WEAK = "weak"
    PROBLEMATIC = "problematic"


@dataclass
class ClaimAnalysis:
    claim_id: int
    quality_score: float
    quality_tier: ClaimQuality
    coverage_score: float
    confidence_score: float
    issues: List[str]
    suggestions: List[str]
    related_claims: List[int]

    def to_dict(self) -> Dict:
        out = asdict(self)
        out["quality_tier"] = self.quality_tier.value
        return out


STOPWORDS = {
    "the", "a", "an", "and", "or", "to", "of", "for", "in", "on", "at",
    "is", "are", "was", "were", "be", "can", "do", "does", "how", "what",
    "which", "when", "where", "why", "with", "this", "that", "from", "by",
    "as", "it", "its", "their", "your", "you", "my", "all", "only", "just",
}

TIER_BASE = {
    1: 1.00,
    2: 0.82,
    3: 0.62,
    4: 0.45,
    5: 0.30,
    6: 0.15,
}

CLAIM_TYPE_WEIGHTS = {
    "FACT": 1.0,
    "MECHANIC": 1.0,
    "CALCULATION": 1.0,
    "RULE": 1.0,
    "VIDEO DEMONSTRATION": 0.9,
    "RECOMMENDATION": 0.75,
    "OPINION": 0.55,
    "RUMOR": 0.20,
}


def _tier(claim: Dict) -> int:
    raw = str(claim.get("Evidence Tier", claim.get("tier", "")))
    m = re.search(r"Tier\s*([1-6])", raw, re.I)
    if m:
        return int(m.group(1))
    try:
        return int(claim.get("tier"))
    except (TypeError, ValueError):
        return 6


def _status(claim: Dict) -> str:
    return str(claim.get("Status", "Under Review")).strip().lower()


def _text(claim: Dict) -> str:
    return str(
        claim.get("Claim", claim.get("claim", "")) + " " +
        claim.get("Category", "") + " " +
        claim.get("Notes", "")
    ).strip()


def _tokens(text: str) -> set:
    return {
        x for x in re.findall(r"[a-z0-9]+", text.lower())
        if x not in STOPWORDS and len(x) > 2
    }


def _claim_id(claim: Dict) -> int:
    try:
        return int(claim.get("id", claim.get("Claim ID")))
    except (TypeError, ValueError):
        return -1


class KnowledgeAnalyzer:
    """Analyze evidence quality without altering the canonical knowledge graph."""

    def __init__(self, claims: List[Dict], sources: Optional[List[Dict]] = None):
        self.claims = claims
        self.sources = sources or []
        self.analyses: Dict[int, ClaimAnalysis] = {}

    def analyze_all(self) -> Dict[int, ClaimAnalysis]:
        for claim in self.claims:
            cid = _claim_id(claim)
            if cid >= 0:
                self.analyses[cid] = self.analyze_claim(claim)
        return self.analyses

    def analyze_claim(self, claim: Dict) -> ClaimAnalysis:
        issues: List[str] = []
        suggestions: List[str] = []
        tier = _tier(claim)
        status = _status(claim)
        text = _text(claim)

        contradictions = self._find_contradictions(claim)
        related = self._find_related_claims(claim)

        if not text or len(text) < 25:
            issues.append("too_short")
            suggestions.append("add_specificity")

        if not claim.get("Source") and not claim.get("source"):
            issues.append("missing_source")
            suggestions.append("add_source_attribution")

        if tier >= 3 and not (claim.get("Source") or claim.get("source") or claim.get("provenance")):
            issues.append("missing_provenance")
            suggestions.append("add_source_attribution")

        if status in {"rejected", "superseded"}:
            issues.append(status)
            suggestions.append("exclude_from_current_truth_retrieval")

        if status == "under review":
            issues.append("under_review")
            suggestions.append("verify_or_resolve")

        if contradictions:
            issues.append("has_preserved_conflict")
            suggestions.append("review_and_resolve_or_preserve_conflict")

        if len(related) >= 4:
            issues.append("high_related_claim_density")
            suggestions.append("check_for_duplicate_or_complementary_claims")

        quality_score = self._score_quality(claim, contradictions)
        confidence_score = self._score_confidence(claim, contradictions)
        coverage_score = self._score_coverage(claim, related)

        # A conflict is a diagnostic issue, not permission to call the claim false.
        if contradictions:
            quality_tier = ClaimQuality.PROBLEMATIC
        else:
            quality_tier = self._map_quality_tier(quality_score)

        return ClaimAnalysis(
            claim_id=_claim_id(claim),
            quality_score=quality_score,
            quality_tier=quality_tier,
            coverage_score=coverage_score,
            confidence_score=confidence_score,
            issues=issues,
            suggestions=list(dict.fromkeys(suggestions)),
            related_claims=[_claim_id(c) for c in related if _claim_id(c) >= 0],
        )

    def _score_quality(self, claim: Dict, contradictions: List[Dict]) -> float:
        tier = _tier(claim)
        score = TIER_BASE.get(tier, 0.10)

        claim_type = str(
            claim.get("Claim Type", claim.get("claim_type", "FACT"))
        ).upper()
        score *= CLAIM_TYPE_WEIGHTS.get(claim_type, 0.8)

        text = _text(claim)
        if len(text) >= 50:
            score += 0.05
        if re.search(r"\b\d+(?:\.\d+)?%?\b", text):
            score += 0.05
        if claim.get("Source") or claim.get("source"):
            score += 0.05
        if claim.get("Timestamp"):
            score += 0.03
        if str(claim.get("Verification Status", "")).lower() in {
            "verified", "tested", "confirmed"
        }:
            score += 0.07
        if contradictions:
            score *= 0.65
        if _status(claim) in {"rejected", "superseded"}:
            score *= 0.15

        return round(max(0.0, min(score, 1.0)), 4)

    def _score_confidence(self, claim: Dict, contradictions: List[Dict]) -> float:
        tier = _tier(claim)
        score = TIER_BASE.get(tier, 0.10)

        explicit = str(claim.get("Confidence", "")).lower()
        if explicit == "high":
            score += 0.08
        elif explicit == "medium":
            score += 0.02
        elif explicit == "low":
            score -= 0.08

        if claim.get("Source") or claim.get("source"):
            score += 0.04
        if claim.get("Timestamp"):
            score += 0.02
        if str(claim.get("Verification Status", "")).lower() in {"verified", "tested"}:
            score += 0.06

        if contradictions:
            score -= 0.20
        if _status(claim) in {"rejected", "superseded"}:
            score = min(score, 0.10)
        elif _status(claim) == "under review":
            score -= 0.10

        return round(max(0.0, min(score, 1.0)), 4)

    def _score_coverage(self, claim: Dict, related: List[Dict]) -> float:
        """Estimate contextual coverage, not truth.

        A claim gets higher coverage when related claims cover the same topic
        across different claim types/source tiers. This deliberately avoids the
        original constant 0.7 placeholder.
        """
        if not related:
            return 0.35

        tiers = {_tier(c) for c in related}
        categories = {
            str(c.get("Category", "")).strip().lower()
            for c in related
            if c.get("Category")
        }
        types = {
            str(c.get("Claim Type", c.get("claim_type", ""))).strip().lower()
            for c in related
            if c.get("Claim Type") or c.get("claim_type")
        }

        score = 0.25
        score += min(0.30, 0.10 * len(tiers))
        score += min(0.20, 0.05 * len(categories))
        score += min(0.15, 0.05 * len(types))
        score += min(0.10, 0.02 * len(related))
        return round(min(score, 1.0), 4)

    def _find_contradictions(self, claim: Dict) -> List[Dict]:
        """Conservative contradiction detector.

        It only flags explicit polarity/value collisions within closely related
        claims. It does not infer contradiction from unrelated words appearing
        anywhere in the corpus.
        """
        text = _text(claim).lower()
        cid = _claim_id(claim)
        results = []

        for other in self.claims:
            if _claim_id(other) == cid:
                continue
            other_text = _text(other).lower()

            # Require substantial lexical/topic overlap first.
            a, b = _tokens(text), _tokens(other_text)
            if len(a & b) < 3:
                continue

            pairs = (
                ("increases", "decreases"),
                ("increase", "decrease"),
                ("higher", "lower"),
                ("more", "less"),
                ("requires", "does not require"),
                ("required", "not required"),
                ("unlocks", "does not unlock"),
                ("available", "unavailable"),
                ("yes", "no"),
            )
            if any((x in text and y in other_text) or
                   (y in text and x in other_text) for x, y in pairs):
                results.append(other)

        return results

    def _find_related_claims(self, claim: Dict, limit: int = 12) -> List[Dict]:
        cid = _claim_id(claim)
        base = _tokens(_text(claim))
        if not base:
            return []

        scored: List[Tuple[float, Dict]] = []
        for other in self.claims:
            if _claim_id(other) == cid:
                continue
            other_tokens = _tokens(_text(other))
            if not other_tokens:
                continue

            inter = len(base & other_tokens)
            union = len(base | other_tokens)
            jaccard = inter / max(union, 1)
            category_bonus = (
                0.10 if str(other.get("Category", "")).lower()
                == str(claim.get("Category", "")).lower() else 0.0
            )
            if inter >= 3:
                scored.append((jaccard + category_bonus, other))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [c for _, c in scored[:limit]]

    def _map_quality_tier(self, score: float) -> ClaimQuality:
        if score >= 0.85:
            return ClaimQuality.EXCELLENT
        if score >= 0.68:
            return ClaimQuality.GOOD
        if score >= 0.48:
            return ClaimQuality.ACCEPTABLE
        if score >= 0.25:
            return ClaimQuality.WEAK
        return ClaimQuality.PROBLEMATIC

    def get_summary(self) -> Dict:
        if not self.analyses:
            self.analyze_all()

        total = len(self.analyses)
        if not total:
            return {
                "total_claims": 0,
                "quality_distribution": {},
                "top_issues": [],
                "average_quality": 0.0,
                "average_coverage": 0.0,
                "average_confidence": 0.0,
            }

        quality_counts: Dict[str, int] = {}
        issue_counts: Dict[str, int] = {}
        for analysis in self.analyses.values():
            key = analysis.quality_tier.value
            quality_counts[key] = quality_counts.get(key, 0) + 1
            for issue in analysis.issues:
                issue_counts[issue] = issue_counts.get(issue, 0) + 1

        return {
            "total_claims": total,
            "quality_distribution": quality_counts,
            "top_issues": sorted(
                issue_counts.items(), key=lambda x: x[1], reverse=True
            )[:10],
            "average_quality": round(
                sum(a.quality_score for a in self.analyses.values()) / total, 4
            ),
            "average_coverage": round(
                sum(a.coverage_score for a in self.analyses.values()) / total, 4
            ),
            "average_confidence": round(
                sum(a.confidence_score for a in self.analyses.values()) / total, 4
            ),
        }

    def export_report(self) -> Dict:
        if not self.analyses:
            self.analyze_all()
        return {
            "summary": self.get_summary(),
            "claims": [a.to_dict() for a in self.analyses.values()],
            "note": (
                "Diagnostic only. Scores do not change evidence authority, "
                "claim status, or current truth."
            ),
        }
