from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.core_satellite_router import (
    core_satellite_params_from_label,
    run_core_satellite_router_research,
)


def test_core_satellite_router_reports_research_and_pit_timing(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "QQQ": _sample_frame(100.0, 0.35),
        "TQQQ": _sample_frame(50.0, 0.8),
        "QLD": _sample_frame(70.0, 0.55),
    }
    requested: list[tuple[object, object]] = []

    def fake_fetch_ohlcv(**kwargs):
        requested.append((kwargs["start"], kwargs["end"]))
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.core_satellite_router.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "core_satellite_fixture")

    result = run_core_satellite_router_research(
        spec_path,
        sample_workspace,
        data_source="alpaca",
        start="2024-01-01",
        end="2024-12-31",
        satellite_symbols=["TQQQ"],
        trend_sma_days=[20],
        momentum_lookback_days=[10],
        min_momentum_pct=[0.0],
        volatility_lookback_days=[10],
        max_volatility_annual_pct=[None],
        drawdown_lookback_days=[20],
        max_drawdown_pct=[None],
        core_weight=[0.6],
        satellite_weight=[0.2],
        risk_off_core_scale=[0.5],
        target_satellite_volatility_pct=[None],
        rebalance_threshold_pct=[0.0, 5.0],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=2,
    )

    assert requested
    assert all(start is not None and end is not None for start, end in requested)
    assert result.report_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "core_satellite_router"
    assert payload["search_space"]["candidate_count"] == 2
    assert payload["acceptance_gate"]["objective"] == (
        "core_satellite_alpha_vs_qqq_buy_hold_after_costs"
    )
    assert payload["pass_status"]["paper_ready_pass"] is False
    assert "index-1 QQQ" in " ".join(payload["anti_leakage"])
    assert payload["candidates"][0]["params"]["label"].startswith("core_sat:")


def test_core_satellite_route_label_round_trips() -> None:
    params = core_satellite_params_from_label(
        "core_sat:sma150_mom60_min3_vol20_maxv30_dd120_maxdd15_core0.7_satQLD0.2_off0.5_tvol45_thr5"
    )

    assert params.trend_sma_days == 150
    assert params.satellite_symbol == "QLD"
    assert params.satellite_weight == 0.2
    assert params.risk_off_core_scale == 0.5
    assert params.target_satellite_volatility_pct == 45
    assert params.label.endswith("satQLD0.2_off0.5_tvol45_thr5")


def test_core_satellite_market_risk_controls_disable_satellite(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "QQQ": _sample_frame(100.0, 0.35),
        "TQQQ": _sample_frame(50.0, 0.8),
    }

    def fake_fetch_ohlcv(**kwargs):
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.core_satellite_router.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "core_satellite_risk_control_fixture")

    result = run_core_satellite_router_research(
        spec_path,
        sample_workspace,
        data_source="alpaca",
        start="2024-01-01",
        end="2024-12-31",
        satellite_symbols=["TQQQ"],
        trend_sma_days=[20],
        momentum_lookback_days=[10],
        min_momentum_pct=[0.0],
        volatility_lookback_days=[10],
        max_volatility_annual_pct=[-1.0],
        drawdown_lookback_days=[20],
        max_drawdown_pct=[None],
        core_weight=[0.6],
        satellite_weight=[0.2],
        risk_off_core_scale=[0.5],
        target_satellite_volatility_pct=[None],
        rebalance_threshold_pct=[0.0],
        walk_forward_folds=1,
        walk_forward_top_k=1,
        max_candidates=1,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    full = payload["selected_candidate"]["full_window"]
    assert full["market_regime_scaled_days"] > 0
    assert full["max_gross_exposure_pct"] <= 30.0


def _sample_frame(start: float, drift: float) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=360, freq="D", tz="UTC")
    close: list[float] = []
    value = start
    for index in range(360):
        cycle = 1.0 if index < 140 or index > 230 else -1.0
        value = max(1.0, value * (1 + (drift * cycle) / 100))
        close.append(value)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": close,
            "high": [value * 1.01 for value in close],
            "low": [value * 0.99 for value in close],
            "close": close,
            "volume": [1_000_000] * len(close),
        }
    )


def _write_spec(sample_workspace: Path, name: str) -> Path:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / f"{name}.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": name,
                "description": "Core satellite router fixture.",
                "timeframe": "daily",
                "universe": ["QQQ", "TQQQ", "QLD"],
                "lifecycle": "draft",
                "entry": {"all": ["close > sma(close, 20)"], "any": []},
                "exit": {"all": [], "any": ["close < sma(close, 20)"]},
                "risk": {"max_position_weight": 1.0},
                "portfolio": {
                    "mode": "hybrid_adaptive_router",
                    "selected_route_label": "placeholder",
                    "max_symbols_per_day": 2,
                    "gross_exposure_limit": 1.0,
                },
                "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "QQQ", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )
    return spec_path
