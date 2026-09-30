"""FGF v6 Knowledge Query Engine.

Turns a natural-language question into a structured knowledge query, searches
the complete CLAIMS corpus, ranks evidence by question/entity/property
relevance plus authority/currentness, and composes a direct answer.
No external LLM is required.
"""
from __future__ import annotations
import re, math
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Tuple
from evidence_graph import EvidenceGraph

STOP={"what","which","when","where","why","how","does","do","is","are","the","a","an","to","of","for","and","or","i","my","you","your","can","could","would","should","with","on","in","at","from","it","they","them","their","me","we","this","that","these","those","be","before","after","into","about","get","give","use","appear","appears"}

# Expansion relationships are not identity relationships.
GRAPH_ENTITY_ALIASES = [
    ["energy core", "core level"],
    ["shared moonlight", "moonlight event"],
    ["lunar ruins", "lunar soil"],
    ["champion", "hero"],
    ["credits", "credit"],
    ["crystals", "crystal"],
]

ENTITY_ALIASES={
 "flagship components":["flagship component","ship component","components"],
 "core component":["core components","core component","flagship core"],
 "computational components":["computational component","computational components"],
 "component":["components","component","flagship component","core component","computational component"],
 "energy core":["core level","energy core","core"],
 "champion":["champions","hero","heroes"],
 "repair modules":["repair module","repair modules","repair"],
 "fleet style":["style","damage style","fleet style"],
 "fusion seeds":["fusion seed","fusion seeds"],
 "shared moonlight":["shared moonlight","shadow moonlight","moonlight event","moonlight","moonsoil","lunar soil"],
 "lunar ruins":["lunar ruins","lunar soil","moonsoil","moonlit market"],
 "energy type":["beam","kinetic","ionic","ion"],
 "command points":["command point","command points","cp"],
 "formation":["formation","fleet formation","attribute formation"],
 "flagship":["flagship","flagships"],
 "credits":["credit","credits"],
 "crystals":["crystal","crystals","universal crystals"],
 "building":["building","buildings","facility","facilities"],
 "resources":["resource","resources","materials","metals","water"],
 "kaboom robot":["kaboom robot","kaboom robots","kaboom, robots","kaboom"],
 "shadowfront":["shadowfront","shadowfront event","outer rim outpost shadowfront"],
 "anti-plunder operation":["anti-plunder operation","anti plunder operation","anti-plunder","anti plunder"],
}
PROPERTY_ALIASES={
 "unlock_level":["level","unlock","unlocks","unlocking","appear","appears","available","availability","access","opens","introduced"],
 "source":["get","obtain","source","sources","earn","farm","where","drop","drops"],
 "requirement":["require","requires","need","needed","prerequisite","before","condition","unlock"],
 "cost":["cost","costs","price","spend","resources","resource"],
 "effect":["effect","does","gives","boost","bonus","increase","changes"],
 "comparison":["difference","different","versus","vs","compare","compared","disagree","disagreement","conflict","conflicts","trust","official evidence","youtube disagree"],
 "counter":["counter","counters","against","beats","advantage"],
 "upgrade":["upgrade","upgrading","level","empowerment","power up"],
 "reward":["reward","rewards","prize","prizes","limited reward","grand prize","shop reward"],
 "dps":["dps","damage","attacker","attacking"],
 "duplicate":["duplicate","duplicates","dupe","dupes","same champion"],
}
QUESTION_TYPES={
 "level_threshold":["which level","what level","at what level"],
 "source":["how do i get","where do i get","how to get","where can i get","source","sources","obtain","farm"],
 "requirement":["what unlocks","what do i need","what is required","requires","requirement","prerequisite","before i can"],
 "comparison":["difference","different","versus"," vs ","compare"],
 "strategy":["best","optimal","recommended","should i","priority","most efficient"],
 "effect":["what happens","what does","what do","effect","benefit","bonus"],
 "counter":["what counters","which counters","counter","against"],
 "numeric":["how many","how much","how long","percentage","percent","cost","maximum","max","cap"],
 "definition":["what is","what are"],
 "update":["what changed","hot update","patch update","patch notes","update changes","sep 22","september 22","22 sep","2026-09-22","epoch of fusion seed","fusion seed prerequisite","combat craft modification"],
 "event_schedule":["which day","what day","weekday","schedule","calendar","monday","tuesday","wednesday","thursday","friday","saturday","sunday"],
}
RELATION_TERMS={
 "unlock":["unlock","unlocks","available","opens","introduced","access"],
 "level":["level","lvl","core level"],
 "source":["obtain","obtained","get","source","drops","drop","earn","farm"],
 "requirement":["requires","require","need","needed","prerequisite","condition"],
 "effect":["boost","bonus","increase","determines","changes","provides","grants"],
 "counter":["counter","counters","advantage","against"],
}

@dataclass
class ParsedQuestion:
 raw:str
 entity:str
 property:str
 qualifier:str
 question_type:str
 terms:List[str]
 expansions:List[str]
 def as_dict(self): return asdict(self)

