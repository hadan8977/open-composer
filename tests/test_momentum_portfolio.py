from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from open_composer.research.momentum_portfolio import (
    MomentumPortfolioResult,
    _decision_session_complete,
    _ml_gate_position,
    _portfolio_metrics,
    _sleeves,
    run_virtual_momentum_paper,
)


class _FixedEstimator:
    def __init__(self, probabilities: list[float]) -> None:
        self.probabilities = iter(probabilities)

    def predict_proba(self, frame: pd.DataFrame) -> np.ndarray:
        probability = next(self.probabilities)
        return np.array([[1.0 - probability, probability]])


def test_portfolio_has_exactly_six_bounded_sleeves() -> None:
    report = {
        "frozen_models": [
            {
                "model_family": "regularized_logistic",
                "model_path": "logistic.joblib",
                "threshold": 0.5,
                "status": "experimental_only",
            },
            {
                "model_family": "lightgbm_challenger",
                "model_path": "lightgbm.joblib",
                "threshold": 0.5,
                "status": "experimental_only",
            },
        ]
    }

    sleeves = _sleeves(Path("."), report)

    assert [row["sleeve_id"] for row in sleeves] == ["R0", "R1", "R2", "R3", "M1", "M2"]
    assert [row["strategy_type"] for row in sleeves] == ["rule"] * 4 + ["ml"] * 2
    assert sleeves[0]["definition_source"] == "strategy_spec"
    assert all(row["timeframe"] in {"15m", "30m"} for row in sleeves)


def test_ml_gate_never_creates_an_entry(tmp_path: Path, monkeypatch) -> None:
    frame = _feature_ready_frame(100)
    baseline = pd.Series([0.0] * 80 + [1.0] * 10 + [0.0] * 10)
    model_path = tmp_path / "model.joblib"
    joblib.dump(_FixedEstimator([0.9]), model_path)
    monkeypatch.setattr(
        "open_composer.research.momentum_portfolio._feature_frame",
        lambda _: pd.DataFrame(1.0, index=frame.index, columns=_feature_columns()),
    )

    gated = _ml_gate_position(
        tmp_path,
        frame,
        baseline,
        {"model_path": "model.joblib", "threshold": 0.5},
    )

    assert (gated <= baseline).all()
    assert gated.loc[baseline.eq(0)].eq(0).all()


def test_ml_gate_fails_safe_to_baseline(tmp_path: Path) -> None:
    frame = _feature_ready_frame(4)
    baseline = pd.Series([0.0, 1.0, 1.0, 0.0])

    gated = _ml_gate_position(
        tmp_path,
        frame,
        baseline,
        {"model_path": "missing.joblib", "threshold": 0.5},
    )

    pd.testing.assert_series_equal(gated, baseline)


def test_metrics_use_elapsed_time_for_intraday_annualization() -> None:
    index = pd.date_range("2025-01-02 14:30", periods=26, freq="30min", tz="UTC")
    returns = pd.Series(0.001, index=index)

    metrics = _portfolio_metrics(returns)

    assert metrics["bars"] == 26
    assert metrics["trading_days"] == 2
    assert metrics["annualized_return_pct"] > metrics["total_return_pct"]


def test_virtual_paper_is_isolated_idempotent_and_stale(tmp_path: Path, monkeypatch) -> None:
    observed_at = datetime(2026, 7, 13, 16, tzinfo=UTC)
    data_as_of = "2026-05-29T16:00:00+00:00"
    portfolio = {
        "portfolio": [
            {
                "sleeve_id": sleeve_id,
                "strategy_type": "rule" if sleeve_id.startswith("R") else "ml",
                "latest_target_weight": 1.0,
                "data_as_of": data_as_of,
                "latest_mark_price": 100.0,
                "timeframe": "30m",
                "sleeve_definition_hash": f"hash-{sleeve_id}",
                "decision_session_complete": True,
            }
            for sleeve_id in ["R0", "R1", "R2", "R3", "M1", "M2"]
        ]
    }
    monkeypatch.setattr(
        "open_composer.research.momentum_portfolio.run_momentum_strategy_portfolio",
        lambda root: MomentumPortfolioResult(Path("x"), Path("y"), portfolio),
    )
    first = run_virtual_momentum_paper(tmp_path, as_of=observed_at)
    second = run_virtual_momentum_paper(tmp_path, as_of=observed_at)

    assert first.payload["status"] == "awaiting_fresh_market_data"
    assert first.payload["broker_writes"] is False
    assert len(first.payload["sleeves"]) == 6
    for sleeve_id in ["R0", "R1", "R2", "R3", "M1", "M2"]:
        sleeve_dir = tmp_path / "reports/paper/virtual_momentum_portfolio" / sleeve_id
        assert not (sleeve_dir / "ledger.jsonl").exists()
        record = json.loads((sleeve_dir / "latest.json").read_text(encoding="utf-8"))
        assert record["sleeve_id"] == sleeve_id
        assert record["status"] == "awaiting_fresh_market_data"
        assert record["paper_order_authorization"] is False
    assert second.payload["sleeves"] == first.payload["sleeves"]


