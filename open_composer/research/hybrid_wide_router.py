from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from open_composer.config import project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.hybrid_adaptive_router import (
    HybridRouterMetrics,
    HybridRouterParams,
    _build_hybrid_params_grid,
    _daily_frame_from_intraday,
    _DailyHybridDataset,
    _effective_lookback,
    _load_daily_hybrid_dataset,
    _params_grid_ranges,
)
from open_composer.research.intraday_daily_rotation import (
    _alpha,
    _annualized_from_total,
    _daily_sharpe,
    _DailyBars,
    _max_drawdown_pct,
    _win_pct,
)
from open_composer.research.metadata import (
    combined_data_profile,
    frame_data_profile,
    runtime_payload,
    search_space,
)
from open_composer.research.rotation import _filter_time_window
from open_composer.storage import write_json


@dataclass(frozen=True)
class WideRouterResearchResult:
    report_path: Path
    json_path: Path
    selected_route_label: str
    research_pass: bool
    paper_ready_pass: bool


def run_wide_router_research(
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
    refresh_data: bool = False,
) -> WideRouterResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    selected_feed = feed or spec.data.feed

    stage_started = perf_counter()
    if (
        data_source == "alpaca"
        and (selected_feed or "iex") == "iex"
        and not refresh_data
        and _daily_cache_available(base, universe, benchmark_symbol, market_symbol)
    ):
        dataset = _load_daily_cache_dataset(
            root=base,
            symbols=universe,
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol,
            market_symbol=market_symbol,
        )
    else:
        dataset = _load_daily_hybrid_dataset(
            spec=spec,
            root=base,
            symbols=universe,
            data_source=data_source,
            feed=selected_feed or "iex",
            start=start,
            end=end,
            benchmark_symbol=benchmark_symbol,
            market_symbol=market_symbol,
            refresh_data=refresh_data,
        )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    params_grid = _wide_params_grid()
    cache = _build_fast_cache(dataset)
    candidates = _score_candidates(spec, dataset, cache, params_grid)
    selected = candidates[0]
    validation = _validation_windows(spec, dataset, cache, selected["params"])
    walk_forward = _walk_forward(spec, dataset, cache, params_grid)
    pass_status = _pass_status(selected, validation, walk_forward, dataset)
    stages["research"] = perf_counter() - stage_started

    json_path = base / "reports" / "research" / f"{spec.name}-hybrid-adaptive-router.json"
    report_path = json_path.with_suffix(".md")
    payload = {
        "strategy_name": spec.name,
        "mode": "hybrid_adaptive_router",
        "research_variant": "wide_nasdaq100_daily_router",
        "source_spec_path": _relpath(spec_path, base),
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "research_window": {"start": start, "end": end},
        "selection_policy": "train_2022_2024_only; 2025 and 2026 windows are validation only",
        "anti_leakage": [
            "candidate ranking uses 2022-2024 train metrics only",
            "signals use closes visible before the entry session",
            "fills are modeled at the next regular-session open",
            "volatility and market drawdown brakes use only prior QQQ closes",
            "validation windows are not used to choose the route",
        ],
        "known_biases": [
            "current-constituent NASDAQ-100 representative universe; not PIT membership",
            "Alpaca IEX cache is not consolidated SIP evidence",
            "LLM/news is not an execution factor in this research pass",
        ],
        "search_space": search_space(
            family="wide_nasdaq100_daily_momentum_router",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=[
                "long-only target weights",
                "max gross <= 75%",
                "max symbol weight <= 25%",
                "train-only selection",
                "daily open-to-open execution assumption",
            ],
        ),
        "acceptance_standard": _acceptance_standard(),
        "acceptance_gate": _acceptance_gate(selected, validation, walk_forward),
        "pass_status": pass_status,
        "data_profile": dataset.data_profile,
        "research_cost": {
            "candidate_count": len(params_grid),
            "estimated_total_backtest_passes": len(params_grid) * 3
            + len(params_grid) * len(_walk_forward_boundaries()),
        },
        "runtime_seconds": runtime_payload(started_at, stages),
        "candidates": [_candidate_payload(row, rank) for rank, row in enumerate(candidates, 1)],
        "walk_forward": walk_forward,
        "validation_windows": validation,
        "references": [
            {
                "title": "Time Series Momentum",
                "authors": "Moskowitz, Ooi, Pedersen",
                "url": "https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2089463",
                "used_for": "trend persistence and momentum timing hypothesis",
            },
            {
                "title": "Momentum Has Its Moments",
                "authors": "Barroso, Santa-Clara",
                "url": "https://doi.org/10.1016/j.jfineco.2014.11.010",
                "used_for": "volatility-managed momentum risk control hypothesis",
            },
        ],
    }
    write_json(json_path, payload)
    _write_markdown(report_path, json_path, payload)
    return WideRouterResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_route_label=str(selected["params"].label),
        research_pass=bool(pass_status["research_pass"]),
        paper_ready_pass=bool(pass_status["paper_ready_pass"]),
    )


