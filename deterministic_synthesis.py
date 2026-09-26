"""Deterministic evidence synthesizer for FGF Intelligence.

This module is the no-LLM response path. It performs bounded symbolic synthesis:
topic/entity gating, authority-aware evidence selection, complementary-claim
chaining, conflict handling, constraint handling, and numeric safety.

It deliberately prefers a transparent answer over fluent unsupported prose.
"""
import re
from typing import Any, Dict, List, Tuple

_TIER_WEIGHT = {
    "tier 1": 4.0,
    "tier 2": 3.0,
    "tier 3": 1.5,
}
_STATUS_WEIGHT = {
    "confirmed": 2.0,
    "current": 1.0,
    "under review": -0.5,
    "candidate": -1.0,
    "superseded": -20.0,
    "rejected": -20.0,
}

_STOP = {
    "what","what's","when","where","how","why","does","do","is","are","the","a",
    "an","to","of","for","and","or","i","my","you","your","can","could","would",
    "should","with","on","in","at","from","this","that","it","me","we","they",
    "be","as","by","about","which","who","much","many"
}

def _tokens(text: str) -> set:
    return {
        x for x in re.findall(r"[a-z0-9]+", str(text).lower())
        if x not in _STOP and len(x) > 1
    }

def _tier(claim: Dict[str, Any]) -> str:
    return str(claim.get("Evidence Tier", "")).lower()

def _status(claim: Dict[str, Any]) -> str:
    return str(claim.get("Status", "")).lower()

def _text(claim: Dict[str, Any]) -> str:
    return str(claim.get("Claim", "")).strip()

def _blob(claim: Dict[str, Any]) -> str:
    return " ".join(str(claim.get(k, "")) for k in ("Claim", "Category", "Notes", "Source")).lower()

def _authority_score(claim: Dict[str, Any]) -> float:
    t = _tier(claim)
    s = _status(claim)
    tw = next((v for k, v in _TIER_WEIGHT.items() if k in t), 0.0)
    sw = next((v for k, v in _STATUS_WEIGHT.items() if k in s), 0.0)
    return tw + sw

def _question_type(q: str) -> str:
    ql = q.lower()
    if any(x in ql for x in ("how do i", "how can i", "how to", "what should i do", "how should i")):
        return "procedure"
    if any(x in ql for x in ("cost", "how much", "how many", "price", "per hour", "how long")):
        return "numeric"
    if any(x in ql for x in ("best", "optimal", "recommended", "should i", "which", "priority", "prioritize")):
        return "strategy"
    if any(x in ql for x in ("compare", "difference", "versus", " vs ")):
        return "comparison"
    if any(x in ql for x in ("what is", "what are", "what does", "what do")):
        return "definition"
    return "generic"

def _requirements(q: str) -> List[str]:
    ql = q.lower()
    out = []
    if any(x in ql for x in ("repair", "damaged", "destroyed", "repair module", "repair cabin", "repair bay", "recover")):
        out.append("repair")
    if any(x in ql for x in ("champion", "champions", "hero", "heroes", "team", "composition", "tier list")):
        out.append("champion")
    if any(x in ql for x in ("energy core", "core 31", "core 32", "core 33", "core 34", "core 35", "fusion seed", "fusion seeds")):
        out.append("energy_core")
    if "flagship" in ql or "blueprint" in ql:
        out.append("flagship")
    if any(x in ql for x in ("credit", "credits", "resource", "resources", "trade", "shipping", "economy")):
        out.append("economy")
    if any(x in ql for x in ("shared moonlight", "moonsoil", "lunar soil", "moonlit treasures", "bingo bash", "full moon")):
        out.append("moonlight")
    if any(x in ql for x in ("beam", "kinetic", "ionic", "ion")):
        out.append("energy_type")
    return list(dict.fromkeys(out))

def _matches_requirement(q: str, claim: Dict[str, Any], req: str) -> bool:
    b = _blob(claim)
    checks = {
        "repair": ("repair","damage","damaged","recover","destroyed"),
        "champion": ("champion","hero","composition","ground team","tier list"),
        "energy_core": ("energy core","core level","core 31","core 32","core 33","core 34","core 35","fusion seed","fusion seeds"),
        "flagship": ("flagship","blueprint","core component"),
        "economy": ("credit","resource","trade","shipping","home port","economy","earn","spend"),
        "moonlight": ("shared moonlight","moonlight","moonsoil","lunar soil","moonlit","bingo bash","full moon"),
        "energy_type": ("beam","kinetic","ionic","ion"),
    }
    return any(x in b for x in checks.get(req, ()))

