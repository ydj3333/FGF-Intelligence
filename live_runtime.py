"""Runtime bridge for FGF v6.3 live observation and experience.

The local observer talks to these API operations. The runtime validates input,
persists structured events, and exposes only validated experience to the
orchestrator. It never writes canonical claims.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen

from experience_engine import build_candidates
from observation_contract import validate_observation


DAILY_LIMIT_SECONDS = 7200
MAX_SESSION_SECONDS = 7200


class LiveObservationRuntime:
    def __init__(self, supabase_url: str, secret: Optional[str]):
        self.supabase_url = (supabase_url or "").rstrip("/")
        self.secret = secret
        self.local_sessions: Dict[str, Dict[str, Any]] = {}
        self.local_events: List[Dict[str, Any]] = []
        self.local_candidates: List[Dict[str, Any]] = []

    def _headers(self, prefer: Optional[str] = None):
        if not self.secret:
            return None
        h = {
            "apikey": self.secret,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        # Modern sb_secret_* and sb_publishable_* keys are opaque API keys.
        # Legacy service_role JWTs still need the Bearer authorization header.
        if not self.secret.startswith("sb_"):
            h["Authorization"] = "Bearer " + self.secret
        if prefer:
            h["Prefer"] = prefer
        return h

    def _request(self, path: str, method="GET", payload=None, prefer=None):
        headers = self._headers(prefer)
        if not headers:
            return None, "server credential not configured"
        data = None
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = Request(
            self.supabase_url + path,
            data=data,
            headers=headers,
            method=method,
        )
        with urlopen(req, timeout=5) as response:
            raw = response.read().decode("utf-8") or "[]"
            return json.loads(raw), None

    def status(self):
        return {
            "ok": True,
            "version": "6.3.0",
            "daily_limit_seconds": DAILY_LIMIT_SECONDS,
            "raw_video_upload": False,
            "supabase_configured": bool(self._headers()),
            "local_active_sessions": len(self.local_sessions),
            "local_event_buffer": len(self.local_events),
        }

    def start_session(self, body: Dict[str, Any]):
        player_id = str(body.get("player_id", "")).strip()
        observer_version = str(body.get("observer_version", "unknown")).strip()[:64]
        if not observer_version:
            return {"ok": False, "error": "observer_version is required"}

        metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
        session_id = str(body.get("session_id", "")).strip()

        if not session_id:
            # Server-side UUID generation through Supabase is preferred.
            session_id = self._new_session_id(player_id)

        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": session_id,
            "player_id": player_id[:128],
            "started_at": now,
            "observer_version": observer_version,
            "status": "active",
            "metadata": metadata,
        }

        if self._headers():
            try:
                rows, err = self._request(
                    "/rest/v1/observation_sessions",
                    "POST",
                    record,
                    "return=representation",
                )
                if err:
                    raise RuntimeError(err)
                if rows:
                    record.update(rows[0])
            except Exception as exc:
                # Keep the live observer usable during temporary DB outages.
                record["storage_warning"] = str(exc)[:160]

        self.local_sessions[session_id] = record
        return {
            "ok": True,
            "session": record,
            "daily_limit_seconds": DAILY_LIMIT_SECONDS,
        }

    def stop_session(self, body: Dict[str, Any]):
        session_id = str(body.get("session_id", "")).strip()
        if not session_id:
            return {"ok": False, "error": "session_id is required"}

        started = self.local_sessions.get(session_id, {}).get("started_at")
        ended = datetime.now(timezone.utc)
        duration = 0
        if started:
            try:
                duration = max(
                    0,
                    int(
                        (
                            ended
                            - datetime.fromisoformat(
                                str(started).replace("Z", "+00:00")
                            )
                        ).total_seconds()
                    ),
                )
            except Exception:
                duration = 0

        duration = min(duration, MAX_SESSION_SECONDS)
        payload = {
            "ended_at": ended.isoformat(),
            "duration_seconds": duration,
            "status": "completed",
        }

        if self._headers():
            try:
                self._request(
                    "/rest/v1/observation_sessions?id=eq." + quote(session_id, safe=""),
                    "PATCH",
                    payload,
                    "return=minimal",
                )
            except Exception:
                pass

        record = self.local_sessions.get(session_id, {"id": session_id})
        record.update(payload)
        self.local_sessions.pop(session_id, None)
        return {"ok": True, "session": record}

    def ingest_observation(self, body: Dict[str, Any]):
        ok, reason, event = validate_observation(body)
        if not ok:
            return {"ok": False, "error": reason}

        event["validation_status"] = "candidate"
        self.local_events.append(event)

        durable = False
        if self._headers():
            payload = dict(event)
            try:
                rows, err = self._request(
                    "/rest/v1/observation_events",
                    "POST",
                    payload,
                    "return=representation",
                )
                if err:
                    raise RuntimeError(err)
                durable = bool(rows is not None)
                if rows:
                    event.update(rows[0])
            except Exception as exc:
                event["storage_warning"] = str(exc)[:160]

        # Rebuild the bounded in-memory experience view immediately. The
        # durable candidate table is updated by rebuild_experience().
        self.local_candidates = build_candidates(self.local_events)

        return {
            "ok": True,
            "durable": durable,
            "event": event,
            "experience_candidates": len(self.local_candidates),
        }

    def rebuild_experience(self):
        events = list(self.local_events)

        if self._headers():
            try:
                rows, err = self._request(
                    "/rest/v1/observation_events"
                    "?select=id,session_id,observed_at,event_type,entity_type,entity_key,"
                    "property,old_value,new_value,context,outcome,confidence,pattern,"
                    "validation_status"
                    "&validation_status=neq.rejected"
                    "&order=observed_at.asc"
                    "&limit=5000"
                )
                if not err and rows:
                    events = rows
            except Exception:
                pass

        candidates = build_candidates(events)
        self.local_candidates = candidates

        durable = 0
        for item in candidates:
            if not self._headers():
                continue
            payload = {
                "pattern_key": item["pattern_key"],
                "context_key": item["context_key"],
                "pattern": item["pattern"],
                "observations": item["observations"],
                "successes": item["successes"],
                "failures": item["failures"],
                "confidence": item["confidence"],
                "status": item["status"],
                "first_seen": item["first_seen"],
                "last_seen": item["last_seen"],
                "provenance": item["provenance"],
                "context": {},
            }
            try:
                self._request(
                    "/rest/v1/experience_candidates",
                    "POST",
                    payload,
                    "resolution=merge-duplicates,return=minimal",
                )
                durable += 1
            except Exception:
                pass

        return {"ok": True, "candidates": len(candidates), "durable": durable}

    def find_relevant(
        self,
        question: str,
        player_context: Optional[Dict[str, Any]] = None,
        limit: int = 4,
        validated_only: bool = True,
    ):
        candidates = list(self.local_candidates)

        if self._headers():
            try:
                status_filter = "validated" if validated_only else "not.is.null"
                rows, err = self._request(
                    "/rest/v1/experience_candidates"
                    "?select=pattern_key,context_key,pattern,observations,successes,"
                    "failures,confidence,status,first_seen,last_seen,provenance,context"
                    "&status=eq." + quote(status_filter, safe="")
                    + "&order=confidence.desc&limit=100"
                )
                if not err and rows is not None:
                    candidates = rows
            except Exception:
                pass

        q_tokens = set(re.findall(r"[a-z0-9]+", str(question).lower()))
        ctx = player_context or {}
        scored = []
        for item in candidates:
            if validated_only and item.get("status") not in {"validated", "confirmed"}:
                continue
            blob = str(item.get("pattern", "")).lower()
            overlap = len(q_tokens & set(re.findall(r"[a-z0-9]+", blob)))
            item_ctx = json.dumps(item.get("context", {}), ensure_ascii=False).lower()
            item_ctx += " " + str(item.get("context_key", "")).lower()
            context_overlap = sum(
                1 for key in ("season", "game_version", "energy_type", "mode")
                if str(ctx.get(key, "")).lower()
                and str(ctx.get(key, "")).lower() in item_ctx
            )
            score = overlap + 2 * context_overlap + float(item.get("confidence") or 0)
            if score > 0:
                scored.append((score, item))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:max(1, min(10, limit))]]

    def record_feedback(self, body: Dict[str, Any]):
        question = str(body.get("question", "")).strip()
        feedback_type = str(body.get("feedback_type", "")).strip().lower()
        if not question:
            return {"ok": False, "error": "question is required"}
        if feedback_type not in {"correct", "needs_improvement"}:
            return {"ok": False, "error": "feedback_type must be correct or needs_improvement"}

        notes = str(body.get("notes", "")).strip()[:2000]
        answer = str(body.get("answer", ""))
        fingerprint = hashlib.sha256(answer.encode("utf-8")).hexdigest()[:32]
        payload = {
            "question": question[:4000],
            "answer_fingerprint": fingerprint,
            "feedback_type": feedback_type,
            "notes": notes,
            "metadata": body.get("metadata") if isinstance(body.get("metadata"), dict) else {},
        }

        durable = False
        if self._headers():
            try:
                rows, err = self._request(
                    "/rest/v1/agent_feedback",
                    "POST",
                    payload,
                    "return=representation",
                )
                durable = not bool(err)
            except Exception:
                pass

        return {"ok": True, "durable": durable, "feedback": payload}

    def _new_session_id(self, player_id: str) -> str:
        # UUID generation without adding another dependency.
        import uuid
        return str(uuid.uuid4())
