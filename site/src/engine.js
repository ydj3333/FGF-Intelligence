/* FGF Intelligence — in-page engine: search, prompt building, fact-check, safe rendering.
   Pure functions only (no DOM), so it runs in the page and in Node tests. */
(function (root) {
  "use strict";

  // ------------------------------------------------------------------ text
  const STOP = new Set(("a an the and or but if then of to in on at by for with from into about as is are was were be been being it its this that these those there here i me my we our you your they them their he she his her what which who whom when where why how do does did can could should would will shall may might must have has had so just also very really any some all get got im dont much many more most than too up out not no yes please tell know want need thing things game fgf guys like").split(" "));
  const GENERIC = new Set(["best", "way", "strategy", "tip", "guide", "good", "better", "plan", "help", "work", "use", "doing", "easy", "fast"]);
  const GENERIC_WEIGHT = 0.3;

  function stem(t) {
    if (t.length <= 3 || /^\d+$/.test(t)) return t;
    const rules = [["ies", "y"], ["oes", "o"], ["ing", ""], ["ed", ""], ["es", ""], ["s", ""]];
    for (const [suf, rep] of rules) {
      if (t.endsWith(suf) && t.length - suf.length >= 3) {
        if (suf === "es" && !/(ses|xes|zes|ches|shes)$/.test(t)) return t.slice(0, -1);
        return t.slice(0, t.length - suf.length) + rep;
      }
    }
    return t;
  }

  function tokenize(text, keepStop) {
    const out = [];
    const m = String(text || "").toLowerCase().replace(/’/g, "'").match(/[a-z0-9]+(?:[.,][0-9]+)?%?/g) || [];
    for (let raw of m) {
      raw = raw.replace(/%$/, "");
      if (!keepStop && STOP.has(raw)) continue;
      out.push(stem(raw));
    }
    return out;
  }
  const phraseKey = (s) => tokenize(s, true).join(" ");

  // FGF vocabulary: each group's members are interchangeable.
  const GLOSSARY_SRC = [
    ["champion", "champions", "hero", "heroes", "commander", "commanders"],
    ["f2p", "free to play", "free-to-play", "no spend", "non spender", "without spending", "zero spend"],
    ["p2p", "pay to play", "spender", "whale", "paid", "purchase", "pack", "packs"],
    ["t100", "top 100", "top100"],
    ["gvg", "guild vs guild", "guild versus guild", "guild war", "guild wars"],
    ["pvp", "player vs player"],
    ["cp", "command point", "command points"],
    ["energy core", "core level", "core lvl"],
    ["fusion seed", "fusion seeds"],
    ["repair", "fix", "heal", "recover", "repair module", "repair modules"],
    ["damaged", "damage", "destroyed", "broken"],
    ["guild", "alliance", "commerce guild", "clan"],
    ["kaboom robot", "kaboom robots", "kaboom"],
    ["shared moonlight", "shadow moonlight", "moonlight event"],
    ["moonsoil", "lunar soil", "moon soil"],
    ["ion", "ionic"],
    ["lineup", "team", "composition", "comp", "formation", "squad"],
    ["cost", "costs", "price", "spend", "how much", "required"],
    ["unlock", "unlocks", "available", "open", "opens", "access"],
    ["speedup", "speed up", "speedups", "acceleration"],
    ["credits", "credit", "money", "gold"],
    ["flagship", "flagships", "mothership"],
    ["server migration", "migration", "migrate", "transfer server", "move server"],
    ["maintenance", "downtime", "server update", "patch"],
    ["season 2", "s2"], ["season 1", "s1"], ["season 3", "s3"],
  ];
  const GLOSSARY = GLOSSARY_SRC.map((g) => [...new Set(g.map(phraseKey).filter(Boolean))]);

  function glossaryExpand(query) {
    const q = " " + phraseKey(query) + " ";
    const extra = [];
    for (const g of GLOSSARY) {
      if (g.some((k) => q.includes(" " + k + " "))) for (const k of g) if (!q.includes(" " + k + " ")) extra.push(k);
    }
    return [...new Set(extra)];
  }

  const NOISE = ["you know", "here we go", "or something like that", "so that's what's up", "okay, so", "okay so", "right here",
    "i wanted to show you", "one thing i learned", "woo", "uh ", " um ", "gonna", "let me", "as you can see", "oh no", "guys",
    "subscribe", "for this test", "hot bar", "i think", "i guess", "kind of", "sort of", "basically", "actually"];
  function noiseScore(text, tier) {
    if (tier <= 2) return 0;
    const low = " " + String(text || "").toLowerCase() + " ";
    let s = Math.min(1, 0.35 * NOISE.filter((m) => low.includes(m)).length);
    const t = String(text || "").trim();
    if (t && t[0] === t[0].toLowerCase() && /[a-z]/.test(t[0])) s += 0.35;
    if (t && !/[.!?)"'…]$/.test(t)) s += 0.15;
    if (t.length > 220) s += 0.2;
    return Math.min(1, s);
  }

  // ----------------------------------------------------------------- index
  function buildIndex(facts) {
    const K1 = 1.4, B = 0.72, W = { c: 1.0, g: 0.45, n: 0.25 };
    const docs = [], tfs = [], lens = [], phr = [], df = new Map(), postings = new Map();
    facts.forEach((f, i) => {
      const tf = new Map(); let len = 0;
      for (const [field, w] of Object.entries(W)) {
        const toks = tokenize(field === "n" ? String(f.n || "").slice(0, 400) : f[field]);
        for (const t of toks) tf.set(t, (tf.get(t) || 0) + w);
        len += w * toks.length;
      }
      for (const t of tf.keys()) {
        df.set(t, (df.get(t) || 0) + 1);
        if (!postings.has(t)) postings.set(t, []);
        postings.get(t).push(docs.length);
      }
      docs.push({ ...f, i, noise: noiseScore(f.c, f.t) });
      tfs.push(tf); lens.push(Math.max(1, len));
      phr.push(" " + phraseKey(f.c + " " + f.g) + " ");
    });
    const N = Math.max(1, docs.length);
    const avg = lens.reduce((a, b) => a + b, 0) / N;
    // Dated facts: for "when / next / latest" questions, newer notices rank higher.
    const dates = docs.map((d) => factDate(d));
    const newest = Math.max(0, ...dates.filter(Boolean).map((d) => +d));
    const TIME_Q = /\b(when|next|upcoming|latest|recent|new|newest|today|tomorrow|this week|schedule|date)\b/i;
    const idf = new Map(); for (const [t, d] of df) idf.set(t, Math.log(1 + (N - d + 0.5) / (d + 0.5)));

    function bm25(i, terms) {
      const tf = tfs[i], norm = K1 * (1 - B + B * lens[i] / avg); let s = 0;
      for (const [t, qw] of terms) { const f = tf.get(t); if (f) s += qw * (idf.get(t) || 0) * (f * (K1 + 1)) / (f + norm); }
      return s;
    }

    function search(query, opts) {
      opts = opts || {};
      const limit = opts.limit || 8, minScore = opts.minScore == null ? 0.8 : opts.minScore;
      const base = tokenize(query);
      if (!base.length) return [];
      const terms = new Map();
      for (const t of base) terms.set(t, Math.max(terms.get(t) || 0, GENERIC.has(t) ? GENERIC_WEIGHT : 1));
      const expPhrases = [];
      for (const ph of glossaryExpand(query)) {
        const toks = ph.split(" ");
        if (toks.length === 1) { if (!terms.has(toks[0])) terms.set(toks[0], 0.6); }
        else { expPhrases.push(ph); for (const t of toks) if (!STOP.has(t) && !terms.has(t)) terms.set(t, 0.35); }
      }
      // Shorthand absent from the data ("T100") hands its weight to the expansion ("Top 100").
      const satisfiedBy = new Map();
      for (const t of new Set(base)) {
        if (postings.has(t)) continue;
        for (const g of GLOSSARY) {
          if (!g.includes(t)) continue;
          for (const member of g) {
            if (member === t) continue;
            const mt = member.split(" ").filter((x) => !STOP.has(x));
            for (const x of mt) terms.set(x, Math.max(terms.get(x) || 0, mt.length === 1 ? 1 : 0.85));
            if (mt.length > 1 && !expPhrases.includes(member)) expPhrases.push(member);
            if (!satisfiedBy.has(t)) satisfiedBy.set(t, new Set());
            mt.forEach((x) => satisfiedBy.get(t).add(x));
          }
        }
      }
      let content = [...new Set(base)].filter((t) => !GENERIC.has(t));
      if (!content.length) content = [...new Set(base)];
      const qk = phraseKey(query).split(" ");
      const bigrams = [];
      for (let k = 0; k + 1 < qk.length; k++) if (!STOP.has(qk[k]) && !STOP.has(qk[k + 1])) bigrams.push(qk[k] + " " + qk[k + 1]);

      const cand = new Set();
      for (const t of terms.keys()) for (const i of postings.get(t) || []) cand.add(i);
      const exclude = new Set(opts.exclude || []);
      const cat = (opts.category || "").toLowerCase();
      const timeQuestion = TIME_Q.test(String(query));
      const hits = [];
      for (const i of cand) {
        const d = docs[i];
        if (exclude.has(i)) continue;
        if (opts.officialOnly && d.t > 2) continue;
        if (cat && d.g.toLowerCase() !== cat) continue;
        let s = bm25(i, terms);
        if (s <= 0) continue;
        for (const bg of bigrams) if (phr[i].includes(" " + bg + " ")) s += 0.9;
        for (const ph of expPhrases) if (phr[i].includes(" " + ph + " ")) s += 0.6;
        const tf = tfs[i];
        const matched = content.filter((t) => tf.has(t) || (satisfiedBy.has(t) && [...satisfiedBy.get(t)].every((x) => tf.has(x))));
        s *= 0.6 + 0.8 * (matched.length / content.length);
        s *= ({ 1: 1.18, 2: 1.10, 3: 0.95 })[d.t] || 0.85;
        s *= d.s === "current" ? 1.05 : 0.92;
        s *= 1 - 0.6 * d.noise;
        if (timeQuestion && dates[i] && newest) {
          const ageDays = (newest - dates[i]) / 864e5;
          s *= 1 + 0.6 * Math.max(0, 1 - ageDays / 45);
        }
        if (s >= minScore) hits.push({ doc: d, score: s });
      }
      hits.sort((a, b) => b.score - a.score || a.doc.t - b.doc.t);
      // Near-duplicate collapse.
      const kept = [], sigs = [];
      for (const h of hits) {
        const toks = new Set(tokenize(h.doc.c));
        const dup = sigs.some((s) => { let inter = 0; for (const x of toks) if (s.has(x)) inter++; const uni = toks.size + s.size - inter; return uni && inter / uni >= 0.8; });
        if (!dup) { kept.push(h); sigs.push(toks); }
        if (kept.length >= limit) break;
      }
      return kept;
    }
    return { docs, search, size: docs.length };
  }

  function matchPlans(plans, text) {
    const q = " " + String(text || "").toLowerCase().replace(/[^a-z0-9 ]+/g, " ").replace(/\s+/g, " ") + " ";
    return plans.filter((p) => p.keywords.some((k) => q.includes(" " + k + " ") || q.includes(" " + k.replace(/ /g, "") + " ")));
  }

  function planText(p, maxChars) {
    const lines = [p.title, p.summary];
    const hdr = p.headers && p.headers.length ? p.headers : null;
    for (const r of p.rows) lines.push(hdr ? r.map((v, j) => (hdr[j] ? hdr[j] + ": " : "") + v).join(" | ") : r.join(" | "));
    const s = lines.filter(Boolean).join("\n");
    return s.length > (maxChars || 2600) ? s.slice(0, (maxChars || 2600) - 1) + "…" : s;
  }

  // ------------------------------------------------------------- evidence
  // A per-answer registry assigns stable [E#] refs.
  function makeRegistry() {
    const items = [], byKey = new Map();
    return {
      items,
      add(key, entry) {
        if (byKey.has(key)) return byKey.get(key);
        const ref = "E" + (items.length + 1);
        items.push({ ref, ...entry });
        byKey.set(key, ref);
        return ref;
      },
      get(ref) { return items.find((x) => x.ref === ref); },
      text() { return items.map((x) => x.text + " " + (x.notes || "")).join("\n"); },
    };
  }

  const TIER_LABEL = { 1: "Tier 1 · in-game/official", 2: "Tier 2 · wiki/tested", 3: "Tier 3 · community report", 4: "Tier 4 · unverified" };

  function factEntry(d) {
    return { kind: "fact", text: d.c, notes: d.n, tier: d.t, category: d.g, season: d.v, state: d.s, source: d.u, index: d.i };
  }
  function planEntry(p) {
    return { kind: "plan", text: planText(p), tier: 2, category: "Curated event plan", title: p.title, planId: p.id, source: "FGF curated plan" };
  }

  function formatEvidence(reg) {
    return reg.items.map((e) => {
      if (e.kind === "plan") return `[${e.ref}] CURATED EVENT PLAN (hand-built by the FGF team from the evidence base):\n${e.text}`;
      const bits = [TIER_LABEL[e.tier] || "Tier ?", e.category];
      if (e.season) bits.push(e.season);
      if (e.state && e.state !== "current") bits.push(e.state === "candidate" ? "not yet verified" : e.state);
      return `[${e.ref}] (${bits.join("; ")}) ${e.text}` + (e.notes && e.tier >= 3 ? `\n    note: ${e.notes}` : "");
    }).join("\n");
  }

  // ---------------------------------------------------------------- prompt
  const RULES = `You are FGF Intelligence, an expert companion for players of the mobile strategy game Foundation: Galactic Frontier (FGF). You talk like an experienced, friendly guildmate and give answers a player can act on right away.

How to answer:
- Use ONLY the evidence supplied with each question (and the player's own details). Do not use outside memory for game facts.
- Work out what the player actually needs, including their constraints (F2P/no spending, Champions they own or lack, Energy Core level, season, event).
- Combine facts to answer questions no single fact answers, and say when a step is your inference rather than a stated fact.
- Authority: Tier 1 (in-game/official) > Tier 2 (wiki/tested) > Tier 3 (community report). If sources disagree, follow the higher tier and mention the disagreement. Present Tier 3 facts as "players report…" / "community guides suggest…".
- Curated event plans were hand-built by the FGF team; treat them as the strongest guidance for that event and keep their specific advice.
- Never invent numbers, costs, timers, rewards, schedules or requirements. Every number you write must appear in the evidence or the player's message. If an exact value is missing, say it isn't confirmed and where to check in-game.
- Respect constraints strictly: for F2P players don't build the plan on paid packs; never build a lineup from Champions the player says they lack; when they list the Champions they own, use only those (a future target may be suggested, labelled as such).
- Cite evidence inline with its ref right after the sentence it supports, like [E2] or [E1][E4]. Only cite refs that were supplied.
- Today's date is {TODAY}. Events or maintenance dated before today are in the past; say so if the player asks about "the next" one and only past dates are known.

Style:
- Lead with the direct answer in 1–2 sentences, then the useful detail as short bullets or numbered steps. A small table is fine when comparing options. Usually under 200 words unless the player asks for a full guide.
- Write for a player: no talk of "evidence packets", "claims" or "databases". Say "the game's official notice", "community guides", etc.
- If the answer depends on something unknown (Core level, roster, server), give the best general answer, then ask one short follow-up question.
- If the evidence really doesn't cover the question, say so in one sentence, share any related facts that help, and suggest where to check in-game.
- Reply in the same language the player writes in.`;

  function profileText(p) {
    if (!p) return "";
    const out = [];
    if (p.season) out.push("Season: " + p.season);
    if (p.core) out.push("Energy Core level: " + p.core);
    if (p.spending) out.push("Spending: " + p.spending);
    if (p.champions && p.champions.length) out.push("Champions owned: " + p.champions.join(", "));
    if (p.server) out.push("Server: " + p.server);
    return out.length ? "The player's account (their own statement, not verified):\n- " + out.join("\n- ") : "";
  }

  function buildTurns({ question, history, registry, profile, today }) {
    const rules = RULES.replace("{TODAY}", today);
    const prof = profileText(profile);
    const turns = [{ role: "user", content: rules + (prof ? "\n\n" + prof : "") }];
    for (const h of history || []) turns.push({ role: h.role, content: h.content });
    const ev = registry.items.length ? formatEvidence(registry) : "(No matching facts were found in the knowledge base.)";
    turns.push({ role: "user", content: `Evidence for this question:\n${ev}\n\nPlayer's question: ${question}` });
    return turns;
  }

  // ------------------------------------------------------------ fact-check
  const CITE_RE = /\[(E\d+(?:\s*[,;]\s*E?\d+)*)\]/g;
  function citedRefs(text) {
    const out = [];
    for (const m of String(text || "").matchAll(CITE_RE)) {
      for (let part of m[1].split(/\s*[,;]\s*/)) {
        part = part.trim().toUpperCase(); if (!part.startsWith("E")) part = "E" + part;
        if (!out.includes(part)) out.push(part);
      }
    }
    return out;
  }
  const NUM_RE = /(?<![A-Za-z0-9])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)(\s*%)?/g;
  const normNum = (s) => { s = s.replace(/,/g, ""); if (s.includes(".")) s = s.replace(/0+$/, "").replace(/\.$/, ""); return s; };
  function numbersIn(text) { const s = new Set(); for (const m of String(text || "").matchAll(NUM_RE)) s.add(normNum(m[1])); return s; }
  function factualNumbers(answer) {
    let body = String(answer || "").replace(CITE_RE, " ");
    body = body.replace(/^\s*(?:[-*]\s*)?\d+[.)]\s+/gm, " ").replace(/\b(?:step|option|tip|phase|priority|day|#)\s*\d+\b/gi, " ");
    body = body.replace(/^\s*\|?[-: |]+\|?\s*$/gm, " ");
    const out = [];
    for (const m of body.matchAll(NUM_RE)) {
      const raw = m[1], n = normNum(raw), v = parseFloat(n);
      if (isNaN(v)) continue;
      if ((m[2] || raw.includes(",") || raw.includes(".") || v >= 10) && !out.includes(n)) out.push(n);
    }
    return out;
  }
  function factCheck(answer, registry, allowedExtra) {
    const known = new Set(registry.items.map((x) => x.ref));
    const refs = citedRefs(answer);
    const unknownRefs = refs.filter((r) => !known.has(r));
    const allowed = new Set([...numbersIn(registry.text()), ...numbersIn(allowedExtra || "")]);
    const unsupported = factualNumbers(answer).filter((n) => !allowed.has(n));
    const facty = String(answer || "").length > 280;
    const uncited = facty && registry.items.length > 0 && refs.length === 0;
    return { passed: !unknownRefs.length && !unsupported.length && !uncited, refs, unknownRefs, unsupported, uncited };
  }

  // --------------------------------------------------------- safe markdown
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  function inline(s, citeClass) {
    return s
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/(^|[\s(])\*([^*\s][^*]*?)\*(?=[\s.,;:!?)]|$)/g, "$1<em>$2</em>")
      .replace(/(^|[\s(])_([^_\s][^_]*?)_(?=[\s.,;:!?)]|$)/g, "$1<em>$2</em>")
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\[(E\d+)\]/g, `<button type="button" class="${citeClass}" data-ref="$1" aria-label="Source $1">$1</button>`);
  }
  function renderMarkdown(text, citeClass) {
    citeClass = citeClass || "cite";
    const lines = esc(text).split("\n");
    let html = "", list = null, i = 0;
    const close = () => { if (list) { html += `</${list}>`; list = null; } };
    while (i < lines.length) {
      const l = lines[i].trim();
      if (/^\|.*\|$/.test(l) && i + 1 < lines.length && /^\|?\s*:?-{2,}/.test(lines[i + 1].trim())) {
        close();
        const cells = (row) => row.trim().replace(/^\||\|$/g, "").split("|").map((c) => inline(c.trim(), citeClass));
        const head = cells(l); i += 2;
        let body = "";
        while (i < lines.length && /^\|.*\|$/.test(lines[i].trim())) { body += "<tr>" + cells(lines[i]).map((c) => `<td>${c}</td>`).join("") + "</tr>"; i++; }
        html += `<div class="table-scroll"><table><thead><tr>${head.map((c) => `<th scope="col">${c}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table></div>`;
        continue;
      }
      let m;
      if (!l) close();
      else if ((m = l.match(/^[-*•]\s+(.*)/))) { if (list !== "ul") { close(); html += "<ul>"; list = "ul"; } html += `<li>${inline(m[1], citeClass)}</li>`; }
      else if ((m = l.match(/^\d+[.)]\s+(.*)/))) { if (list !== "ol") { close(); html += "<ol>"; list = "ol"; } html += `<li>${inline(m[1], citeClass)}</li>`; }
      else if ((m = l.match(/^#{1,4}\s+(.*)/))) { close(); html += `<h4>${inline(m[1], citeClass)}</h4>`; }
      else { close(); html += `<p>${inline(l, citeClass)}</p>`; }
      i++;
    }
    close();
    return html;
  }

  // Latest official updates: Tier 1–2 facts with a date in their season field or text.
  const MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october", "november", "december"];
  function factDate(f) {
    let m = String(f.v || "").match(/(20\d\d)-(\d\d)-(\d\d)/);
    if (m) return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3]));
    m = String(f.c || "").match(/(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),\s*(20\d\d)/);
    if (m) return new Date(Date.UTC(+m[3], MONTHS.indexOf(m[1].toLowerCase()), +m[2]));
    return null;
  }
  function latestOfficial(facts, n) {
    return facts.filter((f) => f.t <= 2).map((f) => ({ f, d: factDate(f) })).filter((x) => x.d)
      .sort((a, b) => b.d - a.d).slice(0, n || 6);
  }

  const api = { tokenize, stem, glossaryExpand, noiseScore, buildIndex, matchPlans, planText, makeRegistry, factEntry, planEntry,
    formatEvidence, buildTurns, profileText, citedRefs, factualNumbers, factCheck, renderMarkdown, esc, latestOfficial, factDate, TIER_LABEL, RULES };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.FGF = api;
})(typeof globalThis !== "undefined" ? globalThis : this);
