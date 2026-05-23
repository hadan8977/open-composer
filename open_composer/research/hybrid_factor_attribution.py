from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.json_utils import json_safe_payload
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.hybrid_router_core import (
    HybridRouterMetrics,
    HybridRouterParams,
    _backtest_hybrid_params,
    _effective_lookback,
    _load_daily_hybrid_dataset,
    hybrid_params_from_label,
)
from open_composer.research.metadata import runtime_payload, search_space
from open_composer.storage import write_json


@dataclass(frozen=True)
class HybridFactorAttributionResult:
    report_path: Path
    json_path: Path
    status: str
    blockers: list[str]
    selected_route_label: str


def run_hybrid_factor_attribution(
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
    selected_route_label: str | None = None,
    refresh_data: bool = False,
) -> HybridFactorAttributionResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    selected_feed = feed or spec.data.feed or data_feed()
    selected_label = selected_route_label or spec.portfolio.selected_route_label
    if not selected_label:
        raise ValueError("hybrid factor attribution requires selected_route_label")
    params = hybrid_params_from_label(selected_label)

    stage_started = perf_counter()
    dataset = _load_daily_hybrid_dataset(
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
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    start_index = _effective_lookback(params)
    end_index = len(dataset.frame) - (1 if params.holding_mode == "open_to_open" else 0)
    baseline = _backtest_hybrid_params(
        spec,
        dataset,
        params,
        start_index=start_index,
        end_index=end_index,
    )
    variants = _build_variants(params)
    variant_metrics = {
        name: _backtest_hybrid_params(
            spec,
            dataset,
            variant,
            start_index=max(start_index, _effective_lookback(variant)),
            end_index=end_index,
        )
        for name, variant in variants.items()
    }
    stages["backtest_attribution_variants"] = perf_counter() - stage_started

    attribution = _attribution_table(baseline, variant_metrics)
    walk_forward_summary = _walk_forward_summary(base, spec.name)
    status, blockers = _attribution_status(attribution, walk_forward_summary)
    runtime = runtime_payload(started_at, stages)
    json_path = base / "reports" / "research" / f"{spec.name}-hybrid-factor-attribution.json"
    report_path = json_path.with_suffix(".md")
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": _relpath(spec_path, base),
        "mode": "hybrid_factor_attribution",
        "status": status,
        "blockers": blockers,
        "route_label": params.label,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "data_profile": dataset.data_profile,
        "search_space": search_space(
            family="hybrid_factor_attribution",
            candidate_count=len(variants) + 1,
            parameter_ranges={
                "selected_route_label": [params.label],
                "ablation": sorted(variants),
            },
            filters=[
                "same StrategySpec cost model",
                "same cached/live market data profile as hybrid router report",
                "attribution is route-level, not single-symbol factor lab",
            ],
        ),
        "baseline": _metrics_payload(baseline),
        "variants": {
            name: {
                "params": variants[name].__dict__,
                "metrics": _metrics_payload(metrics),
            }
            for name, metrics in variant_metrics.items()
        },
        "attribution": attribution,
        "walk_forward_summary": walk_forward_summary,
        "runtime_seconds": runtime,
        "safety_note": (
            "Route-level attribution evidence for promotion review only. It does not "
            "submit paper orders."
        ),
    }
    write_json(json_path, payload)
    _write_markdown(
        path=report_path,
        json_path=json_path,
        route_label=params.label,
        status=status,
        blockers=blockers,
        baseline=baseline,
        attribution=attribution,
        runtime=runtime,
    )
    return HybridFactorAttributionResult(
        report_path=report_path,
        json_path=json_path,
        status=status,
        blockers=blockers,
        selected_route_label=params.label,
    )


def _build_variants(params: HybridRouterParams) -> dict[str, HybridRouterParams]:
    return {
        "no_market_gate": HybridRouterParams(
            holding_mode=params.holding_mode,
            momentum_lookback_days=params.momentum_lookback_days,
            top_n=params.top_n,
            market_sma_days=None,
            min_momentum_pct=params.min_momentum_pct,
            max_position_weight=params.max_position_weight,
        ),
        "no_min_momentum": HybridRouterParams(
            holding_mode=params.holding_mode,
            momentum_lookback_days=params.momentum_lookback_days,
            top_n=params.top_n,
            market_sma_days=params.market_sma_days,
            min_momentum_pct=0.0,
            max_position_weight=params.max_position_weight,
        ),
        "top2_diversified": HybridRouterParams(
            holding_mode=params.holding_mode,
            momentum_lookback_days=params.momentum_lookback_days,
            top_n=max(params.top_n, 2),
            market_sma_days=params.market_sma_days,
            min_momentum_pct=params.min_momentum_pct,
            max_position_weight=min(params.max_position_weight, 0.5),
        ),
        "open_to_close_holding": HybridRouterParams(
            holding_mode="open_to_close",
            momentum_lookback_days=params.momentum_lookback_days,
            top_n=params.top_n,
            market_sma_days=params.market_sma_days,
            min_momentum_pct=params.min_momentum_pct,
            max_position_weight=params.max_position_weight,
        ),
    }


