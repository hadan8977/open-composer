from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.robust_momentum_r4 import (
    EXPECTED_CANDIDATE_IDS,
    ContractViolation,
    FutureFeatureError,
    Panel,
    _assert_feature_availability,
    _buffered_sector_selection,
    _cap_and_normalize,
    _read_source_frame,
    _session_boundary,
    _simulate_asset_targets,
)


def test_candidate_manifest_has_exact_preregistered_ids() -> None:
    path = Path("reports/research/iterations/mom_robust_momentum_r4/candidate-manifest.json")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert payload["generated_before_backtest"] is True
    assert payload["candidate_count"] == 15
    assert tuple(row["candidate_id"] for row in payload["candidates"]) == EXPECTED_CANDIDATE_IDS
    assert sum(row["path"] == "deterministic_allocator" for row in payload["candidates"]) == 7
    assert sum(row["path"] == "ml_risk_allocator" for row in payload["candidates"]) == 6
    assert sum(row["path"] == "negative_controls" for row in payload["candidates"]) == 2


def test_source_frame_rejects_duplicate_timestamps(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp,open,close,volume\n"
        "2026-01-02T00:00:00Z,10,11,100\n"
        "2026-01-02T00:00:00Z,11,12,100\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractViolation, match="duplicate timestamps"):
        _read_source_frame(path, "BAD")


def test_source_frame_rejects_nonfinite_primitive(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(
        "timestamp,open,close,volume\n2026-01-02T00:00:00Z,10,,100\n",
        encoding="utf-8",
    )

    with pytest.raises(ContractViolation, match="non-finite"):
        _read_source_frame(path, "BAD")


def test_future_feature_is_rejected() -> None:
    decision = pd.Timestamp("2026-01-05T21:00:00Z")

    with pytest.raises(FutureFeatureError):
        _assert_feature_availability(decision + pd.Timedelta(seconds=1), decision)

    _assert_feature_availability(decision - pd.Timedelta(microseconds=1), decision)


def test_capped_weights_are_nonnegative_normalized_and_capped() -> None:
    weights = pd.Series([0.8, 0.1, 0.05, 0.05])

    result = _cap_and_normalize(weights, cap=0.4)

    assert result.sum() == pytest.approx(1.0)
    assert result.max() <= 0.4 + 1e-12
    assert (result >= 0).all()


def test_buffered_selection_keeps_eligible_prior_names_with_sector_cap() -> None:
    scores = pd.Series({"A": 0.9, "B": 0.8, "C": 0.7, "D": 0.6, "E": 0.5})
    sectors = {"A": "X", "B": "X", "C": "Y", "D": "Y", "E": "Z"}

    selected = _buffered_sector_selection(
        scores,
        sectors,
        ["B", "D"],
        top_n=3,
        buffer=2,
        sector_cap=1,
    )

    assert selected[:2] == ["B", "D"]
    assert len(selected) == 3
    assert len({sectors[symbol] for symbol in selected}) == 3


def test_simulator_drifts_weights_between_rebalances() -> None:
    dates = pd.date_range("2026-01-02", periods=7, freq="B", tz="UTC")
    open_prices = pd.DataFrame(
        {
            "A": [100, 100, 110, 121, 133.1, 146.41, 161.051],
            "BIL": [100, 100, 100, 100, 100, 100, 100],
        },
        index=dates,
    )
    panel = Panel(
        open=open_prices,
        close=open_prices.copy(),
        volume=pd.DataFrame(1_000.0, index=dates, columns=open_prices.columns),
        stock_symbols=("A",),
        all_symbols=("A", "BIL"),
        sector_by_symbol={"A": "X"},
        source_rows=(),
    )
    targets = pd.DataFrame(
        [[0.5, 0.5]],
        index=[dates[0]],
        columns=["A", "BIL"],
    )

    result = _simulate_asset_targets(
        panel,
        targets,
        cost_bps=0.0,
        start=dates[0],
        end=dates[4],
    )

    assert result["turnover"].iloc[0] == pytest.approx(0.5)
    assert result["turnover"].iloc[1:].sum() == pytest.approx(0.0)
    assert result["returns"].iloc[0] == pytest.approx(0.05)
    assert result["returns"].iloc[1] > result["returns"].iloc[0]


def test_session_boundary_counts_exact_sessions_not_calendar_days() -> None:
    sessions = pd.DatetimeIndex(
        [
            "2026-01-02T00:00:00Z",
            "2026-01-05T00:00:00Z",
            "2026-01-06T00:00:00Z",
            "2026-01-08T00:00:00Z",
        ]
    )

    assert _session_boundary(sessions, sessions[-1], 2) == sessions[1]
    with pytest.raises(ContractViolation, match="insufficient sessions"):
        _session_boundary(sessions, sessions[0], 1)


def test_simulator_rejects_non_normalized_target() -> None:
    dates = pd.date_range("2026-01-02", periods=5, freq="B", tz="UTC")
    values = pd.DataFrame(np.full((5, 2), 100.0), index=dates, columns=["A", "BIL"])
    panel = Panel(
        open=values,
        close=values,
        volume=values,
        stock_symbols=("A",),
        all_symbols=("A", "BIL"),
        sector_by_symbol={"A": "X"},
        source_rows=(),
    )
    targets = pd.DataFrame([[0.7, 0.4]], index=[dates[0]], columns=["A", "BIL"])

    with pytest.raises(ContractViolation, match="invalid asset target"):
        _simulate_asset_targets(
            panel,
            targets,
            cost_bps=10.0,
            start=dates[0],
            end=dates[2],
        )
