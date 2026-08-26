from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import math
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal, Protocol

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from open_composer.adapters.data.alpaca import AlpacaDataError, _alpaca_timeframe
from open_composer.adapters.data.sample import REQUIRED_COLUMNS, normalize_ohlcv
from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key
from open_composer.market_calendar import (
    NEW_YORK,
    expected_us_equity_rth_bar_starts,
    us_equity_session_close,
)
from open_composer.models.strategy_spec import StrategySpec

PAGE_LIMIT = 10_000
MAX_PAGES = 10_000
ADJUSTMENT_ORDER = ("raw", "split", "dividend", "all")
SUPPORTED_ADJUSTMENTS = set(ADJUSTMENT_ORDER)
SUPPORTED_SNAPSHOT_TIMEFRAMES = {"daily", "1m", "5m", "15m", "30m"}
SAFE_SYMBOL_RE = re.compile(r"^[A-Z][A-Z0-9.-]{0,14}$")
CONTRACT_SCHEMA_PATH = Path("schemas/alpaca_snapshot_contract.schema.json")
MANIFEST_SCHEMA_PATH = Path("schemas/alpaca_snapshot_manifest.schema.json")
MANIFEST_NAME = "snapshot-manifest.json"
PUBLICATION_MARKER_NAME = "PUBLICATION_COMPLETE.json"
COLLECTOR_PATH = Path("open_composer/adapters/data/alpaca_snapshot.py")
CALENDAR_PATH = Path("open_composer/market_calendar.py")
PROVENANCE_ARCHIVE_ROOT = Path("open_composer/adapters/data/provenance_archive")
LEGACY_PROVENANCE_ARCHIVES = {
    (
        "manifest_schema",
        MANIFEST_SCHEMA_PATH.as_posix(),
        "b181dc7b8fd79eb27b9924c81d35b7a431606b612d37de03fb5b8f33f9376198",
    ): PROVENANCE_ARCHIVE_ROOT
    / (
        "alpaca_snapshot_manifest-"
        "b181dc7b8fd79eb27b9924c81d35b7a431606b612d37de03fb5b8f33f9376198.source"
    ),
    (
        "collector",
        COLLECTOR_PATH.as_posix(),
        "7c2c15cd83a7230d6c6f37f5d336dc236f93acb0aa0a73f47ff3bb6ca240d89b",
    ): PROVENANCE_ARCHIVE_ROOT
    / "alpaca_snapshot-7c2c15cd83a7230d6c6f37f5d336dc236f93acb0aa0a73f47ff3bb6ca240d89b.source",
    (
        "collector",
        COLLECTOR_PATH.as_posix(),
        "d1e5868ea65760ff80e99f5a4ff218c1ad1651bdc0c634113c2b065f6bb6cf9d",
    ): PROVENANCE_ARCHIVE_ROOT
    / "alpaca_snapshot-d1e5868ea65760ff80e99f5a4ff218c1ad1651bdc0c634113c2b065f6bb6cf9d.source",
    (
        "calendar",
        CALENDAR_PATH.as_posix(),
        "7146e57dc41935b1b669da86b4ad04d21500bbff042c1794db9d059c2aad1e6a",
    ): PROVENANCE_ARCHIVE_ROOT
    / "market_calendar-7146e57dc41935b1b669da86b4ad04d21500bbff042c1794db9d059c2aad1e6a.source",
}
SYMBOL_ASOF_SEMANTICS = "symbol_mapping_only_not_historical_data_vintage"
SPIN_OFF_SUPPORT = "provider_all_composite_only_no_independent_decomposition"
ALL_ADJUSTMENT_RISK = (
    "Alpaca adjustment=all is an independently retrieved provider composite that may include "
    "split, cash-dividend, and spin-off effects; it is not derived from or assumed equivalent "
    "to the raw, split, and dividend responses."
)


@dataclass(frozen=True)
class AlpacaRawHTTPResponse:
    """Exact, unmodified HTTP entity bytes returned by a raw snapshot transport."""

    status_code: int
    entity_bytes: bytes
    headers: Mapping[str, str]


class AlpacaSnapshotTransport(Protocol):
    def get_raw(
        self,
        *,
        path: str,
        data: dict[str, Any],
        headers: Mapping[str, str],
    ) -> AlpacaRawHTTPResponse: ...


class HttpxAlpacaSnapshotTransport:
    """Read-only Alpaca market-data transport preserving response entity bytes."""

    def __init__(self, api_key: str, secret_key: str) -> None:
        import httpx

        self._client = httpx.Client(
            base_url="https://data.alpaca.markets/v2",
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
            },
            timeout=60.0,
        )

    def get_raw(
        self,
        *,
        path: str,
        data: dict[str, Any],
        headers: Mapping[str, str],
    ) -> AlpacaRawHTTPResponse:
        response = self._client.get(path, params=data, headers=dict(headers))
        return AlpacaRawHTTPResponse(
            status_code=response.status_code,
            entity_bytes=response.content,
            headers=dict(response.headers),
        )

    def close(self) -> None:
        self._client.close()


class AlpacaSnapshotTimeframeContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbols: list[str] | None = None
    adjustments: list[Literal["all", "raw", "split", "dividend"]] = Field(min_length=1)
    requested_start: datetime
    requested_end_exclusive: datetime
    required_for: list[str] = Field(min_length=1)

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str] | None) -> list[str] | None:
        return _validated_symbols(value) if value is not None else None

    @field_validator("requested_start", "requested_end_exclusive")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("snapshot timestamps must include timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_window(self) -> AlpacaSnapshotTimeframeContract:
        if self.requested_start >= self.requested_end_exclusive:
            raise ValueError("snapshot request window must be positive and half-open")
        if len(self.adjustments) != len(set(self.adjustments)):
            raise ValueError("snapshot adjustments must be unique")
        return self


class AlpacaSnapshotContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    iter_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    provider: Literal["alpaca"]
    feed: Literal["sip"]
    adjustments: list[Literal["raw", "split", "dividend", "all"]] = Field(min_length=1)
    symbol_asof: date
    symbol_asof_semantics: Literal["symbol_mapping_only_not_historical_data_vintage"]
    currency: Literal["USD"]
    spin_off_handling: Literal["provider_all_composite_only_no_independent_decomposition"]
    historical_vintage_claim_allowed: Literal[False]
    session_scope: Literal["regular"]
    latest_frozen_session: date
    symbols: list[str] = Field(min_length=1)
    timeframes: dict[str, AlpacaSnapshotTimeframeContract]
    bundle_role: Literal["candidate_research", "selection_prohibited_execution_shadow"]
    candidate_required_dataset: str | None = None
    immutable_output_root: str = Field(min_length=1)
    manifest_requirements: list[str] = Field(min_length=1)
    forward_fill_allowed: Literal[False]
    zero_return_substitution_allowed: Literal[False]
    partial_completed_session_allowed: Literal[False]
    overwrite_existing_snapshot_allowed: Literal[False]

    @field_validator("symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        return _validated_symbols(value)

    @model_validator(mode="after")
    def validate_bundle(self) -> AlpacaSnapshotContract:
        if not self.timeframes:
            raise ValueError("snapshot contract requires non-empty timeframes")
        unknown = sorted(set(self.timeframes) - SUPPORTED_SNAPSHOT_TIMEFRAMES)
        if unknown:
            raise ValueError("unsupported snapshot timeframes: " + ", ".join(unknown))
        used_symbols: set[str] = set()
        for timeframe, row in self.timeframes.items():
            symbols = row.symbols or self.symbols
            used_symbols.update(symbols)
            if not set(symbols).issubset(self.symbols):
                raise ValueError(f"{timeframe} symbols must be a subset of contract symbols")
            expected_days = _expected_session_days(
                row.requested_start.date(),
                row.requested_end_exclusive.date(),
            )
            if not expected_days or expected_days[-1] != self.latest_frozen_session:
                raise ValueError(
                    f"{timeframe} request does not end at latest_frozen_session "
                    f"{self.latest_frozen_session.isoformat()}"
                )
        used_adjustments = {
            adjustment for row in self.timeframes.values() for adjustment in row.adjustments
        }
        if used_adjustments != set(self.adjustments):
            raise ValueError("timeframe adjustments must exactly cover contract adjustments")
        if used_symbols != set(self.symbols):
            raise ValueError("every contract symbol must be used by at least one timeframe")
        if self.bundle_role == "candidate_research":
            if set(self.timeframes) != {"daily"}:
                raise ValueError("candidate_research snapshot must contain only daily data")
            daily = self.timeframes["daily"]
            if (
                tuple(daily.adjustments) != ADJUSTMENT_ORDER
                or tuple(self.adjustments) != ADJUSTMENT_ORDER
            ):
                raise ValueError(
                    "candidate_research snapshot requires independent "
                    "raw/split/dividend/all adjustments in canonical order"
                )
            if self.candidate_required_dataset != "daily":
                raise ValueError(
                    "candidate_research snapshot requires candidate_required_dataset=daily"
                )
        else:
            if "daily" in self.timeframes:
                raise ValueError("execution shadow snapshot cannot contain daily data")
            if self.adjustments != ["raw"] or any(
                row.adjustments != ["raw"] for row in self.timeframes.values()
            ):
                raise ValueError("execution shadow snapshot requires adjustment=raw")
            if self.candidate_required_dataset is not None:
                raise ValueError("execution shadow cannot be a candidate-required dataset")
        return self


@dataclass(frozen=True)
class AlpacaSnapshotRequest:
    symbol: str
    timeframe: str
    start: datetime
    end_exclusive: datetime
    feed: str
    adjustment: str
    symbol_asof: date
    currency: str
    session_scope: str = "regular"

    @property
    def output_name(self) -> str:
        timeframe = "1d" if self.timeframe == "daily" else self.timeframe
        return (
            f"{self.symbol.lower()}_{timeframe}_alpaca_"
            f"{self.feed.lower()}_{self.adjustment.lower()}.csv"
        )


class SnapshotPageManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_number: int = Field(ge=1)
    path: str = Field(min_length=1)
    record_count: int = Field(ge=0)
    request_page_token: str | None
    response_next_page_token: str | None
    status_code: Literal[200]
    content_type: str = Field(min_length=1)
    content_encoding: Literal["identity"]
    entity_byte_count: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotQualityManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["complete"]
    expected_session_count: int = Field(ge=1)
    observed_session_count: int = Field(ge=1)
    expected_bar_count: int | None = Field(default=None, ge=1)
    observed_bar_count: int | None = Field(default=None, ge=1)
    provider_off_session_bar_count: int | None = Field(default=None, ge=0)
    complete_sessions: list[date]
    duplicate_timestamp_count: Literal[0]
    missing_timestamps: list[str] = Field(max_length=0)
    nonfinite_count: Literal[0]


class SnapshotItemManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.-]{0,14}$")
    timeframe: str
    feed: Literal["sip"]
    adjustment: Literal["raw", "split", "dividend", "all"]
    adjustment_semantics: Literal[
        "unadjusted",
        "split_adjusted",
        "cash_dividend_adjusted",
        "provider_all_composite_may_include_spin_offs",
    ]
    all_equivalence_assumed: Literal[False]
    session_scope: Literal["regular"]
    requested_start: datetime
    requested_end_exclusive: datetime
    symbol_asof: date
    symbol_asof_semantics: Literal["symbol_mapping_only_not_historical_data_vintage"]
    requested_currency: Literal["USD"]
    response_currency: Literal["USD"] | None
    response_currency_status: Literal["declared", "not_declared_by_bars_endpoint"]
    retrieved_at: datetime
    request_params: dict[str, Any]
    row_count: int = Field(ge=1)
    first_timestamp: datetime
    last_timestamp: datetime
    page_count: int = Field(ge=1)
    pages: list[SnapshotPageManifest] = Field(min_length=1)
    raw_pages_aggregate_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    normalized_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_path: str = Field(min_length=1)
    output_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    quality: SnapshotQualityManifest


class SnapshotInventoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str = Field(min_length=1)
    role: Literal["raw_http_entity", "normalized_csv", "item_manifest"]
    size_bytes: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class SnapshotAdjustmentPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requested_adjustments: list[Literal["raw", "split", "dividend", "all"]]
    independently_retrieved: Literal[True]
    all_equivalence_assumed: Literal[False]
    spin_off_support: Literal["provider_all_composite_only_no_independent_decomposition"]
    all_adjustment_risk: str

    @model_validator(mode="after")
    def validate_risk_statement(self) -> SnapshotAdjustmentPolicy:
        if self.all_adjustment_risk != ALL_ADJUSTMENT_RISK:
            raise ValueError("snapshot all-adjustment risk statement mismatch")
        return self


class AlpacaSnapshotManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[2]
    iter_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]{2,80}$")
    bundle_role: Literal["candidate_research", "selection_prohibited_execution_shadow"]
    provider: Literal["alpaca"]
    endpoint: Literal["https://data.alpaca.markets/v2/stocks/bars"]
    transport_contract: Literal["exact_http_entity_bytes_v1"]
    sdk_package: Literal["alpaca-py"]
    sdk_version: str = Field(min_length=1)
    retrieved_at: datetime
    contract_path: str = Field(min_length=1)
    contract_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_schema_path: Literal["schemas/alpaca_snapshot_contract.schema.json"]
    contract_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    manifest_schema_path: Literal["schemas/alpaca_snapshot_manifest.schema.json"]
    manifest_schema_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    collector_path: Literal["open_composer/adapters/data/alpaca_snapshot.py"]
    collector_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    calendar_path: Literal["open_composer/market_calendar.py"]
    calendar_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    output_root: str = Field(min_length=1)
    immutable: Literal[True]
    overwrite_allowed: Literal[False]
    request_count: int = Field(ge=1)
    adjustment_policy: SnapshotAdjustmentPolicy
    inventory_count: int = Field(ge=1)
    inventory: list[SnapshotInventoryEntry] = Field(min_length=1)
    publication_marker_path: Literal["PUBLICATION_COMPLETE.json"]
    items: list[SnapshotItemManifest] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_counts(self) -> AlpacaSnapshotManifest:
        if self.request_count != len(self.items):
            raise ValueError("snapshot manifest request_count mismatch")
        if self.inventory_count != len(self.inventory):
            raise ValueError("snapshot manifest inventory_count mismatch")
        if len({row.path for row in self.inventory}) != len(self.inventory):
            raise ValueError("snapshot manifest inventory paths must be unique")
        return self


