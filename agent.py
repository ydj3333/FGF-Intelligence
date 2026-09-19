import json,re,os,time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT=Path(__file__).parent
DATA=json.loads((ROOT/'data/knowledge.json').read_text(encoding='utf-8'))
RELEASE='v3.5-seven-layer-reasoning'
CLAIMS=DATA['claims']; RULES=DATA['rules']; CONFLICTS=DATA['conflicts']
AUTH={x:i for i,x in enumerate(DATA['authority_order'])}
LLM_MODEL=os.getenv('FGF_LLM_MODEL','gpt-5.6-luna')
LLM_URL=os.getenv('FGF_LLM_API_URL','https://api.openai.com/v1/responses')

# v3.3 uses a layered retrieval/reasoning stack rather than pretending that
# an untrained neural network can safely learn game truth by itself.
# Learning is therefore bounded: query intent, terminology, authority, status,
# diversity and conflict signals improve retrieval, while the evidence corpus
# remains immutable unless a human/admin evidence pipeline changes it.
DOMAIN_TERMS={
 'damage':['major damage','minor damage','ship loss','repair modules','repair cabin','counterattack'],
 'progression':['energy core','flagship','champion','shipyard','technology','building'],
 'combat':['command points','style advantage','beam','kinetic','ion','war frenzy','counterattack'],
 'guild':['commerce guild','rally','guild technology','port occupation'],
 'economy':['trade shipping','home port','credits','resources','investment'],
 'event':['glory','hunting ground','killstreak','event','arms race']
}
STOP={'what','when','where','how','does','do','is','are','the','a','an','to','of','for','and','or','i','my','you','your','can','has','have','with','on','in'}

def tokens(s):
    return set(re.findall(r"[a-z0-9%]+",s.lower()))

def phrases(s):
    q=s.lower()
    found=[]
    for group in DOMAIN_TERMS.values():
        for term in group:
            if term in q: found.append(term)
    return found

def intent_profile(q):
    specific=classify_intent(q)
    if specific=='Fleet Damage/Repair': return 'repair'
    if specific=='Progression': return 'progression'
    if specific=='Champions': return 'champions'
    if specific=='Events': return 'event'
    if specific=='Economy': return 'economy'
    if specific=='Combat': return 'combat'
    ql=q.lower()
    if any(x in ql for x in ['best','recommend','should i','which','build','strategy']): return 'recommendation'
    if any(x in ql for x in ['cost','price','how much','time','hours','days']): return 'calculation'
    return 'mechanics'

def score(q,c):
    qt=tokens(q)-STOP; ct=tokens(c.get('Claim','')+' '+c.get('Category','')+' '+c.get('Notes',''))
    if not qt:return 0
    overlap=len(qt&ct)/max(1,len(qt))
    s=3.2*overlap
    qphr=phrases(q); cl=c.get('Claim','').lower(); notes=c.get('Notes','').lower()
    for p in qphr:
        if p in cl:s+=3.0
        elif p in notes:s+=1.2
    if c.get('Status')=='Confirmed': s+=1.2
    if c.get('Status') in ('Rejected','Superseded'): s-=20
    tier=c.get('Evidence Tier','')
    if tier.startswith('Tier 1'): s+=2.5
    elif tier.startswith('Tier 2'): s+=1.2
    # Prefer claims that match the query's apparent intent.
    intent=intent_profile(q)
    cat=c.get('Category','').lower()
    if intent=='recommendation' and any(x in cat for x in ['strategy','recommend','meta']): s+=1.0
    if intent=='progression' and any(x in cat for x in ['progress','building','technology','flagship']): s+=1.0
    if intent=='calculation' and any(x in cat for x in ['cost','formula','economy','progress']): s+=1.0
    return s

