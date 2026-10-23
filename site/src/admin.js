/* FGF review page: the owner approves what the pipelines and players added. Talks only to the AI proxy's /admin API. */
(function () {
  "use strict";
  const $ = (s, r) => (r || document).querySelector(s);
  const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));
  const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (m) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[m]));
  let CONFIG = {};
  try { CONFIG = JSON.parse($("#fgf-config").textContent || "{}"); } catch (e) { CONFIG = {}; }
  const API = String(CONFIG.aiEndpoint || "").replace(/\/+$/, "");
  const CATEGORIES = ["Events", "Champions", "Progression", "Combat", "Economy", "Flagships", "Buildings", "PvP", "Guild", "Resources", "Research", "Interface", "Technical", "General"];
  const HELP = {
    review: "New facts from the harvester, screenshots, videos and player links. Approve the right ones, reject the wrong ones. Tier 1 needs your proof.",
    conflicts: "A new fact disagrees with an official one. Keep the current fact, or accept the new one (the old one is retired).",
    corrections: "Players' corrections without a link. Add the right fact if you can confirm it, or mark them done.",
    gaps: "Questions players ask that the app couldn't answer, most asked first. Answer one with a fact, or dismiss it.",
    add: "Add a fact you've confirmed yourself. It goes live after the next sync.",
  };

  // ------------------------------------------------------------ sign-in token
  const KEY = "fgf.review.token";
  const tok = {
    get() { try { return sessionStorage.getItem(KEY) || localStorage.getItem(KEY) || ""; } catch (e) { return mem; } },
    set(t, remember) { mem = t; try { (remember ? localStorage : sessionStorage).setItem(KEY, t); } catch (e) { /* private mode: memory only */ } },
    clear() { mem = ""; try { sessionStorage.removeItem(KEY); localStorage.removeItem(KEY); } catch (e) {} },
  };
  let mem = "";
  const expired = (t) => { const s = Number(String(t).split(".")[0]); return !s || s * 1000 < Date.now(); };

  const state = { type: "review", offset: 0, q: "", tier: "", total: 0, items: [], selected: new Set(), publish: false, prefill: null };

  async function api(path, body) {
    const t = tok.get();
    let r;
    try {
      r = await fetch(API + "/admin/" + path, { method: body === undefined ? "GET" : "POST",
        headers: { "Content-Type": "application/json", ...(t && path !== "login" ? { Authorization: "Bearer " + t } : {}) },
        body: body === undefined ? undefined : JSON.stringify(body) });
    } catch (e) { throw new Error("Can't reach the review service. Check your connection."); }
    let j = {}; try { j = await r.json(); } catch (e) {}
    if (r.status === 401 && path !== "login") { signOut("Your sign-in expired. Please sign in again."); throw new Error("signed out"); }
    if (r.status === 503 && path === "login") { showSetup(j.error); throw new Error("setup"); }
    if (!r.ok) throw new Error(j.error || "Something went wrong (" + r.status + ").");
    return j;
  }

  let toastTimer;
  function toast(msg, err) {
    const el = $("#toast"); el.textContent = msg; el.className = "toast" + (err ? " err" : ""); el.hidden = false;
    clearTimeout(toastTimer); toastTimer = setTimeout(() => { el.hidden = true; }, err ? 6000 : 3500);
  }

  // ------------------------------------------------------------------- views
  function show(view) {
    $("#login-view").hidden = view !== "login";
    $("#setup-view").hidden = view !== "setup";
    $("#panel-view").hidden = view !== "panel";
    $("#signout").hidden = view !== "panel";
    $("#publish").hidden = !(view === "panel" && state.publish);
  }
  function showSetup(msg) {
    $("#setup-text").textContent = msg || "The review page needs the FGF AI proxy and its review settings (see SITE_SETUP.md → Review page).";
    show("setup");
  }
  function signOut(msg) {
    tok.clear(); show("login");
    const e = $("#login-error"); e.textContent = msg || ""; e.hidden = !msg;
    $("#password").focus();
  }

  // ------------------------------------------------------------------ queues
  async function refreshCounts() {
    try {
      const s = await api("summary");
      state.publish = !!s.publish;
      for (const k of ["review", "conflicts", "corrections", "gaps"]) {
        const c = $(`[data-count="${k}"]`); if (c) c.textContent = s[k] == null ? "?" : String(s[k]);
      }
      $("#publish").hidden = !state.publish;
      $("#publish-note").textContent = state.publish
        ? "Approved changes reach players after the next sync (within 6 hours), or right away with Publish now."
        : "Approved changes reach players after the next automatic sync (within 6 hours).";
    } catch (e) { if (e.message !== "signed out") toast(e.message, true); }
  }

  function selectTab(type) {
    state.type = type; state.offset = 0; state.selected.clear();
    for (const b of $$(".adm-tab")) b.setAttribute("aria-selected", String(b.dataset.type === type));
    $("#queue-help").textContent = HELP[type] || "";
    $("#list-view").hidden = type === "add";
    $("#add-view").hidden = type !== "add";
    $("#filters").hidden = !(type === "review" || type === "conflicts");
    $("#bulk").hidden = type !== "review";
    if (type === "add") { fillAddForm(); $("#f-claim").focus(); return; }
    load();
  }

  async function load() {
    const list = $("#items");
    list.innerHTML = `<li class="empty">Loading…</li>`;
    const p = new URLSearchParams({ type: state.type, offset: String(state.offset) });
    if (state.q) p.set("q", state.q);
    if (state.tier) p.set("tier", state.tier);
    try {
      const r = await api("queue?" + p.toString());
      state.items = r.items || []; state.total = r.total || 0; state.selected.clear();
      render();
    } catch (e) {
      if (e.message !== "signed out") list.innerHTML = `<li class="empty">${esc(e.message)} <button class="btn ghost" type="button" id="retry">Try again</button></li>`;
      const rb = $("#retry"); if (rb) rb.addEventListener("click", load);
    }
  }

  const tierChip = (t) => { const m = /tier\s*([1-5])/i.exec(t || ""); const n = m ? m[1] : "?"; return `<span class="chip t${n}">${esc(t || "No tier")}</span>`; };
  const link = (u, label) => /^https?:\/\//.test(u || "") ? `<a href="${esc(u)}" target="_blank" rel="noopener noreferrer">${esc(label || "source")}</a>` : (u ? `<span>${esc(u)}</span>` : "");
  const MODES = { video: "watched video", image: "screenshot", quote: "page quote" };

  function claimMeta(x) {
    return `<div class="meta">${tierChip(x.tier)}<span class="chip">${esc(x.category || "General")}</span>` +
      (x.mode ? `<span class="chip">${esc(MODES[x.mode] || x.mode)}${x.timestamp ? " @ " + esc(x.timestamp) : ""}</span>` : "") +
      (x.by_player ? `<span class="chip plan">from a player's link</span>` : "") +
      (x.source_name ? `<span>${esc(x.source_name)}</span>` : "") + (x.created ? `<span>added ${esc(x.created)}</span>` : "") +
      link(x.source, "open source") + `</div>`;
  }

  function render() {
    const list = $("#items");
    if (!state.items.length) {
      list.innerHTML = `<li class="empty">${state.q || state.tier ? "Nothing matches these filters." : "All done here. Nothing waiting."}</li>`;
    } else {
      list.innerHTML = state.items.map((x, i) => {
        if (state.type === "review") return `<li class="item" data-i="${i}">
            <div class="item-top"><input type="checkbox" class="pick" aria-label="Select this fact"><p class="text">${esc(x.claim)}</p></div>
            ${claimMeta(x)}
            ${x.quote ? `<p class="quote">“${esc(x.quote)}”</p>` : ""}
            <div class="acts"><button class="btn ok" data-act="approve" type="button">Approve</button>
              <button class="btn" data-act="tier1" type="button">Approve as Tier 1…</button>
              <button class="btn bad" data-act="reject" type="button">Reject</button></div></li>`;
        if (state.type === "conflicts") return `<li class="item" data-i="${i}">
            <div class="versus"><p class="new"><b>New fact</b>${esc(x.claim)}</p><p class="old"><b>Current fact</b>${esc(x.conflicts_with || "(not recorded)")}</p></div>
            ${claimMeta(x)}
            ${x.quote ? `<p class="quote">“${esc(x.quote)}”</p>` : ""}
            <div class="acts"><button class="btn ok" data-act="keep_existing" type="button">Keep current fact</button>
              <button class="btn" data-act="accept_new" type="button">Accept new, retire old</button></div></li>`;
        if (state.type === "corrections") return `<li class="item" data-i="${i}">
            <p class="text"><b>“${esc(x.correction)}”</b></p>
            <div class="meta"><span>about the question “${esc(x.question)}”</span><span>${esc(x.created || "")}</span></div>
            ${(x.cited_facts || []).length ? `<p class="quote">The answer used: ${(x.cited_facts || []).map(esc).join(" · ")}</p>` : ""}
            <div class="acts"><button class="btn ok" data-act="as_fact" type="button">Add as a fact…</button>
              <button class="btn" data-act="done" type="button">Done</button>
              <button class="btn bad" data-act="dismiss" type="button">Dismiss</button></div></li>`;
        return `<li class="item" data-i="${i}">
            <p class="text">“${esc(x.example)}”</p>
            <div class="meta"><span class="chip warn">asked ${esc(x.count)}×</span>${x.not_helpful ? `<span>${esc(x.not_helpful)} unhelpful answers</span>` : ""}<span>last asked ${esc(x.last_seen || "")}</span></div>
            <div class="acts"><button class="btn ok" data-act="answer" type="button">Answer with a fact…</button>
              <button class="btn bad" data-act="dismiss" type="button">Dismiss</button></div></li>`;
      }).join("");
    }
    const from = state.total ? state.offset + 1 : 0, to = state.offset + state.items.length;
    $("#pager").innerHTML = state.total > 40 || state.offset
      ? `<button class="btn ghost" type="button" id="prev" ${state.offset ? "" : "disabled"}>Previous</button><span>${from}–${to} of ${state.total}</span>
         <button class="btn ghost" type="button" id="next" ${to < state.total ? "" : "disabled"}>Next</button>`
      : (state.total ? `<span>${state.total} waiting</span>` : "");
    const prev = $("#prev"), next = $("#next");
    if (prev) prev.addEventListener("click", () => { state.offset = Math.max(0, state.offset - 40); load(); });
    if (next) next.addEventListener("click", () => { state.offset += 40; load(); });
    $("#select-all").checked = false;
    updateBulk();
  }

  function updateBulk() {
    const n = state.selected.size;
    $("#bulk-approve").disabled = !n; $("#bulk-reject").disabled = !n;
    $("#bulk-approve").textContent = n ? `Approve selected (${n})` : "Approve selected";
    $("#bulk-reject").textContent = n ? `Reject selected (${n})` : "Reject selected";
  }

  function removeItems(indexes) {
    const ids = new Set(indexes.map((i) => state.items[i]));
    state.items = state.items.filter((x) => !ids.has(x));
    state.total = Math.max(0, state.total - indexes.length);
    state.selected.clear();
    render(); refreshCounts();
    if (!state.items.length && state.total) load();     // page emptied: fetch the next batch
  }

  const idOf = (x) => (state.type === "gaps" ? x.gap_key : x.id);

  async function decide(indexes, action, note) {
    const items = indexes.map((i) => state.items[i]);
    const lis = indexes.map((i) => $(`.item[data-i="${i}"]`)).filter(Boolean);
    lis.forEach((li) => li.classList.add("leaving"));
    try {
      await api("decide", { type: state.type, ids: items.map(idOf), action, note: note || "" });
      const words = { approve: "Approved", reject: "Rejected", promote_tier1: "Approved as Tier 1", keep_existing: "Kept the current fact",
        accept_new: "New fact accepted, old one retired", done: "Marked done", dismiss: "Dismissed" };
      toast(`${words[action] || "Saved"}${items.length > 1 ? ` (${items.length})` : ""}.`);
      removeItems(indexes);
    } catch (e) {
      lis.forEach((li) => li.classList.remove("leaving"));
      if (e.message !== "signed out") toast(e.message, true);
    }
  }

  function proofForm(li, i) {
    if ($(".proof", li)) { $(".proof textarea", li).focus(); return; }
    $(".acts", li).insertAdjacentHTML("beforebegin", `<div class="proof form"><label>Proof for Tier 1
      <textarea maxlength="500" style="min-height:56px" placeholder="e.g. Seen on the in-game shop screen, 24 Oct (screenshot in inbox/processed)"></textarea></label>
      <div class="acts"><button class="btn primary" type="button" data-act="confirm_tier1">Confirm Tier 1</button><button class="btn ghost" type="button" data-act="cancel_tier1">Cancel</button></div></div>`);
    $(".proof textarea", li).focus();
  }

  $("#items").addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-act]"); if (!btn) return;
    const li = btn.closest(".item"); const i = Number(li.dataset.i); const x = state.items[i]; const act = btn.dataset.act;
    if (act === "tier1") return proofForm(li, i);
    if (act === "cancel_tier1") return $(".proof", li).remove();
    if (act === "confirm_tier1") {
      const note = $(".proof textarea", li).value.trim();
      if (note.length < 8) { toast("Describe the proof (8+ characters).", true); $(".proof textarea", li).focus(); return; }
      return decide([i], "promote_tier1", note);
    }
    if (act === "as_fact") { state.prefill = { feedback_id: x.id, context: `Correction from a player about “${x.question}”: “${x.correction}”`, claim: "" }; return selectTab("add"); }
    if (act === "answer") { state.prefill = { gap_key: x.gap_key, context: `Answering a question asked ${x.count}×: “${x.example}”`, claim: "" }; return selectTab("add"); }
    decide([i], act);
  });
  $("#items").addEventListener("change", (ev) => {
    if (!ev.target.classList.contains("pick")) return;
    const i = Number(ev.target.closest(".item").dataset.i);
    if (ev.target.checked) state.selected.add(i); else state.selected.delete(i);
    updateBulk();
  });
  $("#select-all").addEventListener("change", (ev) => {
    state.selected.clear();
    for (const box of $$(".pick")) { box.checked = ev.target.checked; if (box.checked) state.selected.add(Number(box.closest(".item").dataset.i)); }
    updateBulk();
  });
  $("#bulk-approve").addEventListener("click", () => decide([...state.selected].sort((a, b) => a - b), "approve"));
  $("#bulk-reject").addEventListener("click", () => decide([...state.selected].sort((a, b) => a - b), "reject"));

  let qTimer;
  $("#q").addEventListener("input", (ev) => { clearTimeout(qTimer); qTimer = setTimeout(() => { state.q = ev.target.value.trim(); state.offset = 0; load(); }, 350); });
  $("#tier").addEventListener("change", (ev) => { state.tier = ev.target.value; state.offset = 0; load(); });
  for (const b of $$(".adm-tab")) b.addEventListener("click", () => { state.prefill = null; selectTab(b.dataset.type); });

  // ---------------------------------------------------------------- add fact
  $("#f-category").innerHTML = CATEGORIES.map((c) => `<option>${esc(c)}</option>`).join("");
  function fillAddForm() {
    const p = state.prefill;
    $("#add-context").hidden = !p; $("#add-context").textContent = p ? p.context : "";
  }
  $("#f-reset").addEventListener("click", () => { state.prefill = null; fillAddForm(); });
  $("#add-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const btn = $("#add-form button[type=submit]"); btn.disabled = true; btn.textContent = "Saving…";
    const body = { claim: $("#f-claim").value.trim(), category: $("#f-category").value, tier: Number(($("input[name=f-tier]:checked") || {}).value || 2),
      source_url: $("#f-source").value.trim(), note: $("#f-note").value.trim(), ...(state.prefill && state.prefill.gap_key ? { gap_key: state.prefill.gap_key } : {}),
      ...(state.prefill && state.prefill.feedback_id ? { feedback_id: state.prefill.feedback_id } : {}) };
    try {
      await api("fact", body);
      toast(state.prefill ? "Fact saved and the question marked answered." : "Fact saved.");
      $("#add-form").reset(); state.prefill = null; fillAddForm(); refreshCounts();
    } catch (e) { if (e.message !== "signed out") toast(e.message, true); }
    finally { btn.disabled = false; btn.textContent = "Save fact"; }
  });

  // ------------------------------------------------------------- publish/out
  $("#publish").addEventListener("click", async () => {
    const b = $("#publish"); b.disabled = true; b.textContent = "Starting…";
    try { await api("publish", {}); toast("Sync started. The app updates in a few minutes."); }
    catch (e) { if (e.message !== "signed out") toast(e.message, true); }
    finally { b.disabled = false; b.textContent = "Publish now"; }
  });
  $("#signout").addEventListener("click", () => signOut());

  $("#login-form").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const err = $("#login-error"); err.hidden = true;
    const btn = $("#login-form button[type=submit]"); btn.disabled = true;
    try {
      const r = await api("login", { password: $("#password").value });
      tok.set(r.token, $("#remember").checked); $("#password").value = "";
      state.publish = !!r.publish;
      start();
    } catch (e) {
      if (e.message !== "setup") { err.textContent = e.message; err.hidden = false; }
    } finally { btn.disabled = false; }
  });

  function start() { show("panel"); refreshCounts(); selectTab(state.type); }

  if (!API) showSetup("This copy of the app has no AI proxy, so the review page can't work here. Use the published GitHub Pages app.");
  else if (tok.get() && !expired(tok.get())) start();
  else { tok.clear(); show("login"); }
})();
