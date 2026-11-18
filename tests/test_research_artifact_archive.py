"""Archive safety and interruption recovery on synthetic local payloads only."""

from __future__ import annotations

import hashlib
import json
import os
import tarfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from scripts import research_artifact_archive as A


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(A, "ROOT", tmp_path)
    monkeypatch.setattr(A.G, "ROOT", tmp_path)
    monkeypatch.setattr(A.G, "LEDGER_PATH", tmp_path / "disk-ledger.jsonl")
    monkeypatch.setattr(A.G, "LOCK_PATH", tmp_path / "guard.lock")
    policy = json.loads(
        (Path(__file__).parents[1] / "config/research-archive-policy.json").read_text()
    )
    pp = tmp_path / "config/research-archive-policy.json"
    pp.parent.mkdir()
    pp.write_text(json.dumps(policy))
    monkeypatch.setattr(A, "POLICY_PATH", pp)
    mount = tmp_path / "mount"
    mount.mkdir()
    monkeypatch.setattr(A, "mount_available", lambda p: p == mount)
    monkeypatch.setattr(
        A.G,
        "load_policy",
        lambda: {
            "drive": {"remote_root": "gdrive:agent-data", "mount_root": str(mount)},
            "protected": [],
        },
    )
    monkeypatch.setattr(A.G, "in_use", lambda p: [])
    task = tmp_path / "reports/research/program/closed-task"
    task.mkdir(parents=True)
    source = task / "fits.jsonl.gz"
    source.write_bytes(b"frozen-model-provenance\n")
    evidence = task / "accepted.json"
    evidence.write_text('{"verdict":"accepted_complete_substudy","research_pass":false}')
    selection = tmp_path / "selection.json"
    selection.write_text(
        json.dumps(
            {
                "recommended_first_batch": [
                    {
                        "id": "TEST-1",
                        "task_id": "TASK-1",
                        "category": "method/test",
                        "completion": "accept_complete_conditional_substudy",
                        "summary_zh": "已完成条件性子研究，未形成可部署策略。",
                        "authoritative_evidence": [str(evidence)],
                        "files": [{"path": str(source)}],
                    }
                ]
            }
        )
    )
    return {
        "root": tmp_path,
        "policy": policy,
        "source": source,
        "evidence": evidence,
        "selection": selection,
        "mount": mount,
    }


def prepared(work):
    batch_path = A.prepare(work["selection"], work["policy"])
    batch = json.loads(batch_path.read_text())
    return batch_path, batch["files"][0]


def fake_drive(work, monkeypatch, *, success=True, after_upload=None):
    uploaded = []
    objects = {}

    def upload(item, policy, dry):
        assert item.verify == "hash" and not dry
        assert item.path == work["source"]  # native uploader receives original, no temp copy
        uploaded.append(item.remote)
        if not success:
            return False, "verify failed: 1 differences found"
        payload = item.path.read_bytes()
        target = work["mount"] / item.remote
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        objects[item.remote] = {
            "Size": len(payload),
            "ID": "stable-object-id",
            "Hashes": {"md5": hashlib.md5(payload, usedforsecurity=False).hexdigest()},
        }
        if after_upload:
            after_upload()
        return True, "0 differences found"

    def run(cmd, **kwargs):
        assert cmd[:4] == ["rclone", "lsjson", "--stat", "--hash"]
        key = cmd[4].removeprefix("gdrive:agent-data/")
        return (0, json.dumps(objects[key])) if key in objects else (4, "object not found")

    monkeypatch.setattr(A.G, "upload_and_verify", upload)
    monkeypatch.setattr(A.G, "run_cmd", run)
    return uploaded, objects


def test_success_atomic_release_and_resume_preserve_bytes_and_index(work, monkeypatch):
    before = work["source"].read_bytes()
    batch_path, row = prepared(work)
    uploads, _ = fake_drive(work, monkeypatch)
    result = A.execute(batch_path, work["policy"], release_local=True)
    assert result["files"][0]["status"] == "released"
    assert work["source"].is_symlink()
    assert work["source"].read_bytes() == before
    assert os.readlink(work["source"]) == str(work["mount"] / row["remote"])
    events = A.read_events(work["policy"])
    actions = [e["action"] for e in events]
    assert actions.index("release_intent") < actions.index("released")
    cat = json.loads((work["root"] / "reports/research/archive/catalog.json").read_text())
    assert cat["files"][0]["remote_id"] == "stable-object-id"
    assert cat["files"][0]["sha256"] == hashlib.sha256(before).hexdigest()
    assert cat["files"][0]["expiry"] is None
    assert cat["files"][0]["task_outcome"] == "accept_complete_conditional_substudy"
    assert (
        A.execute(batch_path, work["policy"], release_local=True)["files"][0]["status"]
        == "already_released"
    )
    assert len(uploads) == 1
    assert "research_archive_released" in (work["root"] / "disk-ledger.jsonl").read_text()


