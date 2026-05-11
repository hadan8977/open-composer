from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.provenance import write_ohlcv_manifest
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import ensure_dir


class LongbridgeDataError(RuntimeError):
    pass


DEFAULT_LONGBRIDGE_FEED = "nasdaq_basic"


def longbridge_cache_path(
    root: Path,
    symbol: str,
    timeframe: str,
    feed: str | None = None,
) -> Path:
    selected_feed = feed or DEFAULT_LONGBRIDGE_FEED
    return root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_longbridge_{selected_feed}.csv"


def fetch_longbridge_bars(
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    feed: str | None = None,
    use_cache: bool = True,
    adjusted: bool = True,
) -> pd.DataFrame:
    selected_feed = feed or DEFAULT_LONGBRIDGE_FEED
    cache_path = longbridge_cache_path(root, symbol, timeframe, selected_feed)
    if use_cache and cache_path.exists() and start is None and end is None:
        frame = normalize_ohlcv(pd.read_csv(cache_path))
        _annotate_frame(frame, selected_feed, "cache", cache_path)
        write_ohlcv_manifest(
            root,
            provider="longbridge",
            feed=selected_feed,
            symbol=symbol,
            timeframe=timeframe,
            cache_path=cache_path,
            frame=frame,
            source_mode="cache",
            request_params={"adjusted": adjusted},
            caveats=_longbridge_caveats(selected_feed),
        )
        return frame

    try:
        frame = _fetch_live_longbridge_bars(symbol, timeframe, start, end, adjusted)
    except LongbridgeDataError as exc:
        if cache_path.exists() and start is None and end is None:
            frame = normalize_ohlcv(pd.read_csv(cache_path))
            _annotate_frame(frame, selected_feed, "cache_fallback", cache_path)
            write_ohlcv_manifest(
                root,
                provider="longbridge",
                feed=selected_feed,
                symbol=symbol,
                timeframe=timeframe,
                cache_path=cache_path,
                frame=frame,
                source_mode="cache_fallback",
                request_params={"adjusted": adjusted, "refresh_error": str(exc)},
                caveats=_longbridge_caveats(selected_feed),
            )
            return frame
        raise
    ensure_dir(cache_path.parent)
    _annotate_frame(frame, selected_feed, "live_fetch", cache_path)
    frame.to_csv(cache_path, index=False)
    write_ohlcv_manifest(
        root,
        provider="longbridge",
        feed=selected_feed,
        symbol=symbol,
        timeframe=timeframe,
        cache_path=cache_path,
        frame=frame,
        requested_start=start,
        requested_end=end,
        source_mode="live_fetch",
        request_params={"adjusted": adjusted},
        caveats=_longbridge_caveats(selected_feed),
    )
    return frame


def _annotate_frame(frame: pd.DataFrame, feed: str, source_mode: str, path: Path) -> None:
    frame.attrs.update(
        {
            "data_source_provider": "longbridge",
            "data_source_mode": source_mode,
            "data_source_feed": feed,
            "data_source_path": str(path),
        }
    )


def _fetch_live_longbridge_bars(
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    adjusted: bool,
) -> pd.DataFrame:
    try:
        from longbridge.openapi import AdjustType, Config, Period, QuoteContext
    except ImportError as exc:
        raise LongbridgeDataError(
            "longbridge-openapi SDK is required for live Longbridge data fetches; "
            "use cached CSVs or install the SDK before refreshing"
        ) from exc

    config = Config.from_env()
    context = QuoteContext(config)
    period = _longbridge_period(Period, timeframe)
    adjust_type = _longbridge_adjust_type(AdjustType, adjusted)

    method = getattr(context, "history_candlesticks", None) or getattr(
        context, "candlesticks", None
    )
    if method is None:
        raise LongbridgeDataError("Longbridge QuoteContext has no candlestick fetch method")

    try:
        rows = method(symbol.upper(), period, adjust_type, start=start, end=end)
    except TypeError:
        try:
            rows = method(symbol.upper(), period, adjust_type)
        except TypeError as exc:
            raise LongbridgeDataError(
                "unsupported Longbridge SDK candlestick signature; update adapter mapping"
            ) from exc
    return _rows_to_frame(rows)


