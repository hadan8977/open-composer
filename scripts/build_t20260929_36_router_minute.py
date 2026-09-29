"""Extract regular-session SIP 1-minute bars for the 12-name NASDAQ router universe + QQQ.

T-20260929-36 / h20260929_36_router_sip. Streams one calendar month at a time through
`open_composer.adapters.data.sip_parquet.load_sip_bars` (footer-statistics shard pruning +
symbol predicate pushdown), keeps 09:30 <= ET time < 16:00 only, and writes one parquet per
month under data/features/t20260929_36_router_minute/. Resumable: finished months are skipped.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from open_composer.adapters.data.sip_parquet import load_sip_bars  # noqa: E402

UNIVERSE = [
    "AAPL",
    "MSFT",
    "NVDA",
    "AMZN",
    "META",
    "GOOGL",
    "AVGO",
    "AMD",
    "QCOM",
    "AMAT",
    "NFLX",
    "TSLA",
]
MARKET = "QQQ"
SYMBOLS = [*UNIVERSE, MARKET]
OUT_DIR = ROOT / "data" / "features" / "t20260929_36_router_minute"
FIRST_MONTH = (2023, 1)


def regular_session(frame: pd.DataFrame) -> pd.DataFrame:
    """Keep 09:30 <= America/New_York time < 16:00 (same rule as _regular_session_days)."""
    if frame.empty:
        return frame
    local = pd.to_datetime(frame["timestamp"], utc=True).dt.tz_convert("America/New_York")
    minutes = local.dt.hour * 60 + local.dt.minute
    return frame.loc[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)].reset_index(drop=True)


def months(end: datetime) -> list[tuple[int, int]]:
    out, (y, m) = [], FIRST_MONTH
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def extract_month(year: int, month: int) -> Path:
    path = OUT_DIR / f"{year}-{month:02d}.parquet"
    if path.exists():
        return path
    start = pd.Timestamp(year=year, month=month, day=1, tz="UTC")
    end = start + pd.offsets.MonthBegin(1) - pd.Timedelta(nanoseconds=1)
    frame = load_sip_bars(SYMBOLS, frequency="minute", start=start, end=end, allow_missing=True)
    frame = regular_session(frame)
    frame["symbol"] = frame["symbol"].astype(str)
    tmp = path.with_suffix(".tmp")
    frame.to_parquet(tmp, index=False)
    tmp.rename(path)
    return path


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(UTC)
    for year, month in months(now):
        path = OUT_DIR / f"{year}-{month:02d}.parquet"
        if path.exists():
            print(f"{year}-{month:02d} skip", flush=True)
            continue
        t0 = datetime.now(UTC)
        extract_month(year, month)
        n = len(pd.read_parquet(path, columns=["symbol"]))
        print(f"{year}-{month:02d} rows={n} sec={(datetime.now(UTC) - t0).seconds}", flush=True)
    (OUT_DIR / "_DONE.json").write_text(
        json.dumps({"finished_at": now.isoformat(), "symbols": SYMBOLS}), encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
