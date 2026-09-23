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


class InsiderBuyPortfolioConfig(BaseModel):
    """``portfolio.mode=insider_buy_portfolio`` selection rule (H-20260917-01).

    A monthly, equal-weight, long-only book of names whose point-in-time Form 4
    insider table shows open-market buying over the trailing 60 sessions.
    Consumed by ``open_composer.adapters.execution.insider_portfolio_target_weights``;
    every field is a parameter of that adapter and nothing here is read by the
    rule engine. Paths are repo-relative feature roots; the ``*_fallback_root``
    is used (with a recorded warning) only when the preferred root has no
    yearly parquet files yet.
    """

    model_config = ConfigDict(extra="forbid")

    universe_root: str = "data/features/universe_broad"
    universe_fallback_root: str | None = "data/features/universe"
    insider_feature_root: str = "data/features/insider_broad"
    insider_feature_fallback_root: str | None = "data/features/insider"
    #: Optional liquidity band on the cohort's ``adv_rank`` (inclusive, 1-based).
    #: ``None`` on both ends means the whole cohort; e.g. 501/100000 keeps
    #: everything outside the top-500 ADV names.
    adv_rank_min: int | None = Field(default=None, ge=1)
    adv_rank_max: int | None = Field(default=None, ge=1)
    min_open_market_buy_count_60d: int = Field(default=1, ge=1)
    min_net_buy_usd_60d: float = Field(default=25_000.0, ge=0)
    min_buyers_60d: int = Field(default=1, ge=1)
    rank_column: Literal[
        "net_buy_usd_60d",
        "net_buy_shares_60d",
        "buyers_60d",
        "net_buyers_60d",
        "opportunistic_buy_60d",
        "cmp_opportunistic_buy_60d",
    ] = "net_buy_usd_60d"
    max_names: int = Field(default=100, ge=1)
    gross_target: float = Field(default=1.0, gt=0, le=1)
    per_name_cap: float = Field(default=0.05, gt=0, le=1)
    rebalance: Literal["calendar_month_end"] = "calendar_month_end"
    #: A candidate with no daily bar inside the last N sessions is skipped
    #: (delisted / halted / backfilled-only name) and recorded in the manifest.
    stale_bar_sessions: int = Field(default=5, ge=1)

    @model_validator(mode="after")
    def validate_band(self) -> InsiderBuyPortfolioConfig:
        if (
            self.adv_rank_min is not None
            and self.adv_rank_max is not None
            and self.adv_rank_min > self.adv_rank_max
        ):
            raise ValueError("insider_buy.adv_rank_min must be <= adv_rank_max")
        if self.per_name_cap > self.gross_target:
            raise ValueError("insider_buy.per_name_cap must be <= gross_target")
        return self


class RotationDipBoostConfig(BaseModel):
    """Temporary lift of the volatility target after an oversold dip in an
    uptrend (card H-20260922-05, path B): when ``signal_symbol`` closes above
    its ``sma_sessions`` simple moving average and its Wilder RSI over
    ``rsi_sessions`` is below ``rsi_below``, the target becomes
    ``target_annual_vol`` for the next ``hold_sessions`` sessions. The
    multiplier stays capped at 1.0, so a boost can only move the book back
    toward the unscaled rotation, never lever it."""

    model_config = ConfigDict(extra="forbid")

    signal_symbol: str = "QQQ"
    sma_sessions: int = Field(default=200, ge=20, le=400)
    rsi_sessions: int = Field(default=10, ge=2, le=50)
    rsi_below: float = Field(default=30.0, gt=0, lt=100)
    target_annual_vol: float = Field(gt=0, le=3.0)
    hold_sessions: int = Field(ge=1, le=60)

    @field_validator("signal_symbol")
    @classmethod
    def normalize_signal_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if not normalized:
            raise ValueError("vol_target.dip_boost.signal_symbol cannot be blank")
        return normalized


class RotationVolTargetConfig(BaseModel):
    """Down-only volatility target on a rotation book (cards H-20260922-02
    and -05). The multiplier is ``min(1, target / realized)``, where
    ``realized`` is the annualized sample standard deviation of the
    *unscaled* book's daily returns over ``realized_vol_sessions``. It is
    recomputed only at the open after a rebalance close and, with a dip
    boost, at the open after the boost turns on or off; between updates it
    is constant. The weight it removes goes to the cash symbol."""

    model_config = ConfigDict(extra="forbid")

    target_annual_vol: float = Field(gt=0, le=3.0)
    realized_vol_sessions: int = Field(default=21, ge=5, le=126)
    dip_boost: RotationDipBoostConfig | None = None

    @model_validator(mode="after")
    def validate_boost_above_base(self) -> RotationVolTargetConfig:
        if self.dip_boost is not None and (
            self.dip_boost.target_annual_vol <= self.target_annual_vol
        ):
            raise ValueError(
                "vol_target.dip_boost.target_annual_vol must exceed vol_target.target_annual_vol"
            )
        return self


