// Local copy of the production stack for end-to-end tests:
//   mock Gemini (OpenAI-compatible, streaming) -> FGF AI proxy (worker) -> built app (static files)
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { handle } from "../../worker/src/index.js";

const [UP, PROXY, SITE] = [8961, 8962, 8963];
const DIST = path.resolve(process.argv[2] || "site/dist");
const counts = { upstream: 0 };

http.createServer((req, res) => {
  let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => {
    const body = JSON.parse(b); counts.upstream++;
    if (body.model === "busy") { res.writeHead(429); return res.end("{}"); }
    const last = body.messages[body.messages.length - 1].content;
    const ref = (last.match(/\[(E\d+)\] \(Tier [12]/) || [, "E1"])[1];
    const fact = ((last.split("[" + ref + "]")[1] || "").split("\n")[0] || "").replace(/^ \([^)]*\) /, "");
    const answer = `**Short answer:** ${fact} [${ref}]\n\n- Answered by the free AI through the FGF proxy.\n- Follow-ups remember this conversation.`;
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    for (const piece of answer.match(/.{1,30}/gs)) res.write(`data: ${JSON.stringify({ choices: [{ delta: { content: piece } }] })}\n\n`);
    res.write(`data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: "stop" }] })}\n\ndata: [DONE]\n\n`); res.end();
  });
}).listen(UP);

const env = { GEMINI_API_KEY: "test", GEMINI_BASE_URL: `http://127.0.0.1:${UP}`, GEMINI_MODELS: "busy,gemini-test",
  ALLOWED_ORIGINS: `http://127.0.0.1:${SITE}` };
http.createServer(async (req, res) => {
  if (req.url === "/__counts") { res.writeHead(200); return res.end(JSON.stringify(counts)); }
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
