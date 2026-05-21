from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TargetWeightRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    rebalance_id: str
    rebalance_session: str
    signal_session: str | None = None
    time_rule: str = "regular_session_open"
    symbol: str
    target_weight: float


class RebalanceIntent(BaseModel):
    model_config = ConfigDict(extra="allow")

    rebalance_id: str
    rebalance_session: str
    time_rule: str = "regular_session_open"
    symbol: str
    from_weight: float
    to_weight: float
    delta_weight: float
    side: Literal["buy", "sell", "hold"]
    intent_type: str = "set_target_weight"
    requires_order: bool = False


class TargetWeightSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_spec_path: str
    portfolio_mode: str
    route_label: str | None = None
    universe: list[str] = Field(default_factory=list)
    data_profile: dict[str, object] = Field(default_factory=dict)
    acquisition_tier: str = "sample_smoke"
    target_backend: str = "nautilus_trader"
    target_weights: list[TargetWeightRow] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    safety_note: str


class RebalanceIntentSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_spec_path: str
    portfolio_mode: str
    route_label: str | None = None
    intents: list[RebalanceIntent] = Field(default_factory=list)
    summary: dict[str, object] = Field(default_factory=dict)
    execution_substate: Literal["blocked", "observation_only", "order_authorized"] = (
        "observation_only"
    )
    safety_note: str


class RouterExecutionObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_name: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_spec_path: str
    portfolio_mode: str
    route_label: str | None = None
    execution_substate: Literal["blocked", "observation_only", "order_authorized"]
    target_weights_path: str
    rebalance_intents_path: str
    cost_stress_path: str | None = None
    data_evidence_path: str | None = None
    validation_path: str | None = None
    latest_rebalance_session: str | None = None
    latest_order_required_intents: int = 0
    blockers: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    safety_note: str
