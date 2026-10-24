# FGF AI Agent v8.0 — Integration Candidate

This document accompanies the v8.0 AI-agent integration candidate. It does not by itself activate the agent. The production release must wire the `fgf_agent` modules into the HTTP service, preserve the Core-first evidence policy, and pass the original 50-question release benchmark before deployment.

## Database contract

The live Supabase project `FGF-V4-Intelligence` (`qdoixzfkkmvzjfkhzups`) currently contains 10,051 distinct rows in `public.fgf_question_bank`. Of these, 10,038 remain `needs_review`, 13 are approved, 0 are marked `training_eligible`, and 9,000 are generated paraphrase shells. Treat this table as a retrieval/evaluation corpus, not as 10,051 verified gold answers. For model context, retrieve relevant rows on demand and resolve them to linked `public.claims` plus `public.claim_evidence` / `public.evidence_items`; do not pass the whole table into every prompt or treat generated wording as canonical truth.

## Release gates

- Core → validated Experience → YouTube/community fallback remains unchanged.
- Preserve the original 50-question benchmark and the 10,000-question governed-bank audit.
- Never auto-approve question-bank rows or train model weights from unreviewed rows.
- Keep source tier, lifecycle, season/version, conflicts, and provenance with every retrieved claim.
- Do not deploy until CI passes on the exact candidate SHA, live evaluation passes, and production L0–L6 logging is verified.
- No secrets belong in Git. Configure provider and Supabase server credentials only in the deployment environment.

## How the agent uses the database (v8 decision)

- **Facts come from `public.claims`.** The `corpus-sync` workflow mirrors `supabase.public.claims` into `data/knowledge.json` (1,606 claims at 2026-10-21 17:07 UTC, per `data/knowledge_manifest.json`). The agent indexes all of it at startup and searches it on demand through `search_knowledge`, with tier, lifecycle, season, source and conflict flags attached to every result. There's no per-request database round-trip, and it's versioned and testable in CI.
- **The question bank is not a source of facts.** Rows in `public.fgf_question_bank` are questions, and 10,038 of 10,051 are unreviewed (9,000 are generated paraphrase shells). They are used for **evaluation**: running questions through `/api/chat` or `scripts/run_v8_agent_benchmark.py`. They are never retrieved into the prompt as evidence. Approved rows (13 today) can later serve as worked examples once their answers are reviewed.
- **Possible follow-up:** a read-only `get_evidence_details(claim_key)` tool that fetches `claim_evidence` / `evidence_items` from Supabase when a player asks "where is this from?". It is not needed for answering.

## Release benchmark for v8

`scripts/run_v6_objective1_benchmark.py` calls the deterministic engine directly, so it **does not measure the agent**. It gives identical metrics on `main` and on this branch. The agent equivalent is:

```
python scripts/run_v8_agent_benchmark.py --out reports/v8_agent_benchmark.json   # needs an LLM key
```

It runs the same 50 questions through the agent path. A question fails the gate if any of these occur: fallback to the old engine, a failed grounding check, a citation to unseen evidence, forbidden content, an untraceable number, or an answer with no search. Every answer is written to the report for human grading. With `FGF_REQUIRE_AGENT_EVAL=1` it exits 2 when no key is configured, so a release pipeline can't skip it. The `v8 AI agent` workflow runs the offline tests on push/PR and this benchmark on manual dispatch (using the `ANTHROPIC_API_KEY` secret or `FGF_LLM_*` secrets/vars).

## Current status

Candidate branch: `feature/fgf-v8-ai-agent-integration`.

- **Done in code:** the agent is wired into the HTTP service (`/api/ask`, `/api/chat`, `/api/agent/status`, `ai_agent` in `/api/health`), the Core-first reference is in place, and the circuit breaker, agent benchmark and CI workflow are added. The full test suite passes (198 passed, 0 failed), and all CI commands pass locally.
- **Still pending (needs credentials/access):** push to GitHub, merge, Render deploy, the first live benchmark with a real model, production L0–L6 verification, and the Supabase RLS change.

---

# Design and setup: FGF AI Agent (v8.0)

The answer path is now an **LLM agent with tools** instead of keyword rules and
templated sentences. The deterministic engine is still there as an automatic
fallback, so the service keeps answering even with no API key or during a
provider outage.

## Why the old engine gave weak answers

