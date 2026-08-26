from __future__ import annotations

import string
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json


@dataclass(frozen=True)
class FactorDefinition:
    id: str
    family: str
    label: str
    description: str
    inputs: list[str]
    output: str
    default_parameter_space: dict[str, list[Any]]
    expression: str | None = None
    source_card_ids: list[str] = field(default_factory=list)
    implementation_notes: list[str] = field(default_factory=list)
    risk_notes: list[str] = field(default_factory=list)


def materialize_expression(factor: FactorDefinition, params: dict[str, Any] | None = None) -> str:
    """Render a catalog expression template with supplied or default parameters."""
    if factor.expression is None:
        raise ValueError(f"factor {factor.id} has no expression template")
    supplied = params or {}
    resolved: dict[str, Any] = {}
    for key in _expression_placeholders(factor.expression):
        if key in supplied:
            resolved[key] = supplied[key]
        elif key in factor.default_parameter_space:
            options = factor.default_parameter_space[key]
            if not options:
                raise ValueError(f"factor {factor.id} default for {key!r} is empty")
            resolved[key] = options[0]
        else:
            raise ValueError(
                f"factor {factor.id} expression needs {key!r}; "
                "missing from params and default_parameter_space"
            )
    return factor.expression.format(**resolved)


def _expression_placeholders(expression: str) -> list[str]:
    return [
        field_name
        for _, field_name, _, _ in string.Formatter().parse(expression)
        if field_name is not None
    ]


