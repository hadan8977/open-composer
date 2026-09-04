from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.mechanisms.cross_asset_trend_etf import (
    ALL_SYMBOLS,
    CASH_SYMBOL,
    PARAMETER_SPACE,
    UNIVERSE,
    daily_cross_asset_trend_returns,
)


def _returns_panel(
    index: pd.DatetimeIndex, overrides: dict[str, float | pd.Series]
) -> pd.DataFrame:
    """An ALL_SYMBOLS-column returns panel, 0.0 everywhere except ``overrides``."""
    data = {symbol: pd.Series(0.0, index=index) for symbol in ALL_SYMBOLS}
    for symbol, value in overrides.items():
        data[symbol] = pd.Series(value, index=index) if np.isscalar(value) else value
    return pd.DataFrame(data, index=index)


def _three_month_index() -> pd.DatetimeIndex:
    return pd.bdate_range("2020-01-01", "2020-03-31")


def test_parameter_space_has_twelve_unique_combinations() -> None:
    assert len(PARAMETER_SPACE) == 12
    assert len({tuple(sorted(p.items(), key=str)) for p in PARAMETER_SPACE}) == 12


def test_missing_symbol_raises() -> None:
    index = _three_month_index()
    panel = _returns_panel(index, {}).drop(columns=["GLD"])
    with pytest.raises(ValueError, match="missing required symbols"):
        daily_cross_asset_trend_returns(
            panel, {"lookback_months": 1, "top_n": 3, "weighting": "equal"}
        )


def test_unsupported_weighting_raises() -> None:
    # An eligible (positive-momentum) symbol is required to reach the
    # weighting branch at all -- an all-flat panel has no eligible symbols
    # and _target_weights returns all-BIL before weighting is ever consulted.
    index = _three_month_index()
    feb = index[(index.year == 2020) & (index.month == 2)]
    spy_returns = pd.Series(0.0, index=index)
    spy_returns.loc[feb] = 0.004
    panel = _returns_panel(index, {"SPY": spy_returns})
    with pytest.raises(ValueError, match="unsupported weighting"):
        daily_cross_asset_trend_returns(
            panel, {"lookback_months": 1, "top_n": 3, "weighting": "bogus"}
        )


def test_top_n_out_of_range_raises() -> None:
    index = _three_month_index()
    panel = _returns_panel(index, {})
    with pytest.raises(ValueError, match="top_n must be between"):
        daily_cross_asset_trend_returns(
            panel, {"lookback_months": 1, "top_n": 99, "weighting": "equal"}
        )


def test_unfilled_slots_hold_bil_and_zero_momentum_is_excluded() -> None:
    """SPY positive, TLT negative, everything else exactly flat (0.0).

    Only SPY should be selected (flat symbols have momentum == 0, which is
    not > 0 and must be excluded, not treated as "eligible with no edge").
    With top_n=3 and only 1 eligible name, 2/3 of the slot-weight is unfilled
    and must sit in BIL, not vanish or get redistributed onto SPY.
    """
    index = _three_month_index()
    jan = index[(index.year == 2020) & (index.month == 1)]
    feb = index[(index.year == 2020) & (index.month == 2)]
    mar = index[(index.year == 2020) & (index.month == 3)]

    spy_returns = pd.Series(0.0, index=index)
    spy_returns.loc[feb] = 0.005  # positive trailing 1-month return as of Feb month-end
    spy_returns.loc[mar] = -0.005  # realized during the holding period, irrelevant to selection

    tlt_returns = pd.Series(-0.003, index=index)  # always negative -> never eligible
    bil_returns = pd.Series(0.0001, index=index)  # small constant "cash" return

    panel = _returns_panel(
        index, {"SPY": spy_returns, "TLT": tlt_returns, CASH_SYMBOL: bil_returns}
    )
    del jan  # only used to document the three-month structure above

    rebalance_sink: list[dict] = []
    series = daily_cross_asset_trend_returns(
        panel,
        {"lookback_months": 1, "top_n": 3, "weighting": "equal", "cost_bps_per_side": 5.0},
        rebalance_sink=rebalance_sink,
    )

    # Two rebalance decisions have enough trailing history (Feb looking back
    # to Jan, Mar looking back to Feb); Jan's own month-end is excluded (no
    # prior month at all). Mar's decision holds no days (it is the last
    # month-end in this fixture, with no further data after it), so only
    # Feb's decision -- rebalance_sink[0] -- drives the return series below.
    assert len(rebalance_sink) == 2
    weights = rebalance_sink[0]["weights"]
    assert weights["SPY"] == pytest.approx(1.0 / 3.0)
    assert weights["TLT"] == 0.0
    for symbol in UNIVERSE:
        if symbol not in ("SPY",):
            assert weights[symbol] == 0.0
    assert weights[CASH_SYMBOL] == pytest.approx(2.0 / 3.0)

    # Holding period is exactly March; first day carries the one-time cost.
    assert len(series) == len(mar)
    turnover = abs(1.0 / 3.0 - 0.0) + abs(2.0 / 3.0 - 1.0)  # SPY in, BIL down from 100%
    cost = turnover * (2.0 * 5.0 / 10_000.0)
    expected_first = (1.0 / 3.0) * (-0.005) + (2.0 / 3.0) * 0.0001 - cost
    expected_rest = (1.0 / 3.0) * (-0.005) + (2.0 / 3.0) * 0.0001
    assert series.iloc[0] == pytest.approx(expected_first)
    assert series.iloc[-1] == pytest.approx(expected_rest)


