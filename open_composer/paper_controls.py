from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.models.paper import (
    PaperAccountSnapshot,
    PaperAlert,
    PaperAlertReport,
    PaperKillSwitch,
    PaperMonitorReport,
    PaperPositionRecord,
    PaperReconciliationIssue,
    PaperReconciliationReport,
    PaperStatusSnapshot,
)
from open_composer.notifications import safe_dispatch_notification
from open_composer.paper_lock import paper_control_lock
from open_composer.storage import append_jsonl, write_json
from open_composer.strategy_lifecycle import list_strategies

OPEN_ORDER_STATUSES = {
    "accepted",
    "new",
    "partially_filled",
    "pending_cancel",
    "pending_new",
    "submitted",
}
PAPER_SNAPSHOT_STALE_SECONDS = 15 * 60
KILL_SWITCH_CONTROL_VERSION = 2


def load_paper_kill_switch(
    root: Path | None = None,
    *,
    require_control_file: bool = False,
) -> PaperKillSwitch:
    base = root or project_root()
    path = _kill_switch_path(base)
    try:
        payload = _read_unaliased_json(path, base)
    except FileNotFoundError:
        if require_control_file:
            raise
        return PaperKillSwitch()
    history = _read_kill_switch_history(base)
    if not history:
        raise ValueError("paper kill-switch immutable history is missing")
    state = _validate_kill_switch_payload(payload)
    if state.model_dump(mode="json") != history[-1].model_dump(mode="json"):
        raise ValueError("paper kill-switch pointer is not the latest immutable event")
    return state


def set_paper_kill_switch(
    root: Path | None = None,
    *,
    enabled: bool,
    reason: str = "",
    updated_by: str = "system",
) -> PaperKillSwitch:
    base = root or project_root()
    with paper_control_lock(base):
        history = _read_kill_switch_history(base)
        previous = history[-1] if history else None
        sequence = previous.sequence + 1 if previous is not None else 1
        previous_hash = (
            _canonical_hash(previous.model_dump(mode="json")) if previous is not None else None
        )
        updated_at = datetime.now(UTC).isoformat()
        body = {
            "control_version": KILL_SWITCH_CONTROL_VERSION,
            "sequence": sequence,
            "previous_event_hash": previous_hash,
            "enabled": enabled,
            "reason": reason.strip(),
            "updated_by": updated_by,
            "updated_at": updated_at,
        }
        state = PaperKillSwitch(**body)
        canonical_body = state.model_dump(mode="json")
        canonical_body.pop("event_id")
        state = state.model_copy(
            update={"event_id": "kill_" + _canonical_hash(canonical_body)[:16]}
        )
        path = _kill_switch_path(base)
        ensure_dir(path.parent)
        _write_immutable_kill_switch_event(base, state)
        _atomic_write_control(path, state.model_dump(mode="json"))
        append_jsonl(base / "reports" / "paper" / "kill_switch_events.jsonl", [state])
    safe_dispatch_notification(
        kind="kill_switch",
        severity="red",
        title=f"Paper kill switch {'enabled' if enabled else 'cleared'}",
        body=state.reason or "No reason supplied.",
        metadata={"enabled": enabled, "updated_by": updated_by},
        root=base,
    )
    return state


def _kill_switch_history_dir(root: Path) -> Path:
    return root / "reports" / "paper" / "control_history" / "kill_switch"


def _read_kill_switch_history(root: Path) -> list[PaperKillSwitch]:
    directory = _kill_switch_history_dir(root)
    if not directory.exists():
        return []
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("paper kill-switch history directory is invalid")
    states: list[PaperKillSwitch] = []
    for path in sorted(directory.glob("*.json")):
        payload = _read_unaliased_json(path, root)
        state = _validate_kill_switch_payload(payload)
        if path.name != f"{state.event_id}.json":
            raise ValueError("paper kill-switch history path does not match its event id")
        states.append(state)
    states.sort(key=lambda item: item.sequence)
    if [item.sequence for item in states] != list(range(1, len(states) + 1)):
        raise ValueError("paper kill-switch history sequence is not contiguous")
    previous: PaperKillSwitch | None = None
    for state in states:
        expected_hash = (
            _canonical_hash(previous.model_dump(mode="json")) if previous is not None else None
        )
        if state.previous_event_hash != expected_hash:
            raise ValueError("paper kill-switch history previous hash mismatch")
        previous = state
    return states


