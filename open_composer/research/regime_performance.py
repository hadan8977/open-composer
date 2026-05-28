from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import sqrt
from pathlib import Path
from statistics import fmean, pstdev
from typing import Literal

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.evaluation_policy import evaluation_policy_warnings
from open_composer.research.series_io import load_equity_series
from open_composer.storage import write_json
from open_composer.timeframes import bars_per_year

RegimePerformanceStatus = Literal["ok", "warning", "blocked", "not_applicable"]

MIN_REGIME_OBSERVATIONS = 20
DISASTER_RETURN_THRESHOLD_PCT = -40.0


@dataclass(frozen=True)
class RegimeBucketMetric:
    regime: str
    observations: int
    sample_share_pct: float
    annualized_return_pct: float | None
    sharpe: float | None
    hit_rate_pct: float | None
    max_drawdown_pct: float | None


@dataclass(frozen=True)
class RegimePerformanceResult:
    strategy_name: str
    status: RegimePerformanceStatus
    regimes: list[RegimeBucketMetric]
    min_regime_sharpe: float | None
    min_regime_return_pct: float | None
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    json_path: Path | None = None
    report_path: Path | None = None


def build_regime_performance_report(
    spec_path: Path,
    root: Path | None = None,
) -> RegimePerformanceResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    artifacts = backtest_frame(
        spec,
        frame,
        root=base,
        run_id_value=f"regime-performance-{spec.name}-full",
    )
    _, returns = load_equity_series(base, artifacts.run.run_id)
    result = assess_regime_performance(
        spec.name,
        spec.timeframe,
        frame,
        returns,
        policy_warnings=evaluation_policy_warnings(spec),
        json_path=base / "reports" / "research" / f"{spec.name}-regime-performance.json",
        report_path=base / "reports" / "research" / f"{spec.name}-regime-performance.md",
    )
    _write_regime_performance_outputs(result)
    return result


def assess_regime_performance(
    strategy_name: str,
    timeframe: str,
    frame: pd.DataFrame,
    returns: list[float],
    *,
    policy_warnings: list[str] | None = None,
    json_path: Path | None = None,
    report_path: Path | None = None,
) -> RegimePerformanceResult:
    warnings = list(policy_warnings or [])
    labels = _leak_free_regime_labels(frame)
    length = min(len(labels), len(returns))
    if length < MIN_REGIME_OBSERVATIONS:
        return RegimePerformanceResult(
            strategy_name=strategy_name,
            status="not_applicable",
            regimes=[],
            min_regime_sharpe=None,
            min_regime_return_pct=None,
            warnings=[*warnings, f"insufficient_observations:{length}"],
            json_path=json_path,
            report_path=report_path,
        )
    rows = [
        (label, float(returns[index]))
        for index, label in enumerate(labels[:length])
        if label is not None
    ]
    if len(rows) < MIN_REGIME_OBSERVATIONS:
        return RegimePerformanceResult(
            strategy_name=strategy_name,
            status="not_applicable",
            regimes=[],
            min_regime_sharpe=None,
            min_regime_return_pct=None,
            warnings=[*warnings, "insufficient_labeled_regimes"],
            json_path=json_path,
            report_path=report_path,
        )
    regimes: list[RegimeBucketMetric] = []
    for regime in sorted({label for label, _ in rows}):
        values = [value for label, value in rows if label == regime]
        regimes.append(_regime_metric(regime, values, len(rows), timeframe))
    seen = {metric.regime for metric in regimes}
    if "bear_high_vol" not in seen:
        warnings.append("regime_unseen:bear_high_vol")
    thin_threshold = max(5, int(len(rows) * 0.05))
    for metric in regimes:
        if metric.observations < thin_threshold:
            warnings.append(f"regime_thin:{metric.regime}:{metric.observations}")
    returns_by_regime = [
        metric.annualized_return_pct
        for metric in regimes
        if metric.annualized_return_pct is not None
    ]
    sharpes = [metric.sharpe for metric in regimes if metric.sharpe is not None]
    min_return = min(returns_by_regime) if returns_by_regime else None
    min_sharpe = min(sharpes) if sharpes else None
    blockers: list[str] = []
    if min_return is not None and min_return < DISASTER_RETURN_THRESHOLD_PCT:
        blockers.append(f"min_regime_return_disaster:{min_return:.2f}%")
    status: RegimePerformanceStatus = "blocked" if blockers else "warning" if warnings else "ok"
    return RegimePerformanceResult(
        strategy_name=strategy_name,
        status=status,
        regimes=regimes,
        min_regime_sharpe=min_sharpe,
        min_regime_return_pct=min_return,
        blockers=blockers,
        warnings=warnings,
        json_path=json_path,
        report_path=report_path,
    )


