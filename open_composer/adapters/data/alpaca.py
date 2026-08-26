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


SUPPORTED_ADJUSTMENTS = {"raw", "split", "dividend", "all"}


def fetch_alpaca_bars(
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    feed: str,
    use_cache: bool = True,
    adjustment: str | None = None,
) -> pd.DataFrame:
    selected_adjustment = _normalize_adjustment(adjustment)
    cache_path = _alpaca_cache_path(
        root,
        symbol,
        timeframe,
        feed,
        selected_adjustment,
    )
    cached = normalize_ohlcv(pd.read_csv(cache_path)) if cache_path.exists() else None
    if use_cache and cached is not None:
        if _cache_covers_window(cached, start, end):
            frame = _filter_cached_frame(cached, start, end)
            _annotate_frame(frame, feed, "cache", cache_path, selected_adjustment)
            write_ohlcv_manifest(
                root,
                provider="alpaca",
                feed=feed,
                symbol=symbol,
                timeframe=timeframe,
                adjustment=selected_adjustment,
                cache_path=cache_path,
                frame=frame,
                requested_start=start,
                requested_end=end,
                source_mode="cache",
                caveats=_alpaca_caveats(feed, selected_adjustment),
            )
            return frame
    if use_cache:
        resampled = _resampled_cache(
            root,
            symbol,
            timeframe,
            start,
            end,
            feed,
            selected_adjustment,
        )
        if resampled is not None:
            frame, source_path = resampled
            _annotate_frame(
                frame,
                feed,
                "cache_resampled",
                source_path,
                selected_adjustment,
            )
            write_ohlcv_manifest(
                root,
                provider="alpaca",
                feed=feed,
                symbol=symbol,
                timeframe=timeframe,
                adjustment=selected_adjustment,
                cache_path=source_path,
                frame=frame,
                requested_start=start,
                requested_end=end,
                source_mode="cache_resampled",
                request_params={"resampled_from": source_path.name},
                caveats=[
                    *_alpaca_caveats(feed, selected_adjustment),
                    (
                        "Daily bars were resampled from local intraday cache because the "
                        "requested daily cache window was unavailable."
                    ),
                ],
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
        start=_request_start(start, end, cached),
        end=end or datetime.now(UTC),
        feed=feed,
        adjustment=_alpaca_adjustment(selected_adjustment),
    )
    client = StockHistoricalDataClient(
        api_key=alpaca_api_key_id(),
        secret_key=alpaca_api_secret_key(),
    )
    response = client.get_stock_bars(request)
    frame = _bars_to_frame(response, symbol.upper())
    if cached is not None:
        frame = _merge_cached_and_fetched(cached, frame)
    frame = _filter_cached_frame(frame, start, end)
    _annotate_frame(frame, feed, "live_fetch", cache_path, selected_adjustment)
    ensure_dir(cache_path.parent)
    frame.to_csv(cache_path, index=False)
    write_ohlcv_manifest(
        root,
        provider="alpaca",
        feed=feed,
        symbol=symbol,
        timeframe=timeframe,
        adjustment=selected_adjustment,
        cache_path=cache_path,
        frame=frame,
        requested_start=start,
        requested_end=end,
        source_mode="live_fetch",
        caveats=_alpaca_caveats(feed, selected_adjustment),
    )
    return frame


def _request_start(
    start: datetime | None,
    end: datetime | None,
    cached: pd.DataFrame | None,
) -> datetime:
    if start is not None:
        return start
    if end is None and cached is not None and not cached.empty:
        latest = pd.to_datetime(cached["timestamp"], utc=True).max().to_pydatetime()
        return latest - timedelta(days=7)
    return datetime.now(UTC) - timedelta(days=30)


