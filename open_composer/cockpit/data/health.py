"""Pure data for the cockpit's health screen (Step 18, screen 5).

Nothing in this module renders HTML or touches Jinja2 -- `open_composer.cockpit.app`
is the only thing that imports both this module and the template engine. Every
function here is read-only: the only subprocesses it starts are the ones the
project's safety rules explicitly allow (`crontab -l`, `df`, `free`; see
`AGENTS.md` and section 6 of `docs/plan-step-18-readonly-cockpit-2026-09-19.zh.md`),
and every parquet read goes through footer/row-group *statistics* rather than
loading data pages, so a multi-hundred-MB archive costs kilobytes, not megabytes,
to inspect on this 3.9GB box.

Every field that describes the state of something carries a ``status`` of
``"ok" | "warn" | "stale" | "unknown"``. The vocabulary was designed for data
freshness (an ``ok``/``warn``/``stale`` staircase) and is reused as-is for disk,
memory, and cron so the whole page shares one traffic-light vocabulary; for
those non-freshness fields read ``"stale"`` as "critical, needs attention now"
rather than literally "old data". Each threshold is stated in a comment at its
call site rather than centralized, so nobody has to jump files to see why a
number is colored the way it is.
"""

from __future__ import annotations

import json
import os
import re
import resource
import subprocess
import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Literal

import pyarrow.parquet as pq

from open_composer.cockpit.security import secret_scrub
from open_composer.config import project_root

Status = Literal["ok", "warn", "stale", "unknown"]

# How much of a log's tail to read looking for an error marker. Read-only, and
# bounded well under the 50MB single-response budget in the plan's safety rules
# -- this is a `seek()` from the end, never a full read of a log that could be
# many MB after months of cron runs.
_LOG_TAIL_BYTES = 8_000

_ERROR_MARKER_RE = re.compile(r"(?i)\b(traceback|error|exception|failed|fatal)\b")

# Recognizes the five whitespace-separated cron time fields (minute hour dom
# month dow) so a crontab environment-variable line (`PATH=...`, `SHELL=...`)
# does not get misparsed as a job.
_CRON_LINE_RE = re.compile(
    r"^(?P<m>\S+)\s+(?P<h>\S+)\s+(?P<dom>\S+)\s+(?P<mon>\S+)\s+(?P<dow>\S+)\s+(?P<rest>.+)$"
)
_CRON_FIELD_RE = re.compile(r"^[\d*/,\-]+$")
_TRAILING_COMMENT_RE = re.compile(r"#\s*(.*)$")
_REDIRECT_RE = re.compile(r">>\s*(\S+)")


# --------------------------------------------------------------------------
# Cron jobs
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CronLogStatus:
    """One log file a cron job appends to under ``logs/``."""

    path: str  # display path, relative to the repo root
    exists: bool
    mtime: datetime | None
    size_bytes: int | None
    has_error_marker: bool
    tail_snippet: str | None  # already secret_scrub'd; last _LOG_TAIL_BYTES, best-effort decode
    status: Status


@dataclass(frozen=True)
class CronJob:
    name: str
    schedule: str
    command: str
    logs: tuple[CronLogStatus, ...]
    status: Status
    note: str | None = None  # e.g. "no log under logs/ configured for this job"


@dataclass(frozen=True)
class CronReport:
    jobs: tuple[CronJob, ...]
    available: bool  # False if `crontab -l` could not be read at all (no crontab, no binary, ...)
    error: str | None


