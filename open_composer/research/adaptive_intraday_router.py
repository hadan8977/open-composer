from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import product
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import (
    data_feed,
    default_openai_model,
    ensure_dir,
    openai_api_key,
    openai_base_url,
    project_root,
    run_id,
)
from open_composer.context import build_signal_context
from open_composer.feature_packets import (
    FeaturePacketRow,
    write_context_feature_packet,
    write_feature_packet,
)
from open_composer.json_utils import json_safe_payload
from open_composer.models.event import EventRecord
from open_composer.models.signal import Signal, signal_id
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.reports.writer import write_scan_report
from open_composer.research.intraday_daily_rotation import (
    IntradayDailyMetrics,
    IntradayDailyParams,
    IntradayObjective,
    MarketGate,
    SelectionStyle,
    _alpha,
    _annualized_from_total,
    _assumptions,
    _build_params_grid,
    _buy_hold_return,
    _compound_return,
    _daily_sharpe,
    _day_bars,
    _IntradayDataset,
    _load_dataset,
    _max_drawdown_pct,
    _metric_lines,
    _objective_alpha,
    _objective_label,
    _quality_flags,
    _score_metrics,
    _selected_symbols,
    _split_for_oos,
    _symbol_intraday_return,
    _symbol_selection_stats,
    _win_pct,
)
from open_composer.research.metadata import (
    combined_data_profile,
    estimate_grid_research_cost,
    hypothesis_ledger,
    research_brief,
    runtime_payload,
    search_space,
)
from open_composer.storage import append_jsonl, write_json
from open_composer.strategy_versions import register_strategy_version

RouteFamily = Literal[
    "open_momentum",
    "open_reversal",
    "midday_momentum",
    "midday_reversal",
]


@dataclass(frozen=True)
class RoutedIntradaySubStrategy:
    family: RouteFamily
    params: IntradayDailyParams

    @property
    def label(self) -> str:
        return f"{self.family}:{self.params.label}"


@dataclass(frozen=True)
class AdaptiveRouterParams:
    sub_strategies: tuple[RoutedIntradaySubStrategy, ...]

    @property
    def label(self) -> str:
        return "__".join(item.label for item in self.sub_strategies)

    @property
    def max_lookback_days(self) -> int:
        return max(item.params.lookback_days for item in self.sub_strategies)


@dataclass(frozen=True)
class MarketScanState:
    open_return_pct: float
    prior_momentum_pct: float
    relative_volume: float
    family_order: tuple[RouteFamily, ...]
    note: str


@dataclass(frozen=True)
class AdaptiveRouterMetrics:
    base: IntradayDailyMetrics
    route_counts: dict[str, int]
    skipped_days: int


@dataclass(frozen=True)
class AdaptiveRouterCandidate:
    rank: int
    route: AdaptiveRouterParams
    score: float
    train: AdaptiveRouterMetrics
    out_of_sample: AdaptiveRouterMetrics
    full_window: AdaptiveRouterMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class _RouteDayResult:
    symbols: tuple[str, ...]
    strategy_return: float
    equal_weight_return: float
    benchmark_return: float


@dataclass(frozen=True)
class RoutedIntradaySignalPlan:
    symbol: str
    weight: float
    signal_timestamp: datetime
    entry_timestamp: datetime
    exit_timestamp: datetime
    signal_price: float
    entry_price: float
    exit_price: float
    expected_return: float
    conditions: list[str]


@dataclass(frozen=True)
class AdaptiveRouterScanResult:
    run_id: str
    spec_name: str
    route: AdaptiveRouterParams
    date: str
    scan_state: MarketScanState
    selected_sub_strategy: RoutedIntradaySubStrategy | None
    signal_plans: list[RoutedIntradaySignalPlan]
    signals: list[Signal]
    signal_log_path: Path
    report_path: Path
    json_path: Path
    feature_packet_path: Path | None
    context_packet_paths: list[Path]
    risk_policy: dict[str, Any]
    latest_prices: dict[str, float]
    notes: list[str]


@dataclass(frozen=True)
class _RouteBacktestContext:
    day_results: dict[str, list[_RouteDayResult | None]]
    scan_orders: dict[int, tuple[RouteFamily, ...]]


@dataclass(frozen=True)
class AdaptiveRouterWalkForwardSlice:
    fold: int
    route: AdaptiveRouterParams
    train: AdaptiveRouterMetrics
    test: AdaptiveRouterMetrics


@dataclass(frozen=True)
class AdaptiveRouterResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[AdaptiveRouterCandidate]
    walk_forward: list[AdaptiveRouterWalkForwardSlice]
    research_cost: dict[str, Any]
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> AdaptiveRouterCandidate:
        return self.candidates[0]


class LLMAdaptiveRouterChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    news_usage_plan: str
    expected_risks: list[str] = Field(default_factory=list)
    rejected_labels: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LLMAdaptiveRouterResearchResult:
    report_path: Path
    json_path: Path
    prompt_path: Path
    choice: LLMAdaptiveRouterChoice
    selected: AdaptiveRouterCandidate
    reviewed_candidates: list[AdaptiveRouterCandidate]
    status: Literal[
        "written",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
        "local_choice",
    ]


