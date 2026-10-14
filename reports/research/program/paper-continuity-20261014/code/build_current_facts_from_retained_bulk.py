"""Original facts parser, current retained SEC ZIP, no network or credentials."""
import json
import sys
from pathlib import Path

WT=Path('/root/codex-test/wt-paper-continuity-20261014');P=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(WT/'scripts'))
import build_sec_xbrl_fundamentals as f

class NoNetwork:
    def get(self,*args,**kwargs):raise RuntimeError('network forbidden in retained-body parse')
    def stream_to_file(self,*args,**kwargs):raise RuntimeError('network forbidden in retained-body parse')
    def close(self):pass

f.SecClient=NoNetwork
f.ZIP_PATH=P/'current-companyfacts-bulk/companyfacts.zip'
f.FACTS_BATCH_ROOT=P/'current-facts-batches';f.FACTS_BATCH_ROOT.mkdir(exist_ok=True)
assert json.loads((P/'current-companyfacts-bulk/ledger.json').read_text())['complete']
assert f.FACTS_PATH.is_symlink(),'first isolated current-facts parse only'
n=f.run_facts_stage(source='bulk',limit=None,batch_size=50,force=False)
f.FACTS_PATH.unlink()  # unlink the private read-only reference, never write through it.
f.write_facts_from_batches()
print(json.dumps({'current_source_CIKs':n,'new_source_requests':0,'original_facts_parser':True,'private_output':str(f.FACTS_PATH)}),flush=True)
