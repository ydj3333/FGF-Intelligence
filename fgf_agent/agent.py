"""The FGF tool-using agent loop, conversation memory and factory."""
from __future__ import annotations

import os
import re
import threading
import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from .grounding import cited_refs, verify_answer
from .llm import LLMClient, LLMError, build_client_from_env
from .prompts import (CORE_REFERENCE_PROMPT, FINALIZE_PROMPT, REVISION_PROMPT, build_system_prompt,
                      strip_citations, summarize_issues)
from .retrieval import EvidenceIndex
from .tools import EvidenceRegistry, ToolBox

try:
    from observability.logging_levels import emit as _emit
except Exception:  # pragma: no cover
    def _emit(*a, **k):
        return {}

try:
    from constraint_extractor import extract_constraints as _extract_constraints
except Exception:  # pragma: no cover
    _extract_constraints = None


class AgentUnavailable(RuntimeError):
    """Raised when the LLM agent cannot answer; callers fall back to the deterministic engine."""


# ---------------------------------------------------------------- sessions
class SessionStore:
    """Small in-memory conversation memory (per process)."""

    def __init__(self, max_sessions: int = 500, max_turns: int = 6, ttl_seconds: int = 3 * 3600):
        self.max_sessions = max_sessions
        self.max_turns = max_turns
        self.ttl = ttl_seconds
        self._data: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.Lock()

    def get(self, sid: str) -> List[Dict[str, str]]:
        with self._lock:
            item = self._data.get(sid)
            if not item or time.time() - item["t"] > self.ttl:
                self._data.pop(sid, None)
                return []
            self._data.move_to_end(sid)
            return list(item["turns"])

    def append(self, sid: str, question: str, answer: str) -> None:
        with self._lock:
            item = self._data.setdefault(sid, {"turns": [], "t": time.time()})
            item["turns"].extend([{"role": "user", "content": question[:2000]},
                                  {"role": "assistant", "content": strip_citations(answer)[:3000]}])
            item["turns"] = item["turns"][-2 * self.max_turns:]
            item["t"] = time.time()
            self._data.move_to_end(sid)
            while len(self._data) > self.max_sessions:
                self._data.popitem(last=False)

    def clear(self, sid: str) -> None:
        with self._lock:
            self._data.pop(sid, None)


_SID_RE = re.compile(r"^[A-Za-z0-9_-]{6,64}$")


def _clean_sid(sid: Optional[str]) -> str:
    sid = str(sid or "").strip()
    return sid if _SID_RE.match(sid) else uuid.uuid4().hex


