"""scripts/update_sip_archive.py: incremental SIP archive updates.

Step 10 section 3.3 (docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md):
shard identity must be frozen to each shard's actual symbol membership, not
re-derived from a live universe sort, and merges must keep the newest row on
a timestamp collision. Everything here uses a fake ``_fetch_batch`` so no
network/credentials are required; the fake returns frames shaped exactly like
Alpaca's ``get_stock_bars(...).df`` (a (symbol, timestamp) MultiIndex), which
is what real callers of ``_fetch_batch`` receive before ``.reset_index()``.
"""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd
import pytest

import scripts.update_sip_archive as update_sip_archive
from scripts.update_sip_archive import (
    UpdateLockedError,
    _exclusive_lock,
    _merge_and_write,
    _read_shard_frame,
    _refuse_if_bulk_fetch_active,
    append_new_symbols,
    current_window_dirs,
    freeze_shard_symbols,
    load_layout,
    refetch_window_start,
    save_layout,
    update_existing_shards,
    window_full_start,
)


def _bars_frame(rows: list[tuple[str, str, float]]) -> pd.DataFrame:
    """Shaped like Alpaca's ``get_stock_bars(...).df``: a (symbol, timestamp)
    MultiIndex, columns present before ``.reset_index()`` is ever called.
    """
    index = pd.MultiIndex.from_tuples(
        [(symbol, pd.Timestamp(ts, tz="UTC")) for symbol, ts, _ in rows],
        names=["symbol", "timestamp"],
    )
    return pd.DataFrame(
        {
            "open": [value for _, _, value in rows],
            "high": [value for _, _, value in rows],
            "low": [value for _, _, value in rows],
            "close": [value for _, _, value in rows],
            "volume": [100.0 for _ in rows],
            "trade_count": [1.0 for _ in rows],
            "vwap": [value for _, _, value in rows],
        },
        index=index,
    )


def _write_shard(path: Path, rows: list[tuple[str, str, float]]) -> None:
    frame = _bars_frame(rows).reset_index()
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_parquet(path, compression="zstd", index=False)


# ---------------------------------------------------------------------------
# Pure calendar/window helpers
# ---------------------------------------------------------------------------


def test_current_window_dirs_daily_is_just_the_current_year() -> None:
    now = datetime(2026, 9, 4, tzinfo=UTC)
    assert current_window_dirs("daily", now) == [(2026, None)]


def test_current_window_dirs_minute_includes_previous_month_early_in_the_month() -> None:
    now = datetime(2026, 9, 2, tzinfo=UTC)
    assert current_window_dirs("minute", now) == [(2026, 8), (2026, 9)]


def test_current_window_dirs_minute_is_just_the_current_month_later_on() -> None:
    now = datetime(2026, 9, 15, tzinfo=UTC)
    assert current_window_dirs("minute", now) == [(2026, 9)]


def test_window_full_start() -> None:
    assert window_full_start("daily", 2026, None) == datetime(2026, 1, 1, tzinfo=UTC)
    assert window_full_start("minute", 2026, 9) == datetime(2026, 9, 1, tzinfo=UTC)


def test_refetch_window_start_uses_the_full_window_for_a_brand_new_shard() -> None:
    full_start = datetime(2026, 9, 1, tzinfo=UTC)
    assert refetch_window_start(None, full_window_start=full_start) == full_start


def test_refetch_window_start_looks_back_a_couple_of_sessions_from_the_latest_bar() -> None:
    full_start = datetime(2026, 1, 1, tzinfo=UTC)
    max_ts = pd.Timestamp("2026-09-03T20:00:00Z")
    result = refetch_window_start(max_ts, full_window_start=full_start)
    assert full_start < result <= datetime(2026, 9, 3, tzinfo=UTC)
    assert result >= datetime(2026, 8, 28, tzinfo=UTC)


def test_refetch_window_start_never_precedes_the_full_window_start() -> None:
    # A shard's latest bar sitting right at the window boundary must not pull
    # the re-fetch start before the window it belongs to.
    full_start = datetime(2026, 9, 1, tzinfo=UTC)
    max_ts = pd.Timestamp("2026-09-01T14:30:00Z")
    result = refetch_window_start(max_ts, full_window_start=full_start)
    assert result >= full_start


