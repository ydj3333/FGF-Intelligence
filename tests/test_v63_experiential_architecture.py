from fgf_orchestrator import FGFOrchestrator
from experience_engine import build_candidates, InMemoryExperienceStore
from observation_contract import validate_observation


def test_observation_contract_rejects_unknown_event():
    ok, reason, _ = validate_observation({
        "session_id": "s1", "event_type": "invented_event",
        "observed_at": "2026-09-27T10:00:00+05:30",
    })
    assert not ok
    assert "unsupported" in reason


def test_observation_contract_accepts_structured_event():
    ok, reason, clean = validate_observation({
        "session_id": "s1", "event_type": "level_changed",
        "entity_type": "champion", "entity_key": "Lily",
        "property": "level", "old_value": 12, "new_value": 13,
        "observed_at": "2026-09-27T10:00:01+05:30",
        "confidence": 1.4,
        "context": {"season":"S2","energy_type":"Kinetic","screen":"champion"},
    })
    assert ok and not reason
    assert clean["confidence"] == 1.0
    assert clean["context"]["season"] == "S2"


def test_learning_needs_repetition_before_validation():
    events = []
    for i in range(4):
        events.append({
            "event_type":"battle_ended","entity_type":"fleet",
            "entity_key":"kinetic_a","property":"result",
            "new_value":"victory",
            "observed_at":f"2026-09-27T10:0{i}:00+05:30",
            "context":{"season":"S2","energy_type":"Kinetic"},
            "outcome":{"result":"success"},
            "pattern":"Kinetic A produced a victory in this comparable combat context."
        })
    candidates = build_candidates(events)
    assert candidates[0]["status"] == "under_review"
    events.append({**events[-1], "observed_at":"2026-09-27T10:05:00+05:30"})
    candidates = build_candidates(events)
    assert candidates[0]["status"] == "validated"


def test_core_remains_first():
    core = lambda q,ctx=None: {
        "answer":"Core fact: established.",
        "answer_type":"knowledge_query",
        "evidence":[{"id":"E1","claim":"Core fact"}],
        "query":{"question_type":"definition"},
    }
    store = InMemoryExperienceStore([{
        "status":"validated","pattern":"Experience says something else","confidence":0.99,
    }])
    result = FGFOrchestrator(core,store).answer("What is X?")
    assert result["branch"] == "core"
    assert "Core fact" in result["answer"]


def test_strategy_can_use_validated_experience():
    core = lambda q,ctx=None: {
        "answer":"Core facts only.",
        "answer_type":"knowledge_query",
        "evidence":[{"id":"E1","claim":"Core fact"}],
        "query":{"question_type":"strategy"},
    }
    store = InMemoryExperienceStore([{
        "status":"validated",
        "pattern":"Configuration A repeatedly improved the observed outcome.",
        "confidence":0.9,
    }])
    result = FGFOrchestrator(core,store).answer("What should I do?")
    assert result["branch"] == "core+experience"
    assert "Configuration A" in result["answer"]


def test_factual_does_not_use_experience_as_missing_truth():
    core = lambda q,ctx=None: {
        "answer":"I cannot establish this.",
        "answer_type":"knowledge_abstention",
        "evidence":[],
        "query":{"question_type":"definition"},
    }
    store = InMemoryExperienceStore([{
        "status":"validated","pattern":"Observed fact candidate","confidence":0.99,
    }])
    result = FGFOrchestrator(core,store).answer("What is X?")
    assert result["abstained"]
    assert result["branch"] == "core_abstention"