TACTICAL_ROUTER_FACTOR_LIBRARY: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        id="absolute_time_series_momentum_120",
        family="trend_momentum",
        label="120-day absolute momentum",
        description=(
            "Uses an asset's own prior 120-day return as a trend gate before allocating "
            "to high-beta Nasdaq or leveraged ETF sleeves."
        ),
        inputs=["close"],
        output="momentum_pct",
        default_parameter_space={"lookback_days": [60, 120, 180]},
        source_card_ids=["tsm_moskowitz_ooi_pedersen", "faber_taa_trend_filter"],
        implementation_notes=[
            "Use shifted closes only; decision at close t uses data through t-1.",
            "Treat zero or negative momentum as a disqualification, not a short signal.",
        ],
    ),
    FactorDefinition(
        id="cross_sectional_relative_momentum_120",
        family="relative_strength",
        label="120-day relative momentum rank",
        description=(
            "Ranks offensive ETF sleeves by prior 120-day return after each asset passes "
            "its own trend filter."
        ),
        inputs=["close"],
        output="rank_score",
        default_parameter_space={"lookback_days": [60, 90, 120]},
        source_card_ids=["tsm_moskowitz_ooi_pedersen", "vaa_breadth_momentum"],
        implementation_notes=[
            "Rank only assets with finite history and positive absolute momentum.",
            "Keep rank computation independent of future full-window performance.",
        ],
    ),
    FactorDefinition(
        id="volatility_rank_20_252",
        family="risk_regime",
        label="20-day volatility percentile",
        description=(
            "Compares recent QQQ realized volatility with its trailing one-year distribution "
            "to flag high-risk regimes."
        ),
        inputs=["close"],
        output="volatility_percentile",
        default_parameter_space={"vol_window_days": [20, 60], "rank_window_days": [252]},
        source_card_ids=["moreira_muir_volatility_management"],
        implementation_notes=[
            "Use as a risk switch or rank penalty, not as a standalone return predictor.",
            "Stress-test gap events because volatility controls can lag discontinuous crashes.",
        ],
    ),
    FactorDefinition(
        id="drawdown_guard_20_60",
        family="risk_regime",
        label="20/60-day drawdown guard",
        description=(
            "Measures current price relative to recent rolling highs to avoid holding "
            "leveraged sleeves during fast breakdowns."
        ),
        inputs=["close"],
        output="drawdown_pct",
        default_parameter_space={"lookback_days": [20, 60], "trigger_pct": [8.0, 12.0, 16.0]},
        source_card_ids=["faber_taa_trend_filter", "moreira_muir_volatility_management"],
        implementation_notes=[
            "Shift the rolling high by one bar before comparing to the decision price.",
            "Use with recovery rules; otherwise it can over-exit after recoveries begin.",
        ],
    ),
    FactorDefinition(
        id="tech_canary_breadth",
        family="breadth_canary",
        label="Technology canary breadth",
        description=(
            "Counts QQQ/XLK/IGV/SOXX/SMH sleeves with positive trend and momentum to "
            "decide whether Nasdaq beta is broadly confirmed."
        ),
        inputs=["close", "universe_prices"],
        output="breadth_count",
        default_parameter_space={"min_breadth": [2, 3, 4], "lookback_days": [120]},
        source_card_ids=["vaa_breadth_momentum", "faber_taa_trend_filter"],
        implementation_notes=[
            "Breadth is a regime filter; do not treat the count as direct alpha without IC review.",
            "Canary failure should reduce risk sleeve selection, not force idle cash by default.",
        ],
    ),
    FactorDefinition(
        id="semiconductor_leadership_confirmation",
        family="leadership",
        label="Semiconductor leadership confirmation",
        description=(
            "Allows SOXL/TECL-style high-beta technology sleeves only when SMH trend and "
            "long momentum confirm leadership."
        ),
        inputs=["close", "SMH"],
        output="leadership_ok",
        default_parameter_space={"lookback_days": [120, 252], "min_momentum_pct": [60.0, 100.0]},
        source_card_ids=["tsm_moskowitz_ooi_pedersen"],
        implementation_notes=[
            "This is a concentration guard for high-beta sleeves, not proof of independent alpha.",
            "Evaluate with contribution and turnover diagnostics before promotion.",
        ],
    ),
    FactorDefinition(
        id="defensive_asset_dual_momentum",
        family="defensive_selection",
        label="Defensive asset dual momentum",
        description=(
            "Ranks GLD/BIL/IEF/TLT/SHY-style defensive sleeves by their own momentum and "
            "trend so full capital can stay allocated without defaulting to idle cash."
        ),
        inputs=["close"],
        output="defensive_rank",
        default_parameter_space={
            "lookback_days": [60, 120],
            "candidate_assets": [["GLD", "BIL"], ["GLD", "IEF", "SHY"], ["GLD", "TLT", "BIL"]],
        },
        source_card_ids=["vaa_breadth_momentum", "faber_taa_trend_filter"],
        implementation_notes=[
            "Use defensive allocation as full-capital risk substitution, not a low-gross cap.",
            "Cross-source replay is required before adding bond ETFs to paper-ready routing.",
        ],
    ),
    FactorDefinition(
        id="leveraged_etf_extension_guard",
        family="risk_regime",
        label="Leveraged ETF extension guard",
        description=(
            "Downshifts from 3x/high-beta sleeves to moderate beta when an asset is far "
            "above its intermediate trend and short-horizon momentum is stretched."
        ),
        inputs=["close"],
        output="extension_pct",
        default_parameter_space={"sma_days": [50], "extension_pct": [25.0, 35.0]},
        source_card_ids=["leveraged_etf_reset_risk", "momentum_crash_risk"],
        implementation_notes=[
            "This is a crash-risk guard against chasing parabolic leveraged ETF moves.",
            (
                "Accept only if it improves OOS drawdown without destroying recent "
                "TQQQ-relative returns."
            ),
        ],
    ),
    FactorDefinition(
        id="risk_on_recovery_boost",
        family="recovery_regime",
        label="Risk-on recovery boost",
        description=(
            "Allows a controlled upshift from moderate beta to TQQQ when trend, canary "
            "breadth, and short-horizon TQQQ recovery all confirm after a stress period."
        ),
        inputs=["close", "universe_prices"],
        output="recovery_boost_ok",
        default_parameter_space={
            "recovery_lookback_days": [10, 20],
            "min_recovery_pct": [8.0, 12.0],
        },
        source_card_ids=["tsm_moskowitz_ooi_pedersen", "momentum_crash_risk"],
        implementation_notes=[
            "Use as an upshift condition only after trend and breadth gates already pass.",
            "Do not apply when the target leveraged ETF is still below its trend filter.",
        ],
    ),
    FactorDefinition(
        id="strong_risk_on_state",
        family="recovery_regime",
        label="Strong risk-on state",
        description=(
            "Confirms broad technology participation, recovered QQQ drawdown, and positive "
            "TQQQ short/intermediate momentum before overriding conservative QLD/QQQ ranks."
        ),
        inputs=["close", "universe_prices"],
        output="strong_risk_on_ok",
        default_parameter_space={
            "min_breadth": [3, 4],
            "qqq_drawdown_floor_pct": [-4.0, -2.0, 0.0],
            "tqqq_momentum60_min_pct": [10.0, 20.0],
        },
        source_card_ids=[
            "regime_dependent_trend_allocation",
            "state_conditional_momentum_crash_risk",
        ],
        implementation_notes=[
            "Apply only after defensive/stress gates have cleared.",
            "Use to improve participation in strong rebound trends, not to bypass crash guards.",
        ],
    ),
    FactorDefinition(
        id="core_beta_sleeve",
        family="portfolio_construction",
        label="Persistent core beta sleeve",
        description=(
            "Keeps a QQQ/QLD/TQQQ-style core sleeve active during confirmed risk-on "
            "regimes so drawdown control comes from instrument choice and state "
            "switching, not from idle cash."
        ),
        inputs=["close", "trend_state", "portfolio_weights"],
        output="core_weight",
        default_parameter_space={
            "core_assets": [["QQQ", "QLD"], ["QLD", "TQQQ"]],
            "core_weight_pct": [25.0, 40.0, 55.0],
        },
        source_card_ids=[
            "faber_taa_trend_filter",
            "tsm_moskowitz_ooi_pedersen",
        ],
        implementation_notes=[
            "Core sleeve stays long only after market trend gates pass.",
            "Use full gross exposure accounting; never treat unused cash as risk control.",
        ],
    ),
    FactorDefinition(
        id="vix_vix3m_term_structure_state",
        family="implied_volatility_term_structure",
        label="VIX/VIX3M term-structure state",
        description=(
            "Uses the paired Cboe one-month and three-month SPX implied-volatility "
            "indices to classify contango, transition, backwardation, and crisis states "
            "for a separately traded long-only ETF exposure ladder."
        ),
        inputs=[
            "vix_close",
            "vix3m_close",
            "visible_at",
            "source",
            "input_hash",
        ],
        output="volatility_term_structure_state",
        default_parameter_space={
            "risk_on_ratio_max": [0.92, 0.95, 0.98],
            "stress_ratio_min": [1.00, 1.03, 1.06],
            "crisis_vix_min": [35.0, 40.0, 45.0],
            "exit_confirmation_sessions": [1, 2, 3],
        },
        expression=None,
        source_card_ids=[
            "vix_r1_cboe_vix3m_term_structure",
            "vix_r1_vix_term_structure_paper",
        ],
        implementation_notes=[
            (
                "This is an external paired-index packet factor, not an OHLCV expression; "
                "research runners must join only rows whose visible_at is no later than "
                "the next-open decision timestamp."
            ),
            (
                "Require same-date VIX and VIX3M legs, reject forward fill, and fail closed "
                "on missing, stale, duplicate, or nonfinite observations."
            ),
            (
                "The indices are not tradable. Map states only to separately validated "
                "long-only ETF targets such as TQQQ, QQQ, and BIL."
            ),
        ],
        risk_notes=[
            (
                "Historical Cboe downloads establish research replay, not historical "
                "first-seen time or paper-ready collection latency."
            ),
            (
                "VIX/VIX3M state can reverse around gaps; next-open execution and protected "
                "order behavior require separate parity and TCA evidence."
            ),
        ],
    ),
    FactorDefinition(
        id="fixed_anchor_monthly_trend_sleeve",
        family="portfolio_construction",
        label="Fixed anchor plus monthly trend sleeve",
        description=(
            "Keeps a fixed leveraged-ETF anchor invested while a separate tactical sleeve "
            "switches between the leveraged ETF and a declared defensive asset at the final "
            "completed session of each month using the underlying index trend."
        ),
        inputs=["underlying_close", "portfolio_weights", "review_calendar"],
        output="anchor_and_tactical_target_weights",
        default_parameter_space={
            "anchor_weight_pct": [40.0, 50.0, 60.0],
            "trend_sma_sessions": [200],
            "risk_on_assets": [["TQQQ"]],
            "risk_off_assets": [["BIL"]],
            "review_schedule": ["calendar_month_end"],
        },
        source_card_ids=[
            "hbs_r1_time_series_momentum_paper",
            "hbs_r1_tqqq_daily_target_and_path_risk",
        ],
        implementation_notes=[
            (
                "Confirm the underlying index at the completed close and trade at the "
                "next regular open."
            ),
            (
                "The trend gate changes only the tactical sleeve; it never silently "
                "removes the fixed anchor."
            ),
            "Hold units between reviews so actual weights drift until the next scheduled target.",
        ],
        risk_notes=[
            (
                "A persistent leveraged anchor retains gap and path-dependency risk "
                "during failed trends."
            ),
            "A monthly trend review can miss fast breaks and early rebound sessions.",
        ],
    ),
    FactorDefinition(
        id="leadership_satellite_rank",
        family="relative_strength",
        label="Leadership satellite rank",
        description=(
            "Ranks high-beta technology sleeves and allocates a bounded satellite "
            "weight to the strongest positive-momentum leaders beside the core beta sleeve."
        ),
        inputs=["close", "universe_prices", "portfolio_weights"],
        output="satellite_weights",
        default_parameter_space={
            "lookback_days": [20, 60, 120],
            "top_n": [1, 2],
            "max_symbol_weight_pct": [55.0, 70.0, 85.0],
        },
        source_card_ids=[
            "cross_sectional_relative_momentum_120",
            "momentum_crash_risk",
        ],
        implementation_notes=[
            "Satellite rank must require positive absolute momentum before relative ranking.",
            (
                "Cap single-symbol weight so SOXL/TECL-style sleeves cannot dominate "
                "without confirmation."
            ),
        ],
    ),
    FactorDefinition(
        id="stress_only_defensive_sleeve",
        family="portfolio_construction",
        label="Stress-only defensive sleeve",
        description=(
            "Moves the non-risk sleeve to GLD/BIL/IEF only during failed trend, high "
            "volatility, or drawdown stress instead of keeping a large permanent defensive drag."
        ),
        inputs=["close", "risk_state", "portfolio_weights"],
        output="defensive_weight",
        default_parameter_space={
            "defensive_assets": [["GLD", "BIL"], ["GLD", "IEF", "SHY"]],
            "stress_scale": [0.60, 0.75, 0.85],
        },
        source_card_ids=[
            "vaa_breadth_momentum",
            "moreira_muir_volatility_management",
        ],
        implementation_notes=[
            "Only apply defensive substitution when stress conditions are explicit.",
            "Reject variants whose recent return improves only because risk exposure collapsed.",
        ],
    ),
    FactorDefinition(
        id="post_drawdown_reentry_state",
        family="recovery_regime",
        label="Post-drawdown re-entry state",
        description=(
            "Looks for a controlled re-entry after hard stress has cleared: market trend "
            "is valid, recent drawdown is no longer severe, recovery momentum is positive, "
            "and the leveraged sleeve is not already highly extended."
        ),
        inputs=["close", "drawdown_state", "recovery_momentum", "extension_state"],
        output="reentry_ok",
        default_parameter_space={
            "hard_drawdown_pct": [8.0, 10.0, 12.0],
            "recovery_lookback_days": [10],
            "min_recovery_pct": [4.0, 8.0, 12.0],
            "max_momentum60_pct": [20.0, 40.0, 60.0],
        },
        source_card_ids=[
            "short_term_reversal_jegadeesh_1990",
            "momentum_crash_risk",
            "leveraged_etf_reset_risk",
        ],
        implementation_notes=[
            "Use as a re-entry gate after stress clears, not as a standalone buy signal.",
            "Validate against current-OOS TQQQ buy-and-hold and crash windows separately.",
        ],
    ),
    FactorDefinition(
        id="overextension_mean_reversion_guard",
        family="risk_regime",
        label="Overextension mean-reversion guard",
        description=(
            "Treats very high intermediate leveraged-ETF momentum or SMA extension as "
            "overheating risk, because this dataset's time-series diagnostic shows weaker "
            "forward returns in the most extended TQQQ buckets."
        ),
        inputs=["close", "momentum_state", "extension_state"],
        output="overextended",
        default_parameter_space={
            "momentum60_max_pct": [20.0, 40.0, 60.0],
            "extension_sma50_pct": [25.0, 35.0, 45.0],
        },
        source_card_ids=[
            "short_term_reversal_jegadeesh_1990",
            "state_conditional_momentum_crash_risk",
        ],
        implementation_notes=[
            "Use to downshift from TQQQ to QLD/QQQ when extension is high.",
            "Do not interpret negative time-series IC as universal short alpha.",
        ],
    ),
    FactorDefinition(
        id="post_stress_cooldown_confirmation",
        family="recovery_regime",
        label="Post-stress cooldown confirmation",
        description=(
            "Requires a short confirmation period after hard drawdown or trend stress clears "
            "before returning to TQQQ, reducing whipsaw losses during noisy transition states."
        ),
        inputs=["close", "trend_state", "drawdown_state", "fast_momentum_state"],
        output="post_stress_confirmed",
        default_parameter_space={
            "cooldown_days": [0, 5, 10, 20],
            "cooldown_asset": [["QQQ"], ["QLD"], ["adaptive_qld_qqq"]],
            "confirmation_days": [0, 5],
        },
        source_card_ids=[
            "trend_filtering_methods_momentum",
            "momentum_turning_points_slow_fast",
            "time_series_momentum_volatility_states",
        ],
        implementation_notes=[
            "Use as a post-stress re-entry delay, not as a permanent defensive overlay.",
            "Keep gross exposure at 100% by rotating to QQQ/QLD during cooldown.",
        ],
    ),
    FactorDefinition(
        id="melt_up_peak_risk_guard",
        family="risk_regime",
        label="Melt-up peak risk guard",
        description=(
            "Downshifts from TQQQ to QLD when leveraged ETF intermediate momentum and "
            "SMA extension are both extreme, aiming to reduce losses after crowded melt-ups."
        ),
        inputs=["close", "momentum_state", "extension_state", "volatility_state"],
        output="melt_up_guard_active",
        default_parameter_space={
            "momentum60_min_pct": [40.0, 60.0],
            "extension_sma50_pct": [25.0, 35.0],
            "fallback_asset": [["QLD"]],
        },
        source_card_ids=[
            "short_term_reversal_jegadeesh_1990",
            "momentum_trading_predictable_crashes_nber",
            "time_series_momentum_volatility_states",
        ],
        implementation_notes=[
            "Only downshift; do not short or remove gross exposure.",
            (
                "Accept only if full-window drawdown improves without losing recent "
                "TQQQ-relative return."
            ),
        ],
    ),
    FactorDefinition(
        id="early_deterioration_downshift",
        family="risk_regime",
        label="Early deterioration downshift",
        description=(
            "Downshifts risk sleeves from TQQQ/QLD/high-beta assets to QQQ when leveraged "
            "ETF drawdown has started and intermediate momentum is no longer strong enough "
            "to justify staying in higher leverage."
        ),
        inputs=["close", "drawdown_state", "momentum_state", "trend_state"],
        output="early_deterioration_active",
        default_parameter_space={
            "tqqq_dd20_trigger_pct": [8.0, 9.0, 10.0],
            "momentum60_max_pct": [10.0, 15.0, 20.0, 25.0],
            "fallback_asset": [["QQQ"]],
        },
        source_card_ids=[
            "momentum_crash_risk",
            "momentum_trading_predictable_crashes_nber",
            "time_series_momentum_volatility_states",
        ],
        implementation_notes=[
            "This is an early downshift, not a hard-stress defensive allocation.",
            "Require local OOS proof because the trigger can easily become too conservative.",
        ],
    ),
    FactorDefinition(
        id="underlying_moving_average_leverage_gate",
        family="trend_momentum",
        label="Underlying moving-average leverage gate",
        description=(
            "Uses the unlevered Nasdaq proxy's long moving-average and momentum state to "
            "decide whether the router may hold 3x, 2x, or 1x exposure. The intent is to "
            "keep gross exposure near 100% while choosing the leverage level that is "
            "consistent with the underlying trend."
        ),
        inputs=["QQQ", "close", "trend_state", "momentum_state"],
        output="allowed_leverage_tier",
        default_parameter_space={
            "sma_days": [150, 200],
            "momentum_days": [120, 180],
            "risk_on_tiers": [["TQQQ", "QLD", "QQQ"]],
            "fallback_tier": [["QQQ"], ["GLD"]],
        },
        source_card_ids=[
            "faber_taa_trend_filter",
            "leveraged_etf_reset_risk",
        ],
        implementation_notes=[
            "Apply to the underlying QQQ state, not to TQQQ's leveraged price path alone.",
            "Treat this as leverage-tier selection, not a cash-allocation throttle.",
            "Reject variants that improve drawdown only by keeping risk-asset exposure too low.",
        ],
        risk_notes=[
            "Moving-average gates can lag fast crash gaps and miss early rebound days.",
        ],
    ),
    FactorDefinition(
        id="volatility_managed_leverage_state",
        family="risk_regime",
        label="Volatility-managed leverage state",
        description=(
            "Adapts volatility-managed portfolio research to full-gross ETF routing by "
            "switching from TQQQ to QLD/QQQ/GLD when realized volatility is elevated, "
            "rather than reducing gross exposure into idle cash."
        ),
        inputs=["QQQ", "TQQQ", "realized_volatility", "volatility_rank"],
        output="volatility_leverage_tier",
        default_parameter_space={
            "vol_window_days": [20, 60],
            "rank_window_days": [126, 252],
            "high_vol_rank": [0.65, 0.75, 0.85],
            "high_vol_fallback": [["QQQ"], ["QLD"], ["GLD"]],
        },
        source_card_ids=[
            "moreira_muir_volatility_management",
            "time_series_momentum_volatility_states",
        ],
        implementation_notes=[
            "Use volatility as a state input alongside trend and drawdown confirmation.",
            "Do not use proportional cash scaling for this product path.",
            "Stress-test overnight gap handling because volatility signals can react late.",
        ],
        risk_notes=[
            "Volatility-managed rules are parameter-sensitive and require walk-forward review.",
        ],
    ),
    FactorDefinition(
        id="momentum_crash_rebound_guard",
        family="recovery_regime",
        label="Momentum crash rebound guard",
        description=(
            "Blocks immediate high-leverage re-entry after high-volatility drawdowns until "
            "trend, breadth, and recovery momentum agree, addressing the common momentum "
            "crash pattern where previous winners underperform around sharp rebounds."
        ),
        inputs=["drawdown_state", "volatility_state", "breadth_state", "recovery_momentum"],
        output="rebound_guard_active",
        default_parameter_space={
            "drawdown_lookback_days": [20, 60],
            "max_drawdown_pct": [6.0, 8.0, 10.0],
            "min_recovery_days": [3, 5, 10],
            "required_breadth": [1, 2, 3],
        },
        source_card_ids=[
            "momentum_crash_risk",
            "state_conditional_momentum_crash_risk",
            "vaa_breadth_momentum",
        ],
        implementation_notes=[
            "Use as a temporary guard after stress, not as a permanent low-beta regime.",
            "Keep the portfolio fully allocated to QQQ/QLD/GLD while the guard is active.",
            "Evaluate contribution separately from the existing cooldown confirmation factor.",
        ],
        risk_notes=[
            (
                "Can become over-conservative in V-shaped recoveries; current-OOS return "
                "must be checked."
            ),
        ],
    ),
    FactorDefinition(
        id="overnight_intraday_return_split",
        family="execution_timing",
        label="Overnight/intraday return split",
        description=(
            "Separates prior close-to-open and open-to-close returns so daily open "
            "execution can distinguish overnight gap behavior from regular-session "
            "trend behavior."
        ),
        inputs=["open", "close"],
        output="overnight_intraday_state",
        default_parameter_space={
            "overnight_lookback_days": [1, 5, 20],
            "intraday_lookback_days": [1, 5, 20],
            "large_gap_pct": [1.0, 2.0, 3.0],
        },
        source_card_ids=[
            "post_drawdown_factor_overnight_intraday_split",
            "post_drawdown_nasdaq_opening_cross",
        ],
        implementation_notes=[
            "Use only prior-session open and close for next-open decisions.",
            (
                "Treat current-session opening gap as unavailable unless using a "
                "delayed-open workflow."
            ),
            "Evaluate separately from price momentum because it is an execution-timing factor.",
        ],
        risk_notes=[
            "Daily bars cannot validate delayed-open execution; intraday replay is required.",
        ],
    ),
    FactorDefinition(
        id="open_gap_delay_confirmation",
        family="execution_timing",
        label="Open-gap delayed confirmation",
        description=(
            "Flags large opening gaps and requires delayed-open confirmation before "
            "initiating or increasing high-leverage exposure."
        ),
        inputs=["official_open", "prior_close", "intraday_bars"],
        output="delayed_open_allowed",
        default_parameter_space={
            "gap_threshold_pct": [1.5, 2.5, 3.5],
            "confirmation_minutes": [5, 15, 30],
            "fallback_asset": [["QQQ"], ["QLD"], ["GLD"]],
        },
        source_card_ids=[
            "post_drawdown_factor_open_gap_delay_confirmation",
            "post_drawdown_nasdaq_opening_cross",
            "post_drawdown_alpaca_order_support",
        ],
        implementation_notes=[
            "Research-only until intraday bars and official-open reference prices are available.",
            "Use to compare next-open, 5-minute delayed, and 15-minute delayed execution.",
            (
                "Do not mark paper-ready without TCA fields for submitted_at, "
                "fill_price, and slippage."
            ),
        ],
        risk_notes=[
            "Can miss strong opening momentum; compare return loss against gap-risk reduction.",
        ],
    ),
    FactorDefinition(
        id="tqqq_delayed_entry_execution_overlay",
        family="execution_timing",
        label="TQQQ delayed-entry execution overlay",
        description=(
            "Uses intraday minute bars to delay TQQQ entry by a small number of minutes "
            "after the open while leaving non-TQQQ sleeves on the daily open model."
        ),
        inputs=["TQQQ_1m_bars", "daily_target_weights", "official_open"],
        output="delayed_entry_time_rule",
        default_parameter_space={
            "delay_minutes": [5, 15, 30],
            "covered_symbols": [["TQQQ"], ["TQQQ", "QLD"], ["TQQQ", "QLD", "SOXL"]],
            "fallback_time_rule": [["regular_session_open"]],
        },
        source_card_ids=[
            "post_drawdown_factor_open_gap_delay_confirmation",
            "post_drawdown_factor_overnight_intraday_split",
            "post_drawdown_alpaca_order_support",
        ],
        implementation_notes=[
            "Research-only until target-weight rows can carry per-symbol delayed-open time rules.",
            "Requires 1m data coverage for every symbol whose entry time is delayed.",
            "Compare against regular-session-open execution in the same current-OOS window.",
        ],
        risk_notes=[
            "Current evidence covers TQQQ only; portfolio-level delayed execution is incomplete.",
        ],
    ),
    FactorDefinition(
        id="transition_gld_momentum_overlay",
        family="defensive_transition",
        label="Transition GLD momentum overlay",
        description=(
            "During cooldown or post-stress confirmation states, replaces the base "
            "transition sleeve with GLD when GLD absolute momentum is positive."
        ),
        inputs=["router_state", "GLD_daily_bars", "prior_close"],
        output="transition_replacement_symbol",
        default_parameter_space={
            "scope": ["transition", "hard_and_transition"],
            "replacement_symbol": ["GLD", "QQQ"],
            "condition": ["replacement_mom_positive"],
            "lookback_days": [20, 60],
            "min_momentum_pct": [0.0, 5.0],
        },
        source_card_ids=[
            "transition_gld_time_series_momentum",
            "delayed30_offensive_finra_leveraged_etf_path_dependency",
        ],
        implementation_notes=[
            "Use only prior confirmed daily closes; do not inspect same-day GLD movement.",
            "Keep gross exposure at 100%; this changes the defensive sleeve, not cash usage.",
            "Evaluate against the unchanged transition sleeve and delayed-entry baseline.",
        ],
        risk_notes=[
            "Can overfit a short recent stress window; requires forensics and cross-source replay.",
            "Gold exposure can fail during liquidity shocks or real-rate repricing regimes.",
        ],
    ),
    FactorDefinition(
        id="transition_tqqq_momentum_overlay",
        family="offensive_transition",
        label="Transition TQQQ momentum overlay",
        description=(
            "During cooldown or post-stress confirmation states, replaces the base "
            "transition sleeve with TQQQ when TQQQ absolute momentum is positive."
        ),
        inputs=["router_state", "TQQQ_daily_bars", "prior_close"],
        output="transition_replacement_symbol",
        default_parameter_space={
            "scope": ["transition"],
            "replacement_symbol": ["TQQQ", "QLD"],
            "condition": ["replacement_mom_positive"],
            "lookback_days": [20],
            "min_momentum_pct": [0.0],
        },
        source_card_ids=[
            "transition_tqqq_time_series_momentum",
            "delayed30_offensive_finra_leveraged_etf_path_dependency",
        ],
        implementation_notes=[
            "Use only prior confirmed daily closes; do not inspect same-day TQQQ movement.",
            "Keep gross exposure at 100%; this changes the transition sleeve, not cash usage.",
            "Validate against TQQQ buy-and-hold by chronological folds before paper automation.",
        ],
        risk_notes=[
            "Can lag TQQQ in extreme melt-up windows if route state remains defensive too long.",
            "Increases leveraged ETF path-dependency risk compared with GLD or QQQ transitions.",
        ],
    ),
    FactorDefinition(
        id="first_half_hour_intraday_momentum_state",
        family="execution_timing",
        label="First-half-hour intraday momentum state",
        description=(
            "Uses the first 30 minutes after the open as a confirmation state for "
            "offensive-sleeve entries, so a delayed entry can distinguish opening "
            "price discovery from regular-session continuation."
        ),
        inputs=["minute_bars", "official_open", "first_30m_return"],
        output="first_half_hour_momentum_ok",
        default_parameter_space={
            "confirmation_minutes": [15, 30],
            "min_first_window_return_pct": [-0.5, 0.0, 0.5],
            "covered_symbols": [["TQQQ", "QLD", "SOXL", "USD"]],
        },
        source_card_ids=[
            "delayed30_offensive_first_half_hour_intraday_momentum",
            "delayed30_offensive_nasdaq_opening_cross",
        ],
        implementation_notes=[
            "Use only bars at or before the delayed decision timestamp.",
            "Evaluate against fixed-delay baselines before adding another decision gate.",
            "Keep gross exposure at 100%; change timing or sleeve, not cash usage.",
        ],
        risk_notes=[
            "Can overfit a short 1m sample; requires walk-forward execution validation.",
        ],
    ),
    FactorDefinition(
        id="first_half_hour_reversal_guard",
        family="execution_timing",
        label="First-half-hour reversal guard",
        description=(
            "Flags adverse first-half-hour reversal after a large overnight or open move, "
            "blocking immediate offensive-sleeve entries when opening price discovery "
            "fails to hold."
        ),
        inputs=["prior_close", "official_open", "minute_bars"],
        output="opening_reversal_active",
        default_parameter_space={
            "gap_threshold_pct": [1.0, 1.5, 2.5],
            "reversal_threshold_pct": [-0.5, -1.0],
            "fallback_time_rule": [["regular_session_open_plus_30m"]],
        },
        source_card_ids=[
            "delayed30_offensive_first_half_hour_reversal",
            "post_drawdown_factor_overnight_intraday_split",
        ],
        implementation_notes=[
            "Treat as an execution-risk guard, not a standalone short signal.",
            "Compare missed upside versus reduced drawdown and slippage stress.",
        ],
        risk_notes=[
            "Can miss V-shaped opening recoveries and requires TCA review.",
        ],
    ),
    FactorDefinition(
        id="opening_liquidity_stress_state",
        family="execution_timing",
        label="Opening liquidity stress state",
        description=(
            "Uses opening range volatility, spread proxy, volume availability, and gap "
            "size to decide whether regular-open execution, delayed-open execution, "
            "or limit-on-open observation is the right execution policy."
        ),
        inputs=["minute_bars", "official_open", "volume", "gap_state"],
        output="opening_liquidity_stress",
        default_parameter_space={
            "window_minutes": [5, 15, 30],
            "max_open_gap_pct": [1.5, 2.5, 3.5],
            "stress_action": [["delay"], ["limit_on_open_observe"]],
        },
        source_card_ids=[
            "delayed30_offensive_preopen_liquidity_first30",
            "delayed30_offensive_nasdaq_opening_cross",
            "delayed30_offensive_alpaca_order_support",
        ],
        implementation_notes=[
            "Research-only until broker order timestamps and fill quality can be recorded.",
            "Use as TCA policy selection before paper_auto, not as a hidden alpha source.",
        ],
        risk_notes=[
            "Broker paper fills may not reflect true opening liquidity.",
        ],
    ),
    FactorDefinition(
        id="overnight_first_half_hour_reversal_regime",
        family="execution_timing",
        label="Overnight/first-half-hour reversal regime",
        description=(
            "Combines prior close-to-open gap direction, first-half-hour return, and "
            "recent realized volatility to identify opening reversals that can make "
            "offensive leveraged ETF entries fragile."
        ),
        inputs=["prior_close", "official_open", "minute_bars", "realized_volatility"],
        output="opening_reversal_regime",
        default_parameter_space={
            "gap_threshold_pct": [1.0, 2.0],
            "confirmation_minutes": [15, 30],
            "vol_rank_threshold": [0.65, 0.80],
            "fallback_asset": [["QLD"], ["QQQ"]],
        },
        source_card_ids=[
            "delayed30_offensive_overnight_first_half_hour_reversal_regime",
            "post_drawdown_factor_overnight_intraday_split",
        ],
        implementation_notes=[
            "Use only prices observable by the delayed decision timestamp.",
            "Treat as a timing/regime state, not an independent long/short signal.",
            "Keep gross exposure at 100% by rotating the target sleeve when the regime is adverse.",
        ],
        risk_notes=[
            "Requires intraday replay and fold-level contribution; daily bars are insufficient.",
            "Can reduce participation in strong trend days that start with noisy opening reversal.",
        ],
    ),
    FactorDefinition(
        id="late_day_intraday_momentum_pressure",
        family="execution_timing",
        label="Late-day intraday momentum pressure",
        description=(
            "Measures last-window continuation pressure and leveraged-ETF rebalance "
            "context near the close, then carries it as a next-session execution and "
            "risk-state input for high-beta sleeves."
        ),
        inputs=["minute_bars", "close", "leveraged_etf_universe", "volume"],
        output="late_day_pressure_state",
        default_parameter_space={
            "window_minutes": [30, 60],
            "min_last_window_return_pct": [0.5, 1.0],
            "volume_rank_threshold": [0.65, 0.80],
            "allowed_actions": [["observe"], ["delay_next_entry"], ["downshift_next_entry"]],
        },
        source_card_ids=[
            "delayed30_offensive_late_day_intraday_momentum_pressure",
            "delayed30_offensive_finra_leveraged_etf_path_dependency",
        ],
        implementation_notes=[
            "Use as a next-session context feature after the bar is closed.",
            "Do not let it inspect next-day open or delayed-open prices.",
            "Evaluate separately from first-half-hour factors to avoid duplicate timing gates.",
        ],
        risk_notes=[
            "Late-day effects can be microstructure-sensitive and broker-feed dependent.",
            "Paper fills may not reproduce close-adjacent liquidity or rebalance pressure.",
        ],
    ),
    FactorDefinition(
        id="pre_fomc_event_window_state",
        family="event_calendar",
        label="Pre-FOMC event window state",
        description=(
            "Marks scheduled pre-FOMC windows for research-only participation and risk "
            "tests, based on documented pre-announcement equity index return effects."
        ),
        inputs=["pit_event_calendar", "session_date"],
        output="pre_fomc_window",
        default_parameter_space={
            "window_days_before": [1, 2, 3],
            "window_days_after": [0, 1],
            "allowed_actions": [["observe"], ["downshift"], ["participation_boost"]],
        },
        source_card_ids=["post_drawdown_factor_pre_fomc_drift"],
        implementation_notes=[
            "Requires a point-in-time FOMC calendar packet before promotion or paper readiness.",
            "Use as an event state input, not as a standalone buy signal.",
            "Validate single-modality baseline and missing-calendar robustness.",
        ],
        risk_notes=[
            "Calendar effects can decay; event leakage is a blocking risk without PIT timestamps.",
        ],
    ),
)


