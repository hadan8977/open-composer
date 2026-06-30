from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.ml_backend.training import run_rolling_training


def _write_syn_ml_spec(sample_workspace: Path, *, model: bool = True) -> Path:
    raw = {
        "name": "syn_daily_ml_probe" if model else "syn_daily_rule_probe",
        "description": "ML probe spec",
        "timeframe": "daily",
        "universe": ["SYN"],
        "lifecycle": "draft",
        "entry": {"all": ["close > sma(close, 20)"], "any": []},
        "exit": {"all": [], "any": ["close < sma(close, 20)"]},
        "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5, "stop_loss_pct": 5.0},
        "execution": {
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": "sample", "symbol": "SYN", "path": "data/sample/syn_daily.csv"},
        "data_assumptions": {"source": "sample", "adjusted": True, "timezone": "UTC"},
        "factors": {
            "momentum_20": {
                "source": "expression",
                "expression": "(close - lag(close, 20)) / lag(close, 20)",
            },
            "sma_ratio_20": {"source": "expression", "expression": "close / sma(close, 20) - 1"},
            "vol_20": {"source": "expression", "expression": "stddev(close, 20)"},
        },
    }
    if model:
        raw["model"] = {
            "kind": "lightgbm_regressor",
            "features": ["momentum_20", "sma_ratio_20", "vol_20"],
            "label": {"type": "forward_return", "horizon_bars": 5},
            "training": {
                "window_bars": 180,
                "retrain_every_bars": 40,
                "test_window_bars": 40,
                "embargo_bars": 5,
                "seed": 11,
            },
            "selection": {"method": "threshold", "threshold": 0.0},
            "hyperparameters": {"n_estimators": 30, "min_child_samples": 10},
        }
    path = sample_workspace / "strategy_specs" / "drafts" / f"{raw['name']}.yaml"
    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    return path


def test_rolling_training_writes_oos_predictions_and_is_deterministic(
    sample_workspace: Path,
) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, sample_workspace)

    first = run_rolling_training(spec, frame, sample_workspace)
    second = run_rolling_training(spec, frame, sample_workspace)

    assert len(first.folds) > 1
    assert first.full_predictions.notna().sum() > 20
    pd.testing.assert_series_equal(first.full_predictions, second.full_predictions)
    for fold in first.folds:
        assert fold.train_end_idx <= fold.test_start_idx - 10


def test_backtest_frame_uses_ml_branch(sample_workspace: Path) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, sample_workspace)

    result = backtest_frame(spec, frame, root=sample_workspace, run_id_value="ml-probe")

    assert result.run.signals >= 1
    assert any("ML signals use stitched out-of-sample" in item for item in result.run.assumptions)


def test_model_none_rule_path_matches_plain_rule_backtest(sample_workspace: Path) -> None:
    spec_path = _write_syn_ml_spec(sample_workspace, model=False)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, sample_workspace)
    with_explicit_none_path = (
        sample_workspace / "strategy_specs" / "drafts" / "syn_daily_rule_none.yaml"
    )
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["name"] = "syn_daily_rule_none"
    raw["model"] = None
    with_explicit_none_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    explicit_none = load_strategy_spec(with_explicit_none_path)

    first = backtest_frame(spec, frame, root=sample_workspace, run_id_value="rule-a")
    second = backtest_frame(explicit_none, frame, root=sample_workspace, run_id_value="rule-b")

    assert first.run.signals == second.run.signals
    assert first.run.trades == second.run.trades
    assert first.run.total_return_pct == second.run.total_return_pct
