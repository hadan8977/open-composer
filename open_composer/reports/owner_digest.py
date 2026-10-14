"""Owner digest: the daily and weekly e-mail report (`docs/owner-reporting.zh.md`).

Deterministic and read-only.  It reuses the cockpit's builders (paper, health,
queue), reads the research log files and git, and calls no model and no broker.
`collect_digest` does all the I/O; `render_digest` and `digest_subject` are pure.

Since the owner's 2026-10-06 rewrite request the e-mail body is the plain-language
report a writer agent leaves in ``reports/owner/daily/<UTC date>.zh.md`` (weekly:
``reports/owner/weekly/<ISO week>.zh.md``); without it the body is a short
data-only fallback in business names.  Round logs, task lists and run health go
to an attachment (`render_internal_log`), never into the body.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from open_composer.reports.owner_forward import (
    BOOK_ACTIONS_START,
    BookAction,
    ForwardRow,
    collect_book_actions,
    load_forward_rows,
    render_book_actions,
    render_forward,
)
from open_composer.reports.owner_style import (
    ACCOUNT_RULES,
    STRATEGY_RULES,
    account_name,
    apply_business_names,
    candidate_name,
    strategy_name,
)

BEIJING = ZoneInfo("Asia/Shanghai")
WEEKDAYS = "一二三四五六日"
CURRENT_VIEW = Path("docs/current-view.zh.md")
QUEUE_FILE = Path("reports/research/control/autonomous-queue.md")
ROUND_GATE_STATUS = Path("logs/autonomous/round-gate-status.json")
BOOK_DIR = Path("reports/paper/book")
BOOK_LOG = Path("logs/book_v12_daily.log")
EXECUTION_DIR = Path("reports/execution")
WEEKLY_DIR = Path("reports/owner/weekly")
DAILY_DIR = Path("reports/owner/daily")
ROUND_DIR = Path("reports/owner/rounds")
LIVE_TRACK = Path("reports/owner/live-track.json")
REHEARSAL_DIR = Path("reports/paper/rehearsal")
BOOK_ACCOUNTS = ("quant1",)  # 10-06 (C1006-ACCT): quant2 left the v1.2 book (intraday account)
AUTH_WARN_DAYS = 14.0
DISK_WARN_PERCENT = 85.0
ACCOUNT_STALE_HOURS = 30.0
MAX_SECTION_BULLETS = 8
MAX_DONE_TASKS = 30
BULLET_CHARS = 220
ROUND_REPORT_CHARS = 6000
DECISION_WARN_DAYS = 7
RESIDUAL_SHOW = 0.001  # show the unexplained part of a sleeve's day return above 10 bp

_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?:（(.*?)）)?[：:]\s*(.*)$")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
_PRIORITY_RE = re.compile(r"（[^（）]*优先于下方[^（）]*）\s*$")
_ROUND_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2})(\d{2})Z-(lead|exec)\.md$")
_LOG_LINE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})Z (\w+) (.*)$")
_COMMIT_KIND_RE = re.compile(r"^([A-Za-z][A-Za-z\-]*)(?:\([^)]*\))?:")
_KIND_LABELS = {
    "research": "研究",
    "queue": "队列",
    "docs": "文档",
    "data": "数据",
    "ops": "运维",
    "feat": "功能",
    "fix": "修复",
    "paper": "模拟盘",
    "brief": "简报",
    "intel": "情报",
    "other": "其他",
}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SleeveRow:
    name: str
    label: str
    holdings: tuple[tuple[str, float], ...]
    budget: float
    nav: float
    start_session: date
    last_session: date
    navs: tuple[tuple[date, float], ...]  # observed closes, oldest first
    since_return: float | None
    spy_since: float | None
    fill_rate: float | None
    agreement: str
    auth_state: str
    auth_expires: datetime | None
    auth_days: float | None

    def nav_on(self, day: date) -> float:
        """Sleeve value at the close of ``day``: the budget before the first
        session, the last observed close otherwise."""
        value = self.budget
        for session, nav in self.navs:
            if session > day:
                break
            value = nav
        return value

    @property
    def max_drawdown(self) -> float:
        peak, worst = self.budget, 0.0
        for _, nav in self.navs:
            peak = max(peak, nav)
            worst = min(worst, nav / peak - 1.0)
        return worst


@dataclass(frozen=True)
class AccountInfo:
    equity: float | None
    age_hours: float | None
    status: str
    kill_switch_enabled: bool
    kill_switch_reason: str | None
    open_orders: int | None


@dataclass(frozen=True)
class BookAccount:
    account: str
    latest_target: str | None
    latest_plan: str | None
    latest_daily: str | None
    equity: float | None = None
    net_pnl: float | None = None
    net_return: float | None = None
    n_orders: int | None = None
    n_filled: int | None = None
    n_unfilled: int | None = None


@dataclass(frozen=True)
class ViewSection:
    day: date
    time: str | None  # "HH:MM" UTC when the heading carries one
    source: str
    title: str
    bullets: tuple[str, ...]

    @property
    def sort_key(self) -> tuple[date, str]:
        return (self.day, self.time or "")


@dataclass(frozen=True)
class TaskLine:
    task_id: str
    title: str
    status_text: str


@dataclass(frozen=True)
class HealthInfo:
    cron_total: int
    cron_problems: tuple[str, ...]
    live_data: tuple[str, ...]  # "name: latest (status)"
    live_data_problems: tuple[str, ...]
    disk_percent: float | None
    memory_percent: float | None
    gate_used_share: float | None
    gate_week_elapsed: float | None
    gate_checked_at: str | None
    gate_paused: tuple[str, ...]
    gate_limits: tuple[str, ...]
    modal: dict[str, Any] | None
    book_log_errors: int
    book_log_last_error: str | None


@dataclass(frozen=True)
class RoundReport:
    at: datetime
    kind: str  # "lead" | "exec"
    path: str
    text: str


@dataclass(frozen=True)
class DigestData:
    now: datetime
    window_start: datetime
    kind: str  # "daily" | "weekly"
    sleeves: tuple[SleeveRow, ...]
    sessions: tuple[date, ...]  # recent SPY sessions, oldest first
    spy_closes: dict[date, float]
    account: AccountInfo | None
    book: tuple[BookAccount, ...]
    sections: tuple[ViewSection, ...]
    done_tasks: tuple[TaskLine, ...]
    review_tasks: tuple[TaskLine, ...]
    running_tasks: tuple[TaskLine, ...]
    ready_count: int
    blocked_count: int
    commits: Counter = field(default_factory=Counter)
    commit_total: int = 0
    health: HealthInfo | None = None
    weekly_text: str | None = None
    weekly_path: str | None = None
    round_reports: tuple[RoundReport, ...] = ()
    live_track: dict[str, Any] | None = None
    contributions: dict[str, tuple[tuple[str, float], ...]] = field(default_factory=dict)
    errors: tuple[str, ...] = ()
    forward: tuple[list[ForwardRow], dict[str, Any]] | None = None
    book_actions: tuple[BookAction, ...] = ()
    daily_text: str | None = None
    daily_path: str | None = None


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def pct(value: float | None, digits: int = 2) -> str:
    return "—" if value is None else f"{value * 100:+.{digits}f}%"


def money(value: float | None) -> str:
    return "—" if value is None else f"${value:,.0f}"


def beijing_label(moment: datetime) -> str:
    local = moment.astimezone(BEIJING)
    return f"{local:%Y-%m-%d}（周{WEEKDAYS[local.weekday()]}）"


def session_label(day: date) -> str:
    return f"{day:%m-%d}（周{WEEKDAYS[day.weekday()]}）"


def iso_week_label(moment: datetime) -> str:
    year, week, _ = moment.astimezone(UTC).isocalendar()
    return f"{year}-W{week:02d}"


def _clip(text: str, limit: int = BULLET_CHARS) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def parse_view_sections(text: str) -> list[ViewSection]:
    """Dated `## ` sections of `docs/current-view.zh.md` with their top-level bullets."""
    sections: list[ViewSection] = []
    current: dict[str, Any] | None = None

    def flush() -> None:
        if current is not None:
            sections.append(
                ViewSection(
                    day=current["day"],
                    time=current["time"],
                    source=current["source"],
                    title=current["title"],
                    bullets=tuple(_clip(b) for b in current["bullets"][:MAX_SECTION_BULLETS]),
                )
            )

    for line in text.splitlines():
        if line.startswith("## "):
            flush()
            current = None
            match = _HEADING_RE.match(line)
            if not match:
                continue
            try:
                day = date.fromisoformat(match.group(1))
            except ValueError:
                continue
            source = (match.group(2) or "").strip()
            clock = _TIME_RE.search(source)
            time = f"{int(clock.group(1)):02d}:{clock.group(2)}" if clock else None
            title = _PRIORITY_RE.sub("", match.group(3)).strip()
            current = {"day": day, "time": time, "source": source, "title": title, "bullets": []}
            continue
        if current is None:
            continue
        if line.startswith("- "):
            current["bullets"].append(" ".join(line[2:].replace("**", "").split()))
        elif (
            line.startswith("  - ")
            and current["bullets"]
            and current["bullets"][-1].endswith(("：", ":"))
        ):
            # "- **10:10 update**:" carries its content in the first nested bullet
            current["bullets"][-1] += " " + " ".join(line[4:].replace("**", "").split())
    flush()
    return sections


def sections_since(sections: list[ViewSection], start: datetime) -> list[ViewSection]:
    start_utc = start.astimezone(UTC)
    chosen = []
    for section in sections:
        if section.time:
            hour, minute = (int(part) for part in section.time.split(":"))
            at = datetime(
                section.day.year, section.day.month, section.day.day, hour, minute, tzinfo=UTC
            )
            if at >= start_utc:
                chosen.append(section)
        elif section.day >= start_utc.date():
            chosen.append(section)
    return sorted(chosen, key=lambda s: s.sort_key, reverse=True)


def combined_returns(
    sleeves: tuple[SleeveRow, ...], sessions: tuple[date, ...]
) -> tuple[float | None, float | None, float | None]:
    """(total close value, last-session return, 5-session return) of all sleeves."""
    if not sleeves or len(sessions) < 2:
        return None, None, None
    last = sessions[-1]

    def total(day: date) -> float:
        return sum(row.nav_on(day) for row in sleeves)

    now_value = total(last)
    day_ret = now_value / total(sessions[-2]) - 1.0
    base = sessions[-6] if len(sessions) >= 6 else sessions[0]
    week_ret = now_value / total(base) - 1.0
    return now_value, day_ret, week_ret


def sleeve_returns(row: SleeveRow, sessions: tuple[date, ...]) -> tuple[float | None, float | None]:
    if len(sessions) < 2:
        return None, None
    last = sessions[-1]
    day_ret = row.nav_on(last) / row.nav_on(sessions[-2]) - 1.0
    base = sessions[-6] if len(sessions) >= 6 else sessions[0]
    week_ret = row.nav_on(last) / row.nav_on(base) - 1.0
    return day_ret, week_ret


def spy_returns(
    closes: dict[date, float], sessions: tuple[date, ...]
) -> tuple[float | None, float | None]:
    if len(sessions) < 2 or sessions[-1] not in closes:
        return None, None
    last = closes[sessions[-1]]
    prev = closes.get(sessions[-2])
    base = closes.get(sessions[-6] if len(sessions) >= 6 else sessions[0])
    return (
        last / prev - 1.0 if prev else None,
        last / base - 1.0 if base else None,
    )


def holding_contributions(
    qty: dict[str, float],
    closes: dict[str, dict[date, float]],
    day: date,
    prev: date,
    nav_prev: float,
) -> tuple[tuple[str, float], ...]:
    """Each holding's close-to-close P&L on ``day`` as a share of the sleeve's
    value at ``prev``, largest first.  Uses the latest ledger quantities, so a
    position changed on ``day`` itself leaves a residual (shown separately)."""
    parts = []
    for symbol, quantity in qty.items():
        c1, c0 = closes.get(symbol, {}).get(day), closes.get(symbol, {}).get(prev)
        if quantity and c1 and c0 and nav_prev:
            parts.append((symbol, quantity * (c1 - c0) / nav_prev))
    return tuple(sorted(parts, key=lambda item: -abs(item[1])))


def paper_sessions_since(start: str | None, last: date | None) -> int | None:
    """US equity sessions from ``start`` through ``last``, both inclusive."""
    if not start or last is None:
        return None
    try:
        first = date.fromisoformat(start)
    except ValueError:
        return None
    if first > last:
        return 0
    from open_composer.market_sessions import us_equity_session_dates

    return len(us_equity_session_dates(first, last))


def owner_items(data: DigestData) -> list[str]:
    """What only the owner can act on: money, authorizations, decisions."""
    items: list[str] = []
    account = data.account
    if account is not None and account.kill_switch_enabled:
        items.append(f"紧急停止开关已打开：{account.kill_switch_reason or '原因未记录'}")
    for row in data.sleeves:
        if row.auth_days is not None and row.auth_days <= AUTH_WARN_DAYS:
            when = f"{row.auth_expires:%m-%d %H:%M} UTC" if row.auth_expires else "日期未知"
            items.append(
                f"{strategy_name(row.name)}的模拟授权 {row.auth_days:.0f} 天后到期（{when}）"
            )
        if row.auth_state not in ("authorized", ""):
            items.append(f"{strategy_name(row.name)}的授权状态是 {row.auth_state}")
    today = data.now.astimezone(UTC).date()
    for decision in (data.live_track or {}).get("owner_decisions") or []:
        try:
            due = date.fromisoformat(str(decision.get("due")))
        except ValueError:
            continue
        if (due - today).days <= DECISION_WARN_DAYS:
            items.append(f"待你决定：{decision.get('item')}（{due:%m-%d} 前）")
    return items


def ops_items(data: DigestData) -> list[str]:
    """Operational anomalies the research side fixes; listed for awareness."""
    items: list[str] = []
    account = data.account
    if (
        account is not None
        and account.age_hours is not None
        and account.age_hours > ACCOUNT_STALE_HOURS
        and data.now.astimezone(UTC).weekday() in (1, 2, 3, 4, 5)
    ):
        items.append(f"主模拟账户快照已 {account.age_hours:.0f} 小时没有更新")
    health = data.health
    if health is not None:
        items.extend(f"定时任务异常：{problem}" for problem in health.cron_problems)
        items.extend(f"实时数据过期：{problem}" for problem in health.live_data_problems)
        if health.gate_limits:
            items.append("Claude 额度受限：" + "；".join(health.gate_limits))
        if health.gate_paused:
            items.append("研究轮被额度闸门暂停：" + "、".join(health.gate_paused))
        if health.disk_percent is not None and health.disk_percent >= DISK_WARN_PERCENT:
            items.append(f"磁盘使用 {health.disk_percent:.0f}%")
        if health.book_log_errors:
            items.append(
                f"v1.2 每日驱动报错 {health.book_log_errors} 次，"
                f"最近一次：{health.book_log_last_error}"
            )
    items.extend(f"汇报脚本自身问题：{error}" for error in data.errors)
    return items


def attention_items(data: DigestData) -> list[str]:
    return owner_items(data) + ops_items(data)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _holdings_text(row: SleeveRow) -> str:
    if not row.holdings:
        return "—"
    return "、".join(f"{symbol} {weight * 100:.0f}%" for symbol, weight in row.holdings)


def _render_contributions(data: DigestData) -> list[str]:
    rows = []
    for row in data.sleeves:
        parts = data.contributions.get(row.name) or ()
        if not parts:
            continue
        day_ret, _ = sleeve_returns(row, data.sessions)
        shown = [(symbol, share) for symbol, share in parts[:3] if abs(share) >= 0.00005]
        text = "、".join(f"{symbol} {pct(share)}" for symbol, share in shown) or "持仓几乎不动"
        if day_ret is not None:
            residual = day_ret - sum(share for _, share in parts)
            if abs(residual) >= RESIDUAL_SHOW:
                text += f"；调仓与现金 {pct(residual)}"
        rows.append(f"- {row.label.split(' ')[0]}（{pct(day_ret)}）：{text}")
    if not rows:
        return []
    return ["当日盈亏来自哪些持仓（收盘持仓近似，占子策略净值）：", "", *rows]


def _render_paper(data: DigestData) -> list[str]:
    lines: list[str] = []
    if not data.sleeves:
        lines.append("没有正在运行的子策略。")
        return lines
    last = data.sessions[-1] if data.sessions else None
    heading = f"截至美股 {session_label(last)}收盘" if last else "最近收盘"
    lines.append(f"{heading}。每条子策略预算 1.5 万美元，按自身净值复利。")
    lines.append("")
    lines.append(
        "| 子策略 | 目标持仓 | 净值 | 当日 | 近 5 日 | 起始以来 | SPY 同期 | 最大回撤 | 授权剩余 |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for row in data.sleeves:
        day_ret, week_ret = sleeve_returns(row, data.sessions)
        since = f"{pct(row.since_return)}（{row.start_session:%m-%d} 起）"
        auth = f"{row.auth_days:.0f} 天" if row.auth_days is not None else "—"
        lines.append(
            f"| {row.label} | {_holdings_text(row)} | {money(row.nav)} | {pct(day_ret)} | "
            f"{pct(week_ret)} | {since} | {pct(row.spy_since)} | {pct(row.max_drawdown)} | {auth} |"
        )
    total, day_ret, week_ret = combined_returns(data.sleeves, data.sessions)
    lines.append(f"| **合计** | | {money(total)} | {pct(day_ret)} | {pct(week_ret)} | | | | |")
    spy_day, spy_week = spy_returns(data.spy_closes, data.sessions)
    lines.append("")
    lines.append(f"SPY：当日 {pct(spy_day)}，近 5 日 {pct(spy_week)}。")
    if data.account is not None:
        account = data.account
        switch = "打开" if account.kill_switch_enabled else "关闭"
        lines.append(
            f"主模拟账户净值 {money(account.equity)}（其余为闲置现金），紧急停止开关{switch}，"
            f"未成交挂单 {account.open_orders if account.open_orders is not None else '—'} 笔。"
        )
    odd = [
        row
        for row in data.sleeves
        if row.agreement and not row.agreement.startswith("broker holds exactly")
    ]
    if odd:
        lines.append("对账不一致：" + "；".join(f"{row.label}：{row.agreement}" for row in odd))
    else:
        lines.append("对账：经纪商持仓等于各子策略账本之和。")
    attribution = _render_contributions(data)
    if attribution:
        lines.append("")
        lines.extend(attribution)
        lines.append("")
    fills = [
        f"{row.label.split(' ')[0]} {row.fill_rate * 100:.0f}%"
        for row in data.sleeves
        if row.fill_rate is not None
    ]
    if fills:
        lines.append("最近一次成交率：" + "，".join(fills) + "。")
    return lines


def _render_book(data: DigestData) -> list[str]:
    lines = [
        "quant1 跑 F1（市场中性多空 + 短债），100 万美元模拟资金，10-07 首单，"
        "10-12 前基数降到约 30 万；quant2 不跑 F2（机主 10-06 决定），10-09/10 起改做日内账户。",
        "",
        "| 账户 | 最新目标 | 最新计划 | 最新对账 | 净值 | 当日净盈亏 | 订单（成交 / 未成交） |",
        "|---|---|---|---|---|---|---|",
    ]
    for acct in data.book:
        orders = (
            f"{acct.n_orders}（{acct.n_filled} / {acct.n_unfilled}）"
            if acct.n_orders is not None
            else "—"
        )
        pnl = "—"
        if acct.net_pnl is not None:
            pnl = f"{money(acct.net_pnl)}（{pct(acct.net_return)}）"
        lines.append(
            f"| {acct.account} | {acct.latest_target or '—'} | {acct.latest_plan or '—'} | "
            f"{acct.latest_daily or '尚无'} | {money(acct.equity)} | {pnl} | {orders} |"
        )
    if data.health is not None:
        errors = data.health.book_log_errors
        lines.append("")
        lines.append(
            f"每日驱动日志：本期报错 {errors} 次。" if errors else "每日驱动日志：本期没有报错。"
        )
    return lines


def _render_research(data: DigestData) -> list[str]:
    lines: list[str] = ["### 研究判断的更新（`docs/current-view.zh.md`）", ""]
    if data.sections:
        for section in data.sections:
            stamp = f"{section.day:%m-%d}" + (f" {section.time}" if section.time else "")
            source = re.sub(r"\d{1,2}:\d{2}", "", section.source).strip(" ，,") or "研究"
            lines.append(f"- **{stamp} {source}**：{section.title}")
            if data.kind != "weekly":  # the weekly judgement already summarizes the week
                lines.extend(f"  - {bullet}" for bullet in section.bullets)
    else:
        lines.append("- 本期没有新的判断章节。")
    lines.append("")
    lines.append("### 完成或复核的任务")
    lines.append("")
    if data.done_tasks:
        shown = data.done_tasks[:MAX_DONE_TASKS]
        lines.extend(f"- {task.task_id}：{task.title}" for task in shown)
        if len(data.done_tasks) > len(shown):
            lines.append(f"- ……另 {len(data.done_tasks) - len(shown)} 项，见任务队列。")
    else:
        lines.append("- 本期没有。")
    lines.append("")
    lines.append("### 正在做")
    lines.append("")
    for task in data.running_tasks:
        lines.append(f"- 运行中 {task.task_id}：{task.title}")
    for task in data.review_tasks:
        lines.append(f"- 待主审 {task.task_id}：{task.title}")
    lines.append(f"- 排队 {data.ready_count} 项，受阻 {data.blocked_count} 项。")
    if data.commit_total:
        kinds = "、".join(
            f"{_KIND_LABELS.get(kind, kind)} {count}" for kind, count in data.commits.most_common(6)
        )
        lines.append("")
        lines.append(f"提交 {data.commit_total} 次（{kinds}）。")
    return lines


def _render_health(data: DigestData) -> list[str]:
    health = data.health
    if health is None:
        return ["健康数据读取失败，见下方问题清单。"]
    lines = []
    problems = len(health.cron_problems)
    lines.append(f"- 定时任务 {health.cron_total} 个，异常 {problems} 个。")
    if health.live_data:
        lines.append("- 实时数据：" + "；".join(health.live_data) + "。")
    if health.gate_used_share is not None:
        gate = f"- Claude 周额度：已用 {health.gate_used_share * 100:.1f}%"
        if health.gate_week_elapsed is not None:
            gate += f"，本周时间过去 {health.gate_week_elapsed * 100:.1f}%"
        gate += f"（闸门最后检查 {health.gate_checked_at or '未知'}）。"
        lines.append(gate)
    if health.modal:
        modal = health.modal
        lines.append(
            f"- Modal 本月：已结算 ${modal.get('billed_usd', 0):.2f}，"
            f"最坏情况 ${modal.get('projected_usd', 0):.2f}，上限 ${modal.get('cap_usd', 25):.0f}。"
        )
    if health.disk_percent is not None:
        memory = f"，内存 {health.memory_percent:.0f}%" if health.memory_percent is not None else ""
        lines.append(f"- 磁盘 {health.disk_percent:.0f}%{memory}。")
    return lines


def _render_live_track(data: DigestData) -> list[str]:
    track = data.live_track
    if not track:
        return [f"`{LIVE_TRACK}` 缺失，无法列出实盘进度。"]
    live = track.get("live") or []
    names = "、".join(str(item.get("label") or item.get("id")) for item in live)
    lines = [f"实盘：{names or '没有'}。规则：{track.get('rule', '—')}。", ""]
    lines.append("| 候选 | 阶段 | 模拟盘起 | 已满会话 | 下一步 | 截止 | 实盘提议 |")
    lines.append("|---|---|---|---|---|---|---|")
    last = data.sessions[-1] if data.sessions else None
    for item in track.get("candidates") or []:
        done = paper_sessions_since(item.get("paper_since"), last)
        lines.append(
            f"| {item.get('label', item.get('id'))} | {item.get('stage', '—')} | "
            f"{item.get('paper_since') or '—'} | {'—' if done is None else f'{done}/10'} | "
            f"{item.get('next', '—')} | {item.get('next_due', '—')} | "
            f"{item.get('proposal_due', '—')} |"
        )
    engines = track.get("engines") or []
    if engines:
        lines.extend(["", "研究引擎："])
        lines.extend(
            f"- **{engine.get('name')}**：现在 {engine.get('now')}；"
            f"下一步 {engine.get('next')}（{engine.get('due')}）"
            for engine in engines
        )
    lines.extend(["", f"（`{LIVE_TRACK}`，更新于 {track.get('updated_at', '—')}）"])
    return lines


def _demote_headings(text: str) -> list[str]:
    lines = text.rstrip().splitlines()
    if lines and lines[0].startswith("# "):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines = lines[1:]
    return [("###" + line[1:]) if line.startswith("#") else line for line in lines]


def _render_rounds(data: DigestData) -> list[str]:
    if not data.round_reports:
        return [f"没有落盘的自动轮汇报（每轮写入 `{ROUND_DIR}/`）。"]
    lines: list[str] = []
    for report in data.round_reports:
        label = "主审轮" if report.kind == "lead" else "执行轮"
        lines.extend([f"### {label} {report.at:%m-%d %H:%M} UTC", ""])
        body = _demote_headings(report.text)
        if data.kind == "weekly":
            body = [line for line in body if line.strip()][:3]
        lines.extend(body)
        lines.append("")
    return lines


def render_internal_log(data: DigestData) -> str:
    """The old full digest: round logs, task ids, run health.  Attachment only."""
    title = "周报" if data.kind == "weekly" else "日报"
    generated = data.now.astimezone(UTC)
    local = data.now.astimezone(BEIJING)
    out: list[str] = []
    if data.kind == "weekly" and data.weekly_text:
        out.append(data.weekly_text.rstrip())
        out.append("")
        out.append("---")
        out.append("")
        out.append(f"# 附：一周数据（脚本生成，{generated:%Y-%m-%d %H:%M} UTC）")
    else:
        label = iso_week_label(data.now) if data.kind == "weekly" else beijing_label(data.now)
        out.append(f"# 运行记录（{title}附件，内部用语，供查证） · {label}")
        out.append("")
        out.append(
            f"生成于 {generated:%Y-%m-%d %H:%M} UTC（北京 {local:%H:%M}），覆盖 "
            f"{data.window_start.astimezone(UTC):%m-%d %H:%M} UTC 以来。脚本生成，不含模型判断；"
            "口径见 `docs/owner-reporting.zh.md`。"
        )
        if data.kind == "weekly":
            out.append("")
            out.append(
                f"本周判断未写：`{WEEKLY_DIR}/{iso_week_label(data.now)}.zh.md` 不存在"
                "（周六 19:07 主审轮负责），以下只有数据。"
            )
    items = owner_items(data)
    ops = ops_items(data)
    _, day_ret, week_ret = combined_returns(data.sleeves, data.sessions)
    spy_day, spy_week = spy_returns(data.spy_closes, data.sessions)
    period = "本周" if data.kind == "weekly" else "过去 24 小时"
    out.extend(
        [
            "",
            f"**概览**：ETF 子策略当日 {pct(day_ret)}（SPY {pct(spy_day)}），"
            f"近 5 日 {pct(week_ret)}（SPY {pct(spy_week)}）；"
            f"{period}完成或复核 {len(data.done_tasks)} 项研究任务，"
            f"提交 {data.commit_total} 次；需要你处理 {len(items)} 项，"
            f"运行异常 {len(ops)} 项（第六节）。",
        ]
    )
    out.extend(["", "## 需要你处理", ""])
    out.extend([f"- {item}" for item in items] or ["- 没有。"])
    out.extend(["", "## 一、模拟盘（ETF 子策略）", ""])
    out.extend(_render_paper(data))
    out.extend(["", "## 二、股票组合 v1.2（quant1）", ""])
    out.extend(_render_book(data))
    out.extend(["", *render_book_actions(list(data.book_actions))])
    out.extend(["", "## 三、离实盘多远", ""])
    out.extend(_render_live_track(data))
    out.extend(["", "### 前向对预期", "", *render_forward(data.forward)])
    out.extend(["", f"## 四、自动轮汇报（{period}）", ""])
    out.extend(_render_rounds(data))
    out.extend(["", f"## 五、研究进展（{period}）", ""])
    out.extend(_render_research(data))
    out.extend(["", "## 六、运行健康", ""])
    if ops:
        out.append("异常（研究侧处理，列出供你知悉）：")
        out.append("")
        out.extend(f"- {item}" for item in ops)
        out.append("")
    out.extend(_render_health(data))
    out.extend(
        [
            "",
            "详细页面在 cockpit（Cloudflare Access 登录）；"
            "所有数字的来源见 `docs/owner-reporting.zh.md` 第 4 节。",
        ]
    )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Owner-facing body (2026-10-06 rewrite): business names, no codes
# ---------------------------------------------------------------------------

ETF_NAMES: dict[str, str] = {
    "SPY": "标普",
    "QQQ": "纳指",
    "IWM": "小盘股",
    "DIA": "道指",
    "XLB": "材料",
    "XLC": "通信",
    "XLE": "能源",
    "XLF": "金融",
    "XLI": "工业",
    "XLK": "科技",
    "XLP": "必需消费",
    "XLRE": "地产",
    "XLU": "公用事业",
    "XLV": "医疗",
    "XLY": "可选消费",
    "SMH": "半导体",
    "SOXX": "半导体",
    "IGV": "软件",
    "BIL": "短期国债",
    "SHY": "短期国债",
    "IEF": "中期国债",
    "SGOV": "短期国债",
    "SHV": "短期国债",
    "TLT": "长期国债",
    "GLD": "黄金",
    "SOXL": "3 倍半导体",
    "TECL": "3 倍科技",
    "TQQQ": "3 倍纳指",
    "UPRO": "3 倍标普",
    "SPXL": "3 倍标普",
    "FAS": "3 倍金融",
    "ERX": "2 倍能源",
    "LABU": "3 倍生物科技",
    "TNA": "3 倍小盘股",
    "CURE": "3 倍医疗",
    "DRN": "3 倍地产",
}
_TASK_CODE_RE = re.compile(
    r"(?<![A-Za-z0-9_./-])[THIEW]-?\d{2,8}(?:-\d{2,3})?[a-z]?(?![A-Za-z0-9_])"
)
_CODE_PAREN_RE = re.compile(r"[（(][^（）()]*?[THIEW]-?\d{2,8}[^（）()]*[）)]")
REAL_PROBLEM_CRON_WORDS = ("paper", "book", "sip", "rehearsal", "option", "vix", "equity")
IGNORED_CRON_WORDS = ("probe",)  # one-shot execution probes end in expected "errors"


def scrub_codes(text: str) -> str:
    """Safety net for lead-written fields: business names, drop task codes."""
    text = apply_business_names(text)
    text = _CODE_PAREN_RE.sub("", text)
    text = _TASK_CODE_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", text).strip(" ，,；;")


def holding_name(symbol: str) -> str:
    name = ETF_NAMES.get(symbol)
    return f"{name}（{symbol}）" if name else symbol


def _holdings_business(row: SleeveRow) -> str:
    if not row.holdings:
        return "现金"
    return "、".join(f"{holding_name(s)}{w * 100:.0f}%" for s, w in row.holdings)


def problem_items(data: DigestData) -> list[str]:
    """Problems the owner should know about: trading, data and report integrity only.
    Quota pauses, gate limits, disk and the research machinery stay in the attachment."""
    items: list[str] = []
    account = data.account
    if account is not None and account.kill_switch_enabled:
        items.append(
            f"模拟盘的紧急停止开关是打开的：{account.kill_switch_reason or '原因未记录'}。"
        )
    if (
        account is not None
        and account.age_hours is not None
        and account.age_hours > ACCOUNT_STALE_HOURS
        and data.now.astimezone(UTC).weekday() in (1, 2, 3, 4, 5)
    ):
        items.append(
            f"主模拟账户的数据已 {account.age_hours:.0f} 小时没有更新，表里的数字可能是旧的。"
        )
    odd = [
        row
        for row in data.sleeves
        if row.agreement and not row.agreement.startswith("broker holds exactly")
    ]
    if odd:
        names = "、".join(strategy_name(row.name) for row in odd)
        items.append(f"券商持仓和我们的账本对不上：{names}。")
    for row in data.sleeves:
        if row.auth_days is not None and row.auth_days <= AUTH_WARN_DAYS:
            items.append(f"{strategy_name(row.name)}的模拟盘授权 {row.auth_days:.0f} 天后到期。")
    health = data.health
    if health is not None:
        if health.book_log_errors:
            items.append(f"股票多空组合的每日程序报错 {health.book_log_errors} 次，正在处理。")
        trading = [
            problem
            for problem in health.cron_problems
            if any(word in problem.lower() for word in REAL_PROBLEM_CRON_WORDS)
            and not any(word in problem.lower() for word in IGNORED_CRON_WORDS)
        ]
        if trading:
            items.append(
                f"交易或行情相关的定时任务有 {len(trading)} 个报错，正在处理，明细见附件。"
            )
        if health.live_data_problems:
            items.append("行情数据没有按时更新，明细见附件。")
    if data.errors:
        items.append("日报程序有部分数据没读到，表里可能缺项，明细见附件。")
    return items


def render_etf_table(data: DigestData) -> list[str]:
    if not data.sleeves:
        return ["目前没有在运行的 ETF 策略。"]
    last = data.sessions[-1] if data.sessions else None
    lines = [
        f"数字截至美股 {session_label(last)}收盘。" if last else "数字截至最近一次收盘。",
        "",
        "| 策略 | 怎么交易 | 现在持有 | 当日 | 近 5 日 | 开始以来 | 同期 SPY | 最大回撤 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for row in data.sleeves:
        day_ret, week_ret = sleeve_returns(row, data.sessions)
        lines.append(
            f"| {strategy_name(row.name)} | {STRATEGY_RULES.get(row.name, '—')} | "
            f"{_holdings_business(row)} | {pct(day_ret)} | {pct(week_ret)} | "
            f"{pct(row.since_return)}（{row.start_session:%m-%d} 起） | {pct(row.spy_since)} | "
            f"{pct(row.max_drawdown)} |"
        )
    total, day_ret, week_ret = combined_returns(data.sleeves, data.sessions)
    budget = sum(row.budget for row in data.sleeves)
    spy_day, spy_week = spy_returns(data.spy_closes, data.sessions)
    lines.append("")
    lines.append(
        f"合计：本金 {money(budget)}，现在 {money(total)}，"
        f"当日 {pct(day_ret)}，近 5 日 {pct(week_ret)}；"
        f"SPY 当日 {pct(spy_day)}，近 5 日 {pct(spy_week)}。"
    )
    return lines


def render_book_business(data: DigestData) -> list[str]:
    lines = [
        "| 账户 | 账本日期 | 做法 | 净值 | 该日盈亏 | 订单：成交 / 未成交 |",
        "|---|---|---|---|---|---|",
    ]
    start = BOOK_ACTIONS_START.isoformat()
    for acct in data.book:
        trading = bool(acct.latest_daily and acct.latest_daily >= start)
        orders = f"还没有开始交易（{BOOK_ACTIONS_START:%m-%d} 第一次下单）"
        pnl = "—"
        if trading and acct.n_orders is not None:
            orders = f"{acct.n_orders} 笔：{acct.n_filled} / {acct.n_unfilled}"
        if trading and acct.net_pnl is not None:
            pnl = f"{money(acct.net_pnl)}（{pct(acct.net_return)}）"
        lines.append(
            f"| {account_name(acct.account)} | {acct.latest_daily or '尚无账本'} | "
            f"{ACCOUNT_RULES.get(acct.account, '—')} | "
            f"{money(acct.equity)} | {pnl} | {orders} |"
        )
    actions = [a for a in data.book_actions]
    if actions:
        lines.extend(
            [
                "",
                "最近几天的下单情况：",
                "",
                "| 日期 | 账户 | 进度 | 计划笔数 | 发出 | 被拒 "
                "| 全部成交 | 部分成交 | 未成交 | 换手 |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
        )
        for a in actions:
            turnover = "—" if a.turnover is None else f"{a.turnover * 100:.1f}%"
            lines.append(
                f"| {a.day:%m-%d} | {account_name(a.account)} | {a.state} | "
                f"{_count_text(a.n_planned)} | {_count_text(a.n_sent)} | "
                f"{_count_text(a.n_rejected)} | {_count_text(a.n_filled)} | "
                f"{_count_text(a.n_partial)} | {_count_text(a.n_unfilled)} | {turnover} |"
            )
    return lines


def _month_day(value: Any) -> str:
    """'2026-10-08' -> '10-08'; anything else as given, '—' when empty."""
    text = str(value or "").strip()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return text[5:]
    return text or "—"


def _count_text(value: int | None) -> str:
    return "—" if value is None else str(value)


def render_candidates(data: DigestData) -> list[str]:
    track = data.live_track or {}
    rows = track.get("candidates") or []
    if not rows:
        return []
    lines = [
        "| 候选 | 现在在哪一步 | 下一步 | 日期 |",
        "|---|---|---|---|",
    ]
    for item in rows:
        name = candidate_name(str(item.get("id") or ""), scrub_codes(str(item.get("label") or "")))
        lines.append(
            f"| {name} | {scrub_codes(str(item.get('stage') or '—'))} | "
            f"{scrub_codes(str(item.get('next') or '—'))} | {item.get('next_due') or '—'} |"
        )
    return lines


def render_owner_asks(data: DigestData) -> list[str]:
    asks = (data.live_track or {}).get("owner_asks") or []
    if not asks:
        return ["没有登记中的问题或要求。"]
    lines = [
        "| 提出 | 你的问题或要求 | 我们的回答和做法 | 下一步 | 日期 | 状态 |",
        "|---|---|---|---|---|---|",
    ]
    for ask in asks:
        if not isinstance(ask, dict):
            continue
        cells = [
            _month_day(ask.get("asked")),
            scrub_codes(str(ask.get("topic") or "—")),
            scrub_codes(str(ask.get("answer") or "—")),
            scrub_codes(str(ask.get("next") or "—")),
            _month_day(ask.get("due")),
            str(ask.get("status") or "—"),
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def render_decisions(data: DigestData) -> list[str]:
    decisions = (data.live_track or {}).get("owner_decisions") or []
    rows = []
    for item in decisions:
        if not isinstance(item, dict) or not item.get("item"):
            continue
        rows.append(
            f"| {scrub_codes(str(item['item']))} | {_month_day(item.get('due'))} | "
            f"{scrub_codes(str(item.get('default') or '—'))} |"
        )
    if not rows:
        return ["没有。"]
    return ["| 事项 | 截止 | 不答复时的默认 |", "|---|---|---|", *rows]


def render_paper_section(data: DigestData) -> list[str]:
    live = (data.live_track or {}).get("live") or []
    names = "、".join(str(item.get("label") or item.get("id")) for item in live)
    lines = [f"实盘：{names or '没有'}。", ""]
    lines.extend(["### ETF 轮动策略（主模拟账户，每个 1.5 万美元）", ""])
    lines.extend(render_etf_table(data))
    lines.extend(["", "### 股票多空组合（按各账户实际账本日期）", ""])
    lines.extend(render_book_business(data))
    return lines


def _attachment_line(data: DigestData) -> str:
    return "- 自动研究轮的逐轮记录、任务清单和运行状态：见邮件附件（内部用语，供查证）。"


def render_daily_fallback(data: DigestData) -> str:
    local = data.now.astimezone(BEIJING)
    out = [
        f"# Open Composer 日报 · {local:%m-%d}（周{WEEKDAYS[local.weekday()]}）",
        "",
        "今天的文字总结没有按时写成，下面只有自动生成的交易数据和待办；研究进展下一封日报一起补上。",
    ]
    problems = problem_items(data)
    if problems:
        out.extend(["", "## 一、需要你知道的问题", ""])
        out.extend(f"- {item}" for item in problems)
    out.extend(["", "## 二、模拟盘和实盘", ""])
    out.extend(render_paper_section(data))
    out.extend(["", "## 三、你的问题和要求：进展", "", *render_owner_asks(data)])
    out.extend(["", "## 四、需要你决定的事", "", *render_decisions(data)])
    out.extend(["", "## 附：证据（不必读）", "", _attachment_line(data)])
    return "\n".join(out) + "\n"


def render_written(data: DigestData, text: str) -> str:
    """A writer's report as the body: fixed codes get business names; the attachment
    pointer is added to the appendix."""
    body = apply_business_names(text).rstrip()
    if not re.search(r"^#{1,3}\s*附", body, flags=re.M):
        body += "\n\n## 附：证据（不必读）\n"
    return body + "\n" + _attachment_line(data) + "\n"


def render_digest(data: DigestData) -> str:
    if data.kind == "weekly":
        if data.weekly_text:
            out = [render_written(data, data.weekly_text).rstrip()]
        else:
            out = [
                f"# Open Composer 周报 · {iso_week_label(data.now)}",
                "",
                "本周的文字总结没有写成，下面只有自动生成的数据；文字部分写好后补发。",
            ]
        out.extend(["", "---", "", "## 附：一周数据（自动生成）", ""])
        problems = problem_items(data)
        if problems:
            out.extend(["### 需要你知道的问题", "", *(f"- {item}" for item in problems), ""])
        out.extend(render_paper_section(data))
        out.extend(["", "### 你的问题和要求：进展", "", *render_owner_asks(data)])
        out.extend(["", "### 需要你决定的事", "", *render_decisions(data)])
        if not data.weekly_text:
            out.extend(["", _attachment_line(data)])
        return "\n".join(out) + "\n"
    if data.daily_text:
        return render_written(data, data.daily_text)
    return render_daily_fallback(data)


def digest_subject(data: DigestData) -> str:
    _, day_ret, week_ret = combined_returns(data.sleeves, data.sessions)
    spy_day, spy_week = spy_returns(data.spy_closes, data.sessions)
    pending = len(owner_items(data))
    problems = len(problem_items(data))
    if data.kind == "weekly":
        head = f"[Open Composer] 周报 {iso_week_label(data.now)}"
        money_part = f"ETF 策略近 5 日 {pct(week_ret)}，SPY {pct(spy_week)}"
    else:
        local = data.now.astimezone(BEIJING)
        head = f"[Open Composer] 日报 {local:%m-%d}（周{WEEKDAYS[local.weekday()]}）"
        money_part = f"ETF 策略当日 {pct(day_ret)}，SPY {pct(spy_day)}"
    tail = f"需要你决定 {pending}" + (f"｜问题 {problems}" if problems else "")
    return f"{head}｜{money_part}｜{tail}"


_HTML_STYLE = """
body { font-family: -apple-system, 'PingFang SC', 'Microsoft YaHei', Helvetica, sans-serif;
       font-size: 14px; line-height: 1.55; color: #1f2328;
       max-width: 860px; margin: 0 auto; padding: 8px; }