_TACTICAL_EXPRESSION_TEMPLATES: dict[str, str | None] = {
    "absolute_time_series_momentum_120": (
        "(close - lag(close, {lookback_days})) / lag(close, {lookback_days})"
    ),
    "cross_sectional_relative_momentum_120": (
        "(close - lag(close, {lookback_days})) / lag(close, {lookback_days})"
    ),
    "volatility_rank_20_252": "stddev(close, {vol_window_days}) / close",
    "drawdown_guard_20_60": (
        "(close - highest(close, {lookback_days})) / highest(close, {lookback_days})"
    ),
    "tech_canary_breadth": None,
    "semiconductor_leadership_confirmation": None,
    "defensive_asset_dual_momentum": (
        "(close - lag(close, {lookback_days})) / lag(close, {lookback_days})"
    ),
    "leveraged_etf_extension_guard": "(close - sma(close, {sma_days})) / sma(close, {sma_days})",
    "risk_on_recovery_boost": (
        "(close - lag(close, {recovery_lookback_days})) / lag(close, {recovery_lookback_days})"
    ),
    "strong_risk_on_state": "(close - lag(close, 60)) / lag(close, 60)",
    "core_beta_sleeve": None,
    "leadership_satellite_rank": (
        "(close - lag(close, {lookback_days})) / lag(close, {lookback_days})"
    ),
    "stress_only_defensive_sleeve": None,
    "post_drawdown_reentry_state": (
        "(close - lag(close, {recovery_lookback_days})) / lag(close, {recovery_lookback_days})"
    ),
    "overextension_mean_reversion_guard": "(close - sma(close, 50)) / sma(close, 50)",
    "post_stress_cooldown_confirmation": "(close - sma(close, 20)) / sma(close, 20)",
    "melt_up_peak_risk_guard": "(close - sma(close, 50)) / sma(close, 50)",
    "early_deterioration_downshift": "(close - highest(close, 20)) / highest(close, 20)",
    "underlying_moving_average_leverage_gate": (
        "(close - sma(close, {sma_days})) / sma(close, {sma_days})"
    ),
    "volatility_managed_leverage_state": "stddev(close, {vol_window_days}) / close",
    "momentum_crash_rebound_guard": "(close - highest(close, 20)) / highest(close, 20)",
    "overnight_intraday_return_split": "(open - lag(close, 1)) / lag(close, 1)",
    "open_gap_delay_confirmation": "(open - lag(close, 1)) / lag(close, 1)",
    "tqqq_delayed_entry_execution_overlay": None,
    "transition_gld_momentum_overlay": (
        "(close - lag(close, {lookback_days})) / lag(close, {lookback_days})"
    ),
    "transition_tqqq_momentum_overlay": (
        "(close - lag(close, {lookback_days})) / lag(close, {lookback_days})"
    ),
    "first_half_hour_intraday_momentum_state": None,
    "first_half_hour_reversal_guard": None,
    "opening_liquidity_stress_state": None,
    "overnight_first_half_hour_reversal_regime": None,
    "late_day_intraday_momentum_pressure": None,
    "pre_fomc_event_window_state": None,
}


