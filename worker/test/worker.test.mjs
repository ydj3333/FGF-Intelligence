import assert from "node:assert";
import http from "node:http";
import { handle, _internal } from "../src/index.js";

// Mock OpenAI-compatible upstream: model "busy" -> 429, "gone" -> 404, others stream SSE.
const seen = [];
const upstream = http.createServer((req, res) => {
  let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => {
    const body = JSON.parse(b); seen.push({ model: body.model, auth: req.headers.authorization, stream: body.stream });
    if (body.model === "busy") { res.writeHead(429, { "Content-Type": "application/json" }); return res.end('{"error":{"message":"quota"}}'); }
    if (body.model === "gone") { res.writeHead(404); return res.end("{}"); }
    res.writeHead(200, { "Content-Type": "text/event-stream" });
    for (const piece of ["Hello ", "from ", body.model]) res.write(`data: ${JSON.stringify({ choices: [{ delta: { content: piece } }] })}\n\n`);
    res.write(`data: ${JSON.stringify({ choices: [{ delta: {}, finish_reason: "stop" }] })}\n\ndata: [DONE]\n\n`); res.end();
  });
});
await new Promise((r) => upstream.listen(0, r));
const base = `http://127.0.0.1:${upstream.address().port}`;
const env = (extra = {}) => ({ GEMINI_API_KEY: "g-key", GEMINI_BASE_URL: base, GEMINI_MODELS: "busy,gone,good-model", ALLOWED_ORIGINS: "https://ydj3333.github.io", ...extra });
const req = (path, init = {}) => new Request("https://fgf-ai.example.workers.dev" + path, init);
const chat = (messages, origin = "https://ydj3333.github.io", ip = "1.1.1.1") =>
  req("/chat", { method: "POST", headers: { "Content-Type": "application/json", Origin: origin, "CF-Connecting-IP": ip }, body: JSON.stringify({ messages }) });
const reset = () => { _internal.visitors.clear(); _internal.skipped.clear(); seen.length = 0; };
let n = 0; const t = async (name, fn) => { reset(); await fn(); n++; console.log("ok -", name); };

await t("health reports configured providers without secrets", async () => {
  const r = await handle(req("/health"), env()); const j = await r.json();
  assert.deepStrictEqual(j, { ok: true, providers: ["gemini"], models: 3 });
  const r2 = await (await handle(req("/health"), {})).json(); assert.strictEqual(r2.ok, false);
});
await t("falls back across models and streams", async () => {
  const r = await handle(chat([{ role: "user", content: "hi" }]), env());
  assert.strictEqual(r.status, 200); assert.strictEqual(r.headers.get("X-FGF-Model"), "good-model");
  assert.strictEqual(r.headers.get("Access-Control-Allow-Origin"), "https://ydj3333.github.io");
  const text = await r.text(); assert.match(text, /from /); assert.match(text, /good-model/);
  assert.deepStrictEqual(seen.map((s) => s.model), ["busy", "gone", "good-model"]);
  assert.ok(seen.every((s) => s.auth === "Bearer g-key" && s.stream === true));
});
await t("skips failed models on the next request", async () => {
  await handle(chat([{ role: "user", content: "a" }]), env()); seen.length = 0;
  await handle(chat([{ role: "user", content: "b" }], undefined, "2.2.2.2"), env());
  assert.deepStrictEqual(seen.map((s) => s.model), ["good-model"]);
});
await t("all models out of quota -> 429", async () => {
  const r = await handle(chat([{ role: "user", content: "hi" }]), env({ GEMINI_MODELS: "busy" }));
  assert.strictEqual(r.status, 429);
});
await t("groq used after gemini fails", async () => {
  const r = await handle(chat([{ role: "user", content: "hi" }]), env({ GEMINI_MODELS: "busy", GROQ_API_KEY: "q", GROQ_BASE_URL: base, GROQ_MODELS: "groq-model" }));
  assert.strictEqual(r.status, 200); assert.strictEqual(r.headers.get("X-FGF-Model"), "groq-model");
  assert.strictEqual(seen.at(-1).auth, "Bearer q");
});
await t("other websites are refused", async () => {
  const r = await handle(chat([{ role: "user", content: "hi" }], "https://evil.example"), env());
  assert.strictEqual(r.status, 403); assert.strictEqual(seen.length, 0);
});
await t("validation", async () => {
  for (const [msgs, code] of [[[], 400], [[{ role: "system", content: "x" }], 400], [[{ role: "user", content: "x" }, { role: "assistant", content: "y" }], 400],
    [[{ role: "user", content: "x".repeat(130_000) }], 413]]) {
    const r = await handle(chat(msgs), env()); assert.strictEqual(r.status, code, JSON.stringify(msgs).slice(0, 60));
  }
  const bad = await handle(req("/chat", { method: "POST", headers: { Origin: "https://ydj3333.github.io" }, body: "{oops" }), env());
  assert.strictEqual(bad.status, 400);
});
await t("per-visitor rate limit", async () => {
  const e = env({ GEMINI_MODELS: "good-model" });
  for (let i = 0; i < _internal.LIMITS.perVisitorPer10Min; i++) assert.strictEqual((await handle(chat([{ role: "user", content: "q" + i }], undefined, "9.9.9.9"), e)).status, 200);
  assert.strictEqual((await handle(chat([{ role: "user", content: "again" }], undefined, "9.9.9.9"), e)).status, 429);
  assert.strictEqual((await handle(chat([{ role: "user", content: "other" }], undefined, "8.8.8.8"), e)).status, 200);
});
await t("CORS preflight", async () => {
  const r = await handle(req("/chat", { method: "OPTIONS", headers: { Origin: "https://ydj3333.github.io" } }), env());
  assert.strictEqual(r.status, 204); assert.match(r.headers.get("Access-Control-Allow-Methods"), /POST/);
});
upstream.close();
console.log(`${n} passed`);
