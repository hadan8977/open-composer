"""The report centre (``/reports``, 2026-10-04 information-architecture pass).

Three kinds of owner-facing report, each already written to disk by something
else -- this module only lists and renders them, never generates one:

* ``daily``  -- ``logs/owner-report/daily-<UTC date>.md``, written by
  ``scripts/owner_report.py`` (not in git);
* ``weekly`` -- the lead round's judgement ``reports/owner/weekly/<ISO week>.zh.md``
  plus the script's data appendix ``logs/owner-report/weekly-<UTC date>.md``,
  joined by ISO week (either half may be missing);
* ``rounds`` -- ``reports/owner/rounds/<UTC time>-<lead|exec>.md``, one per
  autonomous round from 2026-10-05 on.

Every id an operator can type into a URL is matched against a strict pattern
*before* it becomes a path, and the path still goes through ``safe_repo_path``.
Markdown is rendered with ``markdown_it`` (tables, ordered and nested lists --
the hypothesis-card renderer in ``open_composer.cockpit.markdown`` deliberately
supports neither) after ``secret_scrub``; raw HTML in a report is escaped, not
passed through. Like every cockpit data module this never raises for a missing
or unreadable file: the entry says so and the page shows it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from open_composer.cockpit.security import PathTraversalError, safe_repo_path, secret_scrub

DAILY_DIR = Path("logs/owner-report")
WEEKLY_DIR = Path("reports/owner/weekly")
ROUNDS_DIR = Path("reports/owner/rounds")

KINDS: tuple[str, ...] = ("daily", "weekly", "rounds")
KIND_LABELS: dict[str, str] = {"daily": "Daily", "weekly": "Weekly", "rounds": "Rounds"}

DAILY_ID_RE = re.compile(r"^daily-(\d{4}-\d{2}-\d{2})$")
WEEKLY_DATA_RE = re.compile(r"^weekly-(\d{4}-\d{2}-\d{2})\.md$")
WEEKLY_ID_RE = re.compile(r"^(\d{4})-W(\d{2})$")
ROUND_ID_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})Z-(lead|exec)$")

#: Reports larger than this are cut before rendering; the page says so.
MAX_REPORT_CHARS = 400_000
_BULLET_CHARS = 150


@dataclass(frozen=True)
class ReportEntry:
    """One report in the index -- enough to draw its list row."""

    kind: str  # "daily" | "weekly" | "rounds"
    id: str  # the URL segment, already pattern-checked
    title: str  # first `# ` heading, scrubbed; falls back to a label
    at: datetime  # when the report is *about* (UTC), for ordering
    paths: tuple[str, ...]  # repo-relative files behind this entry, main first
    note: str = ""  # "lead round", "data only", ...

    @property
    def href(self) -> str:
        return f"/reports/{self.kind}/{self.id}"

    @property
    def is_lead(self) -> bool:
        return self.kind == "rounds" and self.id.endswith("-lead")


@dataclass(frozen=True)
class ReportIndex:
    generated_at: datetime
    daily: tuple[ReportEntry, ...]  # newest first
    weekly: tuple[ReportEntry, ...]
    rounds: tuple[ReportEntry, ...]
    warnings: tuple[str, ...] = ()

    def by_kind(self, kind: str) -> tuple[ReportEntry, ...]:
        return {"daily": self.daily, "weekly": self.weekly, "rounds": self.rounds}.get(kind, ())

    @property
    def total(self) -> int:
        return len(self.daily) + len(self.weekly) + len(self.rounds)

    @property
    def newest(self) -> ReportEntry | None:
        """The report to open first on a wide screen: today's daily, else the newest of any kind."""
        everything = sorted(
            (*self.daily, *self.weekly, *self.rounds), key=lambda e: e.at, reverse=True
        )
        return everything[0] if everything else None

    def find(self, kind: str, report_id: str) -> ReportEntry | None:
        return next((e for e in self.by_kind(kind) if e.id == report_id), None)

    @property
    def latest_lead_round(self) -> ReportEntry | None:
        return next((e for e in self.rounds if e.is_lead), None)


