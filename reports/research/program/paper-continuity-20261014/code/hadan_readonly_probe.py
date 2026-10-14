"""One bounded observation of the handed-off worker lane; no scientific job."""
import json
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from open_composer.remote.windows_worker import load_worker_contract, run_worker_command

OUT = ROOT / 'reports/research/program/paper-continuity-20261014'
assert not (OUT / 'hadan-lane-observation.json').exists()
contract = load_worker_contract(ROOT)
terminal = json.loads((OUT / 'hadan-terminal.json').read_text())['terminal_id']
marker = 'PAPER_CONTINUITY_LANE_20261014'
command = r'''powershell -NoProfile -Command "Write-Output 'PAPER_CONTINUITY_LANE_20261014_BEGIN'; $r=@{at_UTC=[DateTime]::UtcNow.ToString('o');available_RAM_bytes=[long](Get-CimInstance Win32_PerfFormattedData_PerfOS_Memory).AvailableBytes;old_host_env_present=(Test-Path 'C:\paseo\scratch\host-freshness-azn-broad-20261012\env\Scripts\python.exe');old_host_root_present=(Test-Path 'C:\paseo\scratch\host-freshness-azn-broad-20261012\root');chinco_env_present=(Test-Path 'C:\paseo\scratch\chinco-cp311-env-20261012-attempt01\Scripts\python.exe')}; $r|ConvertTo-Json -Compress; Write-Output 'PAPER_CONTINUITY_LANE_20261014_END'"'''
sent = run_worker_command(ROOT, ['terminal', 'send-keys', terminal, command, 'Enter'], timeout=40)
assert sent.ok, 'bounded readonly command send failed (details redacted)'
deadline = time.monotonic()+45
while time.monotonic() < deadline:
    captured = run_worker_command(ROOT, ['terminal', 'capture', terminal, '--json'], timeout=30)
    if captured.ok:
        (OUT / 'hadan-lane-capture-attempt2.json').write_text(captured.stdout)
        value = json.loads(captured.stdout)
        lines = [str(s).strip() for s in value.get('lines', [])]
        if marker+'_BEGIN' in lines:
            begin = lines.index(marker+'_BEGIN')
            if marker+'_END' in lines[begin+1:]:
                end = lines.index(marker+'_END', begin+1)
                observation = json.loads(''.join(lines[begin+1:end]))
                assert type(observation['available_RAM_bytes']) is int
                (OUT / 'hadan-lane-observation.json').write_text(json.dumps(observation, indent=2)+'\n')
                print(json.dumps(observation)); break
    time.sleep(1)
else:
    raise TimeoutError('readonly lane observation missing; no job admitted')
