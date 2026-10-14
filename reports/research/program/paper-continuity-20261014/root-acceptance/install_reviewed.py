"""One-off Root integration of the exact reviewed paper recovery package."""

import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from contextlib import ExitStack
from pathlib import Path

ROOT = Path('/root/codex-test/open-composer')
TASK = ROOT / 'reports/research/program/paper-continuity-20261014'
REV = TASK / 'revisions/continuity-v2'
RUN = TASK / 'root-acceptance/installation'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(value):
    temp = RUN / 'journal.tmp'
    with temp.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(RUN / 'journal.json')


def checked(binding):
    path = Path(binding['path'])
    assert path.is_file() and path.stat().st_size == binding['bytes']
    assert sha(path) == binding['sha256'], f'binding changed: {path}'
    return path


def target(relative):
    path = ROOT / relative
    assert path.is_relative_to(ROOT) and '..' not in Path(relative).parts
    assert not any(p.is_symlink() for p in [path, *path.parents] if p.is_relative_to(ROOT))
    return path


def main():
    admission = json.loads(Path(sys.argv[1]).read_text())
    assert admission['root_installation_approved'] is True
    checked(admission['independent_review'])
    patch = checked(admission['patch'])
    data_manifest = json.loads(checked(admission['data_manifest']).read_text())
    manifest = json.loads(checked(admission['revision_manifest']).read_text())
    config = checked(admission['config'])
    assert not RUN.exists(), 'Existing attempt must be inspected, not overwritten.'
    with ExitStack() as stack:
        for relative in ['data/live/.refresh.lock', 'logs/book_v12_daily.lock']:
            stream = stack.enter_context((ROOT / relative).open('a'))
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        assert not (ROOT / 'reports/paper/book/quant1/orders/2026-10-14.json').exists()
        for row in admission['before_code']:
            assert sha(target(row['relative'])) == row['sha256']
        subprocess.run(['git', 'apply', '--check', str(patch)], cwd=ROOT, check=True)
        st = os.statvfs(ROOT)
        assert st.f_bavail * st.f_frsize >= admission['required_available_bytes']
        RUN.mkdir()
        journal = {'state':'preparing', 'admission':str(Path(sys.argv[1]).resolve()),
                   'before':[], 'installed':[], 'production_orders_submitted':0}
        save(journal)
        paths = re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.MULTILINE)
        entries = list(data_manifest['entries']) + [dict(
            path=str(config), bytes=config.stat().st_size, sha256=sha(config),
            proposed_shared_relative_path='config/equity-book-forward.json')]
        all_paths = paths + [r['proposed_shared_relative_path'] for r in entries]
        assert len(all_paths) == len(set(all_paths))
        for relative in all_paths:
            dest = target(relative)
            row = {'relative':relative, 'existed':dest.exists()}
            if dest.exists():
                backup = RUN / 'before' / relative
                backup.parent.mkdir(parents=True, exist_ok=True)
                if relative.startswith('data/'):
                    os.link(dest, backup)
                else:
                    shutil.copy2(dest, backup)
                row.update(backup=str(backup), sha256=sha(backup), bytes=backup.stat().st_size)
            journal['before'].append(row)
        save(journal)
        for row in entries:
            source = Path(row['path'])
            staged = RUN / 'staged' / row['proposed_shared_relative_path']
            staged.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, staged)
            assert staged.stat().st_size == row['bytes'] and sha(staged) == row['sha256']
            with staged.open('rb') as stream:
                os.fsync(stream.fileno())
        journal['state'] = 'staged_and_backed_up'
        save(journal)
        subprocess.run(['git', 'apply', str(patch)], cwd=ROOT, check=True)
        journal['state'] = 'code_applied'
        save(journal)
        for row in manifest['code']:
            relative = str(Path(row['path']).relative_to('/root/codex-test/wt-paper-continuity-20261014'))
            assert sha(target(relative)) == row['sha256'], f'integrated code differs: {relative}'
        for row in entries:
            relative = row['proposed_shared_relative_path']
            dest = target(relative)
            dest.parent.mkdir(parents=True, exist_ok=True)
            (RUN / 'staged' / relative).replace(dest)
            directory_fd = os.open(dest.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
            journal['installed'].append({'relative':relative, 'sha256':row['sha256']})
            save(journal)
        journal['state'] = 'installed_shared_readonly_runtime_validation_pending'
        save(journal)
        print(json.dumps({'state':journal['state'], 'data_and_config':len(entries),
                          'code_files_verified':len(manifest['code']), 'orders':0}))


if __name__ == '__main__':
    main()
