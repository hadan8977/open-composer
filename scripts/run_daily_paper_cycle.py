#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from open_composer.config import ensure_dir, project_root
from open_composer.execution_policy import resolve_execution_policy
from open_composer.market_calendar import us_equity_session_close
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.notifications import safe_dispatch_notification
from open_composer.paper_controls import load_paper_kill_switch
from open_composer.paper_readiness import assess_paper_strategy_readiness
from open_composer.paper_state_drift import LEVERAGED_RISK_ON, write_state_drift_report
from open_composer.paper_validation import check_previous_trading_day_remediation
from open_composer.strategy_versions import strategy_content_hash

DEFAULT_STRATEGY = (
    "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate"
)
DEFAULT_SPEC = (
    "strategy_specs/active/"
    "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml"
)
#: With --refresh-data and no explicit --start, fetch_ohlcv's own default window is
#: "now minus 30 calendar days" (~22 trading sessions), which undershoots the
#: router's 30-*trading*-session minimum and the router params' own lookbacks (up
#: to roughly 100 trading days for this strategy family). 400 calendar days clears
#: both with margin; daily bars are cheap enough that the wider window costs
#: nothing meaningful in latency.
TARGET_WEIGHTS_LOOKBACK_DAYS = 400


@dataclass
class CycleStep:
    name: str
    command: list[str] = field(default_factory=list)
    started_at: str | None = None
    ended_at: str | None = None
    exit_code: int | None = None
    stdout_tail: str = ""
    stderr_tail: str = ""
    artifact_paths: list[str] = field(default_factory=list)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    root = args.root.resolve()
    load_dotenv(root / ".env", override=False)
    cycle_date = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    if _is_model_ranking_portfolio_spec(root, args.spec):
        if args.dry_run:
            for step in _model_ranking_step_commands(["uv", "run", "oc"], args.spec):
                print(" ".join(step))
            return 0
        result = run_model_ranking_observation_cycle(
            root=root,
            spec=args.spec,
            cycle_date=cycle_date,
            oc_cmd=args.oc_cmd.split(),
        )
        return 0 if result["status"] in {"ok", "skipped"} else 1
    if args.dry_run:
        for step in planned_commands(args.strategy, args.spec, root=root):
            print(" ".join(step))
        return 0
    result = run_daily_cycle(
        root=root,
        strategy=args.strategy,
        spec=args.spec,
        cycle_date=cycle_date,
        oc_cmd=args.oc_cmd.split(),
    )
    return 0 if result["status"] in {"ok", "skipped"} else 1


def _is_model_ranking_portfolio_spec(root: Path, spec_ref: str) -> bool:
    """Whether ``spec_ref`` is a ``model_ranking_portfolio`` StrategySpec --
    the sole switch between the classic 4-step router/single-symbol daily
    cycle (``run_daily_cycle``, unchanged) and this mode's reduced,
    observation-only cycle (``run_model_ranking_observation_cycle``, Step 11
    Wave C item 5). Never raises: a missing/unparseable spec falls through
    to the classic path unchanged, which will raise its own clear error the
    same way it always has for a bad ``--spec``.
    """
    path = Path(spec_ref)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return False
    try:
        return load_strategy_spec(path).portfolio.mode == "model_ranking_portfolio"
    except Exception:
        return False


def _model_ranking_step_commands(oc_cmd: list[str], spec: str) -> list[list[str]]:
    return [
        [*oc_cmd, "paper", "sync-account"],
        [*oc_cmd, "strategy", "target-weights", spec],
    ]


