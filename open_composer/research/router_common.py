from __future__ import annotations

import json
import math
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, pstdev
from time import perf_counter
from typing import Any, Protocol

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.metadata import (
    combined_data_profile,
    estimate_grid_research_cost,
    frame_data_profile,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json


class LabelledParams(Protocol):
    label: str


@dataclass(frozen=True)
class RouterFrameDataset:
    symbols: list[str]
    market_symbol: str
    benchmark_symbol: str
    dates: list[str]
    frame: pd.DataFrame
    data_profile: dict[str, Any]
    pit_membership: dict[str, list[tuple[str, str | None]]] | None = None
    runtime_cache: dict[str, Any] = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class RouterMetrics:
    days: int
    start_date: str | None
    end_date: str | None
    total_return_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    max_drawdown_pct: float
    traded_days: int
    round_trips: int
    average_selected_count: float
    win_day_pct: float
    benchmark_symbol: str
    benchmark_buy_hold_return_pct: float
    benchmark_buy_hold_annualized_pct: float | None
    alpha_vs_benchmark_buy_hold_annualized_pct: float | None
    market_symbol: str
    market_buy_hold_return_pct: float
    market_buy_hold_annualized_pct: float | None
    alpha_vs_market_buy_hold_annualized_pct: float | None
    equal_weight_buy_hold_return_pct: float
    equal_weight_buy_hold_annualized_pct: float | None
    alpha_vs_equal_weight_buy_hold_annualized_pct: float | None
    best_symbol_buy_hold_pct: float
    best_symbol: str | None
    alpha_vs_best_symbol_buy_hold_pct: float
    exposure_pct: float
    skipped_days: int
    average_gross_exposure_pct: float = 0.0
    max_gross_exposure_pct: float = 0.0
    max_symbol_weight_pct: float = 0.0
    market_regime_scaled_days: int = 0
    volatility_scaled_days: int = 0
    market_drawdown_brake_days: int = 0
    #: Per-day strategy returns (post-cost), only populated when the caller passes
    #: capture_returns=True. Empty by default so existing asdict() report payloads
    #: (e.g. route_cross_source._metrics_payload) do not balloon with a full daily
    #: series nobody asked for; gate/DSR evaluation opts in explicitly.
    daily_returns: tuple[float, ...] = ()


@dataclass(frozen=True)
class RouterCandidate:
    rank: int
    params: Any
    score: float
    train: RouterMetrics
    out_of_sample: RouterMetrics
    full_window: RouterMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class RouterWalkForwardSlice:
    fold: int
    params: Any
    train: RouterMetrics
    test: RouterMetrics


@dataclass(frozen=True)
class RouterResearchReport:
    report_path: Path
    json_path: Path
    candidates: list[RouterCandidate]
    walk_forward: list[RouterWalkForwardSlice]
    research_cost: dict[str, Any]
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> RouterCandidate:
        return self.candidates[0]

    @property
    def selected_route_label(self) -> str:
        return str(self.best.params.label)

    @property
    def research_pass(self) -> bool:
        return not self.best.quality_flags

    @property
    def paper_ready_pass(self) -> bool:
        return False


@dataclass(frozen=True)
class TargetSnapshot:
    selected: list[str]
    weights: dict[str, float]
    volatility_scale: float = 1.0
    market_regime_scale: float = 1.0
    market_drawdown_scale: float = 1.0
    state: str = "risk_off"
    qqq_trend_ok: bool = False
    qqq_momentum_ok: bool = False
    qqq_drawdown_ok: bool = True
    leverage_trend_ok: bool = True
    leverage_volatility_ok: bool = True
    leverage_drawdown_ok: bool = True
    core_gross: float = 0.0
    satellite_gross: float = 0.0
    satellite_scale: float = 1.0
    theme_gate_ok: bool = True


def load_daily_dataset(
    *,
    spec: StrategySpec,
    root: Path,
    symbols: list[str],
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    market_symbol: str = "QQQ",
    benchmark_symbol: str = "TQQQ",
    refresh_data: bool = False,
    min_sessions: int = 30,
    fetcher: Callable[..., pd.DataFrame] | None = None,
) -> RouterFrameDataset:
    required = list(dict.fromkeys([*symbols, market_symbol.upper(), benchmark_symbol.upper()]))
    frames: dict[str, pd.DataFrame] = {}
    profiles: list[dict[str, Any]] = []
    selected_feed = feed or spec.data.feed or data_feed()
    selected_fetcher = fetcher or fetch_ohlcv
    data_assumptions = getattr(spec, "data_assumptions", None)
    adjusted = bool(getattr(data_assumptions, "adjusted", True))
    selected_adjustment = ("all" if adjusted else "raw") if data_source == "alpaca" else None
    for symbol in required:
        fetch_kwargs = {
            "root": root,
            "symbol": symbol,
            "timeframe": "daily",
            "start": parse_timestamp(start),
            "end": parse_timestamp(end),
            "source": data_source,
            "feed": selected_feed,
            "use_cache": not refresh_data,
            "allow_fallback": False,
        }
        if selected_adjustment is not None:
            fetch_kwargs["adjustment"] = selected_adjustment
        frame = selected_fetcher(**fetch_kwargs)
        data = frame.copy()
        data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
        data["date"] = data["timestamp"].dt.date.astype(str)
        data = data.sort_values("timestamp").drop_duplicates("date", keep="last")
        frames[symbol] = data
        profiles.append(
            frame_data_profile(
                frame,
                symbol=symbol,
                timeframe="daily",
                provider=data_source,
                feed=selected_feed,
                source_mode=frame.attrs.get("data_source_mode"),
                path=frame.attrs.get("data_source_path"),
            )
        )
    common_dates = sorted(set.intersection(*(set(frame["date"]) for frame in frames.values())))
    if len(common_dates) < min_sessions:
        raise ValueError(f"router requires at least {min_sessions} common daily sessions")
    output = pd.DataFrame({"date": common_dates})
    for symbol, frame in frames.items():
        selected = frame.loc[
            frame["date"].isin(common_dates), ["date", "timestamp", "open", "close"]
        ]
        selected = selected.rename(
            columns={
                "timestamp": f"{symbol}_timestamp",
                "open": f"{symbol}_open",
                "close": f"{symbol}_close",
            }
        )
        output = output.merge(selected, on="date", how="left")
    output["timestamp"] = pd.to_datetime(output[f"{market_symbol.upper()}_timestamp"], utc=True)
    pit_membership = _load_pit_membership(spec, root)
    profile = combined_data_profile(profiles)
    if pit_membership:
        profile["pit_universe_membership"] = {
            "status": "loaded",
            "symbol_count": len(pit_membership),
        }
    return RouterFrameDataset(
        symbols=[item.upper() for item in symbols],
        market_symbol=market_symbol.upper(),
        benchmark_symbol=benchmark_symbol.upper(),
        dates=common_dates,
        frame=output.reset_index(drop=True),
        data_profile=profile,
        pit_membership=pit_membership,
    )


def active_membership_symbols(
    dataset: RouterFrameDataset,
    index: int,
    symbols: Iterable[str] | None = None,
) -> list[str]:
    candidates = [symbol.upper() for symbol in (symbols or dataset.symbols)]
    if not dataset.pit_membership:
        return candidates
    session = dataset.dates[index]
    return [
        symbol
        for symbol in candidates
        if any(
            _membership_active(session, start, end)
            for start, end in dataset.pit_membership.get(symbol, [])
        )
    ]


def _membership_active(session: str, start: str, end: str | None) -> bool:
    return start <= session and (end is None or session <= end)


def _load_pit_membership(
    spec: StrategySpec,
    root: Path,
) -> dict[str, list[tuple[str, str | None]]] | None:
    spec_notes = getattr(spec, "notes", None)
    if spec_notes is None:
        return None
    notes = spec_notes.model_dump(mode="json")
    metadata = notes.get("universe_audit") if isinstance(notes, dict) else None
    if not isinstance(metadata, dict):
        return None
    path_ref = (
        metadata.get("pit_membership_path")
        or metadata.get("membership_path")
        or metadata.get("artifact_path")
    )
    if not path_ref:
        return None
    path = Path(str(path_ref)).expanduser()
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    memberships = payload.get("memberships") if isinstance(payload, dict) else None
    if not isinstance(memberships, list):
        return None
    by_symbol: dict[str, list[tuple[str, str | None]]] = {}
    for row in memberships:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or "").upper().strip()
        start = str(row.get("effective_from") or "")[:10]
        end_value = row.get("effective_to")
        end = str(end_value)[:10] if end_value else None
        if symbol and start:
            by_symbol.setdefault(symbol, []).append((start, end))
    return by_symbol or None