# ------------------------------------------------------------------- agent
class FGFAgent:
    def __init__(
        self,
        llm: LLMClient,
        toolbox: ToolBox,
        *,
        sessions: Optional[SessionStore] = None,
        max_steps: int = 7,
        profile_fn: Optional[Callable[[str], Optional[Dict[str, Any]]]] = None,
        core_fn: Optional[Callable[[str, Optional[Dict[str, Any]]], Optional[Dict[str, Any]]]] = None,
        clock: Optional[Callable[[], datetime]] = None,
    ):
        self.llm = llm
        self.toolbox = toolbox
        self.sessions = sessions or SessionStore()
        self.max_steps = max_steps
        self.profile_fn = profile_fn
        self.core_fn = core_fn
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        # Circuit breaker: stop calling a provider that is misconfigured (bad
        # key/model, no credits) or repeatedly failing, so players get the
        # deterministic answer immediately instead of waiting on doomed calls.
        self._breaker_lock = threading.Lock()
        self._breaker_until = 0.0
        self._consecutive_failures = 0
        self.last_error: Optional[str] = None
        self.last_success_at: Optional[float] = None

    # Errors that will not fix themselves: pause the agent for longer.
    _HARD_FAILURES = ("auth_failure", "bad_request", "quota_exhausted")
    HARD_PAUSE_SECONDS = 15 * 60
    SOFT_PAUSE_SECONDS = 2 * 60
    SOFT_FAILURE_THRESHOLD = 3

    def breaker_state(self) -> Dict[str, Any]:
        remaining = max(0.0, self._breaker_until - time.time())
        return {"open": remaining > 0, "seconds_until_retry": round(remaining), "last_error": self.last_error,
                "consecutive_failures": self._consecutive_failures,
                "last_success_at": self.last_success_at}

    def _record_failure(self, category: str) -> None:
        with self._breaker_lock:
            self._consecutive_failures += 1
            self.last_error = category
            if category in self._HARD_FAILURES:
                self._breaker_until = time.time() + self.HARD_PAUSE_SECONDS
            elif self._consecutive_failures >= self.SOFT_FAILURE_THRESHOLD:
                self._breaker_until = time.time() + self.SOFT_PAUSE_SECONDS

    def _record_success(self) -> None:
        with self._breaker_lock:
            self._consecutive_failures = 0
            self._breaker_until = 0.0
            self.last_success_at = time.time()

    def _core_reference(self, question: str, context: Dict[str, Any], registry: EvidenceRegistry,
                        extras: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Core-first: run the curated deterministic engine and turn its answer into a cited reference."""
        if not self.core_fn:
            return None
        try:
            core = self.core_fn(question, context or None) or {}
        except Exception:
            return None
        answer = str(core.get("answer") or "").strip()
        if not answer or core.get("answer_type") in ("knowledge_abstention", "evidence_fallback") \
                or answer.lower().startswith(("i cannot establish", "i could not find")):
            return {"baseline": answer, "used": False}
        ref_map: Dict[str, str] = {}
        for i, ev in enumerate((core.get("evidence") or [])[:8]):
            text = str(ev.get("claim") or ev.get("Claim") or "").strip()
            if not text:
                continue
            doc = self.toolbox.index.find_by_text(text)
            if doc is not None:
                ref = registry.add_doc(doc)
            else:
                raw = {"Claim": text, "Evidence Tier": ev.get("tier") or ev.get("Evidence Tier", ""),
                       "Status": ev.get("status") or ev.get("Status", ""), "Source": ev.get("source") or ev.get("Source", ""),
                       "Category": ev.get("category") or ev.get("Category", "")}
                ref = registry.add_raw("core:" + text[:160], raw, text)
            ref_map[f"E{i + 1}"] = ref
        mapped = re.sub(r"\[E(\d+)\]", lambda m: "[" + ref_map.get("E" + m.group(1), "") + "]" if ref_map.get("E" + m.group(1)) else "", answer)
        lines = [mapped]
        op = core.get("operational") or {}
        if op.get("rows"):
            lines.append("Structured plan: " + str(op.get("title") or ""))
            for row in op["rows"][:10]:
                lines.append(" | ".join(str(x) for x in row))
            extras.setdefault("operational", op)
        text = "\n".join(lines)
        registry.tool_texts.append(text)  # numbers in the curated answer/plan are grounded
        return {"baseline": answer, "used": True, "text": text, "answer_type": core.get("answer_type"),
                "refs": list(ref_map.values())}

    # ---------------------------------------------------------------- api
    def ask(self, question: str, *, session_id: Optional[str] = None,
            player_context: Optional[Dict[str, Any]] = None, player_id: Optional[str] = None) -> Dict[str, Any]:
        question = str(question or "").strip()
        if not question:
            raise ValueError("question is required")
        if time.time() < self._breaker_until:
            raise AgentUnavailable("paused_after_" + str(self.last_error or "errors"))
        started = time.time()
        sid = _clean_sid(session_id)
        context = dict(player_context or {})
        if player_id and self.profile_fn:
            try:
                prof = self.profile_fn(player_id) or {}
                for k, v in prof.items():
                    context.setdefault(k, v)
            except Exception:
                pass

        now = self.clock()
        today = now.strftime("%A %d %B %Y")
        system = build_system_prompt(context, today=today)
        history = self.sessions.get(sid)
        registry = EvidenceRegistry()
        extras: Dict[str, Any] = {}

        core_ref = self._core_reference(question, context, registry, extras)
        turn_content = question
        if core_ref and core_ref.get("used"):
            turn_content = (question + "\n\n" + CORE_REFERENCE_PROMPT.format(reference=core_ref["text"]))
        messages: List[Dict[str, Any]] = history + [{"role": "user", "content": turn_content}]
        trace: List[Dict[str, Any]] = []
        usage = {"input_tokens": 0, "output_tokens": 0, "llm_calls": 0}
        tools = self.toolbox.specs()

        constraints = _extract_constraints(question) if _extract_constraints else None
        unavailable = list(getattr(constraints, "unavailable_entities", ()) or ())
        allowed_extra = " ".join([today, now.strftime("%Y-%m-%d"), str(context), " ".join(h["content"] for h in history)])

        answer_text = ""
        report = None
        revised = False
        # A cited curated-engine reference counts as research for grounding.
        searched = bool(core_ref and core_ref.get("used") and core_ref.get("refs"))

        try:
            for step in range(self.max_steps + 2):
                final_round = step >= self.max_steps
                if final_round:
                    messages.append({"role": "user", "content": FINALIZE_PROMPT})
                resp = self.llm.chat(system, messages, [] if final_round else tools)
                usage["llm_calls"] += 1
                for k_in, k_out in (("input_tokens", "input_tokens"), ("prompt_tokens", "input_tokens"),
                                    ("output_tokens", "output_tokens"), ("completion_tokens", "output_tokens")):
                    if isinstance(resp.usage.get(k_in), int):
                        usage[k_out] += resp.usage[k_in]

                if resp.tool_calls and not final_round:
                    messages.append({"role": "assistant", "content": resp.text,
                                     "tool_calls": [{"id": c.id, "name": c.name, "arguments": c.arguments} for c in resp.tool_calls]})
                    results = []
                    for call in resp.tool_calls[:6]:
                        out = self.toolbox.run(call.name, call.arguments, registry, extras)
                        if call.name in ("search_knowledge", "check_conflicts", "core_progression", "event_strategy_planner"):
                            searched = True
                        trace.append({"step": step + 1, **out["summary"]})
                        results.append({"id": call.id, "name": call.name, "content": out["content"]})
                    for call in resp.tool_calls[6:]:
                        results.append({"id": call.id, "name": call.name, "content": '{"error":"too many parallel tool calls; skipped"}'})
                    messages.append({"role": "tool", "results": results})
                    continue

                draft = (resp.text or "").strip()
                if not draft:
                    continue
                report = verify_answer(
                    draft,
                    known_refs=registry.entries.keys(),
                    allowed_text=registry.all_text() + " " + allowed_extra,
                    user_text=question,
                    searched=searched,
                    unavailable_champions=unavailable,
                )
                answer_text = draft
                if report.passed or revised or final_round:
                    break
                revised = True
                trace.append({"step": step + 1, "tool": "fact_check", "issues": report.issues})
                messages.append({"role": "assistant", "content": draft})
                messages.append({"role": "user", "content": REVISION_PROMPT.format(issues=summarize_issues(report.issues))})
        except LLMError as e:
            self._record_failure(e.category)
            _emit("L4", "agent_llm_failed", status="error", error_category=e.category, provider=self.llm.provider,
                  breaker_open=time.time() < self._breaker_until)
            raise AgentUnavailable(e.category) from e

        if not answer_text:
            raise AgentUnavailable("empty_answer")
        self._record_success()

        if report is not None and not report.passed:
            # Last-resort safety: never present unverified figures as fact.
            if report.unsupported_numbers:
                answer_text += ("\n\n_Note: some figures above could not be matched to the knowledge base "
                                "(" + ", ".join(report.unsupported_numbers[:5]) + "). Double-check them in-game._")
            if report.unknown_refs:
                answer_text = re.sub(r"\[(?:" + "|".join(map(re.escape, report.unknown_refs)) + r")\]", "", answer_text)

        final_text, evidence, used = self._renumber(answer_text, registry)
        self.sessions.append(sid, question, final_text)

        latency = round((time.time() - started) * 1000, 1)
        grounding = report.as_dict() if report else {"passed": True, "issues": []}
        _emit("L4", "agent_answer_completed", status="ok" if grounding.get("passed") else "degraded",
              provider=self.llm.provider, model=self.llm.model, steps=len(trace), evidence_count=len(evidence),
              llm_calls=usage["llm_calls"], revised=revised, duration_ms=latency)

        result: Dict[str, Any] = {
            "question": question,
            "answer": final_text,
            "answer_type": "ai_agent",
            "model": self.llm.model,
            "provider": self.llm.provider,
            "session_id": sid,
            "evidence": evidence,
            "evidence_used": used,
            "uncertainty": "" if grounding.get("passed") else "Automatic fact-check flagged parts of this answer: " + "; ".join(grounding.get("issues", []))[:500],
            "grounding": grounding,
            "quality_gate": {"passes": bool(grounding.get("passed")), "method": "agent_grounding_check"},
            "agent_trace": trace,
            "usage": usage,
            "latency_ms": latency,
            "player_context": context or None,
        }
        if core_ref is not None:
            # Core-first audit trail: the curated engine's answer that the agent was given.
            result["baseline_answer"] = core_ref.get("baseline", "")
            result["answer_layering"] = {
                "baseline": "v6_core_knowledge_query_engine",
                "core_reference_provided": bool(core_ref.get("used")),
                "policy": "AI agent receives the curated Core answer first and builds on it; higher-tier evidence governs",
            }
        if extras.get("operational"):
            result["operational"] = extras["operational"]
        return result

    @staticmethod
    def _renumber(text: str, registry: EvidenceRegistry):
        """Renumber cited refs to E1..Ek in citation order and return cited evidence only."""
        order = [r for r in cited_refs(text) if r in registry]
        mapping = {old: f"E{i + 1}" for i, old in enumerate(order)}

        def repl(m):
            parts = re.split(r"\s*[,;]\s*", m.group(1))
            new = []
            for p in parts:
                p = p.strip().upper()
                p = p if p.startswith("E") else "E" + p
                if p in mapping and mapping[p] not in new:
                    new.append(mapping[p])
            return "".join(f"[{x}]" for x in new)

        new_text = re.sub(r"\[(E\d+(?:\s*[,;]\s*E?\d+)*)\]", repl, text)
        evidence = []
        for old in order:
            e = registry.entries[old]
            raw = dict(e.raw)
            raw.pop("metadata", None)
            evidence.append(raw)
        return new_text, evidence, list(range(1, len(order) + 1))


# ----------------------------------------------------------------- factory
_AGENT: Optional[FGFAgent] = None
_AGENT_LOCK = threading.Lock()
_AGENT_ERROR: Optional[str] = None


def agent_mode() -> str:
    """auto (default): use the AI agent when an LLM key is configured.
    llm: same as auto (kept explicit for clarity).
    deterministic / off: never use the AI agent."""
    return os.getenv("FGF_AGENT_MODE", "auto").strip().lower() or "auto"


def _build_default_agent() -> Optional[FGFAgent]:
    global _AGENT_ERROR
    if agent_mode() in ("deterministic", "off", "disabled", "false", "0"):
        _AGENT_ERROR = "disabled_by_FGF_AGENT_MODE"
        return None
    client = build_client_from_env()
    if client is None:
        _AGENT_ERROR = "no_llm_api_key"
        return None
    import agent as core  # the main FGF module (data, calculators)
    try:
        from operational_intelligence import build_operational_output as event_plan
    except Exception:
        event_plan = None

    claims = list(core.CLAIMS) + list(getattr(core, "GUIDE_CLAIMS", []))
    index = EvidenceIndex(claims)

    def profile_fn(pid: str):
        prof, err = core._player_profile_from_db(pid)
        return prof if not err else None

    toolbox = ToolBox(
        index,
        conflicts_fn=core.relevant_conflicts,
        fleet_fn=core.fleet_builder,
        repair_fn=core.repair_planner,
        progression_fn=core.progression_planner,
        event_plan_fn=event_plan,
        champions=getattr(core, "STANDARD_CHAMPIONS", []),
    )
    def core_fn(question, context):
        # Core-first reference: the curated deterministic pipeline (v6 engine +
        # orchestrator + event planners). Disable with FGF_AGENT_CORE_REFERENCE=off.
        return core._DETERMINISTIC_ANSWER(question, context)

    use_core = os.getenv("FGF_AGENT_CORE_REFERENCE", "on").strip().lower() not in ("off", "0", "false", "no")
    _AGENT_ERROR = None
    return FGFAgent(client, toolbox, profile_fn=profile_fn, core_fn=core_fn if use_core else None,
                    max_steps=int(os.getenv("FGF_AGENT_MAX_STEPS", "7")))


def get_agent() -> Optional[FGFAgent]:
    global _AGENT
    if _AGENT is None:
        with _AGENT_LOCK:
            if _AGENT is None:
                _AGENT = _build_default_agent()
    return _AGENT


def agent_status() -> Dict[str, Any]:
    a = get_agent()
    return {
        "enabled": a is not None,
        "mode": agent_mode(),
        "provider": a.llm.provider if a else None,
        "model": a.llm.model if a else None,
        "indexed_facts": len(a.toolbox.index) if a else None,
        "core_reference": bool(a and a.core_fn),
        "reason_disabled": None if a else _AGENT_ERROR,
        # "open": true means the provider failed (bad key/model, no credits,
        # outage) and players are getting rule-based answers until the retry time.
        "circuit_breaker": a.breaker_state() if a else None,
    }
