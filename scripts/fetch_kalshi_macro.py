#!/usr/bin/env python3
"""Fetch Kalshi macro-release markets and hourly candlesticks (public API, no key).

T-20261002-44. One parquet file of hourly candlesticks per event plus a small
markets JSON next to it, under ``data/research/prediction_markets/kalshi/raw/``.

Routing follows the Kalshi docs (and the MIT-licensed WillBtK/macro_kalshi
scraper): markets settled before ``/historical/cutoff`` live under
``/historical/markets/{ticker}/candlesticks``, newer ones under
``/series/{series}/markets/{ticker}/candlesticks``.

Request discipline: at most 5 requests per second, exponential backoff on
429/5xx and network errors, checkpoint after every event (an event is done when
both of its files exist; files are written atomically).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import polars as pl

BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
DEFAULT_SERIES = (
    "KXCPI",
    "KXPAYROLLS",
    "KXGDP",
    "KXFED",
    "KXPCE",
    "KXCPICOREYOY",
    "KXU3",
)
RAW_DIR = Path("data/research/prediction_markets/kalshi/raw")
MIN_INTERVAL_S = 0.21  # 5 requests per second at most
CHUNK_HOURS = 2400  # stay far below the per-request candlestick cap
MAX_RETRIES = 6

CANDLE_SCHEMA: dict[str, Any] = {
    "series_ticker": pl.Utf8,
    "event_ticker": pl.Utf8,
    "market_ticker": pl.Utf8,
    "endpoint": pl.Utf8,
    "end_period_ts": pl.Int64,
    "yes_bid_open": pl.Float64,
    "yes_bid_high": pl.Float64,
    "yes_bid_low": pl.Float64,
    "yes_bid_close": pl.Float64,
    "yes_ask_open": pl.Float64,
    "yes_ask_high": pl.Float64,
    "yes_ask_low": pl.Float64,
    "yes_ask_close": pl.Float64,
    "price_open": pl.Float64,
    "price_high": pl.Float64,
    "price_low": pl.Float64,
    "price_close": pl.Float64,
    "price_mean": pl.Float64,
    "price_previous": pl.Float64,
    "volume": pl.Float64,
    "open_interest": pl.Float64,
}

HttpGet = Callable[[str, dict[str, Any]], tuple[int, Any]]


def _httpx_get(url: str, params: dict[str, Any]) -> tuple[int, Any]:
    import httpx

    response = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=30.0)
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


class KalshiClient:
    """Rate-limited GET client with exponential backoff; the HTTP layer is injectable."""

    def __init__(
        self,
        http_get: HttpGet = _httpx_get,
        *,
        base_url: str = BASE_URL,
        min_interval_s: float = MIN_INTERVAL_S,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._http_get = http_get
        self._base = base_url.rstrip("/")
        self._min_interval = min_interval_s
        self._sleep = sleep
        self._clock = clock
        self._last = -1e9
        self.requests = 0

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self._base}/{path.lstrip('/')}"
        delay = 1.0
        for attempt in range(MAX_RETRIES + 1):
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()
            self.requests += 1
            try:
                status, body = self._http_get(url, params or {})
            except Exception:  # network error: retry like a 5xx
                status, body = 599, None
            if status == 200 and body is not None:
                return body
            if status == 404:
                return None
            if status == 429 or status >= 500:
                if attempt == MAX_RETRIES:
                    break
                self._sleep(delay)
                delay = min(delay * 2, 60.0)
                continue
            raise RuntimeError(f"unexpected status {status} for {url}")
        raise RuntimeError(f"giving up on {url} after {MAX_RETRIES} retries")


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _pick(block: dict[str, Any] | None, key: str) -> float | None:
    """Value of ``key`` in a candle block; the live endpoint names fields ``<key>_dollars``."""
    block = block or {}
    value = block.get(key)
    if value is None:
        value = block.get(f"{key}_dollars")
    return _f(value)


def parse_candles(
    raw: list[dict[str, Any]], *, series: str, event: str, ticker: str, endpoint: str
) -> list[dict[str, Any]]:
    """Parse candlesticks from either schema.

    ``/historical/...`` returns ``{"close": "0.4"}`` and ``volume``/``open_interest``;
    ``/series/.../candlesticks`` (live) returns ``{"close_dollars": "0.4"}`` and
    ``volume_fp``/``open_interest_fp``. Both are mapped onto the same columns.
    """
    rows = []
    for c in raw:
        bid = c.get("yes_bid") or {}
        ask = c.get("yes_ask") or {}
        price = c.get("price") or {}
        volume = c.get("volume", c.get("volume_fp"))
        interest = c.get("open_interest", c.get("open_interest_fp"))
        rows.append(
            {
                "series_ticker": series,
                "event_ticker": event,
                "market_ticker": ticker,
                "endpoint": endpoint,
                "end_period_ts": int(c["end_period_ts"]),
                "yes_bid_open": _pick(bid, "open"),
                "yes_bid_high": _pick(bid, "high"),
                "yes_bid_low": _pick(bid, "low"),
                "yes_bid_close": _pick(bid, "close"),
                "yes_ask_open": _pick(ask, "open"),
                "yes_ask_high": _pick(ask, "high"),
                "yes_ask_low": _pick(ask, "low"),
                "yes_ask_close": _pick(ask, "close"),
                "price_open": _pick(price, "open"),
                "price_high": _pick(price, "high"),
                "price_low": _pick(price, "low"),
                "price_close": _pick(price, "close"),
                "price_mean": _pick(price, "mean"),
                "price_previous": _pick(price, "previous"),
                "volume": _f(volume),
                "open_interest": _f(interest),
            }
        )
    return rows


def _ts(value: str | None) -> int | None:
    if not value:
        return None
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())


def fetch_cutoff(client: KalshiClient) -> int:
    body = client.get("historical/cutoff")
    stamp = (body or {}).get("market_settled_ts")
    ts = _ts(stamp)
    if ts is None:
        raise RuntimeError("historical/cutoff returned no market_settled_ts")
    return ts


def list_events(client: KalshiClient, series: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    cursor = ""
    while True:
        params: dict[str, Any] = {
            "series_ticker": series,
            "with_nested_markets": "true",
            "limit": 200,
        }
        if cursor:
            params["cursor"] = cursor
        body = client.get("events", params) or {}
        events.extend(body.get("events") or [])
        cursor = body.get("cursor") or ""
        if not cursor:
            return events


def event_markets(
    client: KalshiClient, event: dict[str, Any], live_markets: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Union of nested live markets and historical markets, keyed by ticker."""
    by_ticker = {m["ticker"]: {**m, "_source": "live"} for m in live_markets}
    cursor = ""
    while True:
        params: dict[str, Any] = {"event_ticker": event["event_ticker"], "limit": 1000}
        if cursor:
            params["cursor"] = cursor
        body = client.get("historical/markets", params) or {}
        for m in body.get("markets") or []:
            by_ticker.setdefault(m["ticker"], {**m, "_source": "historical"})
        cursor = body.get("cursor") or ""
        if not cursor:
            break
    return sorted(by_ticker.values(), key=lambda m: (m.get("floor_strike") is None, m["ticker"]))


