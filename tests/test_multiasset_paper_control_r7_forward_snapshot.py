from __future__ import annotations

import hashlib
import json
import shutil
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from open_composer.adapters.data import multiasset_paper_control_r7_snapshot as snapshot
from open_composer.adapters.data.alpaca_snapshot import AlpacaSnapshotContract

ROOT = Path(__file__).resolve().parents[1]


def test_r7_forward_contract_changes_only_registered_session_fields() -> None:
    template = json.loads((ROOT / snapshot.TEMPLATE_PATH).read_text(encoding="utf-8"))
    derived = snapshot.build_r7_forward_snapshot_contract(ROOT, date(2026, 8, 3))

    assert derived["latest_frozen_session"] == "2026-08-03"
    assert derived["immutable_output_root"].endswith("/2026-08-03")
    assert derived["timeframes"]["daily"]["requested_end_exclusive"] == (
        "2026-08-04T00:00:00-04:00"
    )
    for field in set(template) - {
        "latest_frozen_session",
        "immutable_output_root",
        "timeframes",
    }:
        assert derived[field] == template[field]
    assert (
        derived["timeframes"]["daily"]["requested_start"]
        == template["timeframes"]["daily"]["requested_start"]
    )
    AlpacaSnapshotContract.model_validate(derived)


@pytest.mark.parametrize("session", [date(2026, 8, 2), date(2026, 8, 1)])
def test_r7_forward_contract_rejects_pre_epoch_or_non_session(session: date) -> None:
    with pytest.raises(ValueError, match="eligible US trading session"):
        snapshot.build_r7_forward_snapshot_contract(ROOT, session)


def test_r7_forward_contract_publication_is_idempotent_and_detects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = tmp_path / snapshot.TEMPLATE_PATH
    template.parent.mkdir(parents=True)
    shutil.copy2(ROOT / snapshot.TEMPLATE_PATH, template)
    monkeypatch.setattr(snapshot, "verify_r7_lock", lambda *_: {})

    first = snapshot.prepare_r7_forward_snapshot_contract(tmp_path, date(2026, 8, 3))
    second = snapshot.prepare_r7_forward_snapshot_contract(tmp_path, date(2026, 8, 3))
    assert first == second

    first.chmod(0o600)
    first.write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="different bytes"):
        snapshot.prepare_r7_forward_snapshot_contract(tmp_path, date(2026, 8, 3))


def test_r7_forward_manifest_rejects_contract_drift(tmp_path: Path) -> None:
    template = tmp_path / snapshot.TEMPLATE_PATH
    template.parent.mkdir(parents=True)
    shutil.copy2(ROOT / snapshot.TEMPLATE_PATH, template)
    session = date(2026, 8, 3)
    contract_path = tmp_path / snapshot._contract_relative_path(session)
    contract_path.parent.mkdir(parents=True)
    payload = snapshot.build_r7_forward_snapshot_contract(tmp_path, session)
    payload["timeframes"]["daily"]["requested_start"] = "2021-01-01T00:00:00-05:00"
    contract_path.write_text(json.dumps(payload), encoding="utf-8")
    manifest = {
        "contract_path": snapshot._contract_relative_path(session).as_posix(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "output_root": snapshot._snapshot_relative_dir(session).as_posix(),
    }

    with pytest.raises(ValueError, match="outside allowed session fields"):
        snapshot.validate_r7_forward_snapshot_contract(tmp_path, manifest, session)


def test_latest_available_r7_session_is_not_backfillable() -> None:
    with pytest.raises(ValueError, match="cannot begin before"):
        snapshot.latest_available_r7_session(datetime(2026, 8, 3, 20, 14, tzinfo=UTC))
    assert snapshot.latest_available_r7_session(datetime(2026, 8, 3, 20, 15, tzinfo=UTC)) == date(
        2026, 8, 3
    )
