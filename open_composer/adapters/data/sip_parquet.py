"""Read the local SIP versions as one view per price basis."""

from __future__ import annotations

from bisect import bisect_left
from collections.abc import Iterable
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Literal

import pandas as pd
import pyarrow.parquet as pq

DATA_SOURCE_PROVIDER = "alpaca"
DATA_SOURCE_FEED = "sip"
DATA_SOURCE_MODE = "sip_parquet"
ACQUISITION_TIER = "research_strict"
SUPPORTED_FREQUENCIES = ("daily", "minute")
OOS_START = date(2026, 9, 1)
BAR_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)
REQUIRED_COLUMNS = BAR_COLUMNS[:7]
RESULT_COLUMNS = (*BAR_COLUMNS, "source_version")
MARKET_DATA = Path(__file__).resolve().parents[4] / "market-data"
RAW_UPDATE_VERSION = "sip-raw-daily"
ALL_VERSIONS = ("sip-all", "daily-all-20261118T0430Z", "delisted-daily")
RAW_VERSIONS = (RAW_UPDATE_VERSION, "sip-raw-repair", "sip-raw-recent")


class SipParquetError(RuntimeError):
    """Raised when the SIP parquet archive cannot satisfy a strict read."""


def default_sip_root() -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "sip"


def load_sip_bars(
    symbols: str | Iterable[str],
    *,
    frequency: str = "daily",
    start: datetime | str | pd.Timestamp | None = None,
    end: datetime | str | pd.Timestamp | None = None,
    adjustment: Literal["raw", "all"] = "all",
    root: Path | str | None = None,
    allow_missing: bool | None = None,
) -> pd.DataFrame:
    """Return SIP bars and their source_version, sorted by symbol and UTC time.

    UTC bounds are inclusive. The local view returns gaps as missing rows.
    Explicit roots keep frozen archive reads strict unless allow_missing is set.
    """
    _validate_frequency(frequency)
    if adjustment not in ("all", "raw"):
        raise SipParquetError(f"unsupported SIP adjustment {adjustment!r}")
    requested = sorted(
        {symbol.strip().upper() for symbol in ([symbols] if isinstance(symbols, str) else symbols)}
    )
    if not requested or "" in requested:
        raise SipParquetError("at least one nonblank symbol is required")
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise SipParquetError(f"start {start_ts} is after end {end_ts}")

    if root is None:
        directory = MARKET_DATA
        sources = _local_sources(frequency, adjustment, start_ts, end_ts)
    else:
        archive = Path(root)
        version = archive.resolve().name
        other_basis = RAW_VERSIONS if adjustment == "all" else ALL_VERSIONS
        if version in other_basis:
            raise SipParquetError(f"{version} does not have adjustment={adjustment!r}")
        by_year = version == "delisted-daily" and frequency == "daily"
        directory = archive / ("by_year" if by_year else frequency)
        if not directory.is_dir():
            raise SipParquetError(f"SIP {frequency} archive not found at {directory}")
        partition_start = None if version == "sip-raw-repair" else start_ts
        sources = [(version, _candidate_shards(directory, partition_start, end_ts, "*.parquet"))]
    if allow_missing is None:
        allow_missing = root is None

    parts = []
    for version, paths in sources:
        for path in paths:
            stat = path.stat()
            bounds = _symbol_range(path, stat.st_mtime_ns, stat.st_size)
            if bounds is not None:
                low, high = bounds
                index = bisect_left(requested, low)
                if index == len(requested) or requested[index] > high:
                    continue
            table = pq.read_table(path, filters=[("symbol", "in", requested)])
            if table.num_rows:
                columns = (
                    *REQUIRED_COLUMNS,
                    *(name for name in BAR_COLUMNS[7:] if name in table.column_names),
                )
                chunk = table.select(columns).to_pandas().reindex(columns=BAR_COLUMNS)
                parts.append(chunk.assign(source_version=version))

    frame = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=RESULT_COLUMNS)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    if start_ts is not None:
        frame = frame[frame["timestamp"] >= start_ts]
    if end_ts is not None:
        frame = frame[frame["timestamp"] <= end_ts]
    frame = (
        frame.drop_duplicates(subset=["symbol", "timestamp"])
        .sort_values(["symbol", "timestamp"], kind="stable")
        .reset_index(drop=True)
    )
    for column in BAR_COLUMNS[2:]:
        frame[column] = pd.to_numeric(frame[column])
    frame["symbol"] = frame["symbol"].astype("string")
    missing = sorted(set(requested) - set(frame["symbol"]))
    if missing and not allow_missing:
        raise SipParquetError(
            f"no SIP {frequency} bars for {', '.join(missing)} in [{start_ts}, {end_ts}] under {directory}"
        )
    frame.attrs.update(
        data_source_provider=DATA_SOURCE_PROVIDER,
        data_source_mode=DATA_SOURCE_MODE,
        data_source_feed=DATA_SOURCE_FEED,
        data_source_frequency=frequency,
        data_source_path=str(directory),
        data_source_adjustment=adjustment,
        data_source_shard_count=len(parts),
        data_source_symbols=requested,
        data_source_missing_symbols=missing,
        acquisition_tier=ACQUISITION_TIER,
    )
    return frame


