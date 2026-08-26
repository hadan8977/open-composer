from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.market_calendar import NEW_YORK, us_equity_session_close
from open_composer.storage import write_json

TARGET_VALID_DAYS = 20


def build_paper_validation_report(
    *,
    root: Path | None = None,
    target_days: int = TARGET_VALID_DAYS,
    strategy_name: str | None = None,
    spec_hash: str | None = None,
    execution_policy_id: str | None = None,
    execution_policy_hash: str | None = None,
    not_before: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    base = root or project_root()
    evidence_cutoff = _as_utc(as_of or datetime.now(UTC))
    logs = _load_cycle_logs(base, strategy_name=strategy_name)
    logs, excluded_logs = _filter_bound_logs(
        logs,
        spec_hash=spec_hash,
        execution_policy_id=execution_policy_id,
        execution_policy_hash=execution_policy_hash,
        not_before=not_before,
    )
    observation_evaluated = evaluate_validation_days(
        logs,
        target_days=target_days,
        root=base,
        as_of=evidence_cutoff,
        require_order_authorized=False,
    )
    evaluated = evaluate_validation_days(
        logs,
        target_days=target_days,
        root=base,
        as_of=evidence_cutoff,
        require_order_authorized=True,
    )
    return {
        "report_type": "paper_validation_progress",
        "generated_at": datetime.now(UTC).isoformat(),
        "evidence_cutoff": evidence_cutoff.isoformat(),
        "strategy_name": strategy_name,
        "binding": {
            "spec_hash": spec_hash,
            "execution_policy_id": execution_policy_id,
            "execution_policy_hash": execution_policy_hash,
            "not_before": not_before,
        },
        "excluded_logs": excluded_logs,
        "target_days": target_days,
        "forward_observation_progress_days": observation_evaluated["progress_days"],
        "forward_observation_pass": observation_evaluated["paper_validation_pass"],
        "progress_days": evaluated["progress_days"],
        "paper_validation_pass": evaluated["paper_validation_pass"],
        "window_start": evaluated["window_start"],
        "window_end": evaluated["window_end"],
        "consecutive_failures": evaluated["consecutive_failures"],
        "resets": evaluated["resets"],
        "missing_remediations": evaluated["missing_remediations"],
        "days": evaluated["days"],
        "forward_observation_days": observation_evaluated["days"],
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
            (
                "Production reports count only non-future cycle receipts with hash-bound "
                "evidence artifacts."
            ),
            (
                "Broker-free receipts may count toward forward_observation_pass but never "
                "paper_validation_pass."
            ),
            (
                "Broker-free forward observation records account state drift as evidence, "
                "but a drift warning blocks only order-authorized paper validation."
            ),
            (
                "paper_validation_pass requires a bounded canary or full order authorization "
                "plus broker, account, position, readiness, and monitor evidence."
            ),
            (
                "Local hashes provide integrity and epoch binding, not independent external "
                "attestation."
            ),
        ],
    }


