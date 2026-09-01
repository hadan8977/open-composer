"""Loader for the local SIP (consolidated tape) parquet archive under ``data/sip/``.

SIP is the consolidated tape across every US exchange and a strict superset of the
retired IEX feed (measured on one QQQ week: 4121 SIP bars vs 1795 IEX bars, the
difference being extended-hours coverage). The two tapes must never be mixed in a
single dataset, so this loader only ever walks one frequency subtree and refuses
unknown frequencies instead of silently falling back.

Archive layout written by ``scripts/fetch_sip_universe.py``::

    data/sip/daily/{year}/shard-NNNN.parquet
    data/sip/minute/{year}/shard-NNNN.parquet          # legacy whole-year layout
    data/sip/minute/{year}/{month}/shard-NNNN.parquet  # current month-sharded layout

Both minute layouts are read transparently. They were produced by separate fetcher
invocations with different batch sizes, so their shard numbering is unrelated and
their symbol coverage overlaps; rows are de-duplicated on ``(symbol, timestamp)``.

Shard selection uses the parquet footer's ``symbol`` min/max statistics: every shard
holds a contiguous alphabetical slice of the universe, so a whole year of daily
shards can be pruned to the handful of files that can contain a symbol without
reading any row data.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import datetime
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq

from open_composer.adapters.data.sample import normalize_ohlcv

DATA_SOURCE_PROVIDER = "alpaca"
DATA_SOURCE_FEED = "sip"
DATA_SOURCE_MODE = "sip_parquet"
ACQUISITION_TIER = "research_strict"
SUPPORTED_FREQUENCIES = ("daily", "minute")
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
NUMERIC_COLUMNS = ("open", "high", "low", "close", "volume", "trade_count", "vwap")

_SYMBOL_RANGE_CACHE: dict[tuple[str, int, int], tuple[str, str] | None] = {}


class SipParquetError(RuntimeError):
    """Raised when the SIP parquet archive cannot satisfy a request."""


def default_sip_root() -> Path:
    """Return the repository's ``data/sip`` archive root."""
    return Path(__file__).resolve().parents[3] / "data" / "sip"


def load_sip_bars(
    symbols: str | Iterable[str],
    *,
    frequency: str = "daily",
    start: datetime | str | pd.Timestamp | None = None,
    end: datetime | str | pd.Timestamp | None = None,
    root: Path | str | None = None,
    allow_missing: bool = False,
) -> pd.DataFrame:
    """Load normalized SIP bars for ``symbols`` at ``frequency``.

    Parameters
    ----------
    symbols:
        A single ticker or an iterable of tickers. Case-insensitive.
    frequency:
        ``"daily"`` or ``"minute"``. Anything else raises :class:`SipParquetError`;
        the two tapes are never merged.
    start, end:
        Inclusive UTC bounds. Naive datetimes are interpreted as UTC. ``None``
        means unbounded on that side.
    root:
        SIP archive root (the directory holding ``daily/`` and ``minute/``).
        Defaults to :func:`default_sip_root`.
    allow_missing:
        When ``False`` (default) a requested symbol with zero rows in the window
        raises :class:`SipParquetError`.

    Returns
    -------
    DataFrame sorted by ``(symbol, timestamp)`` with the columns in
    :data:`BAR_COLUMNS` and provenance in ``frame.attrs``.
    """
    requested = _normalize_symbols(symbols)
    frequency = _validate_frequency(frequency)
    archive_root = Path(root) if root is not None else default_sip_root()
    frequency_dir = archive_root / frequency
    if not frequency_dir.is_dir():
        raise SipParquetError(
            f"SIP {frequency} archive not found at {frequency_dir}; "
            "run scripts/fetch_sip_universe.py first"
        )

    start_ts = _utc_timestamp(start)
    end_ts = _utc_timestamp(end)
    if start_ts is not None and end_ts is not None and start_ts > end_ts:
        raise SipParquetError(f"start {start_ts.isoformat()} is after end {end_ts.isoformat()}")

    shards = _candidate_shards(frequency_dir, start_ts, end_ts)
    wanted = set(requested)
    parts: list[pd.DataFrame] = []
    read_paths: list[Path] = []
    for path in shards:
        symbol_range = _shard_symbol_range(path)
        if symbol_range is not None and not _range_can_contain(symbol_range, requested):
            continue
        chunk = _read_shard(path, wanted)
        if chunk is None or chunk.empty:
            continue
        parts.append(chunk)
        read_paths.append(path)

    if parts:
        frame = pd.concat(parts, ignore_index=True)
    else:
        frame = pd.DataFrame(columns=list(BAR_COLUMNS))

    frame = _finalize(frame, start_ts, end_ts)

    found = set(frame["symbol"].unique().tolist())
    missing = [symbol for symbol in requested if symbol not in found]
    if missing and not allow_missing:
        raise SipParquetError(
            f"no SIP {frequency} bars for {', '.join(missing)} "
            f"in {_describe_window(start_ts, end_ts)} under {frequency_dir}"
        )

    frame.attrs.update(
        {
            "data_source_provider": DATA_SOURCE_PROVIDER,
            "data_source_mode": DATA_SOURCE_MODE,
            "data_source_feed": DATA_SOURCE_FEED,
            "data_source_frequency": frequency,
            "data_source_path": str(frequency_dir),
            "data_source_adjustment": "all",
            "data_source_shard_count": len(read_paths),
            "data_source_symbols": list(requested),
            "data_source_missing_symbols": missing,
            "acquisition_tier": ACQUISITION_TIER,
        }
    )
    return frame