def read_crontab() -> str:
    """Read the current user's crontab, read-only.

    Returns ``""`` if there is no crontab installed or the binary is missing --
    both are normal, not error, states for this screen (``crontab -l`` on an
    account with no crontab exits non-zero with "no crontab for <user>").
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout


def _derive_job_name(command: str) -> str:
    match = re.search(r"([\w.-]+\.(?:py|sh))\b", command)
    if match:
        return match.group(1)
    return command[:60].strip() or "unnamed job"


def _log_paths_under_logs(command: str, repo_root: Path) -> tuple[Path, ...]:
    """Every ``>> ...`` redirect target in ``command`` that resolves under ``logs/``.

    Cron entries in this repo always ``cd`` into the repo root first, so a
    relative ``logs/foo.log`` redirect means ``<repo_root>/logs/foo.log``.
    Redirects to ``/tmp/...`` (there are some, e.g. the SIP freshness check) are
    intentionally excluded -- the task is to watch the logs this repo owns.
    """
    found: list[Path] = []
    for match in _REDIRECT_RE.finditer(command):
        target = Path(match.group(1))
        if target.is_absolute():
            try:
                target.relative_to(repo_root / "logs")
            except ValueError:
                continue
            resolved = target
        else:
            if target.parts[:1] != ("logs",):
                continue
            resolved = repo_root / target
        if resolved not in found:
            found.append(resolved)
    return tuple(found)


def _read_log_tail(path: Path, max_bytes: int = _LOG_TAIL_BYTES) -> str:
    with path.open("rb") as handle:
        handle.seek(0, 2)
        size = handle.tell()
        handle.seek(max(0, size - max_bytes))
        chunk = handle.read()
    return chunk.decode("utf-8", errors="replace")


def _classify_log(exists: bool, has_error_marker: bool, age_days: float | None) -> Status:
    if not exists:
        return "unknown"
    if has_error_marker:
        return "warn"
    if age_days is None:
        return "unknown"
    # A cron log for a weekday job can legitimately be ~3 days old on a Monday
    # morning (Friday's run); >7 days means at least one full week of silence.
    if age_days <= 3:
        return "ok"
    if age_days <= 7:
        return "warn"
    return "stale"


def build_cron_log_status(path: Path, *, now: datetime | None = None) -> CronLogStatus:
    now = now or datetime.now(UTC)
    if not path.exists():
        return CronLogStatus(
            path=str(path),
            exists=False,
            mtime=None,
            size_bytes=None,
            has_error_marker=False,
            tail_snippet=None,
            status="unknown",
        )
    stat = path.stat()
    mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
    tail = _read_log_tail(path)
    has_error = bool(_ERROR_MARKER_RE.search(tail))
    age_days = (now - mtime).total_seconds() / 86400.0
    return CronLogStatus(
        path=str(path),
        exists=True,
        mtime=mtime,
        size_bytes=stat.st_size,
        has_error_marker=has_error,
        tail_snippet=secret_scrub(tail[-2_000:]),
        status=_classify_log(True, has_error, age_days),
    )


_STATUS_SEVERITY: dict[Status, int] = {"ok": 0, "unknown": 1, "warn": 2, "stale": 3}


def _worst_status(statuses: tuple[Status, ...]) -> Status:
    if not statuses:
        return "unknown"
    return max(statuses, key=lambda s: _STATUS_SEVERITY[s])


def summarize_statuses(statuses: tuple[Status, ...]) -> Status:
    """Roll many statuses up into the single worst one.

    Public so callers outside this module (the persistent top bar in
    ``open_composer.cockpit.app`` rolls up every data-freshness entry into one
    badge) do not need to reach into the private severity ordering above.
    """
    return _worst_status(statuses)


def parse_crontab(
    text: str, *, repo_root: Path | None = None, now: datetime | None = None
) -> tuple[CronJob, ...]:
    """Parse ``crontab -l`` output into structured jobs.

    Lines that are blank, full-line comments, or do not look like a five-field
    cron schedule (crontab environment-variable assignments such as ``PATH=``)
    are skipped rather than reported -- they are not jobs.
    """
    root = repo_root or project_root()
    jobs: list[CronJob] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            head, _, rest = line.partition(" ")
            schedule = head
            command_and_comment = rest.strip()
        else:
            match = _CRON_LINE_RE.match(line)
            if not match or not all(
                _CRON_FIELD_RE.match(match.group(field))
                for field in ("m", "h", "dom", "mon", "dow")
            ):
                continue
            schedule = " ".join(match.group(field) for field in ("m", "h", "dom", "mon", "dow"))
            command_and_comment = match.group("rest")

        comment_match = _TRAILING_COMMENT_RE.search(command_and_comment)
        if comment_match and comment_match.group(1).strip():
            name = comment_match.group(1).strip()
            command = command_and_comment[: comment_match.start()].strip()
        else:
            command = command_and_comment.strip()
            name = _derive_job_name(command)

        log_paths = _log_paths_under_logs(command, root)
        logs = tuple(build_cron_log_status(path, now=now) for path in log_paths)
        note = None if logs else "no log under logs/ configured for this job"
        jobs.append(
            CronJob(
                name=name,
                schedule=schedule,
                command=secret_scrub(command),
                logs=logs,
                status=_worst_status(tuple(log.status for log in logs)) if logs else "unknown",
                note=note,
            )
        )
    return tuple(jobs)


def build_cron_report(*, repo_root: Path | None = None) -> CronReport:
    raw = read_crontab()
    if not raw.strip():
        return CronReport(jobs=(), available=False, error="no crontab installed or readable")
    try:
        jobs = parse_crontab(raw, repo_root=repo_root)
    except Exception as exc:  # defensive: a parse bug must not crash the health page
        return CronReport(jobs=(), available=False, error=f"failed to parse crontab: {exc}")
    return CronReport(jobs=jobs, available=True, error=None)


# --------------------------------------------------------------------------
# Data freshness
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DataFreshnessEntry:
    name: str
    detail: str
    latest_date: date | None
    sessions_behind: int | None
    status: Status


#: `timeUnit` string (from a statistics logical-type's JSON) to ticks-per-second.
_TIME_UNIT_DIVISOR = {
    "seconds": 1,
    "milliseconds": 1_000,
    "microseconds": 1_000_000,
    "nanoseconds": 1_000_000_000,
}


def _stat_max_as_date(stats: object) -> date | None:
    """The max value of a parquet timestamp-column statistics object, as a
    plain :class:`datetime.date`, using only the standard library.

    PyArrow's ``Statistics.max``/``.min`` return a Python ``datetime`` for a
    timestamp column, but materializing that datetime imports pandas as a side
    effect the first time it happens -- measured at roughly 50MB resident on
    this box, more than a third of the app's whole memory budget, just to read
    one date out of a footer. ``.max_raw`` is the same instant as a plain
    Python ``int`` (ticks of ``timeUnit`` since the epoch) with no such side
    effect, so this reimplements the tick-to-date conversion by hand instead.
    Day-level granularity means the day-boundary imprecision from ignoring
    ``isAdjustedToUTC`` (at most a few hours) never matters here.
    """
    if stats is None or not stats.has_min_max:
        return None
    try:
        logical = json.loads(stats.logical_type.to_json())
    except (ValueError, AttributeError, TypeError):
        return None
    if logical.get("Type") != "Timestamp":
        return None
    divisor = _TIME_UNIT_DIVISOR.get(logical.get("timeUnit", ""))
    raw = stats.max_raw
    if divisor is None or raw is None:
        return None
    return datetime.fromtimestamp(raw / divisor, tz=UTC).date()


def _max_stat_date(path: Path, column: str) -> date | None:
    """Max ``date`` for ``column`` in ``path``, read from parquet footer/
    row-group statistics only -- no data pages are read, so this is safe to
    run against multi-hundred-shard directories on request.
    """
    try:
        parquet_file = pq.ParquetFile(path)
    except Exception:
        return None
    names = parquet_file.schema_arrow.names
    if column not in names:
        return None
    idx = names.index(column)
    best: date | None = None
    metadata = parquet_file.metadata
    for rg_index in range(metadata.num_row_groups):
        stats = metadata.row_group(rg_index).column(idx).statistics
        value = _stat_max_as_date(stats)
        if value is not None and (best is None or value > best):
            best = value
    return best


def _numeric_stem(path: Path) -> int:
    try:
        return int(path.stem)
    except ValueError:
        return -1


def latest_date_in_year_partitioned(
    dir_path: Path, date_column: str, *, probe_files: int = 2
) -> tuple[date | None, str]:
    """Latest ``date_column`` across the newest ``probe_files`` yearly parquet
    files (named literally ``YYYY.parquet``) directly under ``dir_path``.

    Only the most recent files are probed: the filename year is the partition
    key, so the maximum date can only live in the most recent file(s). Probing
    two covers the day a fresh year file exists but is nearly empty.
    """
    if not dir_path.is_dir():
        return None, f"{dir_path} does not exist"
    candidates = sorted(
        (p for p in dir_path.glob("*.parquet") if not p.name.startswith("_")),
        key=_numeric_stem,
        reverse=True,
    )
    if not candidates:
        return None, f"no parquet files directly under {dir_path} (build may be scratch-only)"
    best: date | None = None
    for path in candidates[:probe_files]:
        value = _max_stat_date(path, date_column)
        if value is not None and (best is None or value > best):
            best = value
    if best is None:
        return None, f"{date_column!r} column not found or unreadable in {candidates[0].name}"
    return best, f"from {candidates[0].name}"


def latest_date_in_sip_daily(sip_daily_root: Path) -> tuple[date | None, str]:
    if not sip_daily_root.is_dir():
        return None, f"{sip_daily_root} does not exist"
    year_dirs = sorted(
        (p for p in sip_daily_root.iterdir() if p.is_dir() and p.name.isdigit()),
        key=lambda p: int(p.name),
        reverse=True,
    )
    for year_dir in year_dirs[:2]:
        shard_files = sorted(year_dir.glob("*.parquet"))
        if not shard_files:
            continue
        best: date | None = None
        for shard in shard_files:
            value = _max_stat_date(shard, "timestamp")
            if value is not None and (best is None or value > best):
                best = value
        if best is not None:
            return best, f"from {year_dir.name}/ ({len(shard_files)} shards probed)"
    return None, f"no readable shard files under {sip_daily_root}"


def _is_weekday(day: date) -> bool:
    """Weekday-only approximation of a US equity trading session.

    ``scripts/check_sip_freshness.py`` uses the holiday-aware
    ``open_composer.market_calendar.us_equity_session_dates`` for its precise,
    one-shot exit-code decision. That module imports pandas at module scope,
    which is fine for a script that runs once from cron and exits but is not
    something the always-resident cockpit process should carry just to label a
    freshness badge -- measured at roughly 90MB resident on this box, more
    than half of the whole app's 150MB budget. Every ``warn_at``/``stale_after``
    threshold this approximation feeds already has multiple days of slack, so
    missing a market holiday shifts a "sessions behind" count by at most one
    and never flips a fresh archive to "stale" by itself.
    """
    return day.weekday() < 5


def _approx_session_dates(start: date, end: date) -> list[date]:
    if start > end:
        return []
    days = []
    current = start
    one_day = timedelta(days=1)
    while current <= end:
        if _is_weekday(current):
            days.append(current)
        current += one_day
    return days


def _last_completed_session(today: date) -> date | None:
    sessions = _approx_session_dates(today - timedelta(days=30), today)
    earlier = [session for session in sessions if session < today]
    return earlier[-1] if earlier else None


def _sessions_behind(latest: date, reference: date) -> int:
    if latest >= reference:
        return 0
    sessions = _approx_session_dates(latest, reference)
    return max(len([s for s in sessions if s > latest]), 0)


def _classify_freshness(sessions_behind: int | None, *, warn_at: int, stale_after: int) -> Status:
    if sessions_behind is None:
        return "unknown"
    if sessions_behind < warn_at:
        return "ok"
    if sessions_behind <= stale_after:
        return "warn"
    return "stale"


def _freshness_entry(
    name: str,
    latest: date | None,
    detail: str,
    *,
    today: date,
    warn_at: int,
    stale_after: int,
) -> DataFreshnessEntry:
    if latest is None:
        return DataFreshnessEntry(
            name=name, detail=detail, latest_date=None, sessions_behind=None, status="unknown"
        )
    reference = _last_completed_session(today) or today
    behind = _sessions_behind(latest, reference)
    status = _classify_freshness(behind, warn_at=warn_at, stale_after=stale_after)
    return DataFreshnessEntry(
        name=name,
        detail=f"{detail}; {behind} session(s) behind {reference.isoformat()}",
        latest_date=latest,
        sessions_behind=behind,
        status=status,
    )


# Factor-family directories known to publish a consolidated, year-partitioned
# table at their top level (as opposed to `alpha158_broad`, which as of
# 2026-09-19 only has in-progress `_scratch/<year>/batch-*.parquet` files and no
# consolidated table -- that one is reported as `unknown` with a reason instead
# of guessing at a path that does not exist yet).
FACTOR_FAMILIES: tuple[str, ...] = (
    "alpha101",
    "alpha101_broad",
    "alpha158",
    "alpha158_broad",
    "alpha191",
    "alpha191_broad",
    "osap_price",
    "reversal_trend",
)


def build_data_freshness(
    root: Path | None = None, *, today: date | None = None
) -> tuple[DataFreshnessEntry, ...]:
    base = root or project_root()
    ref_today = today or datetime.now(UTC).date()
    entries: list[DataFreshnessEntry] = []

    # SIP daily archive: matches scripts/check_sip_freshness.py's own
    # DEFAULT_MAX_STALE_SESSIONS=2 gate -- warn at 2 sessions behind, stale
    # beyond that (that script exits non-zero at exactly this point).
    sip_latest, sip_detail = latest_date_in_sip_daily(base / "data" / "sip" / "daily")
    entries.append(
        _freshness_entry(
            "SIP daily archive", sip_latest, sip_detail, today=ref_today, warn_at=2, stale_after=2
        )
    )

    # Insider (Form 4) features: a derived daily grid one step downstream of
    # SIP, so a slightly wider band (warn at 3, stale beyond 5) avoids flapping
    # on the same day SIP itself is momentarily behind.
    insider_latest, insider_detail = latest_date_in_year_partitioned(
        base / "data" / "features" / "insider", "trade_date"
    )
    entries.append(
        _freshness_entry(
            "Insider (Form 4) features",
            insider_latest,
            insider_detail,
            today=ref_today,
            warn_at=3,
            stale_after=5,
        )
    )

    # Short-interest features: also a derived daily grid (the underlying FINRA
    # series only moves twice a month, but the feature table forward-fills it
    # onto every session -- see open_composer/research/features/short_interest.py),
    # so the same derived-build band as insider applies.
    short_latest, short_detail = latest_date_in_year_partitioned(
        base / "data" / "features" / "short_interest", "trade_date"
    )
    entries.append(
        _freshness_entry(
            "Short-interest features",
            short_latest,
            short_detail,
            today=ref_today,
            warn_at=3,
            stale_after=5,
        )
    )

    # Factor tables: one entry per known family. Same derived-build band as
    # insider/short-interest.
    for family in FACTOR_FAMILIES:
        latest, detail = latest_date_in_year_partitioned(
            base / "data" / "features" / family, "trade_date"
        )
        entries.append(
            _freshness_entry(
                f"Factor table: {family}",
                latest,
                detail,
                today=ref_today,
                warn_at=3,
                stale_after=5,
            )
        )

    return tuple(entries)


# --------------------------------------------------------------------------
# Disk / memory / process
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class DiskStatus:
    mount: str
    total_bytes: int
    used_bytes: int
    available_bytes: int
    used_percent: float
    status: Status


@dataclass(frozen=True)
class MemoryStatus:
    total_bytes: int
    used_bytes: int
    available_bytes: int
    used_percent: float
    status: Status


@dataclass(frozen=True)
class ProcessStatus:
    pid: int
    rss_bytes: int
    status: Status


def _run_readonly(args: list[str]) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=5, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout


def build_disk_status(mount: str = "/") -> DiskStatus | None:
    output = _run_readonly(["df", "-k", mount])
    if not output:
        return None
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) < 2:
        return None
    fields = lines[-1].split()
    if len(fields) < 4:
        return None
    try:
        total_kb, used_kb, avail_kb = int(fields[1]), int(fields[2]), int(fields[3])
    except ValueError:
        return None
    total = total_kb * 1024
    used = used_kb * 1024
    available = avail_kb * 1024
    used_percent = (used / total * 100.0) if total else 0.0
    # This box has 3.9GB RAM and no room for a full disk; warn well before "no
    # space left" actually breaks a write, stale once it is nearly full.
    if used_percent >= 92:
        status: Status = "stale"
    elif used_percent >= 80:
        status = "warn"
    else:
        status = "ok"
    return DiskStatus(
        mount=mount,
        total_bytes=total,
        used_bytes=used,
        available_bytes=available,
        used_percent=used_percent,
        status=status,
    )


def build_memory_status() -> MemoryStatus | None:
    output = _run_readonly(["free", "-b"])
    if not output:
        return None
    mem_line = next((line for line in output.splitlines() if line.startswith("Mem:")), None)
    if not mem_line:
        return None
    fields = mem_line.split()
    if len(fields) < 7:
        return None
    try:
        total, used, _free, _shared, _buff_cache, available = (int(f) for f in fields[1:7])
    except ValueError:
        return None
    used_percent = (used / total * 100.0) if total else 0.0
    # earlyoom on this box prefers killing agent sessions well before the
    # kernel OOM killer would normally trigger, so warn early (80%) and treat
    # >92% as critical -- the same thresholds as disk, for one shared mental model.
    if used_percent >= 92:
        status: Status = "stale"
    elif used_percent >= 80:
        status = "warn"
    else:
        status = "ok"
    return MemoryStatus(
        total_bytes=total,
        used_bytes=used,
        available_bytes=available,
        used_percent=used_percent,
        status=status,
    )


def build_process_status() -> ProcessStatus:
    usage = resource.getrusage(resource.RUSAGE_SELF)
    # Linux reports ru_maxrss in KiB (it is bytes on macOS, but this box is Linux).
    rss_bytes = usage.ru_maxrss * 1024
    # The acceptance bar for this app is RSS < 150MB; warn on the way there so
    # the health screen catches a leak before the acceptance check would.
    if rss_bytes >= 300 * 1024 * 1024:
        status: Status = "stale"
    elif rss_bytes >= 150 * 1024 * 1024:
        status = "warn"
    else:
        status = "ok"
    return ProcessStatus(pid=os.getpid(), rss_bytes=rss_bytes, status=status)


# --------------------------------------------------------------------------
# Aggregate report
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HealthReport:
    generated_at: datetime
    cron: CronReport
    data_freshness: tuple[DataFreshnessEntry, ...]
    disk: DiskStatus | None
    memory: MemoryStatus | None
    process: ProcessStatus


def build_health_report(root: Path | None = None) -> HealthReport:
    """Assemble the full health screen data model.

    Each section is isolated in its own try/except: a missing crontab binary,
    an unreadable data directory, or a `df`/`free` that is not on PATH must
    degrade that one section to its own "unknown"/absent state rather than
    take down the whole page. This is exercised directly by
    ``tests/test_cockpit_app.py``'s "missing data source" case.
    """
    base = root or project_root()

    try:
        cron = build_cron_report(repo_root=base)
    except Exception as exc:
        cron = CronReport(jobs=(), available=False, error=f"cron report failed: {exc}")

    try:
        data_freshness = build_data_freshness(base)
    except Exception as exc:
        data_freshness = (
            DataFreshnessEntry(
                name="data freshness",
                detail=f"failed to compute: {exc}",
                latest_date=None,
                sessions_behind=None,
                status="unknown",
            ),
        )

    try:
        disk = build_disk_status()
    except Exception:
        disk = None

    try:
        memory = build_memory_status()
    except Exception:
        memory = None

    process = build_process_status()

    return HealthReport(
        generated_at=datetime.now(UTC),
        cron=cron,
        data_freshness=data_freshness,
        disk=disk,
        memory=memory,
        process=process,
    )


#: How long `DataFreshnessCache` reuses one scan. The sources are daily
#: archives, while the status strip and the Now screen render the rollup on
#: every request -- where a fresh parquet-footer scan (~0.5s on this box)
#: was the largest single cost of switching screens.
DATA_FRESHNESS_CACHE_TTL_SECONDS = 60.0


class DataFreshnessCache:
    """`build_data_freshness(root)`, reused for `DATA_FRESHNESS_CACHE_TTL_SECONDS`
    per root. The `/health` screen itself always scans fresh."""

    def __init__(self) -> None:
        self._entries: tuple[DataFreshnessEntry, ...] | None = None
        self._root: Path | None = None
        self._at: datetime | None = None
        self._lock = threading.Lock()

    def get(self, root: Path, *, now: datetime | None = None) -> tuple[DataFreshnessEntry, ...]:
        moment = now or datetime.now(UTC)
        with self._lock:
            if self._entries is not None and self._root == root and self._at is not None:
                age = (moment - self._at).total_seconds()
                if 0 <= age < DATA_FRESHNESS_CACHE_TTL_SECONDS:
                    return self._entries
            entries = build_data_freshness(root)
            self._entries, self._root, self._at = entries, root, moment
            return entries


_DEFAULT_DATA_FRESHNESS_CACHE = DataFreshnessCache()


def get_default_data_freshness_cache() -> DataFreshnessCache:
    return _DEFAULT_DATA_FRESHNESS_CACHE
