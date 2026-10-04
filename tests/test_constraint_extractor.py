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
