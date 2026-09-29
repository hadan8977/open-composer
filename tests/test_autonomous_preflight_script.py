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


@pytest.fixture(autouse=True)
def _quota_api_enabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """This file exercises the pre-2026-09-29 quota-gated `decide()`/`quota_state()`
    paths (T-20260927-04 budget plan A). The owner's 2026-09-29 decision
    ("额度查询先不做了，你自己有数了就行") turned `QUOTA_API_ENABLED` off by
    default (see its docstring in `scripts/autonomous_preflight.py`); tests
    for that disabled path opt out explicitly with their own
    `monkeypatch.setattr(ap, "QUOTA_API_ENABLED", False)`.
    """
    monkeypatch.setattr(ap, "QUOTA_API_ENABLED", True)


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


# --------------------------------------------------------------------------
# Budget plan A (T-20260927-04): quota-based gating in `decide()`
# --------------------------------------------------------------------------


def test_decide_quota_lock_and_rate_limit_still_outrank_quota() -> None:
    fresh_lock = {"started_at": (NOW - timedelta(hours=1)).isoformat(), "agent_id": "a"}
    limited = {"retry_after": (NOW + timedelta(hours=1)).isoformat()}
    good_quota = {"five_hour_percent": 1.0, "seven_day_percent": 1.0}

    verdict, _ = ap.decide(
        now=NOW, lock=fresh_lock, lock_max_hours=4.0, usage={}, activity=[], quota=good_quota
    )
    assert verdict == "skip_round_running"

    verdict, _ = ap.decide(
        now=NOW, lock=None, lock_max_hours=4.0, usage=limited, activity=[], quota=good_quota
    )
    assert verdict == "skip_rate_limited"


def test_decide_quota_five_hour_at_or_over_50_skips_regardless_of_owner() -> None:
    verdict, reasons = ap.decide(
        now=NOW,
        lock=None,
        lock_max_hours=4.0,
        usage={},
        activity=[],
        quota={"five_hour_percent": 50.0, "seven_day_percent": 1.0},
        background_week_percent_est=0.0,
    )
    assert verdict == "skip_quota"
    assert "5h window >= 50%" in reasons[0]


def test_decide_quota_owner_active_and_five_hour_at_or_over_30_skips() -> None:
    busy = [ap.SessionActivity("x", None, NOW.isoformat())]
    verdict, reasons = ap.decide(
        now=NOW,
        lock=None,
        lock_max_hours=4.0,
        usage={},
        activity=busy,
        quota={"five_hour_percent": 30.0, "seven_day_percent": 1.0},
        background_week_percent_est=0.0,
    )
    assert verdict == "skip_quota"
    assert "owner active and 5h >= 30%" in reasons[0]

    # same 5h reading, but owner quiet -> this branch does not fire
    quiet_verdict, _ = ap.decide(
        now=NOW,
        lock=None,
        lock_max_hours=4.0,
        usage={},
        activity=[],
        quota={"five_hour_percent": 30.0, "seven_day_percent": 1.0},
        background_week_percent_est=0.0,
    )
    assert quiet_verdict == "go"


def test_decide_quota_background_week_share_at_or_over_40_skips() -> None:
    verdict, reasons = ap.decide(
        now=NOW,
        lock=None,
        lock_max_hours=4.0,
        usage={},
        activity=[],
        quota={"five_hour_percent": 1.0, "seven_day_percent": 1.0},
        background_week_percent_est=40.0,
    )
    assert verdict == "skip_quota"
    assert "background weekly share >= 40%" in reasons[0]


def test_decide_quota_available_goes_even_when_owner_active_below_thresholds() -> None:
    busy = [ap.SessionActivity("x", None, NOW.isoformat())]
    verdict, reasons = ap.decide(
        now=NOW,
        lock=None,
        lock_max_hours=4.0,
        usage={},
        activity=busy,
        quota={"five_hour_percent": 5.0, "seven_day_percent": 1.0},
        background_week_percent_est=5.0,
    )
    assert verdict == "go"
    assert reasons == []


