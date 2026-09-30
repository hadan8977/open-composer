from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
import pytest

from scripts import run_t20260930_13_intraday_periodicity as m


def _bars(rows: list[tuple[str, str, float]]) -> pl.DataFrame:
    """rows: (symbol, UTC 'YYYY-MM-DD HH:MM', close)."""
    return pl.DataFrame(
        {
            "symbol": [r[0] for r in rows],
            "timestamp": [
                datetime.strptime(r[1], "%Y-%m-%d %H:%M").replace(tzinfo=UTC) for r in rows
            ],
            "close": [r[2] for r in rows],
        },
        schema={
            "symbol": pl.String,
            "timestamp": pl.Datetime("ns", "UTC"),
            "close": pl.Float64,
        },
    )


def _row(df: pl.DataFrame, symbol: str, date: str) -> dict:
    out = df.filter((pl.col("symbol") == symbol) & (pl.col("date").cast(pl.String) == date))
    assert out.height == 1
    return out.to_dicts()[0]


def test_dst_transition_march_and_november() -> None:
    # 2024-03-08 is EST (UTC-5): 09:59 ET = 14:59 UTC.
    # 2024-03-11 is EDT (UTC-4): 09:59 ET = 13:59 UTC.
    # 2024-11-01 is EDT: 15:29 ET = 19:29 UTC.  2024-11-04 is EST: 15:29 ET = 20:29 UTC.
    df = _bars(
        [
            ("A", "2024-03-08 14:59", 10.0),
            ("A", "2024-03-11 13:59", 11.0),
            ("A", "2024-11-01 19:29", 12.0),
            ("A", "2024-11-04 20:29", 13.0),
            # the same UTC clock times one offset later must not be picked up as 09:59 / 15:29
            ("B", "2024-03-11 14:59", 99.0),
            ("B", "2024-11-04 19:29", 98.0),
        ]
    )
    out = m.aggregate_bars(df)
    assert _row(out, "A", "2024-03-08")["p_0959"] == 10.0
    assert _row(out, "A", "2024-03-11")["p_0959"] == 11.0
    assert _row(out, "A", "2024-11-01")["p_1529"] == 12.0
    assert _row(out, "A", "2024-11-04")["p_1529"] == 13.0
    # 14:59 UTC on an EDT day is 10:59 ET, 19:29 UTC on an EST day is 14:29 ET: outside every slot
    assert _row(out, "B", "2024-03-11")["p_0959"] is None
    assert _row(out, "B", "2024-11-04")["p_1529"] is None


def test_slot_rule_last_bar_in_five_minute_window_else_null() -> None:
    # 2024-06-03 is EDT: 09:54 ET = 13:54 UTC ... 09:59 ET = 13:59 UTC, 10:00 ET = 14:00 UTC
    df = _bars(
        [
            ("A", "2024-06-03 13:53", 1.0),  # 09:53 ET, before the window
            ("A", "2024-06-03 13:54", 2.0),  # 09:54 ET, in window
            ("A", "2024-06-03 13:57", 3.0),  # 09:57 ET, in window
            ("A", "2024-06-03 14:00", 4.0),  # 10:00 ET, after the slot end
            ("B", "2024-06-03 13:53", 5.0),  # only an out-of-window bar
            ("B", "2024-06-03 14:00", 6.0),
            # regular closes
            ("A", "2024-06-03 19:59", 7.0),  # 15:59 ET, last regular
            ("A", "2024-06-03 20:00", 8.0),  # 16:00 ET, after-hours, not regular
        ]
    )
    out = m.aggregate_bars(df)
    a = _row(out, "A", "2024-06-03")
    assert a["p_0959"] == 3.0  # the last bar starting in [09:54, 09:59]
    assert a["last_reg_close"] == 7.0
    assert a["n_reg"] == 5
    b = _row(out, "B", "2024-06-03")
    assert b["p_0959"] is None  # missing bar -> NaN, never a stale earlier price


def test_duplicate_bars_are_deduplicated() -> None:
    df = _bars([("A", "2024-06-03 13:59", 3.0), ("A", "2024-06-03 13:59", 3.0)])
    out = m.aggregate_bars(df)
    assert _row(out, "A", "2024-06-03")["n_reg"] == 1


def test_signal_uses_only_sessions_before_t() -> None:
    r = np.full((30, 2), np.nan)
    r[:, 0] = np.arange(30, dtype=float)
    r[:, 1] = 1.0
    r[25, 0] = 1e6  # a spike on session 25 must not enter S(25), only S(26..)
    s1 = m.past_mean_signal(r, 1)
    assert s1[25, 0] == 24.0
    assert s1[26, 0] == 1e6
    assert np.isnan(s1[0, 0])
    s5 = m.past_mean_signal(r, 5)
    assert s5[25, 0] == pytest.approx(np.mean([20, 21, 22, 23, 24]))
    s20 = m.past_mean_signal(r, 20)
    assert np.isnan(s20[10, 0])  # fewer than 16 valid past values
    assert not np.isnan(s20[20, 0])
    # the value at t never changes when r at t and later changes
    r2 = r.copy()
    r2[25:, :] = 123.0
    assert m.past_mean_signal(r2, 20)[25, 0] == m.past_mean_signal(r, 20)[25, 0]


