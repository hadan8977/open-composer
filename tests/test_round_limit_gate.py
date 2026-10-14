"""Tests for scripts/round_limit_gate.py with fake transcripts and a fake Paseo."""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "round_limit_gate.py"
spec = importlib.util.spec_from_file_location("round_limit_gate", SCRIPT)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
sys.modules["round_limit_gate"] = gate
spec.loader.exec_module(gate)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
CFG: dict[str, Any] = {
    "schedules": {"lead": "opus", "exec": "sonnet"},
    "week_anchor_utc": "2026-10-04T00:00:00+00:00",
    "weekly_cap_units": 1000,
    "weights": {"opus": [5, 6.25, 0.5, 25], "sonnet": [3, 3.75, 0.3, 15]},
    "pace_slack": 0.05,
    "owner_reserve": 0.15,
    "resume_margin_minutes": 2,
}


class FakePaseo:
    def __init__(self, statuses: dict[str, str], agents: dict[str, str] | None = None) -> None:
        self.statuses = dict(statuses)
        self.agents = agents or {}
        self.calls: list[tuple[str, str]] = []

    def schedules(self) -> list[dict[str, Any]]:
        return [{"id": k, "status": v} for k, v in self.statuses.items()]

    def pause(self, schedule_id: str) -> None:
        self.calls.append(("pause", schedule_id))
        self.statuses[schedule_id] = "paused"

    def resume(self, schedule_id: str) -> None:
        self.calls.append(("resume", schedule_id))
        self.statuses[schedule_id] = "active"

    def agent_status(self, agent_id: str) -> str | None:
        return self.agents.get(agent_id)


def _write(path: Path, rows: list[dict[str, Any]], mtime: datetime) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")
    stamp = mtime.timestamp()
    import os

    os.utime(path, (stamp, stamp))
    return path


def _rejection(at: datetime, resets: datetime | None, kind: str = "seven_day") -> dict[str, Any]:
    quota: dict[str, Any] = {"status": "rejected", "rateLimitType": kind}
    if resets is not None:
        quota["resetsAt"] = int(resets.timestamp())
    return {"type": "system", "timestamp": at.isoformat(), "quotaLimits": quota}


def _assistant(at: datetime, msg_id: str, model: str, out: int, inp: int = 0) -> dict[str, Any]:
    return {
        "type": "assistant",
        "timestamp": at.isoformat(),
        "message": {
            "id": msg_id,
            "model": model,
            "usage": {"input_tokens": inp, "output_tokens": out},
        },
    }


def _paths(tmp_path: Path) -> dict[str, Path]:
    logs = tmp_path / "logs"
    return {
        "projects_dir": tmp_path / "projects",
        "state_path": logs / "state.json",
        "ledger_path": logs / "ledger.json",
        "status_path": logs / "status.json",
        "lock_path": logs / "round.lock",
        "log_path": logs / "gate.log",
    }


def _run(tmp_path: Path, paseo: FakePaseo, now: datetime = NOW, **kw: Any) -> dict[str, Any]:
    return gate.run_once(now, CFG, paseo, **_paths(tmp_path), **kw)


