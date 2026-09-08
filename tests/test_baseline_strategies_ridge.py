"""RidgeRankStrategy's chunked normal-equations fit must agree with sklearn.

The chunked Gram accumulation exists to keep peak memory independent of the
training window size (see the class docstring); this pins it to the reference
implementation it replaced -- StandardScaler + sklearn.linear_model.Ridge --
so a memory optimization can never silently become a different model.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

from open_composer.research.kernel.baseline_strategies import RidgeRankStrategy

FEATURES = [f"f{i}" for i in range(8)]


def _frame(rows: int, seed: int = 7, constant_feature: bool = False) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    data = rng.standard_normal((rows, len(FEATURES)))
    if constant_feature:
        data[:, 3] = 2.5
    frame = pd.DataFrame(data, columns=FEATURES)
    frame["label"] = data @ np.linspace(1.0, -1.0, len(FEATURES)) + rng.standard_normal(rows) * 0.1
    frame["symbol"] = [f"S{i}" for i in range(rows)]
    return frame


def _sklearn_reference(frame: pd.DataFrame, alpha: float) -> tuple[np.ndarray, np.ndarray]:
    scaler = StandardScaler()
    x = scaler.fit_transform(frame[FEATURES].to_numpy(dtype=np.float64))
    model = Ridge(alpha=alpha, solver="cholesky")
    model.fit(x, frame["label"].to_numpy(dtype=np.float64))
    return model.coef_, model.predict(x)


@pytest.mark.parametrize("chunk_rows", [10_000, 137, 1])
def test_chunked_fit_matches_sklearn_regardless_of_chunk_size(chunk_rows: int) -> None:
    frame = _frame(500)
    strategy = RidgeRankStrategy(FEATURES, "label", alpha=1.0, chunk_rows=chunk_rows)
    strategy.fit(frame)
    reference_coef, reference_predictions = _sklearn_reference(frame, alpha=1.0)

    np.testing.assert_allclose(strategy._coef, reference_coef, rtol=1e-9, atol=1e-9)
    np.testing.assert_allclose(
        strategy.score(frame).to_numpy(), reference_predictions, rtol=1e-8, atol=1e-8
    )


@pytest.mark.parametrize("alpha", [0.1, 1.0, 100.0])
def test_alpha_is_applied_the_same_way_as_sklearn(alpha: float) -> None:
    frame = _frame(400, seed=11)
    strategy = RidgeRankStrategy(FEATURES, "label", alpha=alpha)
    strategy.fit(frame)
    reference_coef, _ = _sklearn_reference(frame, alpha=alpha)
    np.testing.assert_allclose(strategy._coef, reference_coef, rtol=1e-9, atol=1e-9)


def test_constant_feature_does_not_divide_by_zero() -> None:
    frame = _frame(300, seed=3, constant_feature=True)
    strategy = RidgeRankStrategy(FEATURES, "label", alpha=1.0)
    strategy.fit(frame)
    scores = strategy.score(frame)
    assert np.isfinite(scores.to_numpy()).all()
    # StandardScaler maps a constant column to zeros, so it carries no signal.
    assert strategy._scale[3] == 1.0


def test_score_before_fit_raises() -> None:
    with pytest.raises(RuntimeError, match="called before fit"):
        RidgeRankStrategy(FEATURES, "label").score(_frame(5))


def test_empty_training_frame_raises() -> None:
    with pytest.raises(ValueError, match="empty training frame"):
        RidgeRankStrategy(FEATURES, "label").fit(_frame(0))


def test_index_is_the_symbol_column() -> None:
    frame = _frame(20)
    strategy = RidgeRankStrategy(FEATURES, "label", alpha=1.0)
    strategy.fit(frame)
    assert list(strategy.score(frame).index) == list(frame["symbol"])
