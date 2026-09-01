"""Retention policy for the local SIP parquet archive."""

from __future__ import annotations

import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from prune_local_archive import (  # noqa: E402
    RETENTION_DAYS,
    discover_units,
    run,
    select_expired,
)

NOW = datetime(2026, 9, 1, tzinfo=UTC)


def _write_shard(root: Path, kind: str, year: int, month: int | None) -> None:
    directory = root / kind / str(year) / (f"{month:02d}" if month else "")
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "shard-0000.parquet").write_bytes(b"x" * 1024)


def test_minute_months_are_discovered_individually(tmp_path: Path) -> None:
    for month in (1, 2, 3):
        _write_shard(tmp_path, "minute", 2023, month)
    units = discover_units(tmp_path, "minute")
    assert [u.label for u in units] == ["minute/2023/01", "minute/2023/02", "minute/2023/03"]
    assert all(u.bytes_used == 1024 for u in units)


def test_daily_whole_year_is_a_single_unit(tmp_path: Path) -> None:
    _write_shard(tmp_path, "daily", 2016, None)
    units = discover_units(tmp_path, "daily")
    assert [u.label for u in units] == ["daily/2016"]
    assert units[0].month is None


def test_minute_retention_expires_months_older_than_three_and_a_half_years(tmp_path: Path) -> None:
    for month in (1, 2, 3, 4):
        _write_shard(tmp_path, "minute", 2023, month)
    expired = select_expired(discover_units(tmp_path, "minute"), now=NOW)
    # 1278 days before 2026-09-01 is 2023-03-04, so only January and February
    # have fully aged out; March's data extends past the cutoff.
    assert [u.label for u in expired] == ["minute/2023/01", "minute/2023/02"]


def test_whole_year_survives_until_the_entire_year_ages_out(tmp_path: Path) -> None:
    # 10 years before 2026-09-01 lands inside 2016, so 2016 must NOT be dropped:
    # deleting the year would take September-December 2016 with it.
    _write_shard(tmp_path, "daily", 2016, None)
    _write_shard(tmp_path, "daily", 2015, None)
    expired = select_expired(discover_units(tmp_path, "daily"), now=NOW)
    assert [u.label for u in expired] == ["daily/2015"]


def test_dry_run_deletes_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_shard(tmp_path, "daily", 2010, None)
    run(root=tmp_path, remote_root="datasets/sip", now=NOW, apply=False, require_remote=False)
    capsys.readouterr()
    assert (tmp_path / "daily" / "2010" / "shard-0000.parquet").exists()


def test_apply_deletes_only_expired_units(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_shard(tmp_path, "daily", 2010, None)
    _write_shard(tmp_path, "daily", 2025, None)
    run(root=tmp_path, remote_root="datasets/sip", now=NOW, apply=True, require_remote=False)
    capsys.readouterr()
    assert not (tmp_path / "daily" / "2010").exists()
    assert (tmp_path / "daily" / "2025" / "shard-0000.parquet").exists()


def test_missing_remote_backup_blocks_deletion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _write_shard(tmp_path, "daily", 2010, None)
    monkeypatch.setattr("prune_local_archive.remote_has", lambda *_args, **_kw: False)
    run(root=tmp_path, remote_root="datasets/sip", now=NOW, apply=True, require_remote=True)
    capsys.readouterr()
    assert (tmp_path / "daily" / "2010" / "shard-0000.parquet").exists()


def test_retention_horizons_match_the_agreed_storage_split() -> None:
    assert RETENTION_DAYS["daily"] == 3653
    assert RETENTION_DAYS["minute"] == 1278
