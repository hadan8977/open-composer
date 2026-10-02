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
from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import yaml
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
#: The vendor serves ``adjustment="all"`` history: after a split or dividend
#: takes effect it multiplies the WHOLE history of that symbol by an adjustment
#: factor. Refetching only the trailing window therefore leaves a seam (old
#: basis before the window, new basis inside it). A symbol whose overlapping
#: rows no longer match the archive is "restated" and gets its full history
#: (every year directory) replaced -- see ``rewrite_full_history``.
HISTORY_START = datetime(2016, 1, 1, tzinfo=UTC)
RESTATEMENT_RTOL = 1e-6
PRICE_COLUMNS = ("open", "high", "low", "close", "vwap")
REWRITE_BATCH_SIZE = 40
DEFAULT_REWRITE_BUDGET_MIN = 25.0
RESTATEMENTS_FILE = "_restatements.jsonl"
PENDING_FILE = "_restatements_pending.jsonl"
SLEEVE_SPEC_NAMES = (
    "us_etf_sector_rotation_252_top2_weekly",
    "us_etf_growth_rotation_blend_top2_monthly",
    "us_etf_levered_rotation_63_top2_monthly",
    "us_etf_eom_sector_blend_monthly",
)
#: Number of vendor requests issued by this process (reported at the end of a run).
API_CALLS = {"n": 0}


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


def _fetch(data_client, symbols, start: datetime, end: datetime, kind: str):
    """``_fetch_batch`` plus a request counter (looked up at call time so tests can patch it)."""
    API_CALLS["n"] += 1
    return _fetch_batch(data_client, symbols, start, end, kind)


def _as_rows(frame: pd.DataFrame | None) -> pd.DataFrame:
    """A fetched frame as plain rows: upper-case symbol, UTC timestamp, no index."""
    if frame is None or len(frame) == 0:
        return pd.DataFrame(columns=list(BAR_ROW_COLUMNS))
    if "symbol" not in frame.columns or "timestamp" not in frame.columns:
        frame = frame.reset_index()
    frame = frame.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    frame["symbol"] = frame["symbol"].astype("string").str.upper()
    return frame


def detect_restated_symbols(
    existing: pd.DataFrame, fetched: pd.DataFrame, *, rtol: float = RESTATEMENT_RTOL
) -> dict[str, float]:
    """Symbols whose overlapping (symbol, timestamp) rows changed price level.

    Compares open/high/low/close/vwap on the overlap and returns
    ``{symbol: largest relative difference}`` for symbols above ``rtol``.
    """
    if existing is None or fetched is None or len(existing) == 0 or len(fetched) == 0:
        return {}
    old = _as_rows(existing)
    new = _as_rows(fetched)
    columns = [c for c in PRICE_COLUMNS if c in old.columns and c in new.columns]
    if not columns:
        return {}
    old = old.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    new = new.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
    joined = old[["symbol", "timestamp", *columns]].merge(
        new[["symbol", "timestamp", *columns]],
        on=["symbol", "timestamp"],
        suffixes=("_old", "_new"),
    )
    if joined.empty:
        return {}
    worst = pd.Series(0.0, index=joined.index)
    for column in columns:
        before = joined[f"{column}_old"].astype(float)
        after = joined[f"{column}_new"].astype(float)
        scale = before.abs().where(before.abs() > 0, after.abs())
        diff = ((after - before).abs() / scale).fillna(0.0)
        worst = worst.where(worst >= diff, diff)
    per_symbol = worst.groupby(joined["symbol"].astype(str)).max()
    return {str(sym): float(val) for sym, val in per_symbol.items() if val > rtol}


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{os.getpid()}")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def _append_jsonl(path: Path, records: Iterable[dict]) -> None:
    lines = "".join(json.dumps(record, sort_keys=True) + "\n" for record in records)
    if not lines:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(lines)


def _year_shard_map(out: Path) -> dict[int, dict[str, list[Path]]]:
    """year -> symbol -> shard files, from each shard's symbol column only."""
    mapping: dict[int, dict[str, list[Path]]] = {}
    daily = out / "daily"
    if not daily.is_dir():
        return mapping
    for year_dir in sorted(daily.iterdir()):
        if not (year_dir.is_dir() and year_dir.name.isdigit()):
            continue
        per_symbol: dict[str, list[Path]] = {}
        for shard_file in sorted(year_dir.glob("shard-*.parquet")):
            table = pq.read_table(shard_file, columns=["symbol"])
            for value in table.column("symbol").unique().to_pylist():
                per_symbol.setdefault(str(value).upper(), []).append(shard_file)
        mapping[int(year_dir.name)] = per_symbol
    return mapping


