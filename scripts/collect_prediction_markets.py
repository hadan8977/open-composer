#!/usr/bin/env python3
"""Hourly point-in-time snapshot of Kalshi macro markets and a Polymarket watchlist.

T-20261002-44. One run = one snapshot, appended as new parquet files only:

  data/features/prediction_markets/kalshi_hourly/date=YYYY-MM-DD/part-HHMMSS.parquet
  data/features/prediction_markets/polymarket_hourly/date=YYYY-MM-DD/part-HHMMSS.parquet

Every row carries ``fetched_at_utc`` (when we asked) next to the source's own
timestamps. Old files are never rewritten. A run has a 120 s budget; any failure
exits non-zero and writes nothing (both files are staged, then renamed).

Kalshi: all open events of the macro series (public API, no key).
Polymarket: the markets listed in config/prediction_markets/polymarket_watchlist.yaml,
read from the public Gamma API (no key, no wallet). Research input only; nothing here
trades or authenticates.
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

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[1]
KALSHI_BASE = "https://api.elections.kalshi.com/trade-api/v2"
GAMMA_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
KALSHI_SERIES = ("KXCPI", "KXPAYROLLS", "KXGDP", "KXFED", "KXPCE", "KXCPICOREYOY", "KXU3")
WATCHLIST = ROOT / "config/prediction_markets/polymarket_watchlist.yaml"
OUT_ROOT = ROOT / "data/features/prediction_markets"
TOTAL_BUDGET_S = 120.0
MIN_INTERVAL_S = 0.21
MAX_RETRIES = 3

HttpGet = Callable[[str, dict[str, Any], float], tuple[int, Any]]


def _httpx_get(url: str, params: dict[str, Any], timeout: float) -> tuple[int, Any]:
    import httpx

    response = httpx.get(url, params=params, headers={"User-Agent": USER_AGENT}, timeout=timeout)
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


class Http:
    """Rate-limited GET with a hard overall deadline and bounded retries."""

    def __init__(
        self,
        http_get: HttpGet = _httpx_get,
        *,
        budget_s: float = TOTAL_BUDGET_S,
        min_interval_s: float = MIN_INTERVAL_S,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._get = http_get
        self._sleep = sleep
        self._clock = clock
        self._min_interval = min_interval_s
        self._deadline = clock() + budget_s
        self._last = -1e9

    def get(
        self, url: str, params: dict[str, Any] | None = None, *, allow_404: bool = False
    ) -> Any:
        delay = 1.0
        for attempt in range(MAX_RETRIES + 1):
            remaining = self._deadline - self._clock()
            if remaining <= 0:
                raise TimeoutError(f"snapshot budget exhausted before {url}")
            wait = self._min_interval - (self._clock() - self._last)
            if wait > 0:
                self._sleep(wait)
            self._last = self._clock()
            try:
                status, body = self._get(url, params or {}, min(20.0, max(remaining, 1.0)))
            except Exception:
                status, body = 599, None
            if status == 200 and body is not None:
                return body
            if status == 404 and allow_404:
                return None
            if (status == 429 or status >= 500) and attempt < MAX_RETRIES:
                self._sleep(delay)
                delay *= 2
                continue
            raise RuntimeError(f"request failed ({status}): {url}")
        raise RuntimeError(f"request failed: {url}")


def _f(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def kalshi_rows(http: Http, fetched_at: str, series_list: tuple[str, ...]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for series in series_list:
        if http.get(f"{KALSHI_BASE}/series/{series}", allow_404=True) is None:
            continue
        cursor = ""
        while True:
            params: dict[str, Any] = {
                "series_ticker": series,
                "status": "open",
                "with_nested_markets": "true",
                "limit": 200,
            }
            if cursor:
                params["cursor"] = cursor
            body = http.get(f"{KALSHI_BASE}/events", params) or {}
            for event in body.get("events") or []:
                for m in event.get("markets") or []:
                    rows.append(
                        {
                            "fetched_at_utc": fetched_at,
                            "series_ticker": series,
                            "event_ticker": event.get("event_ticker"),
                            "event_title": event.get("title"),
                            "market_ticker": m.get("ticker"),
                            "strike_type": m.get("strike_type"),
                            "floor_strike": _f(m.get("floor_strike")),
                            "cap_strike": _f(m.get("cap_strike")),
                            "status": m.get("status"),
                            "yes_bid": _f(m.get("yes_bid_dollars")),
                            "yes_ask": _f(m.get("yes_ask_dollars")),
                            "yes_bid_size": _f(m.get("yes_bid_size_fp")),
                            "yes_ask_size": _f(m.get("yes_ask_size_fp")),
                            "last_price": _f(m.get("last_price_dollars")),
                            "previous_price": _f(m.get("previous_price_dollars")),
                            "volume": _f(m.get("volume_fp")),
                            "volume_24h": _f(m.get("volume_24h_fp")),
                            "open_interest": _f(m.get("open_interest_fp")),
                            "open_time": m.get("open_time"),
                            "close_time": m.get("close_time"),
                            "expected_expiration_time": m.get("expected_expiration_time"),
                            "source_updated_time": m.get("updated_time"),
                        }
                    )
            cursor = body.get("cursor") or ""
            if not cursor:
                break
    return rows


def load_watchlist(path: Path = WATCHLIST) -> list[dict[str, str]]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [
        {"id": str(m["id"]), "group": str(m.get("group", "")), "note": m.get("note", "")}
        for m in payload["markets"]
    ]


def polymarket_rows(
    http: Http, fetched_at: str, watchlist: list[dict[str, str]]
) -> list[dict[str, Any]]:
    wanted = {m["id"]: m for m in watchlist}
    got: dict[str, dict[str, Any]] = {}
    ids = list(wanted)
    for start in range(0, len(ids), 20):
        chunk = ids[start : start + 20]
        body = http.get(f"{GAMMA_BASE}/markets", {"id": chunk, "limit": len(chunk)}) or []
        for market in body:
            got[str(market.get("id"))] = market
    missing = sorted(set(wanted) - set(got))
    if missing:
        raise RuntimeError(f"Gamma API did not return watchlist ids: {','.join(missing)}")
    rows = []
    for market_id in ids:
        m = got[market_id]
        prices = _json_list(m.get("outcomePrices"))
        tokens = _json_list(m.get("clobTokenIds"))
        rows.append(
            {
                "fetched_at_utc": fetched_at,
                "market_id": market_id,
                "slug": m.get("slug"),
                "question": m.get("question"),
                "watch_group": wanted[market_id]["group"],
                "condition_id": m.get("conditionId"),
                "yes_price": _f(prices[0]) if prices else None,
                "best_bid": _f(m.get("bestBid")),
                "best_ask": _f(m.get("bestAsk")),
                "last_trade_price": _f(m.get("lastTradePrice")),
                "spread": _f(m.get("spread")),
                "volume": _f(m.get("volumeNum")),
                "volume_24h": _f(m.get("volume24hr")),
                "liquidity": _f(m.get("liquidityNum")),
                "active": bool(m.get("active")),
                "closed": bool(m.get("closed")),
                "end_date": m.get("endDate"),
                "source_updated_at": m.get("updatedAt"),
                "clob_yes_token_id": tokens[0] if tokens else None,
            }
        )
    return rows


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
        except ValueError:
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _stage(frame: pd.DataFrame, final: Path) -> Path:
    if final.exists():
        raise FileExistsError(f"refusing to overwrite {final}")
    final.parent.mkdir(parents=True, exist_ok=True)
    tmp = final.with_name(f".{final.name}.tmp")
    frame.to_parquet(tmp, index=False)
    return tmp


def collect_snapshot(
    http: Http,
    out_root: Path,
    *,
    now: datetime | None = None,
    watchlist: list[dict[str, str]] | None = None,
    series_list: tuple[str, ...] = KALSHI_SERIES,
) -> dict[str, Any]:
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    fetched_at = moment.isoformat(timespec="seconds")
    wl = watchlist if watchlist is not None else load_watchlist()
    kalshi = kalshi_rows(http, fetched_at, series_list)
    poly = polymarket_rows(http, fetched_at, wl)
    if not kalshi:
        raise RuntimeError("Kalshi returned no open macro markets")
    day = moment.strftime("%Y-%m-%d")
    part = f"part-{moment.strftime('%H%M%S')}.parquet"
    targets = {
        "kalshi": out_root / "kalshi_hourly" / f"date={day}" / part,
        "polymarket": out_root / "polymarket_hourly" / f"date={day}" / part,
    }
    staged: dict[str, Path] = {}
    renamed: list[Path] = []
    try:
        staged["kalshi"] = _stage(pd.DataFrame(kalshi), targets["kalshi"])
        staged["polymarket"] = _stage(pd.DataFrame(poly), targets["polymarket"])
        for key, tmp in staged.items():
            os.replace(tmp, targets[key])
            renamed.append(targets[key])
    except Exception:
        for tmp in staged.values():
            tmp.unlink(missing_ok=True)
        for final in renamed:  # nothing partial: undo an already renamed first file
            final.unlink(missing_ok=True)
        raise
    return {
        "fetched_at_utc": fetched_at,
        "kalshi_rows": len(kalshi),
        "polymarket_rows": len(poly),
        "files": [str(p) for p in targets.values()],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-root", type=Path, default=OUT_ROOT)
    args = parser.parse_args(argv)
    try:
        result = collect_snapshot(Http(), args.out_root)
    except Exception as exc:  # any failure: non-zero, nothing written
        print(f"collect_prediction_markets failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
