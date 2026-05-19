from __future__ import annotations

import json
import math
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from open_composer.adapters.broker.alpaca_paper import (
    PaperOrderError,
    _trading_client,
    submit_paper_order,
    sync_paper_account,
    sync_paper_orders,
)
from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.adapters.execution import build_nautilus_paper_plan, write_nautilus_paper_plan
from open_composer.config import ensure_dir, project_root, run_id
from open_composer.context import build_signal_context
from open_composer.engines.scanner_engine import run_scan
from open_composer.engines.signal_engine import build_signal, signal_masks
from open_composer.feature_packets import (
    should_auto_emit_context_features,
    write_context_feature_packet,
)
from open_composer.models.runner import PaperRunCycle, PaperRunSignalResult
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.notifications import safe_dispatch_notification
from open_composer.paper_controls import load_paper_kill_switch, paper_open_order_rows
from open_composer.paper_readiness import (
    PaperStrategyReadinessReport,
    assess_paper_strategy_readiness,
    format_paper_readiness_blockers,
    write_paper_readiness_report,
)
from open_composer.reports.writer import write_scan_report
from open_composer.research.hybrid_adaptive_router import (
    _hybrid_selected_symbols,
    _load_daily_hybrid_dataset,
    hybrid_params_from_label,
)
from open_composer.review.llm import review_signal_with_status
from open_composer.storage import append_jsonl
from open_composer.strategy_lifecycle import resolve_strategy_path
from open_composer.strategy_versions import register_strategy_version


class PaperRunnerError(RuntimeError):
    pass


OPEN_ORDER_STATUSES = {
    "accepted",
    "new",
    "partially_filled",
    "pending_cancel",
    "pending_new",
    "submitted",
}
RECENT_OPEN_ORDER_SECONDS = 36 * 60 * 60
OPEN_TO_OPEN_ORDER_WINDOW_START = (9, 20)
OPEN_TO_OPEN_ORDER_WINDOW_END = (9, 30)


def run_paper_cycle(
    spec_ref: str | Path,
    root: Path | None = None,
    allow_paper_orders: bool = False,
    with_review: bool = True,
    require_review_consider: bool = False,
    client: Any | None = None,
) -> PaperRunCycle:
    base = root or project_root()
    spec_path = resolve_strategy_path(spec_ref, base)
    spec = load_strategy_spec(spec_path)
    _validate_runtime_spec(spec)
    readiness = assess_paper_strategy_readiness(spec_path, base)
    readiness_path, _ = write_paper_readiness_report(readiness, base)
    version = register_strategy_version(spec_path, base, created_by="paper_runner")

    cycle = PaperRunCycle(
        run_id=run_id(f"paper-{spec.name}"),
        strategy_name=spec.name,
        strategy_id=spec.name,
        version_id=version.version_id,
        spec_hash=version.content_hash,
        strategy_backend=spec.execution.backend,
        execution_backend="python_reference",
        paper_readiness_report_path=str(readiness_path),
        spec_path=str(spec_path),
        notes=[
            "Runner uses deterministic latest-bar scan.",
            "Paper orders require active paper_auto strategy and explicit allow flag.",
            "Live real-money broker writes are out of scope.",
            f"Paper readiness status={readiness.status}.",
        ],
    )
    if not readiness.ready:
        cycle.notes.append(format_paper_readiness_blockers(readiness))
    signals: list[Signal]
    if spec.execution.backend == "nautilus_trader":
        plan_path = base / "reports" / "runs" / "nautilus_paper" / f"{cycle.run_id}.json"
        plan = build_nautilus_paper_plan(
            spec_path,
            base,
            run_id_value=cycle.run_id,
            version_id=version.version_id,
            spec_hash=version.content_hash,
        )
        write_nautilus_paper_plan(plan_path, plan)
        cycle.backend_plan_path = str(plan_path)
        cycle.execution_backend = plan.selected_backend
        cycle.notes.append(
            "Nautilus paper runtime generated latest-bar signals before the Alpaca Paper "
            "safety gate."
            if plan.selected_backend == "nautilus_paper"
            else (
                "Nautilus paper runtime fell back to the Python reference scan because the "
                "paper plan is not executable."
            )
        )
        if plan.selected_backend == "nautilus_paper":
            if spec.portfolio.mode == "hybrid_adaptive_router":
                signals = _run_hybrid_paper_signal_cycle(
                    spec,
                    base,
                    run_id_value=cycle.run_id,
                    version_id=version.version_id,
                    spec_hash=version.content_hash,
                    client=client,
                    refresh_data=spec.data.source in {"alpaca", "longbridge"},
                )
            else:
                signals = _run_nautilus_paper_signal_cycle(
                    spec,
                    base,
                    run_id_value=cycle.run_id,
                    version_id=version.version_id,
                    spec_hash=version.content_hash,
                    refresh_data=spec.data.source in {"alpaca", "longbridge"},
                )
        else:
            signals = run_scan(
                spec_path,
                root=base,
                refresh_data=spec.data.source in {"alpaca", "longbridge"},
            )
    else:
        signals = run_scan(
            spec_path,
            root=base,
            refresh_data=spec.data.source in {"alpaca", "longbridge"},
        )
    if not signals:
        cycle.notes.append("No latest-bar signal.")
        cycle.finished_at = datetime.now(UTC)
        _write_cycle_artifacts(base, cycle)
        return cycle

    for signal in signals:
        context = build_signal_context(signal.id, base)
        if should_auto_emit_context_features(spec):
            write_context_feature_packet(signal.id, base)
            if (
                "Context-derived feature packets were auto-written for context-capable signals."
                not in cycle.notes
            ):
                cycle.notes.append(
                    "Context-derived feature packets were auto-written for context-capable signals."
                )
        review_result = None
        if with_review and spec.llm_review.enabled:
            review_result = review_signal_with_status(signal, spec, base, context=context)
        signal_result = _decide_signal(
            signal_id=signal.id,
            action=signal.action,
            symbol=signal.symbol,
            price=signal.price,
            spec=spec,
            allow_paper_orders=allow_paper_orders,
            require_review_consider=require_review_consider,
            review_result=review_result,
            readiness=readiness,
            root=base,
            client=client,
        )
        _notify_paper_signal(signal_result, spec, base)
        cycle.signals.append(signal_result)
    cycle.finished_at = datetime.now(UTC)
    _write_cycle_artifacts(base, cycle)
    return cycle