def run_model_ranking_observation_cycle(
    *,
    root: Path,
    spec: str,
    cycle_date: date,
    oc_cmd: list[str] | None = None,
    command_runner=subprocess.run,
) -> dict[str, Any]:
    """Step 11 Wave C item 5: the daily observation-mode cycle for
    ``portfolio.mode=model_ranking_portfolio`` -- account-equity refresh plus
    target weights (which itself writes the per-strategy signal log; see
    ``open_composer.adapters.execution.model_ranking_target_weights``).
    Deliberately **not** a branch inside ``run_daily_cycle``: that function's
    remaining two steps (``paper_cycle`` = ``oc run paper``, and the
    route-state-drift machinery keyed on ``infer_route_state``'s small
    named-route vocabulary) assume a router/single-symbol strategy that
    ``open_composer/runner/paper.py`` (research/runner-owned, not touched by
    this Wave) knows how to dispatch; a cross-sectional top-K book has no
    such dispatch path yet. Keeping this as new, separate code rather than
    editing ``run_daily_cycle`` means zero risk to any other strategy's
    daily cycle. This function refuses to run against anything but a
    draft/manual_signal/broker=none spec, so it can never be pointed at an
    order-capable strategy by mistake.
    """
    started_at = datetime.now(UTC).isoformat()
    load_dotenv(root / ".env", override=False)
    spec_path = Path(spec)
    if not spec_path.is_absolute():
        spec_path = root / spec_path
    strategy_spec = load_strategy_spec(spec_path)
    if strategy_spec.portfolio.mode != "model_ranking_portfolio":
        raise ValueError(
            "run_model_ranking_observation_cycle requires portfolio.mode="
            f"model_ranking_portfolio, got {strategy_spec.portfolio.mode!r}"
        )
    if strategy_spec.execution.mode != "manual_signal" or strategy_spec.execution.broker != "none":
        raise ValueError(
            "model_ranking_portfolio observation cycle requires execution.mode=manual_signal "
            "and execution.broker=none -- this cycle never submits broker orders"
        )
    if strategy_spec.lifecycle != "draft":
        raise ValueError(
            "model_ranking_portfolio observation cycle refuses a non-draft lifecycle "
            f"({strategy_spec.lifecycle!r}); Step 11 Wave C never activates a strategy"
        )
    log_path = (
        root
        / "reports"
        / "paper"
        / "daily_cycle"
        / f"{strategy_spec.name}-observation-{cycle_date:%Y%m%d}.json"
    )
    ensure_dir(log_path.parent)
    if not is_trading_day(cycle_date):
        payload = {
            "report_type": "daily_paper_cycle_observation_only",
            "date": cycle_date.isoformat(),
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "strategy": strategy_spec.name,
            "status": "skipped",
            "skip_reason": "non_trading_day_weekend",
            "steps": [],
            "paper_order_authorization": False,
            "broker_writes": False,
        }
        _write_json(log_path, payload)
        return payload

    selected_oc_cmd = oc_cmd or ["uv", "run", "oc"]
    steps: list[CycleStep] = []
    for name, command in (
        ("account_sync", [*selected_oc_cmd, "paper", "sync-account"]),
        ("target_weights", [*selected_oc_cmd, "strategy", "target-weights", str(spec_path)]),
    ):
        step = _run_step(name, command, root, command_runner)
        steps.append(step)
        if step.exit_code != 0:
            payload = {
                "report_type": "daily_paper_cycle_observation_only",
                "date": cycle_date.isoformat(),
                "started_at": started_at,
                "ended_at": datetime.now(UTC).isoformat(),
                "strategy": strategy_spec.name,
                "status": "failed",
                "failed_step": name,
                "steps": [asdict(item) for item in steps],
                "paper_order_authorization": False,
                "broker_writes": False,
            }
            _write_json(log_path, payload)
            return payload

    target_weights_path = (
        root / "reports" / "execution" / f"{strategy_spec.name}-target-weights.json"
    )
    target_weights_summary: dict[str, Any] = {}
    if target_weights_path.is_file():
        try:
            target_payload = json.loads(target_weights_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            target_payload = {}
        summary = target_payload.get("summary") or {}
        target_weights_summary = {
            "is_new_signal": summary.get("is_new_signal"),
            "nonzero_target_rows": summary.get("nonzero_target_rows"),
            "top_k": summary.get("top_k"),
            "hedge": summary.get("hedge"),
            "idle_cash": summary.get("idle_cash"),
            "idle_cash_fraction": summary.get("idle_cash_fraction"),
            "weight_deviation": summary.get("weight_deviation"),
            "unaffordable": summary.get("unaffordable"),
            "candidate_is_placeholder": summary.get("candidate_is_placeholder"),
            "account_equity": summary.get("account_equity"),
        }
    payload = {
        "report_type": "daily_paper_cycle_observation_only",
        "date": cycle_date.isoformat(),
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "strategy": strategy_spec.name,
        "status": "ok",
        "steps": [asdict(item) for item in steps],
        "artifact_paths": {"log": str(log_path), "target_weights": str(target_weights_path)},
        "target_weights_summary": target_weights_summary,
        "paper_order_authorization": False,
        "broker_writes": False,
        "safety_note": (
            "Observation-only cycle: refreshes account equity and computes target weights "
            "plus the signal log. Never calls `oc run paper` and never submits broker orders."
        ),
    }
    _write_json(log_path, payload)
    return payload


def run_daily_cycle(
    *,
    root: Path,
    strategy: str = DEFAULT_STRATEGY,
    spec: str = DEFAULT_SPEC,
    cycle_date: date,
    oc_cmd: list[str] | None = None,
    command_runner=subprocess.run,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    load_dotenv(root / ".env", override=False)
    log_path = root / "reports" / "paper" / "daily_cycle" / f"{strategy}-{cycle_date:%Y%m%d}.json"
    ensure_dir(log_path.parent)
    binding = _cycle_binding(root, strategy, spec)
    if not is_trading_day(cycle_date):
        payload = {
            "report_type": "daily_paper_cycle",
            "date": cycle_date.isoformat(),
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "strategy": strategy,
            **binding,
            "status": "skipped",
            "skip_reason": "non_trading_day_weekend",
            "steps": [],
            "artifact_paths": {"log": str(log_path)},
        }
        _write_json(log_path, payload)
        return payload

    selected_oc_cmd = oc_cmd or ["uv", "run", "oc"]
    steps: list[CycleStep] = []
    artifacts: dict[str, str] = {"log": str(log_path)}
    remediation_check = check_previous_trading_day_remediation(
        root=root,
        cycle_date=cycle_date,
        strategy_name=strategy,
    )
    artifacts["previous_day_remediation_status"] = str(remediation_check["status"])
    if remediation_check["status"] == "error":
        _notify_remediation_check(remediation_check, strategy=strategy, root=root)
        payload = _cycle_payload(
            root=root,
            cycle_date=cycle_date,
            started_at=started_at,
            strategy=strategy,
            status="failed",
            steps=steps,
            artifacts=artifacts,
            paper_order_authorization=False,
            remediation_check=remediation_check,
            binding=binding,
            failed_step="previous_day_remediation",
        )
        _write_json(log_path, payload)
        _notify_cycle(payload, severity="red", root=root)
        return payload
    authorization_substate, authorization_path = _paper_order_authorization_state(root, strategy)
    paper_order_authorization = authorization_substate in {
        "canary_authorized",
        "order_authorized",
    }
    artifacts["paper_order_authorization_status"] = authorization_substate
    if authorization_path is not None:
        artifacts["paper_authorization"] = str(authorization_path)
    expected_state: str | None = None
    drift_status: str | None = None
    for name, command in _step_commands(
        selected_oc_cmd,
        strategy,
        spec,
        allow_paper_orders=paper_order_authorization,
    ):
        step = _run_step(name, command, root, command_runner)
        if name == "paper_cycle" and paper_order_authorization and step.exit_code == 0:
            paper_cycle_path, paper_cycle_reasons = _capture_paper_cycle_evidence(
                root=root,
                step=step,
                strategy=strategy,
                cycle_date=cycle_date,
                binding=binding,
            )
            if paper_cycle_path is not None:
                artifacts["paper_cycle"] = str(paper_cycle_path)
            if paper_cycle_reasons:
                step.exit_code = 1
                step.stderr_tail = ", ".join(paper_cycle_reasons)
        if name == "paper_monitor" and paper_order_authorization and step.exit_code == 0:
            broker_reasons = _authorized_broker_evidence_reasons(root, strategy)
            if broker_reasons:
                step.exit_code = 1
                step.stderr_tail = ", ".join(broker_reasons)
        steps.append(step)
        if step.exit_code != 0:
            payload = _cycle_payload(
                root=root,
                cycle_date=cycle_date,
                started_at=started_at,
                strategy=strategy,
                status="failed",
                steps=steps,
                artifacts=artifacts,
                paper_order_authorization=paper_order_authorization,
                remediation_check=remediation_check,
                binding=binding,
                failed_step=name,
            )
            _write_json(log_path, payload)
            _notify_cycle(payload, severity="red", root=root)
            return payload
        if name == "target_weights":
            target_path = _target_weights_path(root, strategy)
            review_path = root / "reports" / "paper" / "review_cards" / f"{cycle_date:%Y%m%d}.md"
            card_payload = write_review_card(
                target_weights_path=target_path,
                output_path=review_path,
                cycle_date=cycle_date,
                paper_order_authorization=paper_order_authorization,
            )
            artifacts["target_weights"] = str(target_path)
            review_json_path = review_path.with_suffix(".json")
            _write_json(review_json_path, card_payload)
            artifacts["review_card"] = str(review_json_path)
            artifacts["review_card_markdown"] = str(review_path)
            step.artifact_paths.extend([str(target_path), str(review_json_path), str(review_path)])
            expected_state = str(card_payload["route_state"])
            if card_payload["action_required"]:
                artifacts["action_required"] = "true"
        if name == "paper_monitor" and expected_state:
            drift = write_state_drift_report(
                root=root,
                cycle_date=cycle_date,
                expected_state=expected_state,
                target_weights_path=_target_weights_path(root, strategy),
            )
            drift_step = CycleStep(
                name="state_drift",
                started_at=drift["generated_at"],
                ended_at=datetime.now(UTC).isoformat(),
                exit_code=0,
                artifact_paths=list(drift["artifact_paths"].values()),
            )
            steps.append(drift_step)
            artifacts["state_drift"] = drift["artifact_paths"]["json"]
            artifacts["state_drift_status"] = drift["status"]
            drift_status = drift["status"]
    payload = _cycle_payload(
        root=root,
        cycle_date=cycle_date,
        started_at=started_at,
        strategy=strategy,
        status="ok",
        steps=steps,
        artifacts=artifacts,
        paper_order_authorization=paper_order_authorization,
        remediation_check=remediation_check,
        binding=binding,
    )
    _write_json(log_path, payload)
    _notify_cycle(
        payload,
        severity="warn"
        if artifacts.get("action_required") or drift_status == "warning"
        else "info",
        root=root,
    )
    return payload


def write_review_card(
    *,
    target_weights_path: Path,
    output_path: Path,
    cycle_date: date,
    paper_order_authorization: bool = False,
) -> dict[str, Any]:
    payload = json.loads(target_weights_path.read_text(encoding="utf-8"))
    rows = payload.get("target_weights") or []
    sessions = sorted({str(row["rebalance_session"]) for row in rows})
    latest_session = max(
        (item for item in sessions if item <= cycle_date.isoformat()), default=None
    )
    if latest_session is None and sessions:
        latest_session = sessions[-1]
    latest_rows = [row for row in rows if str(row.get("rebalance_session")) == latest_session]
    selected = [row for row in latest_rows if float(row.get("target_weight") or 0.0) > 0]
    previous_session = _previous_session(sessions, latest_session)
    previous_rows = [row for row in rows if str(row.get("rebalance_session")) == previous_session]
    previous_by_symbol = {
        str(row["symbol"]): float(row.get("target_weight") or 0.0) for row in previous_rows
    }
    live_rows = []
    action_required = False
    for row in latest_rows:
        symbol = str(row["symbol"])
        target = float(row.get("target_weight") or 0.0)
        mapped = round(target, 6)
        previous = previous_by_symbol.get(symbol, 0.0)
        delta = round(target - previous, 6)
        if abs(delta) > 1e-9:
            action_required = True
        live_rows.append(
            {
                "symbol": symbol,
                "target_weight": target,
                "paper_target_weight": mapped,
                "previous_weight": previous,
                "delta_weight": delta,
                "selected": bool(row.get("selected")),
            }
        )
    cash_weight = round(1.0 - sum(item["paper_target_weight"] for item in live_rows), 6)
    route_state = infer_route_state(selected)
    action_line = _action_line(live_rows, cash_weight) if action_required else "No operation."
    card_payload = {
        "date": cycle_date.isoformat(),
        "rebalance_session": latest_session,
        "signal_session": latest_rows[0].get("signal_session") if latest_rows else None,
        "strategy": payload.get("strategy_name"),
        "route_label": payload.get("route_label"),
        "route_state": route_state,
        "live_cash_or_bil_weight": cash_weight,
        "action_required": action_required,
        "action": action_line,
        "paper_order_authorization": paper_order_authorization,
        "rows": live_rows,
    }
    ensure_dir(output_path.parent)
    output_path.write_text(_render_review_card(card_payload), encoding="utf-8")
    return card_payload


def infer_route_state(selected_rows: list[dict[str, Any]]) -> str:
    symbols = [str(row.get("symbol")) for row in selected_rows]
    if "GLD" in symbols:
        return "defensive_gld_proxy"
    if "BIL" in symbols:
        return "cash_or_bil_proxy"
    if any(symbol in LEVERAGED_RISK_ON for symbol in symbols):
        return "risk_on_levered_proxy"
    return "unclassified_" + "_".join(symbols) if symbols else "flat"


def is_trading_day(value: date) -> bool:
    return us_equity_session_close(value) is not None


def planned_commands(strategy: str, spec: str, *, root: Path | None = None) -> list[list[str]]:
    allow_paper_orders = _paper_orders_allowed(root or project_root(), strategy)
    return [
        command
        for _, command in _step_commands(
            ["uv", "run", "oc"],
            strategy,
            spec,
            allow_paper_orders=allow_paper_orders,
        )
    ]


def _step_commands(
    oc_cmd: list[str],
    strategy: str,
    spec: str,
    *,
    allow_paper_orders: bool,
) -> list[tuple[str, list[str]]]:
    paper_command = [
        *oc_cmd,
        "run",
        "paper",
        strategy,
        "--max-cycles",
        "1",
        "--interval-seconds",
        "0",
    ]
    if allow_paper_orders:
        paper_command.append("--allow-paper-orders")
    return [
        ("readiness", [*oc_cmd, "paper", "readiness", strategy]),
        (
            "target_weights",
            [
                *oc_cmd,
                "strategy",
                "target-weights",
                spec,
                "--data-source",
                "alpaca",
                "--refresh-data",
                "--start",
                (date.today() - timedelta(days=TARGET_WEIGHTS_LOOKBACK_DAYS)).isoformat(),
            ],
        ),
        ("paper_cycle", paper_command),
        ("paper_monitor", [*oc_cmd, "paper", "monitor", "--sync-broker"]),
    ]


def _run_step(name: str, command: list[str], root: Path, command_runner) -> CycleStep:
    step = CycleStep(name=name, command=command, started_at=datetime.now(UTC).isoformat())
    result = command_runner(command, cwd=root, text=True, capture_output=True)
    step.ended_at = datetime.now(UTC).isoformat()
    step.exit_code = int(result.returncode)
    step.stdout_tail = _tail(str(result.stdout or ""))
    step.stderr_tail = _tail(str(result.stderr or ""))
    return step


def _cycle_payload(
    *,
    root: Path,
    cycle_date: date,
    started_at: str,
    strategy: str,
    status: str,
    steps: list[CycleStep],
    artifacts: dict[str, str],
    paper_order_authorization: bool,
    remediation_check: dict[str, Any],
    binding: dict[str, str | None],
    failed_step: str | None = None,
) -> dict[str, Any]:
    return {
        "report_type": "daily_paper_cycle",
        "cycle_receipt_version": 3,
        "date": cycle_date.isoformat(),
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "strategy": strategy,
        **binding,
        "status": status,
        "failed_step": failed_step,
        "paper_order_authorization": paper_order_authorization,
        "paper_authorization_substate": artifacts.get(
            "paper_order_authorization_status", "observation_only"
        ),
        "previous_day_remediation_check": remediation_check,
        "steps": [asdict(step) for step in steps],
        "artifact_paths": artifacts,
        "evidence_bindings": _artifact_bindings(
            root,
            artifacts,
            strategy=strategy,
            cycle_date=cycle_date,
            require_broker=paper_order_authorization,
        ),
    }


def _artifact_bindings(
    root: Path,
    artifacts: dict[str, str],
    *,
    strategy: str,
    cycle_date: date,
    require_broker: bool,
) -> list[dict[str, Any]]:
    sources: dict[str, str | Path | None] = {
        "target_weights": artifacts.get("target_weights"),
        "review_card": artifacts.get("review_card"),
        "state_drift": artifacts.get("state_drift"),
    }
    if require_broker:
        sources.update(
            {
                "paper_readiness": root / "reports" / "paper" / "readiness" / f"{strategy}.json",
                "broker_sync": root / "reports" / "paper" / "sync.jsonl",
                "broker_sync_receipt": root
                / "reports"
                / "paper"
                / "broker_receipts"
                / "latest-sync.json",
                "paper_authorization": artifacts.get("paper_authorization"),
                "account_snapshot": root / "reports" / "paper" / "account.json",
                "positions_snapshot": root / "reports" / "paper" / "positions.json",
                "paper_monitor": root / "reports" / "paper" / "monitor.json",
                "paper_cycle": artifacts.get("paper_cycle"),
            }
        )
    bindings = []
    base = root.resolve()
    evidence_dir = (
        root
        / "reports"
        / "paper"
        / "daily_cycle"
        / "evidence"
        / strategy
        / cycle_date.strftime("%Y%m%d")
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    for role, value in sources.items():
        if not value:
            continue
        path = Path(value)
        if not path.is_absolute():
            path = root / path
        try:
            resolved = path.resolve(strict=True)
            relative = resolved.relative_to(base)
        except (FileNotFoundError, ValueError):
            continue
        if not resolved.is_file():
            continue
        suffix = "".join(resolved.suffixes) or ".bin"
        snapshot = evidence_dir / f"{role}{suffix}"
        if snapshot.exists():
            if (
                hashlib.sha256(snapshot.read_bytes()).hexdigest()
                != hashlib.sha256(resolved.read_bytes()).hexdigest()
            ):
                raise ValueError(f"immutable cycle evidence already differs for {role}")
        else:
            shutil.copyfile(resolved, snapshot)
        resolved = snapshot.resolve(strict=True)
        relative = resolved.relative_to(base)
        bindings.append(
            {
                "role": role,
                "path": relative.as_posix(),
                "sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
                "size_bytes": resolved.stat().st_size,
            }
        )
    return bindings


def _authorized_broker_evidence_reasons(root: Path, strategy: str) -> list[str]:
    paths = {
        "paper_readiness": root / "reports" / "paper" / "readiness" / f"{strategy}.json",
        "broker_sync": root / "reports" / "paper" / "sync.jsonl",
        "account_snapshot": root / "reports" / "paper" / "account.json",
        "positions_snapshot": root / "reports" / "paper" / "positions.json",
        "paper_monitor": root / "reports" / "paper" / "monitor.json",
        "broker_sync_receipt": root / "reports" / "paper" / "broker_receipts" / "latest-sync.json",
    }
    reasons = [f"{role}_missing" for role, path in paths.items() if not path.is_file()]
    if reasons:
        return reasons
    try:
        readiness = json.loads(paths["paper_readiness"].read_text(encoding="utf-8"))
        monitor = json.loads(paths["paper_monitor"].read_text(encoding="utf-8"))
        account = json.loads(paths["account_snapshot"].read_text(encoding="utf-8"))
        positions = json.loads(paths["positions_snapshot"].read_text(encoding="utf-8"))
        sync_receipt = json.loads(paths["broker_sync_receipt"].read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ["authorized_broker_evidence_invalid_json"]
    readiness_pair = (readiness.get("status"), readiness.get("execution_substate"))
    if readiness_pair not in {
        ("ok", "order_authorized"),
        ("warning", "canary_authorized"),
    }:
        reasons.append("paper_readiness_not_order_authorized")
    if (
        monitor.get("sync_broker") is not True
        or monitor.get("sync_status") != "ok"
        or monitor.get("status") == "error"
    ):
        reasons.append("paper_monitor_not_synced")
    if account.get("paper") is not True:
        reasons.append("paper_account_not_paper")
    if (
        sync_receipt.get("receipt_version") != 1
        or sync_receipt.get("receipt_source") != "alpaca_paper_sync"
        or sync_receipt.get("paper") is not True
        or not sync_receipt.get("broker_account_id_hash")
        or sync_receipt.get("broker_account_id_hash") != account.get("broker_account_id_hash")
    ):
        reasons.append("broker_sync_receipt_invalid")
    if positions.get("paper") is not True or not isinstance(positions.get("positions"), list):
        reasons.append("paper_positions_invalid")
    return reasons


def _cycle_binding(root: Path, strategy: str, spec_ref: str) -> dict[str, str | None]:
    path = Path(spec_ref)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        return {
            "spec_hash": None,
            "active_spec_hash": None,
            "active_spec_path": None,
            "execution_policy_id": None,
            "execution_policy_hash": None,
        }
    spec = load_strategy_spec(path)
    if spec.name != strategy:
        raise ValueError(
            f"daily cycle strategy={strategy} does not match StrategySpec name={spec.name}"
        )
    active_path = root / "strategy_specs" / "active" / f"{strategy}.yaml"
    if not active_path.is_file():
        raise ValueError(f"daily cycle requires active StrategySpec: {active_path}")
    active_spec = load_strategy_spec(active_path)
    supplied_hash = strategy_content_hash(spec)
    active_hash = strategy_content_hash(active_spec)
    if active_spec.name != strategy:
        raise ValueError(
            f"active StrategySpec name={active_spec.name} does not match daily strategy={strategy}"
        )
    if supplied_hash != active_hash:
        raise ValueError(
            "daily cycle supplied StrategySpec hash does not match the active deployment"
        )
    policy = resolve_execution_policy(active_spec, root)
    return {
        "spec_hash": active_hash,
        "active_spec_hash": active_hash,
        "active_spec_path": str(active_path.relative_to(root)),
        "execution_policy_id": policy.policy_id if policy else None,
        "execution_policy_hash": policy.content_hash if policy else None,
    }


def _capture_paper_cycle_evidence(
    *,
    root: Path,
    step: CycleStep,
    strategy: str,
    cycle_date: date,
    binding: dict[str, str | None],
) -> tuple[Path | None, list[str]]:
    match = re.search(r"\bpaper cycle\s+([A-Za-z0-9_-]+)", step.stdout_tail)
    if match is None:
        return None, ["paper_cycle_run_id_missing"]
    run_id = match.group(1)
    cycles_path = root / "reports" / "runs" / "paper_cycles.jsonl"
    if not cycles_path.is_file():
        return None, ["paper_cycle_artifact_missing"]
    try:
        rows = [
            json.loads(line)
            for line in cycles_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None, ["paper_cycle_artifact_invalid"]
    row = next(
        (
            item
            for item in reversed(rows)
            if isinstance(item, dict) and item.get("run_id") == run_id
        ),
        None,
    )
    if row is None:
        return None, ["paper_cycle_run_artifact_missing"]
    reasons: list[str] = []
    if row.get("strategy_name") != strategy:
        reasons.append("paper_cycle_strategy_mismatch")
    expected_hash = binding.get("spec_hash")
    if expected_hash is not None and row.get("spec_hash") != expected_hash:
        reasons.append("paper_cycle_spec_hash_mismatch")
    signals = row.get("signals")
    if not isinstance(signals, list):
        reasons.append("paper_cycle_signals_invalid")
    elif any(
        isinstance(signal, dict) and signal.get("decision") == "order_error" for signal in signals
    ):
        reasons.append("paper_cycle_order_error")
    output_path = (
        root
        / "reports"
        / "paper"
        / "daily_cycle"
        / "runner_cycles"
        / strategy
        / cycle_date.strftime("%Y%m%d")
        / f"{run_id}.json"
    )
    _write_json(output_path, row)
    return output_path, reasons


def _notify_cycle(payload: dict[str, Any], *, severity: str, root: Path) -> None:
    safe_dispatch_notification(
        kind="digest_daily" if severity == "info" else "system_alert",
        severity=severity,  # type: ignore[arg-type]
        title=f"Daily paper cycle {payload['status']}: {payload['date']}",
        body=(
            f"strategy={payload['strategy']} failed_step={payload.get('failed_step')} "
            f"log={payload['artifact_paths']['log']}"
        ),
        metadata={
            "date": payload["date"],
            "status": payload["status"],
            "failed_step": payload.get("failed_step"),
        },
        root=root,
    )


def _notify_remediation_check(
    payload: dict[str, Any],
    *,
    strategy: str,
    root: Path,
) -> None:
    safe_dispatch_notification(
        kind="system_alert",
        severity="red",
        title=(f"Paper validation remediation missing: {payload.get('previous_trading_day')}"),
        body=(
            f"strategy={strategy} message={payload.get('message')} "
            f"remediation={payload.get('remediation_record_path')}"
        ),
        metadata={
            "strategy": strategy,
            "previous_trading_day": payload.get("previous_trading_day"),
            "status": payload.get("status"),
            "message": payload.get("message"),
            "remediation_record_path": payload.get("remediation_record_path"),
        },
        root=root,
    )


def _paper_orders_allowed(root: Path, strategy: str) -> bool:
    substate, _ = _paper_order_authorization_state(root, strategy)
    return substate in {"canary_authorized", "order_authorized"}


def _paper_order_authorization_state(
    root: Path,
    strategy: str,
) -> tuple[str, Path | None]:
    try:
        readiness = assess_paper_strategy_readiness(strategy, root)
    except Exception:
        return "observation_only", None
    valid = (readiness.status == "ok" and readiness.execution_substate == "order_authorized") or (
        readiness.status == "warning" and readiness.execution_substate == "canary_authorized"
    )
    if not valid:
        return readiness.execution_substate, None
    kill_switch = load_paper_kill_switch(root)
    if kill_switch.enabled:
        return "blocked", None
    check_name = (
        "canary_authorization"
        if readiness.execution_substate == "canary_authorized"
        else "order_authorization"
    )
    check = next((item for item in readiness.checks if item.name == check_name), None)
    path_value = check.details.get("path") if check is not None else None
    path = Path(str(path_value)) if path_value else None
    if path is not None and not path.is_absolute():
        path = root / path
    return readiness.execution_substate, path


def _render_review_card(payload: dict[str, Any]) -> str:
    lines = [
        f"# Paper Review Card: {payload['date']}",
        "",
        f"- Strategy: `{payload['strategy']}`",
        f"- Rebalance session: `{payload['rebalance_session']}`",
        f"- Signal session: `{payload['signal_session']}`",
        f"- Route state: `{payload['route_state']}`",
        f"- Action: {payload['action']}",
        "",
        "## Paper Target Mapping",
        "",
        "| symbol | target weight | paper target | previous | delta | selected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['symbol']} | {row['target_weight']:.4f} | "
            f"{row['paper_target_weight']:.4f} | {row['previous_weight']:.4f} | "
            f"{row['delta_weight']:.4f} | {row['selected']} |"
        )
    lines.extend(
        [
            f"| BIL/cash reserve | - | {payload['live_cash_or_bil_weight']:.4f} | - | - | - |",
            "",
            "## Safety",
            "",
            (
                "- Alpaca Paper order authorization: `order_authorized`; "
                "`--allow-paper-orders` may be passed by the daily cycle."
                if payload["paper_order_authorization"]
                else "- Observation-only paper cycle; no `--allow-paper-orders` was passed."
            ),
            "- Live execution remains manual and must follow the runbook gates.",
            "",
        ]
    )
    return "\n".join(lines)


def _action_line(rows: list[dict[str, Any]], cash_weight: float) -> str:
    selected = [
        f"{row['symbol']} {row['paper_target_weight']:.2%}"
        for row in rows
        if row["paper_target_weight"] > 0
    ]
    return f"Paper target: {', '.join(selected) or 'none'}; BIL/cash {cash_weight:.2%}."


def _previous_session(sessions: list[str], latest_session: str | None) -> str | None:
    if latest_session is None or latest_session not in sessions:
        return None
    index = sessions.index(latest_session)
    return sessions[index - 1] if index > 0 else None


def _target_weights_path(root: Path, strategy: str) -> Path:
    return root / "reports" / "execution" / f"{strategy}-target-weights.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(encoded)
        handle.flush()
    temporary.replace(path)


def _tail(value: str, limit: int = 4000) -> str:
    return value[-limit:]


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the observation-only daily paper cycle.")
    parser.add_argument("--strategy", default=DEFAULT_STRATEGY)
    parser.add_argument("--spec", default=DEFAULT_SPEC)
    parser.add_argument("--date", help="Cycle date in YYYY-MM-DD; defaults to today UTC.")
    parser.add_argument("--root", type=Path, default=project_root())
    parser.add_argument("--oc-cmd", default="uv run oc")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv)


if __name__ == "__main__":
    sys.exit(main())
