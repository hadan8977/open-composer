from __future__ import annotations

import fcntl
import hashlib
import json
import math
import os
import re
import shutil
from collections.abc import Callable, Iterable
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, Protocol

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.events.fetcher import fetch_capability_events
from open_composer.config import default_openai_model, openai_api_key, project_root
from open_composer.market_calendar import next_us_equity_session
from open_composer.models.event import EventRecord
from open_composer.paper_freshness import latest_completed_us_equity_session
from open_composer.research.llm_backends import get_backend
from open_composer.research.pit_semantic_theme_r11 import UNIVERSE, R11PricePanel
from open_composer.research.pit_semantic_theme_r22 import (
    DEVELOPMENT_END,
    ITER_ID,
    M01_OVERRIDE_THRESHOLD,
    M02_SURVIVAL_EXIT_THRESHOLD,
    MODEL_FEATURES,
    RECOVERY_BREADTH_MIN_COUNT,
    RECOVERY_BREADTH_TREND_SESSIONS,
    RECOVERY_QQQ_TREND_SESSIONS,
    RECOVERY_TQQQ_MOMENTUM_MIN,
    RECOVERY_TQQQ_MOMENTUM_SESSIONS,
    REVIEW_EVERY_SESSIONS,
    SPEC_PATHS,
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
from open_composer.strategy_versions import strategy_content_hash

FORWARD_ITER_ID = f"{ITER_ID}_forward"
ITERATION_DIR = Path("reports/research/iterations") / ITER_ID
FORWARD_LOCK_PATH = ITERATION_DIR / "forward/epoch-lock.json"
FORWARD_DATA_DIR = Path("data/forward/pit_semantic_theme_r22")
FORWARD_REPORT_DIR = Path("reports/forward/us_pit_semantic_theme_r22")
HISTORICAL_LOCK_PATH = ITERATION_DIR / "lock-set/historical-evaluation-lock.json"
HISTORICAL_REPORT_PATH = ITERATION_DIR / "historical-evaluation/evaluation-report.json"
HISTORICAL_TARGET_LEDGER_PATH = ITERATION_DIR / "historical-evaluation/target-ledger.jsonl"
PROMPT_PATH = Path("prompts/pit_semantic_theme_r22_factor_v1.txt")
FORWARD_MODULE_PATH = Path("open_composer/research/pit_semantic_theme_r22_forward.py")
FORWARD_TEST_PATH = Path("tests/test_pit_semantic_theme_r22_forward.py")

FORWARD_LOCK_CONTRACT = "pit_semantic_theme_r22_forward_epoch_v1"
SOURCE_PACKET_CONTRACT = "pit_semantic_theme_r22_forward_source_v1"
OBSERVATION_CONTRACT = "pit_semantic_theme_r22_tier0_observation_v1"
RECEIPT_CONTRACT = "pit_semantic_theme_r22_tier0_receipt_v1"
TARGET_CONTRACT = "pit_semantic_theme_r22_target_weights_v1"
INTENT_CONTRACT = "pit_semantic_theme_r22_rebalance_intents_v1"
EXECUTION_OBSERVATION_CONTRACT = "pit_semantic_theme_r22_execution_observation_v1"

PRICE_FEED = "iex"
PRICE_ADJUSTMENT = "all"
LIVE_OVERLAP_TOLERANCE = 0.05
MAX_NEWS_AGE = timedelta(days=7)
MAX_THEME_PACKETS = 8
MAX_THEME_MEMBERS = 8
SEMANTIC_STOCK_BUDGET = 0.0
PLACEBO_SEED = 15108
ACCOUNT_WEIGHT_TOLERANCE = 0.05

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
    "placebo_seed": PLACEBO_SEED,
}

