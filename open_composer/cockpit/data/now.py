"""The Now screen: one glance across every other screen (2026-09-24 redesign).

Answers four questions in one view -- is anything wrong, what are the agents
doing, where is paper equity, how much budget is burning -- by composing the
other data modules rather than re-reading anything itself. Heavy sources the
app already caches (the agent list, the usage estimate, the live quota, the
activity field, data freshness) are passed in by the route; everything else
here is a cheap file read. Like every cockpit data module this never renders
HTML and never raises for a missing source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from open_composer.cockpit.data.activity import ActivityField
from open_composer.cockpit.data.agents import (
    AgentRecord,
    AgentsReport,
    HeavyJobsReport,
    LiveSession,
    build_live_session,
)
from open_composer.cockpit.data.health import (
    CronReport,
    DataFreshnessEntry,
    DiskStatus,
    MemoryStatus,
    Status,
    build_cron_report,
    build_disk_status,
    build_memory_status,
)
from open_composer.cockpit.data.hypotheses import Card, HypothesesReport, lane_status
from open_composer.cockpit.data.paper import (
    AccountEquityHistory,
    AccountSnapshot,
    KillSwitchStatus,
    build_account_equity_history,
    discover_strategy_names,
    load_account_snapshot,
    load_authorization,
    load_kill_switch,
    load_open_order_count,
)
from open_composer.cockpit.data.quota import TopbarQuota, UsageEstimate

#: Research lanes folded into the four stages a glance needs. `unclassified`
#: gets its own stage only when a card actually lands there.
STAGES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("queued", "Queued", ("proposed", "approved", "preregistered")),
    ("running", "Running", ("running",)),
    ("shipped", "Shipped", ("shipped",)),
    ("closed", "Closed", ("refuted", "on hold", "data card")),
    ("unclassified", "Unclassified", ("unclassified",)),
)
_LIVE_SESSIONS = 2
_RECENT_CARDS = 3
_MAX_ATTENTION = 4
_AUTH_WARN_DAYS = 7.0


@dataclass(frozen=True)
class Attention:
    level: Status  # "stale" = act now, "warn" = look soon, "ok" = all clear
    text: str
    href: str


@dataclass(frozen=True)
class PipelineStage:
    key: str
    label: str
    count: int
    lanes: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class RecentCard:
    card: Card
    status: Status
    updated_at: datetime | None


@dataclass(frozen=True)
class ResearchGlance:
    stages: tuple[PipelineStage, ...]
    total: int
    recent: tuple[RecentCard, ...]


@dataclass(frozen=True)
class NowReport:
    generated_at: datetime
    equity: AccountEquityHistory
    account: AccountSnapshot
    kill_switch: KillSwitchStatus
    open_orders: int | None
    strategies: int
    authorized: int
    expired: int
    soonest_expiry_days: float | None
    agent_counts: dict[str, int]
    live: tuple[LiveSession, ...]
    last_active: LiveSession | None  # only when nothing is running
    errored: tuple[AgentRecord, ...]
    heavy: HeavyJobsReport
    research: ResearchGlance
    usage: UsageEstimate
    claude: TopbarQuota
    freshness: tuple[DataFreshnessEntry, ...]
    cron: CronReport
    disk: DiskStatus | None
    memory: MemoryStatus | None
    activity: ActivityField
    attention: tuple[Attention, ...]
    more_attention: int

    @property
    def stale_sources(self) -> int:
        return sum(1 for entry in self.freshness if entry.status == "stale")

    @property
    def failing_cron(self) -> int:
        return sum(1 for job in self.cron.jobs if job.status == "stale")


def summarize_research(report: HypothesesReport, root: Path) -> ResearchGlance:
    stages: list[PipelineStage] = []
    for key, label, lanes in STAGES:
        counts = tuple((lane, len(report.lanes.get(lane, ()))) for lane in lanes)
        count = sum(n for _, n in counts)
        if key == "unclassified" and not count:
            continue
        stages.append(PipelineStage(key=key, label=label, count=count, lanes=counts))

    dated: list[RecentCard] = []
    for card in report.cards:
        try:
            updated = datetime.fromtimestamp((root / card.path).stat().st_mtime, tz=UTC)
        except OSError:
            updated = None
        dated.append(RecentCard(card=card, status=lane_status(card.lane), updated_at=updated))
    epoch = datetime.min.replace(tzinfo=UTC)
    dated.sort(key=lambda item: item.updated_at or epoch, reverse=True)
    return ResearchGlance(
        stages=tuple(stages),
        total=len(report.cards),
        recent=tuple(dated[:_RECENT_CARDS]),
    )


def derive_attention(
    *,
    kill_switch: KillSwitchStatus,
    expired: int,
    soonest_expiry_days: float | None,
    agent_errors: int,
    failing_cron: int,
    stale_sources: int,
    claude: TopbarQuota,
    account: AccountSnapshot,
    disk: DiskStatus | None,
    memory: MemoryStatus | None,
) -> list[Attention]:
    """Everything that needs a look, most urgent first; `All clear` if nothing."""
    found: list[Attention] = []
    if kill_switch.enabled:
        found.append(Attention("stale", "Kill switch on", "/paper"))
    if expired:
        found.append(
            Attention("stale", f"{expired} authorization{'s' * (expired != 1)} expired", "/paper")
        )
    if agent_errors:
        found.append(
            Attention("stale", f"{agent_errors} agent error{'s' * (agent_errors != 1)}", "/agents")
        )
    if failing_cron:
        found.append(Attention("stale", f"{failing_cron} cron failing", "/health"))
    if not claude.available:
        reason = (claude.unavailable_reason or "unknown").split(" -- ")[0]
        text = (
            "Claude token expired" if reason.startswith("token expired") else f"Live quota {reason}"
        )
        found.append(Attention("warn", text, "/quota"))
    else:
        for bar in claude.bars:
            if bar.status in ("warn", "stale"):
                found.append(Attention(bar.status, f"{bar.label} {bar.percent_display}", "/quota"))
    if stale_sources:
        found.append(
            Attention(
                "warn", f"{stale_sources} source{'s' * (stale_sources != 1)} stale", "/health"
            )
        )
    if soonest_expiry_days is not None and 0 <= soonest_expiry_days < _AUTH_WARN_DAYS:
        found.append(Attention("warn", f"Auth ends in {soonest_expiry_days:.1f}d", "/paper"))
    if account.status in ("warn", "stale") and account.age_hours is not None:
        found.append(
            Attention("warn", f"Account snapshot {account.age_hours / 24:.0f}d old", "/paper")
        )
    for label, status in (("Disk", disk), ("Memory", memory)):
        if status is not None and status.status in ("warn", "stale"):
            found.append(
                Attention(status.status, f"{label} {status.used_percent:.0f}% used", "/health")
            )
    order = {"stale": 0, "warn": 1}
    found.sort(key=lambda item: order.get(item.level, 2))
    return found or [Attention("ok", "All clear", "/health")]


def build_now_report(
    root: Path,
    *,
    agents: AgentsReport,
    heavy: HeavyJobsReport,
    hypotheses: HypothesesReport,
    usage: UsageEstimate,
    claude: TopbarQuota,
    freshness: tuple[DataFreshnessEntry, ...],
    activity: ActivityField,
    now: datetime | None = None,
) -> NowReport:
    moment = now or datetime.now(UTC)

    names = discover_strategy_names(root)
    auths = [load_authorization(root, name, now=moment) for name in names]
    authorized = sum(1 for auth in auths if auth.state == "authorized")
    expired = sum(1 for auth in auths if auth.state == "expired")
    remaining = [
        auth.days_remaining
        for auth in auths
        if auth.state == "authorized" and auth.days_remaining is not None
    ]
    account = load_account_snapshot(root, now=moment)
    kill_switch = load_kill_switch(root)
    open_orders, _warnings = load_open_order_count(root)

    counts = {"running": 0, "idle": 0, "error": 0, "closed": 0}
    for summary in agents.agents:
        status = summary.record.last_status
        counts[status] = counts.get(status, 0) + 1
    running = [s.record for s in agents.agents if s.record.last_status == "running"]
    epoch = datetime.min.replace(tzinfo=UTC)
    running.sort(key=lambda record: record.last_activity_at or epoch, reverse=True)
    live = tuple(build_live_session(record) for record in running[:_LIVE_SESSIONS])
    # Nothing running: show what ran last (greyed), not an empty panel.
    resting = [s.record for s in agents.agents if s.record.last_status in ("idle", "closed")]
    resting.sort(key=lambda record: record.last_activity_at or epoch, reverse=True)
    last_active = build_live_session(resting[0]) if not live and resting else None
    errored = tuple(s.record for s in agents.agents if s.record.last_status == "error")

    try:
        cron = build_cron_report(repo_root=root)
    except Exception as exc:  # defensive, mirrors build_health_report
        cron = CronReport(jobs=(), available=False, error=f"cron report failed: {exc}")
    disk = build_disk_status()
    memory = build_memory_status()

    soonest = min(remaining) if remaining else None
    attention = derive_attention(
        kill_switch=kill_switch,
        expired=expired,
        soonest_expiry_days=soonest,
        agent_errors=len(errored),
        failing_cron=sum(1 for job in cron.jobs if job.status == "stale"),
        stale_sources=sum(1 for entry in freshness if entry.status == "stale"),
        claude=claude,
        account=account,
        disk=disk,
        memory=memory,
    )
    return NowReport(
        generated_at=moment,
        equity=build_account_equity_history(root, strategy_names=names),
        account=account,
        kill_switch=kill_switch,
        open_orders=open_orders,
        strategies=len(names),
        authorized=authorized,
        expired=expired,
        soonest_expiry_days=soonest,
        agent_counts=counts,
        live=live,
        last_active=last_active,
        errored=errored,
        heavy=heavy,
        research=summarize_research(hypotheses, root),
        usage=usage,
        claude=claude,
        freshness=freshness,
        cron=cron,
        disk=disk,
        memory=memory,
        activity=activity,
        attention=tuple(attention[:_MAX_ATTENTION]),
        more_attention=max(0, len(attention) - _MAX_ATTENTION),
    )


__all__ = [
    "STAGES",
    "Attention",
    "NowReport",
    "PipelineStage",
    "RecentCard",
    "ResearchGlance",
    "build_now_report",
    "derive_attention",
    "summarize_research",
]
