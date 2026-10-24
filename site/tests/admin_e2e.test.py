"""End-to-end: the owner's review page against the local stack (proxy + fake Supabase), in headless Chromium."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

SITE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8963/"
SHOTS = sys.argv[2] if len(sys.argv) > 2 else "/tmp/"
DB = lambda: json.loads(urllib.request.urlopen("http://127.0.0.1:8962/__db").read())
claim = lambda i: next(c for c in DB()["claims"] if c["id"] == i)
r, errs = {}, []


def count(pg, k):
    return pg.inner_text(f'[data-count="{k}"]')


def toast(pg):
    pg.wait_for_selector("#toast:not([hidden])", timeout=8000)
    t = pg.inner_text("#toast")
    pg.evaluate("document.querySelector('#toast').hidden = true")
    return t


with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 390, "height": 844}, color_scheme="dark", is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("console", lambda m: m.type == "error" and "fonts" not in m.text and "ERR_TUNNEL" not in m.text and "401" not in m.text and "409" not in m.text and errs.append(m.text))
    pg.goto(SITE + "admin.html")
    pg.wait_for_selector("#login-view:not([hidden])")
    # wrong password
    pg.fill("#password", "guess"); pg.click("#login-form button[type=submit]")
    pg.wait_for_selector("#login-error:not([hidden])")
    r["wrong_password"] = pg.inner_text("#login-error")
    pg.fill("#password", "local test password"); pg.click("#login-form button[type=submit]")
    pg.wait_for_selector("#panel-view:not([hidden])")
    pg.wait_for_function("document.querySelector('[data-count=review]').textContent === '3'")
    r["counts"] = {k: count(pg, k) for k in ("review", "conflicts", "corrections", "gaps")}
    pg.wait_for_selector(".item")
    r["review_items"] = pg.eval_on_selector_all(".item .text", "els => els.map(e => e.textContent)")
    r["video_chip"] = pg.is_visible("text=watched video @ 01:15")
    pg.screenshot(path=SHOTS + "review-phone.png")

    # stays signed in on reload (session), then search filter
    pg.reload(); pg.wait_for_selector("#panel-view:not([hidden])"); pg.wait_for_selector(".item")
    pg.fill("#q", "kaboom"); pg.wait_for_function("document.querySelectorAll('.item').length === 2")
    pg.fill("#q", ""); pg.wait_for_function("document.querySelectorAll('.item').length === 3")

    # bulk approve two, Tier 1 needs proof
    items = pg.query_selector_all(".item")
    texts = [i.inner_text() for i in items]
    k_idx = next(n for n, t in enumerate(texts) if "Kaboom starts" in t)
    z_idx = next(n for n, t in enumerate(texts) if "Zora" in t)
    items[k_idx].query_selector(".pick").check(); items[z_idx].query_selector(".pick").check()
    r["bulk_label"] = pg.inner_text("#bulk-approve")
    pg.click("#bulk-approve")
    r["bulk_toast"] = toast(pg)
    pg.wait_for_function("document.querySelectorAll('.item').length === 1")
    r["after_bulk"] = [claim(1)["status"], claim(2)["status"]]
    pg.click(".item >> text=Approve as Tier 1…")
    pg.fill(".proof textarea", "short"); pg.click("text=Confirm Tier 1")
    r["tier1_short_proof"] = toast(pg)
    pg.fill(".proof textarea", "Seen in the in-game shop on 24 Oct"); pg.click("text=Confirm Tier 1")
    r["tier1_toast"] = toast(pg)
    pg.wait_for_selector("text=All done here")
    r["tier1"] = [claim(3)["tier"], claim(3)["status"], claim(3)["metadata"]["tier1_proof"]]

    # dispute
    pg.click('.adm-tab[data-type="conflicts"]'); pg.wait_for_selector(".versus")
    r["dispute_shows_both"] = "12 Migration" in pg.inner_text(".versus .new") and "10 Migration" in pg.inner_text(".versus .old")
    pg.screenshot(path=SHOTS + "review-dispute.png")
    pg.click("text=Accept new, retire old"); toast(pg)
    pg.wait_for_selector("text=All done here")
    r["dispute"] = [claim(4)["status"], claim(5)["status"]]

    # player correction -> add as a fact
    pg.click('.adm-tab[data-type="corrections"]'); pg.wait_for_selector(".item")
    pg.click("text=Add as a fact…")
    pg.wait_for_selector("#add-view:not([hidden])")
    r["add_context"] = pg.inner_text("#add-context")
    pg.fill("#f-claim", "Day 3 of Top 100 Galactic Traders is the building day.")
    pg.select_option("#f-category", "Events")
    pg.fill("#f-source", "https://www.foundation.game/en/news/t100")
    pg.click("#add-form button[type=submit]")
    r["fact_toast"] = toast(pg)
    db = DB()
    new = [c for c in db["claims"] if c["claim_key"].startswith("admin-")]
    r["added_fact"] = [new[0]["claim"], new[0]["tier"], new[0]["status"]] if new else None
    r["correction_status"] = db["app_feedback"][0]["status"]
    # duplicate refused
    pg.fill("#f-claim", "Server migration requires 10 Migration Permits."); pg.click("#add-form button[type=submit]")
    r["duplicate_toast"] = toast(pg)

    # gaps: answer one, dismiss the other
    pg.click('.adm-tab[data-type="gaps"]'); pg.wait_for_selector(".item")
    r["top_gap"] = pg.inner_text(".item .text")
    pg.click(".item >> nth=0 >> text=Answer with a fact…")
    pg.fill("#f-claim", "The next Kaboom event starts on November 7, 2026.")
    pg.click("#add-form button[type=submit]"); toast(pg)
    pg.click('.adm-tab[data-type="gaps"]'); pg.wait_for_selector(".item")
    try:
        pg.click('.item button[data-act="dismiss"]'); toast(pg)
    except Exception:
        pg.screenshot(path=SHOTS + "debug-dismiss.png")
        print("ITEMS:", pg.eval_on_selector_all(".item", "els => els.map(e => e.outerHTML.slice(0, 300))"))
        print("TOAST:", pg.evaluate("document.querySelector('#toast').outerHTML"))
        raise
    pg.wait_for_selector("text=All done here")
    gaps = {g["gap_key"]: g["status"] for g in DB()["knowledge_gaps"]}
    r["gaps"] = gaps
    pg.wait_for_function("document.querySelector('[data-count=gaps]').textContent === '0'")
    r["counts_after"] = {k: count(pg, k) for k in ("review", "conflicts", "corrections", "gaps")}

    # publish now
    pg.click("#publish"); r["publish_toast"] = toast(pg)
    r["dispatches"] = len(DB()["dispatches"])
    pg.screenshot(path=SHOTS + "review-done.png")

    # audit log + sign out
    r["audit_actions"] = sorted({a["action"] for a in DB()["admin_audit"]})
    pg.click("#signout"); pg.wait_for_selector("#login-view:not([hidden])")
    pg.reload(); pg.wait_for_selector("#login-view:not([hidden])")
    r["signed_out_after_reload"] = True
    ctx.close()

    # desktop look
    ctx = b.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page(); pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(SITE + "admin.html"); pg.fill("#password", "local test password"); pg.click("#login-form button[type=submit]")
    pg.wait_for_selector("#panel-view:not([hidden])"); pg.click('.adm-tab[data-type="add"]')
    pg.screenshot(path=SHOTS + "review-desktop-add.png")
    b.close()
r["errors"] = errs
print(json.dumps(r, indent=1, ensure_ascii=False))
