from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any

from open_composer.adapters.execution.nautilus_trader import nautilus_trader_available
from open_composer.adapters.execution.router_target_weights import (
    infer_acquisition_tier,
    write_router_execution_artifacts,
)
from open_composer.config import data_feed, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.adaptive_intraday_router_core import _parse_route_label
from open_composer.research.intraday_daily_rotation import (
    _benchmark_side,
    _load_dataset,
    _selected_positions,
    _symbol_intraday_return,
)
from open_composer.research.metadata import combined_data_profile, runtime_payload
from open_composer.storage import write_json


@dataclass(frozen=True)
class AdaptiveIntradayTargetWeightMappingResult:
    report_path: Path
    json_path: Path
    target_weight_count: int
    rebalance_sessions: int
    nonzero_target_rows: int
    parity_status: str
    reference_metrics: dict[str, object]


def run_adaptive_intraday_target_weight_mapping(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    benchmark_symbol: str = "QQQ",
    market_symbol: str = "QQQ",
    selected_route_label: str | None = None,
    refresh_data: bool = False,
) -> AdaptiveIntradayTargetWeightMappingResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    selected_feed = feed or spec.data.feed or data_feed()
    label = selected_route_label or spec.portfolio.selected_route_label
    if not label:
        raise ValueError("adaptive intraday target-weight mapping requires selected_route_label")
    params = _parse_route_label(label)

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
    start_index = params.lookback_days
    end_index = len(dataset.dates)
    target_rows, rebalance_intents, reference = _build_target_weight_rows(
        spec=spec,
        dataset=dataset,
        params=params,
        route_label=label,
        start_index=start_index,
        end_index=end_index,
    )
    parity = _parity_check(spec=spec, target_rows=target_rows, reference=reference)
    stages["build_mapping"] = perf_counter() - stage_started

    json_path = base / "reports" / "execution" / f"{spec.name}-target-weights.json"
    report_path = json_path.with_suffix(".md")
    runtime = runtime_payload(started_at, stages)
    acquisition_tier = infer_acquisition_tier(
        data_source=data_source,
        data_profile=data_profile,
        refresh_data=refresh_data,
    )
    router_artifacts = write_router_execution_artifacts(
        root=base,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=rebalance_intents,
        data_profile=data_profile,
        route_label=label,
        mapping_summary={
            "reference_metrics": reference,
            "mapping_mode": "adaptive_intraday_target_weight_mapping",
        },
        acquisition_tier=acquisition_tier,
        parity_check=parity,
    )
    payload = {
        "strategy_name": spec.name,
        "mode": "adaptive_intraday_target_weight_mapping",
        "target_backend": "nautilus_trader",
        "source_spec_path": _relpath(spec_path, base),
        "route_label": label,
        "universe": dataset.symbols,
        "portfolio_mode": spec.portfolio.mode,
        "market_symbol": dataset.market_symbol,
        "benchmark_symbol": dataset.benchmark_symbol,
        "data_profile": data_profile,
        "acquisition_tier": acquisition_tier,
        "mapping_assumptions": _mapping_assumptions(spec, label),
        "nautilus_installed": nautilus_trader_available(),
        "reference_metrics": reference,
        "summary": _summary(target_rows, rebalance_intents),
        "parity_check": parity,
        "router_execution_artifacts": {
            name: _relpath(path, base) for name, path in router_artifacts.items()
        },
        "target_weights": target_rows,
        "rebalance_intents": rebalance_intents,
        "runtime_seconds": runtime,
        "safety_note": (
            "This artifact maps the selected adaptive intraday route to observation-only "
            "target weights. It does not submit broker orders or enable paper_auto."
        ),
    }
    write_json(json_path, payload)
    _write_report(
        path=report_path,
        json_path=json_path,
        route_label=label,
        summary=payload["summary"],
        parity=parity,
        runtime=runtime,
        reference=reference,
    )
    return AdaptiveIntradayTargetWeightMappingResult(
        report_path=report_path,
        json_path=json_path,
        target_weight_count=len(target_rows),
        rebalance_sessions=int(payload["summary"]["rebalance_sessions"]),
        nonzero_target_rows=int(payload["summary"]["nonzero_target_rows"]),
        parity_status=str(parity["status"]),
        reference_metrics=reference,
    )


