"""The Today screen (`/`, 2026-10-04): the four blocks built from a synthetic
digest plus a live-track file, the cache contract (a request never collects),
and the route's empty states. The digest fixture mirrors
``tests/test_owner_digest.py`` so the page's numbers are the mail's numbers."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data import today as T
from open_composer.cockpit.data.reports import build_report_index
from open_composer.cockpit.viz import sparkline_points
from open_composer.reports import owner_digest as od

NOW = datetime(2026, 10, 5, 6, 0, tzinfo=UTC)
SESSIONS = tuple(
    date(2026, m, d) for m, d in [(9, 24), (9, 25), (9, 28), (9, 29), (9, 30), (10, 1), (10, 2)]
)
TRACK = {
    "updated_at": "2026-10-04T17:54Z",
    "rule": "机主 10-04：满 10 个真实模拟会话，复核通过后提实盘试点",
    "live": [],
    "candidates": [
        {
            "id": "S1",
            "strategy": "s1",
            "label": "S1 · Sector rotation",
            "stage": "模拟盘",
            "paper_since": "2026-09-21",
            "next": "稳健性与主题复核",
            "next_due": "2026-10-08",
            "proposal_due": "2026-10-13",
        },
        {
            "id": "V12F1",
            "strategy": "book_v12 F1 (quant1)",
            "label": "v1.2 F1 · 市场中性多空",
            "stage": "P1，10-07 开始模拟盘",
            "paper_since": None,
            "next": "10-05/06 彩排",
            "next_due": "2026-10-07",
            "proposal_due": "2026-10-21",
        },
    ],
    "engines": [
        {
            "id": "E1",
            "name": "日频股票组合",
            "now": "v1.2 在 P1",
            "next": "日频调仓",
            "due": "2026-10-09",
        }
    ],
    "owner_decisions": [
        {"item": "实盘资金规模", "due": "2026-10-08"},
        {"item": "授权实盘下单路径", "due": "2026-10-12"},
        {"item": "没有日期的事", "due": "soon"},
    ],
}


def _sleeve(name: str, label: str, navs: list[tuple[date, float]], *, start: date) -> od.SleeveRow:
    return od.SleeveRow(
        name=name,
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
        auth_days=27.0,
    )


def _health(**overrides) -> od.HealthInfo:
    base = dict(
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
        modal=None,
        book_log_errors=0,
        book_log_last_error=None,
    )
    base.update(overrides)
    return od.HealthInfo(**base)


def _digest(**overrides) -> od.DigestData:
    s1 = _sleeve(
        "s1",
        "S1 · Sector rotation",
        [(d, 15000.0 + 10.0 * i) for i, d in enumerate(SESSIONS)],
        start=SESSIONS[0],
    )
    c2 = _sleeve(
        "c2",
        "C2 · Month-end",
        [(date(2026, 10, 1), 14983.0), (date(2026, 10, 2), 15058.0)],
        start=date(2026, 10, 1),
    )
    base = dict(
        now=NOW,
        window_start=datetime(2026, 10, 4, 6, 0, tzinfo=UTC),
        kind="daily",
        sleeves=(c2, s1),
        sessions=SESSIONS,
        spy_closes={d: 760.0 + i for i, d in enumerate(SESSIONS)},
        account=od.AccountInfo(107224.5, 10.0, "ok", False, None, 0),
        book=(
            od.BookAccount("quant1", "2026-10-02", "2026-10-02", None),
            od.BookAccount("quant2", None, None, None),
        ),
        sections=(),
        done_tasks=(),
        review_tasks=(od.TaskLine("T-1", "审", "done（待主审）"),),
        running_tasks=(),
        ready_count=6,
        blocked_count=4,
        commits=Counter(),
        commit_total=0,
        health=_health(),
        live_track=TRACK,
    )
    base.update(overrides)
    return od.DigestData(**base)


def _sources(data: od.DigestData | None = None, error: str | None = None) -> T.TodaySources:
    return T.TodaySources(collected_at=NOW, digest=data, error=error, view_sections=())


def _report(
    tmp_path: Path, data: od.DigestData | None = None, *, track=TRACK, sources=None
) -> T.TodayReport:
    return T.build_today_report(
        tmp_path,
        sources=sources if sources is not None else _sources(data or _digest()),
        track=track,
        index=build_report_index(tmp_path, now=NOW),
        now=NOW,
    )


# --------------------------------------------------------------------------
# Block 1: needs you
# --------------------------------------------------------------------------


def test_needs_is_ok_when_nothing_is_listed(tmp_path: Path) -> None:
    report = _report(tmp_path, track={**TRACK, "owner_decisions": []})
    assert (report.needs.level, report.needs.word) == ("ok", "OK")
    assert T.needs_summary(report.needs) == "Nothing needs you"


def test_needs_lists_the_mail_items_and_dated_decisions(tmp_path: Path) -> None:
    report = _report(tmp_path)
    needs = report.needs
    assert needs.items == ()  # decisions are structured, not repeated as text
    assert [(d.item, d.days_left) for d in needs.decisions] == [
        ("实盘资金规模", 3),
        ("授权实盘下单路径", 7),
        ("没有日期的事", None),
    ]
    assert (needs.level, needs.word) == ("warn", "Attention")
    assert T.needs_summary(needs) == "decision due in 3d"


def test_needs_is_a_problem_only_when_something_stopped(tmp_path: Path) -> None:
    halted = _digest(account=od.AccountInfo(100000.0, 1.0, "ok", True, "manual stop", 0))
    report = _report(tmp_path, halted)
    assert report.needs.word == "Problem"
    assert any("紧急停止" in item for item in report.needs.items)
    driver = _digest(health=_health(book_log_errors=1, book_log_last_error="no plan"))
    report = _report(tmp_path, driver)
    assert report.needs.word == "Attention"  # the research side fixes a driver error
    assert any("每日驱动报错" in item for item in report.needs.ops)
    assert T.needs_summary(report.needs).endswith("1 ops issue")


# --------------------------------------------------------------------------
# Block 2: money
# --------------------------------------------------------------------------


def test_money_numbers_match_the_digest_helpers(tmp_path: Path) -> None:
    data = _digest()
    money = _report(tmp_path, data).money
    total, day, week = od.combined_returns(data.sleeves, data.sessions)
    assert (money.total, money.day, money.week) == (total, day, week)
    assert money.since == pytest.approx(total / 30000.0 - 1.0)
    assert money.spy_day == pytest.approx(od.spy_returns(data.spy_closes, data.sessions)[0])
    assert money.as_of == date(2026, 10, 2)
    assert [s.label for s in money.sleeves] == ["C2 · Month-end", "S1 · Sector rotation"]
    s1 = money.sleeves[1]
    assert s1.sessions == 7 and len(s1.spark) == 7 and s1.href == "/paper/s1"
    assert money.book == () and money.book_pending == ("quant1", "quant2")
    assert money.live == ()


def test_book_accounts_appear_once_they_have_a_daily_record(tmp_path: Path) -> None:
    data = _digest(
        book=(
            od.BookAccount(
                "quant1",
                "2026-10-07",
                "2026-10-07",
                "2026-10-07",
                1001200.0,
                1200.0,
                0.0012,
                10,
                10,
                0,
            ),
            od.BookAccount("quant2", None, None, None),
        )
    )
    money = _report(tmp_path, data).money
    assert [b.account for b in money.book] == ["quant1"] and money.book_pending == ("quant2",)


def test_sparkline_geometry() -> None:
    assert sparkline_points(()) == "0.0,10.0 72.0,10.0" or sparkline_points(()) == ""
    points = sparkline_points((0.01, -0.01), width=72, height=20)
    xs = [float(p.split(",")[0]) for p in points.split()]
    ys = [float(p.split(",")[1]) for p in points.split()]
    assert xs == [0.0, 36.0, 72.0]
    assert ys[1] < ys[0] < ys[2]  # up first, then below the start


# --------------------------------------------------------------------------
# Block 3: path to live
# --------------------------------------------------------------------------


def test_candidates_count_paper_sessions_like_the_mail(tmp_path: Path) -> None:
    data = _digest()
    report = _report(tmp_path, data)
    s1, f1 = report.candidates
    assert s1.paper_sessions == od.paper_sessions_since("2026-09-21", date(2026, 10, 2))
    assert s1.enough_sessions and s1.sessions_done == 10 and s1.href == "/paper/s1"
    assert s1.next_due == date(2026, 10, 8) and s1.proposal_due == date(2026, 10, 13)
    assert f1.paper_sessions is None and f1.paper_since is None and f1.href is None
    assert report.track_rule and report.track_updated_at == "2026-10-04T17:54Z"


def test_missing_or_bad_live_track_degrades(tmp_path: Path) -> None:
    report = _report(tmp_path, track=None)
    assert report.candidates == () and report.engines == () and report.decisions == ()
    assert any("live-track" in e for e in report.errors)
    (tmp_path / "reports/owner").mkdir(parents=True)
    (tmp_path / "reports/owner/live-track.json").write_text("[1, 2]", "utf-8")
    assert T.load_live_track(tmp_path) is None
    (tmp_path / "reports/owner/live-track.json").write_text("{not json", "utf-8")
    assert T.load_live_track(tmp_path) is None


# --------------------------------------------------------------------------
# Block 4: research
# --------------------------------------------------------------------------


def test_research_shows_engines_queue_and_the_newest_lead_round(tmp_path: Path) -> None:
    rounds = tmp_path / "reports/owner/rounds"
    rounds.mkdir(parents=True)
    (rounds / "2026-10-05T0107Z-lead.md").write_text(
        "# 主审轮 2026-10-05 01:07 UTC\n\n- 一。\n- 二。\n- 三。\n- 四。\n", "utf-8"
    )
    (rounds / "2026-10-05T0407Z-exec.md").write_text("# 执行轮\n\n- 跑了。\n", "utf-8")
    report = _report(tmp_path)
    assert [e.name for e in report.engines] == ["日频股票组合"]
    assert report.engines[0].due == date(2026, 10, 9)
    assert report.queue == {"running": 0, "review": 1, "ready": 6, "blocked": 4}
    head = report.headline
    assert head and head.source == "round" and head.label == "Lead round"
    assert (
        head.bullets == ("一。", "二。", "三。")
        and head.href == "/reports/rounds/2026-10-05T0107Z-lead"
    )


def test_research_falls_back_to_the_current_view_without_rounds(tmp_path: Path) -> None:
    sections = tuple(
        od.parse_view_sections("## 2026-10-04（主审轮 16:20）：标题\n- 第一条。\n- 第二条。\n")
    )
    sources = T.TodaySources(collected_at=NOW, digest=_digest(), error=None, view_sections=sections)
    report = _report(tmp_path, sources=sources)
    assert report.headline and report.headline.source == "view"
    assert report.headline.title == "标题" and report.headline.bullets == ("第一条。", "第二条。")
    assert report.headline.at == datetime(2026, 10, 4, 16, 20, tzinfo=UTC)
    assert _report(tmp_path).headline is None


# --------------------------------------------------------------------------
# Cache contract
# --------------------------------------------------------------------------


def test_cache_never_collects_on_get(tmp_path: Path) -> None:
    calls: list[Path] = []

    def collect(root: Path, now: datetime | None = None) -> T.TodaySources:
        calls.append(root)
        return _sources(_digest())

    cache = T.TodayCache(collect=collect)
    assert cache.get(tmp_path) is None and calls == []
    cache.refresh(tmp_path, NOW)
    assert cache.get(tmp_path) is not None and len(calls) == 1
    assert cache.age_seconds(tmp_path, now=NOW) == 0.0


def test_collect_today_sources_survives_a_digest_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    def boom(root: Path, now: datetime, kind: str) -> od.DigestData:
        raise RuntimeError("paper store gone")

    monkeypatch.setattr("open_composer.reports.owner_digest.collect_digest", boom)
    sources = T.collect_today_sources(tmp_path, NOW)
    assert sources.digest is None and "paper store gone" in (sources.error or "")
    report = _report(tmp_path, sources=sources)
    assert report.needs.word == "Attention" and report.money.total is None


# --------------------------------------------------------------------------
# Route
# --------------------------------------------------------------------------


class _Cache:
    def __init__(self, sources: T.TodaySources | None) -> None:
        self.sources = sources

    def get(self, root: Path) -> T.TodaySources | None:
        return self.sources


def _client(
    monkeypatch: pytest.MonkeyPatch, root: Path, sources: T.TodaySources | None
) -> TestClient:
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: root)
    monkeypatch.setattr("open_composer.cockpit.api.project_root", lambda: root)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: root)
    monkeypatch.setattr(
        "open_composer.cockpit.app.get_default_today_cache", lambda: _Cache(sources)
    )
    monkeypatch.setattr(
        "open_composer.cockpit.api.get_default_today_cache", lambda: _Cache(sources)
    )
    return TestClient(create_app(warm=False))


def _write_track(root: Path) -> None:
    import json

    (root / "reports/owner").mkdir(parents=True, exist_ok=True)
    (root / "reports/owner/live-track.json").write_text(json.dumps(TRACK), "utf-8")


def test_today_renders_the_four_blocks_in_order(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_track(tmp_path)
    page = _client(monkeypatch, tmp_path, _sources(_digest())).get("/")
    assert page.status_code == 200
    text = page.text
    assert "<title>Today · Quant</title>" in text
    positions = [
        text.index(label)
        for label in (
            ">Needs you<",
            'href="/paper">Money<',
            ">Path to live<",
            'href="/research">Research<',
        )
    ]
    assert positions == sorted(positions)
    assert 'verdict-word">Attention<' in text and "decision due in" in text
    assert "$30,118" in text  # C2 15058 + S1 15060: the combined sleeve value
    assert "S1 · Sector rotation" in text and 'href="/paper/s1"' in text
    assert "<polyline points=" in text
    assert "Live: <b>none</b>" in text
    assert "10/10" in text and "no paper sessions" in text
    assert "日频股票组合" in text and "No round report yet" in text
    assert "1 to review · 6 ready · 4 blocked" in text
    # retired Now instruments stay off the landing screen
    for gone in ("Fresh tokens", "Model calls", "led--fine", 'data-slot="quota-claude"'):
        assert gone not in text
    assert 'data-slot="system"' in text


def test_today_says_it_is_collecting_before_the_first_snapshot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _write_track(tmp_path)
    page = _client(monkeypatch, tmp_path, None).get("/")
    assert page.status_code == 200
    assert "Collecting the first snapshot" in page.text
    assert 'http-equiv="refresh"' in page.text
    assert (
        "Path to live" in page.text and "S1 · Sector rotation" in page.text
    )  # cheap sources still show


def test_today_renders_on_a_bare_repo(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    page = _client(monkeypatch, tmp_path, _sources(None, "OSError: no paper store")).get("/")
    assert page.status_code == 200
    assert "No live-track file" in page.text
    assert "Report data unavailable" in page.text
    assert "No paper sleeve has a close yet" in page.text


def test_today_api_mirrors_the_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _write_track(tmp_path)
    body = _client(monkeypatch, tmp_path, _sources(_digest())).get("/api/today.json").json()
    assert body["needs"]["word"] == "Attention"
    assert body["money"]["sleeves"][1]["href"] == "/paper/s1"
    assert [c["id"] for c in body["candidates"]] == ["S1", "V12F1"]
