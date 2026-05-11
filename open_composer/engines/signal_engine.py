from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from open_composer.expressions import evaluate_rule_block
from open_composer.models.signal import Signal, signal_id
from open_composer.models.strategy_spec import StrategySpec


def signal_masks(
    spec: StrategySpec,
    frame: pd.DataFrame,
    root: Path | None = None,
) -> tuple[pd.Series, pd.Series]:
    entry = evaluate_rule_block(frame, spec.entry.all, spec.entry.any, spec.factors, root=root)
    exit_ = evaluate_rule_block(frame, spec.exit.all, spec.exit.any, spec.factors, root=root)
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
) -> Signal:
    side = "buy" if action == "entry" else "sell"
    conditions = (
        [*spec.entry.all, *spec.entry.any]
        if action == "entry"
        else [
            *spec.exit.all,
            *spec.exit.any,
        ]
    )
    return Signal(
        id=signal_id(spec.name, spec.primary_symbol, timestamp, action),
        run_id=run_id,
        strategy_name=spec.name,
        strategy_id=spec.name,
        version_id=version_id,
        spec_hash=spec_hash,
        strategy_backend=spec.execution.backend,
        execution_backend=execution_backend,
        symbol=spec.primary_symbol,
        timeframe=spec.timeframe,
        timestamp=timestamp,
        action=action,  # type: ignore[arg-type]
        side=side,  # type: ignore[arg-type]
        source=source,
        price=float(price),
        conditions=conditions,
        lifecycle=spec.lifecycle,
        execution_mode=spec.execution.mode,
        fill_assumption=spec.execution.fill_assumption,
    )
