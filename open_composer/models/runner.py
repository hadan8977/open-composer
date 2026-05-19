from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import ExecutionBackend


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
        "blocked_by_kill_switch",
        "blocked_by_readiness",
        "blocked_by_trade_window",
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
    strategy_id: str | None = None
    version_id: str | None = None
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    backend_plan_path: str | None = None
    paper_readiness_report_path: str | None = None
    spec_path: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    signals: list[PaperRunSignalResult] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
