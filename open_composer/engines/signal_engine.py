from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from open_composer.expressions import ExpressionError, evaluate_rule_block, required_history_bars
from open_composer.models.signal import Signal, signal_id
from open_composer.models.strategy_spec import StrategySpec


def signal_masks(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path | None = None,
) -> tuple[pd.Series, pd.Series]:
    frame = frame.copy()
    frame.attrs.update({"strategy_name": spec.name})
    _validate_signal_frame(spec, frame)
    entry = evaluate_rule_block(
        frame,
        spec.entry.all,
        spec.entry.any,
        spec.factors,
        root=root,
        symbol=spec.primary_symbol,
    )
    exit_ = evaluate_rule_block(
        frame,
        spec.exit.all,
        spec.exit.any,
        spec.factors,
        root=root,
        symbol=spec.primary_symbol,
    )
    return entry, exit_


def required_signal_history_bars(spec: StrategySpec) -> int:
    inferred = required_history_bars(spec.all_expressions(), spec.factors)
    declared = getattr(spec.data_assumptions, "minimum_complete_bars", None)
    if declared is None:
        return inferred
    try:
        return max(inferred, int(declared))
    except (TypeError, ValueError) as exc:
        raise ExpressionError("data_assumptions.minimum_complete_bars must be an integer") from exc


def _validate_signal_frame(spec: StrategySpec, frame: pd.DataFrame) -> None:
    required = required_signal_history_bars(spec)
    if len(frame) < required:
        message = (
            f"strategy {spec.name} requires at least {required} complete bars; "
            f"received {len(frame)}"
        )
        raise ExpressionError(message)
    missing = [
        column
        for column in ["timestamp", "open", "high", "low", "close", "volume"]
        if column not in frame
    ]
    if missing:
        raise ExpressionError("signal frame missing required columns: " + ", ".join(missing))
    recent = frame.tail(required)
    timestamps = pd.to_datetime(recent["timestamp"], utc=True, errors="coerce")
    if timestamps.isna().any() or timestamps.duplicated().any():
        raise ExpressionError(
            "signal frame has invalid or duplicate timestamps in required history"
        )
    numeric = recent[["open", "high", "low", "close", "volume"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if numeric.isna().any().any():
        raise ExpressionError("signal frame has nonfinite required OHLCV values")
    finite = numeric.map(lambda value: math.isfinite(float(value)))
    if not finite.all().all():
        raise ExpressionError("signal frame has nonfinite required OHLCV values")


def build_signal(
    spec: StrategySpec,
    run_id: str,
    timestamp: datetime,
    action: str,
    source: str,
    price: float,
    version_id: str | None = None,
    spec_hash: str | None = None,
    execution_backend: str = "python_reference",
    symbol: str | None = None,
    conditions: list[str] | None = None,
    qty: float | None = None,
    target_weight: float | None = None,
    side_override: Literal["buy", "sell"] | None = None,
) -> Signal:
    if side_override is not None:
        side = side_override
    elif spec.position_direction == "short_only":
        side = "sell" if action == "entry" else "buy"
    else:
        side = "buy" if action == "entry" else "sell"
    selected_symbol = symbol or spec.primary_symbol
    conditions = (
        conditions
        if conditions is not None
        else (
            [*spec.entry.all, *spec.entry.any]
            if action == "entry"
            else [
                *spec.exit.all,
                *spec.exit.any,
            ]
        )
    )
    return Signal(
        id=signal_id(spec.name, selected_symbol, timestamp, action),
        run_id=run_id,
        strategy_name=spec.name,
        strategy_id=spec.name,
        version_id=version_id,
        spec_hash=spec_hash,
        strategy_backend=spec.execution.backend,
        execution_backend=execution_backend,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        timestamp=timestamp,
        action=action,  # type: ignore[arg-type]
        side=side,  # type: ignore[arg-type]
        source=source,
        price=float(price),
        qty=qty,
        target_weight=target_weight,
        conditions=conditions,
        lifecycle=spec.lifecycle,
        execution_mode=spec.execution.mode,
        fill_assumption=spec.execution.fill_assumption,
    )
