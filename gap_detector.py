"""FGF knowledge-gap detector.

Detects *answerability gaps* rather than simply grouping failed questions.
A gap means the current evidence graph is insufficient, unsupported, or too
weak to answer a question safely. It never creates fictional claims.
"""
from collections import defaultdict
import re
from typing import Dict, List, Optional, Tuple


TOPIC_TERMS = {
    "Energy Core": ["core", "energy core", "fusion seed", "fusion seeds", "refinery"],
    "Fleet Repair": ["repair", "damage", "repair module", "repair cabin", "major damage", "minor damage"],
    "Champions": ["champion", "champions", "hero", "heroes", "team", "composition"],
    "Flagship": ["flagship", "blueprint", "blueprints"],
    "Combat": ["combat", "battle", "beam", "kinetic", "ion", "ionic", "counter", "command point", "cp"],
    "Economy": ["credits", "resource", "resources", "alloy", "metal", "water", "crystals", "farm", "cost"],
    "Events": ["event", "gvg", "guild vs guild", "hunting ground", "arms race", "blackout", "glory"],
    "Guild": ["guild", "rally", "port occupation", "guild technology"],
    "Progression": ["upgrade", "unlock", "progression", "level", "technology", "building"],
}

QUESTION_FAMILIES = {
    "exact_cost": ["cost", "how much", "price", "requires"],
    "time_estimate": ["how long", "time", "hours", "days"],
    "how_to": ["how do i", "how can i", "how to", "where can i"],
    "comparison": ["compare", "versus", " vs ", "difference"],
    "recommendation": ["best", "should i", "priority", "optimal", "recommend"],
    "unlock": ["unlock", "what unlocks", "when does"],
    "limit": ["maximum", "max", "how many", "capacity"],
}


def _text(claim: Dict) -> str:
    return " ".join(
        str(claim.get(k, ""))
        for k in ("Claim", "claim", "Category", "Notes")
    ).strip()


def _status(claim: Dict) -> str:
    return str(claim.get("Status", "Under Review")).strip().lower()


def _tier(claim: Dict) -> int:
    raw = str(claim.get("Evidence Tier", claim.get("tier", "")))
    m = re.search(r"tier\s*([1-6])", raw, re.I)
    if m:
        return int(m.group(1))
    try:
        return int(claim.get("tier"))
    except (TypeError, ValueError):
        return 6


def _topic(question: str) -> str:
    q = question.lower()
    scores = {
        topic: sum(1 for term in terms if term in q)
        for topic, terms in TOPIC_TERMS.items()
    }
    best, score = max(scores.items(), key=lambda x: x[1])
    return best if score else "Other"


def _family(question: str) -> str:
    q = question.lower()
    for family, terms in QUESTION_FAMILIES.items():
        if any(term in q for term in terms):
            return family
    return "general"


