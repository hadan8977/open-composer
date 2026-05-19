from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import ExecutionBackend


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    strategy_name: str
    strategy_id: str | None = None
    version_id: str | None = None
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    symbol: str
    timeframe: str
    timestamp: datetime
    action: Literal["entry", "exit"]
    side: Literal["buy", "sell"]
    source: str
    price: float
    qty: float | None = None
    target_weight: float | None = None
    conditions: list[str] = Field(default_factory=list)
    lifecycle: str
    execution_mode: str
    fill_assumption: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def signal_id(strategy_name: str, symbol: str, timestamp: datetime, action: str) -> str:
    raw = f"{strategy_name}|{symbol}|{timestamp.isoformat()}|{action}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"sig_{digest}"
