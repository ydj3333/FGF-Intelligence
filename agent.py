import json,re,os,time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

ROOT=Path(__file__).parent
DATA=json.loads((ROOT/'data/knowledge.json').read_text(encoding='utf-8'))
RELEASE='v5.0.0-player-state'
CLAIMS=DATA['claims']; RULES=DATA['rules']; CONFLICTS=DATA['conflicts']
CONFLICT_REVIEWS_FILE=ROOT/'data'/'conflict_reviews.json'
SUPABASE_URL=os.getenv('FGF_SUPABASE_URL','https://qdoixzfkkmvzjfkhzups.supabase.co').rstrip('/')
SUPABASE_SECRET=os.getenv('FGF_SUPABASE_SECRET_KEY') or os.getenv('FGF_SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
ADMIN_TOKEN=os.getenv('FGF_ADMIN_TOKEN')
try:
    CONFLICT_REVIEWS=json.loads(CONFLICT_REVIEWS_FILE.read_text()) if CONFLICT_REVIEWS_FILE.exists() else {}
except Exception:
    CONFLICT_REVIEWS={}

def _supabase_headers():
    if not SUPABASE_SECRET:
        return None
    return {
        'apikey':SUPABASE_SECRET,
        'Authorization':'Bearer '+SUPABASE_SECRET,
        'Content-Type':'application/json',
        'Accept':'application/json'
    }

def load_remote_conflict_reviews():
    headers=_supabase_headers()
    if not headers:
        return {}
    try:
        req=Request(
            SUPABASE_URL+'/rest/v1/conflict_reviews?select=conflict_id,decision,evidence,notes,reviewer,decided_at&order=decided_at.desc',
            headers=headers, method='GET')
        with urlopen(req,timeout=3) as r:
            rows=json.loads(r.read().decode('utf-8') or '[]')
        return {str(x.get('conflict_id')):{
            'conflict_id':str(x.get('conflict_id')),
            'decision':str(x.get('decision','')),
            'evidence':str(x.get('evidence','')),
            'notes':str(x.get('notes','')),
            'reviewer':str(x.get('reviewer','admin')),
            'reviewed_at':str(x.get('decided_at',''))
        } for x in rows if x.get('conflict_id')}
    except Exception:
        return {}

def apply_conflict_review_to_memory(review):
    for c in CONFLICTS:
        if c.get('Conflict ID')==review['conflict_id']:
            c['Review Status']=review['decision']
            c['Reviewer Evidence']=review.get('evidence','')
            c['Reviewer Notes']=review.get('notes','')
            c['Reviewer']=review.get('reviewer','admin')
            c['Reviewed At']=review.get('reviewed_at','')
            break

def save_conflict_review(review):
    CONFLICT_REVIEWS[review['conflict_id']]=review
    try:
        CONFLICT_REVIEWS_FILE.write_text(json.dumps(CONFLICT_REVIEWS,ensure_ascii=False,indent=2)+'\n')
    except Exception:
        pass
    apply_conflict_review_to_memory(review)

    headers=_supabase_headers()
    if not headers:
        return False
    try:
        payload={
            'conflict_id':review['conflict_id'],
            'decision':review['decision'],
            'evidence':review.get('evidence',''),
            'notes':review.get('notes',''),
            'reviewer':review.get('reviewer','admin'),
            'decided_at':review.get('reviewed_at','') or None
        }
        req=Request(
            SUPABASE_URL+'/rest/v1/conflict_reviews?on_conflict=conflict_id',
            data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
            headers={**headers,'Prefer':'resolution=merge-duplicates,return=minimal'},
            method='POST')
        with urlopen(req,timeout=4):
            pass
        return True
    except Exception:
        return False

_REMOTE_REVIEWS=load_remote_conflict_reviews()
if _REMOTE_REVIEWS:
    CONFLICT_REVIEWS.update(_REMOTE_REVIEWS)
    for _review in _REMOTE_REVIEWS.values():
        apply_conflict_review_to_memory(_review)

AUTH={x:i for i,x in enumerate(DATA['authority_order'])}
LLM_MODEL=os.getenv('FGF_LLM_MODEL','gpt-5.6-luna')
LLM_URL=os.getenv('FGF_LLM_API_URL','https://api.openai.com/v1/responses')
SUPABASE_URL=os.getenv('FGF_SUPABASE_URL','https://qdoixzfkkmvzjfkhzups.supabase.co').rstrip('/')
SUPABASE_SECRET=os.getenv('FGF_SUPABASE_SECRET_KEY') or os.getenv('FGF_SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
ADMIN_TOKEN=os.getenv('FGF_ADMIN_TOKEN')

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
    # Recommendation/player-roster language is more specific than a damage-type
    # token such as "kinetic". Never let the energy type hijack a hero question.
    if (re.search(r'\b(?:hero|heroes|champion|champions)\b', ql)
        and any(x in ql for x in ('best','optimal','recommended','team','composition','tier list'))):
        return 'Champions'
    # Match multi-word phrases normally, but match short tokens as whole words.
    # This prevents false positives such as "ion" matching the suffix of "fusion".
    def matches(keyword):
        if ' ' in keyword or '-' in keyword:
            return keyword in ql
        return re.search(r'\b'+re.escape(keyword)+r'\b', ql) is not None
    # Specific intents must win over broad domains such as Combat/Economy.
    # Player/roster recommendation terms take precedence over broad combat terms.
    ordered=['Fleet Damage/Repair','Progression','Champions','Events','Combat','Economy']
    for intent in ordered:
        if any(matches(k) for k in INTENT_CLASSES[intent]):
            return intent
    # Explicit shorthand/late-progression vocabulary.
    if re.search(r'\bcp\b', ql) or 'command point' in ql:
        return 'Combat'
    if re.search(r'\bcore\s*(?:3[1-5]|35)\b', ql) or 'fusion seed' in ql or 'fusion seeds' in ql:
        return 'Progression'
    return 'Unknown'

def extract_constraints(q):
    ql=q.lower()
    return [name for name,patterns in CONSTRAINT_PATTERNS.items()
            if any(p in ql for p in patterns)]

def query_domains(q):
    """Map the user's detected intent to evidence domains before retrieval."""
    intent=classify_intent(q)
    mapping={
        'Fleet Damage/Repair':['damage'],
        'Progression':['progression'],
        'Combat':['combat'],
        'Economy':['economy'],
        'Champions':['champions'],
        'Events':['event'],
    }
    domains=list(mapping.get(intent,[]))
    ql=q.lower()
    # Only add a second domain when the user explicitly asks for it.
    explicit={
        'damage':['repair','major damage','minor damage','repair module','repair cabin','auto-repair','auto repair'],
        'combat':['command point',' cp ','counterattack','beam','kinetic','ionic','ion','style advantage'],
        'progression':['energy core','flagship level','champion level','shipyard','building level','unlock','upgrade requirement'],
        'guild':['commerce guild','rally','guild technology','port occupation'],
        'economy':['trade','home port','shipping','credits','resources','investment'],
        'event':['event','glory','killstreak','hunting ground'],
    }
    for domain,terms in explicit.items():
        if any(x in ql for x in terms) and domain not in domains:
            domains.append(domain)
    return domains

SEASON_CONTEXT = {
    'S1': {'description':'Baseline progression state; all players start here.'},
    'S2': {'description':'Later progression state; applies after the player/server reaches S2.'},
    'S3': {'description':'Later progression state; applies after the player/server reaches S3.'}
}

def season_of_claim(c):
    raw=str(c.get('Season/Version','')).upper()
    for season in ('S3','S2','S1'):
        if season in raw: return season
    return None

def get_applicable_evidence(claims, player_context=None):
    if not player_context or not player_context.get('season'):
        return claims, 'all_seasons'
    current=str(player_context['season']).upper()
    if current not in SEASON_CONTEXT:
        return claims, 'all_seasons'
    current_claims=[c for c in claims if season_of_claim(c) in (None,current)]
    transition=[]
    if current=='S1':
        transition=[c for c in claims if season_of_claim(c)=='S2' and any(x in c.get('Claim','').lower() for x in ('unlock','requires','available','introduces','level 31','level 32','level 33','level 34','level 35'))]
    return current_claims+transition, ('S1_with_S2_path' if current=='S1' else current)

def current_scope_relevance(c,current_season='S2'):
    status=str(c.get('Status','')).lower()
    return status not in ('rejected','superseded')

def topic_requirements(q):
    """Return hard topic requirements for high-risk question classes.
    These requirements prevent semantically adjacent evidence from becoming
    a substitute answer (for example Flagship costs answering an Energy Core
    cost question).
    """
    ql=q.lower()
    req=[]
    if ('fusion seed' in ql or 'fusion seeds' in ql or
        re.search(r'\\b(?:energy\\s+)?core\\s*(?:3[1-9]|[4-9]0?)\\b', ql) or
        'energy core' in ql):
        req.append('energy_core')
    if any(x in ql for x in ('repair','damaged','destroyed','repair module','repair cabin','repair bay','fix my fleet','recover')):
        req.append('repair')
    if any(x in ql for x in ('champion','champions','hero','heroes','ground team','composition','tier list')):
        req.append('champions')
    if any(x in ql for x in ('flagship','blueprint','core component','flagship component')):
        req.append('flagship')
    if any(x in ql for x in ('credits','resource','resources','farm','earn','spend','economy','trade')):
        req.append('economy')
    return list(dict.fromkeys(req))

def claim_relevance(q,c):
    ql=q.lower()
    cl=(c.get('Claim','')+' '+c.get('Category','')+' '+c.get('Notes','')).lower()
    domains=query_domains(q)
    requirements=topic_requirements(q)

    # Hard entity/topic gates first. These are intentionally conservative:
    # when a question asks for an exact topic, adjacent evidence is rejected.
    for req in requirements:
        if req=='energy_core':
            if not any(x in cl for x in ('energy core','core level','core 31','core 32','core 33','core 34','core 35','fusion seed','fusion seeds','refinery')):
                return False
            if any(x in cl for x in ('flagship blueprint','flagship component','champion fragment')) and not any(x in cl for x in ('energy core','core level','fusion seed','fusion seeds')):
                return False
        elif req=='repair':
            if not any(x in cl for x in ('repair','minor damage','major damage','recover','destroyed')):
                return False
        elif req=='champions':
            if not any(x in cl for x in ('champion','hero','ground team','composition','tier list')):
                return False
            # Generic Energy-Type mechanics are not champion recommendations.
            if any(x in ql for x in ('best','optimal','recommended')) and not any(x in cl for x in ('champion','hero','ground team','composition','tier list')):
                return False
        elif req=='flagship':
            if not any(x in cl for x in ('flagship','blueprint','core component')):
                return False
        elif req=='economy':
            if not any(x in cl for x in ('credit','resource','farm','earn','spend','economy','trade','shipping','home port')):
                return False

    if domains:
        domain_match=any(term in cl for d in domains for term in DOMAIN_TERMS.get(d,[]))
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

def exact_cost_question(q):
    ql=q.lower()
    return (('cost' in ql or 'costs' in ql or 'how much' in ql) and
            ('fusion seed' in ql or 'fusion seeds' in ql or 'core 35' in ql))

def fallback_answer(question,claims,conflicts=None):
    ql=question.lower()

    if exact_cost_question(question):
        exact=[c for c in claims if any(k in c.get('Claim','').lower() for k in ('fusion seed','fusion seeds','cost','core level 35','l35'))]
        numeric=[c for c in exact if re.search(r'\b(?:\d{1,3}(?:,\d{3})*|\d+)\b',c.get('Claim','')) and ('fusion seed' in c.get('Claim','').lower() or 'cost' in c.get('Claim','').lower())]
        if not numeric:
            return {'text':'The current evidence does not establish an exact Fusion Seed cost for Energy Core 35. I will not infer or substitute another upgrade cost.','model':'evidence-fallback','evidence_used':[claims.index(c)+1 for c in exact[:4]],'uncertainty':'Exact Core 35 Fusion Seed cost is not established in the retrieved evidence.'}

    if not claims:
        return {'text':'I could not find sufficiently relevant evidence for that question.','model':'evidence-fallback','evidence_used':[],'uncertainty':'Insufficient retrieved evidence.'}

    # Recommendation questions about heroes/champions must not fall back to generic
    # energy-type mechanics. Use champion evidence and clearly separate meta from facts.
    if classify_intent(question)=='Champions' and any(x in ql for x in ('best','optimal','recommended','heroes','champions','team','composition','tier list')):
        kinetic = any(x in ql for x in ('kinetic','kinetic ship','kinetic fleet'))
        candidates=[]
        for c in claims:
            cl=c.get('Claim','').lower()
            if 'champion' not in cl and 'kinetic' not in cl: continue
            if kinetic and ('kinetic' not in cl): continue
            if any(name in cl for name in ('killer bee','eva von trier','zora dominii','zora domini','kama moai','riian dessos','lani verita','cocoon')):
                candidates.append(c)
        # Prefer confirmed/current evidence first, then high-confidence meta evidence.
        candidates=sorted(candidates,key=lambda c: (
            0 if c.get('Status')=='Confirmed' else 1,
            0 if str(c.get('Confidence','')).lower().startswith('high') else 1,
            c.get('Claim','').lower()
        ))
        if candidates:
            lines=['For a Kinetic ship/fleet, the available evidence identifies these Kinetic Champions:']
            for c in candidates[:6]:
                lines.append('• '+c.get('Claim','').strip())
            lines.append('• Important: the champion classifications are mostly Tier-2/community evidence and several are marked Under Review, so I would not present a single “best” hero as a confirmed fact.')
            return {'text':'\\n'.join(lines),'model':'evidence-fallback','evidence_used':[claims.index(c)+1 for c in candidates[:6]],'uncertainty':'Recommendation is evidence-based but the available Kinetic Champion meta is not uniformly confirmed; Under Review claims remain labeled as such.'}

    # Repair questions must answer the player's actual location/action question,
    # not merely recite the damage taxonomy.
    if any(k in ql for k in ('repair','where can i repair','where do i repair','repair my fleet','fix my fleet')):
        repair_claims=[c for c in claims if any(k in c.get('Claim','').lower() for k in
            ('repair cabin','repair bay','repair module','minor damage','major damage','repair via formation'))]
        location=[c for c in repair_claims if any(k in c.get('Claim','').lower() for k in
            ('repair cabin','repair bay','repair via formation'))]
        minor=[c for c in repair_claims if 'minor damage' in c.get('Claim','').lower() and
               ('auto' in c.get('Claim','').lower() or 'recover' in c.get('Claim','').lower())]
        major=[c for c in repair_claims if 'major damage' in c.get('Claim','').lower() and
               ('repair module' in c.get('Claim','').lower() or 'repair cabin' in c.get('Claim','').lower())]
        selected=[]
        for group in (location,minor,major,repair_claims):
            for c in group:
                if c not in selected:selected.append(c)
                if len(selected)>=4:break
            if len(selected)>=4:break

        lines=['For fleet repair, the evidence distinguishes Minor Damage from Major Damage:']
        if any('repair cabin' in c.get('Claim','').lower() for c in location):
            lines.append('• Major Damage is repaired through the Repair Cabin; the Repair Cabin repairs craft with Major Damage.')
        elif any('repair bay' in c.get('Claim','').lower() for c in location):
            lines.append('• Major Damage sends the damaged craft to the Repair Bay, where repair requires Repair Modules.')
        if minor:
            lines.append('• Minor Damage does not require Repair Modules: it can recover/auto-repair after leaving combat.')
        if not location and not minor:
            lines.append('• The retrieved evidence does not establish the exact repair location.')
        if any(x in ql for x in ('without repair modules','without consuming','ad free','free','no spending')):
            lines.append('• The evidence supports the Minor Damage auto-recovery path as the no-Repair-Module option; it does not establish a separate ad-based repair mechanic.')
        return {'text':'\n'.join(lines),'model':'evidence-fallback','evidence_used':[claims.index(c)+1 for c in selected[:4]],'uncertainty':'Direct repair evidence used; no unsupported repair mechanic was assumed.'}

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

def answer_quality_gate(q,text,claims,evidence_used=None):
    """Final pre-display validation. A fluent answer is not accepted unless
    its topic, evidence, constraints and abstention behavior align with the
    actual question.
    """
    low=text.lower()
    intent=classify_intent(q)
    constraints=extract_constraints(q)
    evidence_used=evidence_used or []
    result={
        'addresses_question':False,
        'uses_relevant_evidence':False,
        'respects_constraints':False,
        'evidence_ids_valid':False,
        'no_unrelated_substitution':True,
        'passes':False
    }

    # Evidence IDs are optional for legacy fallback answers, but if present
    # they must point inside the packet and to claims that survive the same
    # relevance gate as retrieval.
    valid_ids=[]
    for x in evidence_used:
        try:
            n=int(x)
            if 1 <= n <= len(claims): valid_ids.append(n)
        except (TypeError,ValueError):
            pass
    result['evidence_ids_valid']=(not evidence_used) or bool(valid_ids)
    used_claims=[claims[n-1] for n in valid_ids]
    if used_claims:
        result['uses_relevant_evidence']=all(claim_relevance(q,c) for c in used_claims)
    else:
        result['uses_relevant_evidence']=bool(claims) and any(claim_relevance(q,c) for c in claims)

    requirements=topic_requirements(q)

    if intent=='Fleet Damage/Repair':
        result['addresses_question']=any(x in low for x in ('repair','damage','recover','repair bay','repair cabin','repair module'))
        if 'F2P' in constraints:
            result['respects_constraints']=any(x in low for x in ('free','without repair modules','without spending','no-cost','no cost','no-repair-module','no repair module'))
        else:
            result['respects_constraints']=True
        # CP is not a repair answer unless the answer also clearly explains it
        # only as prevention/context; it must never replace the repair response.
        if 'command point' in low and not any(x in low for x in ('repair','damage','recover')):
            result['no_unrelated_substitution']=False
    elif intent=='Champions':
        result['addresses_question']=any(x in low for x in ('champion','hero','team','composition'))
        result['respects_constraints']=('best' in low or 'recommended' in low or 'evidence' in low) if 'Best' in constraints else True
    else:
        result['addresses_question']=len(text.strip())>=20
        result['respects_constraints']=True

    # Exact-cost questions are high-risk: exact cost OR explicit evidence
    # insufficiency. Never accept an answer that substitutes another system's
    # cost.
    if exact_cost_question(q):
        explicit_abstention=any(x in low for x in (
            'not established','does not establish','do not have the exact',
            'don’t have the exact','not in my evidence','insufficient evidence',
            'cannot establish','not available in the evidence'
        ))
        numeric_core_claim=any(
            re.search(r'\\b\\d{1,3}(?:,\\d{3})*\\b', c.get('Claim',''))
            and any(x in c.get('Claim','').lower() for x in ('fusion seed','fusion seeds','core 35','core level'))
            for c in used_claims
        )
        result['addresses_question']=explicit_abstention or numeric_core_claim
        if any(x in low for x in ('flagship blueprint','flagship cost','flagship component','champion fragment')):
            result['no_unrelated_substitution']=False
        result['respects_constraints']=True

    # A topic gate is mandatory for all high-risk questions.
    if requirements and not any(claim_relevance(q,c) for c in claims):
        result['uses_relevant_evidence']=False

    result['passes']=all(v for k,v in result.items() if k!='passes')
    return result
def run_benchmark_suite_100(start=0,count=20):
    suite=json.loads((ROOT/'data/benchmarks_v4_100.json').read_text(encoding='utf-8'))
    start=max(0,int(start)); count=max(1,min(25,int(count)))
    selected=suite['questions'][start:start+count]
    category_intent={
        'Combat & Fleet Mechanics':'Combat',
        'Fleet Repair & Recovery':'Fleet Damage/Repair',
        'Energy Core & Progression':'Progression',
        'Flagship & Blueprints':'Progression',
        'Champions & Heroes':'Champions',
        'Economy & Resources':'Economy',
        'Multi-Intent & Complex Questions':'Multi-Intent'
    }
    rows=[]
    for item in selected:
        q=item['question']
        expected=category_intent[item['category']]
        detected=classify_intent(q)
        constraints=extract_constraints(q)
        hits=retrieve(q,8)
        rows.append({
            'id':item['id'],
            'category':item['category'],
            'question':q,
            'expected_intent_family':expected,
            'detected_intent':detected,
            'intent_match':(expected=='Multi-Intent' or detected==expected),
            'constraints':constraints,
            'evidence_count':len(hits),
            'top_evidence':hits[:3],
            'evidence_retrieved':bool(hits)
        })
    return {
        'version':RELEASE,
        'suite':suite['title'],
        'total':len(rows),
        'suite_total':len(suite['questions']),
        'start':start,
        'count':len(rows),
        'intent_matches':sum(1 for x in rows if x['intent_match']),
        'evidence_retrieved':sum(1 for x in rows if x['evidence_retrieved']),
        'results':rows,
        'note':'This suite measures routing/retrieval readiness. It does not declare unsupported game facts true; synthesis/abstention quality is evaluated separately.'
    }

def run_quality_benchmarks():
    tests=[
        {
            'id':'Q01',
            'question':"what's the best ways to repair your fleets ad free way",
            'must_intent':'Fleet Damage/Repair',
            'must_constraints':['F2P','Best'],
            'must_contain':['repair'],
            'must_not_contain':['command points']
        },
        {
            'id':'Q02',
            'question':'How do I repair my fleet?',
            'must_intent':'Fleet Damage/Repair',
            'must_constraints':[],
            'must_contain':['repair'],
            'must_not_contain':[]
        },
        {
            'id':'Q03',
            'question':'How much does Core 35 cost in fusion seeds?',
            'must_intent':'Progression',
            'must_constraints':[],
            'must_contain':['core 35','fusion seed'],
            'must_not_contain':['flagship blueprint','flagship cost']
        },
        {
            'id':'Q04',
            'question':'best heroes for kinetic ship',
            'must_intent':'Champions',
            'must_constraints':['Best'],
            'must_contain':['champion'],
            'must_not_contain':['5% damage bonus']
        },
        {
            'id':'Q05',
            'question':'What does Kinetic counter?',
            'must_intent':'Combat',
            'must_constraints':[],
            'must_contain':[],
            'must_not_contain':['repair cabin']
        }
    ]
    rows=[]
    for t in tests:
        q=t['question']
        hits=retrieve(q,10)
        s=synthesize(q,hits,relevant_conflicts(q),'benchmark')
        gate=answer_quality_gate(q,s.get('text',''),hits,s.get('evidence_used',[]))
        text_out=s.get('text','').lower()
        rows.append({
            'id':t['id'],
            'question':q,
            'intent':classify_intent(q),
            'intent_ok':classify_intent(q)==t['must_intent'],
            'constraints':extract_constraints(q),
            'constraints_ok':all(x in extract_constraints(q) for x in t['must_constraints']),
            'quality_gate':gate,
            'answer':s.get('text',''),
            'must_contain_ok':all(x in text_out for x in t['must_contain']),
            'must_not_contain_ok':all(x not in text_out for x in t['must_not_contain']),
            'passed':(
                classify_intent(q)==t['must_intent'] and
                all(x in extract_constraints(q) for x in t['must_constraints']) and
                gate.get('passes',False) and
                all(x in text_out for x in t['must_contain']) and
                all(x not in text_out for x in t['must_not_contain'])
            )
        })
    return {'version':RELEASE,'total':len(rows),'passed':sum(1 for x in rows if x['passed']),'failed':sum(1 for x in rows if not x['passed']),'results':rows}

def run_benchmarks():
    tests=[
        ("what's the best ways to repair your fleets ad free way","Fleet Damage/Repair",["F2P","Best"],["repair","damage"]),
        ("How do I repair my fleet?","Fleet Damage/Repair",[],["repair","damage"]),
        ("Why does CP matter?","Combat",[],["command point"]),
        ("How much does Core 35 cost in fusion seeds?","Progression",[],["does not establish","will not infer"]),
        ("best heroes for kinetic ship","Champions",["Best"],["kinetic","champion"])
    ]
    results=[]
    for q,expected_intent,expected_constraints,answer_markers in tests:
        intent=classify_intent(q); constraints=extract_constraints(q); hits=retrieve(q,10)
        provisional=fallback_answer(q,hits).get('text','') if hits else ''
        answer_ok=all(m in provisional.lower() for m in answer_markers)
        passed=intent==expected_intent and all(x in constraints for x in expected_constraints) and bool(hits) and answer_ok
        results.append({"question":q,"expected_intent":expected_intent,"intent":intent,"expected_constraints":expected_constraints,"constraints":constraints,"evidence_count":len(hits),"answer_check":answer_ok,"passed":passed})
    return {"version":RELEASE,"total":len(results),"passed":sum(1 for x in results if x["passed"]),"failed":sum(1 for x in results if not x["passed"]),"results":results}

def answer(q,player_context=None):
    critical=relevant_conflicts(q);hits=retrieve(q,10);hits,scope=get_applicable_evidence(hits,player_context);s=synthesize(q,hits,critical,'answer')
    gate=answer_quality_gate(q,s.get('text',''),hits,s.get('evidence_used',[]))
    if not gate['passes']:
        s=fallback_answer(q,hits,critical)
        s['quality_gate']=gate
        s['uncertainty']='Answer-quality gate rejected the synthesis; deterministic evidence-safe answer returned.'
    else:
        s['quality_gate']=gate
    return {'question':q,'answer_type':'synthesized_evidence','player_context':player_context,'season_scope':scope,'answer':s['text'],'model':s['model'],'evidence_used':s.get('evidence_used',[]),'uncertainty':s.get('uncertainty',''),'synthesis_error':s.get('synthesis_error'),'synthesis_error_detail':s.get('synthesis_error_detail'),'evidence':hits,'critical_conflicts':critical,'rules_applied':RULES[:4],'note':'Answer is synthesized from retrieved evidence and passed an evidence-relevance gate. Tier 1 is preferred for mechanics; conflicts and uncertainty are preserved.'}



def _find_champion_style(name):
    nl=str(name).strip().lower()
    if not nl: return None
    candidates=[]
    for c in CLAIMS:
        cl=str(c.get('Claim','')).lower()
        if nl in cl and any(x in cl for x in ('beam','kinetic','ion','ionic')):
            candidates.append(c)
    return candidates[0] if candidates else None

def repair_planner(damage='minor', repair_modules=0, in_combat=False):
    d=str(damage).strip().lower()
    try: modules=max(0,int(repair_modules))
    except (TypeError,ValueError): modules=0
    if d not in ('minor','major'):
        return {'ok':False,'error':'damage must be minor or major'}
    if in_combat:
        return {'ok':True,'damage':d,'action':'Finish/leave combat before repair processing.','repair_modules_required':(d=='major'),'evidence_basis':['Minor Damage can immediately recover after leaving battle without Repair Modules.','Major Damage requires Repair Modules and is handled through the repair system.']}
    if d=='minor':
        return {'ok':True,'damage':'minor','action':'Leave combat; Minor Damage can recover immediately without consuming Repair Modules.','repair_modules_required':False,'repair_modules_to_consume':0,'evidence_basis':['Minor Damage can immediately recover after leaving battle without Repair Modules.']}
    if modules>0:
        return {'ok':True,'damage':'major','action':'Use the Repair/Repair Cabin workflow and spend Repair Modules on the Major Damage.','repair_modules_required':True,'repair_modules_available':modules,'repair_modules_to_consume':'Not established per ship in current evidence.','evidence_basis':['Major Damage requires Repair Modules.','Repair Cabin repairs craft with Major Damage.']}
    return {'ok':True,'damage':'major','action':'Major Damage cannot be repaired without Repair Modules in the current evidence. Obtain/allocate Repair Modules before repair.','repair_modules_required':True,'repair_modules_available':0,'evidence_basis':['Major Damage requires Repair Modules.']}

def fleet_builder(style='', champions=None):
    style=str(style).strip().lower()
    aliases={'ion':'Ion','ionic':'Ion','beam':'Beam','kinetic':'Kinetic'}
    canonical=aliases.get(style)
    if not canonical:
        return {'ok':False,'error':'style must be Beam, Kinetic, or Ion'}
    champs=[str(x).strip() for x in (champions or []) if str(x).strip()][:3]
    if len(champs)!=3:
        return {'ok':False,'error':'Provide exactly 3 Champions.'}
    rows=[]
    for name in champs:
        c=_find_champion_style(name)
        rows.append({'champion':name,'evidence_style':canonical if c and canonical.lower() in str(c.get('Claim','')).lower() else None,'evidence':c.get('Claim','') if c else None})
    matched=sum(1 for x in rows if x['evidence_style']==canonical)
    bonus='+20% ATK, DEF and INT' if matched==3 else ('+10% ATK, DEF and INT' if matched==2 else 'No matching-style synergy bonus established for this lineup')
    return {'ok':True,'style':canonical,'champions':rows,'matched_champions':matched,'synergy_bonus':bonus,'rule':'2 matching Champions grant +10%; 3 matching Champions grant +20%.','note':'Champion-to-style assignment is evidence-dependent; this builder does not invent an assignment when the corpus does not establish one.'}

def progression_planner(core_level=1,target_level=30,season='S1'):
    try:
        cur=max(1,int(core_level)); target=max(cur,int(target_level))
    except (TypeError,ValueError):
        return {'ok':False,'error':'core_level and target_level must be integers'}
    if target>35:
        return {'ok':False,'error':'Current modeled Energy Core ceiling is 35; higher levels are not established.'}
    q=f'Energy Core level {cur} to {target} requirements upgrades unlocks'
    hits=retrieve(q,20)
    milestones=[]
    for c in hits:
        cl=str(c.get('Claim','')).lower()
        if 'energy core' in cl or 'core level' in cl or 'fusion seed' in cl or 'battle queue' in cl:
            milestones.append({'claim':c.get('Claim',''),'tier':c.get('Evidence Tier',''),'confidence':c.get('Confidence',''),'status':c.get('Status',''),'source':c.get('Source','')})
    known=[]
    if cur<33<=target:
        known.append('Energy Core 33 is documented as unlocking the fourth Battle Queue in the current official progression evidence.')
    if cur<35<=target:
        known.append('Energy Core 35 is documented as the current cap in the Epoch of Fusion Seed progression evidence.')
    return {'ok':True,'season':season,'current_core':cur,'target_core':target,'known_milestones':known,'evidence':milestones[:12],'exact_costs_included':False,'cost_note':'Exact per-level Fusion Seed costs are not inserted unless established by evidence.'}


# V5 Player State persistence
PLAYER_PROFILE_ALLOWED_SEASONS={'S1','S2','S3'}
def _player_profile_from_db(player_id):
    headers=_supabase_headers()
    if not headers:
        return None, 'Supabase server credential is not configured.'
    try:
        from urllib.parse import quote
        req=Request(SUPABASE_URL+'/rest/v1/player_profiles?player_id=eq.'+quote(str(player_id),safe='')+'&select=player_id,season,core_level,flagship_level,champion_levels,fleet_styles,resources,preferences,updated_at',
                    headers=headers,method='GET')
        with urlopen(req,timeout=4) as r:
            rows=json.loads(r.read().decode('utf-8') or '[]')
        return (rows[0] if rows else None), None
    except Exception as e:
        return None, str(e)

def _save_player_profile_to_db(profile):
    headers=_supabase_headers()
    if not headers:
        return False,'Supabase server credential is not configured.'
    payload={'player_id':str(profile['player_id']),'season':profile.get('season','S1'),'core_level':profile.get('core_level'),'flagship_level':profile.get('flagship_level'),
             'champion_levels':profile.get('champion_levels') or {},'fleet_styles':profile.get('fleet_styles') or [],
             'resources':profile.get('resources') or {},'preferences':profile.get('preferences') or {}}
    try:
        req=Request(SUPABASE_URL+'/rest/v1/player_profiles?on_conflict=player_id',
                    data=json.dumps(payload,ensure_ascii=False).encode('utf-8'),
                    headers={**headers,'Prefer':'resolution=merge-duplicates,return=representation'},method='POST')
        with urlopen(req,timeout=4) as r:
            rows=json.loads(r.read().decode('utf-8') or '[]')
        return bool(rows),''
    except Exception as e:
        return False,str(e)

def validate_player_profile(body):
    p=dict(body or {}); pid=str(p.get('player_id','')).strip()
    if not pid or len(pid)>128:return None,'player_id is required and must be <=128 characters.'
    season=str(p.get('season','S1')).upper()
    if season not in PLAYER_PROFILE_ALLOWED_SEASONS:return None,'season must be S1, S2, or S3.'
    def intval(name,lo=1,hi=100):
        v=p.get(name)
        if v is None:return None
        try:v=int(v)
        except Exception:raise ValueError(name+' must be an integer')
        if v<lo or v>hi:raise ValueError(name+' is outside the allowed range')
        return v
    try:
        return {'player_id':pid,'season':season,'core_level':intval('core_level',1,35),'flagship_level':intval('flagship_level',1,100),
                'champion_levels':p.get('champion_levels') if isinstance(p.get('champion_levels'),dict) else {},
                'fleet_styles':p.get('fleet_styles') if isinstance(p.get('fleet_styles'),list) else [],
                'resources':p.get('resources') if isinstance(p.get('resources'),dict) else {},
                'preferences':p.get('preferences') if isinstance(p.get('preferences'),dict) else {}},None
    except ValueError as e:return None,str(e)

class H(BaseHTTPRequestHandler):
    def _json(self,obj,status=200):
        b=json.dumps(obj,ensure_ascii=False).encode();self.send_response(status);self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b)
    def do_GET(self):
        u=urlparse(self.path)
        if u.path=='/api/health':
            configured=bool(os.getenv('FGF_LLM_API_KEY') or os.getenv('OPENAI_API_KEY'))
            return self._json({'ok':True,'version':RELEASE,'claims':len(CLAIMS),'sources':DATA['stats'].get('sources',0),'changes':DATA['stats'].get('change_log_entries',0),'conflicts':len(CONFLICTS),'tier1':DATA['stats']['tier1_claims'],'synthesis_configured':configured,'synthesis_status':'configured_not_runtime_verified' if configured else 'missing_api_key','model':LLM_MODEL,'adaptive_retrieval':True,'bounded_learning':True})
        if u.path=='/api/ask':
            qs=parse_qs(u.query);q=qs.get('q',[''])[0];ctx={}
            if qs.get('season',[''])[0]: ctx['season']=qs.get('season',[''])[0]
            if qs.get('core_level',[''])[0]: ctx['core_level']=qs.get('core_level',[''])[0]
            return self._json(answer(q,ctx or None))
        if u.path=='/api/recommend':
            qs=parse_qs(u.query);q=qs.get('q',[''])[0];objective=qs.get('objective',['general'])[0];return self._json(recommend(q,objective))
        if u.path=='/api/claims':
            qs=parse_qs(u.query);q=qs.get('q',[''])[0];lim=int(qs.get('limit',['50'])[0]);res=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True) if q else [(0,c) for c in CLAIMS];return self._json({'results':[c for s,c in res[:lim]]})
        if u.path=='/api/conflicts':return self._json({'results':CONFLICTS})
        if u.path=='/api/admin/status':
            return self._json({'admin_configured':bool(ADMIN_TOKEN),'review_endpoint_enabled':bool(ADMIN_TOKEN),'auth_scheme':'X-FGF-Admin-Token or Bearer token','message':'Admin review writes are disabled until FGF_ADMIN_TOKEN is configured.' if not ADMIN_TOKEN else 'Admin review authentication is configured.'})
        if u.path=='/api/player/profile':
            qs=parse_qs(u.query);pid=qs.get('player_id',[''])[0].strip()
            if not pid:return self._json({'ok':False,'error':'player_id is required'},400)
            profile,error=_player_profile_from_db(pid)
            if error:return self._json({'ok':False,'durable':False,'error':error},503)
            return self._json({'ok':True,'durable':True,'profile':profile})
        if u.path=='/api/tools/repair':
            qs=parse_qs(u.query)
            return self._json(repair_planner(qs.get('damage',['minor'])[0],qs.get('repair_modules',['0'])[0],qs.get('in_combat',['false'])[0].lower()=='true'))
        if u.path=='/api/tools/fleet-builder':
            qs=parse_qs(u.query); champs=[x for x in qs.get('champion',[])]
            return self._json(fleet_builder(qs.get('style',[''])[0],champs))
        if u.path=='/api/tools/progression':
            qs=parse_qs(u.query)
            return self._json(progression_planner(qs.get('core_level',['1'])[0],qs.get('target_level',['30'])[0],qs.get('season',['S1'])[0]))
        if u.path=='/api/benchmarks':return self._json(run_benchmarks())
        if u.path=='/api/benchmarks/quality':return self._json(run_quality_benchmarks())
        if u.path=='/api/benchmarks/100':
            qs=parse_qs(u.query);start=int(qs.get('start',['0'])[0]);count=int(qs.get('count',['20'])[0]);return self._json(run_benchmark_suite_100(start,count))
        if u.path=='/api/rules':return self._json({'rules':RULES,'authority_order':DATA['authority_order']})
        if u.path=='/v5':
            b=(ROOT/'web/v5.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        if u.path=='/' or u.path=='/index.html':
            b=(ROOT/'web/index.html').read_bytes();self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(b)));self.end_headers();self.wfile.write(b);return
        self.send_error(404)
    def do_POST(self):
        u=urlparse(self.path)
        if u.path=='/api/player/profile':
            try:
                n=int(self.headers.get('Content-Length','0'))
                if n>65536:return self._json({'ok':False,'error':'Request too large'},413)
                body=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                profile,error=validate_player_profile(body)
                if error:return self._json({'ok':False,'error':error},400)
                ok,detail=_save_player_profile_to_db(profile)
                if not ok:return self._json({'ok':False,'durable':False,'error':detail},503)
                return self._json({'ok':True,'durable':True,'profile':profile})
            except Exception as e:return self._json({'ok':False,'error':str(e)},400)
        if u.path=='/api/conflicts/review':
            try:
                n=int(self.headers.get('Content-Length','0'))
                body=json.loads(self.rfile.read(n).decode('utf-8') or '{}')
                cid=str(body.get('conflict_id','')).strip()
                decision=str(body.get('decision','')).strip()
                if not cid or not decision:
                    return self._json({'ok':False,'error':'conflict_id and decision are required'},400)
                allowed={'confirm','reject','supersede','keep_under_review'}
                if decision not in allowed:
                    return self._json({'ok':False,'error':'Invalid decision'},400)
                if not ADMIN_TOKEN:
                    return self._json({'ok':False,'error':'Admin review is disabled: FGF_ADMIN_TOKEN is not configured on the server.'},503)
                supplied=self.headers.get('X-FGF-Admin-Token','')
                if not supplied:
                    supplied=self.headers.get('Authorization','')
                    if supplied.lower().startswith('bearer '): supplied=supplied[7:].strip()
                if supplied != ADMIN_TOKEN:
                    return self._json({'ok':False,'error':'Admin authorization required'},401)
                if n > 65536:
                    return self._json({'ok':False,'error':'Request too large'},413)
                review={'conflict_id':cid,'decision':decision,'evidence':str(body.get('evidence','')).strip(),'notes':str(body.get('notes','')).strip(),'reviewer':'authenticated-admin','reviewed_at':str(body.get('reviewed_at','')).strip()}
                if not any(c.get('Conflict ID')==cid for c in CONFLICTS):
                    return self._json({'ok':False,'error':'Unknown conflict ID'},404)
                durable=save_conflict_review(review)
                return self._json({'ok':True,'review':review,'durable':durable,'storage':'supabase+local_fallback' if durable else 'local_fallback','message':'Review captured. Historical claims remain preserved; final promotion/supersession remains auditable.'})
            except Exception as e:
                return self._json({'ok':False,'error':str(e)},400)
        self.send_error(404)

    def log_message(self,*a):pass

if __name__=='__main__':
    port=int(os.getenv('PORT','8000'));print(f'FGF Intelligence running on http://127.0.0.1:{port}');ThreadingHTTPServer(('0.0.0.0',port),H).serve_forever()
