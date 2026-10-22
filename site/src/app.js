/* FGF Intelligence — page logic. Depends on window.FGF (engine.js). */
(function () {
  "use strict";
  const F = window.FGF;
  const $ = (s, el) => (el || document).querySelector(s);
  const DATA = JSON.parse($("#fgf-data").textContent);
  let CONFIG = {};
  try { CONFIG = JSON.parse(($("#fgf-config") || {}).textContent || "{}"); } catch (e) { CONFIG = {}; }
  const INDEX = F.buildIndex(DATA.facts);
  const CHAMPIONS = ["Ajita", "Aliya", "Cocoon", "Doug Rockwell", "Eva von Trier", "Evan Rogers", "Jodie Beart", "Kama Moai",
    "Killer Bee", "Klara", "Lani Verita", "Lily", "Lucius Pullo", "Phade", "Riian Dessos", "Zora Dominii"];
  const STARTERS = [
    "I'm F2P at Core 28. What should I prioritise?",
    "What's the best way to do T100 without hurting GvG?",
    "How do I repair ships with Major Damage?",
    "What does Style Resonance give with 3 matching Champions?",
    "How many Migration Permits do I need to change server?",
    "When is the next maintenance?",
  ];
  const MAX_HISTORY = 8;

  // ---------------------------------------------------------------- storage
  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* private mode: keep in memory */ } },
  };

  // ------------------------------------------------------------------ state
  const state = {
    profile: Object.assign({ season: "", core: "", spending: "", champions: [], server: "" }, store.get("fgf.profile", {})),
    history: [],          // [{role, content}] sent to the AI for follow-ups (citations stripped)
    lastQuestion: "",
    ai: undefined,        // undefined = connecting; null = no AI here; otherwise {name, title, call, toolsOK}
    aiBlocked: false,     // AI declined/unavailable for this viewer: use instant answers
    busy: false,
    ctl: null,
  };
  const fmtDate = (d) => d.toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });
  const todayText = () => new Date().toLocaleDateString("en-GB", { weekday: "long", day: "numeric", month: "long", year: "numeric" });

  // ------------------------------------------------------------------- mode
  function setMode() {
    const el = $("#mode"), label = $("#mode-label");
    if (navigator.onLine === false) { el.dataset.mode = "offline"; label.textContent = "Offline"; el.title = "You're offline. Guides, facts and instant answers still work."; return; }
    if (state.ai === undefined) { el.dataset.mode = "pending"; label.textContent = "Connecting…"; el.title = ""; return; }
    if (state.ai && !state.aiBlocked) { el.dataset.mode = "ai"; label.textContent = "AI answers on"; el.title = state.ai.title; }
    else { el.dataset.mode = "instant"; label.textContent = "Instant answers"; el.title = "Showing the most relevant facts directly. Written AI answers are not available right now."; }
  }

  // AI backends share one shape: call(turns, {signal, onText, tools}) resolves {text, truncated}
  // or rejects {code, text?} using the same codes as Claude's sample capability.
  function claudeBackend(sample, toolsOK) {
    return { name: "claude", toolsOK, title: "Answers are written by Claude using your own Claude account.",
      call: (turns, o) => sample(turns, { signal: o.signal, cache: false, modelTier: "default", onText: o.onText, ...(o.tools ? { tools: o.tools } : {}) }) };
  }

  // The free AI proxy (Cloudflare Worker in front of Google Gemini). Streams
  // OpenAI-style server-sent events and switches models on its own.
  function proxyBackend(endpoint) {
    const base = endpoint.replace(/\/+$/, "");
    return { name: "proxy", toolsOK: false, title: "Answers are written by a free AI model from the FGF knowledge base.",
      async call(turns, o) {
        let res;
        try {
          res = await fetch(base + "/chat", { method: "POST", headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ messages: turns }), signal: o.signal });
        } catch (e) {
          throw { code: o.signal && o.signal.aborted ? "cancelled" : "upstream_error", message: String(e) };
        }
        if (!res.ok) {
          let err = {}; try { err = await res.json(); } catch (e) {}
          const code = res.status === 429 ? "rate_limited" : res.status === 403 ? "not_granted"
            : res.status === 413 ? "prompt_too_large" : res.status === 400 ? "invalid_request" : "upstream_error";
          throw { code, message: err.error || ("HTTP " + res.status) };
        }
        const reader = res.body.getReader(), dec = new TextDecoder();
        let buf = "", text = "", finish = "";
        try {
          for (;;) {
            const { value, done } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            let nl;
            while ((nl = buf.indexOf("\n")) >= 0) {
              const line = buf.slice(0, nl).trim(); buf = buf.slice(nl + 1);
              if (!line.startsWith("data:")) continue;
              const payload = line.slice(5).trim();
              if (payload === "[DONE]") continue;
              let j; try { j = JSON.parse(payload); } catch (e) { continue; }
              if (j.error) throw { code: "upstream_error", message: String(j.error.message || j.error), text };
              const ch = (j.choices || [])[0] || {};
              const delta = (ch.delta && ch.delta.content) || "";
              if (ch.finish_reason) finish = ch.finish_reason;
              if (delta) { text += delta; o.onText && o.onText({ text, delta }); }
            }
          }
        } catch (e) {
          if (o.signal && o.signal.aborted) throw { code: "cancelled", text };
          throw e && e.code ? e : { code: "upstream_error", message: String(e), text };
        }
        if (!text.trim()) throw { code: "empty_completion", message: "empty answer" };
        return { text, truncated: finish === "length" };
      } };
  }

  async function connectAI() {
    // 1) A configured free AI proxy (GitHub Pages deployment).
    if (CONFIG.aiEndpoint) {
      try {
        const ctl = new AbortController(); const timer = setTimeout(() => ctl.abort(), 8000);
        const r = await fetch(CONFIG.aiEndpoint.replace(/\/+$/, "") + "/health", { signal: ctl.signal });
        clearTimeout(timer);
        const h = r.ok ? await r.json() : null;
        if (h && h.ok) { state.ai = proxyBackend(CONFIG.aiEndpoint); setMode(); return; }
      } catch (e) { /* fall through */ }
    }
    // 2) Opened inside Claude: answers on the viewer's own Claude account.
    const c = window.claude;
    if (c && typeof c.use === "function") {
      try {
        const s = await c.use("sample");
        if (s) {
          let toolsOK = false;
          try { const l = await s.limits(); toolsOK = !!(l && l.tools); } catch (e) {}
          state.ai = claudeBackend(s, toolsOK); setMode(); return;
        }
      } catch (e) { /* fall through */ }
    }
    // 3) No AI available: instant answers from the knowledge base.
    state.ai = null; setMode();
  }

  // ------------------------------------------------------------------ views
  const VIEWS = ["ask", "guides", "facts"];
  function show(view, focus) {
    if (!VIEWS.includes(view)) view = "ask";
    for (const v of VIEWS) {
      $("#view-" + v).hidden = v !== view;
      $("#tab-" + v).setAttribute("aria-selected", String(v === view));
      $("#tab-" + v).tabIndex = v === view ? 0 : -1;
    }
    state.view = view;
    if (view === "facts") renderFacts();
    if (focus) $("#view-" + view + " h1").focus?.();
  }
  document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => { show(b.dataset.view); try { history.replaceState(null, "", "#" + b.dataset.view); } catch (e) {} }));
  $(".tabs").addEventListener("keydown", (e) => {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    const i = VIEWS.indexOf(state.view), n = VIEWS[(i + (e.key === "ArrowRight" ? 1 : VIEWS.length - 1)) % VIEWS.length];
    show(n); $("#tab-" + n).focus();
  });

  // --------------------------------------------------------------- profile
  function renderProfile() {
    const p = state.profile;
    $("#p-season").value = p.season || "";
    $("#p-core").value = p.core || "";
    const sp = document.querySelector(`input[name="spending"][value="${CSS.escape(p.spending || "")}"]`) || $("#sp-none");
    sp.checked = true;
    $("#p-server").value = p.server || "";
    const box = $("#p-champs"); box.innerHTML = "";
    for (const name of CHAMPIONS) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "champ"; b.textContent = name;
      b.setAttribute("aria-pressed", String(p.champions.includes(name)));
      b.addEventListener("click", () => {
        const on = b.getAttribute("aria-pressed") !== "true";
        b.setAttribute("aria-pressed", String(on));
        p.champions = on ? [...p.champions, name] : p.champions.filter((x) => x !== name);
        saveProfile();
      });
      box.appendChild(b);
    }
    summarizeProfile();
  }
  function summarizeProfile() {
    const p = state.profile, bits = [];
    if (p.season) bits.push(p.season);
    if (p.core) bits.push("Core " + p.core);
    if (p.spending) bits.push(p.spending.replace(" (no spending)", ""));
    if (p.champions.length) bits.push(p.champions.length + " Champion" + (p.champions.length > 1 ? "s" : ""));
    if (p.server) bits.push("Server " + p.server);
    $("#acc-summary").textContent = bits.length ? bits.join(" · ") : "Add your Core level, spending and Champions for answers that fit your account.";
  }
  let savedTimer;
  function saveProfile() {
    store.set("fgf.profile", state.profile);
    summarizeProfile();
    $("#saved").textContent = "Saved on this device";
    clearTimeout(savedTimer); savedTimer = setTimeout(() => { $("#saved").textContent = ""; }, 1800);
  }
  $("#p-season").addEventListener("change", (e) => { state.profile.season = e.target.value; saveProfile(); });
  $("#p-core").addEventListener("change", (e) => {
    const v = parseInt(e.target.value, 10);
    state.profile.core = Number.isFinite(v) ? Math.min(35, Math.max(1, v)) : "";
    e.target.value = state.profile.core; saveProfile();
  });
  document.querySelectorAll('input[name="spending"]').forEach((r) => r.addEventListener("change", (e) => { state.profile.spending = e.target.value; saveProfile(); }));
  $("#p-server").addEventListener("change", (e) => { state.profile.server = e.target.value.trim().slice(0, 20); saveProfile(); });

  // ------------------------------------------------------------- side info
  function renderNews() {
    const ul = $("#news"); ul.innerHTML = "";
    for (const { f, d } of F.latestOfficial(DATA.facts, 5)) {
      const li = document.createElement("li");
      li.innerHTML = `<time datetime="${d.toISOString().slice(0, 10)}">${F.esc(fmtDate(d))}</time><p>${F.esc(f.c)}</p>`;
      ul.appendChild(li);
    }
  }
  function renderFreshness() {
    const m = DATA.meta, d = m.synced ? new Date(m.synced) : null;
    const when = d && !isNaN(d) ? fmtDate(d) : "recently";
    $("#freshness").textContent = `${m.facts.toLocaleString()} facts · ${m.official.toLocaleString()} official or tested · updated ${when}`;
    $("#facts-eyebrow").textContent = `${m.facts.toLocaleString()} facts · updated ${when}`;
    $("#foot-data").textContent = `Knowledge base synced ${when} from the FGF Intelligence evidence store: ${m.facts.toLocaleString()} facts, ${m.tier1} Tier 1, ${m.plans} curated event plans.`;
  }
  function renderStarters() {
    const box = $("#starters"); box.innerHTML = "";
    for (const q of STARTERS) {
      const b = document.createElement("button");
      b.type = "button"; b.className = "starter"; b.textContent = q;
      b.addEventListener("click", () => { $("#question").value = q; ask(q); });
      box.appendChild(b);
    }
  }

  // ------------------------------------------------------------- evidence
  function gatherEvidence(question) {
    const reg = F.makeRegistry();
    const words = question.trim().split(/\s+/).length;
    const followUp = state.lastQuestion && words <= 8;
    const query = followUp ? question + " " + state.lastQuestion : question;
    const plans = F.matchPlans(DATA.plans, query).slice(0, 2);
    for (const p of plans) reg.add("p:" + p.id, F.planEntry(p));
    for (const h of INDEX.search(query, { limit: 12 })) reg.add("f:" + h.doc.i, F.factEntry(h.doc));
    if (/f2p|free/i.test(state.profile.spending || "") && !/f2p|free to play/i.test(query)) {
      for (const h of INDEX.search(query + " F2P", { limit: 4 })) reg.add("f:" + h.doc.i, F.factEntry(h.doc));
    }
    const qTok = new Set(F.tokenize(query));
    for (const c of DATA.conflicts) {
      const overlap = F.tokenize(c.topic + " " + c.official).filter((t) => qTok.has(t)).length;
      if (overlap >= 2) reg.add("c:" + c.id, { kind: "fact", tier: 1, category: "Recorded disagreement",
        text: `Sources disagree on: ${c.topic}. Official/in-game evidence: ${c.official}. Other claim: ${c.other}.` + (c.decision ? ` Decision: ${c.decision}.` : "") });
    }
    return { reg, plans };
  }

  function searchTool(reg) {
    return {
      name: "search_knowledge",
      description: "Search the FGF knowledge base for more facts when the supplied evidence does not cover the question. Returns up to 6 facts, each with a ref like E14 that you may cite. Use short, specific queries with game terms.",
      inputSchema: { type: "object", properties: { query: { type: "string", description: "What to look for, e.g. 'Energy Core 33 unlock'" } }, required: ["query"] },
      execute(input) {
        const q = String(input && input.query || "").slice(0, 200);
        if (!q) throw new Error("query is required");
        const out = [];
        for (const h of INDEX.search(q, { limit: 6 })) {
          const ref = reg.add("f:" + h.doc.i, F.factEntry(h.doc));
          out.push({ ref, tier: F.TIER_LABEL[h.doc.t], category: h.doc.g, fact: h.doc.c });
        }
        return out.length ? out : "No matching facts. Try different wording.";
      },
    };
  }

  // ---------------------------------------------------------------- render
  function tierChip(t) { return `<span class="chip t${t}">${F.esc(F.TIER_LABEL[t] || "Unverified")}</span>`; }
  function sourceItem(e) {
    const link = e.source && /^https?:\/\//.test(e.source) ? ` · <a href="${F.esc(e.source)}" target="_blank" rel="noopener noreferrer">source</a>` : "";
    const meta = e.kind === "plan"
      ? `<span class="chip plan">Curated event plan</span> <span>${F.esc(e.title)}</span>`
      : `${tierChip(e.tier)}<span>${F.esc(e.category || "")}</span>${e.season ? `<span>${F.esc(e.season)}</span>` : ""}${e.state === "candidate" ? "<span>not yet verified</span>" : ""}${link}`;
    const text = e.kind === "plan" ? `Hand-built plan. <button type="button" class="btn ghost open-guide" data-plan="${F.esc(e.planId)}">Open guide</button>` : F.esc(e.text);
    return `<li class="src" id="__ID__-${e.ref}"><span class="ref">${e.ref}</span><p>${text}</p><div class="meta">${meta}</div></li>`;
  }
  function sourcesBlock(turnId, entries, title, open) {
    if (!entries.length) return "";
    const items = entries.map((e) => sourceItem(e).replace("__ID__", turnId)).join("");
    return `<details class="sources"${open ? " open" : ""}><summary>${F.esc(title)} (${entries.length})</summary><ul class="src-list">${items}</ul></details>`;
  }
  function wireTurn(el) {
    el.addEventListener("click", (ev) => {
      const cite = ev.target.closest(".cite");
      if (cite) {
        const det = $("details.sources", el); if (det) det.open = true;
        const item = $(`#${el.id}-${cite.dataset.ref}`);
        if (item) {
          el.querySelectorAll(".src.hl").forEach((x) => x.classList.remove("hl"));
          item.classList.add("hl"); item.scrollIntoView({ block: "nearest", behavior: "smooth" }); item.tabIndex = -1; item.focus({ preventScroll: true });
        }
      }
      const g = ev.target.closest(".open-guide");
      if (g) { show("guides"); const target = $("#guide-" + g.dataset.plan); if (target) target.scrollIntoView({ block: "start" }); }
      const r = ev.target.closest(".retry");
      if (r) { $("#question").value = r.dataset.q; ask(r.dataset.q); }
    });
  }

  let turnSeq = 0;
  function newTurn(question) {
    const id = "t" + (++turnSeq) + "-" + Date.now().toString(36);
    const el = document.createElement("article");
    el.className = "turn"; el.id = id;
    el.innerHTML = `<div class="q"></div><div class="a" aria-busy="true"><div class="a-head"><span class="eyebrow">FGF Intelligence</span></div><div class="a-body"><p class="thinking"><span class="pulse" aria-hidden="true"></span><span>Searching the knowledge base…</span></p></div></div>`;
    $(".q", el).textContent = question;
    wireTurn(el);
    $("#thread").appendChild(el);
    $("#ask-grid").classList.add("has-thread");
    $("#new-chat").hidden = false;
    $("#question").placeholder = "Ask a follow-up…";
    el.scrollIntoView({ block: "start", behavior: "smooth" });
    return el;
  }

  function instantAnswer(el, question, reg, plans, note) {
    const facts = reg.items.filter((e) => e.kind === "fact").slice(0, 6);
    let body = "";
    if (plans.length) body += `<p><strong>There's a curated plan for this:</strong> ${plans.map((p) => `<button type="button" class="btn ghost open-guide" data-plan="${F.esc(p.id)}">${F.esc(p.title)}</button>`).join(" ")}</p>`;
    if (facts.length) {
      body += `<p>Here's what the knowledge base says, strongest sources first:</p><ul>` +
        facts.slice().sort((a, b) => a.tier - b.tier).map((e) => `<li>${F.esc(e.text)} <button type="button" class="cite" data-ref="${e.ref}" aria-label="Source ${e.ref}">${e.ref}</button></li>`).join("") + `</ul>`;
    } else if (!plans.length) {
      body += `<p>I couldn't find anything about that in the knowledge base. Try naming the event, building, resource or Champion.</p>`;
    }
    $(".a-body", el).innerHTML = body;
    $(".a-head", el).innerHTML = `<span class="eyebrow">Instant answer</span><span class="chip">From the knowledge base</span>`;
    const used = reg.items.filter((e) => facts.includes(e) || (e.kind === "plan"));
    $(".a", el).insertAdjacentHTML("beforeend",
      sourcesBlock(el.id, used, "Sources", false) +
      `<p class="note">${F.esc(note || defaultInstantNote())}</p>`);
    $(".a", el).setAttribute("aria-busy", "false");
  }

  function defaultInstantNote() {
    if (CONFIG.aiEndpoint) return "Written AI answers are unavailable right now, so these are the most relevant facts. Try again in a little while.";
    return "For a written answer tailored to your account, open this page while signed in to Claude and allow AI answers.";
  }
  function errorCopy(code) {
    const proxy = state.ai && state.ai.name === "proxy";
    const copy = {
      not_granted: proxy ? "The AI service isn't accepting requests from this page, so here are the most relevant facts instead."
        : "AI answers are switched off for this page, so here are the most relevant facts instead.",
      sampling_disabled: "Claude isn't available on this account, so here are the most relevant facts instead.",
      capability_disabled: "AI answers aren't available in this view, so here are the most relevant facts instead.",
      not_declared: "AI answers aren't available in this view, so here are the most relevant facts instead.",
      rate_limited: proxy ? "The free AI is busy or has reached today's limit. Here are the most relevant facts; written answers will be back soon."
        : "You've reached your Claude usage limit for now. Here are the most relevant facts; try a written answer again later.",
      session_expired: "Your Claude sign-in expired. Sign in again for written answers; here are the most relevant facts meanwhile.",
      prompt_too_large: "That question pulled in too much material. Try asking about one event or mechanic at a time.",
      refused: "The AI couldn't answer that as asked. Try rephrasing the question.",
      empty_completion: "The AI returned an empty answer. Try rephrasing the question.",
      invalid_request: "That request couldn't be sent. Try a shorter question.",
    };
    return copy[code] || "The AI didn't respond this time, so here are the most relevant facts.";
  }
  const PERMANENT = new Set(["not_granted", "sampling_disabled", "capability_disabled", "not_declared", "capability_removed"]);

  function setBusy(b) {
    state.busy = b;
    $("#send").disabled = b;
    $("#stop").hidden = !b;
    $("#question").setAttribute("aria-busy", String(b));
  }

  async function ask(raw) {
    const question = String(raw || "").trim().slice(0, 1200);
    if (!question || state.busy) return;
    $("#question").value = "";
    const el = newTurn(question);
    const { reg, plans } = gatherEvidence(question);
    const prevQuestion = state.lastQuestion;
    state.lastQuestion = question;

    if (state.ai === undefined) {
      // Give the AI connection a moment before falling back.
      $(".thinking span:last-child", el).textContent = "Connecting to the AI…";
      for (let i = 0; i < 40 && state.ai === undefined; i++) await new Promise((r) => setTimeout(r, 250));
    }
    const ai = state.ai;
    if (navigator.onLine === false) {
      instantAnswer(el, question, reg, plans, "You're offline, so here are the most relevant facts. Written AI answers come back when you reconnect.");
      $("#announcer").textContent = "Answer ready.";
      return;
    }
    if (!ai || state.aiBlocked) {
      instantAnswer(el, question, reg, plans);
      $("#announcer").textContent = "Answer ready.";
      return;
    }

    setBusy(true);
    const ctl = new AbortController(); state.ctl = ctl;
    const body = $(".a-body", el);
    $(".thinking span:last-child", el).textContent = `Found ${reg.items.length} relevant source${reg.items.length === 1 ? "" : "s"}. Writing your answer…`;
    const profileTxt = F.profileText(state.profile);
    const turns = F.buildTurns({ question, history: state.history.slice(-MAX_HISTORY), registry: reg, profile: state.profile, today: todayText() });
    const opts = { signal: ctl.signal, onText: ({ text }) => { body.innerHTML = F.renderMarkdown(text); } };
    if (ai.toolsOK) opts.tools = [searchTool(reg)];

    let text = "", truncated = false, failure = null;
    try {
      const res = await ai.call(turns, opts);
      text = res.text; truncated = res.truncated;
    } catch (e) {
      failure = e && e.code ? e : { code: "upstream_error" };
      text = failure.text || "";
    } finally {
      setBusy(false); state.ctl = null;
    }

    if (failure && PERMANENT.has(failure.code)) {
      state.aiBlocked = true; setMode();
      instantAnswer(el, question, reg, plans, errorCopy(failure.code));
      $("#announcer").textContent = "Answer ready.";
      return;
    }
    if (failure && !text) {
      if (failure.code === "cancelled") { body.innerHTML = `<p class="note">Stopped.</p>`; $(".a", el).setAttribute("aria-busy", "false"); return; }
      instantAnswer(el, question, reg, plans, errorCopy(failure.code));
      $(".a", el).insertAdjacentHTML("beforeend", `<div class="actions"><button type="button" class="btn retry" data-q="${F.esc(question)}">Try a written answer again</button></div>`);
      return;
    }

    body.innerHTML = F.renderMarkdown(text);
    const check = F.factCheck(text, reg, [question, profileTxt, todayText(), prevQuestion].join(" "));
    const cited = check.refs.map((r) => reg.get(r)).filter(Boolean);
    const head = $(".a-head", el);
    head.insertAdjacentHTML("beforeend", check.passed
      ? `<span class="chip ok" title="Every cited source exists and every number appears in a source.">✓ Checked against sources</span>`
      : `<span class="chip warn" title="Some details could not be matched to a source.">Check details</span>`);
    let foot = "";
    if (!check.passed) {
      const bits = [];
      if (check.unsupported.length) bits.push(`these figures don't appear in any source: ${check.unsupported.slice(0, 5).join(", ")}`);
      if (check.unknownRefs.length) bits.push(`some references point to nothing (${check.unknownRefs.join(", ")})`);
      if (check.uncited) bits.push("the answer doesn't cite its sources");
      foot += `<p class="note warn">Double-check in-game: ${F.esc(bits.join("; "))}.</p>`;
    }
    if (truncated) foot += `<p class="note">The answer was cut short. Ask for one part at a time for more detail.</p>`;
    if (failure && failure.code === "cancelled") foot += `<p class="note">Stopped.</p>`;
    else if (failure) foot += `<p class="note warn">The answer was interrupted. <button type="button" class="btn ghost retry" data-q="${F.esc(question)}">Try again</button></p>`;
    const related = cited.length ? [] : reg.items.slice(0, 4);
    $(".a", el).insertAdjacentHTML("beforeend",
      sourcesBlock(el.id, cited.length ? cited : related, cited.length ? "Sources" : "Related facts", false) + foot);
    $(".a", el).setAttribute("aria-busy", "false");
    $("#announcer").textContent = "Answer ready.";

    if (!failure) {
      state.history.push({ role: "user", content: question }, { role: "assistant", content: text.replace(/\s*\[E\d+(?:\s*[,;]\s*E?\d+)*\]/g, "") });
      state.history = state.history.slice(-MAX_HISTORY);
    }
  }

  // ----------------------------------------------------------- composer
  $("#composer").addEventListener("submit", (e) => { e.preventDefault(); ask($("#question").value); });
  $("#question").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); ask($("#question").value); }
  });
  $("#stop").addEventListener("click", () => state.ctl && state.ctl.abort());
  $("#new-chat").addEventListener("click", () => {
    if (state.busy && state.ctl) state.ctl.abort();
    state.history = []; state.lastQuestion = "";
    $("#thread").innerHTML = ""; $("#new-chat").hidden = true; $("#ask-grid").classList.remove("has-thread");
    $("#question").placeholder = "e.g. I'm F2P at Core 28. What should I prioritise this week?";
    $("#question").focus();
  });

  // --------------------------------------------------------------- guides
  function renderGuides() {
    const nav = $("#guide-nav"), box = $("#guides");
    nav.innerHTML = ""; box.innerHTML = "";
    for (const p of DATA.plans) {
      const a = document.createElement("a");
      a.className = "chip plan"; a.href = "#guides"; a.textContent = p.title.split(" — ")[0] + (p.id === "t100-days" ? " (day by day)" : "");
      a.addEventListener("click", (e) => { e.preventDefault(); $("#guide-" + p.id).scrollIntoView({ block: "start" }); });
      nav.appendChild(a);
      const head = (p.headers && p.headers.length ? p.headers : p.rows[0].map((_, j) => "Column " + (j + 1)));
      const rows = p.rows.map((r) => "<tr>" + r.map((v, j) => `<td data-label="${F.esc(head[j] || "")}">${F.esc(v)}</td>`).join("") + "</tr>").join("");
      const sec = document.createElement("section");
      sec.className = "guide"; sec.id = "guide-" + p.id; sec.setAttribute("aria-labelledby", "gh-" + p.id);
      sec.innerHTML = `<h2 id="gh-${p.id}">${F.esc(p.title)}</h2><p>${F.esc(p.summary || "")}</p>
        <div class="table-scroll" tabindex="0" role="region" aria-label="${F.esc(p.title)} plan"><table><thead><tr>${head.map((h) => `<th scope="col">${F.esc(h)}</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table></div>
        <div class="actions"><button type="button" class="btn ask-plan">Ask about this event</button></div>`;
      $(".ask-plan", sec).addEventListener("click", () => {
        show("ask");
        const q = $("#question"); q.value = `For ${p.title.split(" — ")[0]}: `; q.focus(); q.setSelectionRange(q.value.length, q.value.length);
      });
      box.appendChild(sec);
    }
  }

  // ---------------------------------------------------------------- facts
  function renderCategories() {
    const counts = new Map();
    for (const f of DATA.facts) counts.set(f.g, (counts.get(f.g) || 0) + 1);
    const sel = $("#f-cat");
    [...counts.entries()].filter(([, n]) => n >= 5).sort((a, b) => b[1] - a[1]).forEach(([g, n]) => {
      const o = document.createElement("option"); o.value = g; o.textContent = `${g} (${n})`; sel.appendChild(o);
    });
  }
  function factItem(f) {
    const link = f.u && /^https?:\/\//.test(f.u) ? `<a href="${F.esc(f.u)}" target="_blank" rel="noopener noreferrer">source</a>` : (f.u ? `<span>${F.esc(f.u)}</span>` : "");
    return `<li class="fact"><p>${F.esc(f.c)}</p><div class="meta">${tierChip(f.t)}<span>${F.esc(f.g)}</span>${f.v ? `<span>${F.esc(f.v)}</span>` : ""}${f.s === "candidate" ? "<span>not yet verified</span>" : ""}${f.s === "conflicting" ? '<span class="chip warn">disputed</span>' : ""}${link}</div></li>`;
  }
  let factTimer;
  function renderFacts() {
    const q = $("#f-q").value.trim(), cat = $("#f-cat").value, official = $("#f-official").checked;
    let list, label;
    if (q) {
      list = INDEX.search(q, { limit: 40, category: cat, officialOnly: official, minScore: 0.5 }).map((h) => h.doc);
      label = list.length ? `${list.length} most relevant fact${list.length > 1 ? "s" : ""} for “${q}”` : `No facts match “${q}”. Try a different word or remove filters.`;
    } else {
      list = DATA.facts.filter((f) => (!cat || f.g === cat) && (!official || f.t <= 2))
        .map((f) => ({ f, d: F.factDate(f) })).sort((a, b) => (b.d || 0) - (a.d || 0) || a.f.t - b.f.t).slice(0, 40).map((x) => x.f);
      label = `Showing ${list.length} of ${DATA.facts.filter((f) => (!cat || f.g === cat) && (!official || f.t <= 2)).length} facts, newest dated first. Search to narrow down.`;
    }
    $("#f-count").textContent = label;
    $("#f-list").innerHTML = list.map(factItem).join("");
  }
  $("#fact-filters").addEventListener("submit", (e) => e.preventDefault());
  $("#f-q").addEventListener("input", () => { clearTimeout(factTimer); factTimer = setTimeout(renderFacts, 160); });
  $("#f-cat").addEventListener("change", renderFacts);
  $("#f-official").addEventListener("change", renderFacts);

  // ------------------------------------------------------------------- app
  // Installable app (PWA) features: only when the builder enabled them (GitHub Pages).
  function setupApp() {
    window.addEventListener("online", () => { setMode(); if (state.ai === null) connectAI(); });
    window.addEventListener("offline", setMode);
    if (!CONFIG.pwa) return;
    const standalone = window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
    let deferred = null;
    window.addEventListener("beforeinstallprompt", (e) => { e.preventDefault(); deferred = e; if (!standalone) $("#install").hidden = false; });
    $("#install").addEventListener("click", async () => {
      if (!deferred) return;
      deferred.prompt();
      try { await deferred.userChoice; } catch (e) {}
      deferred = null; $("#install").hidden = true;
    });
    window.addEventListener("appinstalled", () => { $("#install").hidden = true; });
    const ios = /iphone|ipad|ipod/i.test(navigator.userAgent) && !window.MSStream;
    if (ios && !standalone && !store.get("fgf.iosTipDismissed", false)) $("#ios-tip").hidden = false;
    $("#ios-tip-close").addEventListener("click", () => { $("#ios-tip").hidden = true; store.set("fgf.iosTipDismissed", true); });
    if ("serviceWorker" in navigator && location.protocol === "https:") {
      navigator.serviceWorker.register("sw.js").then((reg) => {
        const offer = (w) => { if (!w) return; $("#update-tip").hidden = false; $("#update-reload").onclick = () => w.postMessage("skip-waiting"); };
        if (reg.waiting && navigator.serviceWorker.controller) offer(reg.waiting);
        reg.addEventListener("updatefound", () => {
          const w = reg.installing;
          w && w.addEventListener("statechange", () => { if (w.state === "installed" && navigator.serviceWorker.controller) offer(w); });
        });
        // Check for fresh data whenever the app comes back to the foreground.
        document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") reg.update().catch(() => {}); });
      }).catch(() => {});
      let reloaded = false;
      navigator.serviceWorker.addEventListener("controllerchange", () => { if (!reloaded && !state.busy) { reloaded = true; location.reload(); } });
    }
  }

  // ------------------------------------------------------------------ boot
  function start(saved) {
    renderFreshness(); renderNews(); renderStarters(); renderProfile(); renderGuides(); renderCategories();
    if (!state.profile.core && !state.profile.spending) $("#account").open = window.matchMedia("(min-width: 921px)").matches;
    if (saved && saved.threadHtml) {
      $("#thread").innerHTML = saved.threadHtml;
      $("#thread").querySelectorAll(".turn").forEach(wireTurn);
      state.history = saved.history || []; state.lastQuestion = saved.lastQuestion || "";
      if (state.history.length) { $("#new-chat").hidden = false; $("#ask-grid").classList.add("has-thread"); }
    }
    const hash = (location.hash || "").replace("#", "");
    show(saved && saved.view ? saved.view : (VIEWS.includes(hash) ? hash : "ask"));
    setupApp();
    setMode();
    connectAI();
  }
  const hot = window.claude && window.claude.hot;
  if (hot && typeof hot.snapshot === "function") {
    try { hot.snapshot(() => ({ threadHtml: state.busy ? "" : $("#thread").innerHTML, history: state.history, lastQuestion: state.lastQuestion, view: state.view })); } catch (e) {}
  }
  if (hot && typeof hot.ready === "function") hot.ready(start); else start((hot && hot.data) || {});
})();
