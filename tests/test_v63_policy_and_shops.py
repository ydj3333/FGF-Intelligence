import json
from pathlib import Path
from knowledge_query_engine import KnowledgeQueryEngine
from policy_engine import classify_policy_intent, evaluate_evidence

ROOT=Path(__file__).resolve().parents[1]

def test_v63_factual_policy_excludes_tested_community():
    claims=[
        {"Claim":"A community guide says the shop sells X.","Evidence Tier":"Tier 2 — Tested Community","Status":"Under Review"},
        {"Claim":"Official notice says the shop sells Y.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
    ]
    ev=evaluate_evidence(claims,"factual")
    assert len(ev["usable"])==1
    assert ev["usable"][0]["Claim"].endswith("Y.")

def test_v63_strategy_policy_allows_community_evidence():
    claims=[
        {"Claim":"Community recommends buying speedups.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
    ]
    ev=evaluate_evidence(claims,"strategy")
    assert len(ev["usable"])==1
    assert ev["evidence_state"]=="community_interpretation"

def test_v63_shop_model_has_named_systems():
    data=json.loads((ROOT/"data"/"shop_intelligence.json").read_text())
    names={x["name"] for x in data["shops"]}
    assert "Black Market Trader" in names
    assert "Commerce Guild Shop" in names
    assert "Discount Shop" in names
    assert "Moonlit Market" in names
    assert "Recycle Shop" in names

def test_v63_shop_question_is_interpreted_not_transcribed():
    claims=[
        {"Claim":"Wandering merchant deals allow surplus base resources to be bartered for high-tier acceleration boosts.","Evidence Tier":"Tier 1 — Ultimate/Official","Status":"Confirmed"},
        {"Claim":"Community guidance describes the Black Market Trader as a source of discounted Speedups and Crystals.","Evidence Tier":"Tier 3 — Creator/Community","Status":"Under Review"},
        {"Claim":"The guide recommends saving Credits for the Black Market to purchase speedups at a 50% discount.","Evidence Tier":"Tier 2 — Tested Community","Status":"Under Review"},
    ]
    e=KnowledgeQueryEngine(claims)
    r=e.compose("best resources to buy and in which shops")
    assert r["reasoning"]["mode"]=="shop_strategy"
    assert "Black Market Trader" in r["answer"]
    assert "strategic interpretations" in r["answer"]
    assert len(r["evidence"])<=4

def test_v63_intent_classifier():
    assert classify_policy_intent("strategy","best resources to buy")=="strategy"
    assert classify_policy_intent("generic","why is this useful")=="interpretation"
