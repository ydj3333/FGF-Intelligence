"""Relevance-first evidence retrieval for the FGF agent.

Why this exists
---------------
The legacy retrievers score claims by raw word overlap plus large authority
bonuses, gated by hand-written keyword lists. That lets a high-tier but
off-topic claim outrank the claim that actually answers the question, and it
lets long, garbled video-transcript fragments through.

This index uses:
  * BM25 over the claim text (with category/notes as weaker fields),
  * light stemming and an FGF glossary, so "heroes" finds "Champion" claims,
    "F2P" finds "free-to-play" claims, "T100" finds "Top 100", etc.,
  * a transcript-noise detector that down-weights garbled Tier-3 fragments,
  * authority (tier / lifecycle) as a *bounded* multiplier, never a substitute
    for relevance,
  * near-duplicate collapse so one fact is not shown five times.

The agent calls ``search`` several times with its own reformulations, so the
index does not need to understand the whole question in one shot.
"""
from __future__ import annotations

import hashlib
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

try:  # lifecycle normalisation from the main codebase, when importable
    from claim_lifecycle import normalize_state as _normalize_state
except Exception:  # pragma: no cover - standalone use
    _normalize_state = None


STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "of", "to", "in", "on", "at", "by",
    "for", "with", "from", "into", "about", "as", "is", "are", "was", "were", "be", "been",
    "being", "it", "its", "this", "that", "these", "those", "there", "here", "i", "me", "my",
    "we", "our", "you", "your", "they", "them", "their", "he", "she", "his", "her", "what",
    "which", "who", "whom", "when", "where", "why", "how", "do", "does", "did", "can", "could",
    "should", "would", "will", "shall", "may", "might", "must", "have", "has", "had", "so",
    "just", "also", "very", "really", "any", "some", "all", "get", "got", "im", "i'm", "dont",
    "much", "many", "more", "most", "than", "too", "up", "out", "not", "no", "yes", "please",
    "tell", "know", "want", "need", "thing", "things", "game", "fgf", "guys", "like",
}

# Words that frame a question but don't identify its topic. They still count
# a little, but cannot carry a match on their own.
GENERIC_TERMS = {_w for _w in ("best", "way", "ways", "strategy", "strategi", "tip", "tips", "guide",
                               "good", "better", "plan", "help", "work", "use", "doing", "easy", "fast")}
GENERIC_WEIGHT = 0.3

# Bidirectional FGF vocabulary. Each group is a set of interchangeable surface
# forms; a query term in a group also matches the other members (at a reduced
# weight). Multi-word members are matched as phrases.
GLOSSARY: List[Sequence[str]] = [
    ("champion", "champions", "hero", "heroes", "commander", "commanders"),
    ("f2p", "free to play", "free-to-play", "no spend", "non spender", "without spending", "zero spend"),
    ("p2p", "pay to play", "spender", "whale", "paid", "purchase", "pack", "packs"),
    ("t100", "top 100", "top100"),
    ("gvg", "guild vs guild", "guild versus guild", "guild war", "guild wars"),
    ("pvp", "player vs player", "player versus player"),
    ("pve", "player vs environment"),
    ("cp", "command point", "command points"),
    ("energy core", "core level", "core lvl", "ec"),
    ("fusion seed", "fusion seeds"),
    ("repair", "fix", "heal", "recover", "repair module", "repair modules"),
    ("damaged", "damage", "destroyed", "broken"),
    ("guild", "alliance", "commerce guild", "clan"),
    ("kaboom robot", "kaboom robots", "kaboom"),
    ("shared moonlight", "shadow moonlight", "moonlight event"),
    ("moonsoil", "lunar soil", "moon soil"),
    ("ion", "ionic"),
    ("lineup", "team", "composition", "comp", "formation", "squad"),
    ("best", "optimal", "strongest", "top", "meta", "tier list"),
    ("cost", "costs", "price", "spend", "how much", "required"),
    ("unlock", "unlocks", "available", "open", "opens", "access"),
    ("speedup", "speed up", "speedups", "acceleration", "accelerate"),
    ("credits", "credit", "money", "gold"),
    ("flagship", "flagships", "mothership"),
    ("server migration", "migration", "migrate", "transfer server", "move server"),
    ("maintenance", "downtime", "server update", "patch"),
    ("event", "events"),
    ("season 2", "s2"),
    ("season 1", "s1"),
    ("season 3", "s3"),
]

