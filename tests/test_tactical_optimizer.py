from candidate_generator import GeneratedCandidate
from event_strategy_engine import PlayerState, build_event_model
from tactical_optimizer import rank_candidates, why_first_beats_second


def test_event_specific_optimization_prefers_priority_coverage():
    player = PlayerState(owned_entities=("A", "B", "C", "D"))
    event = build_event_model(
        "event_a",
        objective="objective",
        tactical_priorities=("aoe", "grouping"),
        scoring_factors=("active_pvp",),
    )
    candidates = (
        GeneratedCandidate("A+B+C", ("A", "B", "C"), ("aoe", "grouping")),
        GeneratedCandidate("A+B+D", ("A", "B", "D"), ("aoe",)),
    )
    ranked = rank_candidates(event, player, candidates, limit=2)
    assert ranked[0].candidate.name == "A+B+C"
    assert ranked[0].score > ranked[1].score


def test_event_strategy_does_not_transfer_between_events():
    player = PlayerState(owned_entities=("A", "B", "C"))
    event_a = build_event_model("a", objective="x", tactical_priorities=("aoe",))
    event_b = build_event_model("b", objective="x", tactical_priorities=("occupation",))
    candidate = GeneratedCandidate("A+B+C", ("A", "B", "C"), ("aoe",))
    assert rank_candidates(event_a, player, (candidate,))[0].score > 0
    assert rank_candidates(event_b, player, (candidate,))[0].score < rank_candidates(event_a, player, (candidate,))[0].score


def test_hard_constraint_beats_score():
    player = PlayerState(owned_entities=("A", "B", "C"), unavailable_entities=("C",))
    event = build_event_model("x", objective="x", tactical_priorities=("aoe",))
    candidate = GeneratedCandidate("A+B+C", ("A", "B", "C"), ("aoe",))
    assert rank_candidates(event, player, (candidate,)) == ()


def test_explicit_synergy_and_evidence_are_auditable():
    player = PlayerState(owned_entities=("A", "B", "C", "D"))
    event = build_event_model("x", objective="x", tactical_priorities=("aoe",))
    candidates = (
        GeneratedCandidate("A+B+C", ("A", "B", "C"), ("aoe",)),
        GeneratedCandidate("A+B+D", ("A", "B", "D"), ("aoe",)),
    )
    ranked = rank_candidates(
        event,
        player,
        candidates,
        synergy_map={("A", "B", "C"): ("cluster-burst",)},
        evidence_map={("A", "B", "C"): "Tier 1", ("A", "B", "D"): "derived"},
        limit=2,
    )
    assert ranked[0].candidate.name == "A+B+C"
    assert ranked[0].synergy == ("cluster-burst",)
    assert "evidence=Tier 1" in ranked[0].explanation
    assert "ranks higher" in why_first_beats_second(ranked[0], ranked[1])