INTENT_CLASSES = {
 'Fleet Damage/Repair':['repair','damaged','destroyed','major damage','minor damage','repair module','repair cabin','repair bay','fix my fleet','heal','recover'],
 'Progression':['energy core','level up','unlock','progress','core level','upgrade requirement'],
 'Combat':['battle','fight','pvp','gvg','counterattack','command point','beam','kinetic','ionic','ion','style advantage'],
 'Economy':['resources','farm','earn','spend','credits','free','f2p'],
 'Champions':['champion','hero','team','composition','tier list'],
 'Events':['event','glory','killstreak','hunting ground']
}
CONSTRAINT_PATTERNS = {
 'F2P':['f2p','free to play','ad free','no money','free way','without spending','no spending'],
 'Best':['best','optimal','most efficient','priority','prefer'],
 'Fast':['fastest','quick','as soon as possible','now','today'],
 'Endgame':['late game','endgame','max level','core 30+']
}

def classify_intent(q):
    ql=q.lower()
    # Specific intents must win over broad domains such as Combat/Economy.
    for intent in ['Fleet Damage/Repair','Progression','Champions','Events','Economy','Combat']:
        if any(k in ql for k in INTENT_CLASSES[intent]):
            return intent
    return 'Unknown'

def extract_constraints(q):
    ql=q.lower()
    return [name for name,patterns in CONSTRAINT_PATTERNS.items()
            if any(p in ql for p in patterns)]

def query_domains(q):
    ql=q.lower()
    domains=[]
    if classify_intent(q)=='Fleet Damage/Repair': domains.append('damage')
    
    # Explicit phrase routing prevents unrelated high-frequency terms such as
    # "upgrade" or "best" from dominating a question about repair/damage.
    if any(x in ql for x in ['repair','major damage','minor damage','repair module','repair cabin','auto-repair','auto repair']):
        domains.append('damage')
    if any(x in ql for x in ['command point',' cp ','tactical advantage','counterattack','beam','kinetic','ionic','ion','style advantage']):
        domains.append('combat')
    if any(x in ql for x in ['energy core','flagship level','champion level','shipyard','building level','unlock','upgrade requirement']):
        domains.append('progression')
    if any(x in ql for x in ['commerce guild','rally','guild technology','port occupation']):
        domains.append('guild')
    if any(x in ql for x in ['trade','home port','shipping','credits','resources','investment']):
        domains.append('economy')
    if any(x in ql for x in ['event','glory','killstreak','hunting ground']):
        domains.append('event')
    return domains

def current_scope_relevance(c,current_season='S2'):
    status=str(c.get('Status','')).lower()
    return status not in ('rejected','superseded')

def claim_relevance(q,c):
    ql=q.lower(); cl=(c.get('Claim','')+' '+c.get('Category','')+' '+c.get('Notes','')).lower()
    domains=query_domains(q)
    if domains:
        domain_match=any(term in cl for d in domains for term in DOMAIN_TERMS.get(d,[]))
        # Category/domain mismatch is a hard penalty, not a soft preference.
        cat=c.get('Category','').lower()
        if not domain_match and not any(x in cat for x in domains):
            return False
    return True

def retrieve(q,limit=10):
    ranked=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True)
    hits=[c for s,c in ranked
          if s>0.85 and c.get('Status') not in ('Rejected','Superseded')
          and current_scope_relevance(c) and claim_relevance(q,c)]
    out=[];seen=set();categories=set()
    for c in hits:
        key=(c.get('Category',''),c.get('Claim','').lower()[:120])
        if key in seen:continue
        seen.add(key)
        cat=c.get('Category','')
        out.append(c);categories.add(cat)
        if len(out)>=limit:break
    return out

def relevant_conflicts(q):
    ql=q.lower(); out=[]
    for x in CONFLICTS:
        topic=x.get('Topic','').lower()
        if topic and (topic in ql or any(k in ql for k in tokens(topic) if len(k)>3)):
            out.append(x)
    return out

