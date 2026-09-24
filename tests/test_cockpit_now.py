"""The Now screen and the pieces the 2026-09-24 redesign added under it: the
24-hour model-call field, the account equity history, the attention rules,
the chart geometry, and the live-session card. Every test here builds its own
synthetic transcripts / paper artifacts under ``tmp_path``; the autouse
fixture in ``tests/conftest.py`` keeps the real transcript and agent trees out
of reach for the route tests."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data import activity as ACT
from open_composer.cockpit.data import paper as P
from open_composer.cockpit.data.agents import (
    AgentRecord,
    AgentsReport,
    AgentSummary,
    HeavyJobsReport,
    build_live_session,
)
from open_composer.cockpit.data.health import DiskStatus
from open_composer.cockpit.data.hypotheses import build_hypotheses_report
from open_composer.cockpit.data.now import NowReport, build_now_report, derive_attention
from open_composer.cockpit.data.quota import TopbarQuota, TopbarQuotaBar, build_usage_estimate
from open_composer.cockpit.viz import equity_columns, fresh_bars, led_columns

NOW = datetime(2026, 9, 24, 12, 5, tzinfo=UTC)


def _iso(moment: datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def _assistant(message_id: str, at: datetime, *, output: int, cache_write: int = 0) -> dict:
    return {
        "type": "assistant",
        "timestamp": _iso(at),
        "message": {
            "id": message_id,
            "role": "assistant",
            "model": "claude-test",
            "content": [{"type": "text", "text": "working"}],
            "usage": {
                "input_tokens": 1,
                "output_tokens": output,
                "cache_creation_input_tokens": cache_write,
                "cache_read_input_tokens": 999_999,
            },
        },
    }


def _user(at: datetime) -> dict:
    return {"type": "user", "timestamp": _iso(at), "message": {"role": "user", "content": "go"}}


def _write_jsonl(path: Path, lines: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# Activity field
# --------------------------------------------------------------------------


def test_activity_field_counts_distinct_calls_and_keeps_the_last_usage(tmp_path: Path) -> None:
    at = NOW - timedelta(minutes=30)
    _write_jsonl(
        tmp_path / "-repo" / "session-1.jsonl",
        [
            _user(at),
            # one call logged as two lines sharing a message id: the second
            # line's usage is the call's usage, not the sum of both
            _assistant("msg_a", at, output=10),
            _assistant("msg_a", at + timedelta(seconds=2), output=40, cache_write=100),
            _assistant("msg_b", at + timedelta(seconds=30), output=5),
        ],
    )
    field = ACT.ActivityFieldCache().get(now=NOW, root=tmp_path)

    assert field.total_calls == 2
    # fresh = input + output + cache_creation; cache reads are never folded in
    assert field.total_fresh == (1 + 40 + 100) + (1 + 5)
    assert field.peak_calls == 2
    assert len(field.calls) == ACT.BUCKETS
    assert field.calls[-1] == 0  # the in-progress bucket is 12:00-12:10, calls were 11:35
    assert field.files == 1
    assert not field.partial


def test_activity_field_reads_only_appended_lines_on_refresh(tmp_path: Path) -> None:
    path = _write_jsonl(
        tmp_path / "-repo" / "session-1.jsonl", [_assistant("msg_a", NOW, output=3)]
    )
    cache = ACT.ActivityFieldCache()
    assert cache.get(now=NOW, root=tmp_path).total_calls == 1
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(_assistant("msg_b", NOW, output=3)) + "\n")
        handle.write('{"type": "assistant", "timestamp": "2026-09')  # still being written
    second = cache.get(now=NOW + timedelta(seconds=5), root=tmp_path)
    assert second.total_calls == 2
    with path.open("a", encoding="utf-8") as handle:
        handle.write('-24T12:05:30Z", "message": {"id": "msg_c", "usage": {}}}\n')
    assert cache.get(now=NOW + timedelta(seconds=40), root=tmp_path).total_calls == 3


def test_activity_field_includes_subagent_transcripts(tmp_path: Path) -> None:
    _write_jsonl(tmp_path / "-repo" / "s1.jsonl", [_assistant("msg_main", NOW, output=1)])
    _write_jsonl(
        tmp_path / "-repo" / "s1" / "subagents" / "agent-a1.jsonl",
        [_assistant("msg_sub", NOW, output=1)],
    )
    field = ACT.ActivityFieldCache().get(now=NOW, root=tmp_path)
    assert field.total_calls == 2
    assert field.files == 2


def test_activity_field_skips_files_untouched_since_before_the_window(tmp_path: Path) -> None:
    old = _write_jsonl(
        tmp_path / "-repo" / "old.jsonl",
        [_assistant("msg_old", NOW - timedelta(days=3), output=1)],
    )
    stamp = (NOW - timedelta(days=3)).timestamp()
    os.utime(old, (stamp, stamp))
    assert ACT.ActivityFieldCache().get(now=NOW, root=tmp_path).total_calls == 0


def test_activity_field_is_empty_without_a_transcript_tree(tmp_path: Path) -> None:
    field = ACT.ActivityFieldCache().get(now=NOW, root=tmp_path / "missing")
    assert not field.available
    assert field.calls == (0,) * ACT.BUCKETS


# --------------------------------------------------------------------------
# Account equity history
# --------------------------------------------------------------------------


def _write_snapshot(root: Path, name: str, at: datetime, equity: float) -> None:
    directory = root / "reports" / "paper" / "rehearsal"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = at.strftime("%Y-%m-%d-%H%M%S")
    payload = {"generated_at": at.isoformat(), "equity": equity}
    (directory / f"{name}-{stamp}.json").write_text(json.dumps(payload), encoding="utf-8")
    (directory / f"{name}-latest.json").write_text(json.dumps(payload), encoding="utf-8")


def test_account_equity_history_keeps_gaps_and_uses_the_trading_day(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "alpha", datetime(2026, 9, 10, 23, 15, tzinfo=UTC), 100_000.0)
    _write_snapshot(tmp_path, "beta", datetime(2026, 9, 11, 20, 0, tzinfo=UTC), 100_500.0)
    # 01:21Z on the 16th is 21:21 New York time on the 15th: the 15th's session
    _write_snapshot(tmp_path, "alpha", datetime(2026, 9, 16, 1, 21, tzinfo=UTC), 99_900.0)
    _write_snapshot(tmp_path, "beta", datetime(2026, 9, 16, 23, 30, tzinfo=UTC), 101_000.0)

    history = P.build_account_equity_history(tmp_path)

    by_day = {entry.day: entry.point for entry in history.days}
    assert [entry.day for entry in history.days][0] == date(2026, 9, 10)
    assert [entry.day for entry in history.days][-1] == date(2026, 9, 16)
    assert by_day[date(2026, 9, 12)] is None  # a weekend stays a gap
    assert by_day[date(2026, 9, 15)] is not None
    assert by_day[date(2026, 9, 15)].equity == 99_900.0
    assert history.observations == 4
    assert history.has_history
    assert history.change == pytest.approx(1_000.0)
    assert history.change_pct == pytest.approx(1.0)


def test_account_equity_history_is_empty_without_snapshots(tmp_path: Path) -> None:
    history = P.build_account_equity_history(tmp_path)
    assert history.days == ()
    assert history.latest is None
    assert not history.has_history
    assert equity_columns(history) is None


# --------------------------------------------------------------------------
# Chart geometry
# --------------------------------------------------------------------------


def test_equity_columns_mark_up_down_flat_and_gap_days(tmp_path: Path) -> None:
    _write_snapshot(tmp_path, "alpha", datetime(2026, 9, 10, 20, 0, tzinfo=UTC), 100_000.0)
    _write_snapshot(tmp_path, "alpha", datetime(2026, 9, 11, 20, 0, tzinfo=UTC), 100_000.0)
    _write_snapshot(tmp_path, "alpha", datetime(2026, 9, 14, 20, 0, tzinfo=UTC), 99_000.0)
    _write_snapshot(tmp_path, "alpha", datetime(2026, 9, 15, 20, 0, tzinfo=UTC), 103_000.0)
    chart = equity_columns(P.build_account_equity_history(tmp_path))

    assert chart is not None
    kinds = [column.kind for column in chart.columns]
    assert kinds == ["flat", "flat", "gap", "gap", "down", "up"]
    assert [column.is_last for column in chart.columns] == [False] * 5 + [True]
    assert any(line.is_base and line.label == "100k" for line in chart.grid)
    up = chart.columns[-1]
    assert 0 < up.bottom < 100 and 0 < up.height <= 100 - up.bottom
    assert "no snapshot" in chart.columns[2].title


def _field(calls: list[int], fresh: list[int] | None = None) -> ACT.ActivityField:
    start = NOW - timedelta(minutes=10 * len(calls))
    fresh = fresh or [0] * len(calls)
    return ACT.ActivityField(
        window_start=start,
        window_end=NOW,
        bucket_minutes=10,
        calls=tuple(calls),
        fresh=tuple(fresh),
        total_calls=sum(calls),
        peak_calls=max(calls),
        total_fresh=sum(fresh),
        peak_fresh=max(fresh),
        files=1,
        partial=False,
        generated_at=NOW,
    )


def test_led_columns_are_linear_in_calls_and_mark_the_current_bucket() -> None:
    columns = led_columns(_field([0, 1, 50, 100]), rows=7)
    assert [column.level for column in columns] == [0, 1, 4, 7]
    assert [column.is_now for column in columns] == [False, False, False, True]
    assert columns[0].title.endswith("idle")
    grouped = led_columns(_field([1, 1, 2, 2]), rows=6, group=2)
    assert [column.value for column in grouped] == [2, 4]
    assert [column.level for column in grouped] == [3, 6]


def test_fresh_bars_light_only_the_current_window() -> None:
    bars = fresh_bars(_field([1, 1, 1, 1], [100, 0, 50, 200]), lit_last=2)
    assert [bar.lit for bar in bars] == [False, False, True, True]
    assert [round(bar.pct) for bar in bars] == [50, 0, 25, 100]
    assert bars[1].title.endswith("idle")


# --------------------------------------------------------------------------
# Attention rules
# --------------------------------------------------------------------------


def _quota(available: bool, *, status: str = "ok") -> TopbarQuota:
    if not available:
        return TopbarQuota(available=False, unavailable_reason="token expired -- re-login", bars=())
    bar = TopbarQuotaBar(
        key="five_hour",
        label="5h",
        percent_display="91%",
        width_percent=91.0,
        status=status,
        reset_label="reset 1h",
        projection_label=None,
    )
    return TopbarQuota(available=True, unavailable_reason=None, bars=(bar,))


def _account(status: str = "ok", age_hours: float = 2.0) -> P.AccountSnapshot:
    return P.AccountSnapshot(
        generated_at=NOW,
        equity=100_000.0,
        cash=None,
        buying_power=None,
        portfolio_value=None,
        age_hours=age_hours,
        status=status,
        broker_account_id_hash_prefix=None,
        warnings=(),
    )


def _kill(enabled: bool | None) -> P.KillSwitchStatus:
    return P.KillSwitchStatus(
        enabled=enabled, reason=None, updated_at=None, status="ok", warnings=()
    )


def test_attention_is_all_clear_when_nothing_needs_a_look() -> None:
    items = derive_attention(
        kill_switch=_kill(False),
        expired=0,
        soonest_expiry_days=30.0,
        agent_errors=0,
        failing_cron=0,
        stale_sources=0,
        claude=_quota(True),
        account=_account(),
        disk=None,
        memory=None,
    )
    assert [(item.level, item.text) for item in items] == [("ok", "All clear")]


def test_attention_orders_urgent_items_first() -> None:
    items = derive_attention(
        kill_switch=_kill(True),
        expired=1,
        soonest_expiry_days=2.5,
        agent_errors=2,
        failing_cron=0,
        stale_sources=3,
        claude=_quota(False),
        account=_account(),
        disk=DiskStatus(
            mount="/",
            total_bytes=100,
            used_bytes=90,
            available_bytes=10,
            used_percent=90.0,
            status="warn",
        ),
        memory=None,
    )
    texts = [item.text for item in items]
    assert texts[:3] == ["Kill switch on", "1 authorization expired", "2 agent errors"]
    assert {item.level for item in items[:3]} == {"stale"}
    assert "Claude token expired" in texts
    assert "3 sources stale" in texts
    assert "Auth ends in 2.5d" in texts
    assert "Disk 90% used" in texts


def test_attention_flags_a_hot_quota_window() -> None:
    items = derive_attention(
        kill_switch=_kill(False),
        expired=0,
        soonest_expiry_days=None,
        agent_errors=0,
        failing_cron=0,
        stale_sources=0,
        claude=_quota(True, status="stale"),
        account=_account(),
        disk=None,
        memory=None,
    )
    assert [(item.level, item.text, item.href) for item in items] == [("stale", "5h 91%", "/quota")]


# --------------------------------------------------------------------------
# Live session card
# --------------------------------------------------------------------------


def test_live_session_reads_the_last_tool_calls(tmp_path: Path) -> None:
    session_id = "00000000-0000-4000-8000-000000000009"
    at = NOW - timedelta(minutes=2)
    lines = []
    for index in range(6):
        tool_id = f"toolu_{index}"
        lines.append(
            {
                "type": "assistant",
                "timestamp": _iso(at + timedelta(seconds=index * 10)),
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": tool_id,
                            "name": "Bash",
                            "input": {"command": f"echo step {index}"},
                        }
                    ],
                },
            }
        )
        if index < 5:  # the last call has no result yet: still running
            lines.append(
                {
                    "type": "user",
                    "timestamp": _iso(at + timedelta(seconds=index * 10 + 2)),
                    "message": {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": tool_id, "content": "ok"}
                        ],
                    },
                }
            )
    _write_jsonl(tmp_path / "-repo" / f"{session_id}.jsonl", lines)
    record = AgentRecord(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        provider="claude",
        cwd="/repo",
        workspace_id="/repo",
        title="live test",
        created_at=NOW,
        updated_at=NOW,
        last_activity_at=NOW,
        last_user_message_at=NOW,
        last_status="running",
        model="claude-test",
        session_id=session_id,
    )

    session = build_live_session(record, claude_root=tmp_path)

    assert [entry.target for entry in session.recent_tools] == [
        "echo step 2",
        "echo step 3",
        "echo step 4",
        "echo step 5",
    ]
    assert session.recent_tools[-1].duration_seconds is None
    assert session.recent_tools[0].duration_seconds == pytest.approx(2.0)
    assert session.activity.current_file == "echo step 5"


def test_live_session_without_a_transcript_is_empty_not_an_error(tmp_path: Path) -> None:
    record = AgentRecord(
        id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        provider="claude",
        cwd="/nowhere",
        workspace_id=None,
        title=None,
        created_at=None,
        updated_at=None,
        last_activity_at=None,
        last_user_message_at=None,
        last_status="running",
        model=None,
        session_id="00000000-0000-4000-8000-00000000000a",
    )
    session = build_live_session(record, claude_root=tmp_path)
    assert session.recent_tools == ()
    assert session.activity.transcript_path is None


def _agent(record_id: str, status: str, at: datetime) -> AgentSummary:
    record = AgentRecord(
        id=record_id,
        provider="claude",
        cwd="/nowhere",
        workspace_id=None,
        title=f"session {record_id}",
        created_at=at,
        updated_at=at,
        last_activity_at=at,
        last_user_message_at=at,
        last_status=status,
        model=None,
        session_id=None,
    )
    return AgentSummary(record=record, activity=None)


def _agents(*agents: AgentSummary, at: datetime = NOW) -> AgentsReport:
    return AgentsReport(
        agents=agents,
        closed_collapsed_count=0,
        closed_stale_cutoff=at,
        generated_at=at,
        warnings=(),
    )


def _now_report(root: Path, *agents: AgentSummary) -> NowReport:
    return build_now_report(
        root,
        agents=_agents(*agents),
        heavy=HeavyJobsReport(jobs=(), available=False, warnings=()),
        hypotheses=build_hypotheses_report(root),
        usage=build_usage_estimate(root / "none", now=NOW, subagent_root=root / "none"),
        claude=_quota(True),
        freshness=(),
        activity=_field([0, 1]),
        now=NOW,
    )


def test_now_shows_the_last_session_only_when_nothing_is_running(tmp_path: Path) -> None:
    older = _agent("older", "closed", NOW - timedelta(hours=5))
    newer = _agent("newer", "idle", NOW - timedelta(minutes=40))
    broken = _agent("broken", "error", NOW - timedelta(minutes=1))

    resting = _now_report(tmp_path, older, newer, broken)
    assert resting.live == ()
    assert resting.last_active is not None and resting.last_active.record.id == "newer"
    assert [record.id for record in resting.errored] == ["broken"]

    busy = _agent("busy", "running", NOW - timedelta(hours=2))
    running = _now_report(tmp_path, older, newer, busy)
    assert [session.record.id for session in running.live] == ["busy"]
    assert running.last_active is None


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(warm=False))


def test_now_is_the_landing_screen(client: TestClient) -> None:
    page = client.get("/")
    assert page.status_code == 200
    text = page.text
    assert "<title>Now · Quant</title>" in text
    for label in ("Paper equity", "Agents", "Research", "Fresh tokens", "System", "Model calls"):
        assert label in text
    # the conftest fixture hides every agent and transcript: explicit empties
    assert "No live session" in text
    assert "No model calls logged in the last 24 hours" in text
    assert 'aria-current="page"' in text and 'href="/" data-screen' in text


def test_now_renders_empty_states_for_an_empty_repo(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr("open_composer.cockpit.app.project_root", lambda: tmp_path)
    monkeypatch.setattr("open_composer.cockpit.data.health.project_root", lambda: tmp_path)
    page = TestClient(create_app(warm=False)).get("/")
    assert page.status_code == 200
    assert "No account snapshot yet" in page.text


def test_every_screen_is_in_the_rail_in_order(client: TestClient) -> None:
    text = client.get("/paper").text
    order = [
        text.index(f'href="{path}" data-screen')
        for path in ("/", "/hypotheses", "/lineage", "/agents", "/paper", "/quota", "/health")
    ]
    assert order == sorted(order)
    assert "⌘7" in text


def test_now_greys_the_last_session_when_nothing_is_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    at = datetime.now(UTC) - timedelta(minutes=30)
    report = _agents(_agent("resting", "idle", at), at=at)

    class _Cache:
        def get(self, now: datetime | None = None) -> AgentsReport:
            return report

    monkeypatch.setattr("open_composer.cockpit.app.get_default_topbar_agents_cache", _Cache)
    text = TestClient(create_app(warm=False)).get("/").text
    assert "live-card well is-resting" in text
    assert "last active" in text and "session resting" in text
    assert "No live session" not in text
