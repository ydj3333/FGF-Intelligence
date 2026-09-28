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
    return None

def build_operational_output(question: str, core_evidence: List[Dict[str, Any]] | None = None) -> Dict[str, Any] | None:
    ql=question.lower()
    evidence=core_evidence or []
    key=_event_key(question)
    wants_event = key is not None or any(x in ql for x in ("day by day","day-by-day","daily plan","event schedule","event plan","what should i do each day"))
    wants_shop = any(x in ql for x in ("shop","shops","store","stores","buy in different shops","what to buy"))
    wants_resource = any(x in ql for x in ("save","spend","resources","resource plan","resource allocation","what not to use"))
    wants_combo = any(x in ql for x in ("combo","team","lineup","champion")) and "kaboom" in ql
    if wants_combo:
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
