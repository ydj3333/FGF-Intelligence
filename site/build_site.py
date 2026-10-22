#!/usr/bin/env python3
"""Build the FGF Intelligence app from the repository's live knowledge data.

Outputs (default site/dist/):
  index.html            the installable web app (GitHub Pages)
  manifest.webmanifest  app name, colours, icons (makes it installable)
  sw.js                 offline support + automatic updates
  icons/*.png           home-screen icons
  fgf-data.json         the data bundle (also embedded in index.html)
  artifact.html         the same app for Claude hosting (no install/offline features)

Usage:
  python site/build_site.py [--repo .] [--out site/dist]
  env FGF_AI_ENDPOINT=https://fgf-ai.<you>.workers.dev   (optional: enables free AI answers)

Standard library only, except Pillow for icons (optional: icons are skipped if missing).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent

CATEGORY_FIX = {"event": "Events", "ui": "Interface", "technical": "Technical", "general": "General"}
PLAN_QUESTIONS = [
    ("t100", "best way to do T100", ["t100", "top 100", "galactic traders"]),
    ("t100-days", "Top 100 Galactic Traders day by day plan", ["t100", "top 100", "day by day", "day plan"]),
    ("gvg", "best way to approach GvG", ["gvg", "guild vs guild", "guild versus guild"]),
    ("shadowfront", "best way to do Shadowfront", ["shadowfront"]),
    ("dominance", "best way to do Paths to Dominance", ["paths to dominance", "path to dominance", "dominance"]),
    ("kaboom", "kaboom robots best lineup", ["kaboom", "robots"]),
]


def clean(s, n):
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def tier_of(t):
    m = re.search(r"(?:tier|t)\s*([1-5])", str(t or "").lower())
    return int(m.group(1)) if m else 4


def category(c):
    g = clean(c, 40) or "General"
    return CATEGORY_FIX.get(g.lower(), g[:1].upper() + g[1:])


def build_bundle(repo: Path) -> dict:
    sys.path.insert(0, str(repo))
    cwd = os.getcwd()
    os.chdir(repo)
    try:
        from claim_lifecycle import normalize_state
        try:
            from operational_intelligence import build_operational_output
        except Exception:  # plans are optional
            build_operational_output = None
        data = json.loads((repo / "data/knowledge.json").read_text(encoding="utf-8"))
        manifest = json.loads((repo / "data/knowledge_manifest.json").read_text(encoding="utf-8")) if (repo / "data/knowledge_manifest.json").exists() else {}
        guides_path = repo / "data/verified_guides.json"
        guides_src = json.loads(guides_path.read_text(encoding="utf-8")) if guides_path.exists() else {}

        facts, seen = [], set()

        def add(c):
            claim = clean(c.get("Claim"), 400)
            if not claim:
                return
            state = getattr(normalize_state(c.get("Status")), "value", str(c.get("Status")))
            if state in ("rejected", "superseded", "archived"):
                return
            key = re.sub(r"\W+", " ", claim.lower()).strip()
            if key in seen:
                return
            seen.add(key)
            src = str(c.get("Source", ""))
            facts.append({
                "c": claim, "g": category(c.get("Category")), "t": tier_of(c.get("Evidence Tier")),
                "tl": clean(c.get("Evidence Tier"), 40), "s": state, "f": clean(c.get("Confidence"), 12),
                "v": clean(c.get("Season/Version"), 40),
                "u": clean(src, 300) if src.startswith("http") else clean(src, 80),
                "n": clean(c.get("Notes"), 220),
            })

        for c in data.get("claims", []):
            add(c)
        for g in guides_src.get("guides", []):
            for text in g.get("claims", []):
                add({"Claim": text, "Category": g.get("title", "Guide"), "Evidence Tier": "Tier 2 — Official FGF Wiki",
                     "Status": "confirmed", "Confidence": "High", "Source": g.get("source", ""), "Notes": g.get("source_title", "")})

        conflicts = [{k: clean(c.get(src), 400) for k, src in (
            ("id", "Conflict ID"), ("topic", "Topic"), ("official", "Tier-1 evidence"),
            ("other", "Existing / Tier-2 claim"), ("decision", "Decision"), ("notes", "Notes"))}
            for c in data.get("conflicts", [])]

        plans = []
        if build_operational_output:
            for key, q, keywords in PLAN_QUESTIONS:
                try:
                    o = build_operational_output(q, []) or {}
                except Exception:
                    continue
                rows = o.get("rows") or []
                if not rows:
                    continue
                plans.append({
                    "id": key, "title": clean(o.get("title"), 120),
                    "summary": clean(o.get("recommendation") or o.get("basis"), 900),
                    "headers": o.get("headers") or o.get("columns") or [],
                    "rows": [[clean(x, 400) for x in r] for r in rows],
                    "keywords": keywords, "source_state": clean(o.get("source_state"), 80),
                })
    finally:
        os.chdir(cwd)

    return {
        "meta": {"synced": manifest.get("synced_at_utc") or data.get("generated"), "source": manifest.get("source_of_truth", "knowledge.json"),
                 "facts": len(facts), "tier1": sum(1 for f in facts if f["t"] == 1),
                 "official": sum(1 for f in facts if f["t"] <= 2), "conflicts": len(conflicts), "plans": len(plans)},
        "facts": facts, "conflicts": conflicts, "plans": plans,
    }


def assemble(bundle: dict, config: dict) -> str:
    page = (HERE / "src/page.html").read_text(encoding="utf-8")
    engine = (HERE / "src/engine.js").read_text(encoding="utf-8")
    app = (HERE / "src/app.js").read_text(encoding="utf-8")
    safe = lambda s: s.replace("</", "<\\/")  # never close a <script> early
    data = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    out = (page.replace("{{CONFIG}}", safe(json.dumps(config)))
               .replace("{{DATA}}", safe(data))
               .replace("{{ENGINE}}", safe(engine))
               .replace("{{APP}}", safe(app)))
    assert "{{" not in out.split("<script")[0], "unfilled placeholder"
    return out


APP_HEAD = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#f3f5fa" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0b1020" media="(prefers-color-scheme: dark)">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-title" content="FGF Intel">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<link rel="manifest" href="manifest.webmanifest">
<link rel="icon" type="image/png" sizes="192x192" href="icons/icon-192.png">
<link rel="apple-touch-icon" href="icons/apple-touch-icon.png">
<style>:root{color-scheme:light;padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
body{margin:0}img{max-width:100%}[hidden]{display:none!important}</style>
</head>
<body>
"""

