"""Synthetic-data tests for `scripts/screen_batches/h20260928_04_batch1.py`.

No backtest is run here -- these are unit tests of the pure weight functions
against hand-computed cases, plus the generic contract checks the brief
requires: long-only, sum(weights) <= 1, only universe tickers appear, and no
look-ahead (appending future rows never changes an already-decided `asof`'s
weights).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

import h20260928_04_batch1 as batch1  # noqa: E402

ALL_UNIVERSE_TICKERS = sorted({sym for spec in batch1.SPECS for sym in spec["universe"]})


def _assert_contract(weights: dict[str, float], universe: tuple[str, ...]) -> None:
    assert set(weights) <= set(universe)
    assert all(v >= 0.0 for v in weights.values())
    assert sum(weights.values()) <= 1.0 + 1e-9


def _month_end_index(n_months: int, start: str = "2015-01-31") -> pd.DatetimeIndex:
    """One business-day timestamp per calendar month, spaced a month apart
    (a genuine trading calendar would have more rows per month, but every
    `w_*` function only ever looks at the last-known value per calendar
    month via `_month_end_series`, so one row per month exercises the same
    code path deterministically)."""
    return pd.bdate_range(start=start, periods=n_months, freq="BME")


def _panel(index: pd.DatetimeIndex, series: dict[str, list[float]]) -> pd.DataFrame:
    return pd.DataFrame(series, index=index)


def _random_walk_panel(tickers: list[str], index: pd.DatetimeIndex, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = {}
    for i, sym in enumerate(tickers):
        steps = rng.normal(loc=0.004, scale=0.03, size=len(index))
        data[sym] = 100.0 * np.cumprod(1.0 + steps) * (1.0 + 0.001 * i)
    return pd.DataFrame(data, index=index)


# --------------------------------------------------------------------------
# SPECS shape
# --------------------------------------------------------------------------


def test_specs_ids_and_shape() -> None:
    ids = [spec["id"] for spec in batch1.SPECS]
    assert ids == [
        "F1_DBMF",
        "F1_KMLM",
        "F1_CTA",
        "F1_WTMF",
        "F1_FMF",
        "F2_VAA_G4",
        "F2_DAA_G12",
        "F2_PAA",
        "F2_HAA",
        "F2_GPM",
        "F2_GEM",
        "F2_GTAA",
        "F2_ADM",
        "F2_BAA_BAL",
        "F3_RPAR",
        "F3_UPAR",
        "F3_NTSX",
        "F3_QAI",
        "F3_TRTY",
    ]
    assert len(ids) == len(set(ids)) == 19
    for spec in batch1.SPECS:
        assert spec["freq"] == "M"
        assert callable(spec["fn"])
        assert isinstance(spec["universe"], tuple)
        assert spec["source_card"]


# --------------------------------------------------------------------------
# Generic contract: long-only, sum<=1, universe-only, no look-ahead.
# --------------------------------------------------------------------------


def test_all_candidates_are_long_only_and_universe_bound_on_a_long_synthetic_panel() -> None:
    index = _month_end_index(30)
    panel = _random_walk_panel(ALL_UNIVERSE_TICKERS, index, seed=7)
    check_points = index[14::4]  # several asof points with enough lookback
    for spec in batch1.SPECS:
        for asof in check_points:
            weights = spec["fn"](panel, asof)
            assert isinstance(weights, dict), spec["id"]
            _assert_contract(weights, spec["universe"])


def test_no_lookahead_appending_future_rows_never_changes_past_weights() -> None:
    index = _month_end_index(30)
    panel = _random_walk_panel(ALL_UNIVERSE_TICKERS, index, seed=11)
    asof = index[20]
    truncated = panel.loc[:asof]
    extended = panel  # same frame, but callers only ever pass `close`, and
    # every fn internally does `close.loc[:asof]` first -- so calling with
    # the full (future-including) panel must match calling with a panel
    # that never had the future rows at all.
    for spec in batch1.SPECS:
        before = spec["fn"](truncated, asof)
        after = spec["fn"](extended, asof)
        assert before == after, spec["id"]

    # Also explicitly perturb the future rows (not just extend with more of
    # the same random walk) to rule out a fn that peeks at `close.index.max()`
    # rather than `asof`.
    perturbed = panel.copy()
    future_mask = perturbed.index > asof
    perturbed.loc[future_mask] = perturbed.loc[future_mask] * 5.0 + 1000.0
    for spec in batch1.SPECS:
        before = spec["fn"](truncated, asof)
        after_perturbed = spec["fn"](perturbed, asof)
        assert before == after_perturbed, spec["id"]


def test_missing_ticker_or_pre_inception_history_returns_cash() -> None:
    index = _month_end_index(20)
    for spec in batch1.SPECS:
        empty_panel = pd.DataFrame(index=index)  # no columns at all
        assert spec["fn"](empty_panel, index[-1]) == {}
        nan_panel = pd.DataFrame(
            {sym: [np.nan] * len(index) for sym in spec["universe"]}, index=index
        )
        assert spec["fn"](nan_panel, index[-1]) == {}


# --------------------------------------------------------------------------
# F1 / F3 hold-only candidates: hand-computed.
# --------------------------------------------------------------------------


def test_f1_dbmf_holds_100pct_once_history_exists() -> None:
    index = _month_end_index(5)
    close = pd.DataFrame({"DBMF": [10.0, 10.5, 11.0, 10.8, 11.2]}, index=index)
    assert batch1.w_f1_dbmf(close, index[-1]) == {"DBMF": 1.0}


def test_f1_dbmf_returns_cash_before_inception() -> None:
    index = _month_end_index(5)
    close = pd.DataFrame({"DBMF": [np.nan, np.nan, np.nan, 10.8, 11.2]}, index=index)
    # asof before the first non-null observation -> no history yet.
    assert batch1.w_f1_dbmf(close, index[1]) == {}
    # asof after inception -> holds.
    assert batch1.w_f1_dbmf(close, index[-1]) == {"DBMF": 1.0}


def test_f3_rpar_holds_100pct_once_history_exists() -> None:
    index = _month_end_index(4)
    close = pd.DataFrame({"RPAR": [20.0, 21.0, 19.5, 20.2]}, index=index)
    assert batch1.w_f3_rpar(close, index[-1]) == {"RPAR": 1.0}


# --------------------------------------------------------------------------
# F2_VAA_G4 -- hand-computed.
# --------------------------------------------------------------------------


def _uptrend(n: int, start: float = 100.0, monthly_return: float = 0.02) -> list[float]:
    return [start * (1.0 + monthly_return) ** i for i in range(n)]


def _downtrend(n: int, start: float = 100.0, monthly_return: float = -0.02) -> list[float]:
    return [start * (1.0 + monthly_return) ** i for i in range(n)]


def test_vaa_g4_all_offensive_positive_picks_highest_offensive_momentum() -> None:
    index = _month_end_index(14)
    close = pd.DataFrame(
        {
            "SPY": _uptrend(14, monthly_return=0.03),
            "EFA": _uptrend(14, monthly_return=0.01),
            "EEM": _uptrend(14, monthly_return=0.005),
            "AGG": _uptrend(14, monthly_return=0.002),
            "LQD": _uptrend(14, monthly_return=0.001),
            "IEF": _uptrend(14, monthly_return=0.001),
            "SHY": _uptrend(14, monthly_return=0.0005),
        },
        index=index,
    )
    weights = batch1.w_f2_vaa_g4(close, index[-1])
    # SPY has the strongest uptrend of the four offensive assets, and all
    # four have positive 13612W momentum by construction (monotonic uptrend
    # at every lookback), so VAA-G4 must be 100% SPY.
    assert weights == {"SPY": 1.0}


def test_vaa_g4_one_offensive_negative_picks_best_defensive() -> None:
    index = _month_end_index(14)
    close = pd.DataFrame(
        {
            "SPY": _downtrend(14, monthly_return=-0.03),
            "EFA": _uptrend(14, monthly_return=0.01),
            "EEM": _uptrend(14, monthly_return=0.005),
            "AGG": _uptrend(14, monthly_return=0.002),
            "LQD": _downtrend(14, monthly_return=-0.001),
            "IEF": _uptrend(14, monthly_return=0.004),
            "SHY": _uptrend(14, monthly_return=0.0005),
        },
        index=index,
    )
    weights = batch1.w_f2_vaa_g4(close, index[-1])
    # SPY (an offensive asset) has negative momentum, so the whole portfolio
    # must move to the best-scoring defensive asset -- IEF, by construction.
    assert weights == {"IEF": 1.0}


# --------------------------------------------------------------------------
# F2_GEM -- hand-computed.
# --------------------------------------------------------------------------


def test_gem_absolute_momentum_positive_relative_momentum_picks_spy() -> None:
    index = _month_end_index(14)
    close = pd.DataFrame(
        {
            "SPY": _uptrend(14, monthly_return=0.02),
            "VEU": _uptrend(14, monthly_return=0.01),
            "AGG": _uptrend(14, monthly_return=0.003),
            "BIL": _uptrend(14, monthly_return=0.001),
        },
        index=index,
    )
    assert batch1.w_f2_gem(close, index[-1]) == {"SPY": 1.0}


def test_gem_absolute_momentum_positive_relative_momentum_picks_veu() -> None:
    index = _month_end_index(14)
    close = pd.DataFrame(
        {
            "SPY": _uptrend(14, monthly_return=0.01),
            "VEU": _uptrend(14, monthly_return=0.025),
            "AGG": _uptrend(14, monthly_return=0.003),
            "BIL": _uptrend(14, monthly_return=0.001),
        },
        index=index,
    )
    assert batch1.w_f2_gem(close, index[-1]) == {"VEU": 1.0}


def test_gem_absolute_momentum_negative_holds_bonds() -> None:
    index = _month_end_index(14)
    close = pd.DataFrame(
        {
            "SPY": _downtrend(14, monthly_return=-0.01),
            "VEU": _downtrend(14, monthly_return=-0.02),
            "AGG": _uptrend(14, monthly_return=0.002),
            "BIL": _uptrend(14, monthly_return=0.003),
        },
        index=index,
    )
    # SPY's 12-month return is below BIL's -> absolute momentum is negative.
    assert batch1.w_f2_gem(close, index[-1]) == {"AGG": 1.0}


# --------------------------------------------------------------------------
# F2_GTAA -- hand-computed.
# --------------------------------------------------------------------------


def test_gtaa_holds_only_sleeves_above_their_own_10_month_sma() -> None:
    index = _month_end_index(11)
    close = pd.DataFrame(
        {
            "SPY": _uptrend(11, monthly_return=0.02),  # ends above its own SMA10
            "EFA": _downtrend(11, monthly_return=-0.02),  # ends below its own SMA10
            "TIP": [100.0] * 11,  # flat: last value == mean -> not strictly above
            "GSG": _uptrend(11, monthly_return=0.01),
            "VNQ": _downtrend(11, monthly_return=-0.01),
        },
        index=index,
    )
    weights = batch1.w_f2_gtaa(close, index[-1])
    assert weights == {"SPY": 0.2, "GSG": 0.2}
    _assert_contract(weights, batch1._GTAA_UNIVERSE)


# --------------------------------------------------------------------------
# F2_ADM -- hand-computed.
# --------------------------------------------------------------------------


def test_adm_positive_score_picks_better_equity_leg() -> None:
    index = _month_end_index(8)
    close = pd.DataFrame(
        {
            "SPY": _uptrend(8, monthly_return=0.02),
            "SCZ": _uptrend(8, monthly_return=0.005),
            "TLT": _uptrend(8, monthly_return=0.001),
            "TIP": _uptrend(8, monthly_return=0.001),
        },
        index=index,
    )
    assert batch1.w_f2_adm(close, index[-1]) == {"SPY": 1.0}


def test_adm_negative_score_picks_better_defensive_leg_by_1m_return() -> None:
    index = _month_end_index(8)
    close = pd.DataFrame(
        {
            "SPY": _downtrend(8, monthly_return=-0.02),
            "SCZ": _downtrend(8, monthly_return=-0.03),
            "TLT": _uptrend(8, monthly_return=0.02),
            "TIP": _uptrend(8, monthly_return=0.001),
        },
        index=index,
    )
    assert batch1.w_f2_adm(close, index[-1]) == {"TLT": 1.0}
