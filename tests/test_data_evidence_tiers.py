from __future__ import annotations

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.metadata import data_acquisition_tier, frame_data_profile
from open_composer.research.promotion import DATA_TIERS_NOT_PAPER_READY, _evidence_acquisition_tier


def test_data_acquisition_tier_separates_fresh_pull_from_cache() -> None:
    assert (
        data_acquisition_tier(
            data_source="alpaca",
            source_mode="live_fetch",
            strict_live=True,
        )
        == "research_strict"
    )
    assert (
        data_acquisition_tier(
            data_source="alpaca",
            source_mode="cache",
        )
        == "research_replay_cache"
    )
    assert (
        data_acquisition_tier(
            data_source="alpaca",
            source_mode="fixture_fallback",
        )
        == "fixture_replay"
    )
    assert (
        data_acquisition_tier(
            data_source="sample",
            source_mode="sample",
        )
        == "sample_smoke"
    )


def test_frame_data_profile_includes_acquisition_tier() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2024-01-02", "2024-01-03"], utc=True),
            "open": [1.0, 2.0],
            "high": [1.0, 2.0],
            "low": [1.0, 2.0],
            "close": [1.0, 2.0],
            "volume": [100, 200],
        }
    )
    frame.attrs.update(
        {
            "data_source_provider": "alpaca",
            "data_source_mode": "live_fetch",
            "data_source_feed": "iex",
            "data_source_path": "data/cache/qqq_daily_iex.csv",
        }
    )

    profile = frame_data_profile(frame, symbol="QQQ", timeframe="daily")

    assert profile["acquisition_tier"] == "research_strict"
    assert profile["strict_live"] is True
    assert "iex_feed_not_full_market_sip" in profile["warnings"]


def test_promotion_tier_policy_allows_research_strict_but_blocks_cache() -> None:
    spec = StrategySpec(
        name="tier_check",
        description="tier check",
        timeframe="daily",
        universe=["QQQ"],
        lifecycle="draft",
        entry={"all": ["close > 0"]},
        exit={"any": ["close < 0"]},
        risk={"max_trades_per_day": 1, "max_position_weight": 0.5},
        execution={"backend": "python_reference", "mode": "manual_signal"},
        data={"source": "alpaca", "symbol": "QQQ"},
    )

    strict = _evidence_acquisition_tier(
        spec,
        {
            "source_mode": "live_fetch",
            "acquisition_tier": "research_strict",
            "strict_live": True,
        },
    )
    replay = _evidence_acquisition_tier(
        spec,
        {
            "source_mode": "cache",
            "acquisition_tier": "research_replay_cache",
            "strict_live": False,
        },
    )

    assert strict == "research_strict"
    assert strict not in DATA_TIERS_NOT_PAPER_READY
    assert replay == "research_replay_cache"
    assert replay in DATA_TIERS_NOT_PAPER_READY
