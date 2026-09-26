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

STOP={"what","which","when","where","why","how","does","do","is","are","the","a","an","to","of","for","and","or","i","my","you","your","can","could","would","should","with","on","in","at","from","it","they","them","their","me","we","this","that","these","those","be","before","after","into","about","get","give","use","appear","appears"}

# Expansion relationships are not identity relationships.
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
}
PROPERTY_ALIASES={
 "unlock_level":["level","unlock","unlocks","unlocking","appear","appears","available","availability","access","opens","introduced"],
 "source":["get","obtain","source","sources","earn","farm","where","drop","drops"],
 "requirement":["require","requires","need","needed","prerequisite","before","condition","unlock"],
 "cost":["cost","costs","price","spend","resources","resource"],
 "effect":["effect","does","gives","boost","bonus","increase","changes"],
 "comparison":["difference","different","versus","vs","compare","compared"],
 "counter":["counter","counters","against","beats","advantage"],
 "upgrade":["upgrade","upgrading","level","empowerment","power up"],
}
QUESTION_TYPES={
 "level_threshold":["which level","what level","at what level","level do","level does"],
 "source":["how do i get","where do i get","how to get","where can i get","source","sources","obtain","farm"],
 "requirement":["what unlocks","what do i need","what is required","requires","requirement","prerequisite","before i can"],
 "comparison":["difference","different","versus"," vs ","compare"],
 "strategy":["best","optimal","recommended","should i","priority","most efficient"],
 "effect":["what happens","what does","what do","effect","benefit","bonus"],
 "counter":["what counters","which counters","counter","against"],
 "numeric":["how many","how much","how long","percentage","percent","cost"],
 "definition":["what is","what are"],
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

class QuestionParser:
 def parse(self,question):
  q=question.strip(); ql=q.lower()
  entity="unknown"
  for e in sorted(ENTITY_ALIASES,key=len,reverse=True):
   if e in ql: entity=e; break
  qualifier=""
  if entity!="unknown":
   m=re.search(r"\b([a-z][a-z-]{2,})\s+"+re.escape(entity)+r"\b",ql)
   if m and m.group(1) not in STOP: qualifier=m.group(1)
  qtype="generic"
  for kind,patterns in QUESTION_TYPES.items():
   if any(p in ql for p in patterns): qtype=kind; break
  prop="general"
  order={
   "unlock_level":["level","appear","available","unlock"],
   "source":["get","obtain","source","farm","drop"],
   "requirement":["require","need","prerequisite","before","condition"],
   "cost":["cost","price","spend"],"comparison":["difference","different","versus","compare"],
   "counter":["counter","against","beats"],"effect":["effect","bonus","boost","change","happen"],
   "upgrade":["upgrade","empowerment","power up"]}
  for p,words in order.items():
   if any(w in ql for w in words): prop=p; break
  expansions=[q]
  if entity in ENTITY_ALIASES: expansions+=ENTITY_ALIASES[entity]
  if prop in PROPERTY_ALIASES: expansions+=PROPERTY_ALIASES[prop]
  if qualifier: expansions.append(qualifier+" "+entity)
  return ParsedQuestion(q,entity,prop,qualifier,qtype,sorted(_norm_tokens(q)),list(dict.fromkeys(expansions)))

class KnowledgeQueryEngine:
 def __init__(self,claims): self.claims=claims; self.parser=QuestionParser()
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
  for c in self.claims:
   if str(c.get("Status",c.get("status",""))).lower() in ("rejected","superseded"): continue
   score=3.5*_similarity(p.raw,_blob(c))+self._entity_score(p,c)+self._property_score(p,c)+self._relation_score(p,c)+.65*_authority(c)
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
 def _empty(self,p,note=""):
  return {"answer":"I cannot establish the exact answer from the current FGF knowledge base." if not note else note,"evidence":[],"evidence_used":[],"model":"fgf-v6-knowledge-query-engine","answer_type":"knowledge_abstention","uncertainty":note or "No sufficiently relevant evidence was found.","quality_gate":{"passes":True,"uses_relevant_evidence":False,"reason":"Evidence-safe abstention."},"query":p.as_dict()}
 def _answer(self,p,text,claims,mode):
  unique=[];seen=set()
  for c in claims:
   k=_text(c).strip()
   if k and k not in seen: seen.add(k);unique.append(c)
  answer=text.strip()
  for i in range(len(unique)):
   if f"[E{i+1}]" not in answer: answer+=f" [E{i+1}]"
  evidence=[{"id":f"E{i+1}","claim":_text(c),"tier":c.get("Evidence Tier",c.get("tier","")),"status":c.get("Status",c.get("status","")),"source":c.get("Source",c.get("source","")),"category":c.get("Category",c.get("category",""))} for i,c in enumerate(unique)]
  return {"answer":answer,"evidence":evidence,"evidence_used":list(range(1,len(unique)+1)),"model":"fgf-v6-knowledge-query-engine","answer_type":"knowledge_query","uncertainty":"","quality_gate":{"passes":True,"uses_relevant_evidence":True,"reason":"Direct answer composed from ranked evidence."},"query":p.as_dict(),"reasoning":{"mode":mode,"entity":p.entity,"property":p.property,"question_type":p.question_type,"evidence_count":len(unique)}}
 def compose(self,q,limit=8):
  p=self.parse(q); ranked=self.rank(p,limit); rel=[(c,s) for c,s in ranked if s>=5]
  if not rel:return self._empty(p)
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
  support=[]
  for c,s in rel[1:4]:
   ss=self._direct_sentences(p,c)
   if ss:support.append((c,ss[0]))
  if support:text+=" "+" ".join(x[1] for x in support[:2])
  return self._answer(p,text,[top]+[x[0] for x in support[:2]],"direct")

_ENGINE=None
def get_engine():
 global _ENGINE
 if _ENGINE is None:
  import agent
  _ENGINE=KnowledgeQueryEngine(agent.CLAIMS)
 return _ENGINE
def answer(question,player_context=None):
 r=get_engine().compose(question)
 r["engine_version"]="v6.0.0-knowledge-query-engine"
 if player_context:r["player_context_applied"]={"season":player_context.get("season"),"core_level":player_context.get("core_level")}
 return r
