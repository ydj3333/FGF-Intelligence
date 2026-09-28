"""Evidence-safe YouTube/community retrieval for FGF v6.5.

This module is deliberately a fallback/enrichment provider:
- never promotes video claims to canonical truth;
- searches both extracted candidate claims and indexed video metadata;
- resolves event aliases before lexical matching;
- preserves original video URL and provenance;
- filters rejected/superseded candidates;
- requires meaningful entity/topic overlap before returning a hit;
- caches the small indexed corpus briefly to avoid repeated database scans.
"""

from __future__ import annotations

import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen


EVENT_ALIASES = {
    "kaboom robot": {
        "kaboom robot", "kaboom robots", "kaboom, robots", "kaboom",
        "kaboom robot event", "kaboom event",
    },
    "gvg": {"gvg", "guild vs guild", "guild versus guild", "guild war"},
    "top 100 galactic traders": {
        "top 100 galactic traders", "galactic traders", "top 100 traders",
    },
    "shared moonlight": {
        "shared moonlight", "moonlight", "lunar ruins", "moonsoil",
    },
}

# Terms that materially identify FGF rather than generic gaming videos.
FGF_ANCHORS = {
    "foundation galactic frontier", "fgf", "kaboom robot", "kaboom robots",
    "intel shop", "weapon prism", "computational components",
    "deep space beacons", "energy core", "commerce guild",
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _tokens(value: Any) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", _norm(value)))


def _contains_alias(text: str, aliases: set[str]) -> bool:
    return any(alias in text for alias in aliases)


def _key() -> str:
    return (
        os.getenv("FGF_SUPABASE_SECRET_KEY")
        or os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY")
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
        or ""
    ).strip()


def _headers(key: str) -> Dict[str, str]:
    h = {"apikey": key, "Accept": "application/json"}
    # Modern Supabase sb_* keys are opaque API keys. Legacy service_role
    # JWTs still need the Authorization header.
    if not key.startswith("sb_"):
        h["Authorization"] = "Bearer " + key
    return h


class YouTubeEvidenceProvider:
    """Search the indexed YouTube candidate corpus without promoting it."""

    def __init__(self, supabase_url: Optional[str] = None, ttl_seconds: int = 60):
        self.base = (
            supabase_url
            or os.getenv(
                "FGF_SUPABASE_URL",
                "https://qdoixzfkkmvzjfkhzups.supabase.co",
            )
        ).rstrip("/")
        self.ttl_seconds = max(10, int(ttl_seconds))
        self._cache: Optional[tuple[float, List[Dict[str, Any]], List[Dict[str, Any]]]] = None

    def _get(self, path: str) -> List[Dict[str, Any]]:
        key = _key()
        if not key:
            return []
        req = Request(self.base + path, headers=_headers(key), method="GET")
        try:
            with urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8") or "[]")
            return data if isinstance(data, list) else []
        except Exception:
            # Fallback evidence must fail closed.
            return []

    def _load(self) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        now = time.time()
        if self._cache and now - self._cache[0] < self.ttl_seconds:
            return self._cache[1], self._cache[2]

        candidates = self._get(
            "/rest/v1/video_claim_candidates"
            "?select=id,video_database_id,video_id,claim_text,category,claim_type,"
            "evidence_tier,confidence,status,source_url,evidence_excerpt,metadata"
            "&limit=1000"
        )
        videos = self._get(
            "/rest/v1/video_database"
            "?select=id,video_id,title,video_url,description,published_at,"
            "channel_title,processing_status,metadata"
            "&limit=500"
        )
        self._cache = (now, candidates, videos)
        return candidates, videos

    @staticmethod
    def _status_allowed(row: Dict[str, Any]) -> bool:
        status = _norm(row.get("status") or row.get("processing_status"))
        return status not in {"rejected", "superseded", "invalid"}

    def _topic(self, question: str) -> tuple[Optional[str], set[str]]:
        q = _norm(question)
        # Longest alias first prevents generic "moonlight" from winning over
        # the more specific event name.
        matches = []
        for event, aliases in EVENT_ALIASES.items():
            for alias in aliases:
                if alias in q:
                    matches.append((len(alias), event, aliases))
        if matches:
            _, event, aliases = max(matches, key=lambda x: x[0])
            return event, aliases
        return None, set()

    def _score(
        self,
        question: str,
        event: Optional[str],
        aliases: set[str],
        candidate: Dict[str, Any],
        video: Dict[str, Any],
    ) -> float:
        claim = _norm(candidate.get("claim_text"))
        title = _norm(video.get("title"))
        desc = _norm(video.get("description"))
        excerpt = _norm(candidate.get("evidence_excerpt"))
        blob = " ".join((claim, title, desc, excerpt))

        score = 0.0
        if event and _contains_alias(blob, aliases):
            score += 8.0
        if event and event in claim:
            score += 2.0

        q_tokens = _tokens(question) - {
            "what", "when", "where", "how", "does", "do", "is", "are",
            "the", "a", "an", "to", "of", "for", "and", "or", "i", "my",
            "best", "good", "combo", "team", "lineup", "strategy", "event",
        }
        blob_tokens = _tokens(blob)
        score += min(4.0, len(q_tokens & blob_tokens) * 0.8)

        # Strong FGF anchors reduce accidental matches from unrelated YouTube
        # material. They do not prove the claim; they only establish relevance.
        anchors = sum(1 for x in FGF_ANCHORS if x in blob)
        score += min(2.0, anchors * 0.5)

        # Candidate confidence is enrichment metadata, never canonical truth.
        try:
            conf = float(candidate.get("confidence"))
            score += max(0.0, min(1.0, conf))
        except (TypeError, ValueError):
            pass

        return score

    def find_relevant(
        self,
        question: str,
        player_context: Optional[Dict[str, Any]] = None,
        limit: int = 4,
    ) -> List[Dict[str, Any]]:
        event, aliases = self._topic(question)
        candidates, videos = self._load()
        if not candidates or not videos:
            return []

        videos_by_id = {str(v.get("id")): v for v in videos}
        videos_by_video_id = {str(v.get("video_id")): v for v in videos if v.get("video_id")}

        ranked = []
        for c in candidates:
            if not self._status_allowed(c):
                continue
            video = videos_by_id.get(str(c.get("video_database_id"))) or videos_by_video_id.get(
                str(c.get("video_id"))
            )
            if not video:
                continue
            if not self._status_allowed(video):
                continue

            score = self._score(question, event, aliases, c, video)
            # Event-specific fallback requires a direct event match. Generic
            # YouTube material must never leak into an event answer.
            if event and not _contains_alias(
                " ".join(
                    _norm(x)
                    for x in (
                        c.get("claim_text"),
                        c.get("evidence_excerpt"),
                        video.get("title"),
                        video.get("description"),
                    )
                ),
                aliases,
            ):
                continue
            if score < 8.0:
                continue
            ranked.append((score, c, video))

        ranked.sort(key=lambda x: x[0], reverse=True)

        out = []
        seen = set()
        for score, c, v in ranked:
            key = (str(c.get("video_id")), _norm(c.get("claim_text")))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                {
                    "claim": c.get("claim_text", ""),
                    "summary": c.get("claim_text", ""),
                    "source": "YouTube/community candidate evidence",
                    "source_type": "youtube_candidate",
                    "video_id": v.get("video_id") or c.get("video_id"),
                    "video_title": v.get("title", ""),
                    "video_url": c.get("source_url") or v.get("video_url"),
                    "evidence_excerpt": c.get("evidence_excerpt", ""),
                    "candidate_status": c.get("status", "candidate"),
                    "candidate_confidence": c.get("confidence"),
                    "evidence_tier": c.get("evidence_tier", 3),
                    "retrieval_score": round(score, 3),
                    "event_match": event,
                    "context": player_context or {},
                    "provenance": {
                        "table": "video_claim_candidates",
                        "video_table": "video_database",
                        "canonical_promotion": False,
                    },
                }
            )
            if len(out) >= max(1, min(8, int(limit))):
                break
        return out
