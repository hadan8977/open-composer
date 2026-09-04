"""Incremental daily/minute updater for the local SIP parquet archive.

Why not just resume ``fetch_sip_universe.py``: that fetcher's shard N means
"symbols[N*BATCH_SIZE:(N+1)*BATCH_SIZE] of the CURRENT sorted active universe",
so shard identity is bound to (batch size, universe order, universe size) at
fetch time. The archive under ``data/sip/`` was written at ``BATCH_SIZE=40``
for the ten-year daily backfill and a mix of 40/12 for minute; today's
``BATCH_SIZE`` is 12; and the ACTIVE universe changes size and order every
day as symbols list and delist. ``assert_resumable_layout`` correctly refuses
to resume into that mismatch -- a resume under a different (batch_size,
universe_size) pair would silently skip or duplicate symbols. That refusal is
right, not a bug to route around: see
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 3.3.

The fix decouples shard identity from the live universe entirely: the first
run of this script freezes each shard's actual member symbols (read from the
shard's own parquet content, not re-derived from a sort) into
``_LAYOUT.json``'s ``shard_symbols`` map. From then on, "shard N" always means
that frozen symbol list, forever, independent of batch size or how the
universe reorders. Updating a shard means re-fetching a small trailing window
for its frozen symbols and merging, not re-slicing the universe. Symbols that
list after the freeze get appended as brand new shard numbers; delisted
symbols simply stop returning new rows and stay in their shard's frozen list
(the API returns nothing for them, which is not an error).

This script only ever touches the CURRENT window: the current calendar year
for daily, the current calendar month for minute (plus the previous month
during the first three days of a new month, so a month-end trading session
that lands after the freeze still gets topped up). ``data/sip-hist/`` (the
2016-2022 minute backfill) and every year/month before the current window are
untouched -- they are frozen historical archive, not a live tail.

Concurrency: refuses to run while ``fetch_sip_universe.py`` is active (that
script's resumable-layout guard is not designed to run concurrently with a
second writer touching the same shard files), and takes an exclusive lock
file per archive root so two invocations of this script cannot overlap
either. The loader (``open_composer/adapters/data/sip_parquet.py``) is
unmodified: it already discovers shards by glob and prunes by the parquet
footer's symbol min/max, so new shards and updated shards are picked up with
no loader change, and de-duplicates overlapping rows on its own.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import logging
import os
import subprocess
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_sip_universe import (  # noqa: E402
    BATCH_SIZE,
    _clients,
    _fetch_batch,
    layout_path,
    load_universe,
    shard_path,
)

from open_composer.market_calendar import us_equity_session_dates  # noqa: E402

LOG = logging.getLogger("update_sip_archive")
DEFAULT_OUT = Path("data/sip")
BAR_ROW_COLUMNS = (
    "symbol",
    "timestamp",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "trade_count",
    "vwap",
)
#: Trailing sessions re-requested even when a shard already has data through
#: yesterday, so a late SIP correction (auction print revised, split applied
#: after the fact) overwrites rather than sits stale forever.
REFETCH_LOOKBACK_SESSIONS = 2


class UpdateLockedError(RuntimeError):
    """Raised when a concurrent updater or the initial bulk fetch is active."""


def _lock_path(out: Path) -> Path:
    return out / "_update_sip_archive.lock"


@contextlib.contextmanager
def _exclusive_lock(out: Path):
    """A simple O_CREAT|O_EXCL lock file; refuses rather than waits.

    This intentionally does not detect or clear a stale lock automatically --
    a leftover lock from a crashed run should be loud (the next scheduled run
    fails and says why) rather than silently cleared, which is exactly the
    "fail closed, not silent" convention ``check_sip_freshness.py`` already
    uses for this archive.
    """
    lock_path = _lock_path(out)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise UpdateLockedError(
            f"{lock_path} already exists -- another update_sip_archive.py run is active "
            "or a previous run crashed without cleaning up. Confirm no process is running "
            "(pgrep -f update_sip_archive.py) and remove the lock file by hand before retrying."
        ) from exc
    try:
        os.write(fd, f"{os.getpid()} {datetime.now(UTC).isoformat()}\n".encode())
        os.close(fd)
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _refuse_if_bulk_fetch_active() -> None:
    """Refuse to run while the 2016-2022 backfill (or any bulk fetch) is active.

    That fetcher writes shards under its own (batch_size, universe_size)
    layout and does not expect a second writer touching the same directory
    tree concurrently. ``data/sip-hist/`` is a separate root from
    ``data/sip/`` so there is no file collision, but sharing the API rate
    budget and this box's 3.8GB while both are large parquet operations is
    exactly the kind of resource contention the plan's discipline (never run
    a second fetch process) exists to avoid.
    """
    try:
        result = subprocess.run(
            ["pgrep", "-f", "fetch_sip_universe.py"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateLockedError(f"could not check for an active bulk fetch: {exc}") from exc
    pids = [pid for pid in result.stdout.split() if pid.strip()]
    if pids:
        raise UpdateLockedError(
            f"fetch_sip_universe.py is active (pid(s) {', '.join(pids)}); "
            "update_sip_archive.py must wait for it to finish"
        )


def _atomic_write_parquet(frame: pd.DataFrame, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    tmp = destination.with_suffix(destination.suffix + f".tmp{os.getpid()}")
    frame.to_parquet(tmp, compression="zstd", index=False)
    os.replace(tmp, destination)


def _read_shard_frame(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=list(BAR_ROW_COLUMNS))
    frame = pq.read_table(path).to_pandas()
    if "timestamp" in frame.columns:
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame


def _merge_and_write(existing: pd.DataFrame, fetched: pd.DataFrame, destination: Path) -> int:
    """Merge freshly fetched rows into ``existing`` and write atomically.

    ``keep="last"`` means the newly fetched row wins on any (symbol,
    timestamp) collision -- a late SIP correction overwrites the stale value
    instead of the archive freezing on the first print it ever saw.
    """
    fetched = fetched.copy()
    fetched["timestamp"] = pd.to_datetime(fetched["timestamp"], utc=True)
    fetched["symbol"] = fetched["symbol"].astype("string").str.upper()
    if existing.empty:
        combined = fetched
    else:
        existing = existing.copy()
        existing["symbol"] = existing["symbol"].astype("string").str.upper()
        combined = pd.concat([existing, fetched], ignore_index=True)
    combined = combined.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    combined = combined.sort_values(["symbol", "timestamp"], kind="stable").reset_index(drop=True)
    _atomic_write_parquet(combined, destination)
    return len(fetched)


def _sessions_back(reference: date, *, sessions: int) -> date:
    """The date ``sessions`` US equity trading sessions before ``reference``."""
    window_start = reference - timedelta(days=30)
    trading_days = [d for d in us_equity_session_dates(window_start, reference) if d <= reference]
    if len(trading_days) > sessions:
        return trading_days[-(sessions + 1)]
    return trading_days[0] if trading_days else reference - timedelta(days=sessions * 2)


def refetch_window_start(max_ts: pd.Timestamp | None, *, full_window_start: datetime) -> datetime:
    """Start of the re-fetch window for one shard.

    A brand new shard (no existing rows) gets the full current window from
    its start. An existing shard gets re-fetched from
    ``REFETCH_LOOKBACK_SESSIONS`` trading sessions before its own latest bar,
    so late corrections near the tape's edge are caught without re-pulling
    the whole window every day.
    """
    if max_ts is None or pd.isna(max_ts):
        return full_window_start
    anchor = _sessions_back(max_ts.date(), sessions=REFETCH_LOOKBACK_SESSIONS)
    candidate = datetime(anchor.year, anchor.month, anchor.day, tzinfo=UTC)
    return max(candidate, full_window_start)


def current_window_dirs(kind: str, now: datetime) -> list[tuple[int, int | None]]:
    """(year, month) pairs this script is allowed to touch -- never history."""
    if kind == "daily":
        return [(now.year, None)]
    windows = {(now.year, now.month)}
    if now.day <= 3:
        previous_end = now.replace(day=1) - timedelta(days=1)
        windows.add((previous_end.year, previous_end.month))
    return sorted(windows)


def window_full_start(kind: str, year: int, month: int | None) -> datetime:
    if kind == "daily":
        return datetime(year, 1, 1, tzinfo=UTC)
    assert month is not None
    return datetime(year, month, 1, tzinfo=UTC)


def load_layout(out: Path, kind: str) -> dict:
    path = layout_path(out, kind)
    if not path.exists():
        raise SystemExit(
            f"{path} is missing; this archive was not written by fetch_sip_universe.py "
            "(or its layout file was deleted). Run the initial backfill first."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def save_layout(out: Path, kind: str, layout: dict) -> None:
    path = layout_path(out, kind)
    path.write_text(json.dumps(layout, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def freeze_shard_symbols(
    out: Path, kind: str, layout: dict, *, now: datetime
) -> dict[int, list[str]]:
    """Return (and persist, on first call) each shard's frozen symbol list.

    Reads every shard in the CURRENT window only (see module docstring), from
    the shard's own parquet ``symbol`` column -- not re-derived from a fresh
    universe sort, which is exactly the coupling this script exists to break.
    Idempotent: once ``shard_symbols`` exists in ``_LAYOUT.json`` it is
    returned as-is and never silently rebuilt (a silent rebuild after new
    listings had already been appended under a later index would let a
    symbol collide with two shards).
    """
    existing = layout.get("shard_symbols")
    if isinstance(existing, dict) and existing:
        return {int(key): list(value) for key, value in existing.items()}
    shard_symbols: dict[int, list[str]] = {}
    for year, month in current_window_dirs(kind, now):
        directory = (
            out / kind / str(year) if month is None else out / kind / str(year) / f"{month:02d}"
        )
        if not directory.is_dir():
            continue
        for shard_file in sorted(directory.glob("shard-*.parquet")):
            shard_index = int(shard_file.stem.split("-")[1])
            if shard_index in shard_symbols:
                continue
            table = pq.read_table(shard_file, columns=["symbol"])
            symbols = sorted({str(value).upper() for value in table.column("symbol").to_pylist()})
            if symbols:
                shard_symbols[shard_index] = symbols
    layout["shard_symbols"] = {
        f"{index:04d}": symbols for index, symbols in sorted(shard_symbols.items())
    }
    save_layout(out, kind, layout)
    LOG.info(
        "%s: froze %d shard(s) of symbol membership into %s",
        kind,
        len(shard_symbols),
        layout_path(out, kind),
    )
    return shard_symbols


def update_existing_shards(
    data_client,
    out: Path,
    kind: str,
    shard_symbols: dict[int, list[str]],
    *,
    now: datetime,
) -> int:
    """Top up every frozen shard for every (year, month) in the current window."""
    total_rows = 0
    for year, month in current_window_dirs(kind, now):
        full_start = window_full_start(kind, year, month)
        for shard_index, symbols in sorted(shard_symbols.items()):
            destination = shard_path(out, kind, year, shard_index, month)
            existing = _read_shard_frame(destination)
            max_ts = (
                existing["timestamp"].max()
                if "timestamp" in existing.columns and not existing.empty
                else None
            )
            window_start = refetch_window_start(max_ts, full_window_start=full_start)
            frame = _fetch_batch(data_client, symbols, window_start, now, kind)
            if frame is None or frame.empty:
                continue
            rows = _merge_and_write(existing, frame.reset_index(), destination)
            total_rows += rows
        LOG.info(
            "%s %04d%s: updated %d frozen shard(s)",
            kind,
            year,
            f"-{month:02d}" if month else "",
            len(shard_symbols),
        )
    return total_rows


def append_new_symbols(
    data_client,
    out: Path,
    kind: str,
    layout: dict,
    shard_symbols: dict[int, list[str]],
    active_symbols: list[str],
    *,
    now: datetime,
) -> int:
    """Fetch and append shards for symbols not in any frozen shard yet.

    New shard numbers start at ``max(existing) + 1`` and only ever grow --
    a delisted-then-relisted symbol is treated as new rather than reusing an
    old index, since reuse is exactly the kind of guess
    ``assert_resumable_layout`` was written to refuse.
    """
    known: set[str] = set()
    for symbols in shard_symbols.values():
        known.update(symbols)
    new_symbols = sorted(symbol for symbol in active_symbols if symbol not in known)
    if not new_symbols:
        return 0
    next_index = max(shard_symbols) + 1 if shard_symbols else 0
    batches = [new_symbols[i : i + BATCH_SIZE] for i in range(0, len(new_symbols), BATCH_SIZE)]
    LOG.info(
        "%s: %d newly-listed symbol(s) in %d new shard(s)", kind, len(new_symbols), len(batches)
    )
    total_rows = 0
    for offset, batch in enumerate(batches):
        shard_index = next_index + offset
        for year, month in current_window_dirs(kind, now):
            full_start = window_full_start(kind, year, month)
            destination = shard_path(out, kind, year, shard_index, month)
            frame = _fetch_batch(data_client, batch, full_start, now, kind)
            if frame is None or frame.empty:
                continue
            total_rows += _merge_and_write(
                pd.DataFrame(columns=list(BAR_ROW_COLUMNS)), frame.reset_index(), destination
            )
        shard_symbols[shard_index] = batch
    layout["shard_symbols"] = {
        f"{index:04d}": symbols for index, symbols in sorted(shard_symbols.items())
    }
    save_layout(out, kind, layout)
    return total_rows


def run(*, kind: str, out: Path, now: datetime | None = None, limit: int | None = None) -> int:
    _refuse_if_bulk_fetch_active()
    now = now or datetime.now(UTC)
    with _exclusive_lock(out):
        trading_client, data_client = _clients()
        active_symbols = load_universe(trading_client, limit=limit)
        layout = load_layout(out, kind)
        shard_symbols = freeze_shard_symbols(out, kind, layout, now=now)
        started = time.time()
        updated_rows = update_existing_shards(data_client, out, kind, shard_symbols, now=now)
        new_rows = append_new_symbols(
            data_client, out, kind, layout, shard_symbols, active_symbols, now=now
        )
        elapsed = (time.time() - started) / 60
        LOG.info(
            "%s: done -- %d row(s) refreshed, %d row(s) from new listings, %.1fmin",
            kind,
            updated_rows,
            new_rows,
            elapsed,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["daily", "minute"], required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="Only the first N active symbols.")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    try:
        return run(kind=args.kind, out=args.out, limit=args.limit)
    except UpdateLockedError as exc:
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
