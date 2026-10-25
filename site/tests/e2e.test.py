"""End-to-end: built app + local AI proxy + mock Gemini, in headless Chromium."""
import json, sys
from playwright.sync_api import sync_playwright
SITE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8963/"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/tmp/"
r = {}
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", is_mobile=True, has_touch=True)
    pg = ctx.new_page(); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "fonts" not in m.text and "ERR_TUNNEL" not in m.text and errs.append(m.text))
    pg.goto(SITE); pg.wait_for_function("document.querySelector('#mode').dataset.mode !== 'pending'", timeout=15000)
    r["mode"] = pg.inner_text("#mode-label")
    r["manifest_linked"] = pg.evaluate("!!document.querySelector('link[rel=manifest]')")
    man = pg.evaluate("fetch('manifest.webmanifest').then(r=>r.json())")
    r["manifest"] = {k: man[k] for k in ("name", "short_name", "display", "start_url")}
    r["icons_ok"] = pg.evaluate("Promise.all(['icons/icon-192.png','icons/icon-512.png','icons/maskable-512.png','icons/apple-touch-icon.png'].map(u=>fetch(u).then(r=>r.ok))).then(a=>a.every(Boolean))")
    r["title"] = pg.title()
    pg.click(".starter >> nth=1")   # T100
    pg.wait_for_selector(".turn .a[aria-busy=false]", timeout=20000)
    r["ai_answer"] = pg.inner_text(".turn .a-body")[:140]
    r["ai_checked"] = pg.inner_text(".turn .a-head")
    pg.screenshot(path=SHOTS + "app-phone-ai.png")
    # learning loop: rate the answer
    r["learning_notice"] = pg.is_visible("#foot-learning")
    pg.click(".turn >> nth=0 >> .fb-up")
    pg.wait_for_selector(".turn >> nth=0 >> text=Thanks for the feedback")
    # follow-up
    pg.fill("#question", "and on day 2?"); pg.press("#question", "Enter")
    pg.wait_for_function("document.querySelectorAll('.turn .a[aria-busy=false]').length==2", timeout=20000)
    r["followup_ok"] = "free AI" in pg.inner_text(".turn:nth-child(2) .a-body")
    # correction with a link
    pg.click(".turn:nth-child(2) .fb-fix")
    pg.fill(".turn:nth-child(2) .fb-form textarea", "Day 2 should save speedups for the build stage.")
    pg.fill(".turn:nth-child(2) .fb-form input", "https://www.foundation.game/en/news/t100")
    pg.click(".turn:nth-child(2) .fb-form button[type=submit]")
    pg.wait_for_selector(".turn:nth-child(2) >> text=Your correction will be checked")
    # a question the knowledge base can't answer is reported as a gap
    pg.fill("#question", "what does the zzqv flurbix wobblequark do for my account overall"); pg.press("#question", "Enter")
    pg.wait_for_function("document.querySelectorAll('.turn .a[aria-busy=false]').length==3", timeout=20000)
    pg.wait_for_timeout(500)
    import urllib.request
    fbk = json.loads(urllib.request.urlopen("http://127.0.0.1:8962/__counts").read())["feedback"]
    r["feedback_kinds"] = [x["kind"] for x in fbk]
    r["gap_hidden"] = "[[GAP]]" not in pg.inner_text(".turn:nth-child(3) .a-body") and "don't cover" in pg.inner_text(".turn:nth-child(3) .a-body")
    r["correction_row"] = next((x for x in fbk if x["kind"] == "correction"), {})
    pg.screenshot(path=SHOTS + "app-phone-feedback.png", full_page=False)
    # offline
    ctx.set_offline(True); pg.evaluate("window.dispatchEvent(new Event('offline'))"); pg.wait_for_timeout(200)
    r["offline_mode"] = pg.inner_text("#mode-label")
    pg.fill("#question", "how do I repair major damage"); pg.press("#question", "Enter")
    pg.wait_for_function("document.querySelectorAll('.turn .a[aria-busy=false]').length==4", timeout=10000)
    r["offline_answer_note"] = pg.inner_text(".turn:nth-child(4) .note")
    ctx.set_offline(False); pg.evaluate("window.dispatchEvent(new Event('online'))"); pg.wait_for_timeout(300)
    r["back_online_mode"] = pg.inner_text("#mode-label")
    r["errors"] = errs
    ctx.close()
    # proxy unreachable -> instant answers
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    ctx.route("http://127.0.0.1:8962/**", lambda route: route.abort())
    pg = ctx.new_page(); pg.goto(SITE)
    pg.wait_for_function("document.querySelector('#mode').dataset.mode !== 'pending'", timeout=15000)
    r["proxy_down_mode"] = pg.inner_text("#mode-label")
    pg.fill("#question", "migration permits"); pg.press("#question", "Enter")
    pg.wait_for_selector(".turn .a[aria-busy=false]", timeout=10000)
    r["proxy_down_answer"] = pg.inner_text(".turn .a-body")[:80]
    pg.screenshot(path=SHOTS + "app-desktop-instant.png")
    b.close()
print(json.dumps(r, indent=1, ensure_ascii=False))
