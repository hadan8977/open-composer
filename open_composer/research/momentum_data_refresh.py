from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.alpaca import fetch_alpaca_bars
from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.config import ensure_dir
from open_composer.research.research_cache_manifest import sha256_file
from open_composer.storage import write_json


@dataclass(frozen=True)
class MomentumDataRefreshResult:
    status: str
    receipt_path: Path
    payload: dict[str, Any]


def refresh_momentum_research_data(
    root: Path,
    *,
    symbols: tuple[str, ...] = ("QQQ", "TQQQ"),
    timeframe: str = "30m",
    feed: str = "iex",
    end: datetime | None = None,
    fetcher: Callable[..., pd.DataFrame] = fetch_alpaca_bars,
) -> MomentumDataRefreshResult:
    if timeframe != "30m" or feed != "iex":
        raise ValueError("frozen momentum refresh requires timeframe=30m and feed=iex")
    output_dir = root / "data/research/alpaca_minute"
    ensure_dir(output_dir)
    generated_at = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    status = "ok"
    for symbol in symbols:
        path = output_dir / f"{symbol.lower()}_{timeframe}_alpaca_{feed}.csv"
        old = normalize_ohlcv(pd.read_csv(path)) if path.exists() else pd.DataFrame()
        old_bytes = path.read_bytes() if path.exists() else b""
        start = None
        if not old.empty:
            start = pd.to_datetime(old["timestamp"], utc=True).max().to_pydatetime()
        try:
            fetched = fetcher(
                root,
                symbol,
                timeframe,
                start,
                end or generated_at,
                feed,
                False,
            )
            fetched = _regular_session_only(fetched)
            merged = _append_only_merge(old, fetched)
            _write_csv_preserving_prefix(path, old, merged, old_bytes)
            rows.append(
                {
                    "symbol": symbol,
                    "status": "ok",
                    "path": str(path.relative_to(root)),
                    "previous_records": len(old),
                    "records": len(merged),
                    "appended_records": len(merged) - len(old),
                    "first_timestamp": _timestamp(merged, "min"),
                    "last_timestamp": _timestamp(merged, "max"),
                    "sha256": sha256_file(path),
                }
            )
        except Exception as exc:  # keep the last verified snapshot on any provider failure
            status = "blocked"
            rows.append(
                {
                    "symbol": symbol,
                    "status": "blocked",
                    "path": str(path.relative_to(root)),
                    "error": str(exc),
                    "snapshot_preserved": path.exists() and path.read_bytes() == old_bytes,
                }
            )
    payload = {
        "report_type": "momentum_data_refresh_receipt",
        "status": status,
        "generated_at": generated_at.isoformat(),
        "provider": "alpaca",
        "feed": feed,
        "timeframe": timeframe,
        "strict": True,
        "fallback_allowed": False,
        "rows": rows,
    }
    receipt_dir = ensure_dir(root / "reports/research/control/momentum-data-refresh")
    receipt_path = receipt_dir / f"{generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    write_json(receipt_path, payload)
    write_json(receipt_dir / "latest.json", payload)
    return MomentumDataRefreshResult(status=status, receipt_path=receipt_path, payload=payload)


def verify_frozen_prefix(path: Path, contract: dict[str, Any]) -> None:
    raw = path.read_bytes()
    prefix_bytes = int(contract["prefix_bytes"])
    if len(raw) < prefix_bytes:
        raise ValueError(f"frozen source prefix truncated for {contract['symbol']}")
    actual = hashlib.sha256(raw[:prefix_bytes]).hexdigest()
    if actual != contract["prefix_sha256"]:
        raise ValueError(f"frozen source prefix mismatch for {contract['symbol']}")
    frame = normalize_ohlcv(pd.read_csv(path))
    timestamps = pd.to_datetime(frame["timestamp"], utc=True)
    frozen_at = pd.Timestamp(contract["prefix_last_timestamp"])
    prefix = frame.loc[timestamps <= frozen_at]
    if len(prefix) != int(contract["prefix_rows"]):
        raise ValueError(f"frozen source row count mismatch for {contract['symbol']}")
    if timestamps.duplicated().any() or not timestamps.is_monotonic_increasing:
        raise ValueError(f"non-monotonic or duplicate timestamps for {contract['symbol']}")


def _append_only_merge(old: pd.DataFrame, fetched: pd.DataFrame) -> pd.DataFrame:
    new = normalize_ohlcv(fetched)
    if old.empty:
        return new.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    old = normalize_ohlcv(old)
    old["timestamp"] = pd.to_datetime(old["timestamp"], utc=True)
    new["timestamp"] = pd.to_datetime(new["timestamp"], utc=True)
    overlap = old.merge(new, on="timestamp", suffixes=("_old", "_new"))
    for column in ("open", "high", "low", "close", "volume"):
        if not overlap.empty and not overlap[f"{column}_old"].equals(overlap[f"{column}_new"]):
            raise ValueError(f"historical market data revision detected for {column}")
    appended = new.loc[new["timestamp"] > old["timestamp"].max()]
    return pd.concat([old, appended], ignore_index=True).reset_index(drop=True)


def _regular_session_only(frame: pd.DataFrame) -> pd.DataFrame:
    data = normalize_ohlcv(frame)
    timestamps = pd.to_datetime(data["timestamp"], utc=True)
    local = timestamps.dt.tz_convert("America/New_York")
    minutes = local.dt.hour * 60 + local.dt.minute
    rth = data.loc[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)].copy()
    if len(rth) != len(data):
        extended = len(data) - len(rth)
        if rth.empty:
            raise ValueError(f"provider payload contains only extended-hours bars: {extended}")
    return rth.reset_index(drop=True)


def _write_csv_preserving_prefix(
    path: Path, old: pd.DataFrame, merged: pd.DataFrame, old_bytes: bytes
) -> None:
    if old.empty:
        merged.to_csv(path, index=False)
        return
    appended = merged.iloc[len(old) :]
    if appended.empty:
        return
    appended = appended.copy()
    appended["timestamp"] = pd.to_datetime(appended["timestamp"], utc=True).map(
        lambda value: value.isoformat()
    )
    with path.open("ab") as handle:
        csv = appended.to_csv(index=False, header=False).encode("utf-8")
        handle.write(csv)
    if not path.read_bytes().startswith(old_bytes):
        raise ValueError("append-only write changed the frozen source prefix")


def _timestamp(frame: pd.DataFrame, operation: str) -> str | None:
    if frame.empty:
        return None
    values = pd.to_datetime(frame["timestamp"], utc=True)
    value = values.min() if operation == "min" else values.max()
    return value.isoformat()
