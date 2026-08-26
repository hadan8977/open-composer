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

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.events.fetcher import fetch_capability_events
from open_composer.config import default_openai_model, openai_api_key, project_root
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.event import EventRecord
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.paper_freshness import latest_completed_us_equity_session
from open_composer.research.llm_backends import get_backend
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE, R11PricePanel
from open_composer.research.pit_semantic_theme_r22 import (
    DEVELOPMENT_END,
    M01_OVERRIDE_THRESHOLD,
    M02_SURVIVAL_EXIT_THRESHOLD,
    MODEL_FEATURES,
    RECOVERY_BREADTH_MIN_COUNT,
    RECOVERY_BREADTH_TREND_SESSIONS,
    RECOVERY_QQQ_TREND_SESSIONS,
    RECOVERY_TQQQ_MOMENTUM_MIN,
    RECOVERY_TQQQ_MOMENTUM_SESSIONS,
    REVIEW_EVERY_SESSIONS,
    STRESS_ROUTE,
    TAIL_EXIT_SESSIONS,
    TECH_BREADTH_SYMBOLS,
    _advance_d01_route,
    _advance_nonstress_route,
    _advance_usd_pressure,
    _fit_route_models,
    _predict_probability,
    _stress_route_for_row,
    _target_for_route,
    build_r22_d01_targets,
    build_r22_feature_dataset,
    load_and_validate_r22_specs,
    load_r22_price_panel,
)
from open_composer.research.pit_semantic_theme_r22 import (
    SPEC_PATHS as SOURCE_SPEC_PATHS,
)
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_pit_semantic_theme_r23"
SOURCE_ITER_ID = "mom_pit_semantic_theme_r22"
SPEC_PATHS = {
    candidate_id: Path(f"strategy_specs/drafts/us_pit_semantic_theme_r23_{suffix}.yaml")
    for candidate_id, suffix in (
        ("R23D01", "d01"),
        ("R23D02", "d02"),
        ("R23M01", "m01"),
        ("R23M02", "m02"),
        ("R23L01", "l01"),
        ("R23C01", "c01"),
        ("R23F01", "f01"),
        ("R23P01", "p01"),
    )
}
FORWARD_ITER_ID = f"{ITER_ID}_forward"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
SOURCE_ITERATION_DIR = Path("reports/research/iterations") / SOURCE_ITER_ID
FORWARD_LOCK_PATH = ITERATION_DIR / "forward/epoch-lock.json"
FORWARD_DATA_DIR = Path("data/forward/pit_semantic_theme_r23")
FORWARD_REPORT_DIR = Path("reports/forward/us_pit_semantic_theme_r23")
HISTORICAL_LOCK_PATH = SOURCE_ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
HISTORICAL_REPORT_PATH = SOURCE_ITERATION_DIR / "historical-evaluation/evaluation-report.json"
HISTORICAL_TARGET_LEDGER_PATH = SOURCE_ITERATION_DIR / "historical-evaluation/target-ledger.jsonl"
PROMPT_PATH = Path("prompts/pit_semantic_theme_r23_factor_v1.txt")
PACKET_SCHEMA_PATH = Path("schemas/pit_semantic_theme_r23_forward_packet.schema.json")
FORWARD_MODULE_PATH = Path("open_composer/research/pit_semantic_theme_r23_forward.py")
FORWARD_TEST_PATH = Path("tests/test_pit_semantic_theme_r23_forward.py")

FORWARD_LOCK_CONTRACT = "pit_semantic_theme_r23_forward_epoch_v1"
SOURCE_PACKET_CONTRACT = "pit_semantic_theme_r23_forward_source_v1"
OBSERVATION_CONTRACT = "pit_semantic_theme_r23_tier0_observation_v1"
RECEIPT_CONTRACT = "pit_semantic_theme_r23_tier0_receipt_v1"
TARGET_CONTRACT = "pit_semantic_theme_r23_target_weights_v1"
INTENT_CONTRACT = "pit_semantic_theme_r23_rebalance_intents_v1"
EXECUTION_OBSERVATION_CONTRACT = "pit_semantic_theme_r23_execution_observation_v1"

PRICE_FEED = "iex"
PRICE_ADJUSTMENT = "all"
LIVE_OVERLAP_TOLERANCE = 0.05
MAX_NEWS_AGE = timedelta(days=32)
MAX_THEME_PACKETS = 8
MAX_THEME_MEMBERS = 8
MIN_CONFIRMED_MEMBERS = 2
MIN_PRICE_SESSIONS = 60
MIN_PRICE = 10.0
MIN_MEDIAN_DOLLAR_VOLUME = 25_000_000.0
PRICE_LOOKBACK_DAYS = 180
ATTENTION_SHORT_SESSIONS = 3
ATTENTION_LONG_SESSIONS = 10
RESIDUAL_MOMENTUM_SESSIONS = 5
VOLUME_SHORT_SESSIONS = 5
VOLUME_BASELINE_SESSIONS = 20
MIN_VOLUME_SURPRISE = 1.25
MIN_POSITIVE_MEMBER_BREADTH = 0.60
SEMANTIC_STOCK_BUDGET = 0.0
PLACEBO_SEED = 15108
ACCOUNT_WEIGHT_TOLERANCE = 0.05
R22_HISTORICAL_LOCK_SHA256 = "796c01de14ee1c9b236d9ba3623a0b00050a175044eab272aea4954efda4b932"
R22_HISTORICAL_REPORT_SHA256 = "6fa746c79dacd24296d8d2b7760f6b64436d5ea965403512414f6f854dd96b3d"

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
    "shared_event_impact",
    "unknown",
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
    "shared_event_impact": (
        "affects both",
        "benefits both",
        "companies said",
        "jointly",
        "shared impact",
    ),
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

FORWARD_BEHAVIOR = {
    "candidate_ids": list(SPEC_PATHS),
    "price_feed": PRICE_FEED,
    "price_adjustment": PRICE_ADJUSTMENT,
    "historical_backfill_credit": False,
    "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
    "semantic_price_creates_relationship": False,
    "trained_targets_are_observation_only": True,
    "paper_account_access": "read_only_snapshot",
    "broker_writes": False,
    "order_authority": False,
    "stable_tier0_sessions": 5,
    "minimum_investable_company_entities": MIN_CONFIRMED_MEMBERS,
    "attention_windows_sessions": [ATTENTION_SHORT_SESSIONS, ATTENTION_LONG_SESSIONS],
    "residual_momentum_sessions": RESIDUAL_MOMENTUM_SESSIONS,
    "volume_surprise_windows_sessions": [VOLUME_SHORT_SESSIONS, VOLUME_BASELINE_SESSIONS],
    "volume_surprise_ratio_min": MIN_VOLUME_SURPRISE,
    "minimum_positive_member_breadth": MIN_POSITIVE_MEMBER_BREADTH,
    "minimum_price_sessions": MIN_PRICE_SESSIONS,
    "minimum_price": MIN_PRICE,
    "minimum_median_dollar_volume": MIN_MEDIAN_DOLLAR_VOLUME,
    "placebo_seed": PLACEBO_SEED,
}

LOCKED_PATHS = (
    HISTORICAL_LOCK_PATH,
    HISTORICAL_REPORT_PATH,
    HISTORICAL_TARGET_LEDGER_PATH,
    ITERATION_DIR / "candidate-manifest.json",
    ITERATION_DIR / "data-contract.json",
    ITERATION_DIR / "feature-contract.json",
    ITERATION_DIR / "universe-contract.json",
    ITERATION_DIR / "validation-contract.json",
    ITERATION_DIR / "cost-contract.json",
    ITERATION_DIR / "holdout-contract.json",
    ITERATION_DIR / "modality-role-matrix.json",
    ITERATION_DIR / "model-reuse-decision.json",
    ITERATION_DIR / "knowledge-assessment.json",
    ITERATION_DIR / "external-brief.json",
    Path("reports/research/data-quality/r11-price-repair-20260804-contract.json"),
    Path("reports/research/data-quality/r11-price-repair-20260804-quality.json"),
    PROMPT_PATH,
    Path("schemas/alpaca_snapshot_contract.schema.json"),
    Path("schemas/alpaca_snapshot_manifest.schema.json"),
    PACKET_SCHEMA_PATH,
    Path("open_composer/market_calendar.py"),
    Path("open_composer/adapters/data/alpaca_snapshot.py"),
    Path("open_composer/research/pit_semantic_theme_r22.py"),
    *SOURCE_SPEC_PATHS.values(),
    FORWARD_MODULE_PATH,
    FORWARD_TEST_PATH,
    Path("open_composer/adapters/data/alpaca.py"),
    Path("open_composer/adapters/events/fetcher.py"),
    Path("open_composer/research/llm_backends.py"),
)


def load_and_validate_r23_specs(root: Path) -> dict[str, StrategySpec]:
    specs = {
        candidate_id: load_strategy_spec(root / path) for candidate_id, path in SPEC_PATHS.items()
    }
    if set(specs) != set(SPEC_PATHS):
        raise ValueError("R23 candidate spec coverage mismatch")
    for candidate_id, spec in specs.items():
        notes = spec.notes.model_dump(mode="python") if spec.notes is not None else {}
        if (
            spec.name != f"us_pit_semantic_theme_r23_{candidate_id[-3:].lower()}"
            or spec.lifecycle != "draft"
            or spec.execution.mode != "manual_signal"
            or spec.execution.broker != "none"
            or spec.research_design is None
            or spec.research_design.iter_id != ITER_ID
            or notes.get("candidate_id") != candidate_id
            or float(notes.get("semantic_stock_budget", -1.0)) != SEMANTIC_STOCK_BUDGET
            or notes.get("order_authority") is not False
            or notes.get("broker_writes") is not False
        ):
            raise ValueError(f"R23 spec violates the Tier 0 identity contract: {candidate_id}")
    return specs


class ThemeBackend(Protocol):
    def infer(
        self,
        *,
        model: str,
        prompt: str,
        input_payload: dict[str, Any],
        output_schema: dict[str, Any],
    ) -> dict[str, Any]: ...


class ForwardSourcePacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    packet_contract: Literal["pit_semantic_theme_r23_forward_source_v1"]
    packet_id: str = Field(pattern=r"^r23pkt_[a-f0-9]{24}$")
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
            raise ValueError("R23 source packet requires at least one symbol")
        return normalized

    @model_validator(mode="after")
    def validate_provenance(self) -> ForwardSourcePacket:
        self.published_at = _utc(self.published_at)
        self.fetched_at = _utc(self.fetched_at)
        self.first_seen_at = _utc(self.first_seen_at)
        self.visible_at = _utc(self.visible_at)
        if self.fetched_at < self.published_at:
            raise ValueError("R23 fetched_at cannot precede published_at")
        if self.first_seen_at < self.fetched_at:
            raise ValueError("R23 first_seen_at cannot precede fetched_at")
        if self.visible_at < max(self.published_at, self.fetched_at, self.first_seen_at):
            raise ValueError("R23 visible_at violates safe first-seen ordering")
        expected_hash = _canonical_hash(_source_input_payload(self))
        if self.input_hash != expected_hash:
            raise ValueError("R23 source packet input_hash mismatch")
        if self.packet_id != f"r23pkt_{expected_hash[:24]}":
            raise ValueError("R23 source packet packet_id mismatch")
        return self


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
        "shared_event_impact",
        "unknown",
    ]
    evidence_packet_ids: list[str] = Field(min_length=1, max_length=8)

    @field_validator("source_entity", "target_entity")
    @classmethod
    def normalize_entity(cls, value: str) -> str:
        return value.upper().strip()


class StructuredThemeFactor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    theme_id: str = Field(pattern=r"^r23theme_[a-f0-9]{16}$")
    event_type: str = Field(min_length=1, max_length=128)
    impact_subjects: list[str] = Field(min_length=1, max_length=MAX_THEME_MEMBERS)
    entities: list[str] = Field(min_length=1, max_length=MAX_THEME_MEMBERS)
    relationships: list[ThemeRelationship] = Field(default_factory=list, max_length=32)
    direction: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    horizon_sessions: int = Field(ge=3, le=20)
    evidence_packet_ids: list[str] = Field(min_length=1, max_length=8)
    unknown_fields: list[str] = Field(default_factory=list, max_length=32)

    @field_validator("entities", "impact_subjects")
    @classmethod
    def normalize_entities(cls, values: list[str]) -> list[str]:
        normalized = [value.upper().strip() for value in values if value.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("R23 theme entities must be unique")
        return normalized


class PriceConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    session: date | None = None
    status: Literal["ok", "blocked"]
    blocker: str | None = None
    session_count: int = 0
    close: float | None = None
    momentum_5: float | None = None
    residual_momentum_5: float | None = None
    volume_surprise_5_20: float | None = None
    median_dollar_volume_20: float | None = None
    eligible: bool = False
    residual_positive: bool = False
    volume_confirmed: bool = False
    confirmed: bool = False

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()


THEME_OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "theme_id",
        "event_type",
        "impact_subjects",
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
        "theme_id": {"type": "string", "pattern": "^r23theme_[a-f0-9]{16}$"},
        "event_type": {"type": "string", "minLength": 1, "maxLength": 128},
        "impact_subjects": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_THEME_MEMBERS,
            "uniqueItems": True,
            "items": {"type": "string"},
        },
        "entities": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_THEME_MEMBERS,
            "uniqueItems": True,
            "items": {"type": "string"},
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


