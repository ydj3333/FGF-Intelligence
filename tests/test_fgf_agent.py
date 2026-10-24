"""Tests for the fgf_agent AI layer (no network, no API key needed)."""
import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from fgf_agent.agent import AgentUnavailable, FGFAgent, SessionStore
from fgf_agent.grounding import cited_refs, verify_answer
from fgf_agent.llm import AnthropicClient, LLMError, LLMResponse, OpenAICompatibleClient, ToolCall
from fgf_agent.retrieval import EvidenceIndex, noise_score, tokenize
from fgf_agent.tools import EvidenceRegistry, ToolBox, safe_eval

CLAIMS = [
    {"Claim": "Server migration requires 10 Migration Permits.", "Category": "Progression",
     "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed", "Source": "in-game", "claim_key": "mig1"},
    {"Claim": "A player must leave their current Commerce Guild before registering for server migration.",
     "Category": "Guild", "Evidence Tier": "Tier 2 — Official FGF Wiki", "Status": "Confirmed", "claim_key": "mig2"},
    {"Claim": "Lily is recommended by the community for Kaboom Robot because of high AoE damage.",
     "Category": "Champions", "Evidence Tier": "Tier 3 — Creator/Community", "Status": "Under Review", "claim_key": "kb1"},
    {"Claim": "Three Matching Heroes provide +20% ATK, DEF, and INT to fleet stats.", "Category": "Champions",
     "Evidence Tier": "Tier 1 — Ultimate/Official", "Status": "Confirmed", "claim_key": "syn3"},
    {"Claim": "is claim them from your emails you get and then you know go in your storage", "Category": "Champions",
     "Evidence Tier": "Tier 3 — Creator/Community", "Status": "Under Review", "claim_key": "noise1"},
    {"Claim": "Old migration needed 5 permits.", "Category": "Progression", "Evidence Tier": "Tier 1",
     "Status": "Superseded", "claim_key": "old1"},
]


class ScriptedLLM:
    provider = "fake"
    model = "fake-model"

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def chat(self, system, messages, tools, temperature=0.2):
        self.calls.append({"system": system, "messages": [dict(m) for m in messages], "tools": tools})
        step = self.script.pop(0)
        return step(messages) if callable(step) else step


def make_agent(script, **kw):
    idx = EvidenceIndex(CLAIMS)
    tb = ToolBox(idx, fleet_fn=lambda s, c: {"ok": True, "synergy_bonus": "+20%"}, champions=["Lily", "Klara"])
    llm = ScriptedLLM(script)
    fixed = lambda: datetime(2026, 10, 21, tzinfo=timezone.utc)
    return FGFAgent(llm, tb, sessions=kw.get("sessions") or SessionStore(), clock=fixed), llm


def search(q, cid="c1"):
    return LLMResponse("", [ToolCall(cid, "search_knowledge", {"query": q})])


# ----------------------------------------------------------------- retrieval
def test_retrieval_synonyms_and_filters():
    idx = EvidenceIndex(CLAIMS)
    assert "old1" not in idx.by_id  # superseded never indexed
    hits = idx.search("how many permits to move server", limit=3)
    assert hits and hits[0]["doc"].doc_id == "mig1"
    heroes = [h["doc"].doc_id for h in idx.search("matching heroes bonus", limit=3)]
    assert heroes[0] == "syn3"
    assert all(h["doc"].tier <= 2 for h in idx.search("migration", official_only=True))


def test_noise_is_downweighted():
    assert noise_score(CLAIMS[4]["Claim"], 3) > 0.5
    assert noise_score(CLAIMS[0]["Claim"], 1) == 0.0
    # Both docs match only via the "Champions" category; the clean official one must win.
    hits = [h["doc"].doc_id for h in EvidenceIndex(CLAIMS).search("champions", limit=5, min_score=0)]
    assert hits.index("syn3") < hits.index("noise1")


def test_tokenize_stems():
    assert tokenize("Heroes champions upgrading") == ["hero", "champion", "upgrad"]