def run_paper_loop(
    spec_ref: str | Path,
    root: Path | None = None,
    allow_paper_orders: bool = False,
    with_review: bool = True,
    require_review_consider: bool = False,
    interval_seconds: float = 60.0,
    max_cycles: int = 1,
    client: Any | None = None,
) -> list[PaperRunCycle]:
    cycles: list[PaperRunCycle] = []
    index = 0
    while max_cycles == 0 or index < max_cycles:
        cycles.append(
            run_paper_cycle(
                spec_ref,
                root=root,
                allow_paper_orders=allow_paper_orders,
                with_review=with_review,
                require_review_consider=require_review_consider,
                client=client,
            )
        )
        index += 1
        if max_cycles != 0 and index >= max_cycles:
            break
        time.sleep(interval_seconds)
    return cycles


def _run_nautilus_paper_signal_cycle(
    spec: StrategySpec,
    root: Path,
    *,
    run_id_value: str,
    version_id: str,
    spec_hash: str,
    refresh_data: bool,
) -> list[Signal]:
    frame = load_ohlcv_for_spec(spec, root, refresh=refresh_data)
    entry_mask, exit_mask = signal_masks(spec, frame, root=root)
    latest = frame.iloc[-1]
    timestamp = latest["timestamp"].to_pydatetime()
    signals: list[Signal] = []

    if bool(entry_mask.iloc[-1]):
        signals.append(
            build_signal(
                spec,
                run_id_value,
                timestamp,
                "entry",
                "paper",
                float(latest["close"]),
                version_id=version_id,
                spec_hash=spec_hash,
                execution_backend="nautilus_paper",
            )
        )
    elif bool(exit_mask.iloc[-1]):
        signals.append(
            build_signal(
                spec,
                run_id_value,
                timestamp,
                "exit",
                "paper",
                float(latest["close"]),
                version_id=version_id,
                spec_hash=spec_hash,
                execution_backend="nautilus_paper",
            )
        )

    log_path = root / "signal_logs" / f"{run_id_value}.jsonl"
    report_path = root / "reports" / "scans" / f"{run_id_value}.md"
    append_jsonl(log_path, signals)
    write_scan_report(
        report_path,
        run_id_value,
        spec,
        signals,
        version_id=version_id,
        spec_hash=spec_hash,
        execution_backend="nautilus_paper",
        root=root,
    )
    return signals


