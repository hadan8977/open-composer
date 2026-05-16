from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.provenance import write_ohlcv_manifest
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import alpaca_api_key_id, alpaca_api_secret_key, ensure_dir


class AlpacaDataError(RuntimeError):
    pass


def fetch_alpaca_bars(
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    feed: str,
    use_cache: bool = True,
) -> pd.DataFrame:
    cache_path = root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_{feed}.csv"
    if use_cache and cache_path.exists():
        cached = normalize_ohlcv(pd.read_csv(cache_path))
        if _cache_covers_window(cached, start, end):
            frame = _filter_cached_frame(cached, start, end)
            _annotate_frame(frame, feed, "cache", cache_path)
            write_ohlcv_manifest(
                root,
                provider="alpaca",
                feed=feed,
                symbol=symbol,
                timeframe=timeframe,
                cache_path=cache_path,
                frame=frame,
                requested_start=start,
                requested_end=end,
                source_mode="cache",
                caveats=_alpaca_caveats(feed),
            )
            return frame

    try:
        from alpaca.data.historical import StockHistoricalDataClient
        from alpaca.data.requests import StockBarsRequest
    except ImportError as exc:
        raise AlpacaDataError("alpaca-py is required for Alpaca data fetches") from exc

    request = StockBarsRequest(
        symbol_or_symbols=[symbol.upper()],
        timeframe=_alpaca_timeframe(timeframe),
        start=start or datetime.now(UTC) - timedelta(days=30),
        end=end or datetime.now(UTC),
        feed=feed,
    )
    client = StockHistoricalDataClient(
        api_key=alpaca_api_key_id(),
        secret_key=alpaca_api_secret_key(),
    )
    response = client.get_stock_bars(request)
    frame = _bars_to_frame(response, symbol.upper())
    _annotate_frame(frame, feed, "live_fetch", cache_path)
    ensure_dir(cache_path.parent)
    frame.to_csv(cache_path, index=False)
    write_ohlcv_manifest(
        root,
        provider="alpaca",
        feed=feed,
        symbol=symbol,
        timeframe=timeframe,
        cache_path=cache_path,
        frame=frame,
        requested_start=start,
        requested_end=end,
        source_mode="live_fetch",
        caveats=_alpaca_caveats(feed),
    )
    return frame


def _annotate_frame(frame: pd.DataFrame, feed: str, source_mode: str, path: Path) -> None:
    frame.attrs.update(
        {
            "data_source_provider": "alpaca",
            "data_source_mode": source_mode,
            "data_source_feed": feed,
            "data_source_path": str(path),
        }
    )


def _filter_cached_frame(
    frame: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> pd.DataFrame:
    filtered = frame.copy()
    if start is not None:
        filtered = filtered[filtered["timestamp"] >= _utc_timestamp(start)]
    if end is not None:
        filtered = filtered[filtered["timestamp"] <= _utc_timestamp(end)]
    return filtered.reset_index(drop=True)


def _cache_covers_window(
    frame: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    if start is None and end is None:
        return True
    if frame.empty:
        return False
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    if start is not None and timestamps.min() > _utc_timestamp(start):
        return False
    if end is not None and timestamps.max() < _utc_timestamp(end):
        return False
    return True


def _utc_timestamp(value: datetime) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        return timestamp.tz_localize("UTC")
    return timestamp.tz_convert("UTC")


def _alpaca_timeframe(timeframe: str) -> Any:
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    mapping = {
        "1m": TimeFrame(1, TimeFrameUnit.Minute),
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "30m": TimeFrame(30, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "4h": TimeFrame(4, TimeFrameUnit.Hour),
        "daily": TimeFrame(1, TimeFrameUnit.Day),
        "weekly": TimeFrame(1, TimeFrameUnit.Week),
    }
    if timeframe not in mapping:
        raise AlpacaDataError(f"unsupported Alpaca timeframe: {timeframe}")
    return mapping[timeframe]


def _bars_to_frame(response: Any, symbol: str) -> pd.DataFrame:
    if hasattr(response, "df"):
        frame = response.df.reset_index()
        if "symbol" in frame.columns:
            frame = frame[frame["symbol"] == symbol]
        rename = {
            "timestamp": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
        return normalize_ohlcv(frame.rename(columns=rename)[list(rename)])
    rows = response.get(symbol, []) if isinstance(response, dict) else []
    records = [
        {
            "timestamp": row.timestamp,
            "open": row.open,
            "high": row.high,
            "low": row.low,
            "close": row.close,
            "volume": row.volume,
        }
        for row in rows
    ]
    return normalize_ohlcv(pd.DataFrame(records))


def _alpaca_caveats(feed: str) -> list[str]:
    if feed.lower() == "iex":
        return ["Alpaca free IEX feed is not consolidated full-market SIP data"]
    return [f"Alpaca feed {feed} permissions and coverage must be verified"]
