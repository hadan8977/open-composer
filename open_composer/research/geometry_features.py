from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

import numpy as np
import pandas as pd

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.kernel import ResearchArtifactWriter, ResearchRunIndexRecord
from open_composer.research.metadata import (
    frame_data_profile,
    runtime_payload,
    workspace_relative_path,
)
from open_composer.strategy_versions import strategy_content_hash


@dataclass(frozen=True)
class GeometryFeatureReportResult:
    strategy_name: str
    status: str
    report_path: Path
    json_path: Path
    feature_family: str
    research_only: bool
    promotion_blockers: list[str]


def build_geometry_feature_report(
    spec_path: Path,
    root: Path | None = None,
    *,
    window_bars: int = 20,
) -> GeometryFeatureReportResult:
    if window_bars < 5:
        raise ValueError("--window-bars must be at least 5")
    started_at = perf_counter()
    base = root or Path.cwd()
    writer = ResearchArtifactWriter(base)
    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, base)
    data_profile = frame_data_profile(
        frame,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        provider=spec.data.source,
        feed=spec.data.feed,
        source_mode=frame.attrs.get("data_source_mode") or spec.data.source,
        path=frame.attrs.get("data_source_path") or spec.data.path,
    )
    normalized = _feature_frame(frame)
    feature_summary = _geometry_summary(normalized, window_bars=window_bars)
    warnings = _warnings(feature_summary, data_profile)
    promotion_blockers = [
        "research_only_feature_family",
        "requires_simple_baseline_comparison",
        "requires_out_of_sample_or_walk_forward_validation",
        "requires_cost_capacity_and_execution_reality_review",
        "requires_factor_lab_ablation_and_marginal_lift_evidence",
    ]
    status = "blocked"
    report_path = base / "reports" / "research" / f"{spec.name}-geometry-features.md"
    json_path = base / "reports" / "research" / f"{spec.name}-geometry-features.json"
    runtime = runtime_payload(started_at, {})
    index_record = ResearchRunIndexRecord(
        run_id=f"geometry-features-{spec.name}-{strategy_content_hash(spec)[:12]}",
        strategy_name=spec.name,
        source_spec_path=workspace_relative_path(spec_path, base),
        spec_hash=strategy_content_hash(spec),
        status=status,
        kind="geometry_features",
        data_profile=data_profile,
        candidate_count=1,
        trial_count=1,
        runtime_seconds=float(runtime["total"]),
        gate_status=status,
        blocked_items=promotion_blockers,
        warning_items=warnings,
        report_path=workspace_relative_path(report_path, base),
        json_path=workspace_relative_path(json_path, base),
        source_artifacts={
            "source_spec": workspace_relative_path(spec_path, base),
        },
    )
    payload = {
        "strategy_name": spec.name,
        "status": status,
        "kind": "geometry_features",
        "feature_family": "geometry_topology_research_sandbox",
        "research_only": True,
        "source_spec_path": workspace_relative_path(spec_path, base),
        "spec_hash": strategy_content_hash(spec),
        "window_bars": window_bars,
        "data_profile": data_profile,
        "feature_summary": feature_summary,
        "baseline_requirements": [
            "Compare against momentum, reversal, volatility, volume, and liquidity baselines.",
            "Evaluate marginal lift after costs and capacity constraints.",
            "Run OOS or walk-forward validation before any promotion discussion.",
            "Run ablation against existing StrategySpec factors.",
        ],
        "promotion_blockers": promotion_blockers,
        "warnings": warnings,
        "runtime": runtime,
        "research_run_index_record": index_record.model_dump(mode="json"),
    }
    writer.json(json_path, payload)
    writer.markdown(report_path, _markdown(payload))
    writer.append_index(index_record)
    return GeometryFeatureReportResult(
        strategy_name=spec.name,
        status=status,
        report_path=report_path,
        json_path=json_path,
        feature_family="geometry_topology_research_sandbox",
        research_only=True,
        promotion_blockers=promotion_blockers,
    )


def _feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    data = frame.copy()
    data["timestamp"] = pd.to_datetime(data["timestamp"], utc=True)
    for column in ["open", "high", "low", "close", "volume"]:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=["open", "high", "low", "close", "volume"])
    close = data["close"].replace(0, np.nan)
    volume = data["volume"].replace(0, np.nan)
    data["log_return"] = np.log(close / close.shift(1))
    data["log_volume_change"] = np.log(volume / volume.shift(1))
    data["range_pct"] = (data["high"] - data["low"]) / close
    data["body_pct"] = (data["close"] - data["open"]) / close
    data["dollar_volume"] = data["close"] * data["volume"]
    return data.replace([np.inf, -np.inf], np.nan)


