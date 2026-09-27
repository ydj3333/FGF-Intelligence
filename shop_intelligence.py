"""FGF v6.3 shop intelligence layer.

Separates:
- shop identity and documented mechanics,
- evidence authority,
- strategic interpretation,
- unknown/live-rotation fields.

It intentionally does not treat YouTube transcript fragments as canonical facts.
"""
from __future__ import annotations
import json
from pathlib import Path

ROOT = Path(__file__).parent
SHOP_DATA = json.loads((ROOT / "data" / "shop_intelligence.json").read_text(encoding="utf-8"))

_PRIORITY_ORDER = {
    "P1": 1,
    "P1_event": 2,
    "P1_event_when_limited": 3,
    "P2": 4,
    "P2_event": 5,
}

def _norm(text: str) -> str:
    return " ".join(str(text or "").lower().split())

def all_shops():
    return list(SHOP_DATA["shops"])

def find_shops(query: str):
    q = _norm(query)
    hits = []
    for shop in SHOP_DATA["shops"]:
        terms = [shop["name"], *shop.get("aliases", [])]
        if any(_norm(term) in q for term in terms):
            hits.append(shop)
    return hits

def ranked_shops():
    return sorted(
        SHOP_DATA["shops"],
        key=lambda x: (_PRIORITY_ORDER.get(x.get("strategic_priority"), 99), x["name"])
    )

def strategy_summary(shop):
    return {
        "shop": shop["name"],
        "priority": shop.get("strategic_priority"),
        "currency": shop.get("currency"),
        "documented_inventory": shop.get("documented_inventory", []),
        "evidence_level": shop.get("evidence_level"),
        "reason": shop.get("priority_reason"),
        "strategy_status": shop.get("strategy_status"),
    }

def answer_shop_question(question: str, claims):
    q = _norm(question)
    if not any(x in q for x in ("shop", "store", "merchant", "market")):
        return None

    # "best resources to buy and in which shops" is a strategy request.
    # Return an interpretation assembled from structured shop knowledge,
    # then attach claim-level evidence where possible.
    if any(x in q for x in ("best", "priority", "prioritize", "buy", "spend", "worth")):
        ranked = ranked_shops()
        lines = [
            "I would treat this as a shop-priority strategy question, not a simple transcript lookup.",
            "Current evidence supports the following working priority map:"
        ]
        for shop in ranked[:8]:
            inv = ", ".join(shop.get("documented_inventory", [])) or "inventory not yet canonicalized"
            lines.append(
                f"{shop['name']} — {shop.get('strategic_priority')}: {inv}. "
                f"{shop.get('priority_reason')}"
            )
        lines.append(
            "Important: P1/P2 labels are strategic interpretations of the current corpus, not official in-game rankings. "
            "Community/YouTube claims remain visibly community evidence."
        )
        evidence = []
        qterms = set(q.replace("?", "").split())
        for c in claims:
            text = _norm(c.get("Claim", c.get("claim", "")))
            if any(shop_term in text for shop in SHOP_DATA["shops"] for shop_term in [_norm(shop["name"]), *map(_norm, shop.get("aliases", []))]):
                overlap = len(qterms & set(text.split()))
                if overlap or any(x in text for x in ("weapon prism", "speedup", "crystal", "flagship component", "guild voucher", "moonsoil")):
                    evidence.append(c)
        evidence.sort(key=lambda c: (
            0 if "Tier 1" in str(c.get("Evidence Tier", c.get("tier", ""))) else
            1 if "Tier 2" in str(c.get("Evidence Tier", c.get("tier", ""))) else 2
        ))
        return {"text": " ".join(lines), "claims": evidence[:4], "mode": "shop_strategy"}

    # General shop inventory/identity request.
    lines = ["Known shop systems in the current FGF corpus:"]
    for shop in ranked_shops():
        inv = ", ".join(shop.get("documented_inventory", [])) or "not yet established"
        lines.append(f"{shop['name']} — {inv}; currency: {shop.get('currency')}.")
    lines.append("This is the current known corpus, not a guarantee that every live shop has been captured.")
    return {"text": " ".join(lines), "claims": [], "mode": "shop_catalog"}
