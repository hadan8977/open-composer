from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.config import ensure_dir
from open_composer.context import build_signal_context
from open_composer.models.event import EventRecord
from open_composer.models.signal import Signal
from open_composer.models.strategy_spec import StrategySpec
from open_composer.storage import append_jsonl, find_signal


class FeaturePacketError(ValueError):
    pass


FeatureValue = str | int | float | bool | None


class FeaturePacketEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    single_modality_baseline_metric: str
    marginal_lift_metric: str
    missing_modality_robustness: str
    fixture_path: str | None = None
    notes: str = ""

    @field_validator("fixture_path")
    @classmethod
    def validate_fixture_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            return None
        if stripped.startswith(("/", "\\")) or "\\" in stripped or ":" in stripped:
            raise ValueError("fixture_path must be a POSIX-style workspace-relative path")
        return stripped


class FeaturePacketRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    timestamp: datetime
    published_at: datetime
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    visible_at: datetime
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
    evidence: FeaturePacketEvidence | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper().strip()

    @model_validator(mode="after")
    def validate_point_in_time_order(self) -> FeaturePacketRow:
        self.timestamp = _as_utc(self.timestamp)
        self.published_at = _as_utc(self.published_at)
        self.fetched_at = _as_utc(self.fetched_at)
        self.visible_at = _as_utc(self.visible_at)
        if self.fetched_at < self.published_at:
            raise ValueError("fetched_at cannot precede published_at")
        if self.visible_at < self.fetched_at:
            raise ValueError("visible_at cannot precede fetched_at")
        return self


class FeaturePacketInspection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    exists: bool = False
    record_count: int = 0
    first_timestamp: str | None = None
    last_timestamp: str | None = None
    sources: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)
    schema_versions: list[str] = Field(default_factory=list)
    models: list[str] = Field(default_factory=list)
    input_hashes: list[str] = Field(default_factory=list)
    prompt_hashes: list[str] = Field(default_factory=list)
    missing_model_count: int = 0
    missing_input_hash_count: int = 0
    missing_prompt_hash_count: int = 0
    evidence_count: int = 0
    missing_evidence_count: int = 0
    evidence_fixture_paths: list[str] = Field(default_factory=list)
    dedupe_key_count: int = 0
    duplicate_dedupe_keys: list[str] = Field(default_factory=list)
    pit_order_violation_count: int = 0
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
    visible = _max_datetime([published, fetched], timestamp)
    return FeaturePacketRow(
        timestamp=timestamp,
        published_at=published,
        fetched_at=fetched,
        visible_at=visible,
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
    visible = _max_datetime([latest_published, latest_fetched], signal.timestamp)
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
        visible_at=visible,
        source="context",
        symbol=signal.symbol,
        dedupe_key=f"context:{signal.id}",
        schema_version="1",
        summary=f"Context-derived features for {signal.id}",
        sentiment=_context_sentiment(signal, context.news),
        features=features,
    )


def write_feature_packet(
    path: Path,
    packet: FeaturePacketRow,
    *,
    allow_research_only: bool = True,
) -> Path:
    if packet.evidence is None and not allow_research_only:
        raise FeaturePacketError(
            f"feature packet {packet.symbol}@{packet.timestamp.isoformat()} lacks evidence; "
            "cannot enter paper_auto path"
        )
    assert_visible_at_not_in_future(packet)
    ensure_dir(path.parent)
    return append_jsonl(path, [packet.model_dump(mode="json", exclude_none=True)])