def _validate_kill_switch_payload(payload: object) -> PaperKillSwitch:
    if not isinstance(payload, dict):
        raise ValueError("paper kill-switch control must be a JSON object")
    required = set(PaperKillSwitch.model_fields)
    if set(payload) != required:
        raise ValueError("paper kill-switch control fields are incomplete")
    state = PaperKillSwitch.model_validate(payload)
    if state.control_version != KILL_SWITCH_CONTROL_VERSION or state.sequence < 1:
        raise ValueError("paper kill-switch control version or sequence is invalid")
    body = state.model_dump(mode="json")
    event_id = body.pop("event_id")
    if event_id != "kill_" + _canonical_hash(body)[:16]:
        raise ValueError("paper kill-switch event id is invalid")
    if state.sequence == 1 and state.previous_event_hash is not None:
        raise ValueError("paper kill-switch initial event has an invalid predecessor")
    if state.sequence > 1 and not _is_sha256(state.previous_event_hash):
        raise ValueError("paper kill-switch predecessor hash is invalid")
    return state


def _write_immutable_kill_switch_event(root: Path, state: PaperKillSwitch) -> Path:
    directory = _kill_switch_history_dir(root)
    ensure_dir(directory)
    if directory.is_symlink():
        raise ValueError("paper kill-switch history directory cannot be a symlink")
    path = directory / f"{state.event_id}.json"
    encoded = _encoded_json(state.model_dump(mode="json"))
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
    except FileExistsError:
        existing = _read_unaliased_json(path, root)
        if existing != state.model_dump(mode="json"):
            raise ValueError("paper kill-switch immutable event already differs") from None
        return path
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
    except Exception:
        path.unlink(missing_ok=True)
        raise
    _fsync_directory(directory)
    return path


