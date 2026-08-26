from __future__ import annotations

import copy
from pathlib import Path

import pytest
import yaml

from open_composer.models.strategy_spec import load_strategy_spec


def _model_spec(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    raw["name"] = "fixture_pullback_ml_15m"
    raw["factors"] = {
        "rsi_14": {"source": "expression", "expression": "rsi_simple(close, 14)"},
        "sma_fast": {"source": "expression", "expression": "sma(close, 5)"},
    }
    raw["model"] = {
        "kind": "lightgbm_regressor",
        "features": ["rsi_14", "sma_fast"],
        "label": {"type": "forward_return", "horizon_bars": 5},
        "training": {
            "window_bars": 120,
            "retrain_every_bars": 21,
            "test_window_bars": 21,
            "embargo_bars": 5,
            "seed": 7,
        },
        "selection": {"method": "threshold"},
    }
    return raw


def test_strategy_spec_accepts_optional_ml_model(sample_workspace: Path) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = _model_spec(source)
    target = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_ml_15m.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    spec = load_strategy_spec(target)

    assert spec.model is not None
    assert spec.model.selection.threshold == 0.0
    assert spec.model.features == ["rsi_14", "sma_fast"]


@pytest.mark.parametrize(
    "kind",
    [
        "lightgbm_regressor",
        "lightgbm_classifier",
        "ridge_regressor",
        "logistic_regression_classifier",
    ],
)
def test_strategy_spec_accepts_registered_model_kinds(
    sample_workspace: Path,
    kind: str,
) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = _model_spec(source)
    raw["name"] = f"fixture_{kind}"
    raw["model"]["kind"] = kind
    target = sample_workspace / "strategy_specs" / "drafts" / f"fixture_{kind}.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    spec = load_strategy_spec(target)

    assert spec.model is not None
    assert spec.model.kind == kind


def test_strategy_spec_accepts_path_survival_ml_label(sample_workspace: Path) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = _model_spec(source)
    raw["model"]["label"] = {
        "type": "path_survival",
        "horizon_bars": 10,
        "max_drawdown_pct": 8.0,
        "min_terminal_return_pct": 0.0,
    }
    target = sample_workspace / "strategy_specs" / "drafts" / "path_survival_ml_label.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    spec = load_strategy_spec(target)

    assert spec.model is not None
    assert spec.model.label.type == "path_survival"
    assert spec.model.label.max_drawdown_pct == 8.0


def test_strategy_spec_rejects_unknown_model_feature(sample_workspace: Path) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = _model_spec(source)
    raw["model"]["features"] = ["missing_factor"]
    target = sample_workspace / "strategy_specs" / "drafts" / "bad_ml_feature.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="model.features must reference"):
        load_strategy_spec(target)


def test_strategy_spec_rejects_top_quantile_without_quantile(sample_workspace: Path) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = _model_spec(source)
    raw["model"]["selection"] = {"method": "top_quantile"}
    target = sample_workspace / "strategy_specs" / "drafts" / "bad_ml_selection.yaml"
    target.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    with pytest.raises(ValueError, match="top_quantile requires"):
        load_strategy_spec(target)


def test_strategy_spec_model_none_preserves_existing_spec(sample_workspace: Path) -> None:
    source = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    with_model_none = copy.deepcopy(raw)
    with_model_none["model"] = None
    target = sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_model_none.yaml"
    target.write_text(yaml.safe_dump(with_model_none, sort_keys=False), encoding="utf-8")

    assert load_strategy_spec(source).model is None
    assert load_strategy_spec(target).model is None
