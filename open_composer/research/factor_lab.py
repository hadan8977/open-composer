from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Any

import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.expressions import prepare_factor_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.metadata import frame_data_profile, runtime_payload
from open_composer.storage import write_json

MIN_FACTOR_OBSERVATIONS = 20
LOW_COVERAGE_PCT = 80.0
HIGH_FACTOR_CORRELATION = 0.9


@dataclass(frozen=True)
class FactorLabFactorMetric:
    name: str
    source: str
    coverage_pct: float
    observations: int
    unique_values: int
    forward_return_corr: float | None
    rank_ic: float | None
    rolling_rank_ic_mean: float | None
    rolling_rank_ic_min: float | None
    stability_score: float | None
    quantile_mean_forward_return_pct: dict[str, float]
    horizon_mean_forward_return_pct: dict[str, float]
    top_bottom_spread_pct: float | None
    quantile_turnover_pct: float | None
    flags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class FactorLabResult:
    strategy_name: str
    status: str
    report_path: Path
    json_path: Path
    factor_metrics: list[FactorLabFactorMetric]
    factor_correlation_matrix: dict[str, dict[str, float | None]]
    quality_flags: list[str]


def run_factor_lab(
    spec_path: Path,
    root: Path | None = None,
    *,
    forward_bars: int = 1,
    horizons: list[int] | None = None,
    quantiles: int = 5,
) -> FactorLabResult:
    started_at = perf_counter()
    if forward_bars < 1:
        raise ValueError("--forward-bars must be at least 1")
    if quantiles < 2:
        raise ValueError("--quantiles must be at least 2")
    selected_horizons = sorted({item for item in (horizons or [1, 5, 10]) if item >= 1})
    if not selected_horizons:
        selected_horizons = [forward_bars]

    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    frame.attrs.update({"strategy_name": spec.name})
    data_profile = frame_data_profile(
        frame,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        provider=spec.data.source,
        feed=spec.data.feed,
        source_mode=frame.attrs.get("data_source_mode") or spec.data.source,
        path=frame.attrs.get("data_source_path") or spec.data.path,
    )
    quality_flags: list[str] = []
    factor_metrics: list[FactorLabFactorMetric] = []
    factor_correlation_matrix: dict[str, dict[str, float | None]] = {}

    if not spec.factors:
        quality_flags.append("no_custom_factors")
        status = "blocked"
    else:
        prepared = prepare_factor_frame(
            frame,
            spec.factors,
            root=base,
            symbol=spec.primary_symbol,
            require_feature_symbol=False,
        )
        forward_returns = _forward_returns(prepared, forward_bars)
        horizon_returns = {
            horizon: _forward_returns(prepared, horizon) for horizon in selected_horizons
        }
        factor_metrics = [
            _factor_metric(
                spec,
                prepared,
                name,
                forward_returns,
                horizon_returns,
                quantiles=quantiles,
            )
            for name in spec.factors
        ]
        factor_correlation_matrix = _factor_correlation_matrix(prepared, list(spec.factors))
        quality_flags.extend(_correlation_flags(factor_correlation_matrix))
        quality_flags.extend(
            f"{metric.name}:{flag}" for metric in factor_metrics for flag in metric.flags
        )
        status = "ok" if not quality_flags else "warning"
        if all("insufficient_observations" in metric.flags for metric in factor_metrics):
            status = "blocked"

    report_path = base / "reports" / "research" / f"{spec.name}-factor-lab.md"
    json_path = base / "reports" / "research" / f"{spec.name}-factor-lab.json"
    _write_factor_lab_json(
        json_path,
        spec_path,
        spec,
        status,
        factor_metrics,
        factor_correlation_matrix,
        quality_flags,
        forward_bars,
        selected_horizons,
        quantiles,
        data_profile,
        runtime_payload(started_at, {}),
    )
    _write_factor_lab_report(
        report_path,
        spec_path,
        spec,
        status,
        factor_metrics,
        factor_correlation_matrix,
        quality_flags,
        forward_bars,
        selected_horizons,
        quantiles,
        data_profile,
        json_path,
    )
    return FactorLabResult(
        strategy_name=spec.name,
        status=status,
        report_path=report_path,
        json_path=json_path,
        factor_metrics=factor_metrics,
        factor_correlation_matrix=factor_correlation_matrix,
        quality_flags=quality_flags,
    )