def _atomic_write_control(path: Path, payload: dict[str, object]) -> None:
    ensure_dir(path.parent)
    encoded = _encoded_json(payload)
    with tempfile.NamedTemporaryFile(
        mode="wb",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.chmod(temporary, 0o400)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _read_unaliased_json(path: Path, root: Path) -> dict[str, object]:
    _require_unaliased_path(path, root)
    flags = os.O_RDONLY | os.O_NOFOLLOW
    fd = os.open(path, flags)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError("paper control artifact must be an unaliased regular file")
        with os.fdopen(fd, "r", encoding="utf-8") as handle:
            fd = -1
            payload = json.load(handle)
    finally:
        if fd >= 0:
            os.close(fd)
    if not isinstance(payload, dict):
        raise ValueError("paper control artifact must be a JSON object")
    return payload


def _require_unaliased_path(path: Path, root: Path) -> None:
    absolute_root = root.absolute()
    absolute_path = path.absolute()
    try:
        relative = absolute_path.relative_to(absolute_root)
    except ValueError as exc:
        raise ValueError("paper control artifact escapes the project root") from exc
    current = absolute_root
    if current.is_symlink():
        raise ValueError("project root cannot be a symlink for paper controls")
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("paper control artifact path cannot contain symlinks")


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _is_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _encoded_json(payload: object) -> bytes:
    return (json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8")


def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def enable_paper_kill_switch(
    root: Path | None = None,
    *,
    reason: str,
    updated_by: str = "system",
) -> PaperKillSwitch:
    return set_paper_kill_switch(
        root,
        enabled=True,
        reason=reason,
        updated_by=updated_by,
    )


def clear_paper_kill_switch(
    root: Path | None = None,
    *,
    reason: str = "",
    updated_by: str = "system",
) -> PaperKillSwitch:
    return set_paper_kill_switch(
        root,
        enabled=False,
        reason=reason,
        updated_by=updated_by,
    )


def paper_orders_blocked(root: Path | None = None) -> bool:
    try:
        return load_paper_kill_switch(root, require_control_file=True).enabled
    except (OSError, ValueError):
        return True


def build_paper_status(
    root: Path | None = None,
    *,
    active_paper_auto_strategies: list[str] | None = None,
) -> PaperStatusSnapshot:
    base = root or project_root()
    kill_switch = load_paper_kill_switch(base)
    if active_paper_auto_strategies is None:
        active_paper_auto = [
            item.name
            for item in list_strategies(base)
            if item.lifecycle == "active"
            and item.execution_mode == "paper_auto"
            and item.broker == "alpaca_paper"
        ]
    else:
        active_paper_auto = list(active_paper_auto_strategies)
    order_rows = _paper_order_rows(base)
    status_counts = Counter(
        _order_status_token(row.get("status")) or "unknown" for row in order_rows
    )
    open_order_count = sum(
        count for status, count in status_counts.items() if status.lower() in OPEN_ORDER_STATUSES
    )
    timestamps = [
        _parse_datetime(str(row["submitted_at"])) for row in order_rows if row.get("submitted_at")
    ]
    account = _paper_account(base)
    positions = _paper_positions(base)
    positions_snapshot_at = max((item.updated_at for item in positions), default=None)
    reconciliation = _paper_reconciliation(base)
    alerts = _paper_alert_report(base)
    notes = ["Paper status is rebuilt from local strategy specs and paper order artifacts."]
    if kill_switch.enabled:
        notes.append("Paper kill switch is enabled; automated paper submissions are blocked.")
    if not active_paper_auto:
        notes.append("No active paper_auto strategies were found.")
    if account is None:
        notes.append("No paper account snapshot was found under reports/paper/account.json.")
    return PaperStatusSnapshot(
        kill_switch=kill_switch,
        active_paper_auto_strategies=sorted(active_paper_auto),
        order_status_counts=dict(sorted(status_counts.items())),
        open_order_count=open_order_count,
        account_equity=account.equity if account else None,
        account_cash=account.cash if account else None,
        account_buying_power=account.buying_power if account else None,
        account_portfolio_value=account.portfolio_value if account else None,
        account_snapshot_at=account.generated_at if account else None,
        position_count=len(positions),
        total_position_market_value=sum(item.market_value or 0.0 for item in positions),
        total_unrealized_pl=sum(item.unrealized_pl or 0.0 for item in positions),
        positions_snapshot_at=positions_snapshot_at,
        reconciliation_status=reconciliation.status if reconciliation else "unknown",
        reconciliation_issue_count=reconciliation.issue_count if reconciliation else 0,
        reconciliation_report_path=reconciliation.report_markdown_path if reconciliation else None,
        alert_status=alerts.status if alerts else "unknown",
        alert_count=alerts.alert_count if alerts else 0,
        alert_report_path=alerts.report_markdown_path if alerts else None,
        last_order_at=max(timestamps) if timestamps else None,
        notes=notes,
    )


def write_paper_status(
    root: Path | None = None,
    output_path: Path | None = None,
) -> Path:
    base = root or project_root()
    path = output_path or (base / "reports" / "paper" / "status.json")
    ensure_dir(path.parent)
    write_json(path, build_paper_status(base))
    return path


def reconcile_paper_state(root: Path | None = None) -> PaperReconciliationReport:
    base = root or project_root()
    orders = _paper_order_rows(base)
    positions = _paper_positions(base)
    account = _paper_account(base)
    position_symbols = {item.symbol.upper() for item in positions if item.qty != 0}
    order_symbols = {str(row.get("symbol", "")).upper() for row in orders if row.get("symbol")}
    issues: list[PaperReconciliationIssue] = []
    if account is None:
        issues.append(
            PaperReconciliationIssue(
                severity="warning",
                code="missing_account_snapshot",
                message="reports/paper/account.json is missing; run oc paper sync-account.",
            )
        )
    if not positions and order_symbols:
        issues.append(
            PaperReconciliationIssue(
                severity="warning",
                code="missing_positions_snapshot",
                message="No positions snapshot found while local paper orders exist.",
            )
        )
    for symbol in sorted(position_symbols - order_symbols):
        issues.append(
            PaperReconciliationIssue(
                severity="warning",
                code="position_without_local_order",
                symbol=symbol,
                message=f"Position {symbol} has no matching local paper order record.",
            )
        )
    for row in orders:
        status = _order_status_token(row.get("status"))
        symbol = str(row.get("symbol", "")).upper() or None
        side = str(row.get("side", "")).lower()
        if status in OPEN_ORDER_STATUSES:
            issues.append(
                PaperReconciliationIssue(
                    severity="info",
                    code="open_order",
                    symbol=symbol,
                    message=f"Order {row.get('id', '')} is still open with status={status}.",
                )
            )
        if status == "filled" and side == "buy" and symbol and symbol not in position_symbols:
            issues.append(
                PaperReconciliationIssue(
                    severity="warning",
                    code="filled_buy_without_position",
                    symbol=symbol,
                    message=f"Filled buy order for {symbol} has no matching position snapshot.",
                )
            )
    severity_order = {"info": 1, "warning": 2, "error": 3}
    max_severity = max((severity_order[item.severity] for item in issues), default=0)
    status = "error" if max_severity >= 3 else "warning" if max_severity >= 2 else "ok"
    report = PaperReconciliationReport(
        status=status,
        order_count=len(orders),
        position_count=len(positions),
        open_order_count=sum(
            1 for row in orders if _order_status_token(row.get("status")) in OPEN_ORDER_STATUSES
        ),
        filled_order_count=sum(
            1 for row in orders if _order_status_token(row.get("status")) == "filled"
        ),
        issue_count=len(issues),
        issues=issues,
    )
    json_path = base / "reports" / "paper" / "reconciliation.json"
    md_path = base / "reports" / "paper" / "reconciliation.md"
    report.report_json_path = _relpath(json_path, base)
    report.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, report)
    _write_reconciliation_markdown(md_path, report)
    return report


def build_paper_alerts(root: Path | None = None) -> PaperAlertReport:
    base = root or project_root()
    status = build_paper_status(base)
    alerts: list[PaperAlert] = []
    if status.kill_switch.enabled:
        alerts.append(
            PaperAlert(
                severity="warning",
                code="paper_kill_switch_enabled",
                message="Paper kill switch is enabled; automated submissions are blocked.",
                source_path=_relpath(base / "reports" / "paper" / "kill_switch.json", base),
            )
        )
    if status.reconciliation_status in {"warning", "error"}:
        alerts.append(
            PaperAlert(
                severity=status.reconciliation_status,  # type: ignore[arg-type]
                code="paper_reconciliation_issues",
                message=f"Paper reconciliation has {status.reconciliation_issue_count} issue(s).",
                source_path=status.reconciliation_report_path,
            )
        )
    if status.open_order_count:
        alerts.append(
            PaperAlert(
                severity="info",
                code="paper_open_orders",
                message=f"{status.open_order_count} paper order(s) are still open.",
                source_path=_relpath(base / "reports" / "paper", base),
            )
        )
    if status.account_equity is None:
        alerts.append(
            PaperAlert(
                severity="warning",
                code="missing_paper_account_snapshot",
                message="No paper account snapshot is available; run oc paper sync-account.",
                source_path=_relpath(base / "reports" / "paper" / "account.json", base),
            )
        )
    elif _is_stale(status.account_snapshot_at):
        alerts.append(
            PaperAlert(
                severity="warning",
                code="stale_paper_account_snapshot",
                message=(
                    "Paper account snapshot is stale; run oc paper sync-account before "
                    "making paper execution decisions."
                ),
                source_path=_relpath(base / "reports" / "paper" / "account.json", base),
            )
        )
    if status.position_count and _is_stale(status.positions_snapshot_at):
        alerts.append(
            PaperAlert(
                severity="warning",
                code="stale_paper_positions_snapshot",
                message=(
                    "Paper positions snapshot is stale; run oc paper sync-account before "
                    "reviewing position risk."
                ),
                source_path=_relpath(base / "reports" / "paper" / "positions.json", base),
            )
        )
    if status.total_unrealized_pl < 0:
        alerts.append(
            PaperAlert(
                severity="warning",
                code="paper_unrealized_loss",
                message=f"Paper positions show unrealized PnL {status.total_unrealized_pl:.2f}.",
                source_path=_relpath(base / "reports" / "paper" / "positions.json", base),
            )
        )
    report = PaperAlertReport(
        status=_alert_status(alerts),
        alert_count=len(alerts),
        alerts=alerts,
    )
    json_path = base / "reports" / "paper" / "alerts.json"
    md_path = base / "reports" / "paper" / "alerts.md"
    report.report_json_path = _relpath(json_path, base)
    report.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, report)
    _write_alerts_markdown(md_path, report)
    return report