Before this change, `/api/ask` ran only deterministic code: bag-of-words
scoring, hand-written keyword lists per topic, and answers built by pasting
claim sentences together. Real outputs from the uploaded code:

| Player question | Old answer |
|---|---|
| "I'm F2P at core 28, what should I spend fusion seeds on first?" | "An official launch guide for new players is available…" |
| "what heroes go well together for a kinetic fleet" | "is claim them from your emails you get. And then you can go in your storage…" (raw video transcript) |
| "is it worth joining a guild early" | "This is a comparison question, but the current evidence does not contain a direct head-to-head result." |
| "when is the next maintenance" | September 13–14 window (the October 15 maintenance was in the data but ranked lower) |

No amount of extra keyword rules fixes this. The system has to *understand*
the question, look things up more than once, and *compose* an answer.

## How the agent works

```
player question (+ chat history, + player profile/context)
        │
        ▼
  Core-first: curated rule engine answers first (v6 engine, event plans, Shared
  Moonlight, requirements). Its answer and cited evidence go to the LLM as a reference.
        │
        ▼
  LLM plans ──► search_knowledge (BM25 + FGF glossary, many times, own rewording)
        │       check_conflicts · fleet_synergy · repair_plan · core_progression
        │       event_strategy_planner · calculate · list_champions
        ▼
  draft answer with [E#] citations
        │
        ▼
  fact-check (no LLM): cited refs exist? every number is in evidence/tool/user text?
  searched before stating facts? unavailable Champions not recommended?
        │  fail → one revision round with the issues listed
        ▼
  answer + cited evidence (renumbered E1..En) + grounding report + trace
```

Files (all standard library, no new dependencies):

| File | Purpose |
|---|---|
| `fgf_agent/retrieval.py` | BM25F index over all claims; FGF glossary (heroes↔Champions, F2P, T100, GvG, CP…); transcript-noise down-weighting; authority as a bounded multiplier; near-duplicate collapse |
| `fgf_agent/llm.py` | Provider-agnostic client: Anthropic (Claude) and any OpenAI-compatible API (OpenAI, OpenRouter, Groq, Gemini-compatible, local Ollama) |
| `fgf_agent/tools.py` | Tool definitions + evidence registry; wraps the existing calculators/planners in `agent.py` and `operational_intelligence.py` |
| `fgf_agent/prompts.py` | System prompt: evidence rules (tiers, no invented numbers, F2P/roster constraints, citations) and answer style |
| `fgf_agent/grounding.py` | Post-answer fact-check |
| `fgf_agent/agent.py` | Agent loop, conversation memory (per session, in-process), factory |

## Turning it on (Render)

Set these in the Render dashboard → Environment, then redeploy:

**Option A: Claude (recommended)**
```
ANTHROPIC_API_KEY = sk-ant-...
FGF_AGENT_MODEL   = claude-sonnet-5-5        # or claude-haiku-5-5 for lower cost
```

**Option B: OpenAI (a key is already configured on Render)**

The live service already has `FGF_LLM_API_KEY`/`OPENAI_API_KEY` set, so the agent switches on as soon as v8 is deployed. Check these two things first:
```
FGF_AGENT_MODEL  = <an OpenAI model your key can use, with tool calling>
                   # if unset, the old FGF_LLM_MODEL value is used (default "gpt-5.6-luna"). Confirm it is valid.
FGF_AGENT_MODE   = deterministic   # optional: keep the agent off for the first deploy, then set to auto
```
The OpenAI API is billed per use, separately from ChatGPT plans, so the key needs credits.

**Option C: free tier / other OpenAI-compatible providers**
```
FGF_LLM_PROVIDER = openai
FGF_LLM_API_KEY  = <key>
FGF_AGENT_MODEL  = <model id>
FGF_LLM_BASE_URL = https://generativelanguage.googleapis.com/v1beta/openai   # Google Gemini (has a free tier)
                   # or https://api.groq.com/openai/v1, https://openrouter.ai/api/v1, ...
```

The model must support tool/function calling.

### Safety switch (circuit breaker)

If the provider rejects the key or model (401/403/400/404) or the account has no credits (`insufficient_quota`), the agent **pauses for 15 minutes** and every player gets the rule-based answer immediately. Three transient failures in a row (timeouts, 5xx, dropped connections) pause it for 2 minutes. It retries automatically after the pause. `GET /api/agent/status` → `circuit_breaker` shows `open`, `last_error` and `seconds_until_retry`, which is the quickest way to diagnose a bad key or model.

