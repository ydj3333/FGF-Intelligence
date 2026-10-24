"""YouTube (watched video), playlists, Discord (with images), database sources and the screenshot inbox.
Local fakes for every service; no internet needed."""
import base64
import importlib.util
import io
import json
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


H = load("harvest_sources_media", "scripts/harvest_sources.py")

FEED = """<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom" xmlns:yt="http://www.youtube.com/xml/schemas/2015"
 xmlns:media="http://search.yahoo.com/mrss/">
<entry><yt:videoId>VID1</yt:videoId><title>Season 2 Dev Update</title><published>2026-10-18T10:00:00+00:00</published>
<media:group><media:description>New event: Astral Alignment Party starts October 25, 2026.</media:description></media:group></entry>
<entry><yt:videoId>VID2</yt:videoId><title>Patch Highlights</title><published>2026-10-10T10:00:00+00:00</published>
<media:group><media:description>Watch the highlights.</media:description></media:group></entry>
</feed>"""


def png_bytes():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 20, 30)).save(buf, format="PNG")
    return buf.getvalue()


PNG = png_bytes()


class Fake(BaseHTTPRequestHandler):
    base = ""
    db_rows, video_calls, vision_calls, discord_auth = [], [], [], []
    db_sources = []
    known_videos = []

    def _send(self, code, body, ctype="application/json"):
        raw = body if isinstance(body, bytes) else body.encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(raw)))
        self.end_headers(); self.wfile.write(raw)

    def do_GET(self):
        p = self.path
        if p.startswith("/feeds/videos.xml"):
            return self._send(200, FEED, "application/xml")
        if p.startswith("/discord/channels/555/messages"):
            Fake.discord_auth.append(self.headers.get("Authorization"))
            msgs = [
                {"id": "1001", "timestamp": "2026-10-20T08:00:00Z", "author": {"username": "FGF Official"},
                 "content": "Commerce Guild Duel: the Sunday Stand Down stage begins this week.", "embeds": [], "attachments": []},
                {"id": "1002", "timestamp": "2026-10-21T08:00:00Z", "author": {"username": "FGF Official"}, "content": "",
                 "embeds": [{"title": "Event notice", "description": "See the image."}],
                 "attachments": [{"url": Fake.base + "/img/notice.png", "content_type": "image/png"}]},
            ]
            after = p.split("after=")[1] if "after=" in p else None
            return self._send(200, json.dumps([m for m in msgs if not after or int(m["id"]) > int(after)]))
        if p.startswith("/img/"):
            return self._send(200, PNG, "image/png")
        if p.startswith("/rest/v1/claims"):
            return self._send(200, "[]")
        if p.startswith("/rest/v1/video_database"):
            assert "processing_status=eq.persisted_candidates" in p
            return self._send(200, json.dumps([{"video_id": v} for v in Fake.known_videos]))
        if p.startswith("/rest/v1/sources"):
            return self._send(200, json.dumps(Fake.db_sources))
        if p.startswith("/page/guide"):
            return self._send(200, "<html><head><title>Guide</title></head><body><p>The Research Academy unlocks at Energy Core Level 10 according to the guide.</p></body></html>", "text/html")
        self._send(404, "{}")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.path.startswith("/native/interactions"):
            assert self.headers["x-goog-api-key"] == "g-key"
            video = [i for i in body["input"] if i.get("type") == "video"][0]["uri"]
            Fake.video_calls.append(video)
            claims = [{"claim": "The Astral Alignment Party features Port celebrations and anniversary salutes.", "category": "Events",
                       "claim_type": "FACT", "confidence": "High", "evidence": "Join the Port celebrations and anniversary salutes!", "timestamp": "01:15"}]
            return self._send(200, json.dumps({"status": "completed", "steps": [{"type": "model_output",
                              "content": [{"type": "text", "text": json.dumps({"claims": claims})}]}]}))
        if self.path.startswith("/llm/chat/completions"):
            content = body["messages"][0]["content"]
            if isinstance(content, list):   # image request
                Fake.vision_calls.append(content[1]["image_url"]["url"][:30])
                result = {"transcript": "Dominion Warzone Season 2. Registration closes on October 30, 2026.",
                          "claims": [{"claim": "Dominion Warzone registration closes on October 30, 2026.", "category": "Events",
                                      "claim_type": "SCHEDULE", "confidence": "High", "quote": "Registration closes on October 30, 2026."},
                                     {"claim": "Dominion Warzone grants 9999 gems to all players.", "category": "Events",
                                      "claim_type": "REWARD", "confidence": "Low", "quote": "Registration closes on October 30, 2026."}]}
            elif "Astral Alignment Party starts" in content:
                result = {"claims": [{"claim": "The Astral Alignment Party starts on October 25, 2026.", "category": "Events",
                                      "claim_type": "SCHEDULE", "confidence": "High", "quote": "Astral Alignment Party starts October 25, 2026."}]}
            elif "Sunday Stand Down" in content:
                result = {"claims": [{"claim": "Commerce Guild Duel has a Sunday Stand Down stage.", "category": "Guild",
                                      "claim_type": "RULE", "confidence": "High", "quote": "the Sunday Stand Down stage begins this week"}]}
            elif "Research Academy" in content:
                result = {"claims": [{"claim": "The Research Academy unlocks at Energy Core Level 10.", "category": "Buildings",
                                      "claim_type": "REQUIREMENT", "confidence": "Medium", "quote": "The Research Academy unlocks at Energy Core Level 10"}]}
            else:
                result = {"claims": []}
            return self._send(200, json.dumps({"choices": [{"message": {"content": json.dumps(result)}}]}))
        if self.path.startswith("/rest/v1/claims"):
            Fake.db_rows.extend(body)
            return self._send(201, "")
        self._send(404, "{}")

    def log_message(self, *a):
        pass


