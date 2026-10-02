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


# ---------------------------------------------------------------------------
# Restatement detection and full-history rewrites (vendor re-based the history)
# ---------------------------------------------------------------------------

DAYS_2025 = ["2025-12-29", "2025-12-30", "2025-12-31"]
DAYS_2026 = [
    "2026-01-02",
    "2026-01-05",
    "2026-01-06",
    "2026-01-07",
    "2026-01-08",
    "2026-01-09",
]
NOW = datetime(2026, 1, 12, tzinfo=UTC)


def _series(values: dict[str, float]) -> list[tuple[str, str, float]]:
    return [("AAPL", day, value) for day, value in values.items()]


class _TruthClient:
    """Fake vendor: returns the rows of ``truth`` between start and end, newest basis."""

    def __init__(self, truth: dict[str, dict[str, float]]) -> None:
        self.truth = truth
        self.calls: list[tuple[tuple[str, ...], datetime, str]] = []

    def fetch(self, data_client, symbols, start, end, kind):
        self.calls.append((tuple(symbols), start, kind))
        rows = [
            (symbol, day, value)
            for symbol in symbols
            for day, value in self.truth.get(symbol, {}).items()
            if start <= pd.Timestamp(day, tz="UTC") <= end
        ]
        if not rows:
            return None
        return _bars_frame(rows)

    def full_history_calls(self) -> list[tuple[tuple[str, ...], datetime, str]]:
        return [call for call in self.calls if call[1].year < 2026]


def _two_year_archive(tmp_path: Path, old: dict[str, dict[str, float]]) -> Path:
    out = tmp_path / "sip"
    for year, days in (("2025", DAYS_2025), ("2026", DAYS_2026)):
        rows = [
            (symbol, day, series[day])
            for symbol, series in old.items()
            for day in days
            if day in series
        ]
        _write_shard(out / "daily" / year / "shard-0000.parquet", rows)
    (out / "daily" / "_LAYOUT.json").write_text(
        json.dumps({"batch_size": 40, "shard_symbols": {"0000": sorted(old)}}), encoding="utf-8"
    )
    return out


def _closes(out: Path, symbol: str) -> pd.Series:
    frames = [
        _read_shard_frame(path) for path in sorted((out / "daily").glob("*/shard-0000.parquet"))
    ]
    frame = pd.concat(frames).sort_values("timestamp")
    frame = frame.loc[frame["symbol"] == symbol]
    return frame.set_index("timestamp")["close"]


def _restatement_lines(out: Path) -> list[dict]:
    path = out / "daily" / "_restatements.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _patch_fetch(monkeypatch: pytest.MonkeyPatch, client: _TruthClient) -> None:
    monkeypatch.setattr(update_sip_archive, "_fetch_batch", client.fetch)


def _drift_series(scale: float = 1.0) -> dict[str, float]:
    days = DAYS_2025 + DAYS_2026
    return {day: round((100.0 + 1.5 * i) * scale, 6) for i, day in enumerate(days)}


def test_detect_restated_symbols_flags_only_changed_symbols() -> None:
    existing = _bars_frame(
        [("AAPL", "2026-01-02", 100.0), ("MSFT", "2026-01-02", 50.0), ("ZZ", "2026-01-02", 5.0)]
    ).reset_index()
    fetched = _bars_frame(
        [("AAPL", "2026-01-02", 99.0), ("MSFT", "2026-01-02", 50.0), ("NEW", "2026-01-02", 7.0)]
    ).reset_index()

    result = update_sip_archive.detect_restated_symbols(existing, fetched)

    assert list(result) == ["AAPL"]
    assert result["AAPL"] == pytest.approx(0.01)
    assert update_sip_archive.detect_restated_symbols(existing.iloc[0:0], fetched) == {}
    assert update_sip_archive.detect_restated_symbols(existing, fetched.iloc[0:0]) == {}


def test_a_dividend_restatement_rewrites_both_years_and_keeps_returns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Old archive: AAPL entirely on the old basis; tonight the vendor serves the
    # whole history x0.99 (an ex-dividend date passed), the tail refetch sees it.
    old_basis = _drift_series()
    new_basis = _drift_series(0.99)
    stored = dict(old_basis)
    msft = {day: 50.0 for day in DAYS_2025 + DAYS_2026}
    out = _two_year_archive(tmp_path, {"AAPL": stored, "MSFT": msft})
    msft_before = _read_shard_frame(out / "daily" / "2026" / "shard-0000.parquet")
    msft_before = msft_before.loc[msft_before["symbol"] == "MSFT"].reset_index(drop=True)
    client = _TruthClient({"AAPL": new_basis, "MSFT": msft})
    _patch_fetch(monkeypatch, client)

    update_existing_shards(
        data_client=object(),
        out=out,
        kind="daily",
        shard_symbols={0: ["AAPL", "MSFT"]},
        now=NOW,
    )

    closes = _closes(out, "AAPL")
    assert closes.round(6).tolist() == pytest.approx([new_basis[d] for d in sorted(new_basis)])
    boundary_new = (
        closes.loc[pd.Timestamp("2026-01-02", tz="UTC")]
        / closes.loc[pd.Timestamp("2025-12-31", tz="UTC")]
    )
    assert boundary_new == pytest.approx(old_basis["2026-01-02"] / old_basis["2025-12-31"])
    msft_after = _read_shard_frame(out / "daily" / "2026" / "shard-0000.parquet")
    msft_after = msft_after.loc[msft_after["symbol"] == "MSFT"].reset_index(drop=True)
    pd.testing.assert_frame_equal(msft_before, msft_after, check_dtype=False)
    lines = _restatement_lines(out)
    assert [line["symbol"] for line in lines] == ["AAPL"]
    assert lines[0]["mode"] == "update"
    assert lines[0]["years_rewritten"] == [2025, 2026]
    assert lines[0]["rows_before"] == lines[0]["rows_after"] == len(old_basis)
    assert lines[0]["rows_without_shard"] == 0
    assert lines[0]["refetch_empty"] is False
    assert lines[0]["max_rel_diff"] == pytest.approx(0.01)


