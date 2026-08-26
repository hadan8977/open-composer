from __future__ import annotations

import csv
import hashlib
import io
import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from open_composer.config import ensure_dir
from open_composer.models.event import EventRecord
from open_composer.storage import write_json

CFTC_TFF_FUTURES_ONLY_DATASET = "gpe5-46if"
CFTC_TFF_ENDPOINT = f"https://publicreporting.cftc.gov/resource/{CFTC_TFF_FUTURES_ONLY_DATASET}.csv"
CFTC_TFF_METADATA_URL = (
    f"https://publicreporting.cftc.gov/api/views/{CFTC_TFF_FUTURES_ONLY_DATASET}"
)
CFTC_COT_DOCS_URL = "https://www.cftc.gov/MarketReports/CommitmentsofTraders/index.htm"
CFTC_COT_SPECIAL_ANNOUNCEMENTS_URL = (
    "https://www.cftc.gov/MarketReports/CommitmentsofTraders/"
    "HistoricalSpecialAnnouncements/index.htm"
)

# CFTC began populating PRE with native per-release row timestamps for the report dated
# 2022-09-13. Older reports all carry the same 2022-09-13 migration timestamp, so replay
# uses a deliberately stale two-week rule and excludes the 2018-2019 shutdown backlog.
CFTC_PRE_NATIVE_REPORT_START = date(2022, 9, 13)
CFTC_LEGACY_CONSERVATIVE_LAG_DAYS = 14
CFTC_TFF_TRANSFORM_CONTRACT = "open-composer:cftc-tff-event:v1"
CFTC_TFF_TRANSFORM_HASH = hashlib.sha256(CFTC_TFF_TRANSFORM_CONTRACT.encode()).hexdigest()

_NEW_YORK = ZoneInfo("America/New_York")
_REGULAR_OPEN = time(9, 30)
_LEGACY_EXCLUDED_WINDOWS = (
    # The last pre-shutdown report was published 2018-12-21. Catch-up publication
    # began 2019-02-01 at two reports per week; this wider interval fails closed.
    (date(2018, 12, 24), date(2019, 3, 12), "2018_2019_federal_shutdown_backlog"),
)

_CONTRACT_CODES = {
    "NQ_COT": ("20974+",),
    "ES_COT": ("13874+",),
    "VX_COT": ("1170E1",),
}

_FIELDS = [
    ":id",
    ":created_at",
    ":updated_at",
    "id",
    "report_date_as_yyyy_mm_dd",
    "market_and_exchange_names",
    "cftc_contract_market_code",
    "open_interest_all",
    "dealer_positions_long_all",
    "dealer_positions_short_all",
    "asset_mgr_positions_long",
    "asset_mgr_positions_short",
    "lev_money_positions_long",
    "lev_money_positions_short",
    "other_rept_positions_long",
    "other_rept_positions_short",
    "nonrept_positions_long_all",
    "nonrept_positions_short_all",
]


@dataclass(frozen=True)
class CFTCSnapshotResult:
    events: list[EventRecord]
    snapshot_path: Path
    manifest_path: Path
    excluded_records: int


@dataclass(frozen=True)
class _CFTCDownload:
    records: list[dict[str, str]]
    retrieved_at: datetime
    request_url: str


def fetch_cftc_tff_events(
    *,
    contracts: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    timeout: float = 30.0,
) -> list[EventRecord]:
    download = _download_cftc_tff_records(
        contracts=contracts,
        start=start,
        end=end,
        timeout=timeout,
    )
    return records_to_cftc_events(download.records, fetched_at=download.retrieved_at)


def _download_cftc_tff_records(
    *,
    contracts: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    timeout: float = 30.0,
) -> _CFTCDownload:
    selected = tuple(contracts or ("NQ_COT",))
    if not selected:
        raise ValueError("at least one CFTC contract symbol, code, or name is required")
    start_date = start or date(2006, 6, 13)
    end_date = end or datetime.now(UTC).date()
    if start_date > end_date:
        raise ValueError("CFTC start date must not be after end date")

    where_contracts = " OR ".join(_contract_filter(value) for value in selected)
    params = {
        "$select": ",".join(_FIELDS),
        "$where": (
            f"report_date_as_yyyy_mm_dd between '{start_date.isoformat()}T00:00:00' "
            f"and '{end_date.isoformat()}T23:59:59' and ({where_contracts})"
        ),
        "$order": "report_date_as_yyyy_mm_dd,market_and_exchange_names",
        "$limit": 50000,
    }
    response = httpx.get(CFTC_TFF_ENDPOINT, params=params, timeout=timeout)
    response.raise_for_status()
    return _CFTCDownload(
        records=_read_csv_records(response.text),
        retrieved_at=datetime.now(UTC),
        request_url=str(response.url),
    )