def _factor_metric(
    spec: StrategySpec,
    frame: pd.DataFrame,
    name: str,
    forward_returns: pd.Series,
    horizon_returns: dict[int, pd.Series],
    *,
    quantiles: int,
) -> FactorLabFactorMetric:
    raw = pd.to_numeric(frame[name], errors="coerce")
    coverage_pct = float(raw.notna().mean() * 100) if len(raw) else 0.0
    joined = pd.DataFrame({"factor": raw, "forward_return": forward_returns}).dropna()
    observations = int(len(joined))
    unique_values = int(raw.nunique(dropna=True))
    flags: list[str] = []
    if raw.dropna().empty:
        flags.append("all_nan")
    if coverage_pct < LOW_COVERAGE_PCT:
        flags.append("low_coverage")
    if observations < MIN_FACTOR_OBSERVATIONS:
        flags.append("insufficient_observations")
    if unique_values <= 1 and observations >= MIN_FACTOR_OBSERVATIONS:
        flags.append("zero_variance")
    if unique_values < 3:
        flags.append("low_unique_values")

    forward_corr = _safe_corr(joined["factor"], joined["forward_return"])
    rank_ic = None
    if not {"all_nan", "zero_variance", "insufficient_observations"}.intersection(flags):
        rank_ic = _safe_corr(joined["factor"].rank(), joined["forward_return"].rank())
    rolling_rank_ic_values = _rolling_rank_ic(joined["factor"], joined["forward_return"])
    rolling_rank_ic_mean = (
        float(pd.Series(rolling_rank_ic_values).mean()) if rolling_rank_ic_values else None
    )
    rolling_rank_ic_min = (
        float(pd.Series(rolling_rank_ic_values).min()) if rolling_rank_ic_values else None
    )
    stability_score = _stability_score(rank_ic, rolling_rank_ic_values)
    quantile_returns, top_bottom_spread, quantile_turnover = _quantile_metrics(
        joined["factor"],
        joined["forward_return"],
        quantiles=quantiles,
    )
    horizon_mean_forward_return_pct = _horizon_mean_returns(raw, horizon_returns)
    if rank_ic is None:
        flags.append("rank_ic_unavailable")
    elif abs(rank_ic) < 0.02:
        flags.append("weak_rank_ic")
    if top_bottom_spread is None:
        flags.append("quantile_spread_unavailable")

    factor = spec.factors[name]
    return FactorLabFactorMetric(
        name=name,
        source=factor.source,
        coverage_pct=coverage_pct,
        observations=observations,
        unique_values=unique_values,
        forward_return_corr=forward_corr,
        rank_ic=rank_ic,
        rolling_rank_ic_mean=rolling_rank_ic_mean,
        rolling_rank_ic_min=rolling_rank_ic_min,
        stability_score=stability_score,
        quantile_mean_forward_return_pct=quantile_returns,
        horizon_mean_forward_return_pct=horizon_mean_forward_return_pct,
        top_bottom_spread_pct=top_bottom_spread,
        quantile_turnover_pct=quantile_turnover,
        flags=flags,
    )


def _forward_returns(frame: pd.DataFrame, forward_bars: int) -> pd.Series:
    close = pd.to_numeric(frame["close"], errors="coerce")
    return close.shift(-forward_bars) / close - 1


def _safe_corr(left: pd.Series, right: pd.Series) -> float | None:
    joined = pd.DataFrame({"left": left, "right": right}).dropna()
    if len(joined) < 2 or joined["left"].nunique() < 2 or joined["right"].nunique() < 2:
        return None
    value = joined["left"].corr(joined["right"])
    return None if pd.isna(value) else float(value)


def _rolling_rank_ic(
    factor: pd.Series,
    forward_returns: pd.Series,
    *,
    window: int = 20,
) -> list[float]:
    joined = pd.DataFrame({"factor": factor, "forward_return": forward_returns}).dropna()
    if len(joined) < max(window, 4):
        return []
    values: list[float] = []
    for start in range(0, len(joined) - window + 1):
        chunk = joined.iloc[start : start + window]
        value = _safe_corr(chunk["factor"].rank(), chunk["forward_return"].rank())
        if value is not None:
            values.append(value)
    return values


def _stability_score(rank_ic: float | None, rolling_values: list[float]) -> float | None:
    if rank_ic is None:
        return None
    if not rolling_values:
        return abs(rank_ic)
    same_sign = [
        value
        for value in rolling_values
        if (rank_ic >= 0 and value >= 0) or (rank_ic < 0 and value < 0)
    ]
    return abs(rank_ic) * (len(same_sign) / len(rolling_values))


def _horizon_mean_returns(
    factor: pd.Series,
    horizon_returns: dict[int, pd.Series],
) -> dict[str, float]:
    output: dict[str, float] = {}
    for horizon, returns in horizon_returns.items():
        joined = pd.DataFrame({"factor": factor, "forward_return": returns}).dropna()
        if joined.empty:
            continue
        output[str(horizon)] = float(joined["forward_return"].mean() * 100)
    return output


def _quantile_metrics(
    factor: pd.Series,
    forward_returns: pd.Series,
    *,
    quantiles: int,
) -> tuple[dict[str, float], float | None, float | None]:
    joined = pd.DataFrame({"factor": factor, "forward_return": forward_returns}).dropna()
    if len(joined) < quantiles or joined["factor"].nunique() < 2:
        return {}, None, None
    try:
        labels = pd.qcut(joined["factor"], q=quantiles, labels=False, duplicates="drop")
    except ValueError:
        return {}, None, None
    if labels.isna().all():
        return {}, None, None
    grouped = joined.groupby(labels, observed=True)["forward_return"].mean() * 100
    quantile_returns = {str(int(index)): float(value) for index, value in grouped.items()}
    top_bottom_spread = None
    if len(grouped) >= 2:
        top_bottom_spread = float(grouped.iloc[-1] - grouped.iloc[0])
    turnover = float(labels.diff().fillna(0).ne(0).mean() * 100)
    return quantile_returns, top_bottom_spread, turnover