class SnapshotPublicationMarker(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    status: Literal["complete"]
    manifest_path: Literal["snapshot-manifest.json"]
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    inventory_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def materialize_alpaca_contract_snapshot(
    root: Path,
    contract_path: Path,
    *,
    client: Any | None = None,
    retrieved_at: datetime | None = None,
) -> Path:
    root = root.resolve()
    contract_file = contract_path if contract_path.is_absolute() else root / contract_path
    contract_file = _safe_regular_file(root, contract_file, "snapshot contract")
    contract = _load_contract(contract_file)
    output_root = _safe_output_root(root, str(contract["immutable_output_root"]))
    if output_root.exists():
        raise AlpacaDataError(f"immutable snapshot already exists: {output_root}")

    requests = _requests_from_contract(contract)
    retrieved = (retrieved_at or datetime.now(UTC)).astimezone(UTC)
    latest_frozen_session = date.fromisoformat(str(contract["latest_frozen_session"]))
    _require_session_available(latest_frozen_session, retrieved)
    selected_client = client or _stock_data_client()
    owns_client = client is None
    _require_raw_transport(selected_client)
    _mkdirs_beneath_root(root, output_root.parent)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{output_root.name}.tmp-", dir=str(output_root.parent))
    )
    try:
        items = [
            _materialize_request(
                request,
                selected_client,
                temporary,
                retrieved_at=retrieved,
            )
            for request in requests
        ]
        for item in items:
            complete_sessions = item.get("quality", {}).get("complete_sessions", [])
            if not complete_sessions or complete_sessions[-1] != latest_frozen_session.isoformat():
                raise AlpacaDataError(
                    "snapshot item does not include the required latest frozen session"
                )
        inventory = _build_inventory(temporary)
        manifest_payload = {
            "schema_version": 2,
            "iter_id": contract["iter_id"],
            "bundle_role": contract["bundle_role"],
            "provider": "alpaca",
            "endpoint": "https://data.alpaca.markets/v2/stocks/bars",
            "transport_contract": "exact_http_entity_bytes_v1",
            "sdk_package": "alpaca-py",
            "sdk_version": version("alpaca-py"),
            "retrieved_at": retrieved.isoformat(),
            "contract_path": _relpath(contract_file, root),
            "contract_sha256": _sha256_file(contract_file),
            "contract_schema_path": CONTRACT_SCHEMA_PATH.as_posix(),
            "contract_schema_sha256": _sha256_file(root / CONTRACT_SCHEMA_PATH),
            "manifest_schema_path": MANIFEST_SCHEMA_PATH.as_posix(),
            "manifest_schema_sha256": _sha256_file(root / MANIFEST_SCHEMA_PATH),
            "collector_path": COLLECTOR_PATH.as_posix(),
            "collector_sha256": _sha256_file(Path(__file__)),
            "calendar_path": CALENDAR_PATH.as_posix(),
            "calendar_sha256": _sha256_file(root / CALENDAR_PATH),
            "output_root": _relpath(output_root, root),
            "immutable": True,
            "overwrite_allowed": False,
            "request_count": len(items),
            "adjustment_policy": {
                "requested_adjustments": contract["adjustments"],
                "independently_retrieved": True,
                "all_equivalence_assumed": False,
                "spin_off_support": SPIN_OFF_SUPPORT,
                "all_adjustment_risk": ALL_ADJUSTMENT_RISK,
            },
            "inventory_count": len(inventory),
            "inventory": inventory,
            "publication_marker_path": PUBLICATION_MARKER_NAME,
            "items": items,
        }
        try:
            AlpacaSnapshotManifest.model_validate(manifest_payload)
        except ValueError as exc:
            raise AlpacaDataError(f"generated snapshot manifest is invalid: {exc}") from exc
        manifest = manifest_payload
        manifest_bytes = _json_bytes(manifest)
        _write_durable_bytes(temporary / MANIFEST_NAME, manifest_bytes)
        marker = SnapshotPublicationMarker(
            schema_version=1,
            status="complete",
            manifest_path=MANIFEST_NAME,
            manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest(),
            inventory_sha256=_inventory_sha256(inventory),
        ).model_dump(mode="json")
        _write_durable_bytes(
            temporary / PUBLICATION_MARKER_NAME,
            _json_bytes(marker),
        )
        _fsync_and_seal_tree(temporary)
        _rename_noreplace(temporary, output_root)
        _fsync_directory(output_root.parent)
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise
    finally:
        if owns_client:
            close = getattr(selected_client, "close", None)
            if callable(close):
                close()
    return output_root / MANIFEST_NAME


def verify_alpaca_contract_snapshot(root: Path, manifest_path: Path) -> dict[str, Any]:
    root = root.resolve()
    manifest_file = manifest_path if manifest_path.is_absolute() else root / manifest_path
    manifest_file = _safe_regular_file(root, manifest_file, "snapshot manifest")
    if manifest_file.name != MANIFEST_NAME:
        raise AlpacaDataError(f"snapshot manifest must be named {MANIFEST_NAME}")
    manifest_raw = manifest_file.read_bytes()
    manifest_payload = _decode_json_object(manifest_raw, "snapshot manifest")
    try:
        AlpacaSnapshotManifest.model_validate(manifest_payload)
    except ValueError as exc:
        raise AlpacaDataError(f"snapshot manifest does not match schema v2: {exc}") from exc
    manifest = manifest_payload
    snapshot_root = manifest_file.parent.resolve()
    expected_output_root = _safe_existing_path(root, str(manifest.get("output_root") or ""))
    if expected_output_root != snapshot_root:
        raise AlpacaDataError("snapshot manifest output_root mismatch")

    marker_path = _safe_snapshot_child(
        snapshot_root,
        str(manifest["publication_marker_path"]),
        "publication marker",
    )
    marker_payload = _read_json_object(marker_path, "snapshot publication marker")
    try:
        marker = SnapshotPublicationMarker.model_validate(marker_payload)
    except ValueError as exc:
        raise AlpacaDataError(f"snapshot publication marker is invalid: {exc}") from exc
    if marker.manifest_sha256 != hashlib.sha256(manifest_raw).hexdigest():
        raise AlpacaDataError("snapshot publication marker manifest SHA-256 mismatch")
    if marker.inventory_sha256 != _inventory_sha256(manifest["inventory"]):
        raise AlpacaDataError("snapshot publication marker inventory SHA-256 mismatch")
    contract_path = _safe_existing_path(root, str(manifest.get("contract_path") or ""))
    if not contract_path.is_file():
        raise AlpacaDataError("snapshot contract is missing")
    if manifest.get("contract_sha256") != _sha256_file(contract_path):
        raise AlpacaDataError("snapshot contract SHA-256 mismatch")
    contract = _load_contract(contract_path)
    requests = _requests_from_contract(contract)

    for label in ("contract_schema", "manifest_schema", "collector", "calendar"):
        _verify_provenance_binding(
            root,
            label=label,
            declared_path=str(manifest.get(f"{label}_path") or ""),
            expected_sha256=str(manifest.get(f"{label}_sha256") or ""),
        )

    items = manifest.get("items")
    if not isinstance(items, list) or manifest.get("request_count") != len(items):
        raise AlpacaDataError("snapshot manifest item count mismatch")
    expected_identities = {
        (request.symbol, request.timeframe, request.adjustment) for request in requests
    }
    actual_identities: set[tuple[str, str, str]] = set()
    latest_frozen_session = str(contract["latest_frozen_session"])
    for item in items:
        if not isinstance(item, dict):
            raise AlpacaDataError("snapshot manifest item must be an object")
        identity = (
            str(item.get("symbol") or ""),
            str(item.get("timeframe") or ""),
            str(item.get("adjustment") or ""),
        )
        if identity in actual_identities:
            raise AlpacaDataError("snapshot manifest has duplicate request identity")
        actual_identities.add(identity)
        _verify_snapshot_item(snapshot_root, item, latest_frozen_session)
    if actual_identities != expected_identities:
        raise AlpacaDataError("snapshot manifest request identity mismatch")
    _verify_exact_inventory(snapshot_root, manifest)
    return manifest