class GapDetector:
    """Identify missing/weak evidence without inventing knowledge."""

    def __init__(
        self,
        claims: List[Dict],
        benchmarks: Optional[List[Dict]] = None,
        failed_questions: Optional[List[str]] = None,
        benchmark_results: Optional[List[Dict]] = None,
    ):
        self.claims = claims
        self.benchmarks = benchmarks or []
        self.failed_questions = failed_questions or []
        self.benchmark_results = benchmark_results or []
        self.gaps: List[Dict] = []

    def detect_gaps(self) -> List[Dict]:
        self.gaps = []
        questions = list(dict.fromkeys(
            self.failed_questions +
            [
                str(r.get("question", ""))
                for r in self.benchmark_results
                if r.get("gap") or r.get("answerable") is False
            ]
        ))
        groups = defaultdict(list)
        for question in questions:
            if question.strip():
                groups[(_topic(question), _family(question))].append(question)

        for (topic, family), qs in groups.items():
            support = [self._support(q) for q in qs]
            avg_support = sum(x["score"] for x in support) / len(support)
            unsupported = sum(1 for x in support if not x["answerable"])
            priority = self._priority(topic, family, qs, avg_support, unsupported)

            self.gaps.append({
                "topic": topic,
                "question_family": family,
                "failed_questions": qs,
                "question_count": len(qs),
                "unsupported_count": unsupported,
                "average_support": round(avg_support, 4),
                "priority": round(priority, 4),
                "gap_type": self._gap_type(support),
                "suggested_evidence": self._suggest_evidence(topic, family, qs),
                "reason": self._reason(support),
            })

        self.gaps.sort(key=lambda g: g["priority"], reverse=True)
        return self.gaps

    def _support(self, question: str) -> Dict:
        q = set(re.findall(r"[a-z0-9]+", question.lower()))
        candidates = []
        for claim in self.claims:
            if _status(claim) in {"rejected", "superseded"}:
                continue
            text = set(re.findall(r"[a-z0-9]+", _text(claim).lower()))
            overlap = len(q & text) / max(1, len(q))
            tier = _tier(claim)
            score = overlap + (0.20 if tier == 1 else 0.10 if tier == 2 else 0.0)
            if overlap > 0:
                candidates.append((score, claim))
        candidates.sort(key=lambda x: x[0], reverse=True)
        top = candidates[:5]
        score = top[0][0] if top else 0.0
        # Retrieval overlap alone is not answerability. Exact questions need
        # explicit supporting claims; recommendations need recommendation data.
        family = _family(question)
        if family in {"exact_cost", "time_estimate", "limit"}:
            answerable = score >= 0.72 and any(
                any(ch.isdigit() for ch in _text(c)) for _, c in top[:3]
            )
        elif family == "recommendation":
            answerable = score >= 0.55 and any(
                "recommend" in _text(c).lower() or "best" in _text(c).lower()
                for _, c in top[:3]
            )
        else:
            answerable = score >= 0.60

        return {
            "score": min(score, 1.0),
            "answerable": answerable,
            "top_claim_ids": [
                c.get("id", c.get("Claim ID"))
                for _, c in top[:3]
            ],
        }

    def _priority(
        self, topic: str, family: str, questions: List[str],
        support: float, unsupported: int
    ) -> float:
        # Frequency + inability + user-impact family. This is a work queue
        # priority, not a judgment about gameplay importance.
        impact = {
            "exact_cost": 1.0,
            "time_estimate": 0.9,
            "how_to": 0.9,
            "comparison": 0.8,
            "recommendation": 0.8,
            "unlock": 0.85,
            "limit": 0.75,
            "general": 0.6,
        }.get(family, 0.6)
        frequency = min(len(questions) / 5.0, 1.0)
        failure = unsupported / max(1, len(questions))
        return min(1.0, 0.35 * frequency + 0.45 * failure + 0.20 * impact)

    def _gap_type(self, support: List[Dict]) -> str:
        if all(not x["answerable"] for x in support):
            return "missing_or_unsupported_evidence"
        if any(not x["answerable"] for x in support):
            return "partial_coverage"
        return "retrieval_or_reasoning_gap"

    def _reason(self, support: List[Dict]) -> str:
        if not support:
            return "No benchmark questions supplied."
        if all(not x["answerable"] for x in support):
            return "Available claims do not safely support the failed questions."
        if any(not x["answerable"] for x in support):
            return "Some questions have support while others remain insufficiently grounded."
        return "Claims exist; investigate retrieval, reasoning, or answer synthesis."

    def _suggest_evidence(self, topic: str, family: str, questions: List[str]) -> List[str]:
        # These are evidence-search targets, not proposed facts.
        targets = {
            "exact_cost": "Find authoritative in-game cost tables/screenshots for the requested level/resource.",
            "time_estimate": "Find authoritative production rates, timers, prerequisites, or measured test data.",
            "how_to": "Find direct in-game procedure evidence or authoritative step-by-step documentation.",
            "comparison": "Find comparable current-state stats/mechanics for every option named in the question.",
            "recommendation": "Find evidence-backed options plus explicit player constraints; do not promote community opinion to fact.",
            "unlock": "Find direct unlock-condition evidence for the requested level/state.",
            "limit": "Find authoritative capacity/max-level evidence for the requested state.",
            "general": "Find authoritative evidence that directly addresses the failed question.",
        }
        return [targets.get(family, targets["general"])]

    def get_summary(self) -> Dict:
        if not self.gaps:
            self.detect_gaps()
        return {
            "total_gaps": len(self.gaps),
            "top_gaps": self.gaps[:10],
            "topics_affected": sorted({g["topic"] for g in self.gaps}),
            "total_failed_questions": sum(g["question_count"] for g in self.gaps),
            "total_unsupported_questions": sum(g["unsupported_count"] for g in self.gaps),
        }