def _factor_correlation_matrix(
    frame: pd.DataFrame,
    factor_names: list[str],
) -> dict[str, dict[str, float | None]]:
    values = frame[factor_names].apply(pd.to_numeric, errors="coerce")
    if values.empty:
        return {}
    corr = values.corr()
    matrix: dict[str, dict[str, float | None]] = {}
    for left in factor_names:
        matrix[left] = {}
        for right in factor_names:
            value = corr.loc[left, right] if left in corr.index and right in corr.columns else None
            matrix[left][right] = None if pd.isna(value) else round(float(value), 4)
    return matrix


def _correlation_flags(matrix: dict[str, dict[str, float | None]]) -> list[str]:
    flags: list[str] = []
    seen: set[tuple[str, str]] = set()
    for left, row in matrix.items():
        for right, value in row.items():
            if left == right or value is None:
                continue
            pair = tuple(sorted((left, right)))
            if pair in seen:
                continue
            seen.add(pair)
            if abs(value) >= HIGH_FACTOR_CORRELATION:
                flags.append(f"high_factor_correlation:{pair[0]}:{pair[1]}:{value:.4f}")
    return flags


def _write_factor_lab_json(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: str,
    factor_metrics: list[FactorLabFactorMetric],
    factor_correlation_matrix: dict[str, dict[str, float | None]],
    quality_flags: list[str],
    forward_bars: int,
    horizons: list[int],
    quantiles: int,
    data_profile: dict[str, Any],
    runtime: dict[str, Any],
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "status": status,
        "forward_bars": forward_bars,
        "horizons": horizons,
        "quantiles": quantiles,
        "data_profile": data_profile,
        "quality_flags": quality_flags,
        "factor_metrics": [asdict(metric) for metric in factor_metrics],
        "factor_correlation_matrix": factor_correlation_matrix,
        "runtime": runtime,
    }
    return write_json(path, payload)


def _write_factor_lab_report(
    path: Path,
    spec_path: Path,
    spec: StrategySpec,
    status: str,
    factor_metrics: list[FactorLabFactorMetric],
    factor_correlation_matrix: dict[str, dict[str, float | None]],
    quality_flags: list[str],
    forward_bars: int,
    horizons: list[int],
    quantiles: int,
    data_profile: dict[str, Any],
    json_path: Path,
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Factor Lab: {spec.name}",
        "",
        f"- Source spec: `{spec_path}`",
        f"- JSON: `{json_path}`",
        f"- Status: `{status}`",
        f"- Forward bars: `{forward_bars}`",
        f"- Horizons: `{horizons}`",
        f"- Quantiles: `{quantiles}`",
        f"- Data source/feed: `{data_profile.get('provider')}` / "
        f"`{data_profile.get('feed') or 'none'}`",
        f"- Source mode: `{data_profile.get('source_mode')}`",
        "",
        "## Quality Flags",
        "",
    ]
    if quality_flags:
        lines.extend(f"- `{flag}`" for flag in quality_flags)
    else:
        lines.append("- none")
    lines.extend(["", "## Factor Metrics", ""])
    if factor_metrics:
        lines.extend(
            [
                "| Factor | Source | Coverage | Obs | Unique | Corr | RankIC | "
                "Rolling RankIC | Stability | Spread | Turnover | Flags |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
            ]
        )
        for metric in factor_metrics:
            lines.append(
                "| "
                f"`{metric.name}` | `{metric.source}` | "
                f"{metric.coverage_pct:.2f}% | "
                f"{metric.observations} | "
                f"{metric.unique_values} | "
                f"{_fmt(metric.forward_return_corr)} | "
                f"{_fmt(metric.rank_ic)} | "
                f"{_fmt(metric.rolling_rank_ic_mean)} | "
                f"{_fmt(metric.stability_score)} | "
                f"{_fmt_pct(metric.top_bottom_spread_pct)} | "
                f"{_fmt_pct(metric.quantile_turnover_pct)} | "
                f"`{', '.join(metric.flags) or 'none'}` |"
            )
    else:
        lines.append("- No custom factors available for Factor Lab.")

    lines.extend(["", "## Factor Correlation Matrix", ""])
    lines.extend(_correlation_matrix_lines(factor_correlation_matrix))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _correlation_matrix_lines(matrix: dict[str, dict[str, float | None]]) -> list[str]:
    if not matrix:
        return ["- n/a"]
    names = list(matrix)
    lines = [
        "| Factor | " + " | ".join(f"`{name}`" for name in names) + " |",
        "| --- | " + " | ".join(["---:"] * len(names)) + " |",
    ]
    for left in names:
        values = [_fmt(matrix[left].get(right)) for right in names]
        lines.append(f"| `{left}` | " + " | ".join(values) + " |")
    return lines


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _fmt_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
