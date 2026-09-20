import json, os, re
from datetime import datetime, timezone
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import agent

SUPABASE_URL=os.getenv("FGF_SUPABASE_URL","https://qdoixzfkkmvzjfkhzups.supabase.co").rstrip("/")
SUPABASE_SECRET=os.getenv("FGF_SUPABASE_SECRET_KEY") or os.getenv("FGF_SUPABASE_SERVICE_ROLE_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY")

def headers():
    if not SUPABASE_SECRET: return None
    return {"apikey":SUPABASE_SECRET,"Authorization":"Bearer "+SUPABASE_SECRET,"Content-Type":"application/json","Accept":"application/json"}

def sb(method,path,payload=None):
    h=headers()
    if not h: return None
    data=None if payload is None else json.dumps(payload).encode()
    try:
        r= urlopen(Request(SUPABASE_URL+path,data=data,headers={**h,"Prefer":"return=representation"},method=method),timeout=5)
        return json.loads(r.read().decode() or "[]")
    except Exception:
        return None

def now(): return datetime.now(timezone.utc).isoformat()

def json_body(handler):
    n=min(int(handler.headers.get("Content-Length","0")),131072)
    return json.loads(handler.rfile.read(n).decode() or "{}")

def reply(handler,obj,status=200):
    b=json.dumps(obj,ensure_ascii=False).encode()
    handler.send_response(status); handler.send_header("Content-Type","application/json; charset=utf-8"); handler.send_header("Cache-Control","no-store"); handler.send_header("Content-Length",str(len(b))); handler.end_headers(); handler.wfile.write(b)

def claim_texts():
    return [str(c.get("Claim","")) for c in agent.CLAIMS if c.get("Status") not in ("Rejected","Superseded")]

def evidence_for(q,limit=12):
    try: return agent.retrieve(q,limit)
    except Exception: return []

def player_get(pid):
    rows=sb("GET",f"/rest/v1/player_profiles?player_id=eq.{pid}&select=*")
    return rows[0] if rows else None

def player_save(pid,p):
    payload={
      "player_id":pid,"season":str(p.get("season","S1")).upper(),
      "core_level":int(p.get("core_level",1)),
      "flagship_level":int(p.get("flagship_level",1)),
      "champion_levels":p.get("champion_levels",{}),
      "fleet_styles":p.get("fleet_styles",[]),
      "resources":p.get("resources",{}),
      "preferences":p.get("preferences",{}),
      "updated_at":now()
    }
    rows=sb("POST","/rest/v1/player_profiles?on_conflict=player_id",payload)
    return payload, rows is not None

def known_milestones(start,target,season):
    out=[]
    qs=agent.retrieve(f"Energy Core {target} upgrade unlock requirements",40)
    for c in qs:
        t=c.get("Claim","")
        if "core" in t.lower() or "energy core" in t.lower(): out.append({"claim":t,"tier":c.get("Evidence Tier"),"confidence":c.get("Confidence")})
    if season.upper()=="S2" and target>=33:
        out.append({"claim":"Official evidence states Energy Core L33 unlocks a fourth Battle Queue.","tier":"Tier 2","confidence":"High"})
    if season.upper() in ("S2","S3") and target>=35:
        out.append({"claim":"Official evidence states the Epoch of Fusion Seed technology path raises the Energy Core cap to L35.","tier":"Tier 2","confidence":"High"})
    return out[:20]

def progression(start,target,season):
    start,target=max(1,int(start)),max(1,int(target))
    if target<start: return {"ok":False,"error":"Target Core must be >= current Core."}
    milestones=known_milestones(start,target,season)
    exact_cost_claims=[x for x in evidence_for(f"Energy Core {target} exact cost Fusion Seeds",30)
                       if re.search(r"\b\d[\d,]*\b",x.get("Claim","")) and "fusion seed" in x.get("Claim","").lower()]
    return {
      "ok":True,"current_core":start,"target_core":target,"season":season.upper(),
      "levels":target-start,"known_milestones":milestones,
      "exact_cost_status":"established" if exact_cost_claims else "unknown",
      "cost_note":"Exact cumulative/resource cost is not calculated unless the evidence layer contains level-by-level verified costs.",
      "evidence":[{"claim":x.get("Claim"),"tier":x.get("Evidence Tier"),"source":x.get("Source")} for x in exact_cost_claims[:10]]
    }

