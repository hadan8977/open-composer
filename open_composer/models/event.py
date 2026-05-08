from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    source: str
    symbol: str
    published_at: datetime
    fetched_at: datetime
    event_type: str
    title: str
    summary: str
    url: str = ""
    sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    relevance_score: float = Field(default=0.0, ge=0, le=1)
    dedupe_key: str
    raw: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()


class SignalContext(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signal_id: str
    symbol: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    events: list[EventRecord] = Field(default_factory=list)
    macro: list[EventRecord] = Field(default_factory=list)
    news: list[EventRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def event_id(source: str, symbol: str, published_at: datetime, title: str) -> str:
    raw = f"{source}|{symbol}|{published_at.isoformat()}|{title}"
    return f"evt_{hashlib.sha256(raw.encode()).hexdigest()[:16]}"
