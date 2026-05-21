from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import ExecutionBackend

DataSanityStatus = Literal["ok", "warning"]
ExecutionRealityStatus = Literal["ok", "warning", "blocked"]


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


class ExecutionRealityMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExecutionRealityStatus
    average_dollar_volume: float | None = None
    median_dollar_volume: float | None = None
    min_dollar_volume: float | None = None
    max_trade_notional: float | None = None
    max_bar_participation_pct: float | None = None
    average_bar_participation_pct: float | None = None
    max_adv_participation_pct: float | None = None
    estimated_capacity_notional: float | None = None
    capacity_curve: dict[str, float] = Field(default_factory=dict)
    recommended_max_participation_pct: float | None = None
    slippage_stress_bps: dict[str, float] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class Trade(BaseModel):
    model_config = ConfigDict(extra="forbid")

    direction: Literal["long", "short"] = "long"
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
    buy_hold_return_pct: float | None = None
    alpha_vs_buy_hold_pct: float | None = None
    annualized_return_pct: float | None = None
    sharpe_ratio: float | None = None
    annualized_volatility_pct: float | None = None
    max_drawdown_pct: float | None = None
    downside_volatility_pct: float | None = None
    sortino_ratio: float | None = None
    calmar_ratio: float | None = None
    win_rate_pct: float | None = None
    profit_factor: float | None = None
    average_trade_return_pct: float | None = None
    exposure_pct: float | None = None
    turnover_ratio: float | None = None
    total_fees: float = 0.0
    backend_plan_path: str | None = None
    data_sanity: BacktestDataSanity | None = None
    execution_reality: ExecutionRealityMetrics | None = None
    assumptions: list[str] = Field(default_factory=list)
    report_path: str | None = None
    signal_log_path: str | None = None
