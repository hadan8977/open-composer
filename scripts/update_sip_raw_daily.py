"""Append completed US equity sessions to the local Alpaca SIP RAW archive."""

from __future__ import annotations

import json
import os
import sys
import time as clock
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from open_composer.adapters.data.sip_parquet import BAR_COLUMNS, MARKET_DATA, RAW_UPDATE_VERSION
from open_composer.market_sessions import NEW_YORK, us_equity_session_close, us_equity_session_dates
from open_composer.research.file_lock import lock_file

BARS_URL = "https://data.alpaca.markets/v2/stocks/bars"
ASSETS_URL = "https://paper-api.alpaca.markets/v2/assets"
FIRST_DAY = date(2026, 11, 18)
SIP_DELAY = timedelta(minutes=16)
BATCH_SIZE = 200
TIMEFRAMES = {"daily": "1Day", "minute": "1Min"}
PRICE_FIELDS = dict(zip(BAR_COLUMNS[2:], ("o", "h", "l", "c", "v", "n", "vw"), strict=True))
SCHEMA = pa.schema(
    [("symbol", pa.string()), ("timestamp", pa.timestamp("ns", tz="UTC"))]
    + [(column, pa.float64()) for column in PRICE_FIELDS]
)


def alpaca_session():
    session = requests.Session()
    session.headers.update(
        {
            "APCA-API-KEY-ID": os.environ["ALPACA_API_KEY_ID"],
            "APCA-API-SECRET-KEY": os.environ["ALPACA_API_SECRET_KEY"],
        }
    )
    session.mount(
        "https://",
        HTTPAdapter(
            max_retries=Retry(total=3, backoff_factor=1, status_forcelist=(429, 502, 503, 504))
        ),
    )
    return session


def fetch_shard(session, path, symbols, timeframe, start, end):
    """Publish a shard only after the last page. The end bound is exclusive."""
    params = {
        "symbols": ",".join(symbols),
        "timeframe": timeframe,
        "start": start.isoformat(),
        "end": (end - timedelta(microseconds=1)).isoformat(),
        "feed": "sip",
        "adjustment": "raw",
        "asof": "-",
        "limit": 10000,
    }
    schema = SCHEMA.with_metadata({"sip_query": json.dumps(params)})
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".partial")
    wanted = set(symbols)
    tokens = set()
    count = 0
    with pq.ParquetWriter(partial, schema, compression="zstd") as writer:
        while True:
            response = session.get(BARS_URL, params=params, timeout=(5, 30))
            response.raise_for_status()
            payload = response.json()
            bars = payload["bars"] or {}
            if bars.keys() - wanted:
                raise ValueError("Alpaca returned an unrequested symbol")
            rows = []
            for symbol, values in bars.items():
                for value in values:
                    timestamp = datetime.fromisoformat(value["t"])
                    if start <= timestamp < end:
                        rows.append(
                            {
                                "symbol": symbol,
                                "timestamp": timestamp,
                                **{key: value[field] for key, field in PRICE_FIELDS.items()},
                            }
                        )
            if rows:
                writer.write_table(pa.Table.from_pylist(rows, schema=schema))
                count += len(rows)
            token = payload["next_page_token"]
            if token is None:
                break
            if token in tokens:
                raise ValueError("Alpaca repeated a pagination token")
            tokens.add(token)
            params["page_token"] = token
            remaining = response.headers.get("X-RateLimit-Remaining")
            reset = response.headers.get("X-RateLimit-Reset")
            if remaining is not None and reset is not None and int(remaining) <= 80:
                clock.sleep(max(0.0, float(reset) - clock.time() + 1))
    partial.replace(path)
    return count


def pending_sessions(now, archive):
    today = now.astimezone(NEW_YORK).date()
    if today < FIRST_DAY:
        return []
    sessions = []
    for day in us_equity_session_dates(FIRST_DAY, today):
        close = datetime.combine(day, us_equity_session_close(day), NEW_YORK)
        if now >= close + SIP_DELAY and not (archive / day.isoformat()).is_dir():
            sessions.append((day, close.astimezone(UTC)))
    return sessions


def publish_session(session, archive, day, close, registry):
    stage = archive / ".staging" / day.isoformat()
    stage.mkdir(parents=True, exist_ok=True)
    registry_path = stage / "symbols.json"
    if registry_path.exists():
        symbols = json.loads(registry_path.read_text(encoding="utf-8"))
    else:
        symbols = sorted(registry)
        temporary = registry_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(symbols), encoding="utf-8")
        temporary.replace(registry_path)
    start = datetime.combine(day, time.min, NEW_YORK).astimezone(UTC)
    counts = dict.fromkeys(TIMEFRAMES, 0)
    for frequency, timeframe in TIMEFRAMES.items():
        for offset in range(0, len(symbols), BATCH_SIZE):
            path = stage / frequency / f"shard-{offset // BATCH_SIZE:04d}.parquet"
            if path.exists():
                count = pq.read_metadata(path).num_rows
            else:
                count = fetch_shard(
                    session, path, symbols[offset : offset + BATCH_SIZE], timeframe, start, close
                )
            counts[frequency] += count
        if not counts[frequency]:
            raise ValueError(f"Alpaca returned no {frequency} bars for {day}")
    manifest = {
        "date": day.isoformat(),
        "end_exclusive": close.isoformat(),
        "symbols": len(symbols),
        "rows": counts,
    }
    (stage / "manifest.json").write_text(json.dumps(manifest) + "\n", encoding="utf-8")
    stage.rename(archive / day.isoformat())
    return manifest


def update(session, market_data=MARKET_DATA, now=None):
    archive = market_data / RAW_UPDATE_VERSION
    archive.mkdir(exist_ok=True)
    with (archive / ".writer.lock").open("a+b") as lock:
        lock_file(lock)
        pending = pending_sessions(now or datetime.now(UTC), archive)
        if not pending:
            return []
        prior = sorted(archive.glob("[0-9][0-9][0-9][0-9]-??-??"))
        seed = market_data / "sip-raw-recent" / "request-plan.json"
        registry = set(json.loads(seed.read_text(encoding="utf-8-sig"))["symbols"])
        if prior:
            registry.update(json.loads((prior[-1] / "symbols.json").read_text(encoding="utf-8")))
        response = session.get(
            ASSETS_URL, params={"status": "active", "asset_class": "us_equity"}, timeout=(5, 30)
        )
        response.raise_for_status()
        registry.update(asset["symbol"] for asset in response.json())
        results = []
        for day, close in pending:
            manifest = publish_session(session, archive, day, close, registry)
            print(json.dumps(manifest), flush=True)
            results.append(manifest)
            registry.update(
                json.loads((archive / day.isoformat() / "symbols.json").read_text(encoding="utf-8"))
            )
        return results


if __name__ == "__main__":
    with alpaca_session() as client:
        update(client)
