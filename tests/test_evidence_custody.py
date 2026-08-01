from __future__ import annotations

import json
from pathlib import Path

import pytest

from open_composer.research.evidence_custody import (
    verify_external_custody_record,
    write_external_custody_bundle,
)


def test_external_custody_bundle_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    project = tmp_path / "project"
    custody = tmp_path / "custody"
    project.mkdir()
    subject_sha256 = "a" * 64
    entries = {
        "lock-set/lock-anchor.json": b'{"lock":1}\n',
        "strategy_specs/drafts/candidate.yaml": b"name: candidate\n",
    }

    first = write_external_custody_bundle(
        project_root=project,
        custody_root=custody.resolve(),
        namespace="r5",
        record_kind="lock",
        subject_sha256=subject_sha256,
        entries=entries,
        subject={"iter_id": "r5", "operator_lock_anchor_sha256": subject_sha256},
    )
    second = write_external_custody_bundle(
        project_root=project,
        custody_root=custody.resolve(),
        namespace="r5",
        record_kind="lock",
        subject_sha256=subject_sha256,
        entries=entries,
        subject={"iter_id": "r5", "operator_lock_anchor_sha256": subject_sha256},
    )

    assert first.receipt_path == second.receipt_path
    assert first.receipt_sha256 == second.receipt_sha256
    assert first.bundle_sha256 == second.bundle_sha256
    assert first.receipt_path.stat().st_mode & 0o222 == 0
    assert first.bundle_path.stat().st_mode & 0o222 == 0
    assert first.payload["entry_count"] == 2


def test_external_custody_rejects_worktree_and_tampering(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    with pytest.raises(ValueError, match="outside the project worktree"):
        write_external_custody_bundle(
            project_root=project,
            custody_root=(project / "custody").resolve(),
            namespace="r5",
            record_kind="lock",
            subject_sha256="b" * 64,
            entries={"source.txt": b"source"},
            subject={"iter_id": "r5"},
        )

    custody = tmp_path / "custody"
    record = write_external_custody_bundle(
        project_root=project,
        custody_root=custody.resolve(),
        namespace="r5",
        record_kind="evaluation",
        subject_sha256="c" * 64,
        entries={"evaluation-run/evaluation-report.json": b'{"result":1}\n'},
        subject={"iter_id": "r5"},
    )
    record.receipt_path.chmod(0o600)
    payload = json.loads(record.receipt_path.read_text(encoding="utf-8"))
    payload["entry_count"] = 99
    record.receipt_path.write_text(json.dumps(payload), encoding="utf-8")
    record.receipt_path.chmod(0o400)

    with pytest.raises(ValueError, match="canonical|manifest"):
        verify_external_custody_record(
            project_root=project,
            custody_root=custody.resolve(),
            receipt_path=record.receipt_path,
            expected_namespace="r5",
            expected_record_kind="evaluation",
            expected_subject_sha256="c" * 64,
        )
