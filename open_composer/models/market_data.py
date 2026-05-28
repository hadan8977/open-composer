from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

MarketDataKind = Literal[
    "ohlcv_bar",
    "trade_tick",
    "quote_tick",
    "order_book_delta",
    "depth_snapshot",
]


class TradeTickRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    symbol: str = Field(min_length=1)
    price: float = Field(gt=0)
    size: float = Field(gt=0)
    exchange: str = ""
    conditions: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)


class QuoteTickRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    symbol: str = Field(min_length=1)
    bid_price: float = Field(gt=0)
    bid_size: float = Field(ge=0)
    ask_price: float = Field(gt=0)
    ask_size: float = Field(ge=0)
    exchange: str = ""
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def bid_must_not_exceed_ask(self) -> QuoteTickRow:
        if self.bid_price > self.ask_price:
            raise ValueError("bid_price must be <= ask_price")
        return self


class OrderBookDeltaRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    symbol: str = Field(min_length=1)
    side: Literal["bid", "ask"]
    price: float = Field(gt=0)
    size_delta: float
    level: int = Field(ge=1)
    sequence: int = Field(ge=0)
    source: str = Field(min_length=1)


class DepthLevel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    price: float = Field(gt=0)
    size: float = Field(ge=0)


class DepthSnapshotRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    symbol: str = Field(min_length=1)
    bids: list[DepthLevel] = Field(default_factory=list)
    asks: list[DepthLevel] = Field(default_factory=list)
    sequence: int = Field(ge=0)
    source: str = Field(min_length=1)

    @model_validator(mode="after")
    def require_two_sided_book(self) -> DepthSnapshotRow:
        if not self.bids or not self.asks:
            raise ValueError("depth snapshot requires at least one bid and one ask")
        best_bid = max(level.price for level in self.bids)
        best_ask = min(level.price for level in self.asks)
        if best_bid > best_ask:
            raise ValueError("best bid must be <= best ask")
        return self


class MarketDataManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: MarketDataKind
    path: str
    symbol: str
    venue: str = ""
    first_timestamp: datetime
    last_timestamp: datetime
    row_count: int = Field(ge=0)
    timezone: str = "UTC"
    source: str
    quality_flags: list[str] = Field(default_factory=list)
    sha256: str
    paper_ready: bool = False

    @model_validator(mode="after")
    def timestamps_must_be_ordered(self) -> MarketDataManifest:
        first = self.first_timestamp
        last = self.last_timestamp
        if first.tzinfo is None:
            first = first.replace(tzinfo=UTC)
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if first > last:
            raise ValueError("first_timestamp must be <= last_timestamp")
        return self