def _run_hybrid_paper_signal_cycle(
    spec: StrategySpec,
    root: Path,
    *,
    run_id_value: str,
    version_id: str,
    spec_hash: str,
    client: Any | None,
    refresh_data: bool,
) -> list[Signal]:
    if not spec.portfolio.selected_route_label:
        raise PaperRunnerError("hybrid paper runtime requires a selected_route_label")
    params = hybrid_params_from_label(spec.portfolio.selected_route_label)
    dataset = _load_daily_hybrid_dataset(
        spec=spec,
        root=root,
        symbols=[item.upper() for item in spec.universe],
        data_source=spec.data.source,
        feed=spec.data.feed,
        start=None,
        end=None,
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        refresh_data=refresh_data,
    )
    latest_index = len(dataset.dates)
    gross_limit = spec.portfolio.gross_exposure_limit or 1.0
    max_symbol_weight = spec.portfolio.max_symbol_weight or spec.risk.max_position_weight
    effective_top_n = min(
        params.top_n,
        max(1, int(gross_limit / max_symbol_weight)) if max_symbol_weight > 0 else 1,
        spec.risk.max_trades_per_day,
    )
    selected = _hybrid_selected_symbols(dataset, latest_index, params, effective_top_n)
    latest = dataset.frame.iloc[-1]
    timestamp = latest["timestamp"].to_pydatetime()
    price_by_symbol = {
        symbol: float(latest[f"{symbol}_close"])
        for symbol in dataset.symbols
        if f"{symbol}_close" in latest and float(latest[f"{symbol}_close"]) > 0
    }
    client = client or _trading_client()
    _sync_broker_state(root, client)
    equity = float(getattr(client.get_account(), "equity", 0) or 0)
    positions = {position.symbol: float(position.qty) for position in _client_positions(client)}
    pending_by_symbol = _pending_open_order_deltas(root, strategy_name=spec.name)
    selected_weight = min(max_symbol_weight, gross_limit / len(selected)) if selected else 0.0
    signals: list[Signal] = []
    for symbol in dataset.symbols:
        price = price_by_symbol.get(symbol)
        if price is None or price <= 0:
            continue
        target_weight = selected_weight if symbol in selected else 0.0
        target_qty = math.floor((equity * target_weight) / price) if target_weight > 0 else 0
        pending_qty = pending_by_symbol.get(symbol, 0.0)
        if abs(pending_qty) > 1e-9:
            continue
        current_qty = positions.get(symbol, 0.0)
        delta_qty = target_qty - current_qty
        if abs(delta_qty) < 1e-9:
            continue
        action = "entry" if delta_qty > 0 else "exit"
        conditions = [
            f"route={params.label}",
            f"selected={symbol in selected}",
            f"target_weight={target_weight:.6f}",
            f"target_qty={target_qty:.4f}",
            f"current_qty={current_qty:.4f}",
            f"delta_qty={delta_qty:.4f}",
        ]
        signals.append(
            build_signal(
                spec,
                run_id_value,
                timestamp,
                action,
                "paper",
                price,
                version_id=version_id,
                spec_hash=spec_hash,
                execution_backend="nautilus_paper",
                symbol=symbol,
                conditions=conditions,
                qty=abs(delta_qty),
                target_weight=target_weight,
            )
        )

    log_path = root / "signal_logs" / f"{run_id_value}.jsonl"
    report_path = root / "reports" / "scans" / f"{run_id_value}.md"
    append_jsonl(log_path, signals)
    write_scan_report(
        report_path,
        run_id_value,
        spec,
        signals,
        version_id=version_id,
        spec_hash=spec_hash,
        execution_backend="nautilus_paper",
        root=root,
    )
    return signals


def _validate_runtime_spec(spec: StrategySpec) -> None:
    if spec.lifecycle != "active":
        raise PaperRunnerError("paper runner requires an active StrategySpec")
    if spec.execution.mode not in {"manual_signal", "paper_auto"}:
        raise PaperRunnerError(f"unsupported execution mode: {spec.execution.mode}")
    if spec.execution.mode == "paper_auto" and spec.execution.broker != "alpaca_paper":
        raise PaperRunnerError("paper_auto runner requires broker=alpaca_paper")