LOCKED_PATHS = (
    HISTORICAL_LOCK_PATH,
    HISTORICAL_REPORT_PATH,
    HISTORICAL_TARGET_LEDGER_PATH,
    Path("reports/research/data-quality/r11-price-repair-20260804-contract.json"),
    Path("reports/research/data-quality/r11-price-repair-20260804-quality.json"),
    PROMPT_PATH,
    Path("schemas/alpaca_snapshot_contract.schema.json"),
    Path("schemas/alpaca_snapshot_manifest.schema.json"),
    Path("open_composer/market_calendar.py"),
    Path("open_composer/adapters/data/alpaca_snapshot.py"),
    Path("open_composer/research/pit_semantic_theme_r22.py"),
    FORWARD_MODULE_PATH,
    FORWARD_TEST_PATH,
    Path("open_composer/adapters/data/alpaca.py"),
    Path("open_composer/adapters/events/fetcher.py"),
    Path("open_composer/research/llm_backends.py"),
)


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
    packet_contract: Literal["pit_semantic_theme_r22_forward_source_v1"]
    packet_id: str = Field(pattern=r"^r22pkt_[a-f0-9]{24}$")
    epoch_id: str = Field(min_length=1)
    source: Literal["news.alpaca"]
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
    acquisition_mode: Literal["live_api_forward_only"]

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, values: list[str]) -> list[str]:
        normalized = sorted({value.upper().strip() for value in values if value.strip()})
        if not normalized:
            raise ValueError("R22 source packet requires at least one symbol")
        return normalized


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

    theme_id: str = Field(pattern=r"^r22theme_[a-f0-9]{16}$")
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
            raise ValueError("R22 theme entities must be unique")
        return normalized


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
        "theme_id": {"type": "string", "pattern": "^r22theme_[a-f0-9]{16}$"},
        "entities": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_THEME_MEMBERS,
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
class R22ForwardFreezeResult:
    lock_path: Path
    lock_sha256: str
    epoch_id: str
    anchor_session: date


@dataclass(frozen=True)
class R22ForwardObservationResult:
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


def freeze_pit_semantic_theme_r22_forward(
    root: Path | None = None,
    *,
    created_at: datetime | None = None,
) -> R22ForwardFreezeResult:
    base = (root or project_root()).resolve()
    lock_path = base / FORWARD_LOCK_PATH
    if lock_path.exists():
        raise ValueError("R22 forward epoch lock already exists")
    if (base / FORWARD_DATA_DIR).exists() or (base / FORWARD_REPORT_DIR).exists():
        raise ValueError("R22 forward evidence exists before the epoch lock")

    specs = load_and_validate_r22_specs(base)
    historical = _read_json(_regular_in_root(base, base / HISTORICAL_REPORT_PATH))
    if (
        historical.get("iter_id") != ITER_ID
        or historical.get("decision") != "stop_price_paths"
        or historical.get("workflow_pass") is not True
        or historical.get("research_pass") is not False
        or historical.get("paper_ready_pass") is not False
        or historical.get("transfer_holdout", {}).get("access_count") != 0
    ):
        raise ValueError("R22 historical terminal decision is not the sealed stopped state")

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
        "source_iter_id": ITER_ID,
        "created_at": timestamp.isoformat(),
        "anchor_session": anchor_session.isoformat(),
        "status": "locked_before_first_r22_tier0_observation",
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
        "epoch_id": f"r22fwd_{anchor_sha256[:16]}",
    }
    _exclusive_write_json(lock_path, lock)
    return R22ForwardFreezeResult(
        lock_path=lock_path,
        lock_sha256=_sha256(lock_path),
        epoch_id=str(lock["epoch_id"]),
        anchor_session=anchor_session,
    )