def _verify_provenance_binding(
    root: Path,
    *,
    label: str,
    declared_path: str,
    expected_sha256: str,
) -> None:
    current_path = _safe_regular_file(root, root / declared_path, label)
    if _sha256_file(current_path) == expected_sha256:
        return

    archive_relative = LEGACY_PROVENANCE_ARCHIVES.get((label, declared_path, expected_sha256))
    if archive_relative is None:
        raise AlpacaDataError(f"snapshot {label} SHA-256 mismatch")
    archive_path = _safe_regular_file(root, root / archive_relative, f"{label} provenance archive")
    if _sha256_file(archive_path) != expected_sha256:
        raise AlpacaDataError(f"snapshot {label} archived SHA-256 mismatch")


def load_immutable_alpaca_snapshot(spec: StrategySpec, root: Path) -> pd.DataFrame:
    relative = spec.data.path
    if not relative:
        raise AlpacaDataError("immutable Alpaca StrategySpec requires data.path")
    path = _safe_existing_path(root, relative)
    if not path.exists():
        raise AlpacaDataError(f"immutable Alpaca snapshot is missing: {path}")
    manifest_path = path.with_suffix(".manifest.json")
    if not manifest_path.exists():
        raise AlpacaDataError(f"immutable Alpaca snapshot manifest is missing: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AlpacaDataError(
            f"immutable Alpaca manifest is invalid JSON: {manifest_path}"
        ) from exc
    if not isinstance(manifest, dict):
        raise AlpacaDataError("immutable Alpaca manifest must be an object")
    assumptions = spec.data_assumptions.model_dump(mode="json")
    expected_adjustment = str(assumptions.get("adjustment") or "")
    identity = {
        "symbol": spec.primary_symbol,
        "timeframe": spec.timeframe,
        "feed": spec.data.feed,
        "adjustment": expected_adjustment,
        "session_scope": assumptions.get("session_scope"),
    }
    mismatches = [key for key, expected in identity.items() if manifest.get(key) != expected]
    if mismatches:
        raise AlpacaDataError(
            "immutable Alpaca manifest identity mismatch: " + ", ".join(mismatches)
        )
    actual_hash = _sha256_file(path)
    if manifest.get("output_sha256") != actual_hash:
        raise AlpacaDataError("immutable Alpaca snapshot SHA-256 mismatch")
    try:
        frame = normalize_ohlcv(pd.read_csv(path))
    except (TypeError, ValueError) as exc:
        raise AlpacaDataError(f"immutable Alpaca snapshot is invalid: {exc}") from exc
    if len(frame) != manifest.get("row_count"):
        raise AlpacaDataError("immutable Alpaca snapshot row count mismatch")
    if frame.empty or frame["timestamp"].duplicated().any():
        raise AlpacaDataError("immutable Alpaca snapshot is empty or has duplicate timestamps")
    for column in ["open", "high", "low", "close", "volume"]:
        if not frame[column].map(lambda value: math.isfinite(float(value))).all():
            raise AlpacaDataError(f"immutable Alpaca snapshot has nonfinite {column}")
    first = frame["timestamp"].iloc[0].to_pydatetime().astimezone(UTC)
    last = frame["timestamp"].iloc[-1].to_pydatetime().astimezone(UTC)
    if first != _parse_utc(str(manifest.get("first_timestamp") or "")) or last != _parse_utc(
        str(manifest.get("last_timestamp") or "")
    ):
        raise AlpacaDataError("immutable Alpaca snapshot timestamp bounds mismatch")
    quality = manifest.get("quality")
    if not isinstance(quality, dict) or quality.get("status") != "complete":
        raise AlpacaDataError("immutable Alpaca snapshot quality is not complete")
    frame.attrs.update(
        {
            "data_source_provider": "alpaca",
            "data_source_mode": "immutable_research_snapshot",
            "data_source_feed": spec.data.feed,
            "data_source_path": str(path),
            "data_manifest_path": str(manifest_path),
            "data_manifest_sha256": _sha256_file(manifest_path),
        }
    )
    return frame


