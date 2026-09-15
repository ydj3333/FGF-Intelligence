"""FGF bounded learning cycle.

Runs every 6 hours in CI. It discovers configured sources, records fresh
source observations and creates candidate evidence. It NEVER changes Tier 1
truth automatically. Admin approval is required for promotion.
"""
import json, os, re, hashlib, urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT/'data/learning_config.json').read_text())
STATE_PATH = ROOT/'data/learning_state.json'
STATE = json.loads(STATE_PATH.read_text())

NOW = datetime.now(timezone.utc)


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent':'FGF-Intelligence-Learning/1.0'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode('utf-8', 'replace')[:500000]


def normalize(text):
    return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', text)).strip()


def fingerprint(text):
    return hashlib.sha256(normalize(text).encode()).hexdigest()[:20]


def load_sources():
    path = ROOT/'data/sources.json'
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return data if isinstance(data, list) else data.get('sources', [])


def discover():
    observations=[]
    for src in load_sources():
        if not src.get('enabled', True) or not src.get('url'):
            continue
        try:
            raw=fetch(src['url'])
            text=normalize(raw)
            observations.append({
                'source_id':src.get('id'), 'name':src.get('name'),
                'type':src.get('type','search'), 'url':src['url'],
                'retrieved_utc':NOW.isoformat(), 'status':'retrieved',
                'fingerprint':fingerprint(text), 'content_excerpt':text[:3000]
            })
        except Exception as e:
            observations.append({'source_id':src.get('id'),'name':src.get('name'),
                                 'url':src['url'],'retrieved_utc':NOW.isoformat(),
                                 'status':'error','error':str(e)[:300]})
    return observations


def build_candidates(observations):
    # This stage records evidence for admin/claim extraction. It intentionally
    # does not convert arbitrary web prose into confirmed game mechanics.
    out=[]
    existing={x.get('fingerprint') for x in STATE.get('candidate_claims',[])}
    for o in observations:
        if o.get('status')!='retrieved': continue
        fp=o['fingerprint']
        if fp in existing: continue
        out.append({
            'candidate_id':'CAND-'+fp,
            'state':'Pending Admin Review',
            'proposed_tier':'Tier 2' if o.get('type')=='official' else 'Tier 3',
            'source':o.get('name'), 'url':o.get('url'),
            'retrieved_utc':o.get('retrieved_utc'),
            'evidence_excerpt':o.get('content_excerpt',''),
            'fingerprint':fp,
            'promotion_rule':'Requires explicit admin verification and proof.'
        })
    return out


def main():
    observations=discover()
    candidates=build_candidates(observations)
    STATE['last_refresh_utc']=NOW.isoformat()
    STATE['next_admin_review_utc']=(NOW+timedelta(days=CFG['admin_review_days'])).isoformat()
    STATE.setdefault('source_health',[]).extend(observations)
    STATE['source_health']=STATE['source_health'][-500:]
    STATE.setdefault('candidate_claims',[]).extend(candidates)
    STATE['candidate_claims']=STATE['candidate_claims'][-1000:]
    STATE_PATH.write_text(json.dumps(STATE,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'retrieved':len(observations),'new_candidates':len(candidates),'last_refresh_utc':STATE['last_refresh_utc']}))

if __name__=='__main__': main()
