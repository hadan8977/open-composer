# ruff: noqa: E501
"""Daily refresh of the live equity-book data root (T-20261001-22, R1004-T22).  Not scheduled.

Two layers, both rebuilt for the current year only:

1. **Upstream feature tables** under ``data/features/`` (``UPSTREAM`` below, order matters).  Per
   table: back up the year partition, run the fetch commands, build into a staging directory (or in
   place for the three tables whose builder only writes in place), compare the staged partition with
   the backup on the rows that must not change, then swap it in.  A failed comparison restores the
   backup and the run ends with exit code 3.  Price tables are rebuilt for the whole year every day
   (the vendor re-bases adjusted prices); their comparison is the two-zone rule of T-20261002-02:
   only return-like columns before ``last date - 3 sessions`` gate the swap.
2. **Live root** ``data/live/equity_book/``: ``hygiene``, ``panel`` (current year), ``prices``,
   ``etf``, ``risk``, ``signals`` (current year, ``--force``; reads the risk residuals), ``alpha``
   (themes + formation IC merged with the frozen research snapshot).  The research snapshot
   ``data/research/equity_book/`` is only read.

Modes: default = run; ``--dry-run`` prints the plan; ``--check`` only writes
``data/live/equity_book/_freshness.json``.  Exit codes: 0 ok, 2 the SIP archive has not reached the
expected session yet (nothing is done), 3 an upstream comparison failed (backup restored),
4 a command failed, 6 another run holds the lock.  Log ``logs/refresh_equity_book_live.log``,
lock ``data/live/.refresh.lock``.

Split-type restatements: a new ``max_rel_diff >= 0.2`` record in ``data/sip/daily/_restatements.jsonl``
for a symbol of the portfolio universe also rebuilds the earlier ``daily_broad`` partitions of that
year range (the whole history of the symbol was re-based).  The cursor lives in
``data/live/refresh_state.json``.

Re-based symbols in dependent tables (T-20261006-01): a replaced ``daily_broad`` partition brings
every archive restatement since that partition was built (on 2026-10-05 the 2022-2025 partitions
dated from 09-18 and carried the T-20261002-01 repair).  Tables whose rows follow the price history
(``keys_follow_prices``: ``nsi`` drops pairs around split-like price breaks,
``sec_fundamentals_daily`` takes its rows from ``daily_broad``) may add or drop keys of exactly
those symbols: split-type or row-count-changing records detected after the build time of a
partition this day replaced, for that year.  Backups are taken once per day, so a repeated run
keeps the pre-day files and their build times.

Value columns built from a price table's levels (``values_follow``: ``short_interest`` divides by
``dollar_adv_63 / close`` of ``daily``) inherit that table's two zones: the gate stops at the strict
cut (the vendor revises the latest sessions' volume; on 2026-10-05, 2,650 of 2,696 symbols moved by
a median 2.4e-7 on 10-02), and symbols with any restatement after the price partition was built are
left out of the changed share (a dividend re-basing moves every adjusted close; the price gate
compares returns only).

The script uses no broker interface.  ``fetch`` commands of the news/SEC/FINRA collectors talk to
their public or keyed sources; ``--no-fetch`` skips them.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import shutil
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]

FEATURES = ROOT / "data/features"
LIVE = ROOT / "data/live/equity_book"
SNAPSHOT = ROOT / "data/research/equity_book"
SIP_DAILY = ROOT / "data/sip/daily"
LOCK_FILE = ROOT / "data/live/.refresh.lock"
STATE_FILE = ROOT / "data/live/refresh_state.json"
LOG_FILE = ROOT / "logs/refresh_equity_book_live.log"
BACKUP_ROOT = ROOT / "data/live/backup-refresh"
STAGE_ROOT = FEATURES / "_refresh_tmp"
VENDOR_REVISION_SYMBOLS = FEATURES / "_t02_stage/vendor_revision_symbols.txt"
# --class paper: this feeds the paper book, so run_capped neither queues nor refuses it (the
# research class refuses --mem above 1.2G since 10-07, which stopped the 10-07 22:45 refresh)
CAPPED = ["scripts/run_capped.sh", "--class", "paper", "--mem", "1.8G", "--"]
PY = ["uv", "run", "python"]
NEW_YORK = ZoneInfo("America/New_York")

EXIT_OK, EXIT_NOT_FRESH, EXIT_UPSTREAM, EXIT_COMMAND, EXIT_LOCKED = 0, 2, 3, 4, 6
SPLIT_REL_DIFF = 0.2
HEAVY_RSS_KB = 600_000  # another process above this makes a build wait
HEAVY_WAIT_S = 3 * 3600
# the EWMA risk model needs the full history: a 2025 start left spec_var rank parity at 0.14 of dates
# against 0.84 from 2017 (T-22 live-parity.json); one run takes about 3.5 minutes
RISK_START = "2017-01-01"
STRICT_SESSIONS_BACK = 3
RETURN_COLUMNS = (
    "ret_1,ret_5,ret_21,ret_63,ret_126,ret_252,vol_21,vol_63,max_ret_1_21,"
    "dist_from_252d_high,momentum_252_21"
)
RATIO_COLUMNS = "ret_1,ret_5,ret_21,ret_63,ret_126,ret_252,momentum_252_21"
# risk before signals: resid_mom_12_1 reads risk/residuals_<y>.parquet (T-22: signals built first fall
# back to industry-demeaned returns and differ from the snapshot)
LIVE_STAGES = ("hygiene", "panel", "prices", "etf", "risk", "signals", "alpha")
FRESH_STAGES = ("panel", "prices", "etf", "signals", "risk", "alpha")

log = logging.getLogger("refresh_equity_book_live")


@dataclass(frozen=True)
class Table:
    """One upstream feature table.

    ``fetch``/``build`` are argv lists; ``{year}``, ``{start}``, ``{end}``, ``{as_of}``, ``{tmp}``
    are filled in by :func:`render`.  ``output`` is the year partition (``{year}`` placeholder) or a
    single file; ``in_place`` builders write ``output`` directly (backup restored on failure).
    ``check`` is ``"price"`` (two-zone), ``"plain"`` (rows up to the old last date) or ``"none"``.
    """

    name: str
    output: str
    date_col: str
    keys: str
    build: tuple[str, ...]
    fetch: tuple[tuple[str, ...], ...] = ()
    pre_build: tuple[tuple[str, ...], ...] = ()  # commands run before ``build`` (same placeholders)
    in_place: bool = False
    check: str = "plain"
    link_prior_years: bool = False  # prior-year partitions are *copied* into the staging dir
    monthly: bool = False  # append-only by month_end (see run_monthly_table)
    keys_follow_prices: bool = False  # re-based symbols may add/drop keys (see rebased_symbols)
    values_follow: str = (
        ""  # price table whose levels feed value columns (two-zone, see module doc)
    )
    enabled: bool = True
    note: str = ""


UPSTREAM: tuple[Table, ...] = (
    Table(
        "universe",
        "universe/{year}.parquet",
        "month_end",
        "symbol,month_end",
        build=(
            *PY,
            "scripts/build_feature_universe.py",
            "--memory-limit",
            "1200MB",
            "--out-dir",
            "{tmp}",
        ),
        monthly=True,
    ),
    Table(
        "universe_broad",
        "universe_broad/{year}.parquet",
        "month_end",
        "symbol,month_end",
        build=(
            *PY,
            "scripts/build_feature_universe.py",
            "--no-top-n-cap",
            "--min-dollar-adv",
            "1000000",
            "--min-close",
            "2.0",
            "--include-delisted-root",
            "data/sip-delisted/by_year",
            "--out-dir",
            "{tmp}",
            "--memory-limit",
            "1.2GB",
        ),
        monthly=True,
    ),
    Table(
        "daily",
        "daily/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_daily_features.py",
            "--years",
            "{year}",
            "--out-dir",
            "{tmp}",
            "--memory-limit",
            "1.0GB",
        ),
        check="price",
    ),
    Table(
        "daily_broad",
        "daily_broad/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_daily_features.py",
            "--universe-root",
            "data/features/universe_broad",
            "--extra-daily-root",
            "data/sip-delisted/by_year",
            "--out-dir",
            "{tmp}",
            "--memory-limit",
            "1.0GB",
            "--years",
            "{year}",
        ),
        check="price",
    ),
    Table(
        "sec_fundamentals_facts",
        "sec_fundamentals/facts.parquet",
        "filed",
        "cik,concept,period_end,filed",
        build=(
            *PY,
            "scripts/build_sec_xbrl_fundamentals.py",
            "--stage",
            "facts",
            "--source",
            "bulk",
        ),
        fetch=(
            (
                *PY,
                "scripts/build_sec_xbrl_fundamentals.py",
                "--stage",
                "download",
                "--source",
                "bulk",
                "--force",
            ),
        ),
        in_place=True,
        check="none",
        note="facts are restated by the filer; no row-level gate, the daily table below is gated",
    ),
    Table(
        "sec_fundamentals_daily",
        "sec_fundamentals_daily/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_sec_xbrl_fundamentals.py",
            "--stage",
            "daily",
            "--start-year",
            "{year}",
            "--end-year",
            "{year}",
            "--force",
        ),
        in_place=True,
        keys_follow_prices=True,
        note="sue_eps/sue_rev may change for late 10-Qs entering the quarterly ladder (pitfall #62)",
    ),
    Table(
        "nsi",
        "nsi/nsi.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(*PY, "scripts/build_nsi_signal.py"),
        in_place=True,
        keys_follow_prices=True,
    ),
    Table(
        "insider_broad",
        "insider_broad/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_insider_features.py",
            "--universe-root",
            "data/features/universe_broad",
            "--top-n",
            "1000000",
            "--weekly-top-n",
            "1000000",
            "--start-year",
            "2016",
            "--end-year",
            "{year}",
            "--as-of",
            "{as_of}",
            "--out-root",
            "{tmp}",
            "--skip-weekly-panel",
        ),
        fetch=(
            (
                *PY,
                "scripts/collect_sec_insider_transactions.py",
                "--stage",
                "tail-index",
                "--tail-start",
                "{start}",
                "--tail-end",
                "{end}",
            ),
            (*PY, "scripts/collect_sec_insider_transactions.py", "--stage", "tail-fetch"),
        ),
        link_prior_years=True,
    ),
    Table(
        "short_volume_broad",
        "short_volume_broad/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_short_volume_features.py",
            "--years",
            "{year}",
            "--universe-root",
            "data/features/universe_broad",
            "--out-dir",
            "{tmp}",
            "--as-of",
            "{as_of}",
        ),
        fetch=(
            (
                *PY,
                "scripts/collect_finra_short_volume.py",
                "--stage",
                "download",
                "--start",
                "{start}",
            ),
            (*PY, "scripts/collect_finra_short_volume.py", "--stage", "parse"),
            (*PY, "scripts/collect_finra_short_volume.py", "--stage", "manifest"),
        ),
    ),
    Table(
        "short_interest",
        "short_interest/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_short_interest_features.py",
            "--start-year",
            "2018",
            "--end-year",
            "{year}",
            "--as-of",
            "{as_of}",
            "--out-root",
            "{tmp}",
        ),
        fetch=(
            (*PY, "scripts/collect_finra_short_interest.py", "--stage", "schedule", "--force"),
            (
                *PY,
                "scripts/collect_finra_short_interest.py",
                "--stage",
                "download",
                "--start",
                "{start}",
            ),
            (*PY, "scripts/collect_finra_short_interest.py", "--stage", "parse"),
        ),
        link_prior_years=True,
        values_follow="daily",
    ),
    Table(
        "news_attention",
        "news_attention/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_news_attention_features.py",
            "features",
            "--as-of",
            "{as_of}",
            "--out-root",
            "{tmp}",
        ),
        pre_build=(
            (
                *PY,
                "scripts/build_news_attention_features.py",
                "articles",
                "--as-of",
                "{as_of}",
                "--out-root",
                "{tmp}",
            ),
        ),
        fetch=(
            (
                *PY,
                "scripts/collect_alpaca_news_packets.py",
                "--start",
                "{start}",
                "--end",
                "{end}",
                "--no-resume",
            ),
        ),
        link_prior_years=True,
        note="the 'articles' stage runs first when the article index is stale; see inventory.json",
    ),
    Table(
        "alpha101_alpha191_broad",
        "alpha101_broad/{year}.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(
            *PY,
            "scripts/build_alpha101_alpha191_features.py",
            "--years",
            "{year}",
            "--force",
            "--universe-root",
            "data/features/universe_broad",
            "--alpha101-out-dir",
            "{tmp}",
            "--alpha191-out-dir",
            "{tmp}_191",
            "--extra-daily-root",
            "data/sip-delisted/by_year",
            "--memory-limit",
            "800MB",
        ),
        enabled=False,
        note=(
            "disabled: T-20261002-02 kept the old alpha101/191 tables, so fast-alpha columns of the "
            "live signals are empty after 2026-09-17 (only ML uses them, not the M0 composite)"
        ),
    ),
)


# --------------------------------------------------------------------------
# dates
# --------------------------------------------------------------------------


def expected_session(now: datetime | None = None) -> date:
    """Latest weekday session whose close has passed (New York): today after 16:00, else the day
    before; weekends roll back to Friday.  Exchange holidays are not modelled: on a holiday the SIP
    archive never reaches this date and the run exits 2, which is harmless."""
    now = now or datetime.now(UTC)
    local = now.astimezone(NEW_YORK)
    day = local.date() if local.hour >= 16 else local.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def latest_sip_date(sip_root: Path = SIP_DAILY) -> date | None:
    """Newest bar date of the SIP daily archive, from parquet footer statistics only."""
    import pyarrow.parquet as pq

    years = sorted(int(p.name) for p in sip_root.iterdir() if p.is_dir() and p.name.isdigit())
    for year in reversed(years):
        best = None
        for shard in sorted((sip_root / str(year)).glob("shard-*.parquet")):
            meta = pq.ParquetFile(shard).metadata
            col = meta.schema.names.index("timestamp") if "timestamp" in meta.schema.names else None
            if col is None:
                continue
            for g in range(meta.num_row_groups):
                stats = meta.row_group(g).column(col).statistics
                if stats is not None and stats.has_min_max:
                    best = stats.max if best is None else max(best, stats.max)
        if best is not None:
            return best.date() if hasattr(best, "date") else date.fromisoformat(str(best)[:10])
    return None


# --------------------------------------------------------------------------
# plan
# --------------------------------------------------------------------------


@dataclass
class Step:
    stage: str
    label: str
    argv: list[str]
    env: dict[str, str] = field(default_factory=dict)
    kind: str = "run"  # run | backup | check | swap | merge | restatement

    def text(self) -> str:
        prefix = " ".join(f"{k}={v}" for k, v in self.env.items())
        return (
            f"[{self.stage}] {self.label}: {(prefix + ' ') if prefix else ''}{' '.join(self.argv)}"
        )


def render(
    argv: Sequence[str], *, year: int, day: date, tmp: str, start: date, end: date
) -> list[str]:
    values = {
        "year": str(year),
        "as_of": day.isoformat(),
        "tmp": tmp,
        "start": start.isoformat(),
        "end": end.isoformat(),
    }
    return [a.format(**values) for a in argv]


def stage_dir(table: Table) -> str:
    path = STAGE_ROOT / table.name
    try:
        return str(path.relative_to(ROOT))
    except ValueError:  # staging root outside the project (tests)
        return str(path)


def build_plan(
    day: date,
    *,
    tables: Sequence[Table] = UPSTREAM,
    stages: Sequence[str] = LIVE_STAGES,
    fetch: bool = True,
    upstream: bool = True,
    extra_daily_years: Sequence[int] = (),
    last_dates: dict[str, date] | None = None,
) -> list[Step]:
    """The ordered steps of one refresh for session ``day`` (pure; reads nothing).

    ``extra_daily_years``: earlier years whose ``daily_broad`` partition is rebuilt too (split-type
    restatement).  ``last_dates``: per-table last date of the current partition, used to pick the
    fetch window (default: 14 days back).
    """
    year = day.year
    plan: list[Step] = []
    if upstream:
        for table in tables:
            if not table.enabled:
                continue
            start = (last_dates or {}).get(table.name, day - timedelta(days=14)) - timedelta(days=3)
            tmp = stage_dir(table)

            def r(
                argv: Sequence[str], y: int = year, tmp: str = tmp, start: date = start
            ) -> list[str]:
                return render(argv, year=y, day=day, tmp=tmp, start=start, end=day)

            plan.append(
                Step(f"up:{table.name}", "backup", [table.output.format(year=year)], kind="backup")
            )
            if fetch:
                plan += [
                    Step(f"up:{table.name}", "fetch", [*CAPPED, *r(cmd)]) for cmd in table.fetch
                ]
            plan += [
                Step(f"up:{table.name}", "pre-build", [*CAPPED, *r(cmd)]) for cmd in table.pre_build
            ]
            years = [
                year,
                *(
                    [y for y in extra_daily_years if y != year]
                    if table.name == "daily_broad"
                    else []
                ),
            ]
            for y in years:
                plan.append(Step(f"up:{table.name}", f"build {y}", [*CAPPED, *r(table.build, y)]))
            plan.append(
                Step(f"up:{table.name}", f"check+swap ({table.check})", [table.name], kind="check")
            )
    env = {"OC_EQUITY_BOOK_DIR": str(LIVE.relative_to(ROOT))}
    live_cmds: dict[str, list[list[str]]] = {
        "hygiene": [[*PY, "scripts/build_equity_book_panel.py", "hygiene"]],
        "panel": [[*PY, "scripts/build_equity_book_panel.py", "panel", "--years", str(year)]],
        "prices": [[*PY, "scripts/build_equity_book_panel.py", "prices"]],
        "etf": [[*PY, "scripts/build_equity_book_panel.py", "etf"]],
        "signals": [
            [*PY, "scripts/build_equity_book_signals.py", "build", "--years", str(year), "--force"]
        ],
        "risk": [
            [
                *PY,
                "scripts/build_equity_book_risk.py",
                "--start",
                RISK_START,
                "--end",
                day.isoformat(),
                "--out",
                str(LIVE.relative_to(ROOT) / "risk"),
            ]
        ],
        "alpha": [[*PY, "scripts/build_book_v1_alpha.py"]],
    }
    for stage in stages:
        for cmd in live_cmds[stage]:
            plan.append(Step(f"live:{stage}", "build", [*CAPPED, *cmd], env=dict(env)))
        if stage == "alpha":
            plan.append(
                Step("live:alpha", "merge formation_ic", ["merge_formation_ic"], kind="merge")
            )
    return plan


# --------------------------------------------------------------------------
# freshness
# --------------------------------------------------------------------------


def _max_date_of_parquet(path: Path, column: str) -> date | None:
    import pyarrow.parquet as pq

    if not path.exists():
        return None
    meta = pq.ParquetFile(path).metadata
    names = meta.schema.names
    if column not in names:
        return None
    idx = names.index(column)
    best = None
    for g in range(meta.num_row_groups):
        stats = meta.row_group(g).column(idx).statistics
        if stats is not None and stats.has_min_max:
            best = stats.max if best is None else max(best, stats.max)
    if best is None:
        return None
    return best.date() if hasattr(best, "date") else date.fromisoformat(str(best)[:10])


def stage_last_dates(live: Path, year: int) -> dict[str, date | None]:
    """Last date of every live stage, from file statistics only."""
    return {
        "panel": _max_date_of_parquet(live / f"panel/{year}.parquet", "trade_date"),
        "prices": _max_date_of_parquet(live / f"prices/{year}.parquet", "trade_date"),
        "etf": _max_date_of_parquet(live / "etf_daily.parquet", "trade_date"),
        "signals": _max_date_of_parquet(live / f"signals/{year}.parquet", "trade_date"),
        "risk": _max_date_of_parquet(live / f"risk/exposures_{year}.parquet", "trade_date"),
        "alpha": _max_date_of_parquet(live / f"alpha/book_v1/themes_{year}.parquet", "trade_date"),
    }


def freshness(live: Path, sip_last: date | None, year: int, *, now: datetime | None = None) -> dict:
    """The ``_freshness.json`` payload: per stage last date and whether it equals the SIP's."""
    last = stage_last_dates(live, year)
    stages = {
        name: {
            "last_date": d.isoformat() if d else None,
            "equals_sip_last": bool(d is not None and sip_last is not None and d == sip_last),
        }
        for name, d in last.items()
    }
    lagging = [n for n, s in stages.items() if not s["equals_sip_last"]]
    return {
        "generated_utc": (now or datetime.now(UTC)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "sip_last_date": sip_last.isoformat() if sip_last else None,
        "year": year,
        "stages": stages,
        "fresh": sip_last is not None and not lagging,
        "lagging_stages": lagging,
    }


def upstream_last_dates(features: Path, year: int, sip_last: date | None) -> dict[str, dict]:
    """Last date of every enabled upstream table partition and whether it reaches the SIP date.

    A live stage can end on the SIP date while a table feeding it lags (its rows are then empty and
    the ``*_cov`` flag of the signal is false), so this is the table-level lag report."""
    out: dict[str, dict] = {}
    for table in UPSTREAM:
        if not table.enabled:
            continue
        col = "month_end" if table.date_col == "month_end" else table.date_col
        last = _max_date_of_parquet(features / table.output.format(year=year), col)
        entry: dict = {
            "last_date": last.isoformat() if last else None,
            "reaches_sip_last": bool(
                last is not None and sip_last is not None and last >= sip_last
            ),
        }
        if (
            table.monthly
        ):  # a month-end table ends at the last closed month end, not at the SIP date
            entry["reaches_sip_last"] = None
            entry["monthly"] = True
        out[table.name] = entry
    return out


def write_freshness(live: Path, payload: dict) -> Path:
    live.mkdir(parents=True, exist_ok=True)
    path = live / "_freshness.json"
    path.write_text(json.dumps(payload, indent=1) + "\n")
    return path


# --------------------------------------------------------------------------
# lock
# --------------------------------------------------------------------------


class RefreshLocked(RuntimeError):
    pass


class FileLock:
    """Non-blocking exclusive ``flock``; the file stays on disk."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._fh = None

    def __enter__(self) -> FileLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh = open(self.path, "w")  # noqa: SIM115
        try:
            fcntl.flock(self._fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self._fh.close()
            self._fh = None
            raise RefreshLocked(str(self.path)) from exc
        return self

    def __exit__(self, *exc_info: object) -> None:
        if self._fh is not None:
            fcntl.flock(self._fh, fcntl.LOCK_UN)
            self._fh.close()
            self._fh = None


# --------------------------------------------------------------------------
# restatements
# --------------------------------------------------------------------------


def new_split_restatements(
    path: Path, offset: int, universe: set[str] | None = None
) -> tuple[list[dict], int]:
    """Split-type records (``max_rel_diff >= 0.2``) after line ``offset``; new offset.

    ``universe``: keep only symbols of the portfolio universe (None keeps all)."""
    if not path.exists():
        return [], offset
    lines = path.read_text().splitlines()
    out = []
    for raw in lines[offset:]:
        try:
            rec = json.loads(raw)
        except ValueError:
            continue
        if float(rec.get("max_rel_diff") or 0.0) >= SPLIT_REL_DIFF and (
            universe is None or rec.get("symbol") in universe
        ):
            out.append(rec)
    return out, len(lines)


def read_state(path: Path | None = None) -> dict:
    path = path or STATE_FILE
    return json.loads(path.read_text()) if path.exists() else {}


def write_state(path: Path | None = None, **updates: object) -> None:
    path = path or STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({**read_state(path), **updates}))


def read_cursor(path: Path | None = None) -> int | None:
    """Number of ``_restatements.jsonl`` lines already handled, or None when never initialised."""
    state = read_state(path)
    return int(state.get("restatement_offset", 0)) if "restatement_offset" in state else None


def write_cursor(offset: int, day: date | None = None, path: Path | None = None) -> None:
    write_state(path, restatement_offset=offset, last_day=day.isoformat() if day else None)


def last_universe_month_end(features: Path | None = None) -> date | None:
    """Newest ``month_end`` of ``universe_broad`` (the membership clock of the universe-keyed tables)."""
    root = (features or FEATURES) / "universe_broad"
    best = None
    for p in sorted(root.glob("[0-9][0-9][0-9][0-9].parquet")):
        d = _max_date_of_parquet(p, "month_end")
        best = d if best is None or (d is not None and d > best) else best
    return best


def membership_cut(features: Path | None = None, state_path: Path | None = None) -> date | None:
    """Last date whose universe membership cannot have moved since the previous successful run.

    The universe-keyed tables (daily, insider, short volume, ...) take their rows from the newest
    month end of ``universe_broad`` that is <= the row date.  When a month end was appended after
    the previous run (or the state does not know), rows dated on or after it are legitimately
    re-membered, so the invariance gate stops the day before it.  None: no new month end."""
    now = last_universe_month_end(features)
    if now is None:
        return None
    seen = read_state(state_path).get("universe_month_end")
    if seen is not None and date.fromisoformat(seen) >= now:
        return None
    return now - timedelta(days=1)


def init_cursor(
    restate_path: Path = SIP_DAILY / "_restatements.jsonl", path: Path | None = None
) -> int:
    """Put the cursor at the current end of the restatement log; returns the line count."""
    count = len(restate_path.read_text().splitlines()) if restate_path.exists() else 0
    write_cursor(count, None, path)
    return count


def restatement_years(records: Sequence[dict], current_year: int) -> list[int]:
    years = sorted({int(y) for r in records for y in r.get("years_rewritten", [])})
    return [y for y in years if y < current_year]


def _restatements_after(
    partitions: Sequence[tuple[int, datetime]], path: Path | None = None
) -> list[dict]:
    """Restatement records detected after the build time of a partition whose year they rewrite.

    ``partitions``: (year, build time) of the partitions being replaced."""
    path = path or SIP_DAILY / "_restatements.jsonl"
    if not partitions or not path.exists():
        return []
    out = []
    for raw in path.read_text().splitlines():
        try:
            rec = json.loads(raw)
            seen = datetime.fromisoformat(rec["detected_at"])
            years = {int(y) for y in rec.get("years_rewritten") or []}
        except (ValueError, KeyError, TypeError):
            continue
        seen = seen if seen.tzinfo else seen.replace(tzinfo=UTC)
        if any(year in years and seen > built for year, built in partitions):
            out.append(rec)
    return out


def rebased_symbols(
    partitions: Sequence[tuple[int, datetime]], path: Path | None = None
) -> list[str]:
    """Symbols whose price history in a replaced partition changed after it was built, by a
    split-type factor (``max_rel_diff >= SPLIT_REL_DIFF``) or in its row count: the ones that can
    add or drop keys.  Small re-basings (dividends) move values, not keys, so they stay out."""
    return sorted(
        {
            str(rec["symbol"])
            for rec in _restatements_after(partitions, path)
            if float(rec.get("max_rel_diff") or 0.0) >= SPLIT_REL_DIFF
            or rec.get("rows_before") != rec.get("rows_after")
        }
    )


def restated_symbols(
    partitions: Sequence[tuple[int, datetime]], path: Path | None = None
) -> list[str]:
    """Symbols with any restatement of a replaced partition after it was built (dividend
    re-basings included): every adjusted level of theirs may have moved."""
    return sorted({str(rec["symbol"]) for rec in _restatements_after(partitions, path)})


def replaced_partitions(day: date, table: str = "daily_broad") -> list[tuple[int, datetime]]:
    """(year, build time) of the ``table`` partitions this day's refresh backed up before
    replacing them (``shutil.copy2`` keeps the modification time of the old partition)."""
    root = _backup_path(table_by_name(table), day.year, day).parent
    return [
        (int(p.stem), datetime.fromtimestamp(p.stat().st_mtime, UTC))
        for p in sorted(root.glob("[0-9][0-9][0-9][0-9].parquet"))
    ]


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------


Runner = Callable[..., subprocess.CompletedProcess]


def other_heavy_processes(
    procs: Sequence[tuple[int, int, int]], me: int, limit_kb: int
) -> list[tuple[int, int]]:
    """``(pid, rss_kb)`` of processes above ``limit_kb`` that are not ``me`` or a descendant.

    ``procs``: ``(pid, ppid, rss_kb)`` rows."""
    parent = {pid: ppid for pid, ppid, _ in procs}

    def mine(pid: int) -> bool:
        seen = 0
        while pid and seen < 64:
            if pid == me:
                return True
            pid = parent.get(pid, 0)
            seen += 1
        return False

    return [(pid, rss) for pid, _, rss in procs if rss > limit_kb and not mine(pid)]


def _proc_table() -> list[tuple[int, int, int]]:
    rows = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = {}
            for line in (entry / "status").read_text().splitlines():
                key, _, value = line.partition(":")
                fields[key] = value.split()
            rows.append((int(entry.name), int(fields["PPid"][0]), int(fields["VmRSS"][0])))
        except (OSError, KeyError, IndexError, ValueError):
            continue
    return rows


def wait_for_quiet(
    limit_kb: int = HEAVY_RSS_KB,
    max_wait_s: float = HEAVY_WAIT_S,
    *,
    table: Callable[[], list[tuple[int, int, int]]] = _proc_table,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    me: int | None = None,
) -> bool:
    """Block while another process holds more than ``limit_kb`` RSS (this box has 3.9 GB: two
    builds at once swap and neither finishes).  False when ``max_wait_s`` ran out."""
    start = clock()
    announced = False
    while True:
        blockers = other_heavy_processes(table(), me or os.getpid(), limit_kb)
        if not blockers:
            return True
        if not announced:
            log.info("waiting for other heavy processes: %s", blockers)
            announced = True
        if clock() - start > max_wait_s:
            return False
        sleep(20)


def run_command(step: Step, runner: Runner = subprocess.run) -> int:
    if step.argv[: len(CAPPED)] == CAPPED and not wait_for_quiet():
        log.error("gave up waiting for other heavy processes before %s", step.label)
        return 75
    env = {**os.environ, **step.env}
    log.info("run %s", step.text())
    proc = runner(step.argv, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    tail = (proc.stdout + proc.stderr).splitlines()[-6:]
    for line in tail:
        log.info("  %s", line)
    return proc.returncode


def table_by_name(name: str) -> Table:
    return next(t for t in UPSTREAM if t.name == name)


def check_command(
    table: Table,
    old: Path,
    new: Path,
    cut: date,
    out: Path,
    allow_new: Path | None = None,
    allow_old: Path | None = None,
    exclude: Path | None = None,
) -> list[str]:
    """``check_feature_invariance.py`` argv for one table (two-zone rule for price tables)."""
    cmd = [
        *PY,
        "scripts/check_feature_invariance.py",
        "--new",
        str(new),
        "--old",
        str(old),
        "--date-col",
        table.date_col,
        "--cut",
        cut.isoformat(),
        "--keys",
        table.keys,
        "--out",
        str(out),
    ]
    if allow_new is not None:
        cmd += ["--allow-only-new", str(allow_new)]
    if allow_old is not None:
        cmd += ["--allow-only-old", str(allow_old)]
    if exclude is not None and table.check != "price":
        cmd += ["--exclude-symbols", str(exclude)]
    if table.check == "price":
        cmd += [
            "--columns",
            RETURN_COLUMNS,
            "--price-col",
            "close",
            "--price-tol",
            "0.04",
            "--price-aware-cols",
            RETURN_COLUMNS,
            "--price-ratio-cols",
            RATIO_COLUMNS,
        ]
        if VENDOR_REVISION_SYMBOLS.exists():
            cmd += ["--exclude-symbols", str(VENDOR_REVISION_SYMBOLS)]
    return cmd


def strict_cut(dates: Sequence[date], sessions_back: int = STRICT_SESSIONS_BACK) -> date | None:
    """Last date of the strict zone: ``sessions_back`` sessions before the last date."""
    ordered = sorted(set(dates))
    if len(ordered) <= sessions_back:
        return None
    return ordered[-1 - sessions_back]


def new_entrant_symbols(old: Path, new: Path) -> list[str]:
    """Symbols present in ``new`` but not at all in ``old`` (a month end brought them into the
    universe; the builder backfills their history, which is new rows, not changed rows)."""
    import pyarrow.parquet as pq

    old_syms = set(pq.read_table(old, columns=["symbol"]).column("symbol").unique().to_pylist())
    new_syms = set(pq.read_table(new, columns=["symbol"]).column("symbol").unique().to_pylist())
    return sorted(new_syms - old_syms)


def merge_formation_ic(live: Path = LIVE, snapshot: Path = SNAPSHOT) -> Path:
    """New ``formation_ic.parquet``: snapshot rows up to 2024-12-31 plus live rows from 2025-01-01.

    The live-only file is kept as ``formation_ic_live_only.parquet`` (renamed once per run)."""
    import pandas as pd

    base = live / "alpha/book_v1"
    current = base / "formation_ic.parquet"
    live_only = base / "formation_ic_live_only.parquet"
    marker = base / "formation_ic_merge.json"
    merged_sha = json.loads(marker.read_text()).get("sha256") if marker.exists() else None
    if current.exists() and _sha256(current) != merged_sha:
        # the builder just rewrote it with live years only: keep that file, then merge
        os.replace(current, live_only)
    live_df = pd.read_parquet(live_only)
    old = pd.read_parquet(snapshot / "alpha/book_v1/formation_ic.parquet")
    old = old[pd.to_datetime(old["formation_date"]) <= pd.Timestamp("2024-12-31")]
    new = live_df[pd.to_datetime(live_df["formation_date"]) >= pd.Timestamp("2025-01-01")]
    keys = [c for c in ("formation_date", "universe", "series") if c in old.columns]
    merged = pd.concat([old, new[old.columns]], ignore_index=True).sort_values(keys)
    merged.to_parquet(current, index=False)
    marker.write_text(json.dumps({"sha256": _sha256(current), "rows": len(merged)}))
    return current


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 22), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_path(table: Table, year: int, day: date) -> Path:
    return BACKUP_ROOT / day.isoformat() / table.output.format(year=year)


def _backup_once(src: Path, dst: Path) -> None:
    """Copy ``src`` to ``dst`` unless this day's backup exists: a repeated run of the same day
    keeps the files from before the day's first attempt (restore point and build times)."""
    if dst.exists():
        log.info("keeping the first backup of the day: %s", dst)
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _dates_of(path: Path, column: str) -> list[date]:
    import pyarrow.parquet as pq

    values = pq.read_table(path, columns=[column]).column(column).unique().to_pylist()
    return [v.date() if hasattr(v, "date") else v for v in values]


def new_month_ends(old_last: date | None, sessions: Sequence[date]) -> list[date]:
    """Month ends (last session of a month) after ``old_last`` that are closed.

    A month counts as closed once a later month has a session; the latest month in ``sessions``
    is never closed (its last session is not known yet)."""
    if not sessions:
        return []
    latest = max(sessions)
    last_of: dict[tuple[int, int], date] = {}
    for d in sessions:
        key = (d.year, d.month)
        last_of[key] = max(last_of.get(key, d), d)
    return [
        end
        for key, end in sorted(last_of.items())
        if key != (latest.year, latest.month) and (old_last is None or end > old_last)
    ]


def compose_monthly(old, staged, ends: Sequence[date]):
    """Old rows kept verbatim plus the staged rows of the new month ends only (polars frames)."""
    import polars as pl

    keep = old
    add = staged.filter(pl.col("month_end").cast(pl.Date).is_in(list(ends)))
    return pl.concat([keep, add.select(keep.columns)]).sort(["month_end", "symbol"])


def run_monthly_table(table: Table, day: date, steps: Sequence[Step], runner: Runner) -> int:
    """Append-only update of a month-end table (``universe``, ``universe_broad``).

    The builder recomputes every month from the current archive, which moves old months (vendor
    re-basing, late delistings); the lake keeps old months frozen and only adds closed month ends
    (T-02 composed them the same way), so rebuilding the year and comparing it with the file was
    the wrong check.  Skips when the calendar has no closed month end after the stored last one."""
    import polars as pl

    root = (FEATURES / table.output).parent
    parts = sorted(root.glob("[0-9][0-9][0-9][0-9].parquet"))
    old_last = max((max(_dates_of(p, table.date_col)) for p in parts), default=None)
    sessions: list[date] = []
    for y in range((old_last or day).year, day.year + 1):
        daily = FEATURES / f"daily_broad/{y}.parquet"
        if daily.exists():
            sessions += _dates_of(daily, "trade_date")
    ends = new_month_ends(old_last, sessions)
    if not ends:
        log.info("%s: no new month end after %s: skipped", table.name, old_last)
        return EXIT_OK
    log.info("%s: new month ends %s", table.name, [e.isoformat() for e in ends])
    stage = STAGE_ROOT / table.name
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir(parents=True, exist_ok=True)
    years = sorted({e.year for e in ends})
    backups = {}
    for y in years:
        cur = root / f"{y}.parquet"
        if cur.exists():
            backups[y] = _backup_path(table, y, day)
            backups[y].parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cur, backups[y])
    for step in steps:
        if step.kind == "run" and run_command(step, runner) != 0:
            return EXIT_COMMAND
    composed: dict[int, Path] = {}
    for y in years:
        built = stage / f"{y}.parquet"
        if not built.exists():
            log.error("%s: builder wrote no %s partition", table.name, y)
            return EXIT_COMMAND
        staged = pl.read_parquet(built)
        old = pl.read_parquet(backups[y]) if y in backups else staged.head(0)
        out_dir = stage / "composed"
        out_dir.mkdir(exist_ok=True)
        composed[y] = out_dir / f"{y}.parquet"
        compose_monthly(old, staged, [e for e in ends if e.year == y]).write_parquet(composed[y])
        if y in backups:
            report = BACKUP_ROOT / day.isoformat() / f"check_{table.name}_{y}.json"
            cut = max(_dates_of(backups[y], table.date_col))
            rc = run_command(
                Step(
                    f"up:{table.name}",
                    "check",
                    check_command(table, backups[y], composed[y], cut, report),
                ),
                runner,
            )
            if rc != 0:
                log.error(
                    "%s: old months changed in the composed %s partition; nothing swapped",
                    table.name,
                    y,
                )
                shutil.rmtree(stage, ignore_errors=True)
                return EXIT_UPSTREAM
    for y, path in composed.items():
        shutil.copy2(path, root / f"{y}.parquet")
    shutil.rmtree(stage, ignore_errors=True)
    log.info("%s: swapped in %s", table.name, [e.isoformat() for e in ends])
    return EXIT_OK