def run_adaptive_intraday_router_research(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "TQQQ",
    market_symbol: str = "QQQ",
    lookback_days: list[int] | None = None,
    entry_after_bars: list[int] | None = None,
    top_n_values: list[int] | None = None,
    min_opening_return_pct: list[float] | None = None,
    min_prior_momentum_pct: list[float] | None = None,
    min_relative_volume: list[float] | None = None,
    selection_styles: list[SelectionStyle] | None = None,
    max_opening_return_pct: list[float] | None = None,
    max_prior_momentum_pct: list[float] | None = None,
    market_gates: list[MarketGate] | None = None,
    objective: IntradayObjective = "equal_weight_alpha",
    out_of_sample_ratio: float = 0.3,
    validation_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    top_per_family: int = 3,
    max_route_candidates: int = 180,
    max_base_candidates: int = 720,
    refresh_data: bool = False,
) -> AdaptiveRouterResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    stage_started = perf_counter()
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        raise ValueError("adaptive intraday router requires at least two NASDAQ symbols")
    selected_feed = feed or spec.data.feed or data_feed()
    params_grid = _build_params_grid(
        lookback_days or [5, 10, 20],
        entry_after_bars or [1, 5, 15, 60],
        top_n_values or [1, 2],
        min_opening_return_pct or [0.0, 0.2],
        min_prior_momentum_pct or [0.0, 3.0],
        min_relative_volume or [0.8, 1.0],
        selection_styles or ["opening_momentum", "opening_reversal"],
        max_opening_return_pct,
        max_prior_momentum_pct,
        market_gates
        or [
            "none",
            "qqq_open_positive",
            "qqq_prior_negative",
            "qqq_open_positive_prior_negative",
        ],
        max_candidates=max_base_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started
    stage_started = perf_counter()
    dataset = _load_dataset(
        spec=spec,
        root=base,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    data_profile = combined_data_profile(dataset.profiles)
    stages["load_data"] = perf_counter() - stage_started
    stage_started = perf_counter()
    route_candidates = _build_route_candidates(
        spec=spec,
        dataset=dataset,
        params_grid=params_grid,
        objective=objective,
        out_of_sample_ratio=out_of_sample_ratio,
        top_per_family=top_per_family,
        max_route_candidates=max_route_candidates,
    )
    stages["build_routes"] = perf_counter() - stage_started
    stage_started = perf_counter()
    candidates = _evaluate_route_candidates(
        spec=spec,
        dataset=dataset,
        routes=route_candidates,
        out_of_sample_ratio=out_of_sample_ratio,
        validation_ratio=validation_ratio,
        objective=objective,
    )
    stages["evaluate_routes"] = perf_counter() - stage_started
    research_cost = estimate_grid_research_cost(
        candidate_count=len(params_grid),
        walk_forward_candidate_count=len(route_candidates),
        walk_forward_top_k=None,
        walk_forward_folds=walk_forward_folds,
    ).__dict__
    research_cost["route_candidate_count"] = len(route_candidates)
    stage_started = perf_counter()
    walk_forward = _walk_forward_routes(
        spec=spec,
        dataset=dataset,
        routes=route_candidates,
        folds=walk_forward_folds,
        objective=objective,
    )
    stages["walk_forward"] = perf_counter() - stage_started
    report_path = base / "reports" / "research" / f"{spec.name}-adaptive-intraday-router.md"
    json_path = base / "reports" / "research" / f"{spec.name}-adaptive-intraday-router.json"
    runtime_seconds = runtime_payload(started_at, stages)
    _write_router_json(
        json_path,
        spec,
        dataset,
        candidates,
        walk_forward,
        start,
        end,
        objective,
        research_cost,
        runtime_seconds,
        data_profile,
        params_grid,
    )
    _write_router_report(
        report_path,
        json_path,
        spec,
        dataset,
        candidates,
        walk_forward,
        start,
        end,
        objective,
        research_cost,
        runtime_seconds,
        data_profile,
    )
    return AdaptiveRouterResearchResult(
        report_path=report_path,
        json_path=json_path,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=runtime_seconds,
        data_profile=data_profile,
    )


def run_llm_adaptive_intraday_router_selection(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "TQQQ",
    market_symbol: str = "QQQ",
    lookback_days: list[int] | None = None,
    entry_after_bars: list[int] | None = None,
    top_n_values: list[int] | None = None,
    min_opening_return_pct: list[float] | None = None,
    min_prior_momentum_pct: list[float] | None = None,
    min_relative_volume: list[float] | None = None,
    selection_styles: list[SelectionStyle] | None = None,
    max_opening_return_pct: list[float] | None = None,
    max_prior_momentum_pct: list[float] | None = None,
    market_gates: list[MarketGate] | None = None,
    objective: IntradayObjective = "equal_weight_alpha",
    out_of_sample_ratio: float = 0.3,
    validation_ratio: float = 0.3,
    top_per_family: int = 3,
    max_route_candidates: int = 120,
    max_base_candidates: int = 720,
    refresh_data: bool = False,
    client: Any | None = None,
    model: str | None = None,
    local_choice_label: str | None = None,
) -> LLMAdaptiveRouterResearchResult:
    base = root or project_root()
    research = _router_research_for_llm(
        spec_path=spec_path,
        root=base,
        symbols=symbols,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        lookback_days=lookback_days,
        entry_after_bars=entry_after_bars,
        top_n_values=top_n_values,
        min_opening_return_pct=min_opening_return_pct,
        min_prior_momentum_pct=min_prior_momentum_pct,
        min_relative_volume=min_relative_volume,
        selection_styles=selection_styles,
        max_opening_return_pct=max_opening_return_pct,
        max_prior_momentum_pct=max_prior_momentum_pct,
        market_gates=market_gates,
        objective=objective,
        out_of_sample_ratio=out_of_sample_ratio,
        validation_ratio=validation_ratio,
        top_per_family=top_per_family,
        max_route_candidates=max_route_candidates,
        max_base_candidates=max_base_candidates,
        refresh_data=refresh_data,
    )
    spec = research["spec"]
    dataset = research["dataset"]
    reviewed: list[AdaptiveRouterCandidate] = research["reviewed"]
    prompt = json_safe_payload(_llm_router_prompt(spec, dataset, reviewed, objective))
    prompt_path = base / "reports" / "research" / f"{spec.name}-llm-adaptive-router-prompt.json"
    ensure_dir(prompt_path.parent)
    prompt_path.write_text(json.dumps(prompt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status: Literal[
        "written",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
        "local_choice",
    ] = "written"
    if local_choice_label:
        choice = _local_router_choice(reviewed, local_choice_label)
        status = "local_choice"
    elif client is None and not openai_api_key():
        choice = _deterministic_router_choice(reviewed)
        status = "fallback_no_api_key"
    else:
        try:
            choice = _call_llm_router_choice(
                client or _openai_client(),
                model or default_openai_model(),
                prompt,
            )
            labels = {item.route.label for item in reviewed}
            if choice.selected_label not in labels:
                choice = _deterministic_router_choice(reviewed)
                status = "fallback_invalid_choice"
        except Exception:
            choice = _deterministic_router_choice(reviewed)
            status = "fallback_api_error"
    selected = next(item for item in reviewed if item.route.label == choice.selected_label)
    report_path = base / "reports" / "research" / f"{spec.name}-llm-adaptive-router.md"
    json_path = base / "reports" / "research" / f"{spec.name}-llm-adaptive-router.json"
    _write_llm_router_json(
        json_path,
        spec,
        dataset,
        reviewed,
        choice,
        selected,
        status,
        prompt_path,
        objective,
    )
    _write_llm_router_report(
        report_path,
        json_path,
        prompt_path,
        spec,
        dataset,
        reviewed,
        choice,
        selected,
        status,
        objective,
    )
    return LLMAdaptiveRouterResearchResult(
        report_path=report_path,
        json_path=json_path,
        prompt_path=prompt_path,
        choice=choice,
        selected=selected,
        reviewed_candidates=reviewed,
        status=status,
    )


def run_adaptive_intraday_router_scan(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "TQQQ",
    market_symbol: str = "QQQ",
    route_label: str | None = None,
    scan_date: str | None = None,
    refresh_data: bool = False,
    emit_context_packets: bool = True,
    emit_news_packet: bool = True,
    news_lookback_hours: int = 72,
) -> AdaptiveRouterScanResult:
    """Write a latest/day scan, standard signal log, and replayable feature packets."""
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        raise ValueError("adaptive intraday router scan requires at least two NASDAQ symbols")
    selected_feed = feed or spec.data.feed or data_feed()
    route = _parse_route_label(route_label or spec.portfolio.selected_route_label)
    dataset = _load_dataset(
        spec=spec,
        root=base,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    index = _scan_index(dataset, scan_date)
    current_run_id = run_id(f"scan-{spec.name}-adaptive-router")
    version = register_strategy_version(spec_path, base, created_by="adaptive_router_scan")
    scan_state = _scan_market_state(dataset, index, route)
    selected = _route_selection(dataset, index, route)
    risk_policy = _portfolio_risk_policy(spec, route)
    latest_prices = _latest_prices(dataset, index)
    plans = (
        _signal_plans_for_selection(
            spec=spec,
            dataset=dataset,
            index=index,
            selection=selected,
            risk_policy=risk_policy,
        )
        if selected is not None
        else []
    )
    signals = [
        _signal_from_plan(
            spec=spec,
            run_id_value=current_run_id,
            plan=plan,
            version_id=version.version_id,
            spec_hash=version.content_hash,
        )
        for plan in plans
    ]
    signal_log_path = base / "signal_logs" / f"{current_run_id}.jsonl"
    report_path = base / "reports" / "scans" / f"{current_run_id}.md"
    json_path = base / "reports" / "scans" / f"{current_run_id}.json"
    feature_packet_path = (
        _write_router_news_feature_packets(
            spec=spec,
            root=base,
            signals=signals,
            lookback_hours=news_lookback_hours,
        )
        if emit_news_packet
        else None
    )
    append_jsonl(signal_log_path, signals)
    context_packet_paths: list[Path] = []
    if emit_context_packets:
        for signal in signals:
            build_signal_context(signal.id, base)
            context_packet_paths.append(write_context_feature_packet(signal.id, base))
    notes = _scan_notes(spec, dataset, signals, feature_packet_path)
    result = AdaptiveRouterScanResult(
        run_id=current_run_id,
        spec_name=spec.name,
        route=route,
        date=dataset.dates[index],
        scan_state=scan_state,
        selected_sub_strategy=selected[0] if selected is not None else None,
        signal_plans=plans,
        signals=signals,
        signal_log_path=signal_log_path,
        report_path=report_path,
        json_path=json_path,
        feature_packet_path=feature_packet_path,
        context_packet_paths=context_packet_paths,
        risk_policy=risk_policy,
        latest_prices=latest_prices,
        notes=notes,
    )
    _write_adaptive_scan_json(result, spec, dataset, version.version_id, version.content_hash)
    _write_adaptive_scan_report(result, spec, version.version_id, version.content_hash)
    return result


def _parse_route_label(label: str | None) -> AdaptiveRouterParams:
    if not label:
        raise ValueError(
            "adaptive router scan requires --route-label or portfolio.selected_route_label"
        )
    sub_strategies: list[RoutedIntradaySubStrategy] = []
    for raw_item in label.split("__"):
        if ":" not in raw_item:
            raise ValueError(f"invalid route segment: {raw_item}")
        raw_family, raw_params = raw_item.split(":", 1)
        family = _parse_route_family(raw_family)
        params = _parse_params_label(raw_params)
        sub_strategies.append(RoutedIntradaySubStrategy(family=family, params=params))
    if not sub_strategies:
        raise ValueError("route label did not contain any sub-strategies")
    return AdaptiveRouterParams(tuple(sub_strategies))


def _parse_route_family(value: str) -> RouteFamily:
    normalized = value.strip().lower()
    if normalized not in {
        "open_momentum",
        "open_reversal",
        "midday_momentum",
        "midday_reversal",
    }:
        raise ValueError(f"unsupported route family: {value}")
    return normalized  # type: ignore[return-value]


def _parse_params_label(label: str) -> IntradayDailyParams:
    parts = label.split("_")
    if len(parts) < 6:
        raise ValueError(f"invalid intraday params label: {label}")
    try:
        lookback_days = int(_strip_prefix(parts[0], "lb"))
        entry_after_bars = int(_strip_prefix(parts[1], "entry"))
        top_n = int(_strip_prefix(parts[2], "top"))
        min_opening_return_pct = float(_strip_prefix(parts[3], "open"))
        min_prior_momentum_pct = float(_strip_prefix(parts[4], "mom"))
        min_relative_volume = float(_strip_prefix(parts[5], "rv"))
    except ValueError as exc:
        raise ValueError(f"invalid numeric value in params label: {label}") from exc
    remainder = parts[6:]
    selection_style: SelectionStyle = "opening_momentum"
    max_opening_return_pct: float | None = None
    max_prior_momentum_pct: float | None = None
    if "reversal" in remainder:
        selection_style = "opening_reversal"
        marker_index = remainder.index("reversal")
        gate_parts = remainder[:marker_index]
        suffix = remainder[marker_index + 1 :]
        if len(suffix) != 2:
            raise ValueError(f"invalid reversal suffix in params label: {label}")
        max_opening_return_pct = _parse_optional_float(_strip_prefix(suffix[0], "maxopen"))
        max_prior_momentum_pct = _parse_optional_float(_strip_prefix(suffix[1], "maxmom"))
    else:
        gate_parts = remainder
    market_gate = _parse_market_gate("_".join(gate_parts) if gate_parts else "none")
    return IntradayDailyParams(
        selection_style=selection_style,
        lookback_days=lookback_days,
        entry_after_bars=entry_after_bars,
        top_n=top_n,
        min_opening_return_pct=min_opening_return_pct,
        min_prior_momentum_pct=min_prior_momentum_pct,
        min_relative_volume=min_relative_volume,
        max_opening_return_pct=max_opening_return_pct,
        max_prior_momentum_pct=max_prior_momentum_pct,
        market_gate=market_gate,
    )


def _strip_prefix(value: str, prefix: str) -> str:
    if not value.startswith(prefix):
        raise ValueError(f"{value!r} does not start with {prefix!r}")
    return value[len(prefix) :]


def _parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)


def _parse_market_gate(value: str) -> MarketGate:
    if value in {"", "none"}:
        return "none"
    if not value.startswith("q"):
        raise ValueError(f"invalid market gate label: {value}")
    gate = f"qqq_{value[1:]}"
    allowed: set[MarketGate] = {
        "none",
        "qqq_open_negative",
        "qqq_open_positive",
        "qqq_prior_negative",
        "qqq_prior_positive",
        "qqq_open_and_prior_positive",
        "qqq_open_positive_prior_negative",
    }
    if gate not in allowed:
        raise ValueError(f"unsupported market gate label: {value}")
    return gate  # type: ignore[return-value]


def _scan_index(dataset: _IntradayDataset, scan_date: str | None) -> int:
    if not dataset.dates:
        raise ValueError("dataset contains no common dates")
    if scan_date is None:
        return len(dataset.dates) - 1
    normalized = str(scan_date).strip()
    if normalized not in dataset.dates:
        raise ValueError(
            f"--scan-date {normalized} is not in the common session set "
            f"({dataset.dates[0]} -> {dataset.dates[-1]})"
        )
    return dataset.dates.index(normalized)


def _portfolio_risk_policy(spec: StrategySpec, route: AdaptiveRouterParams) -> dict[str, Any]:
    portfolio = spec.portfolio
    max_symbols = portfolio.max_symbols_per_day or spec.risk.max_trades_per_day
    max_symbol_weight = portfolio.max_symbol_weight or spec.risk.max_position_weight
    gross_limit = portfolio.gross_exposure_limit or min(1.0, max_symbols * max_symbol_weight)
    max_symbols = max(1, min(max_symbols, spec.risk.max_trades_per_day))
    max_symbol_weight = min(max_symbol_weight, spec.risk.max_position_weight, gross_limit)
    return {
        "mode": portfolio.mode,
        "route_label": route.label,
        "max_symbols_per_day": max_symbols,
        "gross_exposure_limit": gross_limit,
        "max_symbol_weight": max_symbol_weight,
        "same_day_flatten": portfolio.same_day_flatten,
        "duplicate_signal_policy": portfolio.duplicate_signal_policy,
        "long_only": True,
    }


def _signal_plans_for_selection(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    index: int,
    selection: tuple[RoutedIntradaySubStrategy, list[str]],
    risk_policy: dict[str, Any],
) -> list[RoutedIntradaySignalPlan]:
    sub_strategy, symbols = selection
    symbols = symbols[: int(risk_policy["max_symbols_per_day"])]
    if not symbols:
        return []
    per_symbol_weight = min(
        float(risk_policy["max_symbol_weight"]),
        float(risk_policy["gross_exposure_limit"]) / len(symbols),
    )
    plans: list[RoutedIntradaySignalPlan] = []
    for symbol in symbols:
        day = _day_bars(dataset, symbol, index)
        params = sub_strategy.params
        if day is None or day.bar_count <= params.entry_after_bars:
            continue
        signal_bar_index = params.entry_after_bars - 1
        entry_bar_index = params.entry_after_bars
        expected_return = _symbol_intraday_return(dataset, symbol, index, params, spec)
        if expected_return is None:
            continue
        plans.append(
            RoutedIntradaySignalPlan(
                symbol=symbol,
                weight=per_symbol_weight,
                signal_timestamp=day.timestamps[signal_bar_index],
                entry_timestamp=day.timestamps[entry_bar_index],
                exit_timestamp=day.timestamps[-1],
                signal_price=float(day.closes[signal_bar_index]),
                entry_price=float(day.opens[entry_bar_index]),
                exit_price=float(day.closes[-1]),
                expected_return=expected_return,
                conditions=[
                    "adaptive_intraday_internal_router",
                    f"route={sub_strategy.label}",
                    f"family={sub_strategy.family}",
                    f"weight={per_symbol_weight:.4f}",
                    "entry confirmed on bar close; fill assumption is next bar open",
                    "same-day flatten at final regular-session close",
                ],
            )
        )
    return plans


def _signal_from_plan(
    *,
    spec: StrategySpec,
    run_id_value: str,
    plan: RoutedIntradaySignalPlan,
    version_id: str,
    spec_hash: str,
) -> Signal:
    return Signal(
        id=signal_id(spec.name, plan.symbol, plan.signal_timestamp, "entry"),
        run_id=run_id_value,
        strategy_name=spec.name,
        strategy_id=spec.name,
        version_id=version_id,
        spec_hash=spec_hash,
        strategy_backend=spec.execution.backend,
        execution_backend="python_reference",
        symbol=plan.symbol,
        timeframe=spec.timeframe,
        timestamp=plan.signal_timestamp,
        action="entry",
        side="buy",
        source="adaptive_router_scan",
        price=plan.signal_price,
        conditions=plan.conditions,
        lifecycle=spec.lifecycle,
        execution_mode=spec.execution.mode,
        fill_assumption=spec.execution.fill_assumption,
    )


def _write_router_news_feature_packets(
    *,
    spec: StrategySpec,
    root: Path,
    signals: list[Signal],
    lookback_hours: int,
) -> Path | None:
    if not signals:
        return None
    path = _news_feature_packet_path(spec, root)
    events = _load_replayable_news_events(root)
    wrote_any = False
    for signal in signals:
        packet = _build_router_news_packet(signal, events, lookback_hours)
        if _jsonl_has_dedupe_key(path, packet.dedupe_key):
            continue
        write_feature_packet(path, packet)
        wrote_any = True
    return path if wrote_any or path.exists() else None


def _news_feature_packet_path(spec: StrategySpec, root: Path) -> Path:
    factor = spec.factors.get("news_sentiment_gate")
    path_value = factor.path if factor is not None else None
    if path_value:
        path = Path(path_value)
        return path if path.is_absolute() else root / path
    return root / "feature_logs" / f"{spec.name}_news_features.jsonl"


def _build_router_news_packet(
    signal: Signal,
    events: list[EventRecord],
    lookback_hours: int,
) -> FeaturePacketRow:
    eligible = _eligible_news_events(signal, events, lookback_hours)
    payload = [
        {
            "source": event.source,
            "symbol": event.symbol,
            "published_at": event.published_at.isoformat(),
            "fetched_at": event.fetched_at.isoformat(),
            "sentiment": event.sentiment,
            "relevance_score": event.relevance_score,
            "dedupe_key": event.dedupe_key,
            "title": event.title,
        }
        for event in eligible
    ]
    sentiment_score = _news_sentiment_score(eligible)
    latest_published = max((event.published_at for event in eligible), default=signal.timestamp)
    latest_fetched = max((event.fetched_at for event in eligible), default=signal.timestamp)
    visible_at = max(latest_published, latest_fetched)
    if visible_at > signal.timestamp:
        visible_at = signal.timestamp
    return FeaturePacketRow(
        timestamp=signal.timestamp,
        published_at=latest_published,
        fetched_at=latest_fetched,
        visible_at=visible_at,
        source="adaptive_router_news_packet",
        symbol=signal.symbol,
        dedupe_key=f"adaptive_router_news:{signal.id}",
        schema_version="1",
        summary=(
            f"Replayable news packet for {signal.id}; "
            f"{len(eligible)} eligible trial/free news records."
        ),
        sentiment=_score_to_sentiment(sentiment_score),
        model="deterministic_news_router_v1",
        input_hash=_hash_payload(payload),
        prompt_hash=_hash_payload({"template": "adaptive_router_news_packet_v1"}),
        features={
            "sentiment_score": sentiment_score,
            "news_count": len(eligible),
            "positive_news_count": sum(event.sentiment == "positive" for event in eligible),
            "negative_news_count": sum(event.sentiment == "negative" for event in eligible),
            "neutral_news_count": sum(event.sentiment == "neutral" for event in eligible),
            "max_relevance": max((event.relevance_score for event in eligible), default=0.0),
            "trial_news_only": True,
            "missing_news": not bool(eligible),
        },
    )


def _eligible_news_events(
    signal: Signal,
    events: list[EventRecord],
    lookback_hours: int,
) -> list[EventRecord]:
    lower_bound = signal.timestamp.timestamp() - lookback_hours * 3600
    allowed_symbols = {signal.symbol, "QQQ", "SPY"}
    selected: list[EventRecord] = []
    for event in events:
        published = (
            event.published_at
            if event.published_at.tzinfo
            else event.published_at.replace(tzinfo=UTC)
        )
        fetched = (
            event.fetched_at if event.fetched_at.tzinfo else event.fetched_at.replace(tzinfo=UTC)
        )
        visible_at = max(published, fetched)
        if event.symbol not in allowed_symbols:
            continue
        if visible_at > signal.timestamp:
            continue
        if visible_at.timestamp() < lower_bound:
            continue
        if event.source not in {"alpha_vantage", "gdelt"} and not event.event_type.endswith("news"):
            continue
        selected.append(event)
    selected.sort(key=lambda item: (item.relevance_score, item.published_at), reverse=True)
    return selected[:10]


def _load_replayable_news_events(root: Path) -> list[EventRecord]:
    paths: list[Path] = []
    raw_root = root / "data" / "raw" / "events"
    if raw_root.exists():
        paths.extend(sorted(raw_root.rglob("*.jsonl")))
    for relative in [
        "data/fixtures/capabilities/alpha_vantage_news.jsonl",
        "data/fixtures/capabilities/gdelt_news.jsonl",
    ]:
        fixture_path = root / relative
        if fixture_path.exists():
            paths.append(fixture_path)
    records: list[EventRecord] = []
    for path in paths:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(EventRecord.model_validate(json.loads(line)))
    return _dedupe_events(records)


def _dedupe_events(records: list[EventRecord]) -> list[EventRecord]:
    output: list[EventRecord] = []
    seen: set[str] = set()
    for record in sorted(records, key=lambda item: item.published_at):
        if record.dedupe_key in seen:
            continue
        seen.add(record.dedupe_key)
        output.append(record)
    return output


def _news_sentiment_score(events: list[EventRecord]) -> float:
    if not events:
        return 0.0
    score = 0.0
    total_weight = 0.0
    for event in events:
        direction = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}.get(
            event.sentiment,
            0.0,
        )
        weight = max(event.relevance_score, 0.1)
        score += direction * weight
        total_weight += weight
    return score / total_weight if total_weight > 0 else 0.0


def _score_to_sentiment(score: float) -> Literal["positive", "neutral", "negative", "unknown"]:
    if score > 0.15:
        return "positive"
    if score < -0.15:
        return "negative"
    return "neutral"


def _hash_payload(payload: Any) -> str:
    encoded = json.dumps(json_safe_payload(payload), sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _jsonl_has_dedupe_key(path: Path, dedupe_key: str) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(raw, dict) and raw.get("dedupe_key") == dedupe_key:
                return True
    return False


def _scan_notes(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    signals: list[Signal],
    feature_packet_path: Path | None,
) -> list[str]:
    notes = [
        "Adaptive router scan uses one StrategySpec with internal sub-strategies.",
        "Signals are confirmed on bar close and assume next-bar-open fills.",
        "Positions are intended to flatten at the regular-session close.",
        f"Data provider caveat: {dataset.profiles[0].get('provider', spec.data.source)} "
        f"{dataset.profiles[0].get('feed') or spec.data.feed or 'unknown feed'} "
        "is research evidence unless promotion gates pass.",
    ]
    if not signals:
        notes.append("No route produced an eligible signal for this scan date.")
    if feature_packet_path is None:
        notes.append("No news feature packet was written because no signal was emitted.")
    else:
        notes.append(
            "News feature packet is replayable but uses trial/free sources; it is not "
            "independent paper-ready Alpha without marginal-lift evidence."
        )
    return notes


def _write_adaptive_scan_json(
    result: AdaptiveRouterScanResult,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    version_id: str,
    spec_hash: str,
) -> Path:
    payload = {
        "run_id": result.run_id,
        "strategy_name": spec.name,
        "strategy_id": spec.name,
        "version_id": version_id,
        "spec_hash": spec_hash,
        "mode": "adaptive_intraday_router_scan",
        "date": result.date,
        "universe": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "route": {
            "label": result.route.label,
            "sub_strategies": [
                {"family": item.family, "label": item.label, "params": item.params.__dict__}
                for item in result.route.sub_strategies
            ],
        },
        "scan_state": result.scan_state.__dict__,
        "selected_sub_strategy": (
            {
                "family": result.selected_sub_strategy.family,
                "label": result.selected_sub_strategy.label,
                "params": result.selected_sub_strategy.params.__dict__,
            }
            if result.selected_sub_strategy is not None
            else None
        ),
        "risk_policy": result.risk_policy,
        "latest_prices": result.latest_prices,
        "signals": [signal.model_dump(mode="json") for signal in result.signals],
        "signal_plans": [plan.__dict__ for plan in result.signal_plans],
        "signal_log_path": _relpath(result.signal_log_path, result.json_path.parents[2]),
        "feature_packet_path": (
            _relpath(result.feature_packet_path, result.json_path.parents[2])
            if result.feature_packet_path
            else None
        ),
        "context_packet_paths": [
            _relpath(path, result.json_path.parents[2]) for path in result.context_packet_paths
        ],
        "notes": result.notes,
    }
    return write_json(result.json_path, payload)


def _write_adaptive_scan_report(
    result: AdaptiveRouterScanResult,
    spec: StrategySpec,
    version_id: str,
    spec_hash: str,
) -> Path:
    write_scan_report(
        result.report_path,
        result.run_id,
        spec,
        result.signals,
        version_id=version_id,
        spec_hash=spec_hash,
        execution_backend="python_reference",
        root=result.report_path.parents[2],
    )
    lines = result.report_path.read_text(encoding="utf-8").rstrip().splitlines()
    news_feature_path = (
        _relpath(result.feature_packet_path, result.report_path.parents[2])
        if result.feature_packet_path
        else "none"
    )
    lines.extend(
        [
            "",
            "## Adaptive Router",
            "",
            f"- Date: `{result.date}`",
            f"- Route: `{result.route.label}`",
            f"- Selected internal route: "
            f"`{result.selected_sub_strategy.label if result.selected_sub_strategy else 'none'}`",
            f"- Market scan: `{result.scan_state.note}`",
            f"- Family order: `{result.scan_state.family_order}`",
            f"- Risk policy: `{result.risk_policy}`",
            f"- Signal log: `{_relpath(result.signal_log_path, result.report_path.parents[2])}`",
            f"- JSON artifact: `{_relpath(result.json_path, result.report_path.parents[2])}`",
            f"- News feature packet: `{news_feature_path}`",
            "",
            "## Portfolio Targets",
            "",
        ]
    )
    if not result.signal_plans:
        lines.append("- No eligible targets.")
    for plan in result.signal_plans:
        lines.extend(
            [
                f"- `{plan.symbol}` weight=`{plan.weight:.4f}` "
                f"signal=`{plan.signal_timestamp.isoformat()}` "
                f"entry=`{plan.entry_timestamp.isoformat()}` "
                f"exit=`{plan.exit_timestamp.isoformat()}` "
                f"signal_price=`{plan.signal_price:.4f}` "
                f"expected_return=`{plan.expected_return * 100:.2f}%`",
            ]
        )
    lines.extend(["", "## Notes", "", *[f"- {note}" for note in result.notes]])
    result.report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result.report_path


def _latest_prices(dataset: _IntradayDataset, index: int) -> dict[str, float]:
    prices: dict[str, float] = {}
    for symbol in [*dataset.symbols, dataset.benchmark_symbol, dataset.market_symbol]:
        day = _day_bars(dataset, symbol, index)
        if day is None or day.bar_count == 0:
            continue
        price = float(day.closes[-1])
        if price > 0:
            prices[symbol] = price
    return prices


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _build_route_candidates(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params_grid: list[IntradayDailyParams],
    objective: IntradayObjective,
    out_of_sample_ratio: float,
    top_per_family: int,
    max_route_candidates: int,
) -> list[AdaptiveRouterParams]:
    split = _split_for_oos(len(dataset.dates), out_of_sample_ratio, params_grid)
    groups: dict[RouteFamily, list[tuple[float, RoutedIntradaySubStrategy]]] = {
        "open_momentum": [],
        "open_reversal": [],
        "midday_momentum": [],
        "midday_reversal": [],
    }
    metric_cache: dict[tuple[str, int], IntradayDailyMetrics] = {}
    for params in params_grid:
        family = _route_family(params)
        metrics = metric_cache.setdefault(
            (params.label, split),
            _backtest_params_base(spec, dataset, params, end_index=split),
        )
        groups[family].append(
            (_score_metrics(metrics, objective), RoutedIntradaySubStrategy(family, params))
        )
    top: dict[RouteFamily, list[RoutedIntradaySubStrategy]] = {}
    for family, rows in groups.items():
        rows.sort(key=lambda item: item[0], reverse=True)
        top[family] = [item for _, item in rows[:top_per_family]]
    routes: list[AdaptiveRouterParams] = []
    routes.extend(AdaptiveRouterParams((item,)) for item in _flatten(top.values()))
    for left_family, right_family in [
        ("open_momentum", "open_reversal"),
        ("open_reversal", "open_momentum"),
        ("open_momentum", "midday_momentum"),
        ("open_reversal", "midday_momentum"),
        ("open_momentum", "midday_reversal"),
        ("open_reversal", "midday_reversal"),
    ]:
        for left, right in product(top[left_family], top[right_family]):
            routes.append(_ordered_route([left, right]))
    for first, second, third in product(
        top["open_momentum"],
        top["open_reversal"],
        [*top["midday_momentum"], *top["midday_reversal"]],
    ):
        routes.append(_ordered_route([first, second, third]))
    unique: dict[str, AdaptiveRouterParams] = {}
    for route in routes:
        unique.setdefault(route.label, route)
    scored_routes = [(_route_training_score(route, groups), route) for route in unique.values()]
    scored_routes.sort(key=lambda item: item[0], reverse=True)
    return [route for _, route in scored_routes[:max_route_candidates]]


def _route_training_score(
    route: AdaptiveRouterParams,
    groups: dict[RouteFamily, list[tuple[float, RoutedIntradaySubStrategy]]],
) -> float:
    scores: dict[str, float] = {}
    for rows in groups.values():
        for score, sub_strategy in rows:
            scores[sub_strategy.label] = score
    return sum(scores.get(item.label, -100.0) for item in route.sub_strategies) / len(
        route.sub_strategies
    )


def _flatten(values: Any) -> list[RoutedIntradaySubStrategy]:
    output: list[RoutedIntradaySubStrategy] = []
    for group in values:
        output.extend(group)
    return output


def _ordered_route(items: list[RoutedIntradaySubStrategy]) -> AdaptiveRouterParams:
    deduped = {item.label: item for item in items}
    ordered = sorted(
        deduped.values(),
        key=lambda item: (item.params.entry_after_bars, _family_priority(item.family)),
    )
    return AdaptiveRouterParams(tuple(ordered))


def _family_priority(family: RouteFamily) -> int:
    return {
        "open_reversal": 0,
        "open_momentum": 1,
        "midday_reversal": 2,
        "midday_momentum": 3,
    }[family]


def _route_family(params: IntradayDailyParams) -> RouteFamily:
    is_midday = params.entry_after_bars >= 30
    if params.selection_style == "opening_reversal":
        return "midday_reversal" if is_midday else "open_reversal"
    return "midday_momentum" if is_midday else "open_momentum"


def _backtest_params_base(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params: IntradayDailyParams,
    *,
    end_index: int,
) -> IntradayDailyMetrics:
    from open_composer.research.intraday_daily_rotation import _backtest_params

    return _backtest_params(
        spec,
        dataset,
        params,
        start_index=params.lookback_days,
        end_index=end_index,
    )


def _evaluate_route_candidates(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    routes: list[AdaptiveRouterParams],
    out_of_sample_ratio: float,
    validation_ratio: float,
    objective: IntradayObjective,
) -> list[AdaptiveRouterCandidate]:
    split = _split_for_routes(len(dataset.dates), out_of_sample_ratio, routes)
    validation_start = max(
        max(item.max_lookback_days for item in routes) + 10,
        int(split * (1 - validation_ratio)),
    )
    context = _build_route_context(spec, dataset, routes)
    rows: list[AdaptiveRouterCandidate] = []
    for route in routes:
        train_for_score = _backtest_route(
            spec,
            dataset,
            route,
            context=context,
            start_index=route.max_lookback_days,
            end_index=validation_start,
        )
        validation = _backtest_route(
            spec,
            dataset,
            route,
            context=context,
            start_index=validation_start,
            end_index=split,
        )
        train = _backtest_route(
            spec,
            dataset,
            route,
            context=context,
            start_index=route.max_lookback_days,
            end_index=split,
        )
        oos = _backtest_route(
            spec,
            dataset,
            route,
            context=context,
            start_index=split,
            end_index=len(dataset.dates),
        )
        full = _backtest_route(
            spec,
            dataset,
            route,
            context=context,
            start_index=route.max_lookback_days,
            end_index=len(dataset.dates),
        )
        flags = _quality_flags(oos.base, full.base)
        rows.append(
            AdaptiveRouterCandidate(
                rank=0,
                route=route,
                score=_router_selection_score(
                    train_for_score,
                    validation,
                    full,
                    objective,
                ),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=flags,
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        AdaptiveRouterCandidate(
            rank=index,
            route=item.route,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            quality_flags=item.quality_flags,
        )
        for index, item in enumerate(rows, start=1)
    ]


def _walk_forward_routes(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    routes: list[AdaptiveRouterParams],
    folds: int,
    objective: IntradayObjective,
) -> list[AdaptiveRouterWalkForwardSlice]:
    max_lookback = max(item.max_lookback_days for item in routes)
    fold_size = max((len(dataset.dates) - max_lookback) // (max(folds, 1) + 1), 5)
    context = _build_route_context(spec, dataset, routes)
    rows: list[AdaptiveRouterWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.dates), test_start + fold_size)
        if test_end - test_start < 5:
            continue
        scored = [
            (
                _score_metrics(
                    _backtest_route(
                        spec,
                        dataset,
                        route,
                        context=context,
                        start_index=max_lookback,
                        end_index=test_start,
                    ).base,
                    objective,
                ),
                route,
            )
            for route in routes
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        rows.append(
            AdaptiveRouterWalkForwardSlice(
                fold=fold,
                route=selected,
                train=_backtest_route(
                    spec,
                    dataset,
                    selected,
                    context=context,
                    start_index=max_lookback,
                    end_index=test_start,
                ),
                test=_backtest_route(
                    spec,
                    dataset,
                    selected,
                    context=context,
                    start_index=test_start,
                    end_index=test_end,
                ),
            )
        )
    return rows


def _backtest_route(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    route: AdaptiveRouterParams,
    *,
    context: _RouteBacktestContext | None = None,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
) -> AdaptiveRouterMetrics:
    context = context or _build_route_context(spec, dataset, [route])
    start_index = max(route.max_lookback_days, start_index)
    end_index = min(end_index, len(dataset.dates))
    strategy_returns: list[float] = []
    selected_counts: list[int] = []
    equal_weight_returns: list[float] = []
    benchmark_intraday_returns: list[float] = []
    equity_curve = [start_equity]
    equity = start_equity
    route_counts = {item.label: 0 for item in route.sub_strategies}
    skipped_days = 0
    round_trips = 0
    traded_days = 0
    for index in range(start_index, end_index):
        selected = _route_day_result(context, index, route)
        if selected is None:
            result = None
            skipped_days += 1
        else:
            sub_strategy, result = selected
            if result.symbols:
                route_counts[sub_strategy.label] += 1
                traded_days += 1
                round_trips += len(result.symbols)
        strategy_return = result.strategy_return if result is not None else 0.0
        selected_count = len(result.symbols) if result is not None else 0
        selected_counts.append(selected_count)
        strategy_returns.append(strategy_return)
        if result is None:
            equal_weight_returns.append(0.0)
            benchmark_intraday_returns.append(0.0)
        else:
            equal_weight_returns.append(result.equal_weight_return)
            benchmark_intraday_returns.append(result.benchmark_return)
        equity *= 1 + strategy_return
        equity_curve.append(equity)
    period_dates = dataset.dates[start_index:end_index]
    total_return_pct = (equity / start_equity - 1) * 100
    equal_weight_total = _compound_return(equal_weight_returns)
    benchmark_intraday_total = _compound_return(benchmark_intraday_returns)
    benchmark_buy_hold = _buy_hold_return(dataset, dataset.benchmark_symbol, start_index, end_index)
    universe_buy_holds = {
        symbol: _buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.symbols
    }
    best_symbol = (
        max(universe_buy_holds, key=universe_buy_holds.get) if universe_buy_holds else None
    )
    best_return = universe_buy_holds[best_symbol] if best_symbol else 0.0
    annualized = _annualized_from_total(total_return_pct, len(strategy_returns))
    equal_weight_annualized = _annualized_from_total(equal_weight_total, len(equal_weight_returns))
    benchmark_intraday_annualized = _annualized_from_total(
        benchmark_intraday_total,
        len(benchmark_intraday_returns),
    )
    benchmark_buy_hold_annualized = _annualized_from_total(
        benchmark_buy_hold,
        len(strategy_returns),
    )
    base = IntradayDailyMetrics(
        days=len(strategy_returns),
        start_date=period_dates[0] if period_dates else None,
        end_date=period_dates[-1] if period_dates else None,
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
        sharpe_ratio=_daily_sharpe(strategy_returns),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        traded_days=traded_days,
        round_trips=round_trips,
        average_selected_count=mean(selected_counts) if selected_counts else 0.0,
        win_day_pct=_win_pct(strategy_returns),
        equal_weight_intraday_return_pct=equal_weight_total,
        equal_weight_intraday_annualized_pct=equal_weight_annualized,
        alpha_vs_equal_weight_annualized_pct=_alpha(annualized, equal_weight_annualized),
        benchmark_symbol=dataset.benchmark_symbol,
        benchmark_intraday_return_pct=benchmark_intraday_total,
        benchmark_intraday_annualized_pct=benchmark_intraday_annualized,
        alpha_vs_benchmark_intraday_annualized_pct=_alpha(
            annualized,
            benchmark_intraday_annualized,
        ),
        benchmark_buy_hold_return_pct=benchmark_buy_hold,
        benchmark_buy_hold_annualized_pct=benchmark_buy_hold_annualized,
        alpha_vs_benchmark_buy_hold_annualized_pct=_alpha(
            annualized,
            benchmark_buy_hold_annualized,
        ),
        universe_equal_weight_buy_hold_pct=mean(universe_buy_holds.values())
        if universe_buy_holds
        else 0.0,
        best_symbol_buy_hold_pct=best_return,
        best_symbol=best_symbol,
        alpha_vs_best_symbol_buy_hold_pct=total_return_pct - best_return,
    )
    return AdaptiveRouterMetrics(base=base, route_counts=route_counts, skipped_days=skipped_days)


def _build_route_context(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    routes: list[AdaptiveRouterParams],
) -> _RouteBacktestContext:
    sub_strategies: dict[str, RoutedIntradaySubStrategy] = {}
    for route in routes:
        for sub_strategy in route.sub_strategies:
            sub_strategies[sub_strategy.label] = sub_strategy
    day_results: dict[str, list[_RouteDayResult | None]] = {}
    for label, sub_strategy in sub_strategies.items():
        rows: list[_RouteDayResult | None] = []
        for index in range(len(dataset.dates)):
            rows.append(_sub_strategy_day_result(spec, dataset, sub_strategy, index))
        day_results[label] = rows
    scan_orders = {
        index: _scan_market_state(dataset, index, routes[0]).family_order
        for index in range(len(dataset.dates))
    }
    return _RouteBacktestContext(day_results=day_results, scan_orders=scan_orders)


def _sub_strategy_day_result(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    sub_strategy: RoutedIntradaySubStrategy,
    index: int,
) -> _RouteDayResult | None:
    symbols = tuple(_selected_symbols(dataset, index, sub_strategy.params))
    if not symbols:
        return None
    strategy_returns = [
        _symbol_intraday_return(dataset, symbol, index, sub_strategy.params, spec)
        for symbol in symbols
    ]
    strategy_returns = [value for value in strategy_returns if value is not None]
    if not strategy_returns:
        return None
    universe_returns = [
        _symbol_intraday_return(dataset, symbol, index, sub_strategy.params, spec)
        for symbol in dataset.symbols
    ]
    universe_returns = [value for value in universe_returns if value is not None]
    benchmark_return = _symbol_intraday_return(
        dataset,
        dataset.benchmark_symbol,
        index,
        sub_strategy.params,
        spec,
    )
    return _RouteDayResult(
        symbols=symbols,
        strategy_return=mean(strategy_returns),
        equal_weight_return=mean(universe_returns) if universe_returns else 0.0,
        benchmark_return=benchmark_return or 0.0,
    )


def _route_day_result(
    context: _RouteBacktestContext,
    index: int,
    route: AdaptiveRouterParams,
) -> tuple[RoutedIntradaySubStrategy, _RouteDayResult] | None:
    by_family: dict[RouteFamily, list[RoutedIntradaySubStrategy]] = {}
    for sub_strategy in route.sub_strategies:
        by_family.setdefault(sub_strategy.family, []).append(sub_strategy)
    for family in context.scan_orders.get(index, ()):
        for sub_strategy in sorted(
            by_family.get(family, []),
            key=lambda item: (item.params.entry_after_bars, item.params.lookback_days),
        ):
            result = context.day_results[sub_strategy.label][index]
            if result is not None:
                return sub_strategy, result
    for sub_strategy in sorted(
        route.sub_strategies,
        key=lambda item: (item.params.entry_after_bars, _family_priority(item.family)),
    ):
        result = context.day_results[sub_strategy.label][index]
        if result is not None:
            return sub_strategy, result
    return None


def _route_selection(
    dataset: _IntradayDataset,
    index: int,
    route: AdaptiveRouterParams,
) -> tuple[RoutedIntradaySubStrategy, list[str]] | None:
    scan = _scan_market_state(dataset, index, route)
    by_family: dict[RouteFamily, list[RoutedIntradaySubStrategy]] = {}
    for sub_strategy in route.sub_strategies:
        by_family.setdefault(sub_strategy.family, []).append(sub_strategy)
    for family in scan.family_order:
        for sub_strategy in sorted(
            by_family.get(family, []),
            key=lambda item: (item.params.entry_after_bars, item.params.lookback_days),
        ):
            symbols = _selected_symbols(dataset, index, sub_strategy.params)
            if symbols:
                return sub_strategy, symbols
    for sub_strategy in sorted(
        route.sub_strategies,
        key=lambda item: (item.params.entry_after_bars, _family_priority(item.family)),
    ):
        symbols = _selected_symbols(dataset, index, sub_strategy.params)
        if symbols:
            return sub_strategy, symbols
    return None


def _scan_market_state(
    dataset: _IntradayDataset,
    index: int,
    route: AdaptiveRouterParams,
) -> MarketScanState:
    market_day = _day_bars(dataset, dataset.market_symbol, index)
    if market_day is None:
        return MarketScanState(
            open_return_pct=0.0,
            prior_momentum_pct=0.0,
            relative_volume=0.0,
            family_order=("open_reversal", "open_momentum", "midday_reversal", "midday_momentum"),
            note="market scan unavailable; using conservative reversal-first ordering",
        )
    scan_after_bars = min(15, max(1, market_day.bar_count - 1))
    scan_anchor = route.sub_strategies[0].params
    scan_params = IntradayDailyParams(
        selection_style="opening_momentum",
        lookback_days=scan_anchor.lookback_days,
        entry_after_bars=max(1, scan_after_bars),
        top_n=1,
        min_opening_return_pct=0.0,
        min_prior_momentum_pct=0.0,
        min_relative_volume=0.0,
        market_gate="none",
    )
    stats = _symbol_selection_stats(dataset, dataset.market_symbol, index, scan_params)
    if stats is None:
        return MarketScanState(
            open_return_pct=0.0,
            prior_momentum_pct=0.0,
            relative_volume=0.0,
            family_order=("open_reversal", "open_momentum", "midday_reversal", "midday_momentum"),
            note="market scan lacked enough bars; using conservative ordering",
        )
    open_return_pct, prior_momentum_pct, relative_volume = stats
    family_order = _family_order_from_scan(
        open_return_pct=open_return_pct,
        prior_momentum_pct=prior_momentum_pct,
        relative_volume=relative_volume,
    )
    note = (
        f"QQQ scan open_return={open_return_pct:.2f}% prior_momentum="
        f"{prior_momentum_pct:.2f}% rel_volume={relative_volume:.2f}"
    )
    return MarketScanState(
        open_return_pct=open_return_pct,
        prior_momentum_pct=prior_momentum_pct,
        relative_volume=relative_volume,
        family_order=family_order,
        note=note,
    )


def _family_order_from_scan(
    *,
    open_return_pct: float,
    prior_momentum_pct: float,
    relative_volume: float,
) -> tuple[RouteFamily, ...]:
    momentum_first = relative_volume >= 1.0 or open_return_pct >= 0.15 or prior_momentum_pct >= 2.0
    reversal_first = relative_volume < 0.95 or open_return_pct <= -0.15 or prior_momentum_pct < 0
    if open_return_pct >= 0 and prior_momentum_pct >= 0:
        return (
            ("open_momentum", "midday_momentum", "open_reversal", "midday_reversal")
            if momentum_first
            else ("open_momentum", "open_reversal", "midday_momentum", "midday_reversal")
        )
    if open_return_pct < 0 and prior_momentum_pct < 0:
        return (
            ("open_reversal", "midday_reversal", "open_momentum", "midday_momentum")
            if reversal_first
            else ("open_reversal", "open_momentum", "midday_reversal", "midday_momentum")
        )
    if open_return_pct >= 0 and prior_momentum_pct < 0:
        return (
            ("open_reversal", "open_momentum", "midday_reversal", "midday_momentum")
            if reversal_first
            else ("open_momentum", "open_reversal", "midday_reversal", "midday_momentum")
        )
    return (
        ("midday_momentum", "open_momentum", "open_reversal", "midday_reversal")
        if momentum_first
        else ("open_reversal", "midday_reversal", "open_momentum", "midday_momentum")
    )


def _split_for_routes(frame_len: int, ratio: float, routes: list[AdaptiveRouterParams]) -> int:
    max_lookback = max(item.max_lookback_days for item in routes)
    split = int(frame_len * (1 - ratio))
    split = max(split, max_lookback + 10)
    return min(split, frame_len - 5)


def _route_diversity_bonus(metrics: AdaptiveRouterMetrics) -> float:
    used = sum(count > 0 for count in metrics.route_counts.values())
    return min(used, 3) * 1.5


def _router_selection_score(
    train: AdaptiveRouterMetrics,
    validation: AdaptiveRouterMetrics,
    full: AdaptiveRouterMetrics,
    objective: IntradayObjective,
) -> float:
    train_alpha = _objective_alpha(train.base, objective) or -100.0
    validation_alpha = _objective_alpha(validation.base, objective) or -100.0
    validation_sharpe = validation.base.sharpe_ratio or 0.0
    validation_drawdown = abs(min(validation.base.max_drawdown_pct, 0.0))
    consistency_penalty = abs(train_alpha - validation_alpha) * 0.25
    sparse_penalty = max(0, 30 - validation.base.traded_days) * 0.8
    return (
        min(train_alpha, validation_alpha) * 0.35
        + validation_alpha * 0.75
        + validation_sharpe * 10.0
        + _route_diversity_bonus(full)
        - validation_drawdown * 0.45
        - consistency_penalty
        - sparse_penalty
    )


def _acceptance_gate(
    candidate: AdaptiveRouterCandidate,
    walk_forward: list[AdaptiveRouterWalkForwardSlice],
    objective: IntradayObjective,
) -> dict[str, Any]:
    objective_alpha = _objective_alpha(candidate.out_of_sample.base, objective)
    wf_alphas = [_objective_alpha(item.test.base, objective) for item in walk_forward]
    positive_wf = sum((value or -1.0) > 0 for value in wf_alphas)
    fold_count = len(wf_alphas)
    passed = (
        (objective_alpha or -1.0) > 0
        and (candidate.out_of_sample.base.sharpe_ratio or 0.0) >= 0.7
        and candidate.out_of_sample.base.traded_days >= 30
        and candidate.out_of_sample.base.max_drawdown_pct > -20
        and fold_count > 0
        and positive_wf == fold_count
    )
    return {
        "passed": passed,
        "objective": objective,
        "oos_objective_alpha_annualized_pct": objective_alpha,
        "oos_sharpe_ratio": candidate.out_of_sample.base.sharpe_ratio,
        "oos_traded_days": candidate.out_of_sample.base.traded_days,
        "oos_max_drawdown_pct": candidate.out_of_sample.base.max_drawdown_pct,
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": fold_count,
        "quality_flags": candidate.quality_flags,
    }


def _pass_status(
    candidate: AdaptiveRouterCandidate,
    objective: IntradayObjective,
    *,
    llm_contribution_ok: bool = False,
    walk_forward: list[AdaptiveRouterWalkForwardSlice] | None = None,
) -> dict[str, Any]:
    oos_objective_alpha = _objective_alpha(candidate.out_of_sample.base, objective) or -100.0
    wf_alphas = [
        _objective_alpha(item.test.base, objective) or -100.0 for item in (walk_forward or [])
    ]
    research_pass = (
        oos_objective_alpha > 0
        and (candidate.out_of_sample.base.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.full_window.base.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.base.sharpe_ratio or 0.0) >= 0.7
        and candidate.out_of_sample.base.traded_days >= 30
        and bool(wf_alphas)
        and all(value > 0 for value in wf_alphas)
    )
    blockers = [
        "draft/manual_signal strategy only",
        "Alpaca IEX is not consolidated SIP data",
        "no broker paper-readiness activation or data-source comparison",
        "news/LLM route influence is advisory until replayed from PIT feature packets",
    ]
    return {
        "workflow_pass": True,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_ok,
        "paper_ready_pass": False,
        "paper_ready_blockers": blockers,
    }


def _write_router_json(
    path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    candidates: list[AdaptiveRouterCandidate],
    walk_forward: list[AdaptiveRouterWalkForwardSlice],
    start: str | None,
    end: str | None,
    objective: IntradayObjective,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
    params_grid: list[IntradayDailyParams],
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "mode": "adaptive_intraday_internal_router",
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "research_window": {"start": start, "end": end},
        "data_profile": data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective=_objective_label(objective),
            hypothesis=(
                "A single intraday strategy with internal market scanning and route selection "
                "can adapt between opening momentum, opening reversal, and midday continuation "
                "without external strategy calls."
            ),
            constraints=_assumptions(spec, dataset),
        ),
        "search_space": search_space(
            family="adaptive_intraday_internal_router",
            candidate_count=research_cost["route_candidate_count"],
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "long-only",
                "same-day exit",
                "one internal route per day",
                "confirmed bars only before each route entry",
            ],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis="Internal strategy routing improves OOS objective Alpha.",
            visible_evidence=["training score", "OOS metrics", "walk-forward folds"],
            hidden_evidence=[],
            counterevidence=candidates[0].quality_flags,
            conclusion="passed"
            if _acceptance_gate(candidates[0], walk_forward, objective)["passed"]
            else "failed",
        ),
        "selection_objective": _objective_label(objective),
        "research_cost": research_cost,
        "runtime_seconds": runtime_seconds,
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward, objective),
        "pass_status": _pass_status(candidates[0], objective, walk_forward=walk_forward),
        "assumptions": _assumptions(spec, dataset),
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_payload(item) for item in walk_forward],
    }
    return write_json(path, payload)


def _write_router_report(
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    candidates: list[AdaptiveRouterCandidate],
    walk_forward: list[AdaptiveRouterWalkForwardSlice],
    start: str | None,
    end: str | None,
    objective: IntradayObjective,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Adaptive Intraday Router Research: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Symbols: {', '.join(dataset.symbols)}",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Market scanner symbol: `{dataset.market_symbol}`",
        f"- Benchmark symbol: `{dataset.benchmark_symbol}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Data source/feed: `{data_profile.get('provider') or 'mixed'}` / "
        f"`{data_profile.get('feed') or 'mixed'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'mixed'}`",
        "- Router shape: one StrategySpec, multiple internal sub-strategies, first eligible "
        "route per day.",
        "- LLM/news usage: advisory route review unless PIT feature packets are available.",
        "- Point-in-time: each internal route uses confirmed bars only before that route entry.",
        f"- Selection objective: {_objective_label(objective)}",
        "",
        "## Assumptions",
        "",
        *[f"- {item}" for item in _assumptions(spec, dataset)],
        "",
        "## Research Cost",
        "",
        f"- Base candidates evaluated for route building: `{research_cost['candidate_count']}`",
        f"- Route candidates evaluated: `{research_cost['route_candidate_count']}`",
        f"- Estimated backtest passes: `{research_cost['estimated_total_backtest_passes']}`",
        f"- Runtime total seconds: `{runtime_seconds['total']:.2f}`",
        "",
        "## Acceptance Gate",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _acceptance_gate(candidates[0], walk_forward, objective).items()
        ],
        "",
        "## Pass Labels",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _pass_status(
                candidates[0],
                objective,
                walk_forward=walk_forward,
            ).items()
        ],
        "",
        "## Top Routed Candidates",
        "",
    ]
    for item in candidates[:10]:
        flags = ", ".join(item.quality_flags) if item.quality_flags else "none"
        lines.extend(
            [
                f"### Rank {item.rank}",
                "",
                f"- Route: `{item.route.label}`",
                f"- Score: `{item.score:.2f}`",
                f"- Route usage full window: `{item.full_window.route_counts}`",
                f"- Skipped days full window: `{item.full_window.skipped_days}`",
                f"- Quality flags: `{flags}`",
                *_metric_lines("Train", item.train.base),
                *_metric_lines("Out of sample", item.out_of_sample.base),
                *_metric_lines("Full window", item.full_window.base),
                "",
            ]
        )
    lines.extend(["## Walk Forward", ""])
    if not walk_forward:
        lines.append("- No walk-forward folds were available.")
    for item in walk_forward:
        lines.extend(
            [
                f"### Fold {item.fold}",
                "",
                f"- Route: `{item.route.label}`",
                f"- Test route usage: `{item.test.route_counts}`",
                *_metric_lines("Train selected", item.train.base),
                *_metric_lines("Test", item.test.base),
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation Notes",
            "",
            "- This is not a front-layer dispatcher; the route list is part of one strategy's "
            "internal decision structure.",
            "- The router trades at most one internal route per day and exits same day.",
            "- Complexity is penalized unless route diversity improves OOS and walk-forward "
            "evidence.",
            "- Trial news capabilities are not counted as independent Alpha until replayable "
            "feature packets with visible_at, published_at, source, input hash, and prompt hash "
            "exist.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _router_research_for_llm(
    *,
    spec_path: Path,
    root: Path,
    symbols: list[str] | None,
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    benchmark_symbol: str,
    market_symbol: str,
    lookback_days: list[int] | None,
    entry_after_bars: list[int] | None,
    top_n_values: list[int] | None,
    min_opening_return_pct: list[float] | None,
    min_prior_momentum_pct: list[float] | None,
    min_relative_volume: list[float] | None,
    selection_styles: list[SelectionStyle] | None,
    max_opening_return_pct: list[float] | None,
    max_prior_momentum_pct: list[float] | None,
    market_gates: list[MarketGate] | None,
    objective: IntradayObjective,
    out_of_sample_ratio: float,
    validation_ratio: float,
    top_per_family: int,
    max_route_candidates: int,
    max_base_candidates: int,
    refresh_data: bool,
) -> dict[str, Any]:
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    selected_feed = feed or spec.data.feed or data_feed()
    params_grid = _build_params_grid(
        lookback_days or [5, 10, 20],
        entry_after_bars or [1, 5, 15, 60],
        top_n_values or [1, 2],
        min_opening_return_pct or [0.0, 0.2],
        min_prior_momentum_pct or [0.0, 3.0],
        min_relative_volume or [0.8, 1.0],
        selection_styles or ["opening_momentum", "opening_reversal"],
        max_opening_return_pct,
        max_prior_momentum_pct,
        market_gates or ["none", "qqq_open_positive", "qqq_prior_negative"],
        max_candidates=max_base_candidates,
    )
    dataset = _load_dataset(
        spec=spec,
        root=root,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        benchmark_symbol=benchmark_symbol,
        market_symbol=market_symbol,
        refresh_data=refresh_data,
    )
    routes = _build_route_candidates(
        spec=spec,
        dataset=dataset,
        params_grid=params_grid,
        objective=objective,
        out_of_sample_ratio=out_of_sample_ratio,
        top_per_family=top_per_family,
        max_route_candidates=max_route_candidates,
    )
    train_end = _split_for_routes(len(dataset.dates), out_of_sample_ratio, routes)
    validation_start = max(
        max(item.max_lookback_days for item in routes) + 10,
        int(train_end * (1 - validation_ratio)),
    )
    reviewed: list[AdaptiveRouterCandidate] = []
    for route in routes:
        train = _backtest_route(
            spec,
            dataset,
            route,
            start_index=route.max_lookback_days,
            end_index=validation_start,
        )
        validation = _backtest_route(
            spec,
            dataset,
            route,
            start_index=validation_start,
            end_index=train_end,
        )
        final_oos = _backtest_route(
            spec,
            dataset,
            route,
            start_index=train_end,
            end_index=len(dataset.dates),
        )
        full = _backtest_route(
            spec,
            dataset,
            route,
            start_index=route.max_lookback_days,
            end_index=len(dataset.dates),
        )
        score = (
            _score_metrics(train.base, objective) * 0.35
            + _score_metrics(validation.base, objective) * 0.65
            + _route_diversity_bonus(full)
        )
        reviewed.append(
            AdaptiveRouterCandidate(
                rank=0,
                route=route,
                score=score,
                train=train,
                out_of_sample=final_oos,
                full_window=full,
                quality_flags=_quality_flags(final_oos.base, full.base),
            )
        )
    reviewed.sort(key=lambda item: item.score, reverse=True)
    reviewed = [
        AdaptiveRouterCandidate(
            rank=index,
            route=item.route,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            quality_flags=item.quality_flags,
        )
        for index, item in enumerate(reviewed, start=1)
    ]
    return {"spec": spec, "dataset": dataset, "reviewed": reviewed}


def _llm_router_prompt(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    reviewed: list[AdaptiveRouterCandidate],
    objective: IntradayObjective,
    limit: int = 18,
) -> dict[str, Any]:
    return {
        "task": "Select one internal-router candidate from training and validation evidence.",
        "strategy_name": spec.name,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "available_evidence": "training and internal validation route summaries only",
        "hidden_from_model": "final out-of-sample and full-window metrics are not shown",
        "selection_objective": _objective_label(objective),
        "news_capability_policy": [
            "news.alpha_vantage and news.gdelt are trial capabilities.",
            "News can justify route downweighting only after PIT feature packets exist.",
            "Do not treat narrative fit as independent Alpha in this prompt.",
        ],
        "anti_leakage_rules": [
            "Prefer validation stability over training score.",
            "Penalize sparse trading and single-route overfitting.",
            "Do not infer final OOS performance.",
            "Do not call external strategies; all route labels are internal sub-strategies.",
        ],
        "candidates": [_llm_candidate_payload(item, objective) for item in reviewed[:limit]],
    }


def _call_llm_router_choice(
    client: Any,
    model: str,
    prompt: dict[str, Any],
) -> LLMAdaptiveRouterChoice:
    messages = [
        {
            "role": "system",
            "content": (
                "You select an internal route candidate from prompt-visible trading research "
                "evidence. Return schema-valid JSON and do not claim paper readiness."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(json_safe_payload(prompt), indent=2, sort_keys=True),
        },
    ]
    try:
        response = client.responses.parse(
            model=model,
            input=messages,
            text_format=LLMAdaptiveRouterChoice,
        )
        parsed = _extract_router_choice(response)
        if parsed is not None:
            return parsed
    except TypeError:
        response = client.responses.create(
            model=model,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "llm_adaptive_router_choice",
                    "strict": True,
                    "schema": LLMAdaptiveRouterChoice.model_json_schema(),
                }
            },
        )
        return LLMAdaptiveRouterChoice.model_validate_json(response.output_text)
    raise ValueError("LLM returned no schema-valid adaptive router choice")


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key(), base_url=openai_base_url())


