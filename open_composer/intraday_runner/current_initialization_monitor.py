"""Bounded event projection for the existing read-only dashboard; no extra reads."""

from __future__ import annotations

import json
from pathlib import Path

from open_composer.intraday_runner.current_initialization_controls import number
from open_composer.intraday_runner.source_activity_reception import bind
from open_composer.intraday_runner.source_method_bindings import bound_bytes
from open_composer.intraday_runner.validation_account_partition import (
    BASE,
    EQUAL,
    H5,
    HIERARCHICAL,
    LSTM,
    STATE,
)

NAMES = {
    BASE: "BASE",
    H5: "H5",
    LSTM: "LSTM",
    STATE: "BASE_STATE_BUDGET",
    EQUAL: "MULTI_EQUAL",
    HIERARCHICAL: "MULTI_HIERARCHICAL",
}


def publish(runtime, phase, result_binding, *, failed=False):
    """Publish actual event facts; incomplete valuation always remains unknown."""
    if type(failed) is not bool or runtime.task not in NAMES:
        raise ValueError("unknown projection scope")
    root = runtime.root
    json.loads(bound_bytes(root, result_binding))
    if (root / "reports") not in (root / result_binding["path"]).parents:
        raise ValueError("monitoring evidence outside reports")
    current = runtime.store.load()
    value = current["snapshot"] if current else None
    bindings = {}

    def local(b):
        bound_bytes(root, b)
        return dict(path=str((root / b["path"]).relative_to(root)), sha256=b["sha256"])

    if current:
        bindings["checkpoint"] = local(bind(runtime.store._revision(current["generation"])))
    decision = runtime.directory / "initial-decision.json"
    if decision.exists():
        bindings["decision"] = local(bind(decision))
    if not failed:
        bindings["reconciliation"] = local(result_binding)
    observed = runtime.clock().isoformat()
    # Counts are unique broker order IDs observed in this event, not shares,
    # attempts, fills, or a claim of all-history completeness.
    counts = dict(submitted=None, filled=None, rejected=None, pending=None)
    positions = []
    capture_path = Path(result_binding["path"]).parent / "account/capture-data.json"
    if not failed and capture_path.is_file():
        capture = json.loads(capture_path.read_text())
        orders = list(capture["orders"].values())
        if len({o["id"] for o in orders}) != len(orders):
            raise ValueError("duplicate observed broker ID")
        terminal = {"filled", "canceled", "expired", "rejected", "replaced"}
        counts = dict(
            submitted=len(orders),
            filled=sum(o["status"] == "filled" for o in orders),
            rejected=sum(o["status"] == "rejected" for o in orders),
            pending=sum(o["status"] not in terminal for o in orders),
        )
        positions = [
            dict(symbol=p["symbol"], qty=p["qty"], market_value=None) for p in capture["positions"]
        ]
        bindings["account_capture"] = local(bind(capture_path))
    allocated = float(number(value["evidence"]["allocated_capital"])) if value else None
    risk = value["evidence"].get("risk", {}) if value else {}
    latches = {k: risk.get(k) if type(risk.get(k)) is bool else None for k in ("halted", "killed")}
    halted = any(x is not False for x in latches.values())
    dispatch_blocked = bool(value and value["evidence"].get("initial_dispatch_blocked") is True)
    running = not failed and "decision" in bindings and "checkpoint" in bindings
    payload = dict(
        schema_version=1,
        task_id=runtime.task,
        mode="paper",
        status="failed"
        if failed or dispatch_blocked
        else "halted"
        if halted
        else "running"
        if running
        else "starting",
        observed_at_utc=observed,
        market_as_of=None,
        reconciled_at_utc=None if failed else observed,
        capital_usd=allocated,
        nav_usd=None,
        net_pnl_usd=None,
        net_return_pct=None,
        net_pnl_status="unknown",
        orders=counts,
        positions=positions,
        source_bindings=bindings,
        order_count_units=(
            "unique broker IDs in this capture; filled means fully filled; partial remains pending"
        ),
        event_phase=phase,
        initial_dispatch_blocked=dispatch_blocked,
        risk_latches=latches,
        risk_latch_status="known" if all(type(x) is bool for x in latches.values()) else "unknown",
        authority=local(runtime.authority),
        spec=local(runtime.auth["spec"]),
        policy=local(runtime.auth["policy"]),
        allocation_flows=[] if value is None else value["evidence"].get("allocation_flows", []),
        broker_equity_change_is_not_own_profit=True,
        modeled_incremental_cost_pnl=None,
        note=(
            "Actual event projection. Capital flows are not profit; "
            "fee/rights/valuation reconciliation remains explicit."
        ),
    )
    encoded = json.dumps(payload, allow_nan=False).encode()
    if len(encoded) > 262144:
        raise ValueError("monitor projection exceeds consumer bound")
    path = root / "reports/paper/validation" / (NAMES[runtime.task] + ".json")
    runtime.ensure_directory(path.parent)
    runtime.write_text(path, json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n")
    return bind(path)
