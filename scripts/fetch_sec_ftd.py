#!/usr/bin/env python3
"""Fetch the SEC fails-to-deliver (FTD) half-month files (T-20260929-72).

``https://www.sec.gov/files/data/fails-deliver-data/cnsfails<YYYYMM><a|b>.zip``
(``a`` = settlement dates 1st-15th, ``b`` = 16th to month end).  Free, key-less.
The SEC requires a descriptive User-Agent and asks for at most 10 requests/second;
this client is single-threaded, at most 5 requests/second, and backs off
exponentially on 403/429/5xx (the SEC answers "Request Rate Threshold Exceeded" with
HTTP 403).  Existing parquet -> skipped (resume); a 404 (file not published yet) is
recorded and not written.

Each zip holds one pipe-delimited text file::

    SETTLEMENT DATE|CUSIP|SYMBOL|QUANTITY (FAILS)|DESCRIPTION|PRICE
    20260601|000361105|AIR|1234|AAR CORP|85.66
    ...
    Trailer record count|12345          (some files carry a trailer line)

The price is the PREVIOUS day's close, "." (or empty) when unavailable.  Since
2008-09-16 every security with a non-zero balance is listed (the earlier 10,000-share
threshold no longer applies), so an absent symbol means a zero balance.

Point in time (frozen in the preregistration): the SEC publishes a file about 15
days after the period ends, so
  * an ``a`` file (settlement dates 1-15) is first usable on the first trading day
    after the LAST calendar day of that month;
  * a ``b`` file (16-end) is first usable on the first trading day after the 16th of
    the NEXT month (the SEC says "approximately the 15th"; one extra day is left).

Output: ``data/sec_ftd/cnsfails<YYYYMM><a|b>.parquet`` with columns settlement_date,
cusip, symbol, quantity, description, price, plus ``_fetch_log.json`` (404 list).
"""

from __future__ import annotations

import argparse
import calendar
import io
import json
import sys
import time
import zipfile
from collections.abc import Callable, Sequence
from datetime import UTC, date, datetime
from pathlib import Path

import polars as pl
import requests

USER_AGENT = "open-composer-research/0.1 personal research"
URL = "https://www.sec.gov/files/data/fails-deliver-data/cnsfails{ym}{half}.zip"
DEFAULT_OUT = Path("data/sec_ftd")
DEFAULT_START = (2019, 1)
MIN_INTERVAL_S = 0.25  # <= 4 requests per second, single thread
MAX_RETRIES = 8
BACKOFF_BASE_S = 5.0
BACKOFF_CAP_S = 180.0
RETRY_STATUS = (403, 429, 500, 502, 503, 504)

SCHEMA = {
    "settlement_date": pl.Date,
    "cusip": pl.Utf8,
    "symbol": pl.Utf8,
    "quantity": pl.Int64,
    "description": pl.Utf8,
    "price": pl.Float64,
}


class RateLimitedError(RuntimeError):
    """Raised when the SEC keeps refusing after all retries."""


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
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.sleep = sleep
        self.clock = clock
        self.min_interval = min_interval
        self._last = -1e9
        self.backoff_total_s = 0.0

    def get(self, url: str):
        """GET with pacing; returns the Response for 200 or 404, raises otherwise."""
        for attempt in range(MAX_RETRIES + 1):
            wait = self.min_interval - (self.clock() - self._last)
            if wait > 0:
                self.sleep(wait)
            self._last = self.clock()
            try:
                resp = self.session.get(url, timeout=120)
            except requests.RequestException:
                resp = None
            if resp is not None and resp.status_code in (200, 404):
                return resp
            if resp is not None and resp.status_code not in RETRY_STATUS:
                raise RuntimeError(f"unexpected HTTP {resp.status_code} for {url}")
            if attempt == MAX_RETRIES:
                break
            delay = min(BACKOFF_CAP_S, BACKOFF_BASE_S * (2**attempt))
            retry_after = resp.headers.get("Retry-After") if resp is not None else None
            if retry_after and str(retry_after).isdigit():
                delay = max(delay, min(float(retry_after), BACKOFF_CAP_S))
            self.backoff_total_s += delay
            self.sleep(delay)
        raise RateLimitedError(f"gave up after {MAX_RETRIES} retries: {url}")


# ------------------------------------------------------------------- names and PIT


