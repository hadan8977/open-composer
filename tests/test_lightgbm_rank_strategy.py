"""Tests for open_composer.research.kernel.lightgbm_rank_strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel.lightgbm_rank_strategy import (
    FIXED_HYPERPARAMETERS,
    LightGBMRankStrategy,
)


def _synthetic_frame(n_rows: int = 400, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    symbols = [f"S{i:03d}" for i in range(n_rows)]
    signal = rng.normal(size=n_rows)
    noise_feature = rng.normal(size=n_rows)
    # label_rank is monotonic in `signal` (plus small noise) so a model that
    # actually learns something should rank on `signal`, not `noise_feature`.
    label_rank = pd.Series(signal + 0.05 * rng.normal(size=n_rows)).rank(pct=True).to_numpy()
    return pd.DataFrame(
        {
            "symbol": symbols,
            "signal": signal,
            "noise_feature": noise_feature,
            "label_rank_5": label_rank,
        }
    )


def test_fit_then_score_before_fit_raises() -> None:
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    with pytest.raises(RuntimeError, match="before fit"):
        strategy.score(_synthetic_frame(10))


def test_top_feature_importances_before_fit_raises() -> None:
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    with pytest.raises(RuntimeError, match="before fit"):
        strategy.top_feature_importances()


def test_num_leaves_derived_from_max_depth() -> None:
    frame = _synthetic_frame()
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    strategy.fit(frame)
    assert strategy._model is not None
    assert strategy._model.get_params()["num_leaves"] == 2**3 - 1
    assert strategy._model.get_params()["max_depth"] == 3


def test_fixed_hyperparameters_applied_verbatim() -> None:
    frame = _synthetic_frame()
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=6)
    strategy.fit(frame)
    params = strategy._model.get_params()
    for key, value in FIXED_HYPERPARAMETERS.items():
        assert params[key] == value, f"{key} was overridden: {params[key]!r} != {value!r}"
    assert params["num_leaves"] == 2**6 - 1


def test_score_ranks_the_informative_feature_over_noise() -> None:
    # FIXED_HYPERPARAMETERS pins min_child_samples=200; a few thousand rows
    # are needed to give LightGBM room to make more than one or two splits
    # (the plan's production panels are far larger). A too-small fixture
    # here would just measure "the tree underfit to a near-constant leaf",
    # not whether the strategy correctly wires features -> a real model.
    train = _synthetic_frame(n_rows=4000, seed=1)
    test = _synthetic_frame(n_rows=4000, seed=2)
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    strategy.fit(train)
    scores = strategy.score(test)
    # The model should recover most of the rank ordering implied by `signal`
    # on held-out data -- a loose but real out-of-sample check, not a hand-
    # picked fixture. Spearman correlation via rank-of-rank Pearson.
    predicted_rank = scores.rank()
    true_rank = pd.Series(test["signal"].to_numpy(), index=test["symbol"].to_numpy()).rank()
    correlation = predicted_rank.corr(true_rank)
    assert correlation > 0.5, f"expected LightGBM to recover the signal, got corr={correlation}"


def test_score_index_is_symbol() -> None:
    frame = _synthetic_frame()
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    strategy.fit(frame)
    scores = strategy.score(frame)
    assert list(scores.index) == list(frame["symbol"])


def test_top_feature_importances_prefers_the_informative_feature() -> None:
    frame = _synthetic_frame(n_rows=800)
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=6)
    strategy.fit(frame)
    importances = strategy.top_feature_importances(n=2)
    assert list(importances.index) == ["signal", "noise_feature"]
    assert importances.iloc[0] > importances.iloc[1]


def test_top_feature_importances_respects_n() -> None:
    frame = _synthetic_frame()
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    strategy.fit(frame)
    assert len(strategy.top_feature_importances(n=1)) == 1


def test_refit_from_scratch_drops_prior_model_state() -> None:
    strategy = LightGBMRankStrategy(["signal", "noise_feature"], "label_rank_5", max_depth=3)
    strategy.fit(_synthetic_frame(seed=1))
    first_model = strategy._model
    strategy.fit(_synthetic_frame(seed=2))
    assert strategy._model is not first_model
