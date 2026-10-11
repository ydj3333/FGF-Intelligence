"""Evidence-backed visual payloads for Ask FGF.

This module emits structured facts only. The browser renders the payload as SVG;
it does not ask an image model to invent or redraw game mechanics.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).parent
GUIDES_PATH = ROOT / "data" / "verified_guides.json"


def _guide(key: str = "server_migration") -> Dict[str, Any]:
    try:
        data = json.loads(GUIDES_PATH.read_text(encoding="utf-8"))
        return next((g for g in data.get("guides", []) if g.get("key") == key), {})
    except (OSError, ValueError, TypeError):
        return {}


def _is_migration_question(question: str) -> bool:
    q = str(question or "").lower()
    return any(term in q for term in (
        "migration", "migrate", "migrating", "new server", "target server"
    ))


def _is_numeric_question(question: str) -> bool:
    q = str(question or "").lower()
    return any(term in q for term in ("how many", "how much", "how long", "what number", "how often"))


def build_visual_answer(question: str, answer: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Return a deterministic, source-linked visual description when it helps."""
    q = str(question or "").strip()
    if not q:
        return None

    if _is_migration_question(q):
        guide = _guide()
        claims = [str(x).strip() for x in guide.get("claims", []) if str(x).strip()]
        if not claims:
            return None

        permits_claim = next((x for x in claims if "10 migration permits" in x.lower()), None)
        # Only show the fixed permit count when the user actually asks
        # about permits. A migration-cost or cooldown question must not be
        # answered with the unrelated number 10.
        is_count = _is_numeric_question(q) and "permit" in q.lower()
        if is_count:
            return {
                "kind": "number_card",
                "title": "SERVER MIGRATION",
                "headline": "10",
                "unit": "Migration Permits",
                "summary": permits_claim or "Server migration requires 10 Migration Permits.",
                "items": [
                    "Confirm that your destination server is eligible.",
                    "Check the current event window and destination quota."
                ],
                "warnings": [
                    "The 25-day cooldown shown in the older infographic is not verified by the cited guide."
                ],
                "source": guide.get("source", ""),
                "source_title": guide.get("source_title", ""),
                "source_published": guide.get("source_published", ""),
                "evidence_basis": "Curated guide claims loaded into the production answer corpus."
            }

        return {
            "kind": "checklist",
            "title": "SERVER MIGRATION 101",
            "subtitle": "Evidence-backed checklist",
            "headline": "10 Migration Permits",
            "steps": [
                {"number": "01", "title": "Prepare", "detail": "Choose an eligible destination and check the migration group and available quota."},
                {"number": "02", "title": "Apply", "detail": "Submit your application before migration day and follow the event instructions."},
                {"number": "03", "title": "Meet requirements", "detail": "Dock/idle Flagships, leave your current Commerce Guild, and ensure you have no character on the target server."},
                {"number": "04", "title": "Confirm transfer", "detail": "Actively confirm migration on the designated migration day."},
                {"number": "05", "title": "Settle in", "detail": "Review your Home Port, rankings, mail and pending trade orders after transfer."}
            ],
            "requirements": [
                "10 Migration Permits are required.",
                "Step down from Trader Prince and other official titles as required; royal titles do not carry over.",
                "Eligibility and destination slots vary by event group, server strength and historical peak power."
            ],
            "warnings": [
                "The 25-day cooldown shown in the older infographic is not verified by the cited guide.",
                "Migration effects, eligibility and quotas can vary by event wave. Check the current in-game notice."
            ],
            "source": guide.get("source", ""),
            "source_title": guide.get("source_title", ""),
            "source_published": guide.get("source_published", ""),
            "evidence_basis": "Curated guide claims loaded into the production answer corpus."
        }

    explicit_visual = any(term in q.lower() for term in (
        "visual", "diagram", "infographic", "draw", "image", "chart", "show me"
    ))
    if not explicit_visual and not _is_numeric_question(q):
        return None

    evidence = answer.get("evidence") or []
    claims: List[str] = []
    for row in evidence:
        if not isinstance(row, dict):
            continue
        text = str(row.get("Claim", row.get("claim", "")) or "").strip()
        if text and text not in claims:
            claims.append(text)
        if len(claims) >= 4:
            break
    if not claims:
        return None

    return {
        "kind": "fact_summary",
        "title": "FGF EVIDENCE SNAPSHOT",
        "headline": claims[0],
        "items": claims[1:4],
        "warnings": [str(answer.get("uncertainty", "")).strip()] if answer.get("uncertainty") else [],
        "source": "",
        "source_title": "Claims retrieved for this answer",
        "evidence_basis": "Only the retrieved evidence text is displayed; no additional game mechanics are inferred."
    }
