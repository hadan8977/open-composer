from __future__ import annotations

from datetime import date
from pathlib import Path

from typer.testing import CliRunner

from open_composer.cli import app
from open_composer.paper_state_drift import (
    build_state_drift_report,
    infer_actual_state_from_positions,
)
from open_composer.research.router_replay_audit import compare_replay_to_baseline


def test_state_drift_infers_actual_state_and_warns_on_mismatch(tmp_path: Path) -> None:
    positions = tmp_path / "positions.json"
    positions.write_text(
        '{"positions": [{"symbol": "TQQQ", "qty": 10, "market_value": 1000}]}',
        encoding="utf-8",
    )

    report = build_state_drift_report(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        expected_state="defensive_gld_proxy",
        positions_path=positions,
    )

    assert infer_actual_state_from_positions([{"symbol": "GLD", "qty": 1}]) == (
        "defensive_gld_proxy"
    )
    assert report["status"] == "warning"
    assert report["actual_state"] == "risk_on_levered_proxy"


def test_state_drift_classifies_all_long_leveraged_positions() -> None:
    for symbol in ("TQQQ", "QLD", "SOXL", "TECL", "ROM", "USD"):
        assert infer_actual_state_from_positions([{"symbol": symbol, "qty": 1}]) == (
            "risk_on_levered_proxy"
        )


def test_state_drift_detects_symbol_mismatch_within_same_risk_bucket(tmp_path: Path) -> None:
    positions = tmp_path / "positions.json"
    positions.write_text(
        '{"positions": [{"symbol": "TQQQ", "qty": 10, "market_value": 1000}]}',
        encoding="utf-8",
    )
    account = tmp_path / "account.json"
    account.write_text('{"portfolio_value": 1000}', encoding="utf-8")
    targets = _write_target_weights(tmp_path, "QLD", 1.0)

    report = build_state_drift_report(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        expected_state="risk_on_levered_proxy",
        positions_path=positions,
        account_path=account,
        target_weights_path=targets,
    )

    assert report["status"] == "warning"
    assert {row["symbol"] for row in report["target_weight_check"]["mismatches"]} == {
        "QLD",
        "TQQQ",
    }


def test_state_drift_detects_weight_mismatch_against_target_weights(tmp_path: Path) -> None:
    positions = tmp_path / "positions.json"
    positions.write_text(
        '{"positions": [{"symbol": "GLD", "qty": 10, "market_value": 500}]}',
        encoding="utf-8",
    )
    account = tmp_path / "account.json"
    account.write_text('{"portfolio_value": 1000}', encoding="utf-8")
    targets = _write_target_weights(tmp_path, "GLD", 1.0)

    report = build_state_drift_report(
        root=tmp_path,
        cycle_date=date(2026, 7, 9),
        expected_state="defensive_gld_proxy",
        positions_path=positions,
        account_path=account,
        target_weights_path=targets,
    )

    assert report["status"] == "warning"
    assert report["target_weight_check"]["mismatches"][0]["symbol"] == "GLD"


def test_router_replay_compare_passes_and_detects_drift() -> None:
    baseline = {
        "full_window_attribution": _attr(10.0, -5.0, 3),
        "folds": [{"fold": "fold1", "attribution": _attr(2.0, -1.0, 1)}],
    }
    current = {
        "full_window_attribution": _attr(10.0, -5.0, 3),
        "folds": {"fold1": _attr(2.0, -1.0, 1)},
    }

    passed = compare_replay_to_baseline(current=current, baseline=baseline)
    assert passed["passed"] is True

    current["folds"]["fold1"] = _attr(3.0, -1.0, 1)
    drift = compare_replay_to_baseline(current=current, baseline=baseline)
    assert drift["passed"] is False
    assert drift["checks"][1]["net_compound_diff"] == 1.0


def test_router_replay_audit_cli_help_smoke() -> None:
    assert CliRunner().invoke(app, ["strategy", "router-replay-audit", "--help"]).exit_code == 0


def _attr(net: float, tqqq: float, transitions: int) -> dict:
    return {
        "net_compound_pct": net,
        "tqqq_compound_pct": tqqq,
        "state_transitions": transitions,
    }


def _write_target_weights(root: Path, symbol: str, weight: float) -> Path:
    path = root / "target-weights.json"
    path.write_text(
        (
            '{"target_weights": ['
            f'{{"rebalance_session": "2026-07-09", "symbol": "{symbol}", '
            f'"target_weight": {weight}, "selected": true}}'
            "]}"
        ),
        encoding="utf-8",
    )
    return path
