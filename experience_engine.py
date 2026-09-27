"""FGF v6.3 experiential learning engine.

Observations are candidate evidence. Only repeated, context-compatible patterns
are promoted to validated experience. This module never changes canonical claims.
"""

from __future__ import annotations
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

VALIDATED_STATUSES = {"validated", "confirmed"}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def observation_key(event: Dict[str, Any]) -> str:
    return "|".join([
        _norm(event.get("event_type")),
        _norm(event.get("entity_type")),
        _norm(event.get("entity_key")),
        _norm(event.get("property")),
        _norm(event.get("new_value")),
    ])


def _context_key(event: Dict[str, Any]) -> str:
    ctx = event.get("context") or {}
    if not isinstance(ctx, dict):
        ctx = {}
    return "|".join([
        _norm(ctx.get("game_version")),
        _norm(ctx.get("season")),
        _norm(ctx.get("server")),
        _norm(ctx.get("energy_type")),
        _norm(ctx.get("mode")),
    ])


def build_candidates(events: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups = defaultdict(list)
    for event in events:
        if str(event.get("validation_status", "candidate")).lower() in {"rejected", "superseded"}:
            continue
        groups[(observation_key(event), _context_key(event))].append(event)

    out = []
    now = datetime.now(timezone.utc).isoformat()
    for (key, context_key), rows in groups.items():
        successes = sum(
            1 for x in rows
            if str((x.get("outcome") or {}).get("result", "")).lower()
            in {"success", "victory", "won", "positive"}
        )
        failures = sum(
            1 for x in rows
            if str((x.get("outcome") or {}).get("result", "")).lower()
            in {"failure", "loss", "lost", "negative"}
        )
        confidence = min(0.99, 0.50 + 0.08 * min(len(rows), 6))
        if successes and failures:
            confidence -= 0.12
        status = "validated" if len(rows) >= 5 and not failures else "under_review"
        pattern = str(rows[-1].get("pattern") or "").strip()
        if not pattern:
            pattern = (
                f"{rows[-1].get('event_type', 'Observed event')} for "
                f"{rows[-1].get('entity_key', 'unknown entity')} produced "
                f"{rows[-1].get('new_value', 'an observed state')}."
            )
        out.append({
            "pattern_key": key, "context_key": context_key,
            "pattern": pattern, "observations": len(rows),
            "successes": successes, "failures": failures,
            "confidence": round(confidence, 3), "status": status,
            "first_seen": rows[0].get("observed_at") or now,
            "last_seen": rows[-1].get("observed_at") or now,
            "provenance": [{
                "event_id": x.get("id"),
                "observed_at": x.get("observed_at"),
                "session_id": x.get("session_id"),
            } for x in rows[-20:]],
        })
    return out


class InMemoryExperienceStore:
    def __init__(self, candidates: Optional[List[Dict[str, Any]]] = None):
        self.events = []
        self.candidates = []
        for item in candidates or []:
            if item.get("pattern_key") is not None or (
                item.get("status") in VALIDATED_STATUSES and item.get("pattern")
            ):
                self.candidates.append(item)
            else:
                self.events.append(item)

    def ingest(self, event: Dict[str, Any]) -> Dict[str, Any]:
        self.events.append(event)
        self.candidates = build_candidates(self.events)
        return event

    def rebuild(self) -> List[Dict[str, Any]]:
        self.candidates = build_candidates(self.events)
        return self.candidates

    def find_relevant(self, question, player_context=None, limit=4, validated_only=True):
        q = _norm(question)
        q_tokens = set(q.split())
        ctx = player_context or {}
        scored = []
        for item in self.candidates:
            if validated_only and item.get("status") not in VALIDATED_STATUSES:
                continue
            blob = _norm(item.get("pattern"))
            overlap = len(q_tokens & set(blob.split()))
            item_ctx = _norm(item.get("context_key"))
            context_overlap = sum(
                1 for k in ("season", "game_version", "energy_type", "mode")
                if _norm(ctx.get(k)) and _norm(ctx.get(k)) in item_ctx
            )
            score = overlap + 2 * context_overlap + float(item.get("confidence", 0))
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [x[1] for x in scored[:limit]]
