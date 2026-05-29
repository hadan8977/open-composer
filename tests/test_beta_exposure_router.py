from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.adapters.execution.beta_target_weights import run_beta_target_weight_mapping
from open_composer.research.beta_exposure_router import (
    beta_params_from_label,
    run_beta_exposure_router_research,
)


def test_beta_exposure_router_reports_target_weight_research(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "QQQ": _sample_frame(100.0, 0.5),
        "TQQQ": _sample_frame(50.0, 0.9),
        "SQQQ": _sample_frame(80.0, -0.3),
    }

    def fake_fetch_ohlcv(**kwargs):
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.beta_router_core.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "beta_router_fixture")

    result = run_beta_exposure_router_research(
        spec_path,
        sample_workspace,
        market_symbol="QQQ",
        leverage_symbol="TQQQ",
        hedge_symbol="SQQQ",
        trend_sma_days=[20],
        momentum_lookback_days=[10],
        min_momentum_pct=[0.0],
        volatility_lookback_days=[10],
        max_volatility_annual_pct=[None],
        drawdown_lookback_days=[20],
        max_drawdown_pct=[None],
        leverage_trend_sma_days=[None, 20],
        max_leverage_volatility_annual_pct=[None],
        leverage_drawdown_lookback_days=[20],
        max_leverage_drawdown_pct=[None],
        risk_on_symbol=["TQQQ"],
        risk_on_weight=[0.5],
        neutral_weight=[0.5],
        risk_off_symbol=["CASH", "SQQQ"],
        risk_off_weight=[0.0, 0.25],
        target_volatility_annual_pct=[None],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=8,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "beta_exposure_router"
    assert payload["market_symbol"] == "QQQ"
    assert payload["leverage_symbol"] == "TQQQ"
    assert payload["hedge_symbol"] == "SQQQ"
    assert payload["search_space"]["candidate_count"] == 6
    assert payload["research_cost"]["walk_forward_candidate_count"] == 1
    assert payload["acceptance_gate"]["objective"] == "risk_managed_beta_alpha_vs_qqq_buy_hold"
    assert payload["pass_status"]["paper_ready_pass"] is False
    assert "index-1 QQQ" in " ".join(payload["anti_leakage"])
    assert payload["candidates"][0]["params"]["label"].startswith("beta:")


def test_beta_exposure_router_loads_non_cash_risk_off_symbol(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "QQQ": _sample_frame(100.0, 0.5),
        "TQQQ": _sample_frame(50.0, 0.9),
        "SQQQ": _sample_frame(80.0, -0.3),
        "GLD": _sample_frame(150.0, 0.1),
    }

    def fake_fetch_ohlcv(**kwargs):
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.beta_router_core.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "beta_router_gld_fixture")

    result = run_beta_exposure_router_research(
        spec_path,
        sample_workspace,
        market_symbol="QQQ",
        leverage_symbol="TQQQ",
        hedge_symbol="SQQQ",
        trend_sma_days=[20],
        momentum_lookback_days=[10],
        min_momentum_pct=[0.0],
        volatility_lookback_days=[10],
        max_volatility_annual_pct=[None],
        drawdown_lookback_days=[20],
        max_drawdown_pct=[None],
        leverage_trend_sma_days=[20],
        max_leverage_volatility_annual_pct=[None],
        leverage_drawdown_lookback_days=[20],
        max_leverage_drawdown_pct=[None],
        risk_on_symbol=["TQQQ"],
        risk_on_weight=[0.5],
        neutral_weight=[0.5],
        risk_off_symbol=["GLD"],
        risk_off_weight=[0.25],
        target_volatility_annual_pct=[None],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=1,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert "GLD" in payload["symbols"]
    assert any(item["symbol"] == "GLD" for item in payload["data_profile"]["per_symbol"])


def test_beta_router_label_round_trip_supports_hedge_asset() -> None:
    params = beta_params_from_label(
        "beta:sma200_mom60_min3_vol20_maxv25_dd120_maxdd15_"
        "levsma50_levmaxv80_levdd60_levmaxdd35_"
        "onTQQQ0.5_neuQQQ0.75_offSQQQ0.25_vt25"
    )

    assert params.risk_on_symbol == "TQQQ"
    assert params.leverage_trend_sma_days == 50
    assert params.max_leverage_volatility_annual_pct == 80
    assert params.leverage_drawdown_lookback_days == 60
    assert params.max_leverage_drawdown_pct == 35
    assert params.neutral_symbol == "QQQ"
    assert params.risk_off_symbol == "SQQQ"
    assert params.risk_off_weight == 0.25
    assert params.label.endswith("offSQQQ0.25_vt25")


def test_beta_target_weight_mapping_matches_python_reference(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "QQQ": _sample_frame(100.0, 0.5),
        "TQQQ": _sample_frame(50.0, 0.9),
        "SQQQ": _sample_frame(80.0, -0.3),
    }

    def fake_fetch_ohlcv(**kwargs):
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.beta_router_core.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "beta_target_fixture")
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["name"] = "beta_target_fixture"
    raw["universe"] = ["QQQ", "TQQQ", "SQQQ"]
    raw["portfolio"] = {
        "mode": "beta_exposure_router",
        "selected_route_label": (
            "beta:sma20_mom10_min0_vol10_maxvnone_dd20_maxddnone_"
            "levsmanone_levmaxvnone_levdd20_levmaxddnone_"
            "onTQQQ0.5_neuQQQ0.5_offCASH0_vtnone"
        ),
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
    }
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    result = run_beta_target_weight_mapping(
        spec_path,
        sample_workspace,
        market_symbol="QQQ",
        leverage_symbol="TQQQ",
        hedge_symbol="SQQQ",
    )

    assert result.parity_status == "pass"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "beta_target_weight_mapping"
    assert payload["summary"]["max_gross_exposure"] <= 1.0
    assert payload["parity_check"]["checks"]["selected_sessions"] == (
        result.reference_metrics.risk_on_days + result.reference_metrics.neutral_days
    )
    assert {"symbol", "target_weight", "rebalance_session", "state"} <= set(
        payload["target_weights"][0]
    )


def _sample_frame(start: float, drift: float) -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=320, freq="D", tz="UTC")
    close: list[float] = []
    value = start
    for index in range(320):
        cycle = 1.0 if index < 120 or index > 210 else -1.0
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
                "description": "Beta router fixture.",
                "timeframe": "daily",
                "universe": ["QQQ", "TQQQ"],
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