def write_paper_validation_report(
    *,
    root: Path | None = None,
    target_days: int = TARGET_VALID_DAYS,
    strategy_name: str | None = None,
    spec_hash: str | None = None,
    execution_policy_id: str | None = None,
    execution_policy_hash: str | None = None,
    not_before: str | None = None,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    base = root or project_root()
    payload = build_paper_validation_report(
        root=base,
        target_days=target_days,
        strategy_name=strategy_name,
        spec_hash=spec_hash,
        execution_policy_id=execution_policy_id,
        execution_policy_hash=execution_policy_hash,
        not_before=not_before,
        as_of=as_of,
    )
    out_dir = ensure_dir(base / "reports" / "paper" / "validation")
    stem = (
        f"{strategy_name}-paper-validation-progress"
        if strategy_name
        else "paper-validation-progress"
    )
    progress_json = out_dir / f"{stem}.json"
    progress_md = out_dir / f"{stem}.md"
    payload["artifact_paths"] = {
        "json": str(progress_json),
        "markdown": str(progress_md),
    }
    write_json(progress_json, payload)
    progress_md.write_text(render_paper_validation_markdown(payload), encoding="utf-8")
    if payload["paper_validation_pass"]:
        prefix = f"{strategy_name}-" if strategy_name else ""
        final_stem = out_dir / f"{prefix}paper-validation-report-{payload['window_end']}"
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
    as_of: datetime | None = None,
    require_order_authorized: bool = False,
) -> dict[str, Any]:
    evidence_cutoff = _as_utc(as_of or datetime.now(UTC))
    days = []
    window_pass_dates: list[str] = []
    consecutive_failures = 0
    resets = []
    seen_dates: set[str] = set()
    for log in sorted(logs, key=lambda item: str(item.get("date", ""))):
        day_value = str(log.get("date", ""))
        try:
            parsed_day = date.fromisoformat(day_value)
        except ValueError:
            parsed_day = None
        if parsed_day is None or us_equity_session_close(parsed_day) is None:
            days.append(
                _day_row(
                    log,
                    counted=False,
                    passed=None,
                    reasons=["invalid_or_non_trading_day"],
                )
            )
            continue
        if parsed_day > evidence_cutoff.date():
            days.append(
                _day_row(
                    log,
                    counted=False,
                    passed=False,
                    reasons=["future_cycle_date"],
                )
            )
            continue
        if day_value in seen_dates:
            passed = False
            reasons = ["duplicate_cycle_log_date"]
            row = _day_row(log, counted=False, passed=passed, reasons=reasons)
            days.append(row)
            consecutive_failures += 1
            if consecutive_failures >= 2:
                resets.append({"date": day_value, "reason": "two_consecutive_failed_trading_days"})
                window_pass_dates = []
                consecutive_failures = 0
            continue
        seen_dates.add(day_value)
        if log.get("status") == "skipped":
            days.append(_day_row(log, counted=False, passed=None, reasons=["skipped"]))
            continue
        passed, reasons = validation_day_pass(
            log,
            root=root,
            as_of=evidence_cutoff,
            require_order_authorized=require_order_authorized,
        )
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
    strategy_name: str | None = None,
) -> dict[str, Any]:
    previous = previous_trading_day(cycle_date)
    stem = f"{strategy_name}-{previous:%Y%m%d}" if strategy_name else f"{previous:%Y%m%d}"
    log_path = root / "reports" / "paper" / "daily_cycle" / f"{stem}.json"
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
    passed, reasons = validation_day_pass(log, root=root, as_of=datetime.now(UTC))
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
    while us_equity_session_close(day) is None:
        day -= timedelta(days=1)
    return day


def render_paper_validation_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Paper Validation Progress",
        "",
        (
            "- Forward observation: "
            f"`{payload['forward_observation_progress_days']}/{payload['target_days']}`"
        ),
        f"- forward_observation_pass: `{payload['forward_observation_pass']}`",
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