@pytest.fixture()
def fake(tmp_path, monkeypatch):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    Fake.base = base
    Fake.db_rows, Fake.video_calls, Fake.vision_calls, Fake.discord_auth, Fake.db_sources = [], [], [], [], []
    Fake.known_videos = []
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    (tmp_path / "knowledge.json").write_text(json.dumps({"claims": []}))
    for mod in (H,):
        monkeypatch.setattr(mod, "STATE_PATH", tmp_path / "state.json")
        monkeypatch.setattr(mod, "KNOWLEDGE_PATH", tmp_path / "knowledge.json")
        monkeypatch.setattr(mod, "YT_FEED", base + "/feeds/videos.xml")
        mod._skipped_models.clear()
    for k, v in {"GEMINI_API_KEY": "g-key", "FGF_HARVEST_LLM_BASE_URL": base + "/llm", "FGF_HARVEST_MODELS": "m1",
                 "FGF_HARVEST_GEMINI_NATIVE_URL": base + "/native", "FGF_SUPABASE_URL": base, "FGF_SUPABASE_SECRET_KEY": "k",
                 "FGF_DISCORD_API": base + "/discord", "DISCORD_BOT_TOKEN": "bot-token", "FGF_DISCORD_CHANNEL_IDS": "555",
                 "FGF_HARVEST_NO_YTDLP": "1"}.items():
        monkeypatch.setenv(k, v)
    yield base, tmp_path, monkeypatch
    srv.shutdown()


def config(tmp_path, monkeypatch, sources, **extra):
    (tmp_path / "cfg.json").write_text(json.dumps({"limits": {"max_pages_per_run": 20}, "sources": sources, **extra}))
    monkeypatch.setattr(H, "CONFIG_PATH", tmp_path / "cfg.json")


def test_youtube_channel_description_and_watched_video(fake):
    base, tmp, mp = fake
    config(tmp, mp, [{"id": "SRC-08", "name": "Official YouTube", "tier": 2, "tier_label": "Tier 2 — Official Developer",
                      "adapter": "youtube_channel", "channel_id": "UC1", "watch_video": True, "max_items": 3, "enabled": True}])
    r = H.run(apply=True)
    rows = {x["claim"]: x for x in Fake.db_rows}
    desc = rows["The Astral Alignment Party starts on October 25, 2026."]
    assert desc["status"] == "Current" and desc["metadata"]["evidence_mode"] == "quote"
    vid = rows["The Astral Alignment Party features Port celebrations and anniversary salutes."]
    assert vid["status"] == "Under Review" and vid["metadata"]["evidence_mode"] == "video"
    assert vid["metadata"]["Source"].endswith("watch?v=VID1&t=75s") and vid["tier"] == "Tier 2 — Official Developer"
    assert len(Fake.video_calls) == 2   # both new videos watched
    # second run: videos already watched, nothing re-processed
    calls = len(Fake.video_calls)
    H.run(apply=True)
    assert len(Fake.video_calls) == calls


def test_playlist_falls_back_to_feed_and_watches(fake):
    base, tmp, mp = fake
    config(tmp, mp, [{"id": "PL", "name": "Playlist", "tier": 3, "tier_label": "Tier 3 — Creator/Community",
                      "adapter": "youtube_playlist", "playlist_id": "PL123", "max_items": 1, "enabled": True}])
    H.run(apply=True)
    assert Fake.video_calls == ["https://www.youtube.com/watch?v=VID1"]     # max_items respected
    assert all(r["tier"].startswith("Tier 3") for r in Fake.db_rows)
    H.run(apply=True)
    assert Fake.video_calls[-1] == "https://www.youtube.com/watch?v=VID2"   # backlog continues next run


def test_videos_already_processed_by_the_transcript_pipeline_are_not_rewatched(fake):
    base, tmp, mp = fake
    Fake.known_videos = ["VID1"]
    config(tmp, mp, [{"id": "PL", "name": "Playlist", "tier": 3, "tier_label": "Tier 3 — Creator/Community",
                      "adapter": "youtube_playlist", "playlist_id": "PL123", "max_items": 5, "enabled": True},
                     {"id": "SRC-08", "name": "Official YouTube", "tier": 2, "tier_label": "Tier 2 — Official Developer",
                      "adapter": "youtube_channel", "channel_id": "UC1", "watch_video": True, "max_items": 3, "enabled": True}])
    r = H.run(apply=True)
    assert "https://www.youtube.com/watch?v=VID1" not in Fake.video_calls
    assert Fake.video_calls.count("https://www.youtube.com/watch?v=VID2") == 1
    # the description of the known video is still read once (cheap text, not video time)
    assert any(x["claim"] == "The Astral Alignment Party starts on October 25, 2026." for x in Fake.db_rows)
    assert r["known_videos_skipped_from"] == 1


