from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from open_composer.notifications.email_smtp import (
    MailConfigError,
    build_message,
    load_mail_config,
    send_message,
)
from open_composer.reports import owner_digest as od
from open_composer.reports.owner_style import (
    apply_business_names,
    lint_errors,
    lint_owner_text,
)

VIEW = """# 当前判断（常设页）

## 2026-10-04（交互会话 09:43）：v1.2 live 数据验收，定时任务已装
- **live 目录验收（T-22）**：组合层核对通过。
  - 子项不进摘要。
- **新数据坑 #63**：回退市值有年内前视。

## 2026-10-04（主审轮 07:07）：v1.3 降成本规则否定，保留 v1.2（优先于下方所有章节）
- **v1.3 否定**：5 个规则无一满足。

## 2026-10-03（上午）：没有时间的章节
- 一条。

## 2026-09-28：S3 的调仓日运气（自动轮，优先于下方所有章节）
- 旧的。
"""


def _sleeve(
    label: str, navs: list[tuple[date, float]], *, start: date, auth_days: float = 27.0
) -> od.SleeveRow:
    return od.SleeveRow(
        name=label.lower(),
        label=label,
        holdings=(("XLK", 0.5), ("XLE", 0.5)),
        budget=15000.0,
        nav=navs[-1][1],
        start_session=start,
        last_session=navs[-1][0],
        navs=tuple(navs),
        since_return=navs[-1][1] / 15000.0 - 1.0,
        spy_since=0.0044,
        fill_rate=1.0,
        agreement="broker holds exactly the sum of all sleeve ledgers (2/2 symbols)",
        auth_state="authorized",
        auth_expires=datetime(2026, 11, 1, 7, 15, tzinfo=UTC),
        auth_days=auth_days,
    )


SESSIONS = tuple(
    date(2026, m, d) for m, d in [(9, 24), (9, 25), (9, 28), (9, 29), (9, 30), (10, 1), (10, 2)]
)

LIVE_TRACK = {
    "updated_at": "2026-10-04T17:54Z",
    "rule": "前向记录从 09-01 算，加满 10 个真实模拟会话",
    "live": [],
    "candidates": [
        {
            "id": "S1",
            "label": "S1 · Sector rotation",
            "stage": "模拟盘",
            "paper_since": "2026-09-21",
            "next": "稳健性复核",
            "next_due": "2026-10-08",
            "proposal_due": "2026-10-13",
        },
        {
            "id": "V12F1",
            "label": "v1.2 F1",
            "stage": "P1",
            "paper_since": None,
            "next": "10-07 首单",
            "next_due": "2026-10-07",
            "proposal_due": "2026-10-21",
        },
    ],
    "engines": [
        {"name": "日频股票组合", "now": "v1.2 在 P1", "next": "每日调仓", "due": "2026-10-09"}
    ],
    "owner_decisions": [
        {"item": "实盘资金规模", "due": "2026-10-08"},
        {"item": "远期事项", "due": "2026-11-30"},
    ],
}


def _data(**overrides) -> od.DigestData:
    s1 = _sleeve(
        "S1 · Sector rotation",
        [(day, 15000.0 + 10.0 * i) for i, day in enumerate(SESSIONS)],
        start=SESSIONS[0],
    )
    c2 = _sleeve(
        "C2 · Month-end",
        [(date(2026, 10, 1), 14983.0), (date(2026, 10, 2), 15058.0)],
        start=date(2026, 10, 1),
    )
    base = dict(
        now=datetime(2026, 10, 5, 0, 50, tzinfo=UTC),
        window_start=datetime(2026, 10, 4, 0, 50, tzinfo=UTC),
        kind="daily",
        sleeves=(c2, s1),
        sessions=SESSIONS,
        spy_closes={day: 760.0 + i for i, day in enumerate(SESSIONS)},
        account=od.AccountInfo(107224.5, 10.0, "ok", False, None, 0),
        book=(
            od.BookAccount("quant1", "2026-09-17", "2026-09-18", None),
            od.BookAccount("quant2", None, None, None),
        ),
        sections=tuple(od.parse_view_sections(VIEW)[:2]),
        done_tasks=(od.TaskLine("T-20261004-55", "S3 九月差距", "done"),),
        review_tasks=(),
        running_tasks=(od.TaskLine("T-20261004-54", "时点泄漏审计", "running"),),
        ready_count=6,
        blocked_count=4,
        commits=Counter({"research": 3, "queue": 2}),
        commit_total=5,
        health=od.HealthInfo(
            cron_total=31,
            cron_problems=(),
            live_data=("SIP daily archive 最新 2026-10-02（ok）",),
            live_data_problems=(),
            disk_percent=72.0,
            memory_percent=80.0,
            gate_used_share=0.045,
            gate_week_elapsed=0.073,
            gate_checked_at="2026-10-04 12:20",
            gate_paused=(),
            gate_limits=(),
            modal={"billed_usd": 1.18, "projected_usd": 4.13, "cap_usd": 25.0},
            book_log_errors=0,
            book_log_last_error=None,
        ),
    )
    base.update(overrides)
    return od.DigestData(**base)


