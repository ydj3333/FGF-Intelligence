from candidate_generator import annotate_event_coverage, generate_combinations
from event_strategy_engine import PlayerState, build_event_model


def test_generates_only_from_owned_roster():
    player = PlayerState(owned_entities=("Zora Dominii", "Lily", "Kama Moai", "Evan Rogers"))
    candidates = generate_combinations(player, team_size=3, limit=20)
    assert len(candidates) == 4
    assert all(set(c.entities).issubset(set(player.owned_entities)) for c in candidates)


def test_five_requested_can_be_generated_when_roster_allows():
    player = PlayerState(owned_entities=("A", "B", "C", "D", "E"))
    candidates = generate_combinations(player, team_size=3, limit=5)
    assert len(candidates) == 5


def test_does_not_generate_team_when_roster_is_too_small():
    player = PlayerState(owned_entities=("A", "B"))
    assert generate_combinations(player, team_size=3) == ()


def test_event_coverage_changes_with_event_model():
    player = PlayerState(owned_entities=("Zora", "Lily", "Kama"))
    candidates = generate_combinations(
        player,
        team_size=3,
        role_tags={
            "Zora": ("grouping",),
            "Lily": ("AOE",),
            "Kama": ("stun",),
        },
    )
    kaboom = build_event_model(
        "kaboom",
        objective="clear waves",
        tactical_priorities=("AOE", "grouping", "stun"),
    )
    shadow = build_event_model(
        "shadowfront",
        objective="occupy vaults",
        tactical_priorities=("occupation", "garrison"),
    )
    k = annotate_event_coverage(candidates, kaboom)[0]
    s = annotate_event_coverage(candidates, shadow)[0]
    assert k.coverage
    assert s.coverage == ()
