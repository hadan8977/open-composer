"""Actual targeted file-size inventory; no price rows or source acquisitions."""
import json
import sys
import os
from unittest.mock import patch
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
WT = Path('/root/codex-test/wt-paper-continuity-20261014')
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(WT), str(WT / 'scripts')]
import forward_refresh_io as io
import refresh_equity_book_live as rf

cfg = {'year': 2026, 'version_directory': 'reports/research/program/paper-continuity-20261014/revisions/continuity-v3/peak-stat-only', 'disk_spill_bound_bytes': 2 * 1024**3}
install = json.loads((HERE.parent / 'continuity-v2/data-installation-manifest.json').read_text())
# Shared historical directories are authoritative. Overlay only the already
# accepted replacement sizes; no physical installation or price read occurs.
overrides = {ROOT / v['proposed_shared_relative_path']: v['bytes'] for v in install['entries']}
real_stat = Path.stat
def installed_stat(path, *args, **kwargs):
    stat = real_stat(path, *args, **kwargs)
    if path in overrides:
        fields = list(stat)
        fields[6] = overrides[path]
        return os.stat_result(fields)
    return stat
with patch.object(Path, 'stat', installed_stat):
    try:
        io.disk_admission(ROOT, cfg, source_root=ROOT, tables=list(rf.UPSTREAM),
                          live=ROOT / 'data/live/equity_book', stages=list(rf.LIVE_STAGES),
                          year=2026, fetch=True)
    except OSError:
        pass
receipt = sorted((ROOT / cfg['version_directory'] / 'admissions').glob('*.json'))[-1]
value = json.loads(receipt.read_text())
value.update(measurement_scope='Actual shared historical feature/live directories and raw/archive sizes, with only accepted installation replacement file sizes overlaid; stat-only; no broad source scan', accepted_size_overlay_count=len(overrides), old_9444666278_bound_superseded=True, root_archive_6768_assumed_released_bytes=0, production_run_performed=False)
installation = install['total_installation_bytes']
value['installation_bytes'] = installation
value['projected_available_after_install_bytes'] = value['actual_available_bytes'] - installation
value['install_plus_refresh_gap_bytes'] = max(0, value['required_available_bytes'] + installation - value['actual_available_bytes'])
value['ready_after_install'] = value['install_plus_refresh_gap_bytes'] == 0
(HERE / 'actual-peak-admission.json').write_text(json.dumps(value, indent=2) + '\n')
print(json.dumps({k: value[k] for k in ['terms', 'required_available_bytes', 'actual_available_bytes', 'install_plus_refresh_gap_bytes', 'ready_after_install']}))
