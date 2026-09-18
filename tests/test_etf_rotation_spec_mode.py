"""``portfolio.mode=etf_rotation_portfolio`` spec registration.

Mirrors ``tests/test_insider_portfolio_target_weights.py``'s fixture pattern
(base fixture spec + dict overrides, validated with
``StrategySpec.model_validate``) but stays scoped to what this file owns:
the pydantic schema (``ETFRotationConfig`` plus the ``PortfolioConfig`` /
``StrategySpec`` cross-field validators), the strategy content hash, and
``paper_rehearsal.validate_rehearsal_spec`` acceptance -- not the (separately
owned) target-weight mapping adapter itself.
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml

from open_composer import paper_rehearsal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.strategy_versions import strategy_content_hash

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_SPEC = (
    REPO_ROOT / "tests" / "fixtures" / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml"
)

DEFAULT_ETF_ROTATION: dict[str, object] = {
    "menu": ["SPY", "QQQ", "IWM"],
    "cash_symbol": "BIL",
    "lookbacks": [21, 63],
    "top_n": 2,
    "rebalance": "monthly_last_session",
    "absolute_momentum_filter": True,
    "min_history_sessions": 260,
}


def _base_raw() -> dict[str, Any]:
    raw = yaml.safe_load(FIXTURE_SPEC.read_text(encoding="utf-8"))
    raw["name"] = "test_etf_rotation_portfolio"
    raw["timeframe"] = "daily"
    raw["universe"] = ["SPY", "QQQ", "IWM", "BIL"]
    return raw


def _spec_dict(
    *,
    etf_rotation: dict[str, object] | None = None,
    portfolio_overrides: dict[str, object] | None = None,
    timeframe: str | None = "daily",
    position_direction: str | None = None,
    include_etf_rotation: bool = True,
) -> dict[str, Any]:
    raw = _base_raw()
    if timeframe is not None:
        raw["timeframe"] = timeframe
    if position_direction is not None:
        raw["position_direction"] = position_direction
    portfolio: dict[str, object] = {
        "mode": "etf_rotation_portfolio",
        "weighting": "equal_weight",
    }
    if include_etf_rotation:
        params = copy.deepcopy(DEFAULT_ETF_ROTATION)
        params.update(etf_rotation or {})
        portfolio["etf_rotation"] = params
    if portfolio_overrides:
        portfolio.update(portfolio_overrides)
    raw["portfolio"] = portfolio
    return raw


def _valid_spec(**kwargs: Any) -> StrategySpec:
    return StrategySpec.model_validate(_spec_dict(**kwargs))


def test_valid_spec_loads() -> None:
    spec = _valid_spec()
    assert spec.portfolio.mode == "etf_rotation_portfolio"
    assert spec.portfolio.etf_rotation is not None
    assert spec.portfolio.etf_rotation.menu == ["SPY", "QQQ", "IWM"]
    assert spec.portfolio.etf_rotation.cash_symbol == "BIL"
    assert spec.portfolio.etf_rotation.top_n == 2
    assert spec.portfolio.etf_rotation.notional_budget_usd is None


def test_mode_without_block_is_rejected() -> None:
    with pytest.raises(ValueError, match="etf_rotation_portfolio requires portfolio.etf_rotation"):
        _valid_spec(include_etf_rotation=False)


def test_block_without_mode_is_rejected() -> None:
    raw = _spec_dict()
    raw["portfolio"]["mode"] = "single_symbol"
    with pytest.raises(
        ValueError, match="portfolio.etf_rotation requires mode=etf_rotation_portfolio"
    ):
        StrategySpec.model_validate(raw)


def test_non_equal_weight_is_rejected() -> None:
    with pytest.raises(
        ValueError, match="etf_rotation_portfolio requires portfolio.weighting=equal_weight"
    ):
        _valid_spec(portfolio_overrides={"weighting": "engine_default"})


def test_cash_symbol_inside_menu_is_rejected() -> None:
    with pytest.raises(ValueError, match="cash_symbol must not appear in menu"):
        _valid_spec(etf_rotation={"cash_symbol": "SPY"})


def test_top_n_exceeds_menu_length_is_rejected() -> None:
    with pytest.raises(ValueError, match="top_n must be <= len\\(menu\\)"):
        _valid_spec(etf_rotation={"top_n": 4})


def test_duplicate_menu_symbol_is_rejected() -> None:
    with pytest.raises(ValueError, match="menu must be unique"):
        _valid_spec(etf_rotation={"menu": ["SPY", "SPY", "IWM"]})


def test_lookback_out_of_range_is_rejected() -> None:
    with pytest.raises(ValueError, match="lookbacks entries must be in 2..504"):
        _valid_spec(etf_rotation={"lookbacks": [1, 63]})
    with pytest.raises(ValueError, match="lookbacks entries must be in 2..504"):
        _valid_spec(etf_rotation={"lookbacks": [21, 505]})


def test_non_daily_timeframe_is_rejected() -> None:
    with pytest.raises(ValueError, match="etf_rotation_portfolio requires timeframe=daily"):
        _valid_spec(timeframe="15m")


def test_short_only_direction_is_rejected() -> None:
    with pytest.raises(
        ValueError, match="etf_rotation_portfolio requires position_direction=long_only"
    ):
        _valid_spec(position_direction="short_only")


def test_notional_budget_usd_accepts_positive_value() -> None:
    spec = _valid_spec(etf_rotation={"notional_budget_usd": 50_000.0})
    assert spec.portfolio.etf_rotation is not None
    assert spec.portfolio.etf_rotation.notional_budget_usd == 50_000.0


def test_notional_budget_usd_rejects_zero() -> None:
    with pytest.raises(ValueError):
        _valid_spec(etf_rotation={"notional_budget_usd": 0.0})


def test_notional_budget_usd_rejects_negative() -> None:
    with pytest.raises(ValueError):
        _valid_spec(etf_rotation={"notional_budget_usd": -1.0})


def test_notional_budget_usd_omitted_still_validates() -> None:
    spec = _valid_spec()
    assert spec.portfolio.etf_rotation is not None
    assert spec.portfolio.etf_rotation.notional_budget_usd is None


def test_content_hash_changes_when_block_changes() -> None:
    baseline = _valid_spec()
    changed = _valid_spec(etf_rotation={"top_n": 1})
    assert strategy_content_hash(baseline) != strategy_content_hash(changed)


def test_content_hash_stable_for_identical_specs() -> None:
    first = _valid_spec()
    second = _valid_spec()
    assert strategy_content_hash(first) == strategy_content_hash(second)


def _rehearsal_ready_spec_dict() -> dict[str, Any]:
    raw = _spec_dict()
    raw["execution_policy"] = {
        "policy_id": "test-etf-rotation-day-market",
        "order_style": "day_market",
        "time_in_force": "day",
        "naked_market_justification": "test fixture only; not real execution",
    }
    return raw


def test_rehearsal_validates_well_formed_spec(tmp_path: Path) -> None:
    spec = StrategySpec.model_validate(_rehearsal_ready_spec_dict())
    payload = paper_rehearsal.validate_rehearsal_spec(spec, tmp_path)
    assert payload["policy_id"] == "test-etf-rotation-day-market"
