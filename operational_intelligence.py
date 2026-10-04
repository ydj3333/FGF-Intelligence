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

CURRENT_WEB_CONTEXT = {
    "season2_schedule": "Season 2 event timing varies by server; use the in-game calendar for the server-specific schedule. Do not infer a date from general cadence.",
    "paths_duration": "Current FGF Wiki event index lists Paths to Dominance as a 24-hour Major Event / Fortress Conquest.",
    "paths_scoring_update": "Release notes for v1.1.44 state that PvP battles in Level 9 star systems grant Paths to Dominance event points.",
    "prince_decree_update": "Release notes for v1.1.36 state that Prince's Decree use counts increased and Prince buff effects/cooldowns no longer reset when Paths to Dominance begins; bounty effects still clear on reset.",
    "season2_map": "Current Season 2 guidance states Paths to Dominance persists on the Siwenna map.",
    "fleet_mechanics": {
        "energy_types": "Beam > Kinetic > Ionic > Beam counter cycle.",
        "energy_advantage": "+5% damage when the Energy Type has the matchup advantage.",
        "champion_synergy": "2 matching Champions: +10% ATK/DEF/INT; 3 matching Champions: +20% ATK/DEF/INT.",
        "skill_order": "Champion skills activate left-to-right in formation order."
    },
    "lifecycle_warning": "The Sep 9 official Epoch of Fusion Seed guide recorded a 60% Combat Craft Modification prerequisite; the Sep 22 hot update reduced it to 40%. Treat 40% as current and 60% as superseded."
}


