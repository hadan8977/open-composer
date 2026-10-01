"""Synthetic tests of the Stage 2a rules (T-20261001-08); no real panel, signal or risk data."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book.signals import THEMES
from scripts import build_book_v1_alpha as bld
from scripts import run_book_v1_stage2 as run


def test_select_window_lag_and_cap() -> None:
    pos = np.arange(0, 22 * 100, 22)  # one formation date per 22 sessions
    t = 22 * 50 + 21
    idx = bld.select_window(pos, t, 36)
    assert len(idx) == 36
    assert pos[idx].max() <= t - 22 and pos[idx[-1]] == 22 * 49  # 22 * 49 + 22 = 1100 <= 1100
    # a formation date exactly 22 sessions before is allowed, 21 sessions before is not
    assert len(bld.select_window(np.array([100]), 122, 36)) == 1
    assert len(bld.select_window(np.array([101]), 122, 36)) == 0
    # fewer than the cap: all eligible, ascending
    idx = bld.select_window(pos, 22 * 5, 36)
    assert list(idx) == [0, 1, 2, 3, 4]  # 22 * 4 = 88 <= 110 - 22


def test_ic_scale_prior_floor_and_shrink() -> None:
    v, prior = bld.ic_scale(np.full(11, 0.5))
    assert prior and v == pytest.approx(0.03)
    v, prior = bld.ic_scale(np.full(12, 0.05))
    assert not prior and v == pytest.approx(0.5 * 0.05 + 0.5 * 0.03)
    v, _ = bld.ic_scale(np.full(20, -0.2))
    assert v == 0.0
    v, _ = bld.ic_scale(np.full(36, 0.0))
    assert v == pytest.approx(0.015)


def test_m1_weights_fallback_and_ir_rule() -> None:
    n = len(THEMES)
    w, fb = bld.m1_weights(np.random.default_rng(0).normal(size=(23, n)))
    assert fb and np.allclose(w, 1.0 / n)  # fewer than 24 observations
    w, fb = bld.m1_weights(-np.abs(np.random.default_rng(1).normal(size=(30, n))) - 0.01)
    assert fb and np.allclose(w, 1.0 / n)  # every theme IC negative -> all weights 0
    rng = np.random.default_rng(2)
    m = rng.normal(0.0, 0.05, size=(60, n))
    m[:, 0] += 0.04  # theme 0 clearly positive
    m[:, 1] -= 0.2  # theme 1 clearly negative
    w, fb = bld.m1_weights(m)
    assert not fb and w[1] == 0.0 and w[0] == w.max() and w.sum() == pytest.approx(1.0)
    # only the last 60 observations count
    long = np.vstack([np.full((100, n), 9.0) + rng.normal(size=(100, n)), m])
    w2, _ = bld.m1_weights(long)
    assert np.allclose(w2, w)


def test_m1_weights_nan_themes_get_zero_until_24_valid() -> None:
    n = len(THEMES)
    rng = np.random.default_rng(4)
    m = rng.normal(0.02, 0.05, size=(40, n))
    m[:20, 0] = np.nan  # theme 0 has only 20 valid ICs in the window
    w, fb = bld.m1_weights(m)
    assert not fb and w[0] == 0.0 and w.sum() == pytest.approx(1.0)
    m[:, 0] = rng.normal(0.02, 0.05, size=40)
    w, _ = bld.m1_weights(m)
    assert np.isfinite(w).all() and w.sum() == pytest.approx(1.0)


def test_residual_target_zero_when_return_is_factor_return() -> None:
    n, k, p = 5, 3, 4
    rng = np.random.default_rng(3)
    x = rng.normal(size=(n, k))
    fret = np.zeros((21, k))
    fret[7] = rng.normal(0.0, 0.01, size=k)  # one active factor day
    r = x @ fret[7]
    t_n = p + 1 + 22
    open_ = np.ones((t_n, n)) * 10.0
    # the return accrues at one open step inside p + 1 .. p + 22: open[p + 1 + 8] onward
    open_[p + 1 + 8 :] = 10.0 * (1.0 + r)
    close = open_.copy()
    y = bld.residual_target(open_, close, p, x, fret)
    assert np.allclose(y, 0.0, atol=1e-12)
    # a different exposure vector leaves a nonzero residual
    y2 = bld.residual_target(open_, close, p, x * 2.0, fret)
    assert np.abs(y2).max() > 1e-6


def test_rank_ic_matches_spearman() -> None:
    a = np.array([1.0, 2.0, 3.0, 4.0, np.nan])
    b = np.array([1.0, 3.0, 2.0, 4.0, 5.0])
    ic, n = bld.rank_ic(a, b)
    assert n == 4 and ic == pytest.approx(pd.Series(a[:4]).corr(pd.Series(b[:4]), "spearman"))


def test_path_ids_unique_and_shards_cover_once() -> None:
    paths = run.main_paths()
    assert len(paths) == 54 and len(set(paths)) == 54
    assert paths[0] == "M0_A_o0_close" and paths[29] == "M1_C_o4_close"
    assert paths[30] == "M0_A_o0_open" and paths[44] == "M0_C_o4_open"
    assert paths[45] == "M0_A_o0_close_loo_value" and paths[-1].endswith("_loo_seasonality")
    for n in (1, 7, 54):
        got = [p for s in range(n) for p in run.shard_paths(paths, s, n)]
        assert sorted(got) == sorted(paths)
    kinds = [run.parse_path(p)["kind"] for p in paths]
    assert kinds.count("main") == 45 and kinds.count("loo") == 9


def test_placebo_offset_is_seed_mod_5() -> None:
    paths = run.placebo_paths(list(range(100)), ["M0_A", "M1_C"])
    assert len(paths) == 200 and len(set(paths)) == 200
    for pid in paths:
        info = run.parse_path(pid)
        assert info["kind"] == "placebo" and info["offset"] == info["seed"] % 5
    assert run.placebo_paths([7], ["M0_B"]) == ["M0_B_s07_o2_close"]
    with pytest.raises(ValueError):
        run.parse_path("M0_A_s07_o3_close")
    assert run.parse_seeds("100") == list(range(100)) and run.parse_seeds("2-4") == [2, 3, 4]


def test_placebo_shuffle_keeps_values_and_is_reproducible() -> None:
    idx = pd.Index([f"S{i}" for i in range(50)])
    vals = np.random.default_rng(5).normal(size=50)
    vals[3] = np.nan
    s = pd.Series(vals, index=idx)

    def draw(seed: int) -> list[pd.Series]:
        rng = np.random.default_rng(run.PLACEBO_SEED_BASE + seed)
        return [run.shuffle_scores(s, rng) for _ in range(3)]

    a, b = draw(4), draw(4)
    for x, y in zip(a, b, strict=True):
        pd.testing.assert_series_equal(x, y)  # same seed, same sequence
    assert not np.array_equal(a[0].to_numpy(), s.to_numpy(), equal_nan=True)
    assert not np.array_equal(a[0].to_numpy(), a[1].to_numpy(), equal_nan=True)  # one draw per call
    for x in a:
        assert x.index.equals(idx)
        assert np.array_equal(np.sort(x.dropna().to_numpy()), np.sort(s.dropna().to_numpy()))
        assert int(x.isna().sum()) == 1
    c = draw(5)
    assert not np.array_equal(a[0].to_numpy(), c[0].to_numpy(), equal_nan=True)


def test_formation_ic_lag_in_class() -> None:
    dates = pd.bdate_range("2020-01-01", periods=400)
    pos = np.arange(10, 380, 22)
    fic = pd.DataFrame(
        {
            "formation_date": dates[pos],
            "universe": "u3000",
            "series": "M0",
            "ic": 0.05,
            "n": 1000,
        }
    )
    fi = run.FormationIC(fic, dates)
    val, n_used, prior = fi.ic_t("u3000", "M0", 10 + 22 * 12)  # 12 formation dates eligible
    assert n_used == 12 and not prior and val == pytest.approx(0.04)
    val, n_used, prior = fi.ic_t("u3000", "M0", 10 + 22 * 12 - 1)  # last one not yet usable
    assert n_used == 11 and prior and val == pytest.approx(0.03)