def _geometry_summary(frame: pd.DataFrame, *, window_bars: int) -> dict[str, Any]:
    returns = frame["log_return"].dropna()
    volume_change = frame["log_volume_change"].dropna()
    range_pct = frame["range_pct"].dropna()
    dollar_volume = frame["dollar_volume"].dropna()
    aligned = frame[["log_return", "log_volume_change", "range_pct", "body_pct"]].dropna()
    rolling = frame[["log_return", "log_volume_change", "range_pct"]].rolling(window_bars)
    rolling_cov_trace = rolling.cov().groupby(level=0).apply(_cov_trace).dropna()
    return {
        "path_signature_low_order": {
            "description": (
                "Deterministic low-order path summaries over return and volume-change paths."
            ),
            "cumulative_log_return": _float(returns.sum()),
            "return_volume_signed_area": _float(
                _signed_area(
                    aligned["log_return"].to_numpy(),
                    aligned["log_volume_change"].to_numpy(),
                )
            ),
            "return_range_signed_area": _float(
                _signed_area(aligned["log_return"].to_numpy(), aligned["range_pct"].to_numpy())
            ),
            "path_length_return_volume": _float(
                _path_length(
                    aligned["log_return"].to_numpy(),
                    aligned["log_volume_change"].to_numpy(),
                )
            ),
        },
        "energy_curvature_proxies": {
            "description": "Research-only proxies; they are not physics claims.",
            "realized_volatility": _float(returns.std()),
            "range_energy": _float((range_pct**2).mean()),
            "volume_change_energy": _float((volume_change**2).mean()),
            "return_curvature_proxy": _float(returns.diff().abs().mean()),
            "range_body_coupling": _float(_corr(frame["range_pct"], frame["body_pct"])),
        },
        "covariance_manifold_proxy": {
            "description": "Log-Euclidean-style scalar proxy from rolling covariance traces.",
            "window_bars": window_bars,
            "rolling_cov_trace_mean": _float(rolling_cov_trace.mean()),
            "rolling_cov_trace_std": _float(rolling_cov_trace.std()),
            "rolling_cov_log_energy": _float(np.log1p(rolling_cov_trace.clip(lower=0)).mean()),
        },
        "graph_topology_proxy": {
            "description": (
                "Single-symbol OHLCV graph proxy; true cross-sectional graph topology needs "
                "a universe panel."
            ),
            "node_count": int(len(aligned.columns)),
            "edge_count_abs_corr_gt_0_5": _edge_count(aligned, threshold=0.5),
            "mean_abs_correlation": _float(_mean_abs_corr(aligned)),
            "requires_cross_sectional_panel": True,
        },
        "liquidity_context": {
            "mean_dollar_volume": _float(dollar_volume.mean()),
            "min_dollar_volume": _float(dollar_volume.min()),
            "volume_observations": int(dollar_volume.count()),
        },
        "sample": {
            "rows": int(len(frame)),
            "usable_rows": int(len(aligned)),
            "first_timestamp": frame["timestamp"].iloc[0].isoformat() if len(frame) else None,
            "last_timestamp": frame["timestamp"].iloc[-1].isoformat() if len(frame) else None,
        },
    }


def _signed_area(x_values: np.ndarray, y_values: np.ndarray) -> float | None:
    if len(x_values) < 2 or len(y_values) < 2:
        return None
    x_delta = np.diff(x_values)
    y_delta = np.diff(y_values)
    return float(0.5 * np.sum(x_values[:-1] * y_delta - y_values[:-1] * x_delta))


def _path_length(x_values: np.ndarray, y_values: np.ndarray) -> float | None:
    if len(x_values) < 2 or len(y_values) < 2:
        return None
    return float(np.sqrt(np.diff(x_values) ** 2 + np.diff(y_values) ** 2).sum())


def _cov_trace(covariance: pd.DataFrame) -> float | None:
    if covariance.empty:
        return None
    values = np.diag(covariance.to_numpy(dtype=float))
    return float(np.nansum(values))


def _corr(left: pd.Series, right: pd.Series) -> float | None:
    joined = pd.concat([left, right], axis=1).dropna()
    if len(joined) < 3:
        return None
    value = joined.iloc[:, 0].corr(joined.iloc[:, 1])
    return float(value) if pd.notna(value) else None


def _edge_count(frame: pd.DataFrame, *, threshold: float) -> int:
    corr = frame.corr(numeric_only=True).abs()
    if corr.empty:
        return 0
    upper = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    return int((corr.to_numpy()[upper] > threshold).sum())


def _mean_abs_corr(frame: pd.DataFrame) -> float | None:
    corr = frame.corr(numeric_only=True).abs()
    if corr.empty or corr.shape[0] < 2:
        return None
    upper = np.triu(np.ones(corr.shape, dtype=bool), k=1)
    values = corr.to_numpy()[upper]
    return float(np.nanmean(values)) if len(values) else None


def _warnings(feature_summary: dict[str, Any], data_profile: dict[str, Any]) -> list[str]:
    warnings = ["research_only_not_paper_ready"]
    sample = feature_summary.get("sample", {})
    if int(sample.get("usable_rows", 0) or 0) < 30:
        warnings.append("short_sample_for_geometry_features")
    if feature_summary.get("graph_topology_proxy", {}).get("requires_cross_sectional_panel"):
        warnings.append("graph_topology_requires_cross_sectional_universe_panel")
    source_mode = data_profile.get("source_mode")
    if source_mode in {"sample", "sample_fallback", "fixture_fallback"}:
        warnings.append(f"{source_mode}_is_not_paper_ready_market_evidence")
    return warnings


def _markdown(payload: dict[str, Any]) -> str:
    features = payload["feature_summary"]
    lines = [
        f"# Geometry Features: {payload['strategy_name']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Research only: `{payload['research_only']}`",
        f"- Feature family: `{payload['feature_family']}`",
        f"- Source spec: `{payload['source_spec_path']}`",
        f"- Window bars: `{payload['window_bars']}`",
        "",
        "## Feature Summary",
        "",
    ]
    for family, values in features.items():
        lines.append(f"### {family}")
        if isinstance(values, dict):
            for key, value in values.items():
                lines.append(f"- {key}: `{value}`")
        lines.append("")
    lines.extend(
        [
            "## Baseline Requirements",
            "",
            *[f"- {item}" for item in payload["baseline_requirements"]],
            "",
            "## Promotion Blockers",
            "",
            *[f"- `{item}`" for item in payload["promotion_blockers"]],
            "",
            "## Warnings",
            "",
            *[f"- `{item}`" for item in payload["warnings"]],
            "",
        ]
    )
    return "\n".join(lines)


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(numeric):
        return None
    return numeric
