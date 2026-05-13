from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from open_composer.config import ensure_dir
from open_composer.context import build_signal_context
from open_composer.models.event import EventRecord
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import append_jsonl, find_signal


class FeaturePacketError(ValueError):
    pass


FeatureValue = str | int | float | bool | None


class FeaturePacketRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    published_at: datetime
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source: str
    symbol: str
    dedupe_key: str
    schema_version: str = "1"
    summary: str = ""
    sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown"
    model: str | None = None
    input_hash: str | None = None
    prompt_hash: str | None = None
    features: dict[str, FeatureValue] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()


class FeaturePacketInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exists: bool = False
    record_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    point_in_time_status: Literal["complete", "partial", "missing"] = "missing"
    replay_warnings: list[str] = Field(default_factory=list)


def parse_feature_pairs(pairs: Iterable[str]) -> dict[str, FeatureValue]:
    features: dict[str, FeatureValue] = {}
    for pair in pairs:
        if "=" not in pair:
            raise FeaturePacketError(f"feature must use key=value syntax: {pair}")
        key, raw_value = pair.split("=", 1)
        key = key.strip()
        if not key:
            raise FeaturePacketError("feature key cannot be empty")
        features[key] = _parse_feature_value(raw_value.strip())
    return features


def build_manual_feature_packet(
    *,
    symbol: str,
    timestamp: datetime,
    source: str,
    features: dict[str, FeatureValue],
    published_at: datetime | None = None,
    fetched_at: datetime | None = None,
    dedupe_key: str | None = None,
    schema_version: str = "1",
    model: str | None = None,
    input_hash: str | None = None,
    prompt_hash: str | None = None,
    summary: str = "",
    sentiment: Literal["positive", "neutral", "negative", "unknown"] = "unknown",
) -> FeaturePacketRow:
    published = published_at or timestamp
    fetched = fetched_at or datetime.now(UTC)
    return FeaturePacketRow(
        timestamp=timestamp,
        published_at=published,
        fetched_at=fetched,
        source=source,
        symbol=symbol,
        dedupe_key=dedupe_key or f"{source}:{symbol.upper()}:{timestamp.isoformat()}",
        schema_version=schema_version,
        model=model,
        input_hash=input_hash,
        prompt_hash=prompt_hash,
        summary=summary,
        sentiment=sentiment,
        features=features,
    )


def build_context_feature_packet(signal_id: str, root: Path) -> FeaturePacketRow:
    signal = find_signal(signal_id, root)
    context = build_signal_context(signal_id, root)
    records = [*context.events, *context.news, *context.macro]
    latest_published = _max_datetime((record.published_at for record in records), signal.timestamp)
    latest_fetched = _max_datetime((record.fetched_at for record in records), datetime.now(UTC))
    features: dict[str, FeatureValue] = {
        "event_count": len(context.events),
        "news_count": len(context.news),
        "macro_count": len(context.macro),
        "context_record_count": len(records),
        "top_event_relevance": _top_relevance(context.events),
        "top_news_relevance": _top_relevance(context.news),
        "top_macro_relevance": _top_relevance(context.macro),
        "positive_news_count": _sentiment_count(context.news, "positive"),
        "negative_news_count": _sentiment_count(context.news, "negative"),
    }
    return FeaturePacketRow(
        timestamp=signal.timestamp,
        published_at=latest_published,
        fetched_at=latest_fetched,
        source="context",
        symbol=signal.symbol,
        dedupe_key=f"context:{signal.id}",
        schema_version="1",
        summary=f"Context-derived features for {signal.id}",
        sentiment=_context_sentiment(signal, context.news),
        features=features,
    )


def write_feature_packet(path: Path, packet: FeaturePacketRow) -> Path:
    ensure_dir(path.parent)
    return append_jsonl(path, [packet])