def test_failed_native_verification_preserves_source(work, monkeypatch):
    batch, _ = prepared(work)
    fake_drive(work, monkeypatch, success=False)
    before = work["source"].read_bytes()
    result = A.execute(batch, work["policy"], release_local=True)
    assert result["files"][0]["status"] == "retained_retryable"
    assert work["source"].read_bytes() == before and not work["source"].is_symlink()
    assert "release_intent" not in [e["action"] for e in A.read_events(work["policy"])]


def test_remote_collision_is_never_overwritten(work, monkeypatch):
    batch, row = prepared(work)
    uploaded, objects = fake_drive(work, monkeypatch)
    objects[row["remote"]] = {"Size": row["bytes"], "ID": "other", "Hashes": {"md5": "0" * 32}}
    result = A.execute(batch, work["policy"], release_local=True)
    assert result["files"][0]["status"] == "retained_retryable"
    assert uploaded == [] and not work["source"].is_symlink()


def test_mutation_with_same_size_and_restored_mtime_preserves_changed_source(work, monkeypatch):
    batch, row = prepared(work)

    def mutate():
        work["source"].write_bytes(b"x" * row["bytes"])
        os.utime(work["source"], ns=(row["mtime_ns"], row["mtime_ns"]))

    fake_drive(work, monkeypatch, after_upload=mutate)
    result = A.execute(batch, work["policy"], release_local=True)
    assert "bytes changed" in result["files"][0]["error"]
    assert work["source"].read_bytes() == b"x" * row["bytes"]
    assert not work["source"].is_symlink()


def test_changed_completion_evidence_preserves_source(work, monkeypatch):
    batch, _ = prepared(work)
    fake_drive(work, monkeypatch, after_upload=lambda: work["evidence"].write_text("reopened"))
    result = A.execute(batch, work["policy"], release_local=True)
    assert "completion evidence changed" in result["files"][0]["error"]
    assert not work["source"].is_symlink()


def test_task_becomes_active_during_upload_preserves_source(work, monkeypatch):
    batch, _ = prepared(work)
    fake_drive(
        work, monkeypatch, after_upload=lambda: monkeypatch.setattr(A.G, "in_use", lambda p: [123])
    )
    result = A.execute(batch, work["policy"], release_local=True)
    assert "became active" in result["files"][0]["error"]
    assert not work["source"].is_symlink()


def test_unavailable_mount_retains_verified_local_copy_and_remote_identity(work, monkeypatch):
    batch, _ = prepared(work)
    fake_drive(work, monkeypatch)
    monkeypatch.setattr(A, "mount_available", lambda p: False)
    result = A.execute(batch, work["policy"], release_local=True)
    assert "unavailable" in result["files"][0]["error"]
    assert not work["source"].is_symlink()
    cat = A.catalog(work["policy"])
    assert cat["files"][0]["remote_id"] == "stable-object-id"
    assert cat["files"][0]["verification"] == "prior_verification_retained_retry_pending"


@pytest.mark.parametrize("kind", ["source", "ancestor"])
def test_prepare_refuses_symlink_source_or_ancestor(work, kind):
    source = work["source"]
    if kind == "source":
        target = source.with_name("actual.gz")
        source.rename(target)
        source.symlink_to(target)
    else:
        task = source.parent
        target = task.with_name("moved-task")
        task.rename(target)
        task.symlink_to(target, target_is_directory=True)
    with pytest.raises(A.ArchiveError, match="Symlink"):
        A.prepare(work["selection"], work["policy"])


@pytest.mark.parametrize("name", ["paper-state.gz", "checkpoint.gz", "secret.gz"])
def test_protected_names_refused(work, name):
    path = work["source"].with_name(name)
    path.write_bytes(b"protected")
    with pytest.raises(A.ArchiveError, match="Protected"):
        A.validate_source(path, work["policy"])


def test_zip_credential_member_refused_without_extraction(work):
    path = work["source"].with_name("inputs.zip")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("config/.env", "example placeholder")
    selection = json.loads(work["selection"].read_text())
    selection["recommended_first_batch"][0]["files"][0]["path"] = str(path)
    work["selection"].write_text(json.dumps(selection))
    with pytest.raises(A.ArchiveError, match="Credential-looking ZIP"):
        A.prepare(work["selection"], work["policy"])
    assert not (path.parent / "config").exists()


def guard_scandir_link_classification(monkeypatch):
    """Catch implicit target stats hidden inside DirEntry classification (e.g. os.walk)."""
    original_scandir = os.scandir
    classified_links = []

    class GuardedEntry:
        def __init__(self, entry):
            self.entry = entry

        def __getattr__(self, name):
            return getattr(self.entry, name)

        def is_dir(self, *, follow_symlinks=True):
            if self.entry.is_symlink():
                classified_links.append(follow_symlinks)
                assert not follow_symlinks, "Directory classification must not follow archive links"
            return self.entry.is_dir(follow_symlinks=follow_symlinks)

        def stat(self, *, follow_symlinks=True):
            if self.entry.is_symlink():
                assert not follow_symlinks, "Metadata inspection must not stat archive targets"
            return self.entry.stat(follow_symlinks=follow_symlinks)

    @contextmanager
    def guarded_scandir(path):
        with original_scandir(path) as entries:
            yield (GuardedEntry(entry) for entry in entries)

    monkeypatch.setattr(os, "scandir", guarded_scandir)
    return classified_links


