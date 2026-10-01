"""FGF v6.4 Operational Intelligence layer.

Turns evidence into player-facing operational structures: event day plans,
shop matrices, resource rules, and explicit unknowns. Canonical evidence is
always the first basis; curated community material is enrichment only.
No unsupported numeric value is fabricated.
"""

from __future__ import annotations
from typing import Any, Dict, List
import re

NOT_ESTABLISHED = "Not established in current evidence"

PLAYBOOKS = {
    "anti_plunder": {
        "name": "Anti-Plunder Operation",
        "kind": "event",
        "days": [
            {"date":"2026-10-02","day":"Fri","objective":"Anti-Plunder Operation","do":NOT_ESTABLISHED,"save":NOT_ESTABLISHED,"avoid":NOT_ESTABLISHED,"state":"USER_SCREENSHOT_OBSERVED"},
            {"date":"2026-10-03","day":"Sat","objective":"Anti-Plunder Operation","do":NOT_ESTABLISHED,"save":NOT_ESTABLISHED,"avoid":NOT_ESTABLISHED,"state":"USER_SCREENSHOT_OBSERVED"},
            {"date":"2026-10-04","day":"Sun","objective":"Anti-Plunder Operation","do":NOT_ESTABLISHED,"save":NOT_ESTABLISHED,"avoid":NOT_ESTABLISHED,"state":"USER_SCREENSHOT_OBSERVED"}
        ],
        "global": {
            "before":NOT_ESTABLISHED,
            "during":NOT_ESTABLISHED,
            "after":NOT_ESTABLISHED
        },
        "source":"User-provided FGF event-calendar screenshot dated 2026-09-30; presence and displayed date span are observed, mechanics/rewards/objectives are not established by this screenshot alone."
    },
    "shadowfront": {
        "name": "Shadowfront",
        "kind": "event",
        "days": [],
        "global": {
            "before": "Confirm the current Shadowfront rules, vault objectives and active rewards before committing scarce resources.",
            "during": "Use the live event objectives and protect traders in the Outer Rim Outpost; current evidence establishes that Shadowfront contains 8 Lesser Vaults and 2 Central Vaults.",
            "after": "Claim established rewards and record event-specific outcomes for the next cycle."
        },
        "source":"Current Tier-1/Tier-2 FGF evidence; no day-by-day Shadowfront schedule is established in the current claim set."
    },
    "gvg": {
        "name": "Guild vs Guild",
        "kind": "event",
        "days": [
            {"day":"Day 1","objective":NOT_ESTABLISHED,"do":"Follow the live in-game objective for the day; use only resources that advance that objective.","save":"Keep Speedups, Champion XP, Beacons, Computational Components and rare upgrade materials available for later objectives.","avoid":"Do not spend heavily before the day's objective and milestone value are understood.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 2","objective":NOT_ESTABLISHED,"do":"Spend only on the current objective and stop when the next milestone is poor value.","save":"Preserve resources needed for later GvG objectives.","avoid":"Do not convert general progression resources into points without a clear objective match.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 3","objective":NOT_ESTABLISHED,"do":"Check the live objective first; use the resource category explicitly requested by the game.","save":"Computational Components and other rare progression materials unless the current objective explicitly calls for them.","avoid":"Do not assume a community day mapping is universal across servers/seasons.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 4","objective":NOT_ESTABLISHED,"do":"Follow the live objective and use only efficient actions that also improve account progression.","save":"Rare materials and reserve resources for later milestones.","avoid":"Avoid low-value spending merely to chase points.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 5","objective":NOT_ESTABLISHED,"do":"Verify the live objective and milestone ladder before spending.","save":"Keep reserve resources if the next milestone has weak value.","avoid":"Do not force a milestone whose reward is not worth the resource cost.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 6","objective":NOT_ESTABLISHED,"do":"Follow server-specific rules and the current in-game objective; PvP-related actions may be relevant only where the event establishes them.","save":"Keep enough reserve for normal progression after the event.","avoid":"Do not treat a generic community schedule as the authoritative server schedule.","state":"COMMUNITY_GUIDE"},
        ],
        "global": {
            "before":"Save Speedups, Beacons, Champion XP, commissions and rare materials; check objectives, milestones and guild coordination.",
            "during":"Spend only on the relevant objective; stop when the next milestone is poor value; prefer actions that advance both account power and event points.",
            "after":"Claim rewards, check expiring currencies, rebuild the reserve and record what was valuable for the next cycle."
        },
        "source":"Curated from stored community/player guide material; day-specific objective mapping is not established in the canonical claim set."
    },
    "top100": {
        "name": "Top 100 Galactic Traders",
        "kind": "event",
        "days": [
            {"day":"Day 1","objective":"Ordinary Tribute activities + moderate Speedups","do":"Use ordinary Tribute activities and moderate Speedups.","save":"Preserve surplus resources for later days.","avoid":"Do not spend heavily just to chase early milestones.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 2","objective":"Commissions","do":"Work commissions and spend Crystals cautiously when they directly advance the objective.","save":"Keep Crystals available for higher-value needs.","avoid":"Avoid unnecessary Crystal spending.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 3","objective":"Beacons / Beacon materials","do":"Use Beacons or Beacon materials when the objective requires them.","save":"Computational Components for GvG where applicable.","avoid":"Do not consume rare Computational Components merely because they are available.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 4","objective":"Mainly commissions","do":"Prioritize commissions that advance the active objective.","save":"Rare resources for stronger objectives.","avoid":"Avoid rare-resource spending without a clear milestone payoff.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 5","objective":"Weaker reward ladder","do":"Take the third milestone if convenient and resource-efficient.","save":"Resources if the fourth milestone has poor value.","avoid":"Usually do not force the fourth milestone when resource cost is disproportionate.","state":"COMMUNITY_GUIDE"},
            {"day":"Day 6","objective":"PvP according to server rules","do":"Participate in PvP only within current server/event rules; overlap with other PvP events where useful.","save":"Normal progression reserve after the event.","avoid":"Do not assume PvP requirements without checking the live server rules.","state":"COMMUNITY_GUIDE"},
        ],
        "global": {
            "before":"Save event-relevant resources and inspect the current milestone ladder.",
            "during":"Match spending to the active objective and stop when marginal reward value drops.",
            "after":"Claim rewards, check expiring currencies and rebuild the reserve."
        },
        "source":"Curated from stored community/player guide material."
    }
}

