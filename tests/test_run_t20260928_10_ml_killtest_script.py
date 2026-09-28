from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import run_t20260928_10_ml_killtest as mod  # noqa: E402


def test_consecutive_increase_streak_resets_on_decrease_and_caps():
    idx = pd.date_range("2020-01-01", periods=20, freq="D")
    eps = pd.DataFrame(
        {
            "A": [1, 1, 1, 2, 2, 2, 3, 3, 2, 2, 4, 4, 4, 4, 5, 5, 5, 5, 5, 6],
        },
        index=idx,
    )
    streak = mod.consecutive_increase_streak(eps, cap=8)["A"]
    # first distinct value has no prior quarter -> streak 0
    assert streak.iloc[0] == 0
    # 1 -> 2 is an increase: streak becomes 1, held until the next change point
    assert streak.iloc[3] == 1
    assert streak.iloc[5] == 1
    # 2 -> 3 is a second consecutive increase
    assert streak.iloc[6] == 2
    # 3 -> 2 is a decrease: streak resets to 0
    assert streak.iloc[8] == 0
    # never exceeds the cap
    assert streak.max() <= 8


def test_consecutive_increase_streak_handles_leading_nan():
    idx = pd.date_range("2020-01-01", periods=10, freq="D")
    eps = pd.DataFrame({"B": [np.nan, np.nan, 1, 1, 2, 2, 3, 3, 2, 2]}, index=idx)
    streak = mod.consecutive_increase_streak(eps, cap=8)["B"]
    assert streak.iloc[0:2].isna().all()
    assert streak.iloc[2] == 0
    assert streak.iloc[4] == 1
    assert streak.iloc[6] == 2
    assert streak.iloc[8] == 0


def test_quantile_grade_is_within_bounds_and_monotonic_within_group():
    y = np.array([1, 2, 3, 4, 5, 10, 20, 30])
    g = np.array([0, 0, 0, 0, 1, 1, 1, 1])
    grade = mod.quantile_grade(y, g, n_bins=5)
    assert grade.min() >= 0
    assert grade.max() <= 4
    # within each group, grade must be non-decreasing as y increases
    for group in (0, 1):
        mask = g == group
        order = np.argsort(y[mask])
        assert np.all(np.diff(grade[mask][order]) >= 0)


def test_derive_jkp_factors_shapes_and_yoy_lag():
    cal = pd.date_range("2016-01-01", periods=600, freq="B")
    syms = ["X", "Y"]

    def mk(seed: int) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        return pd.DataFrame(
            rng.normal(100, 5, size=(len(cal), len(syms))).cumsum(axis=0),
            index=cal,
            columns=syms,
        )

    wide = {
        "operating_cash_flow": mk(1),
        "total_assets": mk(2) + 1000,
        "stockholders_equity": mk(3) + 500,
        "eps_diluted": mk(4) / 50,
        "shares_outstanding": mk(5) + 1e6,
    }
    jkp = mod.derive_jkp_factors(wide, cal)
    assert set(jkp) == {"ocf_at_chg1", "niq_at_chg1", "niq_be_chg1", "ni_inc8q"}
    for frame in jkp.values():
        assert frame.shape == (600, 2)
    # a *_chg1 factor needs 252 prior sessions -- must be all-NaN before that
    assert jkp["ocf_at_chg1"].iloc[: mod.YOY_TRADING_DAYS - 1].isna().all().all()
    assert jkp["ocf_at_chg1"].iloc[mod.YOY_TRADING_DAYS :].notna().any().any()


def test_build_target_is_demeaned_within_formation_date_and_size_quintile():
    cal = pd.date_range("2016-01-01", periods=300, freq="B")
    n_sym = 60
    rng = np.random.default_rng(1)
    syms = [f"S{i}" for i in range(n_sym)] + ["SPY"]
    close = pd.DataFrame(
        100 * np.exp(np.cumsum(rng.normal(0, 0.01, size=(len(cal), len(syms))), axis=0)),
        index=cal,
        columns=syms,
    )
    formation = pd.DataFrame(
        {
            "formation_date": [cal[100]] * n_sym,
            "symbol": syms[:-1],
            "dollar_adv": rng.uniform(1e6, 5e7, size=n_sym),
            "beta_252_spy": rng.normal(1, 0.3, size=n_sym),
        }
    )
    out = mod.build_target(formation, close, 21)
    assert "target_excess_21" in out.columns
    assert out["target_excess_21"].notna().all()
    # demeaned within (formation_date, size_quintile) -> overall mean ~ 0
    assert abs(out["target_excess_21"].mean()) < 1e-9


def test_lookup_wide_at_formation_matches_direct_indexing():
    cal = pd.date_range("2016-01-01", periods=50, freq="B")
    wide = pd.DataFrame(
        np.arange(50 * 2, dtype="float64").reshape(50, 2), index=cal, columns=["X", "Y"]
    )
    formation = pd.DataFrame(
        {"formation_date": [cal[5], cal[5], cal[20]], "symbol": ["X", "Y", "X"]}
    )
    looked = mod.lookup_wide_at_formation(wide, formation, "value")
    assert looked.tolist() == [
        wide.loc[cal[5], "X"],
        wide.loc[cal[5], "Y"],
        wide.loc[cal[20], "X"],
    ]


def test_lightgbm_regression_and_lambdarank_models_fit_predict_roundtrip():
    rng = np.random.default_rng(0)
    X = rng.normal(size=(300, 4))
    y = X[:, 0] + rng.normal(scale=0.1, size=300)
    groups = np.repeat(np.arange(6), 50)

    reg = mod.LightGBMRegressionModel()
    reg.fit(X, y, groups)
    pred = reg.predict(X[:10])
    assert pred.shape == (10,)
    assert np.all(np.isfinite(pred))

    ranker = mod.LightGBMLambdaRankModel()
    ranker.fit(X, y, groups)
    rank_pred = ranker.predict(X[:10])
    assert rank_pred.shape == (10,)
    assert np.all(np.isfinite(rank_pred))
