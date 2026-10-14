"""Inspect our existing terminal and repair only the local control pointer if usable."""
import json
import sys
from pathlib import Path
ROOT=Path.cwd();sys.path.insert(0,str(ROOT));OUT=ROOT/'reports/research/program/paper-continuity-20261014'
from open_composer.remote.windows_worker import _save_terminal,_state_path,load_worker_contract,run_worker_command,worker_preflight
terminal=json.loads((OUT/'hadan-terminal.json').read_text())['terminal_id']
capture=run_worker_command(ROOT,['terminal','capture',terminal,'--json'],timeout=35)
(OUT/'control-pointer-terminal-inspection.json').write_text(json.dumps({'returncode':capture.returncode,'stdout':capture.stdout,'stderr':capture.stderr},indent=2)+'\n')
if not capture.ok:
    raise RuntimeError('Existing owned terminal unavailable: no fresh readiness, no remote work')
json.loads(capture.stdout)
p=_state_path()
(OUT/'control-pointer-before.json').write_text(p.read_text()if p.exists()else '{"previous_pointer_missing":true}\n')
contract=load_worker_contract(ROOT);_save_terminal(terminal,contract['workspace_id'])
result=worker_preflight(ROOT,remote=True)
(OUT/'hadan-control-repaired-standard-preflight.json').write_text(json.dumps(result,indent=2)+'\n')
assert result['ok'] is True,'Actual standard preflight failed; no remote job or transfer'
print(json.dumps({'ok':result['ok'],'worker':result['remote']['worker_status'],'worker_protocol_changed':False,'local_control_pointer_repaired_only':True}))
