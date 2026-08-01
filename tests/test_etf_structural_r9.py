from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.etf_structural_r9 import (
    _write_jsonl,
    compute_monthly_targets,
    simulate_target_portfolio,
)


def test_r9_complete_candidate_builds_frozen_monthly_sleeves(repo_root: Path) -> None:
    spec = load_strategy_spec(
        repo_root / "strategy_specs/drafts/us_etf_structural_momentum_r9.yaml"
    )
    closes = _synthetic_r9_closes()

    targets, records = compute_monthly_targets(closes, spec)

    assert not targets.empty
    assert np.allclose(targets.sum(axis=1), 1.0)
    assert (targets >= 0).all().all()
    assert targets["SPY"].max() <= 0.4
    latest = targets.iloc[-1]
    assert latest["SPY"] == pytest.approx(0.4)
    assert latest["GLD"] == pytest.approx(0.15)
    assert latest["IEF"] == pytest.approx(0.15)
    assert sum(latest[symbol] > 0 for symbol in _sector_symbols()) == 2
    assert all(record["candidate_id"] == "R9D04" for record in records)
    positions = {session: index for index, session in enumerate(closes.index)}
    assert all(
        positions[pd.Timestamp(record["execution_session"])]
        == positions[pd.Timestamp(record["decision_session"])] + 1
        for record in records
    )


def test_simulation_charges_entry_and_terminal_cost_symmetrically() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=6)
    marks = pd.DataFrame({"BIL": [100.0] * len(sessions)}, index=sessions)
    targets = pd.DataFrame({"BIL": [1.0]}, index=pd.DatetimeIndex([sessions[0]]))

    full = simulate_target_portfolio(marks, targets, cost_bps=10.0)
    boundary = simulate_target_portfolio(
        marks,
        targets,
        cost_bps=10.0,
        start=sessions[2],
        end=sessions[-1],
    )

    expected = 0.999**2 - 1.0
    assert full.metrics["total_return_pct"] == pytest.approx(expected * 100.0)
    assert boundary.metrics["total_return_pct"] == pytest.approx(expected * 100.0)
    assert full.metrics["terminal_liquidation_count"] == 1
    assert boundary.metrics["terminal_liquidation_count"] == 1
    assert full.metrics["total_reported_one_way_turnover"] == pytest.approx(1.0)
    assert boundary.events[0]["reason"] == "independent_boundary_entry"


def test_simulation_rejects_nonfinite_marks_instead_of_skipping() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=4)
    marks = pd.DataFrame({"BIL": [100.0, math.nan, 100.0, 100.0]}, index=sessions)
    targets = pd.DataFrame({"BIL": [1.0]}, index=pd.DatetimeIndex([sessions[0]]))

    with pytest.raises(ValueError, match="finite and positive"):
        simulate_target_portfolio(marks, targets, cost_bps=10.0)


def test_maximum_drifted_weight_includes_terminal_open() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=3)
    marks = pd.DataFrame(
        {
            "AAA": [100.0, 100.0, 300.0],
            "BIL": [100.0, 100.0, 100.0],
        },
        index=sessions,
    )
    targets = pd.DataFrame(
        [{"AAA": 0.4, "BIL": 0.6}],
        index=pd.DatetimeIndex([sessions[0]]),
    )

    result = simulate_target_portfolio(marks, targets, cost_bps=0.0)

    assert result.metrics["maximum_drifted_weight"] == pytest.approx(1.2 / 1.8)


def test_simulation_supports_explicit_uninvested_cash_benchmark() -> None:
    sessions = pd.bdate_range("2026-01-02", periods=4)
    marks = pd.DataFrame({"SPY": [100.0, 101.0, 102.0, 103.0]}, index=sessions)
    targets = pd.DataFrame({"SPY": [0.0]}, index=pd.DatetimeIndex([sessions[0]]))

    result = simulate_target_portfolio(marks, targets, cost_bps=10.0)

    assert result.metrics["total_return_pct"] == pytest.approx(0.0)
    assert result.metrics["terminal_liquidation_count"] == 0
    assert result.events == []


def test_target_ledger_serializes_numpy_scalars_canonically(tmp_path: Path) -> None:
    path = tmp_path / "target-ledger.jsonl"

    _write_jsonl(path, [{"votes": np.int64(2), "active": np.bool_(True)}])

    assert path.read_text(encoding="utf-8") == '{"active":true,"votes":2}\n'


def _synthetic_r9_closes() -> pd.DataFrame:
    sessions = pd.bdate_range("2024-01-02", periods=520)
    drifts = {
        "SPY": 0.0005,
        "QQQ": 0.0007,
        "BIL": 0.0001,
        "GLD": 0.0004,
        "IEF": 0.0003,
        "XLB": 0.00055,
        "XLE": 0.0009,
        "XLF": 0.0006,
        "XLI": 0.00058,
        "XLK": 0.0010,
        "XLP": 0.00035,
        "XLU": 0.00032,
        "XLV": 0.00045,
        "XLY": 0.00065,
    }
    return pd.DataFrame(
        {
            symbol: 100.0 * np.exp(drift * np.arange(len(sessions)))
            for symbol, drift in drifts.items()
        },
        index=sessions,
    )


def _sector_symbols() -> list[str]:
    return ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"]