Optional:
```
FGF_AGENT_MODE      = auto | deterministic   # deterministic = never use the LLM
FGF_AGENT_CORE_REFERENCE = on | off           # give the agent the curated engine's answer first (default on)
FGF_AGENT_MAX_STEPS = 7                      # max tool rounds per answer
FGF_AGENT_MAX_TOKENS= 1400
FGF_LLM_TIMEOUT     = 45
```

Check it: `GET /api/agent/status` should show `"enabled": true`. `/api/health`
now also includes an `ai_agent` block.

Cost note: a typical answer is 1–4 LLM calls. When the Core reference already covers the question, the agent can answer in one call.

## API

* `GET /api/ask?q=...&session_id=...&player_id=...&season=S2&core_level=28` uses the same response shape as before, plus agent fields.
* `POST /api/chat` takes multi-turn chat:
  ```json
  {"message": "and what if I don't have Jodie?",
   "session_id": "a1b2c3d4e5f6",
   "player_id": "optional, loads the saved profile",
   "player_context": {"season": "S2", "core_level": 28, "spending": "F2P", "champions": ["Lily", "Zora Dominii"]},
   "reset": false}
  ```
  The response includes `answer`, `evidence` (cited items, in E1..En order), `grounding`
  (`passed`, `issues`, `unsupported_numbers`), `agent_trace` (tools used), `usage`,
  `session_id`. When the agent is unavailable you get the deterministic answer plus
  `agent_fallback_reason`.

The web UI's Ask page is now a chat: follow-up questions keep context, citations render
as `E#` chips that match the Evidence list, and each answer shows whether it passed the fact-check.

## Bugs fixed along the way

* `constraint_extractor.py` contained **literal backspace bytes** where `\b` was intended, and
  `\s`/`\d` had lost their backslashes. Roster ("I have Lily…"), count, time and resource extraction
  never matched. It also passed a bare string where a tuple was expected, which made nearly every
  question count as "best/optimal". The file was rewritten, and all 16 Champions are now recognised.
* Double-escaped raw-string regexes (`r'\\b…'`) in `agent.py`, `deterministic_synthesis.py`,
  `knowledge_query_engine.py` and two scripts never matched what they intended.
* `operational_intelligence.py` used `build_event_model`, `PlayerState`, `CandidateAction` and `decide`
  without importing them, so the roster-aware Kaboom planner crashed silently.
* `scripts/cross_reference_claims.py` import path broke test collection.
* `evidence_graph.py` could normalise an entity name to an empty string (article stripping).
* The query parser failed to classify comparison questions mentioning rewards; Festival Crew/cosmetic
  questions fell through to a generic dump (the daily Sign-In claim appeared in reward answers);
  specific subjects ("Commerce Guild creation") were collapsed to broader entities.
* The API wrapper dropped the Core-first `baseline_answer` / `answer_layering` audit fields.
* T100 "best way" answers never named the event; they now start with the plan title.
* Roster extraction now accepts Champions missing from the alias list (e.g. new releases) when the
  player lists them after "I have…".
* Agent hardening: dropped connections are treated as provider errors, and oversized tool results
  are trimmed while keeping valid JSON.

Test suite: 149 passed / 21 failed / 1 collection error → **198 passed / 0 failed**. Six of the old
failures were stale tests (renamed labels, a later and deliberately stricter quality gate, typos in
the tests' own inputs); they were updated to the current contract with comments. The rest were code bugs, fixed above.

## Testing without an API key

`tests/test_fgf_agent.py` covers retrieval, grounding, revision, memory, fallback and
both provider wire formats against local mock HTTP servers. Run it with `python -m pytest tests/test_fgf_agent.py`.

## Next steps that would raise quality further

1. **Live evaluation**: with a key configured, run the 50-question benchmark and the question bank through
   `/api/chat` and grade answers (LLM-as-judge plus the existing release gates).
2. **Embeddings**: add an embedding re-rank (or Supabase `pgvector`) on top of BM25 for paraphrases the glossary misses.
3. **Feedback loop**: store thumbs-up/down per answer with the `agent_trace`, and review failures to improve the glossary, prompt and data.
4. **Durable memory**: move `SessionStore` to Supabase if multiple instances or restarts make memory loss noticeable.