h1 { font-size: 20px; } h2 { font-size: 17px; margin-top: 22px; border-bottom: 1px solid #d0d7de; }
h3 { font-size: 15px; }
table { border-collapse: collapse; margin: 8px 0; font-size: 13px; }
th, td { border: 1px solid #d0d7de; padding: 4px 7px; text-align: left; vertical-align: top; }
th { background: #f6f8fa; }
code { background: #f6f8fa; padding: 0 3px; font-size: 12px; }
""".strip()


def markdown_to_html(text: str) -> str:
    from markdown_it import MarkdownIt

    body = MarkdownIt("commonmark", {"html": False}).enable("table").render(text)
    return (
        '<!doctype html><html><head><meta charset="utf-8">'
        f"<style>{_HTML_STYLE}</style></head><body>{body}</body></html>"
    )


# ---------------------------------------------------------------------------
# Collection (I/O)
# ---------------------------------------------------------------------------


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_target_holdings(root: Path, strategy_name: str) -> tuple[tuple[str, float], ...]:
    payload = _read_json(root / EXECUTION_DIR / f"{strategy_name}-target-weights.json")
    rows = (payload or {}).get("target_weights") or []
    holdings: list[tuple[str, float]] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("symbol"):
            continue
        weight = row.get("target_weight")
        if isinstance(weight, int | float) and weight > 0:
            holdings.append((str(row["symbol"]), float(weight)))
    return tuple(sorted(holdings, key=lambda item: -item[1]))


def _collect_paper(
    root: Path, now: datetime
) -> tuple[tuple[SleeveRow, ...], AccountInfo, tuple[date, ...], dict[date, float]]:
    from open_composer.cockpit.data.paper import build_paper_report, load_session_prices

    report = build_paper_report(root, now=now)
    rows: list[SleeveRow] = []
    for summary in report.strategies:
        perf = summary.performance
        if perf.status != "live" or perf.history is None or perf.budget is None:
            continue
        navs = tuple(
            (day.day, day.point.equity) for day in perf.history.days if day.point is not None
        )
        if not navs or perf.start_session is None or perf.last_session is None:
            continue
        auth = summary.authorization
        rows.append(
            SleeveRow(
                name=summary.name,
                label=summary.label,
                holdings=load_target_holdings(root, summary.name),
                budget=perf.budget,
                nav=navs[-1][1],
                start_session=perf.start_session,
                last_session=perf.last_session,
                navs=navs,
                since_return=None if perf.return_pct is None else perf.return_pct / 100.0,
                spy_since=None
                if perf.benchmark_return_pct is None
                else perf.benchmark_return_pct / 100.0,
                fill_rate=summary.latest_fill_rate,
                agreement=summary.positions_agreement,
                auth_state=str(getattr(auth, "state", "") or ""),
                auth_expires=getattr(auth, "expires_at", None),
                auth_days=getattr(auth, "days_remaining", None),
            )
        )
    rows.sort(key=lambda row: row.label)
    account = AccountInfo(
        equity=report.account.equity,
        age_hours=report.account.age_hours,
        status=str(report.account.status),
        kill_switch_enabled=bool(report.kill_switch.enabled),
        kill_switch_reason=report.kill_switch.reason,
        open_orders=report.open_order_count,
    )
    last = max((row.last_session for row in rows), default=None)
    sessions: tuple[date, ...] = ()
    closes: dict[date, float] = {}
    if last is not None:
        prices = load_session_prices(root, ("SPY",), last - timedelta(days=21)).get("SPY", {})
        closes = {day: bar[1] for day, bar in prices.items() if day <= last}
        sessions = tuple(sorted(closes))[-10:]
    return tuple(rows), account, sessions, closes


def _latest_stem(folder: Path) -> str | None:
    files = sorted(folder.glob("20??-??-??.json")) if folder.is_dir() else []
    return files[-1].stem if files else None


def collect_book(root: Path) -> tuple[BookAccount, ...]:
    accounts = []
    for account in BOOK_ACCOUNTS:
        base = root / BOOK_DIR / account
        daily_stem = _latest_stem(base / "daily")
        record = _read_json(base / "daily" / f"{daily_stem}.json") if daily_stem else None
        pnl = (record or {}).get("pnl") or {}
        rec = (record or {}).get("reconciliation") or {}
        accounts.append(
            BookAccount(
                account=account,
                latest_target=_latest_stem(base / "targets"),
                latest_plan=_latest_stem(base / "plans"),
                latest_daily=daily_stem,
                equity=pnl.get("equity"),
                net_pnl=pnl.get("net_pnl"),
                net_return=pnl.get("net_return"),
                n_orders=rec.get("n_orders"),
                n_filled=rec.get("n_filled"),
                n_unfilled=rec.get("n_unfilled"),
            )
        )
    return tuple(accounts)


def book_log_errors(path: Path, start: datetime) -> tuple[int, str | None]:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return 0, None
    count, last = 0, None
    start_naive = start.astimezone(UTC).replace(tzinfo=None)
    for line in lines:
        match = _LOG_LINE_RE.match(line)
        if not match or match.group(2) != "ERROR":
            continue
        try:
            at = datetime.fromisoformat(match.group(1))
        except ValueError:
            continue
        if at >= start_naive:
            count += 1
            last = match.group(3)[:200]
    return count, last


def collect_queue(
    root: Path, start: datetime
) -> tuple[tuple[TaskLine, ...], tuple[TaskLine, ...], tuple[TaskLine, ...], int, int]:
    from open_composer.cockpit.data.queue import parse_queue

    try:
        items = parse_queue((root / QUEUE_FILE).read_text(encoding="utf-8"))
    except OSError:
        return (), (), (), 0, 0

    def line(item: Any) -> TaskLine:
        return TaskLine(item.task_id, item.title, item.status_text)

    done = tuple(
        line(item)
        for item in items
        if item.status == "done" and item.updated_at is not None and item.updated_at >= start
    )
    review = tuple(line(item) for item in items if item.status == "review")
    running = tuple(line(item) for item in items if item.status == "running")
    ready = sum(1 for item in items if item.status == "ready")
    blocked = sum(1 for item in items if item.status == "blocked")
    return done, review, running, ready, blocked


def collect_commits(root: Path, start: datetime) -> tuple[Counter, int]:
    try:
        done = subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "log",
                f"--since={start.astimezone(UTC).isoformat()}",
                "--pretty=format:%s",
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return Counter(), 0
    kinds: Counter = Counter()
    subjects = [line for line in done.stdout.splitlines() if line.strip()]
    for subject in subjects:
        match = _COMMIT_KIND_RE.match(subject)
        kinds[match.group(1).lower() if match else "other"] += 1
    return kinds, len(subjects)


def _modal_status(root: Path) -> dict[str, Any] | None:
    try:
        done = subprocess.run(
            [sys.executable, str(root / "scripts" / "modal_budget.py"), "status"],
            capture_output=True,
            text=True,
            timeout=90,
            check=False,
            cwd=root,
        )
        payload = json.loads(done.stdout) if done.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None
    return payload if isinstance(payload, dict) else None


def _cron_reason(job: Any, *, now: datetime) -> str:
    if any(log.has_error_marker for log in job.logs):
        return "日志末尾有报错"
    times = [log.mtime for log in job.logs if log.mtime is not None]
    if times:
        return f"日志 {(now - max(times)).total_seconds() / 86400:.0f} 天没有更新"
    return "状态异常"


def collect_health(root: Path, start: datetime) -> HealthInfo:
    from open_composer.cockpit.data.health import build_health_report

    report = build_health_report(root)
    problems = tuple(
        f"{job.name}（{_cron_reason(job, now=datetime.now(UTC))}）"
        for job in report.cron.jobs
        if job.status in ("warn", "stale")
    )
    live = [entry for entry in report.data_freshness if entry.live]
    live_text = tuple(
        f"{entry.name} 最新 {entry.latest_date or '未知'}（{entry.status}）" for entry in live
    )
    live_problems = tuple(
        f"{entry.name} 最新 {entry.latest_date or '未知'}"
        for entry in live
        if entry.status in ("warn", "stale")
    )
    gate = _read_json(root / ROUND_GATE_STATUS) or {}
    pace = gate.get("pace") or {}
    limits = tuple(str(item) for item in gate.get("limits") or [])
    paused = tuple(str(item) for item in gate.get("paused_by_gate") or [])
    errors, last_error = book_log_errors(root / BOOK_LOG, start)
    return HealthInfo(
        cron_total=len(report.cron.jobs),
        cron_problems=problems,
        live_data=live_text,
        live_data_problems=live_problems,
        disk_percent=report.disk.used_percent if report.disk else None,
        memory_percent=report.memory.used_percent if report.memory else None,
        gate_used_share=pace.get("used_share"),
        gate_week_elapsed=pace.get("week_elapsed"),
        gate_checked_at=str(gate.get("checked_at") or "")[:16].replace("T", " ") or None,
        gate_paused=paused,
        gate_limits=limits,
        modal=_modal_status(root),
        book_log_errors=errors,
        book_log_last_error=last_error,
    )


def collect_round_reports(root: Path, start: datetime) -> tuple[RoundReport, ...]:
    folder = root / ROUND_DIR
    if not folder.is_dir():
        return ()
    reports = []
    for path in folder.glob("*.md"):
        match = _ROUND_FILE_RE.match(path.name)
        if not match:
            continue
        day, hour, minute, kind = match.groups()
        at = datetime.fromisoformat(f"{day}T{hour}:{minute}").replace(tzinfo=UTC)
        if at < start:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) > ROUND_REPORT_CHARS:
            text = (
                text[:ROUND_REPORT_CHARS].rstrip()
                + f"\n\n（截断，全文见 `{ROUND_DIR / path.name}`）"
            )
        reports.append(RoundReport(at, kind, str(ROUND_DIR / path.name), text))
    return tuple(sorted(reports, key=lambda report: report.at, reverse=True))


def load_sleeve_ledger(root: Path, name: str) -> dict[str, float]:
    payload = _read_json(root / REHEARSAL_DIR / f"{name}-latest.json") or {}
    ledger = payload.get("strategy_ledger_positions")
    if payload.get("position_scope") != "strategy_ledger" or not isinstance(ledger, dict):
        return {}
    out: dict[str, float] = {}
    for symbol, qty in ledger.items():
        try:
            value = float(qty)
        except (TypeError, ValueError):
            continue
        if isinstance(symbol, str) and value:
            out[symbol] = value
    return out


def collect_contributions(
    root: Path, sleeves: tuple[SleeveRow, ...], sessions: tuple[date, ...]
) -> dict[str, tuple[tuple[str, float], ...]]:
    if len(sessions) < 2 or not sleeves:
        return {}
    from open_composer.cockpit.data.paper import load_session_prices

    day, prev = sessions[-1], sessions[-2]
    ledgers = {row.name: load_sleeve_ledger(root, row.name) for row in sleeves}
    symbols = tuple(sorted({symbol for ledger in ledgers.values() for symbol in ledger}))
    prices = load_session_prices(root, symbols, prev)
    closes = {symbol: {d: bar[1] for d, bar in bars.items()} for symbol, bars in prices.items()}
    return {
        row.name: holding_contributions(ledgers[row.name], closes, day, prev, row.nav_on(prev))
        for row in sleeves
    }


def load_daily_text(root: Path, now: datetime) -> tuple[str | None, str | None]:
    """The writer's report for the UTC day of ``now`` (`reports/owner/daily/`)."""
    path = root / DAILY_DIR / f"{now.astimezone(UTC):%Y-%m-%d}.zh.md"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None, None
    return (text, str(path.relative_to(root))) if text.strip() else (None, None)


def load_weekly_text(root: Path, now: datetime) -> tuple[str | None, str | None]:
    path = root / WEEKLY_DIR / f"{iso_week_label(now)}.zh.md"
    try:
        return path.read_text(encoding="utf-8"), str(path.relative_to(root))
    except OSError:
        return None, None


def collect_digest(root: Path, now: datetime, kind: str) -> DigestData:
    """Gather everything; each source degrades to an entry in ``errors``."""
    window_start = now - (timedelta(days=7) if kind == "weekly" else timedelta(hours=24))
    errors: list[str] = []
    sleeves: tuple[SleeveRow, ...] = ()
    account: AccountInfo | None = None
    sessions: tuple[date, ...] = ()
    closes: dict[date, float] = {}
    try:
        sleeves, account, sessions, closes = _collect_paper(root, now)
    except Exception as exc:  # one failed source must not stop the mail
        errors.append(f"模拟盘数据读取失败（{type(exc).__name__}）")
    try:
        book = collect_book(root)
    except Exception as exc:
        book = ()
        errors.append(f"v1.2 账户文件读取失败（{type(exc).__name__}）")
    try:
        view_text = (root / CURRENT_VIEW).read_text(encoding="utf-8")
        sections = tuple(sections_since(parse_view_sections(view_text), window_start))
    except OSError as exc:
        sections = ()
        errors.append(f"研究判断页读取失败（{type(exc).__name__}）")
    done, review, running, ready, blocked = collect_queue(root, window_start)
    commits, commit_total = collect_commits(root, window_start)
    health: HealthInfo | None = None
    try:
        health = collect_health(root, window_start)
    except Exception as exc:
        errors.append(f"健康数据读取失败（{type(exc).__name__}）")
    weekly_text, weekly_path = (None, None)
    daily_text, daily_path = (None, None)
    if kind == "weekly":
        weekly_text, weekly_path = load_weekly_text(root, now)
    else:
        daily_text, daily_path = load_daily_text(root, now)
    contributions: dict[str, tuple[tuple[str, float], ...]] = {}
    try:
        contributions = collect_contributions(root, sleeves, sessions)
    except Exception as exc:
        errors.append(f"持仓贡献计算失败（{type(exc).__name__}）")
    round_reports = collect_round_reports(root, window_start)
    live_track = _read_json(root / LIVE_TRACK)
    forward = None
    try:
        forward = load_forward_rows(root)
    except Exception as exc:
        errors.append(f"前向对预期计算失败（{type(exc).__name__}）")
    book_actions: tuple[BookAction, ...] = ()
    try:
        book_actions = tuple(collect_book_actions(root))
    except Exception as exc:
        errors.append(f"v1.2 每日动作读取失败（{type(exc).__name__}）")
    return DigestData(
        now=now,
        window_start=window_start,
        kind=kind,
        sleeves=sleeves,
        sessions=sessions,
        spy_closes=closes,
        account=account,
        book=book,
        sections=sections,
        done_tasks=done,
        review_tasks=review,
        running_tasks=running,
        ready_count=ready,
        blocked_count=blocked,
        commits=commits,
        commit_total=commit_total,
        health=health,
        weekly_text=weekly_text,
        weekly_path=weekly_path,
        round_reports=round_reports,
        live_track=live_track,
        contributions=contributions,
        errors=tuple(errors),
        forward=forward,
        book_actions=book_actions,
        daily_text=daily_text,
        daily_path=daily_path,
    )
