from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.market_calendar import us_equity_session_close
from open_composer.research.core_satellite_r7 import (
    ALL_DAILY_SYMBOLS,
    CORE_SYMBOLS,
    R7FeatureAvailabilityError,
    R7Targets,
    _daily_contract_checks,
    _equal_budget_sleeve,
    _evaluate_simulation,
    _inverse_volatility_sleeve,
    build_r7_targets,
    run_future_packet_control,
    simulate_self_financing,
    validate_event_packet_availability,
)
from open_composer.research.multiscale_low_turnover_r6 import (
    R6Panel,
    build_r6_daily_features,
)


def test_equal_budget_sleeve_leaves_cash_when_too_few_symbols_qualify() -> None:
    weights = _equal_budget_sleeve(["XLB", "XLC"], budget=0.6, symbol_cap=0.2)

    assert weights.to_dict() == {"XLB": 0.2, "XLC": 0.2}
    assert weights.sum() == pytest.approx(0.4)


def test_inverse_volatility_sleeve_respects_budget_and_symbol_cap() -> None:
    volatility = pd.Series({"XLB": 0.05, "XLC": 0.20, "XLE": 0.30})

    weights = _inverse_volatility_sleeve(
        ["XLB", "XLC", "XLE"],
        volatility,
        budget=0.6,
        symbol_cap=0.3,
        target_volatility=0.12,
    )

    assert weights.sum() <= 0.6 + 1e-12
    assert weights.max() <= 0.3 + 1e-12
    assert (weights >= 0.0).all()


def test_self_financing_holdings_drift_between_declared_rebalances() -> None:
    sessions = (
        date(2026, 7, 13),
        date(2026, 7, 14),
        date(2026, 7, 15),
        date(2026, 7, 16),
    )
    panel = _panel(sessions, spy_opens=[100.0, 100.0, 200.0, 200.0])
    panel.daily["XLB"].loc[:, "open"] = [100.0, 100.0, 100.0, 200.0]
    weights = pd.DataFrame(0.0, index=sessions, columns=ALL_DAILY_SYMBOLS)
    weights.loc[:, ["SPY", "XLB"]] = 0.4
    mask = pd.Series(False, index=sessions, dtype=bool)
    mask.loc[sessions[0]] = True

    simulation = simulate_self_financing(panel, R7Targets(weights=weights, decision_mask=mask))
    gross_total = float((1.0 + simulation.gross_returns).prod() - 1.0)

    assert simulation.gross_returns.loc[sessions[1]] == pytest.approx(0.4)
    assert simulation.weights.loc[sessions[2], "SPY"] == pytest.approx(4.0 / 7.0)
    assert simulation.weights.loc[sessions[2], "XLB"] == pytest.approx(2.0 / 7.0)
    assert simulation.gross_returns.loc[sessions[2]] == pytest.approx(2.0 / 7.0)
    assert gross_total == pytest.approx(0.8)
    assert simulation.rebalance_turnover.sum() == pytest.approx(0.8)
    assert simulation.terminal_turnover == pytest.approx(8.0 / 9.0)


def test_costs_apply_at_entry_and_terminal_liquidation() -> None:
    sessions = (
        date(2026, 7, 13),
        date(2026, 7, 14),
        date(2026, 7, 15),
        date(2026, 7, 16),
    )
    panel = _panel(sessions, spy_opens=[100.0, 100.0, 200.0, 200.0])
    weights = pd.DataFrame(0.0, index=sessions, columns=ALL_DAILY_SYMBOLS)
    weights.loc[:, "SPY"] = 0.4
    mask = pd.Series(False, index=sessions, dtype=bool)
    mask.loc[sessions[0]] = True
    simulation = simulate_self_financing(panel, R7Targets(weights=weights, decision_mask=mask))

    evaluation = _evaluate_simulation(
        simulation,
        cost_bps=100.0,
        start_after=sessions[0],
    )

    gross_factor = 1.0 + simulation.gross_returns.loc[sessions[1] :].pipe(
        lambda values: float((1.0 + values).prod() - 1.0)
    )
    expected_factor = (
        (1.0 - 0.4 * 0.01) * gross_factor * (1.0 - simulation.terminal_turnover * 0.01)
    )
    assert evaluation["aggregate"]["total_return_pct"] == pytest.approx(
        (expected_factor - 1.0) * 100.0,
        abs=1e-5,
    )
    assert evaluation["aggregate"]["terminal_execution_session"] == "2026-07-16"


def test_all_daily_candidates_share_schedule_and_respect_target_caps() -> None:
    sessions = tuple(_trading_days(date(2024, 1, 2), 340))
    panel = _panel(sessions)
    features = build_r6_daily_features(panel)
    targets = {
        candidate_id: build_r7_targets(candidate_id, panel, features)
        for candidate_id in ("D01", "D02", "D03", "D04", "D05")
    }

    checks = _daily_contract_checks(targets, panel, features)

    assert checks["checks"]["all_candidates_share_decision_schedule"] is True
    assert checks["checks"]["all_rebalance_targets_respect_40pct_cap"] is True
    assert checks["checks"]["all_rebalance_targets_respect_gross_limit"] is True
    for candidate_targets in targets.values():
        decision_rows = candidate_targets.weights.loc[candidate_targets.decision_mask]
        assert decision_rows.max().max() <= 0.4 + 1e-12
        assert decision_rows.sum(axis=1).max() <= 1.0 + 1e-12


