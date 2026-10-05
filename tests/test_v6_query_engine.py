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

def test_v6_engine_answers_three_hop_chain_only_when_complete():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Research Academy requires Energy Core Level 10.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Energy Core Level 10 can be obtained through Core progression.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Core progression is available at Research Academy.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    e=KnowledgeQueryEngine(claims)
    r=e.compose("What does Research Academy require, how do I get it, and where is it available?")
    assert r["answer_type"]=="knowledge_query"
    assert r["reasoning"]["mode"]=="multi_hop_3"
    assert "Energy Core Level 10" in r["answer"]
    assert "Core progression" in r["answer"]
    assert "available at Research Academy" in r["answer"]
    assert len(r["evidence"])==3


def test_v7_comparison_layer_preserves_existing_core_comparison_subtypes():
    from knowledge_query_engine import KnowledgeQueryEngine

    damage = KnowledgeQueryEngine([
        {"Claim":"Space combat has three categories of fleet damage: Minor Damage (Light), Major Damage (Heavy), and Ship Loss.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Major Damage (Heavy) sends damaged vessels to the Repair Bay and requires Repair Modules for repair.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]).compose("What is the difference between minor and major damage?")
    assert damage["reasoning"]["mode"] == "descriptive_comparison"
    assert "minor damage" in damage["answer"].lower()
    assert "major damage" in damage["answer"].lower()
    assert "better recommendation" not in damage["answer"].lower()

    governance = KnowledgeQueryEngine([
        {"Claim":"Official evidence establishes the mechanic.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"A community YouTube claim reports a different mechanic.",
         "Evidence Tier":"Tier 3 — Creator/Community","Status":"Confirmed"},
    ]).compose("Official evidence and YouTube disagree about this FGF mechanic. What should I trust?")
    assert governance["reasoning"]["mode"] == "evidence_governance"
    assert "official/current evidence governs" in governance["answer"].lower()

    flagship = KnowledgeQueryEngine([
        {"Claim":"The Fleet page configures Flagships, Champions, and combat craft.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"A fleet consists of 1 Flagship, 3 Champions, and multiple combat craft.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Additional Flagship Components enhance ships' base ATK, DEF, and INT attributes.",
         "Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]).compose("What is the difference between flagship and regular ships?")
    assert flagship["reasoning"]["mode"] == "descriptive_comparison"
    assert "flagship" in flagship["answer"].lower()
    assert "better recommendation" not in flagship["answer"].lower()


def test_v7_numeric_cap_does_not_substitute_unrelated_level_facts():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Energy core level 15 unlocks epic.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Energy core level 20 unlocks legendary.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose("What is the maximum Energy Core level?")
    assert result["answer_type"] == "knowledge_abstention"
    assert "does not establish" in result["answer"].lower()


def test_v7_exact_cost_policy_cannot_be_hijacked_by_unrelated_retrieval():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Players can establish their own Home Port.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose("What should I do when the evidence does not establish an exact cost?")
    assert result["reasoning"]["mode"] == "safe_strategy_policy"
    assert "do not invent a number" in result["answer"].lower()


def test_v7_best_strategy_does_not_return_unrelated_facts():
    from knowledge_query_engine import KnowledgeQueryEngine
    claims=[
        {"Claim":"Players can establish their own Home Port.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    result=KnowledgeQueryEngine(claims).compose("What is the best way to farm Credits?")
    assert result["answer_type"] == "knowledge_abstention"
    assert "recommendation" in result["answer"].lower()