@dataclass(frozen=True)
class R23ForwardFreezeResult:
    lock_path: Path
    lock_sha256: str
    epoch_id: str
    anchor_session: date


@dataclass(frozen=True)
class R23ForwardObservationResult:
    status: str
    epoch_id: str
    observation_id: str
    decision_session: date
    action_session: date
    observation_path: Path
    receipt_path: Path
    candidate_count: int
    counted_forward_session: bool
    payload: dict[str, Any]


def freeze_pit_semantic_theme_r23_forward(
    root: Path | None = None,
    *,
    created_at: datetime | None = None,
) -> R23ForwardFreezeResult:
    base = (root or project_root()).resolve()
    lock_path = base / FORWARD_LOCK_PATH
    if lock_path.exists():
        raise ValueError("R23 forward epoch lock already exists")
    if (base / FORWARD_DATA_DIR).exists() or (base / FORWARD_REPORT_DIR).exists():
        raise ValueError("R23 forward evidence exists before the epoch lock")

    specs = load_and_validate_r23_specs(base)
    if _sha256(base / HISTORICAL_LOCK_PATH) != R22_HISTORICAL_LOCK_SHA256:
        raise ValueError("R23 forward requires the immutable R22 historical lock")
    if _sha256(base / HISTORICAL_REPORT_PATH) != R22_HISTORICAL_REPORT_SHA256:
        raise ValueError("R23 forward requires the immutable R22 evaluation report")
    historical = _read_json(_regular_in_root(base, base / HISTORICAL_REPORT_PATH))
    if (
        historical.get("iter_id") != SOURCE_ITER_ID
        or historical.get("decision") != "stop_price_paths"
        or historical.get("workflow_pass") is not True
        or historical.get("research_pass") is not False
        or historical.get("paper_ready_pass") is not False
        or historical.get("transfer_holdout", {}).get("access_count") != 0
    ):
        raise ValueError("R23 historical terminal decision is not the sealed stopped state")

    timestamp = _utc(created_at or datetime.now(UTC))
    anchor_session = latest_completed_us_equity_session(timestamp)
    path_bindings = [_binding(base / path, base) for path in LOCKED_PATHS]
    spec_bindings = [
        {
            **_binding(base / path, base),
            "candidate_id": candidate_id,
            "semantic_sha256": strategy_content_hash(specs[candidate_id]),
        }
        for candidate_id, path in SPEC_PATHS.items()
    ]
    anchor = {
        "schema_version": 1,
        "lock_contract": FORWARD_LOCK_CONTRACT,
        "iter_id": FORWARD_ITER_ID,
        "source_iter_id": SOURCE_ITER_ID,
        "created_at": timestamp.isoformat(),
        "anchor_session": anchor_session.isoformat(),
        "status": "locked_before_first_r23_tier0_observation",
        "paths": path_bindings,
        "specs": spec_bindings,
        "behavior": FORWARD_BEHAVIOR,
        "broker_writes": False,
        "order_authority": False,
    }
    anchor_sha256 = _canonical_hash(anchor)
    lock = {
        **anchor,
        "epoch_anchor_sha256": anchor_sha256,
        "epoch_id": f"r23fwd_{anchor_sha256[:16]}",
    }
    _exclusive_write_json(lock_path, lock)
    return R23ForwardFreezeResult(
        lock_path=lock_path,
        lock_sha256=_sha256(lock_path),
        epoch_id=str(lock["epoch_id"]),
        anchor_session=anchor_session,
    )