def _rewrite_batch(
    batch: list[str],
    fetched: pd.DataFrame,
    shard_map: dict[int, dict[str, list[Path]]],
    *,
    mode: str,
    detected_at: str,
    max_rel_diff: Mapping[str, float],
) -> list[dict]:
    fetched_years = fetched["timestamp"].dt.year if len(fetched) else pd.Series([], dtype="int64")
    records = {
        symbol: {
            "detected_at": detected_at,
            "mode": mode,
            "symbol": symbol,
            "max_rel_diff": float(max_rel_diff.get(symbol, 0.0)),
            "years_rewritten": [],
            "rows_before": 0,
            "rows_after": 0,
            "rows_without_shard": 0,
            "refetch_empty": False,
        }
        for symbol in batch
    }
    by_symbol_year: dict[tuple[str, int], pd.DataFrame] = {}
    if len(fetched):
        for (symbol, year), part in fetched.groupby(["symbol", fetched_years], sort=False):
            by_symbol_year[(str(symbol), int(year))] = part
    fetched_symbols = {symbol for symbol, _ in by_symbol_year}
    for symbol in batch:
        if symbol not in fetched_symbols:
            records[symbol]["refetch_empty"] = True

    files: dict[tuple[int, Path], set[str]] = {}
    for year, per_symbol in shard_map.items():
        for symbol in batch:
            for shard_file in per_symbol.get(symbol, ()):
                files.setdefault((year, shard_file), set()).add(symbol)
    for (symbol, year), part in by_symbol_year.items():
        if symbol in records and not shard_map.get(year, {}).get(symbol):
            records[symbol]["rows_without_shard"] += len(part)

    for (year, shard_file), present in sorted(files.items(), key=lambda item: str(item[0][1])):
        frame = _read_shard_frame(shard_file)
        frame["symbol"] = frame["symbol"].astype("string").str.upper()
        replace = {s for s in present if (s, year) in by_symbol_year}
        for symbol in present:
            records[symbol]["rows_before"] += int((frame["symbol"] == symbol).sum())
        if not replace:
            for symbol in present:
                records[symbol]["rows_after"] += int((frame["symbol"] == symbol).sum())
            continue
        kept = frame.loc[~frame["symbol"].isin(replace)]
        pieces = [by_symbol_year[(symbol, year)] for symbol in sorted(replace)]
        new_rows = pd.concat(pieces, ignore_index=True)
        new_rows = new_rows[[c for c in frame.columns if c in new_rows.columns]]
        combined = pd.concat([kept, new_rows], ignore_index=True)
        combined = combined.drop_duplicates(subset=["symbol", "timestamp"], keep="last")
        combined = combined.sort_values(["symbol", "timestamp"], kind="stable").reset_index(
            drop=True
        )
        _atomic_write_parquet(combined, shard_file)
        for symbol in present:
            records[symbol]["rows_after"] += int((combined["symbol"] == symbol).sum())
            if symbol in replace:
                records[symbol]["years_rewritten"].append(year)
    return [records[symbol] for symbol in batch]


def rewrite_full_history(
    data_client,
    out: Path,
    symbols: Sequence[str],
    *,
    now: datetime,
    history_start: datetime = HISTORY_START,
    mode: str,
    max_rel_diff: Mapping[str, float] | None = None,
    deadline: float | None = None,
    batch_size: int = REWRITE_BATCH_SIZE,
) -> list[dict]:
    """Replace every year's rows of ``symbols`` with the vendor's current history.

    Returns one record per symbol actually processed (the same record is appended
    to ``out/daily/_restatements.jsonl``). Symbols not reached before ``deadline``
    (a ``time.monotonic()`` value) are simply absent from the result and left for
    the caller to queue. A symbol whose full refetch is empty keeps all its rows.
    A year the vendor returned rows for but where the symbol has no shard is not
    created (``rows_without_shard``); a year the vendor returned nothing for keeps
    its old rows.
    """
    ordered = list(dict.fromkeys(str(symbol).upper() for symbol in symbols))
    if not ordered:
        return []
    batch_size = max(1, min(int(batch_size), REWRITE_BATCH_SIZE))
    detected_at = now.isoformat()
    shard_map: dict[int, dict[str, list[Path]]] | None = None
    done: list[dict] = []
    for offset in range(0, len(ordered), batch_size):
        if deadline is not None and time.monotonic() >= deadline:
            break
        batch = ordered[offset : offset + batch_size]
        fetched = _as_rows(_fetch(data_client, batch, history_start, now, "daily"))
        if shard_map is None:
            shard_map = _year_shard_map(out)
        records = _rewrite_batch(
            batch,
            fetched,
            shard_map,
            mode=mode,
            detected_at=detected_at,
            max_rel_diff=max_rel_diff or {},
        )
        _append_jsonl(out / "daily" / RESTATEMENTS_FILE, records)
        done.extend(records)
        LOG.info(
            "rewrite_full_history[%s]: %d/%d symbol(s) done (last batch %s..%s)",
            mode,
            len(done),
            len(ordered),
            batch[0],
            batch[-1],
        )
    return done


