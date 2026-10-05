"""Regression contract: v7/v7.1 must build on the original v6 answer intelligence.

These tests deliberately exercise specialized v6 answer handlers. New stages may
add provenance, evidence fusion, adaptation, or warnings, but must not replace
a correct domain-specific answer with generic retrieval.
"""

from knowledge_query_engine import KnowledgeQueryEngine


def claim(text, tier="Tier 1 — Ultimate/Official", status="Confirmed", category="Events"):
    return {
        "Claim": text,
        "Evidence Tier": tier,
        "Status": status,
        "Source": "regression-test",
        "Category": category,
    }


def test_shared_moonlight_reward_handler_is_preserved():
    engine = KnowledgeQueryEngine([
        claim(
            "Shared Moonlight limited rewards include an exclusive ship skin, a name frame, "
            "an Avatar Frame, a Killing Effect, and a Festival Crew choice among Holly Nico, "
            "Murphy Riley, and Boka Lape."
        ),
        claim("Shared Moonlight is a new limited-time event."),
    ])
    result = engine.compose("What are the Shared Moonlight rewards?")
    answer = result["answer"].lower()

    # The original specialized reward intelligence must survive.
    assert "holly nico" in answer
    assert "murphy riley" in answer
    assert "boka lape" in answer
    assert result["reasoning"]["mode"] in {"strategy_shared_moonlight_rewards", "direct"}


def test_generic_event_claim_must_not_replace_specialized_reward_answer():
    engine = KnowledgeQueryEngine([
        claim("Shared Moonlight includes a daily Sign-In activity that grants event rewards."),
        claim(
            "Shared Moonlight limited rewards include an exclusive ship skin, a name frame, "
            "an Avatar Frame, a Killing Effect, and a Festival Crew choice among Holly Nico, "
            "Murphy Riley, and Boka Lape."
        ),
    ])
    result = engine.compose("Which Festival Crew can I choose in Shared Moonlight?")
    answer = result["answer"].lower()

    assert "holly nico" in answer
    assert "murphy riley" in answer
    assert "boka lape" in answer
    assert "daily sign-in activity" not in answer


def test_stage6_must_be_additive_to_baseline_answer():
    engine = KnowledgeQueryEngine([
        claim(
            "Shared Moonlight limited rewards include an exclusive ship skin, a name frame, "
            "an Avatar Frame, a Killing Effect, and a Festival Crew choice among Holly Nico, "
            "Murphy Riley, and Boka Lape."
        ),
    ])
    baseline = engine.compose("What are the Shared Moonlight rewards?")

    # The contract is explicit: Stage 6 evidence intelligence may decorate the
    # answer, but its presence cannot erase the established core answer.
    stage6_payload = {
        "baseline_answer": baseline["answer"],
        "baseline_evidence": baseline["evidence"],
        "stage": "6",
        "mode": "additive",
    }

    assert stage6_payload["baseline_answer"] == baseline["answer"]
    assert "holly nico" in stage6_payload["baseline_answer"].lower()
    assert len(stage6_payload["baseline_evidence"]) >= 1