def _materialize_request(
    request: AlpacaSnapshotRequest,
    client: Any,
    output_root: Path,
    *,
    retrieved_at: datetime,
) -> dict[str, Any]:
    raw_root = output_root / "raw" / request.symbol.lower() / request.timeframe / request.adjustment
    _mkdirs_beneath_root(output_root, raw_root)
    params = _request_params(request)
    rows: list[dict[str, Any]] = []
    page_records = []
    page_token: str | None = None
    seen_tokens: set[str] = set()
    for page_number in range(1, MAX_PAGES + 1):
        page_params = {**params, "page_token": page_token}
        raw_response = client.get_raw(
            path="/stocks/bars",
            data=page_params,
            headers={"Accept": "application/json", "Accept-Encoding": "identity"},
        )
        response, response_headers = _validated_raw_response(raw_response)
        page_rows = _response_rows(response, request.symbol)
        rows.extend(page_rows)
        page_path = raw_root / f"page-{page_number:04d}.json"
        raw_bytes = raw_response.entity_bytes
        _write_durable_bytes(page_path, raw_bytes)
        next_token_raw = response.get("next_page_token")
        next_token = str(next_token_raw) if next_token_raw not in {None, ""} else None
        response_currency, response_currency_status = _response_currency(
            response_headers,
            request.currency,
        )
        page_records.append(
            {
                "page_number": page_number,
                "request_page_token": page_token,
                "response_next_page_token": next_token,
                "record_count": len(page_rows),
                "path": page_path.relative_to(output_root).as_posix(),
                "status_code": 200,
                "content_type": response_headers["content-type"],
                "content_encoding": "identity",
                "entity_byte_count": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
                "_response_currency": response_currency,
                "_response_currency_status": response_currency_status,
            }
        )
        if next_token is None:
            break
        if next_token in seen_tokens:
            raise AlpacaDataError(f"Alpaca pagination token repeated: {next_token}")
        seen_tokens.add(next_token)
        page_token = next_token
    else:
        raise AlpacaDataError(f"Alpaca response exceeded {MAX_PAGES} pages")

    frame, quality = _normalize_and_validate(rows, request)
    output_path = output_root / request.output_name
    output_bytes = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    _write_durable_bytes(output_path, output_bytes)
    output_hash = _sha256_file(output_path)
    raw_aggregate_hash = hashlib.sha256(
        "".join(record["sha256"] for record in page_records).encode("ascii")
    ).hexdigest()
    response_currencies = {row.pop("_response_currency") for row in page_records}
    response_currency_statuses = {row.pop("_response_currency_status") for row in page_records}
    if len(response_currencies) != 1 or len(response_currency_statuses) != 1:
        raise AlpacaDataError("Alpaca response currency metadata changed across pages")
    item_payload = {
        "symbol": request.symbol,
        "timeframe": request.timeframe,
        "feed": request.feed,
        "adjustment": request.adjustment,
        "adjustment_semantics": _adjustment_semantics(request.adjustment),
        "all_equivalence_assumed": False,
        "session_scope": request.session_scope,
        "requested_start": request.start.isoformat(),
        "requested_end_exclusive": request.end_exclusive.isoformat(),
        "symbol_asof": request.symbol_asof.isoformat(),
        "symbol_asof_semantics": SYMBOL_ASOF_SEMANTICS,
        "requested_currency": request.currency,
        "response_currency": response_currencies.pop(),
        "response_currency_status": response_currency_statuses.pop(),
        "request_params": _json_ready(params),
        "retrieved_at": retrieved_at.isoformat(),
        "output_path": output_path.relative_to(output_root).as_posix(),
        "output_sha256": output_hash,
        "normalized_sha256": output_hash,
        "raw_pages_aggregate_sha256": raw_aggregate_hash,
        "row_count": len(frame),
        "first_timestamp": frame["timestamp"].iloc[0].isoformat(),
        "last_timestamp": frame["timestamp"].iloc[-1].isoformat(),
        "page_count": len(page_records),
        "pages": page_records,
        "quality": quality,
    }
    try:
        item = SnapshotItemManifest.model_validate(item_payload).model_dump(mode="json")
    except ValueError as exc:
        raise AlpacaDataError(f"generated snapshot item is invalid: {exc}") from exc
    item["quality"] = {key: value for key, value in item["quality"].items() if value is not None}
    _write_durable_bytes(output_path.with_suffix(".manifest.json"), _json_bytes(item))
    return item


def _request_params(request: AlpacaSnapshotRequest) -> dict[str, Any]:
    try:
        from alpaca.common.enums import Sort, SupportedCurrencies
        from alpaca.data.enums import Adjustment, DataFeed
        from alpaca.data.requests import StockBarsRequest
    except ImportError as exc:
        raise AlpacaDataError("alpaca-py is required for immutable snapshots") from exc
    if request.adjustment not in SUPPORTED_ADJUSTMENTS:
        raise AlpacaDataError(f"unsupported Alpaca adjustment: {request.adjustment}")
    if request.session_scope != "regular":
        raise AlpacaDataError("immutable stock snapshots currently require session_scope=regular")
    sdk_request = StockBarsRequest(
        symbol_or_symbols=[request.symbol],
        timeframe=_alpaca_timeframe(request.timeframe),
        start=request.start,
        end=request.end_exclusive,
        limit=PAGE_LIMIT,
        currency=SupportedCurrencies(request.currency),
        adjustment=Adjustment(request.adjustment),
        feed=DataFeed(request.feed),
        sort=Sort.ASC,
        asof=request.symbol_asof.isoformat(),
    )
    normalized = _json_ready(sdk_request.to_request_fields())
    if not isinstance(normalized, dict):
        raise AlpacaDataError("Alpaca request parameters must normalize to an object")
    return normalized


