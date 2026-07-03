from __future__ import annotations

import pytest

from open_composer.research.defensive_transition_overlay import (
    DefensiveTransitionOverlay,
    defensive_transition_overlay_effective_lookback,
    defensive_transition_overlay_from_label,
)
from open_composer.research.delayed_entry_overlay import delayed_entry_overlay_from_label
from open_composer.research.hybrid_router_core import hybrid_params_from_label
from open_composer.research.post_drawdown_reentry_router import (
    PostDrawdownReentryParams,
    post_drawdown_reentry_params_from_label,
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


def test_post_drawdown_reentry_label_roundtrip() -> None:
    params = post_drawdown_reentry_params_from_label(BASE_LABEL)

    assert isinstance(params, PostDrawdownReentryParams)
    assert params.label == BASE_LABEL
    assert params.risk_universe == "semi_light"
    assert params.hard_drawdown_pct == 6.0
    assert params.vol_rank_high == 0.65
    assert params.canary_breadth_min == 1
    assert params.soft_stress_asset == "QQQ"
    assert params.defensive_mode == "GLD"
    assert params.cooldown_days == 5
    assert params.cooldown_asset == "QLD"
    assert params.confirmation_days == 5


def test_defensive_overlay_label_expands_pdr_and_roundtrips() -> None:
    overlay = defensive_transition_overlay_from_label(OVERLAY_LABEL)

    assert isinstance(overlay, DefensiveTransitionOverlay)
    assert overlay.base_route_label == BASE_LABEL
    assert overlay.label == OVERLAY_LABEL
    assert overlay.scope == "transition"
    assert overlay.replacement_symbol == "TQQQ"
    assert overlay.condition == "replacement_mom_positive"
    assert overlay.delayed_entry_overlay.time_rule == "regular_session_open_plus_30m"
    assert defensive_transition_overlay_effective_lookback(overlay) == 252


def test_hybrid_dispatch_accepts_active_overlay_label() -> None:
    params = hybrid_params_from_label(OVERLAY_LABEL)

    assert isinstance(params, DefensiveTransitionOverlay)
    assert params.holding_mode == "open_to_open"
    assert params.label == OVERLAY_LABEL


def test_delayed_entry_label_expands_pdr_base() -> None:
    delayed = delayed_entry_overlay_from_label(
        "delayed_entry:delay30_symbolsTQQQ-QLD_base["
        "pdr:semi_light_harddd6_v0.65_breadth1_softQQQ_defGLD_rec104_mom60max20"
        "_ext35_cool5QLD_confirm5_melt6040x25_detdd8m10]"
    )

    assert delayed.delay_minutes == 30
    assert delayed.covered_symbols == ("TQQQ", "QLD")
    assert delayed.base_route_label == BASE_LABEL
    assert delayed.time_rule == "regular_session_open_plus_30m"


@pytest.mark.parametrize(
    "label",
    [
        "pdr:semi_light_harddd6",
        "defensive_overlay:transition_TQQQ_bad_lb20_min0_delay30_base[pdr:x]",
        "delayed_entry:bad",
    ],
)
def test_invalid_pdr_labels_raise(label: str) -> None:
    with pytest.raises(ValueError):
        hybrid_params_from_label(label)