def _extract_router_choice(response: Any) -> LLMAdaptiveRouterChoice | None:
    for output in getattr(response, "output", []):
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", []):
            parsed = getattr(item, "parsed", None)
            if isinstance(parsed, LLMAdaptiveRouterChoice):
                return parsed
            if isinstance(parsed, dict):
                return LLMAdaptiveRouterChoice.model_validate(parsed)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, LLMAdaptiveRouterChoice):
        return parsed
    if isinstance(parsed, dict):
        return LLMAdaptiveRouterChoice.model_validate(parsed)
    return None


def _deterministic_router_choice(
    reviewed: list[AdaptiveRouterCandidate],
) -> LLMAdaptiveRouterChoice:
    selected = reviewed[0]
    return LLMAdaptiveRouterChoice(
        selected_label=selected.route.label,
        confidence=0.0,
        rationale="Fallback selected the highest prompt-visible route score.",
        news_usage_plan="No LLM/news contribution; deterministic fallback only.",
        expected_risks=["No usable LLM response; deterministic fallback used."],
        rejected_labels=[item.route.label for item in reviewed[1:4]],
    )


def _local_router_choice(
    reviewed: list[AdaptiveRouterCandidate],
    label: str,
) -> LLMAdaptiveRouterChoice:
    labels = {item.route.label for item in reviewed}
    if label not in labels:
        raise ValueError(f"--local-choice-label not found in prompt candidates: {label}")
    return LLMAdaptiveRouterChoice(
        selected_label=label,
        confidence=0.0,
        rationale="Local Codex/operator selected from prompt-visible route evidence only.",
        news_usage_plan="Treat news as advisory until PIT feature packets are available.",
        expected_risks=["Local choice is not independent LLM Alpha."],
        rejected_labels=[item.route.label for item in reviewed if item.route.label != label][:3],
    )