def _build_target_weight_rows(
    *,
    spec,
    dataset,
    params,
    route_label: str,
    start_index: int,
    end_index: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]], dict[str, object]]:
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    previous_targets = {symbol: 0.0 for symbol in dataset.symbols}
    traded_days = 0
    round_trips = 0
    strategy_returns: list[float] = []
    max_position_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    gross_limit = spec.portfolio.gross_exposure_limit or max_position_weight
    max_per_leg = min(max_position_weight, gross_limit / max(params.top_n * 2, 1))

    for index in range(start_index, end_index):
        rebalance_session = dataset.dates[index]
        signal_session = dataset.dates[index]
        selected = _selected_positions(dataset, index, params, spec)
        target_by_symbol = {symbol: 0.0 for symbol in dataset.symbols}
        returns: list[float] = []
        for item in selected:
            signed_weight = max_per_leg if item.side == "long" else -max_per_leg
            target_by_symbol[item.symbol] = signed_weight
            value = _symbol_intraday_return(
                dataset,
                item.symbol,
                index,
                params,
                spec,
                side=item.side,
            )
            if value is not None:
                returns.append(value)
        if returns:
            traded_days += 1
            round_trips += len(returns)
        strategy_returns.append(
            sum(
                abs(target_by_symbol[item.symbol]) * value
                for item, value in zip(selected, returns, strict=False)
            )
        )
        rebalance_id = f"{spec.name}:{rebalance_session}"
        for symbol in dataset.symbols:
            target = float(target_by_symbol[symbol])
            previous = float(previous_targets[symbol])
            delta = target - previous
            row = {
                "rebalance_id": rebalance_id,
                "rebalance_session": rebalance_session,
                "signal_session": signal_session,
                "time_rule": "intraday_opening_window_next_bar",
                "symbol": symbol,
                "target_weight": target,
                "selected": abs(target) > 1e-12,
                "route_label": route_label,
                "source": "adaptive_intraday_python_reference",
            }
            target_rows.append(row)
            if abs(target) > 1e-12 or abs(previous) > 1e-12:
                intents.append(
                    {
                        "rebalance_id": rebalance_id,
                        "rebalance_session": rebalance_session,
                        "time_rule": "intraday_opening_window_next_bar",
                        "symbol": symbol,
                        "from_weight": previous,
                        "to_weight": target,
                        "delta_weight": delta,
                        "side": _side(delta),
                        "intent_type": "set_target_weight",
                        "requires_order": abs(delta) > 1e-12,
                        "same_day_flatten": spec.portfolio.same_day_flatten,
                    }
                )
        previous_targets = target_by_symbol
    reference = {
        "days": max(end_index - start_index, 0),
        "traded_days": traded_days,
        "round_trips": round_trips,
        "total_return_pct": _compound_return(strategy_returns),
        "benchmark_side": _benchmark_side(spec),
    }
    return target_rows, intents, reference


def _compound_return(returns: list[float]) -> float:
    equity = 1.0
    for value in returns:
        equity *= 1 + value
    return (equity - 1) * 100


def _summary(
    target_rows: list[dict[str, object]], intents: list[dict[str, object]]
) -> dict[str, object]:
    sessions = sorted({str(row["rebalance_session"]) for row in target_rows})
    gross_by_session = [
        sum(
            abs(float(row.get("target_weight") or 0.0))
            for row in target_rows
            if str(row.get("rebalance_session")) == session
        )
        for session in sessions
    ]
    return {
        "rebalance_sessions": len(sessions),
        "target_weight_rows": len(target_rows),
        "nonzero_target_rows": sum(
            abs(float(row.get("target_weight") or 0.0)) > 1e-12 for row in target_rows
        ),
        "rebalance_intents": len(intents),
        "order_required_intents": sum(bool(row.get("requires_order")) for row in intents),
        "max_gross_exposure": max(gross_by_session, default=0.0),
    }