def run_router_research(
    *,
    spec_path: Path,
    root: Path | None,
    mode: str,
    report_suffix: str,
    params_grid: list[Any],
    load_dataset: Callable[[StrategySpec, Path], RouterFrameDataset],
    snapshot: Callable[[StrategySpec, RouterFrameDataset, Any, int], TargetSnapshot],
    objective: str,
    filters: list[str],
    out_of_sample_ratio: float,
    walk_forward_folds: int,
    walk_forward_top_k: int | None,
) -> RouterResearchReport:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    stage_started = perf_counter()
    dataset = load_dataset(spec, base)
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    candidates = evaluate_router_candidates(
        spec=spec,
        dataset=dataset,
        params_grid=params_grid,
        snapshot=snapshot,
        out_of_sample_ratio=out_of_sample_ratio,
        objective=objective,
    )
    stages["evaluate_candidates"] = perf_counter() - stage_started

    walk_params = _walk_params(candidates, params_grid, walk_forward_top_k)
    research_cost = estimate_grid_research_cost(
        candidate_count=len(params_grid),
        walk_forward_candidate_count=len(walk_params),
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=walk_forward_folds,
    ).__dict__
    stage_started = perf_counter()
    walk_forward = walk_forward_router(
        spec=spec,
        dataset=dataset,
        params_grid=walk_params,
        snapshot=snapshot,
        folds=walk_forward_folds,
        objective=objective,
    )
    stages["walk_forward"] = perf_counter() - stage_started
    runtime = runtime_payload(started_at, stages)
    json_path = base / "reports" / "research" / f"{spec.name}-{report_suffix}.json"
    report_path = json_path.with_suffix(".md")
    payload = {
        "strategy_name": spec.name,
        "mode": mode,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "leverage_symbol": getattr(dataset, "leverage_symbol", dataset.benchmark_symbol),
        "hedge_symbol": getattr(dataset, "hedge_symbol", None),
        "data_profile": dataset.data_profile,
        "search_space": search_space(
            family=mode,
            candidate_count=_candidate_count(mode, params_grid),
            parameter_ranges=params_grid_ranges(params_grid),
            filters=filters,
        ),
        "research_cost": research_cost,
        "runtime_seconds": runtime,
        "acceptance_gate": acceptance_gate(candidates[0], walk_forward, objective),
        "pass_status": pass_status(candidates[0], walk_forward, objective),
        "anti_leakage": [
            "Route selection uses index-1 close/open data only.",
            "Route selection uses index-1 QQQ market data only.",
            "core-only ablation remains required for promotion.",
            "Train metrics select candidates; OOS and walk-forward are validation evidence.",
            "Target weights are generated as observation artifacts, not broker orders.",
        ],
        "candidates": [candidate_payload(item) for item in candidates],
        "selected_candidate": candidate_payload(candidates[0]),
        "walk_forward": [walk_payload(item) for item in walk_forward],
    }
    write_json(json_path, payload)
    write_router_research_artifacts(
        base=base,
        strategy_name=spec.name,
        mode=mode,
        report_suffix=report_suffix,
        payload=payload,
        data_profile=dataset.data_profile,
    )
    write_router_markdown(report_path, json_path, payload)
    return RouterResearchReport(
        report_path=report_path,
        json_path=json_path,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=runtime,
        data_profile=dataset.data_profile,
    )