# ------------------------------------------------------------------ tools
def test_safe_eval():
    assert safe_eval("10*3 + max(2,5)") == 35
    assert safe_eval("1,200 / 4") == 300
    with pytest.raises(Exception):
        safe_eval("__import__('os').system('x')")


def test_registry_refs_are_stable():
    reg = EvidenceRegistry()
    idx = EvidenceIndex(CLAIMS)
    d = idx.get("mig1")
    assert reg.add_doc(d) == "E1" and reg.add_doc(d) == "E1"


# --------------------------------------------------------------- grounding
def test_grounding_flags_invented_numbers_and_refs():
    rep = verify_answer("You need 12 permits [E1][E9].", known_refs=["E1"],
                        allowed_text="Server migration requires 10 Migration Permits.")
    assert not rep.passed
    assert rep.unknown_refs == ["E9"] and rep.unsupported_numbers == ["12"]
    ok = verify_answer("You need 10 permits [E1].\n1. Leave your guild", known_refs=["E1"],
                       allowed_text="requires 10 Migration Permits")
    assert ok.passed
    assert cited_refs("a [E1, E3] b [E2]") == ["E1", "E3", "E2"]


def test_grounding_allows_numbers_from_user():
    rep = verify_answer("At Core 28 you should push to 33 [E1].", known_refs=["E1"],
                        allowed_text="Core 33 unlocks a fourth Battle Queue", user_text="I'm core 28")
    assert rep.passed


# ------------------------------------------------------------- agent loop
def test_agent_searches_then_answers_with_renumbered_citations():
    def final(messages):
        tool_msg = messages[-1]
        payload = json.loads(tool_msg["results"][0]["content"])
        refs = {r["claim"][:10]: r["ref"] for r in payload["results"]}
        ref = refs["Server mig"]
        return LLMResponse(f"You need 10 Migration Permits [{ref}]. Leave your guild first [{refs['A player m']}].")

    agent, llm = make_agent([search("migration permits"), final])
    res = agent.ask("how do I migrate servers?")
    assert res["answer_type"] == "ai_agent"
    assert "[E1]" in res["answer"] and "[E2]" in res["answer"]
    assert res["evidence"][0]["Claim"].startswith("Server migration requires 10")
    assert res["grounding"]["passed"]
    assert res["agent_trace"][0]["tool"] == "search_knowledge"
    assert "21 October 2026" in llm.calls[0]["system"]


def test_agent_revises_when_fact_check_fails():
    agent, llm = make_agent([
        search("migration permits"),
        LLMResponse("You need 25 permits [E1]."),          # invented number
        LLMResponse("You need 10 Migration Permits [E1]."),  # corrected
    ])
    res = agent.ask("permits for migration?")
    assert "10 Migration Permits" in res["answer"]
    assert res["grounding"]["passed"]
    assert any(t.get("tool") == "fact_check" for t in res["agent_trace"])
    assert "do not appear in any evidence" in llm.calls[-1]["messages"][-1]["content"]


def test_agent_flags_if_still_ungrounded_after_revision():
    agent, _ = make_agent([search("migration"), LLMResponse("It costs 999 credits [E1]."),
                           LLMResponse("It costs 999 credits [E1].")])
    res = agent.ask("migration cost?")
    assert not res["grounding"]["passed"]
    assert "could not be matched" in res["answer"]


def test_agent_unavailable_on_llm_error():
    def boom(messages):
        raise LLMError("auth_failure", "HTTP 401")
    agent, _ = make_agent([boom])
    with pytest.raises(AgentUnavailable):
        agent.ask("hi")


def test_session_memory_carries_follow_ups():
    store = SessionStore()
    agent, llm = make_agent([search("migration"), LLMResponse("You need 10 permits [E1]."),
                             LLMResponse("Yes, leave the guild first.")], sessions=store)
    first = agent.ask("how many permits to migrate?", session_id="sess-123456")
    agent.ask("anything else?", session_id=first["session_id"])
    msgs = llm.calls[-1]["messages"]
    assert msgs[0]["content"] == "how many permits to migrate?"
    assert "[E1]" not in msgs[1]["content"]  # citations stripped from memory


