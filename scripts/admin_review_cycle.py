"""Build the admin's 21-day evidence review packet.

The report is decision-oriented: it surfaces only changes, conflicts, repeated
user evidence and source upgrades that need a human decision. No truth is
promoted by this script.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
state=json.loads((ROOT/'data/learning_state.json').read_text())
cfg=json.loads((ROOT/'data/learning_config.json').read_text())
now=datetime.now(timezone.utc)

lines=[
 '# FGF Intelligence — Admin Evidence Review',
 '', f'Generated: {now.isoformat()}',
 '',
 '## Decision rule',
 '- Tier 1 changes require explicit admin confirmation of the exact proposition and proof.',
 '- Do not overwrite older evidence; supersede it with a dated change record.',
 '- Unproven user/session inferences remain outside canonical truth.',
 '',
 '## Items requiring attention',
]

cands=state.get('candidate_claims',[])
conf=state.get('conflict_queue',[])
user=state.get('user_evidence_events',[])
for title,items in [('Candidate evidence',cands[-100:]),('Conflict queue',conf[-100:]),('Repeated user evidence',user[-100:])]:
    lines += [f'### {title}', '']
    if not items:
        lines.append('- None currently queued.')
    else:
        for x in items:
            lines.append(f"- **{x.get('candidate_id',x.get('id','item'))}** — {x.get('state','Pending')}; source={x.get('source',x.get('url','unknown'))}; proposed={x.get('proposed_tier','review')}")
            if x.get('evidence_excerpt'): lines.append(f"  - Proof: {x['evidence_excerpt'][:500]}")
    lines.append('')

lines += [
 '## Required admin outcomes',
 'For each item choose exactly one: CONFIRM → promote to the appropriate tier; REJECT → preserve as rejected evidence; SUPERSEDE → replace current claim while preserving history; KEEP UNDER REVIEW → no canonical change.',
 '',
 '## Review metadata',
 f"Configured review interval: {cfg['admin_review_days']} days.",
 f"Next scheduled review recorded by the learning state: {state.get('next_admin_review_utc')}",
]
(ROOT/'data/admin_review.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Admin review packet generated:', len(cands), 'candidates;', len(conf), 'conflicts;', len(user), 'user-evidence events')
