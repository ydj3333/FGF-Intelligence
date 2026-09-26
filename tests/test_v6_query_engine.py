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
