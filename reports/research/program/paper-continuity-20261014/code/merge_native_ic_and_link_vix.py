import importlib.util
import json
import os
import sys
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
os.environ['OC_EQUITY_BOOK_DIR'] = str(WT / 'data/live/equity_book')
sys.path.insert(0, str(WT))
spec = importlib.util.spec_from_file_location('refresh_native', WT / 'scripts/refresh_equity_book_live.py')
m = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = m
spec.loader.exec_module(m)
target = WT / 'data/live/vix/VIXCLS.csv'
target.parent.mkdir(parents=True, exist_ok=True)
if not target.exists():
    target.symlink_to(ROOT / 'data/live/vix/VIXCLS.csv')
file = m.merge_formation_ic()
(P / 'native-formation-ic-merge.json').write_text(json.dumps({'output': str(file), 'sha256': m._sha256(file), 'method': 'same existing snapshot through2024 + native live2025+ merger; no new model/parameters', 'shared_writes': 0}, indent=2) + '\n')
print({'formation_ic': str(file), 'shared_writes': 0}, flush=True)