def verify_pit_semantic_theme_r23_forward_lock(
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
        or lock.get("iter_id") != FORWARD_ITER_ID
        or lock.get("source_iter_id") != SOURCE_ITER_ID
        or lock.get("epoch_anchor_sha256") != expected_anchor
        or lock.get("epoch_id") != f"r23fwd_{expected_anchor[:16]}"
        or lock.get("behavior") != FORWARD_BEHAVIOR
        or lock.get("broker_writes") is not False
        or lock.get("order_authority") is not False
    ):
        raise ValueError("R23 forward epoch lock identity mismatch")
    created_at = _parse_datetime(lock.get("created_at"), "lock created_at")
    now = _utc(observed_at or datetime.now(UTC))
    if created_at > now:
        raise ValueError("R23 forward epoch lock is future-dated")
    for group in ("paths", "specs"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R23 forward lock group is missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    specs = load_and_validate_r23_specs(base)
    locked_specs = {str(row.get("candidate_id")): row for row in lock["specs"]}
    if set(locked_specs) != set(specs):
        raise ValueError("R23 forward spec coverage mismatch")
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R23 forward semantic spec changed: {candidate_id}")
    return {
        "lock": lock,
        "lock_path": FORWARD_LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "epoch_id": str(lock["epoch_id"]),
        "created_at": created_at,
        "anchor_session": date.fromisoformat(str(lock["anchor_session"])),
    }


def collect_r23_forward_price_panel(
    root: Path,
    *,
    decision_session: date,
    observed_at: datetime,
    feed: str = PRICE_FEED,
    refresh_prices: bool = True,
    price_frames: dict[str, pd.DataFrame] | None = None,
    price_fetcher: Callable[[str], pd.DataFrame] | None = None,
) -> tuple[R11PricePanel, dict[str, Any]]:
    base = root.resolve()
    if feed.lower() != PRICE_FEED:
        raise ValueError("R23 forward price feed is locked to Alpaca IEX")
    historical = load_r22_price_panel(base)
    historical_last = historical.close.index[-1].date()
    fetch_start = datetime.combine(historical_last - timedelta(days=10), datetime.min.time(), UTC)
    rows_by_symbol: dict[str, dict[date, dict[str, float]]] = {}
    source_rows: list[dict[str, Any]] = []
    supplied = price_frames or {}

    for symbol in UNIVERSE:
        if symbol in supplied:
            frame = supplied[symbol].copy()
        elif price_fetcher is not None:
            frame = price_fetcher(symbol).copy()
        else:
            frame = fetch_alpaca_bars(
                base,
                symbol,
                "daily",
                fetch_start,
                observed_at,
                feed.lower(),
                use_cache=not refresh_prices,
                adjustment=PRICE_ADJUSTMENT,
            )
        session_rows = _daily_session_rows(frame, decision_session=decision_session, symbol=symbol)
        if decision_session not in session_rows:
            raise ValueError(
                f"R23 forward live price is missing the latest completed session: "
                f"{symbol} {decision_session}"
            )
        overlap = session_rows.get(historical_last)
        if overlap is not None:
            historical_close = float(historical.close.at[pd.Timestamp(historical_last), symbol])
            relative_gap = abs(overlap["close"] / historical_close - 1.0)
            if relative_gap > LIVE_OVERLAP_TOLERANCE:
                raise ValueError(
                    f"R23 forward live/historical adjustment boundary mismatch: {symbol}"
                )
        rows_by_symbol[symbol] = session_rows
        selected_rows = [
            {"session": session.isoformat(), **values}
            for session, values in sorted(session_rows.items())
            if session >= historical_last
        ]
        source_rows.append(
            {
                "symbol": symbol,
                "feed": feed.lower(),
                "adjustment": PRICE_ADJUSTMENT,
                "source_mode": str(frame.attrs.get("data_source_mode") or "injected"),
                "row_count": len(selected_rows),
                "first_session": selected_rows[0]["session"] if selected_rows else None,
                "last_session": selected_rows[-1]["session"] if selected_rows else None,
                "rows_sha256": _canonical_hash(selected_rows),
                "rows": selected_rows,
            }
        )

    common_new_sessions = set.intersection(
        *[
            {session for session in rows if historical_last < session <= decision_session}
            for rows in rows_by_symbol.values()
        ]
    )
    if decision_session > historical_last and decision_session not in common_new_sessions:
        raise ValueError("R23 forward live panel lacks common latest-session coverage")
    append_sessions = sorted(common_new_sessions)
    fields: dict[str, pd.DataFrame] = {}
    for field_name in ("open", "low", "close", "volume"):
        historical_frame = getattr(historical, field_name).copy()
        if append_sessions:
            append = pd.DataFrame(
                {
                    symbol: [
                        rows_by_symbol[symbol][session][field_name] for session in append_sessions
                    ]
                    for symbol in UNIVERSE
                },
                index=pd.DatetimeIndex(append_sessions),
            )
            historical_frame = pd.concat([historical_frame, append]).sort_index()
        fields[field_name] = historical_frame.loc[: pd.Timestamp(decision_session), list(UNIVERSE)]

    if any(frame.index[-1].date() != decision_session for frame in fields.values()):
        raise ValueError("R23 forward merged panel does not end on the decision session")
    price_snapshot = {
        "schema_version": 1,
        "snapshot_contract": "pit_semantic_theme_r23_forward_price_snapshot_v1",
        "decision_session": decision_session.isoformat(),
        "collected_at": _utc(observed_at).isoformat(),
        "provider": "alpaca",
        "feed": feed.lower(),
        "adjustment": PRICE_ADJUSTMENT,
        "historical_snapshot_last_session": historical_last.isoformat(),
        "appended_sessions": [session.isoformat() for session in append_sessions],
        "symbol_count": len(UNIVERSE),
        "symbols": source_rows,
        "broker_writes": False,
    }
    price_snapshot["content_sha256"] = _canonical_hash(price_snapshot)
    panel = R11PricePanel(
        open=fields["open"],
        low=fields["low"],
        close=fields["close"],
        volume=fields["volume"],
        metadata={
            **historical.metadata,
            "forward_price_snapshot_sha256": price_snapshot["content_sha256"],
            "forward_feed": feed.lower(),
            "forward_adjustment": PRICE_ADJUSTMENT,
            "forward_decision_session": decision_session.isoformat(),
        },
    )
    return panel, price_snapshot


def build_r23_forward_feature_dataset(panel: R11PricePanel) -> pd.DataFrame:
    """Build decision features without calculating any post-development return labels."""
    close = panel.close
    momentum_10 = close / close.shift(RECOVERY_TQQQ_MOMENTUM_SESSIONS) - 1.0
    momentum_20 = close / close.shift(20) - 1.0
    momentum_60 = close / close.shift(60) - 1.0
    momentum_120 = close / close.shift(120) - 1.0
    trend_50 = (
        close
        / close.rolling(
            RECOVERY_QQQ_TREND_SESSIONS,
            min_periods=RECOVERY_QQQ_TREND_SESSIONS,
        ).mean()
        - 1.0
    )
    trend_100 = (
        close
        / close.rolling(
            RECOVERY_BREADTH_TREND_SESSIONS,
            min_periods=RECOVERY_BREADTH_TREND_SESSIONS,
        ).mean()
        - 1.0
    )
    trend_150 = close / close.rolling(150, min_periods=150).mean() - 1.0
    trend_200 = close / close.rolling(200, min_periods=200).mean() - 1.0
    daily_returns = close.pct_change(fill_method=None)
    volatility_20 = daily_returns.rolling(20, min_periods=20).std(ddof=0)
    drawdown_20 = close / close.rolling(20, min_periods=20).max() - 1.0
    drawdown_63 = close / close.rolling(63, min_periods=63).max() - 1.0
    breadth_count = (trend_100.loc[:, TECH_BREADTH_SYMBOLS] > 0.0).sum(axis=1)
    breadth = breadth_count / len(TECH_BREADTH_SYMBOLS)
    rows: list[dict[str, Any]] = []
    d01_route: str | None = None
    d01_held_sessions = 0
    d01_sessions_since_review = 0
    usd_pressure_active = False
    for position in range(200, len(close) - 1):
        decision_session = close.index[position]
        execution_position = position + 1
        execution_session = close.index[execution_position]
        base_risk_on = bool(
            trend_200.iloc[position]["QQQ"] > 0.0 or momentum_120.iloc[position]["QQQ"] > 0.0
        )
        usd_pressure_active, usd_pressure_transition = _advance_usd_pressure(
            active=usd_pressure_active,
            drawdown_20=float(drawdown_20.iloc[position]["USD"]),
            trend_gap_100=float(trend_100.iloc[position]["USD"]),
            momentum_20=float(momentum_20.iloc[position]["USD"]),
        )
        risk_on = bool(base_risk_on and not usd_pressure_active)
        fast_price_recovery = bool(
            trend_50.iloc[position]["QQQ"] > 0.0
            and momentum_10.iloc[position]["TQQQ"] >= RECOVERY_TQQQ_MOMENTUM_MIN
        )
        ordinary_stress_recovery = bool(
            not base_risk_on
            and not usd_pressure_active
            and fast_price_recovery
            and breadth_count.iloc[position] >= RECOVERY_BREADTH_MIN_COUNT
        )
        usd_pressure_recovery = bool(usd_pressure_active and fast_price_recovery)
        recovery_boost = bool(not risk_on and (ordinary_stress_recovery or usd_pressure_recovery))
        (
            d01_route,
            d01_held_sessions,
            d01_sessions_since_review,
            _,
            _,
        ) = _advance_d01_route(
            current_route=d01_route,
            held_sessions=d01_held_sessions,
            sessions_since_review=d01_sessions_since_review,
            risk_on=risk_on,
            recovery_boost=recovery_boost,
        )
        semiconductor_leadership = bool(
            momentum_60.iloc[position]["SMH"] > 0.0
            and trend_150.iloc[position]["SMH"] > 0.0
            and momentum_120.iloc[position]["SMH"] > momentum_120.iloc[position]["QQQ"]
            and momentum_20.iloc[position]["USD"] > 0.0
            and trend_100.iloc[position]["USD"] > 0.0
        )
        rows.append(
            {
                "decision_position": position,
                "decision_session": decision_session.date().isoformat(),
                "execution_position": execution_position,
                "execution_session": execution_session.date().isoformat(),
                "risk_on": risk_on,
                "base_risk_on": base_risk_on,
                "usd_pressure_active": usd_pressure_active,
                "usd_pressure_transition": usd_pressure_transition,
                "fast_price_recovery": fast_price_recovery,
                "ordinary_stress_recovery": ordinary_stress_recovery,
                "usd_pressure_recovery": usd_pressure_recovery,
                "recovery_boost": recovery_boost,
                "semiconductor_leadership": semiconductor_leadership,
                "qqq_momentum_20": float(momentum_20.iloc[position]["QQQ"]),
                "qqq_momentum_120": float(momentum_120.iloc[position]["QQQ"]),
                "qqq_trend_gap_50": float(trend_50.iloc[position]["QQQ"]),
                "qqq_trend_gap_200": float(trend_200.iloc[position]["QQQ"]),
                "tqqq_momentum_10": float(momentum_10.iloc[position]["TQQQ"]),
                "tqqq_momentum_20": float(momentum_20.iloc[position]["TQQQ"]),
                "tqqq_momentum_60": float(momentum_60.iloc[position]["TQQQ"]),
                "tqqq_realized_volatility_20": float(volatility_20.iloc[position]["TQQQ"]),
                "tqqq_drawdown_20": float(drawdown_20.iloc[position]["TQQQ"]),
                "tqqq_drawdown_63": float(drawdown_63.iloc[position]["TQQQ"]),
                "smh_momentum_20": float(momentum_20.iloc[position]["SMH"]),
                "smh_momentum_60": float(momentum_60.iloc[position]["SMH"]),
                "smh_momentum_120": float(momentum_120.iloc[position]["SMH"]),
                "smh_relative_momentum_120": float(
                    momentum_120.iloc[position]["SMH"] - momentum_120.iloc[position]["QQQ"]
                ),
                "smh_trend_gap_150": float(trend_150.iloc[position]["SMH"]),
                "usd_momentum_20": float(momentum_20.iloc[position]["USD"]),
                "usd_momentum_60": float(momentum_60.iloc[position]["USD"]),
                "usd_trend_gap_100": float(trend_100.iloc[position]["USD"]),
                "usd_drawdown_20": float(drawdown_20.iloc[position]["USD"]),
                "tech_breadth_100": float(breadth.iloc[position]),
                "tech_breadth_count_100": int(breadth_count.iloc[position]),
            }
        )
    dataset = pd.DataFrame(rows)
    if dataset.empty or not np.isfinite(dataset.loc[:, MODEL_FEATURES].to_numpy()).all():
        raise ValueError("R23 forward feature dataset is empty or nonfinite")
    return dataset


def _panel_with_action_placeholder(panel: R11PricePanel, action_session: date) -> R11PricePanel:
    action_timestamp = pd.Timestamp(action_session)
    if action_timestamp <= panel.close.index[-1]:
        raise ValueError("R23 forward action placeholder must follow the decision data")
    fields: dict[str, pd.DataFrame] = {}
    for field_name in ("open", "low", "close", "volume"):
        frame = getattr(panel, field_name)
        placeholder = frame.iloc[[-1]].copy()
        placeholder.index = pd.DatetimeIndex([action_timestamp])
        fields[field_name] = pd.concat([frame, placeholder])
    return R11PricePanel(
        open=fields["open"],
        low=fields["low"],
        close=fields["close"],
        volume=fields["volume"],
        metadata={
            **panel.metadata,
            "action_placeholder_session": action_session.isoformat(),
            "action_placeholder_contains_market_data": False,
        },
    )


def _development_panel(panel: R11PricePanel) -> R11PricePanel:
    end = pd.Timestamp(DEVELOPMENT_END)
    fields = {
        field_name: getattr(panel, field_name).loc[:end].copy()
        for field_name in ("open", "low", "close", "volume")
    }
    if fields["close"].index[-1] != end:
        raise ValueError("R23 development-only model panel does not end on its locked boundary")
    return R11PricePanel(
        open=fields["open"],
        low=fields["low"],
        close=fields["close"],
        volume=fields["volume"],
        metadata={**panel.metadata, "forward_model_training_end": DEVELOPMENT_END},
    )


def build_r23_forward_role_targets(
    root: Path,
    *,
    panel: R11PricePanel,
    action_session: date,
    lock_state: dict[str, Any],
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    base = root.resolve()
    load_and_validate_r23_specs(base)
    parent_specs = load_and_validate_r22_specs(base)
    scheduled_panel = _panel_with_action_placeholder(panel, action_session)
    forward_dataset = build_r23_forward_feature_dataset(scheduled_panel)
    d01_frame, d01_records = build_r22_d01_targets(
        scheduled_panel,
        parent_specs["R22D01"],
        forward_dataset,
    )
    d01_record = d01_records[-1]
    if d01_record["execution_session"] != action_session.isoformat():
        raise ValueError("R23 D01 forward target does not cover the action session")

    development = _development_panel(panel)
    development_dataset = build_r22_feature_dataset(development)
    fit_row = development_dataset.iloc[[-1]].copy()
    fit_position = int(fit_row.iloc[0]["decision_position"])
    provenance = {
        "forward_epoch_id": lock_state["epoch_id"],
        "forward_lock_sha256": lock_state["lock_sha256"],
        "training_scope": "locked_development_only",
        "transfer_outcomes_used": False,
    }
    fitted, model_records = _fit_route_models(
        development_dataset,
        fit_row,
        decision_position=fit_position,
        segment_id="R23_FORWARD_FROZEN_DEVELOPMENT_MODEL",
        specs=parent_specs,
        provenance=provenance,
    )
    historical_seeds = _historical_model_route_seeds(base)
    m01_state = historical_seeds["R23M01"]
    m01_route = str(m01_state["m01_selected_route"])
    m01_held_sessions = int(m01_state["m01_held_sessions"])
    m01_sessions_since_review = (
        0 if m01_route == STRESS_ROUTE else (m01_held_sessions - 1) % REVIEW_EVERY_SESSIONS
    )
    tail_exit_sessions = 0
    final_prediction: dict[str, Any] | None = None
    points = forward_dataset[forward_dataset["execution_session"] > DEVELOPMENT_END].sort_values(
        "execution_position"
    )
    if points.empty or str(points.iloc[-1]["execution_session"]) != action_session.isoformat():
        raise ValueError("R23 forward model path does not reach the action session")

    for point in points.to_dict(orient="records"):
        current = pd.DataFrame([point])
        m01_probability = _predict_probability(fitted["R22M01"], current)
        m02_probability = _predict_probability(fitted["R22M02"], current)
        row = current.iloc[0]
        if not bool(row["risk_on"]):
            desired_stress_route = _stress_route_for_row(row)
            m01_switched = m01_route != desired_stress_route
            m01_held_sessions = m01_held_sessions + 1 if m01_route == desired_stress_route else 1
            m01_route = desired_stress_route
            m01_sessions_since_review = 0
            m01_review_due = False
            tail_exit_sessions = 0
        else:
            desired = "TQQQ" if m01_probability >= M01_OVERRIDE_THRESHOLD else "USD100"
            (
                m01_route,
                m01_held_sessions,
                m01_sessions_since_review,
                m01_review_due,
                m01_switched,
            ) = _advance_nonstress_route(
                current_route=m01_route,
                desired_route=desired,
                held_sessions=m01_held_sessions,
                sessions_since_review=m01_sessions_since_review,
            )
            if m02_probability < M02_SURVIVAL_EXIT_THRESHOLD and tail_exit_sessions == 0:
                tail_exit_sessions = TAIL_EXIT_SESSIONS
        m01_target = _target_for_route(m01_route)
        if m01_route != STRESS_ROUTE and tail_exit_sessions > 0:
            m02_target = _target_for_route("QQQ")
            tail_exit_sessions -= 1
            tail_exit_applied = True
        else:
            m02_target = m01_target.copy()
            tail_exit_applied = False
        final_prediction = {
            "decision_session": str(row["decision_session"]),
            "execution_session": str(row["execution_session"]),
            "m01_tqqq100_probability": m01_probability,
            "m02_survival_probability": m02_probability,
            "m01_selected_route": m01_route,
            "m01_held_sessions": m01_held_sessions,
            "m01_sessions_since_review": m01_sessions_since_review,
            "m01_review_due": m01_review_due,
            "m01_switched": m01_switched,
            "tail_exit_applied": tail_exit_applied,
            "risk_on": bool(row["risk_on"]),
            "base_risk_on": bool(row["base_risk_on"]),
            "usd_pressure_active": bool(row["usd_pressure_active"]),
            "usd_pressure_transition": str(row["usd_pressure_transition"]),
            "fast_price_recovery": bool(row["fast_price_recovery"]),
            "ordinary_stress_recovery": bool(row["ordinary_stress_recovery"]),
            "usd_pressure_recovery": bool(row["usd_pressure_recovery"]),
            "recovery_boost": bool(row["recovery_boost"]),
            "model_ids": {
                "R23M01": fitted["R22M01"].model_id,
                "R23M02": fitted["R22M02"].model_id,
            },
            "source_model_candidate_ids": {
                "R23M01": "R22M01",
                "R23M02": "R22M02",
            },
        }
    assert final_prediction is not None

    d01_weights = _normalized_weights(d01_frame.iloc[-1].to_dict())
    m01_weights = _normalized_weights(m01_target.to_dict())
    m02_weights = _normalized_weights(m02_target.to_dict())
    role_targets = {
        "R23D01": d01_weights,
        "R23D02": d01_weights.copy(),
        "R23M01": m01_weights,
        "R23M02": m02_weights,
        "R23L01": d01_weights.copy(),
        "R23C01": m01_weights.copy(),
        "R23F01": m01_weights.copy(),
        "R23P01": m01_weights.copy(),
    }
    if role_targets["R23F01"] != role_targets["R23M01"]:
        raise ValueError("R23 F01 is not the exact M01 target fallback")
    if role_targets["R23D02"] != role_targets["R23D01"]:
        raise ValueError("R23 D02 zero-budget target differs from D01")
    diagnostics = {
        "schema_version": 1,
        "training_scope": "locked_development_only",
        "training_end": DEVELOPMENT_END,
        "transfer_outcomes_used": False,
        "research_promotion_credit": False,
        "model_records": model_records,
        "model_reuse_source_iteration": SOURCE_ITER_ID,
        "current_prediction": final_prediction,
        "d01_route": d01_record,
        "role_target_sources": {
            "R23D01": "R23D01",
            "R23D02": "R23D01_zero_semantic_budget",
            "R23M01": "R23M01_observation_only",
            "R23M02": "R23M02_observation_only",
            "R23L01": "R23D02_then_R23D01_zero_semantic_budget",
            "R23C01": "R23M01_zero_semantic_budget",
            "R23F01": "R23M01_exact_missing_modality_fallback",
            "R23P01": "R23M01_placebo_diagnostic_only",
        },
        "broker_writes": False,
        "order_authority": False,
    }
    return role_targets, diagnostics


def _events_first_seen_in_epoch(
    events: Iterable[EventRecord],
    *,
    epoch_started_at: datetime,
) -> list[EventRecord]:
    epoch_start = _utc(epoch_started_at)
    return [
        event for event in events if _utc(event.first_seen_at or event.fetched_at) >= epoch_start
    ]


def build_r23_forward_source_packets(
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
            raise ValueError("R23 forward accepts only live forward Alpaca News records")
        fetched_at = _utc(event.fetched_at)
        visible_at = _utc(event.visible_at or event.fetched_at)
        if fetched_at < epoch_start or visible_at < epoch_start:
            raise ValueError("R23 forward event predates the locked collector epoch")
        if visible_at > observed + timedelta(minutes=1):
            raise ValueError("R23 forward event is future-dated")
        provider_id = str(event.raw.get("provider_id") or "").strip()
        if not provider_id or not event.version_id:
            raise ValueError("R23 Alpaca News record lacks provider version identity")
        key = f"news.alpaca:{provider_id}:{event.version_id}"
        grouped.setdefault(key, []).append(event)

    packets: list[ForwardSourcePacket] = []
    for source_version_key, rows in sorted(grouped.items()):
        first = sorted(rows, key=lambda row: (row.symbol, row.id))[0]
        title = first.title.strip() or "Untitled Alpaca News record"
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
            "title": title,
            "summary": first.summary.strip(),
            "source_url": first.url,
            "published_at": _utc(first.published_at).isoformat(),
            "rights_scope": first.rights_scope,
            "revision_id": first.revision_id,
        }
        input_hash = _canonical_hash(source_payload)
        packets.append(
            ForwardSourcePacket(
                schema_version=1,
                packet_contract=SOURCE_PACKET_CONTRACT,
                packet_id=f"r23pkt_{input_hash[:24]}",
                epoch_id=epoch_id,
                source="news.alpaca",
                source_version_key=source_version_key,
                provider_article_id=str(first.raw["provider_id"]),
                version_id=str(first.version_id),
                symbols=sorted(provider_symbols),
                title=title,
                summary=first.summary.strip(),
                source_url=first.url,
                published_at=first.published_at,
                fetched_at=min(_utc(row.fetched_at) for row in rows),
                first_seen_at=min(_utc(row.first_seen_at or row.fetched_at) for row in rows),
                visible_at=max(_utc(row.visible_at or row.fetched_at) for row in rows),
                input_hash=input_hash,
                rights_scope=first.rights_scope,
                revision_id=first.revision_id,
                acquisition_mode="live_api_forward_only",
                dedupe_key=source_version_key,
            )
        )
    return sorted(packets, key=lambda packet: (packet.published_at, packet.packet_id))


def build_r23_semantic_diagnostics(
    root: Path,
    *,
    packets: list[ForwardSourcePacket],
    packet_history: list[ForwardSourcePacket] | None = None,
    decision_session: date | None = None,
    observed_at: datetime,
    backend_name: str,
    model: str | None,
    backend: ThemeBackend | None,
    feed: str = PRICE_FEED,
    refresh_prices: bool = True,
    price_frames: dict[str, pd.DataFrame] | None = None,
    price_fetcher: Callable[[str], pd.DataFrame] | None = None,
) -> dict[str, Any]:
    base = root.resolve()
    observed = _utc(observed_at)
    decision = decision_session or latest_completed_us_equity_session(observed)
    history_by_key = {
        packet.source_version_key: packet for packet in [*(packet_history or []), *packets]
    }
    history = sorted(history_by_key.values(), key=lambda row: (row.visible_at, row.packet_id))
    selected = _select_r23_theme_packets(history, decision_session=decision, observed_at=observed)
    selected_symbols = sorted(
        {symbol for packet in selected for symbol in packet.symbols if _is_company_symbol(symbol)}
    )
    price_features, price_inputs, price_errors, session_dates = _load_semantic_price_confirmations(
        base,
        symbols=selected_symbols,
        decision_session=decision,
        observed_at=observed,
        feed=feed,
        refresh_prices=refresh_prices,
        price_frames=price_frames,
        price_fetcher=price_fetcher,
    )
    attention = _session_attention_acceleration(
        history,
        decision_session=decision,
        session_dates=session_dates,
    )
    eligible_symbols = {
        symbol for symbol, row in price_features.items() if row.status == "ok" and row.eligible
    }
    deterministic = [
        _deterministic_theme(
            packet,
            price_features=price_features,
            attention=attention,
            eligible_symbols=eligible_symbols,
            decision_session=decision,
            session_dates=session_dates,
        )
        for packet in selected
    ]
    prompt_path = _regular_in_root(base, base / PROMPT_PATH)
    prompt = prompt_path.read_text(encoding="utf-8")
    prompt_hash = _sha256(prompt_path)
    selected_model = model or default_openai_model()
    parameters_hash = _canonical_hash(
        {
            "backend": backend_name,
            "model": selected_model,
            "prompt_hash": prompt_hash,
            "output_schema_sha256": _canonical_hash(THEME_OUTPUT_SCHEMA),
            "live_llm_in_order_path": False,
        }
    )
    selected_backend = backend
    backend_error: str | None = None
    if selected_backend is None:
        if backend_name == "openai" and not openai_api_key():
            backend_error = "OPENAI_API_KEY_not_configured"
        else:
            try:
                selected_backend = get_backend(backend_name)
            except Exception as exc:
                backend_error = _safe_error(exc)

    llm_results = []
    deterministic_by_packet = {row["packet_id"]: row for row in deterministic}
    for packet in selected:
        deterministic_theme = deterministic_by_packet[packet.packet_id]
        entities = list(deterministic_theme["eligible_members"])
        required_theme_id = f"r23theme_{packet.input_hash[:16]}"
        input_payload = {
            "required_theme_id": required_theme_id,
            "allowed_entities": entities,
            "allowed_relationship_types": list(ALLOWED_RELATIONSHIPS),
            "required_minimum_entities": MIN_CONFIRMED_MEMBERS,
            "llm_role": "structured_extraction_only_no_weights_or_orders",
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
        record = {
            "packet_id": packet.packet_id,
            "input_hash": packet.input_hash,
            "input_payload_sha256": _canonical_hash(input_payload),
            "allowed_entities": entities,
            "prompt_hash": prompt_hash,
            "model": selected_model,
            "backend": backend_name,
            "model_parameters_hash": parameters_hash,
            "required_theme_id": required_theme_id,
        }
        if len(entities) < MIN_CONFIRMED_MEMBERS:
            llm_results.append(
                {
                    **record,
                    "status": "fallback",
                    "structured_output": None,
                    "structured_output_hash": None,
                    "gate_evaluation": _empty_semantic_gate(
                        deterministic_theme,
                        reason="fewer_than_two_eligible_company_entities",
                    ),
                    "error": "fewer_than_two_eligible_company_entities",
                }
            )
            continue
        if selected_backend is None:
            llm_results.append(
                {
                    **record,
                    "status": "fallback",
                    "structured_output": None,
                    "structured_output_hash": None,
                    "gate_evaluation": _empty_semantic_gate(
                        deterministic_theme,
                        reason="LLM_backend_unavailable",
                    ),
                    "error": backend_error or "LLM_backend_unavailable",
                }
            )
            continue
        try:
            raw = selected_backend.infer(
                model=selected_model,
                prompt=prompt,
                input_payload=input_payload,
                output_schema=THEME_OUTPUT_SCHEMA,
            )
            factor = StructuredThemeFactor.model_validate(raw)
            _validate_llm_factor(factor, packet, entities, required_theme_id)
            payload = factor.model_dump(mode="json")
            gate_evaluation = _llm_semantic_gate(factor, deterministic_theme)
            llm_results.append(
                {
                    **record,
                    "status": "valid",
                    "structured_output": payload,
                    "structured_output_hash": _canonical_hash(payload),
                    "gate_evaluation": gate_evaluation,
                    "error": None,
                }
            )
        except Exception as exc:
            error = _safe_error(exc)
            if _is_authentication_error(exc):
                selected_backend = None
                backend_error = error
            llm_results.append(
                {
                    **record,
                    "status": "fallback",
                    "structured_output": None,
                    "structured_output_hash": None,
                    "gate_evaluation": _empty_semantic_gate(
                        deterministic_theme,
                        reason="structured_output_invalid_or_unbound",
                    ),
                    "error": error,
                }
            )
    return {
        "schema_version": 1,
        "semantic_contract": "pit_semantic_theme_r23_semantic_diagnostics_v1",
        "selected_packet_count": len(selected),
        "selected_packet_ids": [packet.packet_id for packet in selected],
        "dynamic_company_symbol_count": len(selected_symbols),
        "dynamic_company_symbols": selected_symbols,
        "price_confirmation": {
            "source": "alpaca",
            "feed": feed,
            "decision_session": decision.isoformat(),
            "errors": price_errors,
            "features": {
                symbol: row.model_dump(mode="json")
                for symbol, row in sorted(price_features.items())
            },
            "input_row_count": len(price_inputs),
            "input_rows_sha256": _canonical_hash(price_inputs),
            "input_rows": price_inputs,
        },
        "attention_acceleration": attention,
        "deterministic_themes": deterministic,
        "admitted_deterministic_theme_count": sum(
            row["state"] == "active" for row in deterministic
        ),
        "llm_materialization": {
            "backend": backend_name,
            "model": selected_model,
            "prompt_path": PROMPT_PATH.as_posix(),
            "prompt_hash": prompt_hash,
            "model_parameters_hash": parameters_hash,
            "valid_factor_count": sum(row["status"] == "valid" for row in llm_results),
            "admitted_factor_count": sum(
                row.get("gate_evaluation", {}).get("admitted") is True for row in llm_results
            ),
            "results": llm_results,
        },
        "gate_contract": {
            "gate_id": "multi_entity_economic_diffusion_gate_v1",
            "minimum_investable_company_entities": MIN_CONFIRMED_MEMBERS,
            "attention_windows_sessions": [
                ATTENTION_SHORT_SESSIONS,
                ATTENTION_LONG_SESSIONS,
            ],
            "residual_momentum_sessions": RESIDUAL_MOMENTUM_SESSIONS,
            "volume_surprise_windows_sessions": [
                VOLUME_SHORT_SESSIONS,
                VOLUME_BASELINE_SESSIONS,
            ],
            "volume_surprise_ratio_min": MIN_VOLUME_SURPRISE,
            "minimum_positive_member_breadth": MIN_POSITIVE_MEMBER_BREADTH,
            "minimum_active_sessions": 3,
            "maximum_active_sessions": 20,
            "price_can_create_relationship": False,
        },
        "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
        "research_pass": False,
        "llm_contribution_pass": False,
        "broker_writes": False,
        "order_authority": False,
    }


def observe_pit_semantic_theme_r23_forward(
    root: Path | None = None,
    *,
    backend_name: str = "openai",
    model: str | None = None,
    news_limit: int = 50,
    collect_news: bool = True,
    feed: str = PRICE_FEED,
    refresh_prices: bool = True,
    observed_at: datetime | None = None,
    events: list[EventRecord] | None = None,
    backend: ThemeBackend | None = None,
    price_frames: dict[str, pd.DataFrame] | None = None,
    price_fetcher: Callable[[str], pd.DataFrame] | None = None,
) -> R23ForwardObservationResult:
    base = (root or project_root()).resolve()
    started_at = _utc(observed_at or datetime.now(UTC))
    lock_state = verify_pit_semantic_theme_r23_forward_lock(base, observed_at=started_at)
    if not 1 <= news_limit <= 1_000:
        raise ValueError("news_limit must be between 1 and 1000")
    decision_session = latest_completed_us_equity_session(started_at)
    action_session = next_us_equity_session(decision_session)
    observation_id = decision_session.strftime("%Y%m%d")
    final_dir = base / FORWARD_DATA_DIR / "observations" / observation_id

    with _forward_writer_lock(base):
        if final_dir.exists():
            receipt = _verify_observation_receipt(base, final_dir / "receipt.json", lock_state)
            _rebuild_forward_projections(base, lock_state)
            return _result_from_receipt(base, final_dir, receipt)

        collected: list[EventRecord] = []
        news_error: str | None = None
        if events is not None:
            collected = events
        elif collect_news:
            try:
                collected = fetch_capability_events(
                    "alpaca_news",
                    base,
                    symbols=None,
                    offline=False,
                    limit=news_limit,
                    sort="DESC",
                )
            except Exception as exc:
                news_error = _safe_error(exc)
        materialized_at = _utc(observed_at or datetime.now(UTC))
        epoch_collected = _events_first_seen_in_epoch(
            collected,
            epoch_started_at=lock_state["created_at"],
        )
        packets = build_r23_forward_source_packets(
            epoch_collected,
            epoch_id=lock_state["epoch_id"],
            epoch_started_at=lock_state["created_at"],
            observed_at=materialized_at,
        )
        prior_source_keys = _published_source_version_keys(base)
        new_packets = [
            packet for packet in packets if packet.source_version_key not in prior_source_keys
        ]
        published_packets = _published_source_packets(base)
        packet_history_by_key = {
            packet.source_version_key: packet for packet in [*published_packets, *new_packets]
        }
        packet_history = sorted(
            packet_history_by_key.values(), key=lambda row: (row.visible_at, row.packet_id)
        )
        panel, price_snapshot = collect_r23_forward_price_panel(
            base,
            decision_session=decision_session,
            observed_at=materialized_at,
            feed=feed,
            refresh_prices=refresh_prices,
            price_frames=price_frames,
            price_fetcher=price_fetcher,
        )
        role_targets, model_diagnostics = build_r23_forward_role_targets(
            base,
            panel=panel,
            action_session=action_session,
            lock_state=lock_state,
        )
        semantic = build_r23_semantic_diagnostics(
            base,
            packets=new_packets,
            packet_history=packet_history,
            decision_session=decision_session,
            observed_at=materialized_at,
            backend_name=backend_name,
            model=model,
            backend=backend,
            feed=feed,
            refresh_prices=refresh_prices,
            price_frames=price_frames,
            price_fetcher=price_fetcher,
        )
        selected_packet_ids = set(semantic["selected_packet_ids"])
        bound_source_packets = [
            packet for packet in packet_history if packet.packet_id in selected_packet_ids
        ]
        semantic["collection"] = {
            "enabled": collect_news or events is not None,
            "collected_event_count": len(collected),
            "epoch_eligible_event_count": len(epoch_collected),
            "pre_epoch_event_count": len(collected) - len(epoch_collected),
            "new_source_packet_count": len(new_packets),
            "bound_source_packet_count": len(bound_source_packets),
            "error": news_error,
        }
        specs = load_and_validate_r23_specs(base)
        previous_targets = _latest_role_targets(base)
        account = _account_snapshot(base, role_targets)
        counted_forward_session = decision_session > lock_state["anchor_session"]
        role_payloads: dict[str, dict[str, Any]] = {}
        for candidate_id, weights in role_targets.items():
            spec = specs[candidate_id]
            strategy_name = spec.name
            previous = previous_targets.get(candidate_id, _zero_weights())
            role_status = _role_status(candidate_id, semantic)
            target_payload = _target_payload(
                candidate_id=candidate_id,
                strategy_name=strategy_name,
                spec_hash=strategy_content_hash(spec),
                epoch_id=lock_state["epoch_id"],
                observation_id=observation_id,
                decision_session=decision_session,
                action_session=action_session,
                generated_at=materialized_at,
                weights=weights,
                role_status=role_status,
                model_diagnostics=model_diagnostics,
                price_snapshot=price_snapshot,
            )
            intents_payload = _intents_payload(
                candidate_id=candidate_id,
                strategy_name=strategy_name,
                spec_hash=strategy_content_hash(spec),
                epoch_id=lock_state["epoch_id"],
                observation_id=observation_id,
                decision_session=decision_session,
                action_session=action_session,
                generated_at=materialized_at,
                previous_weights=previous,
                target_weights=weights,
                target_sha256=str(target_payload["target_sha256"]),
            )
            reconciliation = account["by_candidate"][candidate_id]
            execution_payload = _execution_observation_payload(
                candidate_id=candidate_id,
                strategy_name=strategy_name,
                spec_hash=strategy_content_hash(spec),
                epoch_id=lock_state["epoch_id"],
                observation_id=observation_id,
                decision_session=decision_session,
                action_session=action_session,
                generated_at=materialized_at,
                role_status=role_status,
                target_payload=target_payload,
                intents_payload=intents_payload,
                reconciliation=reconciliation,
                counted_forward_session=counted_forward_session,
            )
            role_payloads[candidate_id] = {
                "target": target_payload,
                "intents": intents_payload,
                "execution": execution_payload,
            }

        observation = {
            "schema_version": 1,
            "observation_contract": OBSERVATION_CONTRACT,
            "iter_id": FORWARD_ITER_ID,
            "source_iter_id": ITER_ID,
            "epoch_id": lock_state["epoch_id"],
            "observation_id": observation_id,
            "collected_at": materialized_at.isoformat(),
            "decision_session": decision_session.isoformat(),
            "action_session": action_session.isoformat(),
            "epoch_anchor_session": lock_state["anchor_session"].isoformat(),
            "counted_forward_session": counted_forward_session,
            "candidate_ids": list(SPEC_PATHS),
            "candidate_count": len(role_payloads),
            "source_packet_count": len(bound_source_packets),
            "new_source_packet_count": len(new_packets),
            "deterministic_theme_count": len(semantic["deterministic_themes"]),
            "valid_llm_factor_count": semantic["llm_materialization"]["valid_factor_count"],
            "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
            "account_reconciliation_status": account["status"],
            "workflow_pass": True,
            "research_pass": False,
            "llm_contribution_pass": False,
            "paper_ready_pass": False,
            "tier0_observation_complete": set(role_payloads) == set(SPEC_PATHS),
            "observation_only": True,
            "broker_writes": False,
            "order_authority": False,
            "limitations": [
                "R23 historical research_pass remains false",
                "current targets are observation artifacts and not broker orders",
                "semantic stock budget remains zero until matched forward lift exists",
                "the bootstrap session at or before the epoch anchor is not forward-counted",
                "Alpaca IEX is not consolidated SIP market data",
            ],
        }
        receipt = _publish_observation(
            base,
            final_dir=final_dir,
            lock_state=lock_state,
            observation=observation,
            price_snapshot=price_snapshot,
            source_packets=bound_source_packets,
            semantic=semantic,
            model_diagnostics=model_diagnostics,
            account=account,
            role_payloads=role_payloads,
        )
        _rebuild_forward_projections(base, lock_state)
        return _result_from_receipt(base, final_dir, receipt)


def _publish_observation(
    root: Path,
    *,
    final_dir: Path,
    lock_state: dict[str, Any],
    observation: dict[str, Any],
    price_snapshot: dict[str, Any],
    source_packets: list[ForwardSourcePacket],
    semantic: dict[str, Any],
    model_diagnostics: dict[str, Any],
    account: dict[str, Any],
    role_payloads: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    final_dir.parent.mkdir(parents=True, exist_ok=True)
    stage = final_dir.parent / f".{final_dir.name}.staging-{os.getpid()}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    try:
        common = {
            "observation.json": observation,
            "price-snapshot.json": price_snapshot,
            "source-packets.json": {
                "schema_version": 1,
                "epoch_id": lock_state["epoch_id"],
                "packets": [packet.model_dump(mode="json") for packet in source_packets],
                "broker_writes": False,
            },
            "semantic-diagnostics.json": semantic,
            "model-diagnostics.json": model_diagnostics,
            "account-reconciliation.json": account,
        }
        for name, payload in common.items():
            _write_json_atomic(stage / name, payload)
        role_bindings: dict[str, dict[str, Any]] = {}
        for candidate_id, payloads in role_payloads.items():
            role_dir = stage / "roles" / candidate_id.lower()
            role_dir.mkdir(parents=True)
            paths = {
                "target": role_dir / "target-weights.json",
                "intents": role_dir / "rebalance-intents.json",
                "execution": role_dir / "execution-observation.json",
            }
            for key, path in paths.items():
                _write_json_atomic(path, payloads[key])
            role_bindings[candidate_id] = {
                key: _staged_binding(path, final_dir / path.relative_to(stage), root)
                for key, path in paths.items()
            }
        common_bindings = {
            name.removesuffix(".json").replace("-", "_"): _staged_binding(
                stage / name,
                final_dir / name,
                root,
            )
            for name in common
        }
        receipt = {
            "schema_version": 1,
            "receipt_contract": RECEIPT_CONTRACT,
            "iter_id": FORWARD_ITER_ID,
            "epoch_id": lock_state["epoch_id"],
            "observation_id": observation["observation_id"],
            "decision_session": observation["decision_session"],
            "action_session": observation["action_session"],
            "published_at": observation["collected_at"],
            "counted_forward_session": observation["counted_forward_session"],
            "lock": {
                "path": lock_state["lock_path"],
                "sha256": lock_state["lock_sha256"],
            },
            "artifacts": common_bindings,
            "roles": role_bindings,
            "candidate_ids": list(role_payloads),
            "observation_only": True,
            "broker_writes": False,
            "order_authority": False,
        }
        _write_json_atomic(stage / "receipt.json", receipt)
        _verify_staged_receipt(root, stage / "receipt.json", receipt)
        os.replace(stage, final_dir)
        _fsync_directory(final_dir.parent)
        return _verify_observation_receipt(root, final_dir / "receipt.json", lock_state)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def _rebuild_forward_projections(
    root: Path,
    lock_state: dict[str, Any] | None = None,
) -> None:
    state = lock_state or verify_pit_semantic_theme_r23_forward_lock(root)
    observations_root = root / FORWARD_DATA_DIR / "observations"
    receipts: list[tuple[Path, dict[str, Any]]] = []
    if observations_root.exists():
        for observation_dir in sorted(observations_root.iterdir()):
            if not observation_dir.is_dir() or observation_dir.name.startswith("."):
                continue
            receipt_path = observation_dir / "receipt.json"
            receipts.append((receipt_path, _verify_observation_receipt(root, receipt_path, state)))
    if not receipts:
        return
    by_session: dict[str, tuple[Path, dict[str, Any]]] = {}
    for receipt_path, receipt in receipts:
        session = str(receipt["decision_session"])
        if session in by_session:
            raise ValueError(f"R23 forward has duplicate decision-session receipts: {session}")
        by_session[session] = (receipt_path, receipt)
    ordered = [by_session[key] for key in sorted(by_session)]
    latest_path, latest = ordered[-1]
    report_dir = root / FORWARD_REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    execution_dir = root / "reports/execution"
    execution_dir.mkdir(parents=True, exist_ok=True)
    for role_bindings in latest["roles"].values():
        target = _read_json(_verify_binding(root, role_bindings["target"]))
        strategy_name = str(target["strategy_name"])
        projection_names = {
            "target": f"{strategy_name}-target-weights.json",
            "intents": f"{strategy_name}-rebalance-intents.json",
            "execution": f"{strategy_name}-execution-observation.json",
        }
        for key, filename in projection_names.items():
            source = _verify_binding(root, role_bindings[key])
            _write_bytes_atomic(execution_dir / filename, source.read_bytes())
    latest_observation = _read_json(_verify_binding(root, latest["artifacts"]["observation"]))
    latest_observation["immutable_receipt"] = _binding(latest_path, root)
    _write_json_atomic(report_dir / "latest-observation.json", latest_observation)
    ledger = []
    for receipt_path, receipt in ordered:
        ledger.append(
            {
                "schema_version": 1,
                "epoch_id": state["epoch_id"],
                "observation_id": receipt["observation_id"],
                "decision_session": receipt["decision_session"],
                "action_session": receipt["action_session"],
                "published_at": receipt["published_at"],
                "counted_forward_session": receipt["counted_forward_session"],
                "receipt": _binding(receipt_path, root),
                "candidate_ids": receipt["candidate_ids"],
                "observation_only": True,
                "broker_writes": False,
            }
        )
    _write_jsonl_atomic(report_dir / "decisions.jsonl", ledger)
    counted = [row for row in ledger if row["counted_forward_session"]]
    readiness = {
        "schema_version": 1,
        "readiness_contract": "pit_semantic_theme_r23_tier0_readiness_v1",
        "epoch_id": state["epoch_id"],
        "epoch_anchor_session": state["anchor_session"].isoformat(),
        "candidate_ids": list(SPEC_PATHS),
        "candidate_count": len(SPEC_PATHS),
        "observation_count": len(ledger),
        "valid_forward_session_count": len(counted),
        "required_stable_sessions": FORWARD_BEHAVIOR["stable_tier0_sessions"],
        "tier0_technical_pass": len(latest["roles"]) == len(SPEC_PATHS),
        "tier0_stability_pass": len(counted) >= FORWARD_BEHAVIOR["stable_tier0_sessions"],
        "latest_decision_session": latest["decision_session"],
        "latest_receipt": _binding(latest_path, root),
        "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
        "research_pass": False,
        "paper_ready_pass": False,
        "observation_only": True,
        "broker_writes": False,
        "order_authority": False,
    }
    _write_json_atomic(report_dir / "readiness.json", readiness)


def _target_payload(
    *,
    candidate_id: str,
    strategy_name: str,
    spec_hash: str,
    epoch_id: str,
    observation_id: str,
    decision_session: date,
    action_session: date,
    generated_at: datetime,
    weights: dict[str, float],
    role_status: dict[str, Any],
    model_diagnostics: dict[str, Any],
    price_snapshot: dict[str, Any],
) -> dict[str, Any]:
    target_sha256 = _canonical_hash(weights)
    route = _candidate_route(candidate_id, weights, model_diagnostics)
    rows = [
        {
            "signal_session": decision_session.isoformat(),
            "rebalance_session": action_session.isoformat(),
            "rebalance_id": f"{strategy_name}:{action_session.isoformat()}",
            "symbol": symbol,
            "target_weight": weight,
            "selected": weight > 0.0,
            "state": route,
            "source": "pit_semantic_theme_r23_forward",
            "holding_mode": "open_to_open_until_next_target",
            "time_rule": "regular_session_open_observation",
            "reference_evaluable": False,
        }
        for symbol, weight in weights.items()
    ]
    return {
        "schema_version": 1,
        "target_contract": TARGET_CONTRACT,
        "iter_id": FORWARD_ITER_ID,
        "candidate_id": candidate_id,
        "strategy_name": strategy_name,
        "spec_hash": spec_hash,
        "epoch_id": epoch_id,
        "observation_id": observation_id,
        "generated_at": generated_at.isoformat(),
        "signal_session": decision_session.isoformat(),
        "rebalance_session": action_session.isoformat(),
        "route": route,
        "target_weights": rows,
        "weights": weights,
        "target_sha256": target_sha256,
        "gross_exposure": math.fsum(weights.values()),
        "role_status": role_status,
        "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
        "data_profile": {
            "provider": "alpaca",
            "feed": price_snapshot["feed"],
            "adjustment": price_snapshot["adjustment"],
            "decision_session": decision_session.isoformat(),
            "price_snapshot_sha256": price_snapshot["content_sha256"],
            "strict_current_session": True,
        },
        "parity_check": {
            "status": "pass",
            "checks": {
                "weight_sum": math.fsum(weights.values()),
                "nonnegative": all(value >= 0.0 for value in weights.values()),
                "f01_exact_m01": True,
                "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
            },
            "warnings": [
                "draft manual_signal spec",
                "Tier 0 observation only",
                "no broker order submission",
            ],
        },
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "observation_only": True,
        "broker_writes": False,
        "order_authority": False,
    }


def _intents_payload(
    *,
    candidate_id: str,
    strategy_name: str,
    spec_hash: str,
    epoch_id: str,
    observation_id: str,
    decision_session: date,
    action_session: date,
    generated_at: datetime,
    previous_weights: dict[str, float],
    target_weights: dict[str, float],
    target_sha256: str,
) -> dict[str, Any]:
    intents = []
    for symbol in UNIVERSE:
        prior = float(previous_weights.get(symbol, 0.0))
        target = float(target_weights.get(symbol, 0.0))
        delta = target - prior
        side = "buy" if delta > 1e-12 else "sell" if delta < -1e-12 else "hold"
        intents.append(
            {
                "rebalance_id": f"{strategy_name}:{action_session.isoformat()}",
                "signal_session": decision_session.isoformat(),
                "rebalance_session": action_session.isoformat(),
                "symbol": symbol,
                "from_weight": prior,
                "to_weight": target,
                "delta_weight": delta,
                "side": side,
                "requires_order": abs(delta) > 1e-12,
                "intent_type": "set_target_weight_observation",
                "time_rule": "regular_session_open_observation",
                "order_authorized": False,
            }
        )
    return {
        "schema_version": 1,
        "intent_contract": INTENT_CONTRACT,
        "iter_id": FORWARD_ITER_ID,
        "candidate_id": candidate_id,
        "strategy_name": strategy_name,
        "spec_hash": spec_hash,
        "epoch_id": epoch_id,
        "observation_id": observation_id,
        "generated_at": generated_at.isoformat(),
        "signal_session": decision_session.isoformat(),
        "rebalance_session": action_session.isoformat(),
        "target_sha256": target_sha256,
        "rebalance_intents": intents,
        "order_required_intent_count": sum(row["requires_order"] for row in intents),
        "observation_only": True,
        "broker_writes": False,
        "order_authority": False,
    }


def _execution_observation_payload(
    *,
    candidate_id: str,
    strategy_name: str,
    spec_hash: str,
    epoch_id: str,
    observation_id: str,
    decision_session: date,
    action_session: date,
    generated_at: datetime,
    role_status: dict[str, Any],
    target_payload: dict[str, Any],
    intents_payload: dict[str, Any],
    reconciliation: dict[str, Any],
    counted_forward_session: bool,
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "execution_observation_contract": EXECUTION_OBSERVATION_CONTRACT,
        "iter_id": FORWARD_ITER_ID,
        "candidate_id": candidate_id,
        "strategy_name": strategy_name,
        "spec_hash": spec_hash,
        "epoch_id": epoch_id,
        "observation_id": observation_id,
        "generated_at": generated_at.isoformat(),
        "signal_session": decision_session.isoformat(),
        "rebalance_session": action_session.isoformat(),
        "counted_forward_session": counted_forward_session,
        "target_sha256": target_payload["target_sha256"],
        "order_required_intent_count": intents_payload["order_required_intent_count"],
        "role_status": role_status,
        "account_reconciliation": reconciliation,
        "execution_substate": "observation_only",
        "submission_attempted": False,
        "submitted_order_count": 0,
        "observation_only": True,
        "broker_writes": False,
        "order_authority": False,
    }


def _account_snapshot(
    root: Path,
    role_targets: dict[str, dict[str, float]],
) -> dict[str, Any]:
    account_path = root / "reports/paper/account.json"
    positions_path = root / "reports/paper/positions.json"
    if not account_path.exists() or not positions_path.exists():
        return {
            "schema_version": 1,
            "status": "not_available",
            "account": None,
            "positions": None,
            "by_candidate": {
                candidate_id: {
                    "status": "not_available",
                    "broker_read_only": True,
                    "broker_writes": False,
                }
                for candidate_id in role_targets
            },
            "broker_read_only": True,
            "broker_writes": False,
        }
    account = _read_json(_regular_in_root(root, account_path))
    positions = _read_json(_regular_in_root(root, positions_path))
    if account.get("paper") is not True or positions.get("paper") is not True:
        raise ValueError("R23 account reconciliation requires paper-only snapshots")
    equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
    if not math.isfinite(equity) or equity <= 0.0:
        raise ValueError("R23 paper account equity is invalid")
    actual_weights: dict[str, float] = {}
    position_rows = positions.get("positions") or []
    for row in position_rows:
        symbol = str(row.get("symbol") or "").upper()
        market_value = float(row.get("market_value") or 0.0)
        if symbol and math.isfinite(market_value):
            actual_weights[symbol] = actual_weights.get(symbol, 0.0) + market_value / equity
    by_candidate = {}
    overall = "ok"
    for candidate_id, target in role_targets.items():
        symbols = sorted(set(actual_weights) | set(target))
        drift = {
            symbol: actual_weights.get(symbol, 0.0) - target.get(symbol, 0.0) for symbol in symbols
        }
        max_abs_drift = max((abs(value) for value in drift.values()), default=0.0)
        status = "ok" if max_abs_drift <= ACCOUNT_WEIGHT_TOLERANCE else "warning"
        if status != "ok":
            overall = "warning"
        by_candidate[candidate_id] = {
            "status": status,
            "equity": equity,
            "actual_weights": actual_weights,
            "target_weights": target,
            "weight_drift": drift,
            "max_absolute_weight_drift": max_abs_drift,
            "weight_tolerance": ACCOUNT_WEIGHT_TOLERANCE,
            "position_count": len(position_rows),
            "paper_position_conflict": max_abs_drift > ACCOUNT_WEIGHT_TOLERANCE,
            "broker_read_only": True,
            "broker_writes": False,
        }
    return {
        "schema_version": 1,
        "status": overall,
        "account": _binding(account_path, root),
        "positions": _binding(positions_path, root),
        "account_generated_at": account.get("generated_at"),
        "positions_generated_at": positions.get("generated_at"),
        "paper": True,
        "equity": equity,
        "positions_summary": [
            {
                "symbol": str(row.get("symbol") or "").upper(),
                "qty": float(row.get("qty") or 0.0),
                "market_value": float(row.get("market_value") or 0.0),
                "side": row.get("side"),
            }
            for row in position_rows
        ],
        "by_candidate": by_candidate,
        "broker_read_only": True,
        "broker_writes": False,
    }


def _role_status(candidate_id: str, semantic: dict[str, Any]) -> dict[str, Any]:
    valid_llm = int(semantic["llm_materialization"]["valid_factor_count"])
    admitted_llm = int(semantic["llm_materialization"]["admitted_factor_count"])
    admitted_deterministic = int(semantic["admitted_deterministic_theme_count"])
    status = {
        "R23D01": ("tier0_reserve", "R23D01"),
        "R23D02": (
            "admitted_zero_budget_shadow" if admitted_deterministic else "context_only_fallback",
            "R23D01",
        ),
        "R23M01": ("trained_shadow", "R23D01"),
        "R23M02": ("trained_tail_shadow", "R23M01_then_R23D01"),
        "R23L01": (
            "admitted_structured_llm_shadow" if admitted_llm else "missing_modality_fallback",
            "R23D02_then_R23D01",
        ),
        "R23C01": (
            "admitted_combined_zero_budget_shadow" if admitted_llm else "missing_modality_fallback",
            "R23M01",
        ),
        "R23F01": ("exact_missing_modality_fallback", "R23M01"),
        "R23P01": ("placebo_diagnostic_only", "R23M01"),
    }
    role_state, fallback = status[candidate_id]
    return {
        "status": role_state,
        "fallback_candidate_id": fallback,
        "valid_llm_factor_count": valid_llm if candidate_id in {"R23L01", "R23C01"} else 0,
        "admitted_llm_factor_count": (admitted_llm if candidate_id in {"R23L01", "R23C01"} else 0),
        "admitted_deterministic_theme_count": (
            admitted_deterministic if candidate_id == "R23D02" else 0
        ),
        "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
        "research_promotion_credit": False,
        "funding_eligible": False,
    }


def _historical_model_route_seeds(root: Path) -> dict[str, dict[str, Any]]:
    path = _regular_in_root(root, root / HISTORICAL_TARGET_LEDGER_PATH)
    latest: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"R23 target ledger row is malformed: {line_number}")
            source_candidate_id = str(row.get("candidate_id") or "")
            if source_candidate_id not in {"R22M01", "R22M02"}:
                continue
            candidate_id = source_candidate_id.replace("R22", "R23", 1)
            if str(row.get("execution_session")) <= DEVELOPMENT_END:
                prior = latest.get(candidate_id)
                if prior is None or str(row["execution_session"]) > str(prior["execution_session"]):
                    latest[candidate_id] = row
    if set(latest) != {"R23M01", "R23M02"}:
        raise ValueError("R23 historical model route seeds are incomplete")
    if latest["R23M02"].get("tail_exit_applied") is not False:
        raise ValueError("R23 historical M02 tail-exit state cannot be continued unambiguously")
    return latest


def _latest_role_targets(root: Path) -> dict[str, dict[str, float]]:
    observations_root = root / FORWARD_DATA_DIR / "observations"
    if not observations_root.exists():
        return {}
    candidates = [
        path
        for path in observations_root.iterdir()
        if path.is_dir() and not path.name.startswith(".") and (path / "receipt.json").exists()
    ]
    if not candidates:
        return {}
    latest = sorted(candidates)[-1]
    receipt = _read_json(latest / "receipt.json")
    output = {}
    for candidate_id, bindings in receipt.get("roles", {}).items():
        target = _read_json(_verify_binding(root, bindings["target"]))
        output[candidate_id] = _normalized_weights(target.get("weights", {}))
    return output


def _published_source_version_keys(root: Path) -> set[str]:
    return {packet.source_version_key for packet in _published_source_packets(root)}


def _published_source_packets(root: Path) -> list[ForwardSourcePacket]:
    output: dict[str, ForwardSourcePacket] = {}
    observations_root = root / FORWARD_DATA_DIR / "observations"
    if not observations_root.exists():
        return []
    for path in sorted(observations_root.glob("*/source-packets.json")):
        payload = _read_json(path)
        for raw in payload.get("packets", []):
            packet = ForwardSourcePacket.model_validate(raw)
            prior = output.get(packet.source_version_key)
            if prior is not None and prior != packet:
                raise ValueError("R23 published source version changed across observations")
            output[packet.source_version_key] = packet
    return sorted(output.values(), key=lambda row: (row.visible_at, row.packet_id))


def _select_r23_theme_packets(
    packets: list[ForwardSourcePacket],
    *,
    decision_session: date,
    observed_at: datetime,
) -> list[ForwardSourcePacket]:
    lower = _utc(observed_at) - MAX_NEWS_AGE
    eligible = [
        packet
        for packet in packets
        if lower <= packet.visible_at <= _utc(observed_at)
        and packet.published_at <= _utc(observed_at)
    ]
    return sorted(
        eligible,
        key=lambda packet: (
            -_event_materiality(packet),
            -sum(_is_company_symbol(symbol) for symbol in packet.symbols),
            -packet.visible_at.timestamp(),
            packet.packet_id,
        ),
    )[:MAX_THEME_PACKETS]


def _load_semantic_price_confirmations(
    root: Path,
    *,
    symbols: list[str],
    decision_session: date,
    observed_at: datetime,
    feed: str,
    refresh_prices: bool,
    price_frames: dict[str, pd.DataFrame] | None,
    price_fetcher: Callable[[str], pd.DataFrame] | None,
) -> tuple[
    dict[str, PriceConfirmation],
    list[dict[str, Any]],
    dict[str, str],
    list[date],
]:
    requested = sorted(set(symbols) | {"QQQ"})
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
                    adjustment=PRICE_ADJUSTMENT,
                )
            frames[symbol] = _semantic_price_frame(frame, decision_session, symbol)
        except Exception as exc:
            errors[symbol] = _safe_error(exc)

    qqq = frames.get("QQQ")
    session_dates = [] if qqq is None else list(qqq["timestamp"].dt.date)
    qqq_momentum = None
    if qqq is not None and len(qqq) >= RESIDUAL_MOMENTUM_SESSIONS + 1:
        qqq_momentum = _return_over(qqq["close"], RESIDUAL_MOMENTUM_SESSIONS)

    features: dict[str, PriceConfirmation] = {}
    price_inputs: list[dict[str, Any]] = []
    for symbol in requested:
        frame = frames.get(symbol)
        if frame is None:
            if symbol != "QQQ":
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
                    "adjustment": PRICE_ADJUSTMENT,
                }
            )
        if symbol != "QQQ":
            features[symbol] = _semantic_price_confirmation(
                symbol,
                frame,
                qqq_momentum,
                decision_session=decision_session,
            )
    return features, price_inputs, errors, session_dates