# ---------------------------------------------------------------------------
# Freezing shard symbol membership
# ---------------------------------------------------------------------------


def test_freeze_shard_symbols_reads_actual_membership_from_shard_content(tmp_path: Path) -> None:
    out = tmp_path / "sip"
    _write_shard(out / "daily" / "2026" / "shard-0000.parquet", [("AAPL", "2026-08-01", 1.0)])
    _write_shard(out / "daily" / "2026" / "shard-0001.parquet", [("MSFT", "2026-08-01", 2.0)])
    (out / "daily" / "_LAYOUT.json").write_text(
        json.dumps({"batch_size": 1, "universe_size": 2}), encoding="utf-8"
    )
    layout = load_layout(out, "daily")
    now = datetime(2026, 9, 4, tzinfo=UTC)

    shard_symbols = freeze_shard_symbols(out, "daily", layout, now=now)

    assert shard_symbols == {0: ["AAPL"], 1: ["MSFT"]}
    persisted = json.loads((out / "daily" / "_LAYOUT.json").read_text(encoding="utf-8"))
    assert persisted["shard_symbols"] == {"0000": ["AAPL"], "0001": ["MSFT"]}


def test_freeze_shard_symbols_is_idempotent_and_never_rescans(tmp_path: Path) -> None:
    out = tmp_path / "sip"
    _write_shard(out / "daily" / "2026" / "shard-0000.parquet", [("AAPL", "2026-08-01", 1.0)])
    (out / "daily" / "_LAYOUT.json").write_text(
        json.dumps({"batch_size": 1, "universe_size": 1}), encoding="utf-8"
    )
    now = datetime(2026, 9, 4, tzinfo=UTC)
    layout = load_layout(out, "daily")
    first = freeze_shard_symbols(out, "daily", layout, now=now)
    assert first == {0: ["AAPL"]}

    # Simulate the shard changing shape after the freeze (e.g. a later, buggy
    # write): a second call must return the FROZEN list, not a rescan.
    _write_shard(out / "daily" / "2026" / "shard-0000.parquet", [("ZZZZ", "2026-08-01", 9.0)])
    reloaded_layout = load_layout(out, "daily")
    second = freeze_shard_symbols(out, "daily", reloaded_layout, now=now)
    assert second == {0: ["AAPL"]}


# ---------------------------------------------------------------------------
# Merge-and-write: keep the newest row on a (symbol, timestamp) collision
# ---------------------------------------------------------------------------


def test_merge_and_write_keeps_the_newest_row_on_collision(tmp_path: Path) -> None:
    destination = tmp_path / "shard-0000.parquet"
    existing = _bars_frame([("AAPL", "2026-08-01", 1.0)]).reset_index()
    fetched = _bars_frame([("AAPL", "2026-08-01", 2.0), ("AAPL", "2026-08-02", 3.0)]).reset_index()

    rows_fetched = _merge_and_write(existing, fetched, destination)

    assert rows_fetched == 2
    result = _read_shard_frame(destination)
    assert len(result) == 2  # deduplicated, not 3
    corrected = result.loc[result["timestamp"] == pd.Timestamp("2026-08-01", tz="UTC")]
    assert corrected["close"].iloc[0] == pytest.approx(2.0)  # the newer value won


def test_merge_and_write_is_atomic_and_leaves_no_temp_file(tmp_path: Path) -> None:
    destination = tmp_path / "2026" / "shard-0000.parquet"
    fetched = _bars_frame([("AAPL", "2026-08-01", 1.0)]).reset_index()

    _merge_and_write(
        pd.DataFrame(columns=list(update_sip_archive.BAR_ROW_COLUMNS)), fetched, destination
    )

    assert destination.exists()
    leftovers = list(destination.parent.glob(destination.name + ".tmp*"))
    assert leftovers == []


# ---------------------------------------------------------------------------
# Updating existing shards and appending newly-listed symbols
# ---------------------------------------------------------------------------


