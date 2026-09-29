#!/usr/bin/env python3
"""Fetch Wikimedia per-article daily pageviews for current S&P 500 constituents.

T-20260929-71.  Free, key-less.  Steps:

1. Read the wikitext of "List of S&P 500 companies" (MediaWiki API, action=parse)
   and parse ticker -> company article title from the constituents table.
2. Resolve redirects in batches of 50 titles (action=query&redirects=1) so the
   pageviews are counted on the canonical article, not on a redirect page.
3. Fetch ``/metrics/pageviews/per-article/en.wikipedia/all-access/user/<title>/
   daily/<start>/<end>`` once per title (single thread, <= 10 requests/second,
   exponential backoff on 429/5xx), write ``data/wikipedia_pageviews/<TICKER>.parquet``
   with columns ``date`` (UTC day) and ``views``.  Existing parquet -> skipped
   (resume).  A 404 (no views in the range) writes an empty parquet.

Point in time: the UTC-day count for day d is complete only after d ends (20:00 ET
the same evening in summer), so consumers may only use it from the close of d and
trade at the next open.  Survivorship: only *current* constituents are listed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import quote

import polars as pl
import requests

USER_AGENT = "open-composer-research/0.1 (personal research; contact via repo owner)"
WIKI_API = "https://en.wikipedia.org/w/api.php"
PAGEVIEWS_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "en.wikipedia/all-access/user/{title}/daily/{start}/{end}"
)
LIST_PAGE = "List of S&P 500 companies"
DEFAULT_START = "2016-07-01"
DEFAULT_OUT = Path("data/wikipedia_pageviews")
MIN_INTERVAL_S = 0.11  # <= ~9 requests per second, single thread
MAX_RETRIES = 8
BACKOFF_BASE_S = 2.0
BACKOFF_CAP_S = 120.0
REDIRECT_BATCH = 50

SCHEMA = {"date": pl.Date, "views": pl.Int64}


class RateLimitedError(RuntimeError):
    """Raised when the API keeps refusing after all retries."""


class Client:
    """Single-threaded HTTP client with pacing and exponential backoff."""

    def __init__(
        self,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        min_interval: float = MIN_INTERVAL_S,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
        self.sleep = sleep
        self.clock = clock
        self.min_interval = min_interval
        self._last = -1e9
        self.backoff_total_s = 0.0

    def get(self, url: str, params: dict | None = None):
        """GET with pacing; returns the Response for 200 or 404, raises otherwise."""
        for attempt in range(MAX_RETRIES + 1):
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            try:
                resp = self.session.get(url, params=params, timeout=60)
            except requests.RequestException:
                resp = None
            if resp is not None and resp.status_code in (200, 404):
                return resp
            if resp is not None and resp.status_code not in (429, 500, 502, 503, 504):
                raise RuntimeError(f"unexpected HTTP {resp.status_code} for {url}")
            if attempt == MAX_RETRIES:
                break
            delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2**attempt))
            retry_after = resp.headers.get("Retry-After") if resp is not None else None
            if retry_after and retry_after.isdigit():
                delay = max(delay, min(float(retry_after), BACKOFF_CAP_S))
            self.backoff_total_s += delay
            self.sleep(delay)
        raise RateLimitedError(f"gave up after {MAX_RETRIES} retries: {url}")


# --------------------------------------------------------------------------- parsing

_SYMBOL_RE = re.compile(r"\{\{\s*\w*Symbol\s*\|\s*([^}|]+?)\s*(?:\|[^}]*)?\}\}", re.IGNORECASE)
_LINK_RE = re.compile(r"\[\[([^\[\]|]+)(?:\|[^\[\]]*)?\]\]")


def parse_constituents(wikitext: str) -> list[tuple[str, str]]:
    """Return [(ticker, article_title)] from the constituents wikitable."""
    start = wikitext.find('id="constituents"')
    if start < 0:
        raise ValueError("constituents table not found in wikitext")
    end = wikitext.find("\n|}", start)
    table = wikitext[start : end if end > 0 else len(wikitext)]
    rows = re.split(r"\n\|-[^\n]*\n", table)
    out: list[tuple[str, str]] = []
    for row in rows[1:]:
        cells = [c for c in re.split(r"\n?\|\||\n\|", row) if c.strip()]
        if len(cells) < 2:
            continue
        sym = _SYMBOL_RE.search(cells[0])
        link = _LINK_RE.search(cells[1])
        if not sym or not link:
            continue
        ticker = sym.group(1).strip().replace(" ", "")
        title = link.group(1).strip().split("#")[0]
        if ticker and title:
            out.append((ticker, title))
    seen: set[str] = set()
    dedup = []
    for tk, ti in out:
        if tk not in seen:
            seen.add(tk)
            dedup.append((tk, ti))
    return dedup


def parse_pageviews(payload: dict) -> pl.DataFrame:
    """REST payload -> DataFrame(date, views); timestamps are YYYYMMDD00."""
    items = payload.get("items", [])
    if not items:
        return pl.DataFrame(schema=SCHEMA)
    dates = [datetime.strptime(str(it["timestamp"])[:8], "%Y%m%d").date() for it in items]
    views = [int(it["views"]) for it in items]
    return pl.DataFrame({"date": dates, "views": views}, schema=SCHEMA).sort("date")


def resolve_redirects(client: Client, titles: list[str]) -> dict[str, str]:
    """Map each input title to its canonical title (after redirects/normalisation)."""
    mapping = {t: t for t in titles}
    for i in range(0, len(titles), REDIRECT_BATCH):
        batch = titles[i : i + REDIRECT_BATCH]
        params: dict = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "redirects": "1",
            "titles": "|".join(batch),
        }
        hops: dict[str, str] = {}
        redirects: dict[str, str] = {}
        while True:
            payload = client.get(WIKI_API, params=params).json()
            query = payload.get("query", {})
            for item in query.get("normalized", []):
                hops[item["from"]] = item["to"]
            for item in query.get("redirects", []):
                redirects[item["from"]] = item["to"]
            cont = payload.get("continue")
            if not cont:
                break
            params = {**params, **cont}
        for t in batch:
            cur = hops.get(t, t)
            mapping[t] = redirects.get(cur, cur)
    return mapping


# --------------------------------------------------------------------------- fetch


def fetch_wikitext(client: Client) -> str:
    params = {
        "action": "parse",
        "page": LIST_PAGE,
        "prop": "wikitext",
        "format": "json",
        "formatversion": "2",
    }
    return client.get(WIKI_API, params=params).json()["parse"]["wikitext"]


def fetch_title(client: Client, title: str, start: str, end: str) -> pl.DataFrame:
    url = PAGEVIEWS_URL.format(
        title=quote(title.replace(" ", "_"), safe=""),
        start=start.replace("-", "") + "00",
        end=end.replace("-", "") + "00",
    )
    resp = client.get(url)
    if resp.status_code == 404:
        return pl.DataFrame(schema=SCHEMA)
    return parse_pageviews(resp.json())


def run(
    client: Client,
    out_dir: Path,
    start: str = DEFAULT_START,
    end: str | None = None,
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    """Fetch every missing ticker; returns a small summary dict."""
    out_dir.mkdir(parents=True, exist_ok=True)
    end = end or (datetime.now(UTC).date() - timedelta(days=1)).isoformat()
    map_path = out_dir / "_title_map.json"
    if map_path.exists():
        title_map = json.loads(map_path.read_text())
    else:
        pairs = parse_constituents(fetch_wikitext(client))
        canonical = resolve_redirects(client, sorted({t for _, t in pairs}))
        title_map = [
            {"ticker": tk, "list_title": ti, "title": canonical.get(ti, ti)} for tk, ti in pairs
        ]
        map_path.write_text(json.dumps(title_map, indent=1))
        log(f"mapped {len(title_map)} tickers")
    done = fetched = 0
    empty: list[str] = []
    for row in title_map:
        path = out_dir / f"{row['ticker']}.parquet"
        if path.exists():
            done += 1
            continue
        if limit is not None and fetched >= limit:
            break
        frame = fetch_title(client, row["title"], start, end)
        tmp = path.with_suffix(".tmp")
        frame.write_parquet(tmp)
        tmp.replace(path)
        fetched += 1
        if frame.is_empty():
            empty.append(row["ticker"])
        if fetched % 25 == 0:
            log(f"fetched {fetched} (already had {done}), backoff {client.backoff_total_s:.0f}s")
    return {
        "tickers": len(title_map),
        "already_present": done,
        "fetched_now": fetched,
        "empty_404": empty,
        "start": start,
        "end": end,
        "backoff_total_s": client.backoff_total_s,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--start", default=DEFAULT_START)
    ap.add_argument("--end", default=None, help="default: yesterday UTC")
    ap.add_argument("--limit", type=int, default=None, help="max new tickers this call")
    args = ap.parse_args(argv)
    try:
        summary = run(Client(), args.out, args.start, args.end, args.limit)
    except RateLimitedError as exc:
        print(f"RATE LIMITED: {exc}; rerun the same command to resume", file=sys.stderr)
        return 3
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
