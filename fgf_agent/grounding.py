"""Post-generation fact-check for agent answers.

Checks, without another LLM call:
  1. every [E#] citation refers to evidence the model actually received;
  2. every "factual" number in the answer appears in the evidence, a tool
     result, or the player's own message (blocks invented costs/timers);
  3. game-fact answers are backed by at least one search;
  4. Champions the player said they don't have are not recommended.
Issues are fed back to the model for one revision round.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, List, Sequence, Set

CITE_RE = re.compile(r"\[(E\d+(?:\s*[,;]\s*E?\d+)*)\]")
NUM_RE = re.compile(r"(?<![A-Za-z0-9])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*%)?")


@dataclass
class GroundingReport:
    passed: bool
    issues: List[str] = field(default_factory=list)
    cited_refs: List[str] = field(default_factory=list)
    unknown_refs: List[str] = field(default_factory=list)
    unsupported_numbers: List[str] = field(default_factory=list)

    def as_dict(self):
        return {"passed": self.passed, "issues": self.issues, "cited_refs": self.cited_refs,
                "unknown_refs": self.unknown_refs, "unsupported_numbers": self.unsupported_numbers}


def cited_refs(text: str) -> List[str]:
    out: List[str] = []
    for grp in CITE_RE.findall(text or ""):
        for part in re.split(r"\s*[,;]\s*", grp):
            part = part.strip().upper()
            if not part.startswith("E"):
                part = "E" + part
            if part not in out:
                out.append(part)
    return out


def _norm_num(s: str) -> str:
    s = s.replace(",", "")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s


def numbers_in(text: str) -> Set[str]:
    return {_norm_num(m.group(1)) for m in NUM_RE.finditer(text or "")}


def _factual_numbers(answer: str) -> List[str]:
    body = CITE_RE.sub(" ", answer or "")
    # drop ordered-list markers / step labels / headings like "1." "2)" "Step 3"
    body = re.sub(r"(?m)^\s*(?:[-*]\s*)?\d+[.)]\s+", " ", body)
    body = re.sub(r"(?i)\b(?:step|option|tip|phase|priority|#)\s*\d+\b", " ", body)
    out = []
    for m in NUM_RE.finditer(body):
        raw, pct = m.group(1), m.group(2)
        n = _norm_num(raw)
        try:
            val = float(n)
        except ValueError:
            continue
        # Single-digit counts ("3 Champions", "2 matching") are too common to
        # police; percentages, decimals, grouped thousands and >= 10 are checked.
        if pct or "," in raw or "." in raw or val >= 10:
            if n not in out:
                out.append(n)
    return out


def verify_answer(
    answer: str,
    *,
    known_refs: Iterable[str],
    allowed_text: str,
    user_text: str = "",
    searched: bool = True,
    unavailable_champions: Sequence[str] = (),
) -> GroundingReport:
    issues: List[str] = []
    known = set(known_refs)
    refs = cited_refs(answer)
    unknown = [r for r in refs if r not in known]
    if unknown:
        issues.append("Cited refs that were never provided: " + ", ".join(unknown) + ". Cite only refs returned by tools.")

    allowed_nums = numbers_in(allowed_text) | numbers_in(user_text)
    unsupported = [n for n in _factual_numbers(answer) if n not in allowed_nums]
    if unsupported:
        issues.append("These numbers do not appear in any evidence or tool result: " + ", ".join(unsupported[:8]) +
                      ". Remove them, replace them with the evidenced value, or say the exact value is not confirmed.")

    if not searched and len(answer or "") > 280:
        issues.append("The answer states game information without searching the knowledge base. Search first and cite the evidence.")

    low = (answer or "").lower()
    flagged = []
    for name in unavailable_champions:
        first = name.split()[0].lower()
        if re.search(r"(?<![a-z])" + re.escape(first) + r"(?![a-z])", low):
            flagged.append(name)
    if flagged:
        issues.append("The player said they do NOT have: " + ", ".join(flagged) +
                      ". Make sure the plan does not rely on them (mentioning them only as unavailable is fine).")

    # The champion check is advisory; it never blocks on its own after revision.
    blocking = bool(unknown or unsupported or (not searched and len(answer or "") > 280))
    return GroundingReport(passed=not blocking and not flagged, issues=issues, cited_refs=refs,
                           unknown_refs=unknown, unsupported_numbers=unsupported)