def test_update_existing_shards_tops_up_from_each_shards_own_latest_bar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "sip"
    destination = out / "daily" / "2026" / "shard-0000.parquet"
    _write_shard(destination, [("AAPL", "2026-08-01", 1.0)])
    requested_windows: list[tuple[tuple[str, ...], datetime, datetime]] = []

    def fake_fetch_batch(data_client, symbols, start, end, kind):
        requested_windows.append((tuple(symbols), start, end))
        return _bars_frame([("AAPL", "2026-08-15", 5.0)])

    monkeypatch.setattr(update_sip_archive, "_fetch_batch", fake_fetch_batch)
    now = datetime(2026, 8, 20, tzinfo=UTC)

    total = update_existing_shards(
        data_client=object(), out=out, kind="daily", shard_symbols={0: ["AAPL"]}, now=now
    )

    assert total == 1
    assert requested_windows[0][0] == ("AAPL",)
    result = _read_shard_frame(destination)
    assert len(result) == 2
    assert pd.Timestamp("2026-08-15", tz="UTC") in set(result["timestamp"])


def test_append_new_symbols_assigns_the_next_shard_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "sip"
    (out / "daily").mkdir(parents=True)
    layout = {"batch_size": 1, "universe_size": 2, "shard_symbols": {"0000": ["AAPL"]}}
    save_layout(out, "daily", layout)

    monkeypatch.setattr(
        update_sip_archive,
        "_fetch_batch",
        lambda data_client, symbols, start, end, kind: _bars_frame(
            [(symbols[0], "2026-01-05", 42.0)]
        ),
    )
    now = datetime(2026, 9, 4, tzinfo=UTC)

    rows = append_new_symbols(
        data_client=object(),
        out=out,
        kind="daily",
        layout=layout,
        shard_symbols={0: ["AAPL"]},
        active_symbols=["AAPL", "ZZZZ"],
        now=now,
    )

    assert rows == 1
    persisted = json.loads((out / "daily" / "_LAYOUT.json").read_text(encoding="utf-8"))
    assert persisted["shard_symbols"]["0001"] == ["ZZZZ"]
    destination = out / "daily" / "2026" / "shard-0001.parquet"
    assert destination.exists()
    result = _read_shard_frame(destination)
    assert result["symbol"].tolist() == ["ZZZZ"]


def test_append_new_symbols_is_a_noop_when_nothing_is_new(tmp_path: Path) -> None:
    out = tmp_path / "sip"
    (out / "daily").mkdir(parents=True)
    layout = {"shard_symbols": {"0000": ["AAPL"]}}
    save_layout(out, "daily", layout)

    rows = append_new_symbols(
        data_client=object(),
        out=out,
        kind="daily",
        layout=layout,
        shard_symbols={0: ["AAPL"]},
        active_symbols=["AAPL"],
        now=datetime(2026, 9, 4, tzinfo=UTC),
    )

    assert rows == 0
    assert not (out / "daily" / "2026").exists()


# ---------------------------------------------------------------------------
# Locking and the bulk-fetch guard
# ---------------------------------------------------------------------------


def test_exclusive_lock_refuses_a_concurrent_run(tmp_path: Path) -> None:
    with _exclusive_lock(tmp_path):
        with pytest.raises(UpdateLockedError, match="already exists"):
            with _exclusive_lock(tmp_path):
                pass  # pragma: no cover - must raise on __enter__


def test_exclusive_lock_releases_on_success_and_on_exception(tmp_path: Path) -> None:
    with _exclusive_lock(tmp_path):
        pass
    assert not (tmp_path / "_update_sip_archive.lock").exists()

    with pytest.raises(ValueError):
        with _exclusive_lock(tmp_path):
            raise ValueError("boom")
    assert not (tmp_path / "_update_sip_archive.lock").exists()


def test_refuse_if_bulk_fetch_active_when_pgrep_finds_a_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 0, stdout="12345\n", stderr="")

    monkeypatch.setattr(update_sip_archive.subprocess, "run", fake_run)
    with pytest.raises(UpdateLockedError, match="fetch_sip_universe.py is active"):
        _refuse_if_bulk_fetch_active()


def test_refuse_if_bulk_fetch_active_when_pgrep_finds_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="")

    monkeypatch.setattr(update_sip_archive.subprocess, "run", fake_run)
    _refuse_if_bulk_fetch_active()  # must not raise