def test_active_limit_pauses_both_schedules_then_resumes_after_reset(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    reset = NOW + timedelta(hours=3)
    _write(projects / "p" / "a.jsonl", [_rejection(NOW - timedelta(minutes=5), reset)], NOW)
    paseo = FakePaseo({"lead": "active", "exec": "active", "other": "active"})

    summary = _run(tmp_path, paseo)
    assert paseo.calls == [("pause", "lead"), ("pause", "exec")]
    assert summary["paused_by_gate"] == ["exec", "lead"]
    assert "other" not in json.dumps(paseo.calls)

    _run(tmp_path, paseo, now=NOW + timedelta(hours=1))  # still limited: no new calls
    assert len(paseo.calls) == 2

    _run(tmp_path, paseo, now=reset + timedelta(minutes=1))  # inside the 2-minute margin
    assert len(paseo.calls) == 2

    after = _run(tmp_path, paseo, now=reset + timedelta(minutes=3))
    assert paseo.calls[2:] == [("resume", "lead"), ("resume", "exec")]
    assert after["paused_by_gate"] == []
    log = (tmp_path / "logs" / "gate.log").read_text(encoding="utf-8")
    assert "pause lead" in log and "resume exec" in log


def test_manual_pause_is_never_resumed(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    reset = NOW + timedelta(hours=1)
    _write(projects / "p" / "a.jsonl", [_rejection(NOW, reset)], NOW)
    paseo = FakePaseo({"lead": "paused", "exec": "active"})
    _run(tmp_path, paseo)
    assert paseo.calls == [("pause", "exec")]
    _run(tmp_path, paseo, now=reset + timedelta(minutes=5))
    assert paseo.calls == [("pause", "exec"), ("resume", "exec")]
    assert paseo.statuses["lead"] == "paused"


def test_model_specific_limit_binds_only_that_model(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write(
        projects / "p" / "a.jsonl",
        [_rejection(NOW, NOW + timedelta(days=1), kind="seven_day_opus")],
        NOW,
    )
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    _run(tmp_path, paseo)
    assert paseo.calls == [("pause", "lead")]


def test_rejection_without_reset_counts_for_five_hours(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write(projects / "p" / "a.jsonl", [_rejection(NOW - timedelta(hours=4), None)], NOW)
    limits = gate.active_limits(projects, NOW, margin=timedelta(minutes=2))
    assert len(limits) == 1
    assert gate.active_limits(projects, NOW + timedelta(hours=2), margin=timedelta(0)) == []


def test_subagent_transcripts_are_scanned(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    path = projects / "p" / "sess" / "subagents" / "agent-1.jsonl"
    _write(path, [_rejection(NOW, NOW + timedelta(hours=2))], NOW)
    assert len(gate.active_limits(projects, NOW, margin=timedelta(0))) == 1


def test_past_resets_do_not_block(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    old = NOW - timedelta(hours=10)
    _write(projects / "p" / "a.jsonl", [_rejection(old, old + timedelta(hours=1))], NOW)
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    summary = _run(tmp_path, paseo)
    assert paseo.calls == [] and summary["limits"] == []


def test_ledger_dedupes_message_ids_across_passes_and_skips_old_lines(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    path = projects / "p" / "a.jsonl"
    anchor = gate._ts(CFG["week_anchor_utc"])
    before_week = datetime(2026, 10, 3, 23, 0, tzinfo=UTC)
    _write(path, [_assistant(before_week, "m0", "claude-opus-5-5", 1_000_000)], NOW)
    _write(path, [_assistant(NOW, "m1", "claude-opus-5-5", 100_000)], NOW)
    ledger = gate.update_ledger({}, projects, NOW, anchor=anchor, weights=CFG["weights"])
    assert round(ledger["total"], 6) == 2.5  # 0.1M output tokens x 25; m0 is last week
    # same message id again with the final output count (Claude Code repeats the id)
    _write(path, [_assistant(NOW, "m1", "claude-opus-5-5", 120_000)], NOW)
    _write(path, [{"type": "progress", "message": {"usage": {"output_tokens": 9}}}], NOW)
    ledger = gate.update_ledger(ledger, projects, NOW, anchor=anchor, weights=CFG["weights"])
    assert round(ledger["total"], 6) == 3.0
    sonnet = [_assistant(NOW, "m2", "claude-sonnet-5-5", 0, inp=1_000_000)]
    _write(projects / "p" / "s" / "subagents" / "agent-x.jsonl", sonnet, NOW)
    ledger = gate.update_ledger(ledger, projects, NOW, anchor=anchor, weights=CFG["weights"])
    assert round(ledger["total"], 6) == 6.0
    assert set(ledger["units"]) == {"interactive", "interactive_subagents"}


def test_partial_last_line_is_left_for_the_next_pass(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    path = projects / "p" / "a.jsonl"
    anchor = gate._ts(CFG["week_anchor_utc"])
    line = json.dumps(_assistant(NOW, "m1", "claude-opus-5-5", 40_000))
    path.parent.mkdir(parents=True)
    path.write_text(line[:30], encoding="utf-8")
    ledger = gate.update_ledger({}, projects, NOW, anchor=anchor, weights=CFG["weights"])
    assert ledger["total"] == 0.0
    path.write_text(line + "\n", encoding="utf-8")
    ledger = gate.update_ledger(ledger, projects, NOW, anchor=anchor, weights=CFG["weights"])
    assert round(ledger["total"], 6) == 1.0


def test_new_week_resets_the_ledger(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    anchor = gate._ts(CFG["week_anchor_utc"])
    _write(projects / "p" / "a.jsonl", [_assistant(NOW, "m1", "claude-opus-5-5", 40_000)], NOW)
    ledger = gate.update_ledger({}, projects, NOW, anchor=anchor, weights=CFG["weights"])
    assert ledger["total"] > 0
    later = NOW + timedelta(days=7)
    ledger = gate.update_ledger(ledger, projects, later, anchor=anchor, weights=CFG["weights"])
    assert ledger["week_start"] == "2026-10-11T00:00:00+00:00" and ledger["total"] == 0.0


def test_pace_pause_with_hysteresis() -> None:
    start = datetime(2026, 10, 4, tzinfo=UTC)
    day2 = start + timedelta(days=2)  # pace 285.7 of 1000, slack 50
    assert gate.pace_check(330, day2, start, CFG, paused=False)["allowed"]
    assert not gate.pace_check(340, day2, start, CFG, paused=False)["allowed"]
    assert not gate.pace_check(300, day2, start, CFG, paused=True)["allowed"]
    assert gate.pace_check(280, day2, start, CFG, paused=True)["allowed"]
    late = start + timedelta(days=6, hours=20)  # pace 976, but the owner reserve binds at 850
    assert not gate.pace_check(860, late, start, CFG, paused=False)["allowed"]


def test_pace_pause_runs_through_the_schedules(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    # 2026-10-05 12:00 is 1.5 days into the week: pace 214, allowed up to 264 units
    heavy = [_assistant(NOW, f"m{i}", "claude-opus-5-5", 1_000_000) for i in range(12)]
    _write(projects / "p" / "a.jsonl", heavy, NOW)  # 12 x 25 = 300 units
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    summary = _run(tmp_path, paseo)
    assert paseo.calls == [("pause", "lead"), ("pause", "exec")]
    assert summary["pace"]["used_units"] == 300.0
    later = NOW + timedelta(days=1)  # pace 357 > 300: back on pace
    _run(tmp_path, paseo, now=later)
    assert paseo.calls[2:] == [("resume", "lead"), ("resume", "exec")]


def test_weekly_limit_records_the_observed_cap_once(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write(projects / "p" / "a.jsonl", [_rejection(NOW, NOW + timedelta(days=2))], NOW)
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    first = _run(tmp_path, paseo)
    assert any("weekly limit seen" in a for a in first["actions"])
    second = _run(tmp_path, paseo, now=NOW + timedelta(minutes=5))
    assert not any("weekly limit seen" in a for a in second["actions"])


def test_dead_lock_is_moved_aside_but_a_live_or_unknown_one_stays(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    lock = paths["lock_path"]
    lock.parent.mkdir(parents=True)
    for holder, status, moved in (
        ("alive", "running", False),
        ("ghost", None, False),
        ("dead", "archived", True),
    ):
        lock.write_text(json.dumps({"agent_id": holder, "started_at": "x"}), encoding="utf-8")
        paseo = FakePaseo(
            {"lead": "active", "exec": "active"}, agents={holder: status} if status else {}
        )
        _run(tmp_path, paseo)
        assert lock.exists() is (not moved)
    assert json.loads(lock.with_name("round.lock.dead").read_text())["agent_id"] == "dead"


def test_dry_run_changes_nothing(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    _write(projects / "p" / "a.jsonl", [_rejection(NOW, NOW + timedelta(hours=2))], NOW)
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    summary = _run(tmp_path, paseo, dry_run=True)
    assert paseo.calls == [] and len(summary["actions"]) == 3  # 2 pauses + cap note
    assert not (tmp_path / "logs" / "state.json").exists()


def test_a_later_successful_call_lifts_the_limit(tmp_path: Path) -> None:
    """The owner used a reset: rounds resume before the recorded Sunday reset."""
    projects = tmp_path / "projects"
    hit = NOW - timedelta(hours=2)
    _write(projects / "p" / "a.jsonl", [_rejection(hit, NOW + timedelta(days=3))], NOW)
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    _run(tmp_path, paseo)
    assert paseo.calls == [("pause", "lead"), ("pause", "exec")]
    later = NOW + timedelta(minutes=10)
    _write(projects / "p" / "b.jsonl", [_assistant(later, "ok1", "claude-opus-5-5", 10)], later)
    summary = _run(tmp_path, paseo, now=later + timedelta(minutes=1))
    assert paseo.calls[2:] == [("resume", "lead"), ("resume", "exec")]
    assert summary["limits"] == []


def test_success_of_another_model_or_before_the_hit_does_not_lift(tmp_path: Path) -> None:
    projects = tmp_path / "projects"
    hit = NOW - timedelta(hours=1)
    _write(
        projects / "p" / "a.jsonl",
        [
            _assistant(hit - timedelta(minutes=5), "early", "claude-opus-5-5", 10),
            _rejection(hit, NOW + timedelta(days=1), kind="seven_day_opus"),
            _assistant(hit + timedelta(minutes=5), "son", "claude-sonnet-5-5", 10),
        ],
        NOW,
    )
    ledger = gate.update_ledger(
        {}, projects, NOW, anchor=gate._ts(CFG["week_anchor_utc"]), weights=CFG["weights"]
    )
    limits = gate.active_limits(
        projects, NOW, margin=timedelta(0), last_success=ledger["last_success"]
    )
    assert [lim.kind for lim in limits] == ["seven_day_opus"]


def test_extra_reset_doubles_that_weeks_cap_only() -> None:
    start = datetime(2026, 10, 4, tzinfo=UTC)
    cfg = dict(CFG, extra_resets_by_week={"2026-10-04T00:00:00+00:00": 1})
    day2 = start + timedelta(days=2)
    assert gate.pace_check(600, day2, start, cfg, paused=False)["allowed"]  # pace 571 + 100
    assert gate.pace_check(600, day2, start, cfg, paused=False)["cap_units"] == 2000
    next_week = start + timedelta(days=9)
    assert not gate.pace_check(600, next_week, start + timedelta(days=7), cfg, paused=False)[
        "allowed"
    ]


def _memory_files(tmp_path: Path, at: datetime, **status: Any) -> dict[str, Path]:
    status_path = tmp_path / "memory" / "governor-status.json"
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(
        json.dumps({"checked_at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), **status}), encoding="utf-8"
    )
    config_path = tmp_path / "memory" / "budget.json"
    config_path.write_text(
        json.dumps(
            {
                "background_agents_max": 3,
                "gate_pause_after_s": 300,
                "agent_admit_headroom_mb": 400,
            }
        ),
        encoding="utf-8",
    )
    return {"memory_status_path": status_path, "memory_config_path": config_path}


def test_memory_cap_pauses_rounds_and_resumes_when_clear(tmp_path: Path) -> None:
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    full = _memory_files(tmp_path, NOW, background_agents=3, low_headroom_s=0, headroom_mb=900)
    summary = _run(tmp_path, paseo, **full)
    assert paseo.calls == [("pause", "lead"), ("pause", "exec")]
    assert summary["memory"] == ["memory: 3 background agents live (cap 3)"]

    later = NOW + timedelta(minutes=5)
    clear = _memory_files(tmp_path, later, background_agents=1, low_headroom_s=0, headroom_mb=900)
    _run(tmp_path, paseo, now=later, **clear)
    assert paseo.calls[2:] == [("resume", "lead"), ("resume", "exec")]


def test_memory_low_headroom_needs_the_full_window(tmp_path: Path) -> None:
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    short = _memory_files(tmp_path, NOW, background_agents=0, low_headroom_s=120, headroom_mb=200)
    assert _run(tmp_path, paseo, **short)["memory"] == []
    assert paseo.calls == []
    long = _memory_files(tmp_path, NOW, background_agents=0, low_headroom_s=300, headroom_mb=200)
    assert _run(tmp_path, paseo, **long)["memory"][0].startswith("memory: headroom 200 MB")


def test_memory_stale_or_missing_status_never_pauses(tmp_path: Path) -> None:
    paseo = FakePaseo({"lead": "active", "exec": "active"})
    stale = _memory_files(
        tmp_path, NOW - timedelta(minutes=10), background_agents=9, low_headroom_s=9999
    )
    assert _run(tmp_path, paseo, **stale)["memory"] == []
    assert _run(tmp_path, paseo)["memory"] == []  # default: no memory status consulted
    assert paseo.calls == []
