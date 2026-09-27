from fgf_orchestrator import FGFOrchestrator
from experience_engine import build_candidates, InMemoryExperienceStore
from observation_contract import validate_observation
from live_runtime import LiveObservationRuntime


def test_observation_contract_rejects_unknown_event():
    ok, reason, _ = validate_observation({
        "session_id": "s1", "event_type": "invented_event",
        "observed_at": "2026-09-27T10:00:00+05:30",
    })
    assert not ok
    assert "unsupported" in reason


def test_observation_contract_accepts_and_clamps_confidence():
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
    events=[]
    for i in range(4):
        events.append({
            "event_type":"battle_ended","entity_type":"fleet",
            "entity_key":"kinetic_a","property":"result","new_value":"victory",
            "observed_at":f"2026-09-27T10:0{i}:00+05:30",
            "context":{"season":"S2","energy_type":"Kinetic"},
            "outcome":{"result":"success"},
            "pattern":"Kinetic A produced a victory in this comparable combat context.",
        })
    candidates=build_candidates(events)
    assert candidates[0]["status"]=="under_review"
    events.append({**events[-1],"observed_at":"2026-09-27T10:05:00+05:30"})
    candidates=build_candidates(events)
    assert candidates[0]["status"]=="validated"


def test_core_remains_first():
    core=lambda q,ctx=None:{
        "answer":"Core fact: established.","answer_type":"knowledge_query",
        "evidence":[{"id":"E1","claim":"Core fact","tier":"Tier 1 — Ultimate/Official"}],
        "query":{"question_type":"definition"},
    }
    store=InMemoryExperienceStore([{"status":"validated","pattern":"Experience says something else","confidence":0.99}])
    result=FGFOrchestrator(core,store).answer("What is X?")
    assert result["branch"]=="core"
    assert "Core fact" in result["answer"]


def test_strategy_can_use_validated_experience():
    core=lambda q,ctx=None:{
        "answer":"Core facts only.","answer_type":"knowledge_query",
        "evidence":[{"id":"E1","claim":"Core fact","tier":"Tier 1 — Ultimate/Official"}],
        "query":{"question_type":"strategy"},
    }
    store=InMemoryExperienceStore([{"status":"validated","pattern":"Configuration A repeatedly improved the observed outcome.","confidence":0.9}])
    result=FGFOrchestrator(core,store).answer("What should I do?")
    assert result["branch"]=="core+experience"
    assert "Configuration A" in result["answer"]


def test_factual_missing_core_does_not_promote_experience():
    core=lambda q,ctx=None:{
        "answer":"I cannot establish this.","answer_type":"knowledge_abstention",
        "evidence":[],"query":{"question_type":"definition"},
    }
    store=InMemoryExperienceStore([{"status":"validated","pattern":"Observed fact candidate","confidence":0.99}])
    result=FGFOrchestrator(core,store).answer("What is X?")
    assert result["abstained"]
    assert result["branch"]=="core_abstention"


def test_runtime_accepts_live_event_without_supabase():
    runtime=LiveObservationRuntime("http://127.0.0.1:9",None)
    assert runtime.start_session({"session_id":"local-test","observer_version":"test"})["ok"]
    observed=runtime.ingest_observation({
        "session_id":"local-test","event_type":"screen_changed",
        "entity_type":"screen","entity_key":"FGF",
        "property":"visual_change_score","new_value":15.2,
        "observed_at":"2026-09-27T10:00:00+05:30",
    })
    assert observed["ok"]
    assert observed["durable"] is False
    assert runtime.stop_session({"session_id":"local-test"})["ok"]


def test_runtime_status_has_two_hour_budget():
    runtime=LiveObservationRuntime("",None)
    status=runtime.status()
    assert status["daily_limit_seconds"]==7200
    assert status["raw_video_upload"] is False