def _daily_cache_available(
    root: Path,
    symbols: list[str],
    benchmark_symbol: str,
    market_symbol: str,
) -> bool:
    required = list(dict.fromkeys([*symbols, benchmark_symbol.upper(), market_symbol.upper()]))
    return all(
        (root / "data" / "cache" / f"{symbol.lower()}_daily_iex.csv").exists()
        for symbol in required
    )


def _load_daily_cache_dataset(
    *,
    root: Path,
    symbols: list[str],
    start: str | None,
    end: str | None,
    benchmark_symbol: str,
    market_symbol: str,
) -> _DailyHybridDataset:
    required = list(dict.fromkeys([*symbols, benchmark_symbol.upper(), market_symbol.upper()]))
    bars: dict[str, dict[str, _DailyBars]] = {}
    profiles: list[dict[str, Any]] = []
    for symbol in required:
        path = root / "data" / "cache" / f"{symbol.lower()}_daily_iex.csv"
        frame = pd.read_csv(path)
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
        frame = _filter_time_window(frame, start, end)
        profiles.append(
            frame_data_profile(
                frame,
                symbol=symbol,
                timeframe="daily",
                provider="alpaca",
                feed="iex",
                source_mode="cache",
                path=path,
            )
        )
        bars[symbol] = _daily_cache_days(frame)
    common_dates = sorted(set.intersection(*(set(bars[symbol]) for symbol in required)))
    if len(common_dates) < 120:
        raise ValueError("wide router requires at least 120 common daily cache sessions")
    frame = _daily_frame_from_intraday(bars, common_dates, required)
    return _DailyHybridDataset(
        symbols=symbols,
        benchmark_symbol=benchmark_symbol.upper(),
        market_symbol=market_symbol.upper(),
        dates=list(frame["date"].astype(str)),
        frame=frame,
        data_profile=combined_data_profile(profiles),
    )


def _daily_cache_days(frame: pd.DataFrame) -> dict[str, _DailyBars]:
    days: dict[str, _DailyBars] = {}
    data = frame.copy().sort_values("timestamp").reset_index(drop=True)
    for _, row in data.iterrows():
        date = pd.Timestamp(row["timestamp"]).tz_convert("America/New_York").date().isoformat()
        days[date] = _DailyBars(
            timestamps=[row["timestamp"]],
            opens=pd.Series([row["open"]]).to_numpy(dtype=float),
            closes=pd.Series([row["close"]]).to_numpy(dtype=float),
            volumes=pd.Series([row["volume"]]).to_numpy(dtype=float),
        )
    return days


def _wide_params_grid() -> list[HybridRouterParams]:
    return _build_hybrid_params_grid(
        holding_modes=["open_to_open"],
        momentum_lookback_days=[60, 90],
        top_n_values=[8, 10],
        market_sma_days=[50],
        min_momentum_pct=[0.0],
        max_position_weight=[0.10],
        gross_exposure_limit=[0.70],
        momentum_score_mode=["raw"],
        risk_adjustment_lookback_days=[None],
        market_below_sma_scale=[0.25, 0.5],
        volatility_lookback_days=[20],
        target_volatility_annual_pct=[30.0, 35.0],
        market_drawdown_lookback_days=[60],
        market_drawdown_brake_pct=[12.0],
        brake_exposure_scale=[0.5],
        max_candidates=48,
    )