def test_parse_view_sections_reads_dates_times_titles_and_top_bullets() -> None:
    sections = od.parse_view_sections(VIEW)
    assert [(s.day.isoformat(), s.time) for s in sections] == [
        ("2026-10-04", "09:43"),
        ("2026-10-04", "07:07"),
        ("2026-10-03", None),
        ("2026-09-28", None),
    ]
    assert sections[0].bullets == (
        "live 目录验收（T-22）：组合层核对通过。",
        "新数据坑 #63：回退市值有年内前视。",
    )
    assert sections[1].title == "v1.3 降成本规则否定，保留 v1.2"
    assert sections[3].title == "S3 的调仓日运气"


def test_sections_since_filters_by_time_and_sorts_newest_first() -> None:
    sections = od.parse_view_sections(VIEW)
    chosen = od.sections_since(sections, datetime(2026, 10, 4, 8, 0, tzinfo=UTC))
    assert [(s.day.isoformat(), s.time) for s in chosen] == [("2026-10-04", "09:43")]
    chosen = od.sections_since(sections, datetime(2026, 10, 3, 1, 0, tzinfo=UTC))
    assert [(s.day.isoformat(), s.time) for s in chosen] == [
        ("2026-10-04", "09:43"),
        ("2026-10-04", "07:07"),
        ("2026-10-03", None),
    ]


def test_returns_count_a_late_starting_sleeve_at_its_budget() -> None:
    data = _data()
    c2, s1 = data.sleeves
    assert c2.nav_on(date(2026, 9, 30)) == 15000.0
    day, week = od.sleeve_returns(s1, SESSIONS)
    assert day == pytest.approx(15060.0 / 15050.0 - 1.0)
    assert week == pytest.approx(15060.0 / 15010.0 - 1.0)
    total, day_all, week_all = od.combined_returns(data.sleeves, SESSIONS)
    assert total == pytest.approx(15058.0 + 15060.0)
    assert day_all == pytest.approx((15058.0 + 15060.0) / (14983.0 + 15050.0) - 1.0)
    assert week_all == pytest.approx((15058.0 + 15060.0) / (15000.0 + 15010.0) - 1.0)
    assert c2.max_drawdown == pytest.approx(14983.0 / 15000.0 - 1.0)


def test_spy_returns_use_close_to_close() -> None:
    closes = {day: 760.0 + i for i, day in enumerate(SESSIONS)}
    day, week = od.spy_returns(closes, SESSIONS)
    assert day == pytest.approx(766.0 / 765.0 - 1.0)
    assert week == pytest.approx(766.0 / 761.0 - 1.0)
    assert od.spy_returns({}, SESSIONS) == (None, None)


def test_attention_items_flag_kill_switch_expiry_errors_and_gate() -> None:
    assert od.attention_items(_data()) == []
    health = _data().health
    flagged = _data(
        now=datetime(2026, 10, 6, 0, 50, tzinfo=UTC),  # Tuesday: a weekday snapshot is due
        account=od.AccountInfo(100000.0, 40.0, "warn", True, "manual stop", 0),
        sleeves=(
            _sleeve("S3 · Levered", [(SESSIONS[-1], 15000.0)], start=SESSIONS[-1], auth_days=9.0),
        ),
        health=od.HealthInfo(
            **{
                **health.__dict__,
                "cron_problems": ("round_limit_gate.py（warn）",),
                "gate_paused": ("38928f29",),
                "book_log_errors": 2,
                "book_log_last_error": "no plan file for quant1",
            }
        ),
        errors=("模拟盘数据读取失败（OSError）",),
    )
    items = od.attention_items(flagged)
    joined = "\n".join(items)
    assert "紧急停止开关已打开：manual stop" in joined
    assert "40 小时没有更新" in joined
    assert "9 天后到期" in joined
    assert "round_limit_gate.py" in joined
    assert "38928f29" in joined
    assert "报错 2 次" in joined
    assert "汇报脚本自身问题" in joined
    owner = "\n".join(od.owner_items(flagged))
    ops = "\n".join(od.ops_items(flagged))
    assert "manual stop" in owner and "9 天后到期" in owner
    assert "round_limit_gate.py" not in owner and "round_limit_gate.py" in ops
    assert "40 小时没有更新" in ops and "汇报脚本自身问题" in ops