def market_meta(m: dict[str, Any]) -> dict[str, Any]:
    keep = (
        "ticker",
        "event_ticker",
        "strike_type",
        "floor_strike",
        "cap_strike",
        "open_time",
        "close_time",
        "expected_expiration_time",
        "occurrence_datetime",
        "settlement_ts",
        "status",
        "result",
        "expiration_value",
        "subtitle",
        "yes_sub_title",
        "_source",
    )
    return {k: m.get(k) for k in keep}


def fetch_market_candles(
    client: KalshiClient, series: str, m: dict[str, Any], cutoff_ts: int
) -> tuple[list[dict[str, Any]], str]:
    ticker = m["ticker"]
    start = _ts(m.get("open_time"))
    end = _ts(m.get("close_time"))
    if start is None or end is None or end <= start:
        return [], "none"
    settled = _ts(m.get("settlement_ts")) or end
    first = "historical" if settled < cutoff_ts else "live"
    order = [first, "live" if first == "historical" else "historical"]
    for endpoint in order:
        rows: list[dict[str, Any]] = []
        t0 = start
        while t0 < end:
            t1 = min(end, t0 + CHUNK_HOURS * 3600)
            path = (
                f"historical/markets/{ticker}/candlesticks"
                if endpoint == "historical"
                else f"series/{series}/markets/{ticker}/candlesticks"
            )
            body = client.get(path, {"start_ts": t0, "end_ts": t1, "period_interval": 60}) or {}
            rows.extend(
                parse_candles(
                    body.get("candlesticks") or [],
                    series=series,
                    event=m["event_ticker"],
                    ticker=ticker,
                    endpoint=endpoint,
                )
            )
            t0 = t1
        if rows:
            return rows, endpoint
    return [], first


