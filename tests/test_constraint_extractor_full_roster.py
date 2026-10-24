from constraint_extractor import extract_constraints


def test_full_roster_names_are_recognised_in_order():
    c = extract_constraints("I have Klara, Phade and Doug Rockwell, what lineup for kaboom?")
    assert c.owned_entities == ("Klara", "Phade", "Doug Rockwell")


def test_exclusion_is_not_owned():
    c = extract_constraints("I have Lily and Klara but I don't have Cocoon")
    assert c.owned_entities == ("Lily", "Klara")
    assert c.unavailable_entities == ("Cocoon",)


def test_generic_question_has_no_goal_without_keywords():
    c = extract_constraints("how does repair work")
    assert c.optimization_goal is None
    assert c.owned_entities == ()


def test_time_and_resource_limits():
    c = extract_constraints("best plan within 30 minutes and under 5000 credits")
    assert c.explicit_time_limit == "30 minutes"
    assert c.resource_limit.startswith("under 5000")
