from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import sqrt
from pathlib import Path
from statistics import fmean, pstdev
from typing import Literal

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.evaluation_policy import (
    evaluation_policy_warnings,
    require_recent_positive,
)
from open_composer.research.series_io import load_equity_series
from open_composer.storage import write_json
from open_composer.timeframes import bars_per_year

AlphaDecayStatus = Literal["ok", "warning", "blocked", "not_applicable"]

MIN_DECAY_OBSERVATIONS = 30
OLD_PNL_CONCENTRATION_BLOCK = 0.70


@dataclass(frozen=True)
class AlphaDecayResult:
    strategy_name: str
    status: AlphaDecayStatus
    slope: float | None
    recent_sharpe: float | None
    old_sharpe: float | None
    mid_sharpe: float | None
    pnl_concentration_old: float | None
    alpha_stale: bool
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    json_path: Path | None = None
    report_path: Path | None = None


def build_alpha_decay_report(
    spec_path: Path,
    root: Path | None = None,
) -> AlphaDecayResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    artifacts = backtest_frame(
        spec,
        frame,
        root=base,
        run_id_value=f"alpha-decay-{spec.name}-full",
    )
    _, returns = load_equity_series(base, artifacts.run.run_id)
    result = assess_alpha_decay(
        spec.name,
        spec.timeframe,
        returns,
        policy_warnings=evaluation_policy_warnings(spec),
        require_recent_positive=require_recent_positive(spec),
        json_path=base / "reports" / "research" / f"{spec.name}-alpha-decay.json",
        report_path=base / "reports" / "research" / f"{spec.name}-alpha-decay.md",
    )
    _write_alpha_decay_outputs(result)
    return result


def assess_alpha_decay(
    strategy_name: str,
    timeframe: str,
    returns: list[float],
    *,
    policy_warnings: list[str] | None = None,
    require_recent_positive: bool = True,
    json_path: Path | None = None,
    report_path: Path | None = None,
) -> AlphaDecayResult:
    clean = [float(value) for value in returns if value == value]
    warnings = list(policy_warnings or [])
    blockers: list[str] = []
    if len(clean) < MIN_DECAY_OBSERVATIONS:
        result = AlphaDecayResult(
            strategy_name=strategy_name,
            status="not_applicable",
            slope=None,
            recent_sharpe=None,
            old_sharpe=None,
            mid_sharpe=None,
            pnl_concentration_old=None,
            alpha_stale=False,
            warnings=[*warnings, f"insufficient_observations:{len(clean)}"],
            json_path=json_path,
            report_path=report_path,
        )
        return result

    thirds = _thirds(clean)
    old_sharpe = _sharpe(thirds[0], timeframe)
    mid_sharpe = _sharpe(thirds[1], timeframe)
    recent_sharpe = _sharpe(thirds[2], timeframe)
    rolling = _rolling_sharpe(clean, timeframe)
    slope = _linear_slope(rolling)
    pnl_concentration_old = _old_pnl_concentration(thirds)
    alpha_stale = False

    if pnl_concentration_old is not None and pnl_concentration_old > OLD_PNL_CONCENTRATION_BLOCK:
        blockers.append(f"old_pnl_concentration_high:{pnl_concentration_old:.3f}")
        alpha_stale = True
    if (
        require_recent_positive
        and recent_sharpe is not None
        and recent_sharpe <= 0.0
        and old_sharpe is not None
        and old_sharpe > 0.5
    ):
        blockers.append(f"recent_sharpe_non_positive_after_strong_old_period:{recent_sharpe:.3f}")
        alpha_stale = True
    if slope is not None and slope < -0.02 and not blockers:
        warnings.append(f"rolling_sharpe_slope_negative:{slope:.5f}")
    if (
        old_sharpe is not None
        and recent_sharpe is not None
        and recent_sharpe < old_sharpe * 0.5
        and not blockers
    ):
        warnings.append(f"recent_sharpe_less_than_half_old:{recent_sharpe:.3f}<{old_sharpe:.3f}")

    status: AlphaDecayStatus = "blocked" if blockers else "warning" if warnings else "ok"
    return AlphaDecayResult(
        strategy_name=strategy_name,
        status=status,
        slope=slope,
        recent_sharpe=recent_sharpe,
        old_sharpe=old_sharpe,
        mid_sharpe=mid_sharpe,
        pnl_concentration_old=pnl_concentration_old,
        alpha_stale=alpha_stale,
        blockers=blockers,
        warnings=warnings,
        json_path=json_path,
        report_path=report_path,
    )


def _write_alpha_decay_outputs(result: AlphaDecayResult) -> None:
    if result.json_path is None or result.report_path is None:
        return
    write_json(
        result.json_path,
        {
            **asdict(result),
            "json_path": str(result.json_path),
            "report_path": str(result.report_path),
            "interpretation": (
                "Alpha decay is a lightweight proxy. A blocked result means recent "
                "returns or old-period concentration suggest the edge may be stale."
            ),
        },
    )
    ensure_dir(result.report_path.parent)
    lines = [
        f"# Alpha Decay: {result.strategy_name}",
        "",
        f"- Status: `{result.status}`",
        f"- Rolling Sharpe slope: `{_fmt(result.slope)}`",
        f"- Old Sharpe: `{_fmt(result.old_sharpe)}`",
        f"- Mid Sharpe: `{_fmt(result.mid_sharpe)}`",
        f"- Recent Sharpe: `{_fmt(result.recent_sharpe)}`",
        f"- Old PnL concentration: `{_fmt(result.pnl_concentration_old)}`",
        f"- Alpha stale: `{result.alpha_stale}`",
        f"- Blockers: `{', '.join(result.blockers) or 'none'}`",
        f"- Warnings: `{', '.join(result.warnings) or 'none'}`",
    ]
    result.report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _thirds(values: list[float]) -> tuple[list[float], list[float], list[float]]:
    third = len(values) // 3
    return values[:third], values[third : 2 * third], values[2 * third :]


def _rolling_sharpe(values: list[float], timeframe: str) -> list[float]:
    window = max(10, min(63, len(values) // 3))
    if len(values) < window:
        return []
    return [
        _sharpe(values[start : start + window], timeframe) or 0.0
        for start in range(0, len(values) - window + 1)
    ]


def _sharpe(values: list[float], timeframe: str) -> float | None:
    if len(values) < 2:
        return None
    stddev = pstdev(values)
    if stddev <= 0.0:
        return None
    return (fmean(values) / stddev) * sqrt(max(bars_per_year(timeframe), 1.0))


def _linear_slope(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    x_mean = (len(values) - 1) / 2.0
    y_mean = fmean(values)
    denom = sum((index - x_mean) ** 2 for index in range(len(values)))
    if denom == 0:
        return None
    return sum((index - x_mean) * (value - y_mean) for index, value in enumerate(values)) / denom


def _old_pnl_concentration(
    thirds: tuple[list[float], list[float], list[float]],
) -> float | None:
    pnls = [sum(segment) for segment in thirds]
    positive_total = sum(value for value in pnls if value > 0)
    if positive_total <= 0.0:
        return None
    return max(0.0, pnls[0]) / positive_total


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
