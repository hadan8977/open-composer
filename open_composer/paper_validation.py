from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

TARGET_VALID_DAYS = 20


def build_paper_validation_report(
    *,
    root: Path | None = None,
    target_days: int = TARGET_VALID_DAYS,
) -> dict[str, Any]:
    base = root or project_root()
    logs = _load_cycle_logs(base)
    evaluated = evaluate_validation_days(logs, target_days=target_days, root=base)
    return {
        "report_type": "paper_validation_progress",
        "generated_at": datetime.now(UTC).isoformat(),
        "target_days": target_days,
        "progress_days": evaluated["progress_days"],
        "paper_validation_pass": evaluated["paper_validation_pass"],
        "window_start": evaluated["window_start"],
        "window_end": evaluated["window_end"],
        "consecutive_failures": evaluated["consecutive_failures"],
        "resets": evaluated["resets"],
        "missing_remediations": evaluated["missing_remediations"],
        "days": evaluated["days"],
        "evidence_inputs": {
            "daily_cycle_dir": str(base / "reports" / "paper" / "daily_cycle"),
            "sync_log": str(base / "reports" / "paper" / "sync.jsonl"),
            "reconciliation": str(base / "reports" / "paper" / "reconciliation.json"),
            "status": str(base / "reports" / "paper" / "status.json"),
            "signal_logs": str(base / "signal_logs"),
        },
        "semantics": [
            "This validates the paper execution workflow, not strategy alpha.",
            "Skipped non-trading days do not count in the denominator.",
            "One failed trading day does not clear the window; two consecutive failures reset it.",
        ],
    }


def write_paper_validation_report(
    *,
    root: Path | None = None,
    target_days: int = TARGET_VALID_DAYS,
) -> dict[str, Any]:
    base = root or project_root()
    payload = build_paper_validation_report(root=base, target_days=target_days)
    out_dir = ensure_dir(base / "reports" / "paper" / "validation")
    progress_json = out_dir / "paper-validation-progress.json"
    progress_md = out_dir / "paper-validation-progress.md"
    payload["artifact_paths"] = {
        "json": str(progress_json),
        "markdown": str(progress_md),
    }
    write_json(progress_json, payload)
    progress_md.write_text(render_paper_validation_markdown(payload), encoding="utf-8")
    if payload["paper_validation_pass"]:
        final_stem = out_dir / f"paper-validation-report-{payload['window_end']}"
        final_json = final_stem.with_suffix(".json")
        final_md = final_stem.with_suffix(".md")
        payload["artifact_paths"]["final_json"] = str(final_json)
        payload["artifact_paths"]["final_markdown"] = str(final_md)
        write_json(final_json, payload)
        final_md.write_text(render_paper_validation_markdown(payload), encoding="utf-8")
        write_json(progress_json, payload)
    return payload


def evaluate_validation_days(
    logs: list[dict[str, Any]],
    *,
    target_days: int = TARGET_VALID_DAYS,
    root: Path | None = None,
) -> dict[str, Any]:
    days = []
    window_pass_dates: list[str] = []
    consecutive_failures = 0
    resets = []
    for log in sorted(logs, key=lambda item: str(item.get("date", ""))):
        if log.get("status") == "skipped":
            days.append(_day_row(log, counted=False, passed=None, reasons=["skipped"]))
            continue
        passed, reasons = validation_day_pass(log)
        row = _day_row(log, counted=True, passed=passed, reasons=reasons)
        if not passed and root is not None:
            remediation_path = remediation_record_path(root, str(log.get("date")))
            row["remediation_required"] = True
            row["remediation_record_path"] = str(remediation_path)
            row["remediation_recorded"] = remediation_path.exists()
        days.append(row)
        if passed:
            window_pass_dates.append(str(log["date"]))
            consecutive_failures = 0
            continue
        consecutive_failures += 1
        if consecutive_failures >= 2:
            resets.append(
                {
                    "date": log.get("date"),
                    "reason": "two_consecutive_failed_trading_days",
                }
            )
            window_pass_dates = []
            consecutive_failures = 0
    progress_days = min(len(window_pass_dates), target_days)
    return {
        "progress_days": progress_days,
        "paper_validation_pass": progress_days >= target_days,
        "window_start": window_pass_dates[0] if window_pass_dates else None,
        "window_end": window_pass_dates[min(progress_days, len(window_pass_dates)) - 1]
        if window_pass_dates
        else None,
        "consecutive_failures": consecutive_failures,
        "resets": resets,
        "missing_remediations": [
            row
            for row in days
            if row.get("remediation_required") and not row.get("remediation_recorded")
        ],
        "days": days,
    }


