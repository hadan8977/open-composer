from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
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
            _log("2026-07-03", status="failed"),
            _log("2026-07-06", status="failed"),
        ]
    )

    assert result["progress_days"] == 0
    assert result["resets"][0]["date"] == "2026-07-06"


def test_paper_validation_writes_final_report_at_target(tmp_path: Path) -> None:
    log_dir = tmp_path / "reports" / "paper" / "daily_cycle"
    log_dir.mkdir(parents=True)
    for day in range(1, 21):
        (log_dir / f"202607{day:02d}.json").write_text(
            json.dumps(_log(f"2026-07-{day:02d}")),
            encoding="utf-8",
        )

    payload = write_paper_validation_report(root=tmp_path, target_days=20)

    assert payload["paper_validation_pass"] is True
    assert Path(payload["artifact_paths"]["final_json"]).exists()
    assert Path(payload["artifact_paths"]["final_markdown"]).exists()


def test_paper_validation_cli_help_smoke() -> None:
    assert CliRunner().invoke(app, ["paper", "validation-report", "--help"]).exit_code == 0


def _log(date: str, *, status: str = "ok", paper_order_authorization: bool = False) -> dict:
    return {
        "date": date,
        "status": status,
        "paper_order_authorization": paper_order_authorization,
        "steps": [{"name": "paper_cycle", "exit_code": 0 if status == "ok" else 1}],
        "artifact_paths": {},
    }
