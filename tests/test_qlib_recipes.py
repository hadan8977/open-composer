"""Tests for ``scripts/run_h20260918_03_qlib_recipes.py`` (H-20260918-03).

No real ``data/`` table is read or written -- every test builds a tiny
synthetic panel in memory. Covers:

(a) each of the three registered models (``ridge``, ``qlib_lgbm``,
    ``double_ensemble``) trains and predicts on a tiny synthetic panel,
    and the two new models carry the card's *exact* published
    hyperparameters (loss/learning_rate/colsample_bytree/subsample/
    lambda_l1/lambda_l2/max_depth/num_leaves for LightGBM; num_models/
    enable_sr/enable_fs/alpha1/alpha2/bins_sr/bins_fs/decay/
    sample_ratios/sub_weights/epochs for DoubleEnsemble) -- with
    ``num_threads=2`` as the one disclosed deviation (card says 20; this
    box has 2 usable cores);
(b) ``topk_dropout_tranches`` holds exactly ``topk`` names once the pool is
    large enough and replaces at most ``n_drop`` of them per rebalance;
(c) ``cache_dir_for`` embeds both the suffix-or-"narrow" tag and the
    feature-family tag, so a broad run's cache can never be silently read
    back as (or overwrite) a narrow run's -- the exact 2026-09-18 defect
    this card's own module docstring says H-20260917-01 hit; and
(d) the open-to-open label helper (``_forward_open_return``) reproduces
    Qlib's ``Ref($close,-2)/Ref($close,-1)-1`` shape for the 1-day label
    and the card's 21-day generalization.
"""

from __future__ import annotations

import importlib

import numpy as np
import pandas as pd
import pytest

qlib_recipes = importlib.import_module("scripts.run_h20260918_03_qlib_recipes")
ml02 = importlib.import_module("scripts.run_h20260917_02_ml_ranking")


