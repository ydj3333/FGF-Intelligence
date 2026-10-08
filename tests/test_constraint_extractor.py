from constraint_extractor import extract_constraints


def test_extracts_explicit_owned_roster_and_alias():
    c = extract_constraints("I have zora, lily and kameni; which order should they be kept in?")
    assert c.owned_entities == ("Zora Dominii", "Lily", "Kama Moai")
    assert c.requested_positions
    assert not c.unavailable_entities


def test_does_not_infer_ownership_from_generic_question():
    c = extract_constraints("what are the best champions for kaboom?")
    assert c.owned_entities == ()


def test_extracts_count_and_objective():
    c = extract_constraints("give me 5 combinations from my champions to maximize points")
    assert c.requested_count == 5
    assert c.optimization_goal == "maximize requested event metric"


def test_extracts_exclusions():
    c = extract_constraints("I don't have Jodie, use my available champions")
    assert "Jodie Beart" in c.unavailable_entities


def test_extracts_fleet_tier_t4_as_first_class_player_state():
    c = extract_constraints("core 25 and t4 what should i do")
    assert c.fleet_tier == "T4"
    assert c.confidence == "high"


def test_extracts_all_fleet_tiers_t1_to_t5():
    for tier in ("T1", "T2", "T3", "T4", "T5"):
        c = extract_constraints(f"my fleet is {tier}; what should i do?")
        assert c.fleet_tier == tier
