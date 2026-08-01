from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.market_calendar import next_us_equity_session
from open_composer.paper_validation import (
    check_previous_trading_day_remediation,
    evaluate_validation_days,
    remediation_record_path,
    write_paper_validation_report,
)


def test_paper_validation_counts_pass_days() -> None:
    result = evaluate_validation_days([_log("2026-07-01"), _log("2026-07-02")])

    assert result["progress_days"] == 2
    assert result["paper_validation_pass"] is False
    assert all(row["passed"] for row in result["days"])


def test_paper_validation_records_failed_day_without_reset() -> None:
    result = evaluate_validation_days([_log("2026-07-01"), _log("2026-07-02", status="failed")])

    assert result["progress_days"] == 1
    assert result["consecutive_failures"] == 1
    assert result["days"][1]["passed"] is False


def test_paper_validation_authorized_day_can_pass() -> None:
    result = evaluate_validation_days([_log("2026-07-01", paper_order_authorization=True)])

    assert result["days"][0]["passed"] is True
    assert "paper_order_authorization_invalid" not in result["days"][0]["reasons"]


def test_paper_validation_accepts_bound_active_canary_broker_day(tmp_path: Path) -> None:
    log = _log("2026-07-01", paper_order_authorization=True)
    log["paper_authorization_substate"] = "canary_authorized"
    log = _with_evidence(tmp_path, log)

    result = evaluate_validation_days(
        [log],
        root=tmp_path,
        as_of=datetime(2026, 7, 1, 23, tzinfo=UTC),
        require_order_authorized=True,
    )

    assert result["progress_days"] == 1
    assert result["days"][0]["reasons"] == []


def test_failed_day_with_remediation_is_recorded_without_missing_flag(tmp_path: Path) -> None:
    path = remediation_record_path(tmp_path, "2026-07-01")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Remediation\n\n- status: fixed\n", encoding="utf-8")

    result = evaluate_validation_days(
        [_log("2026-07-01", status="failed")],
        root=tmp_path,
    )

    assert result["days"][0]["remediation_required"] is True
    assert result["days"][0]["remediation_recorded"] is True
    assert result["missing_remediations"] == []


def test_failed_day_without_remediation_is_reported(tmp_path: Path) -> None:
    result = evaluate_validation_days(
        [_log("2026-07-01", status="failed")],
        root=tmp_path,
    )

    assert result["days"][0]["remediation_required"] is True
    assert result["days"][0]["remediation_recorded"] is False
    assert len(result["missing_remediations"]) == 1


def test_previous_failed_day_remediation_check_paths(tmp_path: Path) -> None:
    log_dir = tmp_path / "reports" / "paper" / "daily_cycle"
    log_dir.mkdir(parents=True)
    (log_dir / "20260708.json").write_text(
        json.dumps(_log("2026-07-08", status="failed")),
        encoding="utf-8",
    )

    missing = check_previous_trading_day_remediation(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
    )
    assert missing["status"] == "error"

    remediation = remediation_record_path(tmp_path, "2026-07-08")
    remediation.parent.mkdir(parents=True, exist_ok=True)
    remediation.write_text("# Remediation\n", encoding="utf-8")
    recorded = check_previous_trading_day_remediation(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
    )
    assert recorded["status"] == "ok"


def test_paper_validation_two_consecutive_failures_reset_window() -> None:
    result = evaluate_validation_days(
        [
            _log("2026-07-01"),
            _log("2026-07-02"),
            _log("2026-07-06", status="failed"),
            _log("2026-07-07", status="failed"),
        ]
    )

    assert result["progress_days"] == 0
    assert result["resets"][0]["date"] == "2026-07-07"


def test_paper_validation_writes_final_report_at_target(tmp_path: Path) -> None:
    log_dir = tmp_path / "reports" / "paper" / "daily_cycle"
    log_dir.mkdir(parents=True)
    day = date(2026, 6, 1)
    for _ in range(20):
        (log_dir / f"{day:%Y%m%d}.json").write_text(
            json.dumps(
                _with_evidence(
                    tmp_path,
                    _log(day.isoformat(), paper_order_authorization=True),
                )
            ),
            encoding="utf-8",
        )
        day = next_us_equity_session(day)

    payload = write_paper_validation_report(root=tmp_path, target_days=20)

    assert payload["paper_validation_pass"] is True
    assert Path(payload["artifact_paths"]["final_json"]).exists()
    assert Path(payload["artifact_paths"]["final_markdown"]).exists()