def _semantic_price_frame(
    frame: pd.DataFrame,
    decision_session: date,
    symbol: str,
) -> pd.DataFrame:
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError(f"R23 semantic daily frame is malformed: {symbol}")
    selected = frame.loc[:, sorted(required)].copy()
    selected["timestamp"] = pd.to_datetime(selected["timestamp"], utc=True, errors="raise")
    selected = selected.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    selected = selected[selected["timestamp"].dt.date <= decision_session]
    numeric_columns = ["open", "high", "low", "close", "volume"]
    for column in numeric_columns:
        selected[column] = pd.to_numeric(selected[column], errors="coerce")
    if (
        selected.empty
        or not selected[numeric_columns].notna().all().all()
        or (selected[["open", "high", "low", "close"]] <= 0).any().any()
        or (selected["volume"] < 0).any()
        or selected["timestamp"].dt.date.iloc[-1] != decision_session
    ):
        raise ValueError(f"R23 semantic daily frame is stale or invalid: {symbol}")
    return selected.reset_index(drop=True)


def _semantic_price_confirmation(
    symbol: str,
    frame: pd.DataFrame,
    qqq_momentum_5: float | None,
    *,
    decision_session: date,
) -> PriceConfirmation:
    session_count = len(frame)
    if session_count < MIN_PRICE_SESSIONS:
        return PriceConfirmation(
            symbol=symbol,
            session=decision_session,
            status="blocked",
            blocker="fewer_than_60_sessions",
            session_count=session_count,
        )
    if qqq_momentum_5 is None:
        return PriceConfirmation(
            symbol=symbol,
            session=decision_session,
            status="blocked",
            blocker="QQQ_residual_benchmark_unavailable",
            session_count=session_count,
        )
    close = frame["close"].astype(float)
    volume = frame["volume"].astype(float)
    momentum_5 = _return_over(close, RESIDUAL_MOMENTUM_SESSIONS)
    residual = momentum_5 - qqq_momentum_5
    short_volume = float(volume.iloc[-VOLUME_SHORT_SESSIONS:].mean())
    baseline_volume = float(volume.iloc[-VOLUME_BASELINE_SESSIONS:].mean())
    volume_surprise = short_volume / max(baseline_volume, 1.0)
    median_dollar_volume = float((close * volume).iloc[-VOLUME_BASELINE_SESSIONS:].median())
    eligible = bool(
        close.iloc[-1] >= MIN_PRICE and median_dollar_volume >= MIN_MEDIAN_DOLLAR_VOLUME
    )
    residual_positive = residual > 0.0
    volume_confirmed = volume_surprise >= MIN_VOLUME_SURPRISE
    return PriceConfirmation(
        symbol=symbol,
        session=decision_session,
        status="ok",
        session_count=session_count,
        close=float(close.iloc[-1]),
        momentum_5=momentum_5,
        residual_momentum_5=residual,
        volume_surprise_5_20=volume_surprise,
        median_dollar_volume_20=median_dollar_volume,
        eligible=eligible,
        residual_positive=residual_positive,
        volume_confirmed=volume_confirmed,
        confirmed=eligible and residual_positive and volume_confirmed,
    )


