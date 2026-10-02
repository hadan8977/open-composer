"""Tests for the precision tolerance mode of scripts/verify_sip_repair.py (T-20261002-01)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "verify_sip_repair.py"
spec = importlib.util.spec_from_file_location("verify_sip_repair", SCRIPT)
assert spec and spec.loader
verify = importlib.util.module_from_spec(spec)
sys.modules["verify_sip_repair"] = verify
spec.loader.exec_module(verify)


def make_frame(
    symbol: str,
    dates: pd.DatetimeIndex,
    close: np.ndarray,
    *,
    open_: np.ndarray | None = None,
    volume: np.ndarray | None = None,
) -> pd.DataFrame:
    open_ = close * 0.998 if open_ is None else open_
    volume = np.full(len(dates), 1000.0) if volume is None else volume
    return pd.DataFrame(
        {
            "symbol": symbol,
            "timestamp": dates,
            "open": np.round(open_, 2),
            "high": close * 1.01,
            "low": close * 0.99,
            "close": np.round(close, 2),
            "volume": volume,
            "trade_count": 10,
            "vwap": close,
        }
    )


def base_series(n: int = 12) -> tuple[pd.DatetimeIndex, np.ndarray]:
    dates = pd.bdate_range("2024-03-04", periods=n, tz="UTC") + pd.Timedelta(hours=5)
    close = 20.0 + np.sin(np.arange(n)) * 0.7
    return dates, close


def counts(events: list[dict]) -> dict[str, int]:
    out: dict[str, int] = {}
    for event in events:
        out[event["class"]] = out.get(event["class"], 0) + 1
    return out


def test_price_decimals_picks_smallest_fit() -> None:
    got = verify.price_decimals(np.array([22.63, 22.635, 22.6351, 22.6, 10.0, 0.0123]))
    assert got.tolist() == [2, 3, 4, 2, 2, 4]


def test_precision_tolerance_sums_half_unit_over_four_prices() -> None:
    p = np.array([20.0])
    expected = 1e-6 + 4 * 0.5 * 1e-2 / 20.0
    assert verify.precision_tolerance(p, p, p, p)[0] == pytest.approx(expected)
    q = np.array([2.5551])  # needs 4 decimals
    assert verify.precision_tolerance(q)[0] == pytest.approx(1e-6 + 0.5e-4 / 2.5551)


def test_identical_and_cent_rounding_noise_are_not_events() -> None:
    dates, close = base_series()
    before = make_frame("AAA", dates, close)
    nudged = close + np.where(np.arange(len(close)) % 2 == 0, 0.004, -0.004)
    after = make_frame("AAA", dates, nudged, open_=close * 0.998 + 0.003)
    assert verify.compare_symbol_precision(before, before.copy())["events"] == []
    assert verify.compare_symbol_precision(before, after)["events"] == []


def test_date_set_difference_is_classified_first() -> None:
    dates, close = base_series()
    before = make_frame("AAA", dates, close)
    after = make_frame("AAA", dates, close * np.where(np.arange(len(close)) >= 6, 0.97, 1.0))
    after = after[after["timestamp"] != dates[5]]
    events = verify.compare_symbol_precision(before, after)["events"]
    assert counts(events) == {"date_set": 1}
    assert events[0]["date"] == dates[6].strftime("%Y-%m-%d")


def test_bar_correction_when_volume_changed_that_day() -> None:
    dates, close = base_series()
    before = make_frame("AAA", dates, close)
    shifted = close.copy()
    shifted[7] *= 1.05
    volume = np.full(len(dates), 1000.0)
    volume[7] = 3000.0
    after = make_frame("AAA", dates, shifted, open_=close * 0.998, volume=volume)
    events = verify.compare_symbol_precision(before, after)["events"]
    assert set(counts(events)) == {"bar_correction"}


def test_factor_revision_moves_open_and_close_by_the_same_amount() -> None:
    dates, close = base_series()
    before = make_frame("AAA", dates, close)
    factor = np.where(np.arange(len(close)) >= 6, 0.99, 1.0)
    after = make_frame("AAA", dates, close * factor, open_=close * 0.998 * factor)
    events = verify.compare_symbol_precision(before, after)["events"]
    assert counts(events) == {"factor_revision": 1}


def test_unexplained_when_only_one_field_moves() -> None:
    dates, close = base_series()
    before = make_frame("AAA", dates, close)
    moved = close.copy()
    moved[8] *= 1.04
    after = make_frame("AAA", dates, moved, open_=close * 0.998)
    events = verify.compare_symbol_precision(before, after)["events"]
    assert set(counts(events)) == {"unexplained"}


def test_year_boundary_event_is_flagged() -> None:
    dates = pd.bdate_range("2025-12-24", periods=10, tz="UTC") + pd.Timedelta(hours=5)
    close = 20.0 + np.sin(np.arange(10)) * 0.7
    before = make_frame("AAA", dates, close)
    moved = close.copy()
    first_2026 = int(np.argmax(dates.year == 2026))
    moved[first_2026] *= 1.03
    after = make_frame("AAA", dates, moved, open_=close * 0.998)
    events = verify.compare_symbol_precision(before, after)["events"]
    assert any(event["year_boundary"] for event in events)


def test_sample_v4_ignores_the_refetch_window_but_counts_it() -> None:
    dates, close = base_series(8)
    before = make_frame("BBB", dates, close)
    after = before.copy()
    after.loc[after.index[-1], "volume"] = 1234.0
    start = pd.Timestamp(dates[-2].tz_localize(None).normalize())
    result = verify.compare_sample_precision(before, after, start)
    assert result["identical_before_window"] is True
    assert result["window_diff"]["volume"] == 1
    after.loc[after.index[2], "close"] = 99.0
    assert verify.compare_sample_precision(before, after, start)["identical_before_window"] is False


def write_tree(root: Path, frames: dict[int, pd.DataFrame]) -> None:
    for year, frame in frames.items():
        year_dir = root / str(year)
        year_dir.mkdir(parents=True)
        frame.to_parquet(year_dir / "shard-0000.parquet")


def test_scan_and_acceptance_end_to_end(tmp_path: Path) -> None:
    dates = pd.bdate_range("2025-12-22", periods=14, tz="UTC") + pd.Timedelta(hours=5)
    close = 20.0 + np.sin(np.arange(14)) * 0.7
    rest = make_frame("AAA", dates, close)
    other = make_frame("BBB", dates, close * 2)
    before_all = pd.concat([rest, other], ignore_index=True)
    # vendor rebased AAA by 0.99 in every year (a pure factor: returns unchanged)
    after_all = before_all.copy()
    mask = after_all["symbol"] == "AAA"
    for column in ("open", "high", "low", "close"):
        after_all.loc[mask, column] = after_all.loc[mask, column] * 0.99
    year = before_all["timestamp"].dt.year

    def split(frame: pd.DataFrame) -> dict[int, pd.DataFrame]:
        return {y: frame[year == y].reset_index(drop=True) for y in (2025, 2026)}

    before_root, after_root = tmp_path / "before", tmp_path / "after"
    write_tree(before_root, split(before_all))
    write_tree(after_root, split(after_all))
    args = SimpleNamespace(before=before_root, after=after_root)
    last, start = verify.archive_window_start(after_root)
    assert last == pd.Timestamp("2026-01-08")
    assert start == pd.Timestamp("2026-01-06")
    scan = verify.scan_shards_precision(
        args, ["shard-0000.parquet"], restated={"AAA"}, sample={"BBB"}, window_start=start
    )
    merged = verify.merge_precision_scans([scan])
    result = verify.precision_result(merged, restated_n=1, sample=["BBB"], sample_size=1)
    # 0.99 rebase moves prices by ~0.2 cents on a 20 dollar stock: rounding noise at most
    assert result["v2p_unexplained"] == 0
    assert result["v4p_identical_before_window"] is True
    assert result["v1p_restated_symbols_checked"] == 1
    assert result["v1p_unexplained_symbols"] <= 1  # limit is int(0.01 * 1) == 0
    assert result["verify_v2_pass"] == (result["v1p_unexplained_symbols"] == 0)


def test_acceptance_limits_fail_closed() -> None:
    merged = {
        "rows": {"date_set": 0, "bar_correction": 0, "factor_revision": 0, "unexplained": 3},
        "symbols": {
            "date_set": [],
            "bar_correction": [],
            "factor_revision": [],
            "unexplained": ["A", "B", "C"],
        },
        "unexplained_by_symbol": {"A": 1, "B": 1, "C": 1},
        "samples": {k: [] for k in verify.PRECISION_CLASSES},
        "v2p_rows": {"date_set": 0, "bar_correction": 0, "factor_revision": 0, "unexplained": 0},
        "v2p_unexplained_symbols": [],
        "restated_checked": 100,
        "missing_after": 0,
        "added_after": 0,
        "window_start": "2026-09-29",
        "sample_v4": {
            "S": {"identical_before_window": True, "window_diff": {}, "window_one_sided_rows": 0}
        },
    }
    result = verify.precision_result(merged, restated_n=100, sample=["S"], sample_size=1)
    assert result["v1p_unexplained_symbols"] == 3
    assert result["v1p_unexplained_symbols_limit"] == 1
    assert result["verify_v2_pass"] is False
    merged["symbols"]["unexplained"] = ["A"]
    merged["unexplained_by_symbol"] = {"A": 1}
    assert verify.precision_result(merged, restated_n=100, sample=["S"], sample_size=1)[
        "verify_v2_pass"
    ]
    merged["sample_v4"]["S"]["identical_before_window"] = False
    assert not verify.precision_result(merged, restated_n=100, sample=["S"], sample_size=1)[
        "verify_v2_pass"
    ]
