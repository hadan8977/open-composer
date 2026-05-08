from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Signal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    run_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    timestamp: datetime
    action: Literal["entry", "exit"]
    side: Literal["buy", "sell"]
    source: str
    price: float
    conditions: list[str] = Field(default_factory=list)
    lifecycle: str
    execution_mode: str
    fill_assumption: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


def signal_id(strategy_name: str, symbol: str, timestamp: datetime, action: str) -> str:
    raw = f"{strategy_name}|{symbol}|{timestamp.isoformat()}|{action}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"sig_{digest}"
