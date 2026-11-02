"""One finite continuation after the existing driver exits; no polling or new job."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
from datetime import UTC, datetime

ROOT = Path('/root/codex-test/open-composer')
RUN = ROOT / 'research/martin_model_completion_20261102/runs/model-completion-20261102-1'
OUT = RUN / 'recovery/finite-continuation.json'
DRIVER = 2424437
FINISHER = 2447186


def record(status, **extra):
    OUT.write_text(json.dumps(dict(at_utc=datetime.now(UTC).isoformat(), pid=os.getpid(),
                                  original_driver=DRIVER, status=status, **extra), indent=2)+'\n')


if __name__ == '__main__':
    command = Path(f'/proc/{DRIVER}/cmdline').read_bytes().replace(b'\0', b' ')
    assert b'research_round.py resume martin_model_completion_20261102' in command
    finisher_command = Path(f'/proc/{FINISHER}/cmdline').read_bytes().replace(b'\0', b' ')
    assert b'finish_saved_accounts.py' in finisher_command
    descriptor = os.pidfd_open(DRIVER)
    finisher_descriptor = os.pidfd_open(FINISHER)
    record('ready_for_model_transport_sleep', native_finisher=FINISHER,
           waits='One pidfd event per process; no model/status polling')
    ready, _, _ = select.select([descriptor], [], [], 6 * 3600)
    os.close(descriptor)
    if not ready:
        record('finite_wait_expired_preserve_jobs')
        sys.exit(0)
    record('model_asleep_waiting_native_terminal', native_finisher=FINISHER,
           original_session='01a19b46-1c81-7b72-8f21-47baae1358f5')
    ready, _, _ = select.select([finisher_descriptor], [], [], 6 * 3600)
    os.close(finisher_descriptor)
    if not ready:
        record('finite_native_wait_expired_preserve_jobs')
        sys.exit(0)
    series_path = RUN.parent / 'model-completion-20261102-series.json'
    state = json.loads(series_path.read_text())
    if state.get('status') in {'decision_handoff', 'paused'}:
        record('original_series_finished_no_resume', series_status=state.get('status'))
        sys.exit(0)
    control = json.loads((ROOT / 'control.json').read_text())
    if control.get('research') is not True or control.get('draft') is not False:
        record('research_disabled_preserve_jobs')
        sys.exit(0)
    # The existing resume command rechecks all native authority and live-job locks.
    record('resuming_original_series_once', series_status=state.get('status'))
    with (RUN / 'recovery/finite-continuation.log').open('x') as output:
        result = subprocess.run([
            str(ROOT / '.venv/bin/python'), str(ROOT / 'scripts/research_round.py'),
            'resume', 'martin_model_completion_20261102', '--run-id', 'model-completion-20261102',
            '--timeout-seconds', '14400', '--follow'], cwd=ROOT, stdin=subprocess.DEVNULL,
            stdout=output, stderr=subprocess.STDOUT)
    record('finite_continuation_returned', returncode=result.returncode,
           evidence='Original run/series files own the result; no numerical jobs launched by this helper')
