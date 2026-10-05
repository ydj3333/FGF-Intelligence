from event_strategy_engine import build_event_model, solve_question
from evidence_fusion import EvidenceRecord


def _events():
    return (
        build_event_model("kaboom", objective="defeat robot waves", tactical_priorities=("AOE", "burst")),
        build_event_model("shadowfront", objective="occupy vaults", tactical_priorities=("occupation", "damage")),
        build_event_model("path_to_dominance", objective="win fortress competition", tactical_priorities=("active PvP", "garrison")),
        build_event_model("commerce_guild_duel_league", objective="increase guild rank", tactical_priorities=("match results", "guild performance")),
    )


def test_stage6_cross_event_paths_are_isolated():
    rows = (
        EvidenceRecord("event:current", "Event duration is 24h", "official", "current", 1, "s1", topic="event_duration"),
        EvidenceRecord("event:old", "Event duration is 48h", "official", "historical", 1, "s2", topic="event_duration"),
    )
    for event in _events():
        result = solve_question(
            "give 1 combo; I have Zora, Lily, Jodie",
            event,
            evidence=rows,
        )
        assert result["stage6"] is not None
        assert result["stage6"]["quality_gate"].allowed
        assert all(event.event_key not in str(x) for x in result["stage6"]["conflicts"])


def test_stage6_unresolved_conflict_blocks_confident_output_across_events():
    rows = (
        EvidenceRecord("same:a", "Mechanic A applies", "official", "current", 1, "s1", topic="shared_mechanic"),
        EvidenceRecord("same:b", "Mechanic B applies", "official", "current", 1, "s2", topic="shared_mechanic"),
    )
    for event in _events():
        result = solve_question(
            "give 1 combo; I have Zora, Lily, Jodie",
            event,
            evidence=rows,
        )
        assert result["stage6"]["quality_gate"].allowed is False
        assert result["stage6"]["quality_gate"].confidence == "uncertain"
