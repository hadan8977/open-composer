from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from math import prod
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data import fetch_ohlcv
from open_composer.analytics import build_performance_metrics
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.storage import write_json


@dataclass(frozen=True)
class LeverageParams:
    leverage: float
    financing_rate_pct: float

    @property
    def label(self) -> str:
        return f"lev{self.leverage:g}_fin{self.financing_rate_pct:g}"


@dataclass(frozen=True)
class LeverageMetrics:
    bars: int
    start_timestamp: str | None
    end_timestamp: str | None
    total_return_pct: float
    buy_hold_return_pct: float
    alpha_vs_buy_hold_pct: float
    annualized_return_pct: float | None
    sharpe_ratio: float | None
    buy_hold_sharpe_ratio: float | None
    max_drawdown_pct: float
    buy_hold_max_drawdown_pct: float
    financing_cost_pct: float


@dataclass(frozen=True)
class LeverageCandidate:
    rank: int
    params: LeverageParams
    score: float
    train: LeverageMetrics
    out_of_sample: LeverageMetrics
    full_window: LeverageMetrics
    quality_flags: list[str]


@dataclass(frozen=True)
class LeverageWalkForwardSlice:
    fold: int
    params: LeverageParams
    train: LeverageMetrics
    test: LeverageMetrics


@dataclass(frozen=True)
class LeverageResearchResult:
    report_path: Path
    json_path: Path
    candidates: list[LeverageCandidate]
    walk_forward: list[LeverageWalkForwardSlice]

    @property
    def best(self) -> LeverageCandidate:
        return self.candidates[0]


def run_leverage_research(
    spec_path: Path,
    root: Path | None = None,
    symbol: str | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    leverage_values: list[float] | None = None,
    financing_rate_pct: list[float] | None = None,
    out_of_sample_ratio: float = 0.3,
    walk_forward_folds: int = 3,
    max_candidates: int = 100,
    refresh_data: bool = False,
    start: str | None = None,
    end: str | None = None,
) -> LeverageResearchResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_symbol = (symbol or spec.primary_symbol).upper()
    selected_feed = feed or spec.data.feed or data_feed()
    frame = fetch_ohlcv(
        root=base,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        start=None,
        end=None,
        source=data_source,
        feed=selected_feed,
        use_cache=not refresh_data,
    )
    frame = _filter_time_window(_normalize_timestamps(frame), start, end)
    if len(frame) < 4:
        raise ValueError("leverage research requires at least 4 bars after filtering")
    params_grid = _build_params_grid(
        leverage_values or [1.0, 1.25, 1.5, 2.0],
        financing_rate_pct or [5.0, 8.0],
        max_candidates=max_candidates,
    )
    candidates = _evaluate_candidates(
        frame=frame,
        timeframe=spec.timeframe,
        params_grid=params_grid,
        out_of_sample_ratio=out_of_sample_ratio,
    )
    walk_forward = _walk_forward(
        frame=frame,
        timeframe=spec.timeframe,
        params_grid=params_grid,
        folds=walk_forward_folds,
    )
    report_path = base / "reports" / "research" / f"{spec.name}-leverage-research.md"
    json_path = base / "reports" / "research" / f"{spec.name}-leverage-research.json"
    _write_leverage_json(
        json_path, spec.name, selected_symbol, spec.timeframe, start, end, candidates, walk_forward
    )
    _write_leverage_report(
        report_path,
        json_path,
        spec.name,
        selected_symbol,
        spec.timeframe,
        start,
        end,
        candidates,
        walk_forward,
    )
    return LeverageResearchResult(report_path, json_path, candidates, walk_forward)


def _build_params_grid(
    leverage_values: list[float],
    financing_rates: list[float],
    *,
    max_candidates: int,
) -> list[LeverageParams]:
    total = prod([len(leverage_values), len(financing_rates)])
    if total > max_candidates:
        raise ValueError(
            f"leverage grid would create {total} candidates; raise --max-candidates "
            f"above {total} or narrow the grid"
        )
    params: list[LeverageParams] = []
    for leverage, financing in product(leverage_values, financing_rates):
        if leverage < 1.0:
            raise ValueError("leverage must be at least 1.0")
        if financing < 0:
            raise ValueError("financing rate must be non-negative")
        params.append(LeverageParams(leverage=leverage, financing_rate_pct=financing))
    return params


