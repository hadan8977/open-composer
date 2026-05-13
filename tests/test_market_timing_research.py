from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.market_timing import run_market_timing_research


def test_market_timing_research_reports_primary_buy_hold_alpha(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    timestamps = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    close = (
        [100 + index for index in range(30)]
        + [130 - index * 0.8 for index in range(30)]
        + [106 + index * 0.7 for index in range(20)]
    )
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [1_000_000 + index * 100 for index in range(80)],
        }
    )

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr("open_composer.research.market_timing.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "aaoi_timing_base.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "aaoi_timing_base",
                "description": "AAOI timing fixture.",
                "timeframe": "daily",
                "universe": ["AAOI"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 8)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAOI", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_market_timing_research(
        spec_path,
        sample_workspace,
        profiles=["trend_pullback"],
        fast_bars=[3],
        slow_bars=[8],
        exit_bars=[8],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        breakout_bars=[5],
        volume_bars=[3],
        stop_loss_pct=[10.0],
        take_profit_pct=[None],
        max_candidates=1,
        start="2024-01-05",
        end="2024-03-15",
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.selected_spec_path is not None
    assert result.selected_spec_path.exists()

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "single_symbol_market_timing"
    assert payload["symbol"] == "AAOI"
    assert payload["research_window"] == {"start": "2024-01-05", "end": "2024-03-15"}
    assert "same-symbol buy-and-hold" in payload["selection_objective"]
    assert payload["acceptance_gate"]["passed"] is False
    assert "alpha_vs_buy_hold_pct" in payload["candidates"][0]["out_of_sample"]
    assert payload["walk_forward"]
    assert (
        payload["candidates"][0]["out_of_sample"]["bars"]
        < payload["candidates"][0]["full_window"]["bars"]
    )

    selected = yaml.safe_load(result.selected_spec_path.read_text(encoding="utf-8"))
    assert selected["execution"]["mode"] == "manual_signal"
    assert selected["execution"]["fill_assumption"] == "next_bar_open"
    assert "lag(highest(close, 5), 1)" == selected["factors"]["prior_breakout"]["expression"]


def test_market_timing_research_supports_risk_control_hold_profile(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    timestamps = pd.date_range("2024-01-01", periods=50, freq="D", tz="UTC")
    close = [100 + index for index in range(50)]
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [1_000_000] * 50,
        }
    )

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr("open_composer.research.market_timing.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "aaoi_hold_base.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "aaoi_hold_base",
                "description": "AAOI hold fixture.",
                "timeframe": "daily",
                "universe": ["AAOI"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 8)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAOI", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_market_timing_research(
        spec_path,
        sample_workspace,
        profiles=["risk_control_hold"],
        fast_bars=[3],
        slow_bars=[8],
        exit_bars=[13],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        breakout_bars=[5],
        volume_bars=[3],
        stop_loss_pct=[20.0],
        take_profit_pct=[None],
        max_candidates=1,
    )

    assert result.best.spec.entry.all == ["close >= trend_slow"]
    assert result.best.spec.exit.any == ["close < exit_trend"]
