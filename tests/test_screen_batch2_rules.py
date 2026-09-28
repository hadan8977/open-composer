"""Synthetic-data tests for `scripts/screen_batches/h20260928_05_batch2.py`.

No backtest is run here -- these are unit tests of the pure weight functions
against hand-computed cases, plus the generic contract checks the iteration
brief requires: long-only, sum(weights) <= 1, only universe tickers appear,
and no look-ahead (appending future rows never changes an already-decided
`asof`'s weights).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_05_batch2 as batch2  # noqa: E402


def _frame(index: pd.DatetimeIndex, columns: list[str], value: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(value, index=index, columns=columns)


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


# --------------------------------------------------------------------------
# SPECS shape
# --------------------------------------------------------------------------


def test_specs_ids_and_shape_match_manifest_expectation() -> None:
    ids = [spec["id"] for spec in batch2.SPECS]
    assert ids == [
        "HFEA_UPRO_TMF",
        "TOM_SPY",
        "EOM_REVERSAL_SPY",
        "FRONT_RUN_SECTOR_TOP2",
        "FOMC_DRIFT_SPY",
        "FOMC_DRIFT_TQQQ",
        "XYLD_COVERED_CALL_PROXY",
    ]
    for spec in batch2.SPECS:
        assert spec["freq"] in ("M", "W", "D")
        assert callable(spec["fn"])
        if spec["freq"] == "D":
            assert callable(spec.get("signal_dates_fn"))
        else:
            assert "signal_dates_fn" not in spec


# --------------------------------------------------------------------------
# HFEA_UPRO_TMF
# --------------------------------------------------------------------------


def test_hfea_fixed_weights_hand_computed() -> None:
    index = pd.bdate_range("2021-01-04", "2021-01-08")
    close = _frame(index, ["UPRO", "TMF"])
    weights = batch2.w_hfea_upro_tmf(close, index[-1])
    assert weights == {"UPRO": 0.55, "TMF": 0.45}
    _assert_contract(weights, ("UPRO", "TMF"))


def test_hfea_returns_cash_before_history_exists() -> None:
    index = pd.bdate_range("2021-01-04", "2021-01-08")
    close = pd.DataFrame({"UPRO": [np.nan] * len(index), "TMF": [100.0] * len(index)}, index=index)
    assert batch2.w_hfea_upro_tmf(close, index[-1]) == {}


# --------------------------------------------------------------------------
# TOM_SPY
# --------------------------------------------------------------------------


def test_tom_signal_dates_hand_computed_january_2021() -> None:
    index = pd.bdate_range("2021-01-01", "2021-04-30")
    dates = batch2.tom_signal_dates(index)
    # January 2021 business days: 1,4,5,6,7,8,...,29 -- 4th trading day is
    # Jan 6 (1=Fri,4=Mon,5=Tue,6=Wed); month-end trading day is Jan 29 (Fri).
    assert pd.Timestamp("2021-01-06") in dates
    assert pd.Timestamp("2021-01-29") in dates


def test_tom_weights_hand_computed() -> None:
    index = pd.bdate_range("2021-01-01", "2021-04-30")
    close = _frame(index, ["SPY"])
    assert batch2.w_tom_spy(close, pd.Timestamp("2021-01-29")) == {"SPY": 1.0}
    assert batch2.w_tom_spy(close, pd.Timestamp("2021-01-06")) == {}
    assert batch2.w_tom_spy(close, pd.Timestamp("2021-01-15")) == {}


def test_tom_no_lookahead() -> None:
    short_index = pd.bdate_range("2021-01-01", "2021-01-29")
    long_index = pd.bdate_range("2021-01-01", "2021-04-30")
    asof = pd.Timestamp("2021-01-29")
    close_short = _frame(short_index, ["SPY"])
    close_long = _frame(long_index, ["SPY"])
    assert batch2.w_tom_spy(close_short, asof) == batch2.w_tom_spy(close_long, asof)


# --------------------------------------------------------------------------
# EOM_REVERSAL_SPY
# --------------------------------------------------------------------------


def test_eom_reversal_negative_return_hand_computed() -> None:
    # January 2021: 4th Friday = Jan 22; month-end trading day = Jan 29.
    index = pd.bdate_range("2021-01-01", "2021-01-29")
    close = _frame(index, ["SPY"])
    close.loc[pd.Timestamp("2021-01-22"), "SPY"] = 100.0
    close.loc[pd.Timestamp("2021-01-29"), "SPY"] = 95.0  # -5%: negative -> long
    weights = batch2.w_eom_reversal_spy(close, pd.Timestamp("2021-01-29"))
    assert weights == {"SPY": 1.0}
    _assert_contract(weights, ("SPY",))


def test_eom_reversal_positive_return_hand_computed() -> None:
    index = pd.bdate_range("2021-01-01", "2021-01-29")
    close = _frame(index, ["SPY"])
    close.loc[pd.Timestamp("2021-01-22"), "SPY"] = 100.0
    close.loc[pd.Timestamp("2021-01-29"), "SPY"] = 105.0  # +5%: positive -> cash
    assert batch2.w_eom_reversal_spy(close, pd.Timestamp("2021-01-29")) == {}


def test_eom_reversal_not_a_month_end_returns_cash() -> None:
    index = pd.bdate_range("2021-01-01", "2021-01-29")
    close = _frame(index, ["SPY"])
    assert batch2.w_eom_reversal_spy(close, pd.Timestamp("2021-01-15")) == {}


# --------------------------------------------------------------------------
# FRONT_RUN_SECTOR_TOP2
# --------------------------------------------------------------------------


def test_front_run_sector_top2_hand_computed() -> None:
    index = pd.bdate_range("2021-01-01", "2021-12-31")
    close = _frame(index, list(batch2.SECTOR_ETFS))
    # holding month for asof = Dec 31 2021 -> January 2022; score window is
    # February 2021 (one year before January 2022's own prior January).
    d_start = pd.Timestamp("2021-02-01")  # Monday, a business day
    d_end = pd.Timestamp("2021-02-26")  # last business day on/before Feb 28 (Sun)
    returns = {
        "XLB": 0.01,
        "XLE": 0.15,
        "XLF": 0.02,
        "XLI": 0.03,
        "XLK": 0.20,
        "XLP": 0.04,
        "XLU": 0.05,
        "XLV": 0.06,
        "XLY": 0.07,
    }
    for sym, ret in returns.items():
        close.loc[d_start, sym] = 1.0
        close.loc[d_end, sym] = 1.0 + ret
    asof = pd.Timestamp("2021-12-31")
    weights = batch2.w_front_run_sector_top2(close, asof)
    assert weights == {"XLK": 0.5, "XLE": 0.5}
    _assert_contract(weights, batch2.SECTOR_ETFS)


def test_front_run_sector_top2_not_month_end_returns_cash() -> None:
    index = pd.bdate_range("2021-01-01", "2021-12-31")
    close = _frame(index, list(batch2.SECTOR_ETFS))
    assert batch2.w_front_run_sector_top2(close, pd.Timestamp("2021-12-15")) == {}


def test_front_run_sector_top2_no_lookahead() -> None:
    short_index = pd.bdate_range("2021-01-01", "2021-12-31")
    long_index = pd.bdate_range("2021-01-01", "2022-06-30")
    close_short = _frame(short_index, list(batch2.SECTOR_ETFS))
    close_long = _frame(long_index, list(batch2.SECTOR_ETFS))
    d_start, d_end = pd.Timestamp("2021-02-01"), pd.Timestamp("2021-02-26")
    for frame in (close_short, close_long):
        for i, sym in enumerate(batch2.SECTOR_ETFS):
            frame.loc[d_start, sym] = 1.0
            frame.loc[d_end, sym] = 1.0 + 0.01 * (i + 1)
    asof = pd.Timestamp("2021-12-31")
    assert batch2.w_front_run_sector_top2(close_short, asof) == batch2.w_front_run_sector_top2(
        close_long, asof
    )


# --------------------------------------------------------------------------
# FOMC_DRIFT_SPY / FOMC_DRIFT_TQQQ
# --------------------------------------------------------------------------


def test_fomc_entry_and_exit_dates_hand_computed() -> None:
    index = pd.bdate_range("2021-01-01", "2021-02-15")
    entries = batch2.fomc_entry_dates(index)
    exits = batch2.fomc_exit_dates(index)
    # Meeting 2021-01-26/27: entry = last trading day before Jan 26 (Tue) ->
    # Jan 25 (Mon); exit = on/before Jan 27 (Wed) -> Jan 27 itself.
    assert pd.Timestamp("2021-01-25") in entries
    assert pd.Timestamp("2021-01-27") in exits


def test_fomc_drift_weights_hand_computed() -> None:
    index = pd.bdate_range("2021-01-01", "2021-02-15")
    close = _frame(index, ["SPY", "TQQQ"])
    assert batch2.w_fomc_drift_spy(close, pd.Timestamp("2021-01-25")) == {"SPY": 1.0}
    assert batch2.w_fomc_drift_spy(close, pd.Timestamp("2021-01-20")) == {}
    assert batch2.w_fomc_drift_tqqq(close, pd.Timestamp("2021-01-25")) == {"TQQQ": 1.0}
    weights = batch2.w_fomc_drift_spy(close, pd.Timestamp("2021-01-25"))
    _assert_contract(weights, ("SPY",))


def test_fomc_meetings_all_start_on_or_before_end() -> None:
    from datetime import date

    for start, end in batch2.FOMC_MEETINGS:
        assert date.fromisoformat(start) <= date.fromisoformat(end)


def test_fomc_drift_no_lookahead() -> None:
    short_index = pd.bdate_range("2021-01-01", "2021-01-25")
    long_index = pd.bdate_range("2021-01-01", "2021-02-15")
    asof = pd.Timestamp("2021-01-25")
    close_short = _frame(short_index, ["SPY"])
    close_long = _frame(long_index, ["SPY"])
    assert batch2.w_fomc_drift_spy(close_short, asof) == batch2.w_fomc_drift_spy(close_long, asof)


# --------------------------------------------------------------------------
# XYLD_COVERED_CALL_PROXY
# --------------------------------------------------------------------------


def test_xyld_buy_and_hold_hand_computed() -> None:
    index = pd.bdate_range("2021-01-01", "2021-01-08")
    close = _frame(index, ["XYLD"])
    weights = batch2.w_xyld_covered_call_proxy(close, index[-1])
    assert weights == {"XYLD": 1.0}
    _assert_contract(weights, ("XYLD",))


def test_xyld_returns_cash_before_history_exists() -> None:
    index = pd.bdate_range("2021-01-01", "2021-01-08")
    close = pd.DataFrame({"XYLD": [np.nan] * len(index)}, index=index)
    assert batch2.w_xyld_covered_call_proxy(close, index[-1]) == {}


# --------------------------------------------------------------------------
# Universe-only ticker checks, all SPECS
# --------------------------------------------------------------------------


@pytest.mark.parametrize("spec", batch2.SPECS, ids=lambda s: s["id"])
def test_universe_only_and_long_only_on_full_universe(spec: dict) -> None:
    index = pd.bdate_range("2020-06-01", "2022-12-31")
    universe = list(spec["universe"])
    close = _frame(index, universe)
    if spec["freq"] == "D":
        dates = spec["signal_dates_fn"](index)
    else:
        dates = [d for d in index if d.day >= 25]  # cheap month-end-ish sample
    for asof in dates[:20]:
        weights = spec["fn"](close, asof)
        _assert_contract(weights, tuple(universe))