def test_min_obs_is_ceil_of_eighty_percent() -> None:
    assert (m.min_obs(1), m.min_obs(5), m.min_obs(20)) == (1, 4, 16)
    r = np.ones((30, 1))
    r[10:14, 0] = np.nan  # four missing sessions in the last-20 window of t = 20 leaves 16 valid
    assert not np.isnan(m.past_mean_signal(r, 20)[20, 0])
    r[15, 0] = np.nan  # 15 valid -> below 0.8 L
    assert np.isnan(m.past_mean_signal(r, 20)[20, 0])


def _write_shard(path: Path, rows: list[tuple[str, str, float]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = _bars(rows).with_columns(
        open=pl.col("close"),
        high=pl.col("close"),
        low=pl.col("close"),
        volume=pl.lit(1.0),
        trade_count=pl.lit(1.0),
        vwap=pl.col("close"),
    )
    df.write_parquet(path)


def test_two_layouts_2023_merge_and_dedupe(tmp_path: Path) -> None:
    root = tmp_path / "minute"
    # legacy whole-year shard: AAA (only here), OVR (overlaps the month shard on one bar)
    _write_shard(
        root / "2023" / "shard-0000.parquet",
        [
            ("AAA", "2023-09-05 13:59", 10.0),  # 09:59 ET (EDT)
            ("AAA", "2023-09-05 19:29", 11.0),  # 15:29 ET
            ("AAA", "2023-07-05 13:59", 1.0),  # before the extract start month
            ("OVR", "2023-09-05 13:59", 20.0),
            ("OVR", "2023-09-05 13:58", 19.0),
            ("IDN", "2023-09-05 13:59", 40.0),  # identical bar set in both layouts
        ],
    )
    # month-directory shard: BBB (only here), OVR (same 13:59 bar + a new 19:29 bar)
    _write_shard(
        root / "2023" / "09" / "shard-0317.parquet",
        [
            ("BBB", "2023-09-05 13:59", 30.0),
            ("OVR", "2023-09-05 13:59", 20.0),
            ("OVR", "2023-09-05 19:29", 21.0),
            ("IDN", "2023-09-05 13:59", 40.0),
        ],
    )
    symbols = ["AAA", "BBB", "OVR", "IDN"]
    legacy = m.legacy_year_pass(root, 2023, symbols, first_month=8, workers=2)
    assert set(legacy) == {9}  # July rows are dropped by the start month
    out = m.extract_month(root, 2023, 9, symbols, legacy[9], workers=2)
    # exactly one row per (symbol, date)
    assert out.select(pl.struct("symbol", "date").n_unique()).item() == out.height == 4
    src = dict(zip(out["symbol"].to_list(), out["src"].to_list(), strict=True))
    assert src == {"AAA": "legacy", "BBB": "month", "OVR": "both", "IDN": "both"}
    ovr = _row(out, "OVR", "2023-09-05")
    assert ovr["p_0959"] == 20.0  # not double counted, last bar in the slot
    assert ovr["p_1529"] == 21.0  # picked up from the month shard
    assert ovr["n_reg"] == 3  # 13:58, 13:59 (once), 19:29 after dedupe on (symbol, timestamp)
    assert _row(out, "AAA", "2023-09-05")["p_1529"] == 11.0
    idn = _row(out, "IDN", "2023-09-05")
    assert idn["n_reg"] == 1 and idn["p_0959"] == 40.0


def test_legacy_only_symbols_are_not_lost_without_month_rows(tmp_path: Path) -> None:
    root = tmp_path / "minute"
    _write_shard(root / "2023" / "shard-0001.parquet", [("AAPL", "2023-10-02 13:59", 170.0)])
    _write_shard(root / "2023" / "10" / "shard-0317.parquet", [("ZS", "2023-10-02 13:59", 150.0)])
    legacy = m.legacy_year_pass(root, 2023, ["AAPL", "ZS"], first_month=8, workers=1)
    out = m.extract_month(root, 2023, 10, ["AAPL", "ZS"], legacy.get(10), workers=1)
    assert sorted(out["symbol"].to_list()) == ["AAPL", "ZS"]


def test_round_trip_cost_and_stress() -> None:
    # 1x: long h 3 + 4, short h 5 + 4 -> 16 bp
    assert m.round_trip_bp(3.0, 5.0) == pytest.approx(16.0)
    # 2x: continuous 2h + 4 and auction 4 per leg -> 2h + 8 per leg -> 2 * 8 + 16 = 32
    assert m.round_trip_bp(3.0, 5.0, mult=2.0) == pytest.approx(32.0)
    ser = {
        "gross": np.array([0.0020]),
        "h_long_bp": np.array([3.0]),
        "h_short_bp": np.array([5.0]),
    }
    nets = m.net_variants(ser)
    assert nets["_rt1_bp"][0] == pytest.approx(16.0)
    assert nets["rt1"][0] == pytest.approx(0.0020 - 16.0 / 1e4)
    assert nets["rt2"][0] == pytest.approx(0.0020 - 32.0 / 1e4)
    assert nets["frozen_10"][0] == pytest.approx(0.0020 - 40.0 / 1e4)
    assert nets["frozen_20"][0] == pytest.approx(0.0020 - 80.0 / 1e4)


def test_tier_boundaries() -> None:
    rt1 = 16.0
    ok = {"t_nw": 2.5, "beat": 0.95}
    assert m.tier_from_stats(15.99, rt1_bp=rt1, **ok) == "closed"
    assert m.tier_from_stats(16.0, rt1_bp=rt1, **ok) == "marginal"
    assert m.tier_from_stats(31.99, rt1_bp=rt1, **ok) == "marginal"
    assert m.tier_from_stats(32.0, rt1_bp=rt1, **ok) == "pass"
    # t and beat gates are inclusive at 2.0 and 0.90, exclusive below
    assert m.tier_from_stats(40.0, 2.0, 0.90, rt1) == "pass"
    assert m.tier_from_stats(40.0, 1.99, 0.90, rt1) == "closed"
    assert m.tier_from_stats(40.0, 2.0, 0.89, rt1) == "closed"
    assert m.tier_from_stats(float("nan"), 3.0, 1.0, rt1) == "closed"
    assert m.tier_from_stats(40.0, 3.0, 1.0, float("nan")) == "closed"


def test_consistency_exclusion() -> None:
    daily = np.array([100.0, 100.0, 100.0, 100.0])
    minute = np.array([100.0, 89.0, 111.0, np.nan])
    got = m.consistency_excluded(daily, minute)
    # |ln(89/100)| = 0.1165 > 0.10, |ln(111/100)| = 0.1044 > 0.10, NaN is not excluded
    assert got.tolist() == [False, True, True, False]


def test_books_short_leg_is_easy_to_borrow_and_disjoint() -> None:
    sig = np.linspace(-1.0, 1.0, 100)
    elig = np.ones(100, dtype=bool)
    elig[:10] = False  # the ten lowest-signal names are hard to borrow
    li, si = m.select_books(sig, elig)
    assert len(li) == len(si) == 10
    assert set(li) == set(range(90, 100))
    assert set(si) == set(range(10, 20))  # lowest eligible
    # too few eligible names -> no book
    assert m.select_books(sig, np.zeros(100, dtype=bool)) is None
    # fewer than 50 valid names -> legs below the minimum size
    assert m.select_books(sig[:40], np.ones(40, dtype=bool)) is None


def test_run_series_and_placebo_shapes() -> None:
    rng = np.random.default_rng(0)
    n_dates, n_sym = 6, 200
    sig = rng.normal(size=(n_dates, n_sym))
    ret = 0.001 * sig + rng.normal(scale=0.001, size=(n_dates, n_sym))  # perfectly informative-ish
    pool = np.ones((n_dates, n_sym), dtype=bool)
    elig = np.ones((n_dates, n_sym), dtype=bool)
    spread_bp = np.full((n_dates, n_sym), 10.0)
    keep: dict = {}
    ser = m.run_series(sig, ret, pool, elig, spread_bp, keep)
    assert np.isfinite(ser["gross"]).all()
    assert (ser["k"] == 20).all()
    assert ser["h_long_bp"][0] == pytest.approx(5.0)  # 0.5 * 10
    assert (ser["gross"] > 0).all()
    pl_series = m.placebo_gross(keep, n_dates, 0)
    assert np.isfinite(pl_series).all()
    assert np.abs(pl_series).mean() < np.abs(ser["gross"]).mean()


def test_window_block_placebo_beat_and_costs() -> None:
    index = pd.bdate_range("2024-01-08", periods=30)
    n = len(index)
    ser = {
        "gross": np.full(n, 0.0040),
        "long": np.full(n, 0.0025),
        "short": np.full(n, -0.0015),
        "h_long_bp": np.full(n, 4.0),
        "h_short_bp": np.full(n, 6.0),
        "k": np.full(n, 20.0),
        "n_valid": np.full(n, 200.0),
        "pool_ew": np.full(n, 0.0005),
        "h_pool_bp": np.full(n, 3.0),
    }
    placebo = np.zeros((m.N_SEEDS, n))
    blk = m.window_block(index, ser, placebo)
    main = blk["main"]
    assert main["mean_bp"] == pytest.approx(40.0)
    assert main["rt1_bp"] == pytest.approx(18.0)
    assert main["placebo_beat"] == 1.0
    assert main["net"]["rt1"]["mean_bp"] == pytest.approx(22.0)
    assert m.tier_from_stats(main["mean_bp"], 3.0, main["placebo_beat"], main["rt1_bp"]) == "pass"


def test_cost_sensitivity_breakeven() -> None:
    cs = m.cost_sensitivity(17.0)
    assert cs["breakeven_h_bp_1x"] == pytest.approx(4.5)  # 2h + 8 = 17
    assert cs["breakeven_h_bp_2x"] == pytest.approx(0.25)  # 4h + 16 = 17
    assert cs["net_bp_1x"]["5"] == pytest.approx(-1.0)