def _atomic_write(path: Path, writer: Callable[[Path], None]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    writer(tmp)
    os.replace(tmp, path)


def checkpoint_is_final(parquet: Path, event: dict[str, Any]) -> bool:
    """A checkpoint is final only if it was written after every market of the event closed.

    Events fetched while still open are fetched again on the next run, because their later
    candles (up to the signal time on T-1) were not yet available. Events without market close
    times keep the old behaviour (final once written).
    """
    closes = [m.get("close_time") for m in (event.get("markets") or []) if m.get("close_time")]
    if not closes:
        return True
    last_close = max(datetime.fromisoformat(str(c).replace("Z", "+00:00")) for c in closes)
    written = datetime.fromtimestamp(parquet.stat().st_mtime, UTC)
    return written >= last_close


def fetch_event(
    client: KalshiClient, series: str, event: dict[str, Any], cutoff_ts: int, out_dir: Path
) -> dict[str, Any]:
    ticker = event["event_ticker"]
    parquet = out_dir / series / f"{ticker}.parquet"
    meta_path = out_dir / series / f"{ticker}.markets.json"
    if parquet.exists() and meta_path.exists() and checkpoint_is_final(parquet, event):
        return {"event": ticker, "skipped": True}
    markets = event_markets(client, event, event.get("markets") or [])
    rows: list[dict[str, Any]] = []
    metas = []
    for m in markets:
        if m.get("strike_type") != "greater" or m.get("floor_strike") is None:
            metas.append({**market_meta(m), "endpoint": "skipped_non_greater"})
            continue
        candles, endpoint = fetch_market_candles(client, series, m, cutoff_ts)
        rows.extend(candles)
        metas.append({**market_meta(m), "endpoint": endpoint, "n_candles": len(candles)})
    frame = pl.DataFrame(rows, schema=CANDLE_SCHEMA) if rows else pl.DataFrame(schema=CANDLE_SCHEMA)
    payload = {
        "series_ticker": series,
        "event_ticker": ticker,
        "title": event.get("title"),
        "sub_title": event.get("sub_title"),
        "fetched_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "cutoff_ts": cutoff_ts,
        "markets": metas,
    }
    _atomic_write(parquet, lambda p: frame.write_parquet(p))
    _atomic_write(meta_path, lambda p: p.write_text(json.dumps(payload, indent=1)))
    return {"event": ticker, "markets": len(metas), "candles": len(rows)}


def run(
    series_list: list[str],
    out_dir: Path,
    client: KalshiClient,
    *,
    log: Callable[[str], None] = print,
    max_events: int | None = None,
) -> dict[str, Any]:
    cutoff_ts = fetch_cutoff(client)
    summary: dict[str, Any] = {"cutoff_ts": cutoff_ts, "series": {}}
    for series in series_list:
        info = client.get(f"series/{series}")
        if info is None:
            log(f"{series}: series not found")
            summary["series"][series] = {"exists": False, "events": 0}
            continue
        events = list_events(client, series)
        events = [e for e in events if e.get("event_ticker")]
        if max_events:
            events = events[:max_events]
        summary["series"][series] = {"exists": True, "events": len(events)}
        log(f"{series}: {len(events)} events")
        for event in events:
            res = fetch_event(client, series, event, cutoff_ts, out_dir)
            log(f"  {res}")
    summary["requests"] = client.requests
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--series", nargs="*", default=list(DEFAULT_SERIES))
    parser.add_argument("--out-dir", type=Path, default=RAW_DIR)
    parser.add_argument("--max-events", type=int, default=None)
    args = parser.parse_args(argv)
    summary = run(list(args.series), args.out_dir, KalshiClient(), max_events=args.max_events)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "_fetch_summary.json").write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    sys.exit(main())
