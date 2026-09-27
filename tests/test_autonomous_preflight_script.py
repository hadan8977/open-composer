"""Autonomous round preflight: owner-quiet gate, lock, per-round usage and the round log."""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import autonomous_preflight as ap  # noqa: E402

NOW = datetime(2026, 9, 28, 1, 7, tzinfo=UTC)


def _transcript(path: Path, started: datetime, last_write: datetime, lines: list[dict]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [{"type": "user", "timestamp": started.isoformat(), "sessionId": path.stem}, *lines]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    stamp = last_write.timestamp()
    os.utime(path, (stamp, stamp))
    return path


def _assistant(msg_id: str, at: datetime, **usage: int) -> dict:
    return {
        "type": "assistant",
        "timestamp": at.isoformat(),
        "message": {"id": msg_id, "model": "claude-opus-5-5", "usage": usage},
    }


def test_owner_activity_counts_only_older_sessions_that_wrote_recently(tmp_path: Path) -> None:
    project = tmp_path / "-root-codex-test-open-composer"
    _transcript(project / "owner.jsonl", NOW - timedelta(hours=6), NOW - timedelta(minutes=3), [])
    _transcript(project / "round.jsonl", NOW - timedelta(minutes=2), NOW - timedelta(minutes=1), [])
    _transcript(project / "idle.jsonl", NOW - timedelta(days=2), NOW - timedelta(hours=2), [])

    active = ap.owner_activity(tmp_path, NOW, quiet_minutes=15, grace_minutes=10)

    assert [Path(item.path).name for item in active] == ["owner.jsonl"]


def test_decide_precedence() -> None:
    fresh_lock = {"started_at": (NOW - timedelta(hours=1)).isoformat(), "agent_id": "a"}
    stale_lock = {"started_at": (NOW - timedelta(hours=9)).isoformat(), "agent_id": "b"}
    busy = [ap.SessionActivity("x", None, NOW.isoformat())]
    limited = {"retry_after": (NOW + timedelta(hours=1)).isoformat()}

    def decision(**kw):
        base = {"now": NOW, "lock": None, "lock_max_hours": 4.0, "usage": {}, "activity": []}
        return ap.decide(**{**base, **kw})[0]

    assert decision(lock=fresh_lock, usage=limited, activity=busy) == "skip_round_running"
    assert decision(lock=stale_lock, usage=limited, activity=busy) == "skip_rate_limited"
    assert decision(usage={"unknown_throttle_reset": True}) == "skip_rate_limited"
    assert decision(activity=busy) == "wait_owner_active"
    assert decision(usage={"retry_after": "2026-09-07T11:30:00+00:00"}) == "go"
    verdict, reasons = ap.decide(
        now=NOW, lock=stale_lock, lock_max_hours=4.0, usage={}, activity=[]
    )
    assert verdict == "go" and "stale lock" in reasons[0]


def test_acquire_release_reports_round_usage_once_per_message(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    projects = tmp_path / "projects"
    monkeypatch.setattr(ap, "PROJECTS_DIR", projects)
    monkeypatch.setattr(ap, "LOCK_PATH", tmp_path / "logs" / "round.lock")
    now = datetime.now(UTC)
    start = now - timedelta(minutes=5)
    session = _transcript(
        projects / "proj" / "round-session.jsonl",
        start,
        now,
        [
            {"type": "assistant", "timestamp": start.isoformat(), "note": "run acquire agent-42"},
            # the same message logged twice must be counted once
            _assistant(
                "m1",
                start + timedelta(minutes=1),
                input_tokens=10,
                output_tokens=5,
                cache_creation_input_tokens=100,
                cache_read_input_tokens=1000,
            ),
            _assistant(
                "m1",
                start + timedelta(minutes=1),
                input_tokens=10,
                output_tokens=5,
                cache_creation_input_tokens=100,
                cache_read_input_tokens=1000,
            ),
        ],
    )
    _transcript(
        projects / "proj" / "round-session" / "subagents" / "agent-1.jsonl",
        start,
        now,
        [
            _assistant(
                "s1",
                start + timedelta(minutes=2),
                input_tokens=1,
                output_tokens=2,
                cache_creation_input_tokens=3,
                cache_read_input_tokens=4,
            )
        ],
    )
    # an older session (the owner's) that mentions the id must not be picked
    _transcript(
        projects / "proj" / "owner-session.jsonl",
        now - timedelta(hours=3),
        now,
        [{"type": "user", "timestamp": now.isoformat(), "note": "what is agent-42 doing?"}],
    )
    args = ap.build_parser().parse_args(["acquire", "--agent-id", "agent-42"])

    taken = ap.acquire(args)
    again = ap.acquire(args)
    released = ap.release(ap.build_parser().parse_args(["release"]))

    assert taken["acquired"] and taken["lock"]["session_file"] == str(session)
    assert again["acquired"] is False
    assert released["released"] and released["usage"]["fresh_tokens"] == 115 + 6
    assert released["usage"]["cache_read_tokens"] == 1004
    assert not (tmp_path / "logs" / "round.lock").exists()


def test_log_writes_header_once_and_escapes_cells(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ap, "ROOT", tmp_path)
    monkeypatch.setattr(ap, "LOG_PATH", tmp_path / "reports" / "autonomous-log.md")
    usage = json.dumps(
        {
            "started_at": "2026-09-28T01:07:00+00:00",
            "ended_at": "2026-09-28T02:10:00+00:00",
            "usage": {"fresh_tokens": 123456, "cache_read_tokens": 7},
        }
    )
    parser = ap.build_parser()
    ap.append_log(parser.parse_args(["log", "--status", "skipped", "--summary", "owner active"]))
    out = ap.append_log(
        parser.parse_args(
            [
                "log",
                "--status",
                "done",
                "--task",
                "T-1",
                "--summary",
                "a | b",
                "--usage-json",
                usage,
            ]
        )
    )

    text = (tmp_path / "reports" / "autonomous-log.md").read_text(encoding="utf-8")
    assert text.count("# 自动研究轮日志") == 1
    assert "| 2026-09-28T01:07 | 2026-09-28T02:10 | done | T-1 | a / b | 123,456 / 7 |" in text
    assert out["logged"] and len(text.strip().splitlines()) == 8
