from fgf_orchestrator import FGFOrchestrator


def test_orchestrator_preserves_core_answer_when_enriching():
    core_answer = {
        "answer": "Festival Crew choices are Holly Nico, Murphy Riley, or Boka Lape.",
        "evidence": [{"claim": "Shared Moonlight limited rewards include a Festival Crew choice among Holly Nico, Murphy Riley, and Boka Lape."}],
        "answer_type": "knowledge_query",
        "query": {"question_type": "strategy"},
    }

    class Experience:
        def find_relevant(self, *args, **kwargs):
            return [{"pattern": "Players report rotating the choice based on account needs."}]

    result = FGFOrchestrator(lambda q, p=None: core_answer, experience_store=Experience()).answer(
        "Which Festival Crew should I choose in Shared Moonlight?"
    )

    assert result["baseline_answer"] == core_answer["answer"]
    assert core_answer["answer"] in result["answer"]
    assert result["answer_layering"]["baseline_preserved"] is True


def test_orchestrator_never_replaces_core_with_policy_abstention():
    core_answer = {
        "answer": "Shared Moonlight offers a Festival Crew choice.",
        "evidence": [{"claim": "Shared Moonlight offers a Festival Crew choice."}],
        "answer_type": "knowledge_query",
        "query": {"question_type": "generic"},
    }

    class Policy:
        pass

    # This test monkey-patches the module policy function so the governance
    # layer requests abstention. The established core answer must remain.
    import fgf_orchestrator as module
    original = module.enforce
    module.enforce = lambda *args, **kwargs: {
        "abstained": True,
        "answer": "REPLACEMENT MUST NOT OCCUR",
        "warnings": ["Policy review warning"],
    }
    try:
        result = FGFOrchestrator(lambda q, p=None: core_answer).answer(
            "What is Shared Moonlight?"
        )
    finally:
        module.enforce = original

    assert result["baseline_answer"] == core_answer["answer"]
    assert "REPLACEMENT MUST NOT OCCUR" not in result["answer"]
    assert core_answer["answer"] in result["answer"]
    assert result["answer_layering"]["baseline_preserved"] is True
