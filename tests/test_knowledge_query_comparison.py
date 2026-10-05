from knowledge_query_engine import KnowledgeQueryEngine


def _claim(text, tier="Tier 1 — Ultimate/Official", status="Confirmed"):
    return {
        "Claim": text,
        "Evidence Tier": tier,
        "Status": status,
        "Source": "test",
        "Category": "Events / Shared Moonlight",
    }


def test_better_than_is_parsed_as_comparison():
    engine = KnowledgeQueryEngine([
        _claim("Shared Moonlight limited rewards include a Festival Crew choice among Holly Nico, Murphy Riley, and Boka Lape."),
    ])
    parsed = engine.parse(
        "On this moonlight event, are the special festival crew members better than the Raych map fragments?"
    )
    assert parsed.question_type == "comparison"
    assert parsed.property == "comparison"


def test_comparison_does_not_fall_back_to_generic_event_description():
    engine = KnowledgeQueryEngine([
        _claim("Shared Moonlight is a new limited-time event."),
        _claim("Shared Moonlight limited rewards include a Festival Crew choice among Holly Nico, Murphy Riley, and Boka Lape."),
    ])
    result = engine.compose(
        "On this moonlight event, are the special festival crew members better than the Raych map fragments?"
    )
    assert "better than" not in result["answer"].lower() or "not establish" in result["answer"].lower()
    assert "festival crew" in result["answer"].lower()
    assert "generic event" not in result["reasoning"].get("mode", "").lower()


def test_comparison_does_not_invent_missing_second_side():
    engine = KnowledgeQueryEngine([
        _claim("Shared Moonlight includes a daily Sign-In activity that grants event rewards."),
    ])
    result = engine.compose(
        "Are the special festival crew members better than the Raych map fragments?"
    )
    assert "cannot establish" in result["answer"].lower() or "could not find" in result["answer"].lower()