SW_TEMPLATE = r"""/* FGF Intelligence service worker: offline support and automatic updates. */
const VERSION = "__VERSION__";
const CACHE = "fgf-app-" + VERSION;
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "icons/icon-512.png", "icons/apple-touch-icon.png"];

self.addEventListener("install", (event) => {
  event.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", (event) => {
  event.waitUntil(caches.keys().then((keys) => Promise.all(keys.filter((k) => k.startsWith("fgf-app-") && k !== CACHE).map((k) => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("message", (event) => { if (event.data === "skip-waiting") self.skipWaiting(); });

const FONT_HOSTS = ["fonts.googleapis.com", "fonts.gstatic.com"];
self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);
  // The app page: newest copy when online (fresh game data), cached copy when offline.
  if (req.mode === "navigate" || (url.origin === location.origin && (url.pathname.endsWith("/") || url.pathname.endsWith("index.html")))) {
    event.respondWith((async () => {
      try {
        const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 4000);
        const fresh = await fetch(req, { signal: ctl.signal }); clearTimeout(timer);
        if (fresh.ok) { const c = await caches.open(CACHE); c.put("index.html", fresh.clone()); }
        return fresh;
      } catch (e) {
        return (await caches.match("index.html")) || (await caches.match("./")) || Response.error();
      }
    })());
    return;
  }
  // Fonts: serve cached, refresh in the background.
  if (FONT_HOSTS.includes(url.hostname)) {
    event.respondWith(caches.open(CACHE).then(async (c) => {
      const hit = await c.match(req);
      const net = fetch(req).then((r) => { if (r.ok || r.type === "opaque") c.put(req, r.clone()); return r; }).catch(() => hit);
      return hit || net;
    }));
    return;
  }
  // Icons and manifest: cache first. Everything else (the AI service) goes straight to the network.
  if (url.origin === location.origin) event.respondWith(caches.match(req).then((hit) => hit || fetch(req)));
});
"""