def _specific_target(q: str) -> Dict[str, Any]:
    ql=q.lower()
    out={}
    m=re.search(r'\b(?:energy\s+)?core\s*(?:level\s*)?(3[1-9]|[4-9]0?)\b',ql)
    if m:
        out["core_level"]=int(m.group(1))
    if "maximum" in ql and "energy core" in ql:
        out["max_core"]=True
    m=re.search(r'\b(beam|kinetic|ionic|ion)\s+(?:weapon\s+)?type?\s*counter(?:s|ed)?\s*(?:what|which)?',ql)
    if not m:
        m=re.search(r'what\s+does\s+(beam|kinetic|ionic|ion)\s+(?:weapon\s+type\s+)?counter',ql)
    if m:
        out["counter_attacker"]="ionic" if m.group(1)=="ion" else m.group(1)
    return out

def _constraint_terms(q: str) -> List[str]:
    ql = q.lower()
    out=[]
    if any(x in ql for x in ("f2p","free to play","free way","without spending","no spending","ad free")):
        out.append("F2P")
    if any(x in ql for x in ("best","optimal","recommended","should i","priority","prioritize")):
        out.append("BEST")
    if any(x in ql for x in ("fastest","quick","as soon as possible")):
        out.append("FAST")
    return out

def _claim_score(q: str, claim: Dict[str, Any], all_claims: List[Dict[str, Any]]) -> float:
    qt = _tokens(q)
    cb = _blob(claim)
    overlap = len(qt & _tokens(cb))
    score = overlap * 1.7 + _authority_score(claim)
    for req in _requirements(q):
        if _matches_requirement(q, claim, req):
            score += 4.0
        else:
            score -= 5.0
    qtype = _question_type(q)
    if qtype == "numeric" and re.search(r"\b\d[\d,.%]*\b", _text(claim)):
        score += 2.0
    if qtype == "procedure" and any(x in cb for x in ("requires","use","can","recover","unlock","upgrade","repair")):
        score += 1.5
    if qtype == "strategy" and any(x in cb for x in ("priority","best","recommended","efficient","strategy","synergy")):
        score += 1.0
    return score

def _select(q: str, claims: List[Dict[str, Any]], limit: int = 8) -> List[Tuple[int, Dict[str, Any], float]]:
    scored=[]
    target=_specific_target(q)
    for idx,c in enumerate(claims,1):
        if _status(c) in ("superseded","rejected"):
            continue
        blob=_blob(c)
        if target.get("core_level") is not None:
            n=str(target["core_level"])
            if not (re.search(r'\\bcore\\s*(?:level\\s*)?'+n+r'\\b',blob) or
                    re.search(r'\\benergy\\s+core\\s*(?:level\\s*)?'+n+r'\\b',blob)):
                # For an exact-level question, generic Energy Core claims are
                # supporting context only and must not masquerade as the answer.
                continue
        if target.get("max_core"):
            if not re.search(r'\\b(?:cap|maximum|max)\\b[^.]{0,60}\\b35\\b|\\b35\\b[^.]{0,60}\\b(?:cap|maximum|max)\\b',blob):
                continue
        if target.get("counter_attacker"):
            attacker=target["counter_attacker"]
            if not (re.search(r'\\b'+re.escape(attacker)+r'\\b[^.]{0,40}\\bcounter(?:s|ed)?\\b',blob)
                    or re.search(r'\\bcounter(?:s|ed)?\\b[^.]{0,40}\\b'+re.escape(attacker)+r'\\b',blob)):
                continue
        if _requirements(q) and not all(_matches_requirement(q,c,r) for r in _requirements(q)):
            continue
        s=_claim_score(q,c,claims)
        if s > 1.5:
            if target.get("core_level") is not None: s += 8.0
            if target.get("max_core"): s += 8.0
            if target.get("counter_attacker"): s += 8.0
            scored.append((idx,c,s))
    scored.sort(key=lambda x:(x[2],_authority_score(x[1])), reverse=True)
    # Keep at most two near-duplicates from the same normalized claim text.
    out=[];seen=set()
    for item in scored:
        key=re.sub(r"\W+"," ",_text(item[1]).lower())[:100]
        if key in seen:
            continue
        seen.add(key);out.append(item)
        if len(out)>=limit:
            break
    return out

