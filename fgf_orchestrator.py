"""FGF v6.3 Live Experiential Orchestrator.

This layer sits above the v6.0 Knowledge Query Engine. It never replaces
canonical retrieval. It decides when additional experiential evidence may be
consulted.

Order:
    1. Core FGF knowledge
    2. Validated/repeated player experience
    3. YouTube/community fallback (future ingestion)
"""

from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional

from policy_engine import classify_intent, enforce


@dataclass
class OrchestrationResult:
    answer: str
    branch: str
    evidence_state: str
    abstained: bool
    core_answerable: bool
    warnings: List[str]
    core: Dict[str, Any]
    experience: List[Dict[str, Any]]
    youtube: List[Dict[str, Any]]
    provenance: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _is_abstention(result: Dict[str, Any]) -> bool:
    return result.get("answer_type") in {
        "knowledge_abstention", "knowledge_policy"
    } or not result.get("evidence")


def _policy_intent(question: str, core: Dict[str, Any]) -> str:
    return classify_intent(question, str((core.get("query") or {}).get("question_type", "")))


class FGFOrchestrator:
    def __init__(self, core_answer, experience_store=None, youtube_provider=None):
        self.core_answer = core_answer
        self.experience_store = experience_store
        self.youtube_provider = youtube_provider

    def answer(self, question: str, player_context: Optional[Dict[str, Any]] = None):
        core = self.core_answer(question, player_context)
        intent = _policy_intent(question, core)
        core_claims = core.get("evidence", []) if isinstance(core.get("evidence"), list) else []
        policy = enforce(
            core.get("answer", ""),
            core_claims,
            question,
            str((core.get("query") or {}).get("question_type", "")),
        )
        if (
            policy.get("abstained")
            and intent == "factual"
            and core.get("answer_type") not in {"knowledge_abstention", "knowledge_policy"}
        ):
            core = dict(core)
            core["answer"] = policy["answer"]
            core["answer_type"] = "knowledge_policy"
            core["evidence"] = []
            core["evidence_used"] = []
            core["uncertainty"] = (
                policy["warnings"][0]
                if policy.get("warnings")
                else "Official evidence is insufficient."
            )
        core_abstains = _is_abstention(core)

        # Established factual answers stop at Core.
        if intent == "factual" and not core_abstains:
            return OrchestrationResult(
                answer=core.get("answer", ""),
                branch="core",
                evidence_state="CONFIRMED",
                abstained=False,
                core_answerable=True,
                warnings=[],
                core=core, experience=[], youtube=[],
                provenance={"branches_used": ["core"]},
            ).as_dict()

        experience = []
        if self.experience_store is not None:
            experience = self.experience_store.find_relevant(
                question, player_context=player_context,
                limit=4, validated_only=True
            )

        if intent in ("strategy", "interpretation") and experience:
            answer = core.get("answer", "")
            additions = [
                f"Observed/validated experience: {item.get('pattern', '')}"
                for item in experience
            ]
            if additions:
                answer = (answer + "\n\n" if answer else "") + "\n".join(
                    f"• {x}" for x in additions
                )
            return OrchestrationResult(
                answer=answer,
                branch="core+experience",
                evidence_state="SUPPORTED",
                abstained=False,
                core_answerable=not core_abstains,
                warnings=["Experience comes from repeated gameplay observations and is not an official mechanic."],
                core=core, experience=experience, youtube=[],
                provenance={"branches_used": ["core", "experience"]},
            ).as_dict()

        youtube = []
        if core_abstains and self.youtube_provider is not None:
            youtube = self.youtube_provider.find_relevant(
                question, player_context=player_context, limit=4
            )
            if youtube:
                answer = (
                    "The current canonical FGF corpus does not establish this. "
                    "The following YouTube/community material is fallback evidence "
                    "and must not be treated as canonical game truth.\n\n"
                    + "\n".join(
                        f"• {x.get('summary', x.get('claim', ''))}" for x in youtube
                    )
                )
                return OrchestrationResult(
                    answer=answer, branch="youtube_fallback",
                    evidence_state="COMMUNITY_INTERPRETATION",
                    abstained=False, core_answerable=False,
                    warnings=[
                        "YouTube/community evidence is fallback material.",
                        "Check current official/in-game evidence before treating it as a mechanic."
                    ],
                    core=core, experience=[], youtube=youtube,
                    provenance={"branches_used": ["core", "youtube"]},
                ).as_dict()

        return OrchestrationResult(
            answer=core.get("answer", "The current evidence is insufficient."),
            branch="core_abstention",
            evidence_state="INSUFFICIENT_EVIDENCE",
            abstained=True, core_answerable=False,
            warnings=["No validated experiential or fallback evidence was available."],
            core=core, experience=experience, youtube=[],
            provenance={"branches_used": ["core"]},
        ).as_dict()