def refresh_paper_monitor(
    root: Path | None = None,
    *,
    sync_broker: bool = False,
) -> PaperMonitorReport:
    base = root or project_root()
    sync_status = "skipped"
    sync_error = ""
    sync_output_paths: list[str] = []
    if sync_broker:
        try:
            sync_output_paths = _sync_broker_snapshots(base)
        except Exception as exc:
            sync_status = "error"
            sync_error = str(exc)
        else:
            sync_status = "ok"

    reconciliation = reconcile_paper_state(base)
    alerts = build_paper_alerts(base)
    status_path = write_paper_status(base)
    status = "error" if sync_status == "error" else _monitor_status(alerts.status)
    report = PaperMonitorReport(
        status=status,
        sync_broker=sync_broker,
        sync_status=sync_status,
        sync_error=sync_error,
        sync_output_paths=sync_output_paths,
        reconciliation_status=reconciliation.status,
        reconciliation_issue_count=reconciliation.issue_count,
        alert_status=alerts.status,
        alert_count=alerts.alert_count,
        status_path=_relpath(status_path, base),
        reconciliation_report_path=reconciliation.report_markdown_path,
        alert_report_path=alerts.report_markdown_path,
    )
    json_path = base / "reports" / "paper" / "monitor.json"
    md_path = base / "reports" / "paper" / "monitor.md"
    report.report_json_path = _relpath(json_path, base)
    report.report_markdown_path = _relpath(md_path, base)
    write_json(json_path, report)
    _write_monitor_markdown(md_path, report)
    return report