def test_virtual_paper_marks_to_market_in_isolated_ledger(tmp_path: Path, monkeypatch) -> None:
    observed_at = datetime(2026, 7, 13, 21, tzinfo=UTC)
    sleeve = {
        "sleeve_id": "R0",
        "strategy_type": "rule",
        "latest_target_weight": 1.0,
        "data_as_of": "2026-07-13T19:30:00+00:00",
        "latest_mark_price": 100.0,
        "timeframe": "30m",
        "sleeve_definition_hash": "definition-v1",
        "decision_session_complete": True,
    }
    portfolio = {"portfolio": [sleeve]}
    monkeypatch.setattr(
        "open_composer.research.momentum_portfolio.run_momentum_strategy_portfolio",
        lambda root: MomentumPortfolioResult(Path("x"), Path("y"), portfolio),
    )
    periods = iter(
        [
            {
                "gross_return": 0.1,
                "turnover": 0.0,
                "cost_return": 0.0,
                "net_return": 0.1,
                "evaluated_bars": 13,
                "evaluation_start": "2026-07-14T13:30:00+00:00",
                "evaluation_end": "2026-07-14T19:00:00+00:00",
            }
        ]
    )
    monkeypatch.setattr(
        "open_composer.research.momentum_portfolio._virtual_period_metrics",
        lambda *args: next(periods),
    )
    first = run_virtual_momentum_paper(tmp_path, as_of=observed_at)
    sleeve.update(
        {
            "data_as_of": "2026-07-14T19:30:00+00:00",
            "latest_mark_price": 110.0,
        }
    )
    second = run_virtual_momentum_paper(tmp_path, as_of=datetime(2026, 7, 14, 21, tzinfo=UTC))

    assert first.payload["status"] == "observed"
    assert first.payload["sleeves"][0]["epoch_anchor"] is True
    assert first.payload["sleeves"][0]["net_return"] == 0.0
    assert first.payload["sleeves"][0]["evaluated_bars"] == 0
    assert second.payload["status"] == "observed"
    ledger = tmp_path / "reports/paper/virtual_momentum_portfolio/R0/ledger.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 2
    assert rows[0]["epoch_anchor"] is True
    assert rows[0]["cost_return"] == 0.0
    assert rows[1]["gross_return"] == 0.1
    assert rows[1]["equity"] > rows[0]["equity"]


def test_definition_change_starts_new_virtual_paper_epoch(tmp_path: Path, monkeypatch) -> None:
    sleeve = {
        "sleeve_id": "R0",
        "strategy_type": "rule",
        "latest_target_weight": 1.0,
        "data_as_of": "2026-07-13T19:30:00+00:00",
        "latest_mark_price": 100.0,
        "timeframe": "30m",
        "sleeve_definition_hash": "definition-v1",
        "decision_session_complete": True,
    }
    monkeypatch.setattr(
        "open_composer.research.momentum_portfolio.run_momentum_strategy_portfolio",
        lambda root: MomentumPortfolioResult(Path("x"), Path("y"), {"portfolio": [sleeve]}),
    )
    monkeypatch.setattr(
        "open_composer.research.momentum_portfolio._virtual_period_metrics",
        lambda *args: {
            "gross_return": 0.0,
            "turnover": 0.0,
            "cost_return": 0.0,
            "net_return": 0.0,
            "evaluated_bars": 1,
            "evaluation_start": "2026-07-13T19:00:00+00:00",
            "evaluation_end": "2026-07-13T19:00:00+00:00",
        },
    )
    run_virtual_momentum_paper(tmp_path, as_of=datetime(2026, 7, 13, 21, tzinfo=UTC))
    sleeve.update(
        {
            "sleeve_definition_hash": "definition-v2",
            "data_as_of": "2026-07-14T19:30:00+00:00",
        }
    )

    result = run_virtual_momentum_paper(tmp_path, as_of=datetime(2026, 7, 14, 21, tzinfo=UTC))

    assert result.payload["sleeves"][0]["definition_epoch_reset"] is True
    assert result.payload["sleeves"][0]["epoch_anchor"] is True
    assert result.payload["sleeves"][0]["previous_target_weight"] == 0.0
    assert result.payload["sleeves"][0]["equity"] == 100000.0


def test_session_completeness_requires_exact_timestamp_set() -> None:
    timestamp = pd.date_range("2026-07-13 13:30", periods=13, freq="30min", tz="UTC")
    frame = pd.DataFrame({"timestamp": timestamp})

    assert _decision_session_complete(frame, "30m") is True
    frame.loc[12, "timestamp"] = frame.loc[11, "timestamp"]
    assert _decision_session_complete(frame, "30m") is False


def _feature_ready_frame(rows: int) -> pd.DataFrame:
    close = pd.Series(np.linspace(100.0, 110.0, rows))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-02", periods=rows, freq="30min", tz="UTC"),
            "signal_open": close,
            "signal_high": close + 1,
            "signal_low": close - 1,
            "signal_close": close,
            "trade_open": close * 2,
            "trade_close": close * 2,
        }
    )


def _feature_columns() -> list[str]:
    return [
        "qqq_roc_12_index_minus_1",
        "qqq_roc_36_index_minus_1",
        "qqq_roc_72_index_minus_1",
        "qqq_atr_ratio_72_index_minus_1",
        "qqq_realized_vol_26_index_minus_1",
        "tqqq_gap_1_index_minus_1",
    ]