def _session_attention_acceleration(
    packets: list[ForwardSourcePacket],
    *,
    decision_session: date,
    session_dates: list[date],
) -> dict[str, dict[str, Any]]:
    sessions = sorted({item for item in session_dates if item <= decision_session})
    if not sessions or decision_session not in sessions:
        return {}
    session_index = {session: index for index, session in enumerate(sessions)}
    decision_index = session_index[decision_session]
    short: Counter[str] = Counter()
    prior: Counter[str] = Counter()
    for packet in packets:
        packet_session = _packet_visible_session(packet, sessions)
        if packet_session is None or packet_session > decision_session:
            continue
        age = decision_index - session_index[packet_session] + 1
        if 1 <= age <= ATTENTION_SHORT_SESSIONS:
            short.update(symbol for symbol in packet.symbols if _is_company_symbol(symbol))
        elif ATTENTION_SHORT_SESSIONS < age <= ATTENTION_LONG_SESSIONS:
            prior.update(symbol for symbol in packet.symbols if _is_company_symbol(symbol))
    symbols = set(short) | set(prior)
    return {
        symbol: {
            "short_count": short[symbol],
            "prior_count": prior[symbol],
            "short_rate": short[symbol] / ATTENTION_SHORT_SESSIONS,
            "prior_rate": prior[symbol] / (ATTENTION_LONG_SESSIONS - ATTENTION_SHORT_SESSIONS),
            "acceleration": (
                short[symbol] / ATTENTION_SHORT_SESSIONS
                - prior[symbol] / (ATTENTION_LONG_SESSIONS - ATTENTION_SHORT_SESSIONS)
            ),
        }
        for symbol in sorted(symbols)
    }


