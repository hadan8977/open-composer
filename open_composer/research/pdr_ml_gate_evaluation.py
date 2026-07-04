from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.defensive_transition_overlay import DefensiveTransitionOverlay
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.pdr_ml_gate import (
    PDR_ML_GATE_FAMILY,
    pdr_ml_gate_artifact_path,
    pdr_ml_gate_search_space,
)
from open_composer.research.router_common import (
    RouterFrameDataset,
    RouterMetrics,
    backtest_router_params,
    load_daily_dataset,
    symbol_holding_return,
)

DEFAULT_START = "2012-01-03"
DEFAULT_END = "2026-05-22"
FULL_WINDOW_START = "2013-01-08"
FOLD_WINDOWS = (
    ("fold1", "2013-01-08", "2015-03-31"),
    ("fold2", "2015-04-01", "2017-06-27"),
    ("fold3", "2017-06-28", "2019-09-17"),
    ("fold4", "2019-09-18", "2021-12-06"),
    ("fold5", "2021-12-07", "2024-02-28"),
    ("fold6", "2024-02-29", "2026-05-21"),
)
CRISIS_WINDOWS = (
    ("q4_2018", "2018-10-01", "2018-12-28"),
    ("covid_crash", "2020-02-19", "2020-03-20"),
    ("calendar_2022", "2022-01-03", "2022-12-29"),
)
CURRENT_OOS_START = "2024-11-04"


