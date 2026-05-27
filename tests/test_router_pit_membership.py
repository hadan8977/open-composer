from __future__ import annotations

import pandas as pd

from open_composer.research.hybrid_router_core import (
    BetaOverrideHybridParams,
    _beta_override_symbol,
)
from open_composer.research.router_common import RouterFrameDataset, selected_by_momentum


def _dataset() -> RouterFrameDataset:
    dates = ["2024-01-02", "2024-01-03", "2024-01-04"]
    return RouterFrameDataset(
        symbols=["AAA", "BBB", "TQQQ"],
        market_symbol="QQQ",
        benchmark_symbol="TQQQ",
        dates=dates,
        frame=pd.DataFrame(
            {
                "date": dates,
                "AAA_close": [100.0, 110.0, 111.0],
                "BBB_close": [100.0, 150.0, 151.0],
                "TQQQ_close": [100.0, 105.0, 106.0],
                "QQQ_close": [100.0, 102.0, 103.0],
            }
        ),
        data_profile={},
        pit_membership={
            "AAA": [("2024-01-02", None)],
            "BBB": [("2024-01-02", "2024-01-03")],
            "TQQQ": [("2024-01-02", None)],
            "QQQ": [("2024-01-02", None)],
        },
    )


def test_selected_by_momentum_filters_symbols_not_active_in_pit_membership() -> None:
    selected = selected_by_momentum(
        _dataset(),
        2,
        lookback=1,
        top_n=1,
        symbols=["AAA", "BBB"],
    )

    assert selected == ["AAA"]


def test_beta_override_symbol_filters_symbols_not_active_in_pit_membership() -> None:
    selected = _beta_override_symbol(
        _dataset(),
        BetaOverrideHybridParams(
            holding_mode="open_to_open",
            momentum_lookback_days=1,
            min_momentum_pct=0.0,
            override_advantage_pct=0.0,
            confirmation_sma_days=None,
            exclude_tqqq=False,
        ),
        2,
    )

    assert selected == "AAA"