def run_upstream_table(
    table: Table,
    day: date,
    steps: Sequence[Step],
    runner: Runner,
    *,
    extra_years: Sequence[int] = (),
    member_cut: date | None = None,
) -> int:
    """Backup, fetch, build, check, swap one table.  0 ok, 3 check failed, 4 command failed."""
    if table.monthly:
        return run_monthly_table(table, day, steps, runner)
    year = day.year
    out = FEATURES / table.output.format(year=year)
    backup = _backup_path(table, year, day)
    had_old = out.exists()
    if had_old:
        _backup_once(out, backup)
    stage = STAGE_ROOT / table.name
    if not table.in_place:
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True, exist_ok=True)
        if table.link_prior_years:
            # copies, never symlinks: a builder that rewrites a prior year would write through a
            # link into the live feature file (it did, for `universe`, in the first e2e run)
            src = out.parent
            for p in sorted(src.glob("[0-9][0-9][0-9][0-9].parquet")):
                if int(p.stem) < year:
                    shutil.copy2(p, stage / p.name)
    for step in steps:
        if step.kind == "run" and run_command(step, runner) != 0:
            if table.in_place and had_old:
                shutil.copy2(backup, out)
            return EXIT_COMMAND
    new = out if table.in_place else stage / out.name
    if table.check != "none" and had_old and new.exists():
        old_dates = _dates_of(backup, table.date_col)
        cut = strict_cut(old_dates) if table.check == "price" else max(old_dates)
        if table.values_follow and cut is not None:
            zone = strict_cut(old_dates)
            if zone is not None and zone < cut:
                log.info(
                    "%s: gate stops at %s (two zones of %s)", table.name, zone, table.values_follow
                )
                cut = zone
        if cut is not None and member_cut is not None and member_cut < cut:
            log.info(
                "%s: gate stops at %s (new month end re-members later rows)", table.name, member_cut
            )
            cut = member_cut
        if cut is not None:
            report = BACKUP_ROOT / day.isoformat() / f"check_{table.name}.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            allow_new = allow_old = None
            if "symbol" in table.keys.split(","):
                entrants = new_entrant_symbols(backup, new)
                rebased = (
                    rebased_symbols(replaced_partitions(day)) if table.keys_follow_prices else []
                )
                if entrants or rebased:
                    allow_new = report.with_name(f"allow_new_{table.name}.txt")
                    allow_new.write_text("\n".join(sorted({*entrants, *rebased})) + "\n")
                if rebased:
                    allow_old = report.with_name(f"allow_old_{table.name}.txt")
                    allow_old.write_text("\n".join(rebased) + "\n")
                if entrants or rebased:
                    log.info(
                        "%s: keys allowed for %d new-entrant and %d re-based symbols",
                        table.name,
                        len(entrants),
                        len(rebased),
                    )
            exclude = None
            if table.values_follow:
                restated = restated_symbols(replaced_partitions(day, table.values_follow))
                if restated:
                    exclude = report.with_name(f"exclude_{table.name}.txt")
                    exclude.write_text("\n".join(restated) + "\n")
                    log.info(
                        "%s: %d symbols restated in %s left out of the changed share",
                        table.name,
                        len(restated),
                        table.values_follow,
                    )
            rc = run_command(
                Step(
                    f"up:{table.name}",
                    "check",
                    check_command(table, backup, new, cut, report, allow_new, allow_old, exclude),
                ),
                runner,
            )
            if rc != 0:
                log.error(
                    "%s: invariance check failed (exit %s); restoring the backup", table.name, rc
                )
                shutil.copy2(backup, out)
                shutil.rmtree(stage, ignore_errors=True)
                return EXIT_UPSTREAM
    if not table.in_place and new.exists():
        shutil.copy2(new, out)
    log.info("%s: swapped in (%s)", table.name, "in place" if table.in_place else out.name)
    if table.name == "daily_broad":
        # split-type restatement: the whole history of the symbol was re-based, so the earlier
        # partitions are replaced too (no row gate: a re-based partition is meant to differ)
        for y in extra_years:
            older, staged = out.parent / f"{y}.parquet", stage / f"{y}.parquet"
            if staged.exists() and older.exists():
                _backup_once(older, _backup_path(table, y, day))
                shutil.copy2(staged, older)
    shutil.rmtree(stage, ignore_errors=True)
    return EXIT_OK