def _score_candidates(
    spec,
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params_grid: list[HybridRouterParams],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    train_start = _index_for_date(dataset, "2022-01-03")
    train_end = _index_for_date(dataset, "2024-12-31", side="right")
    oos_start = _index_for_date(dataset, "2025-01-01")
    oos_end = _index_for_date(dataset, "2025-12-31", side="right")
    full_start = train_start
    full_end = _index_for_date(dataset, "2026-05-18", side="right")
    for params in params_grid:
        train = _fast_backtest(
            spec,
            dataset,
            cache,
            params,
            start_index=max(train_start, _effective_lookback(params)),
            end_index=train_end,
        )
        oos = _fast_backtest(
            spec,
            dataset,
            cache,
            params,
            start_index=max(oos_start, _effective_lookback(params)),
            end_index=oos_end,
        )
        full = _fast_backtest(
            spec,
            dataset,
            cache,
            params,
            start_index=max(full_start, _effective_lookback(params)),
            end_index=full_end,
        )
        train_windows = [
            _fast_backtest(
                spec,
                dataset,
                cache,
                params,
                start_index=max(_index_for_date(dataset, start), _effective_lookback(params)),
                end_index=_index_for_date(dataset, end, side="right"),
            )
            for start, end in [
                ("2022-01-03", "2022-12-30"),
                ("2023-01-03", "2023-12-29"),
                ("2024-01-02", "2024-12-31"),
            ]
        ]
        rows.append(
            {
                "params": params,
                "score": _train_score(train, train_windows),
                "train": train,
                "out_of_sample": oos,
                "full_window": full,
                "train_windows": [item.__dict__ for item in train_windows],
                "quality_flags": _quality_flags(train, oos, full),
            }
        )
    rows.sort(key=lambda row: float(row["score"]), reverse=True)
    return rows


def _train_score(
    metrics: HybridRouterMetrics,
    train_windows: list[HybridRouterMetrics] | None = None,
) -> float:
    annualized = metrics.annualized_return_pct or -100.0
    qqq_alpha = metrics.alpha_vs_market_buy_hold_annualized_pct or -100.0
    ew_alpha = metrics.alpha_vs_equal_weight_buy_hold_annualized_pct or -100.0
    sharpe = metrics.sharpe_ratio or 0.0
    drawdown = abs(min(metrics.max_drawdown_pct, 0.0))
    trade_penalty = max(0, 90 - metrics.traded_days) * 0.25
    high_sharpe_penalty = max(0.0, sharpe - 2.5) * 30.0
    score = annualized + 0.7 * qqq_alpha + 0.4 * ew_alpha + 8 * sharpe - 0.8 * drawdown
    score -= trade_penalty + high_sharpe_penalty
    if train_windows:
        negative_years = sum((item.annualized_return_pct or -100.0) <= 0 for item in train_windows)
        weak_years = sum((item.sharpe_ratio or -100.0) < 0.4 for item in train_windows)
        worst_drawdown = min(item.max_drawdown_pct for item in train_windows)
        score -= negative_years * 45
        score -= weak_years * 15
        score -= max(0.0, abs(min(worst_drawdown, 0.0)) - 20.0) * 2.0
    if annualized < 8:
        score -= 100
    if qqq_alpha <= 0:
        score -= 100
    if ew_alpha <= 0:
        score -= 50
    if metrics.max_drawdown_pct <= -25:
        score -= 150
    if metrics.max_gross_exposure_pct > 75:
        score -= 100
    if metrics.max_symbol_weight_pct > 25:
        score -= 100
    return score


def _validation_windows(
    spec,
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
):
    rows = []
    for name, start, end in _validation_boundaries():
        metrics = _metrics_for_window(spec, dataset, cache, params, start, end)
        rows.append(
            {"name": name, "requested_start": start, "requested_end": end} | metrics.__dict__
        )
    return rows


def _walk_forward(
    spec,
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params_grid: list[HybridRouterParams],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for fold, train_start, train_end, test_start, test_end in _walk_forward_boundaries():
        scored = []
        for params in params_grid:
            train = _metrics_for_window(spec, dataset, cache, params, train_start, train_end)
            scored.append((_train_score(train, [train]), params, train))
        scored.sort(key=lambda item: item[0], reverse=True)
        score, params, train = scored[0]
        test = _metrics_for_window(spec, dataset, cache, params, test_start, test_end)
        rows.append(
            {
                "fold": fold,
                "params": params.__dict__ | {"label": params.label},
                "score": score,
                "train": train.__dict__,
                "test": test.__dict__,
            }
        )
    return rows


def _metrics_for_window(
    spec,
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
    start: str,
    end: str,
) -> HybridRouterMetrics:
    return _fast_backtest(
        spec,
        dataset,
        cache,
        params,
        start_index=max(_index_for_date(dataset, start), _effective_lookback(params)),
        end_index=_index_for_date(dataset, end, side="right"),
    )


def _build_fast_cache(dataset: _DailyHybridDataset) -> dict[str, Any]:
    frame = dataset.frame
    symbols = dataset.symbols
    close = pd.DataFrame({symbol: frame[f"{symbol}_close"].astype(float) for symbol in symbols})
    open_ = pd.DataFrame({symbol: frame[f"{symbol}_open"].astype(float) for symbol in symbols})
    next_open = open_.shift(-1)
    cost_rate = 0.0
    open_to_open_returns = (next_open / open_) - 1.0
    open_to_close_returns = (close / open_) - 1.0
    market_close = frame[f"{dataset.market_symbol}_close"].astype(float)
    benchmark_open = frame[f"{dataset.benchmark_symbol}_open"].astype(float)
    benchmark_close = frame[f"{dataset.benchmark_symbol}_close"].astype(float)
    market_open = frame[f"{dataset.market_symbol}_open"].astype(float)
    return {
        "close": close,
        "close_np": close.to_numpy(dtype=float),
        "open": open_,
        "open_to_open_returns": open_to_open_returns,
        "open_to_open_returns_np": open_to_open_returns.to_numpy(dtype=float),
        "open_to_close_returns": open_to_close_returns,
        "open_to_close_returns_np": open_to_close_returns.to_numpy(dtype=float),
        "market_close": market_close,
        "market_close_np": market_close.to_numpy(dtype=float),
        "benchmark_open": benchmark_open,
        "benchmark_close": benchmark_close,
        "market_open": market_open,
        "cost_rate": cost_rate,
        "vol_cache": {},
        "momentum_cache": {},
        "momentum_np_cache": {},
        "sma_cache": {},
        "market_sma_np_cache": {},
        "market_vol_np_cache": {},
        "symbol_vol_np_cache": {},
    }


def _fast_backtest(
    spec,
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
    *,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
) -> HybridRouterMetrics:
    start_index = max(start_index, _effective_lookback(params))
    end_index = min(
        end_index,
        len(dataset.frame) - (1 if params.holding_mode == "open_to_open" else 0),
    )
    returns: list[float] = []
    selected_counts: list[int] = []
    gross_exposures: list[float] = []
    max_symbol_weights: list[float] = []
    equity_curve = [start_equity]
    equity = start_equity
    traded_days = 0
    round_trips = 0
    skipped_days = 0
    market_regime_scaled_days = 0
    volatility_scaled_days = 0
    market_drawdown_brake_days = 0
    max_symbol_weight = min(
        params.max_position_weight,
        spec.portfolio.max_symbol_weight or spec.risk.max_position_weight,
        spec.risk.max_position_weight,
    )
    gross_limit = min(
        params.gross_exposure_limit,
        spec.portfolio.gross_exposure_limit or params.gross_exposure_limit,
    )
    effective_top_n = min(
        params.top_n,
        spec.portfolio.max_symbols_per_day or params.top_n,
        spec.risk.max_trades_per_day,
    )
    holding_returns = (
        cache["open_to_open_returns_np"]
        if params.holding_mode == "open_to_open"
        else cache["open_to_close_returns_np"]
    )
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    for index in range(start_index, end_index):
        selected = _fast_selected_symbols(dataset, cache, params, index, effective_top_n)
        vol_scale = _fast_volatility_scale(dataset, cache, params, index)
        regime_scale = _fast_regime_scale(dataset, cache, params, index)
        drawdown_scale = _fast_drawdown_scale(dataset, cache, params, index)
        if vol_scale < 0.999999:
            volatility_scaled_days += 1
        if regime_scale < 0.999999:
            market_regime_scaled_days += 1
        if drawdown_scale < 0.999999:
            market_drawdown_brake_days += 1
        effective_gross = gross_limit * vol_scale * regime_scale * drawdown_scale
        if not selected or effective_gross <= 0:
            strategy_return = 0.0
            gross_exposure = 0.0
            max_weight = 0.0
            skipped_days += 1
        else:
            per_symbol = min(max_symbol_weight, effective_gross / len(selected))
            day_returns = holding_returns[index, selected]
            strategy_return = float(np.nansum(day_returns * per_symbol))
            strategy_return -= len(selected) * per_symbol * cost_rate * 2
            gross_exposure = per_symbol * len(selected)
            max_weight = per_symbol
            traded_days += 1
            round_trips += len(selected)
        selected_counts.append(len(selected))
        gross_exposures.append(gross_exposure)
        max_symbol_weights.append(max_weight)
        returns.append(strategy_return)
        equity *= 1 + strategy_return
        equity_curve.append(equity)
    period_dates = dataset.dates[start_index:end_index]
    total_return_pct = (equity / start_equity - 1) * 100
    benchmark_buy_hold = _fast_buy_hold(
        dataset,
        cache,
        dataset.benchmark_symbol,
        start_index,
        end_index,
    )
    market_buy_hold = _fast_buy_hold(dataset, cache, dataset.market_symbol, start_index, end_index)
    equal_weight_buy_hold = sum(
        _fast_buy_hold(dataset, cache, symbol, start_index, end_index) for symbol in dataset.symbols
    ) / max(len(dataset.symbols), 1)
    universe_returns = {
        symbol: _fast_buy_hold(dataset, cache, symbol, start_index, end_index)
        for symbol in dataset.symbols
    }
    best_symbol = max(universe_returns, key=universe_returns.get) if universe_returns else None
    best_return = universe_returns[best_symbol] if best_symbol else 0.0
    annualized = _annualized_from_total(total_return_pct, len(returns))
    benchmark_annualized = _annualized_from_total(benchmark_buy_hold, len(returns))
    market_annualized = _annualized_from_total(market_buy_hold, len(returns))
    equal_weight_annualized = _annualized_from_total(equal_weight_buy_hold, len(returns))
    return HybridRouterMetrics(
        days=len(returns),
        start_date=period_dates[0] if period_dates else None,
        end_date=period_dates[-1] if period_dates else None,
        total_return_pct=total_return_pct,
        annualized_return_pct=annualized,
        sharpe_ratio=_daily_sharpe(returns),
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        traded_days=traded_days,
        round_trips=round_trips,
        average_selected_count=(
            sum(selected_counts) / len(selected_counts) if selected_counts else 0.0
        ),
        win_day_pct=_win_pct(returns),
        benchmark_symbol=dataset.benchmark_symbol,
        benchmark_buy_hold_return_pct=benchmark_buy_hold,
        benchmark_buy_hold_annualized_pct=benchmark_annualized,
        alpha_vs_benchmark_buy_hold_annualized_pct=_alpha(annualized, benchmark_annualized),
        market_symbol=dataset.market_symbol,
        market_buy_hold_return_pct=market_buy_hold,
        market_buy_hold_annualized_pct=market_annualized,
        alpha_vs_market_buy_hold_annualized_pct=_alpha(annualized, market_annualized),
        equal_weight_buy_hold_return_pct=equal_weight_buy_hold,
        equal_weight_buy_hold_annualized_pct=equal_weight_annualized,
        alpha_vs_equal_weight_buy_hold_annualized_pct=_alpha(annualized, equal_weight_annualized),
        best_symbol_buy_hold_pct=best_return,
        best_symbol=best_symbol,
        alpha_vs_best_symbol_buy_hold_pct=total_return_pct - best_return,
        exposure_pct=(traded_days / len(returns) * 100) if returns else 0.0,
        skipped_days=skipped_days,
        average_gross_exposure_pct=(
            sum(gross_exposures) / len(gross_exposures) * 100 if gross_exposures else 0.0
        ),
        max_gross_exposure_pct=max(gross_exposures) * 100 if gross_exposures else 0.0,
        max_symbol_weight_pct=max(max_symbol_weights) * 100 if max_symbol_weights else 0.0,
        market_regime_scaled_days=market_regime_scaled_days,
        volatility_scaled_days=volatility_scaled_days,
        market_drawdown_brake_days=market_drawdown_brake_days,
    )


def _fast_selected_symbols(
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
    index: int,
    top_n: int,
) -> list[int]:
    regime_scale = _fast_regime_scale(dataset, cache, params, index)
    if (
        params.market_sma_days is not None
        and params.market_below_sma_scale <= 0
        and regime_scale <= 0
    ):
        return []
    key = params.momentum_lookback_days
    momentum_cache = cache["momentum_np_cache"]
    if key not in momentum_cache:
        close = cache["close_np"]
        momentum = np.full_like(close, np.nan, dtype=float)
        momentum[key:, :] = (close[key:, :] / close[:-key, :] - 1.0) * 100
        momentum_cache[key] = momentum
    scores = momentum_cache[key][index - 1].copy()
    scores[~np.isfinite(scores)] = -np.inf
    scores[scores < params.min_momentum_pct] = -np.inf
    if params.momentum_score_mode == "risk_adjusted":
        vol = _symbol_volatility_array(cache, params.risk_adjustment_lookback_days or 20)
        denom = vol[index - 1]
        with np.errstate(divide="ignore", invalid="ignore"):
            scores = scores / denom
        scores[~np.isfinite(scores)] = -np.inf
    finite = np.isfinite(scores)
    if not finite.any():
        return []
    count = min(top_n, int(finite.sum()))
    if count <= 0:
        return []
    selected = np.argpartition(scores, -count)[-count:]
    selected = selected[np.argsort(scores[selected])[::-1]]
    return [int(item) for item in selected if np.isfinite(scores[item])]


def _fast_volatility_scale(
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
    index: int,
) -> float:
    if not params.volatility_lookback_days or not params.target_volatility_annual_pct:
        return 1.0
    vol = _market_volatility_array(cache, params.volatility_lookback_days)
    value = float(vol[index - 1]) if index > 0 else 0.0
    if value <= 0 or not np.isfinite(value):
        return 1.0
    return max(0.0, min(1.0, params.target_volatility_annual_pct / value))


def _fast_regime_scale(
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
    index: int,
) -> float:
    if params.market_sma_days is None:
        return 1.0
    if index < params.market_sma_days:
        return 0.0
    sma = _market_sma_array(cache, params.market_sma_days)
    latest = float(cache["market_close_np"][index - 1])
    value = float(sma[index - 1])
    if not np.isfinite(value):
        return 0.0
    return 1.0 if latest > value else params.market_below_sma_scale


def _fast_drawdown_scale(
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    params: HybridRouterParams,
    index: int,
) -> float:
    if not params.market_drawdown_lookback_days or not params.market_drawdown_brake_pct:
        return 1.0
    lookback = params.market_drawdown_lookback_days
    if index - lookback < 0:
        return 1.0
    close = cache["market_close_np"]
    window = close[index - lookback : index]
    peak = float(np.nanmax(window))
    latest = float(close[index - 1])
    if peak <= 0:
        return 1.0
    drawdown_pct = (latest / peak - 1.0) * 100
    return params.brake_exposure_scale if drawdown_pct <= -params.market_drawdown_brake_pct else 1.0


def _market_volatility_series(cache: dict[str, Any], lookback: int) -> pd.Series:
    vol_cache = cache["vol_cache"]
    key = ("market", lookback)
    if key not in vol_cache:
        vol_cache[key] = (
            cache["market_close"].pct_change().rolling(max(2, lookback - 1), min_periods=2).std()
            * (252**0.5)
            * 100
        )
    return vol_cache[key]


def _market_volatility_array(cache: dict[str, Any], lookback: int) -> np.ndarray:
    vol_cache = cache["market_vol_np_cache"]
    if lookback not in vol_cache:
        vol_cache[lookback] = _market_volatility_series(cache, lookback).to_numpy(dtype=float)
    return vol_cache[lookback]


def _symbol_volatility_frame(cache: dict[str, Any], lookback: int) -> pd.DataFrame:
    vol_cache = cache["vol_cache"]
    key = ("symbols", lookback)
    if key not in vol_cache:
        vol_cache[key] = (
            cache["close"].pct_change().rolling(max(2, lookback - 1), min_periods=2).std()
            * (252**0.5)
            * 100
        )
    return vol_cache[key]


def _symbol_volatility_array(cache: dict[str, Any], lookback: int) -> np.ndarray:
    vol_cache = cache["symbol_vol_np_cache"]
    if lookback not in vol_cache:
        vol_cache[lookback] = _symbol_volatility_frame(cache, lookback).to_numpy(dtype=float)
    return vol_cache[lookback]


def _market_sma_series(cache: dict[str, Any], lookback: int) -> pd.Series:
    sma_cache = cache["sma_cache"]
    if lookback not in sma_cache:
        sma_cache[lookback] = cache["market_close"].rolling(lookback, min_periods=lookback).mean()
    return sma_cache[lookback]


def _market_sma_array(cache: dict[str, Any], lookback: int) -> np.ndarray:
    sma_cache = cache["market_sma_np_cache"]
    if lookback not in sma_cache:
        sma_cache[lookback] = _market_sma_series(cache, lookback).to_numpy(dtype=float)
    return sma_cache[lookback]


def _fast_buy_hold(
    dataset: _DailyHybridDataset,
    cache: dict[str, Any],
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    if end_index <= start_index:
        return 0.0
    if symbol == dataset.benchmark_symbol:
        start = float(cache["benchmark_open"].iloc[start_index])
        end = float(cache["benchmark_close"].iloc[end_index - 1])
    elif symbol == dataset.market_symbol:
        start = float(cache["market_open"].iloc[start_index])
        end = float(cache["market_close"].iloc[end_index - 1])
    else:
        start = float(cache["open"][symbol].iloc[start_index])
        end = float(cache["close"][symbol].iloc[end_index - 1])
    return ((end / start) - 1.0) * 100 if start > 0 else 0.0


def _pass_status(
    selected: dict[str, Any],
    validation: list[dict[str, Any]],
    walk_forward: list[dict[str, Any]],
    dataset: _DailyHybridDataset,
) -> dict[str, Any]:
    gate = _acceptance_gate(selected, validation, walk_forward)
    research_pass = all(bool(value) for value in gate["conditions"].values())
    blockers = [
        "current-constituent universe is not point-in-time membership",
        "Alpaca IEX/cache is research evidence, not consolidated paper-ready market evidence",
        "paper_auto activation still requires readiness report and explicit user confirmation",
    ]
    if any(symbol in {"ARM", "CEG"} for symbol in dataset.symbols):
        blockers.append("later-listed symbols shorten common-history robustness unless excluded")
    return {
        "workflow_pass": True,
        "research_pass": research_pass,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "paper_ready_blockers": blockers,
    }


def _acceptance_gate(
    selected: dict[str, Any],
    validation: list[dict[str, Any]],
    walk_forward: list[dict[str, Any]],
) -> dict[str, Any]:
    train = selected["train"]
    oos = selected["out_of_sample"]
    full = selected["full_window"]
    by_name = {row["name"]: row for row in validation}
    ytd = by_name.get("ytd_2026", {})
    positive_wf = sum((row["test"]["annualized_return_pct"] or -100.0) > 0 for row in walk_forward)
    catastrophic_wf = any(
        (row["test"]["max_drawdown_pct"] or -100.0) <= -25 for row in walk_forward
    )
    conditions = {
        "train_annualized_at_least_15": (train.annualized_return_pct or -100.0) >= 15.0,
        "train_alpha_vs_qqq_positive": (train.alpha_vs_market_buy_hold_annualized_pct or -100.0)
        > 0,
        "oos_2025_annualized_at_least_8": (oos.annualized_return_pct or -100.0) >= 8.0,
        "oos_2025_sharpe_band": 0.7 <= (oos.sharpe_ratio or -100.0) <= 2.5,
        "oos_2025_drawdown_controlled": oos.max_drawdown_pct > -25.0,
        "full_annualized_at_least_15": (full.annualized_return_pct or -100.0) >= 15.0,
        "full_alpha_vs_qqq_positive": (full.alpha_vs_market_buy_hold_annualized_pct or -100.0) > 0,
        "full_alpha_vs_equal_weight_positive": (
            full.alpha_vs_equal_weight_buy_hold_annualized_pct or -100.0
        )
        > 0,
        "full_drawdown_controlled": full.max_drawdown_pct > -25.0,
        "ytd_2026_positive": (ytd.get("annualized_return_pct") or -100.0) > 0,
        "max_symbol_weight_ok": max(row["max_symbol_weight_pct"] for row in validation) <= 25.0,
        "max_gross_ok": max(row["max_gross_exposure_pct"] for row in validation) <= 70.0,
        "walk_forward_majority_positive": positive_wf >= max(1, len(walk_forward) // 2 + 1),
        "walk_forward_no_catastrophic_fold": not catastrophic_wf,
    }
    return {
        "passed": all(conditions.values()),
        "conditions": conditions,
        "selected_route": selected["params"].label,
        "train": _gate_metrics(train),
        "out_of_sample_2025": _gate_metrics(oos),
        "full_window": _gate_metrics(full),
        "walk_forward_positive_tests": positive_wf,
        "walk_forward_tests": len(walk_forward),
    }


def _quality_flags(
    train: HybridRouterMetrics,
    oos: HybridRouterMetrics,
    full: HybridRouterMetrics,
) -> list[str]:
    flags: list[str] = []
    if (train.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("train_no_alpha_vs_qqq")
    if (oos.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("oos_no_alpha_vs_qqq")
    if (full.alpha_vs_market_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_qqq")
    if (full.alpha_vs_equal_weight_buy_hold_annualized_pct or -100.0) <= 0:
        flags.append("full_no_alpha_vs_equal_weight")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.7:
        flags.append("oos_low_sharpe")
    if (train.sharpe_ratio or 0.0) > 2.5 or (oos.sharpe_ratio or 0.0) > 2.5:
        flags.append("suspiciously_high_sharpe_review_overfit")
    if full.max_drawdown_pct <= -25:
        flags.append("full_large_drawdown")
    if full.alpha_vs_best_symbol_buy_hold_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    return flags


def _candidate_payload(row: dict[str, Any], rank: int) -> dict[str, Any]:
    return {
        "rank": rank,
        "params": row["params"].__dict__ | {"label": row["params"].label},
        "score": row["score"],
        "quality_flags": row["quality_flags"],
        "train": row["train"].__dict__,
        "out_of_sample": row["out_of_sample"].__dict__,
        "full_window": row["full_window"].__dict__,
        "train_windows": row.get("train_windows", []),
    }


def _gate_metrics(metrics: HybridRouterMetrics) -> dict[str, Any]:
    return {
        "start_date": metrics.start_date,
        "end_date": metrics.end_date,
        "annualized_return_pct": metrics.annualized_return_pct,
        "sharpe_ratio": metrics.sharpe_ratio,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "alpha_vs_qqq_annualized_pct": metrics.alpha_vs_market_buy_hold_annualized_pct,
        "alpha_vs_equal_weight_annualized_pct": (
            metrics.alpha_vs_equal_weight_buy_hold_annualized_pct
        ),
        "round_trips": metrics.round_trips,
        "average_gross_exposure_pct": metrics.average_gross_exposure_pct,
        "max_gross_exposure_pct": metrics.max_gross_exposure_pct,
        "max_symbol_weight_pct": metrics.max_symbol_weight_pct,
    }


def _acceptance_standard() -> dict[str, Any]:
    return {
        "train_window": "2022-2024 selects route",
        "oos_window": "2025 validation only",
        "full_annualized_return_pct": ">= 15",
        "oos_2025_annualized_return_pct": ">= 8",
        "full_alpha_vs_qqq_buy_hold_annualized_pct": "> 0",
        "full_alpha_vs_equal_weight_buy_hold_annualized_pct": "> 0",
        "max_drawdown_pct": "> -25",
        "sharpe_ratio": "0.7 to 2.5 preferred; >2.5 overfit review",
        "max_symbol_weight_pct": "<= 25",
        "max_gross_exposure_pct": "<= 75",
        "paper_ready_pass": False,
    }


def _validation_boundaries() -> list[tuple[str, str, str]]:
    return [
        ("calendar_2022", "2022-01-03", "2022-12-30"),
        ("calendar_2023", "2023-01-03", "2023-12-29"),
        ("calendar_2024", "2024-01-02", "2024-12-31"),
        ("calendar_2025", "2025-01-02", "2025-12-31"),
        ("ytd_2026", "2026-01-02", "2026-05-18"),
        ("full_2022_2026", "2022-01-03", "2026-05-18"),
    ]


def _walk_forward_boundaries() -> list[tuple[str, str, str, str, str]]:
    return [
        ("fold_1", "2022-01-03", "2022-12-30", "2023-01-03", "2023-12-29"),
        ("fold_2", "2022-01-03", "2023-12-29", "2024-01-02", "2024-12-31"),
        ("fold_3", "2022-01-03", "2024-12-31", "2025-01-02", "2025-12-31"),
        ("fold_4", "2022-01-03", "2025-12-31", "2026-01-02", "2026-05-18"),
    ]


def _index_for_date(dataset: _DailyHybridDataset, date: str, *, side: str = "left") -> int:
    dates = list(dataset.dates)
    if side == "right":
        return next((index for index, value in enumerate(dates) if value > date), len(dates))
    return next((index for index, value in enumerate(dates) if value >= date), len(dates))


def _write_markdown(path: Path, json_path: Path, payload: dict[str, Any]) -> None:
    best = payload["candidates"][0]
    gate = payload["acceptance_gate"]
    lines = [
        f"# Wide NASDAQ Daily Hybrid Router: {payload['strategy_name']}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Selected route: `{gate['selected_route']}`",
        f"- Research pass: `{payload['pass_status']['research_pass']}`",
        f"- Paper ready pass: `{payload['pass_status']['paper_ready_pass']}`",
        f"- Selection policy: `{payload['selection_policy']}`",
        f"- Universe size: `{len(payload['symbols'])}`",
        "",
        "## Acceptance",
        "",
    ]
    for key, value in gate["conditions"].items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(
        [
            "",
            "## Selected Metrics",
            "",
            f"- Train annualized / Sharpe / max DD: "
            f"`{_fmt(best['train']['annualized_return_pct'])}%` / "
            f"`{_fmt(best['train']['sharpe_ratio'])}` / "
            f"`{_fmt(best['train']['max_drawdown_pct'])}%`",
            f"- 2025 OOS annualized / Sharpe / max DD: "
            f"`{_fmt(best['out_of_sample']['annualized_return_pct'])}%` / "
            f"`{_fmt(best['out_of_sample']['sharpe_ratio'])}` / "
            f"`{_fmt(best['out_of_sample']['max_drawdown_pct'])}%`",
            f"- Full annualized / Sharpe / max DD: "
            f"`{_fmt(best['full_window']['annualized_return_pct'])}%` / "
            f"`{_fmt(best['full_window']['sharpe_ratio'])}` / "
            f"`{_fmt(best['full_window']['max_drawdown_pct'])}%`",
            f"- Full Alpha vs QQQ / equal-weight annualized: "
            f"`{_fmt(best['full_window']['alpha_vs_market_buy_hold_annualized_pct'])}%` / "
            f"`{_fmt(best['full_window']['alpha_vs_equal_weight_buy_hold_annualized_pct'])}%`",
            f"- Round trips full window: `{best['full_window']['round_trips']}`",
            f"- Max gross / max symbol weight: "
            f"`{_fmt(best['full_window']['max_gross_exposure_pct'])}%` / "
            f"`{_fmt(best['full_window']['max_symbol_weight_pct'])}%`",
            "",
            "## Validation Windows",
            "",
            "| Window | Dates | Ann. | Sharpe | Max DD | Alpha vs QQQ | "
            "Alpha vs EW | Round Trips |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["validation_windows"]:
        lines.append(
            f"| {row['name']} | {row.get('start_date')} -> {row.get('end_date')} | "
            f"{_fmt(row.get('annualized_return_pct'))}% | {_fmt(row.get('sharpe_ratio'))} | "
            f"{_fmt(row.get('max_drawdown_pct'))}% | "
            f"{_fmt(row.get('alpha_vs_market_buy_hold_annualized_pct'))}% | "
            f"{_fmt(row.get('alpha_vs_equal_weight_buy_hold_annualized_pct'))}% | "
            f"{row.get('round_trips')} |"
        )
    lines.extend(
        [
            "",
            "## Risk Review",
            "",
            "- This is not paper-ready while current-constituent and IEX/cache blockers remain.",
            "- LLM/news is advisory only; no LLM alpha is claimed in this route.",
            "- Paper automation remains blocked until separate readiness and user confirmation.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    return f"{float(value):.2f}"


def _relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()