def repair(damage,modules,in_combat):
    damage=damage.lower()
    if damage=="minor":
        return {"ok":True,"path":"Leave combat; Minor Damage can recover automatically without Repair Modules.","modules_required":0,"evidence_basis":["Tier-1 evidence: Minor Damage can immediately recover after leaving battle without Repair Modules.","Tier-1 evidence: Minor Damage auto-repairs once out of combat."]}
    if modules<=0:
        return {"ok":True,"path":"Major Damage requires Repair Modules; without modules, the fleet cannot complete major-damage repair.","modules_required":"at least 1 per applicable repair action","evidence_basis":["Tier-1 evidence: Major Damage requires Repair Modules.","Tier-1 evidence: Repair Cabin/Repair Bay is the repair path for Major Damage."]}
    return {"ok":True,"path":"Use Repair Modules through the repair facility/formation repair path for Major Damage.","modules_required":modules,"evidence_basis":["Tier-1 evidence: Major Damage requires Repair Modules."]}

def synergy(style,champions):
    style=style.title(); names=[x.strip() for x in champions if x.strip()]
    matched=[]
    for n in names:
        hits=evidence_for(f"{n} {style} flagship champion compatibility",15)
        if any(style.lower() in x.get("Claim","").lower() and n.lower() in x.get("Claim","").lower() for x in hits): matched.append(n)
    bonus={2:10,3:20}.get(len(matched),0)
    return {"ok":True,"style":style,"champions":names,"matched_champions":len(matched),"synergy_bonus_percent":bonus,"matched":matched,
            "note":"The +10%/+20% synergy rule is applied only to matching Champions supported by the evidence layer; this is a mechanic calculation, not a meta ranking."}

def priority(pid):
    p=player_get(pid) or {"season":"S1","core_level":1,"flagship_level":1,"champion_levels":{},"resources":{},"preferences":{}}
    core=int(p.get("core_level") or 1)
    answers=[]
    if core<33 and p.get("season","S1").upper() in ("S2","S3"):
        answers.append({"priority":"Energy Core progression","reason":"Current evidence establishes Core L33 as the fourth Battle Queue milestone.","evidence":"Official FGF Epoch of Fusion Seed article."})
    answers.append({"priority":"Keep research/construction active","reason":"Established progression principle; avoid idle timers.","evidence":"Current evidence corpus."})
    answers.append({"priority":"Use evidence-supported fleet synergy","reason":"2 matching Champions = +10%; 3 matching Champions = +20% when the matching Style condition is met.","evidence":"Tier-1 combat evidence."})
    return {"ok":True,"player":p,"priorities":answers}

ORIG_GET=agent.H.do_GET
ORIG_POST=agent.H.do_POST

def new_get(self):
    u=urlparse(self.path); qs=parse_qs(u.query)
    if u.path=="/api/v5/player":
        pid=qs.get("player_id",["default"])[0]; p=player_get(pid)
        return reply(self,{"ok":True,"player_id":pid,"profile":p or {"player_id":pid,"season":"S1","core_level":1,"flagship_level":1,"champion_levels":{},"fleet_styles":[],"resources":{},"preferences":{}}})
    if u.path=="/api/v5/progression":
        return reply(self,progression(qs.get("core_level",["1"])[0],qs.get("target_level",["30"])[0],qs.get("season",["S1"])[0]))
    if u.path=="/api/v5/repair":
        return reply(self,repair(qs.get("damage",["minor"])[0],int(qs.get("repair_modules",["0"])[0]),qs.get("in_combat",["false"])[0].lower()=="true"))
    if u.path=="/api/v5/synergy":
        return reply(self,synergy(qs.get("style",["Kinetic"])[0],qs.get("champion",[])))
    if u.path=="/api/v5/priority":
        return reply(self,priority(qs.get("player_id",["default"])[0]))
    if u.path=="/api/v5/evidence":
        q=qs.get("q",[""])[0]
        return reply(self,{"ok":True,"query":q,"results":[{"claim":c.get("Claim"),"tier":c.get("Evidence Tier"),"confidence":c.get("Confidence"),"status":c.get("Status"),"source":c.get("Source"),"notes":c.get("Notes")} for c in evidence_for(q,20)]})
    if u.path=="/v5":
        try:
            b=(agent.ROOT/"web"/"v5.html").read_bytes()
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(b))); self.end_headers(); self.wfile.write(b); return
        except Exception: pass
    return ORIG_GET(self)

def new_post(self):
    u=urlparse(self.path)
    if u.path=="/api/v5/player":
        try:
            body=json_body(self); pid=str(body.get("player_id","default")).strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}",pid): return reply(self,{"ok":False,"error":"Invalid player_id"},400)
            payload,durable=player_save(pid,body)
            return reply(self,{"ok":True,"durable":durable,"profile":payload})
        except Exception as e: return reply(self,{"ok":False,"error":str(e)},400)
    return ORIG_POST(self)

agent.H.do_GET=new_get
agent.H.do_POST=new_post

if __name__=="__main__":
    port=int(os.getenv("PORT","8000"))
    print("FGF V5 intelligence extension running",port)
    ThreadingHTTPServer(("0.0.0.0",port),agent.H).serve_forever()
