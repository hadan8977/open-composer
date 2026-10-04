"""Owner digest: the daily and weekly e-mail report (`docs/owner-reporting.zh.md`).

Deterministic and read-only.  It reuses the cockpit's builders (paper, health,
queue), reads the research log files and git, and calls no model and no broker.
`collect_digest` does all the I/O; `render_digest` and `digest_subject` are pure.
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

BEIJING = ZoneInfo("Asia/Shanghai")
WEEKDAYS = "一二三四五六日"
CURRENT_VIEW = Path("docs/current-view.zh.md")
QUEUE_FILE = Path("reports/research/control/autonomous-queue.md")
ROUND_GATE_STATUS = Path("logs/autonomous/round-gate-status.json")
BOOK_DIR = Path("reports/paper/book")
BOOK_LOG = Path("logs/book_v12_daily.log")
EXECUTION_DIR = Path("reports/execution")
WEEKLY_DIR = Path("reports/owner/weekly")
BOOK_ACCOUNTS = ("quant1", "quant2")
AUTH_WARN_DAYS = 14.0
DISK_WARN_PERCENT = 85.0
ACCOUNT_STALE_HOURS = 30.0
MAX_SECTION_BULLETS = 8
MAX_DONE_TASKS = 30
BULLET_CHARS = 220

_HEADING_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2})(?:（(.*?)）)?[：:]\s*(.*)$")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
_PRIORITY_RE = re.compile(r"（[^（）]*优先于下方[^（）]*）\s*$")
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
    errors: tuple[str, ...] = ()


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


def attention_items(data: DigestData) -> list[str]:
    items: list[str] = []
    account = data.account
    if account is not None:
        if account.kill_switch_enabled:
            items.append(f"紧急停止开关已打开：{account.kill_switch_reason or '原因未记录'}")
        if (
            account.age_hours is not None
            and account.age_hours > ACCOUNT_STALE_HOURS
            and data.now.astimezone(UTC).weekday() in (1, 2, 3, 4, 5)
        ):
            items.append(f"主模拟账户快照已 {account.age_hours:.0f} 小时没有更新")
    for row in data.sleeves:
        if row.auth_days is not None and row.auth_days <= AUTH_WARN_DAYS:
            when = f"{row.auth_expires:%m-%d %H:%M} UTC" if row.auth_expires else "日期未知"
            items.append(f"{row.label} 的模拟授权 {row.auth_days:.0f} 天后到期（{when}）")
        if row.auth_state not in ("authorized", ""):
            items.append(f"{row.label} 的授权状态是 {row.auth_state}")
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


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _holdings_text(row: SleeveRow) -> str:
    if not row.holdings:
        return "—"
    return "、".join(f"{symbol} {weight * 100:.0f}%" for symbol, weight in row.holdings)


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
        "quant1 跑 F1（市场中性多空 + 短债），quant2 跑 F2（SPY 打底 + 0.3 倍多空叠加），"
        "各 100 万美元模拟资金。",
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


def render_digest(data: DigestData) -> str:
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
        out.append(f"# Open Composer {title} · {label}")
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
    items = attention_items(data)
    _, day_ret, week_ret = combined_returns(data.sleeves, data.sessions)
    spy_day, spy_week = spy_returns(data.spy_closes, data.sessions)
    period = "本周" if data.kind == "weekly" else "过去 24 小时"
    out.extend(
        [
            "",
            f"**概览**：ETF 子策略当日 {pct(day_ret)}（SPY {pct(spy_day)}），"
            f"近 5 日 {pct(week_ret)}（SPY {pct(spy_week)}）；"
            f"{period}完成或复核 {len(data.done_tasks)} 项研究任务，"
            f"提交 {data.commit_total} 次；需要你处理 {len(items)} 项。",
        ]
    )
    out.extend(["", "## 需要你处理", ""])
    out.extend([f"- {item}" for item in items] or ["- 没有。"])
    out.extend(["", "## 一、模拟盘（ETF 子策略）", ""])
    out.extend(_render_paper(data))
    out.extend(["", "## 二、股票组合 v1.2（quant1 / quant2）", ""])
    out.extend(_render_book(data))
    out.extend(["", f"## 三、研究进展（{period}）", ""])
    out.extend(_render_research(data))
    out.extend(["", "## 四、运行健康", ""])
    out.extend(_render_health(data))
    out.extend(
        [
            "",
            "实盘：没有。实盘要过 P2，再加 20 个模拟会话和执行验收，最后由你决定。",
            "",
            "详细页面在 cockpit（Cloudflare Access 登录）；"
            "所有数字的来源见 `docs/owner-reporting.zh.md` 第 4 节。",
        ]
    )
    return "\n".join(out) + "\n"


def digest_subject(data: DigestData) -> str:
    _, day_ret, week_ret = combined_returns(data.sleeves, data.sessions)
    spy_day, spy_week = spy_returns(data.spy_closes, data.sessions)
    pending = len(attention_items(data))
    if data.kind == "weekly":
        head = f"[Open Composer] 周报 {iso_week_label(data.now)}"
        money_part = f"子策略近 5 日 {pct(week_ret)}，SPY {pct(spy_week)}"
    else:
        local = data.now.astimezone(BEIJING)
        head = f"[Open Composer] 日报 {local:%m-%d}（周{WEEKDAYS[local.weekday()]}）"
        money_part = f"子策略当日 {pct(day_ret)}，SPY {pct(spy_day)}"
    return f"{head}｜{money_part}｜待处理 {pending}"


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
    if kind == "weekly":
        weekly_text, weekly_path = load_weekly_text(root, now)
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
        errors=tuple(errors),
    )