def test_decide_quota_unavailable_falls_back_to_owner_quiet_gate() -> None:
    busy = [ap.SessionActivity("x", None, NOW.isoformat())]

    verdict_busy, _ = ap.decide(now=NOW, lock=None, lock_max_hours=4.0, usage={}, activity=busy)
    assert verdict_busy == "wait_owner_active"

    verdict_quiet, _ = ap.decide(now=NOW, lock=None, lock_max_hours=4.0, usage={}, activity=[])
    assert verdict_quiet == "go"

    # one percent missing counts as "quota unavailable" too, not partial gating
    partial_quota = {"five_hour_percent": 90.0, "seven_day_percent": None}
    verdict_partial, _ = ap.decide(
        now=NOW, lock=None, lock_max_hours=4.0, usage={}, activity=busy, quota=partial_quota
    )
    assert verdict_partial == "wait_owner_active"


def test_estimate_background_week_percent_from_synthetic_log_and_transcripts(
    tmp_path: Path,
) -> None:
    resets_at = datetime(2026, 9, 28, 6, 0, tzinfo=UTC)
    week_start = resets_at - timedelta(days=7)
    quota = {"seven_day_percent": 20.0, "seven_day_resets_at": resets_at.isoformat()}

    log_path = tmp_path / "autonomous-log.md"
    in_window_start = (week_start + timedelta(days=1)).isoformat()[:16]
    before_window_start = (week_start - timedelta(days=1)).isoformat()[:16]
    log_path.write_text(
        "# header\n\n"
        "| 开始 (UTC) | 结束 (UTC) | 状态 | 任务 | 摘要 | fresh / cache-read tokens |\n"
        "|---|---|---|---|---|---|\n"
        f"| {in_window_start} | x | done | T-1 | a round | 1,000 / 5 |\n"
        f"| {before_window_start} | x | done | T-0 | old round | 9,000 / 5 |\n",
        encoding="utf-8",
    )

    projects = tmp_path / "projects"
    project_dir = projects / "proj"
    _transcript(
        project_dir / "round.jsonl",
        week_start + timedelta(days=1),
        week_start + timedelta(days=1, minutes=5),
        [
            _assistant(
                "m1",
                week_start + timedelta(days=1),
                input_tokens=600,
                output_tokens=400,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            )
        ],
    )
    _transcript(
        project_dir / "other.jsonl",
        week_start + timedelta(days=2),
        week_start + timedelta(days=2, minutes=5),
        [
            _assistant(
                "m2",
                week_start + timedelta(days=2),
                input_tokens=3000,
                output_tokens=1000,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            )
        ],
    )
    # before the week window: must not be counted in either numerator or denominator
    _transcript(
        project_dir / "stale.jsonl",
        week_start - timedelta(days=2),
        week_start - timedelta(days=2) + timedelta(minutes=5),
        [
            _assistant(
                "m0",
                week_start - timedelta(days=2),
                input_tokens=50_000,
                output_tokens=50_000,
                cache_creation_input_tokens=0,
                cache_read_input_tokens=0,
            )
        ],
    )

    est = ap.estimate_background_week_percent(
        quota, now=resets_at, log_path=log_path, projects_dir=projects
    )

    # round_tokens = 1,000 (only the in-window log row); all_tokens = 1,000 + 4,000 = 5,000
    # estimate = round_tokens / (all_tokens / seven_day_percent) = 1000 / (5000 / 20.0) = 4.0
    assert est == pytest.approx(4.0)


def test_estimate_background_week_percent_degrades_to_zero_without_inputs(
    tmp_path: Path,
) -> None:
    assert ap.estimate_background_week_percent({}, now=NOW) == 0.0
    assert (
        ap.estimate_background_week_percent(
            {"seven_day_percent": 0.5, "seven_day_resets_at": NOW.isoformat()}, now=NOW
        )
        == 0.0
    )
    # no local usage at all in the window -> 0.0, not a divide-by-zero error
    empty_projects = tmp_path / "empty"
    empty_projects.mkdir()
    quota = {"seven_day_percent": 20.0, "seven_day_resets_at": NOW.isoformat()}
    assert (
        ap.estimate_background_week_percent(
            quota, now=NOW, log_path=tmp_path / "missing-log.md", projects_dir=empty_projects
        )
        == 0.0
    )


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