def load_sleeve_symbols(repo_root: Path | None = None) -> list[str]:
    """Upper-case tickers named by the four ETF paper sleeves (priority for rewrites)."""
    root = repo_root or Path(__file__).resolve().parents[1]
    found: set[str] = set()

    def walk(node, key: str | None = None) -> None:
        if isinstance(node, dict):
            for child_key, child in node.items():
                walk(child, str(child_key))
        elif isinstance(node, list):
            for child in node:
                walk(child, key)
        elif isinstance(node, str) and key in {
            "universe",
            "cash_symbol",
            "signal_symbol",
            "reversal_symbol",
        }:
            if node.isupper() and node.isalpha():
                found.add(node)

    for name in SLEEVE_SPEC_NAMES:
        try:
            walk(yaml.safe_load((root / "strategy_specs" / "drafts" / f"{name}.yaml").read_text()))
        except (OSError, yaml.YAMLError):
            continue
    return sorted(found)


def _read_pending(out: Path) -> dict[str, float]:
    path = out / "daily" / PENDING_FILE
    pending: dict[str, float] = {}
    if not path.exists():
        return pending
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            pending[str(item["symbol"]).upper()] = float(item.get("max_rel_diff", 0.0))
    return pending


def _write_pending(out: Path, pending: Mapping[str, float], *, now: datetime) -> None:
    lines = "".join(
        json.dumps(
            {"symbol": symbol, "max_rel_diff": pending[symbol], "queued_at": now.isoformat()},
            sort_keys=True,
        )
        + "\n"
        for symbol in pending
    )
    _atomic_write_text(out / "daily" / PENDING_FILE, lines)


def _priority_order(symbols: Iterable[str], priority: Iterable[str]) -> list[str]:
    first = {str(symbol).upper() for symbol in priority}
    return sorted(set(symbols), key=lambda symbol: (0 if symbol in first else 1, symbol))


def process_restatements(
    data_client,
    out: Path,
    detected: Mapping[str, float],
    *,
    now: datetime,
    budget_min: float,
    priority: Iterable[str] = (),
) -> list[dict]:
    """Rewrite leftovers from earlier runs first, then this run's detections.

    Whatever does not fit in ``budget_min`` stays in the pending file (its tail
    window was already merged, so the newest bar is present; only the seam waits).
    """
    pending = _read_pending(out)
    if not pending and not detected:
        return []
    priority = list(priority)
    fresh = {symbol: diff for symbol, diff in detected.items() if symbol not in pending}
    ordered = _priority_order(pending, priority) + _priority_order(fresh, priority)
    diffs = {**fresh, **pending}
    for symbol, diff in detected.items():
        diffs[symbol] = max(diff, diffs.get(symbol, 0.0))
    deadline = time.monotonic() + max(0.0, budget_min) * 60.0
    records = rewrite_full_history(
        data_client, out, ordered, now=now, mode="update", max_rel_diff=diffs, deadline=deadline
    )
    done = {record["symbol"] for record in records}
    remaining = {symbol: diffs[symbol] for symbol in ordered if symbol not in done}
    _write_pending(out, remaining, now=now)
    if remaining:
        LOG.warning(
            "%d restated symbol(s) queued in %s for the next run (budget %.1f min): %s",
            len(remaining),
            PENDING_FILE,
            budget_min,
            ", ".join(list(remaining)[:20]),
        )
    return records


