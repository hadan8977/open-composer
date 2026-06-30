from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.expressions import prepare_factor_frame
from open_composer.models.strategy_spec import StrategySpec


def build_feature_matrix(spec: StrategySpec, frame: pd.DataFrame, root: Path) -> pd.DataFrame:
    """Build the ML feature matrix from declared StrategySpec factors."""
    if spec.model is None:
        raise ValueError("build_feature_matrix requires spec.model")
    prepared = prepare_factor_frame(
        frame,
        spec.factors,
        root=root,
        symbol=spec.primary_symbol,
        require_feature_symbol=False,
    )
    return pd.DataFrame(
        {
            feature: pd.to_numeric(prepared[feature], errors="coerce")
            for feature in spec.model.features
        },
        index=prepared.index,
    )


def build_label(spec: StrategySpec, frame: pd.DataFrame) -> pd.Series:
    """Build a forward-looking label aligned to the current bar index."""
    if spec.model is None:
        raise ValueError("build_label requires spec.model")
    horizon = spec.model.label.horizon_bars
    close = pd.to_numeric(frame["close"], errors="coerce")
    forward_return = close.shift(-horizon) / close - 1.0
    if spec.model.label.type == "forward_direction":
        threshold = (spec.model.label.threshold_pct or 0.0) / 100.0
        label = (forward_return >= threshold).astype(float)
        label[forward_return.isna()] = float("nan")
        return label
    return forward_return
