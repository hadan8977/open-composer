from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import sqrt
from pathlib import Path
from statistics import fmean, pstdev

import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.research.factor_panel import load_factor_panel, normalize_factor_panel
from open_composer.storage import write_json

LOW_PANEL_COVERAGE_PCT = 80.0
MIN_CROSS_SECTIONAL_TIMESTAMPS = 5


@dataclass(frozen=True)
class FactorPanelMetric:
    factor_name: str
    horizon: int
    observations: int
    timestamp_count: int
    symbol_count: int
    coverage_pct: float
    rank_ic: float | None
    ic_mean: float | None
    ic_std: float | None
    icir: float | None
    ic_t_stat: float | None
    decay_by_horizon: dict[str, float | None] = field(default_factory=dict)
    quantile_returns_pct: dict[str, float] = field(default_factory=dict)
    top_bottom_spread_pct: float | None = None
    top_quantile_turnover_pct: float | None = None
    neutralized_rank_ic: float | None = None
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FactorPanelReport:
    status: str
    panel_path: Path
    report_path: Path
    json_path: Path
    factor_metrics: list[FactorPanelMetric]
    factor_correlation_matrix: dict[str, dict[str, float | None]]
    quality_flags: list[str] = field(default_factory=list)


def run_factor_lab_v2(
    panel_path: Path,
    root: Path | None = None,
    *,
    strategy_name: str | None = None,
    quantiles: int = 5,
    require_visible_at_for_feature_packets: bool = True,
) -> FactorPanelReport:
    if quantiles < 2:
        raise ValueError("--quantiles must be at least 2")
    base = root or project_root()
    panel = load_factor_panel(panel_path)
    label = strategy_name or panel_path.stem
    result = assess_factor_panel(
        panel,
        panel_path=panel_path,
        root=base,
        report_name=label,
        quantiles=quantiles,
        require_visible_at_for_feature_packets=require_visible_at_for_feature_packets,
    )
    _write_factor_panel_outputs(result)
    return result


def assess_factor_panel(
    panel: pd.DataFrame,
    *,
    panel_path: Path,
    root: Path | None = None,
    report_name: str = "factor-panel",
    quantiles: int = 5,
    require_visible_at_for_feature_packets: bool = True,
) -> FactorPanelReport:
    base = root or project_root()
    normalized = normalize_factor_panel(panel)
    quality_flags: list[str] = []
    if require_visible_at_for_feature_packets:
        feature_rows = normalized["source"].astype(str).eq("feature_packet")
        if feature_rows.any() and normalized.loc[feature_rows, "visible_at"].isna().any():
            quality_flags.append("feature_packet_visible_at_missing")
    factor_metrics: list[FactorPanelMetric] = []
    for (factor_name, horizon), group in normalized.groupby(["factor_name", "horizon"]):
        factor_metrics.append(
            _factor_panel_metric(
                factor_name=str(factor_name),
                horizon=int(horizon),
                panel=group,
                all_panel=normalized,
                quantiles=quantiles,
            )
        )
    quality_flags.extend(
        f"{metric.factor_name}:{flag}" for metric in factor_metrics for flag in metric.flags
    )
    correlation = _factor_correlation_matrix(normalized)
    status = "ok"
    if quality_flags:
        status = "warning"
    if not factor_metrics or all(
        "insufficient_cross_sectional_timestamps" in metric.flags for metric in factor_metrics
    ):
        status = "blocked"
    if "feature_packet_visible_at_missing" in quality_flags:
        status = "blocked"
    json_path = base / "reports" / "research" / f"{report_name}-factor-lab-v2.json"
    report_path = base / "reports" / "research" / f"{report_name}-factor-lab-v2.md"
    return FactorPanelReport(
        status=status,
        panel_path=panel_path,
        report_path=report_path,
        json_path=json_path,
        factor_metrics=factor_metrics,
        factor_correlation_matrix=correlation,
        quality_flags=quality_flags,
    )


def _factor_panel_metric(
    *,
    factor_name: str,
    horizon: int,
    panel: pd.DataFrame,
    all_panel: pd.DataFrame,
    quantiles: int,
) -> FactorPanelMetric:
    valid = panel.dropna(subset=["factor_value", "forward_return"]).copy()
    observations = int(len(valid))
    timestamp_count = int(valid["timestamp"].nunique())
    symbol_count = int(valid["symbol"].nunique())
    coverage_pct = float((observations / len(panel)) * 100) if len(panel) else 0.0
    flags: list[str] = []
    if coverage_pct < LOW_PANEL_COVERAGE_PCT:
        flags.append("low_coverage")
    ic_values = _cross_sectional_rank_ics(valid)
    ic_mean = fmean(ic_values) if ic_values else None
    ic_std = pstdev(ic_values) if len(ic_values) > 1 else None
    icir = None if ic_mean is None or ic_std in {None, 0.0} else ic_mean / ic_std
    ic_t_stat = (
        None
        if ic_mean is None or ic_std in {None, 0.0}
        else ic_mean / (ic_std / sqrt(len(ic_values)))
    )
    if len(ic_values) < MIN_CROSS_SECTIONAL_TIMESTAMPS:
        flags.append("insufficient_cross_sectional_timestamps")
    rank_ic = ic_mean
    quantile_returns, spread, turnover = _quantile_metrics(valid, quantiles)
    neutralized_rank_ic = _neutralized_rank_ic(valid)
    decay = _decay_by_horizon(all_panel, factor_name)
    if rank_ic is None:
        flags.append("rank_ic_unavailable")
    elif abs(rank_ic) < 0.02:
        flags.append("weak_rank_ic")
    if spread is None:
        flags.append("quantile_spread_unavailable")
    return FactorPanelMetric(
        factor_name=factor_name,
        horizon=horizon,
        observations=observations,
        timestamp_count=timestamp_count,
        symbol_count=symbol_count,
        coverage_pct=coverage_pct,
        rank_ic=rank_ic,
        ic_mean=ic_mean,
        ic_std=ic_std,
        icir=icir,
        ic_t_stat=ic_t_stat,
        decay_by_horizon=decay,
        quantile_returns_pct=quantile_returns,
        top_bottom_spread_pct=spread,
        top_quantile_turnover_pct=turnover,
        neutralized_rank_ic=neutralized_rank_ic,
        flags=flags,
    )