def available_sip_years(frequency: str, *, root: Path | str | None = None) -> list[int]:
    """Return the calendar years present in the archive for ``frequency``."""
    frequency = _validate_frequency(frequency)
    archive_root = Path(root) if root is not None else default_sip_root()
    frequency_dir = archive_root / frequency
    if not frequency_dir.is_dir():
        return []
    return sorted(
        int(child.name)
        for child in frequency_dir.iterdir()
        if child.is_dir() and _is_year(child.name)
    )


def clear_sip_index_cache() -> None:
    """Drop the cached parquet footer statistics (used by tests)."""
    _SYMBOL_RANGE_CACHE.clear()


def _normalize_symbols(symbols: str | Iterable[str]) -> list[str]:
    if isinstance(symbols, str):
        candidates: Sequence[str] = [symbols]
    else:
        candidates = list(symbols)
    normalized: list[str] = []
    for symbol in candidates:
        cleaned = str(symbol).strip().upper()
        if not cleaned:
            raise SipParquetError("symbol must not be blank")
        if cleaned not in normalized:
            normalized.append(cleaned)
    if not normalized:
        raise SipParquetError("at least one symbol is required")
    return normalized


def _validate_frequency(frequency: str) -> str:
    if frequency not in SUPPORTED_FREQUENCIES:
        raise SipParquetError(
            f"unsupported SIP frequency {frequency!r}; expected one of "
            f"{', '.join(SUPPORTED_FREQUENCIES)}"
        )
    return frequency


def _utc_timestamp(value: datetime | str | pd.Timestamp | None) -> pd.Timestamp | None:
    if value is None:
        return None
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _is_year(name: str) -> bool:
    return len(name) == 4 and name.isdigit()


def _is_month(name: str) -> bool:
    return len(name) == 2 and name.isdigit() and 1 <= int(name) <= 12