def test_quota_state_reports_percents_and_resets_from_the_cockpit_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeWindow:
        def __init__(self, key: str, percent_used: float, resets_at: datetime | None) -> None:
            self.key = key
            self.percent_used = percent_used
            self.resets_at = resets_at

    class _FakeSnapshot:
        available = True
        windows = (
            _FakeWindow("five_hour", 14.0, datetime(2026, 9, 28, 6, 0, tzinfo=UTC)),
            _FakeWindow("seven_day", 3.0, datetime(2026, 10, 4, 0, 0, tzinfo=UTC)),
        )

    class _FakeReport:
        snapshot = _FakeSnapshot()

    class _FakeCache:
        def get(self, *, now):
            return _FakeReport()

    monkeypatch.setattr(ap, "get_default_claude_cache", lambda: _FakeCache())

    quota = ap.quota_state(cache_path=tmp_path / "quota-cache.json")

    assert quota == {
        "five_hour_percent": 14.0,
        "seven_day_percent": 3.0,
        "five_hour_resets_at": "2026-09-28T06:00:00+00:00",
        "seven_day_resets_at": "2026-10-04T00:00:00+00:00",
    }


def test_quota_state_degrades_to_nulls_when_the_reader_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class _FakeCache:
        def get(self, *, now):
            raise RuntimeError("boom")

    monkeypatch.setattr(ap, "get_default_claude_cache", lambda: _FakeCache())

    quota = ap.quota_state(cache_path=tmp_path / "quota-cache.json")

    assert quota == {
        "five_hour_percent": None,
        "seven_day_percent": None,
        "five_hour_resets_at": None,
        "seven_day_resets_at": None,
        "quota_error": "RuntimeError",
    }


# --------------------------------------------------------------------------
# Shared on-disk quota cache (T-20260927-04 follow-up: the endpoint 429s
# when every preflight process calls it fresh)
# --------------------------------------------------------------------------

_CACHED_QUOTA_FIELDS = {
    "five_hour_percent": 27.0,
    "seven_day_percent": 4.0,
    "five_hour_resets_at": "2026-09-28T18:00:00+00:00",
    "seven_day_resets_at": "2026-10-05T00:00:00+00:00",
}


def _write_cache_file(cache_path: Path, fetched_at: datetime) -> None:
    payload = {**_CACHED_QUOTA_FIELDS, "fetched_at": fetched_at.isoformat(), "source": "live"}
    cache_path.write_text(json.dumps(payload), encoding="utf-8")


def test_quota_state_fresh_cache_hit_skips_the_endpoint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    cache_path = tmp_path / "quota-cache.json"
    _write_cache_file(cache_path, now - timedelta(minutes=5))

    def _must_not_be_called() -> dict:
        raise AssertionError("the endpoint must not be called on a fresh cache hit")

    monkeypatch.setattr(ap, "_read_quota_live", _must_not_be_called)

    quota = ap.quota_state(now=now, cache_path=cache_path)

    assert quota == _CACHED_QUOTA_FIELDS


