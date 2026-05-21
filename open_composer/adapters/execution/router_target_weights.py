from __future__ import annotations

from pathlib import Path
from statistics import mean
from typing import Any

from open_composer.config import ensure_dir
from open_composer.models.router_execution import (
    RebalanceIntent,
    RebalanceIntentSnapshot,
    RouterExecutionObservation,
    TargetWeightRow,
    TargetWeightSnapshot,
)
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import write_json

ROUTER_MODES = {
    "adaptive_intraday_internal_router",
    "hybrid_adaptive_router",
    "beta_exposure_router",
    "core_beta_satellite_router",
}


def is_router_strategy(spec: StrategySpec) -> bool:
    return spec.portfolio.mode in ROUTER_MODES


def infer_acquisition_tier(
    *,
    data_source: str,
    data_profile: dict[str, Any] | None = None,
    explicit: str | None = None,
    refresh_data: bool = False,
) -> str:
    if explicit:
        return explicit
    profile = data_profile or {}
    source_mode = str(profile.get("source_mode") or profile.get("data_source_mode") or "").lower()
    if data_source == "sample" or "sample" in source_mode:
        return "sample_smoke"
    if "fixture" in source_mode or "fallback" in source_mode:
        return "fixture_replay"
    if data_source in {"yahoo", "stooq", "alpha_vantage"}:
        return "research_cross_check"
    if refresh_data or source_mode == "live_fetch":
        return "paper_ready_live"
    if source_mode == "cache" or "cache" in source_mode:
        return "cached_live"
    if data_source in {"alpaca", "longbridge"}:
        return "cached_live"
    return "research_cross_check"


def write_router_execution_artifacts(
    *,
    root: Path,
    spec_path: Path,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    rebalance_intents: list[dict[str, object]],
    data_profile: dict[str, object],
    route_label: str | None,
    mapping_summary: dict[str, object],
    acquisition_tier: str,
    parity_check: dict[str, object] | None = None,
) -> dict[str, Path]:
    execution_dir = ensure_dir(root / "reports" / "execution")
    target_path = execution_dir / f"{spec.name}-target-weights.json"
    intents_path = execution_dir / f"{spec.name}-rebalance-intents.json"
    observation_path = execution_dir / f"{spec.name}-execution-observation.json"
    cost_stress_path = root / "reports" / "research" / f"{spec.name}-router-cost-stress.json"
    data_evidence_path = root / "reports" / "research" / f"{spec.name}-router-data-evidence.json"
    validation_path = root / "reports" / "research" / f"{spec.name}-router-validation.json"

    normalized_targets = [
        TargetWeightRow.model_validate(row).model_dump(mode="json") for row in target_rows
    ]
    normalized_intents = [
        RebalanceIntent.model_validate(row).model_dump(mode="json") for row in rebalance_intents
    ]
    summary = _summary(normalized_targets, normalized_intents) | dict(mapping_summary)
    source_spec_path = _relpath(spec_path, root)
    target_snapshot = TargetWeightSnapshot(
        strategy_name=spec.name,
        source_spec_path=source_spec_path,
        portfolio_mode=spec.portfolio.mode,
        route_label=route_label,
        universe=list(spec.universe),
        data_profile=data_profile,
        acquisition_tier=acquisition_tier,
        target_weights=normalized_targets,
        summary=summary,
        safety_note=(
            "Router target weights are observation/control artifacts. They do not submit "
            "broker orders or authorize paper_auto execution."
        ),
    )
    intent_snapshot = RebalanceIntentSnapshot(
        strategy_name=spec.name,
        source_spec_path=source_spec_path,
        portfolio_mode=spec.portfolio.mode,
        route_label=route_label,
        intents=normalized_intents,
        summary=summary,
        execution_substate="observation_only",
        safety_note=(
            "Rebalance intents describe desired target-weight changes only; broker order "
            "authorization is handled by paper readiness and safety gates."
        ),
    )
    validation = _validation_payload(
        spec=spec,
        summary=summary,
        parity_check=parity_check or {},
        target_rows=normalized_targets,
    )
    cost_stress = _cost_stress_payload(spec, summary)
    data_evidence = _data_evidence_payload(
        spec=spec,
        data_profile=data_profile,
        acquisition_tier=acquisition_tier,
    )
    blockers = list(validation.get("blockers", []))
    warnings = list(validation.get("warnings", [])) + list(data_evidence.get("warnings", []))
    observation = RouterExecutionObservation(
        strategy_name=spec.name,
        source_spec_path=source_spec_path,
        portfolio_mode=spec.portfolio.mode,
        route_label=route_label,
        execution_substate="observation_only" if not blockers else "blocked",
        target_weights_path=_relpath(target_path, root),
        rebalance_intents_path=_relpath(intents_path, root),
        cost_stress_path=_relpath(cost_stress_path, root),
        data_evidence_path=_relpath(data_evidence_path, root),
        validation_path=_relpath(validation_path, root),
        latest_rebalance_session=_latest_session(normalized_targets),
        latest_order_required_intents=int(summary.get("order_required_intents") or 0),
        blockers=blockers,
        warnings=warnings,
        safety_note=(
            "Router execution observation is read-only and remains separate from broker "
            "order authorization."
        ),
    )
    write_json(target_path, target_snapshot)
    write_json(intents_path, intent_snapshot)
    write_json(cost_stress_path, cost_stress)
    write_json(data_evidence_path, data_evidence)
    write_json(validation_path, validation)
    write_json(observation_path, observation)
    return {
        "router_target_weights": target_path,
        "router_rebalance_intents": intents_path,
        "router_execution_observation": observation_path,
        "router_cost_stress": cost_stress_path,
        "router_data_evidence": data_evidence_path,
        "router_validation": validation_path,
    }