def _packet_visible_session(
    packet: ForwardSourcePacket,
    sessions: list[date],
) -> date | None:
    visible_day = packet.visible_at.date()
    return next((session for session in sessions if session >= visible_day), None)


def _theme_age_sessions(
    packet: ForwardSourcePacket,
    *,
    decision_session: date,
    session_dates: list[date],
) -> int:
    sessions = sorted({item for item in session_dates if item <= decision_session})
    packet_session = _packet_visible_session(packet, sessions)
    if packet_session is None or decision_session not in sessions:
        return 0
    return sessions.index(decision_session) - sessions.index(packet_session) + 1


def _deterministic_theme(
    packet: ForwardSourcePacket,
    *,
    price_features: dict[str, PriceConfirmation],
    attention: dict[str, dict[str, Any]],
    eligible_symbols: set[str],
    decision_session: date,
    session_dates: list[date],
) -> dict[str, Any]:
    entities = sorted(
        {
            symbol
            for symbol in packet.symbols
            if _is_company_symbol(symbol) and symbol in eligible_symbols
        },
        key=lambda symbol: (
            -float(attention.get(symbol, {}).get("acceleration", 0.0)),
            -float(price_features[symbol].residual_momentum_5 or 0.0),
            symbol,
        ),
    )[:MAX_THEME_MEMBERS]
    text = f"{packet.title} {packet.summary}".lower()
    relationship_type = next(
        (
            relationship
            for relationship, terms in RELATIONSHIP_TERMS.items()
            if any(term in text for term in terms)
        ),
        "unknown",
    )
    relationships: list[dict[str, Any]] = []
    if len(entities) >= 2 and relationship_type != "unknown":
        relationships = [
            {
                "source_entity": entities[0],
                "target_entity": target,
                "relationship_type": relationship_type,
                "evidence_packet_ids": [packet.packet_id],
            }
            for target in entities[1:]
        ]
    confirmations = [price_features[symbol] for symbol in entities]
    confirmed_members = sorted(row.symbol for row in confirmations if row.confirmed)
    residual_positive_members = sorted(row.symbol for row in confirmations if row.residual_positive)
    volume_confirmed_members = sorted(row.symbol for row in confirmations if row.volume_confirmed)
    attention_values = {
        symbol: float(attention.get(symbol, {}).get("acceleration", 0.0)) for symbol in entities
    }
    attention_positive_members = sorted(
        symbol for symbol, value in attention_values.items() if value > 0.0
    )
    breadth = len(confirmed_members) / len(entities) if entities else 0.0
    age_sessions = _theme_age_sessions(
        packet,
        decision_session=decision_session,
        session_dates=session_dates,
    )
    horizon_sessions = _deterministic_horizon(packet)
    checks = {
        "minimum_entities": len(entities) >= MIN_CONFIRMED_MEMBERS,
        "economic_link": bool(relationships),
        "attention_acceleration": (
            len(attention_positive_members) >= MIN_CONFIRMED_MEMBERS
            and _mean(attention_values.values()) > 0.0
        ),
        "minimum_confirmed_members": len(confirmed_members) >= MIN_CONFIRMED_MEMBERS,
        "positive_member_breadth": breadth >= MIN_POSITIVE_MEMBER_BREADTH,
        "minimum_active_age": age_sessions >= 3,
        "within_horizon": 0 < age_sessions <= min(20, horizon_sessions),
    }
    confirmation_pass = all(
        checks[key]
        for key in (
            "minimum_entities",
            "economic_link",
            "attention_acceleration",
            "minimum_confirmed_members",
            "positive_member_breadth",
        )
    )
    admitted = confirmation_pass and checks["minimum_active_age"] and checks["within_horizon"]
    if age_sessions > min(20, horizon_sessions):
        state = "retired"
    elif admitted:
        state = "active"
    elif confirmation_pass:
        state = "confirmed"
    elif relationships:
        state = "cooling" if age_sessions >= 3 else "mapped"
    else:
        state = "mapped" if entities else "seeded"
    return {
        "theme_id": f"r23theme_{packet.input_hash[:16]}",
        "packet_id": packet.packet_id,
        "entities": entities,
        "eligible_members": entities,
        "relationships": relationships,
        "direction": _lexical_direction(text),
        "event_materiality": _event_materiality(packet),
        "event_type": _deterministic_event_type(text),
        "relationship_support": len(relationships),
        "attention_acceleration": _mean(attention_values.values()),
        "attention_by_member": attention_values,
        "attention_positive_members": attention_positive_members,
        "confirmed_members": confirmed_members,
        "residual_positive_members": residual_positive_members,
        "volume_confirmed_members": volume_confirmed_members,
        "positive_member_breadth": breadth,
        "theme_age_sessions": age_sessions,
        "gate_checks": checks,
        "confirmation_gate_pass": confirmation_pass,
        "admitted": admitted,
        "state": state,
        "horizon_sessions": horizon_sessions,
        "price_created_theme": False,
    }


