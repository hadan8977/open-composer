from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.longbridge import (
    DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
    MAX_LONGBRIDGE_CANDLESTICKS,
    _fetch_live_longbridge_bars,
)
from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

DEFAULT_SYMBOLS = [
    "QQQ",
    "TQQQ",
    "QLD",
    "SOXL",
    "USD",
    "SMH",
    "SOXX",
    "XLK",
    "IGV",
    "GLD",
    "BIL",
]
DEFAULT_OUTPUT_DIR = Path("data/research/longbridge_adjusted_daily")
DEFAULT_START_DATE = "2010-02-11"
DEFAULT_END_DATE = "2026-05-22"


def materialize_longbridge_history(
    root: Path,
    symbols: list[str],
    *,
    start_date: str = DEFAULT_START_DATE,
    end_date: str = DEFAULT_END_DATE,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, Any]:
    out_dir = ensure_dir(root / output_dir)
    start = _timestamp(start_date)
    end = _timestamp(end_date)
    rows = []
    for raw_symbol in symbols:
        symbol = raw_symbol.upper()
        path = out_dir / f"{symbol.lower()}_daily_longbridge_adjusted.csv"
        frame: pd.DataFrame | None = None
        if path.exists():
            cached = _read_price_csv(path)
            if _covers(cached, start, end):
                frame = cached
        source_mode = "cache"
        chunks: list[dict[str, Any]] = []
        if frame is None:
            frame, chunks = _fetch_symbol_history(root, symbol, start, end)
            frame.to_csv(path, index=False)
            source_mode = "live_fetch_chunked"
        rows.append(
            {
                "symbol": symbol,
                "path": str(path),
                "source_mode": source_mode,
                "records": int(len(frame)),
                "first_timestamp": _iso(frame["timestamp"].min()) if not frame.empty else None,
                "last_timestamp": _iso(frame["timestamp"].max()) if not frame.empty else None,
                "chunks": chunks,
            }
        )
    return {
        "provider": "longbridge",
        "feed": "nasdaq_basic",
        "adjusted": True,
        "trade_sessions": DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
        "max_request_bars": MAX_LONGBRIDGE_CANDLESTICKS,
        "requested_start": start_date,
        "requested_end": end_date,
        "output_dir": str(root / output_dir),
        "symbols": rows,
    }


def _fetch_symbol_history(
    root: Path,
    symbol: str,
    start: datetime,
    end: datetime,
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    frames = []
    chunks = []
    cursor_end = end
    previous_first: pd.Timestamp | None = None
    while cursor_end >= start:
        try:
            frame = _fetch_live_longbridge_bars(
                root=root,
                symbol=symbol,
                timeframe="daily",
                start=start,
                end=cursor_end,
                adjusted=True,
                count=MAX_LONGBRIDGE_CANDLESTICKS,
                trade_sessions=DEFAULT_LONGBRIDGE_TRADE_SESSIONS,
            )
        except ValueError as exc:
            chunks.append(
                {
                    "requested_end": cursor_end.date().isoformat(),
                    "records": 0,
                    "error": str(exc),
                }
            )
            break
        frame = _normalize_frame(frame)
        if frame.empty:
            break
        frames.append(frame)
        first = frame["timestamp"].min()
        last = frame["timestamp"].max()
        chunks.append(
            {
                "requested_end": cursor_end.date().isoformat(),
                "records": int(len(frame)),
                "first_timestamp": _iso(first),
                "last_timestamp": _iso(last),
            }
        )
        if first <= pd.Timestamp(start):
            break
        if previous_first is not None and first >= previous_first:
            break
        previous_first = first
        cursor_end = first.to_pydatetime() - timedelta(days=1)
    if not frames:
        return _empty_frame(), chunks
    merged = pd.concat(frames, ignore_index=True)
    merged = _normalize_frame(merged)
    merged["_date"] = merged["timestamp"].dt.date
    merged = merged[(merged["_date"] >= start.date()) & (merged["_date"] <= end.date())]
    merged = merged.drop(columns=["_date"])
    return merged.reset_index(drop=True), chunks


def _normalize_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return _empty_frame()
    output = frame[["timestamp", "open", "high", "low", "close", "volume"]].copy()
    output["timestamp"] = pd.to_datetime(output["timestamp"], utc=True)
    output = output.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    for column in ["open", "high", "low", "close", "volume"]:
        output[column] = pd.to_numeric(output[column], errors="coerce")
    return output.reset_index(drop=True)


def _read_price_csv(path: Path) -> pd.DataFrame:
    return _normalize_frame(pd.read_csv(path))


def _empty_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])


def _covers(frame: pd.DataFrame, start: datetime, end: datetime) -> bool:
    del start
    if frame.empty:
        return False
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    dates = timestamps.dt.date
    return bool(dates.min() <= end.date() and dates.max() >= end.date())


def _timestamp(value: str) -> datetime:
    return pd.Timestamp(value, tz=UTC).to_pydatetime()


def _iso(value: Any) -> str:
    return pd.Timestamp(value).isoformat()


def _parse_symbols(values: list[str] | None) -> list[str]:
    if not values:
        return DEFAULT_SYMBOLS
    symbols: list[str] = []
    for value in values:
        symbols.extend(item.strip().upper() for item in value.split(",") if item.strip())
    return list(dict.fromkeys(symbols))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize adjusted daily Longbridge history for research replay."
    )
    parser.add_argument("--symbols", nargs="*", help="Symbols as a space or comma separated list.")
    parser.add_argument("--start", default=DEFAULT_START_DATE, help="Inclusive start date.")
    parser.add_argument("--end", default=DEFAULT_END_DATE, help="Inclusive end date.")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="Output directory.")
    parser.add_argument(
        "--manifest",
        default="reports/research/control/longbridge-adjusted-refetch-manifest.json",
        help="Manifest JSON output path.",
    )
    args = parser.parse_args()
    root = project_root()
    manifest = materialize_longbridge_history(
        root,
        _parse_symbols(args.symbols),
        start_date=args.start,
        end_date=args.end,
        output_dir=Path(args.output_dir),
    )
    manifest_path = root / args.manifest
    ensure_dir(manifest_path.parent)
    write_json(manifest_path, manifest)
    print(manifest_path)


if __name__ == "__main__":
    main()