# Garbled spoken-transcript markers (video auto-captions).
_NOISE_MARKERS = (
    "you know", "here we go", "or something like that", "so that's what's up", "okay, so",
    "okay so", "right here", "i wanted to show you", "one thing i learned", "woo", "uh ",
    " um ", "gonna", "let me", "as you can see", "oh no", "guys", "subscribe", "for this test",
    "hot bar", "i think", "i guess", "kind of", "sort of", "basically", "actually",
)


def _stem(tok: str) -> str:
    """Tiny, predictable stemmer (no external deps)."""
    if len(tok) <= 3 or tok.isdigit():
        return tok
    for suf, rep in (("ies", "y"), ("oes", "o"), ("ing", ""), ("ed", ""), ("es", ""), ("s", "")):
        if tok.endswith(suf) and len(tok) - len(suf) >= 3:
            if suf == "es" and not tok.endswith(("ses", "xes", "zes", "ches", "shes")):
                return tok[:-1]
            return tok[: len(tok) - len(suf)] + rep
    return tok


_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[.,][0-9]+)?%?")


def tokenize(text: str, keep_stop: bool = False) -> List[str]:
    text = (text or "").lower().replace("’", "'")
    out = []
    for raw in _TOKEN_RE.findall(text):
        raw = raw.rstrip("%")
        if not keep_stop and raw in STOPWORDS:
            continue
        out.append(_stem(raw))
    return out


def _phrase_key(phrase: str) -> str:
    return " ".join(tokenize(phrase, keep_stop=True))


class Glossary:
    def __init__(self, groups: Iterable[Sequence[str]] = GLOSSARY):
        self.groups: List[List[str]] = []
        for g in groups:
            keys = [k for k in (_phrase_key(x) for x in g) if k]
            if keys:
                self.groups.append(list(dict.fromkeys(keys)))

    def groups_for_token(self, token: str) -> List[List[str]]:
        return [g for g in self.groups if token in g]

    def expand(self, query: str) -> List[str]:
        """Return extra phrases (as stemmed token strings) implied by the query."""
        qkey = " " + _phrase_key(query) + " "
        extra: List[str] = []
        for g in self.groups:
            if any((" " + k + " ") in qkey for k in g):
                extra.extend(k for k in g if (" " + k + " ") not in qkey)
        return list(dict.fromkeys(extra))


def tier_rank(tier_text: str) -> int:
    t = (tier_text or "").lower().replace(" ", "")
    m = re.search(r"(?:tier|t)([1-5])", t)
    if m:
        return int(m.group(1))
    return 4


def lifecycle_state(status: Any) -> str:
    if _normalize_state is not None:
        try:
            st = _normalize_state(status)
            return getattr(st, "value", str(st))
        except Exception:
            pass
    s = str(status or "").strip().lower()
    if s in ("confirmed", "current", "verified"):
        return "current"
    if s in ("rejected",):
        return "rejected"
    if s in ("superseded",):
        return "superseded"
    if s in ("conflicting",):
        return "conflicting"
    return "candidate"


def noise_score(text: str, tier: int) -> float:
    """0 = clean, 1 = clearly garbled transcript fragment."""
    if tier <= 2:
        return 0.0
    low = " " + (text or "").lower() + " "
    hits = sum(1 for m in _NOISE_MARKERS if m in low)
    score = min(1.0, 0.35 * hits)
    stripped = (text or "").strip()
    if stripped and stripped[0].islower():  # sentence fragment from mid-transcript
        score += 0.35
    if stripped and stripped[-1] not in ".!?)\"'":
        score += 0.15
    if len(stripped) > 220:
        score += 0.2
    return min(1.0, score)


@dataclass
class EvidenceDoc:
    doc_id: str
    claim: str
    category: str
    notes: str
    source: str
    tier: int
    tier_label: str
    status: str
    state: str
    confidence: str
    season: str
    noise: float
    raw: Dict[str, Any] = field(repr=False, default_factory=dict)

    @property
    def is_official(self) -> bool:
        return self.tier <= 2

    def to_public(self, ref: Optional[str] = None, notes_chars: int = 220) -> Dict[str, Any]:
        out = {
            "claim": self.claim,
            "category": self.category,
            "tier": self.tier_label or f"Tier {self.tier}",
            "authority": "official/verified" if self.tier == 1 else "official or tested" if self.tier == 2 else "community-reported",
            "status": self.status,
            "confidence": self.confidence,
            "season": self.season,
            "source": self.source,
        }
        if self.notes:
            out["notes"] = self.notes[:notes_chars]
        if ref:
            out = {"ref": ref, **out}
        return out


