from __future__ import annotations

import importlib.util

import numpy as np
import pandas as pd
import pytest

from scripts import run_t20260930_17_model_family_sweep as sw

HAS_XGB_CAT = (
    importlib.util.find_spec("xgboost") is not None
    and importlib.util.find_spec("catboost") is not None
)


def test_shard_mapping_fixed_and_complete() -> None:
    cells = [sw.cell_for_shard(i, 20) for i in range(20)]
    assert len(set(cells)) == 20
    assert cells == list(sw.CELL_ORDER)
    assert cells[0] == "LGBM_W3_H21"
    assert cells[-1] == "MLP_WX_H63"
    assert not any(c.startswith("ENS") for c in cells)
    expected = {
        f"{f}_{w}_{h}"
        for f in ("LGBM", "XGB", "CAT", "RIDGE", "MLP")
        for w in ("W3", "WX")
        for h in ("H21", "H63")
    }
    assert set(cells) == expected
    assert len(sw.ALL_CELLS) == 24
    with pytest.raises(ValueError):
        sw.cell_for_shard(20, 20)
    with pytest.raises(ValueError):
        sw.cell_for_shard(0, 19)


def test_parse_cell() -> None:
    assert sw.parse_cell("XGB_WX_H63") == ("XGB", "WX", 63)
    assert sw.parse_cell("ENS_W3_H21") == ("ENS", "W3", 21)
    with pytest.raises(ValueError):
        sw.parse_cell("FOO_W3_H21")


def test_missing_fill_only_for_ridge_and_mlp() -> None:
    X = np.array([[1.0, np.nan], [np.nan, 0.2]])
    for fam in ("RIDGE", "MLP"):
        out = sw.fill_missing(X, fam)
        assert not np.isnan(out).any()
        assert out[0, 1] == 0.5 and out[1, 0] == 0.5
        assert out[0, 0] == 1.0
    for fam in ("LGBM", "XGB", "CAT"):
        out = sw.fill_missing(X, fam)
        assert np.isnan(out).sum() == 2


def test_ridge_and_mlp_models_fit_with_nans() -> None:
    rng = np.random.default_rng(0)
    X = rng.random((400, 4))
    y = X[:, 0] - 0.5 + 0.01 * rng.standard_normal(400)
    X[::7, 1] = np.nan
    for fam in ("RIDGE", "MLP"):
        m = sw.FamilyModel(fam)
        m.fit(X, y)
        pred = m.predict(X)
        assert pred.shape == (400,) and np.isfinite(pred).all()
        assert np.corrcoef(pred, y)[0, 1] > 0.5


@pytest.mark.skipif(not HAS_XGB_CAT, reason="xgboost/catboost not installed")
def test_tree_models_fit_with_nans() -> None:
    rng = np.random.default_rng(1)
    X = rng.random((600, 4))
    y = X[:, 0] - 0.5 + 0.01 * rng.standard_normal(600)
    X[::5, 1] = np.nan
    for fam in ("XGB", "CAT"):
        m = sw.FamilyModel(fam)
        m.fit(X, y)
        assert np.isfinite(m.predict(X)).all()


def _pred_frame(values: dict[str, list[float]], date: str = "2020-01-31") -> pd.DataFrame:
    n = len(next(iter(values.values())))
    return pd.DataFrame(
        {
            "formation_date": pd.Timestamp(date),
            "symbol": [f"S{i}" for i in range(n)],
            "pred": next(iter(values.values())),
            "target": np.arange(n, dtype=float),
            "adv_tercile": "T1_liquid",
        }
    )


def test_rank_mean_ensemble_toy() -> None:
    a = _pred_frame({"a": [1.0, 2.0, 3.0, 4.0]})
    b = _pred_frame({"b": [40.0, 30.0, 20.0, 10.0]})  # reversed order, different scale
    ens = sw.rank_mean_ensemble([a, b])
    # ranks pct: a = .25 .5 .75 1 ; b = 1 .75 .5 .25 -> mean 0.625 everywhere
    assert np.allclose(ens["pred"].to_numpy(), 0.625)
    c = _pred_frame({"c": [5.0, 6.0, 7.0, 8.0]})
    ens2 = sw.rank_mean_ensemble([a, c])
    assert np.allclose(ens2["pred"].to_numpy(), [0.25, 0.5, 0.75, 1.0])
    # rank is per date: scaling one date's predictions does not change the mean rank
    d1 = _pred_frame({"a": [1.0, 2.0, 3.0]}, "2020-01-31")
    d2 = _pred_frame({"a": [100.0, 200.0, 300.0]}, "2020-02-29")
    e = sw.rank_mean_ensemble([pd.concat([d1, d2]), pd.concat([d1, d2])])
    assert np.allclose(e.groupby("formation_date")["pred"].apply(list).iloc[0], [1 / 3, 2 / 3, 1.0])
    assert np.allclose(e.groupby("formation_date")["pred"].apply(list).iloc[1], [1 / 3, 2 / 3, 1.0])