def validation_day_pass(
    log: dict[str, Any],
    *,
    root: Path | None = None,
    as_of: datetime | None = None,
    require_order_authorized: bool = False,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    evidence_cutoff = _as_utc(as_of or datetime.now(UTC))
    if log.get("report_type") != "daily_paper_cycle":
        reasons.append("report_type_invalid")
    if log.get("status") != "ok":
        reasons.append(f"cycle_status_{log.get('status')}")
    started_at = _parse_utc_timestamp(log.get("started_at"))
    ended_at = _parse_utc_timestamp(log.get("ended_at"))
    if started_at is None or ended_at is None:
        reasons.append("cycle_timestamps_invalid")
    else:
        if ended_at < started_at:
            reasons.append("cycle_timestamp_order_invalid")
        if ended_at > evidence_cutoff:
            reasons.append("cycle_evidence_from_future")
    day_value = str(log.get("date") or "")
    try:
        cycle_day = date.fromisoformat(day_value)
    except ValueError:
        cycle_day = None
    if cycle_day is None or cycle_day > evidence_cutoff.date():
        reasons.append("cycle_date_not_observable")
    elif started_at is not None and ended_at is not None:
        local_dates = {
            started_at.astimezone(NEW_YORK).date(),
            ended_at.astimezone(NEW_YORK).date(),
        }
        if cycle_day not in local_dates:
            reasons.append("cycle_timestamps_not_aligned_to_session")
        if ended_at - started_at > timedelta(hours=24):
            reasons.append("cycle_duration_exceeds_24h")
    step_names = [str(step.get("name") or "") for step in log.get("steps", [])]
    required_steps = {"readiness", "target_weights", "paper_cycle", "paper_monitor", "state_drift"}
    missing_steps = sorted(required_steps - set(step_names))
    if missing_steps:
        reasons.extend(f"required_step_missing_{name}" for name in missing_steps)
    for step in log.get("steps", []):
        if step.get("exit_code") not in {0, None}:
            reasons.append(f"step_failed_{step.get('name')}")
    artifacts = log.get("artifact_paths") or {}
    if require_order_authorized and artifacts.get("state_drift_status") == "warning":
        reasons.append("state_drift_warning")
    if log.get("paper_order_authorization") not in {False, True}:
        reasons.append("paper_order_authorization_invalid")
    elif require_order_authorized and log.get("paper_order_authorization") is not True:
        reasons.append("paper_order_authorization_required")
    if require_order_authorized and log.get("paper_authorization_substate") not in {
        "canary_authorized",
        "order_authorized",
    }:
        reasons.append("paper_authorization_substate_invalid")
    remediation = log.get("previous_day_remediation_check")
    if not isinstance(remediation, dict) or remediation.get("status") != "ok":
        reasons.append("previous_day_remediation_not_ok")
    if root is not None:
        reasons.extend(_cycle_binding_reasons(log))
        reasons.extend(
            _evidence_binding_reasons(
                log,
                root,
                require_order_authorized=require_order_authorized,
            )
        )
    return not reasons, reasons


def _cycle_binding_reasons(log: dict[str, Any]) -> list[str]:
    reasons = []
    if log.get("cycle_receipt_version") != 3:
        reasons.append("cycle_receipt_version_invalid")
    if not _is_sha256(log.get("spec_hash")):
        reasons.append("spec_hash_invalid")
    if log.get("active_spec_hash") != log.get("spec_hash"):
        reasons.append("active_spec_hash_mismatch")
    if not str(log.get("active_spec_path") or "").strip():
        reasons.append("active_spec_path_missing")
    if not str(log.get("execution_policy_id") or "").strip():
        reasons.append("execution_policy_id_missing")
    if not _is_sha256(log.get("execution_policy_hash")):
        reasons.append("execution_policy_hash_invalid")
    return reasons


def _evidence_binding_reasons(
    log: dict[str, Any],
    root: Path,
    *,
    require_order_authorized: bool,
) -> list[str]:
    bindings = log.get("evidence_bindings")
    if not isinstance(bindings, list):
        return ["evidence_bindings_missing"]
    reasons: list[str] = []
    seen_roles: set[str] = set()
    payloads: dict[str, dict[str, Any]] = {}
    base = root.resolve()
    for binding in bindings:
        if not isinstance(binding, dict):
            reasons.append("evidence_binding_invalid")
            continue
        role = str(binding.get("role") or "")
        path_value = str(binding.get("path") or "")
        expected_hash = binding.get("sha256")
        if not role or role in seen_roles:
            reasons.append("evidence_binding_role_invalid")
            continue
        seen_roles.add(role)
        path = Path(path_value)
        if not path.is_absolute():
            path = root / path
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(base)
        except (FileNotFoundError, ValueError):
            reasons.append(f"evidence_path_invalid_{role}")
            continue
        if not resolved.is_file() or not _is_sha256(expected_hash):
            reasons.append(f"evidence_binding_invalid_{role}")
            continue
        if hashlib.sha256(resolved.read_bytes()).hexdigest() != expected_hash:
            reasons.append(f"evidence_hash_mismatch_{role}")
        if binding.get("size_bytes") != resolved.stat().st_size:
            reasons.append(f"evidence_size_mismatch_{role}")
        if resolved.suffix == ".json":
            try:
                payload = json.loads(resolved.read_text(encoding="utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                reasons.append(f"evidence_json_invalid_{role}")
            else:
                if not isinstance(payload, dict):
                    reasons.append(f"evidence_json_invalid_{role}")
                else:
                    payloads[role] = payload
    required_roles = {"target_weights", "review_card", "state_drift"}
    if require_order_authorized:
        required_roles.update(
            {
                "paper_readiness",
                "broker_sync",
                "broker_sync_receipt",
                "paper_authorization",
                "account_snapshot",
                "positions_snapshot",
                "paper_monitor",
                "paper_cycle",
            }
        )
    for role in required_roles - seen_roles:
        reasons.append(f"evidence_binding_missing_{role}")
    reasons.extend(_evidence_semantic_reasons(log, payloads, require_order_authorized))
    return reasons


def _evidence_semantic_reasons(
    log: dict[str, Any],
    payloads: dict[str, dict[str, Any]],
    require_order_authorized: bool,
) -> list[str]:
    reasons: list[str] = []
    strategy = log.get("strategy")
    day = str(log.get("date") or "")
    target = payloads.get("target_weights")
    if target is None or target.get("strategy_name") != strategy:
        reasons.append("target_weights_strategy_mismatch")
    elif not isinstance(target.get("target_weights"), list):
        reasons.append("target_weights_rows_invalid")
    review = payloads.get("review_card")
    if review is None or review.get("strategy") != strategy or review.get("date") != day:
        reasons.append("review_card_identity_mismatch")
    drift = payloads.get("state_drift")
    drift_status = drift.get("status") if drift is not None else None
    if (
        drift is None
        or drift.get("report_type") != "paper_state_drift"
        or drift.get("date") != day
        or drift_status not in {"ok", "warning"}
        or (require_order_authorized and drift_status != "ok")
    ):
        reasons.append("state_drift_evidence_not_ok")
    if not require_order_authorized:
        return reasons
    readiness = payloads.get("paper_readiness")
    readiness_pair = (
        (readiness.get("status"), readiness.get("execution_substate"))
        if readiness is not None
        else (None, None)
    )
    expected_substate = log.get("paper_authorization_substate")
    expected_pair = (
        ("warning", "canary_authorized")
        if expected_substate == "canary_authorized"
        else ("ok", "order_authorized")
    )
    if (
        readiness is None
        or readiness.get("strategy_name") != strategy
        or readiness_pair != expected_pair
    ):
        reasons.append("paper_readiness_evidence_not_authorized")
    authorization = payloads.get("paper_authorization")
    authorization_kind = "canary" if expected_substate == "canary_authorized" else "full"
    if (
        authorization is None
        or authorization.get("strategy_name") != strategy
        or authorization.get("spec_hash") != log.get("spec_hash")
        or authorization.get("execution_policy_id") != log.get("execution_policy_id")
        or authorization.get("execution_policy_hash") != log.get("execution_policy_hash")
        or authorization.get("authorization_kind") != authorization_kind
        or authorization.get("execution_substate") != expected_substate
        or authorization.get("authorized") is not True
        or authorization.get("order_scope") != "alpaca_paper_only"
        or authorization.get("real_money_broker_writes") != "out_of_scope"
    ):
        reasons.append("paper_authorization_evidence_invalid")
    elif not _authorization_identity_valid(authorization):
        reasons.append("paper_authorization_identity_invalid")
    elif authorization_kind == "canary":
        authorized_at = _parse_utc_timestamp(authorization.get("authorized_at"))
        expires_at = _parse_utc_timestamp(authorization.get("expires_at"))
        cycle_started = _parse_utc_timestamp(log.get("started_at"))
        cycle_ended = _parse_utc_timestamp(log.get("ended_at"))
        if (
            authorized_at is None
            or expires_at is None
            or cycle_started is None
            or cycle_ended is None
            or authorized_at > cycle_started
            or expires_at < cycle_ended
        ):
            reasons.append("paper_canary_not_active_for_cycle")
    monitor = payloads.get("paper_monitor")
    if (
        monitor is None
        or monitor.get("sync_broker") is not True
        or monitor.get("sync_status") != "ok"
        or monitor.get("status") == "error"
    ):
        reasons.append("paper_monitor_evidence_not_synced")
    account = payloads.get("account_snapshot")
    if account is None or account.get("paper") is not True:
        reasons.append("paper_account_evidence_invalid")
    sync_receipt = payloads.get("broker_sync_receipt")
    if (
        sync_receipt is None
        or sync_receipt.get("receipt_version") != 1
        or sync_receipt.get("receipt_source") != "alpaca_paper_sync"
        or sync_receipt.get("paper") is not True
        or not sync_receipt.get("broker_account_id_hash")
        or account is None
        or sync_receipt.get("broker_account_id_hash") != account.get("broker_account_id_hash")
    ):
        reasons.append("broker_sync_receipt_evidence_invalid")
    if (
        authorization_kind == "canary"
        and authorization is not None
        and account is not None
        and authorization.get("broker_account_id_hash") != account.get("broker_account_id_hash")
    ):
        reasons.append("paper_canary_account_binding_mismatch")
    positions = payloads.get("positions_snapshot")
    if (
        positions is None
        or positions.get("paper") is not True
        or not isinstance(positions.get("positions"), list)
    ):
        reasons.append("paper_positions_evidence_invalid")
    paper_cycle = payloads.get("paper_cycle")
    if (
        paper_cycle is None
        or paper_cycle.get("strategy_name") != strategy
        or paper_cycle.get("spec_hash") != log.get("spec_hash")
        or not isinstance(paper_cycle.get("signals"), list)
    ):
        reasons.append("paper_cycle_evidence_invalid")
    elif any(
        isinstance(signal, dict) and signal.get("decision") == "order_error"
        for signal in paper_cycle["signals"]
    ):
        reasons.append("paper_cycle_order_error")
    return reasons


def _parse_utc_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(UTC)


def _authorization_identity_valid(payload: dict[str, Any]) -> bool:
    authorization_id = payload.get("authorization_id")
    body = {key: value for key, value in payload.items() if key != "authorization_id"}
    encoded = json.dumps(body, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    expected = "auth_" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:16]
    return authorization_id == expected


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("paper validation as_of must include timezone")
    return value.astimezone(UTC)


def _is_sha256(value: Any) -> bool:
    text = str(value or "")
    return len(text) == 64 and all(character in "0123456789abcdef" for character in text)


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


def _load_cycle_logs(root: Path, *, strategy_name: str | None = None) -> list[dict[str, Any]]:
    log_dir = root / "reports" / "paper" / "daily_cycle"
    rows = []
    for path in sorted(log_dir.glob("*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if strategy_name is not None and payload.get("strategy") != strategy_name:
            continue
        payload["_path"] = str(path)
        rows.append(payload)
    return rows


def _filter_bound_logs(
    logs: list[dict[str, Any]],
    *,
    spec_hash: str | None,
    execution_policy_id: str | None,
    execution_policy_hash: str | None,
    not_before: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    included: list[dict[str, Any]] = []
    excluded: list[dict[str, str]] = []
    for log in logs:
        reasons = []
        day = str(log.get("date", ""))
        if not_before is not None and day < not_before:
            reasons.append("before_validation_epoch")
        for key, expected in (
            ("spec_hash", spec_hash),
            ("execution_policy_id", execution_policy_id),
            ("execution_policy_hash", execution_policy_hash),
        ):
            if expected is not None and log.get(key) != expected:
                reasons.append(f"{key}_mismatch")
        if reasons:
            excluded.append(
                {
                    "date": day,
                    "log_path": str(log.get("_path") or ""),
                    "reasons": ",".join(reasons),
                }
            )
        else:
            included.append(log)
    return included, excluded
