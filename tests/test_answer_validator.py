from constraint_extractor import extract_constraints
from event_strategy_engine import PlayerState, build_event_model
from candidate_generator import GeneratedCandidate
from tactical_optimizer import rank_candidates
from answer_validator import validate_answer


def test_requested_count_is_verified():
    event = build_event_model("kaboom", objective="waves", tactical_priorities=("aoe",))
    player = PlayerState(owned_entities=("Zora", "Lily", "Jodie", "Kama"))
    constraints = extract_constraints("I have Zora, Lily, Jodie, Kama. Give me 5 combinations.")
    ranked = rank_candidates(
        event, player,
        (
            GeneratedCandidate("Zora + Lily + Jodie", ("Zora", "Lily", "Jodie"), ("aoe",)),
            GeneratedCandidate("Zora + Lily + Kama", ("Zora", "Lily", "Kama"), ("aoe",)),
        ),
        limit=5,
    )
    result = validate_answer(
        question="I have Zora, Lily, Jodie, Kama. Give me 5 combinations.",
        event=event, player=player, constraints=constraints, ranked=ranked,
        generated_count=2, requested_count=5, team_size=3,
    )
    assert result.valid
    assert any(i.code == "requested_count_unmet" for i in result.issues)


def test_unowned_candidate_is_blocked():
    event = build_event_model("kaboom", objective="waves", tactical_priorities=("aoe",))
    player = PlayerState(owned_entities=("Zora", "Lily", "Kama"))
    constraints = extract_constraints("I have Zora, Lily, Kama.")
    ranked = rank_candidates(
        event, player,
        (GeneratedCandidate("Zora + Lily + Jodie", ("Zora", "Lily", "Jodie"), ("aoe",)),),
    )
    result = validate_answer(
        question="I have Zora, Lily, Kama.",
        event=event, player=player, constraints=constraints, ranked=ranked,
        generated_count=0, requested_count=None, team_size=3,
    )
    assert result.valid
    assert not any(i.code == "unowned_entity_returned" for i in result.issues)


def test_position_request_is_never_fabricated():
    event = build_event_model("shadowfront", objective="occupation", tactical_priorities=("occupation",))
    player = PlayerState(owned_entities=("A", "B", "C"))
    constraints = extract_constraints("I have A, B, C. Give me the best order and positions.")
    ranked = rank_candidates(
        event, player,
        (GeneratedCandidate("A+B+C", ("A", "B", "C"), ("occupation",)),),
    )
    result = validate_answer(
        question="I have A, B, C. Give me the best order and positions.",
        event=event, player=player, constraints=constraints, ranked=ranked,
        generated_count=1, requested_count=None, team_size=3,
    )
    assert result.valid
    assert any(i.code == "position_order_unverified" for i in result.issues)


def test_duplicate_candidates_fail_gate():
    from tactical_optimizer import RankedCandidate
    event = build_event_model("x", objective="x", tactical_priorities=("aoe",))
    player = PlayerState(owned_entities=("A", "B", "C"))
    constraints = extract_constraints("I have A, B, C.")
    candidate = GeneratedCandidate("A+B+C", ("A", "B", "C"), ("aoe",))
    dup = (
        RankedCandidate(candidate, 1, ("aoe",), (), (), "derived", ""),
        RankedCandidate(candidate, 1, ("aoe",), (), (), "derived", ""),
    )
    result = validate_answer(
        question="I have A, B, C.",
        event=event, player=player, constraints=constraints, ranked=dup,
        generated_count=2, requested_count=None, team_size=3,
    )
    assert not result.valid
    assert any(i.code == "duplicate_candidate" for i in result.issues)