def test_legacy_scan_indexes_broken_archive_link_without_remote_stat(work, monkeypatch):
    target = work["mount"] / "archive/open-composer/old/binary.gz"
    link = work["source"].with_name("legacy.gz")
    link.symlink_to(target)
    real_stat = Path.stat

    def guarded_stat(path, *args, **kwargs):
        if A.under(path, work["mount"]):
            raise AssertionError("Legacy scan must not stat any remote target")
        return real_stat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "stat", guarded_stat)
    result = A.legacy_scan(work["policy"])
    assert result["remote_payload_reads"] == 0
    assert result["files"][0]["remote"] == "archive/open-composer/old/binary.gz"
    assert result["files"][0]["verification"] == "historical_link_only_not_newly_verified"


def test_legacy_scan_never_follows_direntry_links_during_classification(work, monkeypatch):
    link = work["source"].with_name("legacy.gz")
    link.symlink_to(work["mount"] / "archive/open-composer/old/binary.gz")
    classified = guard_scandir_link_classification(monkeypatch)
    result = A.legacy_scan(work["policy"])
    assert [row["original_path"] for row in result["files"]] == [str(link)]
    assert classified and not any(classified)


def test_legacy_scan_excludes_managed_batch_links_but_preserves_historical_links(work):
    _, row = prepared(work)
    source = work["source"]
    source.unlink()
    source.symlink_to(work["mount"] / row["remote"])
    historical = source.with_name("older-archive.gz")
    historical.symlink_to(work["mount"] / "archive/open-composer/legacy/older.gz")
    result = A.legacy_scan(work["policy"])
    assert [entry["original_path"] for entry in result["files"]] == [str(historical)]
    assert result["remote_payload_reads"] == 0


def test_interruption_after_atomic_replace_recovers_from_intent(work, monkeypatch):
    batch, _ = prepared(work)
    uploads, _ = fake_drive(work, monkeypatch)
    original_event = A.event
    fail = True

    def interrupted(policy, action, **values):
        nonlocal fail
        if action == "released" and fail:
            fail = False
            raise OSError("simulated interrupted final receipt")
        return original_event(policy, action, **values)

    monkeypatch.setattr(A, "event", interrupted)
    result = A.execute(batch, work["policy"], release_local=True)
    assert result["files"][0]["status"] == "release_receipt_pending"
    assert work["source"].is_symlink() and work["source"].read_bytes()
    result = A.execute(batch, work["policy"], release_local=True)
    assert result["files"][0]["status"] == "already_released" and len(uploads) == 1


def test_batch_edit_refused_and_catalog_survives_policy_revision(work):
    batch, _ = prepared(work)
    pp = A.POLICY_PATH
    pp.write_text(pp.read_text() + "\n")
    with pytest.raises(A.ArchiveError, match="Policy changed"):
        A.load_batch(batch, work["policy"])
    assert A.catalog(work["policy"])["files"][0]["status"] == "prepared"
    changed = json.loads(batch.read_text())
    changed["files"][0]["remote"] = "elsewhere"
    batch.write_text(json.dumps(changed))
    with pytest.raises(A.ArchiveError, match="batch has been edited"):
        A.load_batch(batch, work["policy"])


def test_shared_disk_guard_lock_prevents_overlapping_archive_operator(work):
    with A.global_lock(), pytest.raises(A.ArchiveError, match="lock is busy"), A.global_lock():
        pass


def test_metadata_backup_is_copy_only_native_verified_and_excludes_payloads(work, monkeypatch):
    prepared(work)
    archive_root = A.catalog_root(work["policy"])
    (archive_root / "linked-remote.json").symlink_to(
        work["mount"] / "archive/open-composer/old/remote.json"
    )
    classified = guard_scandir_link_classification(monkeypatch)
    uploaded = []
    state = {}

    def upload(item, policy, dry):
        assert item.verify == "hash" and not dry
        with tarfile.open(item.path, "r:gz") as archive:
            names = archive.getnames()
        assert "catalog.json" in names and "events.jsonl" in names
        assert "linked-remote.json" not in names
        assert not any("fits.jsonl.gz" in name or "_snapshots" in name for name in names)
        payload = item.path.read_bytes()
        state["meta"] = {
            "Size": len(payload),
            "ID": "catalog-backup-id",
            "Hashes": {"md5": hashlib.md5(payload, usedforsecurity=False).hexdigest()},
        }
        uploaded.append(item)
        return True, "0 differences found"

    monkeypatch.setattr(A.G, "upload_and_verify", upload)
    monkeypatch.setattr(
        A.G,
        "run_cmd",
        lambda *a, **k: (
            (0, json.dumps(state["meta"])) if "meta" in state else (4, "object not found")
        ),
    )
    receipt = A.backup_catalog(work["policy"])
    assert receipt["remote_id"] == "catalog-backup-id" and len(uploaded) == 1
    assert receipt["mode"] == "copy_only_no_local_or_remote_deletion"
    assert Path(receipt["local_snapshot"]).is_file()
    assert work["source"].is_file() and not work["source"].is_symlink()
    assert classified and not any(classified)
