from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.timeframes import StrategyTimeframe


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


class PortfolioConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: Literal[
        "single_symbol",
        "adaptive_intraday_internal_router",
        "hybrid_adaptive_router",
        "beta_exposure_router",
        "core_beta_satellite_router",
    ] = "single_symbol"
    max_symbols_per_day: int | None = Field(default=None, ge=1)
    gross_exposure_limit: float | None = Field(default=None, gt=0, le=1)
    max_symbol_weight: float | None = Field(default=None, gt=0, le=1)
    same_day_flatten: bool = False
    duplicate_signal_policy: Literal["stable_signal_id", "allow_duplicates"] = "stable_signal_id"
    selected_route_label: str | None = None

    @model_validator(mode="after")
    def require_router_route(self) -> PortfolioConfig:
        if (
            self.mode
            in {
                "adaptive_intraday_internal_router",
                "hybrid_adaptive_router",
                "beta_exposure_router",
                "core_beta_satellite_router",
            }
            and not self.selected_route_label
        ):
            msg = f"{self.mode} portfolio mode requires selected_route_label"
            raise ValueError(msg)
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

    @property
    def primary_symbol(self) -> str:
        return (self.data.symbol or self.universe[0]).upper()

    def all_expressions(self) -> list[str]:
        return [*self.entry.all, *self.entry.any, *self.exit.all, *self.exit.any]


def load_strategy_spec(path: Path | str) -> StrategySpec:
    spec_path = Path(path)
    with spec_path.open("r", encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    if not isinstance(raw, dict):
        msg = f"{spec_path} must contain a YAML mapping"
        raise ValueError(msg)
    spec = StrategySpec.model_validate(raw)

    from open_composer.expressions import validate_expression

    root = spec_path.parents[2] if len(spec_path.parents) >= 3 else spec_path.parent
    for expression in spec.all_expressions():
        validate_expression(expression, spec.factors, root=root)
    return spec
