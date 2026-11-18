"""Paper monitoring failures stay visible without service, broker or mail writes."""

import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import paper_watchdog as watchdog
from scripts import publish_paper_dashboard_daily as daily

NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)
DAY = date(2026, 11, 9)


@pytest.mark.parametrize(
    "problem",
    [None, "blocked_policy", "blocked_service", "stale", "missing", "corrupt", "no_directory", "heartbeat"],
)
def test_watchdog_alerts_attention_without_restarting_healthy_service(tmp_path, monkeypatch, problem):
    state = {
        "heartbeat_at": (NOW - timedelta(seconds=901) if problem == "heartbeat" else NOW).isoformat(),
        "status": "blocked" if problem == "blocked_service" else "running",
        "policy_status": {"BASE": {"status": "blocked" if problem == "blocked_policy" else "ready"}},
    }
    state_path = tmp_path / "state.json"
    state_path.write_text(json.dumps(state))
    targets = tmp_path / "targets"
    if problem != "no_directory":
        targets.mkdir()
        for policy in watchdog.POLICIES:
            (targets / f"{policy}.json").write_text(json.dumps({"application_day": str(DAY)}))
        base = targets / "BASE.json"
        if problem == "stale":
            base.write_text('{"application_day": "2026-11-06"}')
        elif problem == "missing":
            base.unlink()
        elif problem == "corrupt":
            base.write_text('{')
    alerts = []
    monkeypatch.setattr(watchdog, "STATE", state_path)
    monkeypatch.setattr(watchdog, "TARGETS", targets)
    monkeypatch.setattr(watchdog, "now_utc", lambda: NOW)
    monkeypatch.setattr(watchdog, "expected_application_day", lambda _: DAY)
    monkeypatch.setattr(watchdog, "unit_state", lambda: "active")
    monkeypatch.setattr(watchdog, "notify", lambda *a, **kw: alerts.append((a, kw)) or {"email": "test"})

    def no_restart(*a, **kw):
        pytest.fail("blocked policies and target problems must not restart the service")

    monkeypatch.setattr(watchdog.subprocess, "run", no_restart)
    report = watchdog.health(SimpleNamespace(stale_after=900, fix=problem != "heartbeat", wait=0))
    assert report["healthy"] is (problem is None)
    assert len(alerts) == int(problem is not None)
    assert report["restarted"] is False
    if problem in {"stale", "missing", "corrupt"}:
        assert report["stale_targets"] == ["BASE"]
    if problem in {"missing", "corrupt", "no_directory"}:
        assert report["target_errors"]
        assert "target_errors=" in alerts[0][0][1]
    if problem == "blocked_policy":
        assert "blocked=['BASE']" in alerts[0][0][1]


@pytest.fixture
def daily_rig(tmp_path, monkeypatch):
    from open_composer.cockpit.data import paper_books

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW

    sealed = tmp_path / "sealed.json"
    sealed.write_text('{"histories": []}')
    monkeypatch.setattr(daily, "ROOT", tmp_path)
    monkeypatch.setattr(daily, "LOG", tmp_path / "publish.jsonl")
    monkeypatch.setattr(daily, "SEALED_HISTORY", sealed)
    monkeypatch.setattr(daily, "datetime", Clock)
    monkeypatch.setattr(paper_books, "latest_completed_session", lambda _: DAY)
    monkeypatch.setattr(sys, "argv", ["publish_paper_dashboard_daily.py"])
    monkeypatch.setitem(sys.modules, "paper_watchdog", watchdog)
    alerts = []
    monkeypatch.setattr(watchdog, "notify", lambda *a, **kw: alerts.append((a, kw)))
    work = tmp_path / f"reports/paper/diagnostics/forward-projection-{DAY}"
    old_inputs = work / "inputs"
    old_inputs.mkdir(parents=True)
    receipt = {
        "captured_at": NOW.isoformat(),
        "portfolio_history": {"timestamp": [int(NOW.timestamp())], "equity": [100]},
        "account": {"equity": "100"},
    }
    for alias in ("legacy", "quant1", "six"):
        (old_inputs / f"account-{alias}.json").write_text(json.dumps(receipt))
    (work / "history.json").write_text(json.dumps({"through_session": str(DAY)}))
    return SimpleNamespace(root=tmp_path, work=work, old_inputs=old_inputs, receipt=receipt, alerts=alerts)


@pytest.mark.parametrize(
    "problem,expected_steps,error",
    [
        ("capture_failure", ["capture"], "capture failed"),
        ("missing", ["capture"], "FileNotFoundError"),
        ("corrupt", ["capture"], "JSONDecodeError"),
        ("malformed", ["capture"], "KeyError"),
        ("extend_failure", ["capture", "extend"], "extend failed"),
        ("publish_failure", ["capture", "extend", "publish"], "publish failed"),
        (None, ["capture", "extend", "publish"], None),
    ],
)
def test_daily_capture_failure_is_logged_alerted_and_stops_publication(
    daily_rig, monkeypatch, problem, expected_steps, error
):
    rig = daily_rig
    calls = []

    def run(step, command):
        calls.append(step)
        if step == "capture":
            inputs = Path(command[command.index("--out") + 1])
            assert inputs != rig.old_inputs
            assert list(inputs.iterdir()) == []
            if problem != "capture_failure":
                for alias in ("legacy", "quant1", "six"):
                    if alias == "six" and problem == "missing":
                        continue
                    body = json.dumps(rig.receipt)
                    if alias == "six" and problem in {"corrupt", "malformed"}:
                        body = "{" if problem == "corrupt" else "{}"
                    (inputs / f"account-{alias}.json").write_text(body)
        elif step == "extend" and problem != "extend_failure":
            Path(command[command.index("--output") + 1]).write_text(
                json.dumps({"through_session": str(DAY)})
            )
        return {"step": step, "exit_code": int(problem == f"{step}_failure"), "stderr_tail": "test"}

    monkeypatch.setattr(daily, "run", run)
    assert daily.main() == (2 if problem else 0)
    summary = json.loads(daily.LOG.read_text())
    assert calls == expected_steps
    assert summary["ok"] is (problem is None)
    assert len(rig.alerts) == int(problem is not None)
    if error:
        assert error in summary["error"]
        assert error in rig.alerts[0][0][1]
        assert summary["through_session"] is None
    assert len(list(rig.old_inputs.iterdir())) == 3
