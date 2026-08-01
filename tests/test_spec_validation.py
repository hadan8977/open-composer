from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from open_composer.expressions import ExpressionError
from open_composer.models.strategy_spec import FactorConfig, StrategySpec, load_strategy_spec


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


def _etf_structural_spec(repo_root: Path) -> dict:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw.update(
        {
            "name": "us_etf_structural_momentum_r9",
            "timeframe": "daily",
            "universe": [
                "SPY",
                "QQQ",
                "BIL",
                "GLD",
                "IEF",
                "XLB",
                "XLE",
                "XLF",
                "XLI",
                "XLK",
                "XLP",
                "XLU",
                "XLV",
                "XLY",
            ],
            "portfolio": {
                "mode": "etf_structural_family",
                "gross_exposure_limit": 1.0,
                "position_weight_enforcement": "entry_only",
                "etf_structural": {
                    "candidate_id": "R9D04",
                    "enabled_sleeves": ["core", "diversifiers", "sectors"],
                    "core_budget": 0.4,
                    "diversifier_budget": 0.3,
                    "sector_budget": 0.3,
                    "sector_relative": {
                        "symbols": [
                            "XLB",
                            "XLE",
                            "XLF",
                            "XLI",
                            "XLK",
                            "XLP",
                            "XLU",
                            "XLV",
                            "XLY",
                        ]
                    },
                    "risk_overlay": {},
                },
            },
        }
    )
    return raw


def test_etf_structural_family_is_structured_and_normalized(repo_root: Path) -> None:
    raw = _etf_structural_spec(repo_root)
    raw["portfolio"]["etf_structural"]["core_symbol"] = " spy "

    spec = StrategySpec.model_validate(raw)

    config = spec.portfolio.etf_structural
    assert config is not None
    assert config.core_symbol == "SPY"
    assert config.sector_relative.score_method == "equal_weight_mean_relative_return"
    assert config.risk_overlay is not None
    assert config.risk_overlay.drawdown_scope == "equity_sleeves"


def test_etf_structural_family_rejects_missing_universe_symbol(repo_root: Path) -> None:
    raw = _etf_structural_spec(repo_root)
    raw["universe"].remove("GLD")

    with pytest.raises(ValueError, match="GLD"):
        StrategySpec.model_validate(raw)


def test_etf_structural_family_rejects_inconsistent_sleeve_budget(repo_root: Path) -> None:
    raw = _etf_structural_spec(repo_root)
    raw["portfolio"]["etf_structural"]["sector_budget"] = 0.0

    with pytest.raises(ValueError, match="sector_budget"):
        StrategySpec.model_validate(raw)


def test_static_schema_defines_etf_structural_contract(repo_root: Path) -> None:
    schema = json.loads(
        (repo_root / "schemas" / "strategy_spec.schema.json").read_text(encoding="utf-8")
    )

    portfolio = schema["$defs"]["portfolioConfig"]
    family = schema["$defs"]["etfStructuralFamilyConfig"]
    assert schema["additionalProperties"] is False
    assert "etf_structural_family" in portfolio["properties"]["mode"]["enum"]
    assert (
        "monthly_equal_weight_bil_reserve"
        in portfolio["properties"]["cross_sectional_execution_profile"]["enum"]
    )
    profile_rule = portfolio["allOf"][0]
    assert profile_rule["then"]["properties"]["rebalance_schedule"] == {
        "const": "calendar_month_end"
    }
    assert profile_rule["then"]["properties"]["reserve_symbol"] == {"const": "BIL"}
    assert family["properties"]["sector_relative"]["$ref"].endswith("etfSectorRelativeRule")


def test_static_schema_matches_factor_config_extension_fields(repo_root: Path) -> None:
    schema = json.loads(
        (repo_root / "schemas" / "strategy_spec.schema.json").read_text(encoding="utf-8")
    )

    factor = schema["$defs"]["factorConfig"]
    assert "factor_library" in factor["properties"]["source"]["enum"]
    assert factor["properties"]["factor_id"]["type"] == ["string", "null"]
    params = factor["properties"]["params"]
    assert params["type"] == "object"
    transform = schema["$defs"]["crossSectionalRankTransformParams"]
    assert transform["additionalProperties"] is False
    assert transform["properties"]["transform"]["const"] == (
        "weighted_sum_of_component_cross_sectional_percentile_ranks"
    )


def test_cross_sectional_rank_transform_params_are_typed() -> None:
    params = {
        "transform": "weighted_sum_of_component_cross_sectional_percentile_ranks",
        "rank_method": "percentile_rank_by_decision_session",
        "full_sample_fit": False,
        "components": ["momentum", "volatility"],
        "coefficients": [1.0, -1.0],
        "population": "rankable_symbols_with_finite_history",
        "rank_ascending": True,
        "tie_break": "symbol_ascending",
        "apply_at": "decision_close",
    }

    factor = FactorConfig(source="expression", expression="momentum - volatility", params=params)

    assert factor.params == params
    with pytest.raises(ValueError, match="weighted_sum_of_component"):
        FactorConfig(
            source="expression",
            expression="momentum - volatility",
            params={**params, "transform": "weighted_sum_typo"},
        )
    with pytest.raises(ValueError, match="components and coefficients must align"):
        FactorConfig(
            source="expression",
            expression="momentum - volatility",
            params={**params, "coefficients": [1.0]},
        )
    with pytest.raises(ValueError, match="coefficients must be finite"):
        FactorConfig(
            source="expression",
            expression="momentum - volatility",
            params={**params, "coefficients": [1.0, float("nan")]},
        )
