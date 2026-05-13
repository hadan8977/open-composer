from __future__ import annotations

import os
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import dotenv_values, load_dotenv

from open_composer.adapters.data.provenance import write_ohlcv_manifest
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import ensure_dir


class LongbridgeDataError(RuntimeError):
    pass


DEFAULT_LONGBRIDGE_FEED = "nasdaq_basic"
DEFAULT_LONGBRIDGE_TRADE_SESSIONS = "intraday"
MAX_LONGBRIDGE_CANDLESTICKS = 1000
REQUIRED_LONGBRIDGE_ENV = (
    "LONGBRIDGE_APP_KEY",
    "LONGBRIDGE_APP_SECRET",
    "LONGBRIDGE_ACCESS_TOKEN",
)


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
    count: int = MAX_LONGBRIDGE_CANDLESTICKS,
    trade_sessions: str = DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
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
            request_params={"adjusted": adjusted, "trade_sessions": trade_sessions},
            caveats=_longbridge_caveats(selected_feed, trade_sessions),
        )
        return frame

    try:
        frame = _fetch_live_longbridge_bars(
            root,
            symbol,
            timeframe,
            start,
            end,
            adjusted,
            count,
            trade_sessions,
        )
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
                request_params={
                    "adjusted": adjusted,
                    "trade_sessions": trade_sessions,
                    "refresh_error": str(exc),
                },
                caveats=_longbridge_caveats(selected_feed, trade_sessions),
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
        request_params={
            "adjusted": adjusted,
            "count": count,
            "trade_sessions": trade_sessions,
            "longbridge_symbol": _longbridge_security_code(symbol),
        },
        caveats=_longbridge_caveats(selected_feed, trade_sessions),
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
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    adjusted: bool,
    count: int,
    trade_sessions: str,
) -> pd.DataFrame:
    try:
        from longbridge.openapi import AdjustType, Config, Period, QuoteContext, TradeSessions
    except ImportError as exc:
        raise LongbridgeDataError(
            "longbridge SDK is required for live Longbridge data fetches; "
            "install the longbridge package or use cached CSVs"
        ) from exc

    if count < 1 or count > MAX_LONGBRIDGE_CANDLESTICKS:
        raise LongbridgeDataError(
            f"Longbridge candlestick count must be between 1 and {MAX_LONGBRIDGE_CANDLESTICKS}"
        )

    config = _longbridge_config(root, Config)
    context = QuoteContext(config)
    period = _longbridge_period(Period, timeframe)
    adjust_type = _longbridge_adjust_type(AdjustType, adjusted)
    selected_sessions = _longbridge_trade_sessions(TradeSessions, trade_sessions)
    security_code = _longbridge_security_code(symbol)

    if start is not None or end is not None:
        rows = context.history_candlesticks_by_date(
            security_code,
            period,
            adjust_type,
            start.date() if start else None,
            end.date() if end else None,
            selected_sessions,
        )
    else:
        rows = context.candlesticks(
            security_code,
            period,
            count,
            adjust_type,
            selected_sessions,
        )
    return _rows_to_frame(rows)


def fetch_longbridge_quotes(root: Path, symbols: list[str]) -> list[dict[str, Any]]:
    try:
        from longbridge.openapi import Config, QuoteContext
    except ImportError as exc:
        raise LongbridgeDataError("longbridge SDK is required for live Longbridge quotes") from exc

    context = QuoteContext(_longbridge_config(root, Config))
    try:
        rows = context.quote([_longbridge_security_code(symbol) for symbol in symbols])
    except Exception as exc:
        raise LongbridgeDataError(f"Longbridge quote request failed: {exc}") from exc
    return [_quote_to_dict(row) for row in rows]


def longbridge_quote_status(root: Path) -> dict[str, Any]:
    try:
        from longbridge.openapi import Config, QuoteContext
    except ImportError as exc:
        raise LongbridgeDataError(
            "longbridge SDK is required for Longbridge status checks"
        ) from exc

    context = QuoteContext(_longbridge_config(root, Config))
    try:
        level = context.quote_level()
        packages = context.quote_package_details()
    except Exception as exc:
        raise LongbridgeDataError(f"Longbridge quote status request failed: {exc}") from exc
    return {
        "quote_level": level,
        "quote_packages": [_quote_package_to_dict(package) for package in packages],
    }


