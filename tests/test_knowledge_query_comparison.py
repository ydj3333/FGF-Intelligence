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


def test_difference_questions_do_not_enter_value_winner_path():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Space combat has three categories of fleet damage: Minor Damage (Light), Major Damage (Heavy), and Ship Loss.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Major Damage (Heavy) sends damaged vessels to the Repair Bay and requires Repair Modules for repair.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose("What is the difference between minor and major damage?")
    assert result["reasoning"]["mode"] == "descriptive_comparison"
    assert "minor damage" in result["answer"].lower()
    assert "major damage" in result["answer"].lower()
    assert "better recommendation" not in result["answer"].lower()


def test_authority_conflict_questions_use_governance_path():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Official evidence establishes the mechanic.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"A community YouTube claim reports a different mechanic.",
         "Evidence Tier":"Tier 3 — Creator/Community","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose(
        "Official evidence and YouTube disagree about this FGF mechanic. What should I trust?"
    )
    assert result["reasoning"]["mode"] == "evidence_governance"
    assert "official/current evidence governs" in result["answer"].lower()
    assert "better recommendation" not in result["answer"].lower()


def test_flagship_difference_does_not_abstain_as_better_winner():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"The Fleet page configures Flagships, Champions, and combat craft.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"A fleet consists of 1 Flagship, 3 Champions, and multiple combat craft.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Additional Flagship Components enhance ships' base ATK, DEF, and INT attributes.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose("What is the difference between flagship and regular ships?")
    assert result["reasoning"]["mode"] == "descriptive_comparison"
    assert "flagship" in result["answer"].lower()
    assert "better recommendation" not in result["answer"].lower()


def test_flagship_scope_question_is_not_a_value_comparison():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"The Flagship is the heart of a fleet and provides attribute bonuses and abilities.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"When a fleet has Champions matching the Style of its Flagship, the matching count grants additional attributes to the Flagship and combat craft of the same Style.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose("Do flagship bonuses apply to all ships or just the flagship?")
    assert result["reasoning"]["mode"] == "descriptive_comparison"
    assert "flagship" in result["answer"].lower()
    assert "better recommendation" not in result["answer"].lower()
