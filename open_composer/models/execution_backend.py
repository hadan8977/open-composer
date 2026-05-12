from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ExecutionBackend = Literal[
    "python_reference",
    "nautilus_trader",
    "nautilus_backtest",
    "nautilus_paper",
]
BackendStatus = Literal["supported", "partial", "blocked", "unavailable"]


class NautilusCustomDataBinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    factor_name: str
    source: Literal["llm_feature", "feature_packet"]
    path: str
    field: str
    default: float | bool = 0.0
    replay_mode: str = "point_in_time_last_observation"
    description: str = ""
    exists: bool = False
    record_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    point_in_time_status: Literal["complete", "partial", "missing"] = "missing"
    replay_warnings: list[str] = Field(default_factory=list)


class NautilusBacktestPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    run_id: str
    version_id: str | None = None
    spec_hash: str | None = None
    selected_backend: ExecutionBackend
    target_backend: Literal["nautilus_trader"] = "nautilus_trader"
    execution_backend: Literal["nautilus_backtest"] = "nautilus_backtest"
    execution_mode: str
    broker: str
    data_source: str
    data_path: str | None = None
    symbol: str
    timeframe: str
    bar_type: str
    fill_assumption: str
    supported: bool
    status: BackendStatus
    reasons: list[str] = Field(default_factory=list)
    factor_names: list[str] = Field(default_factory=list)
    expression_factor_names: list[str] = Field(default_factory=list)
    llm_feature_factor_names: list[str] = Field(default_factory=list)
    feature_packet_factor_names: list[str] = Field(default_factory=list)
    factor_expressions: dict[str, str] = Field(default_factory=dict)
    custom_data_bindings: list[NautilusCustomDataBinding] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    nautilus_installed: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class NautilusPaperPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    run_id: str
    version_id: str | None = None
    spec_hash: str | None = None
    selected_backend: ExecutionBackend = "python_reference"
    target_backend: Literal["nautilus_paper"] = "nautilus_paper"
    execution_mode: str
    broker: str
    data_source: str
    symbol: str
    timeframe: str
    supported: bool
    status: BackendStatus
    reasons: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    custom_data_bindings: list[NautilusCustomDataBinding] = Field(default_factory=list)
    nautilus_installed: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionBackendPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    version_id: str | None = None
    spec_hash: str | None = None
    selected_backend: ExecutionBackend
    target_backend: ExecutionBackend = "nautilus_trader"
    execution_mode: str
    broker: str
    data_source: str
    symbol: str
    timeframe: str
    supported: bool
    status: BackendStatus
    reasons: list[str] = Field(default_factory=list)
    factor_names: list[str] = Field(default_factory=list)
    llm_feature_factor_names: list[str] = Field(default_factory=list)
    feature_packet_factor_names: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    nautilus_installed: bool = False
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
