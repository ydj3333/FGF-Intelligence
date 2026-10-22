/**
 * FGF AI proxy — a Cloudflare Worker (free plan) between the public FGF site and
 * free AI models. It keeps the API keys secret, accepts requests only from the
 * site's own origin, rate-limits each visitor, and streams the answer back.
 *
 * Model chain (first that works wins, automatically):
 *   Google Gemini free models (GEMINI_MODELS) -> optional Groq free models (GROQ_MODELS)
 * A model that is out of quota, overloaded or unknown is skipped for a while.
 *
 * Secrets (set by the GitHub workflow): GEMINI_API_KEY, optional GROQ_API_KEY.
 * Vars (wrangler.toml / workflow): ALLOWED_ORIGINS, GEMINI_MODELS, GROQ_MODELS.
 *
 * Routes:  GET /health    ->  {ok, providers, models, feedback}
 *          POST /chat     ->  body {messages:[{role:"user"|"assistant", content}]}
 *                            response: OpenAI-style server-sent events (text/event-stream)
 *          POST /feedback ->  body {kind, question, answer_excerpt?, correction?, source_url?, cited_facts?, app_version?}
 *                            stored anonymously in Supabase public.app_feedback (no IP, no account data)
 *                            for the daily learning run. Needs SUPABASE_URL + SUPABASE_KEY (prefer the
 *                            publishable key: the table's policy allows it to insert only, never read).
 */

const DEFAULTS = {
  GEMINI_BASE_URL: "https://generativelanguage.googleapis.com/v1beta/openai",
  GEMINI_MODELS: "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite",
  GROQ_BASE_URL: "https://api.groq.com/openai/v1",
  GROQ_MODELS: "openai/gpt-oss-120b,llama-3.3-70b-versatile",
};
const LIMITS = {
  maxBodyBytes: 200_000,     // the page sends ~10–40 KB per question
  maxMessages: 24,
  maxContentChars: 120_000,
  maxOutputTokens: 1400,
  perVisitorPer10Min: 20,    // best effort, per worker instance
  feedbackPer10Min: 15,
};
const FEEDBACK_KINDS = new Set(["helpful", "not_helpful", "correction", "unanswered"]);

// Per-instance memory: visitor buckets and temporarily skipped models.
const visitors = new Map();
const feedbackVisitors = new Map();
const skipped = new Map();   // "provider:model" -> until (ms)

const list = (s) => String(s || "").split(",").map((x) => x.trim()).filter(Boolean);

function candidates(env) {
  const out = [];
  if (env.GEMINI_API_KEY) for (const m of list(env.GEMINI_MODELS || DEFAULTS.GEMINI_MODELS))
    out.push({ provider: "gemini", model: m, base: env.GEMINI_BASE_URL || DEFAULTS.GEMINI_BASE_URL, key: env.GEMINI_API_KEY });
  if (env.GROQ_API_KEY) for (const m of list(env.GROQ_MODELS || DEFAULTS.GROQ_MODELS))
    out.push({ provider: "groq", model: m, base: env.GROQ_BASE_URL || DEFAULTS.GROQ_BASE_URL, key: env.GROQ_API_KEY });
  return out;
}

function corsHeaders(origin, env) {
  const allowed = allowedOrigin(origin, env);
  return {
    "Access-Control-Allow-Origin": allowed ? origin : "null",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
    "Vary": "Origin",
  };
}

function allowedOrigin(origin, env) {
  const allow = list(env.ALLOWED_ORIGINS);
  if (!allow.length) return true;              // not configured: open (local testing)
  if (!origin) return false;
  return allow.some((a) => a === "*" || a.toLowerCase() === origin.toLowerCase());
}

function json(obj, status, headers) {
  return new Response(JSON.stringify(obj), { status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store", ...headers } });
}

function rateLimited(ip, now, map = visitors, max = LIMITS.perVisitorPer10Min) {
  const windowMs = 10 * 60 * 1000;
  const hits = (map.get(ip) || []).filter((t) => now - t < windowMs);
  if (hits.length >= max) { map.set(ip, hits); return true; }
  hits.push(now); map.set(ip, hits);
  if (map.size > 5000) map.clear();   // keep memory bounded
  return false;
}

const str = (v, max) => (typeof v === "string" ? v.replace(/\s+/g, " ").trim().slice(0, max) : "");

function cleanFeedback(b) {
  if (!b || typeof b !== "object" || !FEEDBACK_KINDS.has(b.kind)) return null;
  const question = str(b.question, 500);
  if (question.length < 2) return null;
  const row = { kind: b.kind, question, answer_excerpt: str(b.answer_excerpt, 1500) || null,
                correction: str(b.correction, 1000) || null, source_url: null, cited_facts: [],
                app_version: str(b.app_version, 40) || null };
  if (row.kind === "correction" && !row.correction) return null;
  const u = str(b.source_url, 500);
  if (/^https?:\/\/[^\s]+$/i.test(u)) row.source_url = u;
  if (Array.isArray(b.cited_facts)) row.cited_facts = b.cited_facts.filter((x) => typeof x === "string").slice(0, 8).map((x) => str(x, 400));
  return row;
}

async function storeFeedback(request, env, cors, now) {
  if (!env.SUPABASE_URL || !env.SUPABASE_KEY) return json({ error: "feedback not configured" }, 503, cors);
  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "anon";
  if (rateLimited(ip, now, feedbackVisitors, LIMITS.feedbackPer10Min)) return json({ error: "Too much feedback in a short time." }, 429, cors);
  const raw = await request.text();
  if (raw.length > 8000) return json({ error: "request too large" }, 413, cors);
  let body; try { body = JSON.parse(raw); } catch (e) { return json({ error: "invalid JSON" }, 400, cors); }
  const row = cleanFeedback(body);
  if (!row) return json({ error: "invalid feedback" }, 400, cors);
  try {
    const r = await fetch(env.SUPABASE_URL.replace(/\/+$/, "") + "/rest/v1/app_feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json", apikey: env.SUPABASE_KEY, Authorization: "Bearer " + env.SUPABASE_KEY, Prefer: "return=minimal" },
      body: JSON.stringify(row),
    });
    if (!r.ok) { console.log(JSON.stringify({ event: "feedback_store_failed", status: r.status })); return json({ error: "could not store feedback" }, 502, cors); }
  } catch (e) {
    return json({ error: "could not store feedback" }, 502, cors);
  }
  console.log(JSON.stringify({ event: "feedback_stored", kind: row.kind }));
  return new Response(null, { status: 204, headers: cors });
}

