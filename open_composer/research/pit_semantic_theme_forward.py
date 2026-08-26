from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import shutil
from collections import Counter
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.events.fetcher import fetch_capability_events
from open_composer.config import default_openai_model, project_root
from open_composer.feature_packets import FeaturePacketRow
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.event import EventRecord
from open_composer.paper_freshness import latest_completed_us_equity_session
from open_composer.paper_state_drift import build_state_drift_report
from open_composer.research.llm_backends import get_backend
from open_composer.research.pit_semantic_theme_r12 import (
    ITER_ID,
    SPEC_PATHS,
    load_and_validate_r12_specs,
)
from open_composer.strategy_versions import strategy_content_hash

ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
FORWARD_LOCK_PATH = ITERATION_DIR / "forward" / "epoch-lock.json"
FORWARD_DATA_DIR = Path("data/forward/pit_semantic_theme_r12")
FORWARD_REPORT_DIR = Path("reports/forward/us_pit_semantic_theme_r12")
PACKET_SCHEMA_PATH = Path("schemas/pit_semantic_theme_forward_packet.schema.json")
PROMPT_PATH = Path("prompts/pit_semantic_theme_r12_factor_v1.txt")
HISTORICAL_LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
HISTORICAL_REPORT_PATH = ITERATION_DIR / "historical-evaluation/evaluation-report.json"
D01_TARGET_PATH = Path("reports/execution/us_pit_semantic_theme_r12_d01-target-weights.json")

SOURCE_PACKET_CONTRACT = "pit_semantic_theme_forward_source_v1"
FORWARD_LOCK_CONTRACT = "pit_semantic_theme_r12_forward_epoch_v1"
OBSERVATION_CONTRACT = "pit_semantic_theme_r12_forward_observation_v1"
RECEIPT_CONTRACT = "pit_semantic_theme_r12_forward_receipt_v1"
LLM_RETRY_CONTRACT = "pit_semantic_theme_r12_llm_retry_v1"
LLM_RETRY_RECEIPT_CONTRACT = "pit_semantic_theme_r12_llm_retry_receipt_v1"
FEATURE_SCHEMA_VERSION = "r12-forward-v1"
PLACEBO_SEED = 11108
MAX_THEME_PACKETS = 8
MAX_THEME_MEMBERS = 8
MIN_CONFIRMED_MEMBERS = 2
MIN_PRICE_SESSIONS = 60
MIN_PRICE = 10.0
MIN_MEDIAN_DOLLAR_VOLUME = 25_000_000.0
MAX_PACKET_AGE = timedelta(days=7)
PRICE_LOOKBACK_DAYS = 180
PRICE_FEED = "iex"

ALLOWED_RELATIONSHIPS = (
    "supplier",
    "customer",
    "equipment",
    "material",
    "energy",
    "infrastructure",
    "competitor",
    "complement",
    "application",
    "unknown",
)

CONTRACT_PATHS = (
    ITERATION_DIR / "candidate-manifest.json",
    ITERATION_DIR / "data-contract.json",
    ITERATION_DIR / "feature-contract.json",
    ITERATION_DIR / "universe-contract.json",
    ITERATION_DIR / "validation-contract.json",
    ITERATION_DIR / "cost-contract.json",
    ITERATION_DIR / "holdout-contract.json",
    ITERATION_DIR / "modality-role-matrix.json",
    ITERATION_DIR / "model-reuse-decision.json",
    PROMPT_PATH,
    HISTORICAL_LOCK_PATH,
    HISTORICAL_REPORT_PATH,
)
IMPLEMENTATION_PATHS = (
    Path("open_composer/research/pit_semantic_theme_forward.py"),
    Path("tests/test_pit_semantic_theme_forward.py"),
    PACKET_SCHEMA_PATH,
    Path("open_composer/adapters/events/fetcher.py"),
    Path("open_composer/models/event.py"),
    Path("open_composer/feature_packets.py"),
    Path("open_composer/research/llm_backends.py"),
    Path("open_composer/research/pit_semantic_theme_r12.py"),
)

FORWARD_BEHAVIOR = {
    "allowed_sources": ["news.alpaca", "events.sec_filings"],
    "historical_backfill_credit": False,
    "semantic_stock_budget": 0.0,
    "broker_writes": False,
    "order_authority": False,
    "price_can_create_theme": False,
    "max_theme_packets": MAX_THEME_PACKETS,
    "max_theme_members": MAX_THEME_MEMBERS,
    "minimum_confirmed_members": MIN_CONFIRMED_MEMBERS,
    "packet_max_age_days": MAX_PACKET_AGE.days,
    "price_confirmation_feed": PRICE_FEED,
    "price_lookback_days": PRICE_LOOKBACK_DAYS,
    "minimum_price_sessions": MIN_PRICE_SESSIONS,
    "minimum_price": MIN_PRICE,
    "minimum_median_dollar_volume": MIN_MEDIAN_DOLLAR_VOLUME,
    "placebo_seed": PLACEBO_SEED,
    "llm_retry_reuses_bound_source_packets": True,
    "llm_retry_forward_session_credit": False,
}

POSITIVE_TERMS = (
    "accelerat",
    "approval",
    "award",
    "beat",
    "contract",
    "expand",
    "growth",
    "launch",
    "order",
    "outperform",
    "partnership",
    "raise",
    "record",
    "surge",
    "upgrade",
)
NEGATIVE_TERMS = (
    "cut",
    "delay",
    "downgrade",
    "fall",
    "fraud",
    "investigation",
    "lawsuit",
    "miss",
    "recall",
    "risk",
    "slump",
    "warning",
)
MATERIALITY_TERMS = (
    "acquisition",
    "approval",
    "contract",
    "earnings",
    "forecast",
    "guidance",
    "investment",
    "launch",
    "merger",
    "order",
    "partnership",
    "revenue",
)
RELATIONSHIP_TERMS = {
    "supplier": ("supplier", "supplies", "supply agreement"),
    "customer": ("customer", "purchase agreement", "orders from"),
    "equipment": ("equipment", "machinery", "tooling"),
    "material": ("material", "component", "components"),
    "energy": ("energy", "power", "electricity"),
    "infrastructure": ("infrastructure", "data center", "network"),
    "competitor": ("competitor", "competes", "rival"),
    "complement": ("complement", "integrates with", "compatible with"),
    "application": ("application", "deployment", "use case"),
}


class ThemeRelationship(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_entity: str = Field(min_length=1, max_length=16)
    target_entity: str = Field(min_length=1, max_length=16)
    relationship_type: Literal[
        "supplier",
        "customer",
        "equipment",
        "material",
        "energy",
        "infrastructure",
        "competitor",
        "complement",
        "application",
        "unknown",
    ]
    evidence_packet_ids: list[str] = Field(min_length=1, max_length=8)

    @field_validator("source_entity", "target_entity")
    @classmethod
    def normalize_entity(cls, value: str) -> str:
        return value.upper().strip()


class StructuredThemeFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str = Field(pattern=r"^r12theme_[a-f0-9]{16}$")
    entities: list[str] = Field(min_length=1, max_length=MAX_THEME_MEMBERS)
    relationships: list[ThemeRelationship] = Field(default_factory=list, max_length=32)
    direction: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    horizon_sessions: int = Field(ge=3, le=20)
    evidence_packet_ids: list[str] = Field(min_length=1, max_length=8)
    unknown_fields: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("entities")
    @classmethod
    def normalize_entities(cls, values: list[str]) -> list[str]:
        normalized = [value.upper().strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("theme entities must be unique")
        return normalized


class ForwardSourcePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    packet_contract: Literal["pit_semantic_theme_forward_source_v1"]
    packet_id: str = Field(pattern=r"^r12pkt_[a-f0-9]{24}$")
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
            raise ValueError("source packet requires at least one symbol")
        return normalized

    @model_validator(mode="after")
    def validate_provenance(self) -> ForwardSourcePacket:
        self.published_at = _utc(self.published_at)
        self.fetched_at = _utc(self.fetched_at)
        self.first_seen_at = _utc(self.first_seen_at)
        self.visible_at = _utc(self.visible_at)
        if self.fetched_at < self.published_at:
            raise ValueError("fetched_at cannot precede published_at")
        if self.first_seen_at < self.fetched_at:
            raise ValueError("first_seen_at cannot precede fetched_at")
        if self.visible_at < max(self.published_at, self.fetched_at, self.first_seen_at):
            raise ValueError("visible_at violates safe first-seen ordering")
        expected_hash = _canonical_hash(_source_input_payload(self))
        if self.input_hash != expected_hash:
            raise ValueError("source packet input_hash mismatch")
        expected_id = f"r12pkt_{expected_hash[:24]}"
        if self.packet_id != expected_id:
            raise ValueError("source packet packet_id mismatch")
        return self


class PriceConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    session: date | None = None
    status: Literal["ok", "blocked"]
    blocker: str | None = None
    session_count: int = 0
    close: float | None = None
    momentum_1: float | None = None
    momentum_5: float | None = None
    momentum_20: float | None = None
    acceleration: float | None = None
    relative_volume: float | None = None
    qqq_residual_5: float | None = None
    median_dollar_volume_20: float | None = None
    confirmation_score: float = 0.0
    reversal_score: float = 0.0
    crowding_score: float = 0.0
    eligible: bool = False
    confirmed: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()


class ThemeBackend(Protocol):
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ForwardFreezeResult:
    lock_path: Path
    lock_sha256: str
    epoch_id: str


@dataclass(frozen=True)
class ForwardObservationResult:
    status: str
    epoch_id: str
    observation_id: str | None
    observation_path: Path | None
    receipt_path: Path | None
    source_packet_count: int
    selected_theme_count: int
    llm_factor_count: int
    payload: dict[str, Any]


@dataclass(frozen=True)
class ForwardLLMRetryResult:
    status: str
    epoch_id: str
    retry_id: str | None
    retry_path: Path | None
    receipt_path: Path | None
    attempted_packet_count: int
    valid_factor_count: int
    payload: dict[str, Any]


THEME_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "theme_id",
        "entities",
        "relationships",
        "direction",
        "confidence",
        "novelty",
        "horizon_sessions",
        "evidence_packet_ids",
        "unknown_fields",
    ],
    "properties": {
        "theme_id": {"type": "string", "pattern": "^r12theme_[a-f0-9]{16}$"},
        "entities": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_THEME_MEMBERS,
            "uniqueItems": True,
            "items": {"type": "string", "pattern": "^[A-Z][A-Z0-9.-]{0,15}$"},
        },
        "relationships": {
            "type": "array",
            "maxItems": 32,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "source_entity",
                    "target_entity",
                    "relationship_type",
                    "evidence_packet_ids",
                ],
                "properties": {
                    "source_entity": {"type": "string"},
                    "target_entity": {"type": "string"},
                    "relationship_type": {"type": "string", "enum": list(ALLOWED_RELATIONSHIPS)},
                    "evidence_packet_ids": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "items": {"type": "string"},
                    },
                },
            },
        },
        "direction": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "novelty": {"type": "number", "minimum": 0, "maximum": 1},
        "horizon_sessions": {"type": "integer", "minimum": 3, "maximum": 20},
        "evidence_packet_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {"type": "string"},
        },
        "unknown_fields": {
            "type": "array",
            "maxItems": 32,
            "items": {"type": "string"},
        },
    },
}