def _summary(
    target_rows: list[dict[str, Any]],
    intents: list[dict[str, Any]],
) -> dict[str, object]:
    sessions = sorted({str(row["rebalance_session"]) for row in target_rows})
    gross_values = [
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
        "max_gross_exposure": max(gross_values, default=0.0),
        "average_gross_exposure": mean(gross_values) if gross_values else 0.0,
    }


def _validation_payload(
    *,
    spec: StrategySpec,
    summary: dict[str, object],
    parity_check: dict[str, object],
    target_rows: list[dict[str, Any]],
) -> dict[str, object]:
    blockers: list[str] = []
    warnings: list[str] = []
    max_gross = float(summary.get("max_gross_exposure") or 0.0)
    gross_limit = spec.portfolio.gross_exposure_limit or 1.0
    max_symbol_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    max_weight = max(
        (abs(float(row.get("target_weight") or 0.0)) for row in target_rows),
        default=0.0,
    )
    if max_gross > gross_limit + 1e-9:
        blockers.append(f"max_gross_exposure={max_gross:.4f} exceeds limit={gross_limit:.4f}")
    if max_weight > max_symbol_weight + 1e-9:
        blockers.append(f"max_symbol_weight={max_weight:.4f} exceeds limit={max_symbol_weight:.4f}")
    if parity_check.get("status") == "blocked":
        blockers.extend(str(item) for item in parity_check.get("blockers", []) if item)
    warnings.extend(str(item) for item in parity_check.get("warnings", []) if item)
    return {
        "strategy_name": spec.name,
        "status": "blocked" if blockers else "ok",
        "portfolio_mode": spec.portfolio.mode,
        "route_label": spec.portfolio.selected_route_label,
        "summary": summary,
        "parity_check": parity_check,
        "blockers": blockers,
        "warnings": warnings,
    }


def _cost_stress_payload(spec: StrategySpec, summary: dict[str, object]) -> dict[str, object]:
    turnover_proxy = float(summary.get("order_required_intents") or 0.0)
    rebalance_sessions = max(float(summary.get("rebalance_sessions") or 0.0), 1.0)
    order_intensity = turnover_proxy / rebalance_sessions
    base_slippage = spec.costs.slippage_bps
    scenarios = [
        {"name": "base", "slippage_bps": base_slippage, "turnover_intensity": order_intensity},
        {
            "name": "double_slippage",
            "slippage_bps": base_slippage * 2 + 5,
            "turnover_intensity": order_intensity,
        },
        {
            "name": "stress_open",
            "slippage_bps": base_slippage * 4 + 15,
            "turnover_intensity": order_intensity * 1.5,
        },
    ]
    return {
        "strategy_name": spec.name,
        "status": "ok",
        "portfolio_mode": spec.portfolio.mode,
        "rebalance_sessions": int(summary.get("rebalance_sessions") or 0),
        "order_required_intents": int(summary.get("order_required_intents") or 0),
        "turnover_intensity": order_intensity,
        "scenarios": scenarios,
        "recommendation": "review stress_open before moving beyond observation_only",
    }


def _data_evidence_payload(
    *,
    spec: StrategySpec,
    data_profile: dict[str, object],
    acquisition_tier: str,
) -> dict[str, object]:
    warnings: list[str] = []
    if acquisition_tier in {
        "sample_smoke",
        "fixture_replay",
        "cached_live",
        "research_cross_check",
    }:
        warnings.append(f"acquisition_tier={acquisition_tier} is not paper-ready evidence")
    return {
        "strategy_name": spec.name,
        "status": "warning" if warnings else "ok",
        "data_source": spec.data.source,
        "timeframe": spec.timeframe,
        "acquisition_tier": acquisition_tier,
        "data_profile": data_profile,
        "warnings": warnings,
    }


def _latest_session(target_rows: list[dict[str, Any]]) -> str | None:
    sessions = sorted(str(row["rebalance_session"]) for row in target_rows)
    return sessions[-1] if sessions else None


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()
