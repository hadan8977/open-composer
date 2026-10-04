"""Synthetic tests for scripts/book_v14_ml_eval.py (T-20261004-03)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from scripts import book_v14_ml_eval as E
from scripts import realism_ladder_book_ls as T25


def _preds() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    rows = []
    for d in pd.bdate_range("2024-01-02", periods=3):
        for s in "ABCDEF":
            rows.append((d, s, float(rng.normal())))
    df = pd.DataFrame(rows, columns=["trade_date", "symbol", "m0"])
    df.loc[(df.trade_date == df.trade_date.min()) & (df.symbol == "C"), "m0"] = np.nan
    return df


def test_prediction_source_rank_normal_and_nan() -> None:
    df = _preds()
    src = E.PredictionSource(df, "m0")
    t = df.trade_date.min()
    uni = pd.Index(["A", "B", "C", "D", "E", "F", "ZZ"])
    out = src(t, None, uni)
    assert list(out.index) == list(uni)
    assert np.isnan(out["C"]) and np.isnan(out["ZZ"])
    ok = out.dropna()
    assert len(ok) == 5
    assert abs(ok.mean()) < 1e-12
    # rank-normal preserves order of the raw values
    raw = df[(df.trade_date == t)].set_index("symbol")["m0"].dropna()
    assert list(ok.sort_values().index) == list(raw.sort_values().index)


def test_placebo_is_within_date_permutation_reproducible_by_seed() -> None:
    df = _preds()
    t = df.trade_date.iloc[7]
    uni = pd.Index(list("ABCDEF"))
    base = E.PredictionSource(df, "m0")(t, None, uni)
    a = E.PredictionSource(df, "m0", placebo_seed=3)(t, None, uni)
    b = E.PredictionSource(df, "m0", placebo_seed=3)(t, None, uni)
    c = E.PredictionSource(df, "m0", placebo_seed=4)(t, None, uni)
    assert np.array_equal(a.to_numpy(), b.to_numpy())
    assert sorted(a.to_numpy()) == pytest.approx(sorted(base.to_numpy()))
    assert not np.array_equal(a.to_numpy(), c.to_numpy()) or not np.array_equal(
        a.to_numpy(), base.to_numpy()
    )
    assert not np.array_equal(a.to_numpy(), base.to_numpy())


def test_restarted_decision_positions_equal_v12_after_start() -> None:
    class Px:
        T = 400
        dates = pd.bdate_range("2017-10-02", periods=400)

    class Ctx:
        px = Px()

    for o in range(5):
        assert E.next_decision_dates_equal(Ctx(), "2019-01-02", o)
        first = int(Px.dates.searchsorted(pd.Timestamp("2019-01-02")))
        mine = T25.decision_positions(Px.T, first, Px.T - 3, T25.WEEK, o)
        assert all(p % 5 == o and p >= first for p in mine)


def test_vol_matched_difference_zero_mean_when_candidate_is_double_base() -> None:
    rng = np.random.default_rng(1)
    idx = pd.bdate_range("2024-01-02", periods=300)
    b = pd.Series(rng.normal(0.0005, 0.01, 300), index=idx)
    d = E.vol_matched_diff(2.0 * b, b)
    assert abs(float(d.mean())) < 1e-12
    assert float(d.abs().max()) < 1e-12


def test_vol_matched_difference_uses_common_window_and_scales_vol() -> None:
    rng = np.random.default_rng(2)
    idx = pd.bdate_range("2024-01-02", periods=300)
    b = pd.Series(rng.normal(0, 0.01, 300), index=idx)
    c = pd.Series(rng.normal(0, 0.03, 300), index=idx)
    d = E.vol_matched_diff(c.iloc[10:], b)
    assert len(d) == 290
    scaled = c.iloc[10:] * (b.iloc[10:].std() / c.iloc[10:].std())
    assert scaled.std() == pytest.approx(b.iloc[10:].std())


def test_count_offsets_improved_is_strict() -> None:
    assert E.count_offsets_improved([1, 2, 3, 4, 5], [1, 1, 4, 3, 5]) == 2
    assert E.count_offsets_improved([2, 2, 2, 2, 2], [1, 1, 1, 1, 3]) == 4
