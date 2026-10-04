"""The Today screen (``/``, 2026-10-04 information-architecture pass).

Four questions, in this order, and nothing else: what needs the owner, how
the money is doing, how far each candidate is from live, what research is
doing. Every number comes from the same place the daily e-mail gets it --
``open_composer.reports.owner_digest`` -- so the page and the mail can never
disagree; the live-track file ``reports/owner/live-track.json`` (kept by the
lead rounds and the interactive session) supplies the candidates, engines and
owner decisions; the report centre supplies the newest lead-round headline.

``collect_digest`` costs 5-10 s on this box (paper ledgers, health scan, a
Modal billing subprocess), so it never runs on a request. :class:`TodayCache`
holds the last snapshot per repo root and the app's warm thread refreshes it
every ``TODAY_REFRESH_SECONDS``; a request only reads. Before the first
refresh lands the page says it is still collecting. Like every cockpit data
module this renders no HTML and never raises for a missing source.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.cockpit.data.reports import (
    ReportEntry,
    ReportIndex,
    build_report_index,
    latest_report_text,
    report_bullets,
)
from open_composer.cockpit.security import secret_scrub
from open_composer.reports.owner_digest import (
    CURRENT_VIEW,
    DigestData,
    SleeveRow,
    ViewSection,
    combined_returns,
    ops_items,
    owner_items,
    paper_sessions_since,
    parse_view_sections,
    sleeve_returns,
    spy_returns,
)

TODAY_REFRESH_SECONDS = 300.0
PAPER_SESSIONS_NEEDED = 10
_HEADLINE_BULLETS = 3
_DECISION_PREFIX = "待你决定"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    item: str
    due: date | None
    days_left: int | None


@dataclass(frozen=True)
class NeedsYou:
    level: str  # "ok" | "warn" | "stale"
    word: str  # "OK" | "Attention" | "Problem"
    items: tuple[str, ...]  # owner_items minus the decisions, same text as the mail
    decisions: tuple[Decision, ...]  # every dated owner decision, soonest first
    ops: tuple[str, ...]  # operational anomalies the research side handles


@dataclass(frozen=True)
class SleeveLine:
    name: str
    label: str
    nav: float
    budget: float
    day: float | None
    week: float | None
    since: float | None
    spy_since: float | None
    start: date
    sessions: int
    spark: tuple[float, ...]  # value / budget - 1 per observed close, oldest first
    holdings: tuple[tuple[str, float], ...]

    @property
    def href(self) -> str:
        return f"/paper/{self.name}"


@dataclass(frozen=True)
class BookLine:
    account: str
    equity: float | None
    net_pnl: float | None
    net_return: float | None
    latest_daily: str | None

    @property
    def trading(self) -> bool:
        return self.equity is not None


@dataclass(frozen=True)
class MoneyBlock:
    as_of: date | None  # last session with a close
    total: float | None
    budget_total: float | None
    day: float | None
    week: float | None
    since: float | None  # sum of sleeve values over sum of budgets
    spy_day: float | None
    spy_week: float | None
    sleeves: tuple[SleeveLine, ...]
    book: tuple[BookLine, ...]  # only accounts that have traded
    book_pending: tuple[str, ...]  # accounts configured but not trading yet
    live: tuple[str, ...]  # live strategies by label; empty = "Live: none"
    account_equity: float | None
    kill_switch: bool
    open_orders: int | None


@dataclass(frozen=True)
class Candidate:
    id: str
    label: str
    strategy: str
    stage: str
    paper_since: date | None
    paper_sessions: int | None
    next: str
    next_due: date | None
    proposal_due: date | None
    href: str | None

    @property
    def needed(self) -> int:
        return PAPER_SESSIONS_NEEDED

    @property
    def sessions_done(self) -> int:
        return min(self.paper_sessions or 0, PAPER_SESSIONS_NEEDED)

    @property
    def enough_sessions(self) -> bool:
        return (self.paper_sessions or 0) >= PAPER_SESSIONS_NEEDED


@dataclass(frozen=True)
class Engine:
    id: str
    name: str
    now: str
    next: str
    due: date | None


@dataclass(frozen=True)
class Headline:
    """The newest judgement: a lead-round report, else the newest dated
    section of ``docs/current-view.zh.md``."""

    source: str  # "round" | "view"
    label: str  # "Lead round" | "Exec round" | "Current view"
    title: str
    bullets: tuple[str, ...]
    at: datetime | None
    href: str


@dataclass(frozen=True)
class TodaySources:
    """What the cache holds: one digest collection plus the parsed view."""

    collected_at: datetime
    digest: DigestData | None
    error: str | None
    view_sections: tuple[ViewSection, ...]


@dataclass(frozen=True)
class TodayReport:
    generated_at: datetime
    collected_at: datetime | None  # None while the first collection is running
    needs: NeedsYou
    money: MoneyBlock
    candidates: tuple[Candidate, ...]
    engines: tuple[Engine, ...]
    decisions: tuple[Decision, ...]
    headline: Headline | None
    queue: dict[str, int]  # running / review / ready / blocked
    track_updated_at: str | None
    track_rule: str | None
    errors: tuple[str, ...]

    @property
    def loading(self) -> bool:
        return self.collected_at is None

    @property
    def age_seconds(self) -> float | None:
        if self.collected_at is None:
            return None
        return (self.generated_at - self.collected_at).total_seconds()


# ---------------------------------------------------------------------------
# Pure builders
# ---------------------------------------------------------------------------


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _text(value: Any) -> str:
    return secret_scrub(" ".join(str(value).split())) if value is not None else ""


def build_decisions(track: dict[str, Any] | None, today: date) -> tuple[Decision, ...]:
    out: list[Decision] = []
    for raw in (track or {}).get("owner_decisions") or []:
        if not isinstance(raw, dict) or not raw.get("item"):
            continue
        due = _date(raw.get("due"))
        out.append(Decision(_text(raw["item"]), due, (due - today).days if due else None))
    far = date.max
    return tuple(sorted(out, key=lambda d: d.due or far))


def needs_summary(needs: NeedsYou) -> str:
    """The line under the verdict word: every reason, or `Nothing needs you`."""
    parts: list[str] = []
    if needs.items:
        parts.append(f"{len(needs.items)} item{'s' * (len(needs.items) != 1)} for you")
    soon = [d for d in needs.decisions if d.days_left is not None and d.days_left <= 7]
    if soon:
        first = soon[0]
        when = (
            "today"
            if first.days_left == 0
            else (f"{-first.days_left}d late" if first.days_left < 0 else f"in {first.days_left}d")
        )
        parts.append(f"decision due {when}")
    elif needs.decisions:
        parts.append(f"{len(needs.decisions)} decision{'s' * (len(needs.decisions) != 1)} ahead")
    if needs.ops:
        parts.append(f"{len(needs.ops)} ops issue{'s' * (len(needs.ops) != 1)}")
    return " · ".join(parts) or "Nothing needs you"


def build_needs(
    data: DigestData | None, decisions: tuple[Decision, ...], error: str | None
) -> NeedsYou:
    """Problem = something stopped (kill switch, research paused by the quota
    gate, the digest itself failing); Attention = anything else that is
    listed; OK = nothing. A failed driver run or a stale feed is Attention:
    the research side fixes it, the owner only needs to know."""
    if data is None:
        items = (f"Report data unavailable: {error}",) if error else ()
        ops: tuple[str, ...] = ()
        stopped = False
    else:
        items = tuple(i for i in owner_items(data) if not i.startswith(_DECISION_PREFIX))
        ops = tuple(ops_items(data)) + tuple(f"汇报脚本自身问题：{e}" for e in data.errors)
        health = data.health
        stopped = (
            (data.account is not None and data.account.kill_switch_enabled)
            or bool(data.errors)
            or (health is not None and bool(health.gate_paused or health.gate_limits))
        )
    if stopped:
        level, word = "stale", "Problem"
    elif items or ops or any(d.days_left is not None and d.days_left <= 7 for d in decisions):
        level, word = "warn", "Attention"
    else:
        level, word = "ok", "OK"
    return NeedsYou(level, word, items, decisions, ops)


def sleeve_spark(row: SleeveRow) -> tuple[float, ...]:
    return tuple(nav / row.budget - 1.0 for _, nav in row.navs) if row.budget else ()


def build_money(data: DigestData | None, track: dict[str, Any] | None) -> MoneyBlock:
    live = tuple(
        _text(item.get("label") or item.get("id"))
        for item in (track or {}).get("live") or []
        if isinstance(item, dict)
    )
    if data is None:
        return MoneyBlock(
            None, None, None, None, None, None, None, None, (), (), (), live, None, False, None
        )
    sessions = data.sessions
    total, day, week = combined_returns(data.sleeves, sessions)
    spy_day, spy_week = spy_returns(data.spy_closes, sessions)
    budget_total = sum(row.budget for row in data.sleeves) or None
    since = (total / budget_total - 1.0) if total is not None and budget_total else None
    sleeves = []
    for row in data.sleeves:
        s_day, s_week = sleeve_returns(row, sessions)
        sleeves.append(
            SleeveLine(
                name=row.name,
                label=row.label,
                nav=row.nav,
                budget=row.budget,
                day=s_day,
                week=s_week,
                since=row.since_return,
                spy_since=row.spy_since,
                start=row.start_session,
                sessions=len(row.navs),
                spark=sleeve_spark(row),
                holdings=row.holdings,
            )
        )
    book = tuple(
        BookLine(a.account, a.equity, a.net_pnl, a.net_return, a.latest_daily) for a in data.book
    )
    return MoneyBlock(
        as_of=sessions[-1] if sessions else None,
        total=total,
        budget_total=budget_total,
        day=day,
        week=week,
        since=since,
        spy_day=spy_day,
        spy_week=spy_week,
        sleeves=tuple(sleeves),
        book=tuple(line for line in book if line.trading),
        book_pending=tuple(line.account for line in book if not line.trading),
        live=live,
        account_equity=data.account.equity if data.account else None,
        kill_switch=bool(data.account and data.account.kill_switch_enabled),
        open_orders=data.account.open_orders if data.account else None,
    )


def build_candidates(
    track: dict[str, Any] | None, data: DigestData | None
) -> tuple[Candidate, ...]:
    last = data.sessions[-1] if data and data.sessions else None
    sleeve_names = {row.name for row in data.sleeves} if data else set()
    out: list[Candidate] = []
    for raw in (track or {}).get("candidates") or []:
        if not isinstance(raw, dict) or not raw.get("id"):
            continue
        strategy = _text(raw.get("strategy"))
        since = raw.get("paper_since")
        out.append(
            Candidate(
                id=_text(raw["id"]),
                label=_text(raw.get("label") or raw["id"]),
                strategy=strategy,
                stage=_text(raw.get("stage") or "—"),
                paper_since=_date(since),
                paper_sessions=paper_sessions_since(str(since) if since else None, last),
                next=_text(raw.get("next") or ""),
                next_due=_date(raw.get("next_due")),
                proposal_due=_date(raw.get("proposal_due")),
                href=f"/paper/{strategy}" if strategy in sleeve_names else None,
            )
        )
    return tuple(out)


def build_engines(track: dict[str, Any] | None) -> tuple[Engine, ...]:
    return tuple(
        Engine(
            id=_text(raw.get("id") or ""),
            name=_text(raw.get("name") or raw.get("id") or "engine"),
            now=_text(raw.get("now") or ""),
            next=_text(raw.get("next") or ""),
            due=_date(raw.get("due")),
        )
        for raw in (track or {}).get("engines") or []
        if isinstance(raw, dict)
    )


def build_headline(
    root: Path, index: ReportIndex, sections: tuple[ViewSection, ...]
) -> Headline | None:
    entry: ReportEntry | None = index.latest_lead_round or (
        index.rounds[0] if index.rounds else None
    )
    if entry is not None:
        text = latest_report_text(root, entry)
        return Headline(
            source="round",
            label="Lead round" if entry.is_lead else "Exec round",
            title=entry.title,
            bullets=report_bullets(text, _HEADLINE_BULLETS),
            at=entry.at,
            href=entry.href,
        )
    if sections:
        newest = max(sections, key=lambda s: s.sort_key)
        at = None
        if newest.time:
            hour, minute = (int(part) for part in newest.time.split(":"))
            at = datetime(
                newest.day.year, newest.day.month, newest.day.day, hour, minute, tzinfo=UTC
            )
        else:
            at = datetime(newest.day.year, newest.day.month, newest.day.day, tzinfo=UTC)
        return Headline(
            source="view",
            label="Current view",
            title=secret_scrub(newest.title),
            bullets=tuple(secret_scrub(b) for b in newest.bullets[:_HEADLINE_BULLETS]),
            at=at,
            href="/research",
        )
    return None


def build_today_report(
    root: Path,
    *,
    sources: TodaySources | None,
    track: dict[str, Any] | None,
    index: ReportIndex,
    now: datetime | None = None,
) -> TodayReport:
    moment = now or datetime.now(UTC)
    data = sources.digest if sources else None
    error = sources.error if sources else None
    sections = sources.view_sections if sources else ()
    decisions = build_decisions(track, moment.date())
    queue = {"running": 0, "review": 0, "ready": 0, "blocked": 0}
    if data is not None:
        queue = {
            "running": len(data.running_tasks),
            "review": len(data.review_tasks),
            "ready": data.ready_count,
            "blocked": data.blocked_count,
        }
    errors: list[str] = []
    if error:
        errors.append(error)
    if track is None:
        errors.append("reports/owner/live-track.json missing or invalid")
    return TodayReport(
        generated_at=moment,
        collected_at=sources.collected_at if sources else None,
        needs=build_needs(data, decisions, error),
        money=build_money(data, track),
        candidates=build_candidates(track, data),
        engines=build_engines(track),
        decisions=decisions,
        headline=build_headline(root, index, sections),
        queue=queue,
        track_updated_at=_text((track or {}).get("updated_at")) or None,
        track_rule=_text((track or {}).get("rule")) or None,
        errors=tuple(errors),
    )


# ---------------------------------------------------------------------------
# I/O
# ---------------------------------------------------------------------------

LIVE_TRACK = Path("reports/owner/live-track.json")


def load_live_track(root: Path) -> dict[str, Any] | None:
    """The live-track file as a dict, or ``None`` when missing or not an object."""
    import json

    try:
        payload = json.loads((root / LIVE_TRACK).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def collect_today_sources(root: Path, now: datetime | None = None) -> TodaySources:
    """One full collection: the daily digest and the parsed current view.
    Slow (5-10 s); only the cache's refresh calls this."""
    from open_composer.reports.owner_digest import collect_digest

    moment = now or datetime.now(UTC)
    digest: DigestData | None = None
    error: str | None = None
    try:
        digest = collect_digest(root, moment, "daily")
    except Exception as exc:  # the page must render without the digest
        error = f"{type(exc).__name__}: {exc}"[:200]
    sections: tuple[ViewSection, ...] = ()
    try:
        sections = tuple(parse_view_sections((root / CURRENT_VIEW).read_text(encoding="utf-8")))
    except OSError:
        pass
    return TodaySources(collected_at=moment, digest=digest, error=error, view_sections=sections)


