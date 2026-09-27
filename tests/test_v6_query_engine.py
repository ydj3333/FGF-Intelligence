import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent

QUESTIONS=[
 "Which level do critical components appear?",
 "How do I get them?",
 "What unlocks them?",
 "What is the difference between Core and other components?",
 "What level do I need before I can upgrade them?",
 "Which buildings affect them?",
 "Can F2P players get them?",
 "What are the best sources?",
 "What happens after the component reaches +6?",
 "Which component changes my fleet style?",
 "What component should I use against Beam?",
]

def test_v6_query_engine_does_not_dump():
    for q in QUESTIONS:
        r=agent.answer(q)
        assert r["model"]=="fgf-v6-knowledge-query-engine"
        assert r["answer"]
        # The answer surface must stay small even when retrieval finds many
        # related claims.
        assert len(r.get("evidence",[])) <= 4
        assert "query" in r and r["query"]["question_type"]
        if r["answer_type"]=="knowledge_abstention":
            assert r["evidence"]==[]

def test_v6_level_question_is_evidence_safe():
    r=agent.answer("which level critical components appear")
    # The corpus currently contains related component evidence, but the exact
    # requested level is not established. A safe agent must abstain rather than
    # substitute Champion/Energy-Core/Flagship facts.
    assert r["answer_type"]=="knowledge_abstention"
    assert r["evidence"]==[]
    assert "level" in r["answer"].lower()

def test_v6_known_flagship_fact_is_direct():
    r=agent.answer("which component changes my fleet style")
    assert r["answer_type"]=="knowledge_query"
    assert "core component" in r["answer"].lower()
    assert len(r["evidence"])<=3

if __name__ == '__main__':
    test_v6_query_engine_does_not_dump()
    test_v6_level_question_is_evidence_safe()
    test_v6_known_flagship_fact_is_direct()
    print('FGF v6 query tests: PASS')

def test_v6_shared_moonlight_rewards():
    r=agent.answer("On this moonlight event what are the best rewards")
    assert r["answer_type"]=="knowledge_query"
    assert "exclusive ship skin" in r["answer"].lower()
    assert "festival crew" in r["answer"].lower()
    assert len(r["evidence"])<=2

def test_v6_best_dps_champion():
    r=agent.answer("best dps champion")
    assert r["answer_type"]=="knowledge_query"
    assert any(x in r["answer"].lower() for x in ("lily","killer bee","zora domini","evan rogers"))
    assert "community" in r["answer"].lower()
    assert len(r["evidence"])<=4

def test_v6_generic_graph_requirement_question():
    r=agent.answer("What does Commerce Guild creation require?")
    assert r["answer_type"]=="knowledge_query"
    assert "Energy Core Level 9" in r["answer"]
    assert "2,000 Credits" in r["answer"]
    assert r["reasoning"]["mode"] in ("graph_requirement","requirement")

def test_v6_generic_entity_parser_does_not_match_substrings():
    engine=agent.get_engine()
    p=engine.parse("What does Commerce Guild creation require?")
    assert p.entity=="commerce guild creation"
    assert p.question_type=="requirement"

def test_v6_multihop_reasoning_requires_complete_chain():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Research Academy requires Energy Core Level 10.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Energy Core Level 10 can be obtained through Core progression.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    e=KnowledgeQueryEngine(claims)
    r=e.compose("What does Research Academy require and how do I get the requirement?")
    assert r["reasoning"]["mode"]=="multi_hop"
    assert "Energy Core Level 10" in r["answer"]
    assert "Core progression" in r["answer"]
    assert len(r["evidence"])==2

def test_v6_graph_exact_matching_does_not_cross_level_entities():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Energy Core Level 10 requires Core progression.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Energy Core unlocks new features.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    e=KnowledgeQueryEngine(claims)
    assert e.graph.outgoing("Energy Core Level 10","requires")
    assert not e.graph.outgoing("Energy Core","requires")

def test_v6_multihop_abstains_on_incomplete_chain():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Research Academy requires Energy Core Level 10.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    e=KnowledgeQueryEngine(claims)
    r=e.compose("What does Research Academy require and how do I get the requirement?")
    assert r["answer_type"]=="knowledge_abstention"
    assert "does not establish the acquisition path" in r["answer"]

def test_v6_benchmark_does_not_flag_question_numbers_as_unsupported():
    from scripts.run_v6_objective1_benchmark import numeric_tokens
    question = "What unlocks at Energy Core level 40?"
    answer = "The current knowledge base does not establish what unlocks at Energy Core level 40."
    evidence = ""
    unsupported = numeric_tokens(answer) - numeric_tokens(evidence) - numeric_tokens(question)
    assert unsupported == set()

def test_v6_graph_entity_resolution_uses_explicit_aliases_only():
    from evidence_graph import EvidenceGraph
    claims=[{
        "Claim":"Energy Core requires Core progression.",
        "Evidence Tier":"Tier 1 — Ultimate/Official",
        "Status":"Confirmed",
    }]
    graph=EvidenceGraph(claims, alias_groups=[["energy core", "core level"]])
    assert graph.outgoing("core level", "requires")
    assert graph.outgoing("energy core", "requires")
    assert not graph.outgoing("unrelated core", "requires")


def test_v6_graph_supports_three_hop_complete_chain_with_provenance():
    from evidence_graph import EvidenceGraph
    claims=[
        {"Claim":"Research Academy requires Energy Core Level 10.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Energy Core Level 10 can be obtained through Core progression.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Core progression is available at Research Academy.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    graph=EvidenceGraph(claims)
    paths=graph.derive(
        ["Research Academy"],
        ("requires","obtained_from","available_at"),
        max_hops=3,
        require_current=True,
        min_tier_score=3.0,
    )
    assert len(paths)==1
    assert len(paths[0])==3
    assert [e.relation for e in paths[0]] == ["requires","obtained_from","available_at"]
    assert len(graph.provenance(paths[0]))==3


def test_v6_graph_rejects_under_review_link_from_production_chain():
    from evidence_graph import EvidenceGraph
    claims=[
        {"Claim":"Research Academy requires Energy Core Level 10.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Energy Core Level 10 can be obtained through Core progression.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Under Review"},
    ]
    graph=EvidenceGraph(claims)
    paths=graph.derive(
        ["Research Academy"],
        ("requires","obtained_from"),
        max_hops=2,
        require_current=True,
        min_tier_score=3.0,
    )
    assert paths==[]