def _synthetic_panel(
    n_dates: int, n_per_date: int, n_features: int, seed: int = 0
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(X, y, groups)`` -- ``groups`` is a formation-date-like integer
    per row, ``y`` is a noisy linear function of the first two features so
    a trained model has something real to pick up on.
    """
    rng = np.random.default_rng(seed)
    n = n_dates * n_per_date
    X = rng.standard_normal((n, n_features))
    groups = np.repeat(np.arange(n_dates), n_per_date)
    y = 0.7 * X[:, 0] - 0.3 * X[:, 1] + 0.05 * rng.standard_normal(n)
    order = rng.permutation(n)  # so groups is not already sorted
    return X[order], y[order], groups[order]


# --------------------------------------------------------------------------
# (a) models
# --------------------------------------------------------------------------


def test_qlib_lgbm_model_has_published_hyperparameters() -> None:
    model = qlib_recipes.QlibLightGBMModel()
    assert model.params["objective"] == "regression"  # the card's "loss: mse"
    assert model.params["learning_rate"] == 0.2
    assert model.params["colsample_bytree"] == 0.8879
    assert model.params["subsample"] == 0.8789
    assert model.params["lambda_l1"] == 205.6999
    assert model.params["lambda_l2"] == 580.9768
    assert model.params["max_depth"] == 8
    assert model.params["num_leaves"] == 210
    # Disclosed deviation: card/Qlib says num_threads=20, this box has 2 cores.
    assert model.params["num_threads"] == 2


def test_qlib_lgbm_model_trains_and_predicts() -> None:
    X, y, groups = _synthetic_panel(n_dates=20, n_per_date=15, n_features=8, seed=1)
    model = qlib_recipes.QlibLightGBMModel()
    model.fit(X, y, groups)
    X_test = np.random.default_rng(2).standard_normal((25, 8))
    preds = model.predict(X_test)
    assert preds.shape == (25,)
    assert np.all(np.isfinite(preds))


def test_double_ensemble_model_has_published_hyperparameters() -> None:
    model = qlib_recipes.DoubleEnsembleModel()
    assert model.num_models == 3
    assert model.enable_sr is True
    assert model.enable_fs is True
    assert model.alpha1 == 1.0
    assert model.alpha2 == 1.0
    assert model.bins_sr == 10
    assert model.bins_fs == 5
    assert model.decay == 0.5
    assert model.sample_ratios == (0.8, 0.7, 0.6, 0.5, 0.4)
    assert model.sub_weights == (1.0, 1.0, 1.0)
    assert model.epochs == 28
    # bins_fs and sample_ratios must line up one-to-one (see module docstring).
    assert len(model.sample_ratios) == model.bins_fs


def test_double_ensemble_model_trains_and_predicts() -> None:
    X, y, groups = _synthetic_panel(n_dates=15, n_per_date=12, n_features=12, seed=3)
    model = qlib_recipes.DoubleEnsembleModel()
    model.fit(X, y, groups)
    assert len(model._submodels) == model.num_models
    X_test = np.random.default_rng(4).standard_normal((30, 12))
    preds = model.predict(X_test)
    assert preds.shape == (30,)
    assert np.all(np.isfinite(preds))


def test_ridge_model_trains_and_predicts() -> None:
    """The card's third model is ``ridge`` from ``ml02``, registered
    unchanged -- a quick sanity check that the reuse (not a copy) works.
    """
    X, y, groups = _synthetic_panel(n_dates=10, n_per_date=10, n_features=5, seed=5)
    model = qlib_recipes.MODEL_REGISTRY["ridge"]()
    assert isinstance(model, ml02.RidgeRankingModel)
    model.fit(X, y, groups)
    preds = model.predict(np.random.default_rng(6).standard_normal((10, 5)))
    assert preds.shape == (10,)


def test_model_registry_has_all_three_card_models() -> None:
    assert set(qlib_recipes.MODEL_NAMES) == {"ridge", "qlib_lgbm", "double_ensemble"}
    for name in qlib_recipes.MODEL_NAMES:
        assert name in qlib_recipes.MODEL_REGISTRY
        assert name in ml02.MODEL_REGISTRY  # extended, not shadowed (see module docstring)


# --------------------------------------------------------------------------
# (b) TopkDropoutStrategy(topk, n_drop)
# --------------------------------------------------------------------------


def test_topk_dropout_holds_topk_and_replaces_at_most_n_drop() -> None:
    topk, n_drop = 5, 2
    n_dates, n_symbols = 6, 20
    rng = np.random.default_rng(7)
    dates = [pd.Timestamp("2024-01-01") + pd.DateOffset(months=i) for i in range(n_dates)]
    symbols = [f"S{i:02d}" for i in range(n_symbols)]
    rows = []
    for date in dates:
        scores = rng.standard_normal(n_symbols)
        for symbol, score in zip(symbols, scores, strict=True):
            rows.append({"formation_date": date, "symbol": symbol, "score": score})
    frame = pd.DataFrame(rows)

    tranches = qlib_recipes.topk_dropout_tranches(frame, "score", dates, topk=topk, n_drop=n_drop)

    previous: set[str] = set()
    for i, date in enumerate(dates):
        held = set(tranches[date])
        assert len(held) == topk
        weights = tranches[date]
        assert all(abs(w - 1.0 / topk) < 1e-9 for w in weights.values())
        if i > 0:
            added = held - previous
            dropped = previous - held
            assert len(added) <= n_drop
            assert len(dropped) <= n_drop
        previous = held


def test_topk_dropout_card_constants_are_50_and_5() -> None:
    """The card says do not tune -- lock in the literal (50, 5)."""
    assert qlib_recipes.TOPK == 50
    assert qlib_recipes.N_DROP == 5


# --------------------------------------------------------------------------
# (c) cache path includes the feature-family tag
# --------------------------------------------------------------------------


def test_cache_dir_includes_suffix_and_feature_family_tag() -> None:
    broad_layered = qlib_recipes.cache_dir_for("_broad", "layered")
    parts = broad_layered.parts
    assert "broad" in parts
    assert "layered" in parts

    narrow_alpha158 = qlib_recipes.cache_dir_for("", "alpha158")
    parts_narrow = narrow_alpha158.parts
    assert "narrow" in parts_narrow
    assert "alpha158" in parts_narrow

    # A broad run and a narrow run must never resolve to the same directory,
    # and neither must the two feature families under the same suffix --
    # exactly the collision the module docstring says H-20260917-01 hit.
    assert broad_layered != narrow_alpha158
    assert qlib_recipes.cache_dir_for("_broad", "alpha158") != qlib_recipes.cache_dir_for(
        "_broad", "layered"
    )
    assert qlib_recipes.cache_dir_for("_broad", "alpha158") != qlib_recipes.cache_dir_for(
        "", "alpha158"
    )


def test_report_and_summary_paths_are_tagged_the_same_way() -> None:
    report = qlib_recipes.report_path_for("_broad", "layered")
    summary = qlib_recipes.summary_path_for("_broad", "layered")
    assert "broad_layered" in report.name
    assert "broad_layered" in summary.name


# --------------------------------------------------------------------------
# (d) open-to-open label helper
# --------------------------------------------------------------------------


def test_forward_open_return_matches_qlib_one_day_label() -> None:
    dates = pd.date_range("2024-01-01", periods=6, freq="D")
    opens = pd.DataFrame(
        {"AAA": [10.0, 11.0, 12.0, 13.0, 14.0, 15.0], "BBB": [1.0, 1.0, 1.0, 2.0, 2.0, 2.0]},
        index=dates,
    )
    formation = pd.DataFrame(
        {"formation_date": [dates[0], dates[0], dates[2]], "symbol": ["AAA", "BBB", "BBB"]}
    )
    one_day = qlib_recipes._forward_open_return(opens, formation, lead=1, horizon=1)
    # AAA at dates[0]: open[2]/open[1] - 1 = 12/11 - 1
    assert one_day.iloc[0] == pytest.approx(12.0 / 11.0 - 1.0)
    # BBB at dates[0]: open[2]/open[1] - 1 = 1/1 - 1 = 0
    assert one_day.iloc[1] == pytest.approx(0.0)
    # BBB at dates[2]: open[4]/open[3] - 1 = 2/2 - 1 = 0
    assert one_day.iloc[2] == pytest.approx(0.0)

    twenty_one_day = qlib_recipes._forward_open_return(opens, formation, lead=1, horizon=3)
    # AAA at dates[0]: open[4]/open[1] - 1 = 14/11 - 1 (falls off the end for horizon 21
    # in this 6-row fixture, so horizon=3 is used instead to stay in range)
    assert twenty_one_day.iloc[0] == pytest.approx(14.0 / 11.0 - 1.0)