def test_event_packet_validator_accepts_only_predecision_visibility() -> None:
    packet = {
        "published_at": "2026-07-21T12:00:00+00:00",
        "fetched_at": "2026-07-21T12:00:02+00:00",
        "visible_at": "2026-07-21T12:00:02+00:00",
        "decision_at": "2026-07-21T13:00:00+00:00",
        "source": "sec",
        "symbol": "SPY",
        "input_hash": "0" * 64,
        "prompt_hash": "1" * 64,
        "dedupe_key": "valid",
        "evidence_spans": [{"start": 0, "end": 1}],
    }

    result = validate_event_packet_availability(packet)

    assert result["availability"] == "valid"
    packet["decision_at"] = "2026-07-21T12:00:01+00:00"
    with pytest.raises(R7FeatureAvailabilityError, match="not visible before"):
        validate_event_packet_availability(packet)


def test_future_packet_control_uses_event_candidate_validator() -> None:
    result = run_future_packet_control()

    assert result["status"] == "rejected_control"
    assert result["pass"] is True
    assert result["reason_code"] == "future_packet_rejected_by_event_candidate_validator"


def test_post_result_audit_supersedes_raw_workflow_pass() -> None:
    root = Path(__file__).resolve().parents[1]
    iteration = root / "reports/research/iterations/mom_core_satellite_r7"
    raw = json.loads((iteration / "evaluation-report.json").read_text(encoding="utf-8"))
    audit = json.loads((iteration / "contract-audit.json").read_text(encoding="utf-8"))
    decision = json.loads((iteration / "final-decision.json").read_text(encoding="utf-8"))

    assert raw["workflow_pass"] is True
    assert raw["selected_candidate_ids"] == []
    assert audit["workflow_pass"] is False
    assert audit["historical_candidate_gate_pass"] is False
    assert audit["selected_candidate_ids"] == []
    assert "evaluation-report.json:workflow_pass" in audit["supersedes"]
    assert decision["broker_orders_authorized"] is False
    assert decision["selected_candidate_ids"] == []


def test_r7_audit_freezes_runner_and_intraday_counterexample() -> None:
    root = Path(__file__).resolve().parents[1]
    iteration = root / "reports/research/iterations/mom_core_satellite_r7"
    raw = json.loads((iteration / "evaluation-report.json").read_text(encoding="utf-8"))
    audit = json.loads((iteration / "contract-audit.json").read_text(encoding="utf-8"))
    runner = root / raw["input_bindings"]["runner_path"]

    assert hashlib.sha256(runner.read_bytes()).hexdigest() == raw["input_bindings"]["runner_sha256"]
    finding_by_code = {row["code"]: row for row in audit["findings"]}
    assert "2024-07-22" in finding_by_code["D06_exact_parent_mask_claim_false"]["detail"]
    assert finding_by_code["strategy_spec_does_not_encode_family_behavior"]["severity"] == "P1"
    assert audit["raw_metrics_policy"]["selection_authority"] is False


def _panel(
    sessions: tuple[date, ...],
    *,
    spy_opens: list[float] | None = None,
) -> R6Panel:
    daily = {}
    length = len(sessions)
    for index, symbol in enumerate(ALL_DAILY_SYMBOLS):
        slope = 0.0002 + index * 0.00003
        periodic = 0.002 * np.sin(np.arange(length) / 7.0 + index * 0.3)
        close = 100.0 * np.cumprod(1.0 + slope + periodic)
        open_values = close * (1.0 - 0.0001)
        if symbol == "SPY" and spy_opens is not None:
            open_values = np.asarray(spy_opens, dtype=float)
            close = open_values.copy()
        daily[symbol] = pd.DataFrame(
            {
                "timestamp": pd.to_datetime(
                    [f"{session.isoformat()}T04:00:00Z" for session in sessions]
                ),
                "open": open_values,
                "high": np.maximum(open_values, close) * 1.001,
                "low": np.minimum(open_values, close) * 0.999,
                "close": close,
                "volume": np.full(length, 1_000_000.0 + index),
            },
            index=sessions,
        )
    return R6Panel(
        daily=daily,
        intraday={symbol: pd.DataFrame() for symbol in CORE_SYMBOLS},
        daily_sessions=sessions,
        intraday_sessions=(),
    )


def _trading_days(start: date, count: int) -> list[date]:
    output = []
    current = start
    while len(output) < count:
        if us_equity_session_close(current) is not None:
            output.append(current)
        current += timedelta(days=1)
    return output
