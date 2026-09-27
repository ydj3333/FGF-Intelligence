"""FGF v6.3 live observation contract.

The local observer sends structured events, not arbitrary text. The server
validates the event before it can enter the experiential store.
"""

from __future__ import annotations
import math
import re
from typing import Any, Dict, Tuple

ALLOWED_EVENT_TYPES = {
    "screen_changed","menu_opened","entity_selected","resource_changed",
    "level_changed","upgrade_started","upgrade_completed","battle_started",
    "battle_ended","action","reward_received","tech_unlocked",
    "building_upgraded","fleet_changed","timer_changed","unknown"
}
MAX_STRING = 512


def _clean(value, max_len=MAX_STRING):
    value = str(value or "").strip()
    value = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", value)
    return value[:max_len]


def validate_observation(event: Dict[str, Any]) -> Tuple[bool, str, Dict[str, Any]]:
    if not isinstance(event, dict):
        return False, "event must be an object", {}
    event_type = _clean(event.get("event_type"), 64)
    if event_type not in ALLOWED_EVENT_TYPES:
        return False, "unsupported event_type", {}
    observed_at = _clean(event.get("observed_at"), 64)
    session_id = _clean(event.get("session_id"), 128)
    if not observed_at:
        return False, "observed_at is required", {}
    if not session_id:
        return False, "session_id is required", {}

    confidence = None
    try:
        n = float(event.get("confidence"))
        if math.isfinite(n):
            confidence = max(0.0, min(1.0, n))
    except (TypeError, ValueError):
        pass

    raw_context = event.get("context") if isinstance(event.get("context"), dict) else {}
    context = {}
    for key in ("game_version","season","server","energy_type","mode","screen","player_id","session_tag"):
        if key in raw_context:
            context[key] = _clean(raw_context[key], 128)

    return True, "", {
        "session_id": session_id,
        "event_type": event_type,
        "entity_type": _clean(event.get("entity_type"), 64),
        "entity_key": _clean(event.get("entity_key"), 256),
        "property": _clean(event.get("property"), 128),
        "old_value": event.get("old_value"),
        "new_value": event.get("new_value"),
        "context": context,
        "outcome": event.get("outcome") if isinstance(event.get("outcome"), dict) else {},
        "observed_at": observed_at,
        "confidence": confidence,
        "source_capture": _clean(event.get("source_capture"), 256),
        "pattern": _clean(event.get("pattern"), 512),
    }
