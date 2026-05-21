from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Capability(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    kind: Literal["market", "event", "macro", "news", "options_chain"]
    status: Literal["approved", "trial", "retired", "workflow_only"]
    provider: str
    use_for: list[str] = Field(default_factory=list)
    reliability: str
    default_mode: Literal["offline", "live_with_cache"]
    fixture: str
    env: list[str] = Field(default_factory=list)
    min_score: float = Field(default=0.75, ge=0, le=1)
    caveats: list[str] = Field(default_factory=list)


class CapabilityRegistry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    capabilities: list[Capability]


class CapabilityEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capability_id: str
    status: str
    records: int
    score: float
    passed: bool
    issues: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
