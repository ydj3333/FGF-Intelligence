// In-memory stand-in for the parts of Supabase's REST API (PostgREST) and GitHub the proxy uses.
// Filters: eq. neq. in.(...) ilike.*x*  ·  order=a.desc,b.asc  ·  limit/offset  ·  Prefer: count=exact
// Writes: POST (with ?on_conflict=col + resolution=ignore-duplicates), PATCH with filters.
import http from "node:http";

export function createMockSupabase(seed = {}) {
  const tables = { claims: [], app_feedback: [], knowledge_gaps: [], admin_audit: [], ...structuredClone(seed) };
  const dispatches = [], keysSeen = [];
  let nextId = 1000;

  const parseIn = (v) => [...v.slice(4, -1).matchAll(/"([^"]*)"|([^,]+)/g)].map((m) => m[1] ?? m[2]);
  function matches(row, params) {
    for (const [k, v] of params) {
      if (["select", "order", "limit", "offset", "on_conflict"].includes(k)) continue;
      const val = row[k] == null ? "" : String(row[k]);
      if (v.startsWith("eq.") && val !== v.slice(3)) return false;
      if (v.startsWith("neq.") && val === v.slice(4)) return false;
      if (v.startsWith("in.(") && !parseIn(v).includes(val)) return false;
      if (v.startsWith("ilike.")) {
        const pat = v.slice(6).toLowerCase().split("*").map((x) => x.replace(/[.+?^${}()|[\]\\]/g, "\\$&")).join(".*");
        if (!new RegExp("^" + pat + "$", "s").test(val.toLowerCase())) return false;
      }
    }
    return true;
  }
  function sortRows(rows, order) {
    if (!order) return rows;
    const keys = order.split(",").map((o) => o.split("."));
    return rows.slice().sort((a, b) => {
      for (const [k, dir] of keys) {
        const x = a[k], y = b[k];
        if (x === y) continue;
        const c = (typeof x === "number" && typeof y === "number") ? x - y : String(x ?? "").localeCompare(String(y ?? ""));
        return dir === "desc" ? -c : c;
      }
      return 0;
    });
  }
  function pick(row, select) {
    if (!select || select === "*") return row;
    return Object.fromEntries(select.split(",").map((c) => [c, row[c] ?? null]));
  }

  const server = http.createServer((req, res) => {
    let b = ""; req.on("data", (c) => (b += c)); req.on("end", () => {
      const url = new URL(req.url, "http://x");
      if (url.pathname.startsWith("/repos/") && url.pathname.endsWith("/dispatches")) {
        dispatches.push({ path: url.pathname, auth: req.headers.authorization, body: JSON.parse(b || "{}") });
        res.writeHead(req.headers.authorization === "Bearer gh-ok" ? 204 : 401); return res.end();
      }
      const m = url.pathname.match(/^\/rest\/v1\/(\w+)$/);
      if (!m || !(m[1] in tables)) { res.writeHead(404, { "Content-Type": "application/json" }); return res.end('{"message":"relation does not exist"}'); }
      keysSeen.push({ table: m[1], method: req.method, key: req.headers.apikey });
      const table = tables[m[1]], params = [...url.searchParams.entries()];
      const prefer = String(req.headers.prefer || "");
      if (req.method === "GET") {
        const all = sortRows(table.filter((r) => matches(r, params)), url.searchParams.get("order"));
        const off = Number(url.searchParams.get("offset") || 0), lim = Number(url.searchParams.get("limit") || 1000);
        const page = all.slice(off, off + lim).map((r) => pick(r, url.searchParams.get("select")));
        const headers = { "Content-Type": "application/json" };
        if (prefer.includes("count=exact")) headers["Content-Range"] = `${off}-${off + page.length - 1}/${all.length}`;
        res.writeHead(200, headers); return res.end(JSON.stringify(page));
      }
      if (req.method === "POST") {
        const rows = [].concat(JSON.parse(b));
        const conflict = url.searchParams.get("on_conflict");
        for (const r of rows) {
          if (conflict && table.some((x) => x[conflict] === r[conflict])) continue;
          table.push({ id: nextId++, created_at: new Date().toISOString(), status: m[1] === "app_feedback" ? "new" : undefined, ...r });
        }
        res.writeHead(201); return res.end();
      }
      if (req.method === "PATCH") {
        const body = JSON.parse(b);
        for (const r of table) if (matches(r, params)) Object.assign(r, body);
        res.writeHead(204); return res.end();
      }
      res.writeHead(405); res.end();
    });
  });
  return { server, tables, dispatches, keysSeen };
}
