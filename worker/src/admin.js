/**
 * FGF review (admin) API, served by the AI proxy. Lets the owner review what the
 * automatic pipelines and players added, from a phone, without touching GitHub files.
 *
 * Secrets (set by the publish workflow, never in Git):
 *   ADMIN_PASSWORD        at least 12 characters; admin is switched off without it
 *   SUPABASE_ADMIN_KEY    Supabase secret key (writes claims, reads feedback)
 *   GITHUB_DISPATCH_TOKEN optional fine-grained token (Actions: write) for "Publish now"
 * Vars: SUPABASE_URL, GITHUB_REPO (owner/repo)
 *
 * Routes (all need an allowed Origin; all but /login need "Authorization: Bearer <token>"):
 *   POST /admin/login    {password}                      -> {token, expires_utc, publish}
 *   GET  /admin/summary                                  -> counts per queue
 *   GET  /admin/queue?type=review|conflicts|corrections|gaps&offset=&q=&tier=
 *   POST /admin/decide   {type, id | ids[], action, note?}
 *   POST /admin/fact     {claim, category, tier, source_url?, note?, gap_key?, feedback_id?}
 *   POST /admin/publish                                  -> starts the corpus sync now
 *
 * Rules kept from the project's core objectives: Tier 1 is only ever set by a person,
 * with proof; every decision is recorded in the claim's metadata and in admin_audit.
 */

const enc = new TextEncoder();
const TOKEN_HOURS = 12;
const REVIEW_STATES = ["Under Review", "candidate", "Needs Review", "Needs verification", "Pending Admin Review"];
const CATEGORIES = ["Progression", "Champions", "Events", "Combat", "Economy", "Flagships", "Buildings", "PvP", "Guild",
  "Resources", "Research", "Interface", "Technical", "General"];
const TIER_LABELS = { 1: "Tier 1 — Admin-confirmed evidence", 2: "Tier 2 — Official Developer", 3: "Tier 3 — Creator/Community" };
const failures = new Map();      // ip -> [times]
const globalFailures = [];

const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const norm = (s) => String(s || "").replace(/\s+/g, " ").trim().toLowerCase();   // same as the corpus sync
const clean = (v, max) => (typeof v === "string" ? v.replace(/\s+/g, " ").trim().slice(0, max) : "");

