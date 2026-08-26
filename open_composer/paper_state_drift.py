from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

LEVERAGED_RISK_ON = {"TQQQ", "QLD", "SOXL", "TECL", "ROM", "USD"}


def infer_actual_state_from_positions(positions: list[dict[str, Any]]) -> str:
    active = {
        str(row.get("symbol", "")).upper()
        for row in positions
        if abs(float(row.get("market_value") or 0.0)) > 1e-9
        or abs(float(row.get("qty") or 0.0)) > 1e-9
    }
    if "GLD" in active:
        return "defensive_gld_proxy"
    if "BIL" in active:
        return "cash_or_bil_proxy"
    if active & LEVERAGED_RISK_ON:
        return "risk_on_levered_proxy"
    return "flat" if not active else "unclassified_" + "_".join(sorted(active))


def build_state_drift_report(
    *,
    root: Path | None = None,
    cycle_date: date,
    expected_state: str,
    positions_path: Path | None = None,
    target_weights_path: Path | None = None,
    account_path: Path | None = None,
    weight_tolerance: float = 0.05,
) -> dict[str, Any]:
    base = root or project_root()
    resolved_positions = positions_path or base / "reports" / "paper" / "positions.json"
    resolved_account = account_path or base / "reports" / "paper" / "account.json"
    positions_payload = _read_json(resolved_positions)
    positions = positions_payload.get("positions") or []
    actual_state = infer_actual_state_from_positions(positions)
    target_check = _target_weight_check(
        cycle_date=cycle_date,
        positions=positions,
        account_path=resolved_account,
        target_weights_path=target_weights_path,
        weight_tolerance=weight_tolerance,
    )
    status = (
        "ok"
        if actual_state == expected_state and target_check["status"] in {"ok", "not_checked"}
        else "warning"
    )
    return {
        "report_type": "paper_state_drift",
        "generated_at": datetime.now(UTC).isoformat(),
        "date": cycle_date.isoformat(),
        "status": status,
        "expected_state": expected_state,
        "actual_state": actual_state,
        "positions_path": str(resolved_positions),
        "account_path": str(resolved_account),
        "target_weight_check": target_check,
        "positions": [
            {
                "symbol": row.get("symbol"),
                "qty": row.get("qty"),
                "market_value": row.get("market_value"),
            }
            for row in positions
        ],
        "message": (
            "paper positions match expected route state"
            if status == "ok"
            else "paper positions differ from expected route state"
        ),
    }


def write_state_drift_report(
    *,
    root: Path | None = None,
    cycle_date: date,
    expected_state: str,
    positions_path: Path | None = None,
    target_weights_path: Path | None = None,
    account_path: Path | None = None,
    weight_tolerance: float = 0.05,
) -> dict[str, Any]:
    base = root or project_root()
    payload = build_state_drift_report(
        root=base,
        cycle_date=cycle_date,
        expected_state=expected_state,
        positions_path=positions_path,
        target_weights_path=target_weights_path,
        account_path=account_path,
        weight_tolerance=weight_tolerance,
    )
    out_dir = ensure_dir(base / "reports" / "paper" / "state_drift")
    json_path = out_dir / f"{cycle_date:%Y%m%d}.json"
    md_path = out_dir / f"{cycle_date:%Y%m%d}.md"
    payload["artifact_paths"] = {"json": str(json_path), "markdown": str(md_path)}
    write_json(json_path, payload)
    md_path.write_text(render_state_drift_markdown(payload), encoding="utf-8")
    return payload


def render_state_drift_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# Paper State Drift: {payload['date']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Expected: `{payload['expected_state']}`",
        f"- Actual: `{payload['actual_state']}`",
        f"- Message: {payload['message']}",
        f"- Target weights: `{payload['target_weight_check']['status']}`",
        "",
        "| symbol | qty | market value |",
        "| --- | --- | --- |",
    ]
    for row in payload["positions"]:
        lines.append(f"| {row['symbol']} | {row['qty']} | {row['market_value']} |")
    mismatches = payload["target_weight_check"].get("mismatches") or []
    if mismatches:
        lines.extend(["", "## Target Weight Mismatches", ""])
        lines.append("| symbol | expected | actual | delta |")
        lines.append("| --- | --- | --- | --- |")
        for row in mismatches:
            lines.append(
                f"| {row['symbol']} | {row['expected_weight']} | "
                f"{row['actual_weight']} | {row['delta']} |"
            )
    lines.append("")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"positions": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _target_weight_check(
    *,
    cycle_date: date,
    positions: list[dict[str, Any]],
    account_path: Path,
    target_weights_path: Path | None,
    weight_tolerance: float,
) -> dict[str, Any]:
    if target_weights_path is None:
        return {"status": "not_checked", "message": "target_weights_path not provided"}
    if not target_weights_path.exists():
        return {
            "status": "warning",
            "message": "target weights artifact is missing",
            "target_weights_path": str(target_weights_path),
        }
    payload = _read_json(target_weights_path)
    rows = payload.get("target_weights") or []
    sessions = sorted({str(row.get("rebalance_session")) for row in rows if row})
    latest_session = max(
        (item for item in sessions if item <= cycle_date.isoformat()), default=None
    )
    latest_rows = [row for row in rows if str(row.get("rebalance_session")) == latest_session]
    expected = {
        str(row.get("symbol", "")).upper(): float(row.get("target_weight") or 0.0)
        for row in latest_rows
    }
    account = _read_json(account_path)
    denominator = float(
        account.get("portfolio_value") or account.get("equity") or _gross_market_value(positions)
    )
    if denominator <= 0:
        denominator = _gross_market_value(positions)
    actual = {
        str(row.get("symbol", "")).upper(): abs(float(row.get("market_value") or 0.0)) / denominator
        for row in positions
        if str(row.get("symbol", "")).strip()
    }
    symbols = sorted(set(expected) | {symbol for symbol, weight in actual.items() if weight > 1e-9})
    mismatches = []
    for symbol in symbols:
        expected_weight = expected.get(symbol, 0.0)
        actual_weight = actual.get(symbol, 0.0)
        delta = actual_weight - expected_weight
        if abs(delta) > weight_tolerance:
            mismatches.append(
                {
                    "symbol": symbol,
                    "expected_weight": round(expected_weight, 6),
                    "actual_weight": round(actual_weight, 6),
                    "delta": round(delta, 6),
                }
            )
    return {
        "status": "warning" if mismatches else "ok",
        "message": "target weights match paper positions"
        if not mismatches
        else "paper positions differ from latest target weights",
        "target_weights_path": str(target_weights_path),
        "rebalance_session": latest_session,
        "weight_tolerance": weight_tolerance,
        "mismatches": mismatches,
    }


def _gross_market_value(positions: list[dict[str, Any]]) -> float:
    return sum(abs(float(row.get("market_value") or 0.0)) for row in positions)
