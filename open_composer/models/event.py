from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EventRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    source: str
    symbol: str
    published_at: datetime
    fetched_at: datetime
    visible_at: datetime | None = None
    first_seen_at: datetime | None = None
    accepted_at: datetime | None = None
    vintage_at: datetime | None = None
    revision: str = "unknown"
    revision_id: str = "unknown"
    version_id: str = "unknown"
    rights: str = "unknown"
    rights_scope: str = "unknown"
    availability_quality: str = "unknown"
    availability_basis: str = "derived_safe_max"
    acquisition_mode: str = "unknown"
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

    @model_validator(mode="after")
    def materialize_visibility(self) -> EventRecord:
        self.published_at = _as_utc(self.published_at)
        self.fetched_at = _as_utc(self.fetched_at)
        self.first_seen_at = (
            _as_utc(self.first_seen_at) if self.first_seen_at is not None else self.fetched_at
        )
        if self.accepted_at is not None:
            self.accepted_at = _as_utc(self.accepted_at)
        if self.vintage_at is not None:
            self.vintage_at = _as_utc(self.vintage_at)
        earliest_safe_visibility = max(
            value
            for value in (
                self.published_at,
                self.fetched_at,
                self.first_seen_at,
                self.accepted_at,
            )
            if value is not None
        )
        if self.visible_at is None:
            self.visible_at = earliest_safe_visibility
        else:
            self.visible_at = _as_utc(self.visible_at)
            if self.visible_at < earliest_safe_visibility:
                raise ValueError(
                    "visible_at cannot precede published_at, fetched_at, "
                    "first_seen_at, or accepted_at"
                )
        return self


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
