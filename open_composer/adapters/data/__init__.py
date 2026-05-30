from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.data.longbridge import fetch_longbridge_bars, normalize_longbridge_feed
from open_composer.adapters.data.provenance import write_ohlcv_manifest
from open_composer.adapters.data.sample import load_sample_ohlcv, normalize_ohlcv
from open_composer.config import data_feed
from open_composer.models.strategy_spec import StrategySpec
from open_composer.timeframes import require_timeframe_supported


def load_ohlcv_for_spec(spec: StrategySpec, root: Path, refresh: bool = False) -> pd.DataFrame:
    if spec.data.source == "sample":
        return load_sample_ohlcv(root, spec)
    if spec.data.source == "alpaca":
        return fetch_ohlcv(
            root=root,
            symbol=spec.primary_symbol,
            timeframe=spec.timeframe,
            start=None,
            end=None,
            source="alpaca",
            feed=spec.data.feed or data_feed(),
            use_cache=not refresh,
        )
    if spec.data.source == "longbridge":
        return fetch_ohlcv(
            root=root,
            symbol=spec.primary_symbol,
            timeframe=spec.timeframe,
            start=None,
            end=None,
            source="longbridge",
            feed=spec.data.feed,
            use_cache=not refresh,
        )
    raise ValueError(f"unsupported data source: {spec.data.source}")


def fetch_ohlcv(
    root: Path,
    symbol: str,
    timeframe: str,
    start: datetime | None,
    end: datetime | None,
    source: str = "alpaca",
    feed: str | None = None,
    use_cache: bool = True,
    allow_fallback: bool = True,
) -> pd.DataFrame:
    if source == "alpaca":
        require_timeframe_supported("alpaca", timeframe)
        try:
            return fetch_alpaca_bars(
                root=root,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                feed=feed or data_feed(),
                use_cache=use_cache,
            )
        except Exception:
            if not allow_fallback:
                raise
            return _fallback_ohlcv(root, symbol, timeframe, source, feed or data_feed())
    if source == "longbridge":
        require_timeframe_supported("longbridge", timeframe)
        selected_feed = normalize_longbridge_feed(feed)
        try:
            return fetch_longbridge_bars(
                root=root,
                symbol=symbol,
                timeframe=timeframe,
                start=start,
                end=end,
                feed=selected_feed,
                legacy_feed_alias=feed,
                use_cache=use_cache,
            )
        except Exception:
            if not allow_fallback:
                raise
            return _fallback_ohlcv(root, symbol, timeframe, source, selected_feed)
    raise ValueError(f"unsupported data source: {source}")


def _fallback_ohlcv(
    root: Path,
    symbol: str,
    timeframe: str,
    source: str,
    feed: str | None,
) -> pd.DataFrame:
    fixture_path = (
        root / "data" / "fixtures" / "capabilities" / f"{source}_{symbol.lower()}_{timeframe}.csv"
    )
    if fixture_path.exists():
        frame = normalize_ohlcv(pd.read_csv(fixture_path))
        frame.attrs.update(
            {
                "data_source_provider": source,
                "data_source_mode": "fixture_fallback",
                "data_source_feed": feed,
                "data_source_path": str(fixture_path),
            }
        )
        _write_fallback_manifest(
            root, symbol, timeframe, source, feed, fixture_path, frame, "fixture"
        )
        return frame
    sample_15m = root / "data" / "sample" / f"{symbol.lower()}_15m.csv"
    if sample_15m.exists():
        frame = normalize_ohlcv(pd.read_csv(sample_15m))
        fallback = _resample_ohlcv(frame, timeframe)
        fallback.attrs.update(
            {
                "data_source_provider": source,
                "data_source_mode": "sample_fallback",
                "data_source_feed": feed,
                "data_source_path": str(sample_15m),
            }
        )
        _write_fallback_manifest(
            root, symbol, timeframe, source, feed, sample_15m, fallback, "sample"
        )
        return fallback
    sample_path = root / "data" / "sample" / f"{symbol.lower()}_{timeframe}.csv"
    if sample_path.exists():
        frame = normalize_ohlcv(pd.read_csv(sample_path))
        frame.attrs.update(
            {
                "data_source_provider": source,
                "data_source_mode": "sample_fallback",
                "data_source_feed": feed,
                "data_source_path": str(sample_path),
            }
        )
        _write_fallback_manifest(
            root, symbol, timeframe, source, feed, sample_path, frame, "sample"
        )
        return frame
    raise FileNotFoundError(f"no fallback OHLCV available for {symbol} {timeframe} source={source}")


def _write_fallback_manifest(
    root: Path,
    symbol: str,
    timeframe: str,
    source: str,
    feed: str | None,
    path: Path,
    frame: pd.DataFrame,
    fallback_kind: str,
) -> None:
    write_ohlcv_manifest(
        root,
        provider=source,
        feed=feed,
        symbol=symbol,
        timeframe=timeframe,
        cache_path=path,
        frame=frame,
        source_mode=f"{fallback_kind}_fallback",
        caveats=[
            f"{source} live/cache data was unavailable; using local {fallback_kind} fallback",
            "Fallback data is for workflow validation and is not production-grade market data",
        ],
    )


def _resample_ohlcv(frame: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    if timeframe == "15m":
        return frame
    freq_map = {
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "daily": "1D",
        "weekly": "1W",
    }
    if timeframe not in freq_map:
        raise ValueError(f"unsupported fallback timeframe: {timeframe}")
    indexed = frame.copy()
    indexed["timestamp"] = pd.to_datetime(indexed["timestamp"], utc=True)
    indexed = indexed.set_index("timestamp")
    resampled = indexed.resample(freq_map[timeframe], label="right", closed="right").agg(
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
