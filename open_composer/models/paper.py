from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperOrderRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    signal_id: str
    client_order_id: str
    strategy_name: str
    symbol: str
    side: Literal["buy", "sell"]
    qty: float
    status: str
    paper: bool = True
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
