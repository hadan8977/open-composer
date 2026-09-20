"""Tests for the cockpit's agent-activity screen (Step 18, screen 3, T7).

Every test builds its own synthetic `~/.paseo/agents` / `~/.claude/projects`
/ `/tmp/claude-0` / `~/.codex/sessions` trees under `tmp_path` and points
`open_composer.cockpit.data.agents`'s module-global roots at them --
`tests/conftest.py`'s autouse fixture already points the real ones at a
nonexistent path for every test in this suite, so nothing here can read this
machine's real agent history.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from open_composer.cockpit.app import create_app
from open_composer.cockpit.data.agents import (
    AGENT_ID_RE,
    AgentRecord,
    TimelineEntry,
    build_agent_detail,
    find_agent_record,
    load_agents,
    load_heavy_jobs,
    stream_agent_timeline,
    summarize_activity,
)

AGENT_RUNNING = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
AGENT_ERROR = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
AGENT_IDLE = "cccccccc-cccc-cccc-cccc-cccccccccccc"
AGENT_CLOSED_RECENT = "dddddddd-dddd-dddd-dddd-dddddddddddd"
AGENT_CLOSED_STALE = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"

NOW = datetime(2026, 9, 20, 12, 0, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _write_agent_json(
    root: Path,
    agent_id: str,
    *,
    workspace: str = "workspace",
    provider: str = "claude",
    cwd: str = "/repo",
    status: str = "idle",
    model: str = "claude-fable-5-1",
    session_id: str = "00000000-0000-4000-8000-000000000001",
    title: str = "a test agent",
    last_activity_at: datetime = NOW,
    extra_top_level: dict | None = None,
) -> Path:
    payload = {
        "id": agent_id,
        "provider": provider,
        "cwd": cwd,
        "workspaceId": cwd,
        "title": title,
        "createdAt": _iso(NOW),
        "updatedAt": _iso(last_activity_at),
        "lastActivityAt": _iso(last_activity_at),
        "lastUserMessageAt": _iso(last_activity_at),
        "lastStatus": status,
        "config": {"model": model},
        "runtimeInfo": {"provider": provider, "sessionId": session_id, "model": model},
    }
    if extra_top_level:
        payload.update(extra_top_level)
    workspace_dir = root / workspace
    workspace_dir.mkdir(parents=True, exist_ok=True)
    path = workspace_dir / f"{agent_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _write_claude_transcript(root: Path, cwd: str, session_id: str, lines: list[dict]) -> Path:
    slug = cwd.replace("/", "-")
    directory = root / slug
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{session_id}.jsonl"
    path.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
    return path


def _assistant_text_line(text: str, *, at: datetime) -> dict:
    return {
        "type": "assistant",
        "timestamp": _iso(at),
        "message": {"role": "assistant", "content": [{"type": "text", "text": text}]},
    }


def _assistant_thinking_line(*, at: datetime) -> dict:
    return {
        "type": "assistant",
        "timestamp": _iso(at),
        "message": {
            "role": "assistant",
            "content": [{"type": "thinking", "thinking": "", "signature": "sig-not-reasoning-abc"}],
        },
    }


def _tool_use_line(name: str, input_obj: dict, *, tool_use_id: str, at: datetime) -> dict:
    return {
        "type": "assistant",
        "timestamp": _iso(at),
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tool_use_id, "name": name, "input": input_obj}],
        },
    }


def _tool_result_line(
    content: str, *, tool_use_id: str, at: datetime, is_error: bool = False
) -> dict:
    return {
        "type": "user",
        "timestamp": _iso(at),
        "message": {
            "role": "user",
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        },
    }


# --------------------------------------------------------------------------
# Allowlisted parse drops the bearer token
# --------------------------------------------------------------------------


def test_allowlisted_parse_never_carries_the_bearer_token(tmp_path: Path) -> None:
    bearer = "Bearer sk-live-agent-secret-0123456789"
    extra = {
        "persistence": {
            "metadata": {
                "mcpServers": {
                    "paseo": {
                        "type": "http",
                        "url": "https://relay.example/mcp",
                        "headers": {"Authorization": bearer},
                    }
                }
            }
        }
    }
    _write_agent_json(tmp_path, AGENT_IDLE, status="idle", extra_top_level=extra)

    record = find_agent_record(AGENT_IDLE, root=tmp_path)
    assert record is not None
    # The allowlist means the raw dict (and therefore the token) is never
    # read into any field on the dataclass in the first place.
    for value in vars(record).values():
        assert "Bearer" not in str(value)
        assert "sk-live-agent-secret" not in str(value)


def test_bearer_token_never_reaches_rendered_html_or_the_sse_stream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    bearer_secret = "sk-ant-oat-liveagentsecret0123456789"  # noqa: S105 - test fixture, not a real key

    extra = {
        "persistence": {
            "metadata": {
                "mcpServers": {"paseo": {"headers": {"Authorization": f"Bearer {bearer_secret}"}}}
            }
        }
    }
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000002",
        extra_top_level=extra,
    )
    # A tool result is the other realistic place a live token leaks (e.g. a
    # `cat ~/.credentials.json`), so plant one there too.
    transcript_path = _write_claude_transcript(
        claude_root,
        "/repo",
        "00000000-0000-4000-8000-000000000002",
        [
            _tool_use_line("Bash", {"command": "cat ~/.paseo-secret"}, tool_use_id="t1", at=NOW),
            _tool_result_line(f"Authorization: Bearer {bearer_secret}", tool_use_id="t1", at=NOW),
        ],
    )
    monkeypatch.setattr("open_composer.cockpit.data.agents.PASEO_AGENTS_DIR", agents_root)
    monkeypatch.setattr("open_composer.cockpit.data.agents.CLAUDE_PROJECTS_DIR", claude_root)

    client = TestClient(create_app())

    board = client.get("/agents")
    assert bearer_secret not in board.text

    detail = client.get(f"/agents/{AGENT_RUNNING}")
    assert detail.status_code == 200
    assert bearer_secret not in detail.text
    # secret_scrub keeps the surrounding "Bearer " label (see
    # `security.secret_scrub`'s docstring) but must redact the token itself.
    assert "REDACTED" in detail.text

    # Exercise the SSE path directly (fake clock/sleep, no real threads or
    # sleeping -- see the dedicated `test_stream_*` tests below for why): a
    # tool result carrying the live token arrives *after* the stream
    # connects, exactly the "cat a credentials file mid-session" scenario.
    generator = stream_agent_timeline(
        AGENT_RUNNING,
        root=agents_root,
        claude_root=claude_root,
        poll_interval=0.0,
        keepalive_interval=1000.0,
        max_duration=1000.0,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    try:
        assert next(generator) == ": stream-open\n\n"
        with transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(
                    _tool_result_line(
                        f"Authorization: Bearer {bearer_secret}", tool_use_id="t2", at=NOW
                    )
                )
                + "\n"
            )
        sse_line = next(generator)
    finally:
        generator.close()
    assert bearer_secret not in sse_line
    assert "REDACTED" in sse_line


# --------------------------------------------------------------------------
# State ordering
# --------------------------------------------------------------------------


def test_load_agents_orders_running_error_idle_then_closed(tmp_path: Path) -> None:
    _write_agent_json(tmp_path, AGENT_IDLE, status="idle", last_activity_at=NOW)
    _write_agent_json(tmp_path, AGENT_CLOSED_RECENT, status="closed", last_activity_at=NOW)
    _write_agent_json(tmp_path, AGENT_ERROR, status="error", last_activity_at=NOW)
    _write_agent_json(tmp_path, AGENT_RUNNING, status="running", last_activity_at=NOW)

    report = load_agents(root=tmp_path, now=NOW, enrich=False)

    assert [a.record.id for a in report.agents] == [
        AGENT_RUNNING,
        AGENT_ERROR,
        AGENT_IDLE,
        AGENT_CLOSED_RECENT,
    ]


def test_load_agents_orders_by_recency_within_a_state(tmp_path: Path) -> None:
    older = "11111111-1111-1111-1111-111111111111"
    newer = "22222222-2222-2222-2222-222222222222"
    _write_agent_json(tmp_path, older, status="idle", last_activity_at=NOW)
    _write_agent_json(tmp_path, newer, status="idle", last_activity_at=NOW.replace(hour=13))

    report = load_agents(root=tmp_path, now=NOW, enrich=False)

    assert [a.record.id for a in report.agents] == [newer, older]


# --------------------------------------------------------------------------
# Closed agents older than 48h are collapsed, not listed
# --------------------------------------------------------------------------


def test_closed_agents_older_than_48h_are_collapsed_into_a_count(tmp_path: Path) -> None:
    _write_agent_json(
        tmp_path, AGENT_CLOSED_RECENT, status="closed", last_activity_at=NOW.replace(hour=11)
    )
    stale_time = NOW.replace(day=17)  # far more than 48h before NOW
    _write_agent_json(tmp_path, AGENT_CLOSED_STALE, status="closed", last_activity_at=stale_time)

    report = load_agents(root=tmp_path, now=NOW, enrich=False)

    ids = [a.record.id for a in report.agents]
    assert AGENT_CLOSED_RECENT in ids
    assert AGENT_CLOSED_STALE not in ids
    assert report.closed_collapsed_count == 1


def test_agent_with_no_timestamps_never_crashes_sorting_or_collapsing(tmp_path: Path) -> None:
    payload_path = _write_agent_json(tmp_path, AGENT_CLOSED_RECENT, status="closed")
    raw = json.loads(payload_path.read_text())
    for key in ("createdAt", "updatedAt", "lastActivityAt", "lastUserMessageAt"):
        raw.pop(key, None)
    payload_path.write_text(json.dumps(raw), encoding="utf-8")

    report = load_agents(root=tmp_path, now=NOW, enrich=False)

    # No reference timestamp at all -> treated as (collapsible) stale, never raises.
    assert report.closed_collapsed_count == 1
    assert report.agents == ()


# --------------------------------------------------------------------------
# Current-file extraction from Read/Bash
# --------------------------------------------------------------------------


def test_summarize_activity_prefers_file_tool_over_bash() -> None:
    entries = [
        TimelineEntry(
            at=NOW,
            kind="tool",
            tool_name="Bash",
            target="ls -la",
            detail=None,
            is_error=False,
            duration_seconds=None,
            tool_use_id="a",
        ),
        TimelineEntry(
            at=NOW,
            kind="tool",
            tool_name="Read",
            target="/repo/foo.py",
            detail=None,
            is_error=False,
            duration_seconds=None,
            tool_use_id="b",
        ),
    ]
    current_file, _last_text, _last_at = summarize_activity(entries)
    assert current_file == "/repo/foo.py"


def test_summarize_activity_falls_back_to_bash_command() -> None:
    entries = [
        TimelineEntry(
            at=NOW,
            kind="tool",
            tool_name="Bash",
            target="git status --short",
            detail=None,
            is_error=False,
            duration_seconds=None,
            tool_use_id="a",
        ),
    ]
    current_file, _last_text, _last_at = summarize_activity(entries)
    assert current_file == "git status --short"


def test_summarize_activity_last_text_is_the_latest_assistant_text_first_160_chars() -> None:
    entries = [
        TimelineEntry(
            at=NOW,
            kind="text",
            tool_name=None,
            target=None,
            detail="first message",
            is_error=False,
            duration_seconds=None,
            tool_use_id=None,
        ),
        TimelineEntry(
            at=NOW,
            kind="text",
            tool_name=None,
            target=None,
            detail="x" * 500,
            is_error=False,
            duration_seconds=None,
            tool_use_id=None,
        ),
    ]
    _current_file, last_text, _last_at = summarize_activity(entries)
    assert last_text == "x" * 160


# --------------------------------------------------------------------------
# Thinking blocks ignored; "reasoning" never appears in rendered HTML
# --------------------------------------------------------------------------


def test_thinking_blocks_are_ignored_and_reasoning_never_rendered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000010",
    )
    _write_claude_transcript(
        claude_root,
        "/repo",
        "00000000-0000-4000-8000-000000000010",
        [
            _assistant_thinking_line(at=NOW),
            _assistant_text_line("here is what I actually said out loud", at=NOW),
        ],
    )
    monkeypatch.setattr("open_composer.cockpit.data.agents.PASEO_AGENTS_DIR", agents_root)
    monkeypatch.setattr("open_composer.cockpit.data.agents.CLAUDE_PROJECTS_DIR", claude_root)

    detail = build_agent_detail(AGENT_RUNNING, root=agents_root, claude_root=claude_root)
    assert len(detail.entries) == 1  # the thinking block produced no entry at all
    assert detail.entries[0].kind == "text"
    assert "sig-not-reasoning-abc" not in (detail.entries[0].detail or "")

    client = TestClient(create_app())
    response = client.get(f"/agents/{AGENT_RUNNING}")
    assert response.status_code == 200
    assert "reasoning" not in response.text.lower()
    assert "sig-not-reasoning-abc" not in response.text


# --------------------------------------------------------------------------
# tool_use / tool_result pairing gives a duration
# --------------------------------------------------------------------------


def test_tool_use_and_tool_result_pairing_gives_a_duration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000003",
    )
    called_at = NOW
    returned_at = NOW.replace(second=3)  # 3 seconds later
    _write_claude_transcript(
        claude_root,
        "/repo",
        "00000000-0000-4000-8000-000000000003",
        [
            _tool_use_line("Bash", {"command": "sleep 3"}, tool_use_id="tool-1", at=called_at),
            _tool_result_line("done", tool_use_id="tool-1", at=returned_at),
        ],
    )

    detail = build_agent_detail(AGENT_RUNNING, root=agents_root, claude_root=claude_root)
    tool_entries = [e for e in detail.entries if e.kind == "tool"]
    assert len(tool_entries) == 1
    assert tool_entries[0].duration_seconds == pytest.approx(3.0)

    result_entries = [e for e in detail.entries if e.kind == "result"]
    assert len(result_entries) == 1
    assert result_entries[0].is_error is False


def test_tool_result_is_error_flag_is_preserved(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000004",
    )
    _write_claude_transcript(
        claude_root,
        "/repo",
        "00000000-0000-4000-8000-000000000004",
        [
            _tool_use_line("Bash", {"command": "false"}, tool_use_id="tool-2", at=NOW),
            _tool_result_line("Exit code 1", tool_use_id="tool-2", at=NOW, is_error=True),
        ],
    )

    detail = build_agent_detail(AGENT_RUNNING, root=agents_root, claude_root=claude_root)
    result_entries = [e for e in detail.entries if e.kind == "result"]
    assert result_entries[0].is_error is True


# --------------------------------------------------------------------------
# SSE generator: new entries after the initial offset, and keep-alives --
# driven directly, no real sleeping.
# --------------------------------------------------------------------------


def test_stream_yields_only_entries_appended_after_connect_time(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000006",
    )
    transcript_path = _write_claude_transcript(
        claude_root,
        "/repo",
        "00000000-0000-4000-8000-000000000006",
        [_assistant_text_line("already here before connect", at=NOW)],
    )

    generator = stream_agent_timeline(
        AGENT_RUNNING,
        root=agents_root,
        claude_root=claude_root,
        poll_interval=0.0,
        keepalive_interval=1000.0,
        max_duration=1000.0,
        clock=lambda: 0.0,
        sleep=lambda _seconds: None,
    )
    try:
        first = next(generator)
        assert first == ": stream-open\n\n"

        # Append a new line *after* the stream connected -- this is the only
        # thing the stream should ever emit as data.
        with transcript_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_assistant_text_line("appended after connect", at=NOW)) + "\n")

        second = next(generator)
        assert second.startswith("data: ")
        payload = json.loads(second[len("data: ") :].strip())
        assert payload["kind"] == "text"
        assert payload["content"] == "appended after connect"
        assert "already here before connect" not in second
    finally:
        generator.close()


def test_stream_emits_keep_alive_once_the_interval_elapses(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000005",
    )
    _write_claude_transcript(claude_root, "/repo", "00000000-0000-4000-8000-000000000005", [])

    class _FakeClock:
        def __init__(self) -> None:
            self.value = 0.0

        def __call__(self) -> float:
            self.value += 10.0
            return self.value

    generator = stream_agent_timeline(
        AGENT_RUNNING,
        root=agents_root,
        claude_root=claude_root,
        poll_interval=0.0,
        keepalive_interval=5.0,
        max_duration=10_000.0,
        clock=_FakeClock(),
        sleep=lambda _seconds: None,
    )
    try:
        assert next(generator) == ": stream-open\n\n"
        assert next(generator) == ": keep-alive\n\n"
    finally:
        generator.close()


def test_stream_closes_itself_after_max_duration(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "claude-projects"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000009",
    )
    _write_claude_transcript(claude_root, "/repo", "00000000-0000-4000-8000-000000000009", [])

    class _FakeClock:
        """First call (the connect-time `start`) returns 0; every call after
        that reports an instant far past `max_duration`."""

        def __init__(self) -> None:
            self.calls = 0

        def __call__(self) -> float:
            self.calls += 1
            return 0.0 if self.calls == 1 else 1_000.0

    generator = stream_agent_timeline(
        AGENT_RUNNING,
        root=agents_root,
        claude_root=claude_root,
        poll_interval=0.0,
        keepalive_interval=1_000_000.0,
        max_duration=5.0,
        clock=_FakeClock(),
        sleep=lambda _seconds: None,
    )
    assert next(generator) == ": stream-open\n\n"
    closing = next(generator)
    assert "stream-closed" in closing
    with pytest.raises(StopIteration):
        next(generator)


def test_stream_of_unknown_agent_id_reports_not_found_without_touching_disk(tmp_path: Path) -> None:
    generator = stream_agent_timeline(
        AGENT_RUNNING, root=tmp_path / "does-not-exist", claude_root=tmp_path / "also-missing"
    )
    assert next(generator) == ": agent not found\n\n"
    with pytest.raises(StopIteration):
        next(generator)


# --------------------------------------------------------------------------
# Id validation rejects traversal
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "candidate",
    [
        "../../etc/passwd",
        "..%2f..%2fetc%2fpasswd",
        "not-a-uuid",
        "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa/../secret",
        "",
        "AAAAAAAA-AAAA-AAAA-AAAA-AAAAAAAAAAAA",  # uppercase: real ids are lowercase
    ],
)
def test_agent_id_regex_rejects_non_conforming_and_traversal_ids(candidate: str) -> None:
    assert AGENT_ID_RE.match(candidate) is None


def test_find_agent_record_refuses_a_traversal_shaped_id_without_touching_disk(
    tmp_path: Path,
) -> None:
    _write_agent_json(tmp_path, AGENT_RUNNING, status="running")
    assert find_agent_record("../../etc/passwd", root=tmp_path) is None


def test_agent_detail_route_404s_for_malformed_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("open_composer.cockpit.data.agents.PASEO_AGENTS_DIR", tmp_path)
    client = TestClient(create_app())
    response = client.get("/agents/not-a-valid-id")
    assert response.status_code == 404


def test_agent_detail_route_404s_for_unknown_but_well_formed_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("open_composer.cockpit.data.agents.PASEO_AGENTS_DIR", tmp_path)
    client = TestClient(create_app())
    response = client.get(f"/agents/{AGENT_RUNNING}")
    assert response.status_code == 404


# --------------------------------------------------------------------------
# Heavy-jobs discovery degrades when systemctl is unavailable
# --------------------------------------------------------------------------


def test_heavy_jobs_degrades_when_systemctl_is_unavailable() -> None:
    report = load_heavy_jobs(run=lambda _args: None)
    assert report.available is False
    assert report.jobs == ()
    assert report.warnings


def test_heavy_jobs_reports_none_when_no_scopes_are_running() -> None:
    def _fake_run(args: list[str]) -> str | None:
        if args[0] == "list-units":
            return ""  # no legend lines at all
        return None

    report = load_heavy_jobs(run=_fake_run)
    assert report.available is True
    assert report.jobs == ()


def test_heavy_jobs_filters_to_the_research_capped_slice(tmp_path: Path) -> None:
    def _fake_run(args: list[str]) -> str | None:
        if args[0] == "list-units":
            return (
                "  run-r911bc0ee.scope loaded active running /usr/bin/sleep 6\n"
                "  run-rOTHERSLICE.scope loaded active running /usr/bin/sleep 6\n"
            )
        if args[0] == "show" and args[1] == "-p" and args[2] == "Slice":
            unit = args[-1]
            if unit == "run-r911bc0ee.scope":
                return "research-capped.slice"
            return "other.slice"
        if args[0] == "show":
            return (
                "ActiveEnterTimestamp=Sun 2026-09-20 06:35:55 UTC\n"
                "MemoryCurrent=188416\nMemoryMax=104857600\n"
            )
        return None

    report = load_heavy_jobs(run=_fake_run, now=NOW)
    assert report.available is True
    assert [job.unit for job in report.jobs] == ["run-r911bc0ee.scope"]
    job = report.jobs[0]
    assert job.memory_current_bytes == 188416
    assert job.memory_max_bytes == 104857600
    assert job.memory_max_unlimited is False
    assert job.elapsed_seconds is not None and job.elapsed_seconds > 0


# --------------------------------------------------------------------------
# GET-only invariant and no-CJK-chrome, specifically for the new agents
# routes (the parametrized versions of these live in test_cockpit_app.py;
# these two are a belt-and-suspenders check scoped to this screen).
# --------------------------------------------------------------------------


def test_agents_routes_are_get_only() -> None:
    app = create_app()
    agent_routes = [r for r in app.routes if getattr(r, "path", "").startswith("/agents")]
    assert agent_routes
    for route in agent_routes:
        methods = getattr(route, "methods", None)
        if methods:
            assert methods <= {"GET", "HEAD"}


def test_agents_board_has_no_cjk_chrome_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("open_composer.cockpit.data.agents.PASEO_AGENTS_DIR", tmp_path)
    client = TestClient(create_app())
    response = client.get("/agents")
    assert response.status_code == 200
    cjk = [ch for ch in response.text if "一" <= ch <= "鿿"]
    assert not cjk


# --------------------------------------------------------------------------
# Subagent transcripts: nested under the parent, degrade to none.
# --------------------------------------------------------------------------


def test_subagents_degrade_to_none_when_tree_absent(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000007",
    )
    detail = build_agent_detail(
        AGENT_RUNNING,
        root=agents_root,
        claude_root=tmp_path / "no-claude-projects",
        subagent_root=tmp_path / "no-subagent-tree",
    )
    assert detail.subagents == ()


def test_subagents_are_discovered_and_nested_under_the_parent_session(tmp_path: Path) -> None:
    agents_root = tmp_path / "agents"
    subagent_root = tmp_path / "claude-0"
    _write_agent_json(
        agents_root,
        AGENT_RUNNING,
        status="running",
        cwd="/repo",
        session_id="00000000-0000-4000-8000-000000000008",
    )
    tasks_dir = subagent_root / "-repo" / "00000000-0000-4000-8000-000000000008" / "tasks"
    tasks_dir.mkdir(parents=True)
    (tasks_dir / "a1b2c3d4e5f6a7b8c.output").write_text(
        json.dumps(_assistant_text_line("subagent report", at=NOW)) + "\n", encoding="utf-8"
    )

    detail = build_agent_detail(
        AGENT_RUNNING,
        root=agents_root,
        claude_root=tmp_path / "no-claude-projects",
        subagent_root=subagent_root,
    )
    assert len(detail.subagents) == 1
    assert detail.subagents[0].id == "a1b2c3d4e5f6a7b8c"
    assert detail.subagents[0].entries[0].detail == "subagent report"


# --------------------------------------------------------------------------
# AgentRecord fields: sanity check on the allowlist itself.
# --------------------------------------------------------------------------


def test_agent_record_has_no_persistence_or_mcp_field() -> None:
    field_names = {f for f in AgentRecord.__dataclass_fields__}
    assert "persistence" not in field_names
    assert "mcpServers" not in field_names
    assert "config" not in field_names  # only its allowlisted .model survives, as `model`
    assert "runtimeInfo" not in field_names  # only its allowlisted .sessionId survives


# --------------------------------------------------------------------------
# Session id / cwd shape checks (they become path components)
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "session_id,cwd",
    [
        ("../../etc/passwd", "/repo"),
        ("00000000-0000-4000-8000-000000000001", "/repo"),
        ("*", "/repo"),
        (AGENT_RUNNING, ".."),
        (AGENT_RUNNING, "relative/dir"),
    ],
    ids=["traversal-session", "non-uuid-session", "glob-session", "dotdot-cwd", "relative-cwd"],
)
def test_agent_json_with_unsafe_session_id_or_cwd_resolves_no_transcript(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_id: str, cwd: str
) -> None:
    agents_root = tmp_path / "agents"
    claude_root = tmp_path / "projects"
    _write_agent_json(agents_root, AGENT_RUNNING, cwd=cwd, session_id=session_id, status="running")
    # A transcript planted where a naive join would land must never be picked up.
    (claude_root / "-repo").mkdir(parents=True)
    (claude_root / "-repo" / f"{AGENT_RUNNING}.jsonl").write_text("", encoding="utf-8")
    monkeypatch.setattr("open_composer.cockpit.data.agents.PASEO_AGENTS_DIR", agents_root)
    monkeypatch.setattr("open_composer.cockpit.data.agents.CLAUDE_PROJECTS_DIR", claude_root)

    record = find_agent_record(AGENT_RUNNING)
    assert record is not None
    assert record.session_id is None or AGENT_ID_RE.match(record.session_id)
    assert record.cwd is None or record.cwd.startswith("/")
    detail = build_agent_detail(AGENT_RUNNING)
    assert detail.transcript_available is False
