from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import ml_composite as mc
from open_composer.research.equity_book import optimize as op
from open_composer.research.equity_book.book_v12 import target_weights


def test_rank_standardize_range_and_nan() -> None:
    df = pd.DataFrame(
        {
            "trade_date": ["a"] * 4 + ["b"] * 3,
            "symbol": list("wxyzwxy"),
            "f": [1.0, 2.0, np.nan, 4.0, 5.0, 5.0, 1.0],
        }
    )
    out = mc.rank_standardize(df, ["f"])
    assert np.isnan(out.loc[2, "f"])
    assert out["f"].dropna().between(-0.5, 0.5).all()
    # date a: three valid values -> pct ranks 1/3, 2/3, 1 -> minus 0.5
    assert out.loc[[0, 1, 3], "f"].tolist() == pytest.approx([1 / 3 - 0.5, 2 / 3 - 0.5, 0.5])
    # date b: tie gets the average rank
    assert out.loc[4, "f"] == pytest.approx(out.loc[5, "f"])
    assert df["f"].iloc[0] == 1.0  # input untouched


def test_book_labels_timing() -> None:
    T = 40
    C = np.tile(np.arange(1.0, T + 1.0)[:, None], (1, 3)) * np.array([1.0, 2.0, 3.0])
    C[:, 2] = np.nan
    S = np.arange(100.0, 100.0 + T)
    beta = np.array([1.0, np.nan, 1.0])
    p = 5
    y = mc.book_labels(C, S, beta, p, 21)
    expected0 = C[p + 22, 0] / C[p + 1, 0] - 1 - 1.0 * (S[p + 22] / S[p + 1] - 1)
    assert y[0] == pytest.approx(expected0)
    assert y[1] == pytest.approx(C[p + 22, 1] / C[p + 1, 1] - 1 - 1.0 * (S[p + 22] / S[p + 1] - 1))
    assert np.isnan(y[2])
    r5 = mc.book_labels(C, S, np.array([4.0, 9.0, 1.0]), p, 5)
    # beta clipped to [-1, 4]
    assert r5[1] == pytest.approx(C[p + 6, 1] / C[p + 1, 1] - 1 - 4.0 * (S[p + 6] / S[p + 1] - 1))
    assert np.isnan(mc.book_labels(C, S, beta, T - 5, 21)).all()


def test_industry_demean_sums_to_zero() -> None:
    x = pd.Series([1.0, 2.0, 3.0, 10.0, 20.0, np.nan], index=list("abcdef"))
    ind = pd.Series([1, 1, 1, 2, 2, 2], index=x.index)
    out = mc.industry_demean(x, ind)
    assert out.groupby(ind).sum().abs().max() < 1e-12
    assert np.isnan(out["f"])
    assert out["a"] == pytest.approx(-1.0)
    m = mc.industry_demean(np.column_stack([x.to_numpy(), x.to_numpy() * 2]), ind.to_numpy())
    assert m[3, 1] == pytest.approx(-10.0)


def test_industry_demean_nan_industry_is_one_group() -> None:
    x = pd.Series([1.0, 3.0, 5.0, 9.0])
    ind = pd.Series([np.nan, np.nan, 7.0, 7.0])
    out = mc.industry_demean(x, ind)
    assert out.tolist() == pytest.approx([-1.0, 1.0, -2.0, 2.0])


def test_rff_determinism_and_shape() -> None:
    g = (0.5, 0.6, 1.0)
    o1, g1 = mc.rff_draw(20261004, 4, 7, g)
    o2, g2 = mc.rff_draw(20261004, 4, 7, g)
    assert np.array_equal(o1, o2) and np.array_equal(g1, g2)
    assert set(g1) <= set(g)
    Z = np.random.default_rng(0).uniform(-0.5, 0.5, (6, 4))
    S = mc.rff(Z, o1, g1)
    assert S.shape == (6, 14)
    assert np.allclose(S[:, :7] ** 2 + S[:, 7:] ** 2, 1.0)
    Z[0, 0] = np.nan
    Z0 = Z.copy()
    Z0[0, 0] = 0.0
    assert np.array_equal(mc.rff(Z, o1, g1), mc.rff(Z0, o1, g1))
    o3, _ = mc.rff_draw(1, 4, 7, g)
    assert not np.array_equal(o1, o3)