def _parity_check(
    *, spec, target_rows: list[dict[str, object]], reference: dict[str, object]
) -> dict[str, object]:
    blockers: list[str] = []
    warnings: list[str] = []
    sessions = sorted({str(row["rebalance_session"]) for row in target_rows})
    max_gross = max((_gross_for_session(target_rows, session) for session in sessions), default=0.0)
    max_weight = max((abs(float(row["target_weight"])) for row in target_rows), default=0.0)
    gross_limit = spec.portfolio.gross_exposure_limit or 1.0
    symbol_limit = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    if max_gross > gross_limit + 1e-9:
        blockers.append(f"max_gross_exposure={max_gross:.4f} exceeds limit={gross_limit:.4f}")
    if max_weight > symbol_limit + 1e-9:
        blockers.append(f"max_symbol_weight={max_weight:.4f} exceeds limit={symbol_limit:.4f}")
    if spec.execution.mode != "paper_auto":
        warnings.append(f"execution.mode={spec.execution.mode}; mapping only, no paper runtime")
    if spec.execution.broker != "alpaca_paper":
        warnings.append(f"execution.broker={spec.execution.broker}; no broker order submission")
    warnings.append(
        "adaptive intraday mapping is observation-only and flattened by policy before "
        "broker routing"
    )
    return {
        "status": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "warnings": warnings,
        "checks": {
            "sessions": len(sessions),
            "reference_traded_days": reference.get("traded_days"),
            "reference_round_trips": reference.get("round_trips"),
            "max_gross_exposure": max_gross,
            "gross_exposure_limit": gross_limit,
            "max_symbol_weight": max_weight,
            "max_symbol_weight_limit": symbol_limit,
        },
    }


def _mapping_assumptions(spec, route_label: str) -> list[str]:
    return [
        f"StrategySpec selected route is {route_label}.",
        "Signals are confirmed after the configured opening window.",
        "Target weights become effective at the next intraday bar open.",
        "Rows are observation target weights, not broker order submissions.",
        f"Gross exposure is capped at {spec.portfolio.gross_exposure_limit or 1.0:.4f}.",
        "Per-symbol target is capped at "
        f"{spec.portfolio.max_symbol_weight or spec.risk.max_position_weight:.4f}.",
    ]


def _write_report(
    *,
    path: Path,
    json_path: Path,
    route_label: str,
    summary: dict[str, object],
    parity: dict[str, object],
    runtime: dict[str, Any],
    reference: dict[str, object],
) -> Path:
    lines = [
        "# Adaptive Intraday Target-Weight Mapping",
        "",
        f"- JSON report: `{json_path}`",
        "- Target backend: `nautilus_trader`",
        f"- Route: `{route_label}`",
        f"- Parity status: `{parity['status']}`",
        f"- Runtime seconds: `{runtime['total']:.2f}`",
        "",
        "## Summary",
        "",
        f"- Rebalance sessions: `{summary['rebalance_sessions']}`",
        f"- Target-weight rows: `{summary['target_weight_rows']}`",
        f"- Nonzero target rows: `{summary['nonzero_target_rows']}`",
        f"- Max gross exposure: `{float(summary['max_gross_exposure']):.4f}`",
        "",
        "## Reference",
        "",
        f"- Traded days / round trips: `{reference['traded_days']}/{reference['round_trips']}`",
        f"- Weighted total return: `{float(reference['total_return_pct']):.2f}%`",
        "",
        "## Parity",
        "",
        f"- Blockers: `{parity['blockers']}`",
        f"- Warnings: `{parity['warnings']}`",
        "",
        "This artifact is read-only and does not authorize broker orders.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _gross_for_session(target_rows: list[dict[str, object]], session: str) -> float:
    return sum(
        abs(float(row["target_weight"]))
        for row in target_rows
        if str(row["rebalance_session"]) == session
    )


def _side(delta: float) -> str:
    if delta > 0:
        return "buy"
    if delta < 0:
        return "sell"
    return "hold"


def _relpath(path: Path | str, root: Path) -> str:
    candidate = Path(path)
    try:
        return candidate.relative_to(root).as_posix()
    except ValueError:
        return candidate.as_posix()
