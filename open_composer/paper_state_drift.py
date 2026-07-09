from __future__ import annotations

import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from open_composer.config import ensure_dir, project_root
from open_composer.storage import write_json

LEVERAGED_RISK_ON = {"TQQQ", "QLD", "SOXL", "USD"}


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
) -> dict[str, Any]:
    base = root or project_root()
    resolved_positions = positions_path or base / "reports" / "paper" / "positions.json"
    positions_payload = _read_json(resolved_positions)
    positions = positions_payload.get("positions") or []
    actual_state = infer_actual_state_from_positions(positions)
    status = "ok" if actual_state == expected_state else "warning"
    return {
        "report_type": "paper_state_drift",
        "generated_at": datetime.now(UTC).isoformat(),
        "date": cycle_date.isoformat(),
        "status": status,
        "expected_state": expected_state,
        "actual_state": actual_state,
        "positions_path": str(resolved_positions),
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
) -> dict[str, Any]:
    base = root or project_root()
    payload = build_state_drift_report(
        root=base,
        cycle_date=cycle_date,
        expected_state=expected_state,
        positions_path=positions_path,
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
        "",
        "| symbol | qty | market value |",
        "| --- | --- | --- |",
    ]
    for row in payload["positions"]:
        lines.append(f"| {row['symbol']} | {row['qty']} | {row['market_value']} |")
    lines.append("")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"positions": []}
    return json.loads(path.read_text(encoding="utf-8"))