KABOOM_COMBO_ROWS = [
    ["Primary community combo","Zora + Lily + Jodie","Zora grouping + Lily AoE/bomb damage + Jodie weapon effects are reported as working together against grouped enemies.","COMMUNITY — Under Review"],
    ["Core strategy","Fast AoE wave clearing","Community guidance prioritizes clearing waves quickly rather than relying on slow single-target damage.","COMMUNITY — Under Review"],
    ["Key mechanic","Enemy grouping","Zora is reported to group enemies tightly; grouping is reported to improve clear efficiency.","COMMUNITY — Under Review"],
    ["Performance caveat","Wave/spawn RNG matters","Community material reports that spawn positioning can affect clear times; treat this as experience, not a guaranteed mechanic.","COMMUNITY — Under Review"],
]

# Five-lineup presentation is deliberately roster-aware. The current corpus establishes
# one concrete Kaboom lineup, not five named lineups. The remaining four rows are
# selection templates, not invented champion recommendations.
KABOOM_LINEUP_OPTIONS = [
    ["Lineup 1","Zora + Lily + Jodie","Known community-tested trio: grouping + AoE/bomb damage + weapon effects.","COMMUNITY — Under Review","Concrete"],
    ["Lineup 2","Zora + Lily + [weapon-effect champion]","Keep Zora's grouping and Lily's AoE; replace Jodie only with a player-owned champion whose weapon effect is suitable for grouped targets.","INFERRED TEMPLATE — Not Kaboom-validated","Roster required"],
    ["Lineup 3","Zora + [AoE champion] + [weapon-effect champion]","Preserve the documented grouping core; substitute Lily and/or Jodie with owned champions matching the required roles.","INFERRED TEMPLATE — Not Kaboom-validated","Roster required"],
    ["Lineup 4","[grouping/control champion] + Lily + [weapon-effect champion]","Preserve Lily's documented AoE role; replace Zora only if the player has another grouping/control option supported by evidence.","INFERRED TEMPLATE — Not Kaboom-validated","Roster required"],
    ["Lineup 5","[control/stun] + [AoE] + [damage/weapon-effect]","Fallback when the named trio is unavailable: prioritize control/grouping, wave-clearing AoE, and a third damage/weapon-effect role.","INFERRED TEMPLATE — Not Kaboom-validated","Roster required"],
]

