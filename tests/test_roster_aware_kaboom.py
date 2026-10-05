from operational_intelligence import build_operational_output


def test_kaboom_respects_named_roster_and_position_request():
    q = "what are the best champions for kaboom if I have zora, lily and kameni which order they should be kept in"
    out = build_operational_output(q, [])
    assert out["mode"] == "event_combo_roster_aware"
    assert out["player_roster"] == ["Zora Dominii", "Lily", "Kama Moai"]
    assert out["selection"] == ["Zora Dominii", "Lily", "Kama Moai"]
    assert [row[1] for row in out["rows"]] == ["Zora Dominii", "Lily", "Kama Moai"]
    assert all("Jodie" not in row[1] for row in out["rows"])
    assert all("Evan" not in row[1] for row in out["rows"])
    assert all("Tactical inference" in row[4] for row in out["rows"])


def test_kaboom_does_not_silently_add_unowned_champions():
    q = "kaboom team position order: I have zora lily kameni"
    out = build_operational_output(q, [])
    assert set(out["selection"]) == {"Zora Dominii", "Lily", "Kama Moai"}
    assert "Jodie Beart" not in out["selection"]
    assert "Evan Rogers" not in out["selection"]
