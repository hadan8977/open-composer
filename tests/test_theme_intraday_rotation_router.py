from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.theme_intraday_rotation_router import (
    run_theme_intraday_rotation_router_research,
    theme_intraday_params_from_label,
)


def test_theme_intraday_router_reports_research_and_prior_close_timing(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    symbols = [
        "QQQ",
        "TQQQ",
        "QLD",
        "SMH",
        "SOXX",
        "NVDA",
        "AVGO",
        "AMD",
        "MSFT",
    ]
    frames = {
        symbol: _sample_frame(100 + index * 3, 0.12 + index * 0.01)
        for index, symbol in enumerate(symbols)
    }

    def fake_fetch_ohlcv(**kwargs):
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.theme_intraday_rotation_router.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "theme_intraday_fixture", symbols)

    result = run_theme_intraday_rotation_router_research(
        spec_path,
        sample_workspace,
        symbols=symbols,
        data_source="alpaca",
        start="2024-01-01",
        end="2025-12-31",
        market_sma_days=[20],
        market_momentum_days=[10],
        min_market_momentum_pct=[0.0],
        signal_momentum_days=[10],
        confirmation_days=[5],
        top_n=[2],
        beta_symbol=["QQQ"],
        beta_weight=[0.25],
        satellite_weight=[0.5],
        max_symbol_weight=[0.25],
        market_below_sma_scale=[0.0],
        target_market_volatility_pct=[None],
        drawdown_lookback_days=[20],
        max_market_drawdown_pct=[None],
        score_mode=["raw"],
        semiconductor_gate=[True],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=1,
    )

    assert result.report_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "theme_intraday_rotation_router"
    assert payload["search_space"]["candidate_count"] == 1
    assert payload["acceptance_gate"]["objective"] == (
        "theme_intraday_rotation_alpha_vs_qqq_and_active_beta_after_costs"
    )
    assert payload["pass_status"]["paper_ready_pass"] is False
    assert payload["pass_status"]["llm_contribution_pass"] is False
    assert "Route selection uses index-1" in " ".join(payload["anti_leakage"])
    assert payload["candidates"][0]["params"]["label"].startswith("theme_intraday:")


def test_theme_intraday_route_label_round_trips() -> None:
    params = theme_intraday_params_from_label(
        "theme_intraday:sma50_mmom20_minm0_lb40_conf5_top3_"
        "betaQLD0.25_sat0.6_maxw0.2_off0.25_tvol40_"
        "dd60_maxdd20_scorecomposite_sem1"
    )

    assert params.market_sma_days == 50
    assert params.beta_symbol == "QLD"
    assert params.beta_weight == 0.25
    assert params.satellite_weight == 0.6
    assert params.score_mode == "composite"
    assert params.semiconductor_gate is True
    assert params.label.endswith("scorecomposite_sem1")


def _sample_frame(start: float, drift: float) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=420, freq="D", tz="UTC")
    close: list[float] = []
    open_: list[float] = []
    value = start
    for index in range(420):
        cycle = 1.0 if index < 250 or index > 320 else -0.8
        open_value = value * (1 + 0.001 * cycle)
        value = max(1.0, open_value * (1 + (drift * cycle) / 100))
        open_.append(open_value)
        close.append(value)
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": [
                max(open_value, close_value) * 1.01
                for open_value, close_value in zip(open_, close, strict=True)
            ],
            "low": [
                min(open_value, close_value) * 0.99
                for open_value, close_value in zip(open_, close, strict=True)
            ],
            "close": close,
            "volume": [1_000_000] * len(close),
        }
    )


def _write_spec(sample_workspace: Path, name: str, symbols: list[str]) -> Path:
    spec_path = sample_workspace / "strategy_specs" / "drafts" / f"{name}.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": name,
                "description": "Theme intraday fixture.",
                "timeframe": "daily",
                "universe": symbols,
                "lifecycle": "draft",
                "entry": {"all": ["close > sma(close, 20)"], "any": []},
                "exit": {"all": [], "any": ["close < sma(close, 20)"]},
                "risk": {"max_position_weight": 0.25, "max_trades_per_day": 4},
                "portfolio": {
                    "mode": "single_symbol",
                    "max_symbols_per_day": 4,
                    "gross_exposure_limit": 1.0,
                    "max_symbol_weight": 0.25,
                    "same_day_flatten": True,
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