class ETFRotationConfig(BaseModel):
    """``portfolio.mode=etf_rotation_portfolio`` selection rule.

    A periodically rescored, equal-weight, long-only rotation across a fixed
    menu of ETFs: each candidate's score is the arithmetic mean of its simple
    total return over every configured lookback (in sessions), the top
    ``top_n`` scorers are held, and (when ``absolute_momentum_filter`` is set)
    a pick is dropped whenever its score does not exceed the cash symbol's
    score over the same lookbacks. ``unfilled_slot_policy`` decides what
    happens to a dropped pick's weight. Consumed by
    ``open_composer.adapters.execution.rotation_target_weights``.
    """

    model_config = ConfigDict(extra="forbid")

    menu: list[str] = Field(min_length=2, max_length=24)
    cash_symbol: str
    lookbacks: list[int] = Field(min_length=1, max_length=8)
    top_n: int = Field(ge=1)
    rebalance: Literal["monthly_last_session", "weekly_friday"]
    absolute_momentum_filter: bool = True
    min_history_sessions: int = Field(default=260, ge=30, le=2000)
    #: What happens to the weight of a pick the absolute-momentum filter
    #: dropped. ``cash`` leaves that slot in ``cash_symbol``, so a two-slot
    #: book with one survivor is 50% invested; this is the more common
    #: published rule and the defensive default. ``renormalize_survivors``
    #: equal-weights the survivors among themselves, so the same book is 100%
    #: in the single survivor. The difference only bites when the filter fires
    #: often, and it concentrates risk exactly when the filter is warning --
    #: measured on card H-20260918-05, the levered sleeve fires the filter in 13
    #: of 52 months and its anchor-window Sharpe is 1.48 under
    #: ``renormalize_survivors`` against 1.26 under ``cash``. Set it explicitly
    #: and say which one the backtest used.
    unfilled_slot_policy: Literal["cash", "renormalize_survivors"] = "cash"
    #: Optional per-strategy sizing budget in USD. Several
    #: ``etf_rotation_portfolio`` strategies may run concurrently against one
    #: shared paper account, so each one needs its own dollar budget rather
    #: than sizing against the full account. When set, the adapter sizes this
    #: book against ``min(notional_budget_usd, account_equity)``; when unset
    #: (the default), it sizes against full account equity, matching every
    #: other portfolio mode's behavior.
    notional_budget_usd: float | None = Field(default=None, gt=0, le=1_000_000)
    #: Optional down-only volatility target (see ``RotationVolTargetConfig``).
    vol_target: RotationVolTargetConfig | None = None
    #: What a paper sleeve is sized against. ``notional_budget`` (default)
    #: sizes every rebalance against ``notional_budget_usd`` as a fixed
    #: amount. ``sleeve_equity`` treats the budget as the sleeve's starting
    #: capital and sizes against the budget plus the sleeve's own marked P&L
    #: (from its fills ledger), so the sleeve compounds like the backtest.
    sizing_basis: Literal["notional_budget", "sleeve_equity"] = "notional_budget"
    #: Optional drawdown exit: when the sleeve's equity (budget plus marked
    #: P&L) falls this fraction below its peak, the paper run liquidates the
    #: sleeve and revokes its rehearsal authorization.
    drawdown_exit_pct: float | None = Field(default=None, gt=0, lt=1)
    #: Optional override of the paper planner's churn tolerance (the drift, as
    #: a fraction of position value, below which a resize is skipped). The
    #: planner default of 0.25 would swallow most volatility-target moves.
    rebalance_tolerance_fraction: float | None = Field(default=None, ge=0, le=0.5)

    @field_validator("menu")
    @classmethod
    def normalize_menu(cls, value: list[str]) -> list[str]:
        normalized = [symbol.upper().strip() for symbol in value]
        if any(not symbol for symbol in normalized):
            raise ValueError("etf_rotation.menu cannot contain blanks")
        if len(normalized) != len(set(normalized)):
            raise ValueError("etf_rotation.menu must be unique")
        return normalized

    @field_validator("cash_symbol")
    @classmethod
    def normalize_cash_symbol(cls, value: str) -> str:
        normalized = value.upper().strip()
        if not normalized:
            raise ValueError("etf_rotation.cash_symbol cannot be blank")
        return normalized

    @field_validator("lookbacks")
    @classmethod
    def validate_lookbacks(cls, value: list[int]) -> list[int]:
        if any(lookback < 2 or lookback > 504 for lookback in value):
            raise ValueError("etf_rotation.lookbacks entries must be in 2..504")
        if len(value) != len(set(value)):
            raise ValueError("etf_rotation.lookbacks must be unique")
        return value

    @model_validator(mode="after")
    def validate_menu_and_top_n(self) -> ETFRotationConfig:
        if self.cash_symbol in self.menu:
            raise ValueError("etf_rotation.cash_symbol must not appear in menu")
        if self.top_n > len(self.menu):
            raise ValueError("etf_rotation.top_n must be <= len(menu)")
        needs_budget = self.sizing_basis == "sleeve_equity" or self.drawdown_exit_pct is not None
        if needs_budget and self.notional_budget_usd is None:
            raise ValueError(
                "etf_rotation.sizing_basis=sleeve_equity and drawdown_exit_pct need "
                "notional_budget_usd as the sleeve's starting equity"
            )
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
        "model_ranking_portfolio",
        "event_driven_capacity_book",
        "insider_buy_portfolio",
        "etf_rotation_portfolio",
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
    #: Step 11 Wave C -- `model_ranking_portfolio` mode fields. All are
    #: required together when `mode == "model_ranking_portfolio"` and must
    #: stay unset for every other mode (enforced in
    #: `require_model_ranking_fields`). Directory produced by the research
    #: line: `model.joblib` (or a rule-based placeholder that needs no
    #: model file), `features.json`, `config.json`, `README.md`.
    candidate_artifact_dir: str | None = None
    universe_rule: Literal["pit_adv_top_n"] | None = None
    universe_top_n: int | None = Field(default=None, ge=1)
    feature_set_id: str | None = None
    label_horizon_days: Literal[5, 10, 21] | None = None
    top_k: int | None = Field(default=None, ge=1)
    rebalance: Literal["weekly_friday_close_monday_open"] | None = None
    #: `none` = long-only top-K; `spy_beta_hedge` = top-K long book plus a
    #: short SPY leg sized at the book's blended 252-session beta.
    hedge: Literal["none", "spy_beta_hedge"] | None = None
    #: Overrides the live Alpaca account equity read for whole-share sizing.
    #: Leave unset in every spec that ships; it exists for deterministic
    #: tests and for a future explicit user override, not for routine use.
    account_equity_for_sizing: float | None = Field(default=None, gt=0)
    #: Step 14 (``docs/plan-step-14-timeframe-agnostic-bar-cycle-runner-2026-09-11.zh.md``)
    #: -- `event_driven_capacity_book` mode fields: a discrete, signal-
    #: triggered entry/exit book with a fixed concurrent-position cap (e.g.
    #: Reversal Trend hourly, `open_composer.execution.signal_engine.ReversalTrendSignalEngine`),
    #: as opposed to a periodically-rescored ranking book
    #: (`model_ranking_portfolio`). All required together when
    #: mode=="event_driven_capacity_book"; must stay unset for every other
    #: mode. `StrategySpec` is this repo's source of truth for strategy
    #: behavior (CLAUDE.md), so the engine's own parameterization lives here,
    #: not hardcoded in a script.
    event_signal_engine: str | None = None
    event_holding_bars: int | None = Field(default=None, ge=1)
    event_exit_rule: Literal["time_stop", "time_stop_or_reverse", "atr_trailing_2x"] | None = None
    event_signal_set: Literal["bull_only", "bull_and_recl"] | None = None
    event_max_positions: int | None = Field(default=None, ge=1)
    event_position_weight: float | None = Field(default=None, gt=0, le=1)
    #: 2026-09-18 -- `insider_buy_portfolio` mode block (H-20260917-01 paper
    #: plumbing). Required iff mode=="insider_buy_portfolio", forbidden
    #: otherwise; see `InsiderBuyPortfolioConfig`.
    insider_buy: InsiderBuyPortfolioConfig | None = None
    #: 2026-09-18 -- `etf_rotation_portfolio` mode block. Required iff
    #: mode=="etf_rotation_portfolio", forbidden otherwise; see
    #: `ETFRotationConfig`.
    etf_rotation: ETFRotationConfig | None = None

    @model_validator(mode="after")
    def require_insider_buy_fields(self) -> PortfolioConfig:
        if self.mode == "insider_buy_portfolio":
            if self.insider_buy is None:
                raise ValueError("insider_buy_portfolio requires portfolio.insider_buy")
            if self.weighting != "equal_weight":
                raise ValueError("insider_buy_portfolio requires portfolio.weighting=equal_weight")
            if self.max_symbol_weight is not None and (
                self.insider_buy.per_name_cap > self.max_symbol_weight + 1e-12
            ):
                raise ValueError(
                    "insider_buy.per_name_cap must not exceed portfolio.max_symbol_weight"
                )
        elif self.insider_buy is not None:
            raise ValueError("portfolio.insider_buy requires mode=insider_buy_portfolio")
        return self

    @model_validator(mode="after")
    def require_etf_rotation_fields(self) -> PortfolioConfig:
        if self.mode == "etf_rotation_portfolio":
            if self.etf_rotation is None:
                raise ValueError("etf_rotation_portfolio requires portfolio.etf_rotation")
            if self.weighting != "equal_weight":
                raise ValueError("etf_rotation_portfolio requires portfolio.weighting=equal_weight")
        elif self.etf_rotation is not None:
            raise ValueError("portfolio.etf_rotation requires mode=etf_rotation_portfolio")
        return self

    @model_validator(mode="after")
    def require_event_driven_fields(self) -> PortfolioConfig:
        event_fields = {
            "event_signal_engine": self.event_signal_engine,
            "event_holding_bars": self.event_holding_bars,
            "event_exit_rule": self.event_exit_rule,
            "event_signal_set": self.event_signal_set,
            "event_max_positions": self.event_max_positions,
            "event_position_weight": self.event_position_weight,
        }
        if self.mode == "event_driven_capacity_book":
            missing = sorted(name for name, value in event_fields.items() if value is None)
            if missing:
                raise ValueError(
                    "event_driven_capacity_book requires portfolio fields: " + ", ".join(missing)
                )
            if not str(self.event_signal_engine).strip():
                raise ValueError(
                    "event_driven_capacity_book requires a non-blank event_signal_engine"
                )
        else:
            populated = sorted(name for name, value in event_fields.items() if value is not None)
            if populated:
                raise ValueError(
                    "event_driven_capacity_book fields require mode=event_driven_capacity_book: "
                    + ", ".join(populated)
                )
        return self

    @model_validator(mode="after")
    def require_model_ranking_fields(self) -> PortfolioConfig:
        model_ranking_fields = {
            "candidate_artifact_dir": self.candidate_artifact_dir,
            "universe_rule": self.universe_rule,
            "universe_top_n": self.universe_top_n,
            "feature_set_id": self.feature_set_id,
            "label_horizon_days": self.label_horizon_days,
            "top_k": self.top_k,
            "rebalance": self.rebalance,
            "hedge": self.hedge,
        }
        if self.mode == "model_ranking_portfolio":
            missing = sorted(name for name, value in model_ranking_fields.items() if value is None)
            if missing:
                raise ValueError(
                    "model_ranking_portfolio requires portfolio fields: " + ", ".join(missing)
                )
            if not str(self.candidate_artifact_dir).strip():
                msg = "model_ranking_portfolio requires a non-blank candidate_artifact_dir"
                raise ValueError(msg)
            if not str(self.feature_set_id).strip():
                raise ValueError("model_ranking_portfolio requires a non-blank feature_set_id")
            if self.weighting != "equal_weight":
                raise ValueError(
                    "model_ranking_portfolio requires portfolio.weighting=equal_weight"
                )
        else:
            populated = sorted(
                name for name, value in model_ranking_fields.items() if value is not None
            )
            if self.account_equity_for_sizing is not None:
                populated.append("account_equity_for_sizing")
            if populated:
                raise ValueError(
                    "model_ranking_portfolio fields require mode=model_ranking_portfolio: "
                    + ", ".join(sorted(populated))
                )
        return self

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
    #: 2026-09-18 -- which positions the paper rehearsal planner reconciles a
    #: strategy against. ``broker_account`` (the default, and the behaviour of
    #: every spec written before this date) plans against every position in the
    #: paper account, so anything held but not in the current targets is sold.
    #: ``strategy_ledger`` plans against only this strategy's own recorded fills
    #: (``reports/paper/rehearsal/<name>-fills.jsonl``) and ignores positions it
    #: did not open. ``strategy_ledger`` is required whenever more than one
    #: strategy shares the paper account, and it is the only correct option when
    #: two strategies can hold the same symbol, because scoping by symbol would
    #: not separate them. Consumed by ``open_composer.paper_rehearsal``.
    position_scope: Literal["broker_account", "strategy_ledger"] = "broker_account"
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

    @model_validator(mode="after")
    def validate_etf_rotation_portfolio(self) -> StrategySpec:
        config = self.portfolio.etf_rotation
        if config is None:
            return self
        if self.timeframe != "daily":
            raise ValueError("etf_rotation_portfolio requires timeframe=daily")
        if self.position_direction != "long_only":
            raise ValueError("etf_rotation_portfolio requires position_direction=long_only")
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
