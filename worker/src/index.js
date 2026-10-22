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
 * Routes:  GET /health  ->  {ok, providers, models}
 *          POST /chat   ->  body {messages:[{role:"user"|"assistant", content}]}
 *                          response: OpenAI-style server-sent events (text/event-stream)
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
};

// Per-instance memory: visitor buckets and temporarily skipped models.
const visitors = new Map();
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

function rateLimited(ip, now) {
  const windowMs = 10 * 60 * 1000;
  const hits = (visitors.get(ip) || []).filter((t) => now - t < windowMs);
  if (hits.length >= LIMITS.perVisitorPer10Min) { visitors.set(ip, hits); return true; }
  hits.push(now); visitors.set(ip, hits);
  if (visitors.size > 5000) visitors.clear();   // keep memory bounded
  return false;
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
    return json({ ok: c.length > 0, providers: [...new Set(c.map((x) => x.provider))], models: c.length }, 200, cors);
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
export const _internal = { visitors, skipped, candidates, validate, LIMITS };
