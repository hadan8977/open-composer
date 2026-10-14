"""Convert already verified source evidence to native SourceCard schema; no new claims/fetches."""
import hashlib,json,shutil
from pathlib import Path
P=Path(__file__).parent;D=Path('reports/research/iterations/t20261013_hf_factor_conditional_method');C=Path('reports/harness/source_cards/day20261013_hf_factor_method.jsonl')
def fingerprint(s):return hashlib.sha256(' '.join(s.lower().split()).encode()).hexdigest()
# Use actual native helper to avoid duplicating its canonicalization convention.
from open_composer.research.knowledge_memory import claim_fingerprint, canonical_source_url
for q in [C,D/'external-brief.json',D/'direction-review.json']:
 out=P/('pre-source-schema-repair-'+q.name)
 if not out.exists():shutil.copyfile(q,out)
cards=[json.loads(r) for r in C.read_text().splitlines()];lookup={}
for r in cards:
 r.update(iteration_id=D.name,accessed_at=r['fetched_at'][:10],verified_at=r['fetched_at'],verification_method='Actual retained author primary text read; exact snapshot/quote/claim bindings verified by native source/direction contract',applies_to=['source_method','conditional_source_clock','cost_metrics'],impact_on_spec='Reproduce frozen source-driven definitions with explicit APP differences; no scope/readiness expansion')
 lookup[r['claim_id']]=r
C.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in cards))
for q in [D/'external-brief.json',D/'direction-review.json']:
 d=json.loads(q.read_text())
 for r in d['source_evidence_bindings']:
  card=lookup[r['claim_id']];r['canonical_url']=canonical_source_url(r['source_url']);r['source_card_claim_id']=r['claim_id'];r['claim_fingerprint']=claim_fingerprint(card['claim']);r['brief_claim_fingerprint']=claim_fingerprint(next(s['core_claim'] for s in d['sources'] if s['claim_id']==r['claim_id']))
 q.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
from open_composer.models.source_card import SourceCard
from open_composer.research.knowledge_memory import _current_source_card_locations
for r in cards:SourceCard.model_validate(r)
assert _current_source_card_locations(json.loads((D/'external-brief.json').read_text()),D.name,Path.cwd())
print('sourcecard schema/native source bindings valid; same claims/URLs/snapshots, no new requests')
