"""V4 regression benchmark: irrelevant evidence must not answer a repair question."""
from agent import retrieve, answer

QUESTION = "what are the best ways to repair your fleets ad free way"

def test_repair_query_routes_to_damage_domain():
    hits = retrieve(QUESTION, 10)
    assert hits, "repair query returned no evidence"
    claims = " ".join(c.get("Claim","").lower() for c in hits)
    assert "repair" in claims or "damage" in claims
    assert "command points" not in claims[:1000] or "repair" in claims

def test_repair_query_does_not_surface_cp_only_answer():
    result = answer(QUESTION)
    text = result["answer"].lower()
    # The historical failure was a CP-only answer to a fleet-repair question.
    assert "command points" not in text or "repair" in text
