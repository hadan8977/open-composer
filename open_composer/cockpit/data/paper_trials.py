"""Read operator-published validation books without importing the trading runner.

``config/paper-validation-dashboard.json`` lists display identities, not trading
authorizations. Each optional snapshot is published by the existing paper owner
after an operating event. Missing snapshots are not-started, never zero-profit
running books. Running status needs bound decision/checkpoint/reconciliation
evidence; financial figures additionally need a bound valuation and market date.
All reads are bounded and local. This consumer never refreshes data or submits.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from open_composer.cockpit.security import secret_scrub

MAX_BYTES = 262_144
MAX_EVIDENCE_BYTES = 2_000_000
MAX_SERVICE_BYTES = 16_777_216
STATES = {"not_started", "starting", "running", "failed", "halted", "stopped"}


@dataclass(frozen=True)
class TrialPosition:
    symbol: str
    qty: float | None
    market_value: float | None


@dataclass(frozen=True)
class ValidationTrial:
    task_id: str
    label: str
    kind: str
    status: str
    observed_at: datetime | None
    market_as_of: str | None
    capital_usd: float | None
    nav_usd: float | None
    net_pnl_usd: float | None
    net_return_pct: float | None
    positions: tuple[TrialPosition, ...]
    submitted: int | None
    filled: int | None
    rejected: int | None
    pending: int | None
    reconciled_at: datetime | None
    note: str
    warnings: tuple[str, ...]
    service_phase: str | None = None
    service_observed_at: datetime | None = None
    last_fill_at: datetime | None = None
    component_market_value_usd: float | None = None
    component_pnl_usd: float | None = None
    component_realized_usd: float | None = None
    component_unrealized_usd: float | None = None
    component_observed_at: datetime | None = None
    component_basis_status: str | None = None
    recorded_order_intents: int | None = None
    unresolved_order_intents: int | None = None
    instruction_status: str | None = None
    next_input_status: str | None = None
    next_application_day: str | None = None
    refresh_not_before: datetime | None = None
    component_return_on_capital_pct: float | None = None
    initial_capital_usd: float | None = None
    allocation_flows_usd: float | None = None
    component_start_at: datetime | None = None
    input_attempt_status: str | None = None
    policy: str | None = None
    ledger_id: str | None = None


def _text(value: Any, limit: int = 240) -> str:
    return secret_scrub(value[:limit]) if isinstance(value, str) else ""


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return stamp if stamp.tzinfo is not None else None


def _path(root: Path, value: Any, directory: str) -> Path:
    if not isinstance(value, str) or Path(value).is_absolute():
        raise ValueError("invalid local artifact path")
    path = (root / value).resolve()
    if not path.is_relative_to((root / directory).resolve()):
        raise ValueError("artifact outside allowed directory")
    return path


def _read(path: Path) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError("oversized dashboard artifact")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("dashboard artifact must be an object")
    return data


def _bound(root: Path, value: Any) -> bool:
    if not isinstance(value, dict) or not re.fullmatch(r"[a-f0-9]{64}", str(value.get("sha256"))):
        return False
    try:
        path = _path(root, value.get("path"), "reports")
        with path.open("rb") as stream:
            raw = stream.read(MAX_EVIDENCE_BYTES + 1)
        return len(raw) <= MAX_EVIDENCE_BYTES and hashlib.sha256(raw).hexdigest() == value["sha256"]
    except (OSError, ValueError):
        return False


def _live_context(root: Path, config: dict, now: datetime) -> tuple[dict, dict, str]:
    """Receive the current native checkpoint; never refresh or mutate the operator."""
    if not config.get("service_state"):
        return {}, {}, ""
    try:
        directory = (
            "runtime/paper/six"
            if config["service_state"] == "runtime/paper/six/runtime-state.json"
            else "reports/research/program"
        )
        path = _path(root, config["service_state"], directory)
        with path.open("rb") as stream:
            raw = stream.read(MAX_SERVICE_BYTES + 1)
        if len(raw) > MAX_SERVICE_BYTES:
            raise ValueError("oversized service checkpoint")
        state = json.loads(raw, parse_float=Decimal)
        if not isinstance(state, dict) or not isinstance(state.get("policy_status"), dict):
            raise ValueError("invalid service checkpoint")
    except (OSError, ValueError, TypeError):
        return {}, {}, "Current paper-service checkpoint unavailable"
    try:
        from scripts.reconcile_six_paper_performance import project

        path = _path(root, config["performance_activities"], "reports/paper")
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != config["performance_activities_sha256"]:
            raise ValueError("saved fill inventory changed")
        activities = json.loads(raw, parse_float=Decimal)
        performance = project(root, state, activities, generated_at=now.isoformat())
        return state, performance, ""
    except (OSError, ValueError, TypeError, KeyError, AssertionError, ImportError):
        return (
            state,
            {},
            "Current trading components unavailable; net P&L remains uncertified",
        )


def _recovered_publication(root, folder, policy, target, sources, now):
    """Receive one confined successful recovery chain; never run its worker."""
    claim = _read(folder / "runtime-recovery-claim.json")
    record = Path(claim["record"]).resolve()
    assert record.parent == folder.parent.resolve()
    assert re.fullmatch(re.escape(folder.name) + r"-runtime-recovery-\d{2}", record.name)

    def bound(binding, expected):
        assert Path(binding["path"]).resolve() == expected.resolve()
        with expected.open("rb") as stream:
            raw = stream.read(MAX_BYTES + 1)
        assert len(raw) <= MAX_BYTES and binding.get("bytes") == len(raw)
        assert hashlib.sha256(raw).hexdigest() == binding["sha256"]
        return json.loads(raw)

    manifest_path = (
        root
        / "reports/paper/diagnostics"
        / ("inference-runtime-repair-" + folder.name.replace("-", ""))
        / "recovery-inputs.json"
    )
    manifest = bound(claim["manifest"], manifest_path)
    assert Path(manifest["prepared_root"]).resolve() == folder.resolve()
    assert manifest.get("purpose") == "same_day_exec127_saved_stage_recovery_v1"
    assert manifest.get("historical_failure_prefix_immutable") is True
    original_path = folder / "refresh-exit.json"
    original_binding = next(
        x
        for x in manifest["immutable_inputs"]
        if Path(x["path"]).resolve() == original_path.resolve()
    )
    original = bound(original_binding, original_path)
    stages = {x["phase"]: x["exit_code"] for x in original.get("stages", [])}
    assert stages.get("source") == stages.get("prepare") == 0
    assert stages.get("inference") == 127
    workers = {
        root / "reports/research/program/paper-launch-20min-20261021/recover_dated_refresh.py",
        root / "open_composer/paper_runtime/six/recover_dated_refresh.py",
    }
    worker = Path(claim["worker"]["path"]).resolve()
    # Hash and confine the recorded worker; do not import/execute it.
    assert worker in {p.resolve() for p in workers}
    raw_worker = worker.read_bytes()
    assert len(raw_worker) == claim["worker"]["bytes"]
    assert hashlib.sha256(raw_worker).hexdigest() == claim["worker"]["sha256"]
    recovered = _read(record / "recovery-exit.json")
    assert recovered.get("exit_code") == 0 and recovered.get("targets_published") is True
    assert recovered.get("status") == "current_input_recovery_published"
    recovered_stages = {x["phase"]: x["exit_code"] for x in recovered.get("stages", [])}
    assert recovered_stages.get("inference") == recovered_stages.get("postprocess") == 0
    produced = bound(recovered["target_result"], folder / "target-production-result.json")
    publication = _read(folder / "publication.json")
    times = [
        _time(x)
        for x in (
            original.get("at"),
            claim.get("at"),
            produced.get("at_utc"),
            publication.get("at"),
            recovered.get("at"),
        )
    ]
    assert all(times) and times == sorted(times) and times[-1] <= now + timedelta(minutes=1)
    assert produced.get("application_day") == folder.name
    assert target and target.get("application_day") == folder.name
    assert produced.get("reference_day") == target.get("reference_day")
    assert policy not in produced.get("blocked_policies", {})
    staged_path = folder / "targets" / (policy + ".json")
    staged = bound(produced["targets"][policy], staged_path)
    target_path = _target_path(root, policy, sources["decision"]["path"])
    current = bound(recovered["published"][policy], target_path)
    published = bound(publication["targets"][policy], target_path)
    assert current == published == staged == target
    assert recovered["published"][policy]["sha256"] == sources["decision"]["sha256"]
    start, end = _time(target.get("as_of")), _time(target.get("valid_until"))
    assert start and end and start <= now < end
    return recovered


def _target_path(root, policy, recorded):
    path = Path(recorded).resolve()
    allowed = {
        root / "reports/research/program/paper-launch-20min-20261021/targets" / (policy + ".json"),
        root / "runtime/paper/six/targets" / (policy + ".json"),
    }
    assert path in {p.resolve() for p in allowed}
    return path


def _session_inputs(root: Path, policy: str, sources: dict, now: datetime) -> dict:
    """Describe saved instructions and the existing worker's UTC delivery calendar.

    This is neither target validation nor a source/result receiver. In particular,
    a published packet is not an order grant or proof of next-session operation.
    """
    from open_composer.market_sessions import (
        NEW_YORK,
        next_us_equity_session,
        previous_us_equity_session,
        us_equity_session_close,
    )

    if policy not in {
        "BASE",
        "H5",
        "LSTM",
        "BASE_STATE_BUDGET",
        "MULTI_EQUAL",
        "MULTI_HIERARCHICAL",
    }:
        return {}
    utc_day = now.astimezone(UTC).date()
    close = us_equity_session_close(utc_day)
    expiry = (
        datetime.combine(utc_day, close, tzinfo=NEW_YORK).astimezone(UTC) - timedelta(minutes=30)
        if close
        else None
    )
    application = utc_day if expiry and now < expiry else next_us_equity_session(utc_day)
    result = dict(
        instruction_status="unavailable",
        next_input_status="awaiting_session_inputs",
        next_application_day=application.isoformat(),
        refresh_not_before=datetime.combine(application, datetime.min.time(), tzinfo=UTC)
        + timedelta(minutes=20),
    )
    if now >= result["refresh_not_before"]:
        result["next_input_status"] = "refresh_not_started"
    target = None
    try:
        decision = sources["decision"]
        # The native publisher uses absolute paths; confine this one reader to
        # the exact existing target, without weakening general evidence binding.
        path = _target_path(root, policy, decision["path"])
        with path.open("rb") as stream:
            body = stream.read(MAX_BYTES + 1)
        assert len(body) <= MAX_BYTES and hashlib.sha256(body).hexdigest() == decision["sha256"]
        target = json.loads(body)
        assert target["policy"] == policy
        start, end = _time(target["as_of"]), _time(target["valid_until"])
        assert start and end and start < end
        app_day = date.fromisoformat(target["application_day"])
        result["instruction_status"] = (
            "expired"
            if now >= end
            else "future"
            if now < start or app_day > utc_day
            else "within_time_bounds"
        )
    except (OSError, ValueError, TypeError, KeyError, AssertionError):
        target = None
        result["instruction_status"] = "unavailable_or_invalid"

    folder = root / "reports/paper/diagnostics/dated-target-refresh" / application.isoformat()
    try:
        if folder.exists():
            result["next_input_status"] = "attempt_unresolved"
            if (folder / "refresh-exit.json").exists():
                exit_record = _read(folder / "refresh-exit.json")
                if exit_record.get("exit_code") != 0:
                    result["next_input_status"] = "producer_failed"
                    result["input_attempt_status"] = "original_producer_failed"
                    if (folder / "runtime-recovery-claim.json").exists():
                        try:
                            recovered = _recovered_publication(
                                root, folder, policy, target, sources, now
                            )
                            assert (
                                target["reference_day"]
                                == previous_us_equity_session(application).isoformat()
                            )
                            assert recovered["targets_published"] is True
                            result["next_input_status"] = (
                                "publication_recorded_not_operating_acceptance"
                                if now >= result["refresh_not_before"]
                                else "future_packet_unverified"
                            )
                            result["input_attempt_status"] = (
                                "original_failed_then_recovery_published"
                            )
                        except (
                            OSError,
                            ValueError,
                            TypeError,
                            KeyError,
                            AssertionError,
                            StopIteration,
                        ):
                            result["next_input_status"] = "recovery_record_unavailable_or_invalid"
                else:
                    result["next_input_status"] = "awaiting_publication"
                    produced = _read(folder / "target-production-result.json")
                    if policy in produced.get("blocked_policies", {}):
                        result["next_input_status"] = "dependency_blocked"
                    elif target and target.get("application_day") == application.isoformat():
                        published = exit_record.get("published", {}).get(policy, {})
                        expected_ref = previous_us_equity_session(application).isoformat()
                        if (
                            published.get("sha256") == sources["decision"]["sha256"]
                            and target.get("reference_day") == expected_ref
                        ):
                            result["next_input_status"] = (
                                "publication_recorded_not_operating_acceptance"
                                if now >= result["refresh_not_before"]
                                else "future_packet_unverified"
                            )
    except (OSError, ValueError, TypeError, KeyError):
        result["next_input_status"] = "saved_attempt_unavailable_or_invalid"
    return result


def _closed_carrying(state: dict, now: datetime) -> bool:
    """Only dated, reconciled, closed-market carrying; never strategy readiness."""
    from open_composer.market_sessions import NEW_YORK, us_equity_session_close

    day = now.astimezone(NEW_YORK).date()
    close = us_equity_session_close(day)
    if close and (
        datetime.combine(day, datetime.min.time().replace(hour=9, minute=30), tzinfo=NEW_YORK)
        <= now
        < datetime.combine(day, close, tzinfo=NEW_YORK)
    ):
        return False
    account_at = _time(state.get("account", {}).get("observed_at"))
    return (
        account_at is not None
        and -60 <= (now - account_at).total_seconds() <= 120
        and state.get("position_mismatch") == {}
        and state.get("open_orders") == []
        and state.get("foreign_open_orders") == []
    )


def _trial(
    root: Path, item: dict, now: datetime, live: tuple[dict, dict, str] | None = None
) -> ValidationTrial:
    warnings: list[str] = []
    data: dict = {}
    status = "not_started"
    try:
        path = _path(root, item.get("snapshot"), "reports/paper")
        if path.exists():
            data = _read(path)
            if (
                data.get("schema_version") != 1
                or data.get("task_id") != item["task_id"]
                or data.get("mode") != "paper"
                or data.get("status") not in STATES
            ):
                raise ValueError("snapshot identity or paper mode mismatch")
            status = data["status"]
    except (OSError, ValueError, TypeError):
        data = {}
        status = "needs_attention"
        warnings.append("Snapshot unavailable or invalid")

    observed = _time(data.get("observed_at_utc"))
    reconciled = _time(data.get("reconciled_at_utc"))
    sources = data.get("source_bindings", {})
    if not isinstance(sources, dict):
        sources = {}
    if data and (observed is None or observed > now + timedelta(minutes=1)):
        status = "needs_attention"
        warnings.append("Snapshot timestamp unavailable or in the future")
    if status == "running" and (
        reconciled is None
        or observed is None
        or reconciled > observed
        or not all(
            _bound(root, sources.get(key)) for key in ("decision", "checkpoint", "reconciliation")
        )
    ):
        status = "needs_attention"
        warnings.append("Running state lacks verified operating evidence")

    market_day = data.get("market_as_of")
    try:
        parsed_day = date.fromisoformat(market_day)
        if observed is None or parsed_day > observed.date():
            raise ValueError("future market date")
    except (ValueError, TypeError):
        market_day = None
    valued = (
        status != "needs_attention"
        and market_day is not None
        and data.get("net_pnl_status") == "reconciled"
        and _bound(root, sources.get("valuation"))
    )
    rows = data.get("positions", [])
    positions = []
    if isinstance(rows, list):
        for row in rows[:256]:
            if isinstance(row, dict) and re.fullmatch(
                r"[A-Z][A-Z0-9.\-]{0,15}", str(row.get("symbol"))
            ):
                positions.append(
                    TrialPosition(
                        row["symbol"],
                        _number(row.get("qty")),
                        _number(row.get("market_value")) if valued else None,
                    )
                )
    orders = data.get("orders", {})
    if not isinstance(orders, dict):
        orders = {}

    def count(key: str) -> int | None:
        value = orders.get(key)
        return value if type(value) is int and value >= 0 else None

    state, performance, live_warning = live or ({}, {}, "")
    policy = item.get("policy")
    heartbeat = _time(state.get("heartbeat_at"))
    operation = state.get("policy_status", {}).get(policy, {})
    operation_at = _time(operation.get("observed_at"))
    phase = operation.get("status")
    if phase is not None:
        if state.get("status") in {
            "paused_or_expired",
            "paused",
            "halted",
            "failed",
            "stopped",
        }:
            phase = state["status"]
        elif heartbeat is None or operation_at is None or state.get("status") != "process_online":
            phase = "needs_attention"
        else:
            ages = [(now - stamp).total_seconds() for stamp in (heartbeat, operation_at)]
            phase = "stale" if max(ages) > 120 else "needs_attention" if min(ages) < -60 else phase
            phase = "waiting_market_open" if phase == "ready_waiting_rth" else phase
    else:
        phase = None
    inputs = _session_inputs(root, policy, sources, now) if state else {}
    unresolved = sum(
        "unknown" in str(order.get("status", ""))
        for order in state.get("orders", {}).values()
        if not order.get("book") or order["book"].split("/")[0] == policy
    )
    note = _text(data.get("note"))
    if inputs:
        if phase in {
            "blocked",
            "waiting_market_open",
            "operating",
        } and _closed_carrying(state, now):
            phase = (
                "closed_market_carrying_order_uncertain" if unresolved else "closed_market_carrying"
            )
        # Preserve the original operator/validator status; expiry must not hide
        # independent input failures, stale reconciliation or a global pause.
        note = (
            f"Saved operator: {operation.get('status', 'unknown')}"
            f" ({operation.get('error_type', 'no recorded error')}). "
            f"Instruction: {inputs['instruction_status']}. "
            f"Session {inputs['next_application_day']}: {inputs['next_input_status']}. "
            "Input timing is not operating acceptance; new-risk guards remain unchanged."
        )
    service_orders = [
        row
        for row in state.get("orders", {}).values()
        if row.get("book", "").split("/")[0] == policy
    ]
    filled_at = [_time(row.get("observation", {}).get("filled_at")) for row in service_orders]
    component = performance.get("sleeves", {}).get(policy, {})
    starts = [
        _time(row.get("time"))
        for name, executions in performance.get("executions", {}).items()
        if name == policy or name.startswith(str(policy) + "/")
        for row in executions
    ]
    if live_warning:
        warnings.append(live_warning)

    return ValidationTrial(
        task_id=item["task_id"],
        label=_text(item.get("label")) or item["task_id"],
        kind=_text(item.get("kind"), 40),
        status=status,
        observed_at=observed,
        market_as_of=market_day,
        capital_usd=_number(component.get("allocated_capital_usd", data.get("capital_usd"))),
        nav_usd=_number(data.get("nav_usd")) if valued else None,
        net_pnl_usd=_number(data.get("net_pnl_usd")) if valued else None,
        net_return_pct=_number(data.get("net_return_pct")) if valued else None,
        positions=tuple(positions),
        submitted=sum(bool(row.get("observation", {}).get("id")) for row in service_orders)
        if phase
        else count("submitted"),
        filled=sum(
            (_number(row.get("observation", {}).get("filled_qty")) or 0) > 0
            for row in service_orders
        )
        if phase
        else count("filled"),
        rejected=sum(row.get("status") == "rejected" for row in service_orders)
        if phase
        else count("rejected"),
        pending=sum(
            row.get("status") not in {"filled", "canceled", "expired", "rejected", "replaced"}
            for row in service_orders
        )
        if phase
        else count("pending"),
        reconciled_at=reconciled,
        note=note,
        warnings=tuple(warnings),
        service_phase=_text(phase, 80) or None,
        service_observed_at=operation_at,
        last_fill_at=max((stamp for stamp in filled_at if stamp is not None), default=None),
        component_market_value_usd=_number(component.get("market_value_usd")),
        component_pnl_usd=_number(component.get("trading_PnL_before_unverified_items_usd")),
        component_realized_usd=_number(component.get("realized_FIFO_before_unverified_costs_usd")),
        component_unrealized_usd=_number(
            component.get("unrealized_FIFO_before_unverified_costs_usd")
        ),
        component_observed_at=_time(performance.get("broker_account_observed_at")),
        component_basis_status=_text(component.get("execution_basis_status"), 80) or None,
        recorded_order_intents=len(service_orders) if phase else None,
        unresolved_order_intents=unresolved if phase else None,
        component_return_on_capital_pct=_number(
            component.get("tracking_return_on_assigned_capital_pct")
        ),
        initial_capital_usd=_number(component.get("initial_allocation_usd")),
        allocation_flows_usd=_number(component.get("internal_allocation_flows_usd")),
        component_start_at=min((stamp for stamp in starts if stamp is not None), default=None),
        policy=_text(item.get("policy"), 120) or None,
        ledger_id=_text(item.get("ledger_id"), 240) or None,
        **inputs,
    )


def load_validation_trials(
    root: Path, *, now: datetime | None = None
) -> tuple[ValidationTrial, ...]:
    """Load only explicitly listed projections; no recursive ledger discovery."""
    path = root / "config/paper-validation-dashboard.json"
    if not path.exists():
        return ()
    try:
        data = _read(path)
        if data.get("schema_version") != 1 or not isinstance(data.get("candidates"), list):
            return ()
        rows = []
        seen = set()
        live = _live_context(root, data, now or datetime.now(UTC))
        for item in data["candidates"][:128]:
            if not isinstance(item, dict):
                continue
            task = item.get("task_id")
            if (
                not isinstance(task, str)
                or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", task)
                or task in seen
            ):
                continue
            seen.add(task)
            rows.append(_trial(root, item, now or datetime.now(UTC), live))
        return tuple(rows)
    except (OSError, ValueError, TypeError):
        return ()