def _candidate_shards(
    frequency_dir: Path,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> list[Path]:
    """Collect shard files whose calendar window can overlap ``[start, end]``."""
    paths: list[Path] = []
    for year_dir in sorted(frequency_dir.iterdir()):
        if not year_dir.is_dir() or not _is_year(year_dir.name):
            continue
        year = int(year_dir.name)
        if start is not None and year < start.year:
            continue
        if end is not None and year > end.year:
            continue
        # Whole-year layout: the shard spans the entire calendar year.
        paths.extend(sorted(year_dir.glob("shard-*.parquet")))
        for month_dir in sorted(year_dir.iterdir()):
            if not month_dir.is_dir() or not _is_month(month_dir.name):
                continue
            month = int(month_dir.name)
            if start is not None and (year, month) < (start.year, start.month):
                continue
            if end is not None and (year, month) > (end.year, end.month):
                continue
            paths.extend(sorted(month_dir.glob("shard-*.parquet")))
    return paths


def _shard_symbol_range(path: Path) -> tuple[str, str] | None:
    """Return the ``(min, max)`` symbol in ``path``, or ``None`` when unavailable."""
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key in _SYMBOL_RANGE_CACHE:
        return _SYMBOL_RANGE_CACHE[key]
    symbol_range: tuple[str, str] | None = None
    try:
        metadata = pq.ParquetFile(path).metadata
        if metadata.num_rows and metadata.num_row_groups:
            lows: list[str] = []
            highs: list[str] = []
            column_index = _symbol_column_index(metadata)
            if column_index is not None:
                for group in range(metadata.num_row_groups):
                    statistics = metadata.row_group(group).column(column_index).statistics
                    if statistics is None or not statistics.has_min_max:
                        lows.clear()
                        break
                    lows.append(str(statistics.min))
                    highs.append(str(statistics.max))
                if lows:
                    symbol_range = (min(lows), max(highs))
        else:
            # Empty shard marker written for a genuinely empty fetch window.
            symbol_range = ("￿", "￿")
    except Exception:  # noqa: BLE001 - a corrupt footer must not prune silently
        symbol_range = None
    _SYMBOL_RANGE_CACHE[key] = symbol_range
    return symbol_range


def _symbol_column_index(metadata: pq.FileMetaData) -> int | None:
    names = list(metadata.schema.names)
    return names.index("symbol") if "symbol" in names else None


def _range_can_contain(symbol_range: tuple[str, str], symbols: Sequence[str]) -> bool:
    low, high = symbol_range
    return any(low <= symbol <= high for symbol in symbols)


def _read_shard(path: Path, wanted: set[str]) -> pd.DataFrame | None:
    table = pq.read_table(path, filters=[("symbol", "in", sorted(wanted))])
    if table.num_rows == 0:
        return None
    present = [column for column in BAR_COLUMNS if column in table.column_names]
    if "symbol" not in present or "timestamp" not in present:
        raise SipParquetError(f"SIP shard {path} is missing symbol/timestamp columns")
    return table.select(present).to_pandas()


def _finalize(
    frame: pd.DataFrame,
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> pd.DataFrame:
    missing = [column for column in BAR_COLUMNS if column not in frame.columns]
    for column in missing:
        frame[column] = pd.Series(dtype="float64" if column in NUMERIC_COLUMNS else "object")
    working = frame.loc[:, list(BAR_COLUMNS)].copy()
    working["symbol"] = working["symbol"].astype("string").str.upper()
    working["timestamp"] = pd.to_datetime(working["timestamp"], utc=True)
    # The whole-year and month-sharded minute layouts overlap, so identical bars
    # can arrive from two shards.
    working = working.drop_duplicates(subset=["symbol", "timestamp"], keep="first")
    if start is not None:
        working = working[working["timestamp"] >= start]
    if end is not None:
        working = working[working["timestamp"] <= end]
    normalized = normalize_ohlcv(working.reset_index(drop=True))
    for column in ("trade_count", "vwap"):
        normalized[column] = pd.to_numeric(normalized[column], errors="coerce")
    normalized["symbol"] = normalized["symbol"].astype("string")
    return normalized.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True)


def _describe_window(start: pd.Timestamp | None, end: pd.Timestamp | None) -> str:
    if start is None and end is None:
        return "the full archive window"
    low = start.isoformat() if start is not None else "archive start"
    high = end.isoformat() if end is not None else "archive end"
    return f"[{low}, {high}]"