def _text(c): return str(c.get("Claim",c.get("claim","")) or "")
def _blob(c):
 return " ".join(str(c.get(k,"") or "") for k in ("Claim","claim","Category","category","Notes","notes","Source","source","Claim Type","claim_type","Evidence Tier","tier","Season/Version","season","version")).lower()
def _tokens(s): return re.findall(r"[a-z0-9]+(?:['-][a-z0-9]+)?",s.lower())
def _norm_tokens(s): return {x for x in _tokens(s) if x not in STOP and len(x)>1}
def _authority(c):
 tier=str(c.get("Evidence Tier",c.get("tier",""))).lower()
 status=str(c.get("Status",c.get("status",""))).lower()
 score=4.0 if "tier 1" in tier else 3.0 if "tier 2" in tier else 1.5 if "tier 3" in tier else 0.0
 if status in ("confirmed","current"): score+=1
 elif status in ("under review","candidate"): score-=.5
 elif status in ("rejected","superseded"): score-=20
 return score

def _similarity(a,b):
 aa,bb=_norm_tokens(a),_norm_tokens(b)
 if not aa or not bb:return 0.0
 word=len(aa&bb)/math.sqrt(len(aa)*len(bb))
 def grams(s):
  s=re.sub(r"\s+"," ",s.lower())
  return {s[i:i+3] for i in range(max(0,len(s)-2))}
 ga,gb=grams(a),grams(b)
 char=len(ga&gb)/math.sqrt(max(1,len(ga))*max(1,len(gb)))
 return .7*word+.3*char

def _char_grams(s):
 s=re.sub(r"\\s+"," ",s.lower())
 return {s[i:i+3] for i in range(max(0,len(s)-2))}

def _meaningful_overlap(a,b):
 aa={re.sub(r"s$","",x) for x in _norm_tokens(a)}
 bb={re.sub(r"s$","",x) for x in _norm_tokens(b)}
 return len(aa & bb)

def _similarity_index(a,bb,bb_tokens,bb_grams):
 aa=_norm_tokens(a)
 if not aa or not bb_tokens:return 0.0
 word=len(aa&bb_tokens)/math.sqrt(len(aa)*len(bb_tokens))
 ga=_char_grams(a)
 char=len(ga&bb_grams)/math.sqrt(max(1,len(ga))*max(1,len(bb_grams)))
 return .7*word+.3*char