def _merge_cached_and_fetched(cached: pd.DataFrame, fetched: pd.DataFrame) -> pd.DataFrame:
    if fetched.empty:
        return cached.copy().reset_index(drop=True)
    merged = pd.concat([cached, fetched], ignore_index=True)
    merged["timestamp"] = pd.to_datetime(merged["timestamp"], utc=True)
    merged = (
        merged.sort_values("timestamp")
        .drop_duplicates(subset=["timestamp"], keep="last")
        .reset_index(drop=True)
    )
    return normalize_ohlcv(merged)


def _annotate_frame(
    frame: pd.DataFrame,
    feed: str,
    source_mode: str,
    path: Path,
    adjustment: str | None,
) -> None:
    frame.attrs.update(
        {
            "data_source_provider": "alpaca",
            "data_source_mode": source_mode,
            "data_source_feed": feed,
            "data_source_path": str(path),
            "data_source_adjustment": adjustment,
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


def _resampled_cache(
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    feed: str,
    adjustment: str | None,
) -> tuple[pd.DataFrame, Path] | None:
    if timeframe != "daily":
        return None
    for source_timeframe in ("15m", "5m", "1m"):
        source_path = _alpaca_cache_path(
            root,
            symbol,
            source_timeframe,
            feed,
            adjustment,
        )
        if not source_path.exists():
            continue
        source = normalize_ohlcv(pd.read_csv(source_path))
        if source.empty or not _cache_covers_daily_dates(source, start, end):
            continue
        frame = _resample_to_daily(source)
        frame = _filter_cached_frame(frame, start, end)
        if frame.empty:
            continue
        return frame, source_path
    return None


def _resample_to_daily(frame: pd.DataFrame) -> pd.DataFrame:
    indexed = frame.copy()
    indexed["timestamp"] = pd.to_datetime(indexed["timestamp"], utc=True)
    indexed = indexed.sort_values("timestamp").set_index("timestamp")
    resampled = indexed.resample("1D", label="left", closed="left").agg(
        {
            "open": "first",
            "high": "max",
            "low": "min",
            "close": "last",
            "volume": "sum",
        }
    )
    resampled = resampled.dropna().reset_index()
    return normalize_ohlcv(resampled)


def _cache_covers_daily_dates(
    frame: pd.DataFrame,
    start: datetime | None,
    end: datetime | None,
) -> bool:
    if start is None and end is None:
        return True
    if frame.empty:
        return False
    dates = pd.to_datetime(frame["timestamp"], utc=True).dt.date
    if start is not None and dates.min() > _utc_timestamp(start).date():
        return False
    if end is not None and dates.max() < _utc_timestamp(end).date():
        return False
    return True


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


def _alpaca_adjustment(adjustment: str | None) -> Any:
    if adjustment is None:
        return None
    from alpaca.data.enums import Adjustment

    return Adjustment(adjustment)


def _normalize_adjustment(adjustment: str | None) -> str | None:
    if adjustment is None:
        return None
    normalized = adjustment.strip().lower()
    if normalized not in SUPPORTED_ADJUSTMENTS:
        raise AlpacaDataError(f"unsupported Alpaca adjustment: {adjustment}")
    return normalized


def _alpaca_cache_path(
    root: Path,
    symbol: str,
    timeframe: str,
    feed: str,
    adjustment: str | None,
) -> Path:
    adjustment_part = f"_{adjustment}" if adjustment else ""
    return root / "data" / "cache" / f"{symbol.lower()}_{timeframe}_{feed}{adjustment_part}.csv"


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


def _alpaca_caveats(feed: str, adjustment: str | None = None) -> list[str]:
    adjustment_caveat = (
        [f"Alpaca bars were explicitly requested with adjustment={adjustment}"]
        if adjustment
        else ["Alpaca provider-default adjustment mode was used"]
    )
    if feed.lower() == "iex":
        return [
            "Alpaca free IEX feed is not consolidated full-market SIP data",
            *adjustment_caveat,
        ]
    return [
        f"Alpaca feed {feed} permissions and coverage must be verified",
        *adjustment_caveat,
    ]