SHOP_ROWS = [
    {"shop":"Intel Shop","priority":"Weapon Prisms; then Deep Space Beacons","buy_when":"When the item advances a current progression need and the exchange is supported by the shop's current inventory/value.","save":"Currency for higher-value progression items if not immediately needed.","avoid":"Unverified items or purchases whose current exchange value is unknown.","state":"COMMUNITY_GUIDE"},
    {"shop":"Black Market","priority":"Discounted Speedups and rare materials","buy_when":"When the discount materially supports a current event/progression objective.","save":"Currency for unusually strong discounts and scarce materials.","avoid":"Routine purchases without a current need.","state":"COMMUNITY_GUIDE"},
    {"shop":"Guild Shop","priority":"Beacons, Speedups, permanent progression","buy_when":"When the item supports permanent progression or an active objective.","save":"Guild currency for permanent progression items if no immediate need exists.","avoid":"Low-impact purchases when a permanent progression item is available.","state":"COMMUNITY_GUIDE"},
    {"shop":"Arena-related Shop","priority":"Premium Champion progress where available","buy_when":"When Champion progression is part of the player's current plan.","save":"Currency for needed Champion progression.","avoid":"Purchases unrelated to the current Champion plan.","state":"COMMUNITY_GUIDE"},
    {"shop":"Regular Shop","priority":"Usually avoid unless urgently needed","buy_when":"Only when the item solves an immediate, evidence-supported need.","save":"General currency for stronger shop opportunities.","avoid":"Impulse purchases and routine full-price spending.","state":"COMMUNITY_GUIDE"},
]

def _blob(evidence: List[Dict[str, Any]]) -> str:
    return " ".join(str(x.get(k,"")) for x in evidence for k in ("Claim","Notes","Category","Source")).lower()

def _event_key(q: str) -> str | None:
    ql=q.lower()
    if any(x in ql for x in ("guild vs guild","gvg","guild versus guild")): return "gvg"
    if any(x in ql for x in ("top 100 galactic traders","galactic traders","top 100 traders")): return "top100"
    if "shadowfront" in ql: return "shadowfront"
    if any(x in ql for x in ("anti-plunder operation","anti plunder operation","anti-plunder","anti plunder")): return "anti_plunder"
    return None

