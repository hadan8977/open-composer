from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import polars as pl

from open_composer.research.features import price_hygiene as ph
from scripts import run_t20260929_32_gap_fade_ls as parent
from scripts import run_t20260930_12_smallcap_gap_auction as s


def _bars(day: str, tz_offset_h: int, minutes_et: list[tuple[int, int]]) -> pl.DataFrame:
    """Minute bars for one symbol; ``tz_offset_h`` is the ET->UTC shift (4 in EDT, 5 in EST)."""
    rows = []
    for i, (h, m) in enumerate(minutes_et):
        ts = datetime.fromisoformat(f"{day}T{h:02d}:{m:02d}:00").replace(tzinfo=UTC)
        ts = ts.replace(hour=(h + tz_offset_h) % 24)
        rows.append({"symbol": "AAA", "timestamp": ts, "close": 10.0 + i, "volume": 100.0})
    return pl.DataFrame(rows).with_columns(pl.col("timestamp").dt.cast_time_unit("ns"))


def _check_cutoffs(day: str, offset: int) -> None:
    mins = [(4, 0), (9, 10), (9, 11), (9, 12), (9, 26), (9, 27), (9, 30), (15, 59), (16, 0)]
    out = s.premarket_aggregate(_bars(day, offset, mins))
    assert out.height == 1
    r = out.row(0, named=True)
    assert r["x15"] == 12.0  # the 09:11 bar (index 2) is in, the 09:12 bar is out
    assert r["x0"] == 14.0  # the 09:26 bar (index 4) is in, the 09:27 bar is out
    assert r["pm_n"] == 3  # 04:00, 09:10, 09:11
    assert r["last_reg_close"] == 17.0  # 15:59 bar, the 16:00 bar is excluded
    assert r["pm_dv"] == 100.0 * (10 + 11 + 12)


def test_cutoffs_summer_time_edt():
    _check_cutoffs("2025-07-15", 4)


def test_cutoffs_winter_time_est():
    _check_cutoffs("2025-01-15", 5)


def test_cutoffs_dst_switch_days():
    _check_cutoffs("2025-03-10", 4)  # first Monday after the spring switch
    _check_cutoffs("2025-11-03", 5)  # first Monday after the autumn switch


def test_no_premarket_bar_gives_null_price():
    out = s.premarket_aggregate(_bars("2025-07-15", 4, [(9, 12), (9, 30)]))
    r = out.row(0, named=True)
    assert r["x15"] is None and r["pm_n"] == 0
    assert r["x0"] == 10.0


def test_consistency_exclusion():
    prev = np.array([10.0, 10.0, 10.0, 10.0])
    minute = np.array([10.5, 5.0, np.nan, 11.1])
    excl = s.consistency_excluded(prev, minute)
    # +5% ok, -50% mismatch, unknown kept, ln(1.11)=0.104 > 0.10 excluded
    assert excl.tolist() == [False, True, False, True]


def test_placebo_ranks_stay_inside_each_date_pool():
    date_idx = np.array([0] * 12 + [1] * 3 + [3] * 20)
    rank = s.sample_placebo_ranks(date_idx, np.random.default_rng(1))
    for d, n in ((0, 12), (1, 3), (3, 20)):
        assert sorted(rank[date_idx == d].tolist()) == list(range(1, n + 1))
    r = np.arange(len(date_idx), dtype=float)
    ones = np.ones(len(date_idx))
    ser, cnt = s.basket_series(date_idx, 5, r, ones, rank <= 10)
    assert cnt.tolist() == [10, 3, 0, 10, 0]  # dates 2 and 4 are empty -> return 0
    assert ser[2] == 0.0 and ser[4] == 0.0
    # basket mean only uses rows of that date
    assert 12 <= ser[1] <= 14 and ser[0] < 12


def test_newey_west_matches_plain_t_for_iid_and_grows_with_autocorrelation():
    rng = np.random.default_rng(0)
    x = rng.normal(0.001, 0.01, 2000)
    assert abs(s.newey_west_t(x) - s.plain_t(x)) < 0.3
    ar = np.zeros(2000)
    for i in range(1, 2000):
        ar[i] = 0.6 * ar[i - 1] + rng.normal(0, 0.01)
    ar += 0.0005
    assert abs(s.newey_west_t(ar)) < abs(s.plain_t(ar))


def test_sigma21_wide_matches_build_signal_panel_z():
    rng = np.random.default_rng(3)
    idx = pd.bdate_range("2024-01-01", periods=120)
    close = pd.DataFrame(
        20 * np.exp(np.cumsum(rng.normal(0, 0.02, (120, 2)), axis=0)), index=idx, columns=["A", "B"]
    )
    open_ = close.shift(1) * (1 + rng.normal(0, 0.01, (120, 2)))
    open_.iloc[0] = close.iloc[0]
    vol = pd.DataFrame(1e6, index=idx, columns=["A", "B"])
    panel = parent.build_signal_panel(close, open_, vol, filter_split_like=False)
    sig = s.sigma21_wide(close, ph)
    prev = close.shift(1)
    m = panel.copy()
    m["sig"] = parent.lookup_from_wide(sig, m["date"], m["symbol"])
    m["prev"] = parent.lookup_from_wide(prev, m["date"], m["symbol"])
    z_hat = (m["open"] / m["prev"] - 1) / m["sig"]
    assert len(m) > 50
    assert np.allclose(z_hat, m["z"], rtol=1e-9)


def test_after_hours_only_bars_create_no_group():
    # 20:30 ET bar in EDT falls on the next UTC day; it must not create a (symbol, date) row
    out = s.premarket_aggregate(_bars("2025-07-15", 4, [(20, 30), (21, 0)]))
    assert out.height == 0