def verify_pit_semantic_theme_r22_forward_lock(
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
        or lock.get("source_iter_id") != ITER_ID
        or lock.get("epoch_anchor_sha256") != expected_anchor
        or lock.get("epoch_id") != f"r22fwd_{expected_anchor[:16]}"
        or lock.get("behavior") != FORWARD_BEHAVIOR
        or lock.get("broker_writes") is not False
        or lock.get("order_authority") is not False
    ):
        raise ValueError("R22 forward epoch lock identity mismatch")
    created_at = _parse_datetime(lock.get("created_at"), "lock created_at")
    now = _utc(observed_at or datetime.now(UTC))
    if created_at > now:
        raise ValueError("R22 forward epoch lock is future-dated")
    for group in ("paths", "specs"):
        rows = lock.get(group)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"R22 forward lock group is missing: {group}")
        for row in rows:
            _verify_binding(base, row)
    specs = load_and_validate_r22_specs(base)
    locked_specs = {str(row.get("candidate_id")): row for row in lock["specs"]}
    if set(locked_specs) != set(specs):
        raise ValueError("R22 forward spec coverage mismatch")
    for candidate_id, spec in specs.items():
        if strategy_content_hash(spec) != locked_specs[candidate_id].get("semantic_sha256"):
            raise ValueError(f"R22 forward semantic spec changed: {candidate_id}")
    return {
        "lock": lock,
        "lock_path": FORWARD_LOCK_PATH.as_posix(),
        "lock_sha256": _sha256(lock_path),
        "epoch_id": str(lock["epoch_id"]),
        "created_at": created_at,
        "anchor_session": date.fromisoformat(str(lock["anchor_session"])),
    }