def test_nw_lag_by_horizon() -> None:
    assert sw.nw_lag_for_horizon(21) == 0
    assert sw.nw_lag_for_horizon(63) == 2
    rng = np.random.default_rng(3)
    x = 0.02 + 0.05 * rng.standard_normal(80)
    s21 = sw.ic_stats(x, sw.nw_lag_for_horizon(21))
    s63 = sw.ic_stats(x, sw.nw_lag_for_horizon(63))
    assert s21["t_nw"] == pytest.approx(sw.newey_west_t(x, 0))
    assert s63["t_nw"] == pytest.approx(sw.newey_west_t(x, 2))
    assert s21["t_nw"] != s63["t_nw"]
    # lag 0 is the population-variance t
    assert s21["t_nw"] == pytest.approx(x.mean() / (x.std(ddof=0) / np.sqrt(len(x))))


def test_newey_west_matches_t35() -> None:
    pytest.importorskip("duckdb")
    from scripts import run_t20260929_35_overnight_persistence as t35

    rng = np.random.default_rng(4)
    x = 0.01 + 0.03 * rng.standard_normal(90)
    for lag in (0, 2):
        assert sw.newey_west_t(x, lag) == pytest.approx(t35.newey_west_t(x, lag))


def _cells(ts: dict[str, float], rankic: float = 0.02) -> dict[str, dict]:
    return {c: {"mean_rankic": rankic, "t_nw": t} for c, t in ts.items()}


def test_stage2_selection_rules() -> None:
    cells = _cells(
        {
            "LGBM_W3_H21": 9.0,  # B0, excluded even with the highest t
            "XGB_W3_H21": 2.5,
            "CAT_W3_H21": 3.5,
            "RIDGE_W3_H21": 1.99,  # below 2.0
            "MLP_W3_H21": 2.0,  # exactly 2.0 qualifies
            "ENS_W3_H21": 3.0,
        }
    )
    sel = sw.select_stage2_cells(cells)
    assert [s["cell"] for s in sel] == ["CAT_W3_H21", "ENS_W3_H21", "XGB_W3_H21"]
    # fewer than three eligible: select fewer
    few = sw.select_stage2_cells(_cells({"LGBM_W3_H21": 5.0, "XGB_W3_H21": 2.2, "CAT_W3_H21": 1.0}))
    assert [s["cell"] for s in few] == ["XGB_W3_H21"]
    # none eligible
    assert sw.select_stage2_cells(_cells({"LGBM_W3_H21": 5.0, "XGB_W3_H21": 1.0})) == []
    # NaN t is not eligible
    assert sw.select_stage2_cells(_cells({"XGB_W3_H21": float("nan")})) == []


def test_b0_parity_boundaries() -> None:
    assert sw.b0_parity_ok(0.0200)
    assert sw.b0_parity_ok(0.0190)
    assert sw.b0_parity_ok(0.0210)
    assert not sw.b0_parity_ok(0.0189)
    assert not sw.b0_parity_ok(0.0211)
    assert not sw.b0_parity_ok(None)
    assert not sw.b0_parity_ok(float("nan"))


def test_answer_family_material_boundary() -> None:
    assert sw.is_material(0.010, 3.0)
    assert sw.is_material(0.030 - 0.020, 3.0)  # float noise: 0.009999999999999998
    assert not sw.is_material(0.0099, 3.5)
    assert not sw.is_material(0.02, 2.99)
    assert not sw.is_material(0.02, None)

    lg = 0.020
    base = {
        f"{f}_{w}_{h}": {"mean_rankic": lg - 0.001, "t_nw": 2.0}
        for f in ("XGB", "CAT", "RIDGE", "MLP", "ENS")
        for w in ("W3", "WX")
        for h in ("H21", "H63")
    }
    for w in ("W3", "WX"):
        for h in ("H21", "H63"):
            base[f"LGBM_{w}_{h}"] = {"mean_rankic": lg, "t_nw": 3.0}
    assert sw.answer_family(sw.family_effect(base)) == "none"
    base["CAT_WX_H63"] = {"mean_rankic": lg + 0.010, "t_nw": 3.0}
    eff = sw.family_effect(base)
    assert eff["WX_H63"]["best_non_lgbm_family"] == "CAT"
    assert eff["WX_H63"]["material"] is True
    assert sw.answer_family(eff) == "material"
    # best family by RankIC is tested, even if another has higher t
    base["XGB_WX_H63"] = {"mean_rankic": lg + 0.012, "t_nw": 2.5}
    eff = sw.family_effect(base)
    assert eff["WX_H63"]["best_non_lgbm_family"] == "XGB"
    assert eff["WX_H63"]["material"] is False
    assert sw.answer_family(eff) == "none"


def test_rank_autocorr_perfect_and_reversed() -> None:
    d1 = pd.DataFrame(
        {
            "formation_date": pd.Timestamp("2020-01-31"),
            "symbol": list("abcdef"),
            "pred": np.arange(6.0),
        }
    )
    d2 = pd.DataFrame(
        {
            "formation_date": pd.Timestamp("2020-02-29"),
            "symbol": list("abcdef"),
            "pred": np.arange(6.0) * 2,
        }
    )
    assert sw.rank_autocorr(pd.concat([d1, d2]))["mean"] == pytest.approx(1.0)
    d2["pred"] = -np.arange(6.0)
    assert sw.rank_autocorr(pd.concat([d1, d2]))["mean"] == pytest.approx(-1.0)
