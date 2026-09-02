"""Resumable bulk fetcher for Alpaca SIP bars across the full US equity universe.

Writes one parquet file per (symbol-shard, year) so an interrupted run resumes by
skipping shards that already exist. SIP is the consolidated tape and is a strict
superset of IEX, so nothing here should ever be mixed with the legacy IEX cache.
"""

from __future__ import annotations

import argparse
import json
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
# Minute bars are fetched one calendar month at a time in small symbol
# batches: a 40-symbol x 1-year minute request materialises >1.5M pandas
# rows at once, which drove this 3.8GB box 1.8GB into swap and stalled the
# fetch for 30 minutes. Month-sharding caps peak memory hard.
BATCH_SIZE = 12
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


def shard_path(out: Path, kind: str, year: int, shard: int, month: int | None = None) -> Path:
    if month is None:
        return out / kind / str(year) / f"shard-{shard:04d}.parquet"
    return out / kind / str(year) / f"{month:02d}" / f"shard-{shard:04d}.parquet"


def shard_is_done(out: Path, kind: str, year: int, shard: int, months: list[int]) -> bool:
    """A shard counts as done as a whole-year file (legacy layout) or all months."""
    if shard_path(out, kind, year, shard).exists():
        return True
    return all(shard_path(out, kind, year, shard, m).exists() for m in months)


def layout_path(out: Path, kind: str) -> Path:
    return out / kind / "_LAYOUT.json"


def assert_resumable_layout(out: Path, kind: str, *, batch_size: int, universe_size: int) -> None:
    """Refuse to resume into a shard numbering that means something else.

    Shard *N* is ``symbols[N * BATCH_SIZE : (N + 1) * BATCH_SIZE]``, so the shard
    index only identifies a set of symbols relative to the batch size that wrote
    it. This bit us for real: an earlier minute run used BATCH_SIZE=40 and got to
    shard 316 (VSS..VUSE, 94% through the alphabet); the resumed run used
    BATCH_SIZE=12 and treated shard 317 as EP.PRC..EPM, 28% through. Resume
    skipped nothing it should have and coverage survived only because the new
    numbering happened to start *earlier* in the alphabet than the old one ended.
    Had the batch size gone the other way, every symbol between the two points
    would have been silently missing, and nothing would have reported it.

    So the layout is recorded next to the shards, and a mismatch is fatal rather
    than silent. Deliberately not auto-migrated: re-deriving which existing shard
    holds which symbols is exactly the kind of guess that produces a quiet gap.
    """
    path = layout_path(out, kind)
    recorded = {"batch_size": batch_size, "universe_size": universe_size}
    if not path.exists():
        has_shards = (
            any((out / kind).glob("**/shard-*.parquet")) if (out / kind).is_dir() else False
        )
        if has_shards:
            raise SystemExit(
                f"{out / kind} already holds shards but no {path.name}; their batch size is "
                "unknown, so resuming could silently skip symbols. Record the layout by hand "
                "or re-fetch into a clean directory."
            )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(recorded, indent=2) + "\n", encoding="utf-8")
        return
    existing = json.loads(path.read_text(encoding="utf-8"))
    drift = {k: (existing.get(k), v) for k, v in recorded.items() if existing.get(k) != v}
    if drift:
        detail = ", ".join(f"{k}: recorded {was}, now {now}" for k, (was, now) in drift.items())
        raise SystemExit(
            f"shard layout changed since this archive was written ({detail}). Shard N means a "
            "different set of symbols under the new layout, so resuming would leave a silent "
            "gap. Finish with the recorded layout, or fetch into a clean directory."
        )


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
    if resume:
        assert_resumable_layout(out, kind, batch_size=BATCH_SIZE, universe_size=len(symbols))
    batches = [symbols[i : i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
    # Daily bars are ~390x smaller per symbol-year, so they stay whole-year;
    # minute bars are sharded per month to bound peak memory.
    months = list(range(1, 13)) if kind == "minute" else [None]

    total_rows = 0
    started = time.time()
    for year in range(start_year, end_year + 1):
        for shard, batch in enumerate(batches):
            if resume and shard_is_done(out, kind, year, shard, [m for m in months if m]):
                continue
            for month in months:
                destination = shard_path(out, kind, year, shard, month)
                if resume and destination.exists():
                    continue
                if month is None:
                    window_start = datetime(year, 1, 1, tzinfo=UTC)
                    window_end = datetime(year + 1, 1, 1, tzinfo=UTC)
                else:
                    window_start = datetime(year, month, 1, tzinfo=UTC)
                    window_end = (
                        datetime(year + 1, 1, 1, tzinfo=UTC)
                        if month == 12
                        else datetime(year, month + 1, 1, tzinfo=UTC)
                    )
                if window_start >= _sip_safe_end(window_end):
                    continue
                frame = _fetch_batch(data_client, batch, window_start, window_end, kind)
                destination.parent.mkdir(parents=True, exist_ok=True)
                if frame is None or frame.empty:
                    # Empty marker so resume does not retry a genuinely empty window.
                    pd.DataFrame(columns=["symbol", "timestamp"]).to_parquet(
                        destination, compression="zstd"
                    )
                    continue
                rows = len(frame)
                frame.reset_index().to_parquet(destination, compression="zstd", index=False)
                del frame  # release before the next window; this box has 3.8GB
                total_rows += rows
            elapsed = (time.time() - started) / 60
            LOG.info(
                "%s %d shard %d/%d  cumulative=%s  elapsed=%.1fmin",
                kind,
                year,
                shard + 1,
                len(batches),
                f"{total_rows:,}",
                elapsed,
            )
    marker = out / kind / f"_COMPLETE_{start_year}_{end_year}.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(
        json.dumps(
            {
                "kind": kind,
                "batch_size": BATCH_SIZE,
                "start_year": start_year,
                "end_year": end_year,
                "symbols": len(symbols),
                "shards_per_year": len(batches),
                "total_rows": total_rows,
                "finished_at": datetime.now(UTC).isoformat(),
                "elapsed_min": round((time.time() - started) / 60, 1),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    LOG.info(
        "done: %s rows in %.1f min -> %s", f"{total_rows:,}", (time.time() - started) / 60, marker
    )
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
