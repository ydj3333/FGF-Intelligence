"""Generic natural-language constraint extraction for FGF v7.

Conservative by design: explicit user statements become hard constraints;
unstated player state is never invented.

History: an earlier revision of this file had its regex escapes corrupted
(``\\b`` became a literal backspace byte and ``\\s``/``\\d`` lost their
backslash), which silently disabled roster, count, time and resource
extraction. Tests in tests/test_constraint_extractor.py cover each pattern.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import re


# Canonical Champion names with the aliases players actually type.
# Canonical spelling follows the rest of the codebase (operational_intelligence).
CHAMPION_ALIASES = {
    "Ajita": ("ajita",),
    "Aliya": ("aliya",),
    "Cocoon": ("cocoon",),
    "Doug Rockwell": ("doug rockwell", "doug", "rockwell"),
    "Eva von Trier": ("eva von trier", "eva"),
    "Evan Rogers": ("evan rogers", "evan"),
    "Jodie Beart": ("jodie beart", "jodie"),
    "Kama Moai": ("kama moai", "kama", "kameni"),
    "Killer Bee": ("killer bee", "killerbee"),
    "Klara": ("klara",),
    "Lani Verita": ("lani verita", "lani"),
    "Lily": ("lily",),
    "Lucius Pullo": ("lucius pullo", "lucius", "pullo"),
    "Phade": ("phade",),
    "Riian Dessos": ("riian dessos", "riian"),
    "Zora Dominii": ("zora dominii", "zora domini", "zora"),
}

# Flat alias -> canonical map (kept for backward compatibility with importers).
ALIASES = {alias: canonical for canonical, aliases in CHAMPION_ALIASES.items() for alias in aliases}

_WORD_NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
                 "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}


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
    if isinstance(patterns, str):  # defensive: never iterate a pattern char-by-char
        patterns = (patterns,)
    return any(re.search(p, q, re.I) for p in patterns)


def find_champion_mentions(text: str) -> List[Tuple[int, str]]:
    """Return (position, canonical name) for each Champion mentioned, in order.

    Longer aliases win over shorter overlapping ones ("zora dominii" over "zora").
    """
    q = text.lower()
    taken: List[Tuple[int, int]] = []
    found: List[Tuple[int, str]] = []
    for alias, canonical in sorted(ALIASES.items(), key=lambda x: -len(x[0])):
        for m in re.finditer(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", q):
            if any(m.start() < e and m.end() > s for s, e in taken):
                continue
            taken.append((m.start(), m.end()))
            found.append((m.start(), canonical))
    found.sort()
    out: List[Tuple[int, str]] = []
    seen = set()
    for pos, name in found:
        if name not in seen:
            seen.add(name)
            out.append((pos, name))
    return out


_NOT_CHAMPIONS = {
    "core", "energy core", "flagship", "flagships", "season", "server", "guild", "f2p", "p2p",
    "kaboom", "gvg", "pvp", "pve", "t100", "beam", "kinetic", "ion", "ionic", "credits", "crystals",
    "fusion seeds", "speedups", "champions", "heroes", "team", "lineup", "i", "we",
}
_ROSTER_LIST_RE = re.compile(
    r"\b(?:I|we)\s+(?:only\s+)?(?:have|own|got|use|can use|unlocked)\s+([^.!?;:]+)"
    r"|\bmy\s+(?:champions?|heroes?|roster|team)\s+(?:are|is|=|:)?\s*([^.!?;]+)",
    re.I,
)


def _explicit_roster_items(question: str) -> List[Tuple[int, str]]:
    """Capitalized names in an explicit ownership list, e.g. "I have Ana, Bo and Cy"."""
    out: List[Tuple[int, str]] = []
    for m in _ROSTER_LIST_RE.finditer(question):
        group = 1 if m.group(1) is not None else 2
        seg, start = m.group(group), m.start(group)
        for im in re.finditer(r"[^,&/]+", seg):
            for part in re.split(r"\s+(?:and|or)\s+", im.group(0)):
                item = part.strip()
                item = re.sub(r"^(?:only|also|both)\s+", "", item, flags=re.I)
                if not item or not re.fullmatch(r"[A-Z][\w'-]*(?:\s+[A-Z][\w'-]*){0,2}", item):
                    continue
                if any(ch.isdigit() for ch in item) or item.lower() in _NOT_CHAMPIONS:
                    continue
                out.append((start + im.start() + im.group(0).find(part.strip()), item))
    return out


_NEGATION =r"(?:don't|do not|dont|doesn't|without|not have|not own|no longer have|haven't got|missing|except|excluding|lack)"


def extract_constraints(question: str) -> ExtractedConstraints:
    q = question.lower()
    unresolved: List[str] = []

    mentions = find_champion_mentions(q)

    # Explicit exclusions are hard constraints. A Champion is excluded when a
    # negation appears shortly before it within the same sentence.
    unavailable: List[str] = []
    for pos, name in mentions:
        window = q[max(0, pos - 40):pos]
        window = re.split(r"[.!?;]", window)[-1]
        if re.search(_NEGATION, window):
            unavailable.append(name)

    # Explicit ownership language is required. Mentioning a Champion alone
    # must not imply ownership.
    ownership_context = _has(q, (
        r"\b(i|we)\s+(have|own|got|use|can use|unlocked)\b",
        r"\b(i|we)'ve\s+(got|unlocked)\b",
        r"\bmy\s+(champions?|heroes?|roster|team)\b",
        r"\bavailable\s+(champions?|heroes?)\b",
        r"\bonly\s+have\b",
    ))
    owned: List[str] = []
    if ownership_context:
        found = [(pos, name) for pos, name in mentions if name not in unavailable]
        # Also accept Champions missing from CHAMPION_ALIASES (e.g. newly
        # released ones) when the player lists them explicitly after "I have".
        known_lower = {n.lower() for n in CHAMPION_ALIASES} | set(ALIASES)
        for pos, name in _explicit_roster_items(question):
            if name.lower() not in known_lower and name not in unavailable:
                found.append((pos, name))
        found.sort()
        for _, name in found:
            if name not in owned:
                owned.append(name)

    m = re.search(r"(?:give me|need|want|show me|provide|list)\s+(\d+|" + "|".join(_WORD_NUMBERS) + r")\b", q)
    requested_count = None
    if m:
        g = m.group(1)
        requested_count = int(g) if g.isdigit() else _WORD_NUMBERS.get(g)

    requested_positions = _has(q, (r"\b(order|position|positions|slot|slots|lineup order|formation order)\b",))

    optimization_goal = None
    if _has(q, (r"maximi[sz]e.*\b(points?|score|damage|kills?)\b", r"maximum.*\b(points?|score|damage|kills?)\b")):
        optimization_goal = "maximize requested event metric"
    elif _has(q, (r"\b(best|optimal|most efficient)\b",)):
        optimization_goal = "best feasible outcome"

    role = None
    for name, patterns in {
        "attacker": (r"\battack(?:ing|er)?\b", r"\boffensive\b"),
        "defender": (r"\bdefend(?:ing|er)?\b", r"\bdefensive\b"),
        "rally": (r"\brally\b",),
    }.items():
        if _has(q, patterns):
            role = name
            break

    tm = re.search(r"\b(\d+)\s*(?:min|mins|minutes|hr|hrs|hours)\b", q)
    explicit_time_limit = tm.group(0) if tm else None

    resource_limit = None
    for rm in re.finditer(r"\b(?:under|within|limit(?:ed)? to|max(?:imum)?(?: of)?)\s*([0-9][0-9,.]*)\s*(credits?|points?|resources?|m|k)?\b", q):
        # "within 30 minutes" is a time limit, not a resource limit.
        if re.match(r"\s*(?:min|mins|minutes|hr|hrs|hours|days?|h)\b", q[rm.end():]) and not rm.group(2):
            continue
        resource_limit = rm.group(0).strip()
        break

    # FGF project terminology: T1–T5 are explicit fleet progression tiers.
    fleet_tier = None
    tm_tier = re.search(r"(?<![a-z0-9])(?:fleet\s*(?:tier|level)?\s*)?t([1-5])(?![a-z0-9])", q, re.I)
    if tm_tier:
        fleet_tier = "T" + tm_tier.group(1)

    if ownership_context and not owned:
        unresolved.append("Ownership was stated, but no recognized Champion name was found.")
    if _has(q, (r"\bbest\b", r"\boptimal\b")) and not (owned or unavailable):
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
