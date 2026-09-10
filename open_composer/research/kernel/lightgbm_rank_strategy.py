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

import numpy as np
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
        num_threads: int | None = None,
        max_bin: int | None = None,
    ) -> None:
        self.feature_columns = list(feature_columns)
        self.label_column = label_column
        self.max_depth = max_depth
        #: 2026-09-10 Track M memory fix: both default to ``None`` (LightGBM's
        #: own defaults, byte-for-byte unchanged from every pre-existing
        #: caller, including Step 11's B3 grid) so this is opt-in, not a
        #: silent behavior change for anyone not passing them. A wider
        #: feature set (e.g. alpha158's 154 columns) OOM-killed at the
        #: 1.8GB run_capped.sh cap; num_threads caps LightGBM's internal
        #: thread pool (each thread duplicates working buffers) and
        #: max_bin=63 (LightGBM's default is 255) shrinks the per-feature
        #: histogram, both real, disclosed reductions in compute/precision
        #: traded for peak memory, not a free win.
        self.num_threads = num_threads
        self.max_bin = max_bin
        self._model: LGBMRegressor | None = None

    def fit(self, train_frame: pd.DataFrame, sample_weight: pd.Series | None = None) -> None:
        # float32 for the same reason as RidgeRankStrategy.fit: the default
        # upcast to float64 doubles a multi-GB training matrix on a 3.9GB
        # box. LightGBM bins features internally, so float32 input costs no
        # accuracy at all here.
        x = train_frame[self.feature_columns].to_numpy(dtype=np.float32)
        y = train_frame[self.label_column].to_numpy(dtype=np.float32)
        extra_params: dict[str, int] = {}
        if self.num_threads is not None:
            extra_params["num_threads"] = self.num_threads
        if self.max_bin is not None:
            extra_params["max_bin"] = self.max_bin
        model = LGBMRegressor(
            max_depth=self.max_depth,
            num_leaves=2**self.max_depth - 1,
            **FIXED_HYPERPARAMETERS,
            **extra_params,
        )
        # Step 13 Track M's recency_halflife_days: omitting sample_weight
        # (every pre-Step-13 caller) is LightGBM's own default of uniform
        # weight, so this is unchanged for every existing experiment.
        w = sample_weight.to_numpy(dtype=np.float32) if sample_weight is not None else None
        model.fit(x, y, sample_weight=w)
        self._model = model

    def score(self, asof_frame: pd.DataFrame) -> pd.Series:
        if self._model is None:
            raise RuntimeError("LightGBMRankStrategy.score called before fit")
        x = asof_frame[self.feature_columns].to_numpy(dtype=np.float32)
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
