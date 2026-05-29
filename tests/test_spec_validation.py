from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from open_composer.expressions import ExpressionError
from open_composer.models.strategy_spec import load_strategy_spec


def _fixture_spec(repo_root: Path) -> Path:
    return (
        repo_root / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
    )


def test_sample_strategy_valid(repo_root: Path) -> None:
    spec = load_strategy_spec(_fixture_spec(repo_root))
    assert spec.name == "fixture_pullback_15m"
    assert spec.execution.mode == "manual_signal"
    assert spec.data.source == "sample"
    assert spec.notes.model_extra and "research_design" in spec.notes.model_extra


def test_strategy_spec_accepts_expanded_timeframes(tmp_path: Path, repo_root: Path) -> None:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw["timeframe"] = "30m"
    raw["data"]["source"] = "alpaca"
    raw["data"]["path"] = None
    path = tmp_path / "expanded_timeframe.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    spec = load_strategy_spec(path)

    assert spec.timeframe == "30m"


def test_unsupported_expression_rejected(tmp_path: Path, repo_root: Path) -> None:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw["entry"]["all"][0] = "supertrend(close, 10) > 0"
    path = tmp_path / "bad.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ExpressionError):
        load_strategy_spec(path)


def test_invalid_execution_mode_rejected(tmp_path: Path, repo_root: Path) -> None:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw["execution"]["mode"] = "live_auto"
    path = tmp_path / "bad_mode.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")
    with pytest.raises(ValueError):
        load_strategy_spec(path)


def test_draft_router_allows_empty_route_label(tmp_path: Path, repo_root: Path) -> None:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": True,
        "selected_route_label": None,
    }
    path = tmp_path / "draft_router.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    spec = load_strategy_spec(path)

    assert spec.portfolio.selected_route_label is None


def test_active_router_requires_route_label(tmp_path: Path, repo_root: Path) -> None:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw["lifecycle"] = "active"
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": True,
        "selected_route_label": None,
    }
    path = tmp_path / "active_router.yaml"
    path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="requires selected_route_label"):
        load_strategy_spec(path)
