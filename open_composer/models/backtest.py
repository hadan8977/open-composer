from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import ExecutionBackend

DataSanityStatus = Literal["ok", "warning"]


class BacktestDataSanity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: DataSanityStatus
    evidence_level: str
    bars: int
    signals: int
    trades: int
    data_source: str
    data_source_mode: str | None = None
    data_feed: str | None = None
    data_path: str | None = None
    first_timestamp: datetime | None = None
    last_timestamp: datetime | None = None
    data_span_days: float | None = None
    average_holding_days: float | None = None
    warnings: list[str] = Field(default_factory=list)


class Trade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_time: datetime
    exit_time: datetime | None = None
    entry_price: float
    exit_price: float | None = None
    shares: float
    entry_fee: float = 0.0
    exit_fee: float = 0.0
    gross_pnl: float = 0.0
    pnl: float = 0.0
    return_pct: float = 0.0


class BacktestRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    strategy_name: str
    strategy_id: str | None = None
    version_id: str | None = None
    spec_hash: str | None = None
    strategy_backend: ExecutionBackend = "python_reference"
    execution_backend: ExecutionBackend = "python_reference"
    symbol: str
    timeframe: str
    bars: int
    signals: int
    trades: int
    start_equity: float
    end_equity: float
    total_return_pct: float
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    total_fees: float = 0.0
    backend_plan_path: str | None = None
    data_sanity: BacktestDataSanity | None = None
    assumptions: list[str] = Field(default_factory=list)
    report_path: str | None = None
    signal_log_path: str | None = None
