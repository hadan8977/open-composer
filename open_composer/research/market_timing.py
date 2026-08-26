from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import prod
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

import pandas as pd
import yaml

from open_composer.adapters.data import fetch_ohlcv
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.json_utils import json_safe_sorted_values
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.iteration_dossier import require_iteration_execution_gate
from open_composer.research.metadata import (
    estimate_grid_research_cost,
    frame_data_profile,
    hypothesis_ledger,
    research_brief,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json

TimingObjective = Literal["primary_alpha"]
TimingProfile = Literal["risk_control_hold", "trend_pullback", "breakout_hold", "macd_trend"]


@dataclass(frozen=True)
class TimingParams:
    profile: TimingProfile
    fast_bars: int
    slow_bars: int
    exit_bars: int
    momentum_bars: int
    min_momentum_pct: float
    breakout_bars: int
    volume_bars: int
    stop_loss_pct: float
    take_profit_pct: float | None

    @property
    def label(self) -> str:
        take_profit = "none" if self.take_profit_pct is None else f"{self.take_profit_pct:g}"
        return (
            f"{self.profile}_f{self.fast_bars}_s{self.slow_bars}_x{self.exit_bars}_"
            f"mom{self.momentum_bars}_{self.min_momentum_pct:g}_bo{self.breakout_bars}_"
            f"vol{self.volume_bars}_sl{self.stop_loss_pct:g}_tp{take_profit}"
        )


@dataclass(frozen=True)
class TimingCandidate:
    rank: int
    params: TimingParams
    spec: StrategySpec
    score: float
    train: BacktestArtifacts
    out_of_sample: BacktestArtifacts
    full_window: BacktestArtifacts
    quality_flags: list[str]


@dataclass(frozen=True)
class TimingWalkForwardSlice:
    fold: int
    params: TimingParams
    train: BacktestArtifacts
    test: BacktestArtifacts


@dataclass(frozen=True)
class TimingResearchResult:
    report_path: Path
    json_path: Path
    selected_spec_path: Path | None
    candidates: list[TimingCandidate]
    walk_forward: list[TimingWalkForwardSlice]
    research_cost: dict[str, Any]
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> TimingCandidate:
        return self.candidates[0]


def run_market_timing_research(
    spec_path: Path,
    root: Path | None = None,
    symbol: str | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    profiles: list[TimingProfile] | None = None,
    fast_bars: list[int] | None = None,
    slow_bars: list[int] | None = None,
    exit_bars: list[int] | None = None,
    momentum_bars: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    breakout_bars: list[int] | None = None,
    volume_bars: list[int] | None = None,
    stop_loss_pct: list[float] | None = None,
    take_profit_pct: list[float | None] | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    max_candidates: int = 300,
    refresh_data: bool = False,
    start: str | None = None,
    end: str | None = None,
    write_best_spec: bool = True,
    walk_forward_top_k: int | None = None,
) -> TimingResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    stage_started = perf_counter()
    base = root or project_root()
    require_iteration_execution_gate(
        spec_path,
        base,
        enforce_unbound_design=True,
        require_registered_iteration=True,
    )
    source = load_strategy_spec(spec_path)
    selected_symbol = (symbol or source.primary_symbol).upper()
    selected_feed = feed or source.data.feed or data_feed()
    frame = fetch_ohlcv(
        root=base,
        symbol=selected_symbol,
        timeframe=source.timeframe,
        start=None,
        end=None,
        source=data_source,
        feed=selected_feed,
        use_cache=not refresh_data,
    )
    frame = _filter_time_window(_normalize_timestamps(frame), start, end)
    if frame.empty:
        raise ValueError("no OHLCV rows remained after applying the requested research window")
    data_profile = frame_data_profile(
        frame,
        symbol=selected_symbol,
        timeframe=source.timeframe,
        provider=data_source,
        feed=selected_feed,
        source_mode="cache" if not refresh_data else "live_fetch",
    )
    stages["load_data"] = perf_counter() - stage_started
    stage_started = perf_counter()

    params_grid = _build_timing_grid(
        profiles or ["risk_control_hold", "trend_pullback", "breakout_hold", "macd_trend"],
        fast_bars or [5, 13],
        slow_bars or [21, 34],
        exit_bars or [13, 21],
        momentum_bars or [3],
        min_momentum_pct or [0.0],
        breakout_bars or [10],
        volume_bars or [5],
        stop_loss_pct or [10.0],
        take_profit_pct or [None],
        max_candidates=max_candidates,
    )
    stages["build_grid"] = perf_counter() - stage_started
    stage_started = perf_counter()
    candidates = _evaluate_timing_candidates(
        source=source,
        frame=frame,
        symbol=selected_symbol,
        data_source=data_source,
        feed=selected_feed,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
        root=base,
    )
    stages["evaluate_candidates"] = perf_counter() - stage_started
    walk_forward_params = _walk_forward_params(
        params_grid=params_grid,
        candidates=candidates,
        walk_forward_top_k=walk_forward_top_k,
    )
    research_cost = estimate_grid_research_cost(
        candidate_count=len(params_grid),
        walk_forward_candidate_count=len(walk_forward_params),
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=walk_forward_folds,
    ).__dict__
    stage_started = perf_counter()
    walk_forward = _walk_forward_timing(
        source=source,
        frame=frame,
        symbol=selected_symbol,
        data_source=data_source,
        feed=selected_feed,
        params_grid=walk_forward_params,
        folds=walk_forward_folds,
        root=base,
    )
    stages["walk_forward"] = perf_counter() - stage_started
    selected_spec_path = _write_selected_spec(base, candidates[0].spec) if write_best_spec else None
    report_path = base / "reports" / "research" / f"{source.name}-market-timing-research.md"
    json_path = base / "reports" / "research" / f"{source.name}-market-timing-research.json"
    stages["write_reports"] = 0.0
    runtime_seconds = runtime_payload(started_at, stages)
    write_started = perf_counter()
    _write_timing_json(
        json_path,
        source,
        selected_symbol,
        start,
        end,
        candidates,
        walk_forward,
        selected_spec_path,
        research_cost,
        runtime_seconds,
        data_profile,
        params_grid,
    )
    _write_timing_report(
        report_path,
        json_path,
        source,
        selected_symbol,
        start,
        end,
        candidates,
        walk_forward,
        selected_spec_path,
        research_cost,
        runtime_seconds,
        data_profile,
    )
    stages["write_reports"] = perf_counter() - write_started
    runtime_seconds = runtime_payload(started_at, stages)
    _write_timing_json(
        json_path,
        source,
        selected_symbol,
        start,
        end,
        candidates,
        walk_forward,
        selected_spec_path,
        research_cost,
        runtime_seconds,
        data_profile,
        params_grid,
    )
    _write_timing_report(
        report_path,
        json_path,
        source,
        selected_symbol,
        start,
        end,
        candidates,
        walk_forward,
        selected_spec_path,
        research_cost,
        runtime_seconds,
        data_profile,
    )
    return TimingResearchResult(
        report_path=report_path,
        json_path=json_path,
        selected_spec_path=selected_spec_path,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=runtime_seconds,
        data_profile=data_profile,
    )


def _build_timing_grid(
    profiles: list[TimingProfile],
    fast_values: list[int],
    slow_values: list[int],
    exit_values: list[int],
    momentum_values: list[int],
    min_momentum_values: list[float],
    breakout_values: list[int],
    volume_values: list[int],
    stop_values: list[float],
    take_profit_values: list[float | None],
    *,
    max_candidates: int,
) -> list[TimingParams]:
    total = prod(
        [
            len(profiles),
            len(fast_values),
            len(slow_values),
            len(exit_values),
            len(momentum_values),
            len(min_momentum_values),
            len(breakout_values),
            len(volume_values),
            len(stop_values),
            len(take_profit_values),
        ]
    )
    if total > max_candidates:
        raise ValueError(
            f"market timing grid would create {total} candidates; "
            f"raise --max-candidates above {total} or narrow the grid"
        )
    params: list[TimingParams] = []
    for item in product(
        profiles,
        fast_values,
        slow_values,
        exit_values,
        momentum_values,
        min_momentum_values,
        breakout_values,
        volume_values,
        stop_values,
        take_profit_values,
    ):
        profile, fast, slow, exit_bar, momentum, min_momentum, breakout, volume, stop, take = item
        if fast >= slow:
            continue
        if exit_bar < fast:
            continue
        if min(fast, slow, exit_bar, momentum, breakout, volume) < 1:
            continue
        params.append(
            TimingParams(
                profile=profile,
                fast_bars=fast,
                slow_bars=slow,
                exit_bars=exit_bar,
                momentum_bars=momentum,
                min_momentum_pct=min_momentum,
                breakout_bars=breakout,
                volume_bars=volume,
                stop_loss_pct=stop,
                take_profit_pct=take,
            )
        )
    if not params:
        raise ValueError("market timing grid produced no valid candidates")
    return params


def _evaluate_timing_candidates(
    *,
    source: StrategySpec,
    frame: pd.DataFrame,
    symbol: str,
    data_source: str,
    feed: str,
    params_grid: list[TimingParams],
    out_of_sample_ratio: float,
    root: Path,
) -> list[TimingCandidate]:
    split = _split_index(frame, out_of_sample_ratio, _max_warmup(params_grid))
    rows: list[TimingCandidate] = []
    for index, params in enumerate(params_grid, start=1):
        spec = _candidate_spec(source, symbol, data_source, feed, params, index)
        train_frame = frame.iloc[:split].copy().reset_index(drop=True)
        oos_start = max(0, split - _warmup(params) - 1)
        oos_evaluation_start = split - oos_start
        oos_frame = frame.iloc[oos_start:].copy().reset_index(drop=True)
        train = backtest_frame(
            spec, train_frame, root=root, run_id_value=f"timing-train-{spec.name}"
        )
        oos = backtest_frame(
            spec,
            oos_frame,
            root=root,
            run_id_value=f"timing-oos-{spec.name}",
            evaluation_start_index=oos_evaluation_start,
        )
        full = backtest_frame(spec, frame, root=root, run_id_value=f"timing-full-{spec.name}")
        rows.append(
            TimingCandidate(
                rank=0,
                params=params,
                spec=spec,
                score=_score_timing_candidate(train),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=_quality_flags(train, oos, full),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        TimingCandidate(
            rank=rank,
            params=item.params,
            spec=item.spec,
            score=item.score,
            train=item.train,
            out_of_sample=item.out_of_sample,
            full_window=item.full_window,
            quality_flags=item.quality_flags,
        )
        for rank, item in enumerate(rows, start=1)
    ]


def _walk_forward_timing(
    *,
    source: StrategySpec,
    frame: pd.DataFrame,
    symbol: str,
    data_source: str,
    feed: str,
    params_grid: list[TimingParams],
    folds: int,
    root: Path,
) -> list[TimingWalkForwardSlice]:
    folds = max(folds, 1)
    max_warmup = _max_warmup(params_grid)
    fold_size = max((len(frame) - max_warmup) // (folds + 1), 2)
    slices: list[TimingWalkForwardSlice] = []
    for fold in range(1, folds + 1):
        test_start = max_warmup + fold * fold_size
        test_end = min(len(frame), test_start + fold_size)
        if test_end - test_start < 2:
            continue
        train_frame = frame.iloc[:test_start].copy().reset_index(drop=True)
        scored: list[tuple[float, TimingParams, StrategySpec, BacktestArtifacts]] = []
        for index, params in enumerate(params_grid, start=1):
            spec = _candidate_spec(source, symbol, data_source, feed, params, index)
            train = backtest_frame(
                spec,
                train_frame,
                root=root,
                run_id_value=f"timing-wf{fold}-train-{spec.name}",
            )
            scored.append((_score_timing_candidate(train), params, spec, train))
        scored.sort(key=lambda item: item[0], reverse=True)
        _, params, spec, train = scored[0]
        warm_start = max(0, test_start - _warmup(params) - 1)
        evaluation_start = test_start - warm_start
        test = backtest_frame(
            spec,
            frame.iloc[warm_start:test_end].copy().reset_index(drop=True),
            root=root,
            run_id_value=f"timing-wf{fold}-test-{spec.name}",
            evaluation_start_index=evaluation_start,
        )
        slices.append(TimingWalkForwardSlice(fold=fold, params=params, train=train, test=test))
    return slices


def _walk_forward_params(
    *,
    params_grid: list[TimingParams],
    candidates: list[TimingCandidate],
    walk_forward_top_k: int | None,
) -> list[TimingParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _candidate_spec(
    source: StrategySpec,
    symbol: str,
    data_source: str,
    feed: str,
    params: TimingParams,
    index: int,
) -> StrategySpec:
    raw = source.model_dump(mode="json")
    raw["name"] = f"{source.name}_timing_{index:03d}"
    raw["description"] = f"{source.description} Market timing candidate {index}."
    raw["universe"] = [symbol]
    raw["lifecycle"] = "draft"
    raw["factors"] = _candidate_factors(params)
    raw["entry"] = {"all": _entry_rules(params), "any": []}
    raw["exit"] = {"all": [], "any": _exit_rules(params)}
    raw["risk"] = {
        **raw["risk"],
        "max_trades_per_day": 1,
        "max_position_weight": 1.0,
        "stop_loss_pct": params.stop_loss_pct,
        "take_profit_pct": params.take_profit_pct,
    }
    raw["execution"] = {
        **raw["execution"],
        "backend": "python_reference",
        "mode": "manual_signal",
        "signal_on": "bar_close",
        "fill_assumption": "next_bar_open",
        "broker": "none",
    }
    raw["data"] = {"source": data_source, "symbol": symbol, "path": None, "feed": feed}
    raw["data_assumptions"] = {
        **raw.get("data_assumptions", {}),
        "source": data_source,
        "adjusted": True,
        "timezone": "America/New_York",
    }
    raw["required_capabilities"] = [
        "market.alpaca_bars" if data_source == "alpaca" else "market.longbridge_bars"
    ]
    raw["notes"] = {
        **raw.get("notes", {}),
        "market_timing_research": {
            "source_strategy": source.name,
            "params": params.__dict__,
            "anti_leakage": (
                "Rules use current and historical bars only; breakout levels are lagged "
                "and fills occur at the next bar open."
            ),
            "promotion_note": (
                "Research-only timing candidate; require OOS, fixed walk-forward, "
                "cost sensitivity, and data-source review before paper use."
            ),
        },
    }
    return StrategySpec.model_validate(raw)


def _candidate_factors(params: TimingParams) -> dict[str, dict[str, Any]]:
    fast = params.fast_bars
    slow = params.slow_bars
    exit_bar = params.exit_bars
    momentum = params.momentum_bars
    breakout = params.breakout_bars
    volume = params.volume_bars
    return {
        "trend_fast": {"source": "expression", "expression": f"ema(close, {fast})"},
        "trend_slow": {"source": "expression", "expression": f"ema(close, {slow})"},
        "exit_trend": {"source": "expression", "expression": f"ema(close, {exit_bar})"},
        "momentum": {"source": "expression", "expression": f"roc(close, {momentum})"},
        "prior_breakout": {
            "source": "expression",
            "expression": f"lag(highest(close, {breakout}), 1)",
        },
        "volume_floor": {"source": "expression", "expression": f"sma(volume, {volume})"},
        "macd_fast": {"source": "expression", "expression": "macd_hist(close, 8, 21, 5)"},
        "macd_slow": {"source": "expression", "expression": "macd_hist(close, 12, 26, 9)"},
    }


def _entry_rules(params: TimingParams) -> list[str]:
    if params.profile == "risk_control_hold":
        return ["close >= trend_slow"]
    common = [
        "close > trend_fast",
        "trend_fast > trend_slow",
        f"momentum >= {params.min_momentum_pct}",
    ]
    if params.profile == "trend_pullback":
        return [*common, "volume >= volume_floor"]
    if params.profile == "breakout_hold":
        return [*common, "close > prior_breakout", "volume >= volume_floor"]
    return [*common, "macd_fast > 0", "macd_slow > 0"]


def _exit_rules(params: TimingParams) -> list[str]:
    if params.profile == "risk_control_hold":
        return ["close < exit_trend"]
    if params.profile == "macd_trend":
        return ["close < exit_trend", "macd_slow < 0"]
    momentum_buffer = abs(params.min_momentum_pct)
    return ["close < exit_trend", f"momentum + {momentum_buffer:g} < 0"]


def _score_timing_candidate(artifacts: BacktestArtifacts) -> float:
    run = artifacts.run
    alpha = run.alpha_vs_buy_hold_pct or 0.0
    sharpe = run.sharpe_ratio or 0.0
    trade_bonus = min(run.trades, 20) * 0.1
    return alpha + sharpe * 10 + trade_bonus - max(0, run.signals - 80) * 0.2


def _quality_flags(
    train: BacktestArtifacts,
    oos: BacktestArtifacts,
    full: BacktestArtifacts,
) -> list[str]:
    flags: list[str] = []
    if train.run.trades < 2:
        flags.append("low_train_trade_count")
    if oos.run.trades < 1:
        flags.append("low_oos_trade_count")
    if (oos.run.alpha_vs_buy_hold_pct or 0.0) <= 0:
        flags.append("oos_no_alpha_vs_buy_hold")
    if oos.run.sharpe_ratio is None or oos.run.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if (full.run.alpha_vs_buy_hold_pct or 0.0) <= 0:
        flags.append("full_window_no_alpha_vs_buy_hold")
    if full.run.trades < 3:
        flags.append("full_window_low_trade_count")
    if train.run.sharpe_ratio and train.run.sharpe_ratio > 5 and oos.run.sharpe_ratio is not None:
        if oos.run.sharpe_ratio < train.run.sharpe_ratio * 0.35:
            flags.append("train_oos_sharpe_decay")
    return flags


def _write_selected_spec(root: Path, spec: StrategySpec) -> Path:
    output_path = root / "strategy_specs" / "drafts" / f"{spec.name}.yaml"
    ensure_dir(output_path.parent)
    output_path.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    return output_path


def _write_timing_json(
    path: Path,
    source: StrategySpec,
    symbol: str,
    start: str | None,
    end: str | None,
    candidates: list[TimingCandidate],
    walk_forward: list[TimingWalkForwardSlice],
    selected_spec_path: Path | None,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
    params_grid: list[TimingParams],
) -> Path:
    payload = {
        "strategy_name": source.name,
        "mode": "single_symbol_market_timing",
        "symbol": symbol,
        "research_window": {"start": start, "end": end},
        "data_profile": data_profile,
        "research_brief": research_brief(
            strategy_name=source.name,
            objective="same-symbol timing Alpha versus buy-and-hold",
            hypothesis=(
                "Point-in-time trend, breakout, volume, and risk controls can improve "
                "OOS Alpha versus holding the same symbol."
            ),
            constraints=[
                "Signals are confirmed at bar close and filled at next bar open.",
                "Breakout factors use lagged highest close.",
                "No LLM call is made inside the backtest loop.",
            ],
        ),
        "search_space": search_space(
            family="single_symbol_market_timing",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=["fast_bars < slow_bars", "exit_bars >= fast_bars"],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis="Timing rules improve OOS Alpha versus buy-and-hold.",
            visible_evidence=["training score", "OOS metrics", "walk-forward folds"],
            hidden_evidence=[],
            counterevidence=candidates[0].quality_flags,
            conclusion=(
                "passed" if _acceptance_gate(candidates[0], walk_forward)["passed"] else "failed"
            ),
        ),
        "research_cost": research_cost,
        "runtime_seconds": runtime_seconds,
        "selection_objective": (
            "train score prioritizes Alpha versus same-symbol buy-and-hold; "
            "OOS and fixed walk-forward are validation evidence"
        ),
        "selected_spec_path": str(selected_spec_path) if selected_spec_path else None,
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward),
        "assumptions": [
            "Signals are confirmed at bar close and filled at the next bar open.",
            "Breakout factors use lag(highest(close, n), 1) to avoid lookahead.",
            "No LLM is called inside the backtest loop.",
            "Best training score is not sufficient for promotion without OOS and walk-forward.",
        ],
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_forward_payload(item) for item in walk_forward],
    }
    return write_json(path, payload)


def _write_timing_report(
    path: Path,
    json_path: Path,
    source: StrategySpec,
    symbol: str,
    start: str | None,
    end: str | None,
    candidates: list[TimingCandidate],
    walk_forward: list[TimingWalkForwardSlice],
    selected_spec_path: Path | None,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Market Timing Research: {source.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Selected spec: `{selected_spec_path}`"
        if selected_spec_path
        else "- Selected spec: n/a",
        f"- Symbol: `{symbol}`",
        f"- Timeframe: `{source.timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Data source/feed: `{data_profile.get('provider') or 'unknown'}` / "
        f"`{data_profile.get('feed') or 'unknown'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        "- Objective: train score prioritizes Alpha versus same-symbol buy-and-hold.",
        "- OOS and fixed walk-forward are validation evidence, not selection data.",
        "- Signal timing: bar-close confirmation; next-bar-open fills.",
        "",
        "## Acceptance Gate",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _acceptance_gate(candidates[0], walk_forward).items()
        ],
        "",
        "## Research Cost",
        "",
        f"- Candidates evaluated: `{research_cost['candidate_count']}`",
        f"- Walk-forward candidates: `{research_cost['walk_forward_candidate_count']}`",
        f"- Walk-forward top-K filter: `{research_cost['walk_forward_top_k'] or 'off'}`",
        f"- Estimated backtest passes: `{research_cost['estimated_total_backtest_passes']}`",
        f"- Runtime total seconds: `{runtime_seconds['total']:.2f}`",
        "",
        "## Runtime Stages",
        "",
        *[f"- {stage}: `{seconds:.2f}s`" for stage, seconds in runtime_seconds["stages"].items()],
        "",
        "## Top Candidates",
        "",
    ]
    for item in candidates[:10]:
        flags = ", ".join(item.quality_flags) if item.quality_flags else "none"
        lines.extend(
            [
                f"### Rank {item.rank}: {item.params.label}",
                "",
                f"- Score: `{item.score:.2f}`",
                f"- Quality flags: `{flags}`",
                *_metric_lines("Train", item.train),
                *_metric_lines("Out of sample", item.out_of_sample),
                *_metric_lines("Full window", item.full_window),
                "",
            ]
        )
    lines.extend(["## Walk Forward", ""])
    if not walk_forward:
        lines.append("- No walk-forward slices were available.")
    for item in walk_forward:
        lines.extend(
            [
                f"### Fold {item.fold}: {item.params.label}",
                "",
                *_metric_lines("Train selected", item.train),
                *_metric_lines("Test", item.test),
                "",
            ]
        )
    lines.extend(
        [
            "## Overfit Notes",
            "",
            "- Candidate parameters are selected from training windows only.",
            "- Fixed walk-forward folds reselect parameters only from prior bars.",
            "- High training Sharpe with weak OOS Sharpe is flagged as decay.",
            "- A candidate that fails Alpha versus buy-and-hold in OOS is not acceptable "
            "for the requested objective even if full-window return looks high.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: TimingCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__,
        "score": candidate.score,
        "strategy_name": candidate.spec.name,
        "quality_flags": candidate.quality_flags,
        "train": _metrics_payload(candidate.train),
        "out_of_sample": _metrics_payload(candidate.out_of_sample),
        "full_window": _metrics_payload(candidate.full_window),
    }


def _walk_forward_payload(item: TimingWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__,
        "train": _metrics_payload(item.train),
        "test": _metrics_payload(item.test),
    }


def _metrics_payload(artifacts: BacktestArtifacts) -> dict[str, Any]:
    run = artifacts.run
    return {
        "bars": run.bars,
        "signals": run.signals,
        "trades": run.trades,
        "total_return_pct": run.total_return_pct,
        "buy_hold_return_pct": run.buy_hold_return_pct,
        "alpha_vs_buy_hold_pct": run.alpha_vs_buy_hold_pct,
        "annualized_return_pct": run.annualized_return_pct,
        "sharpe_ratio": run.sharpe_ratio,
        "total_fees": run.total_fees,
    }


def _acceptance_gate(
    candidate: TimingCandidate,
    walk_forward: list[TimingWalkForwardSlice],
) -> dict[str, Any]:
    oos_alpha = candidate.out_of_sample.run.alpha_vs_buy_hold_pct or 0.0
    wf_alphas = [item.test.run.alpha_vs_buy_hold_pct or 0.0 for item in walk_forward]
    positive_wf = sum(value > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    passed = (
        oos_alpha > 0
        and (candidate.out_of_sample.run.sharpe_ratio or 0.0) >= 0.5
        and candidate.out_of_sample.run.trades >= 3
        and wf_count > 0
        and positive_wf == wf_count
    )
    return {
        "passed": passed,
        "objective": "alpha_vs_same_symbol_buy_hold",
        "oos_alpha_vs_buy_hold_pct": oos_alpha,
        "oos_sharpe_ratio": candidate.out_of_sample.run.sharpe_ratio,
        "oos_trades": candidate.out_of_sample.run.trades,
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": wf_count,
        "quality_flags": candidate.quality_flags,
    }


def _metric_lines(label: str, artifacts: BacktestArtifacts) -> list[str]:
    run = artifacts.run
    return [
        f"- {label} return: `{run.total_return_pct:.2f}%`",
        f"- {label} buy-hold: `{_fmt(run.buy_hold_return_pct)}%`",
        f"- {label} Alpha vs buy-hold: `{_fmt(run.alpha_vs_buy_hold_pct)}%`",
        f"- {label} Sharpe: `{_fmt(run.sharpe_ratio)}`",
        f"- {label} signals/trades: `{run.signals}/{run.trades}`",
        f"- {label} bars: `{run.bars}`",
    ]


def _split_index(frame: pd.DataFrame, out_of_sample_ratio: float, max_warmup: int) -> int:
    split = int(len(frame) * (1 - out_of_sample_ratio))
    split = max(split, max_warmup + 3)
    return min(split, len(frame) - 2)


def _max_warmup(params_grid: list[TimingParams]) -> int:
    return max(_warmup(item) for item in params_grid)


def _warmup(params: TimingParams) -> int:
    return max(
        params.fast_bars,
        params.slow_bars,
        params.exit_bars,
        params.momentum_bars,
        params.breakout_bars + 1,
        params.volume_bars,
        26,
    )


def _params_grid_ranges(params_grid: list[TimingParams]) -> dict[str, list[Any]]:
    keys = [
        "profile",
        "fast_bars",
        "slow_bars",
        "exit_bars",
        "momentum_bars",
        "min_momentum_pct",
        "breakout_bars",
        "volume_bars",
        "stop_loss_pct",
        "take_profit_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _normalize_timestamps(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True)
    return normalized.sort_values("timestamp").drop_duplicates("timestamp").reset_index(drop=True)


def _filter_time_window(
    frame: pd.DataFrame,
    start: str | None,
    end: str | None,
) -> pd.DataFrame:
    filtered = frame.copy()
    if start:
        filtered = filtered[filtered["timestamp"] >= _utc_timestamp(start)]
    if end:
        filtered = filtered[filtered["timestamp"] <= _utc_timestamp(end)]
    return filtered.reset_index(drop=True)


def _utc_timestamp(value: str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