def _write_llm_router_json(
    path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    reviewed: list[AdaptiveRouterCandidate],
    choice: LLMAdaptiveRouterChoice,
    selected: AdaptiveRouterCandidate,
    status: str,
    prompt_path: Path,
    objective: IntradayObjective,
) -> Path:
    contribution = _llm_contribution(status, choice, selected, reviewed)
    payload = {
        "strategy_name": spec.name,
        "mode": "llm_adaptive_internal_router_selection",
        "status": status,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "prompt_path": str(prompt_path),
        "anti_leakage": {
            "llm_visible_metrics": "training and internal validation route summaries only",
            "llm_hidden_metrics": "final out-of-sample and full-window metrics",
            "llm_called_inside_backtest_loop": False,
        },
        "llm_contribution": contribution,
        "pass_status": _pass_status(
            selected,
            objective,
            llm_contribution_ok=bool(contribution["llm_contribution_ok"]),
            walk_forward=None,
        ),
        "choice": choice.model_dump(mode="json"),
        "selected": _candidate_payload(selected),
        "reviewed_candidates": [_llm_candidate_payload(item, objective) for item in reviewed],
    }
    return write_json(path, payload)


def _write_llm_router_report(
    path: Path,
    json_path: Path,
    prompt_path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    reviewed: list[AdaptiveRouterCandidate],
    choice: LLMAdaptiveRouterChoice,
    selected: AdaptiveRouterCandidate,
    status: str,
    objective: IntradayObjective,
) -> Path:
    ensure_dir(path.parent)
    contribution = _llm_contribution(status, choice, selected, reviewed)
    lines = [
        f"# LLM Adaptive Intraday Router Selection: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Prompt artifact: `{prompt_path}`",
        f"- Status: `{status}`",
        f"- Symbols: {', '.join(dataset.symbols)}",
        f"- Market symbol: `{dataset.market_symbol}`",
        f"- Benchmark symbol: `{dataset.benchmark_symbol}`",
        "- Mode: `llm_adaptive_internal_router_selection`",
        f"- Selection objective: {_objective_label(objective)}",
        "- Anti-leakage: final OOS and full-window metrics are hidden until after selection.",
        "- No LLM call is made inside the backtest loop.",
        "",
        "## LLM Choice",
        "",
        f"- Selected: `{choice.selected_label}`",
        f"- Confidence: `{choice.confidence:.2f}`",
        f"- Rationale: {choice.rationale}",
        f"- News usage plan: {choice.news_usage_plan}",
        f"- Expected risks: {', '.join(choice.expected_risks) or 'none'}",
        f"- Rejected labels: {', '.join(choice.rejected_labels) or 'none'}",
        "",
        "## LLM Contribution",
        "",
        f"- Contribution OK: `{contribution['llm_contribution_ok']}`",
        f"- Level: `{contribution['llm_contribution_level']}`",
        f"- Counterevidence: `{contribution['counterevidence']}`",
        "",
        "## Final Validation After Selection",
        "",
        f"- Route: `{selected.route.label}`",
        f"- Market scan note: `{_scan_market_state(dataset, 0, selected.route).note}`",
        (
            f"- Quality flags: "
            f"`{', '.join(selected.quality_flags) if selected.quality_flags else 'none'}`"
        ),
        f"- Route usage full window: `{selected.full_window.route_counts}`",
        *_metric_lines("Train", selected.train.base),
        *_metric_lines("Final OOS", selected.out_of_sample.base),
        *_metric_lines("Full window", selected.full_window.base),
        "",
        "## Candidates Visible To LLM",
        "",
        (
            "| Rank | Route | Score | Train Objective Alpha | "
            "Validation/OOS Objective Alpha | Route Count |"
        ),
        "|---:|---|---:|---:|---:|---:|",
    ]
    for item in reviewed[:18]:
        lines.append(
            f"| {item.rank} | `{item.route.label}` | {item.score:.2f} | "
            f"{(_objective_alpha(item.train.base, objective) or 0.0):.2f}% | "
            f"{(_objective_alpha(item.out_of_sample.base, objective) or 0.0):.2f}% | "
            f"{len(item.route.sub_strategies)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _llm_contribution(
    status: str,
    choice: LLMAdaptiveRouterChoice,
    selected: AdaptiveRouterCandidate,
    reviewed: list[AdaptiveRouterCandidate],
) -> dict[str, Any]:
    top_label = reviewed[0].route.label
    contribution_ok = status == "written" and choice.selected_label != top_label
    counterevidence = []
    if status != "written":
        counterevidence.append("external_llm_api_not_called_or_not_used")
    if choice.selected_label == top_label:
        counterevidence.append("selection_identical_to_deterministic_top_candidate")
    if selected.out_of_sample.base.traded_days < 30:
        counterevidence.append("sparse_oos_trading")
    return {
        "llm_contribution_ok": contribution_ok,
        "llm_contribution_level": (
            "independent_llm_route_selection" if contribution_ok else "llm_advisory_route_review"
        ),
        "selected_prompt_rank": next(
            (item.rank for item in reviewed if item.route.label == choice.selected_label),
            None,
        ),
        "deterministic_top_label": top_label,
        "counterevidence": counterevidence,
    }


