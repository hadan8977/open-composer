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
CAPPED = ["scripts/run_capped.sh", "--mem", "1.8G", "--"]
PY = ["uv", "run", "python"]
NEW_YORK = ZoneInfo("America/New_York")

EXIT_OK, EXIT_NOT_FRESH, EXIT_UPSTREAM, EXIT_COMMAND, EXIT_LOCKED = 0, 2, 3, 4, 6
SPLIT_REL_DIFF = 0.2
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
    in_place: bool = False
    check: str = "plain"
    link_prior_years: bool = False
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
        link_prior_years=True,
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
        link_prior_years=True,
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
        note="sue_eps/sue_rev may change for late 10-Qs entering the quarterly ladder (pitfall #62)",
    ),
    Table(
        "nsi",
        "nsi/nsi.parquet",
        "trade_date",
        "symbol,trade_date",
        build=(*PY, "scripts/build_nsi_signal.py"),
        in_place=True,
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
        out[table.name] = {
            "last_date": last.isoformat() if last else None,
            "reaches_sip_last": bool(
                last is not None and sip_last is not None and last >= sip_last
            ),
        }
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


def restatement_years(records: Sequence[dict], current_year: int) -> list[int]:
    years = sorted({int(y) for r in records for y in r.get("years_rewritten", [])})
    return [y for y in years if y < current_year]


# --------------------------------------------------------------------------
# execution
# --------------------------------------------------------------------------


Runner = Callable[..., subprocess.CompletedProcess]


def run_command(step: Step, runner: Runner = subprocess.run) -> int:
    env = {**os.environ, **step.env}
    log.info("run %s", step.text())
    proc = runner(step.argv, cwd=ROOT, env=env, capture_output=True, text=True, check=False)
    tail = (proc.stdout + proc.stderr).splitlines()[-6:]
    for line in tail:
        log.info("  %s", line)
    return proc.returncode


def table_by_name(name: str) -> Table:
    return next(t for t in UPSTREAM if t.name == name)


def check_command(table: Table, old: Path, new: Path, cut: date, out: Path) -> list[str]:
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


def _dates_of(path: Path, column: str) -> list[date]:
    import pyarrow.parquet as pq

    values = pq.read_table(path, columns=[column]).column(column).unique().to_pylist()
    return [v.date() if hasattr(v, "date") else v for v in values]


def run_upstream_table(
    table: Table,
    day: date,
    steps: Sequence[Step],
    runner: Runner,
    *,
    extra_years: Sequence[int] = (),
) -> int:
    """Backup, fetch, build, check, swap one table.  0 ok, 3 check failed, 4 command failed."""
    year = day.year
    out = FEATURES / table.output.format(year=year)
    backup = _backup_path(table, year, day)
    had_old = out.exists()
    if had_old:
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(out, backup)
    stage = STAGE_ROOT / table.name
    if not table.in_place:
        shutil.rmtree(stage, ignore_errors=True)
        stage.mkdir(parents=True, exist_ok=True)
        if table.link_prior_years:
            src = out.parent
            for p in sorted(src.glob("[0-9][0-9][0-9][0-9].parquet")):
                if int(p.stem) < year:
                    (stage / p.name).symlink_to(p)
    for step in steps:
        if step.kind == "run" and run_command(step, runner) != 0:
            if table.in_place and had_old:
                shutil.copy2(backup, out)
            return EXIT_COMMAND
    new = out if table.in_place else stage / out.name
    if table.check != "none" and had_old and new.exists():
        old_dates = _dates_of(backup, table.date_col)
        cut = strict_cut(old_dates) if table.check == "price" else max(old_dates)
        if cut is not None:
            report = BACKUP_ROOT / day.isoformat() / f"check_{table.name}.json"
            report.parent.mkdir(parents=True, exist_ok=True)
            rc = run_command(
                Step(f"up:{table.name}", "check", check_command(table, backup, new, cut, report)),
                runner,
            )
            if rc != 0:
                log.error(
                    "%s: invariance check failed (exit %s); restoring the backup", table.name, rc
                )
                shutil.copy2(backup, out)
                return EXIT_UPSTREAM
    if not table.in_place and new.exists():
        shutil.copy2(new, out)
    if table.name == "daily_broad":
        # split-type restatement: the whole history of the symbol was re-based, so the earlier
        # partitions are replaced too (no row gate: a re-based partition is meant to differ)
        for y in extra_years:
            older, staged = out.parent / f"{y}.parquet", stage / f"{y}.parquet"
            if staged.exists() and older.exists():
                kept = _backup_path(table, y, day)
                kept.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(older, kept)
                shutil.copy2(staged, older)
    return EXIT_OK


def run_plan(
    day: date,
    plan: Sequence[Step],
    runner: Runner = subprocess.run,
    *,
    extra_years: Sequence[int] = (),
) -> int:
    by_stage: dict[str, list[Step]] = {}
    for step in plan:
        by_stage.setdefault(step.stage, []).append(step)
    for stage, steps in by_stage.items():
        if stage.startswith("up:"):
            code = run_upstream_table(
                table_by_name(stage[3:]), day, steps, runner, extra_years=extra_years
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
    ap.add_argument("--day", default=None, help="session to refresh to (default: latest closed)")
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

    if args.dry_run:
        for step in build_plan(
            day, stages=stages, fetch=not args.no_fetch, upstream=not args.no_upstream
        ):
            print(step.text())
        return EXIT_OK

    setup_logging(Path(args.log_file))
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
        records, offset = new_split_restatements(
            SIP_DAILY / "_restatements.jsonl",
            int(json.loads(STATE_FILE.read_text()).get("restatement_offset", 0))
            if STATE_FILE.exists()
            else 0,
            portfolio_universe(),
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
            stages=stages,
            fetch=not args.no_fetch,
            upstream=not args.no_upstream,
            extra_daily_years=extra_years,
        )
        code = run_plan(day, plan, extra_years=extra_years)
        payload = freshness(LIVE, sip_last, day.year)
        payload["upstream"] = upstream_last_dates(FEATURES, day.year, sip_last)
        write_freshness(LIVE, payload)
        if code == EXIT_OK:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            STATE_FILE.write_text(
                json.dumps({"restatement_offset": offset, "last_day": day.isoformat()})
            )
        return code
    finally:
        lock.__exit__()


if __name__ == "__main__":
    sys.exit(main())
