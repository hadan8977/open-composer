from __future__ import annotations

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec


def predictions_to_signals(
    predictions: pd.Series,
    spec: StrategySpec,
    frame: pd.DataFrame,
) -> tuple[pd.Series, pd.Series]:
    """Convert stitched OOS predictions into entry/exit masks aligned to frame."""
    if spec.model is None:
        raise ValueError("predictions_to_signals requires spec.model")
    aligned = predictions.reindex(frame.index)
    if spec.model.selection.method == "top_quantile":
        quantile = spec.model.selection.quantile
        if quantile is None:
            raise ValueError("top_quantile selection requires quantile")
        threshold = aligned.expanding(min_periods=20).quantile(quantile)
        entry = aligned >= threshold
        exit_ = aligned < threshold
    else:
        threshold = float(spec.model.selection.threshold or 0.0)
        entry = aligned > threshold
        exit_threshold = -threshold if threshold > 0 else threshold
        exit_ = aligned < exit_threshold
    entry = entry.fillna(False).astype(bool)
    exit_ = exit_.fillna(False).astype(bool)
    return entry, exit_
