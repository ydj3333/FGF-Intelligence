import agent
from evidence_graph import EvidenceGraph

def test_graph_extracts_explicit_relationships():
    claims = [
        {"Claim": "Commerce Guild creation requires Energy Core Level 9 and 2,000 Credits.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
        {"Claim": "Flagship Components can be obtained through the Glory Shop, Ascendancy Shrines, and Tribute Vessels.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
        {"Claim": "Upgrading the Energy Core unlocks higher facility tiers.", "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed"},
    ]
    g = EvidenceGraph(claims)
    assert any(e.relation == "requires" and "Energy Core" in e.target for e in g.edges)
    assert any(e.relation == "obtained_from" and "Glory Shop" in e.target for e in g.edges)
    assert any(e.relation == "unlocks" for e in g.edges)

def test_graph_never_invents_edges():
    g = EvidenceGraph([{"Claim": "Energy Core unlocks new features."}])
    assert not g.find_sources("Energy Core", "requires")
    assert not g.outgoing("Energy Core", "requires")

def test_graph_preserves_provenance():
    claims = [{"Claim": "A requires B."}, {"Claim": "B is available from C."}]
    g = EvidenceGraph(claims)
    paths = g.derive(["A"], ("requires", "available_at"), max_hops=2)
    assert len(paths) == 1
    assert [e.target for e in paths[0]] == ["B", "C"]
    assert len(g.provenance(paths[0])) == 2
