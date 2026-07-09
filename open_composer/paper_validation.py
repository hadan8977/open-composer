from __future__ import annotations

import json
from datetime import UTC, datetime
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
    evaluated = evaluate_validation_days(logs, target_days=target_days)
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
) -> dict[str, Any]:
    days = []
    window_pass_dates: list[str] = []
    consecutive_failures = 0
    resets = []
    for log in sorted(logs, key=lambda item: str(item.get("date", ""))):
        if log.get("status") == "skipped":
            days.append(_day_row(log, counted=False, passed=None, reasons=["skipped"]))
            continue
        passed, reasons = _day_pass(log)
        days.append(_day_row(log, counted=True, passed=passed, reasons=reasons))
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
        "days": days,
    }


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
        lines.append(
            f"| {row['date']} | {row['counted']} | {row['passed']} | "
            f"{', '.join(row['reasons']) or '-'} |"
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


def _day_pass(log: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if log.get("status") != "ok":
        reasons.append(f"cycle_status_{log.get('status')}")
    for step in log.get("steps", []):
        if step.get("exit_code") not in {0, None}:
            reasons.append(f"step_failed_{step.get('name')}")
    artifacts = log.get("artifact_paths") or {}
    if artifacts.get("state_drift_status") == "warning":
        reasons.append("state_drift_warning")
    if log.get("paper_order_authorization") is not False:
        reasons.append("paper_order_authorization_unexpected")
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