def test_paper_validation_filters_strategy_and_current_bindings(tmp_path: Path) -> None:
    log_dir = tmp_path / "reports" / "paper" / "daily_cycle"
    log_dir.mkdir(parents=True)
    matching = {
        **_log("2026-07-01", paper_order_authorization=True),
        "strategy": "selected",
        "spec_hash": "a" * 64,
        "execution_policy_id": "policy-v1",
        "execution_policy_hash": "b" * 64,
    }
    stale = {
        **_log("2026-07-02", paper_order_authorization=True),
        "strategy": "selected",
        "spec_hash": "c" * 64,
        "execution_policy_id": "policy-v1",
        "execution_policy_hash": "b" * 64,
    }
    other = {**matching, "date": "2026-07-06", "strategy": "other"}
    for index, row in enumerate([matching, stale, other]):
        row = _with_evidence(tmp_path, row, suffix=str(index))
        (log_dir / f"row-{index}.json").write_text(json.dumps(row), encoding="utf-8")

    payload = write_paper_validation_report(
        root=tmp_path,
        target_days=2,
        strategy_name="selected",
        spec_hash="a" * 64,
        execution_policy_id="policy-v1",
        execution_policy_hash="b" * 64,
        not_before="2026-07-01",
    )

    assert payload["progress_days"] == 1
    assert payload["paper_validation_pass"] is False
    assert payload["excluded_logs"][0]["reasons"] == "spec_hash_mismatch"


def test_paper_validation_does_not_count_weekends_or_duplicate_dates() -> None:
    result = evaluate_validation_days(
        [
            _log("2026-07-02"),
            _log("2026-07-02"),
            _log("2026-07-04"),
        ],
        target_days=2,
    )

    assert result["progress_days"] == 1
    assert [row["reasons"] for row in result["days"]] == [
        [],
        ["duplicate_cycle_log_date"],
        ["invalid_or_non_trading_day"],
    ]


def test_paper_validation_cli_help_smoke() -> None:
    assert CliRunner().invoke(app, ["paper", "validation-report", "--help"]).exit_code == 0


def test_paper_validation_rejects_future_cycle_date() -> None:
    result = evaluate_validation_days(
        [_log("2026-07-20")],
        as_of=datetime(2026, 7, 19, 23, 59, tzinfo=UTC),
    )

    assert result["progress_days"] == 0
    assert result["days"][0]["reasons"] == ["future_cycle_date"]


def test_paper_validation_rejects_modified_bound_artifact(tmp_path: Path) -> None:
    log = _with_evidence(tmp_path, _log("2026-07-01"))
    target = tmp_path / log["evidence_bindings"][0]["path"]
    target.write_text("modified\n", encoding="utf-8")

    result = evaluate_validation_days([log], root=tmp_path)

    assert result["progress_days"] == 0
    assert "evidence_hash_mismatch_target_weights" in result["days"][0]["reasons"]