def _requested_option_count(question: str) -> int | None:
    """Extract an explicit requested alternative count without guessing."""
    ql = question.lower()

    # Allow the subject/topic between the requested count and the option noun,
    # e.g. "give me 5 Kaboom lineups" or "show five Kaboom combos".
    numeric_patterns = [
        r"\b(?:top|give me|show me|need|want)\s+(\d{1,2})(?:\s+[a-z0-9,&'-]+){0,6}\s+(?:options?|alternatives?|lineups?|line\s+ups?|teams?|combos?)\b",
        r"\b(\d{1,2})(?:\s+[a-z0-9,&'-]+){0,6}\s+(?:options?|alternatives?|lineups?|line\s+ups?|teams?|combos?)\b",
        r"\b(?:options?|alternatives?|lineups?|line\s+ups?|teams?|combos?)\s+(?:of|=)\s*(\d{1,2})\b",
    ]
    for pattern in numeric_patterns:
        m = re.search(pattern, ql)
        if m:
            n = int(m.group(1))
            if 2 <= n <= 20:
                return n

    word_patterns = [
        r"\b(?:top|give me|show me|need|want)\s+(five|four|three|two)(?:\s+[a-z0-9,&'-]+){0,6}\s+(?:options?|alternatives?|lineups?|line\s+ups?|teams?|combos?)\b",
        r"\b(five|four|three|two)(?:\s+[a-z0-9,&'-]+){0,6}\s+(?:options?|alternatives?|lineups?|line\s+ups?|teams?|combos?)\b",
    ]
    words = {"two": 2, "three": 3, "four": 4, "five": 5}
    for pattern in word_patterns:
        m = re.search(pattern, ql)
        if m:
            return words[m.group(1)]
    return None

def _verify_operational_output(question: str, output: Dict[str, Any] | None) -> Dict[str, Any] | None:
    """Verify that an operational response satisfies explicit user constraints.

    This is a structural safety check, not a factuality score. It prevents the
    renderer from silently returning fewer alternatives than requested and
    makes roster-dependent placeholders visible instead of presenting them as
    validated combinations.
    """
    if not output:
        return None
    requested = _requested_option_count(question)
    rows = output.get("rows") if isinstance(output.get("rows"), list) else []
    verification = {
        "requested_option_count": requested,
        "returned_option_count": len(rows) if rows else 0,
        "count_match": requested is None or len(rows) == requested,
        "validation_scope": "structural_only",
    }
    if output.get("mode") == "event_combo_options":
        concrete = sum(1 for row in rows if len(row) >= 5 and row[4] == "Concrete")
        roster_required = sum(1 for row in rows if len(row) >= 5 and row[4] == "Roster required")
        verification.update({
            "concrete_validated_options": concrete,
            "roster_required_options": roster_required,
            "requires_player_roster": roster_required > 0,
        })
        if requested is not None and len(rows) != requested:
            raise ValueError(
                f"Operational option-count validation failed: requested {requested}, returned {len(rows)}"
            )
    if not verification["count_match"]:
        raise ValueError(
            f"Operational option-count validation failed: requested {requested}, returned {len(rows)}"
        )
    output = dict(output)
    output["verification"] = verification
    return output



def _profile_constraints(player_context: Dict[str, Any] | None) -> Dict[str, Any]:
    """Normalize optional player context without inventing missing fields."""
    ctx = player_context if isinstance(player_context, dict) else {}
    champions = ctx.get("champion_levels")
    if not isinstance(champions, dict):
        champions = {}
    fleet_styles = ctx.get("fleet_styles")
    if not isinstance(fleet_styles, list):
        fleet_styles = []
    resources = ctx.get("resources")
    if not isinstance(resources, dict):
        resources = {}
    preferences = ctx.get("preferences")
    if not isinstance(preferences, dict):
        preferences = {}
    return {
        "available": bool(ctx),
        "season": ctx.get("season"),
        "core_level": ctx.get("core_level"),
        "flagship_level": ctx.get("flagship_level"),
        "owned_champions": _profile_owned_champions(ctx),
        "fleet_styles": fleet_styles,
        "resources": resources,
        "preferences": preferences,
    }


def _profile_guardrail(profile: Dict[str, Any]) -> str:
    """State exactly how player context may affect operational output."""
    if not profile.get("available"):
        return "No player profile supplied; no personalization assumptions were made."
    return (
        "Player context is a personalization constraint only. "
        "Missing profile fields remain unknown, and player context cannot override "
        "canonical evidence or turn an inference into a validated game fact."
    )