def test_quota_state_stale_cache_used_within_60_minutes_on_429(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    cache_path = tmp_path / "quota-cache.json"
    _write_cache_file(cache_path, now - timedelta(minutes=45))

    def _raise_429() -> dict:
        raise ap._QuotaUnavailable("http 4xx/5xx")

    monkeypatch.setattr(ap, "_read_quota_live", _raise_429)

    quota = ap.quota_state(now=now, cache_path=cache_path)

    assert quota["five_hour_percent"] == 27.0
    assert quota["seven_day_percent"] == 4.0
    assert quota["stale"] is True
    assert quota["age_minutes"] == pytest.approx(45.0, abs=0.1)


def test_quota_state_cache_older_than_60_minutes_degrades_to_nulls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    cache_path = tmp_path / "quota-cache.json"
    _write_cache_file(cache_path, now - timedelta(minutes=90))

    def _raise_429() -> dict:
        raise ap._QuotaUnavailable("http 4xx/5xx")

    monkeypatch.setattr(ap, "_read_quota_live", _raise_429)

    quota = ap.quota_state(now=now, cache_path=cache_path)

    assert quota == {
        "five_hour_percent": None,
        "seven_day_percent": None,
        "five_hour_resets_at": None,
        "seven_day_resets_at": None,
        "quota_error": "http 4xx/5xx",
    }


def test_quota_state_success_refreshes_the_cache_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    now = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    cache_path = tmp_path / "quota-cache.json"
    monkeypatch.setattr(ap, "_read_quota_live", lambda: dict(_CACHED_QUOTA_FIELDS))

    quota = ap.quota_state(now=now, cache_path=cache_path)

    assert quota == _CACHED_QUOTA_FIELDS
    on_disk = json.loads(cache_path.read_text(encoding="utf-8"))
    assert on_disk["five_hour_percent"] == 27.0
    assert on_disk["fetched_at"] == now.isoformat()
    assert "token" not in json.dumps(on_disk).lower()


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


# --------------------------------------------------------------------------
# Owner decision 2026-09-29: QUOTA_API_ENABLED = False by default
# --------------------------------------------------------------------------


def test_decide_with_quota_api_disabled_goes_unless_locked_or_rate_limited(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ap, "QUOTA_API_ENABLED", False)
    fresh_lock = {"started_at": (NOW - timedelta(hours=1)).isoformat(), "agent_id": "a"}
    stale_lock = {"started_at": (NOW - timedelta(hours=9)).isoformat(), "agent_id": "b"}
    busy = [ap.SessionActivity("x", None, NOW.isoformat())]
    limited = {"retry_after": (NOW + timedelta(hours=1)).isoformat()}
    bad_quota = {"five_hour_percent": 99.0, "seven_day_percent": 99.0}

    # a fresh lock still wins over everything, including a pending session limit.
    verdict, _ = ap.decide(
        now=NOW, lock=fresh_lock, lock_max_hours=4.0, usage=limited, activity=busy
    )
    assert verdict == "skip_round_running"

    # a future retry_after (from usage_state()'s local, no-network, no-credential
    # transcript scan) still skips the round even with the flag off -- launching
    # straight into an exhausted session limit is not what "go by default" means.
    verdict, reasons = ap.decide(now=NOW, lock=None, lock_max_hours=4.0, usage=limited, activity=[])
    assert verdict == "skip_rate_limited"
    assert "usage limit resets at" in reasons[0]

    # a *past* retry_after (already reset) does not gate the round.
    past_limited = {"retry_after": (NOW - timedelta(hours=1)).isoformat()}
    verdict, reasons = ap.decide(
        now=NOW, lock=None, lock_max_hours=4.0, usage=past_limited, activity=[]
    )
    assert verdict == "go", reasons

    # the remaining old gates no longer fire: an unrecorded throttle reset,
    # owner activity, or an over-threshold quota reading no longer skip or wait.
    cases = (
        {"usage": {"unknown_throttle_reset": True}, "activity": []},
        {"usage": {}, "activity": busy},
        {
            "usage": {},
            "activity": busy,
            "quota": bad_quota,
            "background_week_percent_est": 99.0,
        },
    )
    for kwargs in cases:
        verdict, reasons = ap.decide(now=NOW, lock=None, lock_max_hours=4.0, **kwargs)
        assert verdict == "go", (kwargs, reasons)

    # a stale lock is ignored (and reported) rather than blocking the round.
    verdict, reasons = ap.decide(
        now=NOW, lock=stale_lock, lock_max_hours=4.0, usage={}, activity=[]
    )
    assert verdict == "go" and "stale lock" in reasons[0]


def test_quota_state_never_calls_the_live_reader_when_disabled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(ap, "QUOTA_API_ENABLED", False)

    def _must_not_be_called() -> dict:
        raise AssertionError("the live quota endpoint must not be reached while disabled")

    monkeypatch.setattr(ap, "_read_quota_live", _must_not_be_called)
    cache_path = tmp_path / "quota-cache.json"
    cache_path.write_text(
        json.dumps({**_CACHED_QUOTA_FIELDS, "fetched_at": NOW.isoformat(), "source": "live"}),
        encoding="utf-8",
    )

    quota = ap.quota_state(now=NOW, cache_path=cache_path)

    assert quota == {"status": "disabled_by_owner_2026-09-29"}


def test_check_report_with_quota_disabled_reports_status_and_goes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ap, "QUOTA_API_ENABLED", False)
    monkeypatch.setattr(ap, "PROJECTS_DIR", tmp_path / "projects")
    monkeypatch.setattr(ap, "LOCK_PATH", tmp_path / "logs" / "round.lock")

    def _must_not_be_called() -> dict:
        raise AssertionError("the live quota endpoint must not be reached while disabled")

    monkeypatch.setattr(ap, "_read_quota_live", _must_not_be_called)

    args = ap.build_parser().parse_args(["check"])
    report = ap.check_report(args)

    assert report["decision"] == "go"
    assert report["quota"] == {"status": "disabled_by_owner_2026-09-29"}
