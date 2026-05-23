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
from open_composer.config import data_feed, ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.beta_router_core import (
    BetaRouterMetrics,
    _effective_lookback,
    backtest_beta_router_params,
    beta_params_from_label,
    beta_target_weight_snapshot,
    load_beta_router_dataset,
)
from open_composer.research.metadata import runtime_payload
from open_composer.storage import write_json


@dataclass(frozen=True)
class BetaTargetWeightMappingResult:
    report_path: Path
    json_path: Path
    target_weight_count: int
    rebalance_sessions: int
    nonzero_target_rows: int
    parity_status: str
    reference_metrics: BetaRouterMetrics


def run_beta_target_weight_mapping(
    spec_path: Path,
    root: Path | None = None,
    *,
    data_source: str = "alpaca",
    feed: str | None = None,
    start: str | None = None,
    end: str | None = None,
    market_symbol: str = "QQQ",
    leverage_symbol: str = "TQQQ",
    hedge_symbol: str | None = "SQQQ",
    selected_route_label: str | None = None,
    refresh_data: bool = False,
) -> BetaTargetWeightMappingResult:
    started_at = perf_counter()
    stages: dict[str, float] = {}
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_feed = feed or spec.data.feed or data_feed()
    label = selected_route_label or spec.portfolio.selected_route_label
    if not label:
        raise ValueError("beta target-weight mapping requires selected_route_label")
    params = beta_params_from_label(label)

    stage_started = perf_counter()
    dataset = load_beta_router_dataset(
        root=base,
        market_symbol=market_symbol,
        leverage_symbol=leverage_symbol,
        hedge_symbol=hedge_symbol,
        timeframe=spec.timeframe,
        data_source=data_source,
        feed=selected_feed,
        start=start,
        end=end,
        refresh_data=refresh_data,
    )
    stages["load_data"] = perf_counter() - stage_started

    stage_started = perf_counter()
    start_index = _effective_lookback(params) + 1
    end_index = len(dataset.frame) - 1
    reference = backtest_beta_router_params(
        spec,
        dataset,
        params,
        start_index=start_index,
        end_index=end_index,
    )
    target_rows, rebalance_intents = _build_target_weight_rows(
        spec=spec,
        dataset=dataset,
        params=params,
        start_index=start_index,
        end_index=end_index,
    )
    parity = _parity_check(
        spec=spec,
        target_rows=target_rows,
        reference=reference,
    )
    stages["build_mapping"] = perf_counter() - stage_started

    json_path = base / "reports" / "execution" / f"{spec.name}-beta-target-weights.json"
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
            "reference_metrics": reference.__dict__,
            "mapping_mode": "beta_target_weight_mapping",
        },
        acquisition_tier=acquisition_tier,
        parity_check=parity,
    )
    payload = {
        "strategy_name": spec.name,
        "mode": "beta_target_weight_mapping",
        "target_backend": "nautilus_trader",
        "source_spec_path": _relpath(spec_path, base),
        "route_label": params.label,
        "market_symbol": dataset.market_symbol,
        "leverage_symbol": dataset.leverage_symbol,
        "hedge_symbol": dataset.hedge_symbol,
        "universe": _symbols(dataset),
        "data_profile": dataset.data_profile,
        "acquisition_tier": acquisition_tier,
        "mapping_assumptions": _mapping_assumptions(spec, params.label),
        "nautilus_installed": nautilus_trader_available(),
        "reference_metrics": reference.__dict__,
        "summary": {
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
        },
        "parity_check": parity,
        "router_execution_artifacts": {
            name: _relpath(path, base) for name, path in router_artifacts.items()
        },
        "target_weights": target_rows,
        "rebalance_intents": rebalance_intents,
        "runtime_seconds": runtime,
        "safety_note": (
            "This artifact maps the selected beta route to target weights for Nautilus. "
            "It does not submit broker orders or enable paper_auto."
        ),
    }
    write_json(json_path, payload)
    _write_report(
        path=report_path,
        json_path=json_path,
        spec=spec,
        route_label=params.label,
        reference=reference,
        summary=payload["summary"],
        parity=parity,
        nautilus_installed=payload["nautilus_installed"],
        runtime=runtime,
    )
    return BetaTargetWeightMappingResult(
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
    spec: StrategySpec,
    dataset,
    params,
    start_index: int,
    end_index: int,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    symbols = _symbols(dataset)
    target_rows: list[dict[str, object]] = []
    intents: list[dict[str, object]] = []
    previous_targets = {symbol: 0.0 for symbol in symbols}
    for index in range(start_index, end_index):
        rebalance_session = dataset.dates[index]
        signal_session = dataset.dates[index - 1] if index > 0 else dataset.dates[index]
        snapshot = beta_target_weight_snapshot(dataset, params, index)
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
                "volatility_scale": snapshot.volatility_scale,
                "qqq_trend_ok": snapshot.qqq_trend_ok,
                "qqq_momentum_ok": snapshot.qqq_momentum_ok,
                "qqq_drawdown_ok": snapshot.qqq_drawdown_ok,
                "leverage_trend_ok": snapshot.leverage_trend_ok,
                "leverage_volatility_ok": snapshot.leverage_volatility_ok,
                "leverage_drawdown_ok": snapshot.leverage_drawdown_ok,
                "source": "beta_python_reference",
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


def _parity_check(
    *,
    spec: StrategySpec,
    target_rows: list[dict[str, object]],
    reference: BetaRouterMetrics,
) -> dict[str, object]:
    blockers: list[str] = []
    warnings: list[str] = []
    sessions = sorted({str(row["rebalance_session"]) for row in target_rows})
    selected_sessions = {
        str(row["rebalance_session"]) for row in target_rows if float(row["target_weight"]) > 0
    }
    max_gross = max((_gross_for_session(target_rows, session) for session in sessions), default=0.0)
    max_weight = max((float(row["target_weight"]) for row in target_rows), default=0.0)
    gross_limit = spec.portfolio.gross_exposure_limit or 1.0
    max_symbol_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    if len(selected_sessions) != reference.risk_on_days + reference.neutral_days:
        blockers.append(
            f"selected_sessions={len(selected_sessions)} does not match "
            f"reference_exposed_days={reference.risk_on_days + reference.neutral_days}"
        )
    if max_gross > gross_limit + 1e-9:
        blockers.append(f"max_gross_exposure={max_gross:.4f} exceeds limit={gross_limit:.4f}")
    if max_weight > max_symbol_weight + 1e-9:
        blockers.append(f"max_symbol_weight={max_weight:.4f} exceeds limit={max_symbol_weight:.4f}")
    if spec.execution.mode != "paper_auto":
        warnings.append(f"execution.mode={spec.execution.mode}; mapping only, no paper runtime")
    if spec.execution.broker != "alpaca_paper":
        warnings.append(f"execution.broker={spec.execution.broker}; no broker order submission")
    warnings.append("cash return is modeled at 0%; target rows are not broker submissions")
    return {
        "status": "pass" if not blockers else "blocked",
        "blockers": blockers,
        "warnings": warnings,
        "checks": {
            "selected_sessions": len(selected_sessions),
            "reference_exposed_days": reference.risk_on_days + reference.neutral_days,
            "max_gross_exposure": max_gross,
            "gross_exposure_limit": gross_limit,
            "max_symbol_weight": max_weight,
            "max_symbol_weight_limit": max_symbol_weight,
        },
    }


def _mapping_assumptions(spec: StrategySpec, route_label: str) -> list[str]:
    return [
        f"StrategySpec selected route is {route_label}.",
        "Signals are confirmed after the prior regular-session close.",
        "Target weights become effective at the next regular-session open.",
        "Rows are target weights, not broker order submissions.",
        f"Gross exposure is capped at {spec.portfolio.gross_exposure_limit or 1.0:.4f}.",
        "Per-symbol target is capped at "
        f"{spec.portfolio.max_symbol_weight or spec.risk.max_position_weight:.4f}.",
    ]


def _write_report(
    *,
    path: Path,
    json_path: Path,
    spec: StrategySpec,
    route_label: str,
    reference: BetaRouterMetrics,
    summary: dict[str, object],
    parity: dict[str, object],
    nautilus_installed: object,
    runtime: dict[str, Any],
) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Beta Target-Weight Mapping: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        "- Target backend: `nautilus_trader`",
        f"- Nautilus installed: `{nautilus_installed}`",
        f"- Route: `{route_label}`",
        f"- Execution mode/broker: `{spec.execution.mode}` / `{spec.execution.broker}`",
        f"- Parity status: `{parity['status']}`",
        f"- Runtime seconds: `{runtime['total']:.2f}`",
        "",
        "## Summary",
        "",
        f"- Rebalance sessions: `{summary['rebalance_sessions']}`",
        f"- Target-weight rows: `{summary['target_weight_rows']}`",
        f"- Nonzero target rows: `{summary['nonzero_target_rows']}`",
        f"- Rebalance intents: `{summary['rebalance_intents']}`",
        f"- Order-required intents: `{summary['order_required_intents']}`",
        f"- Max gross exposure: `{float(summary['max_gross_exposure']):.4f}`",
        "",
        "## Reference Metrics",
        "",
        f"- Full-window days: `{reference.days}`",
        f"- Annualized return: `{_fmt(reference.annualized_return_pct)}%`",
        f"- Sharpe: `{_fmt(reference.sharpe_ratio)}`",
        f"- Max drawdown: `{_fmt(reference.max_drawdown_pct)}%`",
        f"- Alpha vs QQQ annualized: `{_fmt(reference.alpha_vs_market_buy_hold_annualized_pct)}%`",
        f"- Risk-on / neutral / risk-off days: "
        f"`{reference.risk_on_days}/{reference.neutral_days}/{reference.risk_off_days}`",
        "",
        "## Parity",
        "",
        f"- Blockers: `{', '.join(parity['blockers']) if parity['blockers'] else 'none'}`",
        f"- Warnings: `{', '.join(parity['warnings']) if parity['warnings'] else 'none'}`",
        "",
        "## Safety",
        "",
        "- This mapping does not submit orders or enable paper_auto.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _symbols(dataset) -> list[str]:
    symbols = [dataset.market_symbol, dataset.leverage_symbol]
    if dataset.hedge_symbol:
        symbols.append(dataset.hedge_symbol)
    return symbols


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


def _relpath(path: Path, root: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.2f}"
    return str(value)