def records_to_cftc_events(
    records: Iterable[dict[str, str]],
    *,
    fetched_at: datetime,
) -> list[EventRecord]:
    local_retrieved_at = _as_utc(fetched_at)
    events: list[EventRecord] = []
    for raw in records:
        report_date = _parse_report_date(raw.get("report_date_as_yyyy_mm_dd"))
        market = str(raw.get("market_and_exchange_names") or "").strip()
        provider_id = str(raw.get("id") or "").strip()
        if report_date is None or not market:
            continue

        replay = _pit_replay_timestamp(
            raw,
            report_date=report_date,
            retrieved_at=local_retrieved_at,
        )
        if replay is None:
            continue
        visible_at, availability_quality, availability_basis = replay
        provider_created_at = _parse_datetime(raw.get(":created_at"))
        provider_updated_at = _parse_datetime(raw.get(":updated_at"))
        if provider_created_at is None or provider_updated_at is None:
            continue
        normalized = {field: raw.get(field) for field in _FIELDS}
        input_hash = hashlib.sha256(
            json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        symbol = _contract_symbol(market, str(raw.get("cftc_contract_market_code") or ""))
        system_id = str(raw.get(":id") or "").strip()
        record_id = (
            provider_id or system_id or (f"{report_date.isoformat()}:{symbol}:{input_hash[:12]}")
        )
        events.append(
            EventRecord(
                id=f"cftc-tff-{record_id}",
                source="cftc_cot",
                symbol=symbol,
                published_at=visible_at,
                fetched_at=visible_at,
                first_seen_at=visible_at,
                visible_at=visible_at,
                vintage_at=visible_at,
                revision="provider_current_row_historical_report_not_backdated",
                revision_id=f"{provider_updated_at.isoformat()}:{input_hash}",
                version_id=input_hash,
                rights="us_federal_public_data",
                rights_scope="internal_research_and_replay",
                availability_quality=availability_quality,
                availability_basis=availability_basis,
                acquisition_mode="official_historical_api_replay",
                event_type="cftc_tff_futures_only",
                title=f"CFTC TFF {symbol} positions for {report_date.isoformat()}",
                summary=(
                    "Official weekly futures-only aggregate positions. Values are not "
                    "trade recommendations and do not disclose individual traders."
                ),
                url=CFTC_COT_DOCS_URL,
                sentiment="neutral",
                relevance_score=1.0,
                dedupe_key=f"cftc_tff:{record_id}:{input_hash}",
                input_hash=input_hash,
                prompt_hash=CFTC_TFF_TRANSFORM_HASH,
                transform_hash=CFTC_TFF_TRANSFORM_HASH,
                provider_created_at=provider_created_at,
                provider_updated_at=provider_updated_at,
                collector_retrieved_at=local_retrieved_at,
                raw={
                    **normalized,
                    "report_date": report_date.isoformat(),
                    "provider_created_at": provider_created_at.isoformat(),
                    "provider_updated_at": provider_updated_at.isoformat(),
                    "provider_visible_at": visible_at.isoformat(),
                    "collector_retrieved_at": local_retrieved_at.isoformat(),
                    "fetched_at_semantics": "historical_replay_availability_not_local_download",
                    "input_hash": input_hash,
                    "prompt_hash": CFTC_TFF_TRANSFORM_HASH,
                    "transform_hash": CFTC_TFF_TRANSFORM_HASH,
                    "transform_contract": CFTC_TFF_TRANSFORM_CONTRACT,
                    "replay_eligible": True,
                    "dataset_id": CFTC_TFF_FUTURES_ONLY_DATASET,
                    "dataset_url": CFTC_TFF_ENDPOINT,
                    "metadata_url": CFTC_TFF_METADATA_URL,
                    "special_announcements_url": CFTC_COT_SPECIAL_ANNOUNCEMENTS_URL,
                },
            )
        )
    return sorted(events, key=lambda item: (item.visible_at, item.symbol, item.id))


def materialize_cftc_tff_snapshot(
    root: Path,
    *,
    contracts: Iterable[str] | None = None,
    start: date | None = None,
    end: date | None = None,
    output_dir: Path = Path("data/research/cftc_tff_futures_only"),
) -> CFTCSnapshotResult:
    download = _download_cftc_tff_records(contracts=contracts, start=start, end=end)
    events = records_to_cftc_events(download.records, fetched_at=download.retrieved_at)
    excluded_records = len(download.records) - len(events)
    destination = root / output_dir
    ensure_dir(destination)
    snapshot_path = destination / "events.jsonl"
    manifest_path = destination / "snapshot-manifest.json"
    if snapshot_path.exists() or manifest_path.exists():
        raise FileExistsError(f"immutable CFTC snapshot already exists: {destination}")
    snapshot_text = "".join(
        json.dumps(event.model_dump(mode="json"), sort_keys=True) + "\n" for event in events
    )
    snapshot_path.write_text(snapshot_text, encoding="utf-8")
    snapshot_sha256 = hashlib.sha256(snapshot_text.encode("utf-8")).hexdigest()
    visible = [event.visible_at for event in events]
    manifest = {
        "schema_version": 1,
        "provider": "cftc",
        "capability_id": "macro.cftc_cot",
        "dataset_id": CFTC_TFF_FUTURES_ONLY_DATASET,
        "dataset_url": CFTC_TFF_ENDPOINT,
        "metadata_url": CFTC_TFF_METADATA_URL,
        "source_docs_url": CFTC_COT_DOCS_URL,
        "special_announcements_url": CFTC_COT_SPECIAL_ANNOUNCEMENTS_URL,
        "source_mode": "official_historical_api_replay",
        "visibility_policy": (
            "legacy_report_plus_14d_excluding_shutdown_then_native_socrata_system_timestamps"
        ),
        "native_replay_start_report_date": CFTC_PRE_NATIVE_REPORT_START.isoformat(),
        "legacy_conservative_lag_days": CFTC_LEGACY_CONSERVATIVE_LAG_DAYS,
        "legacy_excluded_windows": [
            {"start": start.isoformat(), "end": end.isoformat(), "reason": reason}
            for start, end, reason in _LEGACY_EXCLUDED_WINDOWS
        ],
        "transform_contract": CFTC_TFF_TRANSFORM_CONTRACT,
        "transform_hash": CFTC_TFF_TRANSFORM_HASH,
        "prompt_hash": CFTC_TFF_TRANSFORM_HASH,
        "request_url": download.request_url,
        "retrieved_at": download.retrieved_at.isoformat(),
        "downloaded_records": len(download.records),
        "records": len(events),
        "excluded_records": excluded_records,
        "first_visible_at": min(visible).isoformat() if visible else None,
        "last_visible_at": max(visible).isoformat() if visible else None,
        "snapshot_path": output_dir.joinpath(snapshot_path.name).as_posix(),
        "snapshot_sha256": snapshot_sha256,
        "caveats": [
            "COT is weekly aggregate positioning, not futures price, carry, or order-book data.",
            "Reports before 2022-09-13 use a two-week delayed visibility assumption because PRE "
            "migration timestamps do not prove their original publication time.",
            "The 2018-12-24 through 2019-03-12 shutdown backlog is excluded rather than inferred.",
            "The fixture validates schema only; the immutable official snapshot is the research "
            "evidence.",
            "The feature requires marginal-lift and placebo ablations before promotion.",
        ],
    }
    write_json(manifest_path, manifest)
    return CFTCSnapshotResult(events, snapshot_path, manifest_path, excluded_records)


def _read_csv_records(payload: str) -> list[dict[str, str]]:
    return [dict(row) for row in csv.DictReader(io.StringIO(payload))]


def _parse_report_date(value: str | None) -> date | None:
    if not value:
        return None
    return date.fromisoformat(value[:10])


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _pit_replay_timestamp(
    raw: dict[str, str],
    *,
    report_date: date,
    retrieved_at: datetime,
) -> tuple[datetime, str, str] | None:
    local_retrieved_at = _as_utc(retrieved_at)
    if report_date < CFTC_PRE_NATIVE_REPORT_START:
        if any(start <= report_date <= end for start, end, _ in _LEGACY_EXCLUDED_WINDOWS):
            return None
        legacy_visible_at = datetime.combine(
            report_date + timedelta(days=CFTC_LEGACY_CONSERVATIVE_LAG_DAYS),
            _REGULAR_OPEN,
            tzinfo=_NEW_YORK,
        ).astimezone(UTC)
        if legacy_visible_at > local_retrieved_at:
            return None
        return (
            legacy_visible_at,
            "official_schedule_conservative_legacy_delay",
            "official_normal_release_plus_14d_with_special_outage_exclusion",
        )
    created_at = _parse_datetime(raw.get(":created_at"))
    updated_at = _parse_datetime(raw.get(":updated_at"))
    if created_at is None or updated_at is None:
        return None
    if created_at < datetime.combine(report_date, datetime.min.time(), tzinfo=UTC):
        return None
    if updated_at < created_at:
        return None
    if updated_at > local_retrieved_at:
        return None
    return (
        max(created_at, updated_at),
        "official_provider_row_system_timestamp",
        "max_socrata_created_at_updated_at",
    )


def _contract_symbol(market: str, contract_code: str = "") -> str:
    for symbol, codes in _CONTRACT_CODES.items():
        if contract_code in codes:
            return symbol
    upper = market.upper()
    if "NASDAQ-100" in upper:
        return "NQ_COT"
    if "S&P 500" in upper:
        return "ES_COT"
    if "VIX" in upper:
        return "VX_COT"
    if "GOLD" in upper:
        return "GC_COT"
    return "FUTURES_COT"


def _contract_filter(value: str) -> str:
    normalized = value.upper().strip()
    codes = _CONTRACT_CODES.get(normalized)
    if codes:
        return (
            "("
            + " OR ".join(f"cftc_contract_market_code='{_escape_soql(code)}'" for code in codes)
            + ")"
        )
    if normalized and all(
        character.isalnum() or character in {"+", "-"} for character in normalized
    ):
        return f"cftc_contract_market_code='{_escape_soql(normalized)}'"
    return f"upper(market_and_exchange_names) like '%{_escape_soql(normalized)}%'"


def _escape_soql(value: str) -> str:
    return value.replace("'", "''")