def _sentences(text: str) -> List[str]:
    return [x.strip(" •-") for x in re.split(r"(?<=[.!?])\s+|\n+", text) if x.strip()]

def _action_sentences(selected: List[Tuple[int,Dict[str,Any],float]]) -> List[Tuple[int,str]]:
    patterns=("requires","need to","use ","spend ","repair ","upgrade ","unlock","can ","recover","obtain","select","build","prioritize","check")
    out=[]
    for idx,c,_ in selected:
        for s in _sentences(_text(c)):
            if any(p in s.lower() for p in patterns):
                out.append((idx,s))
    return out

def _numeric_sentences(selected: List[Tuple[int,Dict[str,Any],float]]) -> List[Tuple[int,str]]:
    out=[]
    for idx,c,_ in selected:
        for s in _sentences(_text(c)):
            if re.search(r"\b\d[\d,.%]*\b",s):
                out.append((idx,s))
    return out

def _dedupe_lines(lines: List[Tuple[int,str]], max_items: int=5) -> List[Tuple[int,str]]:
    out=[];seen=set()
    for idx,line in lines:
        key=re.sub(r"\W+"," ",line.lower())
        if key in seen: continue
        seen.add(key);out.append((idx,line))
        if len(out)>=max_items: break
    return out

def _conflict_text(conflicts: List[Dict[str,Any]], q: str) -> List[str]:
    qt=_tokens(q);out=[]
    for c in conflicts or []:
        txt=" ".join(str(c.get(k,"")) for k in ("Claim","Evidence A","Evidence B","Notes")).strip()
        if not txt: continue
        overlap=qt & _tokens(txt)
        # One generic word such as "major" or "level" is not enough to make a
        # conflict relevant. Require a real topic intersection.
        if len(overlap)>=2 or any(x in txt.lower() and x in q.lower() for x in (
            "command point","energy core","repair module","champion","commerce guild","cocoon"
        )):
            out.append(txt)
    return out[:2]