def _validated_raw_response(
    response: Any,
) -> tuple[dict[str, Any], dict[str, str]]:
    if not isinstance(response, AlpacaRawHTTPResponse):
        raise AlpacaDataError(
            "immutable Alpaca snapshots require AlpacaRawHTTPResponse from a get_raw "
            "transport; SDK-decoded dictionaries cannot prove exact HTTP entity bytes"
        )
    if response.status_code != 200:
        raise AlpacaDataError(f"Alpaca bars returned HTTP status {response.status_code}")
    if not isinstance(response.entity_bytes, bytes) or not response.entity_bytes:
        raise AlpacaDataError("Alpaca raw transport returned empty or non-bytes entity data")
    headers = {str(key).lower(): str(value).strip() for key, value in response.headers.items()}
    content_type = headers.get("content-type", "").lower()
    if not content_type.startswith("application/json"):
        raise AlpacaDataError("Alpaca raw response content-type must be application/json")
    content_encoding = headers.get("content-encoding", "identity").lower()
    if content_encoding not in {"", "identity"}:
        raise AlpacaDataError(
            "Alpaca raw transport must request identity content encoding so stored entity "
            "bytes are directly parseable and unmodified"
        )
    headers["content-encoding"] = "identity"
    try:
        payload = json.loads(response.entity_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlpacaDataError("Alpaca raw HTTP entity is not valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise AlpacaDataError("Alpaca bars response must be a JSON object")
    return payload, headers


def _response_currency(
    headers: Mapping[str, str],
    requested_currency: str,
) -> tuple[str | None, str]:
    declared = headers.get("content-currency")
    if declared is None or not declared.strip():
        return None, "not_declared_by_bars_endpoint"
    normalized = declared.strip().upper()
    if normalized != requested_currency:
        raise AlpacaDataError(
            f"Alpaca response currency mismatch: requested={requested_currency} "
            f"declared={normalized}"
        )
    return normalized, "declared"


def _adjustment_semantics(adjustment: str) -> str:
    return {
        "raw": "unadjusted",
        "split": "split_adjusted",
        "dividend": "cash_dividend_adjusted",
        "all": "provider_all_composite_may_include_spin_offs",
    }[adjustment]


def _response_rows(response: dict[str, Any], symbol: str) -> list[dict[str, Any]]:
    bars = response.get("bars")
    if not isinstance(bars, dict):
        raise AlpacaDataError("Alpaca bars response requires a bars object")
    selected = bars.get(symbol.upper(), [])
    if not isinstance(selected, list):
        raise AlpacaDataError(f"Alpaca bars response for {symbol} must be a list")
    rows = []
    for raw in selected:
        if not isinstance(raw, dict):
            raise AlpacaDataError(f"Alpaca bar for {symbol} must be an object")
        rows.append(
            {
                "timestamp": raw.get("t", raw.get("timestamp")),
                "open": raw.get("o", raw.get("open")),
                "high": raw.get("h", raw.get("high")),
                "low": raw.get("l", raw.get("low")),
                "close": raw.get("c", raw.get("close")),
                "volume": raw.get("v", raw.get("volume")),
            }
        )
    return rows


def _normalize_and_validate(
    rows: list[dict[str, Any]],
    request: AlpacaSnapshotRequest,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if not rows:
        raise AlpacaDataError(f"Alpaca returned no bars for {request.symbol} {request.timeframe}")
    try:
        frame = normalize_ohlcv(pd.DataFrame(rows, columns=REQUIRED_COLUMNS))
    except (TypeError, ValueError) as exc:
        raise AlpacaDataError(f"invalid OHLCV response: {exc}") from exc
    timestamps = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")
    in_window = (timestamps >= pd.Timestamp(request.start)) & (
        timestamps < pd.Timestamp(request.end_exclusive)
    )
    frame = frame.loc[in_window].reset_index(drop=True)
    if frame.empty:
        raise AlpacaDataError("no bars remain inside the requested half-open window")
    if frame["timestamp"].duplicated().any():
        duplicates = frame.loc[frame["timestamp"].duplicated(False), "timestamp"]
        raise AlpacaDataError(f"duplicate Alpaca timestamps: {duplicates.iloc[0].isoformat()}")
    for column in ["open", "high", "low", "close", "volume"]:
        if not frame[column].map(lambda value: math.isfinite(float(value))).all():
            raise AlpacaDataError(f"nonfinite Alpaca values in {column}")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any():
        raise AlpacaDataError("Alpaca OHLC prices must be positive")
    if (frame["volume"] < 0).any():
        raise AlpacaDataError("Alpaca volume must be nonnegative")
    if (frame["high"] < frame[["open", "close", "low"]].max(axis=1)).any() or (
        frame["low"] > frame[["open", "close", "high"]].min(axis=1)
    ).any():
        raise AlpacaDataError("Alpaca OHLC bounds are inconsistent")

    if request.timeframe == "daily":
        frame, quality = _validate_daily_sessions(frame, request)
    else:
        frame, quality = _validate_intraday_sessions(frame, request)
    return frame, quality


def _validate_daily_sessions(
    frame: pd.DataFrame,
    request: AlpacaSnapshotRequest,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    expected_days = _expected_session_days(request.start.date(), request.end_exclusive.date())
    local_days = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert(NEW_YORK).dt.date
    counts = local_days.value_counts()
    duplicate_sessions = sorted(day.isoformat() for day, count in counts.items() if count != 1)
    observed_days = set(local_days)
    missing = sorted(day.isoformat() for day in set(expected_days) - observed_days)
    extra = sorted(day.isoformat() for day in observed_days - set(expected_days))
    if duplicate_sessions or missing or extra:
        raise AlpacaDataError(
            "daily session completeness failed: "
            f"duplicates={duplicate_sessions[:3]} missing={missing[:3]} extra={extra[:3]}"
        )
    return frame, {
        "status": "complete",
        "expected_session_count": len(expected_days),
        "observed_session_count": len(observed_days),
        "complete_sessions": [day.isoformat() for day in expected_days],
        "missing_timestamps": [],
        "duplicate_timestamp_count": 0,
        "nonfinite_count": 0,
    }


def _validate_intraday_sessions(
    frame: pd.DataFrame,
    request: AlpacaSnapshotRequest,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    minutes = _timeframe_minutes(request.timeframe)
    expected_days = _expected_session_days(request.start.date(), request.end_exclusive.date())
    expected = {
        timestamp
        for day in expected_days
        for timestamp in expected_us_equity_rth_bar_starts(day, minutes)
    }
    parsed = pd.to_datetime(frame["timestamp"], utc=True)
    regular_mask = parsed.map(_is_regular_session_timestamp)
    off_session_count = int((~regular_mask).sum())
    frame = frame.loc[regular_mask].reset_index(drop=True)
    timestamps = set(pd.to_datetime(frame["timestamp"], utc=True))
    missing = sorted(expected - timestamps)
    extra = sorted(timestamps - expected)
    if missing or extra:
        raise AlpacaDataError(
            "intraday session completeness failed: "
            f"missing={[_iso(item) for item in missing[:3]]} "
            f"extra={[_iso(item) for item in extra[:3]]}"
        )
    complete_sessions = sorted(
        {timestamp.tz_convert(NEW_YORK).date().isoformat() for timestamp in timestamps}
    )
    return frame, {
        "status": "complete",
        "expected_session_count": len(expected_days),
        "observed_session_count": len(complete_sessions),
        "expected_bar_count": len(expected),
        "observed_bar_count": len(timestamps),
        "provider_off_session_bar_count": off_session_count,
        "complete_sessions": complete_sessions,
        "missing_timestamps": [],
        "duplicate_timestamp_count": 0,
        "nonfinite_count": 0,
    }


def _is_regular_session_timestamp(timestamp: pd.Timestamp) -> bool:
    local = timestamp.tz_convert(NEW_YORK)
    close = us_equity_session_close(local.date())
    if close is None:
        return False
    local_time = local.time().replace(tzinfo=None)
    return time(9, 30) <= local_time < close


def _requests_from_contract(contract: dict[str, Any]) -> list[AlpacaSnapshotRequest]:
    if contract.get("provider") != "alpaca":
        raise AlpacaDataError("snapshot contract provider must be alpaca")
    feed = str(contract.get("feed") or "").lower()
    if feed != "sip":
        raise AlpacaDataError("immutable research contract requires feed=sip")
    session_scope = str(contract.get("session_scope") or "regular")
    global_symbols = _symbols(contract.get("symbols"))
    global_adjustments = [str(value).lower() for value in contract.get("adjustments", [])]
    symbol_asof = date.fromisoformat(str(contract.get("symbol_asof") or ""))
    currency = str(contract.get("currency") or "")
    timeframes = contract.get("timeframes")
    if not isinstance(timeframes, dict) or not timeframes:
        raise AlpacaDataError("snapshot contract requires non-empty timeframes")
    requests = []
    for timeframe, raw in timeframes.items():
        if not isinstance(raw, dict):
            raise AlpacaDataError(f"timeframe contract must be an object: {timeframe}")
        symbols = _symbols(raw.get("symbols")) or global_symbols
        adjustments_raw = raw.get("adjustments", global_adjustments)
        if not isinstance(adjustments_raw, list) or not adjustments_raw:
            raise AlpacaDataError(f"timeframe adjustments must be non-empty: {timeframe}")
        start = _parse_utc(str(raw.get("requested_start") or ""))
        end = _parse_utc(str(raw.get("requested_end_exclusive") or ""))
        if start >= end:
            raise AlpacaDataError(f"invalid half-open request window for {timeframe}")
        for symbol in symbols:
            for adjustment in adjustments_raw:
                requests.append(
                    AlpacaSnapshotRequest(
                        symbol=symbol,
                        timeframe=str(timeframe),
                        start=start,
                        end_exclusive=end,
                        feed=feed,
                        adjustment=str(adjustment).lower(),
                        symbol_asof=symbol_asof,
                        currency=currency,
                        session_scope=session_scope,
                    )
                )
    if not requests:
        raise AlpacaDataError("snapshot contract produced no requests")
    return requests


def _load_contract(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AlpacaDataError(f"snapshot contract is invalid JSON: {path}") from exc
    if not isinstance(payload, dict):
        raise AlpacaDataError("snapshot contract must be a JSON object")
    try:
        contract = AlpacaSnapshotContract.model_validate(payload)
    except ValueError as exc:
        raise AlpacaDataError(f"snapshot contract is invalid: {exc}") from exc
    return contract.model_dump(mode="json")


def _stock_data_client() -> Any:
    api_key = alpaca_api_key_id()
    secret_key = alpaca_api_secret_key()
    if not api_key or not secret_key:
        raise AlpacaDataError("Alpaca market-data credentials are not configured")
    return HttpxAlpacaSnapshotTransport(api_key, secret_key)


def _require_raw_transport(client: Any) -> None:
    if not callable(getattr(client, "get_raw", None)):
        raise AlpacaDataError(
            "immutable Alpaca snapshots require a get_raw transport that returns exact "
            "AlpacaRawHTTPResponse entity bytes"
        )


def _expected_session_days(start: date, end_exclusive: date) -> list[date]:
    days = []
    day = start
    while day < end_exclusive:
        if us_equity_session_close(day) is not None:
            days.append(day)
        day += timedelta(days=1)
    return days


def _timeframe_minutes(timeframe: str) -> int:
    if not timeframe.endswith("m"):
        raise AlpacaDataError(f"session-complete snapshot does not support {timeframe}")
    try:
        value = int(timeframe[:-1])
    except ValueError as exc:
        raise AlpacaDataError(f"invalid minute timeframe: {timeframe}") from exc
    if value <= 0 or 390 % value != 0:
        raise AlpacaDataError(f"timeframe must divide the 390-minute regular session: {timeframe}")
    return value


def _symbols(value: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AlpacaDataError("symbols must be an array")
    symbols = [str(symbol).strip().upper() for symbol in value if str(symbol).strip()]
    if len(symbols) != len(set(symbols)):
        raise AlpacaDataError("symbols must be unique")
    return symbols


def _validated_symbols(value: list[str]) -> list[str]:
    symbols = [str(symbol).strip().upper() for symbol in value]
    if any(not SAFE_SYMBOL_RE.fullmatch(symbol) for symbol in symbols):
        raise ValueError("snapshot symbols contain an unsafe or unsupported value")
    if len(symbols) != len(set(symbols)):
        raise ValueError("snapshot symbols must be unique")
    return symbols


def _parse_utc(value: str) -> datetime:
    if not value:
        raise AlpacaDataError("snapshot timestamps are required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AlpacaDataError(f"invalid snapshot timestamp: {value}") from exc
    if parsed.tzinfo is None:
        raise AlpacaDataError(f"snapshot timestamp must include timezone: {value}")
    return parsed.astimezone(UTC)


def _safe_output_root(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise AlpacaDataError("immutable_output_root must be repository-relative")
    resolved_root = root.resolve()
    _reject_symlink_ancestors(resolved_root, path, "immutable_output_root")
    resolved = root / path
    if resolved == resolved_root or resolved_root not in resolved.parents:
        raise AlpacaDataError("immutable_output_root escapes repository root")
    return resolved


def _safe_existing_path(root: Path, relative: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise AlpacaDataError("immutable Alpaca data.path must be repository-relative")
    resolved_root = root.resolve()
    _reject_symlink_ancestors(resolved_root, path, "immutable Alpaca path")
    resolved = root / path
    if resolved_root not in resolved.parents:
        raise AlpacaDataError("immutable Alpaca data.path escapes repository root")
    return resolved


def _safe_path_within(root: Path, path: Path, label: str) -> Path:
    resolved_root = root.resolve()
    try:
        relative = path.relative_to(resolved_root)
    except ValueError as exc:
        raise AlpacaDataError(f"{label} escapes repository root") from exc
    _reject_symlink_ancestors(resolved_root, relative, label)
    resolved = path
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise AlpacaDataError(f"{label} escapes repository root") from exc
    return resolved


def _safe_snapshot_child(snapshot_root: Path, relative: str, label: str) -> Path:
    path = Path(relative)
    if path.is_absolute():
        raise AlpacaDataError(f"snapshot {label} path must be relative")
    resolved_root = snapshot_root.resolve()
    _reject_symlink_ancestors(resolved_root, path, label)
    resolved = snapshot_root / path
    try:
        resolved.relative_to(resolved_root)
    except ValueError as exc:
        raise AlpacaDataError(f"snapshot {label} path escapes snapshot root") from exc
    return resolved


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    return _decode_json_object(_read_regular_bytes(path, label), label)


def _decode_json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AlpacaDataError(f"{label} is invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AlpacaDataError(f"{label} must be a JSON object")
    return payload


def _safe_regular_file(root: Path, path: Path, label: str) -> Path:
    safe = _safe_path_within(root, path, label)
    try:
        mode = safe.lstat().st_mode
    except FileNotFoundError as exc:
        raise AlpacaDataError(f"{label} is missing: {safe}") from exc
    if not stat.S_ISREG(mode):
        raise AlpacaDataError(f"{label} must be a regular non-symlink file: {safe}")
    return safe


def _read_regular_bytes(path: Path, label: str) -> bytes:
    try:
        mode = path.lstat().st_mode
    except FileNotFoundError as exc:
        raise AlpacaDataError(f"{label} is missing: {path}") from exc
    if not stat.S_ISREG(mode):
        raise AlpacaDataError(f"{label} must be a regular non-symlink file: {path}")
    return path.read_bytes()


def _reject_symlink_ancestors(root: Path, relative: Path, label: str) -> None:
    current = root
    for component in relative.parts[:-1]:
        current = current / component
        if current.is_symlink():
            raise AlpacaDataError(f"{label} has a symlinked ancestor: {current}")


def _mkdirs_beneath_root(root: Path, path: Path) -> None:
    root = root.resolve()
    try:
        relative = path.relative_to(root)
    except ValueError as exc:
        raise AlpacaDataError(f"output path escapes repository root: {path}") from exc
    current = root
    for component in relative.parts:
        current = current / component
        if current.exists():
            if current.is_symlink() or not current.is_dir():
                raise AlpacaDataError(f"output path component is not a real directory: {current}")
        else:
            current.mkdir()
            _fsync_directory(current.parent)


def _write_durable_bytes(path: Path, payload: bytes) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise OSError("short write while publishing snapshot artifact")
            view = view[written:]
        os.fsync(fd)
    finally:
        os.close(fd)
    _fsync_directory(path.parent)


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _fsync_and_seal_tree(root: Path) -> None:
    directories: list[Path] = []
    for path in sorted(root.rglob("*")):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise AlpacaDataError(f"snapshot staging contains unsupported entry: {path}")
        if stat.S_ISDIR(mode):
            directories.append(path)
        else:
            _fsync_file(path)
            os.chmod(path, 0o444)
    for directory in sorted(directories, key=lambda item: len(item.parts), reverse=True):
        os.chmod(directory, 0o555)
        _fsync_directory(directory)
    os.chmod(root, 0o555)
    _fsync_directory(root)


def _fsync_file(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _rename_noreplace(source: Path, destination: Path) -> None:
    if os.name != "posix" or not hasattr(ctypes.CDLL(None), "renameat2"):
        raise AlpacaDataError("atomic no-clobber publication requires Linux renameat2")
    libc = ctypes.CDLL(None, use_errno=True)
    renameat2 = libc.renameat2
    renameat2.argtypes = [
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    ]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        -100,
        os.fsencode(source),
        -100,
        os.fsencode(destination),
        1,
    )
    if result != 0:
        error = ctypes.get_errno()
        if error == errno.EEXIST:
            raise AlpacaDataError(f"immutable snapshot already exists: {destination}")
        raise OSError(error, os.strerror(error), destination)


def _json_bytes(payload: Any) -> bytes:
    return (json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n").encode("utf-8")


def _build_inventory(root: Path) -> list[dict[str, Any]]:
    entries = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == MANIFEST_NAME or relative == PUBLICATION_MARKER_NAME:
            continue
        if relative.startswith("raw/"):
            role = "raw_http_entity"
        elif relative.endswith(".manifest.json"):
            role = "item_manifest"
        elif relative.endswith(".csv"):
            role = "normalized_csv"
        else:
            raise AlpacaDataError(f"unclassified snapshot artifact: {relative}")
        entries.append(
            {
                "path": relative,
                "role": role,
                "size_bytes": path.stat().st_size,
                "sha256": _sha256_file(path),
            }
        )
    if not entries:
        raise AlpacaDataError("snapshot bundle has no artifacts to publish")
    return entries


def _inventory_sha256(inventory: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_json_bytes(inventory)).hexdigest()


def _verify_exact_inventory(snapshot_root: Path, manifest: dict[str, Any]) -> None:
    expected = {entry["path"] for entry in manifest["inventory"]}
    expected.update({MANIFEST_NAME, PUBLICATION_MARKER_NAME})
    actual: set[str] = set()
    for path in snapshot_root.rglob("*"):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
            raise AlpacaDataError(f"snapshot contains symlink or unsupported entry: {path}")
        if stat.S_ISREG(mode):
            actual.add(path.relative_to(snapshot_root).as_posix())
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise AlpacaDataError(f"snapshot exact inventory mismatch: missing={missing} extra={extra}")
    for entry in manifest["inventory"]:
        path = _safe_snapshot_child(snapshot_root, entry["path"], "inventory artifact")
        if path.stat().st_size != entry["size_bytes"] or _sha256_file(path) != entry["sha256"]:
            raise AlpacaDataError(f"snapshot inventory hash mismatch: {entry['path']}")


def _verify_snapshot_item(
    snapshot_root: Path,
    item: dict[str, Any],
    latest_frozen_session: str,
) -> None:
    output_path = _safe_snapshot_child(
        snapshot_root,
        str(item.get("output_path") or ""),
        "normalized output",
    )
    if not output_path.is_file() or item.get("output_sha256") != _sha256_file(output_path):
        raise AlpacaDataError("snapshot normalized output SHA-256 mismatch")
    sidecar_path = output_path.with_suffix(".manifest.json")
    sidecar = _read_json_object(sidecar_path, "snapshot item sidecar")
    if sidecar != item:
        raise AlpacaDataError("snapshot item sidecar does not match aggregate manifest")

    pages = item.get("pages")
    if not isinstance(pages, list) or item.get("page_count") != len(pages) or not pages:
        raise AlpacaDataError("snapshot raw page count mismatch")
    page_hashes: list[str] = []
    for page in pages:
        if not isinstance(page, dict):
            raise AlpacaDataError("snapshot raw page record must be an object")
        page_path = _safe_snapshot_child(
            snapshot_root,
            str(page.get("path") or ""),
            "raw page",
        )
        if not page_path.is_file():
            raise AlpacaDataError("snapshot raw page is missing")
        actual_hash = _sha256_file(page_path)
        if page.get("sha256") != actual_hash:
            raise AlpacaDataError("snapshot raw page SHA-256 mismatch")
        page_hashes.append(actual_hash)
    aggregate_hash = hashlib.sha256("".join(page_hashes).encode("ascii")).hexdigest()
    if item.get("raw_pages_aggregate_sha256") != aggregate_hash:
        raise AlpacaDataError("snapshot raw-page aggregate SHA-256 mismatch")

    try:
        frame = normalize_ohlcv(pd.read_csv(output_path))
    except (TypeError, ValueError) as exc:
        raise AlpacaDataError(f"snapshot normalized output is invalid: {exc}") from exc
    if frame.empty or len(frame) != item.get("row_count"):
        raise AlpacaDataError("snapshot normalized row count mismatch")
    if frame["timestamp"].duplicated().any():
        raise AlpacaDataError("snapshot normalized output has duplicate timestamps")
    for column in ["open", "high", "low", "close", "volume"]:
        if not frame[column].map(lambda value: math.isfinite(float(value))).all():
            raise AlpacaDataError(f"snapshot normalized output has nonfinite {column}")
    first_timestamp = frame["timestamp"].iloc[0].to_pydatetime().astimezone(UTC)
    last_timestamp = frame["timestamp"].iloc[-1].to_pydatetime().astimezone(UTC)
    if first_timestamp != _parse_utc(str(item.get("first_timestamp") or "")) or (
        last_timestamp != _parse_utc(str(item.get("last_timestamp") or ""))
    ):
        raise AlpacaDataError("snapshot normalized timestamp bounds mismatch")
    quality = item.get("quality")
    complete_sessions = quality.get("complete_sessions") if isinstance(quality, dict) else None
    if (
        not isinstance(quality, dict)
        or quality.get("status") != "complete"
        or not isinstance(complete_sessions, list)
        or not complete_sessions
        or complete_sessions[-1] != latest_frozen_session
    ):
        raise AlpacaDataError("snapshot item latest-session quality mismatch")


def _require_session_available(session: date, retrieved_at: datetime) -> None:
    close = us_equity_session_close(session)
    if close is None:
        raise AlpacaDataError("latest_frozen_session is not a US equity session")
    available_at = datetime.combine(session, close, tzinfo=NEW_YORK).astimezone(UTC) + timedelta(
        minutes=15
    )
    if retrieved_at < available_at:
        raise AlpacaDataError("latest_frozen_session is not yet safely available at retrieval time")


def _json_ready(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_ready(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, "value"):
        return _json_ready(value.value)
    return value


def _canonical_json_bytes(payload: dict[str, Any]) -> bytes:
    return (
        json.dumps(
            _json_ready(payload),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _iso(timestamp: pd.Timestamp) -> str:
    return timestamp.isoformat()
