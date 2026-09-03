from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.auto_research import _persist_research_strict_tier
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
    assert (
        data_acquisition_tier(
            data_source="alpaca",
            source_mode="sip_parquet",
        )
        == "research_strict"
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


def test_explicit_research_strict_tier_wins_over_cache_profile() -> None:
    spec = StrategySpec(
        name="tier_check_explicit",
        description="tier check explicit",
        timeframe="daily",
        universe=["QQQ"],
        lifecycle="draft",
        entry={"all": ["close > 0"]},
        exit={"any": ["close < 0"]},
        risk={"max_trades_per_day": 1, "max_position_weight": 0.5},
        execution={"backend": "python_reference", "mode": "manual_signal"},
        data={"source": "alpaca", "symbol": "QQQ"},
        data_assumptions={
            "source": "alpaca",
            "adjusted": True,
            "acquisition_tier": "research_strict",
        },
    )

    tier = _evidence_acquisition_tier(
        spec,
        {
            "source_mode": "cache",
            "acquisition_tier": "research_replay_cache",
            "strict_live": False,
        },
    )

    assert tier == "research_strict"
    assert tier not in DATA_TIERS_NOT_PAPER_READY


def test_auto_research_persists_only_earned_research_strict(tmp_path: Path) -> None:
    spec_path = tmp_path / "strict_spec.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "strict_spec",
                "description": "strict spec",
                "timeframe": "daily",
                "universe": ["QQQ"],
                "lifecycle": "draft",
                "entry": {"all": ["close > 0"], "any": []},
                "exit": {"all": [], "any": ["close < 0"]},
                "risk": {"max_trades_per_day": 1, "max_position_weight": 0.5},
                "execution": {"backend": "python_reference", "mode": "manual_signal"},
                "data": {"source": "alpaca", "symbol": "QQQ"},
                "data_assumptions": {"source": "alpaca", "adjusted": True},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    _persist_research_strict_tier(spec_path, {"acquisition_tier": "research_replay_cache"})
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert "acquisition_tier" not in raw["data_assumptions"]

    _persist_research_strict_tier(spec_path, {"acquisition_tier": "research_strict"})
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    assert raw["data_assumptions"]["acquisition_tier"] == "research_strict"