def _longbridge_period(period_enum: Any, timeframe: str) -> Any:
    candidates = {
        "5m": ["Min5", "Min_5", "MIN_5", "M5"],
        "15m": ["Min15", "Min_15", "MIN_15", "M15"],
        "1h": ["Min60", "Min_60", "MIN_60", "Hour", "Hour1", "H1"],
        "daily": ["Day", "DAY", "Daily"],
        "weekly": ["Week", "WEEK", "Weekly"],
    }.get(timeframe)
    if not candidates:
        raise LongbridgeDataError(f"unsupported Longbridge timeframe: {timeframe}")
    for candidate in candidates:
        if hasattr(period_enum, candidate):
            return getattr(period_enum, candidate)
    raise LongbridgeDataError(f"Longbridge SDK period enum missing mapping for {timeframe}")


def _longbridge_adjust_type(adjust_enum: Any, adjusted: bool) -> Any:
    candidates = (
        ["ForwardAdjust", "ForwardAdjusted", "Forward", "AdjustForward"]
        if adjusted
        else ["NoAdjust", "NoneAdjust", "NoAdjusted", "None"]
    )
    for candidate in candidates:
        if hasattr(adjust_enum, candidate):
            return getattr(adjust_enum, candidate)
    return None


def _rows_to_frame(rows: Any) -> pd.DataFrame:
    if isinstance(rows, pd.DataFrame):
        return normalize_ohlcv(_normalize_frame(rows))
    if hasattr(rows, "df") and isinstance(rows.df, pd.DataFrame):
        return normalize_ohlcv(_normalize_frame(rows.df))
    if isinstance(rows, dict):
        for key in ("items", "candlesticks", "data", "rows"):
            value = rows.get(key)
            if value is not None:
                rows = value
                break
    records: list[dict[str, Any]] = []
    iterable = rows if isinstance(rows, list) else list(rows or [])
    for row in iterable:
        records.append(
            {
                "timestamp": _row_value(row, "timestamp", "time", "datetime", "date"),
                "open": _row_value(row, "open", "open_price"),
                "high": _row_value(row, "high", "high_price"),
                "low": _row_value(row, "low", "low_price"),
                "close": _row_value(row, "close", "close_price"),
                "volume": _row_value(row, "volume"),
            }
        )
    return normalize_ohlcv(pd.DataFrame(records))


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    normalized = frame.copy()
    rename_map = {
        "time": "timestamp",
        "datetime": "timestamp",
        "date": "timestamp",
        "open_price": "open",
        "high_price": "high",
        "low_price": "low",
        "close_price": "close",
        "volume": "volume",
    }
    normalized = normalized.rename(columns=rename_map)
    required = ["timestamp", "open", "high", "low", "close", "volume"]
    missing = [column for column in required if column not in normalized.columns]
    if missing:
        raise LongbridgeDataError(f"Longbridge rows missing columns: {', '.join(missing)}")
    return normalized[required]


def _row_value(row: Any, *names: str) -> Any:
    if isinstance(row, dict):
        for name in names:
            if name in row:
                return row[name]
        return None
    for name in names:
        if hasattr(row, name):
            return getattr(row, name)
    return None


def _longbridge_caveats(feed: str) -> list[str]:
    caveats = [
        "Longbridge free US market data is based on Nasdaq Basic, not consolidated SIP data",
        "minute history availability and symbol quotas must be checked against the account",
    ]
    if feed != DEFAULT_LONGBRIDGE_FEED:
        caveats.append(f"feed {feed} must be verified against Longbridge quote card permissions")
    return caveats