def test_sdf_lambda_closed_form() -> None:
    F = np.array(
        [[1.0, 0.0, 2.0, -1.0, 0.5], [0.0, 1.0, 1.0, 2.0, -0.5], [2.0, -1.0, 0.0, 1.0, 1.0]]
    )
    z, s_bar = 0.7, mc.mean_gram_scale(F)
    assert s_bar == pytest.approx(np.trace(F.T @ F / 3) / 5)
    lam = mc.sdf_lambda(F, z, s_bar)
    expected = np.linalg.inv(z * s_bar * np.eye(5) + F.T @ F / 3) @ F.mean(axis=0)
    assert lam == pytest.approx(expected)


def _factors(T: int, P: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    drift = rng.normal(0.0, 0.05, P)
    return drift + rng.normal(0.0, 1.0, (T, P))


def test_choose_z_scale_invariance() -> None:
    F = _factors(130, 12)
    z1, s1 = mc.choose_z(F)
    z2, s2 = mc.choose_z(F * 10.0)
    assert z1 == z2
    assert set(s1) == {repr(z) for z in mc.Z_GRID}
    for k in s1:
        assert s1[k] == pytest.approx(s2[k], rel=1e-9)
    l1 = mc.sdf_lambda(F, z1, mc.mean_gram_scale(F))
    l2 = mc.sdf_lambda(F * 10.0, z1, mc.mean_gram_scale(F * 10.0))
    assert l1 / np.linalg.norm(l1) == pytest.approx(l2 / np.linalg.norm(l2))


def test_choose_z_fallback_below_104_weeks() -> None:
    z, sharpes = mc.choose_z(_factors(103, 8))
    assert z == 1.0 and sharpes == {}
    z, sharpes = mc.choose_z(_factors(104, 8))
    assert z in mc.Z_GRID and len(sharpes) == len(mc.Z_GRID)


def test_permute_within_date_keeps_multiset() -> None:
    y = np.array([1.0, 2.0, 3.0, 10.0, 20.0, 30.0, 40.0])
    d = np.array([0, 0, 0, 1, 1, 1, 1])
    out = mc.permute_within_date(y, d, seed=1)
    assert sorted(out[:3]) == [1.0, 2.0, 3.0]
    assert sorted(out[3:]) == [10.0, 20.0, 30.0, 40.0]
    assert np.array_equal(out, mc.permute_within_date(y, d, seed=1))
    big = np.arange(200.0)
    assert not np.array_equal(mc.permute_within_date(big, np.zeros(200, int), 1), big)


def test_embargo_assertion() -> None:
    assert mc.embargo_ok([10, 20, 57], 100)
    assert mc.embargo_ok([57], 100)
    assert not mc.embargo_ok([10, 58], 100)
    assert mc.embargo_ok([], 100)


def test_simplified_weekly_return_hand_computation() -> None:
    idx = list("abcdef")
    score = pd.Series([0.1, 0.2, 0.3, 0.4, 0.5, 0.6], index=idx)
    ind = pd.Series([1, 1, 1, 2, 2, 2], index=idx)
    r5 = pd.Series([0.01, 0.02, np.nan, 0.03, 0.05, -0.04], index=idx)
    got = mc.simplified_weekly_return(score, ind, r5)
    w = target_weights(op.rank_normal(score), ind)
    assert w.sum() == pytest.approx(0.0, abs=1e-12)
    assert w.abs().sum() == pytest.approx(2.0)
    manual = sum(w[k] * (0.0 if np.isnan(r5[k]) else r5[k]) for k in idx)
    assert got == pytest.approx(manual)
    # within each industry the lowest score is short, the highest long
    assert w["a"] < 0 < w["c"] and w["d"] < 0 < w["f"]
    assert got == pytest.approx(
        w["a"] * 0.01 + w["b"] * 0.02 + w["d"] * 0.03 + w["e"] * 0.05 + w["f"] * -0.04
    )
