import json,re,os,time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from gap_detector import GapDetector
from knowledge_analyzer import KnowledgeAnalyzer
from claim_lifecycle import summarize_states, normalize_state

ROOT=Path(__file__).parent
DATA=json.loads((ROOT/'data/knowledge.json').read_text(encoding='utf-8'))
RELEASE='v5.2.0-core-lifecycle'
CLAIMS=DATA['claims']; RULES=DATA['rules']; CONFLICTS=DATA['conflicts']
CONFLICT_REVIEWS_FILE=ROOT/'data'/'conflict_reviews.json'
SUPABASE_URL=os.getenv('FGF_SUPABASE_URL','https://qdoixzfkkmvzjfkhzups.supabase.co').rstrip('/')
SUPABASE_SECRET=os.getenv('FGF_SUPABASE_SECRET_KEY') or os.getenv('FGF_SUPABASE_SERVICE_ROLE_KEY') or os.getenv('SUPABASE_SERVICE_ROLE_KEY')
ADMIN_TOKEN=os.getenv('FGF_ADMIN_TOKEN')
SYNTHESIS_RUNTIME_STATUS='configured_not_runtime_verified' if (os.getenv('FGF_LLM_API_KEY') or os.getenv('OPENAI_API_KEY')) else 'missing_api_key'
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
 'event':['glory','hunting ground','killstreak','event','arms race','shared moonlight','shadow moonlight','moonlight battlepass','bingo bash','lunar soil','moonsoil','moonlit treasures','full moon charge-up','calendar','schedule','weekday','monday','tuesday','wednesday','thursday','friday','saturday','sunday']
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

def is_shared_moonlight_question(q):
    ql=q.lower()
    return any(x in ql for x in (
        'shared moonlight','shadow moonlight','moonlight event',
        'moonlight battlepass','moonsoil','lunar soil','moonlit treasures',
        'full moon charge-up','bingo bash'
    ))

def is_event_schedule_question(q):
    ql=q.lower()
    schedule_terms=('which day','what day','weekday','schedule','calendar','monday','tuesday',
                    'wednesday','thursday','friday','saturday','sunday','daily rotation',
                    'day-by-day','day by day','when is','what is on')
    return is_shared_moonlight_question(q) and any(x in ql for x in schedule_terms)

def shared_moonlight_schedule_claims(claims):
    out=[]
    for c in claims:
        text=(c.get('Claim','')+' '+c.get('Notes','')).lower()
        if 'shared moonlight' in text and any(x in text for x in ('september 15','september 21','calendar','server')):
            out.append(c)
    return out

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
    if is_shared_moonlight_question(q):
        req.append('shared_moonlight')
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
        elif req=='shared_moonlight':
            if not any(x in cl for x in ('shared moonlight','moonlight','moonsoil','lunar soil','moonlit treasures','bingo bash','full moon charge-up')):
                return False

    if domains:
        domain_match=any(term in cl for d in domains for term in DOMAIN_TERMS.get(d,[]))
        cat=c.get('Category','').lower()
        if not domain_match and not any(x in cat for x in domains):
            return False
    return True

def retrieve(q,limit=10,include_candidates=False):
    """Retrieve evidence with an explicit production-truth boundary.

    Normal answer retrieval uses CURRENT lifecycle claims only. Candidate/
    Under Review evidence is available only to explicit evidence/recommendation
    surfaces that can label it as unverified.
    """
    ranked=sorted(((score(q,c),c) for c in CLAIMS),key=lambda x:x[0],reverse=True)
    hits=[c for s,c in ranked
          if s>0.85
          and (include_candidates or normalize_state(c.get('Status')) == 'current')
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
    """Return static conflicts plus learned YouTube conflicts relevant to the question.

    Learned Tier-3 conflicts stay out of normal production retrieval, but when a
    question touches them they are surfaced alongside the current evidence and
    explicitly labeled as community/YouTube information requiring a latest-info
    check.
    """
    qt = tokens(q)
    out = list(CONFLICTS)
    seen = {str(x.get('Conflict ID', '')) + '|' + str(x.get('Claim', '')) for x in out}
    for x in CLAIMS:
        state = normalize_state(x.get('Status'))
        meta = x.get('metadata') if isinstance(x.get('metadata'), dict) else {}
        if state.value != 'conflicting' and meta.get('conflict_status') != 'held_back':
            continue
        text = str(x.get('Claim', ''))
        if not qt or qt & tokens(text + ' ' + str(x.get('Category', ''))):
            item = {
                'Conflict ID': 'YT-' + str(x.get('claim_key', x.get('supabase_id', ''))),
                'Claim': text,
                'Category': x.get('Category', ''),
                'Evidence Tier': x.get('Evidence Tier', 'Tier 3 — Creator/Community'),
                'Confidence': x.get('Confidence', ''),
                'Status': 'Conflicting',
                'Source': x.get('Source', meta.get('Source', 'YouTube')),
                'Notes': 'YouTube/community claim held back because it conflicts with existing higher-priority evidence. Check latest in-game/official information before relying on it.',
                'Community Evidence': True,
            }
            key = str(item.get('Conflict ID')) + '|' + text
            if key not in seen:
                out.append(item)
                seen.add(key)
    return out

