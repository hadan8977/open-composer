#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.notifications import safe_dispatch_notification

DEFAULT_STRATEGY = (
    "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate"
)
DEFAULT_SPEC = (
    "strategy_specs/active/"
    "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml"
)


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
    cycle_date = date.fromisoformat(args.date) if args.date else datetime.now(UTC).date()
    if args.dry_run:
        for step in planned_commands(args.strategy, args.spec):
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
    log_path = root / "reports" / "paper" / "daily_cycle" / f"{cycle_date:%Y%m%d}.json"
    ensure_dir(log_path.parent)
    if not is_trading_day(cycle_date):
        payload = {
            "report_type": "daily_paper_cycle",
            "date": cycle_date.isoformat(),
            "started_at": started_at,
            "ended_at": datetime.now(UTC).isoformat(),
            "strategy": strategy,
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
    for name, command in _step_commands(selected_oc_cmd, strategy, spec):
        step = _run_step(name, command, root, command_runner)
        steps.append(step)
        if step.exit_code != 0:
            payload = _cycle_payload(
                cycle_date=cycle_date,
                started_at=started_at,
                strategy=strategy,
                status="failed",
                steps=steps,
                artifacts=artifacts,
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
            )
            artifacts["target_weights"] = str(target_path)
            artifacts["review_card"] = str(review_path)
            step.artifact_paths.extend([str(target_path), str(review_path)])
            if card_payload["action_required"]:
                artifacts["action_required"] = "true"
    payload = _cycle_payload(
        cycle_date=cycle_date,
        started_at=started_at,
        strategy=strategy,
        status="ok",
        steps=steps,
        artifacts=artifacts,
    )
    _write_json(log_path, payload)
    _notify_cycle(
        payload,
        severity="warn" if artifacts.get("action_required") else "info",
        root=root,
    )
    return payload


def write_review_card(
    *,
    target_weights_path: Path,
    output_path: Path,
    cycle_date: date,
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
        mapped = round(target * 0.5, 6)
        previous = previous_by_symbol.get(symbol, 0.0)
        delta = round(target - previous, 6)
        if abs(delta) > 1e-9:
            action_required = True
        live_rows.append(
            {
                "symbol": symbol,
                "target_weight": target,
                "live_50pct_weight": mapped,
                "previous_weight": previous,
                "delta_weight": delta,
                "selected": bool(row.get("selected")),
            }
        )
    cash_weight = round(1.0 - sum(item["live_50pct_weight"] for item in live_rows), 6)
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
    if any(symbol in {"TQQQ", "QLD", "SOXL", "USD"} for symbol in symbols):
        return "risk_on_levered_proxy"
    return "unclassified_" + "_".join(symbols) if symbols else "flat"


def is_trading_day(value: date) -> bool:
    return value.weekday() < 5


def planned_commands(strategy: str, spec: str) -> list[list[str]]:
    return [command for _, command in _step_commands(["uv", "run", "oc"], strategy, spec)]


def _step_commands(oc_cmd: list[str], strategy: str, spec: str) -> list[tuple[str, list[str]]]:
    return [
        ("readiness", [*oc_cmd, "paper", "readiness", strategy, "--strict"]),
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
            ],
        ),
        (
            "paper_cycle",
            [*oc_cmd, "run", "paper", strategy, "--max-cycles", "1", "--interval-seconds", "0"],
        ),
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
    cycle_date: date,
    started_at: str,
    strategy: str,
    status: str,
    steps: list[CycleStep],
    artifacts: dict[str, str],
    failed_step: str | None = None,
) -> dict[str, Any]:
    return {
        "report_type": "daily_paper_cycle",
        "date": cycle_date.isoformat(),
        "started_at": started_at,
        "ended_at": datetime.now(UTC).isoformat(),
        "strategy": strategy,
        "status": status,
        "failed_step": failed_step,
        "paper_order_authorization": False,
        "steps": [asdict(step) for step in steps],
        "artifact_paths": artifacts,
    }


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
        "## 50% Live Mapping",
        "",
        "| symbol | target weight | 50% live weight | previous | delta | selected |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for row in payload["rows"]:
        lines.append(
            f"| {row['symbol']} | {row['target_weight']:.4f} | "
            f"{row['live_50pct_weight']:.4f} | {row['previous_weight']:.4f} | "
            f"{row['delta_weight']:.4f} | {row['selected']} |"
        )
    lines.extend(
        [
            f"| BIL/cash reserve | - | {payload['live_cash_or_bil_weight']:.4f} | - | - | - |",
            "",
            "## Safety",
            "",
            "- Observation-only paper cycle; no `--allow-paper-orders` was passed.",
            "- Live execution remains manual and must follow the runbook gates.",
            "",
        ]
    )
    return "\n".join(lines)


def _action_line(rows: list[dict[str, Any]], cash_weight: float) -> str:
    selected = [
        f"{row['symbol']} {row['live_50pct_weight']:.2%}"
        for row in rows
        if row["live_50pct_weight"] > 0
    ]
    return f"Manual live target: {', '.join(selected) or 'none'}; BIL/cash {cash_weight:.2%}."


def _previous_session(sessions: list[str], latest_session: str | None) -> str | None:
    if latest_session is None or latest_session not in sessions:
        return None
    index = sessions.index(latest_session)
    return sessions[index - 1] if index > 0 else None


def _target_weights_path(root: Path, strategy: str) -> Path:
    return root / "reports" / "execution" / f"{strategy}-target-weights.json"


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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