def _profile_owned_champions(player_context: Dict[str, Any] | None) -> List[str]:
    """Return explicitly owned Champions from a persisted player profile."""
    if not isinstance(player_context, dict):
        return []
    raw=player_context.get("champion_levels")
    if not isinstance(raw, dict):
        return []
    owned=[]
    for name, value in raw.items():
        if not isinstance(name, str) or not name.strip():
            continue
        if isinstance(value, dict) and value.get("owned") is False:
            continue
        if value is False or value is None:
            continue
        owned.append(name.strip())
    return owned


KABOOM_ROLE_SIGNALS = {
    "grouping_control": {
        "Zora Domini": ("group enemies tightly", "stun-lock", "group clearing"),
        "Kama Moai": ("stun enemies",),
        "Riian Dessos": ("clearing groups",),
    },
    "aoe_wave_clear": {
        "Lily": ("AOE", "grouped enemies"),
        "Zora Domini": ("group clearing", "AoE pressure", "multi-hit"),
        "Riian Dessos": ("clearing groups",),
    },
    "damage": {
        "Jodie Beart": ("weapon effects", "team damage", "Ion Support/Damage"),
        "Evan Rogers": ("sustained Beam damage", "high-damage", "formation-wide"),
        "Killer Bee": ("high damage", "physical damage"),
        "Lani Verita": ("damage dealer",),
        "Kama Moai": ("damage dealer",),
        "Riian Dessos": ("single target damage",),
        "Zora Domini": ("burst damage", "powerful damage"),
    },
}

def _champion_role_fit(name: str, claims: List[Dict[str, Any]]) -> Dict[str, Any]:
    canonical_name=name.strip()
    aliases=[canonical_name]
    if canonical_name=="Jodie Beart": aliases.append("Jodie Béart")
    if canonical_name=="Zora Domini": aliases.extend(["Zora Dominii","Zora"])
    matched=[]
    for claim in claims:
        cl=str(claim.get("Claim",""))
        if any(a.lower() in cl.lower() for a in aliases):
            matched.append({
                "claim":cl,
                "tier":claim.get("Evidence Tier",""),
                "status":claim.get("Status",""),
                "canonical":claim.get("Canonical",claim.get("canonical",False))
            })
    text=" ".join(x["claim"] for x in matched)
    roles=set()
    for role,catalog in KABOOM_ROLE_SIGNALS.items():
        if any(sig.lower() in text.lower() for sig in catalog.get(canonical_name,())):
            roles.add(role)
    return {"champion":canonical_name,"roles":sorted(roles),"evidence":matched[:6]}

