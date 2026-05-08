from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

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
    if use_cache and cache_path.exists() and start is None and end is None:
        return normalize_ohlcv(pd.read_csv(cache_path))

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
    ensure_dir(cache_path.parent)
    frame.to_csv(cache_path, index=False)
    return frame


def _alpaca_timeframe(timeframe: str) -> Any:
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    mapping = {
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
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