def remediation_record_path(root: Path, day: str | date) -> Path:
    value = day.isoformat() if isinstance(day, date) else str(day)
    compact = value.replace("-", "")
    return root / "reports" / "paper" / "validation" / "remediations" / f"{compact}.md"


def check_previous_trading_day_remediation(
    *,
    root: Path,
    cycle_date: date,
) -> dict[str, Any]:
    previous = previous_trading_day(cycle_date)
    log_path = root / "reports" / "paper" / "daily_cycle" / f"{previous:%Y%m%d}.json"
    remediation_path = remediation_record_path(root, previous)
    if not log_path.exists():
        return {
            "status": "ok",
            "previous_trading_day": previous.isoformat(),
            "message": "previous trading day cycle log is absent",
            "log_path": str(log_path),
            "remediation_record_path": str(remediation_path),
        }
    try:
        log = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "status": "error",
            "previous_trading_day": previous.isoformat(),
            "message": "previous trading day cycle log is invalid JSON",
            "error": str(exc),
            "log_path": str(log_path),
            "remediation_record_path": str(remediation_path),
        }
    if log.get("status") == "skipped":
        return {
            "status": "ok",
            "previous_trading_day": previous.isoformat(),
            "message": "previous trading day log was skipped",
            "log_path": str(log_path),
            "remediation_record_path": str(remediation_path),
        }
    passed, reasons = validation_day_pass(log)
    if passed:
        return {
            "status": "ok",
            "previous_trading_day": previous.isoformat(),
            "message": "previous trading day passed validation",
            "log_path": str(log_path),
            "remediation_record_path": str(remediation_path),
        }
    if remediation_path.exists():
        return {
            "status": "ok",
            "previous_trading_day": previous.isoformat(),
            "message": "previous failed trading day has remediation record",
            "reasons": reasons,
            "log_path": str(log_path),
            "remediation_record_path": str(remediation_path),
        }
    return {
        "status": "error",
        "previous_trading_day": previous.isoformat(),
        "message": "previous failed trading day is missing remediation record",
        "reasons": reasons,
        "log_path": str(log_path),
        "remediation_record_path": str(remediation_path),
    }


def previous_trading_day(value: date) -> date:
    day = value - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def render_paper_validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Paper Validation Progress",
        "",
        f"- Progress: `{payload['progress_days']}/{payload['target_days']}`",
        f"- paper_validation_pass: `{payload['paper_validation_pass']}`",
        f"- Window: `{payload['window_start']}` -> `{payload['window_end']}`",
        "",
        "## Day Table",
        "",
        "| date | counted | passed | reasons |",
        "| --- | --- | --- | --- |",
    ]
    for row in payload["days"]:
        remediation = ""
        if row.get("remediation_required"):
            remediation = " remediation=" + (
                "recorded" if row.get("remediation_recorded") else "missing"
            )
        lines.append(
            f"| {row['date']} | {row['counted']} | {row['passed']} | "
            f"{', '.join(row['reasons']) or '-'}{remediation} |"
        )
    lines.extend(
        [
            "",
            "## Semantics",
            "",
            *[f"- {item}" for item in payload["semantics"]],
            "",
        ]
    )
    return "\n".join(lines)


def validation_day_pass(log: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if log.get("status") != "ok":
        reasons.append(f"cycle_status_{log.get('status')}")
    for step in log.get("steps", []):
        if step.get("exit_code") not in {0, None}:
            reasons.append(f"step_failed_{step.get('name')}")
    artifacts = log.get("artifact_paths") or {}
    if artifacts.get("state_drift_status") == "warning":
        reasons.append("state_drift_warning")
    if log.get("paper_order_authorization") not in {False, True}:
        reasons.append("paper_order_authorization_invalid")
    return not reasons, reasons


def _day_row(
    log: dict[str, Any],
    *,
    counted: bool,
    passed: bool | None,
    reasons: list[str],
) -> dict[str, Any]:
    return {
        "date": log.get("date"),
        "counted": counted,
        "passed": passed,
        "reasons": reasons,
        "log_path": log.get("_path"),
    }


def _load_cycle_logs(root: Path) -> list[dict[str, Any]]:
    log_dir = root / "reports" / "paper" / "daily_cycle"
    rows = []
    for path in sorted(log_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        payload["_path"] = str(path)
        rows.append(payload)
    return rows