def _roster_kaboom_options(question: str, player_context: Dict[str, Any] | None,
                           claims: List[Dict[str, Any]], requested: int) -> Dict[str, Any]:
    owned=_profile_owned_champions(player_context)
    standard=["Ajita","Aliya","Cocoon","Doug Rockwell","Eva von Trier","Evan Rogers",
              "Jodie Beart","Kama Moai","Killer Bee","Klara","Lani Verita","Lily",
              "Lucius Pullo","Phade","Riian Dessos","Zora Domini"]
    standard_map={x.lower():x for x in standard}
    owned=[standard_map[x.lower()] for x in owned if x.lower() in standard_map]
    role_rows={x:_champion_role_fit(x,claims) for x in owned}

    def has(name):
        return any(x.lower()==name.lower() for x in owned)

    candidates=[]
    if has("Zora Domini") and has("Lily") and has("Jodie Beart"):
        candidates.append({
            "lineup":[next(x for x in owned if x.lower()=="zora domini"),next(x for x in owned if x.lower()=="lily"),next(x for x in owned if x.lower()=="jodie beart")],
            "state":"Kaboom evidence — Under Review",
            "basis":"Named Kaboom community combination: Zora grouping + Lily AoE/bomb damage + Jodie weapon effects.",
            "evidence_scope":"Kaboom-specific"
        })

    grouping=[x for x,r in role_rows.items() if "grouping_control" in r["roles"]]
    aoe=[x for x,r in role_rows.items() if "aoe_wave_clear" in r["roles"]]
    damage=[x for x,r in role_rows.items() if "damage" in r["roles"]]
    combos=[]
    for g in grouping:
        for a in aoe:
            for d in damage:
                combo=[g,a,d]
                if len({x.lower() for x in combo})<3: continue
                if any([x for x in candidates if [z.lower() for z in x["lineup"]]==[z.lower() for z in combo]]): continue
                anchor_score=sum(x in ("Zora Domini","Lily","Jodie Beart") for x in combo)
                evidence_count=sum(len(role_rows[x]["evidence"]) for x in combo)
                combos.append((anchor_score,evidence_count,combo))
    combos.sort(key=lambda x:(-x[0],-x[1],[z.lower() for z in x[2]]))
    for _,_,combo in combos:
        candidates.append({
            "lineup":combo,
            "state":"Roster-fit inference — not Kaboom-validated",
            "basis":"All three Champions are owned and their required roles have supporting evidence; the combination itself is an inference, not a Kaboom-specific tested lineup.",
            "evidence_scope":"Role-compatible inference"
        })
        if len(candidates)>=requested: break

    rows=[[i+1," + ".join(x["lineup"]),x["state"],x["basis"],x["evidence_scope"]]
          for i,x in enumerate(candidates[:requested])]
    verification={
        "requested_option_count":requested,
        "returned_option_count":len(rows),
        "count_match":len(rows)==requested,
        "roster_size":len(owned),
        "roster_available":bool(owned),
        "validation_scope":"structural + evidence-gated",
    }
    if len(rows)<requested:
        return {
            "mode":"event_combo_roster_options",
            "title":f"Kaboom, Robots! — {requested} roster-aware lineup options",
            "basis":"The requested count cannot be filled from the supplied roster using only evidence-supported roles without inventing Champions or unsupported combinations.",
            "source_state":"ROSTER_AWARE / EVIDENCE_GATED",
            "columns":["Option","Lineup","State","Basis","Evidence scope"],
            "rows":rows,
            "verification":verification,
            "guardrail":"Insufficient evidence-supported roster combinations to satisfy the requested count. No invented Champions or unsupported Kaboom combinations were added. Add more owned Champions or request fewer alternatives."
        }
    return {
        "mode":"event_combo_roster_options",
        "title":f"Kaboom, Robots! — {requested} roster-aware lineup options",
        "basis":"Options are generated from the player's stored roster. Kaboom-specific evidence is preferred; other combinations are role-compatible inferences and are clearly marked as not Kaboom-validated.",
        "source_state":"ROSTER_AWARE / EVIDENCE_GATED",
        "columns":["Option","Lineup","State","Basis","Evidence scope"],
        "rows":rows,
        "verification":verification,
        "guardrail":"The first named combination is supported by Kaboom-specific community evidence and remains Under Review. Other combinations are role-compatible inferences, not established Kaboom meta. Player roster data was required to produce these actual alternatives."
    }