def test_owner_decisions_due_within_a_week_need_the_owner() -> None:
    items = od.owner_items(_data(live_track=LIVE_TRACK))
    assert items == ["待你决定：实盘资金规模（10-08 前）"]
    assert od.ops_items(_data(live_track=LIVE_TRACK)) == []


def test_holding_contributions_split_the_day_and_leave_a_residual() -> None:
    prev, day = date(2026, 10, 1), date(2026, 10, 2)
    closes = {"XLK": {prev: 100.0, day: 102.0}, "XLE": {prev: 50.0, day: 49.0}, "ZZZ": {day: 1.0}}
    parts = od.holding_contributions(
        {"XLK": 75.0, "XLE": 150.0, "ZZZ": 5.0}, closes, day, prev, 15000.0
    )
    assert [symbol for symbol, _ in parts] == ["XLK", "XLE"]  # no prior close for ZZZ
    assert parts[0][1] == pytest.approx(75.0 * 2.0 / 15000.0)
    assert parts[1][1] == pytest.approx(-150.0 / 15000.0)
    s1 = _sleeve("S1 · Sector rotation", [(prev, 15000.0), (day, 15100.0)], start=prev)
    text = "\n".join(
        od._render_contributions(
            _data(sleeves=(s1,), sessions=(prev, day), contributions={s1.name: parts})
        )
    )
    # day return +0.667% = XLK +1.00% + XLE -1.00% + residual +0.67% (rebalanced that day)
    assert "S1（+0.67%）：XLK +1.00%、XLE -1.00%；调仓与现金 +0.67%" in text


def test_live_track_table_counts_real_paper_sessions() -> None:
    lines = "\n".join(od._render_live_track(_data(live_track=LIVE_TRACK)))
    assert "实盘：没有。" in lines
    # 09-21 .. 10-02 holds ten US equity sessions
    assert "| S1 · Sector rotation | 模拟盘 | 2026-09-21 | 10/10 |" in lines
    assert "| v1.2 F1 | P1 | — | — |" in lines
    assert "**日频股票组合**：现在 v1.2 在 P1；下一步 每日调仓（2026-10-09）" in lines
    assert "缺失" in "\n".join(od._render_live_track(_data()))
    assert od.paper_sessions_since("2026-10-05", date(2026, 10, 2)) == 0
    assert od.paper_sessions_since(None, date(2026, 10, 2)) is None


def test_round_reports_are_read_from_the_window_newest_first(tmp_path: Path) -> None:
    folder = tmp_path / od.ROUND_DIR
    folder.mkdir(parents=True)
    (folder / "2026-10-04T1907Z-lead.md").write_text("# 主审轮\n\n## 结论\n- A\n", encoding="utf-8")
    (folder / "2026-10-04T2207Z-exec.md").write_text("# 执行轮\n\n- B\n", encoding="utf-8")
    (folder / "2026-10-02T1907Z-lead.md").write_text("old", encoding="utf-8")
    (folder / "README.md").write_text("not a report", encoding="utf-8")
    reports = od.collect_round_reports(tmp_path, datetime(2026, 10, 4, 0, 50, tzinfo=UTC))
    assert [(r.at.hour, r.kind) for r in reports] == [(22, "exec"), (19, "lead")]
    text = "\n".join(od._render_rounds(_data(round_reports=reports)))
    assert "### 执行轮 10-04 22:07 UTC" in text and "### 主审轮 10-04 19:07 UTC" in text
    assert "#### 结论" in text and "# 主审轮" not in text.splitlines()
    assert "### 执行轮 10-04 22:07 UTC\n\n- B" in text
    assert "没有落盘" in "\n".join(od._render_rounds(_data()))


