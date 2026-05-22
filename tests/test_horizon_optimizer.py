from __future__ import annotations

from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.horizon_optimizer import optimize_strategy_horizons


def test_strategy_spec_accepts_5m_timeframe(repo_root: Path) -> None:
    raw = {
        "name": "qqq_5m_test",
        "description": "5m test",
        "timeframe": "5m",
        "universe": ["QQQ"],
        "lifecycle": "draft",
        "entry": {"all": ["close > ema(close, 3)"], "any": []},
        "exit": {"all": [], "any": ["close < ema(close, 3)"]},
        "risk": {"max_position_weight": 0.2},
        "execution": {
            "mode": "manual_signal",
            "signal_on": "bar_close",
            "fill_assumption": "next_bar_open",
            "broker": "none",
        },
        "data": {"source": "alpaca", "symbol": "QQQ", "feed": "iex"},
    }

    spec = StrategySpec.model_validate(raw)

    assert spec.timeframe == "5m"
    assert repo_root.exists()


def test_horizon_optimizer_compares_frequency_and_hold_profiles(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv")
    calls: list[tuple[str, str]] = []

    def fake_fetch_ohlcv(**kwargs):
        calls.append((kwargs["symbol"], kwargs["timeframe"]))
        frame = sample.copy()
        if kwargs["timeframe"] == "1h":
            frame = frame.iloc[::4].copy()
        if kwargs["timeframe"] == "5m":
            frame["close"] = frame["close"] * 1.002
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.horizon_optimizer.fetch_ohlcv", fake_fetch_ohlcv)
    result = optimize_strategy_horizons(
        sample_workspace / "strategy_specs" / "drafts" / "fixture_pullback_15m.yaml",
        sample_workspace,
        symbols=["AAA"],
        refresh_data=False,
    )

    assert result.report_path.exists()
    assert result.selected_specs
    assert all(path.exists() for path in result.selected_specs)
    assert {"5m", "15m", "1h"}.issubset({timeframe for _, timeframe in calls})
    report = result.report_path.read_text(encoding="utf-8")
    assert "higher scan frequency" in report
    assert "lower turnover" in report
