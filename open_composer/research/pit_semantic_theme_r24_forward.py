from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SOURCE_PACKET_CONTRACT = "pit_semantic_theme_r24_forward_source_v1"
SEMANTIC_MATERIALIZATION_CONTRACT = "pit_semantic_theme_r24_forward_semantic_materialization_v1"
RUNTIME_STATUS = "pit_contract_validation_only_no_observation_or_orders"
BROKER_WRITES = False
ORDER_AUTHORITY = False


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("R24 forward timestamps must be timezone-aware")
    return value.astimezone(UTC)


def _canonical_hash(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_input_payload(packet: R24ForwardSourcePacket) -> dict[str, Any]:
    payload = packet.model_dump(mode="json")
    payload.pop("packet_id", None)
    payload.pop("input_hash", None)
    return payload


class R24ForwardSourcePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    packet_contract: Literal["pit_semantic_theme_r24_forward_source_v1"]
    packet_id: str = Field(pattern=r"^r24pkt_[a-f0-9]{24}$")
    epoch_id: str = Field(min_length=1)
    source: Literal["news.alpaca", "events.sec_filings"]
    source_version_key: str = Field(min_length=1)
    provider_article_id: str = Field(min_length=1)
    version_id: str = Field(min_length=1)
    symbols: list[str] = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=2000)
    summary: str = Field(max_length=10000)
    source_url: str
    published_at: datetime
    fetched_at: datetime
    first_seen_at: datetime
    visible_at: datetime
    input_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    rights_scope: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    acquisition_mode: Literal["live_api_forward_only"]
    dedupe_key: str = Field(min_length=1)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.upper().strip() for value in values if value.strip()})
        if not normalized:
            raise ValueError("R24 source packet requires at least one symbol")
        return normalized

    @model_validator(mode="after")
    def validate_provenance(self) -> R24ForwardSourcePacket:
        self.published_at = _utc(self.published_at)
        self.fetched_at = _utc(self.fetched_at)
        self.first_seen_at = _utc(self.first_seen_at)
        self.visible_at = _utc(self.visible_at)
        if self.fetched_at < self.published_at:
            raise ValueError("R24 fetched_at cannot precede published_at")
        if self.first_seen_at < self.fetched_at:
            raise ValueError("R24 first_seen_at cannot precede fetched_at")
        if self.visible_at < max(self.published_at, self.fetched_at, self.first_seen_at):
            raise ValueError("R24 visible_at violates safe first-seen ordering")
        expected_hash = _canonical_hash(_source_input_payload(self))
        if self.input_hash != expected_hash:
            raise ValueError("R24 source packet input_hash mismatch")
        if self.packet_id != f"r24pkt_{expected_hash[:24]}":
            raise ValueError("R24 source packet packet_id mismatch")
        return self


class R24SemanticMaterialization(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    materialization_contract: Literal["pit_semantic_theme_r24_forward_semantic_materialization_v1"]
    materialization_id: str = Field(pattern=r"^r24sem_[a-f0-9]{24}$")
    epoch_id: str = Field(min_length=1)
    source_packet_ids: list[str] = Field(min_length=1, max_length=8)
    visible_at: datetime
    prompt_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    model: str = Field(min_length=1)
    model_parameters_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    structured_output_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    unknown_fields: list[str] = Field(default_factory=list, max_length=32)
    semantic_stock_budget: Literal[0.0]
    broker_writes: Literal[False]
    order_authority: Literal[False]

    @field_validator("source_packet_ids")
    @classmethod
    def validate_packet_ids(cls, values: list[str]) -> list[str]:
        normalized = sorted(set(values))
        if len(normalized) != len(values):
            raise ValueError("R24 semantic source packet IDs must be unique")
        if any(not value.startswith("r24pkt_") for value in normalized):
            raise ValueError("R24 semantic materialization references a foreign packet")
        return normalized

    @field_validator("visible_at")
    @classmethod
    def normalize_visible_at(cls, value: datetime) -> datetime:
        return _utc(value)


def build_r24_forward_source_packet(payload: dict[str, Any]) -> R24ForwardSourcePacket:
    candidate = dict(payload)
    candidate.setdefault("schema_version", 1)
    candidate.setdefault("packet_contract", SOURCE_PACKET_CONTRACT)
    candidate["symbols"] = sorted({value.upper().strip() for value in candidate["symbols"]})
    for field_name in ("published_at", "fetched_at", "first_seen_at", "visible_at"):
        candidate[field_name] = _utc(candidate[field_name])
    candidate["packet_id"] = "r24pkt_" + "0" * 24
    candidate["input_hash"] = "0" * 64
    unverified = R24ForwardSourcePacket.model_construct(**candidate)
    digest = _canonical_hash(_source_input_payload(unverified))
    candidate["input_hash"] = digest
    candidate["packet_id"] = f"r24pkt_{digest[:24]}"
    return R24ForwardSourcePacket.model_validate(candidate)


def require_r24_observation_runtime() -> None:
    raise RuntimeError(
        "R24 forward observation is unavailable until historical promotion and target-adapter "
        "parity gates pass"
    )
