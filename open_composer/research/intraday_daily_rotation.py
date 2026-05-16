from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime, time
from itertools import product
from pathlib import Path
from statistics import mean, pstdev
from time import perf_counter
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from open_composer.adapters.data import fetch_ohlcv
from open_composer.config import (
    data_feed,
    default_openai_model,
    ensure_dir,
    openai_api_key,
    openai_base_url,
    project_root,
)
from open_composer.json_utils import json_safe_payload
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.metadata import (
    combined_data_profile,
    estimate_grid_research_cost,
    frame_data_profile,
    hypothesis_ledger,
    research_brief,
    runtime_payload,
    search_space,
)
from open_composer.storage import write_json

MarketGate = Literal[
    "none",
    "qqq_open_negative",
    "qqq_open_positive",
    "qqq_prior_negative",
    "qqq_prior_positive",
    "qqq_open_and_prior_positive",
    "qqq_open_positive_prior_negative",
]
IntradayObjective = Literal["equal_weight_alpha", "benchmark_intraday_alpha"]
SelectionStyle = Literal["opening_momentum", "opening_reversal"]


@dataclass(frozen=True)
class IntradayDailyParams:
    selection_style: SelectionStyle
    lookback_days: int
    entry_after_bars: int
    top_n: int
    min_opening_return_pct: float
    min_prior_momentum_pct: float
    min_relative_volume: float
    max_opening_return_pct: float | None = None
    max_prior_momentum_pct: float | None = None
    market_gate: MarketGate = "none"

    @property
    def label(self) -> str:
        gate = self.market_gate.replace("qqq_", "q")
        base = (
            f"lb{self.lookback_days}_entry{self.entry_after_bars}_top{self.top_n}_"
            f"open{self.min_opening_return_pct:g}_mom{self.min_prior_momentum_pct:g}_"
            f"rv{self.min_relative_volume:g}_{gate}"
        )
        if self.selection_style == "opening_momentum":
            return base
        max_open = (
            "none" if self.max_opening_return_pct is None else f"{self.max_opening_return_pct:g}"
        )
        max_mom = (
            "none" if self.max_prior_momentum_pct is None else f"{self.max_prior_momentum_pct:g}"
        )
        return f"{base}_reversal_maxopen{max_open}_maxmom{max_mom}"


@dataclass(frozen=True)
class IntradayDailyMetrics:
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
    equal_weight_intraday_return_pct: float
    equal_weight_intraday_annualized_pct: float | None
    alpha_vs_equal_weight_annualized_pct: float | None
    benchmark_symbol: str
    benchmark_intraday_return_pct: float
    benchmark_intraday_annualized_pct: float | None
    alpha_vs_benchmark_intraday_annualized_pct: float | None
    benchmark_buy_hold_return_pct: float
    benchmark_buy_hold_annualized_pct: float | None
    alpha_vs_benchmark_buy_hold_annualized_pct: float | None
    universe_equal_weight_buy_hold_pct: float
    best_symbol_buy_hold_pct: float
    best_symbol: str | None
    alpha_vs_best_symbol_buy_hold_pct: float


@dataclass(frozen=True)
class IntradayDailyCandidate:
    rank: int
    params: IntradayDailyParams
    score: float
    train: IntradayDailyMetrics
    out_of_sample: IntradayDailyMetrics
    full_window: IntradayDailyMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class IntradayWalkForwardSlice:
    fold: int
    params: IntradayDailyParams
    train: IntradayDailyMetrics
    test: IntradayDailyMetrics


@dataclass(frozen=True)
class IntradayDailyResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[IntradayDailyCandidate]
    walk_forward: list[IntradayWalkForwardSlice]
    research_cost: dict[str, Any]
    runtime_seconds: dict[str, Any]
    data_profile: dict[str, Any]

    @property
    def best(self) -> IntradayDailyCandidate:
        return self.candidates[0]


class LLMIntradayDailyChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    expected_risks: list[str] = Field(default_factory=list)
    rejected_labels: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LLMIntradayDailyCandidate:
    rank: int
    params: IntradayDailyParams
    train: IntradayDailyMetrics
    validation: IntradayDailyMetrics
    validation_folds: list[IntradayDailyMetrics]
    score: float


@dataclass(frozen=True)
class LLMIntradayDailyResearchResult:
    report_path: Path
    json_path: Path
    prompt_path: Path
    choice: LLMIntradayDailyChoice
    selected: IntradayDailyCandidate
    reviewed_candidates: list[LLMIntradayDailyCandidate]
    status: Literal[
        "written",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
        "local_choice",
    ]


@dataclass(frozen=True)
class _DailyBars:
    opens: np.ndarray
    closes: np.ndarray
    volumes: np.ndarray

    @property
    def bar_count(self) -> int:
        return len(self.closes)


@dataclass(frozen=True)
class _IntradayDataset:
    symbols: list[str]
    benchmark_symbol: str
    market_symbol: str
    dates: list[str]
    bars: dict[str, dict[str, _DailyBars]]
    profiles: list[dict[str, Any]]


