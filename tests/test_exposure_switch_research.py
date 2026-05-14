from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.exposure_switch import run_exposure_switch_research


def test_exposure_switch_research_reports_dynamic_oos_gate(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frame = _sample_frame()

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr(
        "open_composer.research.exposure_switch.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "aaoi_exposure_base")

    result = run_exposure_switch_research(
        spec_path,
        sample_workspace,
        fast_bars=[3],
        slow_bars=[8],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        volatility_bars=[5],
        max_volatility_pct=[None],
        drawdown_bars=[5],
        max_drawdown_pct=[20.0],
        base_exposure=[1.0],
        risk_on_exposure=[1.25],
        risk_off_exposure=[0.0],
        financing_rate_pct=[5.0],
        max_candidates=1,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "dynamic_exposure_switch_research"
    assert payload["symbol"] == "AAOI"
    assert "previous bar close" in " ".join(payload["assumptions"])
    assert isinstance(payload["acceptance_gate"]["passed"], bool)
    assert "out_of_sample" in payload["candidates"][0]
    assert payload["candidates"][0]["full_window"]["exposure_changes"] >= 1
    assert payload["research_cost"]["candidate_count"] == 1
    assert payload["research_cost"]["walk_forward_candidate_count"] == 1
    assert payload["research_cost"]["estimated_total_backtest_passes"] == 12
    assert payload["data_profile"]["symbol"] == "AAOI"
    assert payload["data_profile"]["data_as_of"] == "2024-03-20T00:00:00+00:00"
    assert payload["research_brief"]["objective"] == (
        "dynamic exposure Alpha versus unlevered buy-and-hold"
    )
    assert payload["search_space"]["candidate_count"] == 1
    assert payload["hypothesis_ledger"][0]["hypothesis"].startswith("Dynamic exposure")
    assert payload["runtime_seconds"]["total"] >= 0
    assert set(payload["runtime_seconds"]["stages"]) == {
        "load_data",
        "build_grid",
        "evaluate_candidates",
        "walk_forward",
        "write_reports",
    }


def test_exposure_switch_walk_forward_top_k_reduces_reported_cost(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frame = _sample_frame()

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr(
        "open_composer.research.exposure_switch.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "aaoi_exposure_top_k")

    result = run_exposure_switch_research(
        spec_path,
        sample_workspace,
        fast_bars=[3, 5],
        slow_bars=[8],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        volatility_bars=[5],
        max_volatility_pct=[None],
        drawdown_bars=[5],
        max_drawdown_pct=[20.0],
        base_exposure=[1.0],
        risk_on_exposure=[1.25, 1.5],
        risk_off_exposure=[0.0],
        financing_rate_pct=[5.0],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=4,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["research_cost"]["candidate_count"] == 4
    assert payload["research_cost"]["walk_forward_candidate_count"] == 1
    assert payload["research_cost"]["walk_forward_top_k"] == 1
    assert payload["research_cost"]["estimated_candidate_evaluation_passes"] == 12
    assert payload["research_cost"]["estimated_walk_forward_validation_passes"] == 2
    assert payload["research_cost"]["estimated_walk_forward_selected_passes"] == 4
    assert payload["research_cost"]["estimated_total_backtest_passes"] == 18
    assert len(payload["walk_forward"]) <= 2


def _sample_frame() -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=80, freq="D", tz="UTC")
    close = (
        [100.0 + index for index in range(25)]
        + [124.0 - index * 1.1 for index in range(20)]
        + [102.0 + index * 1.4 for index in range(35)]
    )
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value + 1 for value in close],
            "low": [value - 1 for value in close],
            "close": close,
            "volume": [1_000_000] * 80,
        }
    )


def _write_spec(sample_workspace: Path, name: str) -> Path:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / f"{name}.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": name,
                "description": "AAOI exposure switch fixture.",
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
    return spec_path
