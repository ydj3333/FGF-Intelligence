import assert from "node:assert";
import { handle } from "../src/index.js";
import { _adminInternal } from "../src/admin.js";
import { createMockSupabase } from "./mock-supabase.mjs";

const meta = (extra = {}) => ({ Source: "https://www.foundation.game/en/news/x", source_name: "FGF Official News", evidence_mode: "quote",
  evidence_quote: "quote", "Verification Status": "Auto-harvested", ...extra });
const seed = {
  claims: [
    { id: 1, claim_key: "k1", claim: "Kaboom starts on Saturday, October 24, 2026.", category: "Events", tier: "Tier 2 — Official Developer", status: "Under Review", metadata: meta(), created_at: "2026-10-22T01:00:00Z" },
    { id: 2, claim_key: "k2", claim: "Zora, Lily and Jodie are a strong Kaboom lineup.", category: "Events", tier: "Tier 3 — Creator/Community", status: "Under Review", metadata: meta({ evidence_mode: "video", timestamp: "01:15" }), created_at: "2026-10-22T02:00:00Z" },
    { id: 3, claim_key: "k3", claim: "The in-game shop sells Migration Permits for 500 gems.", category: "Economy", tier: "Tier 1 — In-game UI", status: "Under Review", metadata: meta({ evidence_mode: "image" }), created_at: "2026-10-22T03:00:00Z" },
    { id: 4, claim_key: "k4", claim: "Server migration requires 12 Migration Permits.", category: "Progression", tier: "Tier 3 — Creator/Community", status: "Conflicting",
      metadata: meta({ conflicts_with: "Server migration requires 10 Migration Permits." }), created_at: "2026-10-22T04:00:00Z" },
    { id: 5, claim_key: "k5", claim: "Server migration requires 10 Migration Permits.", category: "Progression", tier: "Tier 2 — Official Developer", status: "Confirmed", metadata: {}, created_at: "2026-09-01T00:00:00Z" },
    { id: 6, claim_key: "k6", claim: "Spare fact under review number six.", category: "General", tier: "Tier 3", status: "candidate", metadata: {}, created_at: "2026-10-01T00:00:00Z" },
  ],
  app_feedback: [{ id: 50, kind: "correction", question: "Best T100 day 3?", correction: "Save speedups for day 3.", status: "needs_review", cited_facts: [], created_at: "2026-10-22T05:00:00Z" },
                 { id: 51, kind: "helpful", question: "x?", status: "processed" }],
  knowledge_gaps: [{ gap_key: "event kaboom", example: "When is the next Kaboom event?", count: 7, status: "open", last_seen: "2026-10-22" },
                   { gap_key: "flagship paint", example: "How do I repaint my flagship?", count: 2, status: "open", last_seen: "2026-10-20" }],
};
const db = createMockSupabase(seed);
await new Promise((r) => db.server.listen(0, r));
const base = `http://127.0.0.1:${db.server.address().port}`;
const PW = "correct horse battery staple";
const env = (extra = {}) => ({ ALLOWED_ORIGINS: "https://ydj3333.github.io", SUPABASE_URL: base, SUPABASE_ADMIN_KEY: "sb_secret", ADMIN_PASSWORD: PW,
  GITHUB_REPO: "ydj3333/FGF-Intelligence", GITHUB_DISPATCH_TOKEN: "gh-ok", GITHUB_API: base, ...extra });
const call = (path, { method = "GET", body, token, origin = "https://ydj3333.github.io", ip = "1.1.1.1", e = env(), now } = {}) =>
  handle(new Request("https://fgf-ai.example.workers.dev" + path, { method, body: body === undefined ? undefined : JSON.stringify(body),
    headers: { "Content-Type": "application/json", Origin: origin, "CF-Connecting-IP": ip, ...(token ? { Authorization: "Bearer " + token } : {}) } }), e, now);
const claim = (id) => db.tables.claims.find((c) => c.id === id);
let n = 0; const t = async (name, fn) => { await fn(); n++; console.log("ok -", name); };