def inspect_feature_packet(path: Path, field: str | None = None) -> FeaturePacketInspection:
    if not path.exists():
        return FeaturePacketInspection(
            exists=False,
            point_in_time_status="missing",
            replay_warnings=["feature packet is missing on disk"],
        )

    rows: list[dict[str, object]] = []
    warnings: list[str] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                warnings.append(f"line {line_number} is not valid JSON")
                continue
            if isinstance(raw, dict):
                rows.append(raw)
            else:
                warnings.append(f"line {line_number} is not a JSON object")

    timestamps: list[datetime] = []
    invalid_timestamps = 0
    seen_dedupe_keys: set[str] = set()
    duplicate_dedupe_keys: set[str] = set()
    for row in rows:
        if row.get("timestamp"):
            try:
                timestamps.append(parse_datetime(str(row["timestamp"])))
            except FeaturePacketError:
                invalid_timestamps += 1
        dedupe_key = row.get("dedupe_key")
        if isinstance(dedupe_key, str):
            if dedupe_key in seen_dedupe_keys:
                duplicate_dedupe_keys.add(dedupe_key)
            seen_dedupe_keys.add(dedupe_key)

    key_sets = [set(row) for row in rows]
    has_timestamp = bool(rows) and all("timestamp" in keys for keys in key_sets)
    has_published_at = bool(rows) and all("published_at" in keys for keys in key_sets)
    has_fetched_at = bool(rows) and all("fetched_at" in keys for keys in key_sets)
    has_dedupe_key = bool(rows) and all("dedupe_key" in keys for keys in key_sets)
    has_schema_version = bool(rows) and all("schema_version" in keys for keys in key_sets)
    has_field = True
    if field:
        has_field = bool(rows) and any(_packet_value(row, field) is not _MISSING for row in rows)

    if not rows:
        warnings.append("feature packet contains no replayable rows")
    if not has_timestamp:
        warnings.append("timestamp is missing for at least one row")
    if invalid_timestamps:
        warnings.append(f"{invalid_timestamps} timestamp value(s) are not ISO-8601 parseable")
    if not has_published_at:
        warnings.append("published_at is missing for at least one row")
    if not has_fetched_at:
        warnings.append("fetched_at is missing for at least one row")
    if not has_dedupe_key:
        warnings.append("dedupe_key is missing for at least one row")
    if not has_schema_version:
        warnings.append("schema_version is missing for at least one row")
    if duplicate_dedupe_keys:
        warnings.append(
            "duplicate dedupe_key value(s): " + ", ".join(sorted(duplicate_dedupe_keys)[:5])
        )
    if field and not has_field:
        warnings.append(f"field {field!r} is missing from feature packet rows")

    if (
        has_timestamp
        and not invalid_timestamps
        and has_published_at
        and has_fetched_at
        and has_dedupe_key
        and has_schema_version
        and not duplicate_dedupe_keys
        and has_field
    ):
        point_in_time_status = "complete"
    elif has_timestamp:
        point_in_time_status = "partial"
    else:
        point_in_time_status = "missing"

    return FeaturePacketInspection(
        exists=True,
        record_count=len(rows),
        first_timestamp=min(timestamps).isoformat() if timestamps else None,
        last_timestamp=max(timestamps).isoformat() if timestamps else None,
        point_in_time_status=point_in_time_status,
        replay_warnings=warnings,
    )


def write_context_feature_packet(
    signal_id: str,
    root: Path,
    output: Path | None = None,
) -> Path:
    path = output or default_context_feature_path(root, signal_id)
    dedupe_key = f"context:{signal_id}"
    if _packet_has_dedupe_key(path, dedupe_key):
        return path
    packet = build_context_feature_packet(signal_id, root)
    return write_feature_packet(path, packet)


def should_auto_emit_context_features(spec: StrategySpec) -> bool:
    if spec.llm_review.enabled:
        return True
    if any(factor.source in {"llm_feature", "feature_packet"} for factor in spec.factors.values()):
        return True
    return False


def default_context_feature_path(root: Path, signal_id: str) -> Path:
    return root / "feature_logs" / f"{signal_id}_context_features.jsonl"


def parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FeaturePacketError(f"invalid datetime: {value}") from exc
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _parse_feature_value(value: str) -> FeatureValue:
    if value == "":
        return ""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return value
    if isinstance(parsed, str | int | float | bool) or parsed is None:
        return parsed
    raise FeaturePacketError("feature values must be string, number, bool, or null")


def _top_relevance(records: list[EventRecord]) -> float:
    if not records:
        return 0.0
    return max(record.relevance_score for record in records)


def _sentiment_count(records: list[EventRecord], sentiment: str) -> int:
    return sum(1 for record in records if record.sentiment == sentiment)


def _context_sentiment(signal: Signal, news: list[EventRecord]) -> str:
    positive = _sentiment_count(news, "positive")
    negative = _sentiment_count(news, "negative")
    if positive > negative:
        return "positive"
    if negative > positive:
        return "negative"
    return "neutral" if signal.action == "entry" else "unknown"


def _max_datetime(values: Iterable[datetime], default: datetime) -> datetime:
    normalized = [value if value.tzinfo else value.replace(tzinfo=UTC) for value in values]
    return max(normalized) if normalized else default


def _packet_has_dedupe_key(path: Path, dedupe_key: str) -> bool:
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            raw = json.loads(line)
            if isinstance(raw, dict) and raw.get("dedupe_key") == dedupe_key:
                return True
    return False


_MISSING = object()


def _packet_value(raw: dict[str, object], field: str) -> object:
    if field in raw:
        return raw[field]
    features = raw.get("features")
    if isinstance(features, dict) and field in features:
        return features[field]
    return _MISSING
