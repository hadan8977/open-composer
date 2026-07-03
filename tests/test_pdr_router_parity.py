from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.hybrid_router_core import (
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.router_common import (
    RouterFrameDataset,
    backtest_router_params,
    load_daily_dataset,
    symbol_holding_return,
)

BASE_LABEL = (
    "post_drawdown_reentry:"
    "semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20"
    "_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10"
)
OVERLAY_LABEL = (
    "defensive_overlay:transition_TQQQ_replacement_mom_positive_lb20_min0_delay30_base["
    "pdr:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20"
    "_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10]"
)
SYMBOLS = ["QQQ", "TQQQ", "QLD", "SOXL", "USD", "SMH", "SOXX", "XLK", "IGV", "GLD", "BIL"]
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "pdr_router"
ROOT = Path(__file__).resolve().parents[1]


def _spec() -> StrategySpec:
    return StrategySpec.model_validate(
        {
            "name": "pdr_router_fixture",
            "description": "PDR router parity fixture.",
            "timeframe": "daily",
            "universe": SYMBOLS,
            "lifecycle": "draft",
            "entry": {"all": ["close > sma(close, 2)"]},
            "exit": {"any": ["close < sma(close, 2)"]},
            "risk": {"max_trades_per_day": 4, "max_position_weight": 1.0},
            "costs": {"commission_pct": 0.005, "slippage_bps": 3.0},
            "execution": {
                "backend": "python_reference",
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "portfolio": {
                "mode": "hybrid_adaptive_router",
                "max_symbols_per_day": 1,
                "gross_exposure_limit": 1.0,
                "max_symbol_weight": 1.0,
                "selected_route_label": OVERLAY_LABEL,
            },
            "data": {"source": "sample", "symbol": "QQQ"},
            "llm_review": {"enabled": False},
            "required_capabilities": ["market.sample_ohlcv"],
        }
    )


def _fixture_dataset() -> RouterFrameDataset:
    frame = pd.read_csv(FIXTURE_DIR / "pdr_router_price_slice.csv")
    return RouterFrameDataset(
        symbols=SYMBOLS,
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
        dates=[str(item) for item in frame["date"]],
        frame=frame,
        data_profile={"source_mode": "fixture", "provider": "test"},
    )


def _golden_slice() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (FIXTURE_DIR / "pdr_router_golden_slice.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]


def _daily_rows(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    params: object,
    start_index: int,
    end_index: int,
) -> list[dict[str, Any]]:
    cost_rate = spec.costs.commission_pct / 100 + spec.costs.slippage_bps / 10_000
    previous_weights: dict[str, float] = {}
    rows: list[dict[str, Any]] = []
    for index in range(start_index, end_index):
        snap = hybrid_target_weight_snapshot(spec, dataset, params, index)
        raw = sum(
            weight * symbol_holding_return(dataset, symbol, index, "open_to_open", spec)
            for symbol, weight in snap.weights.items()
            if weight > 0
        )
        turnover = sum(
            abs(snap.weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in set(snap.weights) | set(previous_weights)
        )
        rows.append(
            {
                "date": dataset.dates[index],
                "state": snap.state,
                "weights": {key: value for key, value in snap.weights.items() if value},
                "net_return": round(raw - turnover * cost_rate, 12),
            }
        )
        previous_weights = snap.weights
    return rows


def test_pdr_router_fixture_slice_matches_golden_decisions() -> None:
    spec = _spec()
    dataset = _fixture_dataset()
    params = hybrid_params_from_label(OVERLAY_LABEL)

    rows = _daily_rows(spec, dataset, params, _effective_lookback(params), len(dataset.dates) - 1)

    assert rows == _golden_slice()


def test_pdr_router_full_local_golden_replay_matches_control_artifact() -> None:
    data_path = ROOT / "data/research/longbridge_adjusted_daily/qqq_daily_longbridge_adjusted.csv"
    golden_path = ROOT / "reports/research/control/pdr-router-golden-daily-decisions-20260703.jsonl"
    fold_path = ROOT / "reports/research/control/pdr-router-fold-attribution-20260703.json"
    if not data_path.exists() or not golden_path.exists() or not fold_path.exists():
        pytest.skip("local Longbridge materialized data or PDR control artifacts are absent")

    spec = _spec()
    params = hybrid_params_from_label(OVERLAY_LABEL)
    dataset = load_daily_dataset(
        spec=spec,
        root=ROOT,
        symbols=SYMBOLS,
        data_source="longbridge",
        feed=None,
        start="2012-01-03",
        end="2026-05-22",
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
    )
    lookback = _effective_lookback(params)
    end_index = len(dataset.dates) - 1
    rows = _daily_rows(spec, dataset, params, lookback, end_index)
    golden = [json.loads(line) for line in golden_path.read_text(encoding="utf-8").splitlines()]
    assert rows == golden

    fold_payload = json.loads(fold_path.read_text(encoding="utf-8"))
    frame_dates = pd.Series(dataset.dates)
    parity_by_fold = {item["fold"]: item for item in fold_payload["parity_check"]["folds"]}
    for fold in fold_payload["folds"]:
        start_date = fold["start_date"]
        end_date = fold["end_date"]
        start_idx = int(frame_dates[frame_dates >= start_date].index[0])
        end_idx = int(frame_dates[frame_dates <= end_date].index[-1]) + 1
        metrics = backtest_router_params(
            spec,
            dataset,
            params,
            snapshot=hybrid_target_weight_snapshot,
            start_index=start_idx,
            end_index=end_idx,
        )
        parity = parity_by_fold[fold["fold"]]
        assert round(metrics.total_return_pct, 2) == parity["engine_total_return_pct"]
        assert round(fold["attribution"]["net_compound_pct"], 2) == parity["recorded_compound_pct"]
