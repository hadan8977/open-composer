from pathlib import Path

import pandas as pd
import pytest

from open_composer.adapters.execution.single_symbol_target_weights import (
    build_single_symbol_target_states,
)
from open_composer.engines.signal_engine import (
    required_signal_history_bars,
    signal_masks,
)
from open_composer.expressions import ExpressionError
from open_composer.models.strategy_spec import load_strategy_spec

SPEC_PATH = Path("strategy_specs/drafts/us_spy_dual_trend_core_r8.yaml")


def test_r8_history_requirement_includes_lag_endpoint() -> None:
    spec = load_strategy_spec(SPEC_PATH)

    assert required_signal_history_bars(spec) == 127
    with pytest.raises(ExpressionError, match="at least 127 complete bars"):
        signal_masks(spec, _rising_frame(126))


@pytest.mark.parametrize("value", [float("nan"), float("inf")])
def test_r8_signal_rejects_nonfinite_required_history(value: float) -> None:
    spec = load_strategy_spec(SPEC_PATH)
    frame = _rising_frame(127)
    frame.loc[frame.index[-1], "close"] = value

    with pytest.raises(ExpressionError, match="nonfinite required OHLCV"):
        signal_masks(spec, frame)


def test_r8_persistent_trend_has_one_entry_then_hold_states() -> None:
    spec = load_strategy_spec(SPEC_PATH)
    states = build_single_symbol_target_states(spec, _rising_frame(130))

    assert len(states) == 4
    assert [state.target_weight for state in states] == [0.4, 0.4, 0.4, 0.4]
    assert [state.requires_order for state in states] == [True, False, False, False]
    assert states[0].previous_target_weight == 0.0
    assert states[-1].state == "risk_on"


def _rising_frame(rows: int) -> pd.DataFrame:
    close = pd.Series([100.0 + index for index in range(rows)])
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2025-01-02", periods=rows, freq="B", tz="UTC"),
            "open": close - 0.25,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": 1_000_000.0,
        }
    )
