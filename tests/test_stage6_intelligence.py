from evidence_fusion import EvidenceRecord, fuse_evidence
from contradiction_engine import detect_conflicts
from player_adaptation import PlayerProfile, adapt_profile
from stage6_quality_gate import apply_quality_gate

def test_fusion_prefers_current_official_and_keeps_provenance():
    rows = (
        EvidenceRecord("p:current", "Combat prerequisite is 40%", "official", "current", 1, "official-sep22"),
        EvidenceRecord("p:old", "Combat prerequisite was 60%", "official", "historical", 1, "official-sep09"),
    )
    fused = fuse_evidence(rows)
    assert fused[0].source_ids
    assert fused[0].evidence_ids

def test_temporal_conflict_is_resolved_but_preserved():
    rows = (
        EvidenceRecord("p:current", "Combat prerequisite is 40%", "official", "current", 1, "s1"),
        EvidenceRecord("p:historical", "Combat prerequisite was 60%", "official", "historical", 1, "s2"),
    )
    conflicts = detect_conflicts(rows)
    assert conflicts
    assert conflicts[0].conflict_type == "temporal"
    assert conflicts[0].resolved
    assert conflicts[0].winner in {"p:current", "p:historical"}

def test_unresolved_same_authority_current_conflict_is_not_confident():
    rows = (
        EvidenceRecord("x:a", "Champion is worth building", "community", "current", 1, "a"),
        EvidenceRecord("x:b", "Champion is not worth building", "community", "current", 1, "b"),
    )
    conflicts = detect_conflicts(rows)
    assert conflicts and conflicts[0].conflict_type == "interpretation"

def test_player_adaptation_never_infers_missing_fields():
    profile = PlayerProfile(spending_profile="F2P", fleet_type="Ion")
    result = adapt_profile(profile, ("spending_profile", "core_level", "fleet_type"))
    assert "core_level" in result.missing_profile_fields
    assert not result.applicable
