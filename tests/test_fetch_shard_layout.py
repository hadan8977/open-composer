"""Resuming a fetch must not silently reinterpret shard numbers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from fetch_sip_universe import (  # noqa: E402
    assert_resumable_layout,
    layout_path,
)


def _shard(root: Path, kind: str, year: int, shard: int) -> None:
    path = root / kind / str(year)
    path.mkdir(parents=True, exist_ok=True)
    (path / f"shard-{shard:04d}.parquet").write_bytes(b"x")


def test_first_run_records_the_layout(tmp_path: Path) -> None:
    assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13416)
    recorded = json.loads(layout_path(tmp_path, "minute").read_text(encoding="utf-8"))
    assert recorded["batch_size"] == 12
    assert recorded["universe_size"] == 13416


def test_resuming_with_the_same_layout_is_allowed(tmp_path: Path) -> None:
    assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13416)
    _shard(tmp_path, "minute", 2023, 0)
    assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13416)


def test_a_changed_batch_size_is_fatal(tmp_path: Path) -> None:
    """The real incident: BATCH_SIZE went 40 -> 12 mid-backfill.

    Shard N is symbols[N*BATCH_SIZE:(N+1)*BATCH_SIZE], so the same index named a
    different symbol slice under each layout. Coverage survived only because the
    new numbering happened to start earlier in the alphabet than the old one had
    reached; the opposite change would have dropped every symbol in between with
    nothing reporting it.
    """
    assert_resumable_layout(tmp_path, "minute", batch_size=40, universe_size=13440)
    _shard(tmp_path, "minute", 2023, 0)
    with pytest.raises(SystemExit, match="shard layout changed"):
        assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13440)


def test_a_changed_universe_size_is_fatal(tmp_path: Path) -> None:
    assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13416)
    _shard(tmp_path, "minute", 2023, 0)
    with pytest.raises(SystemExit, match="shard layout changed"):
        assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=9000)


def test_preexisting_shards_without_a_layout_file_are_fatal(tmp_path: Path) -> None:
    # Their batch size is unknown, so resuming could skip symbols silently.
    _shard(tmp_path, "minute", 2023, 0)
    with pytest.raises(SystemExit, match="no _LAYOUT.json"):
        assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13416)


def test_an_empty_archive_without_a_layout_file_is_fine(tmp_path: Path) -> None:
    (tmp_path / "minute").mkdir(parents=True)
    assert_resumable_layout(tmp_path, "minute", batch_size=12, universe_size=13416)
    assert layout_path(tmp_path, "minute").exists()


def test_the_live_archives_declare_their_layouts() -> None:
    root = Path(__file__).resolve().parents[1] / "data" / "sip"
    for kind in ("daily", "minute"):
        if not (root / kind).is_dir():
            pytest.skip(f"local SIP {kind} archive is not present")
        recorded = json.loads(layout_path(root, kind).read_text(encoding="utf-8"))
        assert recorded["batch_size"] > 0
        assert recorded["universe_size"] > 0


# ---------------------------------------------------------------------------
# The archive must keep updating after the backfill finishes
# ---------------------------------------------------------------------------


def test_recent_windows_are_refetched_even_when_their_shard_exists() -> None:
    """Resume skips existing shards, which freezes the archive on completion day.

    The shard covering the current month was written from a partial month; the
    shard covering the current year from a partial year. Skipping them forever
    means every later backtest runs on prices that quietly recede into the past,
    with nothing reporting it -- the retired IEX cache stopped at 2026-08-04
    exactly this way.
    """
    from datetime import UTC, datetime, timedelta

    from fetch_sip_universe import window_is_stale

    now = datetime(2026, 9, 2, tzinfo=UTC)
    current_month_end = datetime(2026, 10, 1, tzinfo=UTC)
    long_settled_end = datetime(2024, 1, 1, tzinfo=UTC)

    assert window_is_stale(current_month_end, refresh_recent_days=45, now=now)
    assert not window_is_stale(long_settled_end, refresh_recent_days=45, now=now)
    # The boundary is inclusive, so a window ending exactly at the cutoff refreshes.
    assert window_is_stale(now - timedelta(days=45), refresh_recent_days=45, now=now)
    assert not window_is_stale(now - timedelta(days=46), refresh_recent_days=45, now=now)


def test_refresh_can_be_disabled_for_a_pure_backfill() -> None:
    from datetime import UTC, datetime

    from fetch_sip_universe import window_is_stale

    now = datetime(2026, 9, 2, tzinfo=UTC)
    assert not window_is_stale(now, refresh_recent_days=0, now=now)
