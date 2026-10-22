"""Learning loop (player feedback -> checked knowledge) and YouTube evidence in the app. Local fakes only."""
import importlib.util
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


L = load("learn_from_players_test", "scripts/learn_from_players.py")
X = load("export_video_evidence_test", "scripts/export_video_evidence.py")

NOTICE = ("<html><head><title>Kaboom schedule change</title></head><body><main><p>Update: Kaboom now starts on Saturday, "
          "October 24, 2026 instead of Friday. Robots return with the usual rewards.</p></main></body></html>")


class Fake(BaseHTTPRequestHandler):
    feedback, patches, inserted, videos, cands = [], [], [], [], []
    missing_table = False

    def _send(self, code, body, ctype="application/json"):
        raw = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        p = self.path
        if p.startswith("/rest/v1/app_feedback"):
            if Fake.missing_table:
                return self._send(404, '{"message":"relation does not exist"}')
            assert "status=eq.new" in p
            return self._send(200, json.dumps(Fake.feedback))
        if p.startswith("/rest/v1/claims"):
            return self._send(200, "[]")
        if p.startswith("/rest/v1/video_database"):
            return self._send(200, json.dumps(Fake.videos))
        if p.startswith("/rest/v1/video_claim_candidates"):
            return self._send(200, json.dumps(Fake.cands))
        if p.startswith("/page/notice"):
            return self._send(200, NOTICE, "text/html")
        self._send(404, "{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/llm/chat/completions"):
            claims = [{"claim": "Kaboom starts on Saturday, October 24, 2026.", "category": "Events", "claim_type": "SCHEDULE",
                       "confidence": "High", "quote": "Kaboom now starts on Saturday, October 24, 2026"},
                      {"claim": "Kaboom gives 500 extra robots.", "category": "Events", "claim_type": "REWARD",
                       "confidence": "Low", "quote": "Robots return with the usual rewards"}]
            return self._send(200, json.dumps({"choices": [{"message": {"content": json.dumps({"claims": claims})}}]}))
        if self.path.startswith("/rest/v1/claims"):
            Fake.inserted.extend(body)
            return self._send(201, "")
        self._send(404, "{}")

    def do_PATCH(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        Fake.patches.append((self.path, body))
        self._send(204, "")

    def log_message(self, *a):
        pass


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    Fake.feedback, Fake.patches, Fake.inserted, Fake.videos, Fake.cands, Fake.missing_table = [], [], [], [], [], False
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    know = tmp_path / "knowledge.json"
    know.write_text(json.dumps({"claims": [{"Claim": "The Research Academy unlocks at Energy Core Level 10.", "Evidence Tier": "Tier 2"}]}))
    monkeypatch.setattr(L.H, "KNOWLEDGE_PATH", know)
    monkeypatch.setattr(L, "GAPS_PATH", tmp_path / "gaps.json")
    monkeypatch.setattr(L, "REPORT_PATH", tmp_path / "report.md")
    L.H._skipped_models.clear()
    for k, v in {"GEMINI_API_KEY": "g", "FGF_HARVEST_LLM_BASE_URL": base + "/llm", "FGF_HARVEST_MODELS": "m1",
                 "FGF_SUPABASE_URL": base, "FGF_SUPABASE_SECRET_KEY": "k"}.items():
        monkeypatch.setenv(k, v)
    yield base, tmp_path
    srv.shutdown()


def fb(i, kind, question, **kw):
    return {"id": i, "kind": kind, "question": question, "created_at": "2026-10-22T10:00:00Z", "cited_facts": [], **kw}


def test_learning_run(fake):
    base, tmp = fake
    bad_fact = "Kaboom starts on Friday."
    Fake.feedback = [
        fb(1, "correction", "When does Kaboom start?", correction="It moved to Saturday.", source_url=base + "/page/notice"),
        fb(2, "correction", "Kaboom rewards?", correction="See the official post.", source_url="https://www.instagram.com/p/abc"),
        fb(3, "correction", "Best T100 plan?", correction="Day 3 should save speedups."),
        fb(4, "unanswered", "When is the next Kaboom event?"),
        fb(5, "unanswered", "when is next kaboom event"),
        fb(6, "unanswered", "When does the Research Academy unlock?"),
        *[fb(10 + i, "not_helpful", "When does Kaboom start?", cited_facts=[bad_fact]) for i in range(3)],
        fb(20, "helpful", "Academy?", cited_facts=["The Research Academy unlocks at Energy Core Level 10."]),
    ]
    r = L.run(apply=True)
    # the linked source was read; only the grounded fact entered, for review, marked as player-submitted
    assert [x["claim"] for x in Fake.inserted] == ["Kaboom starts on Saturday, October 24, 2026."]
    row = Fake.inserted[0]
    assert row["status"] == "Under Review" and row["tier"].startswith("Tier 3") and row["canonical"] is False
    assert row["metadata"]["submitted_by"] == "player" and row["metadata"]["feedback_id"] == 1
    checked = {x["id"]: x for x in r["links_checked"]}
    assert checked[1]["action"] == "checked" and checked[1]["new_facts"] == 1 and checked[1]["rejected_ungrounded"] == 1
    assert checked[2]["action"] == "needs_screenshot"
    # link-less correction kept for the admin review
    gaps = json.loads((tmp / "gaps.json").read_text())
    assert gaps["corrections_pending_review"][0]["id"] == 3
    # two wordings of the same question -> one gap counted twice; the academy question is already covered
    open_gaps = {k: g for k, g in gaps["gaps"].items() if g["status"] == "open"}
    kaboom = [g for g in open_gaps.values() if "kaboom" in g["example"].lower() and g["unanswered"]]
    assert len(kaboom) == 1 and kaboom[0]["unanswered"] == 2
    assert any(g["status"] == "covered" and "Academy" in g["example"] for g in gaps["gaps"].values())
    # a fact cited in 3 unhelpful answers is flagged for re-checking
    assert r["flagged_facts"][0][0] == bad_fact
    # every row is marked processed
    patched = ",".join(p for p, _ in Fake.patches)
    for i in (1, 2, 3, 4, 5, 6, 10, 11, 12, 20):
        assert str(i) in patched
    assert all(b["status"] == "processed" for _, b in Fake.patches)
    md = L.markdown(r)
    assert "Kaboom" in md and "needs_screenshot" in md


def test_learning_run_is_repeatable_and_dry_run_writes_nothing(fake):
    base, tmp = fake
    Fake.feedback = [fb(4, "unanswered", "When is the next Kaboom event?")]
    L.run(apply=True)
    L.run(apply=True)
    gaps = json.loads((tmp / "gaps.json").read_text())
    assert list(gaps["gaps"].values())[0]["count"] == 2      # counts accumulate across runs
    Fake.patches.clear()
    (tmp / "gaps.json").unlink()
    L.run(apply=False)
    assert not Fake.patches and not (tmp / "gaps.json").exists()


def test_missing_table_explains_setup(fake):
    Fake.missing_table = True
    r = L.run(apply=True)
    assert any("sql/app_feedback.sql" in n for n in r["notes"])


def test_video_evidence_reaches_the_app(fake, monkeypatch):
    base, tmp = fake
    Fake.videos = [{"id": 1, "video_id": "AAAAAAAAAAA", "title": "Kaboom guide", "video_url": "https://www.youtube.com/watch?v=AAAAAAAAAAA",
                    "channel_title": "Creator", "processing_status": "persisted_candidates"},
                   {"id": 2, "video_id": "BBBBBBBBBBB", "title": "Old", "processing_status": "rejected"}]
    Fake.cands = [
        {"id": 1, "video_database_id": 1, "video_id": "AAAAAAAAAAA", "claim_text": "Zora, Lily and Jodie are a popular Kaboom lineup.",
         "category": "Events", "evidence_tier": 2, "status": "candidate", "source_url": "https://www.youtube.com/watch?v=AAAAAAAAAAA&t=60s"},
        {"id": 2, "video_database_id": 1, "video_id": "AAAAAAAAAAA", "claim_text": "This was rejected by the admin review.", "status": "rejected"},
        {"id": 3, "video_database_id": 2, "video_id": "BBBBBBBBBBB", "claim_text": "From a rejected video, not exported.", "status": "candidate"},
    ]
    data = X.export(base, "k")
    assert [c["claim"] for c in data["candidates"]] == ["Zora, Lily and Jodie are a popular Kaboom lineup."]
    assert data["candidates"][0]["tier"] == 3            # never above Tier 3 in the app

    # build the app bundle from a minimal repo containing that export
    repo = tmp / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "data/knowledge.json").write_text(json.dumps({"claims": [
        {"Claim": "Kaboom robots event runs on weekends.", "Category": "Events", "Evidence Tier": "Tier 2", "Status": "Current"}]}))
    (repo / "data/video_evidence.json").write_text(json.dumps(data))
    (repo / "claim_lifecycle.py").write_text((ROOT / "claim_lifecycle.py").read_text())
    B = load("build_site_test", "site/build_site.py")
    sys.modules.pop("claim_lifecycle", None)
    bundle = B.build_bundle(repo)
    sys.modules.pop("claim_lifecycle", None)
    vids = [f for f in bundle["facts"] if f.get("y")]
    assert len(vids) == 1 and vids[0]["t"] == 3 and vids[0]["s"] == "candidate"
    assert "Kaboom guide" in vids[0]["n"] and bundle["meta"]["video"] == 1
    assert [f for f in bundle["facts"] if not f.get("y")][0]["c"] == "Kaboom robots event runs on weekends."
