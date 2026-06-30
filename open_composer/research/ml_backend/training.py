from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.ml_backend.feature_pipeline import build_feature_matrix, build_label
from open_composer.research.ml_backend.model_factory import create_model
from open_composer.research.ml_backend.windows import MLWindowSlice, ml_walk_forward_slices


@dataclass(frozen=True)
class FoldResult:
    fold: int
    train_rows: int
    test_rows: int
    train_metric: float | None
    test_metric: float | None
    feature_importance: dict[str, float]
    train_start_idx: int
    train_end_idx: int
    test_start_idx: int
    test_end_idx: int


@dataclass(frozen=True)
class MLTrainingRun:
    strategy_name: str
    folds: list[FoldResult]
    full_predictions: pd.Series
    labels: pd.Series
    feature_importance_mean: dict[str, float]
    window_metadata: list[dict[str, Any]] = field(default_factory=list)

    def to_payload(self) -> dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "fold_count": len(self.folds),
            "folds": [fold.__dict__ for fold in self.folds],
            "feature_importance_mean": self.feature_importance_mean,
            "prediction_count": int(self.full_predictions.notna().sum()),
            "test_metric_mean": _mean_or_none(
                [fold.test_metric for fold in self.folds if fold.test_metric is not None]
            ),
            "window_metadata": self.window_metadata,
        }


def run_rolling_training(spec: StrategySpec, frame: pd.DataFrame, root: Path) -> MLTrainingRun:
    """Fit on purged train windows and stitch only out-of-sample test predictions."""
    if spec.model is None:
        raise ValueError("run_rolling_training requires spec.model")
    X = build_feature_matrix(spec, frame, root)
    y = build_label(spec, frame)
    model_cfg = spec.model
    slices = ml_walk_forward_slices(
        frame,
        window_bars=model_cfg.training.window_bars,
        test_window_bars=model_cfg.training.test_window_bars,
        retrain_every_bars=model_cfg.training.retrain_every_bars,
        horizon_bars=model_cfg.label.horizon_bars,
        embargo_bars=model_cfg.training.embargo_bars,
    )
    predictions = pd.Series(float("nan"), index=frame.index, dtype="float64")
    folds: list[FoldResult] = []
    importances: list[dict[str, float]] = []
    metadata: list[dict[str, Any]] = []
    for window in slices:
        fold = _fit_predict_fold(spec, X, y, predictions, window)
        if fold is None:
            continue
        folds.append(fold)
        importances.append(fold.feature_importance)
        metadata.append(window.metadata.model_dump(mode="json"))
    return MLTrainingRun(
        strategy_name=spec.name,
        folds=folds,
        full_predictions=predictions,
        labels=y,
        feature_importance_mean=_mean_importances(importances),
        window_metadata=metadata,
    )


def _fit_predict_fold(
    spec: StrategySpec,
    X: pd.DataFrame,
    y: pd.Series,
    predictions: pd.Series,
    window: MLWindowSlice,
) -> FoldResult | None:
    train_X = X.iloc[window.train_start_idx : window.train_end_idx]
    train_y = y.iloc[window.train_start_idx : window.train_end_idx]
    test_X = X.iloc[window.test_start_idx : window.test_end_idx]
    test_y = y.iloc[window.test_start_idx : window.test_end_idx]
    train_joined = train_X.join(train_y.rename("__label__")).dropna()
    test_joined = test_X.join(test_y.rename("__label__")).dropna()
    if len(train_joined) < 30 or len(test_joined) < 5:
        return None
    estimator = create_model(spec)
    train_features = train_joined.drop(columns=["__label__"])
    train_label = train_joined["__label__"]
    test_features = test_joined.drop(columns=["__label__"])
    test_label = test_joined["__label__"]
    if spec.model and spec.model.kind == "lightgbm_classifier":
        train_label = train_label.round().astype(int)
        test_label = test_label.round().astype(int)
    estimator.fit(train_features, train_label)
    train_pred = _predict(estimator, train_features, spec)
    test_pred = _predict(estimator, test_features, spec)
    predictions.loc[test_joined.index] = test_pred
    importance = {
        feature: float(value)
        for feature, value in zip(
            list(train_features.columns),
            getattr(estimator, "feature_importances_", [0.0] * len(train_features.columns)),
            strict=True,
        )
    }
    return FoldResult(
        fold=window.fold,
        train_rows=int(len(train_joined)),
        test_rows=int(len(test_joined)),
        train_metric=_rank_ic(train_pred, train_label),
        test_metric=_rank_ic(test_pred, test_label),
        feature_importance=importance,
        train_start_idx=window.train_start_idx,
        train_end_idx=window.train_end_idx,
        test_start_idx=window.test_start_idx,
        test_end_idx=window.test_end_idx,
    )


def _predict(estimator: Any, features: pd.DataFrame, spec: StrategySpec) -> pd.Series:
    if (
        spec.model
        and spec.model.kind == "lightgbm_classifier"
        and hasattr(estimator, "predict_proba")
    ):
        raw = estimator.predict_proba(features)[:, 1]
    else:
        raw = estimator.predict(features)
    return pd.Series(raw, index=features.index, dtype="float64")


def _rank_ic(prediction: pd.Series, label: pd.Series) -> float | None:
    joined = pd.DataFrame({"prediction": prediction, "label": label}).dropna()
    if len(joined) < 3:
        return None
    if joined["prediction"].nunique(dropna=True) <= 1 or joined["label"].nunique(dropna=True) <= 1:
        return None
    value = joined["prediction"].rank().corr(joined["label"].rank())
    return None if pd.isna(value) else float(value)


def _mean_importances(rows: list[dict[str, float]]) -> dict[str, float]:
    if not rows:
        return {}
    keys = sorted({key for row in rows for key in row})
    return {key: float(sum(row.get(key, 0.0) for row in rows) / len(rows)) for key in keys}


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))
