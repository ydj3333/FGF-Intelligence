import json,re,os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
ROOT=Path(__file__).parent
DATA=json.loads((ROOT/'data/knowledge.json').read_text(encoding='utf-8'))
# Public engine release: evidence-first retrieval; generative synthesis can be layered on later.
RELEASE='v3.0-live-candidate'

CLAIMS=DATA['claims']; RULES=DATA['rules']; CONFLICTS=DATA['conflicts']
AUTH={x:i for i,x in enumerate(DATA['authority_order'])}

def tokens(s): return set(re.findall(r"[a-z0-9%]+",s.lower()))
def score(q,c):
    qt=tokens(q); ct=tokens(c['Claim']+' '+c.get('Category','')+' '+c.get('Notes',''))
    if not qt:return 0
    s=3*len(qt&ct)/len(qt)
    # exact phrase / important domain boosts
    ql=q.lower(); cl=c['Claim'].lower()
    for term in ['guild creation','command points','war frenzy','rally','auto-join','home port','style advantage','energy core','glory acquisition','trade shipping','killstreak','kaboom','arms race','flagship','champion']:
        if term in ql and term in cl:s+=2
    if c.get('Status')=='Confirmed': s+=1
    if c.get('Evidence Tier','').startswith('Tier 1'): s+=2
    return s

def recommend(q, objective='general'):
    # Deterministic recommendation layer: retrieve high-authority claims relevant to the objective.
    objective_terms={'pvp':'pvp arena gvg port war combat','pve':'pve boss event hunting ground shrine','f2p':'f2p free progression economy spending','progression':'energy core building research shipyard construction','economy':'trade home port resources credits guild vouchers','event':'event rewards currency points guild'}
    qq=(q+' '+objective_terms.get(objective,'')).strip()
    ranked=sorted(((score(qq,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True)
    hits=[c for s,c in ranked if s>1.0 and c.get('Status') not in ('Rejected','Superseded')][:12]
    hits=sorted(hits,key=lambda c:(AUTH.get(c.get('Evidence Tier',''),99), -score(qq,c)),reverse=False)
    return {'question':q,'objective':objective,'results':hits,'disclaimer':'Recommendations are evidence-grounded retrieval until the production LLM synthesis layer is connected.'}

def answer(q):
    ql=q.lower()
    # conflict-first safety for known critical topics
    critical=[]
    for x in CONFLICTS:
        if any(k in ql for k in tokens(x['Topic'])):
            critical.append(x)
    ranked=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True)
    hits=[c for s,c in ranked if s>1.0][:10]
    # suppress stale/rejected claims unless explicitly asked
    hits=[c for c in hits if c.get('Status') not in ('Rejected','Superseded')][:8]
    # prefer Tier1 for exact mechanics
    hits=sorted(hits,key=lambda c:(AUTH.get(c.get('Evidence Tier',''),99), -float(c.get('Confidence','').startswith('High')) if False else 0))
    return {
      'question':q,
      'answer_type':'evidence_ranked',
      'results':hits,
      'critical_conflicts':critical,
      'rules_applied':RULES[:4],
      'note':'Tier 1 evidence is preferred for mechanics. Meta/recommendations are labeled and are never presented as hard mechanics.'
    }

class H(BaseHTTPRequestHandler):
    def _json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/health': return self._json({'ok':True,'version':RELEASE,'claims':len(CLAIMS),'sources':DATA['stats'].get('sources',0),'changes':DATA['stats'].get('change_log_entries',0),'conflicts':len(CONFLICTS),'tier1':DATA['stats']['tier1_claims']})
        if u.path=='/api/ask': return self._json(answer(parse_qs(u.query).get('q',[''])[0]))
        if u.path=='/api/recommend':
            qs=parse_qs(u.query); q=qs.get('q',[''])[0]; objective=qs.get('objective',['general'])[0]; return self._json(recommend(q,objective))
        if u.path=='/api/claims':
            q=parse_qs(u.query).get('q',[''])[0]; lim=int(parse_qs(u.query).get('limit',['50'])[0]);
            res=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True) if q else [(0,c) for c in CLAIMS]
            return self._json({'results':[c for s,c in res[:lim]]})
        if u.path=='/api/conflicts': return self._json({'results':CONFLICTS})
        if u.path=='/api/rules': return self._json({'rules':RULES,'authority_order':DATA['authority_order']})
        if u.path=='/' or u.path=='/index.html':
            b=(ROOT/'web/index.html').read_bytes(); self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b); return
        self.send_error(404)
    def log_message(self,*a): pass

if __name__=='__main__':
    port=int(os.getenv('PORT','8000')); print(f'FGF Agent v2 running on http://127.0.0.1:{port}'); ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()
