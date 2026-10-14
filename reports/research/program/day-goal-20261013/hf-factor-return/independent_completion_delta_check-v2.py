"""Bounded independent M2 check: small bindings, AST, saved state, toy tests only."""
import ast
import hashlib
import json
import os
import pickle
import resource
import sys
from pathlib import Path

resource.setrlimit(resource.RLIMIT_CPU, (140, 145))
assert os.sched_getaffinity(0) == {0}
P = Path(__file__).resolve().parent
sys.path.insert(0, str(P))
import numpy as np
import pytest
import sklearn
from hf_completion_resources import snapshot
from hf_run_models import binning_digest, tree_state_digest

checked = {}
def verify(row):
    p = Path(row['path'])
    assert p.stat().st_size < 5_000_000, str(p)
    b = p.read_bytes()
    assert hashlib.sha256(b).hexdigest() == row['sha256'], str(p)
    if 'bytes' in row:
        assert len(b) == row['bytes'], str(p)
    checked[str(p)] = {'sha256': row['sha256'], 'bytes': len(b)}

delta = json.loads((P/'completion-implementation-delta.json').read_text())
def walk(x):
    if isinstance(x, dict):
        if 'path' in x and 'sha256' in x:
            verify(x)
        else:
            for v in x.values(): walk(v)
    elif isinstance(x, list):
        for v in x: walk(v)
walk(delta)
old = json.loads((P/'implementation-M2-archive/implementation-manifest.json').read_text())
new = json.loads((P/'implementation-manifest.json').read_text())
assert old['contracts'] == new['contracts']
previous = {str(Path(r['path']).resolve()): dict(r,path=str(Path(r['path']).resolve())) for r in old['files']}
current = {str(Path(r['path']).resolve()): dict(r,path=str(Path(r['path']).resolve())) for r in new['files']}
assert set(previous) <= set(current)
changed = [p for p in previous if previous[p] != current[p]]
added = [p for p in current if p not in previous]
for p in changed + added:
    if current[p]['bytes'] < 5_000_000: verify(current[p])
    else:
        assert p.endswith('/economic/HGB-scaled-IDX-2019.npy')
        assert current[p] == json.loads((P/'calibration-resume-contract.json').read_text())['scaled_input']
assert len(previous) == 71 and len(current) == 87

parity = json.loads((P/'completion-science-AST-parity.json').read_text())
ast_checked = {}
for name, key, allowed in [
    ('hf_run_models.py','model_function_AST_equal',{'economic_cpu_used','guard','calibrate','resume_calibration','tree_state_digest','binning_digest'}),
    ('hf_evaluate.py','evaluation_function_AST_equal',set()),
]:
    trees = [ast.parse((d/name).read_text()) for d in [P/'implementation-M2-archive',P]]
    funcs = [{n.name: ast.dump(n, include_attributes=False) for n in t.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))} for t in trees]
    differences = [n for n in funcs[0].keys() | funcs[1].keys() if funcs[0].get(n) != funcs[1].get(n)]
    assert set(differences) <= allowed, (name,differences)
    for n in parity[key]: assert funcs[0][n] == funcs[1][n], n
    ast_checked[name] = {'changed_or_added_or_removed':differences,'asserted_equal':parity[key]}

ledger_path = P/'completion-resource-ledger-at-delta-review.json'
ledger = json.loads(ledger_path.read_text())
state = snapshot(ledger_path)
assert abs(state['conservative_used_CPU']-514.57)<1e-8
assert state['commitments']=={'independent-completion-delta-review-01':180}
assert abs(state['remaining_uncommitted_CPU']-35305.43)<1e-8
for row in ledger['entries']:
    if 'receipt' in row: verify(row['receipt'])

contract = json.loads((P/'calibration-resume-contract.json').read_text())
verify(contract['checkpoint150']); verify(contract['scaler'])
assert sklearn.__version__ == contract['sklearn_version'] == '1.9.0'
model=pickle.loads(Path(contract['checkpoint150']['path']).read_bytes())
assert model.n_iter_ == len(model._predictors) == 150
assert model.get_params()==contract['parameters']
assert tree_state_digest(model,150)==contract['first150_tree_digest']
assert binning_digest(model)==contract['bin_threshold_digest']
assert int(model._random_seed)==contract['random_seed']
assert model._feature_subsample_rng.bit_generator.state==contract['feature_subsample_rng_state']
scaler=np.load(contract['scaler']['path'])
for name, spec in contract['scaler_value_hashes'].items():
    a=scaler[name]
    assert list(a.shape)==spec['shape'] and str(a.dtype)==spec['dtype']
    assert hashlib.sha256(a.tobytes()).hexdigest()==spec['sha256']
assert not Path(contract['output350']).exists()

result=dict(small_bindings_checked=checked,inherited_files_not_rehashed=len(previous)-len(changed),
    changed_bindings=changed,added_bindings=added,AST=ast_checked,ledger=state,
    actual_checkpoint150_state_verified=True,scaler_values_verified=True,real_fit_predict_score=False,
    scaled787MB_not_rehashed=True,source300_and_large_features_not_rehashed=True,
    CPU_affinity=sorted(os.sched_getaffinity(0)),test_scope='Synthetic50→150→serialized350 versus same uninterrupted warm chain; no real inputs fitted')
code=pytest.main(['-q',str(P/'test_hf_completion_delta.py'),'--junitxml='+str(P/'independent-completion-delta-tests.xml')])
result['test_exit']=int(code)
result['process_resource']=dict(user_CPU=resource.getrusage(resource.RUSAGE_SELF).ru_utime,system_CPU=resource.getrusage(resource.RUSAGE_SELF).ru_stime,peak_RSS_KiB=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
(P/'independent-completion-delta-verification.json').write_text(json.dumps(result,indent=2)+'\n')
assert code == 0
print(json.dumps({'verified':True,'small_bindings':len(checked),'changed':changed,'added_count':len(added),'resource':result['process_resource']}))