def test_a_split_restatement_leaves_no_half_price_jump(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    days = DAYS_2025 + DAYS_2026
    old = {day: 100.0 for day in days[:-3]} | {day: 50.0 for day in days[-3:]}
    # Old stored rows: unadjusted 100 before the split; the last session is
    # already post-split (50) and the tail window starts one session earlier.
    stored = {day: (100.0 if day != days[-1] else 50.0) for day in days}
    truth = {day: 50.0 for day in days}
    assert old != truth
    out = _two_year_archive(tmp_path, {"AAPL": stored})
    client = _TruthClient({"AAPL": truth})
    _patch_fetch(monkeypatch, client)

    update_existing_shards(
        data_client=object(), out=out, kind="daily", shard_symbols={0: ["AAPL"]}, now=NOW
    )

    ratios = _closes(out, "AAPL").pct_change().dropna() + 1.0
    assert not ((ratios - 0.5).abs() < 0.05).any()
    assert ratios.tolist() == pytest.approx([1.0] * len(ratios))


def test_identical_overlap_does_not_trigger_a_full_history_refetch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = _drift_series()
    out = _two_year_archive(tmp_path, {"AAPL": series})
    client = _TruthClient({"AAPL": series})
    _patch_fetch(monkeypatch, client)

    update_existing_shards(
        data_client=object(), out=out, kind="daily", shard_symbols={0: ["AAPL"]}, now=NOW
    )

    assert client.calls  # the tail window was fetched
    assert client.full_history_calls() == []
    assert _restatement_lines(out) == []


def test_empty_full_history_refetch_keeps_every_old_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_basis = _drift_series()
    stored = dict(old_basis)
    out = _two_year_archive(tmp_path, {"AAPL": stored})
    tail_truth = {day: old_basis[day] * 0.99 for day in DAYS_2026[-3:]}

    def fake_fetch(data_client, symbols, start, end, kind):
        if start.year < 2026:
            return None  # the vendor returns nothing for the long window
        return _bars_frame([("AAPL", day, value) for day, value in tail_truth.items()])

    monkeypatch.setattr(update_sip_archive, "_fetch_batch", fake_fetch)
    update_existing_shards(
        data_client=object(), out=out, kind="daily", shard_symbols={0: ["AAPL"]}, now=NOW
    )

    closes = _closes(out, "AAPL")
    assert len(closes) == len(old_basis)
    for day in DAYS_2025 + DAYS_2026[:3]:
        assert closes.loc[pd.Timestamp(day, tz="UTC")] == pytest.approx(old_basis[day])
    lines = _restatement_lines(out)
    assert len(lines) == 1
    assert lines[0]["refetch_empty"] is True
    assert lines[0]["years_rewritten"] == []
    assert lines[0]["rows_before"] == lines[0]["rows_after"] == len(old_basis)


def test_repair_full_window_rewrites_only_restated_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_basis = _drift_series()
    new_basis = _drift_series(0.5)
    msft = {day: 50.0 for day in DAYS_2025 + DAYS_2026}
    out = _two_year_archive(tmp_path, {"AAPL": old_basis, "MSFT": msft})
    client = _TruthClient({"AAPL": new_basis, "MSFT": msft})
    _patch_fetch(monkeypatch, client)

    records = update_sip_archive.repair_full_window(
        object(), out, {0: ["AAPL", "MSFT"]}, now=NOW, priority=["AAPL"]
    )

    assert [record["symbol"] for record in records] == ["AAPL"]
    assert records[0]["mode"] == "repair"
    assert _closes(out, "AAPL").round(6).tolist() == pytest.approx(
        [new_basis[d] for d in sorted(new_basis)]
    )
    assert _closes(out, "MSFT").tolist() == pytest.approx([50.0] * len(msft))
    year_windows = [call for call in client.calls if call[1] == datetime(2026, 1, 1, tzinfo=UTC)]
    assert len(year_windows) == 1  # one full-year request per shard
    assert _restatement_lines(out)[0]["mode"] == "repair"


def test_symbol_without_a_shard_in_a_year_is_not_added(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_basis = _drift_series()
    out = _two_year_archive(tmp_path, {"AAPL": old_basis})
    (out / "daily" / "2025" / "shard-0000.parquet").unlink()
    _write_shard(out / "daily" / "2025" / "shard-0000.parquet", [("MSFT", "2025-12-31", 9.0)])
    client = _TruthClient({"AAPL": _drift_series(0.5)})
    _patch_fetch(monkeypatch, client)

    records = update_sip_archive.rewrite_full_history(
        object(), out, ["AAPL"], now=NOW, mode="repair"
    )

    assert records[0]["years_rewritten"] == [2026]
    assert records[0]["rows_without_shard"] == len(DAYS_2025)
    assert _read_shard_frame(out / "daily" / "2025" / "shard-0000.parquet")["symbol"].tolist() == [
        "MSFT"
    ]


def test_minute_restatement_is_logged_but_never_rewrites_history(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "sip"
    destination = out / "minute" / "2026" / "09" / "shard-0000.parquet"
    stamps = ["2026-09-10T14:30:00", "2026-09-10T14:31:00", "2026-09-10T14:32:00"]
    _write_shard(destination, [("AAPL", ts, 100.0) for ts in stamps])
    calls: list[datetime] = []

    def fake_fetch(data_client, symbols, start, end, kind):
        calls.append(start)
        return _bars_frame([("AAPL", ts, 99.0) for ts in stamps[1:]])

    monkeypatch.setattr(update_sip_archive, "_fetch_batch", fake_fetch)
    update_existing_shards(
        data_client=object(),
        out=out,
        kind="minute",
        shard_symbols={0: ["AAPL"]},
        now=datetime(2026, 9, 15, tzinfo=UTC),
    )

    rows = _read_shard_frame(destination).sort_values("timestamp")
    assert rows["close"].iloc[0] == pytest.approx(100.0)  # older minute row untouched
    assert all(start.year == 2026 and start.month == 9 for start in calls)
    logged = [
        json.loads(line)
        for line in (out / "minute" / "_restatements.jsonl").read_text().splitlines()
    ]
    assert [item["mode"] for item in logged] == ["minute_detect_only"]
    assert not (out / "daily" / "_restatements.jsonl").exists()


def test_zero_budget_queues_everything_then_the_next_run_drains_the_queue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    old_basis = _drift_series()
    new_basis = _drift_series(0.99)
    out = _two_year_archive(tmp_path, {"AAPL": dict(old_basis)})
    client = _TruthClient({"AAPL": new_basis})
    _patch_fetch(monkeypatch, client)

    update_existing_shards(
        data_client=object(),
        out=out,
        kind="daily",
        shard_symbols={0: ["AAPL"]},
        now=NOW,
        rewrite_budget_min=0,
    )

    assert client.full_history_calls() == []
    pending = [
        json.loads(line)
        for line in (out / "daily" / "_restatements_pending.jsonl").read_text().splitlines()
    ]
    assert [item["symbol"] for item in pending] == ["AAPL"]
    # the tail window was merged anyway: the newest bar is on the new basis
    assert _closes(out, "AAPL").iloc[-1] == pytest.approx(new_basis[DAYS_2026[-1]])
    assert _closes(out, "AAPL").iloc[0] == pytest.approx(old_basis[DAYS_2025[0]])

    update_existing_shards(
        data_client=object(), out=out, kind="daily", shard_symbols={0: ["AAPL"]}, now=NOW
    )

    assert len(client.full_history_calls()) == 1
    assert _closes(out, "AAPL").iloc[0] == pytest.approx(new_basis[DAYS_2025[0]])
    assert (out / "daily" / "_restatements_pending.jsonl").read_text() == ""
    assert [line["symbol"] for line in _restatement_lines(out)] == ["AAPL"]


def test_pending_queue_is_drained_in_sleeve_first_then_alphabetical_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    out = tmp_path / "sip"
    for year in ("2025", "2026"):
        _write_shard(
            out / "daily" / year / "shard-0000.parquet",
            [(s, "2025-12-31" if year == "2025" else "2026-01-02", 10.0) for s in "ABZ"],
        )
    seen: list[tuple[str, ...]] = []

    def fake_fetch(data_client, symbols, start, end, kind):
        seen.append(tuple(symbols))
        return None

    monkeypatch.setattr(update_sip_archive, "_fetch_batch", fake_fetch)

    update_sip_archive.process_restatements(
        object(),
        out,
        {"A": 0.1, "B": 0.1, "Z": 0.1},
        now=NOW,
        budget_min=25,
        priority=["Z"],
    )

    assert seen == [("Z", "A", "B")]
    assert {line["symbol"]: line["refetch_empty"] for line in _restatement_lines(out)} == {
        "Z": True,
        "A": True,
        "B": True,
    }


def test_load_sleeve_symbols_reads_the_four_sleeve_specs() -> None:
    symbols = update_sip_archive.load_sleeve_symbols()
    assert {"SHY", "XLK", "UPRO", "SPY", "QQQ"} <= set(symbols)
