import json, subprocess, time, urllib.request
from pathlib import Path

DATA=json.loads((Path("data")/"knowledge.json").read_text(encoding="utf-8"))
EXPECTED_CLAIMS=len(DATA.get("claims", []))
EXPECTED_TIER1=sum(1 for c in DATA.get("claims", []) if str(c.get("Evidence Tier","")).lower().startswith("tier 1"))
EXPECTED_CONFLICTS=len(DATA.get("conflicts", []))

proc = subprocess.Popen(["python","agent.py"], cwd=".", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(0.6)
    health=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health"))
    assert health["claims"] == EXPECTED_CLAIMS
    assert health["tier1"] == EXPECTED_TIER1
    assert health["conflicts"] == EXPECTED_CONFLICTS
    assert health["claim_lifecycle_aware"] is True
    assert health["version"] == "v5.3.0-response-engine"
    assert "synthesis" in health
    assert "structured_output" in health["synthesis"]
    assert health["lifecycle_states"]["current"] > 0
    assert health["lifecycle_states"]["candidate"] > 0
    lifecycle=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/admin/lifecycle"))
    assert lifecycle["production_current"] > 0
    assert lifecycle["candidate_count"] > 0
    ask=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/ask?q=guild%20creation"))
    assert ask["answer"]
    assert ask["evidence"]
    assert ask["model"]
    assert ask["answer_type"] in ("evidence_fallback","synthesized_evidence")
    assert "quality_gate" in ask
    fleet_dup=urllib.request.urlopen("http://127.0.0.1:8000/api/tools/fleet-builder?style=Ion&champion=Ajita&champion=Ajita&champion=Killer%20Bee")
    fleet_dup_json=json.load(fleet_dup)
    assert fleet_dup_json["ok"] is False
    assert "3 different Champions" in fleet_dup_json["error"]
    fleet_invalid=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/tools/fleet-builder?style=Ion&champion=Ajita&champion=NotAChampion&champion=Killer%20Bee"))
    assert fleet_invalid["ok"] is False
    assert "Non-standard Champion" in fleet_invalid["error"]
    moon=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/ask?q=Shared%20Moonlight%20event%20what%20is%20on%20which%20day%20Monday%20speedups%20shortcut"))
    assert "September 15–21" in moon["answer"] or "September 15-21" in moon["answer"]
    assert "weekday" in moon["answer"].lower()
    assert "not established" in moon["answer"].lower()
    assert "Computational Component" not in moon["answer"] or "Do not move generic" in moon["answer"]
    print("FGF Agent v5.2 lifecycle-aware smoke tests: PASS")
finally:
    proc.terminate(); proc.wait(timeout=2)
