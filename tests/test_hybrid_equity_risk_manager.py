from __future__ import annotations

from types import SimpleNamespace

import pandas as pd
import pytest

from open_composer.research.hybrid_router_core import (
    EquityRiskManagedHybridParams,
    _effective_lookback,
    hybrid_params_from_label,
    hybrid_target_weight_snapshot,
)
from open_composer.research.router_common import RouterFrameDataset, effective_lookback

BASE_ROUTE = (
    "beta_override:baseiter2_lb20_min5_adv0_sma200_exTQQQ_mdd20p6_"
    "ov120t105_g0.8_bearGLDlb60min0sma50w0.8_tqqq_cycle"
)
SELECTED_ROUTE = (
    f"equity_risk_manager:trig18_recover10_scale0.35_defBILw0.5_mindays10__base__{BASE_ROUTE}"
)


def test_equity_risk_manager_label_parses_and_round_trips() -> None:
    params = hybrid_params_from_label(SELECTED_ROUTE)

    assert isinstance(params, EquityRiskManagedHybridParams)
    assert params.base_label == BASE_ROUTE
    assert params.trigger_drawdown_pct == 18
    assert params.recovery_drawdown_pct == 10
    assert params.risk_scale == 0.35
    assert params.defensive_symbol == "BIL"
    assert params.defensive_redeploy == 0.5
    assert params.min_throttle_days == 10
    assert params.label == SELECTED_ROUTE
    assert effective_lookback(params) == effective_lookback(params.base_params)
    assert _effective_lookback(params) >= 200


@pytest.mark.parametrize(
    "manager",
    [
        "trig0_recover0_scale0.35_defBILw0.5_mindays10",
        "trig18_recover18_scale0.35_defBILw0.5_mindays10",
        "trig18_recover10_scale1.1_defBILw0.5_mindays10",
        "trig18_recover10_scale0.35_defBILw1.1_mindays10",
        "trig18_recover10_scale0.35_defBILw0.5_mindays0",
    ],
)
def test_equity_risk_manager_rejects_invalid_bounds(manager: str) -> None:
    with pytest.raises(ValueError):
        hybrid_params_from_label(f"equity_risk_manager:{manager}__base__{BASE_ROUTE}")


def test_equity_risk_manager_snapshot_throttles_after_realized_drawdown() -> None:
    base = "beta_override:baseiter2_lb20_min5_adv0_smanone_exTQQQ_g0.8_tqqq_always"
    params = hybrid_params_from_label(
        f"equity_risk_manager:trig5_recover2_scale0.25_defBILw1_mindays1__base__{base}"
    )
    dates = pd.date_range("2024-01-01", periods=270, freq="B")
    tqqq_open = [100.0] * 255 + [90.0] * 15
    frame = pd.DataFrame(
        {
            "date": [item.date().isoformat() for item in dates],
            "TQQQ_open": tqqq_open,
            "TQQQ_close": tqqq_open,
            "QQQ_open": [100.0] * len(dates),
            "QQQ_close": [100.0] * len(dates),
            "BIL_open": [100.0] * len(dates),
            "BIL_close": [100.0] * len(dates),
        }
    )
    dataset = RouterFrameDataset(
        symbols=["TQQQ", "QQQ", "BIL"],
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
        dates=frame["date"].tolist(),
        frame=frame,
        data_profile={},
    )
    spec = SimpleNamespace(
        portfolio=SimpleNamespace(gross_exposure_limit=0.8),
        costs=SimpleNamespace(commission_pct=0.0, slippage_bps=0.0),
    )

    snapshot = hybrid_target_weight_snapshot(spec, dataset, params, len(dates))

    assert snapshot.state == "equity_throttle"
    assert snapshot.weights["TQQQ"] == pytest.approx(0.2)
    assert snapshot.weights["BIL"] == pytest.approx(0.6)
    assert sum(snapshot.weights.values()) == pytest.approx(0.8)


def test_equity_risk_manager_requires_defensive_symbol_when_throttled() -> None:
    base = "beta_override:baseiter2_lb20_min5_adv0_smanone_exTQQQ_g0.8_tqqq_always"
    params = hybrid_params_from_label(
        f"equity_risk_manager:trig5_recover2_scale0.25_defBILw1_mindays1__base__{base}"
    )
    dates = pd.date_range("2024-01-01", periods=270, freq="B")
    opens = [100.0] * 255 + [90.0] * 15
    frame = pd.DataFrame(
        {
            "date": [item.date().isoformat() for item in dates],
            "TQQQ_open": opens,
            "TQQQ_close": opens,
            "QQQ_open": [100.0] * len(dates),
            "QQQ_close": [100.0] * len(dates),
        }
    )
    dataset = RouterFrameDataset(
        symbols=["TQQQ", "QQQ"],
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
        dates=frame["date"].tolist(),
        frame=frame,
        data_profile={},
    )
    spec = SimpleNamespace(
        portfolio=SimpleNamespace(gross_exposure_limit=0.8),
        costs=SimpleNamespace(commission_pct=0.0, slippage_bps=0.0),
    )

    with pytest.raises(ValueError, match="defensive symbol is absent"):
        hybrid_target_weight_snapshot(spec, dataset, params, len(dates))