async function hmac(secret, msg) {
  const key = await crypto.subtle.importKey("raw", enc.encode("fgf-admin:" + secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  return b64url(await crypto.subtle.sign("HMAC", key, enc.encode(msg)));
}
function sameText(a, b) {          // constant-time comparison
  if (a.length !== b.length) return false;
  let d = 0; for (let i = 0; i < a.length; i++) d |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return d === 0;
}
async function sha256hex(s) {
  return [...new Uint8Array(await crypto.subtle.digest("SHA-256", enc.encode(s)))].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export const adminConfigured = (env) => String(env.ADMIN_PASSWORD || "").length >= 12 && !!env.SUPABASE_URL && !!env.SUPABASE_ADMIN_KEY;

async function makeToken(env, now) {
  const exp = String(Math.floor(now / 1000) + TOKEN_HOURS * 3600);
  return { token: exp + "." + await hmac(env.ADMIN_PASSWORD, exp), expires_utc: new Date(Number(exp) * 1000).toISOString() };
}
async function validToken(env, header, now) {
  const m = /^Bearer\s+(\d{10})\.([A-Za-z0-9_-]{20,})$/.exec(header || "");
  if (!m || Number(m[1]) * 1000 < now) return false;
  return sameText(m[2], await hmac(env.ADMIN_PASSWORD, m[1]));
}
function tooManyFailures(ip, now) {
  const win = 10 * 60 * 1000;
  const mine = (failures.get(ip) || []).filter((t) => now - t < win);
  failures.set(ip, mine);
  while (globalFailures.length && now - globalFailures[0] > win) globalFailures.shift();
  return mine.length >= 5 || globalFailures.length >= 30;
}
function recordFailure(ip, now) {
  failures.set(ip, [...(failures.get(ip) || []), now]); globalFailures.push(now);
  if (failures.size > 5000) failures.clear();
}

// ------------------------------------------------------------------ Supabase
async function sb(env, method, path, body, prefer = "return=minimal") {
  const r = await fetch(env.SUPABASE_URL.replace(/\/+$/, "") + "/rest/v1/" + path, {
    method, headers: { apikey: env.SUPABASE_ADMIN_KEY, Authorization: "Bearer " + env.SUPABASE_ADMIN_KEY,
      "Content-Type": "application/json", Prefer: prefer },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await r.text();
  if (!r.ok) { const e = new Error("database " + r.status + ": " + text.slice(0, 160)); e.status = r.status; throw e; }
  const range = r.headers.get("Content-Range") || "";
  return { data: text ? JSON.parse(text) : null, total: Number((range.split("/")[1] || "").replace("*", "")) || 0 };
}
const inList = (vals) => "in.(" + vals.map((v) => '"' + v + '"').join(",") + ")";
const safeQ = (q) => clean(q, 60).replace(/[^\p{L}\p{N} '\-.]/gu, "");

async function audit(env, action, target, detail) {
  try { await sb(env, "POST", "admin_audit", { action, target: String(target).slice(0, 200), detail }); } catch (e) { /* never block a decision on the log */ }
}

// -------------------------------------------------------------------- queues
const CLAIM_FIELDS = "id,claim_key,claim,category,claim_type,tier,status,confidence,season,version,metadata,created_at";

function claimView(c) {
  const m = c.metadata && typeof c.metadata === "object" ? c.metadata : {};
  return { id: c.id, claim: c.claim, category: c.category, tier: c.tier, status: c.status, confidence: c.confidence,
    created: String(c.created_at || "").slice(0, 10), version: c.version || "",
    source: m.Source || "", source_name: m.source_name || "", mode: m.evidence_mode || "", quote: m.evidence_quote || "",
    timestamp: m.timestamp || "", by_player: m.submitted_by === "player", conflicts_with: m.conflicts_with || "",
    verification: m["Verification Status"] || "", notes: m.Notes || "" };
}

async function queue(env, url) {
  const type = url.searchParams.get("type");
  const offset = Math.max(0, Math.min(100000, parseInt(url.searchParams.get("offset") || "0", 10) || 0));
  const q = safeQ(url.searchParams.get("q") || "");
  const tier = /^[123]$/.test(url.searchParams.get("tier") || "") ? url.searchParams.get("tier") : "";
  const page = `limit=40&offset=${offset}`;
  if (type === "review" || type === "conflicts") {
    let f = type === "review" ? "status=" + encodeURIComponent(inList(REVIEW_STATES)) : "status=eq.Conflicting";
    if (q) f += "&claim=ilike." + encodeURIComponent("*" + q + "*");
    if (tier) f += "&tier=ilike." + encodeURIComponent("*tier " + tier + "*");
    const r = await sb(env, "GET", `claims?select=${CLAIM_FIELDS}&${f}&order=created_at.desc,id.desc&${page}`, undefined, "count=exact");
    return { type, total: r.total, offset, items: (r.data || []).map(claimView) };
  }
  if (type === "corrections") {
    const r = await sb(env, "GET", `app_feedback?select=id,created_at,question,correction,cited_facts,answer_excerpt,source_url&status=eq.needs_review&order=created_at.desc&${page}`, undefined, "count=exact");
    return { type, total: r.total, offset, items: (r.data || []).map((x) => ({ ...x, created: String(x.created_at || "").slice(0, 10) })) };
  }
  if (type === "gaps") {
    const r = await sb(env, "GET", `knowledge_gaps?select=gap_key,example,count,unanswered,not_helpful,first_seen,last_seen&status=eq.open&order=count.desc,last_seen.desc&${page}`, undefined, "count=exact");
    return { type, total: r.total, offset, items: r.data || [] };
  }
  const e = new Error("unknown queue"); e.status = 400; throw e;
}

async function summary(env) {
  const count = async (path) => { try { return (await sb(env, "GET", path + "&limit=1", undefined, "count=exact")).total; } catch (e) { return null; } };
  const [review, conflicts, corrections, gaps] = await Promise.all([
    count("claims?select=id&status=" + encodeURIComponent(inList(REVIEW_STATES))),
    count("claims?select=id&status=eq.Conflicting"),
    count("app_feedback?select=id&status=eq.needs_review"),
    count("knowledge_gaps?select=gap_key&status=eq.open"),
  ]);
  return { review, conflicts, corrections, gaps, publish: !!(env.GITHUB_DISPATCH_TOKEN && env.GITHUB_REPO) };
}

// ----------------------------------------------------------------- decisions
async function updateClaim(env, id, changes, decision, note, now) {
  const r = await sb(env, "GET", `claims?select=id,claim,tier,status,metadata&id=eq.${encodeURIComponent(id)}`, undefined, "return=representation");
  const row = (r.data || [])[0];
  if (!row) { const e = new Error("fact not found"); e.status = 404; throw e; }
  const meta = row.metadata && typeof row.metadata === "object" ? { ...row.metadata } : {};
  const day = new Date(now).toISOString().slice(0, 10);
  meta.review_history = [...(Array.isArray(meta.review_history) ? meta.review_history : []), {
    decision, at: new Date(now).toISOString(), note: note || "", from_status: row.status, from_tier: row.tier }].slice(-20);
  meta["Verification Status"] = { approve: `Admin confirmed ${day}`, promote_tier1: `Admin confirmed as Tier 1 ${day}`,
    reject: `Rejected by admin ${day}`, accept_new: `Admin accepted over older fact ${day}`, keep_existing: `Rejected by admin ${day}: conflicts with current fact`,
    superseded: `Superseded ${day}` }[decision] || meta["Verification Status"];
  if (decision === "promote_tier1") meta.tier1_proof = note;
  await sb(env, "PATCH", `claims?id=eq.${encodeURIComponent(id)}`, { ...changes, metadata: meta });
  await audit(env, "claim:" + decision, id, { claim: row.claim, note: note || "", from: { status: row.status, tier: row.tier }, to: changes });
  return row;
}

async function decide(env, body, now) {
  const type = body.type, action = body.action, note = clean(body.note, 500);
  const ids = (Array.isArray(body.ids) ? body.ids : [body.id]).filter((x) => x !== undefined && x !== null && x !== "").slice(0, 50).map(String);
  if (!ids.length) return [400, { error: "nothing selected" }];
  const done = [];
  if (type === "review") {
    if (!["approve", "reject", "promote_tier1"].includes(action)) return [400, { error: "unknown action" }];
    if (action === "promote_tier1") {
      if (ids.length !== 1) return [400, { error: "promote one fact at a time" }];
      if (note.length < 8) return [400, { error: "Tier 1 needs proof: describe the in-game screen or official source (8+ characters)." }];
    }
    for (const id of ids) {
      const changes = action === "reject" ? { status: "Rejected" }
        : action === "promote_tier1" ? { status: "Confirmed", tier: TIER_LABELS[1] } : { status: "Confirmed" };
      await updateClaim(env, id, changes, action, note, now); done.push(id);
    }
  } else if (type === "conflicts") {
    if (!["keep_existing", "accept_new"].includes(action)) return [400, { error: "unknown action" }];
    for (const id of ids) {
      if (action === "keep_existing") { await updateClaim(env, id, { status: "Rejected" }, action, note, now); done.push(id); continue; }
      const row = await updateClaim(env, id, { status: "Confirmed" }, action, note, now);
      const old = clean((row.metadata || {}).conflicts_with, 600);
      if (old) {
        const r = await sb(env, "GET", `claims?select=id&claim=eq.${encodeURIComponent(old)}&id=neq.${encodeURIComponent(id)}`, undefined, "return=representation");
        for (const o of r.data || []) await updateClaim(env, o.id, { status: "Superseded" }, "superseded", `Replaced by fact ${id}` + (note ? `: ${note}` : ""), now);
      }
      done.push(id);
    }
  } else if (type === "corrections") {
    if (!["done", "dismiss"].includes(action)) return [400, { error: "unknown action" }];
    for (const id of ids) {
      if (!/^\d+$/.test(id)) continue;
      await sb(env, "PATCH", `app_feedback?id=eq.${id}`, { status: action === "done" ? "processed" : "ignored",
        processed_at: new Date(now).toISOString(), result: { decision: "admin_" + action, note } });
      await audit(env, "correction:" + action, id, { note }); done.push(id);
    }
  } else if (type === "gaps") {
    if (action !== "dismiss") return [400, { error: "unknown action" }];
    for (const id of ids) {
      await sb(env, "PATCH", `knowledge_gaps?gap_key=eq.${encodeURIComponent(id)}`, { status: "dismissed", resolved_note: note || "dismissed by admin", updated_at: new Date(now).toISOString() });
      await audit(env, "gap:dismiss", id, { note }); done.push(id);
    }
  } else return [400, { error: "unknown queue" }];
  return [200, { ok: true, done }];
}

async function allClaimNorms(env) {
  const out = new Set();
  for (let offset = 0; offset < 200000; offset += 1000) {
    const r = await sb(env, "GET", `claims?select=claim&order=id.asc&limit=1000&offset=${offset}`, undefined, "return=representation");
    for (const c of r.data || []) out.add(norm(c.claim));
    if ((r.data || []).length < 1000) break;
  }
  return out;
}

async function addFact(env, body, now) {
  const claim = clean(body.claim, 400);
  const tier = [1, 2, 3].includes(Number(body.tier)) ? Number(body.tier) : 0;
  const category = CATEGORIES.includes(body.category) ? body.category : "General";
  const src = clean(body.source_url, 500);
  const note = clean(body.note, 500);
  if (claim.length < 12) return [400, { error: "Write the fact as a full sentence (12+ characters)." }];
  if (!tier) return [400, { error: "Choose a tier." }];
  if (src && !/^https?:\/\/\S+$/i.test(src)) return [400, { error: "The source must be a web link (https://…)." }];
  if (tier === 1 && note.length < 8 && !src) return [400, { error: "Tier 1 needs proof: a link or a description of the in-game screen." }];
  if ((await allClaimNorms(env)).has(norm(claim))) return [409, { error: "This fact is already in the knowledge base." }];
  const day = new Date(now).toISOString();
  const row = {
    claim_key: "admin-" + (await sha256hex(norm(claim))).slice(0, 20), claim, category, claim_type: "FACT", season: "",
    version: day.slice(0, 10), tier: TIER_LABELS[tier], confidence: "High", status: "Confirmed", canonical: false,
    metadata: { Source: src || "Admin entry", Notes: note, "Evidence Type": "Admin entry", "Verification Status": `Admin confirmed ${day.slice(0, 10)}`,
      pipeline: "fgf-admin-review", added_utc: day, canonical_promotion: false, ...(tier === 1 ? { tier1_proof: note || src } : {}),
      ...(body.gap_key ? { answers_gap: clean(body.gap_key, 200) } : {}), ...(body.feedback_id ? { from_feedback: String(body.feedback_id).slice(0, 20) } : {}) },
  };
  await sb(env, "POST", "claims?on_conflict=claim_key", [row], "resolution=ignore-duplicates,return=minimal");
  await audit(env, "fact:add", row.claim_key, { claim, tier, src, note });
  if (body.gap_key) await sb(env, "PATCH", `knowledge_gaps?gap_key=eq.${encodeURIComponent(clean(body.gap_key, 200))}`,
    { status: "answered", resolved_note: claim, updated_at: day }).catch(() => {});
  if (/^\d+$/.test(String(body.feedback_id || ""))) await sb(env, "PATCH", `app_feedback?id=eq.${body.feedback_id}`,
    { status: "processed", processed_at: day, result: { decision: "admin_added_fact", claim_key: row.claim_key } }).catch(() => {});
  return [200, { ok: true, claim_key: row.claim_key }];
}

async function publish(env) {
  if (!env.GITHUB_DISPATCH_TOKEN || !env.GITHUB_REPO) return [503, { error: "Publish now isn't set up (see SITE_SETUP.md). Changes go live with the next automatic sync." }];
  const base = (env.GITHUB_API || "https://api.github.com").replace(/\/+$/, "");
  const r = await fetch(`${base}/repos/${env.GITHUB_REPO}/actions/workflows/corpus-sync.yml/dispatches`, {
    method: "POST", headers: { Authorization: "Bearer " + env.GITHUB_DISPATCH_TOKEN, Accept: "application/vnd.github+json",
      "User-Agent": "fgf-ai-proxy", "Content-Type": "application/json" }, body: JSON.stringify({ ref: "main" }) });
  if (r.status !== 204) return [502, { error: "GitHub didn't start the sync (" + r.status + ")." }];
  await audit(env, "publish", env.GITHUB_REPO, {});
  return [200, { ok: true }];
}

// -------------------------------------------------------------------- router
export async function handleAdmin(request, env, url, cors, json, now) {
  if (!adminConfigured(env)) return json({ error: "Review page isn't set up yet (see SITE_SETUP.md)." }, 503, cors);
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "anon";
  const path = url.pathname.replace(/^\/admin\/?/, "");
  try {
    if (path === "login" && request.method === "POST") {
      if (tooManyFailures(ip, now)) return json({ error: "Too many wrong passwords. Try again in 10 minutes." }, 429, cors);
      let body = {}; try { body = JSON.parse((await request.text()).slice(0, 2000)); } catch (e) {}
      const given = await sha256hex("pw:" + String(body.password || "")), want = await sha256hex("pw:" + env.ADMIN_PASSWORD);
      if (!sameText(given, want)) { recordFailure(ip, now); return json({ error: "Wrong password." }, 401, cors); }
      return json({ ...(await makeToken(env, now)), publish: !!(env.GITHUB_DISPATCH_TOKEN && env.GITHUB_REPO) }, 200, cors);
    }
    if (!(await validToken(env, request.headers.get("Authorization"), now))) return json({ error: "Please sign in again." }, 401, cors);
    if (path === "summary" && request.method === "GET") return json(await summary(env), 200, cors);
    if (path === "queue" && request.method === "GET") return json(await queue(env, url), 200, cors);
    const raw = request.method === "POST" ? await request.text() : "";
    if (raw.length > 20000) return json({ error: "request too large" }, 413, cors);
    let body = {}; if (raw) { try { body = JSON.parse(raw); } catch (e) { return json({ error: "invalid JSON" }, 400, cors); } }
    let res;
    if (path === "decide" && request.method === "POST") res = await decide(env, body, now);
    else if (path === "fact" && request.method === "POST") res = await addFact(env, body, now);
    else if (path === "publish" && request.method === "POST") res = await publish(env);
    else return json({ error: "not_found" }, 404, cors);
    return json(res[1], res[0], cors);
  } catch (e) {
    console.log(JSON.stringify({ event: "admin_error", path, status: e.status || 500, message: String(e.message).slice(0, 200) }));
    if (e.status === 404 && /fact not found/.test(e.message)) return json({ error: "That fact no longer exists." }, 404, cors);
    if (e.status === 400) return json({ error: e.message }, 400, cors);
    if (/database 404/.test(e.message)) return json({ error: "A review table is missing: run sql/app_feedback.sql in Supabase." }, 503, cors);
    return json({ error: "The database didn't respond. Try again." }, 502, cors);
  }
}

export const _adminInternal = { failures, globalFailures, norm, TIER_LABELS, CATEGORIES };
