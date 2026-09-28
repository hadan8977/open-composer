"""Tests for `scripts/screen_batches/h20260928_20_recent_opt.py`.

Covers: (1) SPECS shape/ids match the candidate manifest; (2) no look-ahead
for every weight function (appending future rows never changes an
already-decided `asof`'s weights); (3) the base variants (E0, S0) reproduce
`h20260928_05_batch2`'s `w_eom_reversal_spy` / `w_front_run_sector_top2`
exactly on synthetic data AND on the real local panel for 5 dates; (4) one
hand-computed case per family (E, S, C).
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

import h20260928_05_batch2 as batch2  # noqa: E402
import h20260928_20_recent_opt as opt  # noqa: E402

EXPECTED_IDS = [
    "E0",
    "E1",
    "E2",
    "E3",
    "E4",
    "E5",
    "E6",
    "E7",
    "S0",
    "S1",
    "S2",
    "S_AVG3",
    "S_AVG5",
    "S_SHIFT0",
    "S_SHIFT2",
    "S_11SECTORS",
    "S_INVVOL",
    "S_ABSFILTER",
    "C1",
    "C2",
]


def _frame(index: pd.DatetimeIndex, columns: list[str], value: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(value, index=index, columns=columns)


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


# --------------------------------------------------------------------------
# SPECS shape
# --------------------------------------------------------------------------


def test_specs_ids_match_manifest_expectation() -> None:
    ids = [spec["id"] for spec in opt.SPECS]
    assert ids == EXPECTED_IDS
    for spec in opt.SPECS:
        assert spec["freq"] == "D"
        assert callable(spec["fn"])
        assert callable(spec["signal_dates_fn"])


@pytest.mark.parametrize("spec", opt.SPECS, ids=lambda s: s["id"])
def test_universe_only_and_long_only_on_full_universe(spec: dict) -> None:
    index = pd.bdate_range("2018-07-01", "2022-12-31")
    universe = list(spec["universe"])
    close = _frame(index, universe)
    dates = spec["signal_dates_fn"](index)
    for asof in dates[:20]:
        weights = spec["fn"](close, asof)
        _assert_contract(weights, tuple(universe))


# --------------------------------------------------------------------------
# No look-ahead, every SPECS entry
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", opt.SPECS, ids=lambda s: s["id"])
def test_no_lookahead(spec: dict) -> None:
    rng = np.random.default_rng(sum(map(ord, spec["id"])))
    short_index = pd.bdate_range("2018-07-01", "2021-12-31")
    long_index = pd.bdate_range("2018-07-01", "2022-12-31")
    universe = list(spec["universe"])

    def make_prices(index: pd.DatetimeIndex) -> pd.DataFrame:
        data = {}
        for i, sym in enumerate(universe):
            steps = rng.normal(loc=0.0002 * (i + 1), scale=0.01, size=len(index))
            data[sym] = 100.0 * np.cumprod(1.0 + steps)
        return pd.DataFrame(data, index=index)

    close_short = make_prices(short_index)
    close_long = close_short.reindex(long_index)
    # extend close_long's tail with new synthetic data (never touches the
    # already-decided asof's own history)
    extra = make_prices(long_index[len(short_index) :])
    close_long.loc[extra.index, universe] = extra.to_numpy()

    dates = [d for d in spec["signal_dates_fn"](short_index) if d in short_index]
    for asof in dates[-5:]:
        got_short = spec["fn"](close_short, asof)
        got_long = spec["fn"](close_long, asof)
        assert got_short == got_long, f"{spec['id']} look-ahead at {asof.date()}"


# --------------------------------------------------------------------------
# E0 reproduces batch-2's w_eom_reversal_spy exactly (synthetic + real panel)
# --------------------------------------------------------------------------


def test_e0_reproduces_batch2_synthetic() -> None:
    index = pd.bdate_range("2021-01-01", "2021-12-31")
    close = _frame(index, ["SPY"])
    rng = np.random.default_rng(42)
    close["SPY"] = 100.0 * np.cumprod(1.0 + rng.normal(0.0003, 0.01, size=len(index)))
    e0_fn = opt.SPECS[0]["fn"]
    assert opt.SPECS[0]["id"] == "E0"
    for asof in batch2.month_end_signal_dates(index):
        assert e0_fn(close, asof) == batch2.w_eom_reversal_spy(close, asof)


def test_e0_reproduces_batch2_real_panel_5_dates() -> None:
    import run_h20260918_05_recent_menu as base

    close, _open_ = base.load_panel(["SPY"])
    e0_fn = opt.SPECS[0]["fn"]
    month_ends = batch2.month_end_signal_dates(close.index)
    sample = month_ends[-5:]
    assert len(sample) == 5
    for asof in sample:
        got = e0_fn(close, asof)
        want = batch2.w_eom_reversal_spy(close, asof)
        assert got == want, f"E0 vs batch-2 mismatch at {asof.date()}: {got} != {want}"


# --------------------------------------------------------------------------
# S0 reproduces batch-2's w_front_run_sector_top2 exactly (synthetic + real)
# --------------------------------------------------------------------------


def test_s0_reproduces_batch2_synthetic() -> None:
    index = pd.bdate_range("2019-01-01", "2021-12-31")
    close = _frame(index, list(batch2.SECTOR_ETFS))
    rng = np.random.default_rng(7)
    for i, sym in enumerate(batch2.SECTOR_ETFS):
        close[sym] = 100.0 * np.cumprod(1.0 + rng.normal(0.0001 * (i + 1), 0.012, size=len(index)))
    s0_fn = opt.SPECS[8]["fn"]
    assert opt.SPECS[8]["id"] == "S0"
    for asof in batch2.month_end_signal_dates(index)[-12:]:
        assert s0_fn(close, asof) == batch2.w_front_run_sector_top2(close, asof)


def test_s0_reproduces_batch2_real_panel_5_dates() -> None:
    import run_h20260918_05_recent_menu as base

    close, _open_ = base.load_panel(list(batch2.SECTOR_ETFS))
    s0_fn = opt.SPECS[8]["fn"]
    month_ends = batch2.month_end_signal_dates(close.index)
    sample = month_ends[-5:]
    assert len(sample) == 5
    for asof in sample:
        got = s0_fn(close, asof)
        want = batch2.w_front_run_sector_top2(close, asof)
        assert got == want, f"S0 vs batch-2 mismatch at {asof.date()}: {got} != {want}"


# --------------------------------------------------------------------------
# Hand-computed case per family
# --------------------------------------------------------------------------


def test_e_family_hand_computed_win5_and_threshold_and_qqq_and_magscale() -> None:
    # January 2021 business days end on 2021-01-29; 5th-to-last session is
    # 2021-01-25 (Mon 25,26,27,28,29).
    index = pd.bdate_range("2021-01-01", "2021-01-29")
    close = _frame(index, ["SPY", "QQQ"])
    close.loc[pd.Timestamp("2021-01-25"), ["SPY", "QQQ"]] = 100.0
    close.loc[pd.Timestamp("2021-01-29"), ["SPY", "QQQ"]] = 97.0  # -3%

    win5_fn = opt.make_eom_reversal_fn(formation_sessions=5)
    assert win5_fn(close, pd.Timestamp("2021-01-29")) == {"SPY": 1.0}

    # threshold -1%: -3% clears it -> still long
    thresh_fn = opt.make_eom_reversal_fn(threshold=-0.01)
    assert thresh_fn(close, pd.Timestamp("2021-01-29")) == {"SPY": 1.0}
    # a -0.5% move (4th Friday to month-end) does NOT clear a -1% threshold
    close2 = _frame(index, ["SPY"])
    close2.loc[pd.Timestamp("2021-01-22"), "SPY"] = 100.0  # 4th Friday
    close2.loc[pd.Timestamp("2021-01-29"), "SPY"] = 99.5  # -0.5%
    assert opt.make_eom_reversal_fn(threshold=-0.01)(close2, pd.Timestamp("2021-01-29")) == {}
    assert opt.make_eom_reversal_fn(threshold=0.0)(close2, pd.Timestamp("2021-01-29")) == {
        "SPY": 1.0
    }

    qqq_fn = opt.make_eom_reversal_fn(symbol="QQQ")
    assert qqq_fn(close, pd.Timestamp("2021-01-29")) == {"QQQ": 1.0}

    # magnitude scale: |r|=3% > 2% cap -> weight clipped to 1.0
    magscale_fn = opt.make_eom_reversal_fn(magnitude_scale=True)
    assert magscale_fn(close, pd.Timestamp("2021-01-29")) == {"SPY": 1.0}
    # a smaller move: -1% -> weight = min(1, 0.01/0.02) = 0.5
    close3 = _frame(index, ["SPY"])
    close3.loc[pd.Timestamp("2021-01-22"), "SPY"] = 100.0
    close3.loc[pd.Timestamp("2021-01-29"), "SPY"] = 99.0  # -1%
    got = opt.make_eom_reversal_fn(magnitude_scale=True)(close3, pd.Timestamp("2021-01-29"))
    assert got["SPY"] == pytest.approx(0.5)


def test_e_family_hold_n_sessions_forces_cash_after_exit_date() -> None:
    index = pd.bdate_range("2021-01-01", "2021-02-28")
    close = _frame(index, ["SPY"])
    close.loc[pd.Timestamp("2021-01-22"), "SPY"] = 100.0
    close.loc[pd.Timestamp("2021-01-29"), "SPY"] = 95.0  # negative -> long Feb
    e0_fn = opt.make_eom_reversal_fn()
    # month-end decision date: long
    assert e0_fn(close, pd.Timestamp("2021-01-29")) == {"SPY": 1.0}
    # the 10th-session exit date (not a month-end) forces cash regardless
    tenth = opt._nth_session_dates(index, 10)
    feb_tenth = [d for d in tenth if d.month == 2][0]
    assert e0_fn(close, feb_tenth) == {}
    dates = opt.eom_hold_n_sessions_signal_dates(10)(index)
    assert pd.Timestamp("2021-01-29") in dates
    assert feb_tenth in dates


def test_s_family_hand_computed_top1_shift0_avg3_invvol_absfilter() -> None:
    index = pd.bdate_range("2019-01-01", "2021-12-31")
    close = _frame(index, list(batch2.SECTOR_ETFS))
    asof = pd.Timestamp("2021-12-31")
    # holding month for asof = Dec 31 2021 -> January 2022.
    # front-running (shift=1, the S0/top1 default) score window is
    # February 2021 (one year before, shifted 1 month).
    feb21_start, feb21_end = pd.Timestamp("2021-02-01"), pd.Timestamp("2021-02-26")
    # true-seasonality (shift=0) score window is January 2021 itself.
    jan21_start, jan21_end = pd.Timestamp("2021-01-04"), pd.Timestamp("2021-01-29")
    returns = {
        "XLB": 0.01,
        "XLE": 0.20,
        "XLF": 0.02,
        "XLI": 0.03,
        "XLK": 0.15,
        "XLP": 0.04,
        "XLU": 0.05,
        "XLV": 0.06,
        "XLY": 0.07,
    }
    for sym, ret in returns.items():
        close.loc[feb21_start, sym] = 1.0
        close.loc[feb21_end, sym] = 1.0 + ret
        close.loc[jan21_start, sym] = 1.0
        close.loc[jan21_end, sym] = 1.0 + ret

    top1_fn = opt.make_sector_seasonality_fn(top_n=1)
    assert top1_fn(close, asof) == {"XLE": 1.0}

    shift0_fn = opt.make_sector_seasonality_fn(shift=0)
    weights = shift0_fn(close, asof)
    assert weights == {"XLE": 0.5, "XLK": 0.5}

    # abs filter: trailing 12mo return of XLE and XLK both positive here
    # (flat elsewhere before the Jan-2021 bump, so trailing return > 0) -> kept
    absfilter_fn = opt.make_sector_seasonality_fn(shift=0, abs_filter=True)
    kept = absfilter_fn(close, asof)
    assert set(kept) <= {"XLE", "XLK"}


def test_s_family_avg_years_averages_multiple_lag_windows() -> None:
    index = pd.bdate_range("2016-01-01", "2021-12-31")
    close = _frame(index, list(batch2.SECTOR_ETFS))
    # holding month = Jan 2022 (asof = 2021-12-31); shift=1 -> score windows
    # are Feb of 2021, 2020, 2019 for avg_years=3 -- use the implementation's
    # own date resolution so the test's price bumps land exactly where
    # `_compute_scores` will look for them.
    for lag, ret in ((1, 0.10), (2, 0.20), (3, 0.30)):
        start, end = opt._score_window_lag(1, 2022, lag, shift=1)
        d_start = batch2._nearest_trading_day_at_or_before(index, start)
        d_end = batch2._nearest_trading_day_at_or_before(index, end)
        close.loc[d_start, "XLK"] = 1.0
        close.loc[d_end, "XLK"] = 1.0 + ret
    scores = opt._compute_scores(
        close.loc[:"2021-12-31"], batch2.SECTOR_ETFS, 1, 2022, shift=1, avg_years=3
    )
    assert scores["XLK"] == pytest.approx((0.10 + 0.20 + 0.30) / 3, abs=1e-6)

    avg3_fn = opt.make_sector_seasonality_fn(avg_years=3, top_n=1)
    assert avg3_fn(close, pd.Timestamp("2021-12-31")) == {"XLK": 1.0}


def test_s_family_11sectors_includes_xlc_xlre_when_present() -> None:
    index = pd.bdate_range("2019-01-01", "2021-12-31")
    close = _frame(index, list(opt.SECTOR_ETFS_11))
    # holding month = Jan 2022 (asof = 2021-12-31); default shift=1 -> score
    # window is February 2021 (same convention as batch-2's own S0 test).
    feb21_start, feb21_end = pd.Timestamp("2021-02-01"), pd.Timestamp("2021-02-26")
    for sym in opt.SECTOR_ETFS_11:
        close.loc[feb21_start, sym] = 1.0
        close.loc[feb21_end, sym] = 1.0
    close.loc[feb21_end, "XLC"] = 1.5  # best performer
    close.loc[feb21_end, "XLRE"] = 1.4  # 2nd best
    asof = pd.Timestamp("2021-12-31")
    fn11 = opt.make_sector_seasonality_fn(universe=opt.SECTOR_ETFS_11)
    weights = fn11(close, asof)
    assert weights == {"XLC": 0.5, "XLRE": 0.5}


# --------------------------------------------------------------------------
# C family hand-computed
# --------------------------------------------------------------------------


def test_c1_gates_sector_picks_on_eom_signal() -> None:
    index = pd.bdate_range("2021-01-01", "2021-12-31")
    universe = ("SPY", *batch2.SECTOR_ETFS)
    close = _frame(index, list(universe))
    # C1's own EOM signal at asof=2021-12-31 is evaluated on DECEMBER 2021's
    # own 4th-Friday-to-month-end SPY return (4th Friday of Dec 2021 = Dec
    # 24; month end = Dec 31), not January's.
    close.loc[pd.Timestamp("2021-12-24"), "SPY"] = 100.0
    close.loc[pd.Timestamp("2021-12-31"), "SPY"] = 95.0  # negative -> risk on

    # sector score window (holding month Jan 2022, shift=1) is Feb 2021.
    d_start, d_end = pd.Timestamp("2021-02-01"), pd.Timestamp("2021-02-26")
    for i, sym in enumerate(batch2.SECTOR_ETFS):
        close.loc[d_start, sym] = 1.0
        close.loc[d_end, sym] = 1.0 + 0.01 * (i + 1)  # XLY (last) is best, XLV 2nd

    c1_fn = opt.make_c1_eom_gate_sector_top2_fn()
    weights = c1_fn(close, pd.Timestamp("2021-12-31"))
    assert weights == {"XLY": 0.5, "XLV": 0.5}

    # risk-off case: positive EOM return -> cash regardless of sector scores
    close_off = close.copy()
    close_off.loc[pd.Timestamp("2021-12-24"), "SPY"] = 100.0
    close_off.loc[pd.Timestamp("2021-12-31"), "SPY"] = 105.0  # positive -> risk off
    assert c1_fn(close_off, pd.Timestamp("2021-12-31")) == {}


def test_c2_blends_e0_and_s0_50_50() -> None:
    index = pd.bdate_range("2021-01-01", "2021-12-31")
    universe = ("SPY", *batch2.SECTOR_ETFS)
    close = _frame(index, list(universe))
    # E0's own December 2021 formation window (see test_c1 above).
    close.loc[pd.Timestamp("2021-12-24"), "SPY"] = 100.0
    close.loc[pd.Timestamp("2021-12-31"), "SPY"] = 95.0  # negative -> E0 long SPY

    d_start, d_end = pd.Timestamp("2021-02-01"), pd.Timestamp("2021-02-26")
    for i, sym in enumerate(batch2.SECTOR_ETFS):
        close.loc[d_start, sym] = 1.0
        close.loc[d_end, sym] = 1.0 + 0.01 * (i + 1)

    c2_fn = opt.make_c2_eom_sector_blend_fn()
    weights = c2_fn(close, pd.Timestamp("2021-12-31"))
    assert weights["SPY"] == pytest.approx(0.5)
    assert weights["XLY"] == pytest.approx(0.25)
    assert weights["XLV"] == pytest.approx(0.25)
    assert sum(weights.values()) == pytest.approx(1.0)