def forward_lock_binding_paths() -> tuple[Path, ...]:
    return (*CONTRACT_PATHS, *SPEC_PATHS.values(), *IMPLEMENTATION_PATHS)


def freeze_pit_semantic_theme_forward(
    root: Path | None = None,
    *,
    created_at: datetime | None = None,
) -> ForwardFreezeResult:
    base = (root or project_root()).resolve()
    lock_path = base / FORWARD_LOCK_PATH
    if lock_path.exists():
        raise ValueError("R12 forward epoch lock already exists")
    if (base / FORWARD_DATA_DIR).exists() or (base / FORWARD_REPORT_DIR).exists():
        raise ValueError("R12 forward evidence exists before the epoch lock")

    specs = load_and_validate_r12_specs(base)
    historical = _read_json(_regular_in_root(base, base / HISTORICAL_REPORT_PATH))
    if (
        historical.get("iter_id") != ITER_ID
        or historical.get("decision") != "stop_price_paths"
        or historical.get("paper_ready_pass") is not False
    ):
        raise ValueError("R12 historical terminal decision is not the expected stopped state")

    timestamp = _utc(created_at or datetime.now(UTC))
    contracts = [_binding(base / path, base) for path in CONTRACT_PATHS]
    implementations = [_binding(base / path, base) for path in IMPLEMENTATION_PATHS]
    spec_bindings = []
    for candidate_id, path in SPEC_PATHS.items():
        spec_bindings.append(
            {
                **_binding(base / path, base),
                "candidate_id": candidate_id,
                "semantic_sha256": strategy_content_hash(specs[candidate_id]),
            }
        )
    anchor = {
        "schema_version": 1,
        "lock_contract": FORWARD_LOCK_CONTRACT,
        "iter_id": ITER_ID,
        "created_at": timestamp.isoformat(),
        "status": "locked_before_first_persisted_live_collection",
        "contracts": contracts,
        "specs": spec_bindings,
        "implementation": implementations,
        "behavior": FORWARD_BEHAVIOR,
        "first_successful_collector_receipt_defines_epoch_start": True,
        "historical_backfill_credit": False,
        "historical_replay_authorized": False,
        "broker_writes": False,
        "order_authority": False,
    }
    anchor_sha256 = _canonical_hash(anchor)
    lock = {
        **anchor,
        "epoch_anchor_sha256": anchor_sha256,
        "epoch_id": f"r12fwd_{anchor_sha256[:16]}",
    }
    _exclusive_write_json(lock_path, lock)
    return ForwardFreezeResult(
        lock_path=lock_path,
        lock_sha256=_sha256(lock_path),
        epoch_id=str(lock["epoch_id"]),
    )


