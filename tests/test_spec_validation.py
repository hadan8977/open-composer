from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from open_composer.expressions import ExpressionError
from open_composer.models.strategy_spec import (
    FactorConfig,
    PortfolioConfig,
    StrategySpec,
    load_strategy_spec,
)


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
    dynamic_profile_rule = portfolio["allOf"][1]
    assert dynamic_profile_rule["then"]["properties"]["rebalance_schedule"] == {
        "const": "monday_wednesday_friday"
    }
    assert dynamic_profile_rule["then"]["properties"]["weighting"] == {
        "const": "risk_budgeted_score"
    }
    assert family["properties"]["sector_relative"]["$ref"].endswith("etfSectorRelativeRule")


def test_dynamic_theme_profile_rejects_schedule_drift() -> None:
    with pytest.raises(ValueError, match="dynamic_theme_mwf_bil_reserve"):
        PortfolioConfig(
            mode="cross_sectional_momentum",
            selected_route_label="r8:D01",
            cross_sectional_execution_profile="dynamic_theme_mwf_bil_reserve",
            position_weight_enforcement="entry_only",
            rebalance_schedule="every_bar",
            weighting="risk_budgeted_score",
            reserve_symbol="BIL",
            reserve_exempt_from_max_symbol_weight=True,
        )


def _model_ranking_portfolio_kwargs() -> dict:
    return {
        "mode": "model_ranking_portfolio",
        "candidate_artifact_dir": "reports/research/candidates/step11_momentum_placeholder",
        "universe_rule": "pit_adv_top_n",
        "universe_top_n": 1500,
        "feature_set_id": "daily_only",
        "label_horizon_days": 21,
        "top_k": 50,
        "rebalance": "weekly_friday_close_monday_open",
        "weighting": "equal_weight",
        "hedge": "none",
    }


def test_model_ranking_portfolio_accepts_complete_config() -> None:
    config = PortfolioConfig(**_model_ranking_portfolio_kwargs())

    assert config.mode == "model_ranking_portfolio"
    assert config.top_k == 50
    assert config.hedge == "none"
    assert config.account_equity_for_sizing is None


def test_model_ranking_portfolio_requires_all_fields_together() -> None:
    with pytest.raises(ValueError, match="model_ranking_portfolio requires portfolio fields"):
        PortfolioConfig(mode="model_ranking_portfolio")


def test_model_ranking_portfolio_requires_equal_weight() -> None:
    kwargs = _model_ranking_portfolio_kwargs()
    kwargs["weighting"] = "engine_default"
    with pytest.raises(ValueError, match="weighting=equal_weight"):
        PortfolioConfig(**kwargs)


def test_model_ranking_portfolio_rejects_blank_artifact_dir() -> None:
    kwargs = _model_ranking_portfolio_kwargs()
    kwargs["candidate_artifact_dir"] = "   "
    with pytest.raises(ValueError, match="non-blank candidate_artifact_dir"):
        PortfolioConfig(**kwargs)


@pytest.mark.parametrize(
    "field_name,value",
    [
        ("candidate_artifact_dir", "reports/research/candidates/x"),
        ("universe_rule", "pit_adv_top_n"),
        ("universe_top_n", 1500),
        ("feature_set_id", "daily_only"),
        ("label_horizon_days", 21),
        ("top_k", 50),
        ("rebalance", "weekly_friday_close_monday_open"),
        ("hedge", "none"),
        ("account_equity_for_sizing", 100000.0),
    ],
)
def test_model_ranking_portfolio_fields_require_matching_mode(
    field_name: str, value: object
) -> None:
    with pytest.raises(ValueError, match="require mode=model_ranking_portfolio"):
        PortfolioConfig(mode="single_symbol", **{field_name: value})


def _model_ranking_portfolio_spec(repo_root: Path) -> dict:
    raw = yaml.safe_load(_fixture_spec(repo_root).read_text(encoding="utf-8"))
    raw.update(
        {
            "name": "us_model_ranking_portfolio_step11_wavec",
            "timeframe": "daily",
            "universe": ["SPY"],
            "portfolio": _model_ranking_portfolio_kwargs(),
        }
    )
    return raw


def test_model_ranking_portfolio_spec_loads_end_to_end(repo_root: Path) -> None:
    raw = _model_ranking_portfolio_spec(repo_root)

    spec = StrategySpec.model_validate(raw)

    assert spec.portfolio.mode == "model_ranking_portfolio"
    assert spec.portfolio.feature_set_id == "daily_only"
    assert spec.portfolio.label_horizon_days == 21
    assert spec.portfolio.top_k == 50


def test_model_ranking_portfolio_rejects_non_pit_universe_rule_value() -> None:
    kwargs = _model_ranking_portfolio_kwargs()
    kwargs["universe_rule"] = "current_index_membership"
    with pytest.raises(ValueError):
        PortfolioConfig(**kwargs)


def test_static_schema_defines_model_ranking_portfolio_contract(repo_root: Path) -> None:
    schema = json.loads(
        (repo_root / "schemas" / "strategy_spec.schema.json").read_text(encoding="utf-8")
    )

    portfolio = schema["$defs"]["portfolioConfig"]
    assert "model_ranking_portfolio" in portfolio["properties"]["mode"]["enum"]
    assert portfolio["properties"]["top_k"] == {"type": ["integer", "null"], "minimum": 1}
    assert portfolio["properties"]["hedge"]["enum"] == ["none", "spy_beta_hedge", None]


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