def _decide_signal(
    signal_id: str,
    action: str,
    symbol: str,
    price: float,
    spec: StrategySpec,
    allow_paper_orders: bool,
    require_review_consider: bool,
    review_result: Any | None,
    readiness: PaperStrategyReadinessReport,
    root: Path,
    client: Any | None,
) -> PaperRunSignalResult:
    review_status = (
        getattr(review_result, "status", "not_requested") if review_result else "not_requested"
    )
    review_card = getattr(review_result, "review", None) if review_result else None
    review_verdict = getattr(review_card, "verdict", None)
    if spec.execution.mode == "manual_signal":
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="manual_review",
            review_status=review_status,
            review_verdict=review_verdict,
            message="manual_signal mode: review signal and submit explicitly if desired",
        )
    if not allow_paper_orders:
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="paper_orders_not_allowed",
            review_status=review_status,
            review_verdict=review_verdict,
            message="pass --allow-paper-orders or use oc paper submit after manual approval",
        )
    kill_switch = load_paper_kill_switch(root)
    if kill_switch.enabled:
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="blocked_by_kill_switch",
            review_status=review_status,
            review_verdict=review_verdict,
            message="paper kill switch is enabled"
            + (f": {kill_switch.reason}" if kill_switch.reason else ""),
        )
    if not readiness.ready:
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="blocked_by_readiness",
            review_status=review_status,
            review_verdict=review_verdict,
            message=format_paper_readiness_blockers(readiness),
        )
    if not _paper_order_window_allows(spec):
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="blocked_by_trade_window",
            review_status=review_status,
            review_verdict=review_verdict,
            message=(
                "open_to_open hybrid paper orders are only allowed 09:20-09:30 America/New_York"
            ),
        )
    if require_review_consider and review_verdict != "consider":
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="blocked_by_review",
            review_status=review_status,
            review_verdict=review_verdict,
            message="review gate requires verdict=consider",
        )
    try:
        from open_composer.storage import find_signal

        signal = find_signal(signal_id, root)
        order = submit_paper_order(
            signal,
            spec,
            root,
            client=client,
            qty=getattr(signal, "qty", None),
        )
    except PaperOrderError as exc:
        return PaperRunSignalResult(
            signal_id=signal_id,
            action=action,  # type: ignore[arg-type]
            symbol=symbol,
            price=price,
            decision="order_error",
            review_status=review_status,
            review_verdict=review_verdict,
            message=str(exc),
        )
    return PaperRunSignalResult(
        signal_id=signal_id,
        action=action,  # type: ignore[arg-type]
        symbol=symbol,
        price=price,
        decision="paper_order_submitted",
        review_status=review_status,
        review_verdict=review_verdict,
        order_id=order.id,
        message=f"paper order status={order.status}",
    )


def _paper_order_window_allows(spec: StrategySpec, now: datetime | None = None) -> bool:
    if spec.portfolio.mode != "hybrid_adaptive_router":
        return True
    route = spec.portfolio.selected_route_label or ""
    if not route.startswith("open_to_open:"):
        return True
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    local = current.astimezone(ZoneInfo(spec.data_assumptions.timezone))
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    start = OPEN_TO_OPEN_ORDER_WINDOW_START[0] * 60 + OPEN_TO_OPEN_ORDER_WINDOW_START[1]
    end = OPEN_TO_OPEN_ORDER_WINDOW_END[0] * 60 + OPEN_TO_OPEN_ORDER_WINDOW_END[1]
    return start <= minutes <= end


def _client_positions(client: Any) -> list[Any]:
    if hasattr(client, "get_all_positions"):
        return list(client.get_all_positions())
    if hasattr(client, "get_positions"):
        return list(client.get_positions())
    return []


def _sync_broker_state(root: Path, client: Any) -> None:
    sync_paper_orders(root, client=client)
    sync_paper_account(root, client=client)