def test_inverse_vol_weighting_favors_the_calmer_selected_symbol() -> None:
    """Two eligible symbols, same trailing return, different daily volatility.

    Equal weighting must split 50/50; inverse-vol weighting must overweight
    the calmer one, while keeping the SAME aggregate risky/cash split as
    equal weighting (only the per-name split changes).
    """
    index = pd.bdate_range("2020-01-01", "2020-04-30")
    feb = index[(index.year == 2020) & (index.month == 2)]
    mar = index[(index.year == 2020) & (index.month == 3)]

    rng = np.random.default_rng(20200101)
    # Both symbols end Feb with the same +positive trailing return, but SPY's
    # path is calm (tiny daily noise) and IWM's path is volatile (large daily
    # noise) over the 60-trading-day vol lookback window that precedes the
    # Feb rebalance.
    calm_noise = rng.normal(0.0, 0.0005, size=len(index))
    loud_noise = rng.normal(0.0, 0.02, size=len(index))
    spy_returns = pd.Series(0.0, index=index)
    iwm_returns = pd.Series(0.0, index=index)
    spy_returns.loc[feb] = 0.004 + calm_noise[: len(feb)]
    iwm_returns.loc[feb] = 0.004 + loud_noise[: len(feb)]
    # Re-scale Feb so both end at exactly the same total return (isolate the
    # weighting difference to volatility, not to a momentum-ranking tie-break).
    spy_total = float((1 + spy_returns.loc[feb]).prod() - 1)
    iwm_total = float((1 + iwm_returns.loc[feb]).prod() - 1)
    assert spy_total != pytest.approx(iwm_total)

    panel_equal = _returns_panel(index, {"SPY": spy_returns, "IWM": iwm_returns})
    equal_sink: list[dict] = []
    daily_cross_asset_trend_returns(
        panel_equal,
        {"lookback_months": 1, "top_n": 3, "weighting": "equal"},
        rebalance_sink=equal_sink,
    )
    inv_vol_sink: list[dict] = []
    daily_cross_asset_trend_returns(
        panel_equal,
        {"lookback_months": 1, "top_n": 3, "weighting": "inverse_vol_60d"},
        rebalance_sink=inv_vol_sink,
    )

    equal_weights = equal_sink[0]["weights"]
    inv_weights = inv_vol_sink[0]["weights"]
    assert equal_weights["SPY"] == pytest.approx(equal_weights["IWM"])
    # Same aggregate risky allocation (2 of 3 slots filled) under both schemes.
    assert equal_weights["SPY"] + equal_weights["IWM"] == pytest.approx(
        inv_weights["SPY"] + inv_weights["IWM"]
    )
    assert inv_weights["SPY"] > inv_weights["IWM"]  # SPY is the calmer symbol
    del mar


def test_later_data_does_not_change_an_earlier_rebalance_decision() -> None:
    """A future spike placed only in the last month must not affect a
    rebalance decision made at an earlier month-end (no lookahead)."""
    base_index = pd.bdate_range("2020-01-01", "2020-03-31")
    feb = base_index[(base_index.year == 2020) & (base_index.month == 2)]

    def build(extra_months: pd.DatetimeIndex | None) -> pd.DataFrame:
        index = base_index if extra_months is None else base_index.union(extra_months)
        spy_returns = pd.Series(0.0, index=index)
        spy_returns.loc[feb] = 0.004
        if extra_months is not None:
            spy_returns.loc[extra_months] = 5.0  # absurd future spike
        return _returns_panel(index, {"SPY": spy_returns})

    short_sink: list[dict] = []
    daily_cross_asset_trend_returns(
        build(None),
        {"lookback_months": 1, "top_n": 3, "weighting": "equal"},
        rebalance_sink=short_sink,
    )
    long_index = pd.bdate_range("2020-04-01", "2020-04-30")
    long_sink: list[dict] = []
    daily_cross_asset_trend_returns(
        build(long_index),
        {"lookback_months": 1, "top_n": 3, "weighting": "equal"},
        rebalance_sink=long_sink,
    )

    # Both runs must have made the identical Feb decision -- the April
    # extension (and its absurd spike) cannot leak backward into it.
    assert short_sink[0]["date"] == long_sink[0]["date"]
    assert short_sink[0]["weights"] == long_sink[0]["weights"]


def test_top_n_all_uses_the_full_universe_as_slots() -> None:
    index = _three_month_index()
    feb = index[(index.year == 2020) & (index.month == 2)]
    spy_returns = pd.Series(0.0, index=index)
    spy_returns.loc[feb] = 0.004
    panel = _returns_panel(index, {"SPY": spy_returns})

    sink: list[dict] = []
    daily_cross_asset_trend_returns(
        panel, {"lookback_months": 1, "top_n": None, "weighting": "equal"}, rebalance_sink=sink
    )
    # 1 of 10 universe slots filled -> 1/10 to SPY, 9/10 to BIL.
    assert sink[0]["weights"]["SPY"] == pytest.approx(1.0 / len(UNIVERSE))
    assert sink[0]["weights"][CASH_SYMBOL] == pytest.approx(1.0 - 1.0 / len(UNIVERSE))