def run_paper_monitor_loop(
    root: Path | None = None,
    *,
    interval_seconds: float = 60.0,
    max_cycles: int = 1,
    sync_broker: bool = False,
) -> list[PaperMonitorReport]:
    base = root or project_root()
    reports: list[PaperMonitorReport] = []
    index = 0
    while max_cycles == 0 or index < max_cycles:
        report = refresh_paper_monitor(base, sync_broker=sync_broker)
        reports.append(report)
        append_jsonl(base / "reports" / "paper" / "monitor_cycles.jsonl", [report])
        index += 1
        if max_cycles != 0 and index >= max_cycles:
            break
        time.sleep(interval_seconds)
    return reports


def paper_open_order_rows(root: Path | None = None) -> list[dict[str, object]] | None:
    return _broker_open_order_rows(root or project_root())


def _paper_order_rows(root: Path) -> list[dict[str, object]]:
    broker_rows = _broker_open_order_rows(root)
    if broker_rows is not None:
        return broker_rows
    rows_by_key: dict[str, dict[str, object]] = {}
    paper_root = root / "reports" / "paper"
    for path in sorted(paper_root.glob("*.jsonl")):
        if path.name == "kill_switch_events.jsonl":
            continue
        with path.open("r", encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                if not line.strip():
                    continue
                raw = json.loads(line)
                if isinstance(raw, dict) and "status" in raw:
                    key = str(raw.get("client_order_id") or raw.get("id") or f"{path.name}:{index}")
                    rows_by_key[key] = raw
    return list(rows_by_key.values())


def _broker_open_order_rows(root: Path) -> list[dict[str, object]] | None:
    path = root / "reports" / "paper" / "open_orders.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(raw, dict):
        return None
    generated_at = raw.get("generated_at")
    if generated_at:
        try:
            _parse_datetime(str(generated_at))
        except ValueError:
            return None
    rows = raw.get("orders", [])
    if not isinstance(rows, list):
        return None
    return [row for row in rows if isinstance(row, dict) and "status" in row]


def _order_status_token(value: object) -> str:
    return str(value or "").lower().split(".")[-1]


def _paper_account(root: Path) -> PaperAccountSnapshot | None:
    path = root / "reports" / "paper" / "account.json"
    if not path.exists():
        return None
    return PaperAccountSnapshot.model_validate_json(path.read_text(encoding="utf-8"))


def _paper_positions(root: Path) -> list[PaperPositionRecord]:
    path = root / "reports" / "paper" / "positions.json"
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    rows = raw.get("positions", []) if isinstance(raw, dict) else []
    return [PaperPositionRecord.model_validate(row) for row in rows]


def _paper_reconciliation(root: Path) -> PaperReconciliationReport | None:
    path = root / "reports" / "paper" / "reconciliation.json"
    if not path.exists():
        return None
    return PaperReconciliationReport.model_validate_json(path.read_text(encoding="utf-8"))


def _paper_alert_report(root: Path) -> PaperAlertReport | None:
    path = root / "reports" / "paper" / "alerts.json"
    if not path.exists():
        return None
    return PaperAlertReport.model_validate_json(path.read_text(encoding="utf-8"))


def _alert_status(alerts: list[PaperAlert]) -> str:
    if any(item.severity == "error" for item in alerts):
        return "error"
    if any(item.severity == "warning" for item in alerts):
        return "warning"
    return "ok"


def _monitor_status(alert_status: str) -> str:
    if alert_status == "error":
        return "error"
    if alert_status == "warning":
        return "warning"
    return "ok"


def _sync_broker_snapshots(base: Path) -> list[str]:
    from open_composer.adapters.broker.alpaca_paper import (
        sync_paper_account,
        sync_paper_orders,
    )

    order_path = sync_paper_orders(base)
    account_path, positions_path = sync_paper_account(base)
    return [
        _relpath(order_path, base),
        _relpath(account_path, base),
        _relpath(positions_path, base),
    ]


def _is_stale(timestamp: datetime | None) -> bool:
    if timestamp is None:
        return False
    normalized = timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=UTC)
    return (datetime.now(UTC) - normalized).total_seconds() > PAPER_SNAPSHOT_STALE_SECONDS