def _candidate_payload(candidate: AdaptiveRouterCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "route": {
            "label": candidate.route.label,
            "sub_strategies": [
                {"family": item.family, "params": item.params.__dict__, "label": item.label}
                for item in candidate.route.sub_strategies
            ],
        },
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": _metrics_payload(candidate.train),
        "out_of_sample": _metrics_payload(candidate.out_of_sample),
        "full_window": _metrics_payload(candidate.full_window),
    }


def _metrics_payload(metrics: AdaptiveRouterMetrics) -> dict[str, Any]:
    payload = metrics.base.__dict__.copy()
    payload["route_counts"] = metrics.route_counts
    payload["skipped_days"] = metrics.skipped_days
    return payload


def _walk_payload(item: AdaptiveRouterWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "route": item.route.label,
        "train": _metrics_payload(item.train),
        "test": _metrics_payload(item.test),
    }


def _llm_candidate_payload(
    item: AdaptiveRouterCandidate,
    objective: IntradayObjective,
) -> dict[str, Any]:
    return {
        "rank": item.rank,
        "route_label": item.route.label,
        "sub_strategy_count": len(item.route.sub_strategies),
        "route_families": [sub.family for sub in item.route.sub_strategies],
        "route_counts": item.full_window.route_counts,
        "score": item.score,
        "train_objective_alpha_annualized_pct": _objective_alpha(item.train.base, objective),
        "validation_objective_alpha_annualized_pct": _objective_alpha(
            item.out_of_sample.base,
            objective,
        ),
        "validation_sharpe": item.out_of_sample.base.sharpe_ratio,
        "validation_traded_days": item.out_of_sample.base.traded_days,
        "validation_max_drawdown_pct": item.out_of_sample.base.max_drawdown_pct,
    }


def _params_grid_ranges(params_grid: list[IntradayDailyParams]) -> dict[str, list[Any]]:
    return {
        "selection_style": sorted({item.selection_style for item in params_grid}),
        "lookback_days": sorted({item.lookback_days for item in params_grid}),
        "entry_after_bars": sorted({item.entry_after_bars for item in params_grid}),
        "top_n": sorted({item.top_n for item in params_grid}),
        "min_opening_return_pct": sorted({item.min_opening_return_pct for item in params_grid}),
        "min_prior_momentum_pct": sorted({item.min_prior_momentum_pct for item in params_grid}),
        "min_relative_volume": sorted({item.min_relative_volume for item in params_grid}),
        "max_opening_return_pct": sorted(
            {item.max_opening_return_pct for item in params_grid},
            key=lambda value: -999 if value is None else value,
        ),
        "market_gate": sorted({item.market_gate for item in params_grid}),
    }