def longbridge_credentials_status(root: Path) -> dict[str, str]:
    _load_longbridge_env(root)
    return {
        name: "set" if _longbridge_env_value(root, name) else "missing"
        for name in REQUIRED_LONGBRIDGE_ENV
    }


def missing_longbridge_credentials(root: Path) -> list[str]:
    status = longbridge_credentials_status(root)
    return [name for name, value in status.items() if value == "missing"]


def _longbridge_config(root: Path, config_cls: Any) -> Any:
    _load_longbridge_env(root)
    missing = missing_longbridge_credentials(root)
    if missing:
        raise LongbridgeDataError(
            "missing Longbridge API Key credentials: "
            + ", ".join(missing)
            + "; official SDK API Key auth requires App Key, App Secret, and Access Token"
        )
    return config_cls.from_apikey(
        _longbridge_env_value(root, "LONGBRIDGE_APP_KEY") or "",
        _longbridge_env_value(root, "LONGBRIDGE_APP_SECRET") or "",
        _longbridge_env_value(root, "LONGBRIDGE_ACCESS_TOKEN") or "",
        enable_print_quote_packages=False,
    )


def _load_longbridge_env(root: Path) -> None:
    load_dotenv(root / ".env", override=False)


def _longbridge_env_value(root: Path, name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value
    env_path = root / ".env"
    if not env_path.exists():
        return None
    loaded = dotenv_values(env_path).get(name)
    return loaded or None


def _longbridge_security_code(symbol: str) -> str:
    selected = symbol.upper().strip()
    if "." in selected:
        return selected
    return f"{selected}.US"


def _longbridge_period(period_enum: Any, timeframe: str) -> Any:
    candidates = {
        "1m": ["Min_1", "Min1", "MIN_1", "M1"],
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


def _longbridge_trade_sessions(sessions_enum: Any, trade_sessions: str) -> Any:
    selected = trade_sessions.strip().lower()
    if selected in {"intraday", "regular", "regular_hours"}:
        return sessions_enum.Intraday
    if selected in {"all", "extended", "extended_hours"}:
        return sessions_enum.All
    raise LongbridgeDataError(
        f"unsupported Longbridge trade sessions: {trade_sessions}; expected intraday or all"
    )


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


def _quote_to_dict(row: Any) -> dict[str, Any]:
    return {
        "symbol": _row_value(row, "symbol"),
        "last_done": _decimal_value(_row_value(row, "last_done")),
        "prev_close": _decimal_value(_row_value(row, "prev_close")),
        "open": _decimal_value(_row_value(row, "open")),
        "high": _decimal_value(_row_value(row, "high")),
        "low": _decimal_value(_row_value(row, "low")),
        "timestamp": _row_value(row, "timestamp"),
        "volume": _row_value(row, "volume"),
        "turnover": _decimal_value(_row_value(row, "turnover")),
        "trade_status": str(_row_value(row, "trade_status")),
    }


def _quote_package_to_dict(row: Any) -> dict[str, Any]:
    return {
        "key": _row_value(row, "key"),
        "name": _row_value(row, "name"),
        "description": _row_value(row, "description"),
        "start_at": _row_value(row, "start_at"),
        "end_at": _row_value(row, "end_at"),
    }


def _decimal_value(value: Any) -> float | int | str | None:
    if isinstance(value, Decimal):
        return float(value)
    return value


def _longbridge_caveats(feed: str, trade_sessions: str) -> list[str]:
    caveats = [
        "Longbridge free US market data is based on Nasdaq Basic, not consolidated SIP data",
        "historical candlestick requests are limited to 1000 bars per request",
        "monthly historical candlestick symbol quotas depend on the Longbridge account tier",
        (
            "minute history availability depends on market and starts from the documented "
            "market-specific date"
        ),
    ]
    if feed != DEFAULT_LONGBRIDGE_FEED:
        caveats.append(f"feed {feed} must be verified against Longbridge quote card permissions")
    if trade_sessions.strip().lower() in {"all", "extended", "extended_hours"}:
        caveats.append(
            "extended-hours candlesticks include pre/post-market; US overnight data requires "
            "LV1 OpenAPI quote card and LONGBRIDGE_ENABLE_OVERNIGHT=true"
        )
    return caveats
