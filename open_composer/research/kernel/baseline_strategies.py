"""Step 11 Wave A 3.5: the B0-B2 baseline-chain ranking strategies.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 3.5. Each class
implements ``loop.RankingStrategy`` (``fit`` once per walk-forward test year
on an embargoed training window, ``score`` once per weekly rebalance date).
B3 (LightGBM) is Wave B's job (a small preregistered grid, not a single
fixed baseline) and lives in ``scripts/run_b3_grid.py`` instead of here.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler


class EqualWeightUniverseStrategy:
    """B0: the whole PIT-eligible universe, equal-weighted -- the control.
    ``fit`` is a no-op (no parameters); ``score`` returns a constant so every
    symbol ties and ``top_k=None`` (the caller's job) keeps them all.
    """

    def fit(self, train_frame: pd.DataFrame) -> None:  # noqa: ARG002 -- interface no-op
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

    def fit(self, train_frame: pd.DataFrame) -> None:  # noqa: ARG002
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
    """

    def __init__(
        self, feature_columns: Sequence[str], label_column: str, alpha: float = 1.0
    ) -> None:
        self.feature_columns = list(feature_columns)
        self.label_column = label_column
        self.alpha = alpha
        self._scaler: StandardScaler | None = None
        self._model: Ridge | None = None

    def fit(self, train_frame: pd.DataFrame) -> None:
        x = train_frame[self.feature_columns].to_numpy()
        y = train_frame[self.label_column].to_numpy()
        scaler = StandardScaler()
        x_scaled = scaler.fit_transform(x)
        model = Ridge(alpha=self.alpha, random_state=7)
        model.fit(x_scaled, y)
        self._scaler = scaler
        self._model = model

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        if self._scaler is None or self._model is None:
            raise RuntimeError("RidgeRankStrategy.score called before fit")
        x = asof_frame[self.feature_columns].to_numpy()
        x_scaled = self._scaler.transform(x)
        predictions = self._model.predict(x_scaled)
        return pd.Series(predictions, index=asof_frame["symbol"].to_numpy())