def verify_pit_semantic_theme_forward_lock(
    root: Path | None = None,
    *,
    observed_at: datetime | None = None,
) -> dict[str, Any]:
    base = (root or project_root()).resolve()
    lock_path = _regular_in_root(base, base / FORWARD_LOCK_PATH)
    lock = _read_json(lock_path)
    anchor = {
        key: value for key, value in lock.items() if key not in {"epoch_anchor_sha256", "epoch_id"}
    }
    expected_anchor = _canonical_hash(anchor)
    if (
        lock.get("schema_version") != 1
        or lock.get("lock_contract") != FORWARD_LOCK_CONTRACT
        or lock.get("iter_id") != ITER_ID
        or lock.get("epoch_anchor_sha256") != expected_anchor
        or lock.get("epoch_id") != f"r12fwd_{expected_anchor[:16]}"
        or lock.get("behavior") != FORWARD_BEHAVIOR
        or lock.get("broker_writes") is not False
        or lock.get("order_authority") is not False
        or lock.get("historical_backfill_credit") is not False
    ):
        raise ValueError("R12 forward epoch lock identity mismatch")
    created_at = _parse_datetime(lock.get("created_at"), "lock created_at")
    now = _utc(observed_at or datetime.now(UTC))
    if created_at > now:
        raise ValueError("R12 forward epoch lock is future-dated")
    for group in ("contracts", "specs", "implementation"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R12 forward lock group is missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    specs = load_and_validate_r12_specs(base)
    locked_specs = {str(row.get("candidate_id")): row for row in lock["specs"]}
    if set(locked_specs) != set(specs):
        raise ValueError("R12 forward lock spec coverage mismatch")
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R12 forward semantic spec changed: {candidate_id}")
    return {
        "lock": lock,
        "lock_path": FORWARD_LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "epoch_id": str(lock["epoch_id"]),
        "created_at": created_at,
    }


def observe_pit_semantic_theme_forward(
    root: Path | None = None,
    *,
    backend_name: str = "openai",
    model: str | None = None,
    news_limit: int = 50,
    feed: str = PRICE_FEED,
    refresh_prices: bool = True,
    observed_at: datetime | None = None,
    events: list[EventRecord] | None = None,
    backend: ThemeBackend | None = None,
    price_frames: dict[str, pd.DataFrame] | None = None,
    price_fetcher: Callable[[str], pd.DataFrame] | None = None,
) -> ForwardObservationResult:
    base = (root or project_root()).resolve()
    started_at = _utc(observed_at or datetime.now(UTC))
    lock_state = verify_pit_semantic_theme_forward_lock(base, observed_at=started_at)
    if feed.lower() != PRICE_FEED:
        raise ValueError("R12 forward price confirmation is locked to the Alpaca IEX feed")
    if not 1 <= news_limit <= 1_000:
        raise ValueError("news_limit must be between 1 and 1000")

    with _forward_writer_lock(base):
        collected = events
        if collected is None:
            collected = fetch_capability_events(
                "alpaca_news",
                base,
                symbols=None,
                offline=False,
                limit=news_limit,
                sort="DESC",
            )
        completed_at = _utc(observed_at or datetime.now(UTC))
        packets = build_forward_source_packets(
            collected,
            epoch_id=lock_state["epoch_id"],
            epoch_started_at=lock_state["created_at"],
            observed_at=completed_at,
        )
        existing_keys = _published_source_version_keys(base)
        new_packets = [
            packet for packet in packets if packet.source_version_key not in existing_keys
        ]
        if not new_packets:
            payload = {
                "status": "no_new_packets",
                "epoch_id": lock_state["epoch_id"],
                "collected_event_count": len(collected),
                "broker_writes": False,
                "order_authority": False,
            }
            _rebuild_forward_projections(base)
            return ForwardObservationResult(
                status="no_new_packets",
                epoch_id=lock_state["epoch_id"],
                observation_id=None,
                observation_path=None,
                receipt_path=None,
                source_packet_count=0,
                selected_theme_count=0,
                llm_factor_count=0,
                payload=payload,
            )

        historical_packets = _published_source_packets(base)
        packet_history = [*historical_packets, *new_packets]
        selected_packets = _select_theme_packets(new_packets, completed_at)
        attention = _attention_acceleration(packet_history, completed_at)
        selected_symbols = sorted(
            {
                symbol
                for packet in selected_packets
                for symbol in _rank_packet_symbols(packet, attention)
                if _is_equity_symbol(symbol)
            }
        )
        decision_session = latest_completed_us_equity_session(completed_at)
        price_features, price_inputs, price_errors = _load_price_confirmations(
            base,
            symbols=selected_symbols,
            decision_session=decision_session,
            observed_at=completed_at,
            feed=feed.lower(),
            refresh_prices=refresh_prices,
            price_frames=price_frames,
            price_fetcher=price_fetcher,
        )
        eligible_symbols = {
            symbol
            for symbol, feature in price_features.items()
            if feature.status == "ok" and feature.eligible
        }
        deterministic_themes = [
            _deterministic_theme(
                packet,
                price_features,
                attention,
                eligible_symbols=eligible_symbols,
            )
            for packet in selected_packets
        ]
        llm_allowed_symbols = {
            packet.packet_id: _rank_packet_symbols(
                packet,
                attention,
                eligible_symbols=eligible_symbols,
            )
            for packet in selected_packets
        }

        (
            selected_model,
            selected_backend,
            prompt,
            prompt_hash,
            model_parameters_hash,
        ) = _llm_runtime(
            base,
            backend_name=backend_name,
            model=model,
            backend=backend,
        )
        llm_results = _materialize_llm_themes(
            selected_packets,
            backend=selected_backend,
            backend_name=backend_name,
            model=selected_model,
            prompt=prompt,
            prompt_hash=prompt_hash,
            model_parameters_hash=model_parameters_hash,
            allowed_symbols=llm_allowed_symbols,
        )
        materialized_at = _utc(observed_at or datetime.now(UTC))
        event_rows = _event_feature_rows(
            deterministic_themes,
            packets={packet.packet_id: packet for packet in selected_packets},
            materialized_at=materialized_at,
            epoch_id=lock_state["epoch_id"],
        )
        theme_rows = _theme_feature_rows(
            llm_results,
            packets={packet.packet_id: packet for packet in selected_packets},
            price_features=price_features,
            materialized_at=materialized_at,
            epoch_id=lock_state["epoch_id"],
            prompt_hash=prompt_hash,
        )
        placebo_rows, placebo_mapping = _placebo_feature_rows(
            theme_rows,
            decision_session=decision_session,
            epoch_id=lock_state["epoch_id"],
        )

        d01 = _load_d01_snapshot(base, decision_session)
        roles = _candidate_role_outputs(
            d01=d01,
            deterministic_themes=deterministic_themes,
            llm_results=llm_results,
            theme_rows=theme_rows,
            placebo_rows=placebo_rows,
        )
        packet_manifest_hash = _canonical_hash(
            [packet.model_dump(mode="json") for packet in new_packets]
        )
        observation_id = f"{decision_session:%Y%m%d}-{packet_manifest_hash[:12]}"
        final_dir = base / FORWARD_DATA_DIR / "observations" / observation_id
        if final_dir.exists():
            receipt = _verify_observation_receipt(base, final_dir / "receipt.json", lock_state)
            _rebuild_forward_projections(base)
            return _result_from_receipt(final_dir, receipt)

        account_reconciliation = _account_reconciliation(base, d01, decision_session)
        observation = {
            "schema_version": 1,
            "observation_contract": OBSERVATION_CONTRACT,
            "iter_id": ITER_ID,
            "epoch_id": lock_state["epoch_id"],
            "observation_id": observation_id,
            "collected_at": materialized_at.isoformat(),
            "decision_session": decision_session.isoformat(),
            "action_session": next_us_equity_session(decision_session).isoformat(),
            "source_packet_count": len(new_packets),
            "selected_theme_count": len(selected_packets),
            "llm_valid_factor_count": len(theme_rows),
            "event_feature_count": len(event_rows),
            "placebo_feature_count": len(placebo_rows),
            "price_confirmation": {
                "feed": feed.lower(),
                "source": "alpaca",
                "symbol_count": len(price_features),
                "errors": price_errors,
                "features": {
                    symbol: row.model_dump(mode="json")
                    for symbol, row in sorted(price_features.items())
                },
            },
            "deterministic_themes": deterministic_themes,
            "llm_materialization": {
                "backend": backend_name,
                "model": selected_model,
                "prompt_path": PROMPT_PATH.as_posix(),
                "prompt_hash": prompt_hash,
                "model_parameters_hash": model_parameters_hash,
                "results": llm_results,
            },
            "placebo": {
                "seed": PLACEBO_SEED,
                "operation": "per_decision_session_theme_to_symbol_permutation",
                "mapping": placebo_mapping,
                "mapping_sha256": _canonical_hash(placebo_mapping),
            },
            "candidate_roles": roles,
            "d01_target_snapshot": d01,
            "account_reconciliation": account_reconciliation,
            "workflow_pass": True,
            "research_pass": False,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "semantic_stock_budget": 0.0,
            "observation_only": True,
            "broker_writes": False,
            "order_authority": False,
            "limitations": [
                "one forward observation cannot establish semantic alpha",
                "all semantic candidates retain zero stock capital",
                "trained ETF rankers remain stopped and fall back to D01",
                "Alpaca News first-seen time begins at local collection, not provider publication",
                "IEX confirmation is current observation data and not SIP historical evidence",
            ],
        }
        receipt = _publish_observation(
            base,
            final_dir=final_dir,
            lock_state=lock_state,
            observation=observation,
            source_packets=new_packets,
            event_rows=event_rows,
            theme_rows=theme_rows,
            placebo_rows=placebo_rows,
            price_inputs=price_inputs,
            d01=d01,
        )
        _rebuild_forward_projections(base)
        return _result_from_receipt(final_dir, receipt)


def retry_pit_semantic_theme_forward_llm(
    root: Path | None = None,
    *,
    backend_name: str = "openai",
    model: str | None = None,
    max_packets: int = MAX_THEME_PACKETS,
    observed_at: datetime | None = None,
    backend: ThemeBackend | None = None,
) -> ForwardLLMRetryResult:
    """Retry failed LLM materialization without recollecting or re-crediting source packets."""
    base = (root or project_root()).resolve()
    materialized_at = _utc(observed_at or datetime.now(UTC))
    lock_state = verify_pit_semantic_theme_forward_lock(base, observed_at=materialized_at)
    if not 1 <= max_packets <= 100:
        raise ValueError("max_packets must be between 1 and 100")

    with _forward_writer_lock(base):
        (
            selected_model,
            selected_backend,
            prompt,
            prompt_hash,
            model_parameters_hash,
        ) = _llm_runtime(
            base,
            backend_name=backend_name,
            model=model,
            backend=backend,
        )
        contexts = _pending_llm_retry_contexts(
            base,
            lock_state=lock_state,
            model_parameters_hash=model_parameters_hash,
        )[:max_packets]
        if not contexts:
            _rebuild_llm_retry_projections(base, lock_state)
            return ForwardLLMRetryResult(
                status="no_pending_llm_packets",
                epoch_id=lock_state["epoch_id"],
                retry_id=None,
                retry_path=None,
                receipt_path=None,
                attempted_packet_count=0,
                valid_factor_count=0,
                payload={
                    "status": "no_pending_llm_packets",
                    "epoch_id": lock_state["epoch_id"],
                    "forward_session_credit": False,
                    "broker_writes": False,
                    "order_authority": False,
                },
            )

        packets = [context["packet"] for context in contexts]
        allowed_symbols = {
            context["packet"].packet_id: context["allowed_entities"] for context in contexts
        }
        results = _materialize_llm_themes(
            packets,
            backend=selected_backend,
            backend_name=backend_name,
            model=selected_model,
            prompt=prompt,
            prompt_hash=prompt_hash,
            model_parameters_hash=model_parameters_hash,
            allowed_symbols=allowed_symbols,
        )
        context_by_packet = {context["packet"].packet_id: context for context in contexts}
        decorated_results: list[dict[str, Any]] = []
        theme_rows: list[dict[str, Any]] = []
        for result in results:
            context = context_by_packet[str(result["packet_id"])]
            decorated = {
                **result,
                "source_observation_id": context["source_observation_id"],
                "source_decision_session": context["decision_session"],
                "source_receipt_sha256": context["receipt_binding"]["sha256"],
                "attempt_number": context["prior_attempt_count"] + 1,
            }
            decorated_results.append(decorated)
            rows = _theme_feature_rows(
                [decorated],
                packets={context["packet"].packet_id: context["packet"]},
                price_features=context["price_features"],
                materialized_at=materialized_at,
                epoch_id=lock_state["epoch_id"],
                prompt_hash=prompt_hash,
            )
            for row in rows:
                row["dedupe_key"] = f"{row['dedupe_key']}:retry:{model_parameters_hash[:12]}"
                row["materialization_kind"] = "llm_retry"
                row["source_observation_id"] = context["source_observation_id"]
            theme_rows.extend(rows)

        source_evidence = _llm_retry_source_evidence(contexts)
        retry_identity = {
            "epoch_id": lock_state["epoch_id"],
            "materialized_at": materialized_at.isoformat(),
            "model_parameters_hash": model_parameters_hash,
            "packets": [
                {
                    "packet_id": context["packet"].packet_id,
                    "input_hash": context["packet"].input_hash,
                    "source_observation_id": context["source_observation_id"],
                    "attempt_number": context["prior_attempt_count"] + 1,
                }
                for context in contexts
            ],
        }
        retry_id = f"r12llm_{materialized_at:%Y%m%dT%H%M%SZ}_{_canonical_hash(retry_identity)[:12]}"
        final_dir = base / FORWARD_DATA_DIR / "llm-retries" / retry_id
        if final_dir.exists():
            receipt = _verify_llm_retry_receipt(base, final_dir / "receipt.json", lock_state)
            _rebuild_llm_retry_projections(base, lock_state)
            return _llm_retry_result_from_receipt(final_dir, receipt)

        payload = {
            "schema_version": 1,
            "retry_contract": LLM_RETRY_CONTRACT,
            "iter_id": ITER_ID,
            "epoch_id": lock_state["epoch_id"],
            "retry_id": retry_id,
            "materialized_at": materialized_at.isoformat(),
            "backend": backend_name,
            "model": selected_model,
            "prompt_path": PROMPT_PATH.as_posix(),
            "prompt_hash": prompt_hash,
            "model_parameters_hash": model_parameters_hash,
            "attempted_packet_count": len(decorated_results),
            "valid_factor_count": len(theme_rows),
            "results": decorated_results,
            "source_evidence": source_evidence,
            "forward_session_credit": False,
            "source_packet_credit": 0,
            "semantic_stock_budget": 0.0,
            "observation_only": True,
            "broker_writes": False,
            "order_authority": False,
            "limitations": [
                "retry reuses immutable source packets and does not change first_seen_at",
                "retry does not create a new forward trading session",
                "retry factors retain zero stock capital until matched forward evidence passes",
            ],
        }
        receipt = _publish_llm_retry(
            base,
            final_dir=final_dir,
            lock_state=lock_state,
            payload=payload,
            theme_rows=theme_rows,
            source_evidence=source_evidence,
        )
        _rebuild_llm_retry_projections(base, lock_state)
        return _llm_retry_result_from_receipt(final_dir, receipt)


def build_forward_source_packets(
    events: Iterable[EventRecord],
    *,
    epoch_id: str,
    epoch_started_at: datetime,
    observed_at: datetime,
) -> list[ForwardSourcePacket]:
    epoch_start = _utc(epoch_started_at)
    observed = _utc(observed_at)
    grouped: dict[str, list[EventRecord]] = {}
    for event in events:
        if event.source != "alpaca_news" or event.acquisition_mode != "live_api_forward_only":
            raise ValueError("R12 forward collection accepts only live forward Alpaca News records")
        fetched_at = _utc(event.fetched_at)
        visible_at = _utc(event.visible_at or event.fetched_at)
        if fetched_at < epoch_start or visible_at < epoch_start:
            raise ValueError("R12 forward event predates the locked collector epoch")
        if visible_at > observed + timedelta(minutes=1):
            raise ValueError("R12 forward event is future-dated")
        provider_id = str(event.raw.get("provider_id") or "").strip()
        if not provider_id or not event.version_id:
            raise ValueError("R12 Alpaca News record lacks provider version identity")
        key = f"news.alpaca:{provider_id}:{event.version_id}"
        grouped.setdefault(key, []).append(event)

    packets: list[ForwardSourcePacket] = []
    for source_version_key, rows in sorted(grouped.items()):
        first = sorted(rows, key=lambda row: (row.symbol, row.id))[0]
        provider_symbols = {
            str(symbol).upper().strip()
            for row in rows
            for symbol in row.raw.get("provider_symbols", [])
            if isinstance(symbol, str) and symbol.strip()
        }
        provider_symbols.update(row.symbol for row in rows if row.symbol != "MARKET")
        if not provider_symbols:
            continue
        source_payload = {
            "source": "news.alpaca",
            "provider_article_id": str(first.raw["provider_id"]),
            "version_id": str(first.version_id),
            "symbols": sorted(provider_symbols),
            "title": first.title.strip(),
            "summary": first.summary.strip(),
            "source_url": first.url,
            "published_at": _utc(first.published_at).isoformat(),
            "rights_scope": first.rights_scope,
            "revision_id": first.revision_id,
        }
        input_hash = _canonical_hash(source_payload)
        fetched_at = min(_utc(row.fetched_at) for row in rows)
        first_seen_at = min(_utc(row.first_seen_at or row.fetched_at) for row in rows)
        visible_at = max(_utc(row.visible_at or row.fetched_at) for row in rows)
        packets.append(
            ForwardSourcePacket(
                schema_version=1,
                packet_contract=SOURCE_PACKET_CONTRACT,
                packet_id=f"r12pkt_{input_hash[:24]}",
                epoch_id=epoch_id,
                source="news.alpaca",
                source_version_key=source_version_key,
                provider_article_id=str(first.raw["provider_id"]),
                version_id=str(first.version_id),
                symbols=sorted(provider_symbols),
                title=first.title.strip() or "Untitled Alpaca News record",
                summary=first.summary.strip(),
                source_url=first.url,
                published_at=first.published_at,
                fetched_at=fetched_at,
                first_seen_at=first_seen_at,
                visible_at=visible_at,
                input_hash=input_hash,
                rights_scope=first.rights_scope,
                revision_id=first.revision_id,
                acquisition_mode="live_api_forward_only",
                dedupe_key=source_version_key,
            )
        )
    return sorted(packets, key=lambda packet: (packet.published_at, packet.packet_id))


def _select_theme_packets(
    packets: list[ForwardSourcePacket], observed_at: datetime
) -> list[ForwardSourcePacket]:
    lower = _utc(observed_at) - MAX_PACKET_AGE
    eligible = [packet for packet in packets if packet.published_at >= lower]
    return sorted(
        eligible,
        key=lambda packet: (
            -_event_materiality(packet),
            -len(packet.symbols),
            -packet.published_at.timestamp(),
            packet.packet_id,
        ),
    )[:MAX_THEME_PACKETS]


def _event_materiality(packet: ForwardSourcePacket) -> float:
    text = f"{packet.title} {packet.summary}".lower()
    hits = sum(term in text for term in MATERIALITY_TERMS)
    score = 0.25 + (0.16 * hits) + (0.05 * min(len(packet.symbols), 5))
    return round(min(score, 1.0), 6)


def _deterministic_theme(
    packet: ForwardSourcePacket,
    price_features: dict[str, PriceConfirmation],
    attention: dict[str, float],
    *,
    eligible_symbols: set[str],
) -> dict[str, Any]:
    entities = _rank_packet_symbols(packet, attention, eligible_symbols=eligible_symbols)
    relation_type = _relationship_type(f"{packet.title} {packet.summary}")
    relationships = []
    if relation_type != "unknown" and len(entities) >= 2:
        relationships = [
            {
                "source_entity": entities[0],
                "target_entity": target,
                "relationship_type": relation_type,
                "evidence_packet_ids": [packet.packet_id],
            }
            for target in entities[1:]
        ]
    confirmations = [
        price_features[symbol]
        for symbol in entities
        if symbol in price_features and price_features[symbol].confirmed
    ]
    eligible = [
        price_features[symbol]
        for symbol in entities
        if symbol in price_features and price_features[symbol].eligible
    ]
    materiality = _event_materiality(packet)
    mean_reversal = _mean(row.reversal_score for row in eligible)
    mean_crowding = _mean(row.crowding_score for row in eligible)
    if len(confirmations) >= MIN_CONFIRMED_MEMBERS:
        state = "cooling" if max(mean_reversal, mean_crowding) >= 0.7 else "active"
    elif len(eligible) >= MIN_CONFIRMED_MEMBERS:
        state = "confirmed"
    elif entities:
        state = "mapped"
    else:
        state = "seeded"
    direction = _lexical_direction(f"{packet.title} {packet.summary}")
    return {
        "theme_id": f"r12theme_{packet.input_hash[:16]}",
        "packet_id": packet.packet_id,
        "entities": entities,
        "relationships": relationships,
        "direction": direction,
        "event_materiality": materiality,
        "relationship_support": len(relationships),
        "attention_acceleration": round(
            max((attention.get(item, 0.0) for item in entities), default=0.0), 6
        ),
        "confirmed_members": sorted(row.symbol for row in confirmations),
        "eligible_members": sorted(row.symbol for row in eligible),
        "breadth": round(len(confirmations) / len(entities), 6) if entities else 0.0,
        "state": state,
        "horizon_sessions": _deterministic_horizon(packet),
        "price_created_theme": False,
    }


def _llm_runtime(
    root: Path,
    *,
    backend_name: str,
    model: str | None,
    backend: ThemeBackend | None,
) -> tuple[str, ThemeBackend, str, str, str]:
    selected_model = model or default_openai_model()
    selected_backend = backend or get_backend(backend_name)
    prompt_path = _regular_in_root(root, root / PROMPT_PATH)
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt_hash = _sha256(prompt_path)
    model_parameters_hash = _canonical_hash(
        {
            "backend": backend_name,
            "model": selected_model,
            "output_schema_sha256": _canonical_hash(THEME_OUTPUT_SCHEMA),
            "prompt_hash": prompt_hash,
            "live_llm_in_order_path": False,
        }
    )
    return selected_model, selected_backend, prompt, prompt_hash, model_parameters_hash


def _llm_input_payload(
    packet: ForwardSourcePacket,
    entities: list[str],
) -> dict[str, Any]:
    return {
        "required_theme_id": f"r12theme_{packet.input_hash[:16]}",
        "allowed_entities": entities,
        "allowed_relationship_types": list(ALLOWED_RELATIONSHIPS),
        "source_packet": {
            "packet_id": packet.packet_id,
            "source": packet.source,
            "source_url": packet.source_url,
            "published_at": packet.published_at.isoformat(),
            "visible_at": packet.visible_at.isoformat(),
            "title": packet.title,
            "summary": packet.summary,
            "symbols": entities,
        },
    }


def _materialize_llm_themes(
    packets: list[ForwardSourcePacket],
    *,
    backend: ThemeBackend,
    backend_name: str,
    model: str,
    prompt: str,
    prompt_hash: str,
    model_parameters_hash: str,
    allowed_symbols: dict[str, list[str]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for packet in packets:
        entities = allowed_symbols.get(packet.packet_id, [])[:MAX_THEME_MEMBERS]
        required_theme_id = f"r12theme_{packet.input_hash[:16]}"
        input_payload = _llm_input_payload(packet, entities)
        base = {
            "packet_id": packet.packet_id,
            "input_hash": packet.input_hash,
            "input_payload_sha256": _canonical_hash(input_payload),
            "allowed_entities": entities,
            "prompt_hash": prompt_hash,
            "model": model,
            "backend": backend_name,
            "model_parameters_hash": model_parameters_hash,
            "required_theme_id": required_theme_id,
        }
        if not entities:
            results.append(
                {
                    **base,
                    "status": "fallback",
                    "structured_output": None,
                    "structured_output_hash": None,
                    "fallback_candidate_id": "R12D02_then_R12D01",
                    "error": "no_eligible_us_equity_members",
                }
            )
            continue
        try:
            raw = backend.infer(
                model=model,
                prompt=prompt,
                input_payload=input_payload,
                output_schema=THEME_OUTPUT_SCHEMA,
            )
            factor = StructuredThemeFactor.model_validate(raw)
            _validate_llm_factor_binding(factor, packet, entities, required_theme_id)
            payload = factor.model_dump(mode="json")
            results.append(
                {
                    **base,
                    "status": "valid",
                    "structured_output": payload,
                    "structured_output_hash": _canonical_hash(payload),
                    "fallback_candidate_id": None,
                    "error": None,
                }
            )
        except Exception as exc:
            results.append(
                {
                    **base,
                    "status": "fallback",
                    "structured_output": None,
                    "structured_output_hash": None,
                    "fallback_candidate_id": "R12D02_then_R12D01",
                    "error": _safe_error(exc),
                }
            )
    return results


def _validate_llm_factor_binding(
    factor: StructuredThemeFactor,
    packet: ForwardSourcePacket,
    allowed_entities: list[str],
    required_theme_id: str,
) -> None:
    allowed = set(allowed_entities)
    if factor.theme_id != required_theme_id:
        raise ValueError("LLM theme_id is not bound to the source packet")
    if not set(factor.entities).issubset(allowed):
        raise ValueError("LLM factor introduced an entity absent from source evidence")
    if set(factor.evidence_packet_ids) != {packet.packet_id}:
        raise ValueError("LLM factor evidence_packet_ids are not exactly source-bound")
    for relationship in factor.relationships:
        if relationship.source_entity not in allowed or relationship.target_entity not in allowed:
            raise ValueError("LLM relationship introduced an unbound entity")
        if set(relationship.evidence_packet_ids) != {packet.packet_id}:
            raise ValueError("LLM relationship lacks exact packet evidence")


def _event_feature_rows(
    themes: list[dict[str, Any]],
    *,
    packets: dict[str, ForwardSourcePacket],
    materialized_at: datetime,
    epoch_id: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    deterministic_hash = _canonical_hash(
        {"contract": "r12_deterministic_event_state_v1", "behavior": FORWARD_BEHAVIOR}
    )
    for theme in themes:
        packet = packets[str(theme["packet_id"])]
        for symbol in theme["entities"]:
            row = FeaturePacketRow(
                timestamp=materialized_at,
                published_at=packet.published_at,
                fetched_at=packet.fetched_at,
                visible_at=max(packet.visible_at, materialized_at),
                source="news.alpaca:deterministic_theme",
                symbol=symbol,
                dedupe_key=f"R12D02:{epoch_id}:{theme['theme_id']}:{symbol}",
                schema_version=FEATURE_SCHEMA_VERSION,
                model="source_bound_event_relationship_state_machine_v1",
                input_hash=packet.input_hash,
                prompt_hash=deterministic_hash,
                summary=f"Deterministic event state for {theme['theme_id']}",
                features={
                    "event_materiality": float(theme["event_materiality"]),
                    "relationship_support": int(theme["relationship_support"]),
                    "attention_acceleration": float(theme["attention_acceleration"]),
                    "theme_direction": float(theme["direction"]),
                    "price_confirmation_5": 0.0,
                },
            ).model_dump(mode="json", exclude_none=True)
            row.update(
                {
                    "candidate_id": "R12D02",
                    "epoch_id": epoch_id,
                    "packet_id": packet.packet_id,
                    "theme_id": theme["theme_id"],
                    "theme_state": theme["state"],
                    "evidence_packet_ids": [packet.packet_id],
                    "semantic_stock_budget": 0.0,
                    "broker_writes": False,
                }
            )
            rows.append(row)
    return rows


def _theme_feature_rows(
    results: list[dict[str, Any]],
    *,
    packets: dict[str, ForwardSourcePacket],
    price_features: dict[str, PriceConfirmation],
    materialized_at: datetime,
    epoch_id: str,
    prompt_hash: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in results:
        if result["status"] != "valid":
            continue
        factor = StructuredThemeFactor.model_validate(result["structured_output"])
        packet = packets[str(result["packet_id"])]
        for symbol in factor.entities:
            price = price_features.get(symbol)
            confirmation = price.confirmation_score if price is not None else 0.0
            combined = factor.direction * factor.confidence * (0.5 + 0.5 * factor.novelty)
            row = FeaturePacketRow(
                timestamp=materialized_at,
                published_at=packet.published_at,
                fetched_at=packet.fetched_at,
                visible_at=max(packet.visible_at, materialized_at),
                source="news.alpaca:openai_structured_theme",
                symbol=symbol,
                dedupe_key=f"R12L01:{epoch_id}:{factor.theme_id}:{symbol}",
                schema_version=FEATURE_SCHEMA_VERSION,
                model=str(result["model"]),
                input_hash=packet.input_hash,
                prompt_hash=prompt_hash,
                summary=f"Structured forward theme factor for {factor.theme_id}",
                features={
                    "theme_direction": float(factor.direction),
                    "confidence": float(factor.confidence),
                    "novelty": float(factor.novelty),
                    "horizon_sessions": int(factor.horizon_sessions),
                    "price_confirmation_score": float(confirmation),
                    "combined_observation_score": float(combined * (1.0 + confirmation)),
                },
            ).model_dump(mode="json", exclude_none=True)
            row.update(
                {
                    "candidate_ids": ["R12L01", "R12C01"],
                    "epoch_id": epoch_id,
                    "packet_id": packet.packet_id,
                    "theme_id": factor.theme_id,
                    "entities": factor.entities,
                    "relationships": [
                        relationship.model_dump(mode="json")
                        for relationship in factor.relationships
                    ],
                    "evidence_packet_ids": factor.evidence_packet_ids,
                    "structured_output_hash": result["structured_output_hash"],
                    "model_parameters_hash": result["model_parameters_hash"],
                    "semantic_stock_budget": 0.0,
                    "live_llm_in_order_path": False,
                    "broker_writes": False,
                }
            )
            rows.append(row)
    return rows


def _placebo_feature_rows(
    theme_rows: list[dict[str, Any]],
    *,
    decision_session: date,
    epoch_id: str,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    by_theme: dict[str, list[dict[str, Any]]] = {}
    for row in theme_rows:
        by_theme.setdefault(str(row["theme_id"]), []).append(row)
    output: list[dict[str, Any]] = []
    mapping: list[dict[str, str]] = []
    for theme_id, rows in sorted(by_theme.items()):
        source_symbols = sorted(str(row["symbol"]) for row in rows)
        shuffled = sorted(
            source_symbols,
            key=lambda symbol: hashlib.sha256(
                f"{PLACEBO_SEED}|{decision_session}|{theme_id}|{symbol}".encode("ascii")
            ).hexdigest(),
        )
        if len(shuffled) > 1 and shuffled == source_symbols:
            shuffled = shuffled[1:] + shuffled[:1]
        symbol_map = dict(zip(source_symbols, shuffled, strict=True))
        for row in rows:
            source_symbol = str(row["symbol"])
            target_symbol = symbol_map[source_symbol]
            clone = json.loads(json.dumps(row))
            clone["symbol"] = target_symbol
            clone["source"] = "news.alpaca:structured_theme_placebo"
            clone["dedupe_key"] = f"R12P01:{epoch_id}:{theme_id}:{target_symbol}"
            clone["candidate_ids"] = ["R12P01"]
            clone["placebo_source_symbol"] = source_symbol
            output.append(clone)
            mapping.append(
                {
                    "theme_id": theme_id,
                    "source_symbol": source_symbol,
                    "placebo_symbol": target_symbol,
                }
            )
    return output, mapping


def _load_price_confirmations(
    root: Path,
    *,
    symbols: list[str],
    decision_session: date,
    observed_at: datetime,
    feed: str,
    refresh_prices: bool,
    price_frames: dict[str, pd.DataFrame] | None,
    price_fetcher: Callable[[str], pd.DataFrame] | None,
) -> tuple[dict[str, PriceConfirmation], list[dict[str, Any]], dict[str, str]]:
    requested = sorted(set(symbols) | ({"QQQ"} if symbols else set()))
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for symbol in requested:
        try:
            if price_frames is not None:
                if symbol not in price_frames:
                    raise ValueError("injected price frame is missing")
                frame = price_frames[symbol].copy()
            elif price_fetcher is not None:
                frame = price_fetcher(symbol).copy()
            else:
                frame = fetch_alpaca_bars(
                    root=root,
                    symbol=symbol,
                    timeframe="daily",
                    start=observed_at - timedelta(days=PRICE_LOOKBACK_DAYS),
                    end=observed_at,
                    feed=feed,
                    use_cache=not refresh_prices,
                )
            frames[symbol] = _price_frame_through_session(frame, decision_session)
        except Exception as exc:
            errors[symbol] = _safe_error(exc)

    qqq_momentum = None
    if "QQQ" in frames and len(frames["QQQ"]) >= 21:
        qqq_momentum = _return_over(frames["QQQ"]["close"], 5)
    features: dict[str, PriceConfirmation] = {}
    price_inputs: list[dict[str, Any]] = []
    for symbol in requested:
        frame = frames.get(symbol)
        if frame is None:
            features[symbol] = PriceConfirmation(
                symbol=symbol,
                status="blocked",
                blocker=errors.get(symbol, "missing_price_frame"),
            )
            continue
        for row in frame.tail(65).to_dict(orient="records"):
            price_inputs.append(
                {
                    "symbol": symbol,
                    "timestamp": pd.Timestamp(row["timestamp"]).isoformat(),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row["volume"]),
                    "feed": feed,
                }
            )
        features[symbol] = _price_confirmation(symbol, frame, qqq_momentum)
    return features, price_inputs, errors


def _price_frame_through_session(frame: pd.DataFrame, session: date) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if not required.issubset(frame.columns):
        raise ValueError("price frame lacks required OHLCV columns")
    selected = frame[list(required)].copy()
    selected["timestamp"] = pd.to_datetime(selected["timestamp"], utc=True, errors="raise")
    selected = selected.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    selected = selected[selected["timestamp"].dt.date <= session]
    for column in ("open", "high", "low", "close", "volume"):
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    if (
        selected.empty
        or not selected[["open", "high", "low", "close", "volume"]].notna().all().all()
    ):
        raise ValueError("price frame is empty or nonfinite")
    if (selected[["open", "high", "low", "close"]] <= 0).any().any() or (
        selected["volume"] < 0
    ).any():
        raise ValueError("price frame contains invalid values")
    return selected.reset_index(drop=True)


def _price_confirmation(
    symbol: str, frame: pd.DataFrame, qqq_momentum_5: float | None
) -> PriceConfirmation:
    session_count = len(frame)
    session = frame["timestamp"].iloc[-1].date()
    if session_count < MIN_PRICE_SESSIONS:
        return PriceConfirmation(
            symbol=symbol,
            session=session,
            status="blocked",
            blocker="fewer_than_60_sessions",
            session_count=session_count,
        )
    if qqq_momentum_5 is None:
        return PriceConfirmation(
            symbol=symbol,
            session=session,
            status="blocked",
            blocker="QQQ_reference_missing_or_short",
            session_count=session_count,
        )
    close = frame["close"].astype(float)
    volume = frame["volume"].astype(float)
    momentum_1 = _return_over(close, 1)
    momentum_5 = _return_over(close, 5)
    momentum_20 = _return_over(close, 20)
    acceleration = momentum_5 - (momentum_20 / 4.0)
    prior_volume = volume.iloc[-21:-1]
    relative_volume = float(volume.iloc[-1] / max(float(prior_volume.mean()), 1.0))
    dollar_volume = (close * volume).iloc[-20:]
    median_dollar_volume = float(dollar_volume.median())
    residual = momentum_5 - qqq_momentum_5
    eligible = bool(
        close.iloc[-1] >= MIN_PRICE and median_dollar_volume >= MIN_MEDIAN_DOLLAR_VOLUME
    )
    confirmation_score = (
        0.35 * math.tanh(8.0 * momentum_5)
        + 0.25 * math.tanh(12.0 * acceleration)
        + 0.20 * max(-1.0, min(1.0, (relative_volume - 1.0) / 2.0))
        + 0.20 * math.tanh(8.0 * residual)
    )
    reversal = max(0.0, min(1.0, (-momentum_1 - 0.02) / 0.08))
    crowding = max(
        0.0,
        min(
            1.0,
            0.5 * max(0.0, (relative_volume - 3.0) / 3.0)
            + 0.5 * max(0.0, (momentum_5 - 0.25) / 0.25),
        ),
    )
    confirmed = bool(
        eligible
        and momentum_5 > 0
        and acceleration > 0
        and residual > 0
        and relative_volume >= 0.8
        and confirmation_score > 0.1
    )
    return PriceConfirmation(
        symbol=symbol,
        session=session,
        status="ok",
        session_count=session_count,
        close=float(close.iloc[-1]),
        momentum_1=momentum_1,
        momentum_5=momentum_5,
        momentum_20=momentum_20,
        acceleration=acceleration,
        relative_volume=relative_volume,
        qqq_residual_5=residual,
        median_dollar_volume_20=median_dollar_volume,
        confirmation_score=confirmation_score,
        reversal_score=reversal,
        crowding_score=crowding,
        eligible=eligible,
        confirmed=confirmed,
    )


def _load_d01_snapshot(root: Path, decision_session: date) -> dict[str, Any]:
    path = root / D01_TARGET_PATH
    if not path.exists():
        return {
            "status": "blocked",
            "blocker": "D01_target_artifact_missing",
            "target_sha256": None,
            "weights": {},
        }
    payload = _read_json(_regular_in_root(root, path))
    parity = payload.get("parity_check") or {}
    rows = payload.get("target_weights") or []
    selected = [
        row for row in rows if str(row.get("signal_session")) == decision_session.isoformat()
    ]
    if parity.get("status") != "pass" or not selected:
        return {
            "status": "blocked",
            "blocker": "D01_target_artifact_stale_or_parity_failed",
            "target_sha256": None,
            "weights": {},
            "artifact": _binding(path, root),
        }
    action_sessions = {str(row.get("rebalance_session")) for row in selected}
    if action_sessions != {next_us_equity_session(decision_session).isoformat()}:
        raise ValueError("R12 D01 target action session is not the next equity session")
    weights = {
        str(row["symbol"]).upper(): float(row.get("target_weight") or 0.0) for row in selected
    }
    if any(not math.isfinite(value) or value < 0 for value in weights.values()):
        raise ValueError("R12 D01 target contains invalid weights")
    selected_rows = [row for row in selected if float(row.get("target_weight") or 0.0) > 0]
    return {
        "status": "ok",
        "artifact": _binding(path, root),
        "acquisition_tier": payload.get("acquisition_tier"),
        "route_label": payload.get("route_label"),
        "decision_session": decision_session.isoformat(),
        "action_session": next_us_equity_session(decision_session).isoformat(),
        "state": str(selected_rows[0].get("state")) if selected_rows else "cash",
        "weights": dict(sorted(weights.items())),
        "gross_exposure": math.fsum(weights.values()),
        "target_sha256": _canonical_hash(dict(sorted(weights.items()))),
        "parity_status": "pass",
        "observation_only": True,
        "broker_writes": False,
    }


def _candidate_role_outputs(
    *,
    d01: dict[str, Any],
    deterministic_themes: list[dict[str, Any]],
    llm_results: list[dict[str, Any]],
    theme_rows: list[dict[str, Any]],
    placebo_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    target_hash = d01.get("target_sha256")
    llm_valid = sum(result["status"] == "valid" for result in llm_results)
    active = sum(theme["state"] == "active" for theme in deterministic_themes)
    roles = [
        ("R12D01", "deterministic_high_beta_execution_baseline", "tier0_observation", "D01"),
        ("R12D02", "deterministic_semantic_event_theme_state", "shadow", "R12D01"),
        ("R12M01", "fold_local_ridge_etf_route_ranker", "stopped", "R12D01"),
        ("R12M02", "fold_local_lightgbm_complexity_challenger", "stopped", "R12D01"),
        (
            "R12L01",
            "structured_llm_theme_factor",
            "shadow" if llm_valid else "fallback",
            "R12D02_then_R12D01",
        ),
        (
            "R12C01",
            "ml_core_plus_structured_semantic_theme",
            "shadow" if llm_valid else "fallback",
            "R12D01",
        ),
        ("R12F01", "missing_modality_exact_m01_fallback", "exact_fallback", "R12D01"),
        ("R12P01", "shuffled_semantic_mapping_placebo", "placebo", "R12D01"),
    ]
    output = []
    for candidate_id, role, status, fallback in roles:
        output.append(
            {
                "candidate_id": candidate_id,
                "role": role,
                "status": status if d01.get("status") == "ok" else "blocked_by_D01_target",
                "fallback_candidate_id": fallback,
                "target_source_candidate_id": "R12D01",
                "target_sha256": target_hash,
                "semantic_stock_budget": 0.0,
                "active_deterministic_theme_count": active if candidate_id == "R12D02" else 0,
                "valid_llm_theme_count": llm_valid if candidate_id in {"R12L01", "R12C01"} else 0,
                "feature_row_count": (
                    len(placebo_rows)
                    if candidate_id == "R12P01"
                    else len(theme_rows)
                    if candidate_id in {"R12L01", "R12C01"}
                    else 0
                ),
                "observation_only": True,
                "broker_writes": False,
                "order_authority": False,
            }
        )
    hashes = {row["target_sha256"] for row in output}
    if len(hashes) != 1:
        raise ValueError("R12 zero-budget candidate targets do not share the exact D01 fallback")
    return output


def _account_reconciliation(
    root: Path, d01: dict[str, Any], decision_session: date
) -> dict[str, Any]:
    positions_path = root / "reports/paper/positions.json"
    account_path = root / "reports/paper/account.json"
    if d01.get("status") != "ok" or not positions_path.exists() or not account_path.exists():
        return {
            "status": "not_available",
            "broker_read_only": True,
            "broker_writes": False,
        }
    report = build_state_drift_report(
        root=root,
        cycle_date=next_us_equity_session(decision_session),
        expected_state=str(d01.get("state") or "cash"),
        positions_path=positions_path,
        account_path=account_path,
        target_weights_path=root / D01_TARGET_PATH,
        weight_tolerance=0.05,
    )
    return {
        **report,
        "account_binding": _binding(account_path, root),
        "positions_binding": _binding(positions_path, root),
        "broker_read_only": True,
        "broker_writes": False,
    }


def _pending_llm_retry_contexts(
    root: Path,
    *,
    lock_state: dict[str, Any],
    model_parameters_hash: str,
) -> list[dict[str, Any]]:
    prior_results = _published_llm_retry_results(root, lock_state)
    successful = {
        (
            str(result.get("source_observation_id")),
            str(result.get("packet_id")),
            str(result.get("model_parameters_hash")),
        )
        for result in prior_results
        if result.get("status") == "valid"
    }
    attempt_counts = Counter(
        (
            str(result.get("source_observation_id")),
            str(result.get("packet_id")),
            str(result.get("model_parameters_hash")),
        )
        for result in prior_results
    )
    observations_dir = root / FORWARD_DATA_DIR / "observations"
    if not observations_dir.exists():
        return []

    contexts: list[dict[str, Any]] = []
    for directory in sorted(
        path
        for path in observations_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ):
        receipt_path = directory / "receipt.json"
        receipt = _verify_observation_receipt(root, receipt_path, lock_state)
        bindings = receipt["bindings"]
        observation = _read_json(root / bindings["observation"]["path"])
        llm_materialization = observation.get("llm_materialization")
        results = (
            llm_materialization.get("results") if isinstance(llm_materialization, dict) else None
        )
        if not isinstance(results, list):
            raise ValueError("R12 forward observation lacks LLM materialization results")
        packet_rows = _read_jsonl(root / bindings["source_packets"]["path"])
        packets = {
            packet.packet_id: packet
            for packet in (ForwardSourcePacket.model_validate(row) for row in packet_rows)
        }
        raw_price_features = (observation.get("price_confirmation") or {}).get("features")
        if not isinstance(raw_price_features, dict):
            raise ValueError("R12 forward observation lacks bound price confirmations")
        price_features = {
            str(symbol): PriceConfirmation.model_validate(value)
            for symbol, value in raw_price_features.items()
        }
        source_observation_id = str(receipt["observation_id"])
        for result in results:
            if not isinstance(result, dict) or result.get("status") != "fallback":
                continue
            allowed_entities = result.get("allowed_entities")
            if not isinstance(allowed_entities, list) or not allowed_entities:
                continue
            if not all(isinstance(symbol, str) for symbol in allowed_entities):
                raise ValueError("R12 forward LLM allowed entities are malformed")
            packet = packets.get(str(result.get("packet_id")))
            if packet is None or packet.input_hash != result.get("input_hash"):
                raise ValueError("R12 forward retry source packet binding mismatch")
            input_payload_hash = _canonical_hash(_llm_input_payload(packet, allowed_entities))
            if input_payload_hash != result.get("input_payload_sha256"):
                raise ValueError("R12 forward retry input payload binding mismatch")
            key = (source_observation_id, packet.packet_id, model_parameters_hash)
            if key in successful:
                continue
            contexts.append(
                {
                    "packet": packet,
                    "allowed_entities": allowed_entities,
                    "price_features": price_features,
                    "source_observation_id": source_observation_id,
                    "decision_session": str(receipt["decision_session"]),
                    "receipt_binding": _binding(receipt_path, root),
                    "observation_binding": bindings["observation"],
                    "source_packets_binding": bindings["source_packets"],
                    "prior_attempt_count": attempt_counts[key],
                }
            )
    contexts.sort(
        key=lambda row: (str(row["decision_session"]), row["packet"].packet_id),
        reverse=True,
    )
    return contexts


def _llm_retry_source_evidence(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for context in contexts:
        observation_id = str(context["source_observation_id"])
        evidence = grouped.setdefault(
            observation_id,
            {
                "source_observation_id": observation_id,
                "decision_session": context["decision_session"],
                "receipt_binding": context["receipt_binding"],
                "observation_binding": context["observation_binding"],
                "source_packets_binding": context["source_packets_binding"],
                "packet_ids": [],
            },
        )
        evidence["packet_ids"].append(context["packet"].packet_id)
    for evidence in grouped.values():
        evidence["packet_ids"] = sorted(set(evidence["packet_ids"]))
    return [grouped[key] for key in sorted(grouped)]


def _publish_observation(
    root: Path,
    *,
    final_dir: Path,
    lock_state: dict[str, Any],
    observation: dict[str, Any],
    source_packets: list[ForwardSourcePacket],
    event_rows: list[dict[str, Any]],
    theme_rows: list[dict[str, Any]],
    placebo_rows: list[dict[str, Any]],
    price_inputs: list[dict[str, Any]],
    d01: dict[str, Any],
) -> dict[str, Any]:
    parent = final_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".staging-{final_dir.name}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=False)
    try:
        files = {
            "source_packets": staging / "source-packets.jsonl",
            "event_features": staging / "event-features.jsonl",
            "theme_factors": staging / "theme-factors.jsonl",
            "placebo_factors": staging / "placebo-theme-factors.jsonl",
            "price_inputs": staging / "price-inputs.jsonl",
            "observation": staging / "observation.json",
        }
        _write_jsonl_atomic(
            files["source_packets"],
            [packet.model_dump(mode="json") for packet in source_packets],
        )
        _write_jsonl_atomic(files["event_features"], event_rows)
        _write_jsonl_atomic(files["theme_factors"], theme_rows)
        _write_jsonl_atomic(files["placebo_factors"], placebo_rows)
        _write_jsonl_atomic(files["price_inputs"], price_inputs)
        _write_json_atomic(files["observation"], observation)
        bindings = {
            name: _staged_binding(path, final_dir / path.name, root) for name, path in files.items()
        }
        external_bindings = {}
        if d01.get("artifact"):
            external_bindings["d01_target_weights"] = d01["artifact"]
        receipt_anchor = {
            "schema_version": 1,
            "receipt_contract": RECEIPT_CONTRACT,
            "iter_id": ITER_ID,
            "epoch_id": lock_state["epoch_id"],
            "epoch_lock_path": lock_state["lock_path"],
            "epoch_lock_sha256": lock_state["lock_sha256"],
            "observation_id": observation["observation_id"],
            "collected_at": observation["collected_at"],
            "decision_session": observation["decision_session"],
            "action_session": observation["action_session"],
            "source_packet_count": len(source_packets),
            "selected_theme_count": observation["selected_theme_count"],
            "llm_factor_count": observation["llm_valid_factor_count"],
            "bindings": bindings,
            "external_bindings": external_bindings,
            "historical_backfill_credit": False,
            "semantic_stock_budget": 0.0,
            "observation_only": True,
            "broker_writes": False,
            "order_authority": False,
        }
        receipt = {
            **receipt_anchor,
            "receipt_payload_sha256": _canonical_hash(receipt_anchor),
        }
        _write_json_atomic(staging / "receipt.json", receipt)
        os.replace(staging, final_dir)
        _fsync_directory(parent)
        return _verify_observation_receipt(root, final_dir / "receipt.json", lock_state)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _verify_observation_receipt(
    root: Path, receipt_path: Path, lock_state: dict[str, Any]
) -> dict[str, Any]:
    receipt = _read_json(_regular_in_root(root, receipt_path))
    anchor = {key: value for key, value in receipt.items() if key != "receipt_payload_sha256"}
    if (
        receipt.get("schema_version") != 1
        or receipt.get("receipt_contract") != RECEIPT_CONTRACT
        or receipt.get("iter_id") != ITER_ID
        or receipt.get("epoch_id") != lock_state["epoch_id"]
        or receipt.get("epoch_lock_sha256") != lock_state["lock_sha256"]
        or receipt.get("receipt_payload_sha256") != _canonical_hash(anchor)
        or receipt.get("broker_writes") is not False
        or receipt.get("order_authority") is not False
        or receipt.get("semantic_stock_budget") != 0.0
    ):
        raise ValueError("R12 forward observation receipt identity mismatch")
    bindings = receipt.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != {
        "source_packets",
        "event_features",
        "theme_factors",
        "placebo_factors",
        "price_inputs",
        "observation",
    }:
        raise ValueError("R12 forward observation receipt binding coverage mismatch")
    for binding in bindings.values():
        _verify_binding(root, binding)
    for binding in (receipt.get("external_bindings") or {}).values():
        _verify_binding(root, binding)
    observation = _read_json(root / bindings["observation"]["path"])
    if (
        observation.get("observation_contract") != OBSERVATION_CONTRACT
        or observation.get("observation_id") != receipt.get("observation_id")
        or observation.get("epoch_id") != receipt.get("epoch_id")
        or observation.get("source_packet_count") != receipt.get("source_packet_count")
        or observation.get("broker_writes") is not False
    ):
        raise ValueError("R12 forward observation payload mismatch")
    return receipt


def _publish_llm_retry(
    root: Path,
    *,
    final_dir: Path,
    lock_state: dict[str, Any],
    payload: dict[str, Any],
    theme_rows: list[dict[str, Any]],
    source_evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    parent = final_dir.parent
    parent.mkdir(parents=True, exist_ok=True)
    staging = parent / f".staging-{final_dir.name}-{os.getpid()}"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=False)
    try:
        files = {
            "retry": staging / "llm-retry.json",
            "theme_factors": staging / "theme-factors.jsonl",
        }
        _write_json_atomic(files["retry"], payload)
        _write_jsonl_atomic(files["theme_factors"], theme_rows)
        bindings = {
            name: _staged_binding(path, final_dir / path.name, root) for name, path in files.items()
        }
        receipt_anchor = {
            "schema_version": 1,
            "receipt_contract": LLM_RETRY_RECEIPT_CONTRACT,
            "iter_id": ITER_ID,
            "epoch_id": lock_state["epoch_id"],
            "epoch_lock_path": lock_state["lock_path"],
            "epoch_lock_sha256": lock_state["lock_sha256"],
            "retry_id": payload["retry_id"],
            "materialized_at": payload["materialized_at"],
            "model_parameters_hash": payload["model_parameters_hash"],
            "attempted_packet_count": payload["attempted_packet_count"],
            "valid_factor_count": payload["valid_factor_count"],
            "bindings": bindings,
            "source_evidence": source_evidence,
            "forward_session_credit": False,
            "source_packet_credit": 0,
            "semantic_stock_budget": 0.0,
            "observation_only": True,
            "broker_writes": False,
            "order_authority": False,
        }
        receipt = {
            **receipt_anchor,
            "receipt_payload_sha256": _canonical_hash(receipt_anchor),
        }
        _write_json_atomic(staging / "receipt.json", receipt)
        os.replace(staging, final_dir)
        _fsync_directory(parent)
        return _verify_llm_retry_receipt(root, final_dir / "receipt.json", lock_state)
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _verify_llm_retry_receipt(
    root: Path,
    receipt_path: Path,
    lock_state: dict[str, Any],
) -> dict[str, Any]:
    receipt = _read_json(_regular_in_root(root, receipt_path))
    anchor = {key: value for key, value in receipt.items() if key != "receipt_payload_sha256"}
    if (
        receipt.get("schema_version") != 1
        or receipt.get("receipt_contract") != LLM_RETRY_RECEIPT_CONTRACT
        or receipt.get("iter_id") != ITER_ID
        or receipt.get("epoch_id") != lock_state["epoch_id"]
        or receipt.get("epoch_lock_sha256") != lock_state["lock_sha256"]
        or receipt.get("receipt_payload_sha256") != _canonical_hash(anchor)
        or receipt.get("forward_session_credit") is not False
        or receipt.get("source_packet_credit") != 0
        or receipt.get("semantic_stock_budget") != 0.0
        or receipt.get("broker_writes") is not False
        or receipt.get("order_authority") is not False
    ):
        raise ValueError("R12 forward LLM retry receipt identity mismatch")
    bindings = receipt.get("bindings")
    if not isinstance(bindings, dict) or set(bindings) != {"retry", "theme_factors"}:
        raise ValueError("R12 forward LLM retry binding coverage mismatch")
    for binding in bindings.values():
        _verify_binding(root, binding)

    source_evidence = receipt.get("source_evidence")
    if not isinstance(source_evidence, list) or not source_evidence:
        raise ValueError("R12 forward LLM retry lacks source evidence")
    packets: dict[str, ForwardSourcePacket] = {}
    packet_observations: dict[str, str] = {}
    for evidence in source_evidence:
        if not isinstance(evidence, dict):
            raise ValueError("R12 forward LLM retry source evidence is malformed")
        original_receipt_path = _verify_binding(root, evidence.get("receipt_binding"))
        _verify_binding(root, evidence.get("observation_binding"))
        source_packets_path = _verify_binding(root, evidence.get("source_packets_binding"))
        original_receipt = _verify_observation_receipt(root, original_receipt_path, lock_state)
        observation_id = str(evidence.get("source_observation_id") or "")
        if observation_id != original_receipt.get("observation_id"):
            raise ValueError("R12 forward LLM retry source observation identity mismatch")
        packet_ids = evidence.get("packet_ids")
        if not isinstance(packet_ids, list) or not packet_ids:
            raise ValueError("R12 forward LLM retry source packet IDs are missing")
        source_rows = {
            packet.packet_id: packet
            for packet in (
                ForwardSourcePacket.model_validate(row) for row in _read_jsonl(source_packets_path)
            )
        }
        for packet_id in packet_ids:
            packet = source_rows.get(str(packet_id))
            if packet is None:
                raise ValueError("R12 forward LLM retry packet is absent from source evidence")
            packets[packet.packet_id] = packet
            packet_observations[packet.packet_id] = observation_id

    payload = _read_json(root / bindings["retry"]["path"])
    if (
        payload.get("retry_contract") != LLM_RETRY_CONTRACT
        or payload.get("retry_id") != receipt.get("retry_id")
        or payload.get("epoch_id") != receipt.get("epoch_id")
        or payload.get("model_parameters_hash") != receipt.get("model_parameters_hash")
        or payload.get("attempted_packet_count") != receipt.get("attempted_packet_count")
        or payload.get("valid_factor_count") != receipt.get("valid_factor_count")
        or payload.get("source_evidence") != source_evidence
        or payload.get("forward_session_credit") is not False
        or payload.get("broker_writes") is not False
    ):
        raise ValueError("R12 forward LLM retry payload mismatch")
    results = payload.get("results")
    if not isinstance(results, list) or len(results) != receipt.get("attempted_packet_count"):
        raise ValueError("R12 forward LLM retry result coverage mismatch")
    for result in results:
        if not isinstance(result, dict):
            raise ValueError("R12 forward LLM retry result is malformed")
        packet = packets.get(str(result.get("packet_id")))
        allowed_entities = result.get("allowed_entities")
        if packet is None or not isinstance(allowed_entities, list):
            raise ValueError("R12 forward LLM retry result lacks source binding")
        if result.get("source_observation_id") != packet_observations[packet.packet_id]:
            raise ValueError("R12 forward LLM retry result observation binding mismatch")
        if result.get("input_hash") != packet.input_hash or result.get(
            "input_payload_sha256"
        ) != _canonical_hash(_llm_input_payload(packet, allowed_entities)):
            raise ValueError("R12 forward LLM retry input binding mismatch")
        error = result.get("error")
        if isinstance(error, str) and re.search(r"(?i)sk-[a-z0-9_-]{8,}", error):
            raise ValueError("R12 forward LLM retry error contains credential material")
    return receipt


def _published_llm_retry_results(
    root: Path,
    lock_state: dict[str, Any],
) -> list[dict[str, Any]]:
    retries_dir = root / FORWARD_DATA_DIR / "llm-retries"
    if not retries_dir.exists():
        return []
    output: list[dict[str, Any]] = []
    for directory in sorted(
        path for path in retries_dir.iterdir() if path.is_dir() and not path.name.startswith(".")
    ):
        receipt = _verify_llm_retry_receipt(root, directory / "receipt.json", lock_state)
        payload = _read_json(root / receipt["bindings"]["retry"]["path"])
        output.extend(payload["results"])
    return output


def _rebuild_llm_retry_projections(root: Path, lock_state: dict[str, Any]) -> None:
    retries_dir = root / FORWARD_DATA_DIR / "llm-retries"
    if not retries_dir.exists():
        return
    receipts: list[dict[str, Any]] = []
    theme_rows: list[dict[str, Any]] = []
    latest: dict[str, Any] | None = None
    for directory in sorted(
        path for path in retries_dir.iterdir() if path.is_dir() and not path.name.startswith(".")
    ):
        receipt = _verify_llm_retry_receipt(root, directory / "receipt.json", lock_state)
        receipts.append(receipt)
        bindings = receipt["bindings"]
        theme_rows.extend(_read_jsonl(root / bindings["theme_factors"]["path"]))
        latest = _read_json(root / bindings["retry"]["path"])
        latest["receipt_binding"] = _binding(directory / "receipt.json", root)
    _write_jsonl_atomic(root / FORWARD_REPORT_DIR / "llm-retry-ledger.jsonl", receipts)
    _write_jsonl_atomic(
        root / FORWARD_DATA_DIR / "llm-retry-theme-factors.jsonl",
        _dedupe_rows(theme_rows, "dedupe_key"),
    )
    if latest is not None:
        _write_json_atomic(root / FORWARD_REPORT_DIR / "latest-llm-retry.json", latest)


def _rebuild_forward_projections(root: Path) -> None:
    observations_dir = root / FORWARD_DATA_DIR / "observations"
    if not observations_dir.exists():
        return
    lock_state = verify_pit_semantic_theme_forward_lock(root)
    receipts: list[dict[str, Any]] = []
    feature_groups: dict[str, list[dict[str, Any]]] = {
        "event_features": [],
        "theme_factors": [],
        "placebo_factors": [],
    }
    packets: list[dict[str, Any]] = []
    latest_observation: dict[str, Any] | None = None
    for directory in sorted(
        path
        for path in observations_dir.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    ):
        receipt = _verify_observation_receipt(root, directory / "receipt.json", lock_state)
        receipts.append(receipt)
        bindings = receipt["bindings"]
        packets.extend(_read_jsonl(root / bindings["source_packets"]["path"]))
        for name in feature_groups:
            feature_groups[name].extend(_read_jsonl(root / bindings[name]["path"]))
        latest_observation = _read_json(root / bindings["observation"]["path"])
        latest_observation["receipt_binding"] = _binding(directory / "receipt.json", root)

    data_dir = root / FORWARD_DATA_DIR
    _write_jsonl_atomic(
        data_dir / "source-packet-index.jsonl", _dedupe_rows(packets, "source_version_key")
    )
    _write_jsonl_atomic(
        data_dir / "event-features.jsonl",
        _dedupe_rows(feature_groups["event_features"], "dedupe_key"),
    )
    _write_jsonl_atomic(
        data_dir / "theme-factors.jsonl",
        _dedupe_rows(feature_groups["theme_factors"], "dedupe_key"),
    )
    _write_jsonl_atomic(
        data_dir / "placebo-theme-factors.jsonl",
        _dedupe_rows(feature_groups["placebo_factors"], "dedupe_key"),
    )
    _write_jsonl_atomic(root / FORWARD_REPORT_DIR / "observation-ledger.jsonl", receipts)
    if latest_observation is not None:
        _write_json_atomic(
            root / FORWARD_REPORT_DIR / "latest-observation.json", latest_observation
        )


def _published_source_version_keys(root: Path) -> set[str]:
    return {packet.source_version_key for packet in _published_source_packets(root)}


def _published_source_packets(root: Path) -> list[ForwardSourcePacket]:
    path = root / FORWARD_DATA_DIR / "source-packet-index.jsonl"
    if not path.exists():
        return []
    return [ForwardSourcePacket.model_validate(row) for row in _read_jsonl(path)]


def _attention_acceleration(
    packets: list[ForwardSourcePacket], observed_at: datetime
) -> dict[str, float]:
    now = _utc(observed_at)
    current_start = now - timedelta(hours=24)
    prior_start = now - timedelta(hours=48)
    current: Counter[str] = Counter()
    prior: Counter[str] = Counter()
    for packet in packets:
        bucket = (
            current
            if packet.published_at >= current_start
            else prior
            if packet.published_at >= prior_start
            else None
        )
        if bucket is not None:
            bucket.update(packet.symbols)
    symbols = set(current) | set(prior)
    return {
        symbol: round(
            (current[symbol] - prior[symbol]) / max(1, current[symbol] + prior[symbol]), 6
        )
        for symbol in symbols
    }


def _rank_packet_symbols(
    packet: ForwardSourcePacket,
    attention: dict[str, float],
    *,
    eligible_symbols: set[str] | None = None,
) -> list[str]:
    symbols = packet.symbols
    if eligible_symbols is not None:
        symbols = [symbol for symbol in symbols if symbol in eligible_symbols]
    return sorted(
        symbols,
        key=lambda symbol: (-attention.get(symbol, 0.0), symbol),
    )[:MAX_THEME_MEMBERS]


def _is_equity_symbol(symbol: str) -> bool:
    normalized = symbol.upper().strip()
    return bool(
        re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", normalized) and not normalized.endswith("USD")
    )


def _relationship_type(text: str) -> str:
    normalized = text.lower()
    for relationship, terms in RELATIONSHIP_TERMS.items():
        if any(term in normalized for term in terms):
            return relationship
    return "unknown"


def _lexical_direction(text: str) -> float:
    normalized = text.lower()
    positive = sum(term in normalized for term in POSITIVE_TERMS)
    negative = sum(term in normalized for term in NEGATIVE_TERMS)
    return round(max(-1.0, min(1.0, (positive - negative) / max(1, positive + negative))), 6)


def _deterministic_horizon(packet: ForwardSourcePacket) -> int:
    text = f"{packet.title} {packet.summary}".lower()
    if any(term in text for term in ("earnings", "guidance", "forecast")):
        return 10
    if any(term in text for term in ("contract", "order", "partnership", "approval")):
        return 8
    return 5


def _return_over(series: pd.Series, sessions: int) -> float:
    value = float(series.iloc[-1] / series.iloc[-1 - sessions] - 1.0)
    if not math.isfinite(value):
        raise ValueError("price return is nonfinite")
    return value


def _source_input_payload(packet: ForwardSourcePacket) -> dict[str, Any]:
    return {
        "source": packet.source,
        "provider_article_id": packet.provider_article_id,
        "version_id": packet.version_id,
        "symbols": packet.symbols,
        "title": packet.title,
        "summary": packet.summary,
        "source_url": packet.source_url,
        "published_at": packet.published_at.isoformat(),
        "rights_scope": packet.rights_scope,
        "revision_id": packet.revision_id,
    }


def _result_from_receipt(final_dir: Path, receipt: dict[str, Any]) -> ForwardObservationResult:
    observation_path = final_dir / "observation.json"
    payload = _read_json(observation_path)
    return ForwardObservationResult(
        status="published",
        epoch_id=str(receipt["epoch_id"]),
        observation_id=str(receipt["observation_id"]),
        observation_path=observation_path,
        receipt_path=final_dir / "receipt.json",
        source_packet_count=int(receipt["source_packet_count"]),
        selected_theme_count=int(receipt["selected_theme_count"]),
        llm_factor_count=int(receipt["llm_factor_count"]),
        payload=payload,
    )


def _llm_retry_result_from_receipt(
    final_dir: Path,
    receipt: dict[str, Any],
) -> ForwardLLMRetryResult:
    retry_path = final_dir / "llm-retry.json"
    payload = _read_json(retry_path)
    return ForwardLLMRetryResult(
        status="published",
        epoch_id=str(receipt["epoch_id"]),
        retry_id=str(receipt["retry_id"]),
        retry_path=retry_path,
        receipt_path=final_dir / "receipt.json",
        attempted_packet_count=int(receipt["attempted_packet_count"]),
        valid_factor_count=int(receipt["valid_factor_count"]),
        payload=payload,
    )


def _safe_error(exc: Exception) -> str:
    value = str(exc)
    if re.search(r"(?i)(api\s*key|secret|token|invalid_api_key|authenticationerror)", value):
        return f"{type(exc).__name__}: provider authentication failed; credentials not persisted"
    value = re.sub(r"(?i)sk-[a-z0-9_-]+", "<redacted>", value)
    value = re.sub(r"(?i)(api[_ -]?key|secret|token)\s*[:=]\s*\S+", r"\1=<redacted>", value)
    return f"{type(exc).__name__}: {value}"[:500]


def _mean(values: Iterable[float]) -> float:
    rows = list(values)
    return math.fsum(rows) / len(rows) if rows else 0.0


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: Any, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"R12 forward {label} is invalid") from exc
    return _utc(parsed)


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("ascii")


def _canonical_hash(value: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(value)).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _regular_in_root(root: Path, path: Path) -> Path:
    base = root.resolve()
    candidate = path if path.is_absolute() else base / path
    cursor = candidate
    while cursor != base and cursor != cursor.parent:
        if cursor.is_symlink():
            raise ValueError(f"R12 forward bound path cannot use symlinks: {candidate}")
        cursor = cursor.parent
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R12 forward bound path escapes the project root: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"R12 forward bound path is not a regular file: {candidate}")
    return resolved


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = _regular_in_root(root, path)
    return {
        "path": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _staged_binding(stage_path: Path, destination: Path, root: Path) -> dict[str, Any]:
    return {
        "path": destination.resolve(strict=False).relative_to(root.resolve()).as_posix(),
        "sha256": _sha256(stage_path),
        "size_bytes": stage_path.stat().st_size,
    }


def _verify_binding(root: Path, binding: Any) -> Path:
    if not isinstance(binding, dict):
        raise ValueError("R12 forward file binding is malformed")
    path = _regular_in_root(root, root / str(binding.get("path") or ""))
    if _sha256(path) != binding.get("sha256") or path.stat().st_size != binding.get("size_bytes"):
        raise ValueError(f"R12 forward file binding changed: {binding.get('path')}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R12 forward JSON artifact must be an object: {path}")
    return payload


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            payload = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"R12 forward JSONL row is not an object: {path}:{line_number}")
            rows.append(payload)
    return rows


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    output: dict[str, dict[str, Any]] = {}
    for row in rows:
        value = str(row.get(key) or "")
        if not value:
            raise ValueError(f"R12 forward projection row lacks {key}")
        if value in output and output[value] != row:
            raise ValueError(f"R12 forward projection has conflicting duplicate {key}: {value}")
        output[value] = row
    return [output[value] for value in sorted(output)]


def _exclusive_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    _fsync_directory(path.parent)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    data = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n"
    with temporary.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    with temporary.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, allow_nan=False) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


@contextmanager
def _forward_writer_lock(root: Path):
    lock_path = root / ITERATION_DIR / "forward" / ".writer.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
