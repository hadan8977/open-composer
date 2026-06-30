from __future__ import annotations

from typing import Any

from open_composer.models.strategy_spec import StrategySpec

_REGRESSOR_DEFAULTS: dict[str, Any] = {
    "num_leaves": 15,
    "max_depth": 4,
    "min_child_samples": 20,
    "learning_rate": 0.05,
    "n_estimators": 200,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "reg_lambda": 1.0,
    "random_state": 42,
    "n_jobs": 1,
    "verbosity": -1,
}


def create_model(spec: StrategySpec):
    """Create a conservative LightGBM estimator for small financial samples."""
    if spec.model is None:
        raise ValueError("create_model requires spec.model")
    try:
        from lightgbm import LGBMClassifier, LGBMRegressor
    except ImportError as exc:  # pragma: no cover - exercised when dependency missing
        raise RuntimeError(
            "LightGBM is required for StrategySpec.model; run `uv sync` to install ML deps"
        ) from exc
    params = {**_REGRESSOR_DEFAULTS, **spec.model.hyperparameters}
    params["random_state"] = spec.model.training.seed
    if spec.model.kind == "lightgbm_classifier":
        return LGBMClassifier(**params)
    return LGBMRegressor(**params)