def _pending_open_order_deltas(root: Path, *, strategy_name: str) -> dict[str, float]:
    deltas: dict[str, float] = {}
    for row in _deduped_paper_order_rows(root):
        status = _order_status_token(row.get("status"))
        if status not in OPEN_ORDER_STATUSES:
            continue
        submitted_at = _parse_optional_datetime(row.get("submitted_at"))
        if (
            submitted_at
            and (datetime.now(UTC) - submitted_at).total_seconds() > RECENT_OPEN_ORDER_SECONDS
        ):
            continue
        row_strategy = str(row.get("strategy_name") or "")
        if row_strategy and row_strategy != strategy_name:
            continue
        symbol = str(row.get("symbol") or "").upper()
        side = str(row.get("side") or "").lower().split(".")[-1]
        if not symbol:
            continue
        try:
            qty = float(row.get("qty") or 0.0)
        except (TypeError, ValueError):
            continue
        signed = qty if side == "buy" else -qty if side == "sell" else 0.0
        deltas[symbol] = deltas.get(symbol, 0.0) + signed
    return deltas


def _deduped_paper_order_rows(root: Path) -> list[dict[str, Any]]:
    broker_rows = paper_open_order_rows(root)
    if broker_rows is not None:
        return broker_rows
    paper_root = root / "reports" / "paper"
    rows_by_key: dict[str, dict[str, Any]] = {}
    for path in sorted(paper_root.glob("*.jsonl")):
        if path.name == "kill_switch_events.jsonl":
            continue
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if not isinstance(raw, dict) or "status" not in raw:
                    continue
                key = str(raw.get("client_order_id") or raw.get("id") or f"{path.name}:{index}")
                rows_by_key[key] = raw
    return list(rows_by_key.values())


def _order_status_token(value: Any) -> str:
    return str(value or "").lower().split(".")[-1]


def _parse_optional_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        timestamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if timestamp.tzinfo is None:
        return timestamp.replace(tzinfo=UTC)
    return timestamp.astimezone(UTC)


def _notify_paper_signal(
    signal_result: PaperRunSignalResult,
    spec: StrategySpec,
    root: Path,
) -> None:
    if signal_result.decision == "order_error":
        kind = "alpaca_error"
        severity = "red"
    elif signal_result.decision in {
        "blocked_by_kill_switch",
        "blocked_by_readiness",
        "blocked_by_review",
    }:
        kind = "signal_actionable"
        severity = "warn"
    else:
        kind = "signal_actionable"
        severity = "info"
    safe_dispatch_notification(
        kind=kind,  # type: ignore[arg-type]
        severity=severity,  # type: ignore[arg-type]
        title=(
            f"{spec.name}: {signal_result.action.upper()} "
            f"{signal_result.symbol} {signal_result.decision}"
        ),
        body=signal_result.message,
        metadata={
            "signal_id": signal_result.signal_id,
            "strategy": spec.name,
            "symbol": signal_result.symbol,
            "action": signal_result.action,
            "price": signal_result.price,
            "decision": signal_result.decision,
            "execution_mode": spec.execution.mode,
        },
        root=root,
    )


def _write_cycle_artifacts(root: Path, cycle: PaperRunCycle) -> None:
    append_jsonl(root / "reports" / "runs" / "paper_cycles.jsonl", [cycle])
    _write_cycle_markdown(root / "reports" / "runs" / f"{cycle.run_id}.md", cycle)


def _write_cycle_markdown(path: Path, cycle: PaperRunCycle) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Paper Runner Cycle: {cycle.strategy_name}",
        "",
        f"- Run ID: `{cycle.run_id}`",
        f"- Strategy ID: `{cycle.strategy_id or cycle.strategy_name}`",
        f"- Version ID: `{cycle.version_id or 'unregistered'}`",
        f"- Spec hash: `{cycle.spec_hash or 'unregistered'}`",
        f"- Strategy backend: `{cycle.strategy_backend}`",
        f"- Execution backend: `{cycle.execution_backend}`",
        f"- Backend plan: `{cycle.backend_plan_path or 'n/a'}`",
        f"- Paper readiness: `{cycle.paper_readiness_report_path or 'n/a'}`",
        f"- Started: {cycle.started_at.isoformat()}",
        f"- Finished: {cycle.finished_at.isoformat() if cycle.finished_at else 'open'}",
        f"- Spec: `{cycle.spec_path}`",
        "",
        "## Signals",
        "",
    ]
    if cycle.signals:
        lines.extend(
            f"- `{item.signal_id}` {item.action} {item.symbol} @ {item.price:.2f}: "
            f"{item.decision} review={item.review_verdict or item.review_status} "
            f"order={item.order_id or 'n/a'}"
            for item in cycle.signals
        )
    else:
        lines.append("- No latest-bar signal.")
    lines.extend(["", "## Notes", "", *[f"- {note}" for note in cycle.notes]])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