let token;
await t("admin is off without a strong password and database key", async () => {
  assert.strictEqual((await call("/admin/login", { method: "POST", body: { password: "short" }, e: env({ ADMIN_PASSWORD: "short" }) })).status, 503);
  assert.strictEqual((await call("/admin/summary", { e: env({ SUPABASE_ADMIN_KEY: "" }) })).status, 503);
  const h = await (await call("/health", { e: env({ GEMINI_API_KEY: "g" }) })).json();
  assert.strictEqual(h.admin, true);
});
await t("sign-in: wrong password, lockout, other sites refused, token works and expires", async () => {
  assert.strictEqual((await call("/admin/login", { method: "POST", body: { password: "nope" }, ip: "6.6.6.6" })).status, 401);
  for (let i = 0; i < 4; i++) await call("/admin/login", { method: "POST", body: { password: "nope" }, ip: "6.6.6.6" });
  assert.strictEqual((await call("/admin/login", { method: "POST", body: { password: PW }, ip: "6.6.6.6" })).status, 429, "locked out after 5 failures");
  assert.strictEqual((await call("/admin/login", { method: "POST", body: { password: PW }, origin: "https://evil.example" })).status, 403);
  const r = await call("/admin/login", { method: "POST", body: { password: PW } });
  assert.strictEqual(r.status, 200);
  const j = await r.json(); token = j.token; assert.ok(j.publish && /^\d{10}\./.test(token));
  assert.strictEqual(r.headers.get("Access-Control-Allow-Origin"), "https://ydj3333.github.io");
  assert.strictEqual((await call("/admin/summary")).status, 401, "no token");
  assert.strictEqual((await call("/admin/summary", { token: token.slice(0, -2) + "xx" })).status, 401, "forged token");
  assert.strictEqual((await call("/admin/summary", { token, now: Date.now() + 13 * 3600e3 })).status, 401, "expired after 12 h");
  assert.strictEqual((await call("/admin/summary", { token, e: env({ ADMIN_PASSWORD: "a different password!" }) })).status, 401, "password change signs everyone out");
  _adminInternal.failures.clear(); _adminInternal.globalFailures.length = 0;
});
await t("summary and queues", async () => {
  const s = await (await call("/admin/summary", { token })).json();
  assert.deepStrictEqual(s, { review: 4, conflicts: 1, corrections: 1, gaps: 2, publish: true });
  const q = await (await call("/admin/queue?type=review", { token })).json();
  assert.strictEqual(q.total, 4); assert.deepStrictEqual(q.items.map((x) => x.id), [3, 2, 1, 6]);   // newest first
  assert.strictEqual(q.items[1].mode, "video"); assert.strictEqual(q.items[1].timestamp, "01:15");
  const qs = await (await call("/admin/queue?type=review&q=" + encodeURIComponent("kaboom"), { token })).json();
  assert.deepStrictEqual(qs.items.map((x) => x.id).sort(), [1, 2]);
  const qt = await (await call("/admin/queue?type=review&tier=1", { token })).json();
  assert.deepStrictEqual(qt.items.map((x) => x.id), [3]);
  const inj = await call("/admin/queue?type=review&q=" + encodeURIComponent("x&status=eq.Confirmed"), { token });
  assert.strictEqual(inj.status, 200); assert.strictEqual((await inj.json()).total, 0, "search text can't add filters");
  const c = await (await call("/admin/queue?type=conflicts", { token })).json();
  assert.strictEqual(c.items[0].conflicts_with, "Server migration requires 10 Migration Permits.");
  assert.strictEqual((await (await call("/admin/queue?type=gaps", { token })).json()).items[0].count, 7);
  assert.strictEqual((await (await call("/admin/queue?type=corrections", { token })).json()).items[0].id, 50);
  assert.strictEqual((await call("/admin/queue?type=secrets", { token })).status, 400);
});
await t("approve, bulk reject, and Tier 1 only with proof", async () => {
  let r = await call("/admin/decide", { method: "POST", token, body: { type: "review", id: 1, action: "approve", note: "matches the official post" } });
  assert.strictEqual(r.status, 200);
  assert.strictEqual(claim(1).status, "Confirmed"); assert.match(claim(1).metadata["Verification Status"], /^Admin confirmed/);
  assert.strictEqual(claim(1).metadata.review_history[0].from_status, "Under Review");
  assert.strictEqual(claim(1).metadata.Source, "https://www.foundation.game/en/news/x", "metadata kept");
  r = await call("/admin/decide", { method: "POST", token, body: { type: "review", id: 3, action: "promote_tier1", note: "short" } });
  assert.strictEqual(r.status, 400); assert.strictEqual(claim(3).tier, "Tier 1 — In-game UI");
  r = await call("/admin/decide", { method: "POST", token, body: { type: "review", ids: [3, 2], action: "promote_tier1", note: "seen in the shop screen today" } });
  assert.strictEqual(r.status, 400, "one at a time");
  r = await call("/admin/decide", { method: "POST", token, body: { type: "review", id: 3, action: "promote_tier1", note: "Seen in the in-game shop on 23 Oct" } });
  assert.strictEqual(r.status, 200); assert.strictEqual(claim(3).tier, "Tier 1 — Admin-confirmed evidence"); assert.strictEqual(claim(3).metadata.tier1_proof, "Seen in the in-game shop on 23 Oct");
  r = await call("/admin/decide", { method: "POST", token, body: { type: "review", ids: [2, 6], action: "reject" } });
  assert.deepStrictEqual((await r.json()).done, ["2", "6"]); assert.strictEqual(claim(2).status, "Rejected"); assert.strictEqual(claim(6).status, "Rejected");
  assert.strictEqual((await call("/admin/decide", { method: "POST", token, body: { type: "review", id: 999, action: "approve" } })).status, 404);
  assert.ok(db.tables.admin_audit.some((a) => a.action === "claim:promote_tier1" && a.detail.note.includes("shop")));
});
await t("dispute: accept the new fact retires the old one", async () => {
  const r = await call("/admin/decide", { method: "POST", token, body: { type: "conflicts", id: 4, action: "accept_new", note: "patch 2.3 changed it" } });
  assert.strictEqual(r.status, 200);
  assert.strictEqual(claim(4).status, "Confirmed"); assert.strictEqual(claim(5).status, "Superseded");
  assert.match(claim(5).metadata.review_history[0].note, /Replaced by fact 4/);
});
await t("add a fact (answers a gap / correction), duplicates refused, Tier 1 needs proof", async () => {
  let r = await call("/admin/fact", { method: "POST", token, body: { claim: "Kaboom starts on Saturday, October 24, 2026.", tier: 2, category: "Events" } });
  assert.strictEqual(r.status, 409, "already known (same text, any spacing/case)");
  r = await call("/admin/fact", { method: "POST", token, body: { claim: "The next Kaboom event starts on November 7, 2026.", tier: 1, category: "Events" } });
  assert.strictEqual(r.status, 400);
  r = await call("/admin/fact", { method: "POST", token, body: { claim: "  The next Kaboom event starts on   November 7, 2026. ", tier: 2, category: "Events",
    source_url: "https://www.foundation.game/en/news/kaboom", gap_key: "event kaboom", feedback_id: 50 } });
  assert.strictEqual(r.status, 200);
  const added = db.tables.claims.at(-1);
  assert.strictEqual(added.claim, "The next Kaboom event starts on November 7, 2026.");
  assert.strictEqual(added.status, "Confirmed"); assert.strictEqual(added.canonical, false); assert.strictEqual(added.tier, "Tier 2 — Official Developer");
  assert.ok(added.claim_key.startsWith("admin-")); assert.strictEqual(added.metadata.pipeline, "fgf-admin-review");
  assert.strictEqual(db.tables.knowledge_gaps[0].status, "answered");
  assert.strictEqual(db.tables.app_feedback[0].status, "processed");
  assert.strictEqual((await call("/admin/fact", { method: "POST", token, body: { claim: "Bad link fact for testing.", tier: 3, source_url: "javascript:x" } })).status, 400);
});
await t("dismiss a gap; queues empty; publish now", async () => {
  assert.strictEqual((await call("/admin/decide", { method: "POST", token, body: { type: "gaps", id: "flagship paint", action: "dismiss" } })).status, 200);
  assert.strictEqual(db.tables.knowledge_gaps[1].status, "dismissed");
  const s = await (await call("/admin/summary", { token })).json();
  assert.deepStrictEqual([s.review, s.conflicts, s.corrections, s.gaps], [0, 0, 0, 0]);
  let r = await call("/admin/publish", { method: "POST", token });
  assert.strictEqual(r.status, 200);
  assert.deepStrictEqual(db.dispatches.at(-1), { path: "/repos/ydj3333/FGF-Intelligence/actions/workflows/corpus-sync.yml/dispatches", auth: "Bearer gh-ok", body: { ref: "main" } });
  r = await call("/admin/publish", { method: "POST", token, e: env({ GITHUB_DISPATCH_TOKEN: "" }) });
  assert.strictEqual(r.status, 503);
  assert.ok(db.keysSeen.every((k) => k.key === "sb_secret"));
});
await t("missing review tables are explained", async () => {
  const r = await call("/admin/queue?type=gaps", { token, e: env({ SUPABASE_URL: base + "/nothing" }) });
  assert.strictEqual(r.status, 503); assert.match((await r.json()).error, /app_feedback\.sql/);
});
db.server.close();
console.log(`${n} passed`);
