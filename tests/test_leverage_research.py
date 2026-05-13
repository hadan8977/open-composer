from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.leverage import run_leverage_research


def test_leverage_research_reports_alpha_and_caveat(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=20, freq="D", tz="UTC"),
            "open": [100.0 + index for index in range(20)],
            "high": [101.0 + index for index in range(20)],
            "low": [99.0 + index for index in range(20)],
            "close": [100.0 + index for index in range(20)],
            "volume": [1_000_000] * 20,
        }
    )

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr("open_composer.research.leverage.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "aaoi_leverage_base.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "aaoi_leverage_base",
                "description": "AAOI leverage fixture.",
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

    result = run_leverage_research(
        spec_path,
        sample_workspace,
        leverage_values=[1.0, 1.5],
        financing_rate_pct=[0.0],
        max_candidates=2,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "levered_long_exposure_research"
    assert "not stock-selection Alpha" in " ".join(payload["assumptions"])
    assert payload["candidates"][0]["params"]["leverage"] == 1.5
    assert payload["candidates"][0]["out_of_sample"]["alpha_vs_buy_hold_pct"] > 0
    assert isinstance(payload["acceptance_gate"]["passed"], bool)