def test_sleeve_ledger_reads_only_dedicated_ledgers(tmp_path: Path) -> None:
    folder = tmp_path / od.REHEARSAL_DIR
    folder.mkdir(parents=True)
    (folder / "s1-latest.json").write_text(
        '{"position_scope": "strategy_ledger",'
        ' "strategy_ledger_positions": {"XLK": 39, "XLE": "x", "Z": 0}}',
        encoding="utf-8",
    )
    (folder / "shared-latest.json").write_text(
        '{"position_scope": "account", "strategy_ledger_positions": {"XLK": 1}}', encoding="utf-8"
    )
    assert od.load_sleeve_ledger(tmp_path, "s1") == {"XLK": 39.0}
    assert od.load_sleeve_ledger(tmp_path, "shared") == {}
    assert od.load_sleeve_ledger(tmp_path, "missing") == {}


def test_internal_log_keeps_the_old_sections_and_numbers() -> None:
    text = od.render_internal_log(_data())
    for heading in (
        "## 需要你处理",
        "## 一、模拟盘",
        "## 二、股票组合 v1.2",
        "## 三、离实盘多远",
        "## 四、自动轮汇报",
        "## 五、研究进展",
        "## 六、运行健康",
    ):
        assert heading in text
    assert "- 没有。" in text
    assert "| **合计** |" in text
    assert "T-20261004-55" in text and "运行中 T-20261004-54" in text
    assert "需要你处理 0 项，运行异常 0 项" in text
    assert "提交 5 次（研究 3、队列 2）" in text
    subject = od.digest_subject(_data())
    assert subject.startswith("[Open Composer] 日报 10-05（周一）")
    assert subject.endswith("需要你决定 0")


def test_render_weekly_embeds_the_written_report_or_says_it_is_missing() -> None:
    written = od.render_digest(_data(kind="weekly", weekly_text="# 周报 2026-W41\n\n结论。\n"))
    assert written.startswith("# 周报 2026-W41")
    assert "## 附：一周数据（自动生成）" in written
    assert "见邮件附件" in written
    missing = od.render_digest(_data(kind="weekly"))
    assert "本周的文字总结没有写成" in missing
    assert "本周判断未写" in od.render_internal_log(_data(kind="weekly"))


def test_markdown_to_html_renders_tables_and_nested_lists() -> None:
    html = od.markdown_to_html("| a | b |\n|---|---|\n| 1 | 2 |\n\n- x\n  - y\n")
    assert "<table>" in html and "<td>1</td>" in html
    assert html.count("<ul>") == 2


def test_book_log_errors_counts_only_the_window(tmp_path: Path) -> None:
    log = tmp_path / "book.log"
    log.write_text(
        "2026-10-03T22:40:00Z ERROR old failure\n"
        "2026-10-04T22:40:00Z INFO run: ok\n"
        "2026-10-04T22:45:00Z ERROR no plan file for quant1 on 2026-10-05\n",
        encoding="utf-8",
    )
    count, last = od.book_log_errors(log, datetime(2026, 10, 4, 0, 50, tzinfo=UTC))
    assert count == 1 and last == "no plan file for quant1 on 2026-10-05"


def test_load_target_holdings_keeps_positive_weights(tmp_path: Path) -> None:
    folder = tmp_path / od.EXECUTION_DIR
    folder.mkdir(parents=True)
    (folder / "s3-target-weights.json").write_text(
        '{"target_weights": [{"symbol": "TECL", "target_weight": 0.5},'
        ' {"symbol": "SHY", "target_weight": 0.0}, {"leg": "cash", "target_weight": 0.0},'
        ' {"symbol": "UPRO", "target_weight": 0.5}]}',
        encoding="utf-8",
    )
    assert od.load_target_holdings(tmp_path, "s3") == (("TECL", 0.5), ("UPRO", 0.5))
    assert od.load_target_holdings(tmp_path, "missing") == ()