def _cross_sectional_rank_ics(panel: pd.DataFrame) -> list[float]:
    values: list[float] = []
    for _, group in panel.groupby("timestamp"):
        if group["symbol"].nunique() < 2:
            continue
        value = _safe_corr(group["factor_value"].rank(), group["forward_return"].rank())
        if value is not None:
            values.append(value)
    return values


def _quantile_metrics(
    panel: pd.DataFrame,
    quantiles: int,
) -> tuple[dict[str, float], float | None, float | None]:
    rows: list[pd.DataFrame] = []
    for _, group in panel.groupby("timestamp"):
        if group["factor_value"].nunique() < 2 or len(group) < 2:
            continue
        ranked = group.copy()
        try:
            ranked["quantile"] = pd.qcut(
                ranked["factor_value"].rank(method="first"),
                q=min(quantiles, len(ranked)),
                labels=False,
                duplicates="drop",
            )
        except ValueError:
            continue
        rows.append(ranked)
    if not rows:
        return {}, None, None
    labeled = pd.concat(rows)
    returns = {
        str(int(quantile) + 1): float(value * 100)
        for quantile, value in labeled.groupby("quantile")["forward_return"].mean().items()
    }
    if not returns:
        return {}, None, None
    keys = sorted(returns, key=lambda value: int(value))
    spread = returns[keys[-1]] - returns[keys[0]] if len(keys) >= 2 else None
    turnover = _top_quantile_turnover(labeled, top_quantile=max(int(key) for key in keys) - 1)
    return returns, spread, turnover


def _top_quantile_turnover(panel: pd.DataFrame, *, top_quantile: int) -> float | None:
    previous: set[str] | None = None
    turnovers: list[float] = []
    for _, group in panel.sort_values("timestamp").groupby("timestamp"):
        current = set(group.loc[group["quantile"] == top_quantile, "symbol"].astype(str))
        if previous is not None and (previous or current):
            union = len(previous | current)
            overlap = len(previous & current)
            turnovers.append(1.0 - (overlap / union if union else 0.0))
        previous = current
    return None if not turnovers else float(fmean(turnovers) * 100)


def _neutralized_rank_ic(panel: pd.DataFrame) -> float | None:
    working = panel.copy()
    neutralizers = [
        column
        for column in ["group", "market_cap_bucket"]
        if column in working.columns and working[column].notna().any()
    ]
    if not neutralizers:
        return None
    for column in neutralizers:
        working["factor_value"] = working["factor_value"] - working.groupby(["timestamp", column])[
            "factor_value"
        ].transform("mean")
    values = _cross_sectional_rank_ics(working)
    return fmean(values) if values else None


def _decay_by_horizon(panel: pd.DataFrame, factor_name: str) -> dict[str, float | None]:
    output: dict[str, float | None] = {}
    factor_panel = panel[panel["factor_name"] == factor_name]
    for horizon, group in factor_panel.groupby("horizon"):
        values = _cross_sectional_rank_ics(group.dropna(subset=["factor_value", "forward_return"]))
        output[str(int(horizon))] = fmean(values) if values else None
    return output


def _factor_correlation_matrix(panel: pd.DataFrame) -> dict[str, dict[str, float | None]]:
    pivot = panel.pivot_table(
        index=["timestamp", "symbol"],
        columns="factor_name",
        values="factor_value",
        aggfunc="mean",
    )
    factors = [str(column) for column in pivot.columns]
    output: dict[str, dict[str, float | None]] = {}
    for left in factors:
        output[left] = {}
        for right in factors:
            output[left][right] = _safe_corr(pivot[left], pivot[right])
    return output


def _safe_corr(left: pd.Series, right: pd.Series) -> float | None:
    joined = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(joined) < 2 or joined["left"].nunique() < 2 or joined["right"].nunique() < 2:
        return None
    value = joined["left"].corr(joined["right"])
    return None if pd.isna(value) else float(value)


def _write_factor_panel_outputs(result: FactorPanelReport) -> None:
    write_json(
        result.json_path,
        {
            **asdict(result),
            "panel_path": str(result.panel_path),
            "report_path": str(result.report_path),
            "json_path": str(result.json_path),
        },
    )
    ensure_dir(result.report_path.parent)
    lines = [
        "# Factor Lab V2",
        "",
        f"- Status: `{result.status}`",
        f"- Panel: `{result.panel_path}`",
        f"- Quality flags: `{', '.join(result.quality_flags) or 'none'}`",
        "",
        "| Factor | Horizon | Obs | Symbols | RankIC | ICIR | t-stat | Spread | Turnover | Flags |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for metric in result.factor_metrics:
        lines.append(
            f"| `{metric.factor_name}` | {metric.horizon} | {metric.observations} | "
            f"{metric.symbol_count} | {_fmt(metric.rank_ic)} | {_fmt(metric.icir)} | "
            f"{_fmt(metric.ic_t_stat)} | {_fmt_pct(metric.top_bottom_spread_pct)} | "
            f"{_fmt_pct(metric.top_quantile_turnover_pct)} | "
            f"`{', '.join(metric.flags) or 'none'}` |"
        )
    result.report_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
