from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from open_composer.models.execution_backend import ExecutionBackend


class StrategyVersion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy_id: str
    strategy_name: str
    version_id: str
    content_hash: str
    lifecycle: str
    source_paths: list[str] = Field(default_factory=list)
    snapshot_path: str
    manifest_path: str
    parent_version_id: str | None = None
    created_by: str = "system"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    first_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_seen_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    model_ref: str | None = None
    prompt_session_id: str | None = None
    symbol: str
    timeframe: str
    universe: list[str] = Field(default_factory=list)
    factor_names: list[str] = Field(default_factory=list)
    llm_feature_factor_names: list[str] = Field(default_factory=list)
    feature_packet_factor_names: list[str] = Field(default_factory=list)
    backend: ExecutionBackend = "python_reference"
    execution_mode: str
    broker: str
    data_source: str
    llm_review_enabled: bool = False
    required_capabilities: list[str] = Field(default_factory=list)