TACTICAL_ROUTER_FACTOR_LIBRARY = tuple(
    replace(factor, expression=_TACTICAL_EXPRESSION_TEMPLATES.get(factor.id))
    for factor in TACTICAL_ROUTER_FACTOR_LIBRARY
)


# WorldQuant Alpha101 subset: single-symbol, no cross-sectional rank/neutralization.
ALPHA101_LIBRARY: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        id="alpha101_001_neg_delta_close_1d",
        family="momentum_short",
        label="Alpha101 #001 negative close delta",
        description="Negative close-to-close change as a short-term reversal proxy.",
        inputs=["close"],
        output="signed_return_pct",
        default_parameter_space={"lag_days": [1, 2, 3]},
        expression="-1 * (close - lag(close, {lag_days})) / lag(close, {lag_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_002_neg_roc_close_2d",
        family="momentum_short",
        label="Alpha101 short reversal 2-day",
        description="Negative two-day return for mean-reversion screening.",
        inputs=["close"],
        output="signed_return_pct",
        default_parameter_space={"lag_days": [2, 3, 5]},
        expression="-1 * (close - lag(close, {lag_days})) / lag(close, {lag_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_003_open_close_reversal",
        family="kline_shape",
        label="Alpha101 open-close reversal",
        description="Close below open produces positive reversal score.",
        inputs=["open", "close"],
        output="body_reversal_pct",
        default_parameter_space={},
        expression="-1 * (close - open) / open",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_004_high_close_pressure",
        family="kline_shape",
        label="Alpha101 high-close pressure",
        description="Distance from high to close normalized by close.",
        inputs=["high", "close"],
        output="upper_pressure_pct",
        default_parameter_space={},
        expression="(high - close) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_005_close_low_recovery",
        family="kline_shape",
        label="Alpha101 close-low recovery",
        description="Distance from close to low normalized by close.",
        inputs=["low", "close"],
        output="lower_recovery_pct",
        default_parameter_space={},
        expression="(close - low) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_006_volume_weighted_return_5d",
        family="volume_momentum",
        label="Alpha101 volume-weighted return",
        description="Five-day return scaled by volume relative to its moving average.",
        inputs=["close", "volume"],
        output="volume_weighted_return",
        default_parameter_space={"lookback_days": [5, 10, 20]},
        expression=(
            "((close - lag(close, {lookback_days})) / lag(close, {lookback_days})) "
            "* (volume / sma(volume, {lookback_days}))"
        ),
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_007_price_above_sma_10d",
        family="trend_momentum",
        label="Alpha101 price above SMA",
        description="Close location relative to a short moving average.",
        inputs=["close"],
        output="trend_score",
        default_parameter_space={"window_days": [10, 20, 50]},
        expression="(close - sma(close, {window_days})) / sma(close, {window_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_008_ema_trend_12d",
        family="trend_momentum",
        label="Alpha101 EMA trend",
        description="Close location relative to an exponential moving average.",
        inputs=["close"],
        output="trend_score",
        default_parameter_space={"window_days": [12, 26, 50]},
        expression="(close - ema(close, {window_days})) / ema(close, {window_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_009_roc_5d",
        family="trend_momentum",
        label="Alpha101 five-day ROC",
        description="Short time-series momentum over configurable lag.",
        inputs=["close"],
        output="return_pct",
        default_parameter_space={"lookback_days": [5, 10, 20]},
        expression="roc(close, {lookback_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_010_neg_roc_5d",
        family="momentum_short",
        label="Alpha101 negative five-day ROC",
        description="Inverted short-horizon return for reversal candidates.",
        inputs=["close"],
        output="signed_return_pct",
        default_parameter_space={"lookback_days": [5, 10, 20]},
        expression="-1 * roc(close, {lookback_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_011_close_to_20d_high",
        family="breakout_position",
        label="Alpha101 close to 20-day high",
        description="Close position relative to recent rolling high.",
        inputs=["close"],
        output="breakout_score",
        default_parameter_space={"window_days": [20, 55, 120]},
        expression="(close - highest(close, {window_days})) / highest(close, {window_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_012_close_to_20d_low",
        family="breakout_position",
        label="Alpha101 close to 20-day low",
        description="Close recovery from recent rolling low.",
        inputs=["close"],
        output="recovery_score",
        default_parameter_space={"window_days": [20, 55, 120]},
        expression="(close - lowest(close, {window_days})) / lowest(close, {window_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_013_range_compression_20d",
        family="volatility_rank",
        label="Alpha101 range compression",
        description="Daily range normalized by recent close volatility.",
        inputs=["high", "low", "close"],
        output="range_vol_ratio",
        default_parameter_space={"window_days": [20, 60]},
        expression="((high - low) / close) / (stddev(close, {window_days}) / close)",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_014_volatility_breakout_20d",
        family="volatility_rank",
        label="Alpha101 volatility breakout",
        description="Close deviation from SMA scaled by rolling volatility.",
        inputs=["close"],
        output="zscore",
        default_parameter_space={"window_days": [20, 60]},
        expression="zscore(close, {window_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_015_rsi_reversal_14d",
        family="momentum_short",
        label="Alpha101 RSI reversal",
        description="Inverted RSI displacement from neutral.",
        inputs=["close"],
        output="rsi_reversal_score",
        default_parameter_space={"window_days": [7, 14, 21]},
        expression="-1 * (rsi(close, {window_days}) - 50) / 50",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_016_rsi_momentum_14d",
        family="trend_momentum",
        label="Alpha101 RSI momentum",
        description="RSI displacement from neutral.",
        inputs=["close"],
        output="rsi_momentum_score",
        default_parameter_space={"window_days": [7, 14, 21]},
        expression="(rsi(close, {window_days}) - 50) / 50",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_017_macd_histogram",
        family="trend_momentum",
        label="Alpha101 MACD histogram",
        description="MACD histogram as a trend acceleration signal.",
        inputs=["close"],
        output="macd_histogram",
        default_parameter_space={"fast_days": [12], "slow_days": [26], "signal_days": [9]},
        expression="macd_hist(close, {fast_days}, {slow_days}, {signal_days}) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_018_bollinger_location_20d",
        family="volatility_rank",
        label="Alpha101 Bollinger location",
        description="Close relative to Bollinger midline.",
        inputs=["close"],
        output="bollinger_location",
        default_parameter_space={"window_days": [20, 60]},
        expression="(close - bollinger_mid(close, {window_days})) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_019_bollinger_upper_extension",
        family="volatility_rank",
        label="Alpha101 upper-band extension",
        description="Close extension above the Bollinger upper band.",
        inputs=["close"],
        output="upper_extension",
        default_parameter_space={"window_days": [20, 60]},
        expression="(close - bollinger_upper(close, {window_days})) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_020_bollinger_lower_recovery",
        family="momentum_short",
        label="Alpha101 lower-band recovery",
        description="Close recovery above the Bollinger lower band.",
        inputs=["close"],
        output="lower_recovery",
        default_parameter_space={"window_days": [20, 60]},
        expression="(close - bollinger_lower(close, {window_days})) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_021_atr_normalized_range",
        family="volatility_rank",
        label="Alpha101 ATR normalized",
        description="Average true range normalized by close.",
        inputs=["high", "low", "close"],
        output="atr_pct",
        default_parameter_space={"window_days": [14, 20]},
        expression="atr({window_days}) / close",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_022_volume_surge_20d",
        family="volume_momentum",
        label="Alpha101 volume surge",
        description="Volume relative to its moving average.",
        inputs=["volume"],
        output="volume_ratio",
        default_parameter_space={"window_days": [20, 60]},
        expression="volume / sma(volume, {window_days})",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_023_volume_surge_reversal",
        family="volume_momentum",
        label="Alpha101 volume-surge reversal",
        description="Negative return under elevated volume.",
        inputs=["close", "volume"],
        output="volume_reversal_score",
        default_parameter_space={"lookback_days": [1, 5], "volume_window_days": [20]},
        expression=(
            "-1 * ((close - lag(close, {lookback_days})) / lag(close, {lookback_days})) "
            "* (volume / sma(volume, {volume_window_days}))"
        ),
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_024_open_gap_reversal",
        family="overnight_gap",
        label="Alpha101 open-gap reversal",
        description="Inverted overnight gap.",
        inputs=["open", "close"],
        output="overnight_reversal_pct",
        default_parameter_space={},
        expression="-1 * (open - lag(close, 1)) / lag(close, 1)",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_025_intraday_return",
        family="execution_timing",
        label="Alpha101 intraday return",
        description="Open-to-close return.",
        inputs=["open", "close"],
        output="intraday_return_pct",
        default_parameter_space={},
        expression="(close - open) / open",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_026_neg_intraday_return",
        family="momentum_short",
        label="Alpha101 negative intraday return",
        description="Inverted open-to-close return.",
        inputs=["open", "close"],
        output="intraday_reversal_pct",
        default_parameter_space={},
        expression="-1 * (close - open) / open",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_027_close_lag_spread_10d",
        family="trend_momentum",
        label="Alpha101 close-lag spread",
        description="Close spread over lagged close.",
        inputs=["close"],
        output="return_pct",
        default_parameter_space={"lag_days": [10, 20, 60]},
        expression="(close / lag(close, {lag_days})) - 1",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_028_sma_slope_20d",
        family="trend_momentum",
        label="Alpha101 SMA slope",
        description="Moving-average slope normalized by prior moving average.",
        inputs=["close"],
        output="slope_pct",
        default_parameter_space={"window_days": [20, 50], "lag_days": [5, 10]},
        expression=(
            "(sma(close, {window_days}) - lag(sma(close, {window_days}), {lag_days})) "
            "/ lag(sma(close, {window_days}), {lag_days})"
        ),
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_029_vol_adjusted_momentum",
        family="trend_momentum",
        label="Alpha101 vol-adjusted momentum",
        description="Return divided by realized volatility.",
        inputs=["close"],
        output="vol_adjusted_return",
        default_parameter_space={"lookback_days": [20, 60]},
        expression="roc(close, {lookback_days}) / (stddev(close, {lookback_days}) / close)",
        source_card_ids=["kakushadze_101_alphas"],
    ),
    FactorDefinition(
        id="alpha101_030_vol_adjusted_reversal",
        family="momentum_short",
        label="Alpha101 vol-adjusted reversal",
        description="Inverted return divided by realized volatility.",
        inputs=["close"],
        output="vol_adjusted_reversal",
        default_parameter_space={"lookback_days": [5, 20]},
        expression="-1 * roc(close, {lookback_days}) / (stddev(close, {lookback_days}) / close)",
        source_card_ids=["kakushadze_101_alphas"],
    ),
)