def _validate_llm_factor(
    factor: StructuredThemeFactor,
    packet: ForwardSourcePacket,
    allowed_entities: list[str],
    required_theme_id: str,
) -> None:
    allowed = set(allowed_entities)
    source_text = f"{packet.title} {packet.summary}".lower()
    if factor.theme_id != required_theme_id:
        raise ValueError("R23 LLM theme_id is not packet-bound")
    if not set(factor.entities).issubset(allowed):
        raise ValueError("R23 LLM factor introduced an unbound entity")
    if not set(factor.impact_subjects).issubset(allowed):
        raise ValueError("R23 LLM impact subject introduced an unbound entity")
    if set(factor.evidence_packet_ids) != {packet.packet_id}:
        raise ValueError("R23 LLM factor lacks exact packet evidence")
    for relationship in factor.relationships:
        if relationship.source_entity not in allowed or relationship.target_entity not in allowed:
            raise ValueError("R23 LLM relationship introduced an unbound entity")
        if set(relationship.evidence_packet_ids) != {packet.packet_id}:
            raise ValueError("R23 LLM relationship lacks exact packet evidence")
        terms = RELATIONSHIP_TERMS.get(relationship.relationship_type, ())
        if relationship.relationship_type != "unknown" and not any(
            term in source_text for term in terms
        ):
            raise ValueError("R23 LLM relationship is not supported by cited source text")


def _empty_semantic_gate(theme: dict[str, Any], *, reason: str) -> dict[str, Any]:
    return {
        "admitted": False,
        "state": theme.get("state", "seeded"),
        "theme_age_sessions": int(theme.get("theme_age_sessions") or 0),
        "eligible_members": list(theme.get("eligible_members") or []),
        "confirmed_members": list(theme.get("confirmed_members") or []),
        "positive_member_breadth": float(theme.get("positive_member_breadth") or 0.0),
        "reason": reason,
    }