def evidence_packet(question,claims,conflicts=None):
    return {'question':question,'intent':intent_profile(question),'constraints':extract_constraints(question),'season_scope':'S2/current preferred; historical evidence retained when needed','evidence':[{'id':i,'claim':c.get('Claim',''),'category':c.get('Category',''),'tier':c.get('Evidence Tier',''),'confidence':c.get('Confidence',''),'status':c.get('Status',''),'source':c.get('Source',''),'notes':c.get('Notes',''),'timestamp':c.get('Timestamp','')} for i,c in enumerate(claims,1)],'conflicts':conflicts or []}

def extract_output(data):
    text=str(data.get('output_text') or '').strip()
    if not text:
        for item in data.get('output',[]):
            for part in item.get('content',[]):
                if part.get('type')=='output_text':text+=part.get('text','')
    return text.strip()

def parse_synthesis(text,max_id):
    try:
        obj=json.loads(text)
        if isinstance(obj,dict) and obj.get('answer'):
            ids=[]
            for x in obj.get('evidence_ids',[]):
                try:
                    n=int(x)
                    if 1<=n<=max_id:ids.append(n)
                except (TypeError,ValueError):pass
            return obj['answer'].strip(),ids,obj.get('uncertainty','')
    except (ValueError,TypeError):pass
    ids=[]
    for n in re.findall(r'(?:evidence|source|ref(?:erence)?)\s*(?:ids?|#)?\s*[:#]?\s*([0-9, ]+)',text,re.I):
        for x in n.split(','):
            try:
                v=int(x.strip())
                if 1<=v<=max_id and v not in ids:ids.append(v)
            except ValueError:pass
    return text,ids,''

def fallback_answer(question,claims,conflicts=None):
    if not claims:return {'text':'I could not find sufficiently relevant evidence for that question.','model':'evidence-fallback','evidence_used':[],'uncertainty':'Insufficient retrieved evidence.'}
    mechanics=[c for c in claims if c.get('Evidence Tier','').startswith('Tier 1')]
    selected=mechanics[:4] or claims[:4]
    lines=['Based on the retrieved FGF evidence:']
    for c in selected: lines.append('• '+c.get('Claim','').strip())
    if conflicts:lines.append('• Uncertainty: a related evidence conflict is preserved for review rather than resolved by assumption.')
    return {'text':'\n'.join(lines),'model':'evidence-fallback','evidence_used':[claims.index(c)+1 for c in selected],'uncertainty':'Deterministic fallback used; synthesis model unavailable.'}

def _api_error_detail(e):
    try:
        raw=e.read().decode('utf-8','replace');obj=json.loads(raw);err=obj.get('error',{}) if isinstance(obj,dict) else {}
        return '; '.join(x for x in [err.get('type',''),err.get('code',''),err.get('message','')] if x)[:600]
    except Exception:return str(getattr(e,'reason',e))[:300]

