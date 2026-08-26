from __future__ import annotations

from typing import Any

from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.models.strategy_spec import StrategySpec

_LIGHTGBM_DEFAULTS: dict[str, Any] = {
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
    """Create the estimator declared by the StrategySpec."""
    if spec.model is None:
        raise ValueError("create_model requires spec.model")
    kind = spec.model.kind
    if kind == "ridge_regressor":
        params = {"alpha": 1.0, "fit_intercept": True, **spec.model.hyperparameters}
        return Pipeline([("scale", StandardScaler()), ("model", Ridge(**params))])
    if kind == "logistic_regression_classifier":
        params = {
            "C": 1.0,
            "penalty": "l2",
            "solver": "lbfgs",
            "max_iter": 1000,
            "random_state": spec.model.training.seed,
            **spec.model.hyperparameters,
        }
        return Pipeline([("scale", StandardScaler()), ("model", LogisticRegression(**params))])
    try:
        from lightgbm import LGBMClassifier, LGBMRegressor
    except ImportError as exc:  # pragma: no cover - exercised when dependency missing
        raise RuntimeError(
            "LightGBM is required for StrategySpec.model; run `uv sync` to install ML deps"
        ) from exc
    params = {**_LIGHTGBM_DEFAULTS, **spec.model.hyperparameters}
    params["random_state"] = spec.model.training.seed
    if kind == "lightgbm_classifier":
        return LGBMClassifier(**params)
    if kind == "lightgbm_regressor":
        return LGBMRegressor(**params)
    raise ValueError(f"unsupported model kind: {kind}")


def is_classifier_model(spec: StrategySpec) -> bool:
    return bool(spec.model and spec.model.kind.endswith("_classifier"))


def create_lightgbm_classifier(
    *,
    seed: int = 42,
    hyperparameters: dict[str, Any] | None = None,
):
    """Create the conservative classifier used by route-level research gates."""
    try:
        from lightgbm import LGBMClassifier
    except ImportError as exc:  # pragma: no cover - exercised when dependency missing
        raise RuntimeError(
            "LightGBM is required for PDR ML gate training; run `uv sync` to install ML deps"
        ) from exc
    params = {**_LIGHTGBM_DEFAULTS, **(hyperparameters or {})}
    params["random_state"] = seed
    return LGBMClassifier(**params)
