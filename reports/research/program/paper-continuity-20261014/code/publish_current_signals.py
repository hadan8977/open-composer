import json
import sys
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
P = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WT / 'scripts'))
from prepare_host_forward_version import compose, sha256

old = ROOT / 'data/live/equity_book/signals/2026.parquet'
current = WT / 'data/live/equity_book/signals/2026.parquet'
candidate = P / 'natural-reader-candidates/signals-2026.parquet'
assert not candidate.exists()
current.replace(candidate)
r = compose(old, candidate, current, expected_baseline_sha256=sha256(old), prefix_end='2026-10-07', suffix_end='2026-10-13', source_manifest=P / 'current-feature-input-manifest.json', version_id='paper-continuity-reader-forward-20261014')
(P / 'compose-current-reader-signals.json').write_text(json.dumps(r, indent=2) + '\n')
print({'prefix_rows': r['prefix_verification']['rows'], 'suffix_rows': r['suffix_rows']}, flush=True)
