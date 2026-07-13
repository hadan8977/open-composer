from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.mom_minute_lockbox import _position
from open_composer.research.momentum_signal_router import (
    momentum_route_from_label,
    momentum_target_position,
)


def test_frozen_momentum_route_matches_selected_candidate(repo_root: Path) -> None:
    spec = load_strategy_spec(repo_root / "strategy_specs/drafts/us_mom_minute_p1_003_frozen.yaml")
    assert spec.portfolio.selected_route_label is not None

    route = momentum_route_from_label(spec.portfolio.selected_route_label)

    assert route.signal_symbol == "QQQ"
    assert route.target_symbol == "TQQQ"
    assert route.timeframe == "30m"
    assert route.lookback_bars == 72
    assert route.atr_filter_multiplier == 2.5
    assert route.target_weight == 1.0
    assert spec.lifecycle == "draft"
    assert spec.execution.mode == "manual_signal"
    assert spec.execution.broker == "none"


def test_shared_position_function_has_research_parity() -> None:
    rows = 160
    close = pd.Series([100 + index * 0.1 + (index % 7) * 0.2 for index in range(rows)])
    frame = pd.DataFrame(
        {
            "signal_close": close,
            "signal_high": close + 0.5,
            "signal_low": close - 0.5,
        }
    )

    shared = momentum_target_position(frame, lookback_bars=72, atr_filter_multiplier=2.5)
    research = _position(frame, lookback_bars=72, atr_filter_multiplier=2.5)

    pd.testing.assert_series_equal(shared, research)
