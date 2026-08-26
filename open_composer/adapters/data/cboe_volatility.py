from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
import shutil
import tempfile
import urllib.request
from collections.abc import Callable, Iterable
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.market_calendar import (
    NEW_YORK,
    next_us_equity_session,
    us_equity_session_close,
)
from open_composer.storage import write_json

VIX_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"
VIX3M_HISTORY_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX3M_History.csv"
CAPABILITY_ID = "market.cboe_volatility_indices"
PUBLICATION_TIME_ET = time(16, 15)
VISIBLE_TIME_ET = time(9, 30)
CSV_COLUMNS = ("DATE", "OPEN", "HIGH", "LOW", "CLOSE")


class CboeVolatilityPacket(BaseModel):
    """A historical index observation with conservative next-session visibility."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    observation_date: date
    vix_open: float = Field(gt=0)
    vix_high: float = Field(gt=0)
    vix_low: float = Field(gt=0)
    vix_close: float = Field(gt=0)
    vix3m_open: float = Field(gt=0)
    vix3m_high: float = Field(gt=0)
    vix3m_low: float = Field(gt=0)
    vix3m_close: float = Field(gt=0)
    vix_to_vix3m_ratio: float = Field(gt=0)
    normalized_term_slope: float
    published_at: datetime
    visible_at: datetime
    fetched_at: datetime
    source: Literal["cboe_global_indices"] = "cboe_global_indices"
    source_urls: dict[str, str]
    input_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    prompt_hash: None = None
    prompt_hash_applicable: Literal[False] = False
    acquisition_mode: Literal["official_historical_csv_research_snapshot"] = (
        "official_historical_csv_research_snapshot"
    )
    published_at_basis: Literal["conservative_official_dissemination_window_end_1615_et"] = (
        "conservative_official_dissemination_window_end_1615_et"
    )
    visibility_basis: Literal["next_us_equity_regular_open_after_observation"] = (
        "next_us_equity_regular_open_after_observation"
    )
    fetched_at_is_historical_first_seen: Literal[False] = False

    @field_validator("published_at", "visible_at", "fetched_at")
    @classmethod
    def require_aware_utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("packet timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_prices_and_timing(self) -> CboeVolatilityPacket:
        _validate_ohlc(
            self.vix_open,
            self.vix_high,
            self.vix_low,
            self.vix_close,
            label="VIX",
        )
        _validate_ohlc(
            self.vix3m_open,
            self.vix3m_high,
            self.vix3m_low,
            self.vix3m_close,
            label="VIX3M",
        )
        if self.visible_at <= self.published_at:
            raise ValueError("visible_at must be after the completed index session")
        return self


def build_cboe_volatility_packets(
    vix_csv: bytes,
    vix3m_csv: bytes,
    *,
    fetched_at: datetime,
) -> list[CboeVolatilityPacket]:
    packets, _ = _build_packets_with_pairing_audit(
        vix_csv,
        vix3m_csv,
        fetched_at=fetched_at,
    )
    return packets


def _build_packets_with_pairing_audit(
    vix_csv: bytes,
    vix3m_csv: bytes,
    *,
    fetched_at: datetime,
) -> tuple[list[CboeVolatilityPacket], dict[str, object]]:
    fetched = _as_utc(fetched_at)
    vix_rows = _parse_index_csv(vix_csv, label="VIX")
    vix3m_rows = _parse_index_csv(vix3m_csv, label="VIX3M")
    common_dates, pairing_audit = _paired_observation_dates(vix_rows, vix3m_rows)
    if not common_dates:
        raise ValueError("Cboe VIX and VIX3M histories have no overlapping rows")

    packets: list[CboeVolatilityPacket] = []
    source_urls = {"VIX": VIX_HISTORY_URL, "VIX3M": VIX3M_HISTORY_URL}
    for observation_date in common_dates:
        vix = vix_rows[observation_date]
        vix3m = vix3m_rows[observation_date]
        published_at = datetime.combine(
            observation_date,
            PUBLICATION_TIME_ET,
            tzinfo=NEW_YORK,
        ).astimezone(UTC)
        visible_session = next_us_equity_session(observation_date)
        visible_at = datetime.combine(
            visible_session,
            VISIBLE_TIME_ET,
            tzinfo=NEW_YORK,
        ).astimezone(UTC)
        canonical_input = json.dumps(
            {
                "observation_date": observation_date.isoformat(),
                "source_urls": source_urls,
                "vix": vix,
                "vix3m": vix3m,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        packets.append(
            CboeVolatilityPacket(
                observation_date=observation_date,
                vix_open=vix["open"],
                vix_high=vix["high"],
                vix_low=vix["low"],
                vix_close=vix["close"],
                vix3m_open=vix3m["open"],
                vix3m_high=vix3m["high"],
                vix3m_low=vix3m["low"],
                vix3m_close=vix3m["close"],
                vix_to_vix3m_ratio=vix["close"] / vix3m["close"],
                normalized_term_slope=vix3m["close"] / vix["close"] - 1.0,
                published_at=published_at,
                visible_at=visible_at,
                fetched_at=fetched,
                source_urls=source_urls,
                input_hash=hashlib.sha256(canonical_input).hexdigest(),
            )
        )
    return packets, pairing_audit


def collect_cboe_volatility_snapshot(
    output_root: Path,
    *,
    fetch_bytes: Callable[[str], bytes] | None = None,
    fetched_at: datetime | None = None,
) -> Path:
    """Fetch and publish one immutable, read-only Cboe research snapshot."""

    output = output_root.resolve()
    if output.exists():
        raise ValueError(f"Cboe snapshot output already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    fetch = fetch_bytes or _http_get_bytes
    vix_csv = fetch(VIX_HISTORY_URL)
    vix3m_csv = fetch(VIX3M_HISTORY_URL)
    retrieved_at = _as_utc(fetched_at or datetime.now(UTC))
    packets, pairing_audit = _build_packets_with_pairing_audit(
        vix_csv,
        vix3m_csv,
        fetched_at=retrieved_at,
    )
    staleness_days = (retrieved_at.astimezone(NEW_YORK).date() - packets[-1].observation_date).days
    if staleness_days < 0 or staleness_days > 7:
        raise ValueError(
            "Cboe volatility snapshot latest observation is outside the seven-day "
            "collection freshness boundary"
        )

    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        raw_dir = stage / "raw"
        raw_dir.mkdir()
        vix_path = raw_dir / "VIX_History.csv"
        vix3m_path = raw_dir / "VIX3M_History.csv"
        vix_path.write_bytes(vix_csv)
        vix3m_path.write_bytes(vix3m_csv)

        packets_path = stage / "cboe-volatility-packets.jsonl"
        packet_text = "".join(
            json.dumps(packet.model_dump(mode="json"), sort_keys=True) + "\n" for packet in packets
        )
        packets_path.write_text(packet_text, encoding="utf-8")

        frame_path = stage / "cboe-volatility-daily.csv"
        frame = pd.DataFrame(packet.model_dump(mode="json") for packet in packets)
        frame.to_csv(frame_path, index=False)
        usable = [packet for packet in packets if packet.visible_at <= retrieved_at]
        manifest = {
            "schema_version": 1,
            "capability_id": CAPABILITY_ID,
            "provider": "cboe_global_indices",
            "fetched_at": retrieved_at.isoformat(),
            "immutable": True,
            "paper_ready": False,
            "historical_first_seen_claim": False,
            "visibility_policy": "next_us_equity_regular_open_after_observation",
            "publication_time_basis": ("conservative_official_dissemination_window_end_1615_et"),
            "source_urls": {"VIX": VIX_HISTORY_URL, "VIX3M": VIX3M_HISTORY_URL},
            "row_count": len(packets),
            "first_observation_date": packets[0].observation_date.isoformat(),
            "last_observation_date": packets[-1].observation_date.isoformat(),
            "latest_usable_observation_date": (
                usable[-1].observation_date.isoformat() if usable else None
            ),
            "overlap_policy": "intersection_without_forward_fill",
            "pairing_audit": pairing_audit,
            "collection_staleness_days": staleness_days,
            "inventory": [
                _inventory_row(vix_path, stage, "raw_official_csv"),
                _inventory_row(vix3m_path, stage, "raw_official_csv"),
                _inventory_row(packets_path, stage, "pit_packet_jsonl"),
                _inventory_row(frame_path, stage, "normalized_research_csv"),
            ],
            "limitations": [
                (
                    "Historical fetched_at is the actual snapshot retrieval time and is not "
                    "a historical first-seen timestamp."
                ),
                (
                    "VIX and VIX3M are non-tradable index levels; all execution must use "
                    "separately validated tradable instruments."
                ),
                (
                    "The research snapshot is not paper-ready until live collection latency "
                    "and fail-closed runtime behavior are verified."
                ),
            ],
        }
        write_json(stage / "snapshot-manifest.json", manifest)
        os.replace(stage, output)
    except Exception:
        shutil.rmtree(stage, ignore_errors=True)
        raise
    return output / "snapshot-manifest.json"


def load_cboe_volatility_snapshot(manifest_path: Path) -> pd.DataFrame:
    manifest_file = manifest_path.resolve()
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    if (
        manifest.get("capability_id") != CAPABILITY_ID
        or manifest.get("immutable") is not True
        or manifest.get("historical_first_seen_claim") is not False
    ):
        raise ValueError("invalid Cboe volatility snapshot manifest contract")
    root = manifest_file.parent
    inventory = manifest.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        raise ValueError("Cboe volatility snapshot inventory is missing")
    for row in inventory:
        path = _safe_inventory_path(root, str(row.get("path") or ""))
        if _sha256(path.read_bytes()) != row.get("sha256"):
            raise ValueError(f"Cboe volatility snapshot hash mismatch: {path.name}")
    frame_row = next(
        (row for row in inventory if row.get("role") == "normalized_research_csv"),
        None,
    )
    if frame_row is None:
        raise ValueError("Cboe volatility normalized CSV is missing")
    frame_path = _safe_inventory_path(root, str(frame_row["path"]))
    frame = pd.read_csv(frame_path)
    if len(frame) != int(manifest.get("row_count") or -1):
        raise ValueError("Cboe volatility snapshot row count mismatch")
    for column in ("published_at", "visible_at", "fetched_at"):
        frame[column] = pd.to_datetime(frame[column], utc=True, errors="raise")
    if frame["observation_date"].duplicated().any():
        raise ValueError("Cboe volatility snapshot contains duplicate dates")
    return frame.sort_values("observation_date").reset_index(drop=True)


def _parse_index_csv(payload: bytes, *, label: str) -> dict[date, dict[str, float]]:
    try:
        text = payload.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{label} history is not UTF-8 CSV") from exc
    reader = csv.DictReader(io.StringIO(text))
    if tuple(reader.fieldnames or ()) != CSV_COLUMNS:
        raise ValueError(f"{label} history columns do not match the Cboe contract")
    rows: dict[date, dict[str, float]] = {}
    for line_number, raw in enumerate(reader, start=2):
        try:
            observed = datetime.strptime(raw["DATE"].strip(), "%m/%d/%Y").date()
            values = {
                key.lower(): float(raw[key].strip()) for key in ("OPEN", "HIGH", "LOW", "CLOSE")
            }
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{label} history line {line_number} is invalid") from exc
        if observed in rows:
            raise ValueError(f"{label} history contains duplicate date {observed}")
        _validate_positive_values(values.values(), label=label)
        rows[observed] = values
    if not rows:
        raise ValueError(f"{label} history is empty")
    return rows


def _paired_observation_dates(
    vix_rows: dict[date, dict[str, float]],
    vix3m_rows: dict[date, dict[str, float]],
) -> tuple[list[date], dict[str, object]]:
    overlap_start = max(min(vix_rows), min(vix3m_rows))
    vix_dates = {day for day in vix_rows if day >= overlap_start}
    vix3m_dates = {day for day in vix3m_rows if day >= overlap_start}
    vix_only = sorted(vix_dates - vix3m_dates)
    vix3m_only = sorted(vix3m_dates - vix_dates)
    unmatched_sessions = [
        day for day in (*vix_only, *vix3m_only) if us_equity_session_close(day) is not None
    ]
    if unmatched_sessions:
        rendered = ",".join(day.isoformat() for day in sorted(unmatched_sessions)[:10])
        raise ValueError(f"Cboe VIX/VIX3M missing paired equity-session rows: {rendered}")
    common_dates = sorted(vix_dates.intersection(vix3m_dates))
    non_session_common = [day for day in common_dates if us_equity_session_close(day) is None]
    if non_session_common:
        rendered = ",".join(day.isoformat() for day in non_session_common[:10])
        raise ValueError(f"Cboe paired history contains non-equity-session rows: {rendered}")
    return common_dates, {
        "overlap_start": overlap_start.isoformat(),
        "paired_session_count": len(common_dates),
        "unmatched_equity_session_count": 0,
        "vix_only_non_session_dates": [day.isoformat() for day in vix_only],
        "vix3m_only_non_session_dates": [day.isoformat() for day in vix3m_only],
        "forward_fill_used": False,
    }


def _validate_ohlc(
    open_value: float,
    high_value: float,
    low_value: float,
    close_value: float,
    *,
    label: str,
) -> None:
    values = (open_value, high_value, low_value, close_value)
    _validate_positive_values(values, label=label)
    if high_value < max(open_value, close_value, low_value):
        raise ValueError(f"{label} high is below another OHLC value")
    if low_value > min(open_value, close_value, high_value):
        raise ValueError(f"{label} low is above another OHLC value")


def _validate_positive_values(values: Iterable[float], *, label: str) -> None:
    if not all(math.isfinite(float(value)) and float(value) > 0 for value in values):
        raise ValueError(f"{label} OHLC values must be finite and positive")


def _http_get_bytes(url: str) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "OpenComposer/1.0 read-only research"},
        method="GET",
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        if response.status != 200:
            raise ValueError(f"Cboe history request failed with HTTP {response.status}")
        return response.read()


def _inventory_row(path: Path, root: Path, role: str) -> dict[str, object]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "role": role,
        "size_bytes": len(payload),
        "sha256": _sha256(payload),
    }


def _safe_inventory_path(root: Path, relative: str) -> Path:
    candidate = (root / relative).resolve()
    if candidate != root and root not in candidate.parents:
        raise ValueError("Cboe volatility inventory path escapes snapshot root")
    if not candidate.is_file():
        raise ValueError(f"Cboe volatility inventory file is missing: {relative}")
    return candidate


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    return value.astimezone(UTC)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()
