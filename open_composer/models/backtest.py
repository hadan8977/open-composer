from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Trade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_time: datetime
    exit_time: datetime | None = None
    entry_price: float
    exit_price: float | None = None
    shares: float
    pnl: float = 0.0
    return_pct: float = 0.0


class BacktestRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    strategy_name: str
    symbol: str
    timeframe: str
    bars: int
    signals: int
    trades: int
    start_equity: float
    end_equity: float
    total_return_pct: float
    assumptions: list[str] = Field(default_factory=list)
    report_path: str | None = None
    signal_log_path: str | None = None