def repair_full_window(
    data_client,
    out: Path,
    shard_symbols: dict[int, list[str]],
    *,
    now: datetime,
    priority: Iterable[str] = (),
) -> list[dict]:
    """Daily only: compare the whole current year against the vendor and fix restated symbols."""
    year_start = datetime(now.year, 1, 1, tzinfo=UTC)
    restated: dict[str, float] = {}
    for shard_index, symbols in sorted(shard_symbols.items()):
        existing = _read_shard_frame(shard_path(out, "daily", now.year, shard_index))
        if existing.empty:
            continue
        frame = _fetch(data_client, symbols, year_start, now, "daily")
        if frame is None or len(frame) == 0:
            continue
        restated.update(detect_restated_symbols(existing, _as_rows(frame)))
    LOG.info("repair-full-window: %d restated symbol(s) found", len(restated))
    ordered = _priority_order(restated, priority)
    return rewrite_full_history(
        data_client, out, ordered, now=now, mode="repair", max_rel_diff=restated
    )


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
    rewrite_budget_min: float = DEFAULT_REWRITE_BUDGET_MIN,
    priority_symbols: Iterable[str] = (),
) -> int:
    """Top up every frozen shard for every (year, month) in the current window.

    Daily: a symbol whose overlapping rows changed price level was restated by
    the vendor; its tail is merged as always and its full 2016-now history is
    replaced afterwards (``process_restatements``, time-boxed by
    ``rewrite_budget_min``). Minute: detection is only logged (known limit).
    """
    total_rows = 0
    detected: dict[str, float] = {}
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
            frame = _fetch(data_client, symbols, window_start, now, kind)
            if frame is None or frame.empty:
                continue
            fetched = frame.reset_index()
            changed = detect_restated_symbols(existing, fetched)
            if changed and kind == "daily":
                for symbol, diff in changed.items():
                    detected[symbol] = max(diff, detected.get(symbol, 0.0))
            elif changed:
                LOG.warning(
                    "%s %04d-%02d shard %04d: %d restated symbol(s), detect only: %s",
                    kind,
                    year,
                    month or 0,
                    shard_index,
                    len(changed),
                    ", ".join(sorted(changed)[:10]),
                )
                _append_jsonl(
                    out / kind / RESTATEMENTS_FILE,
                    [
                        {
                            "detected_at": now.isoformat(),
                            "mode": "minute_detect_only",
                            "symbol": symbol,
                            "max_rel_diff": diff,
                        }
                        for symbol, diff in sorted(changed.items())
                    ],
                )
            rows = _merge_and_write(existing, fetched, destination)
            total_rows += rows
        LOG.info(
            "%s %04d%s: updated %d frozen shard(s)",
            kind,
            year,
            f"-{month:02d}" if month else "",
            len(shard_symbols),
        )
    if kind == "daily":
        started = time.time()
        records = process_restatements(
            data_client,
            out,
            detected,
            now=now,
            budget_min=rewrite_budget_min,
            priority=priority_symbols,
        )
        LOG.info(
            "daily: %d detected, %d full-history rewrite(s) in %.1fs",
            len(detected),
            len(records),
            time.time() - started,
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
            frame = _fetch(data_client, batch, full_start, now, kind)
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


def run(
    *,
    kind: str,
    out: Path,
    now: datetime | None = None,
    limit: int | None = None,
    rewrite_budget_min: float = DEFAULT_REWRITE_BUDGET_MIN,
    repair: bool = False,
) -> int:
    _refuse_if_bulk_fetch_active()
    now = now or datetime.now(UTC)
    with _exclusive_lock(out):
        trading_client, data_client = _clients()
        active_symbols = load_universe(trading_client, limit=limit)
        layout = load_layout(out, kind)
        shard_symbols = freeze_shard_symbols(out, kind, layout, now=now)
        started = time.time()
        sleeve_symbols = load_sleeve_symbols()
        if repair and kind == "daily":
            repaired = repair_full_window(
                data_client, out, shard_symbols, now=now, priority=sleeve_symbols
            )
            LOG.info("repair-full-window: %d symbol(s) rewritten", len(repaired))
        updated_rows = update_existing_shards(
            data_client,
            out,
            kind,
            shard_symbols,
            now=now,
            rewrite_budget_min=rewrite_budget_min,
            priority_symbols=sleeve_symbols,
        )
        new_rows = append_new_symbols(
            data_client, out, kind, layout, shard_symbols, active_symbols, now=now
        )
        elapsed = (time.time() - started) / 60
        LOG.info(
            "%s: done -- %d row(s) refreshed, %d row(s) from new listings, %.1fmin, %d api call(s)",
            kind,
            updated_rows,
            new_rows,
            elapsed,
            API_CALLS["n"],
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["daily", "minute"], required=True)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--limit", type=int, default=None, help="Only the first N active symbols.")
    parser.add_argument(
        "--rewrite-budget-min",
        type=float,
        default=DEFAULT_REWRITE_BUDGET_MIN,
        help="Minutes per run for full-history rewrites of restated symbols (daily); the rest "
        f"is queued in {PENDING_FILE}.",
    )
    parser.add_argument(
        "--repair-full-window",
        action="store_true",
        help="Daily only: refetch the whole current year, find symbols whose stored rows no "
        "longer match the vendor and rewrite their full history.",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", stream=sys.stdout
    )
    load_dotenv(dotenv_path=Path(__file__).resolve().parents[1] / ".env")
    try:
        return run(
            kind=args.kind,
            out=args.out,
            limit=args.limit,
            rewrite_budget_min=args.rewrite_budget_min,
            repair=args.repair_full_window,
        )
    except UpdateLockedError as exc:
        LOG.error("%s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