def _relpath(path: Path, base: Path) -> str:
    try:
        return path.relative_to(base).as_posix()
    except ValueError:
        return path.as_posix()


def _write_reconciliation_markdown(path: Path, report: PaperReconciliationReport) -> Path:
    ensure_dir(path.parent)
    lines = [
        "# Paper Reconciliation",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Status: `{report.status}`",
        f"- Orders: `{report.order_count}`",
        f"- Positions: `{report.position_count}`",
        f"- Open orders: `{report.open_order_count}`",
        f"- Filled orders: `{report.filled_order_count}`",
        f"- Issues: `{report.issue_count}`",
        "",
        "## Issues",
        "",
    ]
    if report.issues:
        lines.extend(
            (
                f"- `{item.severity}` `{item.code}`"
                + (f" `{item.symbol}`" if item.symbol else "")
                + f": {item.message}"
            )
            for item in report.issues
        )
    else:
        lines.append("- No reconciliation issues found.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_alerts_markdown(path: Path, report: PaperAlertReport) -> Path:
    ensure_dir(path.parent)
    lines = [
        "# Paper Alerts",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Status: `{report.status}`",
        f"- Alerts: `{report.alert_count}`",
        "",
        "## Alerts",
        "",
    ]
    if report.alerts:
        lines.extend(
            (
                f"- `{item.severity}` `{item.code}`: {item.message}"
                + (f" Source: `{item.source_path}`" if item.source_path else "")
            )
            for item in report.alerts
        )
    else:
        lines.append("- No paper alerts.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_monitor_markdown(path: Path, report: PaperMonitorReport) -> Path:
    ensure_dir(path.parent)
    lines = [
        "# Paper Monitor Refresh",
        "",
        f"- Generated at: `{report.generated_at.isoformat()}`",
        f"- Status: `{report.status}`",
        f"- Broker sync: `{report.sync_status}` requested=`{report.sync_broker}`",
        f"- Broker sync outputs: `{', '.join(report.sync_output_paths) or 'n/a'}`",
        f"- Broker sync error: `{report.sync_error or 'n/a'}`",
        f"- Reconciliation: `{report.reconciliation_status}` "
        f"issues=`{report.reconciliation_issue_count}`",
        f"- Alerts: `{report.alert_status}` alerts=`{report.alert_count}`",
        f"- Status snapshot: `{report.status_path}`",
        f"- Reconciliation report: `{report.reconciliation_report_path or 'n/a'}`",
        f"- Alert report: `{report.alert_report_path or 'n/a'}`",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _kill_switch_path(root: Path) -> Path:
    return root / "reports" / "paper" / "kill_switch.json"


def _parse_datetime(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed
