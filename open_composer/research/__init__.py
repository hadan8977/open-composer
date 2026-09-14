"""Research package facade.

Until 2026-09-14 this module eagerly re-exported every public research entry
point from 42 submodules, so importing *any* ``open_composer.research.*``
module (the research kernel from a cron cycle, one CLI command, one test)
first paid for the whole research tree -- measured at ~5 s and ~200 MB on
this box before any work started, most of it the hybrid-router ->
pdr_ml_gate -> sklearn chain. The same names now resolve lazily (PEP 562):
``from open_composer.research import run_factor_lab`` and
``open_composer.research.run_factor_lab`` both still work and import the
owning submodule on first access only; ``from open_composer.research import
<submodule>`` keeps working through the normal import machinery. To add a
public name, add one ``_EXPORTS`` entry and list it in ``__all__``.
"""

from __future__ import annotations

import importlib
from typing import Any

#: Public name -> owning submodule (imported on first attribute access).
_EXPORTS: dict[str, str] = {
    "run_adaptive_intraday_router_research": "open_composer.research.adaptive_intraday_router",
    "run_adaptive_intraday_router_scan": "open_composer.research.adaptive_intraday_router",
    "run_llm_adaptive_intraday_router_selection": "open_composer.research.adaptive_intraday_router",
    "run_aggressive_theme_router_research": "open_composer.research.aggressive_theme_router",
    "build_alternative_data_quality_report": "open_composer.research.alt_data_quality",
    "build_alternative_data_evidence": "open_composer.research.alternative_data_evidence",
    "backtest_beta_router_params": "open_composer.research.beta_exposure_router",
    "run_beta_exposure_router_research": "open_composer.research.beta_exposure_router",
    "BlindTestReport": "open_composer.research.blind_test",
    "BlindTestResult": "open_composer.research.blind_test",
    "run_blind_test": "open_composer.research.blind_test",
    "build_research_contract": "open_composer.research.contracts",
    "write_research_contract": "open_composer.research.contracts",
    "ResearchControlResult": "open_composer.research.control",
    "load_memory_packet": "open_composer.research.control",
    "update_research_control": "open_composer.research.control",
    "run_core_beta_satellite_router_research": "open_composer.research.core_beta_satellite_router",
    "run_core_satellite_router_research": "open_composer.research.core_satellite_router",
    "CostGridReport": "open_composer.research.cost_sensitivity",
    "CostGridResult": "open_composer.research.cost_sensitivity",
    "run_cost_grid": "open_composer.research.cost_sensitivity",
    "DraftResult": "open_composer.research.drafter",
    "draft_strategy_from_idea": "open_composer.research.drafter",
    "draft_strategy_from_idea_with_status": "open_composer.research.drafter",
    "StrategyEvidenceResult": "open_composer.research.evidence",
    "build_strategy_evidence": "open_composer.research.evidence",
    "run_exposure_switch_research": "open_composer.research.exposure_switch",
    "FactorLabResult": "open_composer.research.factor_lab",
    "run_factor_lab": "open_composer.research.factor_lab",
    "GeometryFeatureReportResult": "open_composer.research.geometry_features",
    "build_geometry_feature_report": "open_composer.research.geometry_features",
    "optimize_strategy_horizons": "open_composer.research.horizon_optimizer",
    "run_hybrid_adaptive_router_research": "open_composer.research.hybrid_adaptive_router",
    "run_hybrid_factor_attribution": "open_composer.research.hybrid_factor_attribution",
    "run_hybrid_news_marginal_lift_research": "open_composer.research.hybrid_news_evidence",
    "build_hybrid_paper_plan": "open_composer.research.hybrid_paper_plan",
    "run_wide_router_research": "open_composer.research.hybrid_wide_router",
    "run_intraday_daily_rotation_research": "open_composer.research.intraday_daily_rotation",
    "run_llm_intraday_daily_rotation_selection": "open_composer.research.intraday_daily_rotation",
    "write_intraday_product_reflection": "open_composer.research.intraday_daily_rotation",
    "run_leverage_research": "open_composer.research.leverage",
    "run_llm_exposure_switch_meta_selection": "open_composer.research.llm_exposure_switch",
    "run_llm_rotation_meta_selection": "open_composer.research.llm_rotation",
    "run_market_timing_research": "open_composer.research.market_timing",
    "optimize_strategy": "open_composer.research.optimizer",
    "optimize_option_overlays": "open_composer.research.options_overlay",
    "build_options_overlay_report": "open_composer.research.options_research",
    "build_options_research_report": "open_composer.research.options_research",
    "parse_sweep_parameters": "open_composer.research.parameter_sweep",
    "run_parameter_sweep": "open_composer.research.parameter_sweep",
    "sweep_parameters_from_spec": "open_composer.research.parameter_sweep",
    "OverfitRiskResult": "open_composer.research.pbo",
    "build_overfit_risk_report": "open_composer.research.pbo",
    "PromotionReport": "open_composer.research.promotion",
    "build_promotion_report": "open_composer.research.promotion",
    "RegimeSearchReport": "open_composer.research.regime_retrieval",
    "search_similar_regimes": "open_composer.research.regime_retrieval",
    "StrategyResearchReportResult": "open_composer.research.research_report",
    "build_strategy_research_report": "open_composer.research.research_report",
    "run_rotation_research": "open_composer.research.rotation",
    "build_short_risk_report": "open_composer.research.short_risk",
    "SkillAttributionReport": "open_composer.research.skill_attribution",
    "SkillAttributionRow": "open_composer.research.skill_attribution",
    "run_skill_attribution": "open_composer.research.skill_attribution",
    "validate_strategy_dag": "open_composer.research.strategy_dag",
    "write_strategy_dag_validation": "open_composer.research.strategy_dag",
    "run_theme_intraday_rotation_router_research": (
        "open_composer.research.theme_intraday_rotation_router"
    ),
    "UniverseAuditResult": "open_composer.research.universe_audit",
    "assess_universe_audit": "open_composer.research.universe_audit",
    "run_universe_audit": "open_composer.research.universe_audit",
    "optimize_strategy_universe": "open_composer.research.universe_optimizer",
}

