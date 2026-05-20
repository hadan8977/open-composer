from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.aggressive_theme_router import (
    aggressive_theme_params_from_label,
    run_aggressive_theme_router_research,
)


def test_aggressive_theme_router_reports_research_and_pit_timing(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "QQQ": _sample_frame(100.0, 0.25),
        "SPY": _sample_frame(100.0, 0.12),
        "SMH": _sample_frame(80.0, 0.45),
        "SOXX": _sample_frame(85.0, 0.38),
        "XLK": _sample_frame(90.0, 0.28),
        "IGV": _sample_frame(75.0, 0.2),
        "ARKK": _sample_frame(60.0, 0.1),
        "IWM": _sample_frame(70.0, 0.08),
        "DIA": _sample_frame(95.0, 0.06),
        "TQQQ": _sample_frame(50.0, 0.7),
        "QLD": _sample_frame(55.0, 0.5),
        "SOXL": _sample_frame(40.0, 0.85),
    }
    requested: list[tuple[object, object]] = []

    def fake_fetch_ohlcv(**kwargs):
        requested.append((kwargs["start"], kwargs["end"]))
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.aggressive_theme_router.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "aggressive_theme_fixture")

    result = run_aggressive_theme_router_research(
        spec_path,
        sample_workspace,
        data_source="alpaca",
        start="2024-01-01",
        end="2024-12-31",
        trend_sma_days=[20],
        momentum_lookback_days=[10],
        top_n_values=[1],
        min_theme_momentum_pct=[0.0],
        core_weight=[0.2],
        theme_gross_weight=[0.6],
        levered_symbol=["TQQQ"],
        levered_weight=[0.1],
        defensive_symbol=["CASH", "QQQ"],
        defensive_weight=[0.0],
        volatility_lookback_days=[10],
        target_portfolio_volatility_pct=[None],
        max_market_volatility_pct=[None],
        drawdown_lookback_days=[20],
        max_market_drawdown_pct=[None],
        rebalance_threshold_pct=[0.0],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=2,
    )

    assert requested
    assert all(start is not None and end is not None for start, end in requested)
    assert result.report_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "aggressive_theme_router"
    assert payload["search_space"]["candidate_count"] == 2
    assert payload["acceptance_gate"]["objective"] == "aggressive_theme_alpha_vs_qqq_after_costs"
    assert payload["pass_status"]["paper_ready_pass"] is False
    assert "index-1 close" in " ".join(payload["anti_leakage"])
    assert payload["candidates"][0]["params"]["label"].startswith("aggr_theme:")


def test_aggressive_theme_route_label_round_trips() -> None:
    params = aggressive_theme_params_from_label(
        "aggr_theme:sma150_mom63_top2_min5_core0.25_theme0.65_"
        "levSOXL0.1_defSPY0.5_vol20_tvol45_maxv35_dd120_maxdd20_thr5"
    )

    assert params.trend_sma_days == 150
    assert params.momentum_lookback_days == 63
    assert params.top_n == 2
    assert params.levered_symbol == "SOXL"
    assert params.levered_weight == 0.1
    assert params.defensive_symbol == "SPY"
    assert params.defensive_weight == 0.5
    assert params.target_portfolio_volatility_pct == 45
    assert params.label.endswith("defSPY0.5_vol20_tvol45_maxv35_dd120_maxdd20_thr5")


def _sample_frame(start: float, drift: float) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=360, freq="D", tz="UTC")
    close: list[float] = []
    value = start
    for index in range(360):
        cycle = 1.0 if index < 140 or index > 230 else -0.7
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
                "description": "Aggressive theme router fixture.",
                "timeframe": "daily",
                "universe": ["QQQ", "SPY", "SMH", "SOXX", "XLK", "IGV", "ARKK"],
                "lifecycle": "draft",
                "entry": {"all": ["close > sma(close, 20)"], "any": []},
                "exit": {"all": [], "any": ["close < sma(close, 20)"]},
                "risk": {"max_position_weight": 1.0},
                "portfolio": {
                    "mode": "hybrid_adaptive_router",
                    "selected_route_label": "placeholder",
                    "max_symbols_per_day": 3,
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