def run_plan(
    day: date,
    plan: Sequence[Step],
    runner: Runner = subprocess.run,
    *,
    extra_years: Sequence[int] = (),
    member_cut: date | None = None,
) -> int:
    by_stage: dict[str, list[Step]] = {}
    for step in plan:
        by_stage.setdefault(step.stage, []).append(step)
    for stage, steps in by_stage.items():
        if stage.startswith("up:"):
            code = run_upstream_table(
                table_by_name(stage[3:]),
                day,
                steps,
                runner,
                extra_years=extra_years,
                member_cut=member_cut,
            )
            if code != EXIT_OK:
                return code
            continue
        for step in steps:
            if step.kind == "merge":
                log.info("merge formation_ic")
                merge_formation_ic()
            elif run_command(step, runner) != 0:
                return EXIT_COMMAND
    return EXIT_OK


def setup_logging(path: Path = LOG_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)sZ %(levelname)s %(message)s", "%Y-%m-%dT%H:%M:%S")
    fmt.converter = time.gmtime
    for handler in (logging.FileHandler(path), logging.StreamHandler(sys.stdout)):
        handler.setFormatter(fmt)
        log.addHandler(handler)
    log.setLevel(logging.INFO)


def portfolio_universe() -> set[str] | None:
    """Symbols of the live panel universe (current year), or None when no panel exists yet."""
    import pyarrow.parquet as pq

    year = date.today().year
    path = LIVE / f"panel/{year}.parquet"
    if not path.exists():
        return None
    return set(pq.read_table(path, columns=["symbol"]).column("symbol").unique().to_pylist())


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the plan, do nothing")
    ap.add_argument("--check", action="store_true", help="only write _freshness.json")
    ap.add_argument(
        "--init-cursor",
        action="store_true",
        help="set the restatement cursor to the end of _restatements.jsonl and exit",
    )
    ap.add_argument("--day", default=None, help="session to refresh to (default: latest closed)")
    ap.add_argument(
        "--tables", default=None, help="upstream tables to refresh, comma separated (default: all)"
    )
    ap.add_argument("--no-fetch", action="store_true", help="skip the upstream fetch commands")
    ap.add_argument("--no-upstream", action="store_true", help="live layer only")
    ap.add_argument("--stages", default=",".join(LIVE_STAGES), help="live stages, comma separated")
    ap.add_argument("--lock-file", default=str(LOCK_FILE))
    ap.add_argument("--log-file", default=str(LOG_FILE))
    args = ap.parse_args(argv)

    day = date.fromisoformat(args.day) if args.day else expected_session()
    stages = [s for s in args.stages.split(",") if s]
    bad = [s for s in stages if s not in LIVE_STAGES]
    if bad:
        ap.error(f"unknown stages: {bad}")
    tables: Sequence[Table] = UPSTREAM
    if args.tables:
        wanted = [t for t in args.tables.split(",") if t]
        unknown = [t for t in wanted if t not in {x.name for x in UPSTREAM}]
        if unknown:
            ap.error(f"unknown tables: {unknown}")
        tables = [t for t in UPSTREAM if t.name in wanted]

    if args.dry_run:
        for step in build_plan(
            day,
            tables=tables,
            stages=stages,
            fetch=not args.no_fetch,
            upstream=not args.no_upstream,
        ):
            print(step.text())
        return EXIT_OK

    setup_logging(Path(args.log_file))
    if args.init_cursor:
        count = init_cursor()
        log.info("restatement cursor set to %d lines (%s)", count, STATE_FILE)
        return EXIT_OK
    try:
        lock = FileLock(Path(args.lock_file))
        lock.__enter__()
    except RefreshLocked:
        log.error("another refresh holds %s", args.lock_file)
        return EXIT_LOCKED
    try:
        sip_last = latest_sip_date()
        if args.check:
            payload = freshness(LIVE, sip_last, day.year)
            payload["upstream"] = upstream_last_dates(FEATURES, day.year, sip_last)
            path = write_freshness(LIVE, payload)
            log.info("wrote %s", path)
            return EXIT_OK
        if sip_last is None or sip_last < day:
            log.info("SIP archive ends %s, before session %s: nothing to do", sip_last, day)
            return EXIT_NOT_FRESH
        cursor = read_cursor()
        if cursor is None:
            log.warning(
                "no restatement cursor %s: restatements are not processed (run --init-cursor once)",
                STATE_FILE,
            )
            records, offset = [], None
        else:
            records, offset = new_split_restatements(
                SIP_DAILY / "_restatements.jsonl", cursor, portfolio_universe()
            )
        extra_years = restatement_years(records, day.year)
        if records:
            log.warning(
                "split-type restatements for %s; rebuilding daily_broad %s too",
                sorted({r["symbol"] for r in records}),
                extra_years,
            )
        plan = build_plan(
            day,
            tables=tables,
            stages=stages,
            fetch=not args.no_fetch,
            upstream=not args.no_upstream,
            extra_daily_years=extra_years,
        )
        code = run_plan(
            day,
            plan,
            extra_years=extra_years,
            member_cut=membership_cut(),
        )
        payload = freshness(LIVE, sip_last, day.year)
        payload["upstream"] = upstream_last_dates(FEATURES, day.year, sip_last)
        write_freshness(LIVE, payload)
        if code == EXIT_OK:
            month_end = last_universe_month_end()
            write_state(
                last_day=day.isoformat(),
                universe_month_end=month_end.isoformat() if month_end else None,
            )
            if offset is not None:
                write_cursor(offset, day)
        return code
    finally:
        lock.__exit__()


if __name__ == "__main__":
    sys.exit(main())