PLAYBOOKS = {
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
    if any(x in ql for x in ("paths to dominance","path to dominance","trader prince","prince ability","prince tributes")): return "path_to_dominance"
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



KABOOM_CHAMPION_ALIASES = {
    "Zora Dominii": ("zora dominii", "zora"),
    "Lily": ("lily",),
    "Jodie Beart": ("jodie beart", "jodie"),
    "Kama Moai": ("kama moai", "kama", "kameni"),
    "Evan Rogers": ("evan rogers", "evan"),
}

def _extract_player_roster(question: str) -> List[str]:
    """Extract explicitly named player-owned Champions from an operational query.

    This is intentionally conservative: only known Champion aliases are resolved.
    A roster constraint must override generic 'best combo' retrieval.
    """
    ql = question.lower()
    found = []
    aliases = sorted(
        ((alias, canonical) for canonical, names in KABOOM_CHAMPION_ALIASES.items() for alias in names),
        key=lambda x: len(x[0]),
        reverse=True,
    )
    for alias, canonical in aliases:
        if re.search(r"(?<![a-z0-9])" + re.escape(alias) + r"(?![a-z0-9])", ql):
            if canonical not in found:
                found.append(canonical)
    return found

def _kaboom_roster_answer(question: str, roster: List[str], evidence_count: int) -> Dict[str, Any]:
    """Use the generic v7 strategy engine for a roster-constrained event decision."""
    event = build_event_model(
        "kaboom_robots",
        objective="clear robot waves and maximize kills",
        scoring_factors=("kills",),
        tactical_priorities=("AOE", "grouping", "stun"),
        duration="48h",
        evidence_state="tier 2",
    )
    player = PlayerState(owned_entities=tuple(roster))

    # These candidates are evidence-derived roles, not an exhaustive global
    # roster. The engine filters first, so a generic Jodie recommendation can
    # never override an explicit player-owned roster.
    role_map = {
        "Zora Dominii": ("grouping", "Group robot waves so area damage can hit clustered targets."),
        "Lily": ("AOE", "Primary burst area damage against grouped robot waves."),
        "Jodie Beart": ("AOE", "Community evidence reports extra damage against grouped targets."),
        "Kama Moai": ("stun", "Use control/stun to help keep the wave contained."),
        "Evan Rogers": ("damage", "Damage-oriented option; current Kaboom evidence does not establish a specific slot role."),
    }
    candidates = []
    for champion in ("Zora Dominii", "Lily", "Jodie Beart", "Kama Moai", "Evan Rogers"):
        if champion in role_map:
            tag, rationale = role_map[champion]
            candidates.append(
                CandidateAction(
                    name=champion,
                    entities=(champion,),
                    tags=(tag,),
                    evidence_state="tier 2",
                    rationale=rationale,
                )
            )

    decision = decide(event, player, candidates, limit=3)
    selected = [x.name for x in decision.selected]

    # Preserve the user's requested positional answer while making the
    # positional ordering an explicit tactical inference, not an invented
    # official slot mechanic.
    preferred_order = ["Zora Dominii", "Lily", "Kama Moai"]
    ordered = [x for x in preferred_order if x in selected]
    ordered += [x for x in selected if x not in ordered]

    role_text = {
        "Zora Dominii": ("Position 1", "Group / cluster", "Start by grouping the wave."),
        "Lily": ("Position 2", "AOE burst", "Follow the grouping with burst AOE."),
        "Kama Moai": ("Position 3", "Control / stun", "Use control to contain the remaining wave."),
        "Jodie Beart": ("Position", "Cluster damage", "Community evidence supports grouped-target damage."),
        "Evan Rogers": ("Position", "Damage", "Current Kaboom evidence does not establish an exact slot role."),
    }
    rows = []
    for champion in ordered:
        pos, role, why = role_text[champion]
        rows.append([pos, champion, role, why, "Tactical inference — exact slot order not established"])

    return {
        "mode": "event_strategy_engine",
        "title": "Kaboom, Robots! — roster-constrained strategy",
        "basis": "v7 Event Strategy Engine: event mechanics are evaluated against the player's explicit roster before ranking recommendations.",
        "core_evidence_count": evidence_count,
        "event_model": {
            "event": event.event_key,
            "objective": event.objective,
            "scoring_factors": list(event.scoring_factors),
            "tactical_priorities": list(event.tactical_priorities),
            "duration": event.duration,
        },
        "player_roster": roster,
        "selection": ordered,
        "columns": ["Position", "Champion", "Role", "Why", "Position confidence"],
        "rows": rows,
        "rejected_candidates": list(decision.rejected),
        "confidence": decision.confidence,
        "recommendation": (
            "For the supplied roster, the recommended sequence is Zora → Lily → Kama: "
            "group → burst AOE → control. The exact positional order is a tactical inference, "
            "not an official slot-order mechanic in the current evidence."
        ),
        "guardrail": "Do not silently substitute a Champion outside the player's explicit roster.",
    }

def build_operational_output(question: str, core_evidence: List[Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
    ql=question.lower()
    evidence=core_evidence or []
    key=_event_key(question)
    wants_event = key is not None or any(x in ql for x in ("day by day","day-by-day","daily plan","event schedule","event plan","what should i do each day"))
    wants_shop = any(x in ql for x in ("shop","shops","store","stores","buy in different shops","what to buy"))
    wants_resource = any(x in ql for x in ("save","spend","resources","resource plan","resource allocation","what not to use"))
    wants_combo = any(x in ql for x in ("combo","team","lineup","champion","position","order")) and "kaboom" in ql
    if wants_combo:
        roster = _extract_player_roster(question)
        asks_for_position = bool(re.search(r"\b(position|order|slot|where|keep)\b", ql))
        if roster and asks_for_position:
            return _kaboom_roster_answer(question, roster, len(evidence))
        wants_five_lineups = bool(re.search(r"\b5\b|five", ql)) and any(
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
    if key == "path_to_dominance":
        return {
            "mode":"event_operational_overview",
            "title":"Paths to Dominance — Trader Prince operational intelligence",
            "basis":"Primary in-game UI evidence from the supplied Path to Dominance document. Exact event dates were not supplied and are intentionally not inferred.",
            "core_evidence_count":len(evidence),
            "source_state":"PRIMARY_IN_GAME_UI",
            "current_web_context": CURRENT_WEB_CONTEXT,
            "global_rules":[
                {"phase":"Cadence","action":"Competition occurs every two weeks."},
                {"phase":"Postponement","action":"If Dominion Warzone occurs that week, the competition on that server is postponed by one week."},
                {"phase":"Competition","action":"Control of the highest-level star system's Star Space Station determines the Trader Prince competition; competition lasts up to 24 hours."},
                {"phase":"Appointment","action":"Winning Commerce Guild chairman has 24 hours to appoint a Commerce Guild member as Trader Prince; otherwise the chairman assumes the title."},
                {"phase":"Reset","action":"Appointments and Prince Ability effects reset when the next competition begins."},
            ],
            "position_rules":[
                ["Eligibility","Energy Core level 16+ required to apply","Tier 1 — in-game UI"],
                ["Applications","Only one Counselor position may be applied for or held at a time","Tier 1 — in-game UI"],
                ["Capacity","Up to 50 applications per position; full positions lock submissions","Tier 1 — in-game UI"],
                ["Cooldown","30 minutes between position applications","Tier 1 — in-game UI"],
                ["Rejection","Cannot reapply for that position for the remainder of the day","Tier 1 — in-game UI"],
                ["Appointment","Minimum appointment duration is 5 minutes; can continue indefinitely if no replacement is approved","Tier 1 — in-game UI"],
                ["Control","Trader Prince/Acting Prince can appoint; Trader Prince can remove a player","Tier 1 — in-game UI"],
            ],
            "positions":["Strategic Counselor","Acting Prince","Military Counselor","Construction Counselor","Research Counselor","Counselor of Internal Affairs"],
            "abilities":[
                ["Commission","Issues a quest to all Korell traders to submit Unity Points","10/10 shown","Tier 1 — in-game UI"],
                ["Treasure","Places a Prince's Treasure near the Ascendancy Fortress","4/4 shown","Tier 1 — in-game UI"],
                ["Dividend","Spends Unity Points to gain 2,000 Credits","10/10 shown","Tier 1 — in-game UI"],
                ["Prosperity","Basic trade resource earnings +15% for all Korell traders for 24 hours","4/4 shown","Tier 1 — in-game UI"],
                ["Safeguard","Major Damage Points -10% for all Korell traders for 24 hours","4/4 shown","Tier 1 — in-game UI"],
                ["Advance","Fleet Attack +15% for all Korell traders for 24 hours","4/4 shown","Tier 1 — in-game UI"],
                ["Assistance","Building Speed +10% for all Korell traders for 24 hours","4/4 shown","Tier 1 — in-game UI"],
                ["Knowledge","Research Speed +10% for all Korell traders for 24 hours","4/4 shown","Tier 1 — in-game UI"],
                ["Mobilization","Combat Craft Manufacturing Speed +10% for all Korell traders for 24 hours","4/4 shown","Tier 1 — in-game UI"],
                ["Traderhunt","Wanted notice; marks and slows a trader and prevents Interstellar Shelter triggering","50/50 shown; duration not stated","Tier 1 — in-game UI"],
            ],
            "scoring":[
                ["Leaderboard threshold","1,000 points minimum to claim leaderboard rewards","Tier 1 — in-game UI"],
                ["Rank bands","1, 2, 3, 4-10, 11-30, 31-50","Tier 1 — in-game UI"],
                ["Unranked","No ranking rewards","Tier 1 — in-game UI"],
                ["Participation bands","50K-150K; 150K-300K; 300K-480K; 480K-700K; 700K-1M; >1M","Tier 1 — in-game UI"],
                ["Reward delivery","Participation rewards sent by mail after battle ends","Tier 1 — in-game UI"],
            ],
            "guardrail":"Do not invent event start/end dates, exact reward names from unidentified icons, Traderhunt duration, or Unity Point costs that are not explicitly legible in the supplied evidence."
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
