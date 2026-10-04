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


def test_render_daily_has_fixed_sections_and_numbers() -> None:
    text = od.render_digest(_data())
    for heading in (
        "## 需要你处理",
        "## 一、模拟盘",
        "## 二、股票组合 v1.2",
        "## 三、研究进展",
        "## 四、运行健康",
    ):
        assert heading in text
    assert "- 没有。" in text
    assert "| **合计** |" in text
    assert "T-20261004-55" in text and "运行中 T-20261004-54" in text
    assert "实盘：没有。" in text
    assert "提交 5 次（研究 3、队列 2）" in text
    subject = od.digest_subject(_data())
    assert subject.startswith("[Open Composer] 日报 10-05（周一）")
    assert subject.endswith("待处理 0")


def test_render_weekly_embeds_the_written_report_or_says_it_is_missing() -> None:
    written = od.render_digest(_data(kind="weekly", weekly_text="# 周报 2026-W41\n\n结论。\n"))
    assert written.startswith("# 周报 2026-W41")
    assert "# 附：一周数据" in written
    missing = od.render_digest(_data(kind="weekly"))
    assert "本周判断未写" in missing


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
    text = od.render_digest(_data(kind="weekly", done_tasks=many))
    assert "live 目录验收（T-22）" not in text  # bullets are daily-only
    assert "v1.2 live 数据验收" in text
    assert "……另 10 项" in text
