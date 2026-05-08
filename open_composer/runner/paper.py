from __future__ import annotations

import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.adapters.broker.alpaca_paper import PaperOrderError, submit_paper_order
from open_composer.config import ensure_dir, project_root, run_id
from open_composer.context import build_signal_context
from open_composer.engines.scanner_engine import run_scan
from open_composer.models.runner import PaperRunCycle, PaperRunSignalResult
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.review.llm import review_signal_with_status
from open_composer.storage import append_jsonl
from open_composer.strategy_lifecycle import resolve_strategy_path


class PaperRunnerError(RuntimeError):
    pass


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

    cycle = PaperRunCycle(
        run_id=run_id(f"paper-{spec.name}"),
        strategy_name=spec.name,
        spec_path=str(spec_path),
        notes=[
            "Runner uses deterministic latest-bar scan.",
            "Paper orders require active paper_auto strategy and explicit allow flag.",
            "Live real-money broker writes are out of scope.",
        ],
    )
    signals = run_scan(spec_path, root=base, refresh_data=spec.data.source == "alpaca")
    if not signals:
        cycle.notes.append("No latest-bar signal.")
        cycle.finished_at = datetime.now(UTC)
        _write_cycle_artifacts(base, cycle)
        return cycle

    for signal in signals:
        context = build_signal_context(signal.id, base)
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
            root=base,
            client=client,
        )
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

        order = submit_paper_order(find_signal(signal_id, root), spec, root, client=client)
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


def _write_cycle_artifacts(root: Path, cycle: PaperRunCycle) -> None:
    append_jsonl(root / "reports" / "runs" / "paper_cycles.jsonl", [cycle])
    _write_cycle_markdown(root / "reports" / "runs" / f"{cycle.run_id}.md", cycle)


def _write_cycle_markdown(path: Path, cycle: PaperRunCycle) -> Path:
    ensure_dir(path.parent)
    lines = [
        f"# Paper Runner Cycle: {cycle.strategy_name}",
        "",
        f"- Run ID: `{cycle.run_id}`",
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
