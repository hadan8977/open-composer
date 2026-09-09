"""Step 11 Wave A 3.5: the B0-B2 baseline-chain ranking strategies.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.5. Each class
implements ``loop.RankingStrategy`` (``fit`` once per walk-forward test year
on an embargoed training window, ``score`` once per weekly rebalance date).
B3 (LightGBM) is Wave B's job (a small preregistered grid, not a single
fixed baseline) and lives in ``scripts/run_b3_grid.py`` instead of here.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import pandas as pd


class EqualWeightUniverseStrategy:
    """B0: the whole PIT-eligible universe, equal-weighted -- the control.
    ``fit`` is a no-op (no parameters); ``score`` returns a constant so every
    symbol ties and ``top_k=None`` (the caller's job) keeps them all.
    """

    def fit(  # noqa: ARG002 -- interface no-op
        self, train_frame: pd.DataFrame, sample_weight: pd.Series | None = None
    ) -> None:
        return None

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        return pd.Series(1.0, index=asof_frame["symbol"].to_numpy())


class MomentumFactorStrategy:
    """B1: single factor, trailing 12-1 momentum (``momentum_252_21`` --
    ``ret_252 - ret_21``, plan section 3.3's skip-most-recent-month
    momentum), ranked descending. ``fit`` is a no-op: the rule is fixed, not
    estimated.
    """

    def __init__(self, factor_column: str = "momentum_252_21") -> None:
        self.factor_column = factor_column

    def fit(  # noqa: ARG002
        self, train_frame: pd.DataFrame, sample_weight: pd.Series | None = None
    ) -> None:
        return None

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        return asof_frame.set_index("symbol")[self.factor_column]


class RidgeRankStrategy:
    """B2: ridge regression of the standardized feature block onto the
    cross-sectional percentile-rank label (plan section 3.5: "岭回归（标准化
    特征 → 标签分位），按年重训"). Refit from scratch every test year on that
    year's anchored, embargoed training window -- no state carries over
    between years, so a later year's fit can never see an earlier year's
    residual influence beyond what its own training window already implies.

    **Constant-memory fit.** The expanding-window training frame reaches ~6M
    rows by the last test year. Materializing it as one dense matrix and
    handing that to ``StandardScaler`` + ``sklearn.Ridge`` costs three
    copies (~3GB on this 3.9GB box) and was OOM-killed on 2026-09-08. With
    only ~23-40 features, the normal equations are tiny, so this accumulates
    the Gram matrix ``Z'Z`` (p x p) and ``Z'y`` (p) in row chunks and solves
    ``(Z'Z + alpha*I) w = Z'(y - ybar)`` directly: peak memory is one chunk
    (tens of MB) regardless of how many rows the window holds, and the
    solution is the same one ``Ridge(solver="cholesky")`` computes on
    standardized inputs (asserted against sklearn in
    ``tests/test_baseline_strategies_ridge.py``). Moments accumulate in
    float64 even though the panel is float32.
    """

    def __init__(
        self,
        feature_columns: Sequence[str],
        label_column: str,
        alpha: float = 1.0,
        chunk_rows: int = 500_000,
    ) -> None:
        self.feature_columns = list(feature_columns)
        self.label_column = label_column
        self.alpha = alpha
        self.chunk_rows = chunk_rows
        self._mean: np.ndarray | None = None
        self._scale: np.ndarray | None = None
        self._coef: np.ndarray | None = None
        self._intercept: float | None = None

    def _chunks(self, frame: pd.DataFrame, sample_weight: pd.Series | None = None):
        for start in range(0, len(frame), self.chunk_rows):
            block = frame.iloc[start : start + self.chunk_rows]
            x = block[self.feature_columns].to_numpy(dtype=np.float64)
            y = block[self.label_column].to_numpy(dtype=np.float64)
            # Step 13 Track M: an all-ones weight chunk when no
            # sample_weight was given makes every formula below identical,
            # element for element, to the original unweighted computation
            # (multiplying by 1.0 changes nothing) -- so omitting
            # sample_weight (every pre-Step-13 caller) reproduces the exact
            # same fit as before this method learned about weights at all.
            w = (
                np.ones(len(block), dtype=np.float64)
                if sample_weight is None
                else sample_weight.iloc[start : start + self.chunk_rows].to_numpy(dtype=np.float64)
            )
            yield x, y, w

    def fit(self, train_frame: pd.DataFrame, sample_weight: pd.Series | None = None) -> None:
        n_features = len(self.feature_columns)
        total_weight = 0.0
        sum_x = np.zeros(n_features)
        sum_x2 = np.zeros(n_features)
        sum_y = 0.0
        for x, y, w in self._chunks(train_frame, sample_weight):
            total_weight += float(w.sum())
            sum_x += x.T @ w
            sum_x2 += np.einsum("ij,ij,i->j", x, x, w)
            sum_y += float(y @ w)
        if total_weight <= 0:
            raise ValueError("RidgeRankStrategy.fit received an empty training frame")
        mean = sum_x / total_weight
        # Weighted population variance (ddof=0), matching StandardScaler
        # when every weight is 1; a constant feature gets scale 1.0 so it
        # standardizes to 0 instead of dividing by zero -- also
        # StandardScaler's behavior.
        variance = np.maximum(sum_x2 / total_weight - mean**2, 0.0)
        scale = np.sqrt(variance)
        scale[scale == 0.0] = 1.0
        y_mean = sum_y / total_weight

        gram = np.zeros((n_features, n_features))
        rhs = np.zeros(n_features)
        for x, y, w in self._chunks(train_frame, sample_weight):
            z = (x - mean) / scale
            gram += (z * w[:, None]).T @ z
            rhs += z.T @ (w * (y - y_mean))
        coef = np.linalg.solve(gram + self.alpha * np.eye(n_features), rhs)

        self._mean = mean
        self._scale = scale
        self._coef = coef
        self._intercept = y_mean

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        if self._coef is None or self._mean is None or self._scale is None:
            raise RuntimeError("RidgeRankStrategy.score called before fit")
        x = asof_frame[self.feature_columns].to_numpy(dtype=np.float64)
        z = (x - self._mean) / self._scale
        predictions = z @ self._coef + float(self._intercept or 0.0)
        return pd.Series(predictions, index=asof_frame["symbol"].to_numpy())
