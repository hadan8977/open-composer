from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from open_composer.adapters.execution.router_target_weights import (
    infer_acquisition_tier,
    write_router_execution_artifacts,
)
from open_composer.config import data_feed, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.beta_exposure_router import beta_params_from_label
from open_composer.research.core_beta_satellite_router import (
    _build_beta_indicator_cache,
    _build_cache,
    _effective_lookback,
    _target_snapshot,
    core_beta_satellite_params_from_label,
    load_core_beta_satellite_dataset,
)
from open_composer.research.metadata import runtime_payload
from open_composer.storage import write_json


@dataclass(frozen=True)
class CoreBetaSatelliteTargetWeightMappingResult:
    report_path: Path
    json_path: Path
    target_weight_count: int
    rebalance_sessions: int
    nonzero_target_rows: int
    validation_status: str


def run_core_beta_satellite_target_weight_mapping(
    spec_path: Path,
    root: Path | None = None,
    *,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    selected_route_label: str | None = None,
    refresh_data: bool = False,
) -> CoreBetaSatelliteTargetWeightMappingResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    label = selected_route_label or spec.portfolio.selected_route_label
    if not label:
        raise ValueError("core beta satellite target-weight mapping requires selected_route_label")
    params = core_beta_satellite_params_from_label(label)
    selected_feed = feed or spec.data.feed or data_feed()

    stage_started = perf_counter()
    dataset = load_core_beta_satellite_dataset(
        root=base,
        spec=spec,
        symbols=symbols,
        params_grid=[params],
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    cache = _build_cache(dataset)
    beta_cache = _build_beta_indicator_cache(dataset.beta_dataset)
    core_params = beta_params_from_label(params.core_route_label)
    start_index = _effective_lookback(params)
    end_index = len(dataset.frame) - 1
    target_rows, rebalance_intents = _build_target_weight_rows(
        spec=spec,
        dataset=dataset,
        cache=cache,
        beta_cache=beta_cache,
        core_params=core_params,
        params=params,
        start_index=start_index,
        end_index=end_index,
    )
    validation = _validation(spec, target_rows)
    stages["build_mapping"] = perf_counter() - stage_started

    json_path = (
        base / "reports" / "execution" / f"{spec.name}-core-beta-satellite-target-weights.json"
    )
    report_path = json_path.with_suffix(".md")
    runtime = runtime_payload(started_at, stages)
    acquisition_tier = infer_acquisition_tier(
        data_source=data_source,
        data_profile=dataset.data_profile,
        refresh_data=refresh_data,
    )
    router_artifacts = write_router_execution_artifacts(
        root=base,
        spec_path=spec_path,
        spec=spec,
        target_rows=target_rows,
        rebalance_intents=rebalance_intents,
        data_profile=dataset.data_profile,
        route_label=params.label,
        mapping_summary={
            "mapping_mode": "core_beta_satellite_target_weight_mapping",
            "core_route_label": params.core_route_label,
        },
        acquisition_tier=acquisition_tier,
        parity_check=validation,
    )
    summary = {
        "rebalance_sessions": len({row["rebalance_session"] for row in target_rows}),
        "target_weight_rows": len(target_rows),
        "nonzero_target_rows": sum(float(row["target_weight"]) > 0 for row in target_rows),
        "rebalance_intents": len(rebalance_intents),
        "order_required_intents": sum(bool(row["requires_order"]) for row in rebalance_intents),
        "max_gross_exposure": max(
            _gross_for_session(target_rows, str(session))
            for session in {row["rebalance_session"] for row in target_rows}
        )
        if target_rows
        else 0.0,
    }
    payload = {
        "strategy_name": spec.name,
        "mode": "core_beta_satellite_target_weight_mapping",
        "target_backend": "nautilus_trader",
        "source_spec_path": _relpath(spec_path, base),
        "route_label": params.label,
        "core_route_label": params.core_route_label,
        "universe": _all_trade_symbols(dataset),
        "data_profile": dataset.data_profile,
        "acquisition_tier": acquisition_tier,
        "summary": summary,
        "validation": validation,
        "router_execution_artifacts": {
            name: _relpath(path, base) for name, path in router_artifacts.items()
        },
        "target_weights": target_rows,
        "rebalance_intents": rebalance_intents,
        "runtime_seconds": runtime,
        "safety_note": (
            "This maps the selected core-beta-satellite route to observation-only target "
            "weights. It does not submit broker orders."
        ),
    }
    write_json(json_path, payload)
    _write_report(report_path, json_path, spec, params.label, summary, validation)
    return CoreBetaSatelliteTargetWeightMappingResult(
        report_path=report_path,
        json_path=json_path,
        target_weight_count=len(target_rows),
        rebalance_sessions=int(summary["rebalance_sessions"]),
        nonzero_target_rows=int(summary["nonzero_target_rows"]),
        validation_status=str(validation["status"]),
    )


def _build_target_weight_rows(
    *,
    spec: StrategySpec,
    dataset,
    cache,
    beta_cache,
    core_params,
    params,
    start_index: int,
    end_index: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    symbols = _all_trade_symbols(dataset)
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    previous_targets = {symbol: 0.0 for symbol in symbols}
    for index in range(start_index, end_index):
        rebalance_session = dataset.dates[index]
        signal_session = dataset.dates[index - 1] if index > 0 else dataset.dates[index]
        snapshot = _target_snapshot(dataset, cache, beta_cache, core_params, params, index)
        target_by_symbol = {symbol: snapshot.weights.get(symbol, 0.0) for symbol in symbols}
        for symbol in symbols:
            target = float(target_by_symbol[symbol])
            previous = float(previous_targets[symbol])
            delta = target - previous
            row = {
                "rebalance_id": f"{spec.name}:{rebalance_session}",
                "rebalance_session": rebalance_session,
                "signal_session": signal_session,
                "time_rule": "regular_session_open",
                "symbol": symbol,
                "target_weight": target,
                "state": snapshot.state,
                "route_label": params.label,
                "selected": symbol in snapshot.selected,
                "core_gross": snapshot.core_gross,
                "satellite_gross": snapshot.satellite_gross,
                "satellite_scale": snapshot.satellite_scale,
                "theme_gate_ok": snapshot.theme_gate_ok,
                "source": "core_beta_satellite_python_reference",
            }
            target_rows.append(row)
            if target > 0 or previous > 0:
                intents.append(
                    {
                        "rebalance_id": row["rebalance_id"],
                        "rebalance_session": rebalance_session,
                        "time_rule": "regular_session_open",
                        "symbol": symbol,
                        "from_weight": previous,
                        "to_weight": target,
                        "delta_weight": delta,
                        "side": _side(delta),
                        "intent_type": "set_target_weight",
                        "requires_order": abs(delta) > 1e-12,
                        "reference_daily_roll": True,
                    }
                )
        previous_targets = target_by_symbol
    return target_rows, intents


def _validation(spec: StrategySpec, target_rows: list[dict[str, object]]) -> dict[str, object]:
    sessions = sorted({str(row["rebalance_session"]) for row in target_rows})
    max_gross = max((_gross_for_session(target_rows, session) for session in sessions), default=0.0)
    max_weight = max((float(row["target_weight"]) for row in target_rows), default=0.0)
    gross_limit = spec.portfolio.gross_exposure_limit or 1.0
    max_symbol_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    blockers: list[str] = []
    warnings = ["core-beta-satellite target weights are observation-only until paper readiness"]
    if max_gross > gross_limit + 1e-9:
        blockers.append(f"max_gross_exposure={max_gross:.4f} exceeds limit={gross_limit:.4f}")
    if max_weight > max_symbol_weight + 1e-9:
        blockers.append(f"max_symbol_weight={max_weight:.4f} exceeds limit={max_symbol_weight:.4f}")
    return {
        "status": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "warnings": warnings,
        "checks": {
            "rebalance_sessions": len(sessions),
            "max_gross_exposure": max_gross,
            "gross_exposure_limit": gross_limit,
            "max_symbol_weight": max_weight,
            "max_symbol_weight_limit": max_symbol_weight,
        },
    }


def _write_report(
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    route_label: str,
    summary: dict[str, object],
    validation: dict[str, object],
) -> Path:
    lines = [
        f"# Core Beta Satellite Target Weights: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Route: `{route_label}`",
        f"- Validation: `{validation['status']}`",
        "- Execution substate: `observation_only`",
        "",
        "## Summary",
        "",
        f"- Rebalance sessions: `{summary['rebalance_sessions']}`",
        f"- Target-weight rows: `{summary['target_weight_rows']}`",
        f"- Nonzero target rows: `{summary['nonzero_target_rows']}`",
        f"- Order-required intents: `{summary['order_required_intents']}`",
        f"- Max gross exposure: `{float(summary['max_gross_exposure']):.4f}`",
        "",
        "## Safety",
        "",
        "- This artifact does not submit orders or authorize paper_auto.",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _all_trade_symbols(dataset) -> list[str]:
    return list(dict.fromkeys(["QQQ", "TQQQ", "SQQQ", *dataset.symbols]))


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
