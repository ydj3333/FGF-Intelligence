const assert = require("assert");
const FGF = require("../src/engine.js");
const data = require(process.env.FGF_DATA || "../dist/fgf-data.json");
const idx = FGF.buildIndex(data.facts);
const top = (q, n = 3, o = {}) => idx.search(q, { limit: n, ...o }).map((h) => h.doc.c);
let pass = 0; const t = (name, fn) => { fn(); pass++; console.log("ok -", name); };

t("indexes every fact", () => assert.strictEqual(idx.size, data.facts.length));
t("migration permits", () => assert.match(top("how many permits to move server")[0], /10 Migration Permits/));
t("T100 shorthand finds Top 100", () => assert.ok(top("best way to do T100", 3).every((c) => /Top 100/i.test(c))));
t("maintenance finds Oct 15 notice in top 2", () => assert.ok(top("when is the next maintenance", 2).some((c) => /October 15, 2026/.test(c))));
t("repair", () => assert.match(top("how do i repair major damage")[0], /Major Damage/));
t("heroes→champions synonym", () => assert.ok(top("matching heroes bonus", 4).some((c) => /Matching Heroes|Style Resonance/.test(c))));
t("kaboom aoe", () => assert.match(top("best kaboom robots team aoe")[0], /Kaboom/));
t("official filter", () => assert.ok(idx.search("migration", { officialOnly: true, limit: 8 }).every((h) => h.doc.t <= 2)));
t("plan matching", () => {
  assert.deepStrictEqual(FGF.matchPlans(data.plans, "best way to do T100?").map((p) => p.id).sort(), ["t100", "t100-days"]);
  assert.deepStrictEqual(FGF.matchPlans(data.plans, "GvG tips").map((p) => p.id), ["gvg"]);
  assert.deepStrictEqual(FGF.matchPlans(data.plans, "how do I repair"), []);
});
t("creator-video facts rank below core facts and are labelled for the AI", () => {
  const facts = [
    { c: "Kaboom robots lineup: Zora, Lily and Jodie work well together.", g: "Events", t: 3, s: "candidate", y: 1, n: "From the video “Kaboom guide”", u: "https://www.youtube.com/watch?v=AAAAAAAAAAA" },
    { c: "Kaboom robots lineup: Zora and Lily are the recommended core.", g: "Events", t: 3, s: "candidate", n: "" },
    { c: "A disputed Kaboom robots timer claim.", g: "Events", t: 3, s: "conflicting", n: "" },
  ];
  const small = FGF.buildIndex(facts);
  const hits = small.search("kaboom robots lineup zora lily", { limit: 3 });
  assert.ok(!hits[0].doc.y, "a core fact outranks an equally relevant video fact");
  const reg = FGF.makeRegistry();
  for (const h of small.search("kaboom robots", { limit: 3 })) reg.add("f" + h.doc.i, FGF.factEntry(h.doc));
  const ev = FGF.formatEvidence(reg);
  assert.match(ev, /from a creator's YouTube video; not yet verified\) Kaboom robots lineup: Zora, Lily and Jodie/);
  assert.match(ev, /disputed\) A disputed Kaboom/);
  assert.ok(FGF.hasGap("Not covered.\n[[GAP]]") && !FGF.hasGap("All good [E1]"));
  assert.strictEqual(FGF.stripGap("Not covered.\n[[GAP]]\n"), "Not covered.");
  assert.match(FGF.RULES, /return exactly that many/); assert.match(FGF.RULES, /Never invent Champion/);
});
t("registry + prompt", () => {
  const reg = FGF.makeRegistry();
  for (const h of idx.search("migration permits", { limit: 3 })) reg.add("f" + h.doc.i, FGF.factEntry(h.doc));
  const p = FGF.matchPlans(data.plans, "gvg")[0]; reg.add("p" + p.id, FGF.planEntry(p));
  const turns = FGF.buildTurns({ question: "how do I migrate?", history: [{ role: "user", content: "hi" }, { role: "assistant", content: "Hello" }], registry: reg, profile: { core: 28, spending: "F2P", champions: ["Lily"] }, today: "Thursday 22 October 2026" });
  assert.strictEqual(turns[0].role, "user"); assert.strictEqual(turns.at(-1).role, "user");
  assert.match(turns[0].content, /22 October 2026/); assert.match(turns[0].content, /Energy Core level: 28/);
  assert.match(turns.at(-1).content, /\[E1\] \(Tier 1/); assert.match(turns.at(-1).content, /CURATED EVENT PLAN/);
  assert.ok(JSON.stringify(turns).length < 60000);
});
t("fact-check", () => {
  const reg = FGF.makeRegistry(); reg.add("a", { kind: "fact", text: "Server migration requires 10 Migration Permits.", tier: 1 });
  let r = FGF.factCheck("You need 10 permits [E1].\n1. Leave your guild", reg, "");
  assert.ok(r.passed, JSON.stringify(r));
  r = FGF.factCheck("You need 25 permits [E1][E7].", reg, "");
  assert.ok(!r.passed); assert.deepStrictEqual(r.unsupported, ["25"]); assert.deepStrictEqual(r.unknownRefs, ["E7"]);
  r = FGF.factCheck("At Core 28 push to 10 [E1].", reg, "I'm core 28"); assert.ok(r.passed);
  r = FGF.factCheck("| Day | Plan |\n|---|---|\n| Day 1 | 10 permits [E1] |", reg, ""); assert.ok(r.passed, JSON.stringify(r));
});
t("markdown is escaped and formatted", () => {
  const h = FGF.renderMarkdown("**Bold** <script>x</script> [E1]\n- a\n- b\n\n| A | B |\n|---|---|\n| 1 | 2 |");
  assert.ok(!h.includes("<script>")); assert.match(h, /<strong>Bold<\/strong>/); assert.match(h, /data-ref="E1"/);
  assert.match(h, /<ul><li>a<\/li><li>b<\/li><\/ul>/); assert.match(h, /<table>/);
});
t("latest official", () => { const l = FGF.latestOfficial(data.facts, 5); assert.ok(l.length >= 3); assert.match(l[0].d.toISOString(), /^2026-10-1[45]/); });
const t0 = Date.now(); for (let i = 0; i < 50; i++) idx.search("best F2P plan for core 28 fusion seeds", { limit: 12 }); 
t("search speed", () => assert.ok((Date.now() - t0) / 50 < 30, "ms/search=" + (Date.now() - t0) / 50));
console.log(`${pass} passed; avg search ${((Date.now() - t0) / 50).toFixed(1)} ms`);
