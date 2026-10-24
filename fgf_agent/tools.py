"""Tools the FGF agent can call, plus the per-answer evidence registry."""
from __future__ import annotations

import ast
import json
import math
import operator
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence

from .retrieval import EvidenceDoc, EvidenceIndex

MAX_TOOL_OUTPUT_CHARS = 7000


# --------------------------------------------------------------------- registry
@dataclass
class RegistryEntry:
    ref: str
    doc: Optional[EvidenceDoc]
    raw: Dict[str, Any]
    text: str


class EvidenceRegistry:
    """Assigns stable [E#] refs to every piece of evidence shown to the model."""

    def __init__(self) -> None:
        self.entries: Dict[str, RegistryEntry] = {}
        self._by_key: Dict[str, str] = {}
        self.tool_texts: List[str] = []  # raw tool outputs (for number grounding)

    def add_doc(self, doc: EvidenceDoc) -> str:
        key = "doc:" + doc.doc_id
        if key in self._by_key:
            return self._by_key[key]
        ref = f"E{len(self.entries) + 1}"
        self.entries[ref] = RegistryEntry(ref, doc, doc.raw, doc.claim + " " + doc.notes)
        self._by_key[key] = ref
        return ref

    def add_raw(self, key: str, raw: Dict[str, Any], text: str) -> str:
        key = "raw:" + key
        if key in self._by_key:
            return self._by_key[key]
        ref = f"E{len(self.entries) + 1}"
        self.entries[ref] = RegistryEntry(ref, None, raw, text)
        self._by_key[key] = ref
        return ref

    def __contains__(self, ref: str) -> bool:
        return ref in self.entries

    def __len__(self) -> int:
        return len(self.entries)

    def all_text(self) -> str:
        return " \n".join([e.text for e in self.entries.values()] + self.tool_texts)


# ------------------------------------------------------------------ calculator
_OPS = {
    ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod, ast.Pow: operator.pow,
    ast.USub: operator.neg, ast.UAdd: operator.pos,
}
_FUNCS = {"min": min, "max": max, "round": round, "ceil": math.ceil, "floor": math.floor, "sum": lambda *a: sum(a), "abs": abs}


def safe_eval(expr: str) -> float:
    expr = str(expr).replace("×", "*").replace("÷", "/").replace("^", "**")
    expr = re.sub(r"(?<=\d),(?=\d{3}(?!\d))", "", expr)  # 1,200 -> 1200 but keep max(2,5)
    if len(expr) > 300:
        raise ValueError("expression too long")
    node = ast.parse(expr, mode="eval")

    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            left, right = ev(n.left), ev(n.right)
            if isinstance(n.op, ast.Pow) and abs(right) > 12:
                raise ValueError("exponent too large")
            return _OPS[type(n.op)](left, right)
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsupported expression")

    return ev(node)


# ---------------------------------------------------------------- tool specs
TOOL_SPECS: List[Dict[str, Any]] = [
    {
        "name": "search_knowledge",
        "description": (
            "Search the FGF knowledge base (official announcements, in-game screens, wiki, tested guides, "
            "community/creator reports). Returns facts with a ref id (E#), authority tier and source. "
            "Use short, specific queries with game terms (e.g. 'Energy Core 33 unlock', 'Kaboom Robot lineup AoE', "
            "'Migration Permits requirement'). Call it multiple times with different wording or sub-topics."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to look for, using game vocabulary."},
                "category": {"type": "string", "description": "Optional category filter, e.g. Progression, Champions, Events, Combat, Economy, Flagships, Guild, PvP, Buildings."},
                "official_only": {"type": "boolean", "description": "Only Tier 1/2 (official or tested) facts. Default false."},
                "limit": {"type": "integer", "description": "Max results, 1-10. Default 8."},
            },
            "required": ["query"],
        },
    },
    {
        "name": "check_conflicts",
        "description": "List known disagreements between sources on a topic (e.g. a community video contradicting official info). Use for contested or surprising claims.",
        "parameters": {
            "type": "object",
            "properties": {"topic": {"type": "string"}},
            "required": ["topic"],
        },
    },
    {
        "name": "list_champions",
        "description": "Return the standard list of Champion (hero) names in the game, for spelling and for roster questions.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "name": "fleet_synergy",
        "description": "Compute Style Resonance for a 3-Champion fleet of a given style (Beam, Kinetic or Ion), using documented Champion styles. Returns which Champions match and the bonus.",
        "parameters": {
            "type": "object",
            "properties": {
                "style": {"type": "string", "enum": ["Beam", "Kinetic", "Ion"]},
                "champions": {"type": "array", "items": {"type": "string"}, "description": "Exactly 3 standard Champion names."},
            },
            "required": ["style", "champions"],
        },
    },
    {
        "name": "repair_plan",
        "description": "Repair path for damaged fleets given damage type (minor or major), Repair Modules available, and whether the fleet is still in combat.",
        "parameters": {
            "type": "object",
            "properties": {
                "damage": {"type": "string", "enum": ["minor", "major"]},
                "repair_modules": {"type": "integer"},
                "in_combat": {"type": "boolean"},
            },
            "required": ["damage"],
        },
    },
    {
        "name": "core_progression",
        "description": "Documented Energy Core milestones and requirements between the player's current level and a target level (max 35).",
        "parameters": {
            "type": "object",
            "properties": {
                "current_level": {"type": "integer"},
                "target_level": {"type": "integer"},
                "season": {"type": "string", "description": "S1, S2 or S3"},
            },
            "required": ["current_level", "target_level"],
        },
    },
    {
        "name": "event_strategy_planner",
        "description": (
            "Structured planner for event lineups/strategy (e.g. Kaboom Robots lineups from the player's owned Champions, "
            "event priorities). Pass the player's request in natural language including event name and owned Champions."
        ),
        "parameters": {
            "type": "object",
            "properties": {"request": {"type": "string"}},
            "required": ["request"],
        },
    },
    {
        "name": "calculate",
        "description": "Evaluate an arithmetic expression exactly (+ - * / ** min max round ceil floor). Use for totals, per-day rates, time estimates.",
        "parameters": {
            "type": "object",
            "properties": {"expression": {"type": "string"}},
            "required": ["expression"],
        },
    },
]