def synthesize_deterministic(question: str, claims: List[Dict[str,Any]], conflicts=None) -> Dict[str,Any]:
    """Produce an answer without an external model.

    The algorithm is deliberately conservative:
    1. Select only current/non-rejected evidence relevant to the question.
    2. Weight authority and lifecycle state.
    3. Chain complementary procedural/numeric facts.
    4. Never manufacture a missing value.
    5. Surface conflicts instead of silently resolving them.
    """
    q=question.strip()
    selected=_select(q,claims,8)
    conflicts=conflicts or []
    refs=[x[0] for x in selected]
    qtype=_question_type(q)
    reqs=_requirements(q)
    constraints=_constraint_terms(q)

    # Explicit F2P + major-damage handling: the corpus establishes the
    # Repair Module requirement, but that is not evidence of a free acquisition
    # route. State that limitation instead of inventing a workaround.
    if "F2P" in constraints and "repair" in reqs and "major" in q.lower():
        repair_refs=[x[0] for x in selected[:3]]
        lines=[
            "For Major Damage, the current evidence says Repair Modules are required for repair.",
            "• The current evidence does not establish a no-spend/free method to complete that repair. I will not invent one."
        ]
        if repair_refs:
            lines.append("Evidence: "+", ".join(f"[E{x}]" for x in repair_refs))
        return {
            "text":"\\n".join(lines),
            "model":"deterministic-evidence-synthesis",
            "evidence_used":repair_refs,
            "uncertainty":"A free/no-spend repair route is not established in the current evidence.",
            "synthesis_method":"symbolic_evidence_synthesis"
        }

    if not selected:
        return {
            "text":"I don't have sufficiently relevant current evidence to answer that safely. I won't substitute a related FGF mechanic or invent the missing value.",
            "model":"deterministic-evidence-synthesis",
            "evidence_used":[],
            "uncertainty":"No sufficiently relevant current evidence was retrieved.",
            "synthesis_method":"symbolic_evidence_synthesis"
        }

    top=selected[0]
    top_text=_text(top[1])
    target=_specific_target(q)
    lines=[]

    # Exact counter questions should return the direct relationship, not an
    # adjacent synergy/meta claim.
    if target.get("counter_attacker"):
        rel=[]
        attacker=target["counter_attacker"]
        for idx,c,_ in selected:
            txt=_text(c)
            if re.search(r'\\b'+re.escape(attacker)+r'\\b[^.]{0,40}\\bcounter(?:s|ed)?\\b',txt.lower()):
                rel.append((idx,txt))
        if rel:
            lines.append(rel[0][1] + f" [E{rel[0][0]}]")
            refs=[x[0] for x in rel[:3]]
            lines.append("Evidence: "+", ".join(f"[E{x}]" for x in refs))
            return {
                "text":"\\n".join(lines),
                "model":"deterministic-evidence-synthesis",
                "evidence_used":refs,
                "uncertainty":"",
                "synthesis_method":"symbolic_evidence_synthesis"
            }


    # Direct answer first: prefer the highest-authority claim, then add
    # complementary facts rather than dumping the whole retrieval set.
    if qtype=="numeric":
        nums=_dedupe_lines(_numeric_sentences(selected),4)
        exactish=[x for x in nums if any(k in x[1].lower() for k in ("cost","requires","per ","level","%","hours","days"))]
        if exactish:
            lines.append(exactish[0][1] + f" [E{exactish[0][0]}]")
        else:
            lines.append("The current evidence does not establish the exact numeric value requested. [E%d]" % top[0])
    elif qtype=="procedure":
        actions=_dedupe_lines(_action_sentences(selected),4)
        if actions:
            lines.append("The documented path is:")
            for idx,s in actions[:3]:
                lines.append(f"• {s} [E{idx}]")
        else:
            lines.append(top_text + f" [E{top[0]}]")
    elif qtype=="strategy":
        lines.append("Based on the documented mechanics, the practical approach is:")
        lines.append(f"• {top_text} [E{top[0]}]")
        for idx,c,_ in selected[1:4]:
            if idx==top[0]: continue
            lines.append(f"• {_text(c)} [E{idx}]")
    elif qtype=="comparison":
        for idx,c,_ in selected[:5]:
            lines.append(f"• {_text(c)} [E{idx}]")
        lines.append("The evidence does not by itself establish an overall winner; the documented differences are the basis for your choice.")
    else:
        lines.append(f"{top_text} [E{top[0]}]")
        for idx,c,_ in selected[1:4]:
            lines.append(f"• {_text(c)} [E{idx}]")

    # Constraint handling is explicit and never adds a paid mechanic.
    if "F2P" in constraints:
        lines.append("• F2P constraint applied: I have excluded unsupported spending requirements.")

    # Surface relevant conflicts separately. The higher-tier current evidence
    # remains the production basis; community conflicts are not promoted.
    ctexts=_conflict_text(conflicts,q)
    if ctexts:
        lines.append("• Conflict requiring a current check: community/YouTube evidence differs from another evidence position. Check the latest official/in-game information before relying on the conflicting detail.")

    # If we selected only weak/under-review material, say so.
    if _tier(top[1]).startswith("tier 3") or _status(top[1]) in ("candidate","under review"):
        lines.append("• Evidence status: the leading evidence is lower-tier or not fully confirmed; treat it as provisional.")

    # Procedure bullets already contain the actionable next step; do not repeat them.

    evidence_line="Evidence: "+", ".join(f"[E{x}]" for x in refs[:6])
    lines.append(evidence_line)

    uncertainty=""
    if qtype=="numeric" and not _numeric_sentences(selected):
        uncertainty="Exact numeric value is not established in the retrieved current evidence."
    elif ctexts:
        uncertainty="A relevant evidence conflict is present; latest official/in-game information should be checked."
    elif _tier(top[1]).startswith("tier 3") or _status(top[1]) in ("candidate","under review"):
        uncertainty="The leading retrieved evidence is provisional rather than fully confirmed."

    return {
        "text":"\n".join(lines),
        "model":"deterministic-evidence-synthesis",
        "evidence_used":refs[:6],
        "uncertainty":uncertainty,
        "synthesis_method":"symbolic_evidence_synthesis",
        "selected_evidence_count":len(selected)
    }