# Qlib Alpha158 subset: K-line, overnight, price-position, and rolling OHLCV features.
ALPHA158_LIBRARY: tuple[FactorDefinition, ...] = (
    FactorDefinition(
        id="alpha158_kbar_body",
        family="kline_shape",
        label="Alpha158 K-bar body",
        description="Daily candle body normalized by open.",
        inputs=["open", "close"],
        output="body_pct",
        default_parameter_space={},
        expression="(close - open) / open",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_kbar_upper_shadow",
        family="kline_shape",
        label="Alpha158 upper shadow proxy",
        description="High-to-close distance normalized by open.",
        inputs=["open", "high", "close"],
        output="upper_shadow_pct",
        default_parameter_space={},
        expression="(high - close) / open",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_kbar_lower_shadow",
        family="kline_shape",
        label="Alpha158 lower shadow proxy",
        description="Close-to-low distance normalized by open.",
        inputs=["open", "low", "close"],
        output="lower_shadow_pct",
        default_parameter_space={},
        expression="(close - low) / open",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_kbar_high_low_range",
        family="kline_shape",
        label="Alpha158 high-low range",
        description="High-low range normalized by open.",
        inputs=["open", "high", "low"],
        output="range_pct",
        default_parameter_space={},
        expression="(high - low) / open",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_overnight_gap",
        family="overnight_gap",
        label="Alpha158 overnight gap",
        description="Open versus prior close.",
        inputs=["open", "close"],
        output="overnight_return_pct",
        default_parameter_space={},
        expression="(open - lag(close, 1)) / lag(close, 1)",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_overnight_gap_abs",
        family="overnight_gap",
        label="Alpha158 signed gap magnitude",
        description="Signed open gap normalized by prior close.",
        inputs=["open", "close"],
        output="gap_pct",
        default_parameter_space={},
        expression="(open / lag(close, 1)) - 1",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_intraday_return",
        family="execution_timing",
        label="Alpha158 intraday return",
        description="Open-to-close session return.",
        inputs=["open", "close"],
        output="intraday_return_pct",
        default_parameter_space={},
        expression="(close - open) / open",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_price_position_20d",
        family="position",
        label="Alpha158 price position",
        description="Close position in a rolling high-low range.",
        inputs=["close", "high", "low"],
        output="position_score",
        default_parameter_space={"window_days": [20, 60]},
        expression=(
            "(close - lowest(low, {window_days})) / "
            "(highest(high, {window_days}) - lowest(low, {window_days}))"
        ),
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_high_position_20d",
        family="position",
        label="Alpha158 high position",
        description="High position in a rolling high-low range.",
        inputs=["high", "low"],
        output="position_score",
        default_parameter_space={"window_days": [20, 60]},
        expression=(
            "(high - lowest(low, {window_days})) / "
            "(highest(high, {window_days}) - lowest(low, {window_days}))"
        ),
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_low_position_20d",
        family="position",
        label="Alpha158 low position",
        description="Low position in a rolling high-low range.",
        inputs=["high", "low"],
        output="position_score",
        default_parameter_space={"window_days": [20, 60]},
        expression=(
            "(low - lowest(low, {window_days})) / "
            "(highest(high, {window_days}) - lowest(low, {window_days}))"
        ),
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_close_sma_ratio_5d",
        family="trend_momentum",
        label="Alpha158 close/SMA ratio",
        description="Close relative to short moving average.",
        inputs=["close"],
        output="ma_ratio",
        default_parameter_space={"window_days": [5, 10, 20]},
        expression="close / sma(close, {window_days}) - 1",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_volume_sma_ratio_5d",
        family="volume_momentum",
        label="Alpha158 volume/SMA ratio",
        description="Volume relative to short moving average.",
        inputs=["volume"],
        output="volume_ratio",
        default_parameter_space={"window_days": [5, 10, 20]},
        expression="volume / sma(volume, {window_days}) - 1",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_return_1d",
        family="trend_momentum",
        label="Alpha158 one-day return",
        description="One-bar close return.",
        inputs=["close"],
        output="return_pct",
        default_parameter_space={"lag_days": [1, 2, 5]},
        expression="(close - lag(close, {lag_days})) / lag(close, {lag_days})",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_return_5d",
        family="trend_momentum",
        label="Alpha158 five-day return",
        description="Five-bar close return.",
        inputs=["close"],
        output="return_pct",
        default_parameter_space={"lag_days": [5, 10, 20]},
        expression="(close - lag(close, {lag_days})) / lag(close, {lag_days})",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_vwap_proxy_5d",
        family="volume_momentum",
        label="Alpha158 VWAP proxy momentum",
        description="Close momentum scaled by volume trend.",
        inputs=["close", "volume"],
        output="volume_weighted_momentum",
        default_parameter_space={"window_days": [5, 10]},
        expression=(
            "(close - sma(close, {window_days})) * volume / sma(volume, {window_days}) / close"
        ),
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_stddev_20d",
        family="volatility_rank",
        label="Alpha158 close volatility",
        description="Rolling close standard deviation normalized by close.",
        inputs=["close"],
        output="volatility_pct",
        default_parameter_space={"window_days": [20, 60]},
        expression="stddev(close, {window_days}) / close",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_zscore_20d",
        family="volatility_rank",
        label="Alpha158 close z-score",
        description="Rolling close z-score.",
        inputs=["close"],
        output="zscore",
        default_parameter_space={"window_days": [20, 60]},
        expression="zscore(close, {window_days})",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_high_close_ratio",
        family="kline_shape",
        label="Alpha158 high/close ratio",
        description="High extension above close.",
        inputs=["high", "close"],
        output="high_close_ratio",
        default_parameter_space={},
        expression="high / close - 1",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_low_close_ratio",
        family="kline_shape",
        label="Alpha158 low/close ratio",
        description="Close extension above low.",
        inputs=["low", "close"],
        output="low_close_ratio",
        default_parameter_space={},
        expression="close / low - 1",
        source_card_ids=["qlib_alpha158"],
    ),
    FactorDefinition(
        id="alpha158_close_open_ratio",
        family="kline_shape",
        label="Alpha158 close/open ratio",
        description="Close-to-open ratio minus one.",
        inputs=["open", "close"],
        output="close_open_ratio",
        default_parameter_space={},
        expression="close / open - 1",
        source_card_ids=["qlib_alpha158"],
    ),
)


