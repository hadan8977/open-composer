from __future__ import annotations

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.ml_backend.feature_pipeline import build_feature_matrix, build_label
from open_composer.research.ml_backend.windows import ml_walk_forward_slices


def _frame(n: int = 180) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=n, freq="D", tz="UTC")
    close = pd.Series(range(100, 100 + n), dtype="float64")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": 1_000_000,
        }
    )


def _spec() -> StrategySpec:
    return StrategySpec.model_validate(
        {
            "name": "ml_no_lookahead_probe",
            "description": "test",
            "timeframe": "daily",
            "universe": ["QQQ"],
            "lifecycle": "draft",
            "entry": {"all": ["close > sma(close, 2)"], "any": []},
            "exit": {"all": [], "any": ["close < sma(close, 2)"]},
            "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5},
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "QQQ"},
            "factors": {
                "sma2": {"source": "expression", "expression": "sma(close, 2)"},
                "roc1": {
                    "source": "expression",
                    "expression": "(close - lag(close, 1)) / lag(close, 1)",
                },
            },
            "model": {
                "features": ["sma2", "roc1"],
                "label": {"type": "forward_return", "horizon_bars": 5},
                "training": {
                    "window_bars": 120,
                    "test_window_bars": 21,
                    "retrain_every_bars": 21,
                    "embargo_bars": 5,
                },
            },
        }
    )


def test_label_alignment_and_tail_nan() -> None:
    spec = _spec()
    frame = _frame()
    label = build_label(spec, frame)

    assert label.iloc[0] == frame["close"].iloc[5] / frame["close"].iloc[0] - 1
    assert label.tail(5).isna().all()


def test_feature_matrix_uses_current_and_past_bars(tmp_path) -> None:
    spec = _spec()
    frame = _frame()
    X = build_feature_matrix(spec, frame, tmp_path)

    assert X["sma2"].iloc[10] == (frame["close"].iloc[9] + frame["close"].iloc[10]) / 2
    assert (
        X["roc1"].iloc[10]
        == (frame["close"].iloc[10] - frame["close"].iloc[9]) / frame["close"].iloc[9]
    )


def test_ml_walk_forward_purges_horizon_and_embargo() -> None:
    frame = _frame(220)
    slices = ml_walk_forward_slices(
        frame,
        window_bars=120,
        test_window_bars=21,
        retrain_every_bars=21,
        horizon_bars=5,
        embargo_bars=5,
    )

    assert slices
    for item in slices:
        assert item.train_end_idx <= item.test_start_idx - 5 - 5
        assert item.train_start_idx < item.train_end_idx
        assert item.test_start_idx < item.test_end_idx
        assert item.metadata.train.embargo.purged is True
        assert item.metadata.train.embargo.embargo_bars == 5
