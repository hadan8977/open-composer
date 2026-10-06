"""T-20260929-60: resumable fetcher for the DoltHub ``post-no-preference/options`` database.

Source: https://www.dolthub.com/repositories/post-no-preference/options (free, no key).
Tables: ``option_chain`` (date, act_symbol, expiration, strike, call_put, bid, ask, vol,
delta, gamma, theta, vega, rho) and ``volatility_history`` (date, act_symbol, hv_current,
iv_current, ...).

Access: the public SQL API
``https://www.dolthub.com/api/v1alpha1/post-no-preference/options?q=<SQL>`` -- one row cap of
1,000 per query, so every query is paged with ``ORDER BY ... LIMIT 1000 OFFSET n``. One thread,
exponential backoff on 429/5xx/timeouts, a checkpoint every ``--checkpoint-every`` requests
(default 200) and on exit. Observed 2026-09-29: latency per query swings between 0.3 s and 57 s
(even ``SELECT 1``), so the design is built for few, large, resumable requests.

Why the queries look the way they do: ``option_chain`` has a (date, act_symbol, ...) primary
key, so ``date IN (...) AND act_symbol IN (...)`` is a cheap prefix lookup, while a symbol
filter over a date range scans every symbol and returns HTTP 504. Every job therefore
enumerates dates (US session calendar) instead of filtering a range.

Jobs (``--jobs``, comma separated, run in this order):

``agg``
    ``--agg-batch-dates`` dates per request, ONE aggregate row per (date, symbol) computed
    server side (row count, expiries, strikes, null/crossed/zero-bid/negative quote counts,
    overall and inside the 0.10<=|delta|<=0.90 band). Exact trading-day coverage, contract
    counts and quote hygiene without downloading chains.
    -> ``data/dolthub_options/agg/agg_{first_date}_{n}d.parquet``.
``chain``
    Full chains of all ``--symbols`` for ONE date per request, dates taken from ``agg`` in a
    seeded shuffle, so any truncation is a uniform random sample of the available days.
    -> ``data/dolthub_options/option_chain/part_*.parquet``.
``volhist``
    ``volatility_history`` in ``--volhist-window-days`` windows (symbol-restricted, or the
    whole table with ``--volhist-all``; about 1,540 rows per day).
    -> ``data/dolthub_options/volatility_history/*.parquet``.

Resume: rerun the same command; finished units are read from
``data/dolthub_options/checkpoint.json`` and skipped.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "dolthub_options"
API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
PAGE_LIMIT = 1000
USER_AGENT = "open-composer-research/1.0 (personal research; single thread)"
DEFAULT_SYMBOLS = ("SPY", "QQQ", "AAPL", "NVDA", "TSLA")
EXTRA_SYMBOLS = ("IWM", "SMH", "TQQQ", "MSFT", "AMZN", "GOOGL", "META")
DATA_START = date(2019, 2, 1)
_SYM = re.compile(r"^[A-Z0-9.\-]{1,10}$")

CHAIN_COLUMNS = (
    "date, act_symbol, expiration, strike, call_put, bid, ask, vol, delta, gamma, theta, vega, rho"
)
VOLHIST_COLUMNS = (
    "date, act_symbol, hv_current, hv_week_ago, hv_month_ago, "
    "iv_current, iv_week_ago, iv_month_ago, iv_year_high, iv_year_low"
)


def _transient_error(body: str) -> bool:
    """DoltHub reports upstream 5xx/timeouts as HTTP 400 with an explanatory message."""
    lowered = body.lower()
    return any(k in lowered for k in ("status code 5", "timed out", "timeout", "deadline"))


class ApiError(RuntimeError):
    """The API answered with a non-retryable error."""


@dataclass
class Client:
    """Single-threaded SQL-API client with exponential backoff and request accounting."""

    max_retries: int = 8
    base_delay: float = 5.0
    max_delay: float = 300.0
    timeout: float = 240.0
    min_interval: float = 0.0
    opener: Callable[[str, float], tuple[int, str]] | None = None
    sleep: Callable[[float], None] = time.sleep
    log: Callable[[str], None] = field(default=lambda m: print(m, flush=True))
    requests_made: int = 0
    retries: int = 0
    last_request_at: float = 0.0
    latencies: list[float] = field(default_factory=list)
    statuses: dict[str, int] = field(default_factory=dict)
    on_request: Callable[[], None] | None = None

    def _http_get(self, url: str) -> tuple[int, str]:
        if self.opener is not None:
            return self.opener(url, self.timeout)
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8", errors="replace")

    def query(self, sql: str) -> list[dict[str, str]]:
        """Run one SQL statement; return its rows. Retries 429/5xx/timeouts with backoff."""
        url = API + "?" + urllib.parse.urlencode({"q": sql})
        delay = self.base_delay
        for attempt in range(self.max_retries + 1):
            wait = self.min_interval - (time.monotonic() - self.last_request_at)
            if wait > 0:
                self.sleep(wait)
            started = time.monotonic()
            self.last_request_at = started
            self.requests_made += 1
            try:
                status, body = self._http_get(url)
            except (TimeoutError, urllib.error.URLError, OSError) as exc:
                status, body = 0, f"transport error: {exc!r}"
            self.latencies.append(time.monotonic() - started)
            self.statuses[str(status)] = self.statuses.get(str(status), 0) + 1
            if self.on_request is not None:
                self.on_request()
            if status == 200:
                try:
                    payload = json.loads(body)
                except ValueError:
                    payload = None
                if isinstance(payload, dict):
                    if payload.get("query_execution_status") == "Success":
                        rows = payload.get("rows") or []
                        return [{k: v for k, v in row.items()} for row in rows]
                    message = str(payload.get("query_execution_message") or "")
                    if not _transient_error(message) and (
                        "syntax" in message.lower() or "unknown" in message.lower()
                    ):
                        raise ApiError(message[:300])
                    self.log(f"non-success: {message[:120]}")
                    # Otherwise (timeout, busy, "Running") treat as retryable.
                    status = 599
            elif 400 <= status < 500 and status != 429 and not _transient_error(body):
                raise ApiError(f"HTTP {status}: {body[:300]}")
            if attempt == self.max_retries:
                raise ApiError(f"gave up after {attempt + 1} attempts, last status {status}")
            self.retries += 1
            self.log(f"retry {attempt + 1} status={status} sleep={delay:.0f}s")
            self.sleep(delay)
            delay = min(delay * 2, self.max_delay)
        raise ApiError("unreachable")  # pragma: no cover

    def paged(self, base_sql: str, order_by: str) -> list[dict[str, str]]:
        """Page ``base_sql ORDER BY order_by`` in blocks of 1,000 rows until a short page."""
        rows: list[dict[str, str]] = []
        offset = 0
        while True:
            page = self.query(f"{base_sql} ORDER BY {order_by} LIMIT {PAGE_LIMIT} OFFSET {offset}")
            rows.extend(page)
            if len(page) < PAGE_LIMIT:
                return rows
            offset += PAGE_LIMIT


# --------------------------------------------------------------------------- checkpoint


@dataclass
class Checkpoint:
    """Finished-unit ledger, flushed every ``every`` requests and on exit."""

    path: Path
    every: int = 200
    done: dict[str, list[str]] = field(default_factory=dict)
    request_count: int = 0
    since_flush: int = 0
    stats: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path, every: int = 200) -> Checkpoint:
        cp = cls(path=path, every=every)
        if path.is_file():
            payload = json.loads(path.read_text())
            cp.done = {k: list(v) for k, v in payload.get("done", {}).items()}
            cp.request_count = int(payload.get("request_count", 0))
            cp.stats = dict(payload.get("stats", {}))
        return cp

    def is_done(self, job: str, unit: str) -> bool:
        return unit in self._set(job)

    def _set(self, job: str) -> set[str]:
        cache = getattr(self, "_cache", None)
        if cache is None:
            cache = self._cache = {}
        if job not in cache:
            cache[job] = set(self.done.get(job, []))
        return cache[job]

    def mark(self, job: str, unit: str) -> None:
        self._set(job).add(unit)

    def tick(self) -> bool:
        """Count one request; True when a periodic flush is due."""
        self.request_count += 1
        self.since_flush += 1
        return self.since_flush >= self.every

    def flush(self) -> None:
        cache = getattr(self, "_cache", {})
        self.done = {job: sorted(units) for job, units in cache.items()} | {
            job: units for job, units in self.done.items() if job not in cache
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "written_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "request_count": self.request_count,
                    "stats": self.stats,
                    "done": self.done,
                },
                indent=1,
            )
        )
        tmp.replace(self.path)
        self.since_flush = 0


# --------------------------------------------------------------------------- helpers


def check_symbol(symbol: str) -> str:
    if not _SYM.match(symbol):
        raise ValueError(f"bad symbol {symbol!r}")
    return symbol


def sql_dates(days: Iterable[str]) -> str:
    """Quoted, validated ISO-date list for an IN clause."""
    out = [f"'{date.fromisoformat(d).isoformat()}'" for d in days]
    if not out:
        raise ValueError("no dates")
    return ", ".join(out)


def sql_symbols(symbols: Iterable[str]) -> str:
    return ", ".join(f"'{check_symbol(s)}'" for s in symbols)


def agg_sql(symbols: Iterable[str], days: Iterable[str]) -> str:
    """Per (date, symbol) aggregate for a list of dates, computed server side.

    ``date IN (...)`` uses the (date, act_symbol, ...) primary-key prefix, so it is cheap; a
    plain symbol filter over a date range scans every symbol's rows and returns HTTP 504.
    """
    band = "ABS(delta) BETWEEN 0.10 AND 0.90"
    return (
        "SELECT date, act_symbol, COUNT(*) n_rows, COUNT(DISTINCT expiration) n_exp, "
        "COUNT(DISTINCT strike) n_strikes, MIN(expiration) min_exp, MAX(expiration) max_exp, "
        "SUM(CASE WHEN bid IS NULL OR ask IS NULL THEN 1 ELSE 0 END) n_null, "
        "SUM(CASE WHEN bid < 0 THEN 1 ELSE 0 END) n_neg_bid, "
        "SUM(CASE WHEN ask <= 0 THEN 1 ELSE 0 END) n_nonpos_ask, "
        "SUM(CASE WHEN ask < bid THEN 1 ELSE 0 END) n_crossed, "
        "SUM(CASE WHEN bid = 0 THEN 1 ELSE 0 END) n_zero_bid, "
        f"SUM(CASE WHEN {band} THEN 1 ELSE 0 END) n_band, "
        f"SUM(CASE WHEN {band} AND (bid IS NULL OR ask IS NULL) THEN 1 ELSE 0 END) n_band_null, "
        f"SUM(CASE WHEN {band} AND bid < 0 THEN 1 ELSE 0 END) n_band_neg_bid, "
        f"SUM(CASE WHEN {band} AND ask <= 0 THEN 1 ELSE 0 END) n_band_nonpos_ask, "
        f"SUM(CASE WHEN {band} AND ask < bid THEN 1 ELSE 0 END) n_band_crossed, "
        f"SUM(CASE WHEN {band} AND bid = 0 AND ask > 0 THEN 1 ELSE 0 END) n_band_zero_bid, "
        "SUM(CASE WHEN vol IS NULL OR vol <= 0 THEN 1 ELSE 0 END) n_vol_missing "
        f"FROM option_chain WHERE date IN ({sql_dates(days)}) "
        f"AND act_symbol IN ({sql_symbols(symbols)}) GROUP BY date, act_symbol"
    )


def chain_sql(symbols: Iterable[str], day: str) -> str:
    """Full chains of several symbols for ONE date (primary-key prefix lookup)."""
    return (
        f"SELECT {CHAIN_COLUMNS} FROM option_chain "
        f"WHERE date = {sql_dates([day])} AND act_symbol IN ({sql_symbols(symbols)})"
    )


CHAIN_ORDER = "act_symbol, expiration, strike, call_put"


def volhist_sql(lo: date, hi: date, symbols: Iterable[str] | None) -> str:
    where = f"date >= '{lo.isoformat()}' AND date < '{hi.isoformat()}'"
    if symbols:
        quoted = ", ".join(f"'{check_symbol(s)}'" for s in symbols)
        where += f" AND act_symbol IN ({quoted})"
    return f"SELECT {VOLHIST_COLUMNS} FROM volatility_history WHERE {where}"


VOLHIST_ORDER = "date, act_symbol"


def shuffled_days(symbol: str, days: list[str], seed: int = 20260929) -> list[str]:
    """Deterministic seeded shuffle so any prefix is a uniform random sample of days."""
    rng = random.Random(f"{seed}:{symbol}")
    out = sorted(days)
    rng.shuffle(out)
    return out


def interleave(streams: list[list[tuple[str, str]]]) -> Iterable[tuple[str, str]]:
    """Round-robin over per-symbol (symbol, day) streams."""
    longest = max((len(s) for s in streams), default=0)
    for i in range(longest):
        for stream in streams:
            if i < len(stream):
                yield stream[i]


def to_frame(rows: list[dict[str, str]], numeric: Iterable[str]) -> Any:
    import pandas as pd

    frame = pd.DataFrame(rows)
    for column in numeric:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    return frame


CHAIN_NUMERIC = ("strike", "bid", "ask", "vol", "delta", "gamma", "theta", "vega", "rho")
VOLHIST_NUMERIC = (
    "hv_current",
    "hv_week_ago",
    "hv_month_ago",
    "iv_current",
    "iv_week_ago",
    "iv_month_ago",
    "iv_year_high",
    "iv_year_low",
)


# --------------------------------------------------------------------------- jobs


@dataclass
class Runner:
    client: Client
    cp: Checkpoint
    cache: Path
    deadline: float | None = None
    stop: bool = False

    def out_of_time(self) -> bool:
        return self.stop or (self.deadline is not None and time.monotonic() >= self.deadline)

    def job_agg(self, symbols: list[str], days: list[str], batch_dates: int) -> None:
        """Server-side per-(date, symbol) aggregates, ``batch_dates`` dates per request."""
        import pandas as pd

        out = self.cache / "agg"
        out.mkdir(parents=True, exist_ok=True)
        tag = "-".join(symbols)
        for i in range(0, len(days), batch_dates):
            batch = days[i : i + batch_dates]
            unit = f"{tag}:{batch[0]}"
            if self.cp.is_done("agg", unit):
                continue
            if self.out_of_time():
                return
            rows = self.client.paged(agg_sql(symbols, batch), "date, act_symbol")
            frame = pd.DataFrame(rows)
            for column in frame.columns:
                if column not in ("date", "act_symbol", "min_exp", "max_exp"):
                    frame[column] = pd.to_numeric(frame[column], errors="coerce")
            frame.to_parquet(out / f"agg_{batch[0]}_{len(batch)}d.parquet", index=False)
            self.cp.mark("agg", unit)
            self.cp.stats[f"agg_rows:{unit}"] = len(frame)
            self.cp.flush()  # few, slow requests: flush per unit
            self.client.log(f"agg {unit}: {len(batch)} dates -> {len(frame)} symbol-days")

    def known_days(self) -> list[str]:
        """Dates on which at least one symbol had chain rows, from the agg cache."""
        import pandas as pd

        days: set[str] = set()
        for path in sorted((self.cache / "agg").glob("agg_*.parquet")):
            frame = pd.read_parquet(path)  # an all-empty batch has no columns at all
            if "date" in frame.columns:
                days.update(frame["date"].astype(str).tolist())
        return sorted(days)

    def job_chain(
        self,
        symbols: list[str],
        max_units: int | None,
        flush_units: int,
        only_dates: list[str] | None = None,
    ) -> None:
        """Full chains, one date per request (all symbols), seeded-shuffle date order."""
        import pandas as pd

        tag = "-".join(symbols)
        order = only_dates if only_dates else shuffled_days(tag, self.known_days())
        frames: list[Any] = []
        pending: list[str] = []
        fetched = 0

        def write_shard() -> None:
            if frames:
                folder = self.cache / "option_chain"
                folder.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
                pd.concat(frames, ignore_index=True).to_parquet(
                    folder / f"part_{stamp}.parquet", index=False
                )
                frames.clear()
            for day in pending:
                self.cp.mark("chain", f"{tag}:{day}")
            pending.clear()
            self.cp.flush()

        try:
            for day in order:
                if self.cp.is_done("chain", f"{tag}:{day}"):
                    continue
                if self.out_of_time() or (max_units is not None and fetched >= max_units):
                    break
                rows = self.client.paged(chain_sql(symbols, day), CHAIN_ORDER)
                fetched += 1
                if rows:
                    frames.append(to_frame(rows, CHAIN_NUMERIC))
                pending.append(day)
                if len(pending) >= flush_units:
                    write_shard()
                    self.client.log(f"chain: {fetched} dates this run, {self.cp.request_count} req")
        finally:
            write_shard()

    def job_volhist(
        self,
        symbols: list[str] | None,
        start: date,
        end: date,
        window_days: int,
        weekdays_only: bool = False,
        workers: int = 1,
        newest_first: bool = False,
    ) -> None:
        """Pull ``volatility_history`` in day windows; ``workers`` > 1 runs windows concurrently."""
        out = self.cache / "volatility_history"
        out.mkdir(parents=True, exist_ok=True)
        tag = "all" if not symbols else "-".join(symbols)
        skip_weekends = weekdays_only and window_days == 1
        windows: list[tuple[date, date]] = []
        lo = start
        while lo <= end:
            hi = min(lo + timedelta(days=window_days), end + timedelta(days=1))
            if not (skip_weekends and lo.weekday() >= 5):
                windows.append((lo, hi))
            lo = hi
        windows = [
            w for w in windows if not self.cp.is_done("volhist", f"{tag}:{w[0].isoformat()}")
        ]
        if newest_first:
            windows.reverse()

        def record(lo: date, rows: list[dict[str, str]]) -> None:
            unit = f"{tag}:{lo.isoformat()}"
            frame = to_frame(rows, VOLHIST_NUMERIC)
            frame.to_parquet(out / f"{tag}_{lo.isoformat()}.parquet", index=False)
            self.cp.mark("volhist", unit)
            self.cp.stats[f"volhist_rows:{unit}"] = len(frame)
            self.cp.flush()
            self.client.log(f"volhist {unit}: {len(frame)} rows")

        if workers <= 1:
            for lo, hi in windows:
                if self.out_of_time():
                    return
                record(lo, self.client.paged(volhist_sql(lo, hi, symbols), VOLHIST_ORDER))
            return

        from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

        template = self.client

        def fetch(lo: date, hi: date) -> tuple[date, list[dict[str, str]], Client]:
            worker = Client(
                max_retries=template.max_retries,
                base_delay=template.base_delay,
                max_delay=template.max_delay,
                timeout=template.timeout,
                min_interval=template.min_interval,
                opener=template.opener,
                sleep=template.sleep,
                log=template.log,
            )
            return lo, worker.paged(volhist_sql(lo, hi, symbols), VOLHIST_ORDER), worker

        def absorb(done_futures: set) -> None:
            for fut in done_futures:
                lo, rows, worker = fut.result()
                self.cp.request_count += worker.requests_made
                template.requests_made += worker.requests_made
                template.retries += worker.retries
                template.latencies.extend(worker.latencies)
                for k, v in worker.statuses.items():
                    template.statuses[k] = template.statuses.get(k, 0) + v
                record(lo, rows)

        pending: set = set()
        with ThreadPoolExecutor(max_workers=workers) as pool:
            try:
                for lo, hi in windows:
                    if self.out_of_time():
                        break
                    while len(pending) >= workers:
                        finished, pending = wait(pending, return_when=FIRST_COMPLETED)
                        absorb(finished)
                    pending.add(pool.submit(fetch, lo, hi))
            finally:
                if pending:
                    finished, _ = wait(pending)
                    absorb(finished)


def session_days(start: date, end: date) -> list[str]:
    """US equity session dates (calendar only, no market data is read)."""
    sys.path.insert(0, str(ROOT))
    from open_composer.market_calendar import us_equity_session_dates

    return [d.isoformat() for d in us_equity_session_dates(start, end)]


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--jobs", default="agg,chain,volhist")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--start", default=DATA_START.isoformat())
    p.add_argument("--end", default=date.today().isoformat())
    p.add_argument("--cache", default=str(CACHE))
    p.add_argument("--checkpoint-every", type=int, default=200)
    p.add_argument("--chain-flush-units", type=int, default=200)
    p.add_argument("--max-chain-units", type=int, default=None)
    p.add_argument(
        "--chain-dates", default="", help="comma list of ISO dates to fetch first-class (chain job)"
    )
    p.add_argument("--volhist-all", action="store_true")
    p.add_argument("--volhist-window-days", type=int, default=60)
    p.add_argument("--workers", type=int, default=1, help="volhist: concurrent day windows")
    p.add_argument("--newest-first", action="store_true", help="volhist: latest windows first")
    p.add_argument(
        "--weekdays-only",
        action="store_true",
        help="volhist: skip Saturday/Sunday day-cells (only with --volhist-window-days 1)",
    )
    p.add_argument("--agg-batch-dates", type=int, default=60)
    p.add_argument("--max-minutes", type=float, default=None)
    p.add_argument("--min-interval", type=float, default=0.0)
    p.add_argument("--timeout", type=float, default=240.0)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cache = Path(args.cache)
    symbols = [check_symbol(s.strip().upper()) for s in args.symbols.split(",") if s.strip()]
    start, end = date.fromisoformat(args.start), date.fromisoformat(args.end)
    cp = Checkpoint.load(cache / "checkpoint.json", every=args.checkpoint_every)
    client = Client(min_interval=args.min_interval, timeout=args.timeout)
    client.on_request = lambda: cp.flush() if cp.tick() else None
    runner = Runner(
        client,
        cp,
        cache,
        deadline=time.monotonic() + args.max_minutes * 60 if args.max_minutes else None,
    )

    def handle(signum: int, _frame: Any) -> None:
        runner.stop = True  # flag only: no I/O inside a signal handler

    signal.signal(signal.SIGTERM, handle)
    signal.signal(signal.SIGINT, handle)
    jobs = [j.strip() for j in args.jobs.split(",") if j.strip()]
    try:
        if "agg" in jobs:
            runner.job_agg(symbols, session_days(start, end), args.agg_batch_dates)
        if "chain" in jobs:
            only = [d.strip() for d in args.chain_dates.split(",") if d.strip()]
            runner.job_chain(symbols, args.max_chain_units, args.chain_flush_units, only or None)
        if "volhist" in jobs:
            vh_symbols = None if args.volhist_all else symbols
            runner.job_volhist(
                vh_symbols,
                start,
                end,
                args.volhist_window_days,
                args.weekdays_only,
                args.workers,
                args.newest_first,
            )
    finally:
        lat = sorted(client.latencies)
        if lat:
            cp.stats["latency_s"] = {
                "n": len(lat),
                "median": round(lat[len(lat) // 2], 2),
                "p90": round(lat[int(len(lat) * 0.9)], 2),
                "max": round(lat[-1], 2),
            }
        cp.stats["statuses_last_run"] = client.statuses
        cp.stats["retries_last_run"] = client.retries
        cp.flush()
        print(
            f"exit: requests_this_run={client.requests_made} retries={client.retries} "
            f"statuses={client.statuses} total_requests={cp.request_count}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