def _write_regime_performance_outputs(result: RegimePerformanceResult) -> None:
    if result.json_path is None or result.report_path is None:
        return
    write_json(
        result.json_path,
        {
            **asdict(result),
            "json_path": str(result.json_path),
            "report_path": str(result.report_path),
            "interpretation": (
                "Regime performance is a leak-free trailing-label proxy. It checks whether "
                "strategy returns remain acceptable across observed market regimes."
            ),
        },
    )
    ensure_dir(result.report_path.parent)
    lines = [
        f"# Regime Performance: {result.strategy_name}",
        "",
        f"- Status: `{result.status}`",
        f"- Minimum regime Sharpe: `{_fmt(result.min_regime_sharpe)}`",
        f"- Minimum regime annualized return: `{_fmt_pct(result.min_regime_return_pct)}`",
        f"- Blockers: `{', '.join(result.blockers) or 'none'}`",
        f"- Warnings: `{', '.join(result.warnings) or 'none'}`",
        "",
        "| Regime | Obs | Share | Ann Return | Sharpe | Hit Rate | Max DD |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for metric in result.regimes:
        lines.append(
            f"| `{metric.regime}` | {metric.observations} | "
            f"{metric.sample_share_pct:.2f}% | {_fmt_pct(metric.annualized_return_pct)} | "
            f"{_fmt(metric.sharpe)} | {_fmt_pct(metric.hit_rate_pct)} | "
            f"{_fmt_pct(metric.max_drawdown_pct)} |"
        )
    result.report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _leak_free_regime_labels(frame: pd.DataFrame) -> list[str | None]:
    close = pd.to_numeric(frame["close"], errors="coerce").reset_index(drop=True)
    returns = close.pct_change()
    trend_window = min(60, max(10, len(close) // 5))
    vol_window = min(20, max(5, len(close) // 10))
    labels: list[str | None] = []
    historical_vols: list[float] = []
    for index in range(len(close)):
        if index < max(trend_window, vol_window) or close.iloc[index - trend_window] == 0:
            labels.append(None)
            continue
        trailing_return = close.iloc[index] / close.iloc[index - trend_window] - 1.0
        vol = float(returns.iloc[index - vol_window + 1 : index + 1].std())
        historical_vols.append(vol)
        past = historical_vols[:-1]
        if not past:
            labels.append(None)
            continue
        percentile = sum(1 for value in past if value <= vol) / len(past)
        trend = "bull" if trailing_return >= 0.0 else "bear"
        if percentile < 0.33:
            vol_label = "low_vol"
        elif percentile < 0.67:
            vol_label = "mid_vol"
        else:
            vol_label = "high_vol"
        labels.append(f"{trend}_{vol_label}")
    return labels


def _regime_metric(
    regime: str,
    values: list[float],
    total_count: int,
    timeframe: str,
) -> RegimeBucketMetric:
    return RegimeBucketMetric(
        regime=regime,
        observations=len(values),
        sample_share_pct=(len(values) / total_count) * 100 if total_count else 0.0,
        annualized_return_pct=fmean(values) * bars_per_year(timeframe) * 100 if values else None,
        sharpe=_sharpe(values, timeframe),
        hit_rate_pct=(sum(1 for value in values if value > 0) / len(values)) * 100
        if values
        else None,
        max_drawdown_pct=_max_drawdown_pct(values),
    )


def _sharpe(values: list[float], timeframe: str) -> float | None:
    if len(values) < 2:
        return None
    stddev = pstdev(values)
    if stddev <= 0.0:
        return None
    return (fmean(values) / stddev) * sqrt(max(bars_per_year(timeframe), 1.0))


def _max_drawdown_pct(values: list[float]) -> float | None:
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    for value in values:
        equity *= 1.0 + value
        peak = max(peak, equity)
        if peak > 0.0:
            max_drawdown = min(max_drawdown, equity / peak - 1.0)
    return max_drawdown * 100


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