@dataclass(frozen=True)
class ReportDoc:
    """One rendered report: the entry, its HTML, and any appendix."""

    entry: ReportEntry
    html: str  # already escaped and secret-scrubbed; template marks it safe
    appendix_html: str | None  # weekly: the script's data half
    modified_at: datetime | None
    chars: int
    truncated: bool
    error: str | None  # unreadable file, etc.; html is then empty


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def iso_week_of(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def _week_anchor(week_id: str) -> datetime | None:
    """The Sunday that ends ISO week ``week_id`` (the weekly is sent that day), midnight UTC."""
    match = WEEKLY_ID_RE.match(week_id)
    if not match:
        return None
    year, week = int(match.group(1)), int(match.group(2))
    try:
        sunday = date.fromisocalendar(year, week, 7)
    except ValueError:
        return None
    return datetime(sunday.year, sunday.month, sunday.day, tzinfo=UTC)


def report_title(text: str, fallback: str) -> str:
    """The first ``# `` heading of a markdown document, scrubbed; ``fallback`` otherwise."""
    for line in text.splitlines()[:20]:
        stripped = line.strip()
        if stripped.startswith("# "):
            return secret_scrub(stripped[2:].strip().replace("**", "")) or fallback
    return fallback


def report_bullets(text: str, limit: int = 3) -> tuple[str, ...]:
    """The first ``limit`` top-level bullets after the title (bold markers dropped)."""
    bullets: list[str] = []
    for line in text.splitlines():
        if line.startswith("- ") or line.startswith("* "):
            body = " ".join(line[2:].replace("**", "").split())
            if body:
                bullets.append(_clip(secret_scrub(body)))
        if len(bullets) >= limit:
            break
    return tuple(bullets)


def _clip(text: str, limit: int = _BULLET_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def render_report_markdown(text: str) -> str:
    """CommonMark + tables, raw HTML escaped, secrets scrubbed first.

    Separate from :func:`open_composer.reports.owner_digest.markdown_to_html`
    (which wraps a whole e-mail page around the body) and from the card
    renderer in ``open_composer.cockpit.markdown`` (no ordered/nested lists).
    """
    from markdown_it import MarkdownIt

    parser = MarkdownIt("commonmark", {"html": False, "linkify": False})
    parser.enable("table").enable("strikethrough")
    return parser.render(secret_scrub(text))


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------


def _read_text(path: Path) -> tuple[str | None, str | None]:
    """(text, error)."""
    try:
        return path.read_text(encoding="utf-8", errors="replace"), None
    except OSError as exc:
        return None, f"{type(exc).__name__}: cannot read {path.name}"


def _mtime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    except OSError:
        return None


def _head(path: Path, limit: int = 4096) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as handle:
            return handle.read(limit)
    except OSError:
        return ""


def _list_daily(root: Path, warnings: list[str]) -> list[ReportEntry]:
    folder = root / DAILY_DIR
    if not folder.is_dir():
        return []
    entries: list[ReportEntry] = []
    for path in folder.glob("daily-*.md"):
        match = DAILY_ID_RE.match(path.stem)
        if not match:
            continue
        try:
            day = date.fromisoformat(match.group(1))
        except ValueError:
            warnings.append(f"skipped {path.name}: not a date")
            continue
        title = report_title(_head(path), f"Daily {day.isoformat()}")
        entries.append(
            ReportEntry(
                kind="daily",
                id=path.stem,
                title=title,
                at=datetime(day.year, day.month, day.day, tzinfo=UTC),
                paths=(str(DAILY_DIR / path.name),),
                note="",
            )
        )
    return entries


def _list_weekly(root: Path, warnings: list[str]) -> list[ReportEntry]:
    judgements: dict[str, Path] = {}
    folder = root / WEEKLY_DIR
    if folder.is_dir():
        for path in folder.glob("*.zh.md"):
            week_id = path.name[: -len(".zh.md")]
            if WEEKLY_ID_RE.match(week_id) and _week_anchor(week_id) is not None:
                judgements[week_id] = path
            else:
                warnings.append(f"skipped {path.name}: not an ISO week")
    data: dict[str, Path] = {}
    daily_dir = root / DAILY_DIR
    if daily_dir.is_dir():
        for path in daily_dir.glob("weekly-*.md"):
            match = WEEKLY_DATA_RE.match(path.name)
            if not match:
                continue
            try:
                day = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            # a Sunday send belongs to the week that just ended
            data[iso_week_of(day - timedelta(days=1))] = path
    entries: list[ReportEntry] = []
    for week_id in sorted(set(judgements) | set(data)):
        anchor = _week_anchor(week_id)
        if anchor is None:
            continue
        paths: list[str] = []
        if week_id in judgements:
            paths.append(str(WEEKLY_DIR / judgements[week_id].name))
        if week_id in data:
            paths.append(str(DAILY_DIR / data[week_id].name))
        if week_id in judgements:
            title = report_title(_head(judgements[week_id]), f"Week {week_id}")
            note = "judgement + data" if week_id in data else "judgement"
        else:
            title = report_title(_head(data[week_id]), f"Week {week_id}")
            note = "data only"
        entries.append(
            ReportEntry(
                kind="weekly", id=week_id, title=title, at=anchor, paths=tuple(paths), note=note
            )
        )
    return entries


def _list_rounds(root: Path, warnings: list[str]) -> list[ReportEntry]:
    folder = root / ROUNDS_DIR
    if not folder.is_dir():
        return []
    entries: list[ReportEntry] = []
    for path in folder.glob("*.md"):
        match = ROUND_ID_RE.match(path.stem)
        if not match:
            if path.name != "README.md":
                warnings.append(f"skipped {path.name}: not a round file name")
            continue
        day, hour, minute, kind = match.groups()
        try:
            at = datetime.fromisoformat(f"{day}T{hour}:{minute}").replace(tzinfo=UTC)
        except ValueError:
            warnings.append(f"skipped {path.name}: not a time")
            continue
        label = "Lead round" if kind == "lead" else "Exec round"
        title = report_title(_head(path), f"{label} {at:%Y-%m-%d %H:%M} UTC")
        entries.append(
            ReportEntry(
                kind="rounds",
                id=path.stem,
                title=title,
                at=at,
                paths=(str(ROUNDS_DIR / path.name),),
                note="lead round" if kind == "lead" else "exec round",
            )
        )
    return entries


def build_report_index(root: Path, *, now: datetime | None = None) -> ReportIndex:
    """List every report on disk, newest first within each kind. Cheap: one
    directory walk per kind plus the first 4 KiB of each file for its title."""
    warnings: list[str] = []
    newest_first = lambda items: tuple(sorted(items, key=lambda e: e.at, reverse=True))  # noqa: E731
    return ReportIndex(
        generated_at=now or datetime.now(UTC),
        daily=newest_first(_list_daily(root, warnings)),
        weekly=newest_first(_list_weekly(root, warnings)),
        rounds=newest_first(_list_rounds(root, warnings)),
        warnings=tuple(warnings),
    )


def valid_report_id(kind: str, report_id: str) -> bool:
    if kind == "daily":
        return bool(DAILY_ID_RE.match(report_id))
    if kind == "weekly":
        return bool(WEEKLY_ID_RE.match(report_id))
    if kind == "rounds":
        return bool(ROUND_ID_RE.match(report_id))
    return False


def load_report(root: Path, entry: ReportEntry) -> ReportDoc:
    """Render one indexed report. Every path is re-checked with ``safe_repo_path``."""
    rendered: list[str] = []
    errors: list[str] = []
    modified: datetime | None = None
    chars = 0
    truncated = False
    for rel in entry.paths:
        try:
            path = safe_repo_path(rel, root=root)
        except PathTraversalError as exc:
            errors.append(str(exc))
            rendered.append("")
            continue
        text, error = _read_text(path)
        if text is None:
            errors.append(error or f"cannot read {rel}")
            rendered.append("")
            continue
        chars += len(text)
        if len(text) > MAX_REPORT_CHARS:
            text = text[:MAX_REPORT_CHARS]
            truncated = True
        rendered.append(render_report_markdown(text))
        stamp = _mtime(path)
        if stamp is not None and (modified is None or stamp > modified):
            modified = stamp
    html = rendered[0] if rendered else ""
    appendix = rendered[1] if len(rendered) > 1 and rendered[1] else None
    return ReportDoc(
        entry=entry,
        html=html,
        appendix_html=appendix,
        modified_at=modified,
        chars=chars,
        truncated=truncated,
        error="; ".join(errors) or None,
    )


def latest_report_text(root: Path, entry: ReportEntry) -> str:
    """Raw (scrubbed) text of an entry's main file, for the Today tile's bullets."""
    try:
        path = safe_repo_path(entry.paths[0], root=root)
    except (PathTraversalError, IndexError):
        return ""
    text, _error = _read_text(path)
    return secret_scrub(text or "")


__all__ = [
    "DAILY_DIR",
    "KIND_LABELS",
    "KINDS",
    "ROUNDS_DIR",
    "WEEKLY_DIR",
    "ReportDoc",
    "ReportEntry",
    "ReportIndex",
    "build_report_index",
    "iso_week_of",
    "latest_report_text",
    "load_report",
    "render_report_markdown",
    "report_bullets",
    "report_title",
    "valid_report_id",
]
