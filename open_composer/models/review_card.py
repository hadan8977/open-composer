from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewCard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    strategy_name: str
    symbol: str
    timestamp: str
    verdict: Literal["consider", "avoid", "wait"]
    confidence: float = Field(ge=0, le=1)
    catalyst: str = ""
    evidence: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    invalidation: list[str] = Field(default_factory=list)
    primary_risk_source: str = ""
    if_wrong_top_3_reasons: list[str] = Field(default_factory=list, max_length=3)
    action_suggestion: str
    model: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