__all__ = [
    "DraftResult",
    "draft_strategy_from_idea",
    "draft_strategy_from_idea_with_status",
    "StrategyEvidenceResult",
    "BlindTestReport",
    "BlindTestResult",
    "CostGridReport",
    "CostGridResult",
    "ResearchControlResult",
    "RegimeSearchReport",
    "SkillAttributionReport",
    "SkillAttributionRow",
    "run_blind_test",
    "run_beta_exposure_router_research",
    "backtest_beta_router_params",
    "run_core_satellite_router_research",
    "run_core_beta_satellite_router_research",
    "run_adaptive_intraday_router_scan",
    "run_adaptive_intraday_router_research",
    "run_llm_adaptive_intraday_router_selection",
    "run_aggressive_theme_router_research",
    "build_alternative_data_quality_report",
    "build_alternative_data_evidence",
    "build_research_contract",
    "write_research_contract",
    "run_cost_grid",
    "update_research_control",
    "load_memory_packet",
    "search_similar_regimes",
    "run_skill_attribution",
    "build_short_risk_report",
    "run_exposure_switch_research",
    "FactorLabResult",
    "GeometryFeatureReportResult",
    "build_geometry_feature_report",
    "run_factor_lab",
    "run_hybrid_adaptive_router_research",
    "run_hybrid_factor_attribution",
    "run_hybrid_news_marginal_lift_research",
    "run_wide_router_research",
    "build_hybrid_paper_plan",
    "run_intraday_daily_rotation_research",
    "run_llm_intraday_daily_rotation_selection",
    "write_intraday_product_reflection",
    "optimize_option_overlays",
    "build_options_overlay_report",
    "build_options_research_report",
    "parse_sweep_parameters",
    "PromotionReport",
    "OverfitRiskResult",
    "StrategyResearchReportResult",
    "UniverseAuditResult",
    "assess_universe_audit",
    "build_strategy_research_report",
    "build_strategy_evidence",
    "build_promotion_report",
    "build_overfit_risk_report",
    "run_parameter_sweep",
    "sweep_parameters_from_spec",
    "run_universe_audit",
    "run_llm_exposure_switch_meta_selection",
    "run_llm_rotation_meta_selection",
    "run_leverage_research",
    "run_market_timing_research",
    "run_rotation_research",
    "run_theme_intraday_rotation_router_research",
    "optimize_strategy_horizons",
    "optimize_strategy",
    "optimize_strategy_universe",
    "validate_strategy_dag",
    "write_strategy_dag_validation",
]


def __getattr__(name: str) -> Any:
    module_name = _EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = getattr(importlib.import_module(module_name), name)
    globals()[name] = value  # cache so later lookups bypass __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_EXPORTS))