class TodayCache:
    """Last collection per repo root. ``get`` never collects; ``refresh`` does."""

    def __init__(self, collect=collect_today_sources) -> None:
        self._collect = collect
        self._lock = threading.Lock()
        self._entries: dict[Path, TodaySources] = {}

    def get(self, root: Path) -> TodaySources | None:
        with self._lock:
            return self._entries.get(root.resolve())

    def put(self, root: Path, sources: TodaySources) -> None:
        with self._lock:
            self._entries[root.resolve()] = sources

    def refresh(self, root: Path, now: datetime | None = None) -> TodaySources:
        sources = self._collect(root, now)
        self.put(root, sources)
        return sources

    def age_seconds(self, root: Path, now: datetime | None = None) -> float | None:
        entry = self.get(root)
        if entry is None:
            return None
        return ((now or datetime.now(UTC)) - entry.collected_at).total_seconds()


_DEFAULT_CACHE: TodayCache | None = None
_DEFAULT_LOCK = threading.Lock()


def get_default_today_cache() -> TodayCache:
    global _DEFAULT_CACHE
    with _DEFAULT_LOCK:
        if _DEFAULT_CACHE is None:
            _DEFAULT_CACHE = TodayCache()
        return _DEFAULT_CACHE


def today_report_for(
    root: Path, *, now: datetime | None = None, cache: TodayCache | None = None
) -> TodayReport:
    """What the route renders: cached sources (maybe none yet) plus the cheap
    per-request reads (live track, report index)."""
    source_cache = cache if cache is not None else get_default_today_cache()
    return build_today_report(
        root,
        sources=source_cache.get(root),
        track=load_live_track(root),
        index=build_report_index(root, now=now),
        now=now,
    )


__all__ = [
    "LIVE_TRACK",
    "PAPER_SESSIONS_NEEDED",
    "TODAY_REFRESH_SECONDS",
    "BookLine",
    "Candidate",
    "Decision",
    "Engine",
    "Headline",
    "MoneyBlock",
    "NeedsYou",
    "SleeveLine",
    "TodayCache",
    "TodayReport",
    "TodaySources",
    "build_candidates",
    "build_decisions",
    "build_engines",
    "build_headline",
    "build_money",
    "build_needs",
    "needs_summary",
    "build_today_report",
    "collect_today_sources",
    "get_default_today_cache",
    "load_live_track",
    "sleeve_spark",
    "today_report_for",
]
