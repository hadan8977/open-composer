"""Byte-verify the existing authorized Drive backup; release only own transport copy."""
import hashlib
import json
import subprocess
from pathlib import Path

P = Path(__file__).resolve().parents[1]
source = P / 'hadan-core-package/input.zip'
remote = 'gdrive:agent-data/archive/open-composer/paper-continuity-20261014/hadan-core-package/input.zip'
with source.open('rb') as stream:
    expected = hashlib.file_digest(stream, 'sha256').hexdigest()
size = source.stat().st_size
proc = subprocess.Popen(['rclone', 'cat', remote], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
digest = hashlib.sha256()
count = 0
while chunk := proc.stdout.read(65536):
    count += len(chunk)
    assert count <= size, 'remote entity exceeds bound'
    digest.update(chunk)
error = proc.stderr.read()
code = proc.wait()
actual = digest.hexdigest()
result = {'local': str(source), 'remote': remote, 'bytes': size, 'expected_sha256': expected, 'actual_remote_sha256': actual, 'remote_bytes': count, 'rclone_exit': code, 'full_byte_stream_verified': code == 0 and size == count and expected == actual, 'original_sources_and_failures_deleted': 0, 'authorization': 'existing disk-policy Drive archive contract; private redundant transport only', 'shared_disk_guard_changed': False}
(P / 'own-transport-archive-verification.json').write_text(json.dumps(result, indent=2) + '\n')
assert result['full_byte_stream_verified']
source.unlink()
print({'full_byte_stream_verified': True, 'released_bytes': size, 'source_or_failure_records_deleted': 0}, flush=True)