def test_unavailable_champion_triggers_revision():
    agent, llm = make_agent([search("kaboom lineup"), LLMResponse("Use Lily and Jodie for AoE [E1]."),
                             LLMResponse("Use Lily for AoE [E1]; Jodie is not available to you.")])
    res = agent.ask("kaboom team? I don't have Jodie")
    assert any("do NOT have" in i for t in res["agent_trace"] for i in t.get("issues", []))


def test_core_answer_falls_back_to_deterministic(monkeypatch):
    import agent as core
    import fgf_agent

    class Broken:
        def ask(self, *a, **k):
            raise AgentUnavailable("rate_limited")
    monkeypatch.setattr(fgf_agent, "get_agent", lambda: Broken())
    res = core.answer("how do i repair major damage")
    assert res.get("agent_fallback_reason") == "agent_unavailable: rate_limited"
    assert res.get("answer")


# -------------------------------------------------- provider wire formats
class _MockProvider(BaseHTTPRequestHandler):
    seen = []

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        _MockProvider.seen.append((self.path, {k.lower(): v for k, v in self.headers.items()}, body))
        if self.path.endswith("/v1/messages"):
            if any(m["role"] == "user" and isinstance(m["content"], list) and m["content"][0].get("type") == "tool_result" for m in body["messages"]):
                out = {"content": [{"type": "text", "text": "Done [E1]."}], "stop_reason": "end_turn", "usage": {"input_tokens": 5, "output_tokens": 3}}
            else:
                out = {"content": [{"type": "text", "text": "Let me check."},
                                   {"type": "tool_use", "id": "tu1", "name": "search_knowledge", "input": {"query": "migration"}}],
                       "stop_reason": "tool_use"}
        else:
            if body["messages"][-1]["role"] == "tool":
                out = {"choices": [{"message": {"content": "Done [E1]."}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 5}}
            else:
                out = {"choices": [{"message": {"content": None, "tool_calls": [
                    {"id": "call1", "type": "function", "function": {"name": "search_knowledge", "arguments": "{\"query\":\"migration\"}"}}]},
                    "finish_reason": "tool_calls"}]}
        raw = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *a):
        pass


@pytest.fixture()
def mock_server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), _MockProvider)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    _MockProvider.seen.clear()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
def test_provider_round_trip_over_http(mock_server, kind):
    if kind == "anthropic":
        client = AnthropicClient("k", "claude-test", base_url=mock_server)
    else:
        client = OpenAICompatibleClient("k", "gpt-test", base_url=mock_server + "/v1")
    tb = ToolBox(EvidenceIndex(CLAIMS))
    agent = FGFAgent(client, tb)
    res = agent.ask("how do I migrate?")
    assert res["answer"].startswith("Done [E1]")
    assert res["evidence"]
    path, headers, body = _MockProvider.seen[-1]
    if kind == "anthropic":
        assert headers.get("x-api-key") == "k" and body["tools"][0]["input_schema"]["type"] == "object"
        assert body["messages"][1]["content"][1]["type"] == "tool_use"
    else:
        assert headers.get("authorization") == "Bearer k"
        assert body["messages"][0]["role"] == "system"
        assert body["messages"][2]["tool_calls"][0]["function"]["name"] == "search_knowledge"
        assert body["messages"][3]["role"] == "tool"


# ------------------------------------------------------ circuit breaker
def test_breaker_pauses_after_hard_failure_and_skips_llm():
    def bad_key(messages):
        raise LLMError("auth_failure", "HTTP 401")
    agent, llm = make_agent([bad_key])
    with pytest.raises(AgentUnavailable):
        agent.ask("hi")
    assert agent.breaker_state()["open"] and agent.breaker_state()["last_error"] == "auth_failure"
    calls_before = len(llm.calls)
    with pytest.raises(AgentUnavailable, match="paused_after_auth_failure"):
        agent.ask("hi again")
    assert len(llm.calls) == calls_before  # no doomed provider call


