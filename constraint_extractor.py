"""Generic natural-language constraint extraction for FGF v7.

Conservative by design: explicit user statements become hard constraints;
unstated player state is never invented.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Tuple
import re


ALIASES = {
    "zora": "Zora Dominii",
    "zora dominii": "Zora Dominii",
    "lily": "Lily",
    "jodie": "Jodie Beart",
    "jodie beart": "Jodie Beart",
    "kama": "Kama Moai",
    "kameni": "Kama Moai",
    "kama moai": "Kama Moai",
    "evan": "Evan Rogers",
    "evan rogers": "Evan Rogers",
}


@dataclass(frozen=True)
class ExtractedConstraints:
    owned_entities: Tuple[str, ...] = ()
    unavailable_entities: Tuple[str, ...] = ()
    requested_count: int | None = None
    requested_positions: bool = False
    optimization_goal: str | None = None
    role: str | None = None
    explicit_time_limit: str | None = None
    resource_limit: str | None = None
    fleet_tier: str | None = None
    confidence: str = "low"
    unresolved_phrases: Tuple[str, ...] = ()


def _has(q: str, patterns: tuple[str, ...]) -> bool:
    return any(re.search(p, q, re.I) for p in patterns)


def extract_constraints(question: str) -> ExtractedConstraints:
    q = question.lower()
    owned: List[str] = []
    unavailable: List[str] = []
    unresolved: List[str] = []

    # Explicit ownership language is required. Mentioning a Champion alone
    # must not imply ownership.
    ownership_context = _has(q, (
        r"(i|we)s+(have|own|got|use|can use)",
        r"mys+(champions?|roster|team)",
        r"availables+(champions?|heroes?)",
    ))
    if ownership_context:
        for alias, canonical in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
            if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", q):
                if canonical not in owned:
                    owned.append(canonical)

    # Explicit exclusions are hard constraints.
    for alias, canonical in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
        if re.search(r"(?:don't|do not|dont|without|not have|not owned|missing)[^.!?]{0,35}" + re.escape(alias) + r"", q):
            if canonical not in unavailable:
                unavailable.append(canonical)
            if canonical in owned:
                owned.remove(canonical)

    m = re.search(r"(?:give me|need|want|show me|provide)s+(d+|five|three|four|two|one)", q)
    if m:
        requested_count = {"one":1,"two":2,"three":3,"four":4,"five":5}.get(m.group(1), int(m.group(1)) if m.group(1).isdigit() else None)
    else:
        requested_count = None

    requested_positions = _has(q, (r"(order|position|slot|lineup order|formation order)",))

    if _has(q, (r"maximize.*(points?|score|damage|kills?)", r"maximum.*(points?|score|damage|kills?)")):
        optimization_goal = "maximize requested event metric"
    elif _has(q, (r"best|optimal|most efficient")):
        optimization_goal = "best feasible outcome"

    role = None
    for name, patterns in {
        "attacker": (r"attack(?:ing)?", r"offensive"),
        "defender": (r"defend(?:ing)?", r"defensive"),
        "rally": (r"rally",),
    }.items():
        if _has(q, patterns):
            role = name
            break

    tm = re.search(r"(d+)s*(?:min|mins|minutes|hr|hrs|hours)", q)
    explicit_time_limit = tm.group(0) if tm else None

    rm = re.search(r"(?:under|within|limit(?:ed)? to|max(?:imum)?(?: of)?)s*([0-9,.]+)s*(credits?|points?|resources?|m|k)?", q)
    resource_limit = rm.group(0) if rm else None

    # FGF player-state terminology: T1–T5 are fleet progression tiers in this project.
    # Treat an explicit T1..T5 token as player state; never silently discard it.
    fleet_tier = None
    tm_tier = re.search(r"(?<![a-z0-9])(?:fleet\\s*(?:tier|level)?\\s*)?t([1-5])(?![a-z0-9])", q, re.I)
    if tm_tier:
        fleet_tier = "T" + tm_tier.group(1)

    if ownership_context and not owned:
        unresolved.append("Ownership was stated, but no recognized Champion name was found.")
    if _has(q, (r"best", r"optimal")) and not (owned or unavailable):
        unresolved.append("No player roster constraint was explicitly supplied.")

    confidence = "high" if (owned or unavailable or requested_count or requested_positions or optimization_goal or role or fleet_tier) else "low"

    return ExtractedConstraints(
        owned_entities=tuple(owned),
        unavailable_entities=tuple(unavailable),
        requested_count=requested_count,
        requested_positions=requested_positions,
        optimization_goal=optimization_goal,
        role=role,
        explicit_time_limit=explicit_time_limit,
        resource_limit=resource_limit,
        fleet_tier=fleet_tier,
        confidence=confidence,
        unresolved_phrases=tuple(unresolved),
    )
