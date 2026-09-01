"""Resumable bulk fetcher for Alpaca SIP bars across the full US equity universe.

Writes one parquet file per (symbol-shard, year) so an interrupted run resumes by
skipping shards that already exist. SIP is the consolidated tape and is a strict
superset of IEX, so nothing here should ever be mixed with the legacy IEX cache.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

LOG = logging.getLogger("fetch_sip")
DEFAULT_OUT = Path("data/sip")
BATCH_SIZE = 40
# Alpaca rejects SIP queries reaching into the last ~15 minutes without a
# real-time SIP subscription; 16 gives a small safety margin.
SIP_RECENT_EMBARGO_MINUTES = 16
MAX_RETRIES = 5


def _clients():
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.trading.client import TradingClient

    key = os.getenv("ALPACA_API_KEY_ID")
    secret = os.getenv("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        raise SystemExit("ALPACA_API_KEY_ID / ALPACA_API_SECRET_KEY are not configured")
    return (
        TradingClient(key, secret, paper=True),
        StockHistoricalDataClient(key, secret),
    )


def load_universe(trading_client, *, limit: int | None = None) -> list[str]:
    from alpaca.trading.enums import AssetClass, AssetStatus
    from alpaca.trading.requests import GetAssetsRequest

    assets = trading_client.get_all_assets(
        GetAssetsRequest(status=AssetStatus.ACTIVE, asset_class=AssetClass.US_EQUITY)
    )
    symbols = sorted({a.symbol for a in assets if a.tradable})
    return symbols[:limit] if limit else symbols


def _timeframe(kind: str):
    from alpaca.data.timeframe import TimeFrame

    return TimeFrame.Minute if kind == "minute" else TimeFrame.Day


def _sip_safe_end(end: datetime) -> datetime:
    """Clamp ``end`` to the newest timestamp a SIP query is allowed to reach.

    Alpaca rejects SIP queries whose window extends into the last ~15 minutes
    ("subscription does not permit querying recent SIP data") unless the account
    carries a real-time SIP subscription. Historical backfills never need that
    edge, so clamp instead of failing the whole shard.
    """
    ceiling = datetime.now(UTC) - timedelta(minutes=SIP_RECENT_EMBARGO_MINUTES)
    return min(end, ceiling)


def _fetch_batch(data_client, symbols: list[str], start: datetime, end: datetime, kind: str):
    from alpaca.data.requests import StockBarsRequest

    end = _sip_safe_end(end)
    if end <= start:
        return None
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=_timeframe(kind),
        start=start,
        end=end,
        feed="sip",
        adjustment="all",
    )
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return data_client.get_stock_bars(request).df
        except Exception as exc:  # noqa: BLE001 - transient API/network errors
            if attempt == MAX_RETRIES:
                raise
            wait = min(60, 2**attempt)
            LOG.warning("batch failed (%s), retry %d/%d in %ds", exc, attempt, MAX_RETRIES, wait)
            time.sleep(wait)
    return None


def shard_path(out: Path, kind: str, year: int, shard: int) -> Path:
    return out / kind / str(year) / f"shard-{shard:04d}.parquet"


def run(
    *,
    kind: str,
    start_year: int,
    end_year: int,
    out: Path,
    limit: int | None,
    resume: bool,
) -> int:
    trading_client, data_client = _clients()
    symbols = load_universe(trading_client, limit=limit)
    LOG.info("universe: %d tradable symbols", len(symbols))
    batches = [symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]

    total_rows = 0
    started = time.time()
    for year in range(start_year, end_year + 1):
        year_start = datetime(year, 1, 1, tzinfo=UTC)
        year_end = datetime(year + 1, 1, 1, tzinfo=UTC)
        for shard, batch in enumerate(batches):
            destination = shard_path(out, kind, year, shard)
            if resume and destination.exists():
                continue
            frame = _fetch_batch(data_client, batch, year_start, year_end, kind)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if frame is None or frame.empty:
                # Persist an empty marker so resume does not retry a genuinely empty shard.
                pd.DataFrame(columns=["symbol", "timestamp"]).to_parquet(
                    destination, compression="zstd"
                )
                continue
            frame.reset_index().to_parquet(destination, compression="zstd", index=False)
            total_rows += len(frame)
            elapsed = time.time() - started
            LOG.info(
                "%s %d shard %d/%d  rows=%s  cumulative=%s  elapsed=%.1fmin",
                kind,
                year,
                shard + 1,
                len(batches),
                f"{len(frame):,}",
                f"{total_rows:,}",
                elapsed / 60,
            )
    LOG.info("done: %s rows in %.1f min", f"{total_rows:,}", (time.time() - started) / 60)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["daily", "minute"], required=True)
    parser.add_argument("--start-year", type=int, required=True)
    parser.add_argument("--end-year", type=int, required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="Only the first N symbols.")
    parser.add_argument("--no-resume", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    return run(
        kind=args.kind,
        start_year=args.start_year,
        end_year=args.end_year,
        out=args.out,
        limit=args.limit,
        resume=not args.no_resume,
    )


if __name__ == "__main__":
    raise SystemExit(main())
