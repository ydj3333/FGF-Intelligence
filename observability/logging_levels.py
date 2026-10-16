"""Structured L0-L6 runtime observability for FGF Intelligence.

Logs are JSON Lines on stdout so Render/container log collection can ingest them.
Never log credentials, request bodies, raw screenshots, or full player-private data.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
import uuid
from contextvars import ContextVar, Token
from datetime import datetime, timezone
from typing import Any

_LEVELS = {
    "L0": "project",
    "L1": "observation",
    "L2": "evidence",
    "L3": "learning",
    "L4": "reasoning",
    "L5": "evaluation",
    "L6": "operations",
}
_ALLOWED = set(_LEVELS)
_correlation_context: ContextVar[str | None] = ContextVar("fgf_log_correlation_id", default=None)
_logger = logging.getLogger("fgf.runtime")
_logger.setLevel(logging.INFO)
_logger.propagate = False
if not _logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    _logger.addHandler(handler)


def emit(level: str, event: str, *, status: str = "ok", correlation_id: str | None = None,
         duration_ms: float | None = None, **fields: Any) -> dict[str, Any]:
    """Emit one redacted, structured event and return the record for tests."""
    code = str(level).upper()
    if code not in _ALLOWED:
        raise ValueError(f"Unsupported FGF logging level: {level}")
    record: dict[str, Any] = {
        "schema": "fgf.logging.v1",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": code,
        "category": _LEVELS[code],
        "event": str(event)[:160],
        "status": str(status)[:32],
        "service": os.getenv("RENDER_SERVICE_NAME", "fgf-intelligence"),
        "release": os.getenv("RENDER_GIT_COMMIT", os.getenv("FGF_RELEASE", "unknown")),
        "correlation_id": correlation_id or _correlation_context.get() or str(uuid.uuid4()),
    }
    if duration_ms is not None:
        record["duration_ms"] = round(max(0.0, float(duration_ms)), 3)
    # Only scalar and bounded JSON-compatible metadata is accepted. Secret-like
    # field names are always redacted; payloads and free-form bodies are omitted.
    safe: dict[str, Any] = {}
    for key, value in fields.items():
        k = str(key)[:64]
        if any(term in k.lower() for term in ("token", "secret", "password", "authorization", "api_key", "request_body", "screenshot", "raw_video")):
            safe[k] = "[REDACTED]"
            continue
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[k] = value[:500] if isinstance(value, str) else value
        elif isinstance(value, (list, tuple)):
            safe[k] = [str(item)[:120] for item in value[:20]]
        elif isinstance(value, dict):
            safe[k] = {"keys": sorted(str(x)[:64] for x in list(value.keys())[:30])}
        else:
            safe[k] = type(value).__name__
    record.update(safe)
    _logger.info(json.dumps(record, ensure_ascii=False, separators=(",", ":"), default=str))
    return record


def timed_event(level: str, event: str, **fields: Any):
    """Context manager for duration-aware stage logging."""
    from contextlib import contextmanager

    @contextmanager
    def _timer():
        started = time.perf_counter()
        correlation_id = str(fields.pop("correlation_id", None) or uuid.uuid4())
        try:
            yield correlation_id
        except Exception as exc:
            emit(level, event, status="error", correlation_id=correlation_id,
                 duration_ms=(time.perf_counter() - started) * 1000,
                 error_type=type(exc).__name__, **fields)
            raise
        else:
            emit(level, event, status="ok", correlation_id=correlation_id,
                 duration_ms=(time.perf_counter() - started) * 1000, **fields)
    return _timer()


def set_correlation_id(correlation_id: str) -> Token:
    """Bind a request correlation ID for all events in the current execution context."""
    return _correlation_context.set(str(correlation_id))


def reset_correlation_id(token: Token) -> None:
    """Restore the previous request correlation context."""
    _correlation_context.reset(token)


def level_catalog() -> dict[str, str]:
    """Return a copy of the canonical logging-level registry."""
    return dict(_LEVELS)
