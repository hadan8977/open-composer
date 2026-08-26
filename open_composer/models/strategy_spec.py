from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.timeframes import StrategyTimeframe
from open_composer.yaml_utils import safe_load_yaml


class RuleBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    all: list[str] = Field(default_factory=list)
    any: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_rules(self) -> RuleBlock:
        if not self.all and not self.any:
            msg = "rule block must define at least one rule in 'all' or 'any'"
            raise ValueError(msg)
        return self


class RiskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_trades_per_day: int = Field(default=3, ge=1)
    max_position_weight: float = Field(default=0.2, gt=0, le=1)
    stop_loss_pct: float | None = Field(default=None, gt=0)
    take_profit_pct: float | None = Field(default=None, gt=0)


class ETFTrendRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fast_sma_sessions: int = Field(default=126, ge=2)
    slow_sma_sessions: int = Field(default=252, ge=2)
    momentum_sessions: int = Field(default=252, ge=2)
    required_positive_votes: int = Field(default=2, ge=1, le=3)


class ETFSectorRelativeRule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] = Field(min_length=1)
    fast_momentum_sessions: int = Field(default=126, ge=2)
    slow_momentum_sessions: int = Field(default=252, ge=2)
    trend_sma_sessions: int = Field(default=210, ge=2)
    benchmark_symbol: str = "SPY"
    score_method: Literal["equal_weight_mean_relative_return"] = "equal_weight_mean_relative_return"
    weighting: Literal["equal_weight"] = "equal_weight"
    top_n: int = Field(default=2, ge=1)
    hold_rank: int = Field(default=4, ge=1)
    hold_buffer_policy: Literal["retain_through_hold_rank_then_fill_top_n"] = (
        "retain_through_hold_rank_then_fill_top_n"
    )
    tie_break: Literal["symbol_ascending"] = "symbol_ascending"

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        normalized = [symbol.upper().strip() for symbol in value]
        if any(not symbol for symbol in normalized):
            raise ValueError("sector_relative.symbols cannot contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("sector_relative.symbols must be unique")
        return normalized

    @field_validator("benchmark_symbol")
    @classmethod
    def normalize_benchmark_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if not normalized:
            raise ValueError("sector_relative.benchmark_symbol cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_hold_rank(self) -> ETFSectorRelativeRule:
        if self.hold_rank < self.top_n:
            raise ValueError("sector_relative.hold_rank must be >= top_n")
        return self


class ETFStructuralRiskOverlay(BaseModel):
    model_config = ConfigDict(extra="forbid")

    volatility_lookback_sessions: int = Field(default=63, ge=2)
    volatility_reference_symbol: str = "SPY"
    volatility_measure: Literal["annualized_close_to_close"] = "annualized_close_to_close"
    annualization_sessions: int = Field(default=252, ge=2)
    medium_volatility_threshold: float = Field(default=0.18, gt=0)
    high_volatility_threshold: float = Field(default=0.25, gt=0)
    medium_exposure_scale: float = Field(default=0.75, gt=0, le=1)
    high_exposure_scale: float = Field(default=0.5, gt=0, le=1)
    volatility_scope: Literal["all_non_reserve_sleeves"] = "all_non_reserve_sleeves"
    drawdown_lookback_sessions: int = Field(default=63, ge=2)
    drawdown_reference_symbol: str = "SPY"
    drawdown_trigger: float = Field(default=-0.10, ge=-1, lt=0)
    drawdown_exposure_scale: float = Field(default=0.5, gt=0, le=1)
    drawdown_scope: Literal["equity_sleeves"] = "equity_sleeves"
    recovery_sma_sessions: int = Field(default=126, ge=2)
    recovery_rule: Literal["reference_close_above_sma"] = "reference_close_above_sma"

    @field_validator("volatility_reference_symbol", "drawdown_reference_symbol")
    @classmethod
    def normalize_reference_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if not normalized:
            raise ValueError("risk overlay reference symbols cannot be blank")
        return normalized

    @model_validator(mode="after")
    def validate_threshold_order(self) -> ETFStructuralRiskOverlay:
        if self.high_volatility_threshold <= self.medium_volatility_threshold:
            raise ValueError("high volatility threshold must exceed medium threshold")
        if self.high_exposure_scale > self.medium_exposure_scale:
            raise ValueError("high-volatility scale cannot exceed medium-volatility scale")
        return self


class ETFStructuralFamilyConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    rebalance_frequency: Literal["calendar_month_end"] = "calendar_month_end"
    decision_anchor: Literal["last_session_close"] = "last_session_close"
    execution_anchor: Literal["next_session_open"] = "next_session_open"
    core_symbol: str = "SPY"
    reserve_symbol: str = "BIL"
    diversifier_symbols: list[str] = Field(default_factory=lambda: ["GLD", "IEF"])
    diversifier_weighting: Literal["equal_weight"] = "equal_weight"
    enabled_sleeves: list[Literal["core", "diversifiers", "sectors"]] = Field(min_length=1)
    core_budget: float = Field(default=0.4, ge=0, le=1)
    diversifier_budget: float = Field(default=0.0, ge=0, le=1)
    sector_budget: float = Field(default=0.0, ge=0, le=1)
    core_trend: ETFTrendRule = Field(default_factory=ETFTrendRule)
    diversifier_trend: ETFTrendRule = Field(default_factory=ETFTrendRule)
    sector_relative: ETFSectorRelativeRule
    risk_overlay: ETFStructuralRiskOverlay | None = None
    reserve_receives_unallocated: bool = True
    natural_weight_drift_between_rebalances: bool = True

    @field_validator("core_symbol", "reserve_symbol")
    @classmethod
    def normalize_single_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if not normalized:
            raise ValueError("ETF structural symbols cannot be blank")
        return normalized

    @field_validator("diversifier_symbols")
    @classmethod
    def normalize_diversifier_symbols(cls, value: list[str]) -> list[str]:
        normalized = [symbol.upper().strip() for symbol in value]
        if any(not symbol for symbol in normalized):
            raise ValueError("diversifier_symbols cannot contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("diversifier_symbols must be unique")
        return normalized

    @model_validator(mode="after")
    def validate_sleeves_and_budgets(self) -> ETFStructuralFamilyConfig:
        budget = self.core_budget + self.diversifier_budget + self.sector_budget
        if budget > 1 + 1e-12:
            raise ValueError("ETF structural sleeve budgets cannot exceed 1.0")
        expected_positive = {
            "core": ("core_budget", self.core_budget),
            "diversifiers": ("diversifier_budget", self.diversifier_budget),
            "sectors": ("sector_budget", self.sector_budget),
        }
        for sleeve, (field_name, sleeve_budget) in expected_positive.items():
            if (sleeve in self.enabled_sleeves) != (sleeve_budget > 0):
                raise ValueError(f"enabled_sleeves and {field_name} are inconsistent")
        if "diversifiers" in self.enabled_sleeves and not self.diversifier_symbols:
            raise ValueError("diversifier sleeve requires diversifier_symbols")
        if self.core_symbol == self.reserve_symbol:
            raise ValueError("core_symbol and reserve_symbol must differ")
        return self


class PortfolioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[
        "single_symbol",
        "adaptive_intraday_internal_router",
        "hybrid_adaptive_router",
        "beta_exposure_router",
        "core_beta_satellite_router",
        "momentum_signal_router",
        "cross_sectional_momentum",
        "etf_structural_family",
    ] = "single_symbol"
    max_symbols_per_day: int | None = Field(default=None, ge=1)
    gross_exposure_limit: float | None = Field(default=None, gt=0, le=1)
    max_symbol_weight: float | None = Field(default=None, gt=0, le=1)
    same_day_flatten: bool = False
    duplicate_signal_policy: Literal["stable_signal_id", "allow_duplicates"] = "stable_signal_id"
    selected_route_label: str | None = None
    cross_sectional_execution_profile: Literal[
        "generic",
        "monthly_equal_weight_bil_reserve",
        "dynamic_theme_mwf_bil_reserve",
    ] = "generic"
    position_weight_enforcement: Literal["entry_only", "continuous"] = "entry_only"
    rebalance_schedule: Literal[
        "every_bar",
        "calendar_month_end",
        "monday_wednesday_friday",
    ] = "every_bar"
    weighting: Literal["engine_default", "equal_weight", "risk_budgeted_score"] = "engine_default"
    reserve_symbol: str | None = None
    reserve_exempt_from_max_symbol_weight: bool = False
    etf_structural: ETFStructuralFamilyConfig | None = None

    @model_validator(mode="after")
    def require_router_route(self) -> PortfolioConfig:
        if (
            self.mode
            in {
                "adaptive_intraday_internal_router",
                "hybrid_adaptive_router",
                "beta_exposure_router",
                "core_beta_satellite_router",
                "momentum_signal_router",
                "cross_sectional_momentum",
            }
            and not self.selected_route_label
        ):
            msg = f"{self.mode} portfolio mode requires selected_route_label"
            raise ValueError(msg)
        if self.mode == "etf_structural_family" and self.etf_structural is None:
            raise ValueError("etf_structural_family mode requires portfolio.etf_structural")
        if self.mode != "etf_structural_family" and self.etf_structural is not None:
            raise ValueError("portfolio.etf_structural requires mode=etf_structural_family")
        if self.cross_sectional_execution_profile == "monthly_equal_weight_bil_reserve":
            required_fields = {
                "mode",
                "position_weight_enforcement",
                "rebalance_schedule",
                "weighting",
                "reserve_symbol",
                "reserve_exempt_from_max_symbol_weight",
            }
            missing_fields = sorted(required_fields - self.model_fields_set)
            expected = {
                "mode": self.mode == "cross_sectional_momentum",
                "position_weight_enforcement": self.position_weight_enforcement == "entry_only",
                "rebalance_schedule": self.rebalance_schedule == "calendar_month_end",
                "weighting": self.weighting == "equal_weight",
                "reserve_symbol": self.reserve_symbol == "BIL",
                "reserve_exempt_from_max_symbol_weight": (
                    self.reserve_exempt_from_max_symbol_weight is True
                ),
            }
            failed = [
                *[f"missing:{name}" for name in missing_fields],
                *sorted(name for name, passed in expected.items() if not passed),
            ]
            if failed:
                raise ValueError(
                    "monthly_equal_weight_bil_reserve execution profile mismatch: "
                    + ", ".join(failed)
                )
        elif self.cross_sectional_execution_profile == "dynamic_theme_mwf_bil_reserve":
            required_fields = {
                "mode",
                "position_weight_enforcement",
                "rebalance_schedule",
                "weighting",
                "reserve_symbol",
                "reserve_exempt_from_max_symbol_weight",
            }
            missing_fields = sorted(required_fields - self.model_fields_set)
            expected = {
                "mode": self.mode == "cross_sectional_momentum",
                "position_weight_enforcement": self.position_weight_enforcement == "entry_only",
                "rebalance_schedule": self.rebalance_schedule == "monday_wednesday_friday",
                "weighting": self.weighting == "risk_budgeted_score",
                "reserve_symbol": self.reserve_symbol == "BIL",
                "reserve_exempt_from_max_symbol_weight": (
                    self.reserve_exempt_from_max_symbol_weight is True
                ),
            }
            failed = [
                *[f"missing:{name}" for name in missing_fields],
                *sorted(name for name, passed in expected.items() if not passed),
            ]
            if failed:
                raise ValueError(
                    "dynamic_theme_mwf_bil_reserve execution profile mismatch: " + ", ".join(failed)
                )
        elif (
            self.mode != "cross_sectional_momentum"
            and self.cross_sectional_execution_profile != "generic"
        ):
            raise ValueError("cross-sectional execution profiles require cross_sectional_momentum")
        return self


class CostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    commission_pct: float = Field(default=0.0, ge=0)
    slippage_bps: float = Field(default=0.0, ge=0)
    impact_model: Literal["linear", "sqrt", "almgren_chriss"] = "linear"
    impact_eta: float = Field(default=0.0, ge=0)
    impact_gamma: float = Field(default=0.0, ge=0)


class ExecutionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    backend: Literal["python_reference", "nautilus_trader"] = "python_reference"
    mode: Literal["manual_signal", "paper_auto"] = "manual_signal"
    signal_on: Literal["bar_close"] = "bar_close"
    fill_assumption: Literal["next_bar_open"] = "next_bar_open"
    broker: Literal["none", "alpaca_paper"] = "none"

    @model_validator(mode="after")
    def broker_matches_mode(self) -> ExecutionConfig:
        if self.mode == "paper_auto" and self.broker != "alpaca_paper":
            msg = "paper_auto execution requires broker=alpaca_paper"
            raise ValueError(msg)
        if self.mode == "manual_signal" and self.broker == "alpaca_paper":
            msg = "manual_signal execution must use broker=none"
            raise ValueError(msg)
        return self


class DataConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["sample", "alpaca", "longbridge"] = "sample"
    symbol: str | None = None
    path: str | None = None
    feed: str | None = None


class DataAssumptions(BaseModel):
    model_config = ConfigDict(extra="allow")

    source: str = "sample"
    adjusted: bool = True
    timezone: str = "America/New_York"
    acquisition_tier: (
        Literal[
            "sample_smoke",
            "fixture_replay",
            "cached_live",
            "research_replay_cache",
            "research_strict",
            "research_cross_check",
            "cross_source_verified",
            "paper_ready_live",
        ]
        | None
    ) = None


class LLMReviewConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    model: str | None = None


class LLMFactorOutputSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["object"] = "object"
    required: list[str] = Field(default_factory=list)
    properties: dict[str, dict[str, Any]] = Field(default_factory=dict)


class LLMFactorCachePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["materialize_then_replay"] = "materialize_then_replay"
    key_fields: list[str] = Field(
        default_factory=lambda: [
            "symbol",
            "visible_at",
            "input_view_version",
            "input_hash",
            "prompt_hash",
            "model",
            "schema_version",
        ]
    )


class CrossSectionalRankTransformParams(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transform: Literal["weighted_sum_of_component_cross_sectional_percentile_ranks"]
    rank_method: Literal["percentile_rank_by_decision_session"]
    full_sample_fit: Literal[False]
    components: list[str] = Field(min_length=1)
    coefficients: list[float] = Field(min_length=1)
    population: Literal["rankable_symbols_with_finite_history"]
    rank_ascending: Literal[True]
    tie_break: Literal["symbol_ascending"]
    apply_at: Literal["decision_close"]
    placebo_operation: Literal["per_decision_session_symbol_permutation"] | None = None
    placebo_seed: int | None = None
    placebo_mapping: Literal["same_permutation_for_all_formula_columns"] | None = None

    @field_validator("components")
    @classmethod
    def validate_components(cls, value: list[str]) -> list[str]:
        normalized = [component.strip() for component in value]
        if any(not component for component in normalized):
            raise ValueError("cross-sectional transform components cannot be blank")
        if len(normalized) != len(set(normalized)):
            raise ValueError("cross-sectional transform components must be unique")
        return normalized

    @field_validator("coefficients")
    @classmethod
    def validate_coefficients(cls, value: list[float]) -> list[float]:
        if any(not math.isfinite(float(coefficient)) for coefficient in value):
            raise ValueError("cross-sectional transform coefficients must be finite")
        return value

    @model_validator(mode="after")
    def validate_lengths_and_placebo(self) -> CrossSectionalRankTransformParams:
        if len(self.components) != len(self.coefficients):
            raise ValueError("cross-sectional transform components and coefficients must align")
        placebo_values = (
            self.placebo_operation,
            self.placebo_seed,
            self.placebo_mapping,
        )
        if any(value is not None for value in placebo_values) and not all(
            value is not None for value in placebo_values
        ):
            raise ValueError("placebo transform metadata must be complete or absent")
        return self


class FactorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["expression", "llm_feature", "feature_packet", "factor_library"] = "expression"
    expression: str | None = None
    path: str | None = None
    field: str | None = None
    default: float | bool = 0.0
    description: str = ""
    factor_id: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)
    input_view: str | None = None
    input_view_version: int | None = Field(default=None, ge=1)
    prompt_template_path: str | None = None
    output_schema: LLMFactorOutputSchema | None = None
    cache_policy: LLMFactorCachePolicy | None = None
    model_ref: str | None = None

    @model_validator(mode="after")
    def require_factor_source_fields(self) -> FactorConfig:
        if "transform" in self.params:
            self.params = CrossSectionalRankTransformParams.model_validate(self.params).model_dump(
                mode="json",
                exclude_none=True,
            )
        if self.source == "expression" and not self.expression:
            msg = "expression factors require expression"
            raise ValueError(msg)
        if self.source == "feature_packet" and not self.field:
            msg = "feature_packet factors require field"
            raise ValueError(msg)
        if self.source == "llm_feature":
            missing = [
                name
                for name, value in {
                    "field": self.field,
                    "input_view": self.input_view,
                    "input_view_version": self.input_view_version,
                    "prompt_template_path": self.prompt_template_path,
                    "output_schema": self.output_schema,
                }.items()
                if value is None or value == ""
            ]
            if missing and not self.path:
                msg = (
                    "llm_feature factors require either a replay packet path or materialization "
                    f"fields: {', '.join(missing)}"
                )
                raise ValueError(msg)
            if not self.path and self.cache_policy is None:
                self.cache_policy = LLMFactorCachePolicy()
        if self.source == "factor_library":
            if not self.factor_id:
                msg = "factor_library factors require factor_id"
                raise ValueError(msg)
            from open_composer.research.factor_library import get_factor, materialize_expression

            try:
                factor = get_factor(self.factor_id)
            except KeyError as exc:
                msg = f"factor_id {self.factor_id!r} not in factor_library catalog"
                raise ValueError(msg) from exc
            if not factor.expression:
                msg = (
                    f"factor {self.factor_id} has no expression template; "
                    "cannot use as source=factor_library"
                )
                raise ValueError(msg)
            rendered = materialize_expression(factor, self.params)
            object.__setattr__(self, "expression", rendered)
            if not self.description:
                object.__setattr__(self, "description", factor.description)
        return self


class NotesConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    intent: str = ""
    open_questions: list[str] = Field(default_factory=list)


class ResearchDesign(BaseModel):
    model_config = ConfigDict(extra="allow")

    iter_id: str | None = Field(default=None, pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    workflow_only_ungated_draft: bool = False
    campaign_contract_path: str | None = None
    candidate_manifest_path: str | None = None
    candidate_policy_contract_path: str | None = None
    data_feasibility_path: str | None = None
    universe_contract_path: str | None = None
    data_contract_path: str | None = None
    holdout_contract_path: str | None = None
    cost_contract_path: str | None = None
    cumulative_trial_contract_path: str | None = None
    source_cards_path: str | None = None
    source_card_claim_ids: list[str] = Field(default_factory=list)
    preregistration_lock_path: str | None = None
    parameter_space: dict[str, list[float | int | str | bool | None]] = Field(default_factory=dict)
    candidate_budget: int | None = Field(default=None, ge=1)
    selection_objective: str = ""
    anti_overfit_notes: list[str] = Field(default_factory=list)
    validation_plan: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Optional execution-policy and reality-model extensions (skill-first harness)
# These fields are opt-in; specs without them continue to validate. Strategies
# whose risk domains require execution_policy / execution_reality_report
# artifacts may either populate these fields and generate the artifact via
# `oc strategy execution-policy`, or hand-write the JSON artifact directly.
# ---------------------------------------------------------------------------


class PriceProtection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit_offset_bps: float | None = Field(default=None, ge=0)
    max_open_gap_pct: float | None = Field(default=None, ge=0)
    max_spread_bps: float | None = Field(default=None, ge=0)


class ParticipationCap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_adv_pct: float | None = Field(default=None, ge=0, le=100)
    max_open_bar_volume_pct: float | None = Field(default=None, ge=0, le=100)


class FallbackBehavior(BaseModel):
    model_config = ConfigDict(extra="forbid")

    if_not_filled: Literal["skip", "retry_5m", "retry_15m", "delay_to_close"] = "skip"
    if_gap_exceeds_limit: Literal["skip", "delay_to_5m", "delay_to_15m"] = "skip"
    if_spread_exceeds_limit: Literal["skip", "delay_to_5m", "delay_to_15m"] = "skip"


class HistoricalExecutionContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal["guaranteed_next_regular_open_cost_stress"]
    equivalent_to_future_order_policy: Literal[False]
    paper_readiness_credit: Literal[False]


class FutureOrderContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_style: Literal["opg_limit"]
    submission_cutoff_et: str = Field(pattern=r"^\d{2}:\d{2}:\d{2}$")
    limit_reference: Literal["prior_regular_close"]
    buy_limit_offset_bps: float = Field(ge=0)
    sell_limit_offset_bps: float = Field(ge=0)
    gap_reference: Literal["prior_regular_close"]
    unfilled_target_policy: Literal["retain_actual_holdings_until_next_scheduled_review"]
    partial_fill_policy: Literal["cancel_remainder_and_reconcile_actual_weights"]
    paired_leg_policy: Literal["no_unhedged_second_leg_after_first_leg_rejection"]
    retry_policy: Literal["none"]
    duplicate_order_policy: Literal["stable_signal_id"]


class TCAPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    compare_to: list[Literal["decision_price", "official_open", "arrival_price", "vwap"]] = Field(
        default_factory=lambda: ["decision_price", "official_open"]
    )
    record_submitted_at: bool = True
    record_fill_price: bool = True
    review_frequency: Literal["per_order", "daily", "weekly"] = "weekly"


class ExecutionPolicy(BaseModel):
    """Structured execution policy for paper_auto / daily-open strategies.

    Used when a strategy declares an explicit execution method other than the
    default DAY market order. The execution-reality-reviewer skill compares at
    least two alternatives; the recommended policy is recorded here.
    """

    model_config = ConfigDict(extra="forbid")

    policy_id: str = Field(min_length=1)
    order_style: Literal[
        "day_market",
        "moo_market",
        "opg_limit",
        "loo_limit",
        "delayed_open_5m",
        "delayed_open_15m",
        "twap",
    ]
    time_in_force: Literal["day", "opg", "ioc", "gtc"] = "day"
    price_protection: PriceProtection = Field(default_factory=PriceProtection)
    participation_cap: ParticipationCap = Field(default_factory=ParticipationCap)
    fallback_behavior: FallbackBehavior = Field(default_factory=FallbackBehavior)
    tca: TCAPlan = Field(default_factory=TCAPlan)
    alternatives_compared: list[str] = Field(default_factory=list, min_length=0)
    source_card_ids: list[str] = Field(default_factory=list)
    naked_market_justification: str | None = None
    historical_execution_contract: HistoricalExecutionContract | None = None
    future_order_contract: FutureOrderContract | None = None

    @model_validator(mode="after")
    def require_justification_for_naked_market(self) -> ExecutionPolicy:
        if (
            self.order_style == "day_market"
            and self.price_protection.limit_offset_bps is None
            and self.price_protection.max_open_gap_pct is None
            and not self.naked_market_justification
        ):
            msg = (
                "day_market without price_protection requires naked_market_justification "
                "explaining why the risk is acceptable"
            )
            raise ValueError(msg)
        return self


class StressScenario(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    slippage_bps: float = Field(ge=0)
    open_gap_pct: float = Field(default=0.0, ge=0)


class RealityModel(BaseModel):
    """Optional execution-reality assumptions used by the execution-reality reviewer.

    Mirrors the QuantConnect Reality Modeling split between strategy logic and
    broker/fill assumptions. Populated by execution-reality-reviewer skill or by
    `oc strategy execution-policy`.
    """

    model_config = ConfigDict(extra="forbid")

    fill_model: Literal[
        "next_bar_open",
        "next_regular_open_with_policy",
        "delayed_open_with_policy",
        "twap",
    ] = "next_bar_open"
    slippage_model: Literal[
        "fixed_bps",
        "stress_bps_by_volatility_and_participation",
        "almgren_chriss",
    ] = "fixed_bps"
    stress_scenarios: list[StressScenario] = Field(default_factory=list)


class MLLabel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "forward_return",
        "forward_direction",
        "path_survival",
        "net_incremental_policy_value",
    ] = "forward_return"
    horizon_bars: int | None = Field(default=5, ge=1, le=60)
    horizon_mode: Literal["fixed_bars", "next_scheduled_review_open"] = "fixed_bars"
    review_schedule: Literal["calendar_month_end"] | None = None
    maximum_horizon_bars: int | None = Field(default=None, ge=1, le=60)
    threshold_pct: float | None = None
    max_drawdown_pct: float | None = Field(default=None, ge=0)
    min_terminal_return_pct: float | None = None
    path_drawdown_reference: Literal["start_open", "running_open_peak"] | None = None
    baseline_policy: str | None = None
    alternative_policy: str | None = None
    value_measure: Literal["log_wealth_ratio"] | None = None
    one_way_cost_bps: float | None = Field(default=None, ge=0)
    terminal_rejoin_cost_included: bool | None = None

    @model_validator(mode="after")
    def validate_horizon_and_policy_value(self) -> MLLabel:
        if self.horizon_mode == "fixed_bars" and self.horizon_bars is None:
            raise ValueError("fixed_bars ML labels require horizon_bars")
        if self.horizon_mode == "next_scheduled_review_open":
            if (
                self.horizon_bars is not None
                or self.review_schedule is None
                or self.maximum_horizon_bars is None
            ):
                raise ValueError(
                    "next_scheduled_review_open labels require review_schedule and "
                    "maximum_horizon_bars with horizon_bars=null"
                )
        elif self.maximum_horizon_bars is not None:
            raise ValueError("fixed_bars ML labels must not set maximum_horizon_bars")
        if self.type == "net_incremental_policy_value":
            required = (
                self.baseline_policy,
                self.alternative_policy,
                self.value_measure,
                self.one_way_cost_bps,
                self.terminal_rejoin_cost_included,
            )
            if self.horizon_mode != "next_scheduled_review_open" or any(
                value is None for value in required
            ):
                raise ValueError(
                    "net_incremental_policy_value requires scheduled horizon, policies, "
                    "value_measure, costs, and terminal rejoin semantics"
                )
        return self


class MLTraining(BaseModel):
    model_config = ConfigDict(extra="forbid")

    window_bars: int = Field(default=378, ge=120)
    retrain_every_bars: int | None = Field(default=21, ge=5)
    retrain_schedule: Literal["fixed_bars", "calendar_month_end"] = "fixed_bars"
    test_window_bars: int = Field(default=63, ge=21)
    purge_bars: int | None = Field(default=None, ge=0)
    embargo_bars: int = Field(default=5, ge=0)
    seed: int = 42

    @model_validator(mode="after")
    def validate_retrain_schedule(self) -> MLTraining:
        if self.retrain_schedule == "fixed_bars" and self.retrain_every_bars is None:
            raise ValueError("fixed_bars training requires retrain_every_bars")
        if self.retrain_schedule == "calendar_month_end":
            if self.retrain_every_bars is not None or self.purge_bars is None:
                raise ValueError(
                    "calendar_month_end training requires retrain_every_bars=null and "
                    "an explicit purge_bars"
                )
        return self


class MLSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: Literal["threshold", "top_quantile"] = "threshold"
    threshold: float | None = None
    quantile: float | None = Field(default=None, gt=0, lt=1)
    operator: Literal[
        "greater_than_or_equal",
        "less_than_or_equal",
        "lower_bound_strictly_greater_than",
    ] = "greater_than_or_equal"

    @model_validator(mode="after")
    def require_selection_value(self) -> MLSelection:
        if self.method == "threshold" and self.threshold is None:
            object.__setattr__(self, "threshold", 0.0)
        if self.method == "top_quantile" and self.quantile is None:
            msg = "selection.method=top_quantile requires 0<quantile<1"
            raise ValueError(msg)
        return self


class MLProbabilityCalibratorConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["logistic_regression"]
    C: float = Field(gt=0)
    penalty: Literal["l2"] = "l2"
    solver: Literal["lbfgs"] = "lbfgs"
    max_iter: int = Field(ge=1)
    use_training_seed: bool = True


class MLAbstentionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    calibration_method: Literal[
        "chronological_split_conformal_lower_bound",
        "chronological_platt_scaling",
    ]
    calibration_fraction: float = Field(gt=0, lt=0.5)
    minimum_fit_rows: int = Field(ge=1)
    minimum_calibration_rows: int = Field(ge=1)
    minimum_positive_class_rows: int | None = Field(default=None, ge=1)
    minimum_negative_class_rows: int | None = Field(default=None, ge=1)
    minimum_calibration_positive_class_rows: int | None = Field(default=None, ge=1)
    minimum_calibration_negative_class_rows: int | None = Field(default=None, ge=1)
    target_coverage: float | None = Field(default=None, gt=0, lt=1)
    quantile_method: Literal["higher"] | None = None
    calibrator: MLProbabilityCalibratorConfig | None = None
    fallback_candidate_id: str = Field(min_length=1)
    insufficient_data_action: Literal["exact_target_identity_fallback"]

    @model_validator(mode="after")
    def validate_calibration_contract(self) -> MLAbstentionConfig:
        conformal = self.calibration_method == "chronological_split_conformal_lower_bound"
        if conformal != (self.target_coverage is not None and self.quantile_method is not None):
            raise ValueError(
                "split conformal abstention requires target_coverage and quantile_method; "
                "other calibration methods must omit them"
            )
        if conformal == (self.calibrator is not None):
            raise ValueError(
                "Platt calibration requires a calibrator contract; conformal calibration "
                "must not declare one"
            )
        class_minima = (
            self.minimum_positive_class_rows,
            self.minimum_negative_class_rows,
            self.minimum_calibration_positive_class_rows,
            self.minimum_calibration_negative_class_rows,
        )
        if self.calibration_method == "chronological_platt_scaling" and any(
            value is None for value in class_minima
        ):
            raise ValueError("Platt calibration requires positive and negative class minima")
        return self


class MLPolicyAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["invert_tactical_sleeve", "shift_portfolio_weight"]
    source_symbol: str | None = None
    destination_symbol: str | None = None
    portfolio_weight_delta: float | None = Field(default=None, gt=0, le=1)
    apply_at: Literal["next_regular_session_open"]
    hold_until: Literal["next_scheduled_review_open"]

    @model_validator(mode="after")
    def validate_weight_shift(self) -> MLPolicyAction:
        fields = (self.source_symbol, self.destination_symbol, self.portfolio_weight_delta)
        if self.kind == "shift_portfolio_weight" and any(value is None for value in fields):
            raise ValueError("shift_portfolio_weight requires symbols and portfolio_weight_delta")
        if self.kind == "invert_tactical_sleeve" and any(value is not None for value in fields):
            raise ValueError("invert_tactical_sleeve must not declare fixed weight-shift fields")
        return self


class MLModelConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal[
        "lightgbm_regressor",
        "lightgbm_classifier",
        "ridge_regressor",
        "logistic_regression_classifier",
    ] = "lightgbm_regressor"
    label: MLLabel = Field(default_factory=MLLabel)
    features: list[str] = Field(min_length=1)
    training: MLTraining = Field(default_factory=MLTraining)
    selection: MLSelection = Field(default_factory=MLSelection)
    abstention: MLAbstentionConfig | None = None
    action: MLPolicyAction | None = None
    preprocessing: Literal["standard_scaler"] = "standard_scaler"
    hyperparameters: dict[str, Any] = Field(default_factory=dict)
    baseline: Literal["linear_composite", "none"] = "linear_composite"


class StrategySpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    timeframe: StrategyTimeframe
    universe: list[str] = Field(min_length=1)
    lifecycle: Literal["draft", "approved", "active", "retired"]
    position_direction: Literal["long_only", "short_only", "long_short"] = "long_only"
    entry: RuleBlock
    exit: RuleBlock
    risk: RiskConfig
    portfolio: PortfolioConfig = Field(default_factory=PortfolioConfig)
    costs: CostConfig = Field(default_factory=CostConfig)
    execution: ExecutionConfig
    data: DataConfig = Field(default_factory=DataConfig)
    data_assumptions: DataAssumptions = Field(default_factory=DataAssumptions)
    factors: dict[str, FactorConfig] = Field(default_factory=dict)
    llm_review: LLMReviewConfig = Field(default_factory=LLMReviewConfig)
    notes: NotesConfig = Field(default_factory=NotesConfig)
    research_design: ResearchDesign | None = None
    required_capabilities: list[str] = Field(default_factory=list)
    execution_policy: ExecutionPolicy | None = None
    reality_model: RealityModel | None = None
    model: MLModelConfig | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not value.replace("_", "").replace("-", "").isalnum():
            msg = "name may only contain letters, numbers, underscores, and hyphens"
            raise ValueError(msg)
        return value

    @field_validator("universe")
    @classmethod
    def normalize_universe(cls, value: list[str]) -> list[str]:
        return [symbol.upper().strip() for symbol in value]

    @field_validator("factors")
    @classmethod
    def validate_factor_names(cls, value: dict[str, FactorConfig]) -> dict[str, FactorConfig]:
        reserved = {"open", "high", "low", "close", "volume"}
        for name in value:
            if not name.isidentifier():
                msg = f"factor name must be a valid identifier: {name}"
                raise ValueError(msg)
            if name in reserved:
                msg = f"factor name is reserved: {name}"
                raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def validate_model_features(self) -> StrategySpec:
        if self.model is None:
            return self
        missing = [feature for feature in self.model.features if feature not in self.factors]
        if missing:
            msg = "model.features must reference declared spec factors: " + ", ".join(missing)
            raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def validate_etf_structural_family(self) -> StrategySpec:
        config = self.portfolio.etf_structural
        if config is None:
            return self
        if self.timeframe != "daily":
            raise ValueError("etf_structural_family requires timeframe=daily")
        if self.position_direction != "long_only":
            raise ValueError("etf_structural_family requires position_direction=long_only")
        universe = set(self.universe)
        required_symbols = {
            config.core_symbol,
            config.reserve_symbol,
            config.sector_relative.benchmark_symbol,
            *config.diversifier_symbols,
            *config.sector_relative.symbols,
        }
        if config.risk_overlay is not None:
            required_symbols.update(
                {
                    config.risk_overlay.volatility_reference_symbol,
                    config.risk_overlay.drawdown_reference_symbol,
                }
            )
        missing = sorted(required_symbols - universe)
        if missing:
            raise ValueError(
                "portfolio.etf_structural symbols must be in universe: " + ", ".join(missing)
            )
        if config.core_symbol in config.sector_relative.symbols:
            raise ValueError("core_symbol cannot also be a sector candidate")
        if config.reserve_symbol in config.sector_relative.symbols:
            raise ValueError("reserve_symbol cannot also be a sector candidate")
        if set(config.diversifier_symbols) & set(config.sector_relative.symbols):
            raise ValueError("diversifier and sector symbol sets must be disjoint")
        return self

    @property
    def primary_symbol(self) -> str:
        return (self.data.symbol or self.universe[0]).upper()

    def all_expressions(self) -> list[str]:
        return [*self.entry.all, *self.entry.any, *self.exit.all, *self.exit.any]


def load_strategy_spec(path: Path | str, *, validate: bool = True) -> StrategySpec:
    spec_path = Path(path)
    with spec_path.open("r", encoding="utf-8") as handle:
        raw = safe_load_yaml(handle)
    if not isinstance(raw, dict):
        msg = f"{spec_path} must contain a YAML mapping"
        raise ValueError(msg)
    spec = StrategySpec.model_validate(raw)
    if not validate:
        return spec

    from open_composer.expressions import validate_expression

    root = spec_path.parents[2] if len(spec_path.parents) >= 3 else spec_path.parent
    for expression in spec.all_expressions():
        validate_expression(expression, spec.factors, root=root)
    return spec