def test_discord_text_and_images(fake):
    base, tmp, mp = fake
    config(tmp, mp, [{"id": "SRC-09", "name": "Discord", "tier": 2, "tier_label": "Tier 2 — Official Developer",
                      "adapter": "discord_channel", "channels_env": "FGF_DISCORD_CHANNEL_IDS", "guild_id": "999", "enabled": True}])
    r = H.run(apply=True)
    rows = {x["claim"]: x for x in Fake.db_rows}
    assert "Commerce Guild Duel has a Sunday Stand Down stage." in rows
    img = rows["Dominion Warzone registration closes on October 30, 2026."]
    assert img["metadata"]["evidence_mode"] == "image" and img["metadata"]["Source"] == "https://discord.com/channels/999/555/1002"
    assert not any("9999 gems" in c for c in rows)            # number not in the image text: rejected
    assert Fake.discord_auth[0] == "Bot bot-token" and Fake.vision_calls[0].startswith("data:image/png;base64")
    state = json.loads(H.STATE_PATH.read_text())
    assert state["discord"]["555"] == "1002"
    n = len(Fake.db_rows)
    H.run(apply=True)                                          # only messages after 1002 are fetched
    assert len(Fake.db_rows) == n


def test_discord_not_configured_is_reported_not_failed(fake):
    base, tmp, mp = fake
    mp.delenv("DISCORD_BOT_TOKEN")
    config(tmp, mp, [{"id": "SRC-09", "name": "Discord", "tier": 2, "tier_label": "Tier 2 — Official Developer",
                      "adapter": "discord_channel", "enabled": True}])
    r = H.run(apply=True)
    assert r["sources"][0]["status"] == "not_configured"


def test_sources_from_database_table(fake):
    base, tmp, mp = fake
    Fake.db_sources = [
        {"id": 7, "name": "Guide site", "url": base + "/page/guide", "tier": "T3", "active": True},
        {"id": 8, "name": "Official X", "url": "https://x.com/FoundationGF_EN", "tier": "T2"},
        {"id": 9, "name": "Retired", "url": base + "/page/old", "active": False},
        {"id": 10, "name": "Official site again", "url": base + "/page/guide/", "tier": 1},   # same URL: not duplicated
    ]
    config(tmp, mp, [], use_database_sources=True)
    r = H.run(apply=True)
    assert r["database_sources"]["used"] == 1
    assert any("Official X" in s for s in r["database_sources"]["skipped"])
    row = Fake.db_rows[0]
    assert row["claim"] == "The Research Academy unlocks at Energy Core Level 10."
    assert row["tier"].startswith("Tier 3") and row["metadata"]["source_id"] == "DB-7"


def test_screenshot_inbox(fake, monkeypatch):
    base, tmp, mp = fake
    S = load("ingest_screenshots_test", "scripts/ingest_screenshots.py")
    for name in ("official", "ingame"):
        (tmp / "inbox" / name).mkdir(parents=True)
    (tmp / "inbox/official/instagram-2026-10-21-warzone.png").write_bytes(PNG)
    (tmp / "inbox/ingame/notice.png").write_bytes(PNG)
    (tmp / "inbox/ingame/notes.txt").write_text("ignored")
    monkeypatch.setattr(S, "ROOT", tmp)
    monkeypatch.setattr(S, "INBOX", tmp / "inbox")
    for attr in ("STATE_PATH", "KNOWLEDGE_PATH"):
        monkeypatch.setattr(S.H, attr, getattr(H, attr))
    monkeypatch.setattr(S.H, "_skipped_models", {})
    monkeypatch.setenv("GITHUB_REPOSITORY", "ydj3333/FGF-Intelligence")
    r = S.run(apply=True)
    rows = Fake.db_rows
    official = [x for x in rows if x["tier"] == "Tier 2 — Official Developer"]
    assert official and official[0]["status"] == "Current" and official[0]["version"] == "2026-10-21"
    assert official[0]["metadata"]["Source"].startswith("https://github.com/ydj3333/FGF-Intelligence/blob/main/inbox/processed/")
    # the in-game screenshot repeats the same text: the duplicate is skipped, nothing is auto-Tier-1-live
    assert not any(x["tier"].startswith("Tier 1") and x["status"] != "Under Review" for x in rows)
    # images moved out of the inbox, text file left alone
    assert not (tmp / "inbox/official/instagram-2026-10-21-warzone.png").exists()
    assert list((tmp / "inbox/processed").rglob("*.png")) and (tmp / "inbox/ingame/notes.txt").exists()
