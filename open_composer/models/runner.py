from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class PaperRunSignalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    action: Literal["entry", "exit"]
    symbol: str
    price: float
    decision: Literal[
        "manual_review",
        "paper_order_submitted",
        "paper_orders_not_allowed",
        "blocked_by_review",
        "order_error",
    ]
    review_status: str = "not_requested"
    review_verdict: str | None = None
    order_id: str | None = None
    message: str = ""


class PaperRunCycle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    strategy_name: str
    spec_path: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    signals: list[PaperRunSignalResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