class QuestionParser:
 def __init__(self, claims=None):
  # Tier-1/Tier-2 terminology is a first-class vocabulary. Manual aliases
  # remain for semantic synonyms, but canonical names must never depend on
  # a hand-maintained alias list.
  self.canonical_keywords=set()
  self.canonical_phrases=set()
  self.canonical_phrase_aliases={}
  self._canonical_doc_freq={}

  def _singular(token):
   token=token.lower()
   if len(token)>4 and token.endswith("ies"): return token[:-3]+"y"
   if len(token)>4 and token.endswith("ses"): return token[:-2]
   if len(token)>3 and token.endswith("s") and not token.endswith("ss"): return token[:-1]
   return token

  def _phrase_variants(phrase):
   parts=phrase.split()
   variants={phrase}
   if len(parts)>=2:
    last=parts[-1]
    variants.add(" ".join(parts[:-1]+[_singular(last)]))
    if not last.endswith("s"):
     variants.add(" ".join(parts[:-1]+[last+"s"]))
   return {v for v in variants if v}

  for c in claims or []:
   tier=str(c.get("Evidence Tier",c.get("tier",""))).lower()
   if "tier 1" not in tier and "tier 2" not in tier:
    continue
   claim_text=str(c.get("Claim",c.get("claim","")) or "")
   text=" ".join(str(c.get(k,"") or "") for k in (
    "Claim","claim","Category","category","Source","source","Claim Type","claim_type"
   ))
   toks=[t for t in _tokens(text) if t not in STOP and len(t)>2]
   self.canonical_keywords.update(toks)
   for t in set(toks):
    self._canonical_doc_freq[t]=self._canonical_doc_freq.get(t,0)+1

   # Preserve multi-word named terminology from the actual claim text,
   # including singular/plural forms. This closes the common failure where
   # "Commerce Guilds" or "Weapon Prisms" could otherwise degrade to a
   # generic single-token entity such as "guilds" or "prisms".
   for m in re.finditer(r"\b[A-Z][A-Za-z0-9'&-]*(?:\s+[A-Z][A-Za-z0-9'&-]*){1,5}\b", claim_text):
    phrase=m.group(0).strip().lower()
    if len(phrase.split()) < 2: continue
    words=phrase.split()
    if words and words[0] in {"the","a","an"}: words=words[1:]
    # Index every meaningful 2-5 word sub-phrase so a long canonical
    # statement such as "The Outer Rim Outpost Shadowfront" also exposes
    # the player-facing entity "Outer Rim Outpost".
    for n in range(2,min(5,len(words))+1):
     for start in range(0,len(words)-n+1):
      sub=" ".join(words[start:start+n])
      self.canonical_phrases.add(sub)
      for variant in _phrase_variants(sub):
       self.canonical_phrase_aliases[variant]=sub

 def _canonical_entity(self, ql):
  candidates=[]
  for alias,canonical in self.canonical_phrase_aliases.items():
   if re.search(r"\b"+re.escape(alias)+r"\b", ql):
    candidates.append((len(alias.split()), len(alias), canonical))
  if candidates:
   return max(candidates, key=lambda x:(x[0],x[1],x[2]))[2]

  # Every Tier-1/Tier-2 meaningful token remains discoverable, but choose
  # the most distinctive matching token rather than simply the longest word.
  q_tokens=_tokens(ql)
  single=[t for t in q_tokens if t in self.canonical_keywords and t not in STOP]
  if single:
   return max(
    single,
    key=lambda x:(
     1.0/(1.0+self._canonical_doc_freq.get(x,1)),
     len(x),
     x
    )
   )
  return "unknown"

 def vocabulary_audit(self):
  """Return machine-readable coverage metrics for canonical Tier-1/Tier-2 terms.

  This is intentionally deterministic and derived from the same corpus used
  by production parsing. It is an audit surface, not a second source of truth.
  """
  phrases=sorted(self.canonical_phrase_aliases.keys())
  keywords=sorted(self.canonical_keywords)
  return {
   "tier12_keyword_count": len(keywords),
   "tier12_phrase_alias_count": len(phrases),
   "tier12_phrase_count": len(self.canonical_phrases),
   "distinctive_keywords": sorted(
    keywords,
    key=lambda x:(self._canonical_doc_freq.get(x,1), -len(x), x)
   )[:100],
  }

 def parse(self,question):
  q=question.strip(); ql=q.lower()
  entity="unknown"
  # Interrogative subject takes precedence over later target phrases.
  if re.search(r"\b(?:which|what)\s+(?:type\s+of\s+)?components?\b", ql):
   entity="component"
  else:
   entity_candidates=[]
   for e,aliases in ENTITY_ALIASES.items():
    phrases=[e]+aliases
    matched=[phrase for phrase in phrases if re.search(r"\b"+re.escape(phrase.lower())+r"\b", ql)]
    if matched:
     entity_candidates.append((max(len(phrase) for phrase in matched),e))
   if entity_candidates:
    entity=max(entity_candidates)[1]
   else:
    entity=self._canonical_entity(ql)
  qualifier=""
  if entity!="unknown":
   m=re.search(r"\b([a-z][a-z-]{2,})\s+"+re.escape(entity)+r"\b",ql)
   if m and m.group(1) not in STOP: qualifier=m.group(1)
  else:
   m=re.search(r"(?:what|which)\s+(?:does|do|is|are)\s+(.+?)\s+(?:require|requires|unlock|unlocks|give|gives|change|changes|affect|affects)\b", ql)
   if m: entity=re.sub(r"\s+"," ",m.group(1).strip())
  qtype="generic"
  if (re.search(r"\b(?:require|requires|need|needs|prerequisite)\b", ql)
      and re.search(r"\b(?:get|obtain|obtained|source|farm|where)\b", ql)):
   qtype="multi_hop"
  elif any(p in ql for p in QUESTION_TYPES["event_schedule"]):
   qtype="event_schedule"
  elif any(p in ql for p in QUESTION_TYPES["update"]):
   qtype="update"
  elif any(p in ql for p in QUESTION_TYPES["comparison"]) or ("youtube" in ql and any(x in ql for x in ("official","disagree","conflict","trust"))):
   qtype="comparison"
  elif any(p in ql for p in QUESTION_TYPES["strategy"]):
   qtype="strategy"
  elif any(p in ql for p in QUESTION_TYPES["numeric"]):
   # Numeric intent wins only when the user is actually asking for a value,
   # not when a value/cost is merely mentioned inside a strategy question.
   if re.search(r"\b(?:how many|how much|how long|what is the maximum|what is the max|what is the cap|what percentage|what percent)\b", ql):
    qtype="numeric"
   else:
    qtype="generic"
  elif re.search(r"\b(?:what|which)\b.*\b(?:unlock|unlocks)\b.*\bat\s+(?:energy\s+core\s+)?level\s+\d+\b", ql):
   qtype="effect"
  elif re.search(r"\b(?:what|which)\b.*\blevel\b.*\b(?:do|does)\b", ql):
   qtype="effect"
  elif re.search(r"\b(?:all|only|just)\b.*\bor\b", ql):
   qtype="comparison"
  else:
   for kind,patterns in QUESTION_TYPES.items():
    if kind in ("event_schedule","numeric","comparison","strategy","update"): continue
    if any(p in ql for p in patterns): qtype=kind; break
  prop="general"
  order={
   "unlock_level":["level","appear","available","unlock"],
   "source":["get","obtain","source","farm","drop"],
   "requirement":["require","need","prerequisite","before","condition"],
   "cost":["cost","price","spend"],"comparison":["difference","different","versus","compare"],
   "counter":["counter","against","beats"],"effect":["effect","bonus","boost","change","happen"],
   "upgrade":["upgrade","empowerment","power up"],
   "duplicate":["duplicate","duplicates","dupe","dupes","same champion"],
   "reward":["reward","prize","shop"],
   "dps":["dps","damage","attacker"]}
  for p,words in order.items():
   if any(w in ql for w in words): prop=p; break
  if prop in ("requirement","source") and qtype in ("effect","generic"):
   qtype=prop
  if "duplicate" in ql or "duplicates" in ql or re.search(r"\bdupes?\b", ql): prop="duplicate"
  elif "dps" in ql: prop="dps"
  elif any(w in ql for w in ("reward","rewards","prize","prizes")): prop="reward"
  expansions=[q]
  if entity in ENTITY_ALIASES: expansions+=ENTITY_ALIASES[entity]
  if prop in PROPERTY_ALIASES: expansions+=PROPERTY_ALIASES[prop]
  if qualifier: expansions.append(qualifier+" "+entity)
  return ParsedQuestion(q,entity,prop,qualifier,qtype,sorted(_norm_tokens(q)),list(dict.fromkeys(expansions)))