ALL_FACTORS: tuple[FactorDefinition, ...] = (
    *TACTICAL_ROUTER_FACTOR_LIBRARY,
    *ALPHA101_LIBRARY,
    *ALPHA158_LIBRARY,
)
_FACTOR_INDEX: dict[str, FactorDefinition] = {factor.id: factor for factor in ALL_FACTORS}
if len(_FACTOR_INDEX) != len(ALL_FACTORS):
    _seen: set[str] = set()
    duplicates = []
    for _factor in ALL_FACTORS:
        if _factor.id in _seen:
            duplicates.append(_factor.id)
        _seen.add(_factor.id)
    raise ValueError("duplicate factor ids: " + ", ".join(sorted(set(duplicates))))


def get_factor(factor_id: str) -> FactorDefinition:
    try:
        return _FACTOR_INDEX[factor_id]
    except KeyError as exc:
        raise KeyError(f"unknown factor definition: {factor_id}") from exc


def list_factors(
    family: str | None = None,
    inputs: set[str] | None = None,
    expression_only: bool = False,
) -> list[FactorDefinition]:
    result = list(ALL_FACTORS)
    if family:
        result = [factor for factor in result if factor.family == family]
    if inputs:
        result = [factor for factor in result if set(factor.inputs).issubset(inputs)]
    if expression_only:
        result = [factor for factor in result if factor.expression]
    return result