def _attribution_table(
    baseline: HybridRouterMetrics,
    variants: dict[str, HybridRouterMetrics],
) -> dict[str, dict[str, float | str | None]]:
    baseline_alpha = baseline.alpha_vs_benchmark_buy_hold_annualized_pct
    baseline_ann = baseline.annualized_return_pct
    baseline_sharpe = baseline.sharpe_ratio
    rows: dict[str, dict[str, float | str | None]] = {}
    for name, metrics in variants.items():
        rows[name] = {
            "variant_alpha_vs_tqqq_annualized_pct": (
                metrics.alpha_vs_benchmark_buy_hold_annualized_pct
            ),
            "delta_alpha_vs_tqqq_annualized_pct": _delta(
                baseline_alpha,
                metrics.alpha_vs_benchmark_buy_hold_annualized_pct,
            ),
            "variant_annualized_return_pct": metrics.annualized_return_pct,
            "delta_annualized_return_pct": _delta(baseline_ann, metrics.annualized_return_pct),
            "variant_sharpe_ratio": metrics.sharpe_ratio,
            "delta_sharpe_ratio": _delta(baseline_sharpe, metrics.sharpe_ratio),
            "variant_max_drawdown_pct": metrics.max_drawdown_pct,
            "delta_max_drawdown_pct": metrics.max_drawdown_pct - baseline.max_drawdown_pct,
            "variant_traded_days": float(metrics.traded_days),
            "delta_traded_days": float(metrics.traded_days - baseline.traded_days),
            "interpretation": _interpretation(name),
        }
    return rows


def _attribution_status(
    attribution: dict[str, dict[str, float | str | None]],
    walk_forward_summary: dict[str, Any],
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    if _float(attribution["open_to_close_holding"]["delta_alpha_vs_tqqq_annualized_pct"]) <= 0:
        blockers.append("holding-mode attribution did not favor open_to_open")
    if _float(
        attribution["no_market_gate"]["delta_alpha_vs_tqqq_annualized_pct"]
    ) < -5 and not bool(walk_forward_summary.get("all_positive_alpha_folds")):
        blockers.append("market-gate ablation materially outperformed selected route")
    if _float(attribution["no_min_momentum"]["delta_alpha_vs_tqqq_annualized_pct"]) < -5:
        blockers.append("minimum-momentum ablation materially outperformed selected route")
    return ("ok" if not blockers else "blocked", blockers)


def _walk_forward_summary(root: Path, strategy_name: str) -> dict[str, Any]:
    path = root / "reports" / "research" / f"{strategy_name}-hybrid-adaptive-router.json"
    if not path.exists():
        return {
            "path": _relpath(path, root),
            "available": False,
            "all_positive_alpha_folds": False,
        }
    try:
        payload = json_safe_payload(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return {
            "path": _relpath(path, root),
            "available": False,
            "all_positive_alpha_folds": False,
        }
    acceptance = payload.get("acceptance_gate", {}) if isinstance(payload, dict) else {}
    if not isinstance(acceptance, dict):
        acceptance = {}
    fold_count = int(acceptance.get("walk_forward_fold_count") or 0)
    positive_count = int(acceptance.get("walk_forward_positive_alpha_folds") or 0)
    return {
        "path": _relpath(path, root),
        "available": True,
        "fold_count": fold_count,
        "positive_alpha_folds": positive_count,
        "all_positive_alpha_folds": fold_count > 0 and positive_count == fold_count,
    }


def _metrics_payload(metrics: HybridRouterMetrics) -> dict[str, Any]:
    return json_safe_payload(metrics.__dict__)


def _write_markdown(
    *,
    path: Path,
    json_path: Path,
    route_label: str,
    status: str,
    blockers: list[str],
    baseline: HybridRouterMetrics,
    attribution: dict[str, dict[str, float | str | None]],
    runtime: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        "# Hybrid Factor Attribution",
        "",
        f"- JSON report: `{json_path}`",
        f"- Route: `{route_label}`",
        f"- Status: `{status}`",
        f"- Blockers: `{blockers}`",
        f"- Runtime seconds: `{runtime['total']:.2f}`",
        "",
        "## Baseline",
        "",
        f"- Return: `{baseline.total_return_pct:.2f}%`",
        f"- Annualized: `{_fmt(baseline.annualized_return_pct)}%`",
        f"- Alpha vs TQQQ annualized: "
        f"`{_fmt(baseline.alpha_vs_benchmark_buy_hold_annualized_pct)}%`",
        f"- Sharpe: `{_fmt(baseline.sharpe_ratio)}`",
        f"- Max drawdown: `{baseline.max_drawdown_pct:.2f}%`",
        f"- Trades: `{baseline.round_trips}`",
        "",
        "## Ablations",
        "",
        "| Ablation | Delta Alpha vs TQQQ Ann | Delta Ann Return | Delta Sharpe | "
        "Delta Max DD | Delta Trades |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for name, row in attribution.items():
        lines.append(
            f"| `{name}` | {_fmt(row['delta_alpha_vs_tqqq_annualized_pct'])}% | "
            f"{_fmt(row['delta_annualized_return_pct'])}% | "
            f"{_fmt(row['delta_sharpe_ratio'])} | "
            f"{_fmt(row['delta_max_drawdown_pct'])}% | "
            f"{_fmt(row['delta_traded_days'])} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Positive delta means the selected route outperformed that ablation.",
            "- This is route-level evidence for the hybrid router promotion gate.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _interpretation(name: str) -> str:
    return {
        "no_market_gate": "Tests whether QQQ regime filtering adds value.",
        "no_min_momentum": "Tests whether the minimum momentum threshold adds value.",
        "top2_diversified": "Tests whether two half-weight names improve risk-adjusted results.",
        "open_to_close_holding": "Tests whether intraday holding beats open-to-open holding.",
    }.get(name, "Route ablation.")


def _delta(value: float | None, baseline: float | None) -> float | None:
    if value is None or baseline is None:
        return None
    return value - baseline


def _float(value: float | str | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _fmt(value: float | str | None) -> str:
    return "n/a" if value is None else f"{float(value):.2f}"


def _relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()