def _doc_id(c: Dict[str, Any]) -> str:
    key = c.get("claim_key") or c.get("supabase_id")
    if key:
        return str(key)
    raw = (str(c.get("Claim", "")) + "|" + str(c.get("Source", ""))).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


class EvidenceIndex:
    """BM25F-style index over FGF claims."""

    K1 = 1.4
    B = 0.72
    FIELD_WEIGHTS = {"claim": 1.0, "category": 0.45, "notes": 0.25}

    def __init__(self, claims: Iterable[Dict[str, Any]], glossary: Optional[Glossary] = None):
        self.glossary = glossary or Glossary()
        self.docs: List[EvidenceDoc] = []
        self.by_id: Dict[str, EvidenceDoc] = {}
        self._tf: List[Dict[str, float]] = []
        self._len: List[float] = []
        self._phr: List[str] = []
        df: Counter = Counter()
        seen_text = set()
        for c in claims:
            claim = str(c.get("Claim") or c.get("claim") or "").strip()
            if not claim:
                continue
            tier_label = str(c.get("Evidence Tier") or c.get("tier") or "")
            tier = tier_rank(tier_label)
            status = str(c.get("Status") or c.get("status") or "")
            state = lifecycle_state(status)
            if state in ("rejected", "superseded", "archived"):
                continue
            norm = re.sub(r"\W+", " ", claim.lower()).strip()
            if norm in seen_text:
                continue
            seen_text.add(norm)
            notes = str(c.get("Notes") or c.get("notes") or "")
            doc = EvidenceDoc(
                doc_id=_doc_id(c),
                claim=claim,
                category=str(c.get("Category") or c.get("category") or ""),
                notes=notes,
                source=str(c.get("Source") or c.get("source") or ""),
                tier=tier,
                tier_label=tier_label,
                status=status,
                state=state,
                confidence=str(c.get("Confidence") or c.get("confidence") or ""),
                season=str(c.get("Season/Version") or c.get("season") or ""),
                noise=noise_score(claim, tier),
                raw=c,
            )
            if doc.doc_id in self.by_id:
                doc.doc_id = doc.doc_id + "-" + str(len(self.docs))
            tf: Dict[str, float] = defaultdict(float)
            length = 0.0
            for fname, text in (("claim", doc.claim), ("category", doc.category), ("notes", doc.notes[:400])):
                w = self.FIELD_WEIGHTS[fname]
                toks = tokenize(text)
                for t in toks:
                    tf[t] += w
                length += w * len(toks)
            for t in tf:
                df[t] += 1
            self.docs.append(doc)
            self.by_id[doc.doc_id] = doc
            self._tf.append(dict(tf))
            self._len.append(max(1.0, length))
            self._phr.append(" " + _phrase_key(doc.claim + " " + doc.category) + " ")
        n = max(1, len(self.docs))
        self._avglen = sum(self._len) / n if self._len else 1.0
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._postings: Dict[str, List[int]] = defaultdict(list)
        for i, tf in enumerate(self._tf):
            for t in tf:
                self._postings[t].append(i)

    def __len__(self) -> int:
        return len(self.docs)

    # ------------------------------------------------------------------ search
    def _bm25(self, i: int, terms: Dict[str, float]) -> float:
        tf = self._tf[i]
        norm = self.K1 * (1 - self.B + self.B * self._len[i] / self._avglen)
        s = 0.0
        for t, qw in terms.items():
            f = tf.get(t)
            if not f:
                continue
            s += qw * self._idf.get(t, 0.0) * (f * (self.K1 + 1)) / (f + norm)
        return s

    def search(
        self,
        query: str,
        limit: int = 8,
        *,
        include_community: bool = True,
        official_only: bool = False,
        category: Optional[str] = None,
        season: Optional[str] = None,
        exclude_ids: Iterable[str] = (),
        min_score: float = 0.8,
    ) -> List[Dict[str, Any]]:
        """Return ranked hits: [{"doc": EvidenceDoc, "score": float, "matched": [...]}, ...]."""
        base = tokenize(query)
        if not base:
            return []
        terms: Dict[str, float] = {}
        for t in base:
            terms[t] = max(terms.get(t, 0.0), GENERIC_WEIGHT if t in GENERIC_TERMS else 1.0)
        expansions = self.glossary.expand(query)
        exp_phrases = []
        for ph in expansions:
            toks = ph.split()
            if len(toks) == 1:
                terms.setdefault(toks[0], 0.6)
            else:
                exp_phrases.append(ph)
                for t in toks:
                    if t not in STOPWORDS:
                        terms.setdefault(t, 0.35)
        # Shorthand the corpus never uses ("T100") hands its full weight to
        # its expansion ("Top 100"), and is satisfied when that expansion matches.
        satisfied_by: Dict[str, set] = {}
        for t in set(base):
            if t in self._postings:
                continue
            for g in self.glossary.groups_for_token(t):
                for member in g:
                    if member == t:
                        continue
                    mtoks = [x for x in member.split() if x not in STOPWORDS]
                    for x in mtoks:
                        terms[x] = max(terms.get(x, 0.0), 1.0 if len(mtoks) == 1 else 0.85)
                    if len(mtoks) > 1 and member not in exp_phrases:
                        exp_phrases.append(member)
                    satisfied_by.setdefault(t, set()).update(mtoks)
        content = [t for t in dict.fromkeys(base) if t not in GENERIC_TERMS] or list(dict.fromkeys(base))
        qkey = _phrase_key(query)
        q_bigrams = [" ".join(p) for p in zip(qkey.split(), qkey.split()[1:]) if not set(p) & STOPWORDS]

        candidates = set()
        for t in terms:
            candidates.update(self._postings.get(t, ()))
        exclude = set(exclude_ids)
        cat_l = (category or "").lower().strip()
        season_u = (season or "").upper().strip()
        hits = []
        for i in candidates:
            doc = self.docs[i]
            if doc.doc_id in exclude:
                continue
            if official_only and doc.tier > 2:
                continue
            if not include_community and doc.tier > 2:
                continue
            if cat_l and cat_l not in doc.category.lower():
                continue
            if season_u and doc.season and season_u not in doc.season.upper() and re.search(r"S[1-9]", doc.season.upper()):
                continue
            s = self._bm25(i, terms)
            if s <= 0:
                continue
            phr = self._phr[i]
            # Phrase bonuses: exact multi-word matches are strong relevance signals.
            bonus = 0.0
            for bg in q_bigrams:
                if " " + bg + " " in phr:
                    bonus += 0.9
            for ph in exp_phrases:
                if " " + ph + " " in phr:
                    bonus += 0.6
            s += bonus
            # Coverage: fraction of distinct *content* query terms matched
            # (generic words like "best"/"way" don't count either way).
            tf_i = self._tf[i]
            matched = [t for t in content if t in tf_i or (t in satisfied_by and satisfied_by[t] <= set(tf_i))]
            coverage = len(matched) / max(1, len(content))
            s *= 0.6 + 0.8 * coverage
            # Bounded authority & quality multipliers (relevance stays dominant).
            authority = {1: 1.18, 2: 1.10, 3: 0.95, 4: 0.85, 5: 0.8}.get(doc.tier, 0.85)
            lifecycle = 1.05 if doc.state == "current" else 0.97 if doc.state in ("validated", "verified") else 0.92
            quality = 1.0 - 0.6 * doc.noise
            s *= authority * lifecycle * quality
            if s >= min_score:
                hits.append({"doc": doc, "score": round(s, 3), "matched": matched})
        hits.sort(key=lambda h: (-h["score"], h["doc"].tier))
        return self._collapse(hits)[:limit]

    @staticmethod
    def _collapse(hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Drop near-duplicates (keep the best-ranked / most authoritative)."""
        kept: List[Dict[str, Any]] = []
        sigs: List[set] = []
        for h in hits:
            toks = set(tokenize(h["doc"].claim))
            dup = False
            for s in sigs:
                if toks and s and len(toks & s) / len(toks | s) >= 0.8:
                    dup = True
                    break
            if not dup:
                kept.append(h)
                sigs.append(toks)
        return kept

    def get(self, doc_id: str) -> Optional[EvidenceDoc]:
        return self.by_id.get(doc_id)

    def find_by_text(self, claim_text: str) -> Optional[EvidenceDoc]:
        """Exact (normalised) claim-text lookup, used to merge refs from other engines."""
        if not hasattr(self, "_by_text"):
            self._by_text = {re.sub(r"\W+", " ", d.claim.lower()).strip(): d for d in self.docs}
        return self._by_text.get(re.sub(r"\W+", " ", str(claim_text or "").lower()).strip())

    def categories(self) -> List[str]:
        return sorted({d.category for d in self.docs if d.category})
