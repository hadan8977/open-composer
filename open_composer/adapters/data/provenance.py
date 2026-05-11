from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import ensure_dir
from open_composer.storage import write_json


def cache_manifest_path(
    root: Path,
    symbol: str,
    timeframe: str,
    provider: str,
    feed: str | None = None,
) -> Path:
    feed_part = f"_{_slug(feed)}" if feed else ""
    name = f"{symbol.lower()}_{timeframe}_{provider}{feed_part}.json"
    return root / "data" / "cache" / "manifests" / name


def write_ohlcv_manifest(
    root: Path,
    *,
    provider: str,
    symbol: str,
    timeframe: str,
    cache_path: Path,
    frame: pd.DataFrame,
    feed: str | None = None,
    requested_start: datetime | None = None,
    requested_end: datetime | None = None,
    source_mode: str,
    request_params: dict[str, Any] | None = None,
    caveats: list[str] | None = None,
) -> Path:
    timestamps = pd.to_datetime(frame["timestamp"], utc=True) if not frame.empty else []
    first_timestamp = timestamps.iloc[0].isoformat() if len(timestamps) else None
    last_timestamp = timestamps.iloc[-1].isoformat() if len(timestamps) else None
    manifest = {
        "provider": provider,
        "feed": feed,
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "records": int(len(frame)),
        "first_timestamp": first_timestamp,
        "last_timestamp": last_timestamp,
        "cache_path": str(cache_path),
        "cache_updated_at": datetime.now(UTC).isoformat(),
        "requested_start": requested_start.isoformat() if requested_start else None,
        "requested_end": requested_end.isoformat() if requested_end else None,
        "source_mode": source_mode,
        "request_params": request_params or {},
        "caveats": caveats or [],
    }
    path = cache_manifest_path(root, symbol, timeframe, provider, feed)
    ensure_dir(path.parent)
    return write_json(path, manifest)


def _slug(value: str | None) -> str:
    return (value or "").lower().replace(" ", "_").replace("/", "_")