def _truncate(obj: Any) -> str:
    """Serialise a tool result within the size budget, always as valid JSON."""
    s = json.dumps(obj, ensure_ascii=False, default=str)
    if len(s) <= MAX_TOOL_OUTPUT_CHARS:
        return s
    if isinstance(obj, dict):
        obj = dict(obj)
        # Drop whole list items (e.g. lowest-ranked search results) first.
        for key in ("results", "conflicts", "rows", "evidence"):
            items = obj.get(key)
            if isinstance(items, list):
                items = list(items)
                while items and len(json.dumps({**obj, key: items}, ensure_ascii=False, default=str)) > MAX_TOOL_OUTPUT_CHARS - 40:
                    items.pop()
                obj[key] = items
                obj["truncated"] = True
                s = json.dumps(obj, ensure_ascii=False, default=str)
                if len(s) <= MAX_TOOL_OUTPUT_CHARS:
                    return s
    return json.dumps({"truncated": True, "partial": s[: MAX_TOOL_OUTPUT_CHARS - 60]}, ensure_ascii=False)


class ToolBox:
    """Executes tool calls against the knowledge base and existing calculators.

    The legacy helpers are injected so this package has no import cycle with
    agent.py and can be unit-tested with fakes.
    """

    def __init__(
        self,
        index: EvidenceIndex,
        *,
        conflicts_fn: Optional[Callable[[str], List[Dict[str, Any]]]] = None,
        fleet_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        repair_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        progression_fn: Optional[Callable[..., Dict[str, Any]]] = None,
        event_plan_fn: Optional[Callable[[str, List[Dict[str, Any]]], Optional[Dict[str, Any]]]] = None,
        champions: Sequence[str] = (),
    ) -> None:
        self.index = index
        self.conflicts_fn = conflicts_fn
        self.fleet_fn = fleet_fn
        self.repair_fn = repair_fn
        self.progression_fn = progression_fn
        self.event_plan_fn = event_plan_fn
        self.champions = list(champions)

    def specs(self) -> List[Dict[str, Any]]:
        available = {
            "check_conflicts": self.conflicts_fn is not None,
            "fleet_synergy": self.fleet_fn is not None,
            "repair_plan": self.repair_fn is not None,
            "core_progression": self.progression_fn is not None,
            "event_strategy_planner": self.event_plan_fn is not None,
            "list_champions": bool(self.champions),
        }
        return [t for t in TOOL_SPECS if available.get(t["name"], True)]

    # ------------------------------------------------------------- dispatch
    def run(self, name: str, args: Dict[str, Any], registry: EvidenceRegistry,
            extras: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run a tool; returns {"content": str (for the model), "summary": {...}}."""
        handler = getattr(self, "_t_" + str(name), None)
        if handler is None:
            out = {"error": f"Unknown tool '{name}'."}
            return {"content": _truncate(out), "summary": {"tool": name, "error": "unknown_tool"}}
        try:
            out, summary = handler(args or {}, registry, extras if extras is not None else {})
        except Exception as exc:  # tool failures must not kill the answer
            out = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            summary = {"error": type(exc).__name__}
        content = _truncate(out)
        if name not in ("search_knowledge", "check_conflicts"):
            registry.tool_texts.append(content)
        return {"content": content, "summary": {"tool": name, **summary}}

    # --------------------------------------------------------------- tools
    def _t_search_knowledge(self, args, registry, extras):
        query = str(args.get("query") or "").strip()
        if not query:
            return {"error": "query is required"}, {"results": 0}
        try:
            limit = max(1, min(10, int(args.get("limit") or 8)))
        except (TypeError, ValueError):
            limit = 8
        hits = self.index.search(query, limit=limit, category=args.get("category") or None,
                                 official_only=bool(args.get("official_only")))
        if not hits and args.get("category"):
            hits = self.index.search(query, limit=limit, official_only=bool(args.get("official_only")))
        results = []
        for h in hits:
            ref = registry.add_doc(h["doc"])
            results.append(h["doc"].to_public(ref))
        out: Dict[str, Any] = {"query": query, "results": results}
        if not results:
            out["note"] = ("No matching facts. Try other wording (synonyms, the exact mechanic/event/resource name) "
                           "or a broader query. If repeated searches find nothing, tell the player it isn't covered.")
        return out, {"query": query, "results": len(results), "refs": [r["ref"] for r in results]}

    def _t_check_conflicts(self, args, registry, extras):
        topic = str(args.get("topic") or "").strip()
        rows = self.conflicts_fn(topic) if (self.conflicts_fn and topic) else []
        out = []
        for c in rows[:6]:
            text = " | ".join(str(c.get(k, "")) for k in ("Topic", "Claim", "Existing / Tier-2 claim", "Tier-1 evidence", "Decision", "Notes") if c.get(k))
            raw = {
                "Claim": "Conflict: " + str(c.get("Topic") or c.get("Claim") or "")[:200],
                "Notes": text[:600],
                "Evidence Tier": c.get("Evidence Tier") or "Conflict record",
                "Status": c.get("Status") or c.get("Decision") or "Conflicting",
                "Source": c.get("Source", ""),
                "Category": c.get("Category", "Conflict"),
            }
            ref = registry.add_raw(str(c.get("Conflict ID") or text[:80]), raw, text)
            out.append({"ref": ref, "summary": text[:600]})
        return {"topic": topic, "conflicts": out, "note": "" if out else "No recorded conflicts on this topic."}, {"topic": topic, "results": len(out)}

    def _t_list_champions(self, args, registry, extras):
        return {"champions": self.champions}, {"results": len(self.champions)}

    def _t_fleet_synergy(self, args, registry, extras):
        res = self.fleet_fn(args.get("style", ""), list(args.get("champions") or []))
        return res, {"ok": bool(res.get("ok"))}

    def _t_repair_plan(self, args, registry, extras):
        res = self.repair_fn(args.get("damage", "minor"), int(args.get("repair_modules") or 0), bool(args.get("in_combat")))
        return res, {"ok": bool(res.get("ok"))}

    def _t_core_progression(self, args, registry, extras):
        res = self.progression_fn(int(args.get("current_level") or 1), int(args.get("target_level") or 35), str(args.get("season") or "S2"))
        # Register the evidence rows so the model can cite them.
        for row in (res.get("evidence") or [])[:12]:
            ref = registry.add_raw("prog:" + str(row.get("claim", ""))[:120],
                                   {"Claim": row.get("claim", ""), "Evidence Tier": row.get("tier", ""),
                                    "Confidence": row.get("confidence", ""), "Status": row.get("status", ""),
                                    "Source": row.get("source", "")}, str(row.get("claim", "")))
            row["ref"] = ref
        return res, {"ok": bool(res.get("ok"))}

    def _t_event_strategy_planner(self, args, registry, extras):
        request = str(args.get("request") or "").strip()
        # Give the planner the event evidence it expects.
        hits = self.index.search(request, limit=10)
        evidence = [h["doc"].raw for h in hits]
        plan = self.event_plan_fn(request, evidence) if self.event_plan_fn else None
        if not plan or not plan.get("rows"):
            return {"plan": None, "note": "No structured plan for this request; answer from searched evidence instead."}, {"ok": False}
        extras["operational"] = plan
        keep = {k: plan.get(k) for k in ("title", "mode", "recommendation", "rows", "columns", "headers",
                                         "player_roster", "selection", "source_state", "notes", "warnings") if plan.get(k)}
        return {"plan": keep}, {"ok": True, "mode": plan.get("mode")}

    def _t_calculate(self, args, registry, extras):
        expr = str(args.get("expression") or "")
        val = safe_eval(expr)
        if isinstance(val, float) and val.is_integer():
            val = int(val)
        elif isinstance(val, float):
            val = round(val, 4)
        return {"expression": expr, "result": val}, {"expression": expr[:80]}
