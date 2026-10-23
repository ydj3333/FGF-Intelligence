// Local copy of the production stack for end-to-end tests:
//   mock Gemini (OpenAI-compatible, streaming) -> FGF AI proxy (worker) -> built app (static files)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { handle } from "../../worker/src/index.js";
import { createMockSupabase } from "../../worker/test/mock-supabase.mjs";

const [UP, PROXY, SITE, DB] = [8961, 8962, 8963, 8964];
const now = new Date().toISOString();
const m = (extra) => ({ Source: "https://www.foundation.game/en/news/kaboom", source_name: "FGF Official News", evidence_mode: "quote",
  evidence_quote: "Kaboom now starts on Saturday", ...extra });
const db = createMockSupabase({
  claims: [
    { id: 1, claim_key: "k1", claim: "Kaboom starts on Saturday, October 24, 2026.", category: "Events", tier: "Tier 2 — Official Developer", status: "Under Review", metadata: m(), created_at: now },
    { id: 2, claim_key: "k2", claim: "Zora, Lily and Jodie are a strong Kaboom lineup.", category: "Events", tier: "Tier 3 — Creator/Community", status: "Under Review",
      metadata: m({ evidence_mode: "video", timestamp: "01:15", source_name: "YouTube playlist", Source: "https://www.youtube.com/watch?v=AAAAAAAAAAA&t=75s" }), created_at: now },
    { id: 3, claim_key: "k3", claim: "The shop sells Migration Permits for 500 gems.", category: "Economy", tier: "Tier 1 — In-game UI", status: "Under Review",
      metadata: m({ evidence_mode: "image", source_name: "In-game screenshot" }), created_at: now },
    { id: 4, claim_key: "k4", claim: "Server migration requires 12 Migration Permits.", category: "Progression", tier: "Tier 3 — Creator/Community", status: "Conflicting",
      metadata: m({ conflicts_with: "Server migration requires 10 Migration Permits.", source_name: "Reddit" }), created_at: now },
    { id: 5, claim_key: "k5", claim: "Server migration requires 10 Migration Permits.", category: "Progression", tier: "Tier 2 — Official Developer", status: "Confirmed", metadata: {}, created_at: "2026-09-01" },
  ],
  app_feedback: [{ id: 50, kind: "correction", question: "Best T100 plan for day 3?", correction: "Save speedups for day 3, the building day.", status: "needs_review", cited_facts: ["Day 3 is research day."], created_at: now }],
  knowledge_gaps: [{ gap_key: "event kaboom", example: "When is the next Kaboom event?", count: 7, unanswered: 7, status: "open", last_seen: "2026-10-23" },
                   { gap_key: "flagship paint", example: "How do I repaint my flagship?", count: 2, unanswered: 2, status: "open", last_seen: "2026-10-20" }],
});
db.server.listen(DB);
const DIST = path.resolve(process.argv[2] || "site/dist");
const counts = { upstream: 0 };

http.createServer((req, res) => {
  let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => {
    const body = JSON.parse(b);
    counts.upstream++;
    if (body.model === "busy") { res.writeHead(429); return res.end("{}"); }
    const last = body.messages[body.messages.length - 1].content;
    const ref = (last.match(/\[(E\d+)\] \(Tier [12]/) || [, "E1"])[1];
    const fact = ((last.split("[" + ref + "]")[1] || "").split("\n")[0] || "").replace(/^ \([^)]*\) /, "");
    const answer = /wobblequark/.test(last) ? "The sources don't cover that yet. Check the in-game help screen.\n[[GAP]]"
      : `**Short answer:** ${fact} [${ref}]\n\n- Answered by the free AI through the FGF proxy.\n- Follow-ups remember this conversation.`;
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    for (const piece of answer.match(/.{1,30}/gs)) res.write(`data: ${JSON.stringify({ choices: [{ delta: { content: piece } }] })}\n\n`);
    res.write(`data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: "stop" }] })}\n\ndata: [DONE]\n\n`); res.end();
  });
}).listen(UP);

const env = { GEMINI_API_KEY: "test", GEMINI_BASE_URL: `http://127.0.0.1:${UP}`, GEMINI_MODELS: "busy,gemini-test",
  ALLOWED_ORIGINS: `http://127.0.0.1:${SITE}`, SUPABASE_URL: `http://127.0.0.1:${DB}`, SUPABASE_KEY: "sb_publishable_test",
  ADMIN_PASSWORD: "local test password", SUPABASE_ADMIN_KEY: "sb_secret_test", GITHUB_REPO: "ydj3333/FGF-Intelligence", GITHUB_DISPATCH_TOKEN: "gh-ok", GITHUB_API: `http://127.0.0.1:${DB}` };
http.createServer(async (req, res) => {
  if (req.url === "/__counts") { res.writeHead(200); return res.end(JSON.stringify({ ...counts, feedback: db.tables.app_feedback.filter((x) => x.id < 50 || x.id >= 1000) })); }
  if (req.url === "/__db") { res.writeHead(200); return res.end(JSON.stringify({ ...db.tables, dispatches: db.dispatches })); }
  const chunks = []; for await (const c of req) chunks.push(c);
  const body = chunks.length ? Buffer.concat(chunks) : undefined;
  const r = await handle(new Request(`http://127.0.0.1:${PROXY}${req.url}`, { method: req.method, headers: req.headers, body: req.method === "GET" || req.method === "OPTIONS" ? undefined : body }), env);
  res.writeHead(r.status, Object.fromEntries(r.headers));
  if (r.body) for await (const c of r.body) res.write(c);
  res.end();
}).listen(PROXY);

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json", ".webmanifest": "application/manifest+json", ".png": "image/png" };
http.createServer((req, res) => {
  let p = decodeURIComponent(req.url.split("?")[0]); if (p.endsWith("/")) p += "index.html";
  const f = path.join(DIST, p);
  if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { "Content-Type": TYPES[path.extname(f)] || "application/octet-stream" }); fs.createReadStream(f).pipe(res);
}).listen(SITE, () => console.log("stack ready"));
