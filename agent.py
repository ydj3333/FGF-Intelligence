import json,re,os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT=Path(__file__).parent
DATA=json.loads((ROOT/'data/knowledge.json').read_text(encoding='utf-8'))
RELEASE='v3.1-synthesis-ready'
CLAIMS=DATA['claims']; RULES=DATA['rules']; CONFLICTS=DATA['conflicts']
AUTH={x:i for i,x in enumerate(DATA['authority_order'])}
LLM_MODEL=os.getenv('FGF_LLM_MODEL','gpt-5.6-luna')


def tokens(s): return set(re.findall(r"[a-z0-9%]+",s.lower()))

def score(q,c):
    qt=tokens(q); ct=tokens(c['Claim']+' '+c.get('Category','')+' '+c.get('Notes',''))
    if not qt:return 0
    s=3*len(qt&ct)/len(qt)
    ql=q.lower(); cl=c['Claim'].lower()
    for term in ['guild creation','command points','war frenzy','rally','auto-join','home port','style advantage','energy core','glory acquisition','trade shipping','killstreak','kaboom','arms race','flagship','champion']:
        if term in ql and term in cl:s+=2
    if c.get('Status')=='Confirmed': s+=1
    if c.get('Evidence Tier','').startswith('Tier 1'): s+=2
    return s


def retrieve(q, limit=10):
    ranked=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True)
    hits=[c for s,c in ranked if s>1.0 and c.get('Status') not in ('Rejected','Superseded')]
    # Diversity: avoid returning many near-identical claims from one topic.
    out=[]; seen=set()
    for c in hits:
        key=(c.get('Category',''), c.get('Claim','').lower()[:80])
        if key in seen: continue
        seen.add(key); out.append(c)
        if len(out)>=limit: break
    return out


def relevant_conflicts(q):
    ql=q.lower(); out=[]
    for x in CONFLICTS:
        topic=x.get('Topic','')
        if any(k in ql for k in tokens(topic)):
            out.append(x)
    return out


def evidence_packet(question, claims, conflicts=None):
    rows=[]
    for i,c in enumerate(claims,1):
        rows.append({
            'id':i,
            'claim':c.get('Claim',''),
            'category':c.get('Category',''),
            'tier':c.get('Evidence Tier',''),
            'confidence':c.get('Confidence',''),
            'status':c.get('Status',''),
            'source':c.get('Source',''),
            'notes':c.get('Notes',''),
            'timestamp':c.get('Timestamp','')
        })
    return {'question':question,'evidence':rows,'conflicts':conflicts or []}


def synthesize(question, claims, conflicts=None, mode='answer'):
    """Turn retrieved evidence into a concise player-facing answer.
    If FGF_LLM_API_KEY is absent, use a deterministic fallback rather than dumping raw claims.
    """
    conflicts=conflicts or []
    key=os.getenv('FGF_LLM_API_KEY') or os.getenv('OPENAI_API_KEY')
    packet=evidence_packet(question,claims,conflicts)
    if not key:
        if not claims:
            return {'text':'I could not find sufficiently relevant evidence for that question.','model':'fallback','evidence_used':[]}
        lead=claims[0]
        text=lead.get('Claim','')
        if conflicts:
            text += ' There is also a preserved evidence conflict; I would not treat the conflicting value as current without further verification.'
        return {'text':text,'model':'fallback','evidence_used':list(range(1,min(4,len(claims))+1))}

    system=(
        'You are FGF Intelligence, an evidence-first game intelligence assistant for Foundation: Galactic Frontier. '
        'Answer like a strong expert assistant, not like a database. Synthesize the evidence into a direct answer. '
        'Do not dump claims. Do not invent facts. Tier 1 is authoritative only for the exact proposition it establishes. '
        'If evidence conflicts, state the current higher-tier result and briefly mention the preserved conflict. '
        'Separate mechanics from recommendations/meta. If evidence is insufficient, say so. '
        'Use only the supplied evidence packet. Keep normal answers concise (usually 2-6 short paragraphs or bullets). '
        'Return JSON with keys: answer, evidence_ids, uncertainty. evidence_ids must contain only IDs from the packet.'
    )
    user=json.dumps({'mode':mode,'packet':packet},ensure_ascii=False)
    body=json.dumps({'model':LLM_MODEL,'input':[{'role':'system','content':system},{'role':'user','content':user}], 'max_output_tokens':700}).encode()
    req=Request('https://api.openai.com/v1/responses',data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(req,timeout=25) as r:
            data=json.loads(r.read().decode('utf-8'))
        text=data.get('output_text','').strip()
        if not text:
            for item in data.get('output',[]):
                for part in item.get('content',[]):
                    if part.get('type')=='output_text': text+=part.get('text','')
        parsed=json.loads(text)
        return {'text':parsed.get('answer','').strip(),'model':LLM_MODEL,'evidence_used':parsed.get('evidence_ids',[]),'uncertainty':parsed.get('uncertainty','')}
    except (HTTPError,URLError,TimeoutError,ValueError,KeyError) as e:
        return {'text':'The evidence was retrieved, but the synthesis service is temporarily unavailable. Showing the strongest evidence instead.','model':'fallback','evidence_used':list(range(1,min(4,len(claims))+1)),'synthesis_error':type(e).__name__}


def recommend(q, objective='general'):
    objective_terms={'pvp':'pvp arena gvg port war combat','pve':'pve boss event hunting ground shrine','f2p':'f2p free progression economy spending','progression':'energy core building research shipyard construction','economy':'trade home port resources credits guild vouchers','event':'event rewards currency points guild'}
    qq=(q+' '+objective_terms.get(objective,'')).strip()
    hits=retrieve(qq,12)
    synthesis=synthesize(q or ('Give me the best recommendation for '+objective),hits,relevant_conflicts(q+' '+objective),'recommendation')
    return {'question':q,'objective':objective,'answer':synthesis['text'],'model':synthesis['model'],'evidence_used':synthesis.get('evidence_used',[]),'uncertainty':synthesis.get('uncertainty',''),'evidence':hits,'conflicts':relevant_conflicts(q+' '+objective),'disclaimer':'Recommendations are synthesized from retrieved evidence; they are not hard mechanics unless the evidence itself establishes a mechanic.'}


def answer(q):
    critical=relevant_conflicts(q)
    hits=retrieve(q,10)
    synthesis=synthesize(q,hits,critical,'answer')
    return {'question':q,'answer_type':'synthesized_evidence','answer':synthesis['text'],'model':synthesis['model'],'evidence_used':synthesis.get('evidence_used',[]),'uncertainty':synthesis.get('uncertainty',''),'evidence':hits,'critical_conflicts':critical,'rules_applied':RULES[:4],'note':'The answer is synthesized from retrieved evidence. Tier 1 is preferred for mechanics; conflicts and uncertainty are preserved.'}


class H(BaseHTTPRequestHandler):
    def _json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode(); self.send_response(status); self.send_header('Content-Type','application/json; charset=utf-8'); self.send_header('Content-Length',str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/health': return self._json({'ok':True,'version':RELEASE,'claims':len(CLAIMS),'sources':DATA['stats'].get('sources',0),'changes':DATA['stats'].get('change_log_entries',0),'conflicts':len(CONFLICTS),'tier1':DATA['stats']['tier1_claims'],'synthesis':bool(os.getenv('FGF_LLM_API_KEY') or os.getenv('OPENAI_API_KEY'))})
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
    port=int(os.getenv('PORT','8000')); print(f'FGF Intelligence running on http://127.0.0.1:{port}'); ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()