def _local_sources(frequency, adjustment, start, end):
    if adjustment == "raw":
        update_paths = []
        for day in sorted((MARKET_DATA / RAW_UPDATE_VERSION).glob("[0-9][0-9][0-9][0-9]-??-??")):
            # The date partition is a New York session and can extend into the
            # following UTC date. Row timestamps supply the exact bounds.
            session = pd.Timestamp(day.name, tz="UTC")
            if (start is None or start.normalize() <= session + pd.Timedelta(days=1)) and (
                end is None or end.normalize() >= session
            ):
                update_paths.extend(sorted((day / frequency).glob("*.parquet")))
        sources = [(RAW_UPDATE_VERSION, update_paths)]
        for version in RAW_VERSIONS[1:]:
            # Repair partitions are named for query start, including multi-year queries.
            lower = None if version == "sip-raw-repair" else start
            paths = _candidate_shards(MARKET_DATA / version / frequency, lower, end, "*.parquet")
            sources.append((version, paths))
        return sources

    primary = MARKET_DATA / "sip-all" if MARKET_DATA.is_dir() else default_sip_root()
    sources = [("sip-all", _candidate_shards(primary / frequency, start, end))]
    if frequency == "daily":
        sources.extend(
            (version, _candidate_shards(MARKET_DATA / version / folder, start, end, "*.parquet"))
            for version, folder in (
                ("daily-all-20261118T0430Z", "daily"),
                ("delisted-daily", "by_year"),
            )
        )
    return sources


def available_sip_years(frequency: str, *, root: Path | str | None = None) -> list[int]:
    """Return the calendar years present in the primary archive."""
    _validate_frequency(frequency)
    directory = (Path(root) if root is not None else default_sip_root()) / frequency
    return sorted(
        int(path.name) for path in directory.glob("[0-9][0-9][0-9][0-9]") if path.is_dir()
    )


def clear_sip_index_cache() -> None:
    _symbol_range.cache_clear()


def _validate_frequency(frequency: str) -> None:
    if frequency not in SUPPORTED_FREQUENCIES:
        raise SipParquetError(f"unsupported SIP frequency {frequency!r}; expected daily or minute")


def _candidate_shards(
    directory: Path,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
    pattern: str = "shard-*.parquet",
) -> list[Path]:
    paths = []
    for year in sorted(directory.glob("[0-9][0-9][0-9][0-9]")):
        if (start is not None and int(year.name) < start.year) or (
            end is not None and int(year.name) > end.year
        ):
            continue
        paths.extend(sorted(year.glob(pattern)))
        for month in sorted(year.glob("[0-9][0-9]")):
            partition = (int(year.name), int(month.name))
            if (start is not None and partition < (start.year, start.month)) or (
                end is not None and partition > (end.year, end.month)
            ):
                continue
            paths.extend(sorted(month.glob(pattern)))
    return paths


@lru_cache(maxsize=65536)
def _symbol_range(path: Path, mtime_ns: int, size: int) -> tuple[str, str] | None:
    metadata = pq.read_metadata(path)
    if not metadata.num_rows:
        return ("\uffff", "\uffff")
    column = metadata.schema.names.index("symbol")
    stats = [
        metadata.row_group(i).column(column).statistics for i in range(metadata.num_row_groups)
    ]
    if any(item is None or not item.has_min_max for item in stats):
        return None
    return min(item.min for item in stats), max(item.max for item in stats)