def test_breaker_soft_failures_need_threshold_and_success_resets():
    def flaky(messages):
        raise LLMError("server_error", "HTTP 503")
    agent, _ = make_agent([flaky, flaky, LLMResponse("Hello! Ask me anything about FGF.")])
    for _ in range(2):
        with pytest.raises(AgentUnavailable):
            agent.ask("hi")
    assert not agent.breaker_state()["open"]
    agent.ask("hi")
    assert agent.breaker_state()["consecutive_failures"] == 0


# ------------------------------------------------------ core-first reference
def test_core_reference_is_given_cited_and_recorded():
    core_result = {
        "answer": "Server migration requires 10 Migration Permits. [E1]",
        "answer_type": "knowledge_query",
        "evidence": [{"claim": "Server migration requires 10 Migration Permits.", "tier": "Tier 1", "status": "Confirmed",
                      "source": "in-game", "category": "Progression"}],
        "operational": {"title": "Migration checklist", "rows": [["Step 1", "Collect 10 permits"]]},
    }

    def final(messages):
        assert "Reference answer from FGF's curated rule engine" in messages[-1]["content"]
        assert "[E1]" in messages[-1]["content"]
        return LLMResponse("You need 10 Migration Permits [E1]. Collect them first, then register.")

    idx = EvidenceIndex(CLAIMS)
    llm = ScriptedLLM([final])
    agent = FGFAgent(llm, ToolBox(idx), core_fn=lambda q, ctx: core_result)
    res = agent.ask("how many permits do I need to migrate?")
    assert res["grounding"]["passed"]  # core reference counts as research
    assert res["evidence"][0]["Claim"].startswith("Server migration requires 10")
    assert res["baseline_answer"].startswith("Server migration requires")
    assert res["answer_layering"]["core_reference_provided"] is True
    assert res["operational"]["title"] == "Migration checklist"


def test_core_abstention_is_not_injected():
    def final(messages):
        assert "Reference answer" not in messages[-1]["content"]
        return LLMResponse("Hi!")
    agent = FGFAgent(ScriptedLLM([final]), ToolBox(EvidenceIndex(CLAIMS)),
                     core_fn=lambda q, ctx: {"answer": "I cannot establish the exact answer.", "answer_type": "knowledge_abstention"})
    res = agent.ask("hello")
    assert res["answer_layering"]["core_reference_provided"] is False


def test_openai_insufficient_quota_is_hard_failure(mock_server):
    class Quota(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            raw = json.dumps({"error": {"type": "insufficient_quota", "code": "insufficient_quota"}}).encode()
            self.send_response(429); self.send_header("Content-Length", str(len(raw))); self.end_headers(); self.wfile.write(raw)
        def log_message(self, *a):
            pass
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Quota)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        client = OpenAICompatibleClient("k", "m", base_url=f"http://127.0.0.1:{srv.server_address[1]}/v1")
        with pytest.raises(LLMError) as ei:
            client.chat("s", [{"role": "user", "content": "hi"}], [])
        assert ei.value.category == "quota_exhausted"
    finally:
        srv.shutdown()


def test_shorthand_missing_from_corpus_uses_expansion_and_generic_words_dont_dominate():
    claims = [
        {"Claim": "Upgrading Flagships is listed as a way to increase Command Points.", "Evidence Tier": "Tier 1", "Status": "Confirmed", "claim_key": "cp"},
        {"Claim": "Save Crystals for the Top 100 event milestones.", "Evidence Tier": "Tier 2", "Status": "Confirmed", "claim_key": "t100"},
    ]
    hits = EvidenceIndex(claims).search("best way to do T100", limit=2)
    assert hits[0]["doc"].doc_id == "t100"
