from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Literal

import pandas as pd

from open_composer.expressions import evaluate_rule_block
from open_composer.models.signal import Signal, signal_id
from open_composer.models.strategy_spec import StrategySpec


def signal_masks(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path | None = None,
) -> tuple[pd.Series, pd.Series]:
    frame = frame.copy()
    frame.attrs.update({"strategy_name": spec.name})
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