def file_keys(
    start: tuple[int, int] = DEFAULT_START, end: date | None = None
) -> list[tuple[str, str]]:
    """[(YYYYMM, 'a'|'b')] from ``start`` up to the month of ``end`` (default today)."""
    end = end or datetime.now(UTC).date()
    out: list[tuple[str, str]] = []
    y, m = start
    while (y, m) <= (end.year, end.month):
        out.append((f"{y:04d}{m:02d}", "a"))
        out.append((f"{y:04d}{m:02d}", "b"))
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


def file_url(ym: str, half: str) -> str:
    return URL.format(ym=ym, half=half)


def cutoff_date(ym: str, half: str) -> date:
    """Calendar date after which the file's data counts as public (see module doc)."""
    y, m = int(ym[:4]), int(ym[4:])
    if half == "a":
        return date(y, m, calendar.monthrange(y, m)[1])
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    return date(ny, nm, 16)


def available_date(ym: str, half: str, trading_days: Sequence[date]) -> date | None:
    """First trading day strictly after the cutoff; None if past the calendar's end."""
    cut = cutoff_date(ym, half)
    for d in trading_days:  # sorted ascending
        if d > cut:
            return d
    return None


# ------------------------------------------------------------------------ parsing


def parse_ftd_text(text: str) -> tuple[pl.DataFrame, dict[str, int]]:
    """Pipe-delimited FTD text -> (frame, {'rows', 'skipped_lines', 'bad_price'})."""
    rows: list[tuple] = []
    skipped = bad_price = 0
    for i, line in enumerate(text.splitlines()):
        line = line.strip()
        if not line:
            continue
        parts = [p.strip() for p in line.split("|")]
        if i == 0 and not parts[0].isdigit():
            continue  # header
        if len(parts) < 6 or len(parts[0]) != 8 or not parts[0].isdigit():
            skipped += 1  # trailer record count or a malformed line
            continue
        try:
            sd = datetime.strptime(parts[0], "%Y%m%d").date()
            qty = int(parts[3].replace(",", ""))
        except ValueError:
            skipped += 1
            continue
        price: float | None
        try:
            price = float(parts[5])
            if not price > 0:
                price = None
        except ValueError:
            price = None
        if price is None:
            bad_price += 1
        rows.append((sd, parts[1], parts[2], qty, parts[4], price))
    frame = pl.DataFrame(rows, schema=SCHEMA, orient="row")
    return frame, {"rows": len(rows), "skipped_lines": skipped, "bad_price": bad_price}


def parse_zip(content: bytes) -> tuple[pl.DataFrame, dict[str, int]]:
    with zipfile.ZipFile(io.BytesIO(content)) as zf:
        name = zf.namelist()[0]
        text = zf.read(name).decode("latin-1")
    return parse_ftd_text(text)


# -------------------------------------------------------------------------- fetch


def run(
    client: Client,
    out_dir: Path,
    start: tuple[int, int] = DEFAULT_START,
    end: date | None = None,
    limit: int | None = None,
    log: Callable[[str], None] = print,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    keys = file_keys(start, end)
    have = fetched = 0
    missing: list[str] = []
    stats = {"rows": 0, "skipped_lines": 0, "bad_price": 0}
    for ym, half in keys:
        stem = f"cnsfails{ym}{half}"
        path = out_dir / f"{stem}.parquet"
        if path.exists():
            have += 1
            continue
        if limit is not None and fetched >= limit:
            break
        resp = client.get(file_url(ym, half))
        if resp.status_code == 404:
            missing.append(stem)
            continue
        frame, st = parse_zip(resp.content)
        tmp = path.with_suffix(".tmp")
        frame.write_parquet(tmp)
        tmp.replace(path)
        fetched += 1
        for k in stats:
            stats[k] += st[k]
        if fetched % 10 == 0:
            log(f"fetched {fetched} (already had {have}), backoff {client.backoff_total_s:.0f}s")
    summary = {
        "files_expected": len(keys),
        "already_present": have,
        "fetched_now": fetched,
        "not_published_404": missing,
        "parsed_now": stats,
        "backoff_total_s": client.backoff_total_s,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    (out_dir / "_fetch_log.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--start", default="2019-01", help="YYYY-MM")
    ap.add_argument("--end", default=None, help="YYYY-MM-DD, default today UTC")
    ap.add_argument("--limit", type=int, default=None, help="max new files this call")
    args = ap.parse_args(argv)
    sy, sm = (int(x) for x in args.start.split("-"))
    end = date.fromisoformat(args.end) if args.end else None
    try:
        summary = run(Client(), args.out, (sy, sm), end, args.limit)
    except RateLimitedError as exc:
        print(f"RATE LIMITED: {exc}; rerun the same command to resume", file=sys.stderr)
        return 3
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
