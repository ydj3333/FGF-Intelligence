#!/usr/bin/env python3
"""Daily learning run: turn what players tell the app into checked knowledge.

Reads new rows from Supabase public.app_feedback (written by the app's AI proxy):

  correction + link   -> the linked page/video is read and its facts go through the same checks
                         as the harvester (quote and every number must appear in the source;
                         duplicates skipped; contradictions with Tier 1/2 held back as
                         "Conflicting"). Player-submitted evidence always enters "Under Review":
                         players can point to evidence, but never change facts directly.
  correction, no link -> listed for the admin review (nothing changes).
  unanswered / 👎     -> grouped into knowledge gaps (data/knowledge_gaps.json) with counts, so
                         the team sees what players need; gaps are marked covered automatically
                         once the knowledge base has matching facts.
  👍 / 👎 on facts     -> facts that keep getting cited in unhelpful answers are flagged for re-checking.

Each processed row is marked processed with what happened. Writes data/learning_report.md.

Usage: python scripts/learn_from_players.py [--apply]
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import sys
import urllib.error
import urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("harvest_sources_for_learning", ROOT / "scripts/harvest_sources.py")
H = importlib.util.module_from_spec(spec)
spec.loader.exec_module(H)

GAPS_PATH = ROOT / "data/knowledge_gaps.json"
REPORT_PATH = ROOT / "data/learning_report.md"
MAX_LINKS_PER_RUN = 15
OFFICIAL_DOMAINS = ("foundation.game", "store.steampowered.com", "steamcommunity.com")
STOP = {"the", "and", "for", "what", "how", "best", "when", "does", "can", "should", "with", "this", "that", "are",
        "you", "fgf", "game", "get", "who", "why", "which", "where", "need", "want", "about", "there", "have", "has",
        "next", "much", "many", "way", "tell", "give", "please", "some", "any", "from", "into", "your", "my", "our"}
NOW = datetime.now(timezone.utc)


def stem(t: str) -> str:
    for suf in ("ing", "ed", "es", "s"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            return t[: -len(suf)]
    return t


def gap_tokens(q: str) -> list:
    return sorted({stem(t) for t in re.findall(r"[a-z0-9]+", H.norm(q)) if len(t) > 2 and t not in STOP})


def gap_key(q: str) -> str:
    return " ".join(gap_tokens(q))[:160]


def covered(tokens: list, corpus_tokens: list) -> bool:
    """A gap counts as covered once one fact contains all its (2+) significant words."""
    need = set(tokens)
    return len(need) >= 2 and any(need <= t for t in corpus_tokens)


def source_for(url: str, fid) -> dict:
    host = urllib.parse.urlparse(url).netloc.lower()
    official = any(host == d or host.endswith("." + d) for d in OFFICIAL_DOMAINS)
    tier, label = (2, "Tier 2 — Official Developer") if official else (3, "Tier 3 — Creator/Community")
    return {"id": f"PLAYER-{fid}", "name": f"Player correction #{fid} (source checked)", "tier": tier, "tier_label": label,
            "status": "Under Review", "extra_metadata": {"submitted_by": "player", "feedback_id": fid}}


def check_link(h, row: dict) -> dict:
    """Read the linked source and ingest its grounded facts. Returns a result dict."""
    url = row["source_url"]
    host = urllib.parse.urlparse(url).netloc.lower()
    if any(host == d or host.endswith("." + d) for d in H.LOGIN_WALLED):
        return {"action": "needs_screenshot", "note": "login-walled site: add a screenshot to inbox/ to use it"}
    src = source_for(url, row["id"])
    srep = h.source_report(src)
    page = {"url": url, "title": f"Player correction: {row.get('correction', '')[:120]}", "published": "", "render": False}
    yt = re.search(r"(?:youtube\.com/(?:watch\?v=|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})", url)
    text = ""
    if yt:
        page["video_url"] = "https://www.youtube.com/watch?v=" + yt.group(1)
        page["url"] = page["video_url"]
        src["tier"], src["tier_label"] = 3, "Tier 3 — Creator/Community"
    else:
        try:
            title, text, _ = H.html_to_text(H.fetch(url), url)
            if len(text) < 300:
                rendered = H.render(url)
                if len(rendered) > len(text):
                    text = rendered
        except Exception as e:
            return {"action": "unreadable", "note": f"{type(e).__name__}: {str(e)[:120]}"}
        page["title"] = (title or page["title"])[:200]
        text = text[:16000]
        if len(text) < 40:
            return {"action": "unreadable", "note": "no readable text on the page"}
    before = (h.report["inserted"], h.report["held_back"], h.report["duplicates"], h.report["rejected"])
    complete, info = h.process_page(src, page, srep, text)
    if not complete and not info.get("claims"):
        return {"action": "retry", "note": "; ".join(srep["notes"])[:200]}
    after = (h.report["inserted"], h.report["held_back"], h.report["duplicates"], h.report["rejected"])
    d = [a - b for a, b in zip(after, before)]
    return {"action": "checked", "tier": src["tier_label"], "new_facts": d[0], "held_back_conflicts": d[1],
            "already_known": d[2], "rejected_ungrounded": d[3]}


def fetch_new(base: str, key: str) -> list:
    q = urllib.parse.urlencode({"select": "*", "status": "eq.new", "order": "id.asc", "limit": "500"})
    return H.sb_request("GET", f"{base}/rest/v1/app_feedback?{q}", key, prefer="count=none") or []


def mark(base: str, key: str, ids: list, status: str, result: dict = None):
    if not ids:
        return
    body = {"status": status, "processed_at": NOW.isoformat()}
    if result is not None:
        body["result"] = result
    H.sb_request("PATCH", f"{base}/rest/v1/app_feedback?id=in.({','.join(str(i) for i in ids)})", key, body)


def run(apply: bool) -> dict:
    base, key = H.supabase()
    report = {"started_utc": NOW.isoformat(), "mode": "apply" if (apply and base and key) else "dry_run",
              "feedback_rows": 0, "links_checked": [], "corrections_for_review": [], "gaps_new": 0,
              "gaps_open": 0, "gaps_covered": 0, "flagged_facts": [], "inserted": 0, "notes": []}
    if not (base and key):
        report["notes"].append("Supabase key not set: nothing to learn from.")
        return report
    try:
        rows = fetch_new(base, key)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            report["notes"].append("Table app_feedback not found: run sql/app_feedback.sql once in Supabase (see SITE_SETUP.md).")
            return report
        raise
    report["feedback_rows"] = len(rows)
    h = H.Harvest(apply, {"max_claims_per_page": 25}, {"pages": {}})
    writing = h.writing

    # 1) corrections with links: check the evidence
    retry_ids, done = set(), 0
    for r in [x for x in rows if x.get("kind") == "correction" and x.get("source_url")]:
        if done >= MAX_LINKS_PER_RUN:
            retry_ids.add(r["id"])
            continue
        done += 1
        res = check_link(h, r)
        if res["action"] == "retry":
            retry_ids.add(r["id"])
        report["links_checked"].append({"id": r["id"], "question": r.get("question", "")[:160],
                                        "correction": r.get("correction", "")[:300], "url": r["source_url"], **res})
        if writing and res["action"] != "retry":
            mark(base, key, [r["id"]], "processed", res)

    # 2) corrections without links: kept for the admin review (nothing changes on their own)
    gaps = H.load_json(GAPS_PATH, {"gaps": {}})
    gaps.setdefault("gaps", {})
    pending = gaps.setdefault("corrections_pending_review", [])
    for r in [x for x in rows if x.get("kind") == "correction" and not x.get("source_url")]:
        item = {"id": r["id"], "date": str(r.get("created_at") or NOW.isoformat())[:10], "question": r.get("question", "")[:160],
                "correction": r.get("correction", "")[:300], "about": (r.get("cited_facts") or [])[:3]}
        report["corrections_for_review"].append(item)
        if not any(p.get("id") == r["id"] for p in pending):
            pending.append(item)
    gaps["corrections_pending_review"] = pending[-200:]
    report["corrections_pending_total"] = len(gaps["corrections_pending_review"])

    # 3) knowledge gaps from unanswered questions and unhelpful answers
    for r in rows:
        if r.get("kind") not in ("unanswered", "not_helpful"):
            continue
        k = gap_key(r.get("question", ""))
        if not k:
            continue
        g = gaps["gaps"].get(k)
        if not g:
            report["gaps_new"] += 1
            g = gaps["gaps"][k] = {"example": r.get("question", "")[:300], "count": 0, "unanswered": 0, "not_helpful": 0,
                                   "first_seen": str(r.get("created_at") or NOW.isoformat())[:10], "status": "open"}
        g["count"] += 1
        g[r["kind"]] = g.get(r["kind"], 0) + 1
        g["last_seen"] = str(r.get("created_at") or NOW.isoformat())[:10]
        if g.get("status") == "covered":
            g["status"] = "open"        # asked again after being covered: check it really is answerable
    corpus_tokens = [{stem(x) for x in t} for _, t, _, _ in h.corpus.items]
    for k, g in gaps["gaps"].items():
        if g.get("status") == "open" and covered(k.split(), corpus_tokens):
            g["status"], g["covered_on"] = "covered", NOW.strftime("%Y-%m-%d")
    report["gaps_open"] = sum(1 for g in gaps["gaps"].values() if g.get("status") == "open")
    report["gaps_covered"] = sum(1 for g in gaps["gaps"].values() if g.get("status") == "covered")
    gaps["updated_utc"] = NOW.isoformat()

    # 4) facts that keep appearing in unhelpful answers
    votes = defaultdict(Counter)
    for r in rows:
        if r.get("kind") in ("helpful", "not_helpful"):
            for f in r.get("cited_facts") or []:
                votes[f][r["kind"]] += 1
    history = gaps.setdefault("fact_votes", {})
    for f, c in votes.items():
        v = history.setdefault(f[:400], {"helpful": 0, "not_helpful": 0})
        v["helpful"] += c["helpful"]
        v["not_helpful"] += c["not_helpful"]
    report["flagged_facts"] = sorted(([f, v["helpful"], v["not_helpful"]] for f, v in history.items()
                                      if v["not_helpful"] >= 3 and v["not_helpful"] >= 2 * v["helpful"] + 1),
                                     key=lambda x: -x[2])[:30]

    report["inserted"] = h.report["inserted"]
    report["new_claims"] = h.report["new_claims"]
    if writing:
        GAPS_PATH.write_text(json.dumps(gaps, ensure_ascii=False, indent=1), encoding="utf-8")
        handled = {x["id"] for x in report["links_checked"]} | retry_ids
        mark(base, key, [r["id"] for r in rows if r["id"] not in handled], "processed")
    report["top_gaps"] = sorted(([g["example"], g["count"], k] for k, g in gaps["gaps"].items() if g.get("status") == "open"),
                                key=lambda x: -x[1])[:25]
    return report


def markdown(r: dict) -> str:
    out = [f"# FGF learning report ({r['started_utc'][:16].replace('T', ' ')} UTC, {r['mode']})", "",
           f"Player feedback read: **{r['feedback_rows']}**. New facts from player-linked sources: **{r['inserted']}** (all *Under Review*).",
           f"Knowledge gaps: **{r['gaps_open']}** open ({r['gaps_new']} new), {r['gaps_covered']} now covered.", ""]
    for n in r["notes"]:
        out.append(f"> {n}")
    if r["links_checked"]:
        out += ["## Corrections with a source link", "", "| # | Correction | Source | Result |", "|---|---|---|---|"]
        for x in r["links_checked"]:
            res = (f"{x.get('new_facts', 0)} new, {x.get('held_back_conflicts', 0)} conflicts held for review, "
                   f"{x.get('already_known', 0)} already known") if x["action"] == "checked" else f"{x['action']}: {x.get('note', '')}"
            out.append(f"| {x['id']} | {x['correction'].replace('|', '/')} | {x['url']} | {res} |")
        out.append("")
    if r["corrections_for_review"]:
        out += [f"## New corrections without a link (admin review; {r.get('corrections_pending_total', 0)} pending in data/knowledge_gaps.json)", ""]
        out += [f"- #{x['id']} on “{x['question']}”: {x['correction']}" for x in r["corrections_for_review"]]
        out.append("")
    if r.get("top_gaps"):
        out += ["## What players ask that the app can't answer well", "", "| Times asked | Example question |", "|---|---|"]
        out += [f"| {c} | {q.replace('|', '/')} |" for q, c, _ in r["top_gaps"]]
        out.append("")
    if r["flagged_facts"]:
        out += ["## Facts to re-check (often cited in unhelpful answers)", "", "| 👍 | 👎 | Fact |", "|---|---|---|"]
        out += [f"| {u} | {d} | {f.replace('|', '/')} |" for f, u, d in r["flagged_facts"]]
        out.append("")
    if r.get("new_claims"):
        out += ["## New facts", ""] + [f"- {c.get('claim', c) if isinstance(c, dict) else c}" for c in r["new_claims"][:40]]
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    r = run(args.apply)
    md = markdown(r)
    if r["mode"] == "apply":
        REPORT_PATH.write_text(md, encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as f:
            f.write(md)
    if os.getenv("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"inserted={r['inserted']}\n")
    print(md)


if __name__ == "__main__":
    sys.exit(main())