def _llm_semantic_gate(
    factor: StructuredThemeFactor,
    deterministic_theme: dict[str, Any],
) -> dict[str, Any]:
    entities = set(factor.entities)
    confirmed = entities.intersection(deterministic_theme.get("confirmed_members") or [])
    attention_positive = entities.intersection(
        deterministic_theme.get("attention_positive_members") or []
    )
    relationships = [
        relationship
        for relationship in factor.relationships
        if relationship.relationship_type != "unknown"
        and relationship.source_entity in entities
        and relationship.target_entity in entities
    ]
    breadth = len(confirmed) / len(entities) if entities else 0.0
    age_sessions = int(deterministic_theme.get("theme_age_sessions") or 0)
    checks = {
        "minimum_entities": len(entities) >= MIN_CONFIRMED_MEMBERS,
        "minimum_impact_subjects": len(set(factor.impact_subjects)) >= MIN_CONFIRMED_MEMBERS,
        "economic_link_or_explicit_shared_impact": bool(relationships),
        "attention_acceleration": len(attention_positive) >= MIN_CONFIRMED_MEMBERS,
        "minimum_confirmed_members": len(confirmed) >= MIN_CONFIRMED_MEMBERS,
        "positive_member_breadth": breadth >= MIN_POSITIVE_MEMBER_BREADTH,
        "minimum_active_age": age_sessions >= 3,
        "within_horizon": 0 < age_sessions <= min(20, factor.horizon_sessions),
    }
    admitted = all(checks.values())
    return {
        "admitted": admitted,
        "state": "active" if admitted else deterministic_theme.get("state", "mapped"),
        "theme_age_sessions": age_sessions,
        "eligible_members": sorted(entities),
        "confirmed_members": sorted(confirmed),
        "positive_member_breadth": breadth,
        "relationship_count": len(relationships),
        "checks": checks,
        "reason": None if admitted else "one_or_more_preregistered_gate_checks_failed",
    }


def _event_materiality(packet: ForwardSourcePacket) -> float:
    text = f"{packet.title} {packet.summary}".lower()
    terms = (
        "acquisition",
        "approval",
        "contract",
        "earnings",
        "guidance",
        "investment",
        "launch",
        "merger",
        "order",
        "partnership",
        "revenue",
    )
    return round(min(1.0, 0.25 + 0.15 * sum(term in text for term in terms)), 6)


def _deterministic_event_type(text: str) -> str:
    for event_type, terms in (
        ("earnings_or_guidance", ("earnings", "guidance", "forecast")),
        ("commercial_contract", ("contract", "order", "purchase agreement")),
        ("partnership", ("partnership", "collaboration", "jointly")),
        ("product_or_capacity", ("launch", "capacity", "data center", "deployment")),
        ("regulatory", ("approval", "investigation", "lawsuit", "recall")),
        ("corporate_transaction", ("acquisition", "merger", "investment")),
    ):
        if any(term in text for term in terms):
            return event_type
    return "other_source_bound_event"


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
        raise ValueError("R23 price return is nonfinite")
    return value


def _mean(values: Iterable[float]) -> float:
    rows = [float(value) for value in values]
    return math.fsum(rows) / len(rows) if rows else 0.0


def _lexical_direction(text: str) -> float:
    lowered = text.lower()
    positive = sum(term in lowered for term in POSITIVE_TERMS)
    negative = sum(term in lowered for term in NEGATIVE_TERMS)
    if positive + negative == 0:
        return 0.0
    return round((positive - negative) / (positive + negative), 6)


def _is_equity_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol)) and symbol != "MARKET"


def _is_company_symbol(symbol: str) -> bool:
    normalized = symbol.upper().strip()
    return bool(
        _is_equity_symbol(normalized)
        and normalized not in set(UNIVERSE)
        and not normalized.endswith("USD")
    )


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


def _daily_session_rows(
    frame: pd.DataFrame,
    *,
    decision_session: date,
    symbol: str,
) -> dict[date, dict[str, float]]:
    required = {"timestamp", "open", "low", "close", "volume"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError(f"R23 live daily frame is malformed: {symbol}")
    normalized = frame.loc[:, sorted(required)].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="raise")
    normalized["session"] = normalized["timestamp"].dt.date
    normalized = normalized[normalized["session"] <= decision_session]
    if normalized["session"].duplicated().any():
        raise ValueError(f"R23 live daily frame has duplicate sessions: {symbol}")
    output: dict[date, dict[str, float]] = {}
    for row in normalized.to_dict(orient="records"):
        values = {field: float(row[field]) for field in ("open", "low", "close", "volume")}
        if (
            not all(math.isfinite(value) for value in values.values())
            or min(values["open"], values["low"], values["close"]) <= 0.0
            or values["volume"] < 0.0
            or values["low"] > min(values["open"], values["close"])
        ):
            raise ValueError(f"R23 live daily frame contains invalid OHLCV: {symbol}")
        output[row["session"]] = values
    return output


def _candidate_route(
    candidate_id: str,
    weights: dict[str, float],
    diagnostics: dict[str, Any],
) -> str:
    del candidate_id, diagnostics
    selected = [symbol for symbol, weight in weights.items() if weight > 0.0]
    if len(selected) != 1 or not math.isclose(weights[selected[0]], 1.0, abs_tol=1e-12):
        return "multi_asset"
    return "USD100" if selected[0] == "USD" else selected[0]


def _normalized_weights(values: dict[str, Any]) -> dict[str, float]:
    weights = {symbol: float(values.get(symbol, 0.0)) for symbol in UNIVERSE}
    if not all(
        math.isfinite(value) and value >= 0.0 for value in weights.values()
    ) or not math.isclose(math.fsum(weights.values()), 1.0, abs_tol=1e-12):
        raise ValueError("R23 forward target weights violate the long-only unit-budget contract")
    return weights


def _zero_weights() -> dict[str, float]:
    return {symbol: 0.0 for symbol in UNIVERSE}


def _verify_staged_receipt(root: Path, path: Path, receipt: dict[str, Any]) -> None:
    if _read_json(path) != receipt:
        raise ValueError("R23 staged receipt changed after publication")
    bindings = list(receipt["artifacts"].values())
    for role in receipt["roles"].values():
        bindings.extend(role.values())
    for binding in bindings:
        relative = Path(str(binding["path"]))
        parts = relative.parts
        marker = parts.index("observations")
        staged_relative = Path(*parts[marker + 2 :])
        stage_path = path.parent / staged_relative
        if (
            _sha256(stage_path) != binding["sha256"]
            or stage_path.stat().st_size != binding["size_bytes"]
        ):
            raise ValueError("R23 staged artifact does not match its receipt binding")


def _verify_observation_receipt(
    root: Path,
    receipt_path: Path,
    lock_state: dict[str, Any],
) -> dict[str, Any]:
    path = _regular_in_root(root, receipt_path)
    receipt = _read_json(path)
    if (
        receipt.get("schema_version") != 1
        or receipt.get("receipt_contract") != RECEIPT_CONTRACT
        or receipt.get("iter_id") != FORWARD_ITER_ID
        or receipt.get("epoch_id") != lock_state["epoch_id"]
        or receipt.get("lock")
        != {"path": lock_state["lock_path"], "sha256": lock_state["lock_sha256"]}
        or receipt.get("candidate_ids") != list(SPEC_PATHS)
        or set(receipt.get("roles", {})) != set(SPEC_PATHS)
        or receipt.get("observation_only") is not True
        or receipt.get("broker_writes") is not False
        or receipt.get("order_authority") is not False
    ):
        raise ValueError("R23 forward receipt identity mismatch")
    decision_session = date.fromisoformat(str(receipt["decision_session"]))
    if receipt.get("action_session") != next_us_equity_session(decision_session).isoformat():
        raise ValueError("R23 forward receipt action session is invalid")
    expected_counted = decision_session > lock_state["anchor_session"]
    if receipt.get("counted_forward_session") is not expected_counted:
        raise ValueError("R23 forward receipt counting status is invalid")
    artifacts = receipt.get("artifacts")
    required_artifacts = {
        "observation",
        "price_snapshot",
        "source_packets",
        "semantic_diagnostics",
        "model_diagnostics",
        "account_reconciliation",
    }
    if not isinstance(artifacts, dict) or set(artifacts) != required_artifacts:
        raise ValueError("R23 forward receipt artifact coverage mismatch")
    for binding in artifacts.values():
        _verify_binding(root, binding)
    for candidate_id, role in receipt["roles"].items():
        if set(role) != {"target", "intents", "execution"}:
            raise ValueError(f"R23 forward role binding coverage mismatch: {candidate_id}")
        target = _read_json(_verify_binding(root, role["target"]))
        intents = _read_json(_verify_binding(root, role["intents"]))
        execution = _read_json(_verify_binding(root, role["execution"]))
        weights = _normalized_weights(target.get("weights", {}))
        target_hash = _canonical_hash(weights)
        if (
            target.get("candidate_id") != candidate_id
            or target.get("target_contract") != TARGET_CONTRACT
            or target.get("target_sha256") != target_hash
            or target.get("observation_only") is not True
            or target.get("broker_writes") is not False
            or intents.get("intent_contract") != INTENT_CONTRACT
            or intents.get("target_sha256") != target_hash
            or intents.get("order_authority") is not False
            or execution.get("execution_observation_contract") != EXECUTION_OBSERVATION_CONTRACT
            or execution.get("target_sha256") != target_hash
            or execution.get("submission_attempted") is not False
            or execution.get("submitted_order_count") != 0
            or execution.get("broker_writes") is not False
        ):
            raise ValueError(f"R23 forward role payload mismatch: {candidate_id}")
    f01 = _read_json(_verify_binding(root, receipt["roles"]["R23F01"]["target"]))
    m01 = _read_json(_verify_binding(root, receipt["roles"]["R23M01"]["target"]))
    if f01["target_sha256"] != m01["target_sha256"]:
        raise ValueError("R23 forward F01 target is not the exact M01 fallback")
    return receipt


def _result_from_receipt(
    root: Path,
    final_dir: Path,
    receipt: dict[str, Any],
) -> R23ForwardObservationResult:
    observation_path = _verify_binding(root, receipt["artifacts"]["observation"])
    payload = _read_json(observation_path)
    return R23ForwardObservationResult(
        status="published",
        epoch_id=str(receipt["epoch_id"]),
        observation_id=str(receipt["observation_id"]),
        decision_session=date.fromisoformat(str(receipt["decision_session"])),
        action_session=date.fromisoformat(str(receipt["action_session"])),
        observation_path=observation_path,
        receipt_path=final_dir / "receipt.json",
        candidate_count=len(receipt["candidate_ids"]),
        counted_forward_session=bool(receipt["counted_forward_session"]),
        payload=payload,
    )


def _safe_error(exc: Exception) -> str:
    value = f"{type(exc).__name__}: {exc}".replace("\n", " ")
    if _is_authentication_error(exc) or re.search(
        r"(?:api[_ -]?key|secret|token|sk-[a-z0-9])",
        value,
        re.IGNORECASE,
    ):
        return f"{type(exc).__name__}: authentication_or_credential_error_redacted"
    return value[:500]


def _is_authentication_error(exc: Exception) -> bool:
    name = type(exc).__name__.lower()
    value = str(exc).lower()
    return (
        "authentication" in name
        or "permission" in name
        or "unauthorized" in value
        or "invalid_api_key" in value
        or "incorrect api key" in value
        or "status: 401" in value
        or "error code: 401" in value
    )


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _parse_datetime(value: Any, label: str) -> datetime:
    try:
        return _utc(datetime.fromisoformat(str(value)))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"R23 forward {label} is invalid") from exc


def _canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


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
    relative = candidate.absolute().relative_to(base)
    cursor = base
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise ValueError(f"R23 forward bound path cannot use symlinks: {candidate}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R23 forward bound path escapes project root: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"R23 forward bound path is not a regular file: {candidate}")
    return resolved


def _binding(path: Path, root: Path) -> dict[str, Any]:
    resolved = _regular_in_root(root, path)
    return {
        "path": resolved.relative_to(root.resolve()).as_posix(),
        "sha256": _sha256(resolved),
        "size_bytes": resolved.stat().st_size,
    }


def _staged_binding(stage_path: Path, destination: Path, root: Path) -> dict[str, Any]:
    destination_relative = destination.absolute().relative_to(root.resolve()).as_posix()
    return {
        "path": destination_relative,
        "sha256": _sha256(stage_path),
        "size_bytes": stage_path.stat().st_size,
    }


def _verify_binding(root: Path, binding: Any) -> Path:
    required = {"path", "sha256", "size_bytes"}
    if not isinstance(binding, dict) or not required.issubset(binding):
        raise ValueError("R23 forward file binding is malformed")
    path = _regular_in_root(root, root / str(binding["path"]))
    if _sha256(path) != binding["sha256"] or path.stat().st_size != binding["size_bytes"]:
        raise ValueError(f"R23 forward file binding changed: {binding.get('path')}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R23 forward JSON artifact must be an object: {path}")
    return payload


def _exclusive_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(_canonical_json_bytes(payload) + b"\n")
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    _fsync_directory(path.parent)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    _write_bytes_atomic(path, _canonical_json_bytes(payload) + b"\n")


def _write_jsonl_atomic(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    content = b"".join(_canonical_json_bytes(row) + b"\n" for row in rows)
    _write_bytes_atomic(path, content)


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.tmp-{os.getpid()}"
    with temporary.open("wb") as handle:
        handle.write(content)
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
    lock_path = root / ITERATION_DIR / "forward/.writer.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