function validate(body) {
  if (!body || !Array.isArray(body.messages)) return "messages must be an array";
  const msgs = body.messages;
  if (!msgs.length || msgs.length > LIMITS.maxMessages) return "too many or too few messages";
  let chars = 0;
  for (const m of msgs) {
    if (!m || (m.role !== "user" && m.role !== "assistant") || typeof m.content !== "string" || !m.content.trim()) return "each message needs role user/assistant and text";
    chars += m.content.length;
  }
  if (chars > LIMITS.maxContentChars) return "too_large";
  if (msgs[msgs.length - 1].role !== "user") return "last message must be from the user";
  return null;
}

export async function handle(request, env, now = Date.now()) {
  const url = new URL(request.url);
  const origin = request.headers.get("Origin") || "";
  const cors = corsHeaders(origin, env);

  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  if (url.pathname === "/health" && request.method === "GET") {
    const c = candidates(env);
    return json({ ok: c.length > 0, providers: [...new Set(c.map((x) => x.provider))], models: c.length,
                  feedback: !!(env.SUPABASE_URL && env.SUPABASE_KEY) }, 200, cors);
  }

  if (url.pathname === "/feedback" && request.method === "POST") {
    if (!allowedOrigin(origin, env)) return json({ error: "origin_not_allowed" }, 403, cors);
    return storeFeedback(request, env, cors, now);
  }

  if (url.pathname !== "/chat" || request.method !== "POST") return json({ error: "not_found" }, 404, cors);
  if (!allowedOrigin(origin, env)) return json({ error: "origin_not_allowed" }, 403, cors);

  const ip = request.headers.get("CF-Connecting-IP") || request.headers.get("X-Forwarded-For") || "anon";
  if (rateLimited(ip, now)) return json({ error: "Too many questions in a short time. Please wait a few minutes." }, 429, { ...cors, "Retry-After": "300" });

  const raw = await request.text();
  if (raw.length > LIMITS.maxBodyBytes) return json({ error: "request too large" }, 413, cors);
  let body; try { body = JSON.parse(raw); } catch (e) { return json({ error: "invalid JSON" }, 400, cors); }
  const problem = validate(body);
  if (problem === "too_large") return json({ error: "request too large" }, 413, cors);
  if (problem) return json({ error: problem }, 400, cors);

  const chain = candidates(env);
  if (!chain.length) return json({ error: "AI is not configured" }, 503, cors);

  let sawRateLimit = false, lastStatus = 0;
  for (const c of chain) {
    const key = c.provider + ":" + c.model;
    if ((skipped.get(key) || 0) > now) continue;
    let upstream;
    try {
      upstream = await fetch(c.base.replace(/\/+$/, "") + "/chat/completions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + c.key },
        body: JSON.stringify({ model: c.model, messages: body.messages, stream: true, max_tokens: LIMITS.maxOutputTokens, temperature: 0.3 }),
      });
    } catch (e) {
      lastStatus = 502; skipped.set(key, now + 60_000); continue;
    }
    if (upstream.ok && upstream.body) {
      console.log(JSON.stringify({ event: "chat_ok", provider: c.provider, model: c.model }));
      return new Response(upstream.body, { status: 200, headers: { ...cors, "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-store", "X-FGF-Model": c.model } });
    }
    lastStatus = upstream.status;
    try { await upstream.body?.cancel(); } catch (e) {}
    // Out of quota / rate limited: skip this model for 10 min. Unknown model or bad key: 1 hour.
    // Server trouble: 1 minute. Then try the next model.
    if (upstream.status === 429) { sawRateLimit = true; skipped.set(key, now + 10 * 60_000); }
    else if ([400, 401, 403, 404].includes(upstream.status)) skipped.set(key, now + 60 * 60_000);
    else skipped.set(key, now + 60_000);
    console.log(JSON.stringify({ event: "chat_model_failed", provider: c.provider, model: c.model, status: upstream.status }));
  }
  if (sawRateLimit) return json({ error: "The free AI has reached its limit for now." }, 429, { ...cors, "Retry-After": "600" });
  return json({ error: "AI temporarily unavailable", upstream_status: lastStatus }, 502, cors);
}

export default { fetch: (request, env) => handle(request, env) };

// Test hooks (not used by Cloudflare).
export const _internal = { visitors, feedbackVisitors, skipped, candidates, validate, cleanFeedback, LIMITS };