def _evaluate_candidates(
    *,
    frame: pd.DataFrame,
    timeframe: str,
    params_grid: list[LeverageParams],
    out_of_sample_ratio: float,
) -> list[LeverageCandidate]:
    split = _split_index(frame, out_of_sample_ratio)
    rows: list[LeverageCandidate] = []
    for params in params_grid:
        train = _backtest_leverage(frame.iloc[:split].copy(), timeframe, params)
        oos = _backtest_leverage(frame.iloc[split:].copy(), timeframe, params)
        full = _backtest_leverage(frame, timeframe, params)
        rows.append(
            LeverageCandidate(
                rank=0,
                params=params,
                score=_score_candidate(train),
                train=train,
                out_of_sample=oos,
                full_window=full,
                quality_flags=_quality_flags(train, oos, full),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        LeverageCandidate(
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
    frame: pd.DataFrame,
    timeframe: str,
    params_grid: list[LeverageParams],
    folds: int,
) -> list[LeverageWalkForwardSlice]:
    folds = max(folds, 1)
    fold_size = max(len(frame) // (folds + 1), 2)
    slices: list[LeverageWalkForwardSlice] = []
    for fold in range(1, folds + 1):
        test_start = fold * fold_size
        test_end = min(len(frame), test_start + fold_size)
        if test_end - test_start < 2:
            continue
        train_frame = frame.iloc[:test_start].copy()
        train_scores = [
            (_score_candidate(_backtest_leverage(train_frame, timeframe, params)), params)
            for params in params_grid
        ]
        train_scores.sort(key=lambda item: item[0], reverse=True)
        selected = train_scores[0][1]
        slices.append(
            LeverageWalkForwardSlice(
                fold=fold,
                params=selected,
                train=_backtest_leverage(train_frame, timeframe, selected),
                test=_backtest_leverage(
                    frame.iloc[test_start:test_end].copy(), timeframe, selected
                ),
            )
        )
    return slices


def _backtest_leverage(
    frame: pd.DataFrame,
    timeframe: str,
    params: LeverageParams,
    start_equity: float = 100_000.0,
) -> LeverageMetrics:
    if len(frame) < 2:
        return _empty_metrics(frame)
    prices = [float(frame["open"].iloc[0]), *[float(value) for value in frame["close"].tolist()]]
    returns = [
        (current / previous) - 1 for previous, current in zip(prices, prices[1:], strict=False)
    ]
    financing_per_bar = _financing_per_bar(params.financing_rate_pct, timeframe)
    equity = start_equity
    buy_hold_equity = start_equity
    equity_curve = [equity]
    buy_hold_curve = [buy_hold_equity]
    financing_cost = 0.0
    for period_return in returns:
        financing_drag = max(params.leverage - 1.0, 0.0) * financing_per_bar
        before_financing = equity * (1 + params.leverage * period_return)
        period_financing = equity * financing_drag
        equity = max(before_financing - period_financing, 0.0)
        buy_hold_equity *= 1 + period_return
        equity_curve.append(equity)
        buy_hold_curve.append(buy_hold_equity)
        financing_cost += period_financing
        if equity <= 0:
            break
    total_return_pct = (equity / start_equity - 1) * 100
    buy_hold_return_pct = (buy_hold_equity / start_equity - 1) * 100
    metrics = build_performance_metrics(equity_curve, timeframe)
    buy_hold_metrics = build_performance_metrics(buy_hold_curve, timeframe)
    return LeverageMetrics(
        bars=len(frame),
        start_timestamp=frame["timestamp"].iloc[0].isoformat(),
        end_timestamp=frame["timestamp"].iloc[-1].isoformat(),
        total_return_pct=total_return_pct,
        buy_hold_return_pct=buy_hold_return_pct,
        alpha_vs_buy_hold_pct=total_return_pct - buy_hold_return_pct,
        annualized_return_pct=metrics.annualized_return_pct,
        sharpe_ratio=metrics.sharpe_ratio,
        buy_hold_sharpe_ratio=buy_hold_metrics.sharpe_ratio,
        max_drawdown_pct=_max_drawdown_pct(equity_curve),
        buy_hold_max_drawdown_pct=_max_drawdown_pct(buy_hold_curve),
        financing_cost_pct=(financing_cost / start_equity) * 100,
    )


def _score_candidate(metrics: LeverageMetrics) -> float:
    drawdown_penalty = abs(min(metrics.max_drawdown_pct, 0.0)) * 0.2
    sharpe = metrics.sharpe_ratio or 0.0
    return metrics.alpha_vs_buy_hold_pct + sharpe * 5 - drawdown_penalty


def _quality_flags(
    train: LeverageMetrics,
    oos: LeverageMetrics,
    full: LeverageMetrics,
) -> list[str]:
    flags: list[str] = []
    if train.alpha_vs_buy_hold_pct > 0 and oos.alpha_vs_buy_hold_pct <= 0:
        flags.append("train_oos_alpha_decay")
    if oos.alpha_vs_buy_hold_pct <= 0:
        flags.append("oos_no_alpha_vs_buy_hold")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if (
        oos.sharpe_ratio is not None
        and oos.buy_hold_sharpe_ratio is not None
        and oos.sharpe_ratio < oos.buy_hold_sharpe_ratio
    ):
        flags.append("oos_sharpe_below_buy_hold")
    if full.alpha_vs_buy_hold_pct <= 0:
        flags.append("full_window_no_alpha_vs_buy_hold")
    if _drawdown_expanded(oos.max_drawdown_pct, oos.buy_hold_max_drawdown_pct, multiple=1.5):
        flags.append("oos_levered_drawdown_expansion")
    if _drawdown_expanded(full.max_drawdown_pct, full.buy_hold_max_drawdown_pct, multiple=1.5):
        flags.append("full_levered_drawdown_expansion")
    return flags


def _acceptance_gate(
    candidate: LeverageCandidate,
    walk_forward: list[LeverageWalkForwardSlice],
) -> dict[str, Any]:
    wf_alphas = [item.test.alpha_vs_buy_hold_pct for item in walk_forward]
    positive_wf = sum(value > 0 for value in wf_alphas)
    wf_count = len(wf_alphas)
    passed = (
        candidate.out_of_sample.alpha_vs_buy_hold_pct > 0
        and (candidate.out_of_sample.sharpe_ratio or 0.0) >= 0.5
        and (
            candidate.out_of_sample.buy_hold_sharpe_ratio is None
            or (candidate.out_of_sample.sharpe_ratio or 0.0)
            >= candidate.out_of_sample.buy_hold_sharpe_ratio
        )
        and wf_count > 0
        and positive_wf == wf_count
        and "oos_levered_drawdown_expansion" not in candidate.quality_flags
        and "full_levered_drawdown_expansion" not in candidate.quality_flags
    )
    return {
        "passed": passed,
        "objective": "levered_alpha_vs_unlevered_buy_hold",
        "oos_alpha_vs_buy_hold_pct": candidate.out_of_sample.alpha_vs_buy_hold_pct,
        "oos_sharpe_ratio": candidate.out_of_sample.sharpe_ratio,
        "oos_buy_hold_sharpe_ratio": candidate.out_of_sample.buy_hold_sharpe_ratio,
        "oos_max_drawdown_pct": candidate.out_of_sample.max_drawdown_pct,
        "oos_buy_hold_max_drawdown_pct": candidate.out_of_sample.buy_hold_max_drawdown_pct,
        "walk_forward_positive_alpha_folds": positive_wf,
        "walk_forward_fold_count": wf_count,
        "quality_flags": candidate.quality_flags,
    }


def _drawdown_expanded(
    strategy_drawdown_pct: float,
    buy_hold_drawdown_pct: float,
    *,
    multiple: float,
) -> bool:
    strategy_magnitude = abs(min(strategy_drawdown_pct, 0.0))
    buy_hold_magnitude = abs(min(buy_hold_drawdown_pct, 0.0))
    if buy_hold_magnitude <= 0:
        return strategy_magnitude > 0
    return strategy_magnitude > buy_hold_magnitude * multiple


def _write_leverage_json(
    path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start: str | None,
    end: str | None,
    candidates: list[LeverageCandidate],
    walk_forward: list[LeverageWalkForwardSlice],
) -> Path:
    payload = {
        "strategy_name": strategy_name,
        "mode": "levered_long_exposure_research",
        "symbol": symbol,
        "timeframe": timeframe,
        "research_window": {"start": start, "end": end},
        "selection_objective": (
            "training score prioritizes excess return over unlevered buy-and-hold after "
            "financing drag; OOS and walk-forward are validation evidence"
        ),
        "acceptance_gate": _acceptance_gate(candidates[0], walk_forward),
        "assumptions": [
            "This is leverage research, not stock-selection Alpha.",
            "Returns are mark-to-market levered exposure to the same underlying.",
            "Financing drag is charged per bar on borrowed exposure.",
            "No paper orders are emitted by this research command.",
        ],
        "candidates": [_candidate_payload(item) for item in candidates],
        "walk_forward": [_walk_forward_payload(item) for item in walk_forward],
    }
    return write_json(path, payload)


def _write_leverage_report(
    path: Path,
    json_path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    start: str | None,
    end: str | None,
    candidates: list[LeverageCandidate],
    walk_forward: list[LeverageWalkForwardSlice],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Leverage Research: {strategy_name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Symbol: `{symbol}`",
        f"- Timeframe: `{timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        "- Objective: excess return over unlevered buy-and-hold after financing drag.",
        "- Caveat: this is levered beta exposure, not stock-selection Alpha.",
        "",
        "## Acceptance Gate",
        "",
        *[
            f"- {key}: `{value}`"
            for key, value in _acceptance_gate(candidates[0], walk_forward).items()
        ],
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
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _candidate_payload(candidate: LeverageCandidate) -> dict[str, Any]:
    return {
        "rank": candidate.rank,
        "params": candidate.params.__dict__,
        "score": candidate.score,
        "quality_flags": candidate.quality_flags,
        "train": candidate.train.__dict__,
        "out_of_sample": candidate.out_of_sample.__dict__,
        "full_window": candidate.full_window.__dict__,
    }


def _walk_forward_payload(item: LeverageWalkForwardSlice) -> dict[str, Any]:
    return {
        "fold": item.fold,
        "params": item.params.__dict__,
        "train": item.train.__dict__,
        "test": item.test.__dict__,
    }


def _metric_lines(label: str, metrics: LeverageMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} buy-hold: `{metrics.buy_hold_return_pct:.2f}%`",
        f"- {label} Alpha vs buy-hold: `{metrics.alpha_vs_buy_hold_pct:.2f}%`",
        f"- {label} Sharpe: `{_fmt(metrics.sharpe_ratio)}`",
        f"- {label} buy-hold Sharpe: `{_fmt(metrics.buy_hold_sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} buy-hold max drawdown: `{metrics.buy_hold_max_drawdown_pct:.2f}%`",
        f"- {label} financing cost: `{metrics.financing_cost_pct:.2f}%`",
    ]


def _split_index(frame: pd.DataFrame, out_of_sample_ratio: float) -> int:
    split = int(len(frame) * (1 - out_of_sample_ratio))
    split = max(split, 2)
    return min(split, len(frame) - 2)


def _financing_per_bar(financing_rate_pct: float, timeframe: str) -> float:
    return financing_rate_pct / 100 / _bars_per_year(timeframe)


def _bars_per_year(timeframe: str) -> float:
    mapping = {
        "5m": 252 * 78,
        "15m": 252 * 26,
        "1h": 252 * 6.5,
        "daily": 252,
        "weekly": 52,
    }
    return float(mapping.get(timeframe, 252))


def _max_drawdown_pct(equity_curve: list[float]) -> float:
    if not equity_curve:
        return 0.0
    peak = equity_curve[0]
    max_drawdown = 0.0
    for value in equity_curve:
        peak = max(peak, value)
        if peak <= 0:
            continue
        max_drawdown = min(max_drawdown, (value / peak - 1) * 100)
    return max_drawdown


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


def _empty_metrics(frame: pd.DataFrame) -> LeverageMetrics:
    return LeverageMetrics(
        bars=len(frame),
        start_timestamp=frame["timestamp"].iloc[0].isoformat() if len(frame) else None,
        end_timestamp=frame["timestamp"].iloc[-1].isoformat() if len(frame) else None,
        total_return_pct=0.0,
        buy_hold_return_pct=0.0,
        alpha_vs_buy_hold_pct=0.0,
        annualized_return_pct=None,
        sharpe_ratio=None,
        buy_hold_sharpe_ratio=None,
        max_drawdown_pct=0.0,
        buy_hold_max_drawdown_pct=0.0,
        financing_cost_pct=0.0,
    )


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
