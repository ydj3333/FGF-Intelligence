import json, subprocess, time, urllib.request

proc = subprocess.Popen(["python","agent.py"], cwd=".", stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    time.sleep(0.6)
    health=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/health"))
    assert health["claims"] == 853
    assert health["tier1"] >= 450
    assert health["conflicts"] == 5
    ask=json.load(urllib.request.urlopen("http://127.0.0.1:8000/api/ask?q=guild%20creation"))
    assert ask["results"]
    assert any("Level 9" in r["Claim"] for r in ask["results"])
    print("FGF Agent v3 smoke tests: PASS")
finally:
    proc.terminate(); proc.wait(timeout=2)