def all_factor_definitions() -> list[FactorDefinition]:
    return list(ALL_FACTORS)


def factor_definition_ids() -> list[str]:
    return [item.id for item in ALL_FACTORS]


def get_factor_definition(factor_id: str) -> FactorDefinition:
    return get_factor(factor_id)


def factor_definitions_for_ids(factor_ids: list[str]) -> list[FactorDefinition]:
    return [get_factor_definition(factor_id) for factor_id in factor_ids]


def write_factor_library_artifact(
    *,
    strategy_name: str,
    factor_ids: list[str],
    root: Path | None = None,
    stem: str | None = None,
) -> tuple[Path, Path]:
    base = root or project_root()
    selected = factor_definitions_for_ids(factor_ids)
    output_stem = stem or f"{strategy_name}-factor-library"
    json_path = base / "reports" / "research" / f"{output_stem}.json"
    md_path = base / "reports" / "research" / f"{output_stem}.md"
    ensure_dir(json_path.parent)
    payload = {
        "strategy_name": strategy_name,
        "factor_count": len(selected),
        "factor_ids": [item.id for item in selected],
        "factors": [asdict(item) for item in selected],
    }
    write_json(json_path, payload)
    _write_markdown(md_path, payload)
    return json_path, md_path


def _write_markdown(path: Path, payload: dict[str, Any]) -> None:
    lines = [
        f"# Factor Library: {payload['strategy_name']}",
        "",
        f"- Factor count: `{payload['factor_count']}`",
        "",
        "| Factor | Family | Output | Parameter Space |",
        "|---|---|---|---|",
    ]
    for item in payload["factors"]:
        lines.append(
            f"| `{item['id']}` | {item['family']} | `{item['output']}` | "
            f"`{item['default_parameter_space']}` |"
        )
    lines.extend(["", "## Notes", ""])
    for item in payload["factors"]:
        lines.append(f"### `{item['id']}`")
        lines.append("")
        lines.append(item["description"])
        lines.append("")
        for note in item["implementation_notes"]:
            lines.append(f"- {note}")
        for note in item["risk_notes"]:
            lines.append(f"- Risk: {note}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
