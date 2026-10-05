"""Release gate for the pre-existing FGF Core intelligence.

These are not new Stage-6 expectations. They pin established v6 behavior so
future layers can only build on it.
"""

import agent


def _assert_core_survives(question, required_terms):
    result = agent.answer(question)
    assert result["answer"]
    assert result["baseline_answer"]
    assert result["answer_layering"]["baseline_preserved"] is True
    answer = result["answer"].lower()
    for term in required_terms:
        assert term.lower() in answer, (question, result["answer"], term)


def test_established_shared_moonlight_intelligence_survives():
    _assert_core_survives(
        "On this moonlight event what are the best rewards",
        ["exclusive ship skin", "festival crew"],
    )


def test_established_dps_intelligence_survives():
    _assert_core_survives(
        "best dps champion",
        ["community"],
    )


def test_established_graph_requirement_intelligence_survives():
    _assert_core_survives(
        "What does Commerce Guild creation require?",
        ["energy core level 9", "2,000 credits"],
    )


def test_established_safe_abstention_survives():
    result = agent.answer("which level critical components appear")
    assert result["answer_type"] == "knowledge_abstention"
    assert result["answer"]
    # An abstention is not an established Core answer, so no later layer is
    # allowed to manufacture a replacement fact.
    assert result["evidence"] == []