def collect_r22_forward_price_panel(
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
        raise ValueError("R22 forward price feed is locked to Alpaca IEX")
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
                f"R22 forward live price is missing the latest completed session: "
                f"{symbol} {decision_session}"
            )
        overlap = session_rows.get(historical_last)
        if overlap is not None:
            historical_close = float(historical.close.at[pd.Timestamp(historical_last), symbol])
            relative_gap = abs(overlap["close"] / historical_close - 1.0)
            if relative_gap > LIVE_OVERLAP_TOLERANCE:
                raise ValueError(
                    f"R22 forward live/historical adjustment boundary mismatch: {symbol}"
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
        raise ValueError("R22 forward live panel lacks common latest-session coverage")
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
        raise ValueError("R22 forward merged panel does not end on the decision session")
    price_snapshot = {
        "schema_version": 1,
        "snapshot_contract": "pit_semantic_theme_r22_forward_price_snapshot_v1",
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


def build_r22_forward_feature_dataset(panel: R11PricePanel) -> pd.DataFrame:
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
        raise ValueError("R22 forward feature dataset is empty or nonfinite")
    return dataset


def _panel_with_action_placeholder(panel: R11PricePanel, action_session: date) -> R11PricePanel:
    action_timestamp = pd.Timestamp(action_session)
    if action_timestamp <= panel.close.index[-1]:
        raise ValueError("R22 forward action placeholder must follow the decision data")
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
        raise ValueError("R22 development-only model panel does not end on its locked boundary")
    return R11PricePanel(
        open=fields["open"],
        low=fields["low"],
        close=fields["close"],
        volume=fields["volume"],
        metadata={**panel.metadata, "forward_model_training_end": DEVELOPMENT_END},
    )


def build_r22_forward_role_targets(
    root: Path,
    *,
    panel: R11PricePanel,
    action_session: date,
    lock_state: dict[str, Any],
) -> tuple[dict[str, dict[str, float]], dict[str, Any]]:
    base = root.resolve()
    specs = load_and_validate_r22_specs(base)
    scheduled_panel = _panel_with_action_placeholder(panel, action_session)
    forward_dataset = build_r22_forward_feature_dataset(scheduled_panel)
    d01_frame, d01_records = build_r22_d01_targets(
        scheduled_panel,
        specs["R22D01"],
        forward_dataset,
    )
    d01_record = d01_records[-1]
    if d01_record["execution_session"] != action_session.isoformat():
        raise ValueError("R22 D01 forward target does not cover the action session")

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
        segment_id="R22_FORWARD_FROZEN_DEVELOPMENT_MODEL",
        specs=specs,
        provenance=provenance,
    )
    historical_seeds = _historical_model_route_seeds(base)
    m01_state = historical_seeds["R22M01"]
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
        raise ValueError("R22 forward model path does not reach the action session")

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
                candidate_id: fitted[candidate_id].model_id for candidate_id in ("R22M01", "R22M02")
            },
        }
    assert final_prediction is not None

    d01_weights = _normalized_weights(d01_frame.iloc[-1].to_dict())
    m01_weights = _normalized_weights(m01_target.to_dict())
    m02_weights = _normalized_weights(m02_target.to_dict())
    role_targets = {
        "R22D01": d01_weights,
        "R22D02": d01_weights.copy(),
        "R22M01": m01_weights,
        "R22M02": m02_weights,
        "R22L01": d01_weights.copy(),
        "R22C01": m01_weights.copy(),
        "R22F01": m01_weights.copy(),
        "R22P01": m01_weights.copy(),
    }
    if role_targets["R22F01"] != role_targets["R22M01"]:
        raise ValueError("R22 F01 is not the exact M01 target fallback")
    if role_targets["R22D02"] != role_targets["R22D01"]:
        raise ValueError("R22 D02 zero-budget target differs from D01")
    diagnostics = {
        "schema_version": 1,
        "training_scope": "locked_development_only",
        "training_end": DEVELOPMENT_END,
        "transfer_outcomes_used": False,
        "research_promotion_credit": False,
        "model_records": model_records,
        "current_prediction": final_prediction,
        "d01_route": d01_record,
        "role_target_sources": {
            "R22D01": "R22D01",
            "R22D02": "R22D01_zero_semantic_budget",
            "R22M01": "R22M01_observation_only",
            "R22M02": "R22M02_observation_only",
            "R22L01": "R22D02_then_R22D01_zero_semantic_budget",
            "R22C01": "R22M01_zero_semantic_budget",
            "R22F01": "R22M01_exact_missing_modality_fallback",
            "R22P01": "R22M01_placebo_diagnostic_only",
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


def build_r22_forward_source_packets(
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
            raise ValueError("R22 forward accepts only live forward Alpaca News records")
        fetched_at = _utc(event.fetched_at)
        visible_at = _utc(event.visible_at or event.fetched_at)
        if fetched_at < epoch_start or visible_at < epoch_start:
            raise ValueError("R22 forward event predates the locked collector epoch")
        if visible_at > observed + timedelta(minutes=1):
            raise ValueError("R22 forward event is future-dated")
        provider_id = str(event.raw.get("provider_id") or "").strip()
        if not provider_id or not event.version_id:
            raise ValueError("R22 Alpaca News record lacks provider version identity")
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
        }
        input_hash = _canonical_hash(source_payload)
        packets.append(
            ForwardSourcePacket(
                schema_version=1,
                packet_contract=SOURCE_PACKET_CONTRACT,
                packet_id=f"r22pkt_{input_hash[:24]}",
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
                fetched_at=min(_utc(row.fetched_at) for row in rows),
                first_seen_at=min(_utc(row.first_seen_at or row.fetched_at) for row in rows),
                visible_at=max(_utc(row.visible_at or row.fetched_at) for row in rows),
                input_hash=input_hash,
                rights_scope=first.rights_scope,
                acquisition_mode="live_api_forward_only",
            )
        )
    return sorted(packets, key=lambda packet: (packet.published_at, packet.packet_id))


def build_r22_semantic_diagnostics(
    root: Path,
    *,
    packets: list[ForwardSourcePacket],
    observed_at: datetime,
    backend_name: str,
    model: str | None,
    backend: ThemeBackend | None,
) -> dict[str, Any]:
    base = root.resolve()
    lower = _utc(observed_at) - MAX_NEWS_AGE
    selected = sorted(
        [packet for packet in packets if packet.published_at >= lower],
        key=lambda packet: (-_event_materiality(packet), -len(packet.symbols), packet.packet_id),
    )[:MAX_THEME_PACKETS]
    deterministic = [_deterministic_theme(packet) for packet in selected]
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
    for packet in selected:
        entities = [symbol for symbol in packet.symbols if _is_equity_symbol(symbol)][
            :MAX_THEME_MEMBERS
        ]
        required_theme_id = f"r22theme_{packet.input_hash[:16]}"
        input_payload = {
            "required_theme_id": required_theme_id,
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
        if not entities:
            llm_results.append(
                {
                    **record,
                    "status": "fallback",
                    "structured_output": None,
                    "structured_output_hash": None,
                    "error": "no_source_bound_equity_entities",
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
            llm_results.append(
                {
                    **record,
                    "status": "valid",
                    "structured_output": payload,
                    "structured_output_hash": _canonical_hash(payload),
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
                    "error": error,
                }
            )
    return {
        "schema_version": 1,
        "semantic_contract": "pit_semantic_theme_r22_semantic_diagnostics_v1",
        "selected_packet_count": len(selected),
        "deterministic_themes": deterministic,
        "llm_materialization": {
            "backend": backend_name,
            "model": selected_model,
            "prompt_path": PROMPT_PATH.as_posix(),
            "prompt_hash": prompt_hash,
            "model_parameters_hash": parameters_hash,
            "valid_factor_count": sum(row["status"] == "valid" for row in llm_results),
            "results": llm_results,
        },
        "semantic_stock_budget": SEMANTIC_STOCK_BUDGET,
        "research_pass": False,
        "llm_contribution_pass": False,
        "broker_writes": False,
        "order_authority": False,
    }


def observe_pit_semantic_theme_r22_forward(
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
) -> R22ForwardObservationResult:
    base = (root or project_root()).resolve()
    started_at = _utc(observed_at or datetime.now(UTC))
    lock_state = verify_pit_semantic_theme_r22_forward_lock(base, observed_at=started_at)
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
        packets = build_r22_forward_source_packets(
            epoch_collected,
            epoch_id=lock_state["epoch_id"],
            epoch_started_at=lock_state["created_at"],
            observed_at=materialized_at,
        )
        prior_source_keys = _published_source_version_keys(base)
        new_packets = [
            packet for packet in packets if packet.source_version_key not in prior_source_keys
        ]
        panel, price_snapshot = collect_r22_forward_price_panel(
            base,
            decision_session=decision_session,
            observed_at=materialized_at,
            feed=feed,
            refresh_prices=refresh_prices,
            price_frames=price_frames,
            price_fetcher=price_fetcher,
        )
        role_targets, model_diagnostics = build_r22_forward_role_targets(
            base,
            panel=panel,
            action_session=action_session,
            lock_state=lock_state,
        )
        semantic = build_r22_semantic_diagnostics(
            base,
            packets=new_packets,
            observed_at=materialized_at,
            backend_name=backend_name,
            model=model,
            backend=backend,
        )
        semantic["collection"] = {
            "enabled": collect_news or events is not None,
            "collected_event_count": len(collected),
            "epoch_eligible_event_count": len(epoch_collected),
            "pre_epoch_event_count": len(collected) - len(epoch_collected),
            "new_source_packet_count": len(new_packets),
            "error": news_error,
        }
        specs = load_and_validate_r22_specs(base)
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
            "source_packet_count": len(new_packets),
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
                "R22 historical research_pass remains false",
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
            source_packets=new_packets,
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
    state = lock_state or verify_pit_semantic_theme_r22_forward_lock(root)
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
            raise ValueError(f"R22 forward has duplicate decision-session receipts: {session}")
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
        "readiness_contract": "pit_semantic_theme_r22_tier0_readiness_v1",
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
            "source": "pit_semantic_theme_r22_forward",
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
        raise ValueError("R22 account reconciliation requires paper-only snapshots")
    equity = float(account.get("equity") or account.get("portfolio_value") or 0.0)
    if not math.isfinite(equity) or equity <= 0.0:
        raise ValueError("R22 paper account equity is invalid")
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
    status = {
        "R22D01": ("tier0_reserve", "R22D01"),
        "R22D02": ("zero_budget_shadow", "R22D01"),
        "R22M01": ("trained_shadow", "R22D01"),
        "R22M02": ("trained_tail_shadow", "R22M01_then_R22D01"),
        "R22L01": (
            "structured_llm_shadow" if valid_llm else "missing_modality_fallback",
            "R22D02_then_R22D01",
        ),
        "R22C01": (
            "combined_zero_budget_shadow" if valid_llm else "missing_modality_fallback",
            "R22M01",
        ),
        "R22F01": ("exact_missing_modality_fallback", "R22M01"),
        "R22P01": ("placebo_diagnostic_only", "R22M01"),
    }
    role_state, fallback = status[candidate_id]
    return {
        "status": role_state,
        "fallback_candidate_id": fallback,
        "valid_llm_factor_count": valid_llm if candidate_id in {"R22L01", "R22C01"} else 0,
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
                raise ValueError(f"R22 target ledger row is malformed: {line_number}")
            candidate_id = str(row.get("candidate_id") or "")
            if candidate_id not in {"R22M01", "R22M02"}:
                continue
            if str(row.get("execution_session")) <= DEVELOPMENT_END:
                prior = latest.get(candidate_id)
                if prior is None or str(row["execution_session"]) > str(prior["execution_session"]):
                    latest[candidate_id] = row
    if set(latest) != {"R22M01", "R22M02"}:
        raise ValueError("R22 historical model route seeds are incomplete")
    if latest["R22M02"].get("tail_exit_applied") is not False:
        raise ValueError("R22 historical M02 tail-exit state cannot be continued unambiguously")
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
    output: set[str] = set()
    observations_root = root / FORWARD_DATA_DIR / "observations"
    if not observations_root.exists():
        return output
    for path in sorted(observations_root.glob("*/source-packets.json")):
        payload = _read_json(path)
        for packet in payload.get("packets", []):
            key = str(packet.get("source_version_key") or "")
            if key:
                output.add(key)
    return output


def _deterministic_theme(packet: ForwardSourcePacket) -> dict[str, Any]:
    entities = [symbol for symbol in packet.symbols if _is_equity_symbol(symbol)][
        :MAX_THEME_MEMBERS
    ]
    text = f"{packet.title} {packet.summary}".lower()
    relationship_type = next(
        (
            relationship
            for relationship, terms in RELATIONSHIP_TERMS.items()
            if any(term in text for term in terms)
        ),
        "unknown",
    )
    relationships = []
    if len(entities) >= 2 and relationship_type != "unknown":
        relationships.append(
            {
                "source_entity": entities[0],
                "target_entity": entities[1],
                "relationship_type": relationship_type,
                "evidence_packet_ids": [packet.packet_id],
            }
        )
    return {
        "theme_id": f"r22theme_{packet.input_hash[:16]}",
        "packet_id": packet.packet_id,
        "entities": entities,
        "relationships": relationships,
        "direction": _lexical_direction(text),
        "event_materiality": _event_materiality(packet),
        "state": "mapped" if entities else "seeded",
        "horizon_sessions": 5,
        "price_created_theme": False,
    }


def _validate_llm_factor(
    factor: StructuredThemeFactor,
    packet: ForwardSourcePacket,
    allowed_entities: list[str],
    required_theme_id: str,
) -> None:
    allowed = set(allowed_entities)
    if factor.theme_id != required_theme_id:
        raise ValueError("R22 LLM theme_id is not packet-bound")
    if not set(factor.entities).issubset(allowed):
        raise ValueError("R22 LLM factor introduced an unbound entity")
    if set(factor.evidence_packet_ids) != {packet.packet_id}:
        raise ValueError("R22 LLM factor lacks exact packet evidence")
    for relationship in factor.relationships:
        if relationship.source_entity not in allowed or relationship.target_entity not in allowed:
            raise ValueError("R22 LLM relationship introduced an unbound entity")
        if set(relationship.evidence_packet_ids) != {packet.packet_id}:
            raise ValueError("R22 LLM relationship lacks exact packet evidence")


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


def _lexical_direction(text: str) -> float:
    lowered = text.lower()
    positive = sum(term in lowered for term in POSITIVE_TERMS)
    negative = sum(term in lowered for term in NEGATIVE_TERMS)
    if positive + negative == 0:
        return 0.0
    return round((positive - negative) / (positive + negative), 6)


def _is_equity_symbol(symbol: str) -> bool:
    return bool(re.fullmatch(r"[A-Z][A-Z0-9.]{0,9}", symbol)) and symbol != "MARKET"


def _daily_session_rows(
    frame: pd.DataFrame,
    *,
    decision_session: date,
    symbol: str,
) -> dict[date, dict[str, float]]:
    required = {"timestamp", "open", "low", "close", "volume"}
    if frame.empty or not required.issubset(frame.columns):
        raise ValueError(f"R22 live daily frame is malformed: {symbol}")
    normalized = frame.loc[:, sorted(required)].copy()
    normalized["timestamp"] = pd.to_datetime(normalized["timestamp"], utc=True, errors="raise")
    normalized["session"] = normalized["timestamp"].dt.date
    normalized = normalized[normalized["session"] <= decision_session]
    if normalized["session"].duplicated().any():
        raise ValueError(f"R22 live daily frame has duplicate sessions: {symbol}")
    output: dict[date, dict[str, float]] = {}
    for row in normalized.to_dict(orient="records"):
        values = {field: float(row[field]) for field in ("open", "low", "close", "volume")}
        if (
            not all(math.isfinite(value) for value in values.values())
            or min(values["open"], values["low"], values["close"]) <= 0.0
            or values["volume"] < 0.0
            or values["low"] > min(values["open"], values["close"])
        ):
            raise ValueError(f"R22 live daily frame contains invalid OHLCV: {symbol}")
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
        raise ValueError("R22 forward target weights violate the long-only unit-budget contract")
    return weights


def _zero_weights() -> dict[str, float]:
    return {symbol: 0.0 for symbol in UNIVERSE}


def _verify_staged_receipt(root: Path, path: Path, receipt: dict[str, Any]) -> None:
    if _read_json(path) != receipt:
        raise ValueError("R22 staged receipt changed after publication")
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
            raise ValueError("R22 staged artifact does not match its receipt binding")


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
        raise ValueError("R22 forward receipt identity mismatch")
    decision_session = date.fromisoformat(str(receipt["decision_session"]))
    if receipt.get("action_session") != next_us_equity_session(decision_session).isoformat():
        raise ValueError("R22 forward receipt action session is invalid")
    expected_counted = decision_session > lock_state["anchor_session"]
    if receipt.get("counted_forward_session") is not expected_counted:
        raise ValueError("R22 forward receipt counting status is invalid")
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
        raise ValueError("R22 forward receipt artifact coverage mismatch")
    for binding in artifacts.values():
        _verify_binding(root, binding)
    for candidate_id, role in receipt["roles"].items():
        if set(role) != {"target", "intents", "execution"}:
            raise ValueError(f"R22 forward role binding coverage mismatch: {candidate_id}")
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
            raise ValueError(f"R22 forward role payload mismatch: {candidate_id}")
    f01 = _read_json(_verify_binding(root, receipt["roles"]["R22F01"]["target"]))
    m01 = _read_json(_verify_binding(root, receipt["roles"]["R22M01"]["target"]))
    if f01["target_sha256"] != m01["target_sha256"]:
        raise ValueError("R22 forward F01 target is not the exact M01 fallback")
    return receipt


def _result_from_receipt(
    root: Path,
    final_dir: Path,
    receipt: dict[str, Any],
) -> R22ForwardObservationResult:
    observation_path = _verify_binding(root, receipt["artifacts"]["observation"])
    payload = _read_json(observation_path)
    return R22ForwardObservationResult(
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
        raise ValueError(f"R22 forward {label} is invalid") from exc


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
            raise ValueError(f"R22 forward bound path cannot use symlinks: {candidate}")
    resolved = candidate.resolve(strict=True)
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"R22 forward bound path escapes project root: {candidate}") from exc
    if not resolved.is_file():
        raise ValueError(f"R22 forward bound path is not a regular file: {candidate}")
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
        raise ValueError("R22 forward file binding is malformed")
    path = _regular_in_root(root, root / str(binding["path"]))
    if _sha256(path) != binding["sha256"] or path.stat().st_size != binding["size_bytes"]:
        raise ValueError(f"R22 forward file binding changed: {binding.get('path')}")
    return path


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"R22 forward JSON artifact must be an object: {path}")
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
