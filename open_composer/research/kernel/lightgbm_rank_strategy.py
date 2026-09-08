"""Step 11 Wave B: B3, LightGBM ranking.

docs/plan-step-11-ml-first-loop-2026-09-06.zh.md section 4. Regression onto
the cross-sectional percentile-rank label (the same target B2's ridge uses,
``label_rank_h``) rather than ``lambdarank`` -- the plan asks for either,
recorded as chosen so this is not mistaken for an oversight. Implements the
same ``loop.RankingStrategy`` protocol as ``baseline_strategies.py``'s B0-B2
(``fit`` once per walk-forward test year on that year's anchored, embargoed
training window; ``score`` once per weekly rebalance date), refitting from
scratch every year exactly like B2's ``RidgeRankStrategy`` -- no state carries
over between years.

All hyperparameters except ``num_leaves`` (derived from the grid's tree-depth
axis, ``2**max_depth - 1``) are fixed by the plan text, not searched:
``n_estimators=400, learning_rate=0.03, min_child_samples=200,
feature_fraction=0.7, bagging_fraction=0.7, seed=7``. The grid itself (label
horizon x tree depth x feature set, <=12 configs) is assembled by
``scripts/run_b3_grid.py``, not here -- this module is just the one
``RankingStrategy`` implementation every grid cell instantiates with
different ``(feature_columns, label_column, max_depth)``.
"""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
from lightgbm import LGBMRegressor

#: Plan section 4's fixed hyperparameters, held constant across every grid
#: cell -- only max_depth (and therefore num_leaves) and the caller's choice
#: of feature_columns/label_column vary between grid cells.
FIXED_HYPERPARAMETERS: dict[str, float | int] = {
    "n_estimators": 400,
    "learning_rate": 0.03,
    "min_child_samples": 200,
    "feature_fraction": 0.7,
    "bagging_fraction": 0.7,
    "bagging_freq": 1,
    "random_state": 7,
    "verbosity": -1,
}


class LightGBMRankStrategy:
    """B3: LightGBM regressor trained on ``feature_columns`` -> the
    cross-sectional percentile-rank label ``label_column``, refit from
    scratch every test year (see module docstring).
    """

    def __init__(
        self,
        feature_columns: Sequence[str],
        label_column: str,
        *,
        max_depth: int,
    ) -> None:
        self.feature_columns = list(feature_columns)
        self.label_column = label_column
        self.max_depth = max_depth
        self._model: LGBMRegressor | None = None

    def fit(self, train_frame: pd.DataFrame) -> None:
        x = train_frame[self.feature_columns].to_numpy()
        y = train_frame[self.label_column].to_numpy()
        model = LGBMRegressor(
            max_depth=self.max_depth,
            num_leaves=2**self.max_depth - 1,
            **FIXED_HYPERPARAMETERS,
        )
        model.fit(x, y)
        self._model = model

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        if self._model is None:
            raise RuntimeError("LightGBMRankStrategy.score called before fit")
        x = asof_frame[self.feature_columns].to_numpy()
        predictions = self._model.predict(x)
        return pd.Series(predictions, index=asof_frame["symbol"].to_numpy())

    def top_feature_importances(self, n: int = 20) -> pd.Series:
        """Top-``n`` features by LightGBM's default (split-count) importance,
        for the plan's "特征重要性前 20" report requirement.
        """
        if self._model is None:
            raise RuntimeError("top_feature_importances called before fit")
        importances = pd.Series(
            self._model.feature_importances_, index=self.feature_columns
        ).sort_values(ascending=False)
        return importances.head(n)