def evaluate_pdr_router_ml_gate(
    spec_path: Path,
    *,
    root: Path | None = None,
    data_source: str = "longbridge",
    feed: str | None = None,
    start: str = DEFAULT_START,
    end: str = DEFAULT_END,
    report_date: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    gated_params = hybrid_params_from_label(spec.portfolio.selected_route_label or "")
    if not isinstance(gated_params, DefensiveTransitionOverlay) or gated_params.ml_gate is None:
        raise ValueError("PDR ML gate evaluation requires a defensive_overlay route with ml_gate")
    baseline_params = replace(gated_params, ml_gate=None)
    dataset = load_daily_dataset(
        spec=spec,
        root=base,
        symbols=spec.universe,
        data_source=data_source,
        feed=feed,
        start=start,
        end=end,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    full_start_idx, full_end_idx = _window_indices(
        dataset,
        FULL_WINDOW_START,
        dataset.dates[-2],
        min_start_idx=max(_effective_lookback(baseline_params), _effective_lookback(gated_params)),
    )
    full_baseline = _metrics(spec, dataset, baseline_params, full_start_idx, full_end_idx)
    full_gated = _metrics(spec, dataset, gated_params, full_start_idx, full_end_idx)
    walk_forward = [
        _window_result(spec, dataset, baseline_params, gated_params, name, start_date, end_date)
        for name, start_date, end_date in FOLD_WINDOWS
    ]
    crisis = [
        _window_result(spec, dataset, baseline_params, gated_params, name, start_date, end_date)
        for name, start_date, end_date in CRISIS_WINDOWS
    ]
    current_oos = _window_result(
        spec,
        dataset,
        baseline_params,
        gated_params,
        "current_oos",
        CURRENT_OOS_START,
        dataset.dates[-2],
    )
    attribution = _ml_release_attribution(
        spec,
        dataset,
        baseline_params,
        gated_params,
        full_start_idx,
        full_end_idx,
    )
    acceptance = _acceptance_gate(full_baseline, full_gated, walk_forward, crisis, current_oos)
    generated_at = datetime.now(UTC).isoformat()
    stamp = report_date or datetime.now(UTC).strftime("%Y%m%d")
    out_dir = ensure_dir(output_dir or base / "reports" / "research" / "control")
    json_path = out_dir / f"pdr-router-ml-gate-eval-{stamp}.json"
    md_path = out_dir / f"pdr-router-ml-gate-eval-{stamp}.md"
    payload = {
        "report_type": "pdr_router_ml_gate_eval",
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path),
        "baseline_route_label": baseline_params.label,
        "gated_route_label": gated_params.label,
        "generated_at": generated_at,
        "data_profile": {
            "provider": data_source,
            "source_mode": dataset.data_profile.get("source_mode"),
            "acquisition_tier": "research_replay_cache",
            "data_as_of": dataset.dates[-1] if dataset.dates else None,
            "paper_ready_evidence": False,
            "comparison_discipline": "baseline and gated are run on the same loaded dataset",
        },
        "search_space": {
            "family": PDR_ML_GATE_FAMILY,
            "candidate_count": len(pdr_ml_gate_search_space()),
            "parameter_ranges": {
                "horizon_bars": [10, 20],
                "threshold_return_pct": [0, 2],
                "probability_threshold": [0.6, 0.7, 0.8],
            },
        },
        "acceptance_gate": acceptance,
        "pass_status": {
            "workflow_pass": True,
            "research_pass": bool(acceptance["ml_gate_beats_fixed_route"]),
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "paper_ready_blockers": [
                "R.2 evaluation is research evidence only",
                "active paper_auto specs are intentionally unchanged",
            ],
        },
        "windows": {
            "full_window": {
                "start_date": dataset.dates[full_start_idx],
                "end_date": dataset.dates[full_end_idx - 1],
                "baseline": _metrics_payload(full_baseline),
                "gated": _metrics_payload(full_gated),
            },
            "crisis": crisis,
            "current_oos": current_oos,
        },
        "walk_forward": walk_forward,
        "benchmark_family": _benchmark_family_payload(full_gated),
        "attribution": attribution,
        "trial_ledger_path": str(
            base / "reports" / "research" / "ml" / spec.name / "pdr_mlgate_trial_ledger.jsonl"
        ),
        "selected_prediction_artifact": str(
            pdr_ml_gate_artifact_path(spec, gated_params.ml_gate, root=base)
        ),
        "artifact_paths": {"json": str(json_path), "markdown": str(md_path)},
    }
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    md_path.write_text(_render_markdown(payload), encoding="utf-8")
    return payload


def _metrics(
    spec: Any,
    dataset: RouterFrameDataset,
    params: object,
    start_index: int,
    end_index: int,
) -> RouterMetrics:
    return backtest_router_params(
        spec,
        dataset,
        params,
        snapshot=hybrid_target_weight_snapshot,
        start_index=start_index,
        end_index=end_index,
    )


def _window_result(
    spec: Any,
    dataset: RouterFrameDataset,
    baseline_params: object,
    gated_params: object,
    name: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    start_idx, end_idx = _window_indices(dataset, start_date, end_date)
    baseline = _metrics(spec, dataset, baseline_params, start_idx, end_idx)
    gated = _metrics(spec, dataset, gated_params, start_idx, end_idx)
    return {
        "name": name,
        "start_date": dataset.dates[start_idx],
        "end_date": dataset.dates[end_idx - 1],
        "baseline": _metrics_payload(baseline),
        "gated": _metrics_payload(gated),
        "gated_beats_tqqq": gated.total_return_pct > gated.benchmark_buy_hold_return_pct,
        "gated_total_vs_tqqq_multiple": _ratio_or_none(
            gated.total_return_pct,
            gated.benchmark_buy_hold_return_pct,
        ),
    }


def _acceptance_gate(
    baseline: RouterMetrics,
    gated: RouterMetrics,
    walk_forward: list[dict[str, Any]],
    crisis: list[dict[str, Any]],
    current_oos: dict[str, Any],
) -> dict[str, Any]:
    wf_wins = sum(1 for row in walk_forward if row["gated_beats_tqqq"])
    current_gated = current_oos["gated"]
    current_tqqq = current_gated["benchmark_buy_hold_return_pct"]
    gates = {
        "wf_beats_tqqq_at_least_4_of_6": {
            "passed": wf_wins >= 4,
            "actual": wf_wins,
            "threshold": 4,
        },
        "full_window_annualized_return_at_least_33": {
            "passed": (gated.annualized_return_pct or float("-inf")) >= 33.0,
            "actual": gated.annualized_return_pct,
            "threshold": 33.0,
        },
        "full_window_sharpe_at_least_1_1": {
            "passed": (gated.sharpe_ratio or float("-inf")) >= 1.1,
            "actual": gated.sharpe_ratio,
            "threshold": 1.1,
        },
        "full_window_maxdd_not_worse_than_baseline": {
            "passed": gated.max_drawdown_pct >= baseline.max_drawdown_pct,
            "actual": gated.max_drawdown_pct,
            "baseline": baseline.max_drawdown_pct,
        },
        "crisis_windows_all_beat_tqqq": {
            "passed": all(row["gated_beats_tqqq"] for row in crisis),
            "actual": [row["name"] for row in crisis if row["gated_beats_tqqq"]],
            "threshold": [row["name"] for row in crisis],
        },
        "current_oos_sharpe_and_total_gate": {
            "passed": (
                (current_gated["sharpe_ratio"] or float("-inf")) >= 1.7
                and current_gated["total_return_pct"] >= 1.5 * current_tqqq
            ),
            "actual": {
                "sharpe_ratio": current_gated["sharpe_ratio"],
                "total_return_pct": current_gated["total_return_pct"],
                "tqqq_total_return_pct": current_tqqq,
            },
            "threshold": {"sharpe_ratio": 1.7, "total_vs_tqqq_multiple": 1.5},
        },
    }
    failed = [name for name, gate in gates.items() if not gate["passed"]]
    passed = not failed
    return {
        "objective": "ml_gate_beats_fixed_route",
        "passed": passed,
        "gates": gates,
        "ml_gate_beats_fixed_route": passed,
        "failed_gates": failed,
    }


def _ml_release_attribution(
    spec: Any,
    dataset: RouterFrameDataset,
    baseline_params: object,
    gated_params: object,
    start_index: int,
    end_index: int,
) -> dict[str, Any]:
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    previous_base: dict[str, float] = {}
    previous_gated: dict[str, float] = {}
    release_count = 0
    non_hard_state_changes = 0
    net_delta_sum = 0.0
    for index in range(start_index, end_index):
        base = hybrid_target_weight_snapshot(spec, dataset, baseline_params, index)
        gated = hybrid_target_weight_snapshot(spec, dataset, gated_params, index)
        base_net = _snapshot_net_return(
            spec, dataset, index, base.weights, previous_base, cost_rate
        )
        gated_net = _snapshot_net_return(
            spec, dataset, index, gated.weights, previous_gated, cost_rate
        )
        if base.state == "hard_stress_defensive" and "ml_release" in gated.state:
            release_count += 1
            net_delta_sum += gated_net - base_net
        elif base.state != gated.state or base.weights != gated.weights:
            non_hard_state_changes += 1
        previous_base = base.weights
        previous_gated = gated.weights
    return {
        "ml_release_days": release_count,
        "non_hard_stress_state_or_weight_changes": non_hard_state_changes,
        "ml_release_net_delta_arithmetic_pct_points": net_delta_sum * 100,
        "interpretation": (
            "Gate changes should concentrate in hard_stress_defensive days; non-hard "
            "changes indicate unintended route drift."
        ),
    }


def _snapshot_net_return(
    spec: Any,
    dataset: RouterFrameDataset,
    index: int,
    weights: dict[str, float],
    previous_weights: dict[str, float],
    cost_rate: float,
) -> float:
    raw = sum(
        weight * symbol_holding_return(dataset, symbol, index, "open_to_open", spec)
        for symbol, weight in weights.items()
        if weight > 0
    )
    turnover = sum(
        abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
        for symbol in set(weights) | set(previous_weights)
    )
    return raw - turnover * cost_rate


def _window_indices(
    dataset: RouterFrameDataset,
    start_date: str,
    end_date: str,
    *,
    min_start_idx: int = 0,
) -> tuple[int, int]:
    start_idx = next(index for index, date in enumerate(dataset.dates) if date >= start_date)
    end_idx = max(index for index, date in enumerate(dataset.dates) if date <= end_date) + 1
    start_idx = max(start_idx, min_start_idx)
    if end_idx <= start_idx:
        raise ValueError(f"empty evaluation window {start_date}..{end_date}")
    return start_idx, end_idx


def _metrics_payload(metrics: RouterMetrics) -> dict[str, Any]:
    return {
        "days": metrics.days,
        "start_date": metrics.start_date,
        "end_date": metrics.end_date,
        "total_return_pct": metrics.total_return_pct,
        "annualized_return_pct": metrics.annualized_return_pct,
        "sharpe_ratio": metrics.sharpe_ratio,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "traded_days": metrics.traded_days,
        "round_trips": metrics.round_trips,
        "benchmark_symbol": metrics.benchmark_symbol,
        "benchmark_buy_hold_return_pct": metrics.benchmark_buy_hold_return_pct,
        "market_symbol": metrics.market_symbol,
        "market_buy_hold_return_pct": metrics.market_buy_hold_return_pct,
        "equal_weight_buy_hold_return_pct": metrics.equal_weight_buy_hold_return_pct,
        "best_symbol": metrics.best_symbol,
        "best_symbol_buy_hold_pct": metrics.best_symbol_buy_hold_pct,
    }


def _benchmark_family_payload(metrics: RouterMetrics) -> dict[str, Any]:
    return {
        "strategy_total_return_pct": metrics.total_return_pct,
        "same_symbol_buy_hold": {
            "symbol": metrics.benchmark_symbol,
            "total_return_pct": metrics.benchmark_buy_hold_return_pct,
        },
        "market_proxy": {
            "symbol": metrics.market_symbol,
            "total_return_pct": metrics.market_buy_hold_return_pct,
        },
        "equal_weight_universe": {
            "total_return_pct": metrics.equal_weight_buy_hold_return_pct,
        },
        "ex_post_best_symbol": {
            "symbol": metrics.best_symbol,
            "total_return_pct": metrics.best_symbol_buy_hold_pct,
        },
        "cash_proxy": {"symbol": "BIL", "included_in_universe": True},
    }


def _ratio_or_none(numerator: float, denominator: float) -> float | None:
    if abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def _render_markdown(payload: dict[str, Any]) -> str:
    acceptance = payload["acceptance_gate"]
    full = payload["windows"]["full_window"]
    lines = [
        f"# PDR Router ML Gate Evaluation: {payload['strategy_name']}",
        "",
        f"- Verdict: `ml_gate_beats_fixed_route={acceptance['ml_gate_beats_fixed_route']}`",
        (
            f"- Data: `{payload['data_profile']['provider']}` / "
            f"`{payload['data_profile']['source_mode']}`"
        ),
        f"- Paper-ready evidence: `{payload['data_profile']['paper_ready_evidence']}`",
        f"- Trial ledger: `{payload['trial_ledger_path']}`",
        "",
        "## Acceptance",
        "",
        "| gate | passed | actual | threshold |",
        "|---|---:|---|---|",
    ]
    for name, gate in acceptance["gates"].items():
        lines.append(
            f"| `{name}` | `{gate['passed']}` | `{_compact(gate.get('actual'))}` | "
            f"`{_compact(gate.get('threshold', gate.get('baseline')))}` |"
        )
    lines.extend(
        [
            "",
            "## Full Window",
            "",
            "| path | total % | ann % | sharpe | max dd % | TQQQ bh % |",
            "|---|---:|---:|---:|---:|---:|",
            _metrics_row("baseline", full["baseline"]),
            _metrics_row("gated", full["gated"]),
            "",
            "## Walk Forward",
            "",
            "| fold | gated total % | TQQQ bh % | beats TQQQ | gated sharpe | gated max dd % |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for row in payload["walk_forward"]:
        gated = row["gated"]
        lines.append(
            f"| {row['name']} | {_fmt(gated['total_return_pct'])} | "
            f"{_fmt(gated['benchmark_buy_hold_return_pct'])} | `{row['gated_beats_tqqq']}` | "
            f"{_fmt(gated['sharpe_ratio'])} | {_fmt(gated['max_drawdown_pct'])} |"
        )
    lines.extend(
        [
            "",
            "## Attribution",
            "",
            f"- ML release days: `{payload['attribution']['ml_release_days']}`",
            "- Non-hard-stress state/weight changes: "
            f"`{payload['attribution']['non_hard_stress_state_or_weight_changes']}`",
            "- ML release net delta arithmetic pp: "
            f"`{_fmt(payload['attribution']['ml_release_net_delta_arithmetic_pct_points'])}`",
            "",
            "## Pass Status",
            "",
            f"- workflow_pass: `{payload['pass_status']['workflow_pass']}`",
            f"- research_pass: `{payload['pass_status']['research_pass']}`",
            f"- llm_contribution_pass: `{payload['pass_status']['llm_contribution_pass']}`",
            f"- paper_ready_pass: `{payload['pass_status']['paper_ready_pass']}`",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _metrics_row(label: str, row: dict[str, Any]) -> str:
    return (
        f"| {label} | {_fmt(row['total_return_pct'])} | "
        f"{_fmt(row['annualized_return_pct'])} | {_fmt(row['sharpe_ratio'])} | "
        f"{_fmt(row['max_drawdown_pct'])} | {_fmt(row['benchmark_buy_hold_return_pct'])} |"
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.3f}"
    return str(value)


def _compact(value: Any) -> str:
    if isinstance(value, dict | list):
        return json.dumps(value, sort_keys=True)
    return _fmt(value)
