from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from scripts.run_daily_paper_cycle import (
    DEFAULT_STRATEGY,
    main,
    run_daily_cycle,
)


def test_daily_paper_cycle_success_writes_log_and_review_card(tmp_path: Path) -> None:
    _write_target_weights(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    payload = run_daily_cycle(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        command_runner=fake_run,
        oc_cmd=["oc"],
    )

    assert payload["status"] == "ok"
    assert len(commands) == 4
    assert all("--allow-paper-orders" not in command for command in commands)
    assert payload["artifact_paths"]["state_drift_status"] == "warning"
    card = tmp_path / "reports" / "paper" / "review_cards" / "20260709.md"
    assert card.exists()
    assert "50% Live Mapping" in card.read_text(encoding="utf-8")
    log_path = tmp_path / "reports" / "paper" / "daily_cycle" / "20260709.json"
    log = json.loads(log_path.read_text(encoding="utf-8"))
    assert log["status"] == "ok"
    assert [step["name"] for step in log["steps"]][-1] == "state_drift"


def test_daily_cycle_passes_allow_paper_orders_when_router_authorized(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import scripts.run_daily_paper_cycle as daily_cycle

    _write_target_weights(tmp_path)
    monkeypatch.setattr(
        daily_cycle,
        "assess_paper_strategy_readiness",
        lambda strategy, root: SimpleNamespace(
            status="ok",
            ready=True,
            execution_substate="order_authorized",
        ),
    )
    monkeypatch.setattr(
        daily_cycle,
        "load_paper_kill_switch",
        lambda root: SimpleNamespace(enabled=False),
    )
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    payload = run_daily_cycle(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        command_runner=fake_run,
        oc_cmd=["oc"],
    )

    assert payload["paper_order_authorization"] is True
    assert any(
        command[:3] == ["oc", "run", "paper"] and "--allow-paper-orders" in command
        for command in commands
    )


def test_daily_paper_cycle_failure_stops_and_records_failed_step(tmp_path: Path) -> None:
    _write_target_weights(tmp_path)
    commands: list[list[str]] = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return SimpleNamespace(
            returncode=1 if command[1:3] == ["run", "paper"] else 0,
            stdout="",
            stderr="paper failed",
        )

    payload = run_daily_cycle(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        command_runner=fake_run,
        oc_cmd=["oc"],
    )

    assert payload["status"] == "failed"
    assert payload["failed_step"] == "paper_cycle"
    assert all(command[1:3] != ["paper", "monitor"] for command in commands)
    log_path = tmp_path / "reports" / "paper" / "daily_cycle" / "20260709.json"
    assert "paper failed" in log_path.read_text(encoding="utf-8")


def test_cycle_emits_error_when_previous_failed_day_has_no_remediation(
    tmp_path: Path,
) -> None:
    _write_target_weights(tmp_path)
    previous_log = tmp_path / "reports" / "paper" / "daily_cycle" / "20260708.json"
    previous_log.parent.mkdir(parents=True, exist_ok=True)
    previous_log.write_text(
        json.dumps(
            {
                "date": "2026-07-08",
                "status": "failed",
                "paper_order_authorization": False,
                "steps": [{"name": "paper_cycle", "exit_code": 1}],
                "artifact_paths": {},
            }
        ),
        encoding="utf-8",
    )

    def fake_run(command, **kwargs):
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    payload = run_daily_cycle(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        command_runner=fake_run,
        oc_cmd=["oc"],
    )

    assert payload["previous_day_remediation_check"]["status"] == "error"
    assert payload["artifact_paths"]["previous_day_remediation_status"] == "error"


def test_daily_paper_cycle_weekend_skips_without_commands(tmp_path: Path) -> None:
    def fake_run(command, **kwargs):
        raise AssertionError("weekend should not execute commands")

    payload = run_daily_cycle(
        root=tmp_path,
        cycle_date=date(2026, 7, 11),
        command_runner=fake_run,
        oc_cmd=["oc"],
    )

    assert payload["status"] == "skipped"
    assert payload["skip_reason"] == "non_trading_day_weekend"


def test_daily_paper_cycle_dry_run_prints_plan_without_execution(
    capsys,
    tmp_path: Path,
) -> None:
    exit_code = main(["--dry-run", "--date", "2026-07-09", "--root", str(tmp_path)])

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "uv run oc run paper" in output
    assert "--allow-paper-orders" not in output


def _write_target_weights(root: Path) -> None:
    path = root / "reports" / "execution" / f"{DEFAULT_STRATEGY}-target-weights.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "strategy_name": DEFAULT_STRATEGY,
        "route_label": "defensive_overlay:test",
        "target_weights": [
            {
                "rebalance_session": "2026-07-08",
                "signal_session": "2026-07-07",
                "symbol": "GLD",
                "target_weight": 1.0,
                "selected": True,
            },
            {
                "rebalance_session": "2026-07-08",
                "signal_session": "2026-07-07",
                "symbol": "QLD",
                "target_weight": 0.0,
                "selected": False,
            },
            {
                "rebalance_session": "2026-07-09",
                "signal_session": "2026-07-08",
                "symbol": "GLD",
                "target_weight": 0.0,
                "selected": False,
            },
            {
                "rebalance_session": "2026-07-09",
                "signal_session": "2026-07-08",
                "symbol": "QLD",
                "target_weight": 1.0,
                "selected": True,
            },
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