def call_llm(question,claims,conflicts,mode,temperature=0.2):
    key=os.getenv('FGF_LLM_API_KEY') or os.getenv('OPENAI_API_KEY')
    if not key:return None,{'synthesis_error':'missing_api_key'}
    system='''You are FGF Intelligence, an evidence-first expert assistant for Foundation: Galactic Frontier.\n\nUse ONLY the supplied evidence packet. Answer the player directly, naturally and concisely. Obey the packet intent and constraints. Never substitute a related mechanic for the requested one. Treat F2P/free as a spending constraint. Treat historical seasons as historical unless current applicability is established. Do not dump database records. For mechanics, prioritize Tier-1 and current Confirmed evidence. Preserve meaningful conflicts; never average or silently choose between conflicting claims. Separate confirmed mechanics from recommendations/meta. Never invent numbers, costs, timers, requirements or effects. If evidence is insufficient, explicitly say so.\n\nReturn JSON only with this shape: {"answer":"...","evidence_ids":[1,2],"uncertainty":"..."}. The answer should normally be 1 direct paragraph followed by 2-5 useful bullets. Cite evidence inline as [E1], [E2] and finish with a short Evidence: [E1, E2] line. Do not mention APIs, prompts, retrieval, hidden reasoning, or that you are a language model.'''
    user=json.dumps({'mode':mode,'packet':evidence_packet(question,claims,conflicts)},ensure_ascii=False)
    body=json.dumps({'model':LLM_MODEL,'input':[{'role':'system','content':system},{'role':'user','content':user}],'temperature':temperature,'max_output_tokens':900}).encode()
    req=Request(LLM_URL,data=body,headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    try:
        with urlopen(req,timeout=35) as r:data=json.loads(r.read().decode('utf-8'))
        text=extract_output(data)
        if not text:raise ValueError('empty_model_output')
        return text,{}
    except HTTPError as e:return None,{'synthesis_error':'HTTP '+str(e.code),'synthesis_error_detail':_api_error_detail(e)}
    except (URLError,TimeoutError) as e:return None,{'synthesis_error':type(e).__name__}
    except (ValueError,KeyError) as e:return None,{'synthesis_error':type(e).__name__}

def synthesize(question,claims,conflicts=None,mode='answer'):
    conflicts=conflicts or []
    text,err=call_llm(question,claims,conflicts,mode,0.2)
    if text:
        answer_text,ids,unc=parse_synthesis(text,len(claims))
        if answer_text:return {'text':answer_text,'model':LLM_MODEL,'evidence_used':ids or list(range(1,min(4,len(claims))+1)),'uncertainty':unc}
    # One low-temperature retry handles transient/model-format failures without
    # changing evidence or truth state.
    if err.get('synthesis_error') not in ('missing_api_key',):
        retry_text,retry_err=call_llm(question,claims,conflicts,mode,0.0)
        if retry_text:
            answer_text,ids,unc=parse_synthesis(retry_text,len(claims))
            if answer_text:return {'text':answer_text,'model':LLM_MODEL,'evidence_used':ids or list(range(1,min(4,len(claims))+1)),'uncertainty':unc}
        err=retry_err or err
    fb=fallback_answer(question,claims,conflicts)
    fb.update(err)
    return fb

def recommend(q,objective='general'):
    objective_terms={'pvp':'pvp arena gvg port war combat','pve':'pve boss event hunting ground shrine','f2p':'f2p free progression economy spending','progression':'energy core building research shipyard construction','economy':'trade home port resources credits guild vouchers','event':'event rewards currency points guild'}
    qq=(q+' '+objective_terms.get(objective,'')).strip();hits=retrieve(qq,12)
    s=synthesize(q or ('Give me the best recommendation for '+objective),hits,relevant_conflicts(q+' '+objective),'recommendation')
    return {'question':q,'objective':objective,'answer':s['text'],'model':s['model'],'evidence_used':s.get('evidence_used',[]),'uncertainty':s.get('uncertainty',''),'synthesis_error':s.get('synthesis_error'),'synthesis_error_detail':s.get('synthesis_error_detail'),'evidence':hits,'conflicts':relevant_conflicts(q+' '+objective),'disclaimer':'Recommendations are synthesized from retrieved evidence; they are not hard mechanics unless the evidence itself establishes a mechanic.'}

def answer_quality_gate(q,text,claims):
    low=text.lower(); intent=classify_intent(q); constraints=extract_constraints(q)
    result={'addresses_question':False,'uses_relevant_evidence':False,'respects_constraints':False,'passes':False}
    if intent=='Fleet Damage/Repair':
        result['addresses_question']=any(x in low for x in ('repair','damage','recover','repair bay','repair cabin'))
        result['uses_relevant_evidence']=any(any(x in c.get('Claim','').lower() for x in ('repair','damage','recover')) for c in claims)
        result['respects_constraints']=('free' in low or 'without repair modules' in low or 'without spending' in low) if 'F2P' in constraints else True
        if 'command point' in low and not any(x in low for x in ('repair','damage','recover')): return result
    else:
        result['addresses_question']=len(text.strip())>=20
        result['uses_relevant_evidence']=bool(claims)
        result['respects_constraints']=('free' in low or 'without spending' in low) if 'F2P' in constraints else True
    result['passes']=all(result.values())
    return result
def fallback_answer(question,claims,conflicts=None):
    if not claims:return {'text':'I could not find sufficiently relevant evidence for that question.','model':'evidence-fallback','evidence_used':[],'uncertainty':'Insufficient retrieved evidence.'}
    domains=query_domains(question)
    if 'damage' in domains:
        selected=[c for c in claims if any(x in c.get('Claim','').lower() for x in ('minor damage','major damage','repair module','repair cabin','auto-repair'))][:5]
        lines=['For repairing fleets without consuming Repair Modules:']
        for c in selected[:4]: lines.append('• '+c.get('Claim','').strip())
        if not selected: lines.append('• The current evidence does not establish a free repair method.')
        return {'text':'\\n'.join(lines),'model':'evidence-fallback','evidence_used':[claims.index(c)+1 for c in selected[:4]],'uncertainty':'Direct repair evidence used; no unsupported ad/free mechanic was assumed.'}
    mechanics=[c for c in claims if c.get('Evidence Tier','').startswith('Tier 1')]
    selected=mechanics[:4] or claims[:4]
    lines=['Based on the retrieved FGF evidence:']
    for c in selected: lines.append('• '+c.get('Claim','').strip())
    if conflicts:lines.append('• Uncertainty: a related evidence conflict is preserved for review rather than resolved by assumption.')
    return {'text':'\\n'.join(lines),'model':'evidence-fallback','evidence_used':[claims.index(c)+1 for c in selected],'uncertainty':'Deterministic fallback used; synthesis model unavailable.'}

def answer(q):
    critical=relevant_conflicts(q);hits=retrieve(q,10);s=synthesize(q,hits,critical,'answer')
    if not answer_quality_gate(q,s.get('text',''),hits):
        s=fallback_answer(q,hits,critical)
        s['uncertainty']='Answer-quality gate rejected the synthesis; deterministic evidence-safe answer returned.'
    return {'question':q,'answer_type':'synthesized_evidence','answer':s['text'],'model':s['model'],'evidence_used':s.get('evidence_used',[]),'uncertainty':s.get('uncertainty',''),'synthesis_error':s.get('synthesis_error'),'synthesis_error_detail':s.get('synthesis_error_detail'),'evidence':hits,'critical_conflicts':critical,'rules_applied':RULES[:4],'note':'Answer is synthesized from retrieved evidence and passed an evidence-relevance gate. Tier 1 is preferred for mechanics; conflicts and uncertainty are preserved.'}

class H(BaseHTTPRequestHandler):
    def _json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/health':return self._json({'ok':True,'version':RELEASE,'claims':len(CLAIMS),'sources':DATA['stats'].get('sources',0),'changes':DATA['stats'].get('change_log_entries',0),'conflicts':len(CONFLICTS),'tier1':DATA['stats']['tier1_claims'],'synthesis':bool(os.getenv('FGF_LLM_API_KEY') or os.getenv('OPENAI_API_KEY')),'model':LLM_MODEL,'adaptive_retrieval':True,'bounded_learning':True})
        if u.path=='/api/ask':return self._json(answer(parse_qs(u.query).get('q',[''])[0]))
        if u.path=='/api/recommend':
            qs=parse_qs(u.query);q=qs.get('q',[''])[0];objective=qs.get('objective',['general'])[0];return self._json(recommend(q,objective))
        if u.path=='/api/claims':
            qs=parse_qs(u.query);q=qs.get('q',[''])[0];lim=int(qs.get('limit',['50'])[0]);res=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True) if q else [(0,c) for c in CLAIMS];return self._json({'results':[c for s,c in res[:lim]]})
        if u.path=='/api/conflicts':return self._json({'results':CONFLICTS})
        if u.path=='/api/rules':return self._json({'rules':RULES,'authority_order':DATA['authority_order']})
        if u.path=='/' or u.path=='/index.html':
            b=(ROOT/'web/index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        self.send_error(404)
    def log_message(self,*a):pass

if __name__=='__main__':
    port=int(os.getenv('PORT','8000'));print(f'FGF Intelligence running on http://127.0.0.1:{port}');ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()