def _build_operational_output_base(question: str, core_evidence: List[Dict[str, Any]] | None = None, player_context: Dict[str, Any] | None = None, all_claims: List[Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
    profile=_profile_constraints(player_context)
    ql=question.lower()
    evidence=core_evidence or []
    profile=_profile_constraints(player_context)
    key=_event_key(question)
    wants_event = key is not None or any(x in ql for x in ("day by day","day-by-day","daily plan","event schedule","event plan","what should i do each day"))
    wants_shop = any(x in ql for x in ("shop","shops","store","stores","buy in different shops","what to buy"))
    wants_resource = any(x in ql for x in ("save","spend","resources","resource plan","resource allocation","what not to use"))
    wants_combo = any(x in ql for x in ("combo","team","lineup","champion")) and "kaboom" in ql
    if wants_combo:
        requested_options=_requested_option_count(question)
        if requested_options and player_context and isinstance(player_context.get("champion_levels"), dict):
            return _roster_kaboom_options(
                question,
                player_context,
                all_claims or core_evidence or [],
                requested_options
            )
        wants_five_lineups = bool(requested_options == 5 or re.search(r"\b5\b|five", ql)) and any(
            x in ql for x in ("line up", "lineup", "team", "combo")
        )
        if wants_five_lineups:
            return _verify_operational_output(question, {
                "mode":"event_combo_options",
                "title":"Kaboom, Robots! — 5 lineup options",
                "basis":"The current evidence corpus establishes one concrete community lineup. Four additional rows are roster-aware selection templates rather than invented champion combinations.",
                "core_evidence_count":len(evidence),
                "source_state":"COMMUNITY_ENRICHMENT",
                "columns":["Option","Lineup","Why","Evidence state","Selection state"],
                "rows":KABOOM_LINEUP_OPTIONS,
                "guardrail":"Only Lineup 1 is a named Kaboom community combination in the current corpus. Do not treat the four templates as validated champion combinations. Provide the player's available Champions/levels to resolve the placeholders into real alternatives without guessing."
            })
        return {
            "mode":"event_combo",
            "title":"Kaboom, Robots! — evidence-backed combo",
            "basis":"Official evidence establishes the event mechanics; no official 'best combo' claim was found. The lineup below is community evidence and remains Under Review.",
            "core_evidence_count":len(evidence),
            "source_state":"COMMUNITY_ENRICHMENT",
            "columns":["Aspect","Current answer","Why","Evidence state"],
            "rows":KABOOM_COMBO_ROWS,
            "guardrail":"Do not treat the community lineup as a canonical game rule. Re-check current Season 2/in-game behavior and your available Champion levels before committing resources."
        }
    if key == "shadowfront":
        p=PLAYBOOKS[key]
        return {
            "mode":"event_overview",
            "title":"Shadowfront — evidence-backed event overview",
            "basis":"Current canonical FGF evidence establishes Shadowfront facts; no day-by-day schedule is established in the current claim set.",
            "core_evidence_count":len(evidence),
            "source_state":"CANONICAL_CORE",
            "global_rules":[
                {"phase":"Established","action":"Shadowfront contains 8 Lesser Vaults and 2 Central Vaults."},
                {"phase":"Established","action":"Traders inside the Outer Rim Outpost Shadowfront cannot be attacked by other Commerce Guilds."},
                {"phase":"Current update","action":"Commerce Guild rewards in Shadowfront were increased in the September 22, 2026 hot update."},
            ],
            "columns":["Aspect","Current evidence","Evidence state"],
            "rows":[
                ["Vault structure","8 Lesser Vaults + 2 Central Vaults","Tier 1 — Confirmed"],
                ["Outer Rim Outpost","Traders inside it cannot be attacked by other Commerce Guilds","Tier 1 — Confirmed"],
                ["September 22, 2026 update","Commerce Guild rewards were increased","Tier 2 — Official Developer / Current"],
                ["Day-by-day schedule","Not established in current evidence","UNKNOWN — do not guess"],
            ],
            "guardrail":"Do not invent Shadowfront day objectives, timers, rewards or spending priorities that are not established by current evidence."
        }
    if key and wants_event:
        p=PLAYBOOKS[key]
        return {
            "mode":"event_day_plan",
            "title":p["name"]+" — operational plan",
            "basis":"Core evidence first; curated community guide used only as enrichment.",
            "core_evidence_count":len(evidence),
            "source_state":"COMMUNITY_ENRICHMENT",
            "source_note":p["source"],
            "global_rules":[
                {"phase":"Before event","action":p["global"]["before"]},
                {"phase":"During event","action":p["global"]["during"]},
                {"phase":"After event","action":p["global"]["after"]},
            ],
            "community_enrichment": ([
                {
                    "claim":"A community report associates Anti-Plunder Operation with Xarnas star capture, Solar Swords spawning, and a Prismatic Core usage unlock.",
                    "evidence_state":"Tier 3 — Creator/Community / Under Review",
                    "confidence":"Low",
                    "source":"User-provided Discord screenshot",
                    "raw_text":"Xarnas star capture - Solar swords spawn + prismatic core usage unlock + event",
                    "validation":"Needs Testing"
                }
            ] if key == "anti_plunder" else []),
            "columns":["Day","Objective","DO","SAVE","AVOID","Evidence state"],
            "rows":[[d["day"],d["objective"],d["do"],d["save"],d["avoid"],d["state"]] for d in p["days"]],
            "guardrail":"Any exact day mapping not established by authoritative current evidence is explicitly marked Not established; use the live in-game event/calendar for the server-specific objective."
        }
    if wants_shop:
        return {
            "mode":"shop_matrix",
            "title":"Shop-by-shop buying matrix",
            "basis":"Core evidence first; current shop inventory/value must be checked in-game.",
            "core_evidence_count":len(evidence),
            "source_state":"COMMUNITY_ENRICHMENT",
            "columns":["Shop","Priority / target","BUY WHEN","SAVE","AVOID","Evidence state"],
            "rows":[[x["shop"],x["priority"],x["buy_when"],x["save"],x["avoid"],x["state"]] for x in SHOP_ROWS],
            "guardrail":"This is a prioritization framework, not a claim that every listed item is currently stocked or priced this way. Verify the live shop inventory before purchase."
        }
    if wants_resource and any(x in ql for x in ("event","gvg","guild")):
        return {
            "mode":"resource_rules",
            "title":"Resource USE / SAVE / DON'T USE matrix",
            "basis":"Core evidence first; community guidance is labeled separately.",
            "core_evidence_count":len(evidence),
            "source_state":"COMMUNITY_ENRICHMENT",
            "columns":["Resource","USE","SAVE","DON'T USE","Evidence state"],
            "rows":[
                ["Speedups","Active objective/milestone that rewards the spend","For future event days and high-value milestones","Impulse spending outside an objective","COMMUNITY_GUIDE"],
                ["Champion XP","When the active objective explicitly rewards Champion progression","For relevant progression/event windows","Dumping XP only for points without a useful milestone","COMMUNITY_GUIDE"],
                ["Beacons","When the active objective or progression need supports them","For Beacon-focused objectives","Spending without checking upcoming objective value","COMMUNITY_GUIDE"],
                ["Computational Components","Only when the current objective clearly calls for them","For GvG/research objectives where applicable","Routine spending merely because the components are available","COMMUNITY_GUIDE"],
                ["Rare upgrade materials","When they advance a needed permanent upgrade and/or active objective","For strong milestones and scarce progression","Low-value event points","COMMUNITY_GUIDE"],
            ],
            "guardrail":"Exact quantities, point values and day assignments are not inferred unless established by evidence."
        }
    return None


def build_operational_output(question: str, core_evidence: List[Dict[str, Any]] | None = None,
                             player_context: Dict[str, Any] | None = None,
                             all_claims: List[Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
    """Public operational builder with a uniform player-context contract."""
    output=_build_operational_output_base(question, core_evidence, player_context, all_claims)
    if not output:
        return output
    profile=_profile_constraints(player_context)
    result=dict(output)
    result["player_context"]={
        "available":profile["available"],
        "season":profile["season"],
        "core_level":profile["core_level"],
        "flagship_level":profile["flagship_level"],
        "owned_champion_count":len(profile["owned_champions"]),
        "fleet_styles":profile["fleet_styles"],
        "resource_fields_present":sorted(profile["resources"].keys()),
        "preferences_present":sorted(profile["preferences"].keys()),
    }
    result["personalization_guardrail"]=_profile_guardrail(profile)
    return result