def test_mail_config_hides_password_and_reports_missing_keys(tmp_path: Path) -> None:
    env = tmp_path / "mail.env"
    env.write_text(
        "SMTP_HOST=smtp.example.com\nSMTP_PORT=587\nSMTP_USER=me@example.com\n"
        "SMTP_PASSWORD='s3cret'\nMAIL_FROM=me@example.com\nMAIL_TO=a@example.com, b@example.com\n",
        encoding="utf-8",
    )
    config = load_mail_config(env)
    assert config.recipients == ("a@example.com", "b@example.com")
    assert config.password == "s3cret" and "s3cret" not in repr(config)
    env.write_text("SMTP_PORT=587\nSMTP_PASSWORD=s3cret\n", encoding="utf-8")
    with pytest.raises(MailConfigError) as err:
        load_mail_config(env)
    assert "SMTP_HOST" in str(err.value) and "s3cret" not in str(err.value)


class _FakeSMTP:
    instances: list[_FakeSMTP] = []

    def __init__(self, host: str, port: int, **kwargs) -> None:
        self.host, self.port, self.kwargs = host, port, kwargs
        self.calls: list[str] = []
        _FakeSMTP.instances.append(self)

    def __enter__(self) -> _FakeSMTP:
        return self

    def __exit__(self, *exc) -> None:
        self.calls.append("quit")

    def starttls(self, context=None) -> None:
        self.calls.append("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(f"login:{user}")

    def send_message(self, message) -> None:
        self.calls.append(f"send:{message['Subject']}")


def test_send_message_uses_starttls_on_587_and_ssl_on_465(tmp_path: Path) -> None:
    env = tmp_path / "mail.env"
    body = (
        "SMTP_HOST=smtp.example.com\nSMTP_PORT={port}\nSMTP_USER=me\n"
        "SMTP_PASSWORD=pw\nMAIL_FROM=me@x\nMAIL_TO=you@x\n"
    )
    env.write_text(body.format(port=587), encoding="utf-8")
    config = load_mail_config(env)
    message = build_message(config, "日报", "正文", "<p>正文</p>")
    assert message.is_multipart()
    _FakeSMTP.instances.clear()
    send_message(config, message, smtp_factory=_FakeSMTP)
    assert _FakeSMTP.instances[0].calls == ["starttls", "login:me", "send:日报", "quit"]
    env.write_text(body.format(port=465), encoding="utf-8")
    config = load_mail_config(env)
    send_message(config, build_message(config, "s", "t"), smtp_factory=_FakeSMTP)
    assert _FakeSMTP.instances[1].calls == ["login:me", "send:s", "quit"]
    assert "context" in _FakeSMTP.instances[1].kwargs


def test_a_bullet_ending_in_a_colon_takes_its_first_nested_bullet() -> None:
    text = (
        "## 2026-10-04（交互会话 10:10）：更新\n- **10:10 更新（交互会话）**：\n"
        "  - **T-30 完成**：S3 占 89%。\n  - 第二条不要。\n"
    )
    (section,) = od.parse_view_sections(text)
    assert section.bullets == ("10:10 更新（交互会话）： T-30 完成：S3 占 89%。",)


def test_weekly_lists_section_titles_only_and_caps_the_task_list() -> None:
    many = tuple(od.TaskLine(f"T-202610{i:02d}-01", f"任务 {i}", "done") for i in range(40))
    text = od.render_internal_log(_data(kind="weekly", done_tasks=many))
    assert "live 目录验收（T-22）" not in text  # bullets are daily-only
    assert "v1.2 live 数据验收" in text
    assert "……另 10 项" in text


# ---------------------------------------------------------------------------
# Owner-facing body (2026-10-06 rewrite)
# ---------------------------------------------------------------------------

OWNER_TRACK = {
    **LIVE_TRACK,
    "owner_decisions": [
        {"item": "实盘资金是否按约 2 万美元设计", "due": "2026-10-10", "default": "按 2 万美元"},
    ],
    "owner_asks": [
        {
            "asked": "2026-10-06",
            "topic": "必须做高频策略",
            "answer": "先调研再做（T-20261006-12）",
            "next": "10-10 前上模拟盘",
            "due": "2026-10-10",
            "status": "进行中",
        }
    ],
}


def _named_sleeves() -> tuple[od.SleeveRow, ...]:
    row = _sleeve(
        "S3 · Levered rotation",
        [(day, 15000.0 + 20.0 * i) for i, day in enumerate(SESSIONS)],
        start=SESSIONS[0],
    )
    return (od.SleeveRow(**{**row.__dict__, "name": "us_etf_levered_rotation_63_top2_monthly"}),)


def test_daily_body_is_the_written_report_plus_the_attachment_pointer() -> None:
    written = "# Open Composer 日报 · 10-07\n\n## 一、结论\n\n1. S3 今天涨了。\n"
    text = od.render_digest(_data(daily_text=written, daily_path="reports/owner/daily/x.zh.md"))
    assert text.startswith("# Open Composer 日报 · 10-07")
    assert "杠杆轮动 今天涨了" in text  # fixed codes get their business name
    assert "## 附：证据（不必读）" in text and "见邮件附件" in text
    assert "## 四、自动轮汇报" not in text


def test_daily_fallback_has_business_names_and_passes_the_lint() -> None:
    data = _data(sleeves=_named_sleeves(), live_track=OWNER_TRACK)
    text = od.render_digest(data)
    assert "今天的文字总结没有按时写成" in text
    assert "| 杠杆轮动 |" in text and "能源（XLE）50%" in text
    assert "市场中性账户" in text and "还没有开始交易" in text
    assert "| 实盘资金是否按约 2 万美元设计 | 10-10 | 按 2 万美元 |" in text
    assert "先调研再做" in text and "T-20261006-12" not in text
    assert lint_errors(text) == []


def test_problem_items_leave_out_quota_gate_and_probe_noise() -> None:
    health = _data().health
    noisy = _data(
        health=od.HealthInfo(
            **{
                **health.__dict__,
                "cron_problems": (
                    "round_limit_gate.py（日志末尾有报错）",
                    "book_paper_cls_probe.py（日志末尾有报错）",
                ),
                "gate_paused": ("38928f29",),
                "gate_limits": ("five_hour",),
            }
        )
    )
    assert od.problem_items(noisy) == []
    real = _data(
        health=od.HealthInfo(
            **{**health.__dict__, "cron_problems": ("run_daily_paper_cycle.py（日志末尾有报错）",)}
        )
    )
    assert od.problem_items(real) == ["交易或行情相关的定时任务有 1 个报错，正在处理，明细见附件。"]


def test_lint_flags_codes_paths_and_long_brackets_but_not_the_appendix() -> None:
    text = (
        "# 日报\n\n- T75 和 T-20261005-31 完成，S3 的权重按 v1.2 定。\n"
        "- 见 `reports/x.md`"
        "（这是一段超过三十个字的括号说明，只有我们自己需要知道的内部处理细节）。\n"
        "\n## 附：证据\n\n- `reports/research/intel/I-20261004-03-x.md`，T-20261005-31\n"
    )
    findings = lint_owner_text(text)
    errors = {(f.kind, f.text) for f in findings if f.level == "error"}
    assert ("任务编号", "T75") in errors
    assert ("任务或档案编号", "T-20261005-31") in errors
    assert ("策略或计划代号", "S3") in errors and ("版本代号", "v1.2") in errors
    assert any(kind == "代码或路径" for kind, _ in errors)
    assert any(f.kind == "括号里的长说明" for f in findings)
    assert all(f.line <= 4 for f in findings)  # nothing from the appendix


def test_apply_business_names_stops_at_the_appendix() -> None:
    text = "S1、C2 和 v1.2 F1；quant2\n## 附：证据\nS1 路径\n"
    out = apply_business_names(text)
    assert out.splitlines()[0] == "行业轮动、月末效应 和 股票多空（市场中性）；SPY 增强账户"
    assert out.splitlines()[-1] == "S1 路径"
    assert "XS1" in apply_business_names("XS1") and "S10" in apply_business_names("S10")


def test_build_message_attaches_markdown(tmp_path: Path) -> None:
    env = tmp_path / "mail.env"
    env.write_text(
        "SMTP_HOST=smtp.example.com\nSMTP_PORT=587\nSMTP_USER=a@example.com\n"
        "SMTP_PASSWORD=pw\nMAIL_FROM=a@example.com\nMAIL_TO=a@example.com\n",
        encoding="utf-8",
    )
    config = load_mail_config(env)
    message = build_message(config, "s", "正文", "<p>正文</p>", [("运行记录.md", "# 记录\n")])
    parts = list(message.iter_attachments())
    assert len(parts) == 1
    assert parts[0].get_filename() == "运行记录.md"
    assert parts[0].get_content_type() == "text/markdown"