def assert_visible_at_not_in_future(
    packet: FeaturePacketRow,
    now: datetime | None = None,
) -> None:
    current = now or datetime.now(UTC)
    visible_at = (
        packet.visible_at if packet.visible_at.tzinfo else packet.visible_at.replace(tzinfo=UTC)
    )
    current = current if current.tzinfo else current.replace(tzinfo=UTC)
    if visible_at > current:
        raise FeaturePacketError(
            f"feature packet visible_at {visible_at.isoformat()} is in the future"
        )


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
    pit_order_violation_count = 0
    invalid_pit_timestamp_count = 0
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
        if all(row.get(field) for field in ("published_at", "fetched_at", "visible_at")):
            try:
                published_at = parse_datetime(str(row["published_at"]))
                fetched_at = parse_datetime(str(row["fetched_at"]))
                visible_at = parse_datetime(str(row["visible_at"]))
            except FeaturePacketError:
                invalid_pit_timestamp_count += 1
            else:
                if fetched_at < published_at or visible_at < fetched_at:
                    pit_order_violation_count += 1

    key_sets = [set(row) for row in rows]
    has_timestamp = bool(rows) and all("timestamp" in keys for keys in key_sets)
    has_published_at = bool(rows) and all("published_at" in keys for keys in key_sets)
    has_fetched_at = bool(rows) and all("fetched_at" in keys for keys in key_sets)
    has_visible_at = bool(rows) and all("visible_at" in keys for keys in key_sets)
    has_dedupe_key = bool(rows) and all("dedupe_key" in keys for keys in key_sets)
    has_schema_version = bool(rows) and all("schema_version" in keys for keys in key_sets)
    has_field = True
    evidence_count = 0
    missing_evidence_count = 0
    evidence_fixture_paths: list[str] = []
    missing_model_count = 0
    missing_input_hash_count = 0
    missing_prompt_hash_count = 0
    for row in rows:
        if not row.get("model"):
            missing_model_count += 1
        if not row.get("input_hash"):
            missing_input_hash_count += 1
        if not row.get("prompt_hash"):
            missing_prompt_hash_count += 1
        evidence = row.get("evidence")
        if isinstance(evidence, dict):
            evidence_count += 1
            fixture_path = evidence.get("fixture_path")
            if isinstance(fixture_path, str) and fixture_path:
                evidence_fixture_paths.append(fixture_path)
        else:
            missing_evidence_count += 1
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
    if not has_visible_at:
        warnings.append("visible_at is missing for at least one row")
    if invalid_pit_timestamp_count:
        warnings.append(
            f"{invalid_pit_timestamp_count} PIT timestamp value(s) are not ISO-8601 parseable"
        )
    if pit_order_violation_count:
        warnings.append(
            f"{pit_order_violation_count} row(s) violate published_at <= fetched_at <= visible_at"
        )
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
        and has_visible_at
        and has_dedupe_key
        and has_schema_version
        and not duplicate_dedupe_keys
        and not invalid_pit_timestamp_count
        and not pit_order_violation_count
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
        sources=_sorted_values(row.get("source") for row in rows),
        symbols=_sorted_values(row.get("symbol") for row in rows),
        schema_versions=_sorted_values(row.get("schema_version") for row in rows),
        models=_sorted_values(row.get("model") for row in rows),
        input_hashes=_sorted_values(row.get("input_hash") for row in rows),
        prompt_hashes=_sorted_values(row.get("prompt_hash") for row in rows),
        missing_model_count=missing_model_count,
        missing_input_hash_count=missing_input_hash_count,
        missing_prompt_hash_count=missing_prompt_hash_count,
        evidence_count=evidence_count,
        missing_evidence_count=missing_evidence_count,
        evidence_fixture_paths=sorted(set(evidence_fixture_paths)),
        dedupe_key_count=len(_sorted_values(row.get("dedupe_key") for row in rows)),
        duplicate_dedupe_keys=sorted(duplicate_dedupe_keys),
        pit_order_violation_count=pit_order_violation_count,
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


def default_materialized_feature_path(root: Path, strategy_name: str, factor_name: str) -> Path:
    return root / "reports" / "features" / strategy_name / factor_name / "packets.jsonl"


def feature_packet_path_for_factor(
    root: Path,
    strategy_name: str,
    factor_name: str,
    factor: object,
) -> Path | None:
    path_value = getattr(factor, "path", None)
    if path_value:
        path = Path(str(path_value))
        return path if path.is_absolute() else root / path
    if getattr(factor, "source", "") == "llm_feature":
        return default_materialized_feature_path(root, strategy_name, factor_name)
    return None


def feature_packet_path_label(strategy_name: str, factor_name: str, factor: object) -> str | None:
    path_value = getattr(factor, "path", None)
    if path_value:
        return str(path_value)
    if getattr(factor, "source", "") == "llm_feature":
        return f"reports/features/{strategy_name}/{factor_name}/packets.jsonl"
    return None


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


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


_MISSING = object()


def _packet_value(raw: dict[str, object], field: str) -> object:
    if field in raw:
        return raw[field]
    features = raw.get("features")
    if isinstance(features, dict) and field in features:
        return features[field]
    return _MISSING


def _sorted_values(values: Iterable[object]) -> list[str]:
    return sorted({str(value) for value in values if value not in {None, ""}})