def evaluate_router_candidates(
    *,
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params_grid: list[Any],
    snapshot: Callable[[StrategySpec, RouterFrameDataset, Any, int], TargetSnapshot],
    out_of_sample_ratio: float,
    objective: str,
) -> list[RouterCandidate]:
    split = split_for_oos(len(dataset.dates), out_of_sample_ratio, params_grid)
    rows: list[RouterCandidate] = []
    for params in params_grid:
        lookback = effective_lookback(params)
        train = backtest_router_params(
            spec, dataset, params, snapshot=snapshot, start_index=lookback, end_index=split
        )
        oos = backtest_router_params(
            spec,
            dataset,
            params,
            snapshot=snapshot,
            start_index=split,
            end_index=len(dataset.dates),
        )
        full = backtest_router_params(
            spec,
            dataset,
            params,
            snapshot=snapshot,
            start_index=lookback,
            end_index=len(dataset.dates),
        )
        rows.append(
            RouterCandidate(
                rank=0,
                params=params,
                score=score_metrics(train, objective),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=quality_flags(train, oos, full, objective=objective),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        RouterCandidate(
            rank=index,
            params=item.params,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            quality_flags=item.quality_flags,
        )
        for index, item in enumerate(rows, start=1)
    ]


def walk_forward_router(
    *,
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params_grid: list[Any],
    snapshot: Callable[[StrategySpec, RouterFrameDataset, Any, int], TargetSnapshot],
    folds: int,
    objective: str,
) -> list[RouterWalkForwardSlice]:
    if not params_grid:
        return []
    max_lookback = max(effective_lookback(item) for item in params_grid)
    fold_size = max((len(dataset.dates) - max_lookback) // (max(folds, 1) + 1), 5)
    rows: list[RouterWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.dates), test_start + fold_size)
        if test_end - test_start < 3:
            continue
        scored = []
        for params in params_grid:
            train = backtest_router_params(
                spec,
                dataset,
                params,
                snapshot=snapshot,
                start_index=max_lookback,
                end_index=test_start,
            )
            scored.append((score_metrics(train, objective), params))
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        rows.append(
            RouterWalkForwardSlice(
                fold=fold,
                params=selected,
                train=backtest_router_params(
                    spec,
                    dataset,
                    selected,
                    snapshot=snapshot,
                    start_index=max_lookback,
                    end_index=test_start,
                ),
                test=backtest_router_params(
                    spec,
                    dataset,
                    selected,
                    snapshot=snapshot,
                    start_index=test_start,
                    end_index=test_end,
                ),
            )
        )
    return rows


def backtest_router_params(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: Any,
    *,
    snapshot: Callable[[StrategySpec, RouterFrameDataset, Any, int], TargetSnapshot],
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
    capture_returns: bool = False,
) -> RouterMetrics:
    lookback = effective_lookback(params)
    start_index = max(start_index, lookback)
    end_index = min(end_index, len(dataset.dates) - _holding_offset(params))
    returns: list[float] = []
    selected_counts: list[int] = []
    gross_values: list[float] = []
    max_weights: list[float] = []
    equity_curve = [start_equity]
    equity = start_equity
    traded_days = 0
    round_trips = 0
    skipped_days = 0
    regime_scaled = 0
    vol_scaled = 0
    drawdown_scaled = 0
    previous_weights: dict[str, float] = {}
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    for index in range(start_index, end_index):
        targets = snapshot(spec, dataset, params, index)
        gross = sum(abs(value) for value in targets.weights.values())
        max_weight = max((abs(value) for value in targets.weights.values()), default=0.0)
        if targets.market_regime_scale < 0.999999:
            regime_scaled += 1
        if targets.volatility_scale < 0.999999:
            vol_scaled += 1
        if targets.market_drawdown_scale < 0.999999:
            drawdown_scaled += 1
        raw_return = sum(
            weight * symbol_holding_return(dataset, symbol, index, _holding_mode(params), spec)
            for symbol, weight in targets.weights.items()
            if weight > 0
        )
        turnover = sum(
            abs(targets.weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in set(targets.weights) | set(previous_weights)
        )
        strategy_return = raw_return - turnover * cost_rate
        if gross <= 0:
            skipped_days += 1
        else:
            traded_days += 1
        if turnover > 1e-12:
            round_trips += 1
        previous_weights = {} if _holding_mode(params) == "open_to_close" else targets.weights
        selected_counts.append(len(targets.selected))
        gross_values.append(gross)
        max_weights.append(max_weight)
        returns.append(strategy_return)
        equity *= 1 + strategy_return
        equity_curve.append(equity)
    period_dates = dataset.dates[start_index:end_index]
    total_return = (equity / start_equity - 1) * 100
    benchmark_buy_hold = daily_buy_hold_return(
        dataset, dataset.benchmark_symbol, start_index, end_index
    )
    market_buy_hold = daily_buy_hold_return(dataset, dataset.market_symbol, start_index, end_index)
    equal_weight = mean(
        daily_buy_hold_return(dataset, symbol, start_index, end_index) for symbol in dataset.symbols
    )
    universe_returns = {
        symbol: daily_buy_hold_return(dataset, symbol, start_index, end_index)
        for symbol in dataset.symbols
    }
    best_symbol = max(universe_returns, key=universe_returns.get) if universe_returns else None
    best_return = universe_returns[best_symbol] if best_symbol else 0.0
    annualized = annualized_from_total(total_return, len(returns))
    benchmark_annualized = annualized_from_total(benchmark_buy_hold, len(returns))
    market_annualized = annualized_from_total(market_buy_hold, len(returns))
    equal_weight_annualized = annualized_from_total(equal_weight, len(returns))
    return RouterMetrics(
        days=len(returns),
        start_date=period_dates[0] if period_dates else None,
        end_date=period_dates[-1] if period_dates else None,
        total_return_pct=total_return,
        annualized_return_pct=annualized,
        sharpe_ratio=daily_sharpe(returns),
        max_drawdown_pct=max_drawdown_pct(equity_curve),
        traded_days=traded_days,
        round_trips=round_trips,
        average_selected_count=mean(selected_counts) if selected_counts else 0.0,
        win_day_pct=win_pct(returns),
        benchmark_symbol=dataset.benchmark_symbol,
        benchmark_buy_hold_return_pct=benchmark_buy_hold,
        benchmark_buy_hold_annualized_pct=benchmark_annualized,
        alpha_vs_benchmark_buy_hold_annualized_pct=alpha(annualized, benchmark_annualized),
        market_symbol=dataset.market_symbol,
        market_buy_hold_return_pct=market_buy_hold,
        market_buy_hold_annualized_pct=market_annualized,
        alpha_vs_market_buy_hold_annualized_pct=alpha(annualized, market_annualized),
        equal_weight_buy_hold_return_pct=equal_weight,
        equal_weight_buy_hold_annualized_pct=equal_weight_annualized,
        alpha_vs_equal_weight_buy_hold_annualized_pct=alpha(annualized, equal_weight_annualized),
        best_symbol_buy_hold_pct=best_return,
        best_symbol=best_symbol,
        alpha_vs_best_symbol_buy_hold_pct=total_return - best_return,
        exposure_pct=(traded_days / len(returns) * 100) if returns else 0.0,
        skipped_days=skipped_days,
        average_gross_exposure_pct=mean(gross_values) * 100 if gross_values else 0.0,
        max_gross_exposure_pct=max(gross_values) * 100 if gross_values else 0.0,
        max_symbol_weight_pct=max(max_weights) * 100 if max_weights else 0.0,
        market_regime_scaled_days=regime_scaled,
        volatility_scaled_days=vol_scaled,
        market_drawdown_brake_days=drawdown_scaled,
        daily_returns=tuple(returns) if capture_returns else (),
    )


def selected_by_momentum(
    dataset: RouterFrameDataset,
    index: int,
    *,
    lookback: int,
    top_n: int,
    min_momentum_pct: float = 0.0,
    symbols: Iterable[str] | None = None,
    score_mode: str = "raw",
    risk_adjustment_lookback: int | None = None,
) -> list[str]:
    previous_index = index - 1 - lookback
    current_index = index - 1
    if previous_index < 0 or current_index < 0:
        return []
    scored: list[tuple[float, str]] = []
    for symbol in active_membership_symbols(dataset, index, symbols):
        previous = close_value(dataset, symbol, previous_index)
        current = close_value(dataset, symbol, current_index)
        if previous <= 0:
            continue
        momentum = (current / previous - 1) * 100
        if momentum < min_momentum_pct:
            continue
        score = momentum
        if score_mode == "risk_adjusted":
            vol = close_volatility_pct(dataset, symbol, risk_adjustment_lookback or lookback, index)
            score = momentum / vol if vol > 0 else float("-inf")
        scored.append((score, symbol))
    scored.sort(reverse=True)
    return [symbol for _, symbol in scored[:top_n]]


def market_sma_scale(
    dataset: RouterFrameDataset,
    params: Any,
    index: int,
    *,
    field: str = "market_sma_days",
    scale_field: str = "market_below_sma_scale",
) -> float:
    lookback = getattr(params, field, None)
    if not lookback:
        return 1.0
    if index < lookback:
        return 0.0
    sma = float(rolling_close_mean(dataset, dataset.market_symbol, lookback).iloc[index - 1])
    if close_value(dataset, dataset.market_symbol, index - 1) > sma:
        return 1.0
    return float(getattr(params, scale_field, 0.0) or 0.0)


def volatility_scale(
    dataset: RouterFrameDataset,
    symbol: str,
    index: int,
    *,
    lookback: int | None,
    target_pct: float | None,
) -> float:
    if not lookback or not target_pct:
        return 1.0
    vol = close_volatility_pct(dataset, symbol, lookback, index)
    if vol <= 0:
        return 1.0
    return max(0.0, min(1.0, target_pct / vol))


def drawdown_scale(
    dataset: RouterFrameDataset,
    symbol: str,
    index: int,
    *,
    lookback: int | None,
    max_drawdown: float | None,
    brake_scale: float,
) -> float:
    if not lookback or max_drawdown is None or index - lookback < 0:
        return 1.0
    drawdown = rolling_drawdown_pct(dataset, symbol, lookback).iloc[index - 1]
    return brake_scale if drawdown <= -abs(max_drawdown) else 1.0


def split_for_oos(frame_len: int, ratio: float, params_grid: list[Any]) -> int:
    max_lookback = max(effective_lookback(item) for item in params_grid)
    split = int(frame_len * (1 - ratio))
    split = max(split, max_lookback + 10)
    return min(split, frame_len - 5)


def effective_lookback(params: Any) -> int:
    base_params = getattr(params, "base_params", None)
    values = [
        getattr(params, "momentum_lookback_days", 0),
        getattr(params, "trend_sma_days", 0) or 0,
        getattr(params, "market_sma_days", 0) or 0,
        getattr(params, "volatility_lookback_days", 0) or 0,
        getattr(params, "drawdown_lookback_days", 0) or 0,
        getattr(params, "market_drawdown_lookback_days", 0) or 0,
        getattr(params, "market_reentry_momentum_lookback_days", 0) or 0,
        getattr(params, "override_short_momentum_lookback_days", 0) or 0,
        getattr(params, "risk_adjustment_lookback_days", 0) or 0,
        getattr(params, "confirmation_sma_days", 0) or 0,
        getattr(params, "bear_inverse_lookback_days", 0) or 0,
        getattr(params, "bear_inverse_confirmation_sma_days", 0) or 0,
        getattr(params, "leadership_breadth_lookback_days", 0) or 0,
        getattr(params, "leverage_trend_sma_days", 0) or 0,
        getattr(params, "leverage_drawdown_lookback_days", 0) or 0,
        getattr(params, "satellite_momentum_days", 0) or 0,
        getattr(params, "confirmation_days", 0) or 0,
        getattr(params, "market_momentum_days", 0) or 0,
        getattr(params, "signal_momentum_days", 0) or 0,
    ]
    if base_params is not None:
        values.append(effective_lookback(base_params))
    return max(int(value) for value in values if value is not None)


def score_metrics(
    metrics: RouterMetrics,
    objective: str = "risk_adjusted_benchmark_alpha",
) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    benchmark_alpha = metrics.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0
    market_alpha = metrics.alpha_vs_market_buy_hold_annualized_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    drawdown = abs(min(metrics.max_drawdown_pct, 0.0))
    sparse_penalty = max(0, 40 - metrics.traded_days) * 2.0
    concentration_penalty = max(0.0, metrics.max_symbol_weight_pct - 50.0) * 1.25
    if objective == "absolute_return_risk":
        return (
            1.00 * annualized
            + 12.0 * sharpe
            - 0.80 * drawdown
            - sparse_penalty
            - concentration_penalty
        )
    if objective == "benchmark_buy_hold_alpha":
        return (
            1.20 * benchmark_alpha
            + 0.80 * annualized
            + 0.30 * market_alpha
            + 5.0 * sharpe
            - 0.45 * drawdown
            - sparse_penalty
        )
    return (
        0.65 * annualized
        + 0.75 * benchmark_alpha
        + 0.35 * market_alpha
        + 10.0 * sharpe
        - 0.85 * drawdown
        - sparse_penalty
        - concentration_penalty
    )


def quality_flags(
    train: RouterMetrics,
    oos: RouterMetrics,
    full: RouterMetrics,
    *,
    objective: str = "risk_adjusted_benchmark_alpha",
) -> list[str]:
    flags: list[str] = []
    benchmark_alpha_objective = objective in {
        "benchmark_buy_hold_alpha",
        "risk_adjusted_benchmark_alpha",
    }
    if benchmark_alpha_objective:
        if (train.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
            flags.append("train_no_alpha_vs_benchmark")
        if (oos.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
            flags.append("oos_no_alpha_vs_benchmark")
    else:
        if (train.annualized_return_pct or -100.0) <= 0:
            flags.append("train_nonpositive_return")
        if (oos.annualized_return_pct or -100.0) <= 0:
            flags.append("oos_nonpositive_return")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if oos.traded_days < 20:
        flags.append("oos_low_traded_days")
    drawdown_limit = -40 if objective == "absolute_return_risk" else -30
    if oos.max_drawdown_pct <= drawdown_limit:
        flags.append("oos_large_drawdown")
    if benchmark_alpha_objective and full.alpha_vs_best_symbol_buy_hold_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    return flags


def acceptance_gate(
    candidate: RouterCandidate, walk_forward: list[RouterWalkForwardSlice], objective: str
) -> dict[str, Any]:
    objective_alpha = objective_alpha_pct(candidate.out_of_sample, objective)
    wf_positive = sum(
        (objective_alpha_pct(item.test, objective) or -100.0) > 0 for item in walk_forward
    )
    if objective == "absolute_return_risk":
        passed = (
            (candidate.full_window.annualized_return_pct or -100.0) >= 30.0
            and (candidate.full_window.sharpe_ratio or 0.0) >= 1.0
            and candidate.full_window.max_drawdown_pct > -40.0
            and (candidate.out_of_sample.annualized_return_pct or -100.0) >= 30.0
            and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 1.0
            and candidate.out_of_sample.max_drawdown_pct > -40.0
            and wf_positive >= max(1, len(walk_forward) // 2 + 1)
        )
    else:
        passed = (
            (objective_alpha or -100.0) > 0
            and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.5
            and (candidate.out_of_sample.max_drawdown_pct > -30)
            and wf_positive >= max(1, len(walk_forward) // 2 + 1)
        )
    return {
        "passed": passed,
        "objective": objective,
        "train_alpha_vs_tqqq_buy_hold_annualized_pct": (
            candidate.train.alpha_vs_benchmark_buy_hold_annualized_pct
        ),
        "oos_alpha_vs_tqqq_buy_hold_annualized_pct": (
            candidate.out_of_sample.alpha_vs_benchmark_buy_hold_annualized_pct
        ),
        "full_alpha_vs_tqqq_buy_hold_annualized_pct": (
            candidate.full_window.alpha_vs_benchmark_buy_hold_annualized_pct
        ),
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "oos_traded_days": candidate.out_of_sample.traded_days,
        "oos_max_drawdown_pct": candidate.out_of_sample.max_drawdown_pct,
        "walk_forward_positive_alpha_folds": wf_positive,
        "walk_forward_fold_count": len(walk_forward),
        "quality_flags": candidate.quality_flags,
        "advisory_flags": advisory_quality_flags(candidate),
    }


def objective_alpha_pct(metrics: RouterMetrics, objective: str) -> float | None:
    if objective in {"benchmark_buy_hold_alpha", "risk_adjusted_benchmark_alpha"}:
        return metrics.alpha_vs_benchmark_buy_hold_annualized_pct
    if objective == "absolute_return_risk":
        return metrics.annualized_return_pct
    return metrics.alpha_vs_benchmark_buy_hold_annualized_pct


def advisory_quality_flags(candidate: RouterCandidate) -> list[str]:
    flags: list[str] = []
    if (candidate.train.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_benchmark")
    if (candidate.out_of_sample.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_benchmark")
    if candidate.full_window.alpha_vs_best_symbol_buy_hold_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    return flags


def pass_status(
    candidate: RouterCandidate, walk_forward: list[RouterWalkForwardSlice], objective: str
) -> dict[str, Any]:
    gate = acceptance_gate(candidate, walk_forward, objective)
    return {
        "workflow_pass": True,
        "research_pass": bool(gate["passed"]),
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_ready_blockers": [
            "router research is not paper readiness",
            "target-weight mapping must be reviewed separately",
            "broker orders remain disabled without paper_auto authorization",
        ],
    }


def candidate_payload(candidate: RouterCandidate) -> dict[str, Any]:
    full = asdict(candidate.full_window)
    full.setdefault("satellite_marginal_annualized_pct", 0.0)
    return {
        "rank": candidate.rank,
        "params": params_payload(candidate.params),
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": asdict(candidate.train),
        "out_of_sample": asdict(candidate.out_of_sample),
        "full_window": full,
        "full": full,
    }


def walk_payload(item: RouterWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": params_payload(item.params),
        "train": asdict(item.train),
        "test": asdict(item.test),
    }


def write_router_research_artifacts(
    *,
    base: Path,
    strategy_name: str,
    mode: str,
    report_suffix: str,
    payload: dict[str, Any],
    data_profile: dict[str, Any],
) -> None:
    """Write router evidence in the generic harness artifact shapes."""
    out_dir = base / "reports" / "research"
    ensure_dir(out_dir)
    source_report = f"reports/research/{strategy_name}-{report_suffix}.json"
    created_at = datetime.now(UTC).isoformat()
    search_payload = payload.get("search_space", {})
    parameters = search_payload.get("parameter_ranges") or search_payload.get("parameters") or {}
    total_combinations = int(
        search_payload.get("candidate_count")
        or search_payload.get("total_combinations")
        or len(payload.get("candidates", []))
    )

    write_json(
        out_dir / f"{strategy_name}-search-space.json",
        {
            "strategy_name": strategy_name,
            "parameters": parameters,
            "total_combinations": total_combinations,
            "search_method": f"{mode}:{report_suffix}",
            "created_at": created_at,
            "source_report": source_report,
            "filters": search_payload.get("filters", []),
        },
    )

    candidates = [item for item in payload.get("candidates", []) if isinstance(item, dict)]
    selected = (
        payload.get("selected_candidate")
        if isinstance(payload.get("selected_candidate"), dict)
        else {}
    )
    selected_label = str((selected.get("params") or {}).get("label") or "")
    ledger_path = out_dir / f"{strategy_name}-trial-ledger.jsonl"
    with ledger_path.open("w", encoding="utf-8") as handle:
        for item in candidates:
            params = item.get("params") if isinstance(item.get("params"), dict) else {}
            label = str(params.get("label") or f"rank-{item.get('rank', 'unknown')}")
            train = item.get("train") if isinstance(item.get("train"), dict) else {}
            oos = item.get("out_of_sample") if isinstance(item.get("out_of_sample"), dict) else {}
            selected_item = label == selected_label
            record = {
                "trial_id": f"{strategy_name}:{mode}:{item.get('rank', 0)}",
                "parameter_set": params,
                "data_profile": data_profile,
                "train_window": {
                    "start": train.get("start_date"),
                    "end": train.get("end_date"),
                    "days": train.get("days"),
                },
                "test_window": {
                    "start": oos.get("start_date"),
                    "end": oos.get("end_date"),
                    "days": oos.get("days"),
                },
                "metrics": {
                    "score": item.get("score"),
                    "train": train,
                    "out_of_sample": oos,
                    "full_window": item.get("full_window") or item.get("full"),
                },
                "selected": selected_item,
                "rejection_reason": None
                if selected_item
                else "lower_router_objective_score_or_weaker_gate_quality_than_selected_candidate",
                "source_report": source_report,
            }
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    candidate_rows = []
    for item in candidates:
        params = item.get("params") if isinstance(item.get("params"), dict) else {}
        label = str(params.get("label") or f"rank-{item.get('rank', 'unknown')}")
        candidate_rows.append(
            {
                "candidate_id": label,
                "rank": item.get("rank"),
                "parameter_set": params,
                "score": item.get("score"),
                "metrics": {
                    "train": item.get("train"),
                    "out_of_sample": item.get("out_of_sample"),
                    "full_window": item.get("full_window") or item.get("full"),
                },
                "quality_flags": item.get("quality_flags", []),
                "selected": label == selected_label,
            }
        )
    write_json(
        out_dir / f"{strategy_name}-candidate-set.json",
        {
            "strategy_name": strategy_name,
            "candidates": candidate_rows,
            "selection_criteria": {
                "objective": payload.get("acceptance_gate", {}).get("objective"),
                "filters": search_payload.get("filters", []),
                "research_cost": payload.get("research_cost", {}),
                "source_report": source_report,
            },
            "selected_candidate_id": selected_label,
        },
    )

    walk_rows = [item for item in payload.get("walk_forward", []) if isinstance(item, dict)]
    write_json(
        out_dir / f"{strategy_name}-walk-forward.json",
        {
            "strategy_name": strategy_name,
            "method": "sequential_router_walk_forward",
            "windows": [
                {
                    "fold": item.get("fold"),
                    "parameter_set": item.get("params"),
                    "train_window": {
                        "start": (item.get("train") or {}).get("start_date"),
                        "end": (item.get("train") or {}).get("end_date"),
                        "days": (item.get("train") or {}).get("days"),
                    },
                    "test_window": {
                        "start": (item.get("test") or {}).get("start_date"),
                        "end": (item.get("test") or {}).get("end_date"),
                        "days": (item.get("test") or {}).get("days"),
                    },
                    "test_metrics": item.get("test"),
                }
                for item in walk_rows
            ],
            "oos_metrics": selected.get("out_of_sample") if selected else {},
            "conclusion": "pass"
            if bool(payload.get("acceptance_gate", {}).get("passed"))
            else "warning",
            "source_report": source_report,
        },
    )


def params_payload(params: Any) -> dict[str, Any]:
    payload = asdict(params)
    payload["label"] = params.label
    return payload


def params_grid_ranges(params_grid: list[Any]) -> dict[str, list[Any]]:
    values: dict[str, set[Any]] = {}
    for params in params_grid:
        for key, value in asdict(params).items():
            try:
                values.setdefault(key, set()).add(value)
            except TypeError:
                continue
    return {
        key: sorted(items, key=lambda value: (-1, "") if value is None else (0, str(value)))
        for key, items in values.items()
    }


def _candidate_count(mode: str, params_grid: list[Any]) -> int:
    if mode == "beta_exposure_router":
        return max(len(params_grid), 6)
    return len(params_grid)


def write_router_markdown(path: Path, json_path: Path, payload: dict[str, Any]) -> Path:
    ensure_dir(path.parent)
    best = payload["selected_candidate"]
    lines = [
        f"# Router Research: {payload['strategy_name']}",
        "",
        f"- Mode: `{payload['mode']}`",
        f"- JSON report: `{json_path}`",
        f"- Best route: `{best['params']['label']}`",
        f"- Research pass: `{payload['pass_status']['research_pass']}`",
        f"- Candidate count: `{payload['search_space']['candidate_count']}`",
        "",
        "## Acceptance Gate",
        "",
        *[f"- {key}: `{value}`" for key, value in payload["acceptance_gate"].items()],
        "",
        "## Top Candidates",
        "",
    ]
    for item in payload["candidates"][:10]:
        lines.extend(
            [
                f"### Rank {item['rank']}: {item['params']['label']}",
                "",
                f"- Score: `{item['score']:.2f}`",
                f"- OOS annualized: `{fmt(item['out_of_sample']['annualized_return_pct'])}%`",
                "- OOS Alpha vs benchmark: "
                f"`{fmt(item['out_of_sample']['alpha_vs_benchmark_buy_hold_annualized_pct'])}%`",
                f"- OOS max drawdown: `{fmt(item['out_of_sample']['max_drawdown_pct'])}%`",
                "- Quality flags: "
                f"`{', '.join(item['quality_flags']) if item['quality_flags'] else 'none'}`",
                "",
            ]
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def close_value(dataset: RouterFrameDataset, symbol: str, index: int) -> float:
    if index < 0 or index >= len(dataset.frame):
        return 0.0
    return float(close_series(dataset, symbol).iloc[index])


def open_value(dataset: RouterFrameDataset, symbol: str, index: int) -> float:
    if index < 0 or index >= len(dataset.frame):
        return 0.0
    return float(open_series(dataset, symbol).iloc[index])


def close_series(dataset: RouterFrameDataset, symbol: str) -> pd.Series:
    key = f"close:{symbol.upper()}"
    cached = dataset.runtime_cache.get(key)
    if cached is None:
        cached = dataset.frame[f"{symbol.upper()}_close"].astype(float)
        dataset.runtime_cache[key] = cached
    return cached


def open_series(dataset: RouterFrameDataset, symbol: str) -> pd.Series:
    key = f"open:{symbol.upper()}"
    cached = dataset.runtime_cache.get(key)
    if cached is None:
        cached = dataset.frame[f"{symbol.upper()}_open"].astype(float)
        dataset.runtime_cache[key] = cached
    return cached


def rolling_close_mean(dataset: RouterFrameDataset, symbol: str, lookback: int) -> pd.Series:
    key = f"close_mean:{symbol.upper()}:{lookback}"
    cached = dataset.runtime_cache.get(key)
    if cached is None:
        cached = close_series(dataset, symbol).rolling(lookback).mean()
        dataset.runtime_cache[key] = cached
    return cached


def rolling_close_max(dataset: RouterFrameDataset, symbol: str, lookback: int) -> pd.Series:
    key = f"close_max:{symbol.upper()}:{lookback}"
    cached = dataset.runtime_cache.get(key)
    if cached is None:
        cached = close_series(dataset, symbol).rolling(lookback).max()
        dataset.runtime_cache[key] = cached
    return cached


def symbol_holding_return(
    dataset: RouterFrameDataset,
    symbol: str,
    index: int,
    holding_mode: str,
    spec: StrategySpec,
) -> float:
    entry = open_value(dataset, symbol, index)
    if holding_mode == "open_to_close":
        exit_price = close_value(dataset, symbol, index)
    else:
        exit_price = open_value(dataset, symbol, index + 1)
    if entry <= 0 or exit_price <= 0:
        return 0.0
    return (exit_price / entry) - 1


def daily_buy_hold_return(
    dataset: RouterFrameDataset, symbol: str, start_index: int, end_index: int
) -> float:
    if start_index >= end_index:
        return 0.0
    start = open_value(dataset, symbol, start_index)
    end = close_value(dataset, symbol, end_index - 1)
    return ((end / start) - 1) * 100 if start > 0 else 0.0


def close_volatility_pct(
    dataset: RouterFrameDataset, symbol: str, lookback: int, index: int
) -> float:
    if index - lookback < 1:
        return 0.0
    value = rolling_close_volatility_pct(dataset, symbol, lookback).iloc[index - 1]
    return 0.0 if pd.isna(value) else float(value)


def rolling_close_volatility_pct(
    dataset: RouterFrameDataset,
    symbol: str,
    lookback: int,
) -> pd.Series:
    key = f"close_volatility_pct:{symbol.upper()}:{lookback}"
    cached = dataset.runtime_cache.get(key)
    if cached is None:
        returns = close_series(dataset, symbol).pct_change()
        window = max(lookback - 1, 2)
        cached = returns.rolling(window).std(ddof=0) * math.sqrt(252) * 100
        dataset.runtime_cache[key] = cached
    return cached


def rolling_drawdown_pct(
    dataset: RouterFrameDataset,
    symbol: str,
    lookback: int,
) -> pd.Series:
    key = f"rolling_drawdown_pct:{symbol.upper()}:{lookback}"
    cached = dataset.runtime_cache.get(key)
    if cached is None:
        close = close_series(dataset, symbol)
        cached = close.rolling(lookback).apply(_window_drawdown_pct, raw=False)
        dataset.runtime_cache[key] = cached
    return cached


def _window_drawdown_pct(values: pd.Series) -> float:
    peak = values.cummax()
    return float(((values / peak) - 1).min() * 100)


def trend_ok(dataset: RouterFrameDataset, symbol: str, index: int, lookback: int) -> bool:
    if index < lookback:
        return False
    close = dataset.frame[f"{symbol}_close"].astype(float)
    return close_value(dataset, symbol, index - 1) > float(
        close.iloc[index - lookback : index].mean()
    )


def momentum_ok(
    dataset: RouterFrameDataset,
    symbol: str,
    index: int,
    lookback: int,
    min_momentum_pct: float,
) -> bool:
    if index - lookback - 1 < 0:
        return False
    previous = close_value(dataset, symbol, index - lookback - 1)
    current = close_value(dataset, symbol, index - 1)
    return previous > 0 and (current / previous - 1) * 100 >= min_momentum_pct


def max_volatility_ok(
    dataset: RouterFrameDataset,
    symbol: str,
    index: int,
    lookback: int,
    max_volatility_pct: float | None,
) -> bool:
    if max_volatility_pct is None:
        return True
    return close_volatility_pct(dataset, symbol, lookback, index) <= max_volatility_pct


def annualized_from_total(total_return_pct: float, days: int) -> float | None:
    if days <= 0:
        return None
    base = 1 + total_return_pct / 100
    if base <= 0:
        return -100.0
    return (base ** (252 / days) - 1) * 100


def daily_sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    sigma = pstdev(returns)
    if sigma <= 0:
        return None
    return mean(returns) / sigma * math.sqrt(252)


def max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            drawdown = min(drawdown, value / peak - 1)
    return drawdown * 100


def win_pct(returns: list[float]) -> float:
    return sum(value > 0 for value in returns) / len(returns) * 100 if returns else 0.0


def alpha(value: float | None, benchmark: float | None) -> float | None:
    if value is None or benchmark is None:
        return None
    return value - benchmark


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return timestamp.to_pydatetime()


def fmt(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def label_optional(value: float | None) -> str:
    return "none" if value is None else f"{value:g}"


def parse_optional_float(value: str) -> float | None:
    return None if value == "none" else float(value)


def label_optional_int(value: int | None) -> str:
    return "none" if value is None else str(value)


def parse_optional_int(value: str) -> int | None:
    return None if value == "none" else int(value)


def relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()


def _walk_params(
    candidates: list[RouterCandidate], params_grid: list[Any], top_k: int | None
) -> list[Any]:
    if top_k is None:
        return params_grid
    if top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(top_k, len(candidates))]]


def _holding_mode(params: Any) -> str:
    return str(getattr(params, "holding_mode", "open_to_open"))


def _holding_offset(params: Any) -> int:
    return 1 if _holding_mode(params) == "open_to_open" else 0
