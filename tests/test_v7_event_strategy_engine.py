from event_strategy_engine import (
    CandidateAction,
    PlayerState,
    build_event_model,
    decide,
)


def test_kaboom_uses_event_objective_and_player_roster():
    event = build_event_model(
        "kaboom_robots",
        objective="clear robot waves",
        scoring_factors=("kills",),
        tactical_priorities=("AOE", "grouping", "stun"),
        duration="48h",
        evidence_state="tier 2",
    )
    player = PlayerState(owned_entities=("Zora", "Lily", "Kama"))
    candidates = (
        CandidateAction("generic community trio", ("Zora", "Jodie", "Lily"), ("AOE",), "tier 2"),
        CandidateAction("player trio", ("Zora", "Lily", "Kama"), ("grouping", "AOE", "stun"), "tier 2"),
    )
    result = decide(event, player, candidates, limit=1)
    assert result.selected[0].name == "player trio"
    assert any("Jodie" in reason for _, reason in result.rejected)


def test_shadowfront_has_different_objective_than_kaboom():
    event = build_event_model(
        "shadowfront",
        objective="occupy and hold Vaults",
        scoring_factors=("occupation", "combat damage", "final hit"),
        tactical_priorities=("occupation", "damage", "garrison"),
        duration="5 days",
        evidence_state="tier 2",
    )
    assert "occupation" in event.objective.lower()
    assert "AOE" not in event.tactical_priorities


def test_paths_to_dominance_uses_title_timing_not_pve_wave_logic():
    event = build_event_model(
        "path_to_dominance",
        objective="conquest of the target fortress and Glory",
        scoring_factors=("active PvP", "rallies", "garrison"),
        tactical_priorities=("rally coordination", "garrison", "title timing"),
        timing_rules=("hold title at action start to receive buff",),
        duration="24h",
        evidence_state="primary_in_game_ui",
    )
    assert "title timing" in event.tactical_priorities
    assert "rally coordination" in event.scoring_factors


def test_commerce_duel_uses_rank_points_and_demotions():
    event = build_event_model(
        "commerce_guild_duel_league",
        objective="maximize League Rank Points",
        scoring_factors=("match result", "guild performance", "individual contribution"),
        tactical_priorities=("winning", "individual contribution"),
        duration="1 month (testing)",
        evidence_state="tier 2",
    )
    assert "Rank Points" in event.objective
    assert "match result" in event.scoring_factors


def test_hard_constraint_beats_generic_optimal_candidate():
    event = build_event_model(
        "kaboom",
        objective="clear waves",
        tactical_priorities=("AOE",),
        evidence_state="tier 2",
    )
    player = PlayerState(owned_entities=("Zora", "Lily", "Kama"))
    candidates = (
        CandidateAction("best generic", ("Zora", "Jodie", "Lily"), ("AOE",), "tier 1"),
        CandidateAction("feasible", ("Zora", "Lily", "Kama"), ("AOE",), "tier 2"),
    )
    result = decide(event, player, candidates, limit=1)
    assert result.selected[0].name == "feasible"


def test_end_to_end_five_combinations_respects_owned_roster():
    from event_strategy_engine import solve_question
    event = build_event_model(
        "kaboom",
        objective="clear robot waves",
        scoring_factors=("kills",),
        tactical_priorities=("AOE", "grouping"),
    )
    result = solve_question(
        "I have A, B, C, D and E. Give me 5 combinations.",
        event,
        team_size=3,
        limit=5,
    )
    assert result["generated_count"] == 10
    assert len(result["decision"].selected) == 5
    for selected in result["decision"].selected:
        assert set(selected.entities).issubset({"A", "B", "C", "D", "E"})
