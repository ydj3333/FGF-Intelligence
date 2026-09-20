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

    # Separate diagnostic dimensions. These are not quality penalties.
    has_preserved_conflict: bool
    is_superseded: bool
    is_current: bool
    contradictions: List[int]

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
        # Some canonical corpus exports do not carry an explicit claim ID.
        # Assign deterministic 1-based internal IDs without mutating the corpus.
        self._internal_ids = {
            id(claim): (_claim_id(claim) if _claim_id(claim) >= 0 else index)
            for index, claim in enumerate(self.claims, start=1)
        }

    def _id_for(self, claim: Dict) -> int:
        return self._internal_ids.get(id(claim), _claim_id(claim))

    def analyze_all(self) -> Dict[int, ClaimAnalysis]:
        for claim in self.claims:
            cid = self._id_for(claim)
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

        is_superseded = status == "superseded"
        is_current = status == "confirmed"
        has_preserved_conflict = bool(contradictions)

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

        # Conflict is a diagnostic dimension, never a quality-tier penalty.
        if has_preserved_conflict:
            issues.append("has_preserved_conflict")
            suggestions.append("review_conflict_context")

        if len(related) >= 4:
            issues.append("high_related_claim_density")
            suggestions.append("check_for_duplicate_or_complementary_claims")

        # These scores are independent dimensions.
        quality_score = self._score_quality(claim)
        confidence_score = self._score_confidence(claim)
        coverage_score = self._score_coverage(claim, related)
        quality_tier = self._map_quality_tier(quality_score)

        return ClaimAnalysis(
            claim_id=cid,
            quality_score=quality_score,
            quality_tier=quality_tier,
            coverage_score=coverage_score,
            confidence_score=confidence_score,
            has_preserved_conflict=has_preserved_conflict,
            is_superseded=is_superseded,
            is_current=is_current,
            contradictions=[self._id_for(c) for c in contradictions if self._id_for(c) >= 0],
            issues=list(dict.fromkeys(issues)),
            suggestions=list(dict.fromkeys(suggestions)),
            related_claims=[self._id_for(c) for c in related if self._id_for(c) >= 0],
        )

    def _score_quality(self, claim: Dict) -> float:
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
        # Conflict and historical status are separate diagnostics.
        return round(max(0.0, min(score, 1.0)), 4)

    def _score_confidence(self, claim: Dict) -> float:
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

        # Confidence is independent from conflict/current-truth status.
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

        Explicit polarity collisions require close topic overlap. Numerical
        disagreement additionally requires the same entity anchor and the same
        normalized relation. This prevents Core 8 vs Core 9 from being treated
        as a contradiction merely because both contain numbers.
        """
        text = _text(claim).lower()
        cid = self._id_for(claim)
        category = str(claim.get("Category", "")).strip().lower()
        results = []

        polarity_pairs = (
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

        def entity_anchors(value: str) -> set:
            words = {
                "core", "level", "stage", "tier", "building", "ship", "hero",
                "champion", "flagship", "port", "chapter", "queue", "wave",
                "slot", "node", "research", "technology", "tech", "mission",
                "zone",
            }
            anchors = set()
            for word in words:
                anchors.update(
                    f"{word} {n}"
                    for n in re.findall(rf"\b{re.escape(word)}\s+(\d+)\b", value)
                )
            return anchors

        def value_numbers(value: str) -> List[str]:
            tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", value)
            value_words = {
                "requires", "require", "costs", "cost", "uses", "use", "gives",
                "grants", "provides", "produces", "damage", "speed", "percent",
                "seconds", "minutes", "hours", "alloy", "seed", "seeds",
            }
            values = []
            for i, token in enumerate(tokens):
                if not re.fullmatch(r"\d+(?:\.\d+)?", token):
                    continue
                prev = tokens[i - 1] if i else ""
                nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
                if prev in value_words or nxt in value_words or float(token) >= 100:
                    values.append(token)
            return values

        def relation_signature(value: str) -> str:
            tokens = re.findall(r"[a-z]+|\d+(?:\.\d+)?", value)
            value_words = {
                "requires", "require", "costs", "cost", "uses", "use", "gives",
                "grants", "provides", "produces", "damage", "speed", "percent",
                "seconds", "minutes", "hours", "alloy", "seed", "seeds",
            }
            out = []
            for i, token in enumerate(tokens):
                if re.fullmatch(r"\d+(?:\.\d+)?", token):
                    prev = tokens[i - 1] if i else ""
                    nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
                    if prev in value_words or nxt in value_words or float(token) >= 100:
                        out.append("<value>")
                    else:
                        out.append(token)
                elif token not in STOPWORDS:
                    out.append(token)
            return " ".join(out)

        for other in self.claims:
            if self._id_for(other) == cid:
                continue

            other_text = _text(other).lower()
            other_category = str(other.get("Category", "")).strip().lower()

            if category and other_category and category != other_category:
                continue

            a, b = _tokens(text), _tokens(other_text)
            if len(a & b) < 3:
                continue

            polarity_conflict = any(
                (x in text and y in other_text) or
                (y in text and x in other_text)
                for x, y in polarity_pairs
            )

            numeric_conflict = False
            nums_a = value_numbers(text)
            nums_b = value_numbers(other_text)
            if nums_a and nums_b and nums_a != nums_b:
                anchors_a = entity_anchors(text)
                anchors_b = entity_anchors(other_text)
                same_relation = relation_signature(text) == relation_signature(other_text)
                if same_relation and anchors_a and anchors_a == anchors_b:
                    numeric_conflict = True

            if polarity_conflict or numeric_conflict:
                results.append(other)

        return results

    def _find_related_claims(self, claim: Dict, limit: int = 12) -> List[Dict]:
        cid = self._id_for(claim)
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
        conflict_count = 0
        superseded_count = 0
        current_count = 0

        for analysis in self.analyses.values():
            key = analysis.quality_tier.value
            quality_counts[key] = quality_counts.get(key, 0) + 1
            if analysis.has_preserved_conflict:
                conflict_count += 1
            if analysis.is_superseded:
                superseded_count += 1
            if analysis.is_current:
                current_count += 1
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
            "conflict_count": conflict_count,
            "superseded_count": superseded_count,
            "current_count": current_count,
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