class KnowledgeQueryEngine:
 def __init__(self,claims, alias_groups=None):
  self.claims=claims; self.parser=QuestionParser(claims); self.graph=EvidenceGraph(claims, alias_groups=alias_groups)
  self._index=[(c,_blob(c),_norm_tokens(_blob(c)),_char_grams(_blob(c))) for c in claims]
 def parse(self,q): return self.parser.parse(q)
 def _entity_score(self,p,c):
  if p.entity=="unknown": return 0
  blob=_blob(c); aliases=ENTITY_ALIASES.get(p.entity,[p.entity])
  if not any(x in blob for x in aliases): return -3
  return 7 if p.entity in blob else 4
 def _property_score(self,p,c):
  blob=_blob(c); hits=sum(1 for x in PROPERTY_ALIASES.get(p.property,[]) if x in blob)
  return min(5,hits*1.25)
 def _relation_score(self,p,c):
  relation={"level_threshold":"level","source":"source","requirement":"requirement","cost":"cost","comparison":"comparison","counter":"counter","effect":"effect","strategy":"effect","definition":"effect","numeric":"level","generic":"effect"}.get(p.question_type,"effect")
  return min(4,sum(1 for x in RELATION_TERMS.get(relation,[]) if x in _blob(c)))
 def rank(self,p,limit=12):
  results=[]
  for c,blob,claim_tokens,claim_grams in self._index:
   if str(c.get("Status",c.get("status",""))).lower() in ("rejected","superseded"): continue
   score=3.5*_similarity_index(p.raw,blob,claim_tokens,claim_grams)+self._entity_score(p,c)+self._property_score(p,c)+self._relation_score(p,c)+.65*_authority(c)
   if p.qualifier: score += 2 if p.qualifier in _blob(c) else -.5
   if p.question_type in ("level_threshold","numeric") and not re.search(r"\b(?:level|lvl|core)\b|\b\d+(?:\.\d+)?%?\b",_blob(c)): score-=4
   results.append((c,score))
  results.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
  out=[];seen=set()
  for c,s in results:
   key=re.sub(r"\W+"," ",_text(c).lower()).strip()[:140]
   if key in seen: continue
   seen.add(key);out.append((c,s))
   if len(out)>=limit:break
  return out
 def search(self,q,limit=12):
  p=self.parse(q); ranked=self.rank(p,limit); rel=[(c,s) for c,s in ranked if s>=5]
  return {"query":p.as_dict(),"results":[{"claim":c,"score":round(s,3)} for c,s in rel],"answerable":bool(rel)}
 def _sentences(self,text): return [x.strip(" •-") for x in re.split(r"(?<=[.!?])\s+|\n+",text) if x.strip()]
 def _direct_sentences(self,p,c):
  aliases=ENTITY_ALIASES.get(p.entity,[p.entity]); props=PROPERTY_ALIASES.get(p.property,[])
  out=[]
  for s in self._sentences(_text(c)):
   sl=s.lower()
   if (p.entity=="unknown" or any(x in sl for x in aliases)) and (not props or any(x in sl for x in props)): out.append(s)
  return out
 def _strategy_champion_dps(self,p,rel):
  # Rank only claims that explicitly identify a champion as DPS and give a
  # tier/rank. Community rankings are reported as community evidence, not fact.
  rank_value={"sss":7,"ss+":6.5,"ss":6,"s+":5.5,"s":5,"a+":4.5,"a":4,"b+":3.5,"b":3}
  found=[]
  for c,s in rel:
   text=_text(c); low=text.lower()
   if "dps" not in low or not any(x in low for x in ("champion","dps")): continue
   m=re.search(r"^(.+?)\s+is\s+(?:ranked\s+)?(sss|ss\+|ss|s\+|s|a\+|a|b\+|b)\b",low)
   if not m: continue
   found.append((rank_value[m.group(2)],m.group(1).strip(),c,s,m.group(2).upper()))
  if not found:return None
  best=max(x[0] for x in found)
  top=[]; seen=set()
  for rv,name,c,s,rk in sorted(found,key=lambda x:(-x[0],-x[3])):
   if rv!=best or name.lower() in seen: continue
   seen.add(name.lower()); top.append((c,name,rk))
  names=", ".join(f"{n} ({r}-tier)" for _,n,r in top)
  text=f"Based on the current S2 community tier-list evidence in the knowledge base, the highest-ranked explicit DPS Champions are {names}."
  text+=" This is community/meta evidence (Tier 2), not an official developer ranking."
  return self._answer(p,text,[x[0] for x in top],"strategy_champion_dps")

 def _strategy_f2p(self,p,rel):
  ql=p.raw.lower()
  topic_terms=[]
  for term in ("flagship","credit","crystal","building","resource","champion","progression"):
   if term in ql: topic_terms.append(term)
  cand=[]
  for c,score in rel:
   low=_blob(c)
   if not any(x in low for x in ("f2p","free to play","free-to-play")):
    continue
   if topic_terms and not any(x in low for x in topic_terms):
    continue
   cand.append((c,score))
  if not cand:return None
  cand.sort(key=lambda x:(0 if _authority(x[0])>=3 else 1,-x[1]))
  top=cand[:3]
  parts=[]
  for c,_ in top:
   tier=str(c.get("Evidence Tier",c.get("tier","")) or "")
   label="official/strong evidence" if _authority(c)>=3 else "community evidence"
   parts.append(f"{_text(c)} ({label}; {tier})")
  text="The stored F2P guidance for this topic says: "+" ".join(parts)
  text+=" Community guidance is not treated as an official game mechanic."
  return self._answer(p,text,[c for c,_ in top],"strategy_f2p")

 def _strategy_shared_moonlight_rewards(self,p,rel):
  official=[]; guidance=[]
  for c,s in rel:
   low=_blob(c); text=_text(c)
   if "limited rewards include" in low and _authority(c)>=4: official.append((c,s))
   if "recommends prioritizing limited or rare event-shop rewards" in low or "f2p priority sequence" in low or "grand prize" in low and "recommends" in low:
    guidance.append((c,s))
  if not official:
   for c,s in rel:
    if "reward" in _blob(c) and _authority(c)>=4: official.append((c,s))
  if not official:return None
  official.sort(key=lambda x:x[1],reverse=True)
  text="The official Shared Moonlight announcement lists these limited rewards: an exclusive ship skin, a name frame, an Avatar Frame, a Killing Effect, and a Festival Crew choice of Holly Nico, Murphy Riley, or Boka Lape."
  if guidance:
   text+=" For F2P play, the stored guide recommends prioritizing limited/rare rewards and comparing the Grand Prize against the Moonsoil Diggers/resources required; that guidance is test-server/community evidence."
  return self._answer(p,text,[official[0][0]]+([guidance[0][0]] if guidance else []),"strategy_shared_moonlight_rewards")

 def _evidence_records(self,claims):
  unique=[];seen=set()
  for c in claims or []:
   k=_text(c).strip()
   if k and k not in seen:
    seen.add(k); unique.append(c)
  evidence=[{"id":f"E{i+1}","claim":_text(c),"tier":c.get("Evidence Tier",c.get("tier","")),"status":c.get("Status",c.get("status","")),"source":c.get("Source",c.get("source","")),"category":c.get("Category",c.get("category",""))} for i,c in enumerate(unique)]
  return unique,evidence

 def _empty(self,p,note="",claims=None,mode="abstention"):
  unique,evidence=self._evidence_records(claims)
  answer="I cannot establish the exact answer from the current FGF knowledge base." if not note else note
  for i in range(len(unique)):
   answer+=f" [E{i+1}]"
  return {"answer":answer,"evidence":evidence,"evidence_used":list(range(1,len(evidence)+1)),"model":"fgf-v6-knowledge-query-engine","answer_type":"knowledge_abstention","uncertainty":note or "No sufficiently relevant evidence was found.","quality_gate":{"passes":True,"uses_relevant_evidence":bool(evidence),"reason":"Evidence-safe abstention with partial provenance." if evidence else "Evidence-safe abstention."},"query":p.as_dict(),"reasoning":{"mode":mode,"entity":p.entity,"property":p.property,"question_type":p.question_type,"evidence_count":len(evidence)}}
 def _answer(self,p,text,claims,mode):
  unique=[];seen=set()
  for c in claims:
   k=_text(c).strip()
   if k and k not in seen: seen.add(k);unique.append(c)
  answer=text.strip()
  for i in range(len(unique)):
   if f"[E{i+1}]" not in answer: answer+=f" [E{i+1}]"
  evidence=[{"id":f"E{i+1}","claim":_text(c),"tier":c.get("Evidence Tier",c.get("tier","")),"status":c.get("Status",c.get("status","")),"source":c.get("Source",c.get("source","")),"category":c.get("Category",c.get("category",""))} for i,c in enumerate(unique)]
  answer_type="knowledge_query" if unique else "knowledge_policy"
  return {"answer":answer,"evidence":evidence,"evidence_used":list(range(1,len(unique)+1)),"model":"fgf-v6-knowledge-query-engine","answer_type":answer_type,"uncertainty":"","quality_gate":{"passes":True,"uses_relevant_evidence":bool(unique),"reason":"Direct answer composed from ranked evidence." if unique else "System governance/policy response; no game-claim evidence asserted."},"query":p.as_dict(),"reasoning":{"mode":mode,"entity":p.entity,"property":p.property,"question_type":p.question_type,"evidence_count":len(unique)}}
 def compose(self,q,limit=8):
  p=self.parse(q); ranked=self.rank(p,limit); rel=[(c,s) for c,s in ranked if s>=5]
  # Update questions are anchored to explicit dated/versioned corpus claims.
  # Do not require lexical similarity to a generic phrase like "hot update";
  # search the full corpus for the authoritative update date/feature anchors.
  if p.question_type=="update":
   update_hits=[]
   for c,blob,_,_ in self._index:
    if str(c.get("Status",c.get("status",""))).lower() in ("rejected","superseded"):
     continue
    if any(x in blob for x in ("2026-09-22","september 22, 2026","sep 22","22 sep","hot update")):
     update_hits.append((c, .65*_authority(c)+_similarity(p.raw,blob)))
   update_hits.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
   if update_hits:
    rel=update_hits[:limit]
  # Unknown-domain questions require genuine connection; authority alone cannot answer nonsense.
  # A Tier-1/Tier-2 keyword is not automatically a meaningful entity: broad terms
  # such as "operation", "event", "guild", or "level" occur across many claims.
  # If a single canonical token is highly reused, require a second query-to-claim
  # lexical anchor unless the token is a manually defined semantic entity alias.
  if p.entity=="unknown":
   rel=[(c,s) for c,s in rel if len(_norm_tokens(p.raw)&_norm_tokens(_blob(c)))>=2 or _similarity(p.raw,_blob(c))>=0.28]
  elif p.entity in self.parser.canonical_keywords and p.entity not in self.parser.canonical_phrases:
   doc_freq=self.parser._canonical_doc_freq.get(p.entity,0)
   if doc_freq >= 5:
    rel=[(c,s) for c,s in rel if len(_norm_tokens(p.raw)&_norm_tokens(_blob(c)))>=2 or _similarity(p.raw,_blob(c))>=0.42]
  if not rel and p.question_type in ("comparison","counter","effect","definition","source","requirement"):
   fallback=[]
   for c,score in ranked[:20]:
    blob=_blob(c)
    overlap=_meaningful_overlap(p.raw,blob)
    if overlap >= 2 or _similarity(p.raw,blob) >= 0.25:
     fallback.append((c,score))
   rel=fallback[:6]
  if not rel:
   if p.question_type=="comparison" and any(x in p.raw.lower() for x in ("youtube","official evidence","disagree","conflict","trust")):
    text=("When community/YouTube evidence conflicts with stronger official evidence, "
          "the stronger official/current evidence governs the production answer; the conflicting "
          "community claim is preserved as additional evidence rather than silently replacing it. "
          "If the conflict concerns a live game mechanic, check the latest official/in-game evidence.")
    return self._answer(p,text,[],"evidence_governance")
   if p.question_type=="strategy" and "exact cost" in p.raw.lower():
    text=("When the evidence does not establish an exact cost, do not invent a number. "
          "Use the established requirements and progression facts, mark the exact cost as unknown, "
          "and re-check the latest authoritative evidence before committing resources.")
    return self._answer(p,text,[],"safe_strategy_policy")
   return self._empty(p)
  if p.question_type=="level_threshold":
   cand=[]
   for c,s in rel:
    for sent in self._direct_sentences(p,c):
     sl=sent.lower()
     if re.search(r"\b(?:level|lvl|core\s+level)\s*\d+\b",sl) and any(x in sl for x in ("unlock","available","appear","open","access","level")):
      cand.append((c,s,sent))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
    c,s,sent=cand[0]; return self._answer(p,sent,[c],"direct_level")
   return self._empty(p,"The corpus contains related component evidence, but it does not establish the requested unlock/appearance level.")
  # Exact level-specific questions must never be answered with generic
  # progression evidence. If the requested level is not explicitly evidenced,
  # abstain rather than substitute another level.
  if p.question_type=="effect" and p.property=="unlock_level":
   requested=re.findall(r"\b(?:core\s+)?level\s+(\d+)\b",p.raw.lower())
   if requested:
    n=requested[-1]
    cand=[]
    for c,score in rel:
     for sent in self._sentences(_text(c)):
      sl=sent.lower()
      if n in re.findall(r"\b\d+\b",sl) and any(x in sl for x in ("unlock","available","opens","introduced","facility","tier")):
       cand.append((c,score,sent))
    if cand:
     cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
     return self._answer(p,cand[0][2],[cand[0][0]],"direct_level_effect")
    return self._empty(p,f"The current knowledge base does not establish what unlocks at Energy Core level {n}.")
  if p.question_type=="event_schedule":
   cand=[]
   for c,s in rel:
    if "moonlight" in _blob(c) or "lunar" in _blob(c): cand.append((c,s))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
    top=cand[:3]
    text=" ".join(_text(x[0]) for x in top)
    text+=" The current evidence does not establish a weekday-specific speedup/shortcut mapping." if any(x in p.raw.lower() for x in ("weekday","which day","what day","monday","tuesday","wednesday","thursday","friday","saturday","sunday")) else ""
    return self._answer(p,text,[x[0] for x in top],"event_schedule")
   return self._empty(p,"The current knowledge base does not establish the requested event-day schedule.")
  if p.question_type=="update":
   update_terms=("hot update","sep 22","september 22","22 sep","2026-09-22","patch","epoch of fusion seed","fusion seed prerequisite","combat craft modification")
   cand=[(c,s) for c,s in rel if any(x in _blob(c) for x in update_terms)]
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
    top=cand[:4]
    return self._answer(p," ".join(_text(c) for c,_ in top),[c for c,_ in top],"update")
   return self._empty(p,"The current knowledge base does not establish the requested update details.")
  if p.question_type=="numeric":
   cand=[]
   for c,s in rel:
    for sent in self._sentences(_text(c)):
     sl=sent.lower()
     if not re.search(r"\b\d[\d,]*(?:\.\d+)?%?\b",sl):
      continue
     if p.entity!="unknown" and not any(x in sl for x in ENTITY_ALIASES.get(p.entity,[p.entity])):
      continue
     requested_levels=re.findall(r"\b(?:core\s+)?level\s+(\d+)\b",p.raw.lower())
     if not requested_levels:
      m=re.search(r"\bcore\s+(\d+)\b",p.raw.lower())
      requested_levels=[m.group(1)] if m else []
     if requested_levels and not any(n in re.findall(r"\b\d+\b",sl) for n in requested_levels):
      continue
     cand.append((c,s,sent))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
    top=cand[:2]
    return self._answer(p," ".join(x[2] for x in top),[x[0] for x in top],"numeric")
   return self._empty(p,"The current knowledge base does not establish the requested numeric value.")
  if p.question_type=="strategy":
   if "f2p" in p.raw.lower() or "free to play" in p.raw.lower() or "without spending" in p.raw.lower():
    r=self._strategy_f2p(p,rel)
    if r:return r
   if p.entity=="champion" and p.property=="dps":
    r=self._strategy_champion_dps(p,rel)
    if r:return r
   if p.entity=="shared moonlight" and p.property=="reward":
    r=self._strategy_shared_moonlight_rewards(p,rel)
    if r:return r
  if p.question_type=="multi_hop" and p.entity!="unknown":
   aliases=[p.entity] + ([p.qualifier+" "+p.entity] if p.qualifier else [])
   wants_availability=bool(re.search(r"\\b(?:where|available|shop|location)\\b", p.raw.lower()))
   if wants_availability:
    paths=self.graph.derive(
     aliases,
     ("requires","obtained_from","available_at"),
     max_hops=3,
     require_current=True,
     min_tier_score=2.0,
    )
    if paths:
     path=paths[0]
     req,source,location=path[0].target,path[1].target,path[2].target
     text=(f"{path[0].source} requires {req}. {req} can be obtained through {source}. "
           f"{source} is available at {location}.")
     return self._answer(p,text,self.graph.provenance(path),"multi_hop_3")
   requirement_paths=self.graph.derive(aliases, ("requires",), max_hops=1, require_current=True, min_tier_score=2.0)
   if requirement_paths:
    complete=[]; incomplete=[]
    for req_path in requirement_paths:
     target=req_path[0].target
     source_paths=self.graph.derive(
      [target], ("obtained_from",), max_hops=1, require_current=True, min_tier_score=2.0
     )
     if source_paths:
      complete.append((req_path,source_paths))
     else:
      incomplete.append((req_path,target))
    if complete and not incomplete:
     parts=[]; provenance=[]
     for req_path,source_paths in complete:
      source_list=", ".join(x[0].target for x in source_paths)
      parts.append(f"{req_path[0].target} can be obtained through {source_list}")
      provenance.extend(self.graph.provenance(req_path))
      for path in source_paths: provenance.extend(self.graph.provenance(path))
     requirements_text=", ".join(x[0].target for x in requirement_paths)
     detail_text=". ".join(parts)
     if wants_availability:
      detail_text += " The evidence does not establish where that source is available."
     text=f"{requirement_paths[0][0].source} requires {requirements_text}. {detail_text}."
     return self._answer(p,text,provenance,"multi_hop")
    # A multi-hop answer is only valid when every requested link is evidenced.
    established=requirement_paths[0][0].source+" requires "+", ".join(x[0].target for x in requirement_paths)+"."
    established_claims=[]
    for req_path in requirement_paths:
     established_claims.extend(self.graph.provenance(req_path))
    return self._empty(
     p,
     established+" The knowledge base does not establish the acquisition path for every requirement, so I will not infer it.",
     claims=established_claims,
     mode="multi_hop_incomplete",
    )
  if p.property=="duplicate":
   cand=[]
   for c,s in rel:
    for sent in self._direct_sentences(p,c):
     if re.search(r"\b(?:duplicate|duplicates|dupe|dupes|same champion)\b",sent.lower()):
      cand.append((c,s,sent))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
    return self._answer(p,cand[0][2],[cand[0][0]],"duplicate")
   related_duplicates=[]
   for c,score in ranked[:20]:
    low=_blob(c)
    if "duplicate" in low and ("crew" in low or "star level" in low):
     related_duplicates.append((c,score))
   if related_duplicates:
    related_duplicates.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True)
    related=related_duplicates[0][0]
    return self._empty(
     p,
     "The current corpus documents duplicates for Crew star-level promotion, but it does not establish that duplicate Champions are required for Champion upgrades.",
     claims=[related],
     mode="duplicate_partial_abstention",
    )
   return self._empty(p,"The current knowledge base does not establish whether duplicate Champions are required for the requested upgrade.")
  if p.question_type=="requirement" and p.entity!="unknown":
   aliases=[p.entity] + ([p.qualifier+" "+p.entity] if p.qualifier else [])
   paths=self.graph.derive(aliases, ("requires",), max_hops=1)
   if paths:
    source=paths[0][0].source
    targets=[]; provenance=[]
    for path in paths:
     if path[0].target not in targets: targets.append(path[0].target)
     provenance.extend(self.graph.provenance(path))
    text=f"{source} requires "+", ".join(targets[:-1])+((" and " if len(targets)>1 else "")+targets[-1] if targets else "")+"."
    return self._answer(p,text,provenance,"graph_requirement")
  if p.question_type=="source" and p.entity!="unknown":
   aliases=[p.entity] + ([p.qualifier+" "+p.entity] if p.qualifier else [])
   paths=self.graph.derive(aliases, ("obtained_from",), max_hops=1)
   if paths:
    source=paths[0][0].source
    targets=[]; provenance=[]
    for path in paths:
     if path[0].target not in targets: targets.append(path[0].target)
     provenance.extend(self.graph.provenance(path))
    text=f"{source} can be obtained through "+", ".join(targets[:-1])+(( " and " if len(targets)>1 else "")+targets[-1] if targets else "")+"."
    return self._answer(p,text,provenance,"graph_source")
  if p.question_type=="source":
   cand=[]
   for c,s in rel:
    for sent in self._direct_sentences(p,c):
     if any(x in sent.lower() for x in ("obtain","obtained","get","source","drop","drops","earn","farm","shop","through")): cand.append((c,s,sent))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True); top=cand[:3]
    return self._answer(p," ".join(x[2] for x in top),[x[0] for x in top],"source")
  if p.question_type=="requirement":
   cand=[]
   for c,s in rel:
    for sent in self._direct_sentences(p,c):
     if any(x in sent.lower() for x in ("requires","require","need","needed","prerequisite","before","unlock")): cand.append((c,s,sent))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True); top=cand[:3]
    return self._answer(p," ".join(x[2] for x in top),[x[0] for x in top],"requirement")
  if p.question_type=="counter":
   cand=[]
   for c,s in rel:
    for sent in self._sentences(_text(c)):
     if "counter" in sent.lower() or "against" in sent.lower(): cand.append((c,s,sent))
   if cand:
    cand.sort(key=lambda x:(x[1],_authority(x[0])),reverse=True); return self._answer(p,cand[0][2],[cand[0][0]],"counter")
  if p.question_type=="comparison":
   return self._answer(p," ".join(_text(c) for c,_ in rel[:3]),[c for c,_ in rel[:3]],"comparison")
  top,_=rel[0]; direct=self._direct_sentences(p,top); text=direct[0] if direct else _text(top)
  if re.search(r"\bwhich\s+(?:type\s+of\s+)?components?\b", p.raw.lower()) and direct:
   return self._answer(p,text,[top],"direct_component")
  support=[]
  top_authority=_authority(top)
  for c,s in rel[1:4]:
   ss=self._direct_sentences(p,c)
   # Do not append low-tier/noisy context to a direct high-tier answer.
   if ss and _authority(c) >= top_authority-1.0:
    support.append((c,ss[0]))
  if support:text+=" "+" ".join(x[1] for x in support[:2])
  return self._answer(p,text,[top]+[x[0] for x in support[:2]],"direct")

_ENGINE=None
def get_engine():
 global _ENGINE
 if _ENGINE is None:
  import agent
  _ENGINE=KnowledgeQueryEngine(agent.CLAIMS, alias_groups=GRAPH_ENTITY_ALIASES)
 return _ENGINE
def answer(question,player_context=None):
 r=get_engine().compose(question)
 r["engine_version"]="v6.0.0-knowledge-query-engine"
 if player_context:r["player_context_applied"]={"season":player_context.get("season"),"core_level":player_context.get("core_level")}
 return r
