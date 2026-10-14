"""One-off verified cold archive; no source deletion in prepare/upload phase."""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
sys.path.insert(0, str(ROOT / 'scripts'))
import disk_guard as guard

OUT = ROOT / 'reports/research/program/paper-continuity-20261014/disk-recovery'
STAGE = ROOT / 'data/_paper_cold_features_20261014'
REMOTE = 'archive/open-composer/cold-features-20261014'
MANIFEST = OUT / 'root-cold-feature-manifest.json'


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def hashes(path):
    sha, md5 = hashlib.sha256(), hashlib.md5()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            sha.update(chunk)
            md5.update(chunk)
    return sha.hexdigest(), md5.hexdigest()


def main():
    started = time.process_time()
    policy = guard.load_policy()
    with guard.LOCK_PATH.open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if sys.argv[1] == 'prepare-upload':
            assert not STAGE.exists() and not MANIFEST.exists()
            sources = [ROOT / 'data/features' / kind / f'{year}.parquet'
                       for kind in ['alpha158', 'alpha191', 'osap_price_broad']
                       for year in range(2016, 2024)]
            rows = []
            for source in sources:
                assert source.is_file() and not source.is_symlink()
                assert guard.safe_to_delete(source, policy)[0]
                assert not guard.in_use(source), f'active file: {source}'
                before = source.stat()
                sha, md5 = hashes(source)
                after = source.stat()
                assert (before.st_ino, before.st_size, before.st_mtime_ns) == (
                    after.st_ino, after.st_size, after.st_mtime_ns)
                relative = source.relative_to(ROOT / 'data/features')
                target = STAGE / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                os.link(source, target)
                rows.append(dict(source=str(source), staged=str(target),
                                 relative=str(relative), bytes=after.st_size,
                                 sha256=sha, md5=md5, inode=after.st_ino,
                                 mtime_ns=after.st_mtime_ns))
            dump(MANIFEST, dict(at_utc=datetime.now(timezone.utc).isoformat(),
                               scope='24 inactive derived partitions,2016-2023 only',
                               remote=REMOTE, files=rows,
                               bytes=sum(r['bytes'] for r in rows),
                               original_source_and_active_tasks_changed=False,
                               deletion_authorized_only_after_remote_hash_check=True,
                               CPU_prepare=time.process_time()-started))
            proc = subprocess.run(['gdrive', '--json', 'upload', str(STAGE),
                                   '--remote', REMOTE, '--strategy', 'direct-large'],
                                  capture_output=True, text=True, timeout=60)
            (OUT / 'root-cold-feature-upload-response.json').write_text(proc.stdout)
            (OUT / 'root-cold-feature-upload-stderr.txt').write_text(proc.stderr)
            assert proc.returncode == 0, 'upload enqueue failed; original files retained'
            print(proc.stdout, flush=True)
            print(json.dumps({'staged_files':len(rows), 'bytes':sum(r['bytes'] for r in rows),
                              'CPU':time.process_time()-started, 'local_removed':0}), flush=True)
        elif sys.argv[1] == 'verify-release':
            manifest = json.loads(MANIFEST.read_text())
            rows = manifest['files']
            job = json.loads((OUT / 'root-cold-feature-upload-response.json').read_text())['job_id']
            deadline = time.monotonic() + 1800
            while True:
                proc = subprocess.run(['gdrive', '--json', 'job', 'status', str(job)],
                                      capture_output=True, text=True, timeout=30, check=True)
                status = json.loads(proc.stdout)
                dump(OUT / 'root-cold-feature-upload-status.json', status)
                if status['finished']:
                    assert status['success'], 'Archive failed; all local files retained.'
                    break
                assert time.monotonic() < deadline, 'Upload still running; retain local copies.'
                time.sleep(30)
            destination = policy['drive']['remote_root'] + '/' + REMOTE
            check = subprocess.run(['rclone', 'check', str(STAGE), destination,
                                    '--one-way', '--checkers', '2'],
                                   capture_output=True, text=True, timeout=1200)
            log = check.stdout + check.stderr
            (OUT / 'root-cold-feature-remote-check.txt').write_text(log)
            assert check.returncode == 0 and re.search(r'\b0 differences found', log)
            listing = subprocess.run(['rclone', 'lsjson', destination, '--recursive',
                                      '--files-only', '--hash', '--hash-type', 'MD5'],
                                     capture_output=True, text=True, timeout=120, check=True)
            (OUT / 'root-cold-feature-remote-hashes.json').write_text(listing.stdout)
            remote = {r['Path']:r for r in json.loads(listing.stdout)}
            assert set(remote) == {r['relative'] for r in rows}
            mounted = Path(policy['drive']['mount_root']) / REMOTE
            for row in rows:
                rr = remote[row['relative']]
                assert rr['Size'] == row['bytes'] and rr['Hashes']['md5'] == row['md5']
                source, staged = Path(row['source']), Path(row['staged'])
                st = source.stat()
                assert not source.is_symlink() and st.st_ino == row['inode']
                assert st.st_size == row['bytes'] and st.st_mtime_ns == row['mtime_ns']
                assert os.path.samefile(source, staged)
                assert (mounted / row['relative']).stat().st_size == row['bytes']
                assert not guard.in_use(source) and not guard.in_use(staged)
            before = os.statvfs(ROOT)
            receipt = {'state':'remote_verified_before_local_release', 'job_id':job,
                       'remote_MD5_matches':len(rows), 'released':[],
                       'available_before':before.f_bavail * before.f_frsize}
            dump(OUT / 'root-cold-feature-release.json', receipt)
            for row in rows:
                item = guard.Item(kind='warm', path=Path(row['source']),
                                  remote=REMOTE+'/'+row['relative'],
                                  symlink_to=mounted / row['relative'])
                ok, reason, _ = guard.delete_path(item, policy, False)
                assert ok, reason
                receipt['released'].append(row['source'])
                guard.ledger({'action':'verified_cold_feature_reference',
                              'path':row['source'], 'remote':item.remote,
                              'sha256':row['sha256'], 'md5':row['md5'],
                              'verification':str(OUT/'root-cold-feature-remote-check.txt'),
                              'storage_still_retained_until_stage_release':True})
                dump(OUT / 'root-cold-feature-release.json', receipt)
            ok, reason, _ = guard.delete_path(guard.Item(kind='backup', path=STAGE), policy, False)
            assert ok, reason
            after = os.statvfs(ROOT)
            receipt.update(state='verified_archive_local_storage_released',
                           available_after=after.f_bavail * after.f_frsize,
                           CPU=time.process_time()-started,
                           missing_original_information=0, original_paths_preserved=True)
            dump(OUT / 'root-cold-feature-release.json', receipt)
            guard.ledger({'action':'verified_cold_features_archive_and_release',
                          'files':len(rows), 'bytes':manifest['bytes'], 'remote':REMOTE,
                          'receipt':str(OUT/'root-cold-feature-release.json')})
            print(json.dumps(receipt), flush=True)
        else:
            raise SystemExit('Unknown phase.')


if __name__ == '__main__':
    main()
