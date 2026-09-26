import json, subprocess, tempfile, time, urllib.request
from pathlib import Path
from urllib.error import URLError, HTTPError

DATA=json.loads((Path("data")/"knowledge.json").read_text(encoding="utf-8"))
EXPECTED_CLAIMS=len(DATA.get("claims", []))
EXPECTED_TIER1=sum(1 for c in DATA.get("claims", []) if str(c.get("Evidence Tier","")).lower().startswith("tier 1"))
EXPECTED_CONFLICTS=len(DATA.get("conflicts", []))

log_file=tempfile.NamedTemporaryFile(prefix="fgf-agent-",suffix=".log",delete=False)
log_path=log_file.name
log_file.close()
proc = subprocess.Popen(["python","agent.py"], cwd=".", stdout=subprocess.DEVNULL, stderr=open(log_path,"w",encoding="utf-8"))

def get_json(url, timeout=2):
    return json.load(urllib.request.urlopen(url, timeout=timeout))

def diagnostic():
    try:
        return Path(log_path).read_text(encoding="utf-8",errors="replace")[-12000:]
    except Exception:
        return ""

try:
    health=None
    last_error=None
    deadline=time.time()+5
    while time.time() < deadline:
        if proc.poll() is not None:
            raise AssertionError("agent.py exited during startup.\n"+diagnostic())
        try:
            health=get_json("http://127.0.0.1:8000/api/health")
            break
        except (URLError, HTTPError, ConnectionError) as e:
            last_error=e
            time.sleep(0.15)
    if health is None:
        raise AssertionError(f"agent health endpoint did not become ready: {last_error}\n{diagnostic()}")

    assert health["claims"] == EXPECTED_CLAIMS
    assert health["tier1"] == EXPECTED_TIER1
    assert health["conflicts"] == EXPECTED_CONFLICTS
    assert health["claim_lifecycle_aware"] is True
    assert health["version"] == "v5.4.5-deterministic-agent"
    assert health["response_engine"]["status"] == "ready"
    assert health["response_engine"]["primary_model"] == "deterministic-evidence-synthesis"
    assert health["response_engine"]["external_api_required"] is False
    assert "synthesis" in health
    assert "structured_output" in health["synthesis"]
    assert health["lifecycle_states"]["current"] > 0
    assert health["lifecycle_states"]["candidate"] > 0
    lifecycle=get_json("http://127.0.0.1:8000/api/admin/lifecycle")
    assert lifecycle["production_current"] > 0
    assert lifecycle["candidate_count"] > 0
    try:
        ask=get_json("http://127.0.0.1:8000/api/ask?q=guild%20creation")
    except Exception as e:
        raise AssertionError(f"/api/ask failed: {e}\nSERVER LOG:\n{diagnostic()}") from e
    assert ask["answer"]
    assert ask["evidence"]
    assert ask["model"]
    assert ask["answer_type"] in ("evidence_fallback","synthesized_evidence")
    assert ask["model"] == "deterministic-evidence-synthesis"
    assert ask["quality_gate"]["passes"] is True
    assert "quality_gate" in ask
    fleet_dup=get_json("http://127.0.0.1:8000/api/tools/fleet-builder?style=Ion&champion=Ajita&champion=Ajita&champion=Killer%20Bee")
    assert fleet_dup["ok"] is False
    assert "3 different Champions" in fleet_dup["error"]
    fleet_invalid=get_json("http://127.0.0.1:8000/api/tools/fleet-builder?style=Ion&champion=Ajita&champion=NotAChampion&champion=Killer%20Bee")
    assert fleet_invalid["ok"] is False
    assert "Non-standard Champion" in fleet_invalid["error"]
    moon=get_json("http://127.0.0.1:8000/api/ask?q=Shared%20Moonlight%20event%20what%20is%20on%20which%20day%20Monday%20speedups%20shortcut")
    assert "moonlight" in moon["answer"].lower() or "evidence" in moon["answer"].lower()
    assert "weekday" in moon["answer"].lower() or "not established" in moon["answer"].lower()
    assert "Computational Component" not in moon["answer"]
    print("FGF Agent v5.3 response-engine smoke tests: PASS")
finally:
    proc.terminate()
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
    try:
        Path(log_path).unlink(missing_ok=True)
    except Exception:
        pass