def make_icons(out: Path) -> bool:
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        print("Pillow not installed: icons skipped")
        return False
    import math
    icons = out / "icons"
    icons.mkdir(parents=True, exist_ok=True)

    def draw(size, pad_ratio):
        S = size * 4
        img = Image.new("RGBA", (S, S), (11, 16, 32, 255))
        d = ImageDraw.Draw(img)
        c = S / 2
        r = S * (0.5 - pad_ratio)
        w = max(4, int(S * 0.035))
        d.ellipse([c - r, c - r, c + r, c + r], outline=(39, 51, 79, 255), width=w)
        # tilted orbit: draw a clean ellipse on its own layer, then rotate it
        orbit = Image.new("RGBA", (S, S), (0, 0, 0, 0))
        ImageDraw.Draw(orbit).ellipse([c - r, c - r * 0.4, c + r, c + r * 0.4], outline=(242, 181, 68, 255), width=w)
        img.alpha_composite(orbit.rotate(24, resample=Image.BICUBIC, center=(c, c)))
        d = ImageDraw.Draw(img)
        pr = r * 0.30
        d.ellipse([c - pr, c - pr, c + pr, c + pr], fill=(95, 212, 200, 255))
        a = math.radians(24)
        mx, my, mr = c + r * math.cos(a), c - r * math.sin(a), r * 0.16
        d.ellipse([mx - mr, my - mr, mx + mr, my + mr], fill=(242, 181, 68, 255))
        return img.resize((size, size), Image.LANCZOS)

    draw(192, 0.12).save(icons / "icon-192.png")
    draw(512, 0.12).save(icons / "icon-512.png")
    draw(512, 0.22).save(icons / "maskable-512.png")   # safe zone for Android adaptive icons
    draw(180, 0.14).convert("RGB").save(icons / "apple-touch-icon.png")
    return True


def write_app(out: Path, bundle: dict, ai_endpoint: str) -> str:
    out.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))
    version = hashlib.sha1((data_json + ai_endpoint + "".join(
        (HERE / "src" / f).read_text(encoding="utf-8") for f in ("page.html", "engine.js", "app.js"))).encode()).hexdigest()[:12]
    config = {"aiEndpoint": ai_endpoint, "pwa": True, "version": version}
    html = APP_HEAD + assemble(bundle, config) + "\n</body>\n</html>\n"
    (out / "index.html").write_text(html, encoding="utf-8")
    (out / "fgf-data.json").write_text(data_json, encoding="utf-8")
    (out / "sw.js").write_text(SW_TEMPLATE.replace("__VERSION__", version), encoding="utf-8")
    manifest = {
        "name": "FGF Intelligence", "short_name": "FGF Intel",
        "description": "Fact-checked answers, event guides and a fact library for Foundation: Galactic Frontier.",
        "id": "./", "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#0b1020", "theme_color": "#0b1020", "orientation": "any",
        "categories": ["games", "utilities"],
        "icons": [
            {"src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png"},
            {"src": "icons/maskable-512.png", "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }
    (out / "manifest.webmanifest").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    make_icons(out)
    # Claude-hosted variant: same app, no install/offline features (that host provides AI via Claude).
    (out / "artifact.html").write_text(assemble(bundle, {"aiEndpoint": "", "pwa": False, "version": version}), encoding="utf-8")
    return version


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(HERE.parent))
    ap.add_argument("--out", default=str(HERE / "dist"))
    args = ap.parse_args()
    ai = os.getenv("FGF_AI_ENDPOINT", "").strip()
    if ai and not re.match(r"^https://[A-Za-z0-9.-]+(?::\d+)?(/[\w./-]*)?$", ai) and not ai.startswith("http://127.0.0.1"):
        raise SystemExit("FGF_AI_ENDPOINT must be an https URL")
    bundle = build_bundle(Path(args.repo).resolve())
    version = write_app(Path(args.out), bundle, ai)
    size = (Path(args.out) / "index.html").stat().st_size // 1024
    print(json.dumps({"built": str(args.out), "version": version, "index_kb": size, "ai_endpoint": ai or None,
                      "built_at": datetime.now(timezone.utc).isoformat(), **bundle["meta"]}))


if __name__ == "__main__":
    main()