def test_paper_validation_rejects_runner_order_error_even_with_zero_step_exit(
    tmp_path: Path,
) -> None:
    log = _with_evidence(
        tmp_path,
        _log("2026-07-01", paper_order_authorization=True),
    )
    binding = next(row for row in log["evidence_bindings"] if row["role"] == "paper_cycle")
    path = tmp_path / binding["path"]
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["signals"] = [{"decision": "order_error"}]
    path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
    binding["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
    binding["size_bytes"] = path.stat().st_size

    result = evaluate_validation_days(
        [log],
        root=tmp_path,
        as_of=datetime(2026, 7, 1, 23, tzinfo=UTC),
        require_order_authorized=True,
    )

    assert result["progress_days"] == 0
    assert "paper_cycle_order_error" in result["days"][0]["reasons"]


def test_paper_validation_rejects_non_active_spec_binding(tmp_path: Path) -> None:
    log = _with_evidence(tmp_path, _log("2026-07-01"))
    log["active_spec_hash"] = "c" * 64

    result = evaluate_validation_days([log], root=tmp_path)

    assert result["progress_days"] == 0
    assert "active_spec_hash_mismatch" in result["days"][0]["reasons"]


def _log(date: str, *, status: str = "ok", paper_order_authorization: bool = False) -> dict:
    started = datetime.fromisoformat(date).replace(tzinfo=UTC, hour=13)
    return {
        "report_type": "daily_paper_cycle",
        "cycle_receipt_version": 3,
        "date": date,
        "started_at": started.isoformat(),
        "ended_at": (started + timedelta(minutes=5)).isoformat(),
        "spec_hash": "a" * 64,
        "active_spec_hash": "a" * 64,
        "active_spec_path": "strategy_specs/active/test.yaml",
        "execution_policy_id": "policy-v1",
        "execution_policy_hash": "b" * 64,
        "status": status,
        "paper_order_authorization": paper_order_authorization,
        "paper_authorization_substate": (
            "order_authorized" if paper_order_authorization else "observation_only"
        ),
        "previous_day_remediation_check": {"status": "ok"},
        "steps": [
            {"name": "readiness", "exit_code": 0},
            {"name": "target_weights", "exit_code": 0},
            {"name": "paper_cycle", "exit_code": 0 if status == "ok" else 1},
            {"name": "paper_monitor", "exit_code": 0},
            {"name": "state_drift", "exit_code": 0},
        ],
        "artifact_paths": {},
    }


def _with_evidence(root: Path, log: dict, *, suffix: str = "") -> dict:
    bindings = []
    payloads = {
        "target_weights": {
            "strategy_name": log.get("strategy"),
            "target_weights": [],
        },
        "review_card": {
            "strategy": log.get("strategy"),
            "date": log["date"],
        },
        "state_drift": {
            "report_type": "paper_state_drift",
            "date": log["date"],
            "status": "ok",
        },
    }
    if log.get("paper_order_authorization") is True:
        account_hash = "c" * 64
        substate = log.get("paper_authorization_substate")
        authorization_kind = "canary" if substate == "canary_authorized" else "full"
        authorization = {
            "strategy_name": log.get("strategy"),
            "spec_hash": log["spec_hash"],
            "execution_policy_id": log["execution_policy_id"],
            "execution_policy_hash": log["execution_policy_hash"],
            "authorization_kind": authorization_kind,
            "execution_substate": substate,
            "authorized": True,
            "authorized_at": log["started_at"],
            "authorized_by": "test",
            "order_scope": "alpaca_paper_only",
            "real_money_broker_writes": "out_of_scope",
        }
        if authorization_kind == "canary":
            authorization["broker_account_id_hash"] = account_hash
            authorization["expires_at"] = (
                datetime.fromisoformat(log["ended_at"]) + timedelta(days=1)
            ).isoformat()
        authorization["authorization_id"] = (
            "auth_"
            + hashlib.sha256(
                json.dumps(
                    authorization,
                    ensure_ascii=True,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()[:16]
        )
        payloads.update(
            {
                "paper_readiness": {
                    "strategy_name": log.get("strategy"),
                    "status": "warning" if authorization_kind == "canary" else "ok",
                    "execution_substate": substate,
                },
                "paper_authorization": authorization,
                "broker_sync": {"paper": True, "orders": []},
                "broker_sync_receipt": {
                    "receipt_version": 1,
                    "receipt_source": "alpaca_paper_sync",
                    "paper": True,
                    "broker_account_id_hash": account_hash,
                },
                "account_snapshot": {
                    "paper": True,
                    "broker_account_id_hash": account_hash,
                },
                "positions_snapshot": {"paper": True, "positions": []},
                "paper_monitor": {
                    "status": "ok",
                    "sync_broker": True,
                    "sync_status": "ok",
                },
                "paper_cycle": {
                    "run_id": f"paper-{log['date']}",
                    "strategy_name": log.get("strategy"),
                    "spec_hash": log["spec_hash"],
                    "signals": [],
                },
            }
        )
    for role, payload in payloads.items():
        path = root / "evidence" / f"{log['date']}-{suffix}-{role}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, sort_keys=True) + "\n", encoding="utf-8")
        bindings.append(
            {
                "role": role,
                "path": path.relative_to(root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "size_bytes": path.stat().st_size,
            }
        )
    return {**log, "evidence_bindings": bindings}
