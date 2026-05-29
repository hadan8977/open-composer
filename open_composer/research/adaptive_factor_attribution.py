from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from time import perf_counter
from typing import Any

from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.json_utils import json_safe_payload
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.adaptive_intraday_router_core import _parse_route_label
from open_composer.research.intraday_daily_rotation import (
    IntradayDailyMetrics,
    IntradayDailyParams,
    _backtest_params,
    _load_dataset,
    _split_for_oos,
)
from open_composer.research.metadata import runtime_payload, search_space
from open_composer.storage import write_json


@dataclass(frozen=True)
class AdaptiveFactorAttributionResult:
    report_path: Path
    json_path: Path
    status: str
    blockers: list[str]
    selected_route_label: str


def run_adaptive_factor_attribution(
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
    out_of_sample_ratio: float = 0.3,
    refresh_data: bool = False,
) -> AdaptiveFactorAttributionResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_label = selected_route_label or spec.portfolio.selected_route_label
    if not selected_label:
        selected_label = _selected_label_from_research(base, spec.name)
    if not selected_label:
        raise ValueError(
            "adaptive factor attribution requires selected_route_label or research JSON"
        )
    params = _parse_route_label(selected_label)
    universe = [item.upper() for item in (symbols or spec.universe)]
    selected_feed = feed or spec.data.feed or data_feed()

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
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    split = _split_for_oos(len(dataset.dates), out_of_sample_ratio, [params])
    baseline = _evaluate_route(spec, dataset, params, split)
    variants = _build_variants(params)
    variant_metrics = {
        name: _evaluate_route(spec, dataset, variant, split) for name, variant in variants.items()
    }
    stages["backtest_attribution_variants"] = perf_counter() - stage_started

    attribution = _attribution_table(baseline, variant_metrics)
    walk_forward_summary = _walk_forward_summary(base, spec.name)
    status, blockers = _attribution_status(attribution, walk_forward_summary)
    runtime = runtime_payload(started_at, stages)
    json_path = base / "reports" / "research" / f"{spec.name}-adaptive-factor-attribution.json"
    report_path = json_path.with_suffix(".md")
    payload = {
        "strategy_name": spec.name,
        "source_spec_path": _relpath(spec_path, base),
        "mode": "adaptive_factor_attribution",
        "status": status,
        "blockers": blockers,
        "route_label": params.label,
        "symbols": dataset.symbols,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "search_space": search_space(
            family="adaptive_factor_attribution",
            candidate_count=len(variants) + 1,
            parameter_ranges={
                "selected_route_label": [params.label],
                "ablation": sorted(variants),
            },
            filters=[
                "same StrategySpec cost model",
                "same data profile as adaptive router report",
                "route-level attribution, not single-symbol factor lab",
            ],
        ),
        "baseline": _route_payload(baseline),
        "variants": {
            name: {
                "params": variants[name].__dict__,
                "metrics": _route_payload(metrics),
            }
            for name, metrics in variant_metrics.items()
        },
        "attribution": attribution,
        "walk_forward_summary": walk_forward_summary,
        "runtime_seconds": runtime,
        "safety_note": (
            "Route-level attribution evidence for promotion review only. It does not submit "
            "paper orders."
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
    return AdaptiveFactorAttributionResult(
        report_path=report_path,
        json_path=json_path,
        status=status,
        blockers=blockers,
        selected_route_label=params.label,
    )


def _evaluate_route(
    spec: Any,
    dataset: Any,
    params: IntradayDailyParams,
    split: int,
) -> dict[str, IntradayDailyMetrics]:
    oos_start = max(params.lookback_days, split)
    return {
        "full": _backtest_params(
            spec,
            dataset,
            params,
            start_index=params.lookback_days,
            end_index=len(dataset.dates),
        ),
        "oos": _backtest_params(
            spec,
            dataset,
            params,
            start_index=oos_start,
            end_index=len(dataset.dates),
        ),
    }


def _build_variants(params: IntradayDailyParams) -> dict[str, IntradayDailyParams]:
    variants: dict[str, IntradayDailyParams] = {}
    if params.market_gate != "none":
        variants["no_market_gate"] = replace(params, market_gate="none")
    else:
        variants["qqq_open_positive_gate"] = replace(params, market_gate="qqq_open_positive")
    if params.min_relative_volume > 0:
        variants["no_relative_volume_filter"] = replace(params, min_relative_volume=0.0)
    variants["entry_delay_alternative"] = replace(
        params,
        entry_after_bars=2 if params.entry_after_bars <= 1 else max(1, params.entry_after_bars - 1),
    )
    variants["prior_momentum_gate_alternative"] = replace(
        params,
        min_prior_momentum_pct=0.0 if params.min_prior_momentum_pct > 0 else 3.0,
    )
    if params.selection_style == "opening_reversal":
        variants["reversal_threshold_alternative"] = replace(
            params,
            max_opening_return_pct=None,
            max_prior_momentum_pct=None,
        )
    else:
        variants["reversal_threshold_alternative"] = replace(
            params,
            selection_style="opening_reversal",
            max_opening_return_pct=max(params.min_opening_return_pct, 0.5),
            max_prior_momentum_pct=None,
        )
    return variants


def _attribution_table(
    baseline: dict[str, IntradayDailyMetrics],
    variants: dict[str, dict[str, IntradayDailyMetrics]],
) -> dict[str, dict[str, float | str | None]]:
    rows: dict[str, dict[str, float | str | None]] = {}
    base_full = baseline["full"]
    base_oos = baseline["oos"]
    for name, metrics in variants.items():
        full = metrics["full"]
        oos = metrics["oos"]
        oos_alpha_delta = _delta(
            base_oos.alpha_vs_equal_weight_annualized_pct,
            oos.alpha_vs_equal_weight_annualized_pct,
        )
        oos_sharpe_delta = _delta(base_oos.sharpe_ratio, oos.sharpe_ratio)
        oos_drawdown_delta = (
            None
            if base_oos.max_drawdown_pct is None
            else base_oos.max_drawdown_pct - oos.max_drawdown_pct
        )
        rows[name] = {
            "full_annualized_return_pct": full.annualized_return_pct,
            "oos_annualized_return_pct": oos.annualized_return_pct,
            "full_sharpe_ratio": full.sharpe_ratio,
            "oos_sharpe_ratio": oos.sharpe_ratio,
            "full_max_drawdown_pct": full.max_drawdown_pct,
            "oos_max_drawdown_pct": oos.max_drawdown_pct,
            "full_equal_weight_alpha_annualized_pct": (full.alpha_vs_equal_weight_annualized_pct),
            "oos_equal_weight_alpha_annualized_pct": (oos.alpha_vs_equal_weight_annualized_pct),
            "delta_oos_equal_weight_alpha_annualized_pct": oos_alpha_delta,
            "delta_oos_annualized_return_pct": _delta(
                base_oos.annualized_return_pct,
                oos.annualized_return_pct,
            ),
            "delta_oos_sharpe_ratio": oos_sharpe_delta,
            "delta_oos_max_drawdown_pct": oos_drawdown_delta,
            "delta_full_equal_weight_alpha_annualized_pct": _delta(
                base_full.alpha_vs_equal_weight_annualized_pct,
                full.alpha_vs_equal_weight_annualized_pct,
            ),
            "conclusion": _conclusion(oos_alpha_delta, oos_sharpe_delta, oos_drawdown_delta),
            "interpretation": _interpretation(name),
        }
    return rows


def _attribution_status(
    attribution: dict[str, dict[str, float | str | None]],
    walk_forward_summary: dict[str, Any],
) -> tuple[str, list[str]]:
    blockers: list[str] = []
    for name, row in attribution.items():
        if row.get("conclusion") == "harmful":
            blockers.append(f"{name} ablation materially dominated selected route")
    if blockers and bool(walk_forward_summary.get("all_positive_alpha_folds")):
        return "warning", blockers
    return ("ok" if not blockers else "blocked", blockers)


def _selected_label_from_research(root: Path, strategy_name: str) -> str | None:
    path = root / "reports" / "research" / f"{strategy_name}-adaptive-intraday-router.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    candidates = payload.get("candidates")
    if isinstance(candidates, list) and candidates:
        first = candidates[0]
        if isinstance(first, dict) and first.get("label"):
            return str(first["label"])
        params = first.get("params") if isinstance(first, dict) else None
        if isinstance(params, dict) and params.get("label"):
            return str(params["label"])
    return None


def _walk_forward_summary(root: Path, strategy_name: str) -> dict[str, Any]:
    path = root / "reports" / "research" / f"{strategy_name}-adaptive-intraday-router.json"
    if not path.exists():
        return {"path": _relpath(path, root), "available": False}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"path": _relpath(path, root), "available": False}
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


def _route_payload(metrics: dict[str, IntradayDailyMetrics]) -> dict[str, Any]:
    return {key: json_safe_payload(value.__dict__) for key, value in metrics.items()}


def _write_markdown(
    *,
    path: Path,
    json_path: Path,
    route_label: str,
    status: str,
    blockers: list[str],
    baseline: dict[str, IntradayDailyMetrics],
    attribution: dict[str, dict[str, float | str | None]],
    runtime: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    base_oos = baseline["oos"]
    lines = [
        "# Adaptive Factor Attribution",
        "",
        f"- JSON report: `{json_path}`",
        f"- Route: `{route_label}`",
        f"- Status: `{status}`",
        f"- Blockers: `{blockers}`",
        f"- Runtime seconds: `{runtime['total']:.2f}`",
        "",
        "## Baseline OOS",
        "",
        f"- Annualized: `{_fmt(base_oos.annualized_return_pct)}%`",
        f"- Equal-weight alpha annualized: "
        f"`{_fmt(base_oos.alpha_vs_equal_weight_annualized_pct)}%`",
        f"- Sharpe: `{_fmt(base_oos.sharpe_ratio)}`",
        f"- Max drawdown: `{base_oos.max_drawdown_pct:.2f}%`",
        "",
        "## Ablations",
        "",
        "| Ablation | Delta OOS EW Alpha Ann | Delta OOS Ann Return | Delta OOS Sharpe | "
        "Delta OOS Max DD | Conclusion |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name, row in attribution.items():
        lines.append(
            f"| `{name}` | {_fmt(row['delta_oos_equal_weight_alpha_annualized_pct'])}% | "
            f"{_fmt(row['delta_oos_annualized_return_pct'])}% | "
            f"{_fmt(row['delta_oos_sharpe_ratio'])} | "
            f"{_fmt(row['delta_oos_max_drawdown_pct'])}% | {row['conclusion']} |"
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- Positive delta means the selected route outperformed that ablation.",
            "- This is router-aware factor evidence for promotion review.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _conclusion(
    alpha_delta: float | None,
    sharpe_delta: float | None,
    drawdown_delta: float | None,
) -> str:
    alpha = _float(alpha_delta)
    sharpe = _float(sharpe_delta)
    drawdown = _float(drawdown_delta)
    if alpha >= 5.0 and sharpe >= -0.1:
        return "positive"
    if alpha <= -5.0 and sharpe <= 0.0 and drawdown <= 2.0:
        return "harmful"
    if abs(alpha) < 2.0:
        return "neutral"
    return "inconclusive"


def _interpretation(name: str) -> str:
    return {
        "no_market_gate": "Tests whether QQQ regime filtering adds value.",
        "qqq_open_positive_gate": "Tests whether adding a QQQ open-positive gate helps.",
        "no_relative_volume_filter": "Tests whether relative volume confirmation adds value.",
        "entry_delay_alternative": "Tests whether the chosen entry delay adds value.",
        "prior_momentum_gate_alternative": "Tests prior-session momentum gate sensitivity.",
        "reversal_threshold_alternative": "Tests opening momentum versus reversal threshold logic.",
    }.get(name, "Route ablation.")


def _delta(baseline: float | None, variant: float | None) -> float | None:
    if baseline is None or variant is None:
        return None
    return baseline - variant


def _float(value: float | str | None) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fmt(value: float | str | None) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "n/a"


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