def run_intraday_daily_rotation_research(
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
    walk_forward_folds: int = 3,
    walk_forward_top_k: int | None = None,
    max_candidates: int = 240,
    refresh_data: bool = False,
) -> IntradayDailyResearchResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    stage_started = perf_counter()
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        raise ValueError("intraday daily rotation requires at least two NASDAQ symbols")
    selected_feed = feed or spec.data.feed or data_feed()
    params_grid = _build_params_grid(
        lookback_days or [5, 10, 20],
        entry_after_bars or [1, 2],
        top_n_values or [1, 2],
        min_opening_return_pct or [0.0, 0.2],
        min_prior_momentum_pct or [0.0, 3.0],
        min_relative_volume or [0.8, 1.0],
        selection_styles or ["opening_momentum"],
        max_opening_return_pct,
        max_prior_momentum_pct,
        market_gates or ["none", "qqq_open_positive"],
        max_candidates=max_candidates,
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
    candidates = _evaluate_candidates(
        spec=spec,
        dataset=dataset,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
        objective=objective,
    )
    stages["evaluate_candidates"] = perf_counter() - stage_started
    walk_params = _walk_forward_params(params_grid, candidates, walk_forward_top_k)
    research_cost = estimate_grid_research_cost(
        candidate_count=len(params_grid),
        walk_forward_candidate_count=len(walk_params),
        walk_forward_top_k=walk_forward_top_k,
        walk_forward_folds=walk_forward_folds,
    ).__dict__
    stage_started = perf_counter()
    walk_forward = _walk_forward(
        spec=spec,
        dataset=dataset,
        params_grid=walk_params,
        folds=walk_forward_folds,
        objective=objective,
    )
    stages["walk_forward"] = perf_counter() - stage_started
    report_path = base / "reports" / "research" / f"{spec.name}-intraday-daily-rotation.md"
    json_path = base / "reports" / "research" / f"{spec.name}-intraday-daily-rotation.json"
    runtime_seconds = runtime_payload(started_at, stages)
    _write_research_json(
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
    _write_research_report(
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
    return IntradayDailyResearchResult(
        report_path=report_path,
        json_path=json_path,
        candidates=candidates,
        walk_forward=walk_forward,
        research_cost=research_cost,
        runtime_seconds=runtime_seconds,
        data_profile=data_profile,
    )


def run_llm_intraday_daily_rotation_selection(
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
    validation_ratio: float = 0.3,
    validation_folds: int = 3,
    out_of_sample_ratio: float = 0.3,
    max_candidates: int = 240,
    refresh_data: bool = False,
    client: Any | None = None,
    model: str | None = None,
    local_choice_label: str | None = None,
) -> LLMIntradayDailyResearchResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        raise ValueError("LLM intraday rotation requires at least two symbols")
    selected_feed = feed or spec.data.feed or data_feed()
    params_grid = _build_params_grid(
        lookback_days or [5, 10, 20],
        entry_after_bars or [1, 2],
        top_n_values or [1, 2],
        min_opening_return_pct or [0.0, 0.2],
        min_prior_momentum_pct or [0.0, 3.0],
        min_relative_volume or [0.8, 1.0],
        selection_styles or ["opening_momentum"],
        max_opening_return_pct,
        max_prior_momentum_pct,
        market_gates or ["none", "qqq_open_positive"],
        max_candidates=max_candidates,
    )
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
    train_end = _split_for_oos(len(dataset.dates), out_of_sample_ratio, params_grid)
    reviewed = _build_llm_reviewed_candidates(
        spec=spec,
        dataset=dataset,
        params_grid=params_grid,
        train_end=train_end,
        validation_ratio=validation_ratio,
        validation_folds=validation_folds,
        objective=objective,
    )
    prompt = _llm_selection_prompt(spec, dataset, reviewed, objective)
    prompt = json_safe_payload(prompt)
    prompt_path = base / "reports" / "research" / f"{spec.name}-llm-intraday-selection-prompt.json"
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
        choice = _local_choice(reviewed, local_choice_label)
        status = "local_choice"
    elif client is None and not openai_api_key():
        choice = _deterministic_llm_choice(reviewed)
        status = "fallback_no_api_key"
    else:
        try:
            choice = _call_llm_choice(
                client or _openai_client(),
                model or default_openai_model(),
                prompt,
            )
            labels = {item.params.label for item in reviewed}
            if choice.selected_label not in labels:
                choice = _deterministic_llm_choice(reviewed)
                status = "fallback_invalid_choice"
        except Exception:
            choice = _deterministic_llm_choice(reviewed)
            status = "fallback_api_error"
    selected_params = _params_by_label(reviewed)[choice.selected_label]
    selected = _selected_candidate(
        spec=spec,
        dataset=dataset,
        params=selected_params,
        train_end=train_end,
        objective=objective,
    )
    json_path = base / "reports" / "research" / f"{spec.name}-llm-intraday-selection.json"
    report_path = base / "reports" / "research" / f"{spec.name}-llm-intraday-selection.md"
    _write_llm_json(
        json_path,
        spec,
        dataset,
        reviewed,
        choice,
        selected,
        status,
        prompt_path,
        start,
        end,
        objective,
    )
    _write_llm_report(
        report_path,
        json_path,
        prompt_path,
        spec,
        dataset,
        reviewed,
        choice,
        selected,
        status,
        start,
        end,
        objective,
    )
    return LLMIntradayDailyResearchResult(
        report_path=report_path,
        json_path=json_path,
        prompt_path=prompt_path,
        choice=choice,
        selected=selected,
        reviewed_candidates=reviewed,
        status=status,
    )


def write_intraday_product_reflection(
    root: Path,
    *,
    pure_report: Path,
    llm_report: Path,
    output_path: Path | None = None,
) -> Path:
    path = output_path or root / "reports" / "research" / "intraday-product-reflection.md"
    ensure_dir(path.parent)
    lines = [
        "# Intraday Strategy Product Reflection",
        "",
        f"- Pure quant report: `{pure_report}`",
        f"- LLM meta-selection report: `{llm_report}`",
        "",
        "## What Worked",
        "",
        "- File-first reports make leakage boundaries visible: training, validation, OOS, and "
        "walk-forward are separate artifacts.",
        "- The LLM path is constrained to prompt-visible candidate summaries and cannot see "
        "final OOS/full-window metrics before selection.",
        "- Daily intraday open/close logic avoids overnight leverage and makes TQQQ buy-and-hold "
        "a stress benchmark rather than the only acceptance gate.",
        "- Alpaca cache coverage checks now prevent a short diagnostic fetch from contaminating "
        "a longer research window.",
        "",
        "## Product Gaps",
        "",
        "- The core StrategySpec model cannot yet express portfolio-level daily stock selection "
        "and same-day liquidation directly; this research module bridges that gap.",
        "- Alpaca IEX is convenient but not consolidated SIP data, so fill and volume evidence "
        "must stay research-only until a stronger feed is compared.",
        "- LLM contribution is currently meta-selection, not independent per-symbol Alpha; "
        "future work should add replayable feature packets with visible_at/published_at hashes.",
        "- Intraday risk controls should support explicit end-of-day flatten, hard stop/take "
        "ordering assumptions, and liquidity/borrow filters.",
        "- Two-year 1m research still needs a persisted daily feature cache and stage progress "
        "telemetry; raw CSV grouping is too opaque for long-running dashboard jobs.",
        "",
        "## Next Improvements",
        "",
        "- Promote daily portfolio strategies into first-class StrategySpec semantics.",
        "- Add a benchmark suite with QQQ, TQQQ buy-and-hold, TQQQ intraday-only, equal-weight "
        "universe, and ex-post best symbol in one common schema.",
        "- Add data-source comparison between Alpaca IEX, Alpaca SIP when available, and "
        "Longbridge Nasdaq Basic before any paper-readiness claim.",
        "- Add walk-forward parameter freezing and model-card style LLM prompt auditing to the "
        "Dashboard research records.",
        "- Add a blind forward-test artifact that is created only after a candidate family is "
        "locked, so OOS discovery does not become accidental future leakage.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _build_params_grid(
    lookbacks: list[int],
    entry_bars: list[int],
    top_ns: list[int],
    min_opening: list[float],
    min_momentum: list[float],
    min_rel_volume: list[float],
    selection_styles: list[SelectionStyle],
    max_opening: list[float] | None,
    max_momentum: list[float] | None,
    market_gates: list[MarketGate],
    *,
    max_candidates: int,
) -> list[IntradayDailyParams]:
    params: list[IntradayDailyParams] = []
    for style in selection_styles:
        if style == "opening_momentum":
            opening_values = min_opening
            momentum_values = min_momentum
            max_opening_values: list[float | None] = [None]
            max_momentum_values: list[float | None] = [None]
        elif style == "opening_reversal":
            opening_values = [0.0]
            momentum_values = [0.0]
            max_opening_values = max_opening or [0.0, -0.2]
            max_momentum_values = max_momentum or [None]
        else:
            raise ValueError(f"unsupported selection style: {style}")
        for (
            lookback,
            entry_after,
            top_n,
            opening,
            momentum,
            rel_volume,
            max_open,
            max_mom,
            gate,
        ) in product(
            lookbacks,
            entry_bars,
            top_ns,
            opening_values,
            momentum_values,
            min_rel_volume,
            max_opening_values,
            max_momentum_values,
            market_gates,
        ):
            if lookback < 2:
                raise ValueError("lookback days must be at least 2")
            if entry_after < 1:
                raise ValueError("entry_after_bars must be at least 1")
            if top_n < 1:
                raise ValueError("top_n must be at least 1")
            params.append(
                IntradayDailyParams(
                    selection_style=style,
                    lookback_days=lookback,
                    entry_after_bars=entry_after,
                    top_n=top_n,
                    min_opening_return_pct=opening,
                    min_prior_momentum_pct=momentum,
                    min_relative_volume=rel_volume,
                    max_opening_return_pct=max_open,
                    max_prior_momentum_pct=max_mom,
                    market_gate=gate,
                )
            )
    if len(params) > max_candidates:
        raise ValueError(
            f"intraday grid would create {len(params)} candidates; raise --max-candidates "
            f"above {len(params)} or narrow the grid"
        )
    return params


def _load_dataset(
    *,
    spec: StrategySpec,
    root: Path,
    symbols: list[str],
    data_source: str,
    feed: str | None,
    start: str | None,
    end: str | None,
    benchmark_symbol: str,
    market_symbol: str,
    refresh_data: bool,
) -> _IntradayDataset:
    all_symbols = list(dict.fromkeys([*symbols, benchmark_symbol.upper(), market_symbol.upper()]))
    bars: dict[str, dict[str, _DailyBars]] = {}
    profiles: list[dict[str, Any]] = []
    for symbol in all_symbols:
        frame = fetch_ohlcv(
            root=root,
            symbol=symbol,
            timeframe=spec.timeframe,
            start=_parse_datetime(start),
            end=_parse_datetime(end),
            source=data_source,
            feed=feed,
            use_cache=not refresh_data,
            allow_fallback=False,
        )
        profiles.append(
            frame_data_profile(
                frame,
                symbol=symbol,
                timeframe=spec.timeframe,
                provider=data_source,
                feed=feed,
                source_mode=frame.attrs.get("data_source_mode"),
                path=frame.attrs.get("data_source_path"),
            )
        )
        bars[symbol] = _regular_session_days(frame)
    common_dates = _common_dates(bars, all_symbols)
    if len(common_dates) < 30:
        raise ValueError("fewer than 30 common regular-session days were available")
    return _IntradayDataset(
        symbols=symbols,
        benchmark_symbol=benchmark_symbol.upper(),
        market_symbol=market_symbol.upper(),
        dates=common_dates,
        bars=bars,
        profiles=profiles,
    )


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(UTC)
    else:
        timestamp = timestamp.tz_convert(UTC)
    return timestamp.to_pydatetime()


def _regular_session_days(frame: pd.DataFrame) -> dict[str, _DailyBars]:
    if frame.empty:
        return {}
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    local = data["timestamp"].dt.tz_convert("America/New_York")
    data["session_date"] = local.dt.date.astype(str)
    data["session_time"] = local.dt.time
    mask = data["session_time"].map(lambda value: time(9, 30) <= value < time(16, 0))
    data = data.loc[mask].sort_values("timestamp").reset_index(drop=True)
    days: dict[str, _DailyBars] = {}
    for date, group in data.groupby("session_date", sort=True):
        if len(group) < 4:
            continue
        days[date] = _DailyBars(
            opens=group["open"].to_numpy(dtype=float, copy=True),
            closes=group["close"].to_numpy(dtype=float, copy=True),
            volumes=group["volume"].to_numpy(dtype=float, copy=True),
        )
    return days


def _common_dates(bars: dict[str, dict[str, _DailyBars]], symbols: list[str]) -> list[str]:
    date_sets = [set(bars.get(symbol, {})) for symbol in symbols]
    if not date_sets:
        return []
    return sorted(set.intersection(*date_sets))


def _evaluate_candidates(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params_grid: list[IntradayDailyParams],
    out_of_sample_ratio: float,
    objective: IntradayObjective,
) -> list[IntradayDailyCandidate]:
    split = _split_for_oos(len(dataset.dates), out_of_sample_ratio, params_grid)
    rows: list[IntradayDailyCandidate] = []
    for params in params_grid:
        train = _backtest_params(
            spec, dataset, params, start_index=params.lookback_days, end_index=split
        )
        oos_start = max(params.lookback_days, split)
        oos = _backtest_params(
            spec, dataset, params, start_index=oos_start, end_index=len(dataset.dates)
        )
        full = _backtest_params(
            spec,
            dataset,
            params,
            start_index=params.lookback_days,
            end_index=len(dataset.dates),
        )
        flags = _quality_flags(oos, full)
        rows.append(
            IntradayDailyCandidate(
                rank=0,
                params=params,
                score=_score_metrics(train, objective),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=flags,
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        IntradayDailyCandidate(
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


def _walk_forward(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params_grid: list[IntradayDailyParams],
    folds: int,
    objective: IntradayObjective,
) -> list[IntradayWalkForwardSlice]:
    max_lookback = max(item.lookback_days for item in params_grid)
    fold_size = max((len(dataset.dates) - max_lookback) // (max(folds, 1) + 1), 5)
    rows: list[IntradayWalkForwardSlice] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = max_lookback + fold * fold_size
        test_end = min(len(dataset.dates), test_start + fold_size)
        if test_end - test_start < 5:
            continue
        scored = [
            (
                _score_metrics(
                    _backtest_params(
                        spec,
                        dataset,
                        params,
                        start_index=max_lookback,
                        end_index=test_start,
                    ),
                    objective,
                ),
                params,
            )
            for params in params_grid
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        selected = scored[0][1]
        rows.append(
            IntradayWalkForwardSlice(
                fold=fold,
                params=selected,
                train=_backtest_params(
                    spec,
                    dataset,
                    selected,
                    start_index=max_lookback,
                    end_index=test_start,
                ),
                test=_backtest_params(
                    spec,
                    dataset,
                    selected,
                    start_index=test_start,
                    end_index=test_end,
                ),
            )
        )
    return rows


def _walk_forward_params(
    params_grid: list[IntradayDailyParams],
    candidates: list[IntradayDailyCandidate],
    walk_forward_top_k: int | None,
) -> list[IntradayDailyParams]:
    if walk_forward_top_k is None:
        return params_grid
    if walk_forward_top_k < 1:
        raise ValueError("--walk-forward-top-k must be at least 1")
    return [item.params for item in candidates[: min(walk_forward_top_k, len(candidates))]]


def _backtest_params(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params: IntradayDailyParams,
    *,
    start_index: int,
    end_index: int,
    start_equity: float = 100_000.0,
) -> IntradayDailyMetrics:
    start_index = max(params.lookback_days, start_index)
    end_index = min(end_index, len(dataset.dates))
    selected_counts: list[int] = []
    strategy_returns: list[float] = []
    equal_weight_returns: list[float] = []
    benchmark_intraday_returns: list[float] = []
    equity_curve = [start_equity]
    equity = start_equity
    traded_days = 0
    round_trips = 0
    for index in range(start_index, end_index):
        selected = _selected_symbols(dataset, index, params)
        day_returns = [
            _symbol_intraday_return(dataset, symbol, index, params, spec) for symbol in selected
        ]
        day_returns = [value for value in day_returns if value is not None]
        strategy_return = mean(day_returns) if day_returns else 0.0
        if day_returns:
            traded_days += 1
            round_trips += len(day_returns)
        selected_counts.append(len(day_returns))
        strategy_returns.append(strategy_return)
        universe_returns = [
            _symbol_intraday_return(dataset, symbol, index, params, spec)
            for symbol in dataset.symbols
        ]
        universe_returns = [value for value in universe_returns if value is not None]
        equal_weight_returns.append(mean(universe_returns) if universe_returns else 0.0)
        benchmark_return = _symbol_intraday_return(
            dataset,
            dataset.benchmark_symbol,
            index,
            params,
            spec,
        )
        benchmark_intraday_returns.append(benchmark_return or 0.0)
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
    return IntradayDailyMetrics(
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


def _selected_symbols(
    dataset: _IntradayDataset,
    index: int,
    params: IntradayDailyParams,
) -> list[str]:
    if not _market_gate_passes(dataset, index, params):
        return []
    scores: list[tuple[float, str]] = []
    for symbol in dataset.symbols:
        stats = _symbol_selection_stats(dataset, symbol, index, params)
        if stats is None:
            continue
        opening_return, prior_momentum, relative_volume = stats
        if params.selection_style == "opening_reversal":
            if (
                params.max_opening_return_pct is not None
                and opening_return > params.max_opening_return_pct
            ):
                continue
            if (
                params.max_prior_momentum_pct is not None
                and prior_momentum > params.max_prior_momentum_pct
            ):
                continue
        else:
            if opening_return < params.min_opening_return_pct:
                continue
            if prior_momentum < params.min_prior_momentum_pct:
                continue
        if relative_volume < params.min_relative_volume:
            continue
        if params.selection_style == "opening_reversal":
            score = -opening_return * 0.55 - prior_momentum * 0.20 + (relative_volume - 1.0) * 20.0
        else:
            score = prior_momentum * 0.45 + opening_return * 0.35 + (relative_volume - 1.0) * 20.0
        scores.append((score, symbol))
    scores.sort(reverse=True)
    return [symbol for _, symbol in scores[: params.top_n]]


def _market_gate_passes(
    dataset: _IntradayDataset,
    index: int,
    params: IntradayDailyParams,
) -> bool:
    if params.market_gate == "none":
        return True
    stats = _symbol_selection_stats(dataset, dataset.market_symbol, index, params)
    if stats is None:
        return False
    opening_return, prior_momentum, _ = stats
    if params.market_gate == "qqq_open_positive":
        return opening_return > 0
    if params.market_gate == "qqq_open_negative":
        return opening_return < 0
    if params.market_gate == "qqq_prior_positive":
        return prior_momentum > 0
    if params.market_gate == "qqq_prior_negative":
        return prior_momentum < 0
    if params.market_gate == "qqq_open_and_prior_positive":
        return opening_return > 0 and prior_momentum > 0
    if params.market_gate == "qqq_open_positive_prior_negative":
        return opening_return > 0 and prior_momentum < 0
    return False


def _symbol_selection_stats(
    dataset: _IntradayDataset,
    symbol: str,
    index: int,
    params: IntradayDailyParams,
) -> tuple[float, float, float] | None:
    if index < params.lookback_days:
        return None
    day = _day_bars(dataset, symbol, index)
    if day is None or day.bar_count <= params.entry_after_bars:
        return None
    previous_day = _day_bars(dataset, symbol, index - 1)
    lookback_day = _day_bars(dataset, symbol, index - params.lookback_days)
    if previous_day is None or lookback_day is None:
        return None
    first_open = day.opens[0]
    opening_close = day.closes[params.entry_after_bars - 1]
    previous_close = previous_day.closes[-1]
    lookback_close = lookback_day.closes[-1]
    if first_open <= 0 or lookback_close <= 0:
        return None
    opening_return = (opening_close / first_open - 1) * 100
    prior_momentum = (previous_close / lookback_close - 1) * 100
    current_volume = float(day.volumes[: params.entry_after_bars].sum())
    prior_volumes: list[float] = []
    for prior_index in range(index - params.lookback_days, index):
        prior_day = _day_bars(dataset, symbol, prior_index)
        if prior_day is not None and prior_day.bar_count >= params.entry_after_bars:
            prior_volumes.append(float(prior_day.volumes[: params.entry_after_bars].sum()))
    avg_volume = mean(prior_volumes) if prior_volumes else 0.0
    relative_volume = current_volume / avg_volume if avg_volume > 0 else 0.0
    return opening_return, prior_momentum, relative_volume


def _symbol_intraday_return(
    dataset: _IntradayDataset,
    symbol: str,
    index: int,
    params: IntradayDailyParams,
    spec: StrategySpec,
) -> float | None:
    day = _day_bars(dataset, symbol, index)
    if day is None or day.bar_count <= params.entry_after_bars:
        return None
    entry = day.opens[params.entry_after_bars]
    exit_price = day.closes[-1]
    if entry <= 0:
        return None
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    return (exit_price * (1 - cost_rate)) / (entry * (1 + cost_rate)) - 1


def _day_bars(dataset: _IntradayDataset, symbol: str, index: int) -> _DailyBars | None:
    if index < 0 or index >= len(dataset.dates):
        return None
    return dataset.bars.get(symbol, {}).get(dataset.dates[index])


def _buy_hold_return(
    dataset: _IntradayDataset,
    symbol: str,
    start_index: int,
    end_index: int,
) -> float:
    if start_index >= end_index:
        return 0.0
    start_day = _day_bars(dataset, symbol, start_index)
    end_day = _day_bars(dataset, symbol, end_index - 1)
    if start_day is None or end_day is None:
        return 0.0
    start_price = start_day.opens[0]
    end_price = end_day.closes[-1]
    return ((end_price / start_price) - 1) * 100 if start_price > 0 else 0.0


def _split_for_oos(
    frame_len: int,
    ratio: float,
    params_grid: list[IntradayDailyParams],
) -> int:
    max_lookback = max(item.lookback_days for item in params_grid)
    split = int(frame_len * (1 - ratio))
    split = max(split, max_lookback + 10)
    return min(split, frame_len - 5)


def _compound_return(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1 + value
    return (equity - 1) * 100


def _annualized_from_total(total_return_pct: float, days: int) -> float | None:
    if days <= 0:
        return None
    base = 1 + total_return_pct / 100
    if base <= 0:
        return -100.0
    return (base ** (252 / days) - 1) * 100


def _daily_sharpe(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    sigma = pstdev(returns)
    if sigma <= 0:
        return None
    return (mean(returns) / sigma) * math.sqrt(252)


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    peak = equity_curve[0] if equity_curve else 0.0
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak > 0:
            max_drawdown = min(max_drawdown, (value / peak - 1) * 100)
    return max_drawdown


def _win_pct(returns: list[float]) -> float:
    if not returns:
        return 0.0
    return (sum(value > 0 for value in returns) / len(returns)) * 100


def _alpha(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _score_metrics(metrics: IntradayDailyMetrics, objective: IntradayObjective) -> float:
    sharpe = metrics.sharpe_ratio or 0.0
    if objective == "benchmark_intraday_alpha":
        alpha = metrics.alpha_vs_benchmark_intraday_annualized_pct or -100.0
    else:
        alpha = metrics.alpha_vs_equal_weight_annualized_pct or -100.0
    return (
        alpha
        + sharpe * 8
        - abs(min(metrics.max_drawdown_pct, 0.0)) * 0.35
        + min(metrics.traded_days, 80) * 0.05
    )


def _quality_flags(
    oos: IntradayDailyMetrics,
    full: IntradayDailyMetrics,
) -> list[str]:
    flags: list[str] = []
    if (oos.alpha_vs_equal_weight_annualized_pct or -1.0) <= 0:
        flags.append("oos_no_annualized_alpha_vs_equal_weight_intraday")
    if (oos.alpha_vs_benchmark_intraday_annualized_pct or -1.0) <= 0:
        flags.append("oos_no_annualized_alpha_vs_benchmark_intraday")
    if (oos.alpha_vs_benchmark_buy_hold_annualized_pct or -1.0) <= 0:
        flags.append("oos_no_annualized_alpha_vs_benchmark_buy_hold")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if oos.traded_days < 10:
        flags.append("low_oos_traded_days")
    if full.alpha_vs_best_symbol_buy_hold_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    return flags


def _acceptance_gate(
    candidate: IntradayDailyCandidate,
    walk_forward: list[IntradayWalkForwardSlice],
    objective: IntradayObjective,
) -> dict[str, Any]:
    objective_alpha = _objective_alpha(candidate.out_of_sample, objective)
    wf_alphas = [_objective_alpha(item.test, objective) for item in walk_forward]
    positive_wf = sum((value or -1.0) > 0 for value in wf_alphas)
    fold_count = len(wf_alphas)
    passed = (
        (objective_alpha or -1.0) > 0
        and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.5
        and candidate.out_of_sample.traded_days >= 10
        and fold_count > 0
        and positive_wf == fold_count
    )
    return {
        "passed": passed,
        "objective": objective,
        "oos_objective_alpha_annualized_pct": objective_alpha,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "oos_traded_days": candidate.out_of_sample.traded_days,
        "oos_alpha_vs_tqqq_buy_hold_annualized_pct": (
            candidate.out_of_sample.alpha_vs_benchmark_buy_hold_annualized_pct
        ),
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": fold_count,
        "quality_flags": candidate.quality_flags,
    }


def _objective_alpha(
    metrics: IntradayDailyMetrics,
    objective: IntradayObjective,
) -> float | None:
    if objective == "benchmark_intraday_alpha":
        return metrics.alpha_vs_benchmark_intraday_annualized_pct
    return metrics.alpha_vs_equal_weight_annualized_pct


def _build_llm_reviewed_candidates(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params_grid: list[IntradayDailyParams],
    train_end: int,
    validation_ratio: float,
    validation_folds: int,
    objective: IntradayObjective,
) -> list[LLMIntradayDailyCandidate]:
    split = max(
        max(item.lookback_days for item in params_grid) + 10,
        int(train_end * (1 - validation_ratio)),
    )
    split = min(split, train_end - 5)
    fold_size = max(
        (train_end - max(item.lookback_days for item in params_grid)) // (validation_folds + 1), 5
    )
    rows: list[LLMIntradayDailyCandidate] = []
    for params in params_grid:
        train = _backtest_params(
            spec, dataset, params, start_index=params.lookback_days, end_index=split
        )
        validation = _backtest_params(spec, dataset, params, start_index=split, end_index=train_end)
        folds: list[IntradayDailyMetrics] = []
        for fold in range(1, max(validation_folds, 1) + 1):
            test_start = params.lookback_days + fold * fold_size
            test_end = min(train_end, test_start + fold_size)
            if test_end - test_start >= 5:
                folds.append(
                    _backtest_params(
                        spec,
                        dataset,
                        params,
                        start_index=test_start,
                        end_index=test_end,
                    )
                )
        score = _llm_meta_score(train, validation, folds, objective)
        rows.append(
            LLMIntradayDailyCandidate(
                rank=0,
                params=params,
                train=train,
                validation=validation,
                validation_folds=folds,
                score=score,
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        LLMIntradayDailyCandidate(
            rank=index,
            params=item.params,
            train=item.train,
            validation=item.validation,
            validation_folds=item.validation_folds,
            score=item.score,
        )
        for index, item in enumerate(rows, start=1)
    ]


def _llm_meta_score(
    train: IntradayDailyMetrics,
    validation: IntradayDailyMetrics,
    folds: list[IntradayDailyMetrics],
    objective: IntradayObjective,
) -> float:
    train_alpha = _objective_alpha(train, objective) or -100.0
    validation_alpha = _objective_alpha(validation, objective) or -100.0
    fold_alphas = [_objective_alpha(item, objective) or -100.0 for item in folds]
    positive_folds = sum(value > 0 for value in fold_alphas)
    min_fold = min(fold_alphas) if fold_alphas else -100.0
    avg_fold = mean(fold_alphas) if fold_alphas else -100.0
    return (
        min(train_alpha, validation_alpha) * 0.4
        + validation_alpha * 0.5
        + avg_fold * 0.5
        + min_fold * 0.4
        + positive_folds * 12
        + (validation.sharpe_ratio or 0.0) * 6
        - abs(train_alpha - validation_alpha) * 0.2
        - abs(min(validation.max_drawdown_pct, 0.0)) * 0.2
    )


def _selected_candidate(
    *,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    params: IntradayDailyParams,
    train_end: int,
    objective: IntradayObjective,
) -> IntradayDailyCandidate:
    train = _backtest_params(
        spec, dataset, params, start_index=params.lookback_days, end_index=train_end
    )
    oos = _backtest_params(
        spec, dataset, params, start_index=train_end, end_index=len(dataset.dates)
    )
    full = _backtest_params(
        spec, dataset, params, start_index=params.lookback_days, end_index=len(dataset.dates)
    )
    return IntradayDailyCandidate(
        rank=1,
        params=params,
        score=_score_metrics(train, objective),
        train=train,
        out_of_sample=oos,
        full_window=full,
        quality_flags=_quality_flags(oos, full),
    )


def _llm_selection_prompt(
    spec: StrategySpec,
    dataset: _IntradayDataset,
    reviewed: list[LLMIntradayDailyCandidate],
    objective: IntradayObjective,
    limit: int = 24,
) -> dict[str, Any]:
    return {
        "task": (
            "Select one daily intraday NASDAQ stock-selection method from training-only evidence."
        ),
        "strategy_name": spec.name,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "available_evidence": "training, internal validation, and prior validation folds only",
        "hidden_from_model": "final out-of-sample and full-window metrics",
        "selection_objective": _objective_label(objective),
        "anti_leakage_rules": [
            "Do not infer final OOS performance.",
            "Prefer stable validation alpha and positive prior folds.",
            "Penalize sparse trading and high drawdown.",
            "Do not use benchmark buy-and-hold as a tradable intraday target.",
        ],
        "candidates": [_llm_candidate_payload(item, objective) for item in reviewed[:limit]],
    }


def _call_llm_choice(
    client: Any,
    model: str,
    prompt: dict[str, Any],
) -> LLMIntradayDailyChoice:
    messages = [
        {
            "role": "system",
            "content": (
                "You choose a trading research candidate from training-only evidence. "
                "Return schema-valid JSON and do not claim live trading certainty."
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
            text_format=LLMIntradayDailyChoice,
        )
        parsed = _extract_llm_choice(response)
        if parsed is not None:
            return parsed
    except TypeError:
        response = client.responses.create(
            model=model,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "llm_intraday_daily_choice",
                    "strict": True,
                    "schema": LLMIntradayDailyChoice.model_json_schema(),
                }
            },
        )
        return LLMIntradayDailyChoice.model_validate_json(response.output_text)
    raise ValueError("LLM returned no schema-valid intraday choice")


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key(), base_url=openai_base_url())


def _extract_llm_choice(response: Any) -> LLMIntradayDailyChoice | None:
    for output in getattr(response, "output", []):
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", []):
            parsed = getattr(item, "parsed", None)
            if isinstance(parsed, LLMIntradayDailyChoice):
                return parsed
            if isinstance(parsed, dict):
                return LLMIntradayDailyChoice.model_validate(parsed)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, LLMIntradayDailyChoice):
        return parsed
    if isinstance(parsed, dict):
        return LLMIntradayDailyChoice.model_validate(parsed)
    return None


def _deterministic_llm_choice(
    reviewed: list[LLMIntradayDailyCandidate],
) -> LLMIntradayDailyChoice:
    selected = reviewed[0]
    return LLMIntradayDailyChoice(
        selected_label=selected.params.label,
        confidence=0.0,
        rationale="Fallback selected the highest training-only meta score.",
        expected_risks=["No usable LLM response; deterministic fallback used."],
        rejected_labels=[item.params.label for item in reviewed[1:4]],
    )


def _local_choice(
    reviewed: list[LLMIntradayDailyCandidate],
    label: str,
) -> LLMIntradayDailyChoice:
    labels = {item.params.label for item in reviewed}
    if label not in labels:
        raise ValueError(f"--local-choice-label not found in prompt candidates: {label}")
    return LLMIntradayDailyChoice(
        selected_label=label,
        confidence=0.0,
        rationale="Local Codex/operator selected from prompt-visible training evidence only.",
        expected_risks=["Local choice is not independent LLM Alpha."],
        rejected_labels=[item.params.label for item in reviewed if item.params.label != label][:3],
    )


def _params_by_label(
    reviewed: list[LLMIntradayDailyCandidate],
) -> dict[str, IntradayDailyParams]:
    return {item.params.label: item.params for item in reviewed}


def _write_research_json(
    path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    candidates: list[IntradayDailyCandidate],
    walk_forward: list[IntradayWalkForwardSlice],
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
        "mode": _research_mode(spec),
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "research_window": {"start": start, "end": end},
        "data_profile": data_profile,
        "research_brief": research_brief(
            strategy_name=spec.name,
            objective=_objective_label(objective),
            hypothesis=(
                "Opening-range strength, prior momentum, and relative opening volume can "
                "select NASDAQ stocks with better intraday risk-adjusted returns than "
                "equal-weight intraday exposure."
            ),
            constraints=_assumptions(spec, dataset),
        ),
        "search_space": search_space(
            family="daily_intraday_opening_rotation",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=["long-only", "same-day exit", "confirmed opening bars only"],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis="Daily intraday stock selection improves OOS objective Alpha.",
            visible_evidence=["training score", "OOS metrics", "walk-forward folds"],
            hidden_evidence=[],
            counterevidence=candidates[0].quality_flags,
            conclusion="passed"
            if _acceptance_gate(candidates[0], walk_forward, objective)["passed"]
            else "failed",
        ),
        "research_cost": research_cost,
        "runtime_seconds": runtime_seconds,
        "selection_objective": _objective_label(objective),
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward, objective),
        "pass_status": _pass_status(candidates[0], objective),
        "assumptions": _assumptions(spec, dataset),
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_payload(item) for item in walk_forward],
    }
    return write_json(path, payload)


def _write_research_report(
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    candidates: list[IntradayDailyCandidate],
    walk_forward: list[IntradayWalkForwardSlice],
    start: str | None,
    end: str | None,
    objective: IntradayObjective,
    research_cost: dict[str, Any],
    runtime_seconds: dict[str, Any],
    data_profile: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Intraday Daily Rotation Research: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Symbols: {', '.join(dataset.symbols)}",
        f"- Timeframe: `{spec.timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Market gate symbol: `{dataset.market_symbol}`",
        f"- Benchmark symbol: `{dataset.benchmark_symbol}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Data source/feed: `{data_profile.get('provider') or 'mixed'}` / "
        f"`{data_profile.get('feed') or 'mixed'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'mixed'}`",
        f"- LLM review enabled: `{spec.llm_review.enabled}`",
        "- LLM in backtest loop: `False`",
        "- Point-in-time: selection uses previous closes plus confirmed opening bars only.",
        "- Execution: enter next bar after opening window, exit same day on last regular bar.",
        f"- Selection objective: {_objective_label(objective)}",
        "",
        "## Assumptions",
        "",
        *[f"- {item}" for item in _assumptions(spec, dataset)],
        "",
        "## Research Cost",
        "",
        f"- Candidates evaluated: `{research_cost['candidate_count']}`",
        f"- Walk-forward candidates: `{research_cost['walk_forward_candidate_count']}`",
        f"- Walk-forward top-K filter: `{research_cost['walk_forward_top_k'] or 'off'}`",
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
        *[f"- {key}: `{value}`" for key, value in _pass_status(candidates[0], objective).items()],
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
        lines.append("- No walk-forward folds were available.")
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
            "## Overfit And Benchmark Notes",
            "",
            "- Best parameters are selected on the training window; OOS is scored after selection.",
            "- Walk-forward folds reselect parameters only from prior days.",
            "- `TQQQ` buy-and-hold is a leveraged overnight benchmark and is shown as a stress "
            "comparison, not the primary intraday acceptance gate.",
            "- The comparable intraday benchmarks are equal-weight universe intraday and "
            f"`{dataset.benchmark_symbol}` intraday-only over the same entry/exit bars.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_llm_json(
    path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    reviewed: list[LLMIntradayDailyCandidate],
    choice: LLMIntradayDailyChoice,
    selected: IntradayDailyCandidate,
    status: str,
    prompt_path: Path,
    start: str | None,
    end: str | None,
    objective: IntradayObjective,
) -> Path:
    contribution = _llm_contribution(status, choice, selected, reviewed)
    payload = {
        "strategy_name": spec.name,
        "mode": "llm_training_meta_selection_daily_intraday",
        "status": status,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "prompt_path": str(prompt_path),
        "research_window": {"start": start, "end": end},
        "selection_objective": _objective_label(objective),
        "anti_leakage": {
            "llm_visible_metrics": "training, internal validation, and prior folds only",
            "llm_hidden_metrics": "final out-of-sample and full-window metrics",
            "llm_called_inside_backtest_loop": False,
        },
        "llm_contribution": contribution,
        "pass_status": _pass_status(
            selected,
            objective,
            llm_contribution_ok=bool(contribution["llm_contribution_ok"]),
        ),
        "choice": choice.model_dump(mode="json"),
        "selected": _candidate_payload(selected),
        "reviewed_candidates": [_llm_candidate_payload(item, objective) for item in reviewed],
    }
    return write_json(path, payload)


def _write_llm_report(
    path: Path,
    json_path: Path,
    prompt_path: Path,
    spec: StrategySpec,
    dataset: _IntradayDataset,
    reviewed: list[LLMIntradayDailyCandidate],
    choice: LLMIntradayDailyChoice,
    selected: IntradayDailyCandidate,
    status: str,
    start: str | None,
    end: str | None,
    objective: IntradayObjective,
) -> Path:
    ensure_dir(path.parent)
    contribution = _llm_contribution(status, choice, selected, reviewed)
    flags = ", ".join(selected.quality_flags) if selected.quality_flags else "none"
    lines = [
        f"# LLM Intraday Daily Rotation Selection: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Prompt artifact: `{prompt_path}`",
        f"- Status: `{status}`",
        f"- Symbols: {', '.join(dataset.symbols)}",
        f"- Market symbol: `{dataset.market_symbol}`",
        f"- Benchmark symbol: `{dataset.benchmark_symbol}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        "- Mode: `llm_training_meta_selection_daily_intraday`",
        f"- Selection objective: {_objective_label(objective)}",
        "- Anti-leakage: final OOS and full-window metrics are hidden until after selection.",
        "- No LLM call is made inside the backtest loop.",
        "",
        "## LLM Choice",
        "",
        f"- Selected: `{choice.selected_label}`",
        f"- Confidence: `{choice.confidence:.2f}`",
        f"- Rationale: {choice.rationale}",
        f"- Expected risks: {', '.join(choice.expected_risks) or 'none'}",
        f"- Rejected labels: {', '.join(choice.rejected_labels) or 'none'}",
        "",
        "## LLM Contribution",
        "",
        f"- Contribution OK: `{contribution['llm_contribution_ok']}`",
        f"- Level: `{contribution['llm_contribution_level']}`",
        f"- Label: {contribution['llm_contribution_label']}",
        "",
        "## Pass Labels",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _pass_status(
                selected,
                objective,
                llm_contribution_ok=bool(contribution["llm_contribution_ok"]),
            ).items()
        ],
        "",
        "## Final Validation After Selection",
        "",
        f"- Quality flags: `{flags}`",
        *_metric_lines("Train", selected.train),
        *_metric_lines("Final OOS", selected.out_of_sample),
        *_metric_lines("Full window", selected.full_window),
        "",
        "## Candidates Visible To LLM",
        "",
        (
            "| Rank | Label | Meta Score | Train Objective Alpha | Validation Objective Alpha | "
            "Fold Avg Alpha | Fold Min Alpha | Positive Folds |"
        ),
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in reviewed[:24]:
        fold_alphas = [_objective_alpha(fold, objective) or 0.0 for fold in item.validation_folds]
        lines.append(
            f"| {item.rank} | `{item.params.label}` | {item.score:.2f} | "
            f"{(_objective_alpha(item.train, objective) or 0.0):.2f}% | "
            f"{(_objective_alpha(item.validation, objective) or 0.0):.2f}% | "
            f"{(mean(fold_alphas) if fold_alphas else 0.0):.2f}% | "
            f"{(min(fold_alphas) if fold_alphas else 0.0):.2f}% | "
            f"{sum(value > 0 for value in fold_alphas)}/{len(fold_alphas)} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _llm_contribution(
    status: str,
    choice: LLMIntradayDailyChoice,
    selected: IntradayDailyCandidate,
    reviewed: list[LLMIntradayDailyCandidate],
) -> dict[str, Any]:
    top_label = reviewed[0].params.label
    contribution_ok = status == "written" and choice.selected_label != top_label
    label = "independent_llm_selection_signal" if contribution_ok else "llm_assisted_selection_only"
    counterevidence = []
    if status != "written":
        counterevidence.append("external_llm_api_not_called_or_not_used")
    if choice.selected_label == top_label:
        counterevidence.append("selection_identical_to_deterministic_top_candidate")
    if selected.out_of_sample.traded_days < 10:
        counterevidence.append("sparse_oos_trading")
    return {
        "llm_contribution_ok": contribution_ok,
        "llm_contribution_level": label,
        "llm_contribution_label": label,
        "selected_prompt_rank": next(
            (item.rank for item in reviewed if item.params.label == choice.selected_label),
            None,
        ),
        "deterministic_top_label": top_label,
        "counterevidence": counterevidence,
    }


def _research_mode(spec: StrategySpec) -> str:
    if spec.llm_review.enabled:
        return "quant_with_advisory_llm_review_daily_intraday"
    return "pure_quant_daily_intraday_rotation"


def _pass_status(
    candidate: IntradayDailyCandidate,
    objective: IntradayObjective,
    *,
    llm_contribution_ok: bool = False,
) -> dict[str, Any]:
    oos_objective_alpha = _objective_alpha(candidate.out_of_sample, objective) or -100.0
    research_pass = (
        oos_objective_alpha > 0
        and (candidate.out_of_sample.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.full_window.alpha_vs_benchmark_buy_hold_annualized_pct or -100.0) > 0
        and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.5
        and candidate.out_of_sample.traded_days >= 10
    )
    return {
        "workflow_pass": True,
        "research_pass": research_pass,
        "llm_contribution_pass": llm_contribution_ok,
        "paper_ready_pass": False,
        "paper_ready_blockers": [
            "draft/manual_signal strategy only",
            "Alpaca IEX is not consolidated SIP data",
            "no broker paper-readiness activation or data-source comparison",
            "LLM output is advisory unless replayed from feature packets",
        ],
    }


def _candidate_payload(candidate: IntradayDailyCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__,
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_payload(item: IntradayWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__,
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _llm_candidate_payload(
    item: LLMIntradayDailyCandidate,
    objective: IntradayObjective,
) -> dict[str, Any]:
    fold_alphas = [_objective_alpha(fold, objective) or 0.0 for fold in item.validation_folds]
    return {
        "rank": item.rank,
        "label": item.params.label,
        "params": item.params.__dict__,
        "meta_score": item.score,
        "train_objective_alpha_annualized_pct": _objective_alpha(item.train, objective),
        "validation_objective_alpha_annualized_pct": _objective_alpha(
            item.validation,
            objective,
        ),
        "validation_sharpe": item.validation.sharpe_ratio,
        "validation_traded_days": item.validation.traded_days,
        "fold_avg_objective_alpha_annualized_pct": mean(fold_alphas) if fold_alphas else None,
        "fold_min_objective_alpha_annualized_pct": min(fold_alphas) if fold_alphas else None,
        "fold_positive_count": sum(value > 0 for value in fold_alphas),
        "fold_count": len(fold_alphas),
    }


def _metric_lines(label: str, metrics: IntradayDailyMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} annualized: `{_fmt(metrics.annualized_return_pct)}%`",
        f"- {label} Alpha vs equal-weight intraday annualized: "
        f"`{_fmt(metrics.alpha_vs_equal_weight_annualized_pct)}%`",
        f"- {label} Alpha vs {metrics.benchmark_symbol} intraday annualized: "
        f"`{_fmt(metrics.alpha_vs_benchmark_intraday_annualized_pct)}%`",
        f"- {label} Alpha vs {metrics.benchmark_symbol} buy-hold annualized: "
        f"`{_fmt(metrics.alpha_vs_benchmark_buy_hold_annualized_pct)}%`",
        f"- {label} Sharpe: `{_fmt(metrics.sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} traded days / round trips: `{metrics.traded_days}/{metrics.round_trips}`",
        f"- {label} win day pct: `{metrics.win_day_pct:.2f}%`",
        f"- {label} benchmark buy-hold: "
        f"`{metrics.benchmark_symbol} {metrics.benchmark_buy_hold_return_pct:.2f}%`",
        (
            f"- {label} ex-post best buy-hold: "
            f"`{metrics.best_symbol} {metrics.best_symbol_buy_hold_pct:.2f}%`"
        ),
    ]


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _assumptions(spec: StrategySpec, dataset: _IntradayDataset) -> list[str]:
    return [
        "Selection uses only previous regular-session closes plus confirmed same-day opening bars.",
        "Entry occurs at the next bar open after the opening window.",
        "All positions are exited at the same day's final regular-session close.",
        "No overnight positions, leverage, shorts, or real broker orders are used.",
        f"Commission is {spec.costs.commission_pct:.4g}% per fill.",
        f"Slippage is {spec.costs.slippage_bps:.4g} bps per fill.",
        f"{dataset.benchmark_symbol} buy-and-hold is reported as a stress benchmark, not "
        "as the primary intraday acceptance gate.",
        "Alpaca IEX data is not consolidated full-market SIP data when feed=iex.",
    ]


def _params_grid_ranges(params_grid: list[IntradayDailyParams]) -> dict[str, list[Any]]:
    keys = [
        "lookback_days",
        "entry_after_bars",
        "top_n",
        "min_opening_return_pct",
        "min_prior_momentum_pct",
        "min_relative_volume",
        "selection_style",
        "max_opening_return_pct",
        "max_prior_momentum_pct",
        "market_gate",
    ]
    return {key: _sorted_unique(getattr(item, key) for item in params_grid) for key in keys}


def _sorted_unique(values: Any) -> list[Any]:
    unique = set(values)
    return sorted(unique, key=lambda value: (value is None, str(value)))


def _objective_label(objective: IntradayObjective) -> str:
    if objective == "benchmark_intraday_alpha":
        return "prefer stable annualized Alpha versus benchmark-symbol intraday exposure"
    return "prefer stable annualized Alpha versus equal-weight universe intraday exposure"
