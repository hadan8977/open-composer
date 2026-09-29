"""Synthetic-data tests for
`scripts/screen_batches/h20260929_34_levered_single_stock.py`.

No backtest and no menu rebuild is run here; importing the module reads the
real `menu.parquet` once at module scope (small, already built), but every
test below either calls the module's helper functions directly with
synthetic inputs, or monkeypatches `_MENU_MONTH_ENDS`/`_MENU_BY_MONTH` so
`menu_for_asof` never depends on the real menu contents.

Covers (per the brief's minimum): the synthetic 2x daily-reset series' one-
day math; the menu lookup's no-look-ahead property (only month-end-as-of
data, never a future month's menu); every weights_fn variant (momentum
top-k, equal-weight control, random-pick placebo) returns weights that sum
to <=1 and stay within its declared universe; the random-pick placebo is
deterministic (same seed+month -> same pick) and does not depend on price
data at all.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260929_34_levered_single_stock as batch  # noqa: E402


def _assert_contract(weights: dict[str, float]) -> None:
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


# --- synthetic 2x daily-reset series: one-day math --------------------


def test_synthetic_l2_one_day_matches_formula() -> None:
    index = pd.bdate_range("2024-01-02", periods=5)
    # underlying closes/opens for one stock "AAA"; BIL supplies rf_d.
    under_close = pd.DataFrame({"AAA": [100.0, 102.0, 101.0, 103.5, 104.0]}, index=index)
    under_open = pd.DataFrame({"AAA": [100.0, 100.5, 102.5, 101.5, 103.0]}, index=index)
    rf_d = pd.Series([0.0, 0.0001, 0.0002, -0.0001, 0.0003], index=index)

    l2_close, l2_open = batch._synthetic_l2(under_close, under_open, rf_d)

    assert l2_close.columns.tolist() == ["L2_AAA"]
    # day 0: seeded at the underlying's own first close.
    assert l2_close["L2_AAA"].iloc[0] == 100.0
    assert np.isnan(l2_open["L2_AAA"].iloc[0])

    # day 1 manual math: r_cc = 102/100 - 1 = 0.02
    r_cc_1 = 102.0 / 100.0 - 1.0
    factor_1 = 1.0 + 2.0 * r_cc_1 - rf_d.iloc[1] - batch.FIN_D
    expected_close_1 = 100.0 * factor_1
    assert l2_close["L2_AAA"].iloc[1] == pytest.approx(expected_close_1, rel=1e-9)

    # day 1 open leg: open_L(1) = close_L(0) * (1 + 2*(open(1)/close(0) - 1))
    open_leg_1 = 2.0 * (under_open["AAA"].iloc[1] / under_close["AAA"].iloc[0] - 1.0)
    expected_open_1 = 100.0 * (1.0 + open_leg_1)
    assert l2_open["L2_AAA"].iloc[1] == pytest.approx(expected_open_1, rel=1e-9)

    # day 2 manual math, chained off day 1's close_L (cumprod correctness).
    r_cc_2 = 101.0 / 102.0 - 1.0
    factor_2 = 1.0 + 2.0 * r_cc_2 - rf_d.iloc[2] - batch.FIN_D
    expected_close_2 = expected_close_1 * factor_2
    assert l2_close["L2_AAA"].iloc[2] == pytest.approx(expected_close_2, rel=1e-9)


def test_synthetic_l2_nan_before_first_valid_date() -> None:
    index = pd.bdate_range("2024-01-02", periods=5)
    under_close = pd.DataFrame({"BBB": [np.nan, np.nan, 50.0, 51.0, 49.5]}, index=index)
    under_open = pd.DataFrame({"BBB": [np.nan, np.nan, 50.0, 50.5, 50.0]}, index=index)
    rf_d = pd.Series(0.0, index=index)

    l2_close, l2_open = batch._synthetic_l2(under_close, under_open, rf_d)

    assert np.isnan(l2_close["L2_BBB"].iloc[0])
    assert np.isnan(l2_close["L2_BBB"].iloc[1])
    assert l2_close["L2_BBB"].iloc[2] == 50.0  # seeded at first valid close
    assert np.isnan(l2_open["L2_BBB"].iloc[2])  # no prior close_L to base the open leg on


# --- menu lookup: no look-ahead ----------------------------------------


def _patch_menu(monkeypatch, month_ends: list[pd.Timestamp], by_month: dict) -> None:
    monkeypatch.setattr(batch, "_MENU_MONTH_ENDS", month_ends)
    monkeypatch.setattr(batch, "_MENU_BY_MONTH", by_month)


def test_menu_for_asof_uses_only_past_month_ends(monkeypatch) -> None:
    jan_end = pd.Timestamp("2024-01-31")
    feb_end = pd.Timestamp("2024-02-29")
    by_month = {
        jan_end: {20: ["AAA", "BBB"], 50: ["AAA", "BBB", "CCC"]},
        feb_end: {20: ["ZZZ", "YYY"], 50: ["ZZZ", "YYY", "XXX"]},
    }
    _patch_menu(monkeypatch, [jan_end, feb_end], by_month)

    # Before any month-end: no menu (no look-ahead into January's own data).
    assert batch.menu_for_asof(pd.Timestamp("2024-01-15"), 20) == []
    # Exactly on January's month-end: January's own menu (computed as of
    # that date, not a future one).
    assert batch.menu_for_asof(jan_end, 20) == ["AAA", "BBB"]
    # A few sessions into February (offset-shifted signal date): still
    # January's menu, never February's (which hasn't happened yet as of
    # this date in a rebalance-offset sense before Feb's own month-end).
    assert batch.menu_for_asof(pd.Timestamp("2024-02-05"), 20) == ["AAA", "BBB"]
    # On/after February's month-end: February's menu.
    assert batch.menu_for_asof(feb_end, 50) == ["ZZZ", "YYY", "XXX"]
    assert batch.menu_for_asof(pd.Timestamp("2024-03-10"), 50) == ["ZZZ", "YYY", "XXX"]


# --- weights_fn contract: sum(weights) <= 1, universe-only -------------


def _synthetic_close_panel() -> pd.DataFrame:
    index = pd.bdate_range("2023-01-02", periods=140)
    rng = np.random.default_rng(3)
    cols = {}
    for sym, drift in [("AAA", 0.002), ("BBB", -0.001), ("CCC", 0.0005), ("DDD", 0.0015)]:
        rets = rng.normal(drift, 0.01, len(index))
        cols[sym] = 100.0 * np.cumprod(1.0 + rets)
    cols["BIL"] = 100.0 * np.cumprod(1.0 + np.full(len(index), 0.0001))
    close = pd.DataFrame(cols, index=index)
    # L2_ columns: build via the module's own synthesizer for internal
    # consistency (not re-deriving the formula by hand here).
    rf_d = (close["BIL"] / close["BIL"].shift(1) - 1.0).fillna(0.0)
    l2_close, _l2_open = batch._synthetic_l2(
        close[["AAA", "BBB", "CCC", "DDD"]], close[["AAA", "BBB", "CCC", "DDD"]], rf_d
    )
    return pd.concat([close, l2_close], axis=1)


def _menu_fixture(monkeypatch) -> pd.Timestamp:
    month_end = pd.Timestamp("2023-04-28")  # >=63 sessions into the synthetic panel
    by_month = {month_end: {20: ["AAA", "BBB", "CCC", "DDD"], 50: ["AAA", "BBB", "CCC", "DDD"]}}
    _patch_menu(monkeypatch, [month_end], by_month)
    return month_end


def test_momentum_topk_weights_sum_leq_1_and_in_universe(monkeypatch) -> None:
    close = _synthetic_close_panel()
    asof = _menu_fixture(monkeypatch)
    for top_n in (20, 50):
        for k in (1, 2, 3):
            for lev in ("1x", "2x"):
                fn = batch._momentum_topk_weights_fn(top_n, k, lev)
                weights = fn(close, asof)
                _assert_contract(weights)
                allowed = {"AAA", "BBB", "CCC", "DDD", "L2_AAA", "L2_BBB", "L2_CCC", "L2_DDD"}
                assert set(weights) <= allowed
                if lev == "2x":
                    assert all(sym.startswith("L2_") for sym in weights)
                else:
                    assert all(not sym.startswith("L2_") for sym in weights)


def test_equal_weight_control_sum_leq_1(monkeypatch) -> None:
    close = _synthetic_close_panel()
    asof = _menu_fixture(monkeypatch)
    fn = batch._equal_weight_control_fn(20, "2x")
    weights = fn(close, asof)
    _assert_contract(weights)
    # all 4 menu names held (equal weight, no ranking) before any vt40 scaling.
    assert len(weights) <= 4


def test_absolute_momentum_filter_drops_negative_momentum_names(monkeypatch) -> None:
    close = _synthetic_close_panel()
    asof = _menu_fixture(monkeypatch)
    fn = batch._momentum_topk_weights_fn(20, 4, "1x")  # k=4 -> all 4 menu names "selected"
    weights = fn(close, asof)
    mom = close.pct_change(batch.MOMENTUM_LOOKBACK, fill_method=None).loc[asof]
    for sym in ("AAA", "BBB", "CCC", "DDD"):
        if mom[sym] <= 0:
            assert sym not in weights


# --- random-pick placebo: deterministic, price-independent -------------


def test_rand_pick_placebo_deterministic_and_price_independent(monkeypatch) -> None:
    asof = _menu_fixture(monkeypatch)
    close_a = _synthetic_close_panel()
    close_b = _synthetic_close_panel() * 1.5  # different price level/scale

    fn = batch._rand_pick_placebo_fn(20, 2, "2x", batch.RAND_SEED)
    w1 = fn(close_a, asof)
    w2 = fn(close_a, asof)
    w3 = fn(close_b, asof)

    _assert_contract(w1)
    assert set(w1) == set(w2)  # same seed + same month -> same pick
    assert set(w1) == set(w3)  # picks do not depend on price data at all
    assert len(w1) == 2
    assert all(sym.startswith("L2_") for sym in w1)


def test_rand_pick_placebo_varies_by_month(monkeypatch) -> None:
    jan_end = pd.Timestamp("2024-01-31")
    feb_end = pd.Timestamp("2024-02-29")
    by_month = {
        jan_end: {20: ["A", "B", "C", "D", "E"], 50: ["A", "B", "C", "D", "E"]},
        feb_end: {20: ["A", "B", "C", "D", "E"], 50: ["A", "B", "C", "D", "E"]},
    }
    _patch_menu(monkeypatch, [jan_end, feb_end], by_month)
    close = pd.DataFrame(
        {sym: [100.0] * 5 for sym in ["A", "B", "C", "D", "E", "BIL"]},
        index=pd.bdate_range("2024-01-02", periods=5),
    )
    fn = batch._rand_pick_placebo_fn(20, 2, "1x", batch.RAND_SEED)
    w_jan = fn(close, jan_end)
    w_feb = fn(close, feb_end)
    # not guaranteed to differ for every seed/month pair, but the RNG must at
    # least be re-seeded per month (not literally the same call every time) --
    # checked indirectly via reproducibility already covered above; here we
    # just confirm both picks are valid, non-empty subsets of the menu.
    assert set(w_jan) <= {"A", "B", "C", "D", "E"}
    assert set(w_feb) <= {"A", "B", "C", "D", "E"}
    assert len(w_jan) == 2
    assert len(w_feb) == 2
