from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.core_beta_satellite_router import (
    core_beta_satellite_params_from_label,
    core_route_label,
    run_core_beta_satellite_router_research,
)


def test_core_beta_satellite_router_reports_ablation_and_pit_timing(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    symbols = [
        "QQQ",
        "TQQQ",
        "SQQQ",
        "SMH",
        "NVDA",
        "AVGO",
        "AMD",
        "AMAT",
        "QCOM",
        "MU",
        "LRCX",
        "ASML",
        "KLAC",
        "MRVL",
        "INTC",
        "TXN",
        "ADI",
        "NXPI",
        "MPWR",
    ]
    frames = {
        symbol: _sample_frame(100.0 + index, 0.12 + index * 0.01)
        for index, symbol in enumerate(symbols)
    }
    frames["SQQQ"] = _sample_frame(80.0, -0.05)

    def fake_fetch_ohlcv(**kwargs):
        symbol = str(kwargs["symbol"]).upper()
        return normalize_ohlcv(frames[symbol].copy())

    monkeypatch.setattr(
        "open_composer.research.core_beta_satellite_core.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "core_beta_satellite_fixture")

    result = run_core_beta_satellite_router_research(
        spec_path,
        sample_workspace,
        data_source="alpaca",
        core_variant=["active75"],
        universe_mode=["semiconductor"],
        satellite_budget=[0.0, 0.1],
        satellite_momentum_days=[20],
        confirmation_days=[5],
        top_n=[2],
        max_symbol_weight=[0.1],
        score_mode=["raw"],
        theme_gate_symbol=["SMH"],
        theme_sma_days=[30],
        theme_momentum_days=[10],
        min_theme_momentum_pct=[0.0],
        satellite_volatility_lookback_days=[20],
        target_satellite_volatility_pct=[None],
        walk_forward_top_k=1,
        max_candidates=2,
    )

    assert result.report_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "core_beta_satellite_router"
    assert payload["search_space"]["candidate_count"] == 2
    assert payload["pass_status"]["paper_ready_pass"] is False
    assert "core-only ablation" in " ".join(payload["anti_leakage"])
    assert payload["selected_candidate"]["params"]["label"].startswith("core_beta_sat:")
    assert "satellite_marginal_annualized_pct" in payload["selected_candidate"]["full_window"]


def test_core_beta_satellite_label_round_trips() -> None:
    params = core_beta_satellite_params_from_label(
        "core_beta_sat:coreactive75_usemiconductor_sat0.1_mom20_conf5_top2_"
        "maxw0.1_scoreraw_gateSMH_gsma50_gmom20_gmin0_vol20_tvolnone"
    )

    assert params.core_variant == "active75"
    assert params.universe_mode == "semiconductor"
    assert params.theme_gate_symbol == "SMH"
    assert params.satellite_budget == 0.1
    assert params.label.endswith("gateSMH_gsma50_gmom20_gmin0_vol20_tvolnone")


def test_core_beta_satellite_core_variant_changes_beta_route() -> None:
    active75 = core_beta_satellite_params_from_label(
        "core_beta_sat:coreactive75_usemiconductor_sat0.1_mom20_conf5_top2_"
        "maxw0.1_scoreraw_gateSMH_gsma50_gmom20_gmin0_vol20_tvolnone"
    )
    aggressive100 = core_beta_satellite_params_from_label(
        "core_beta_sat:coreaggressive100_usemiconductor_sat0.1_mom20_conf5_top2_"
        "maxw0.1_scoreraw_gateSMH_gsma50_gmom20_gmin0_vol20_tvolnone"
    )

    assert "onTQQQ0.75_neuQQQ0.75" in active75.core_route_label
    assert "onTQQQ1_neuQQQ1" in aggressive100.core_route_label
    assert active75.core_route_label == core_route_label("active75")


def _sample_frame(start: float, drift: float) -> pd.DataFrame:
    timestamps = pd.date_range("2022-01-03", periods=900, freq="B", tz="UTC")
    close: list[float] = []
    value = start
    for index in range(len(timestamps)):
        cycle = 1.0 if index < 360 or index > 520 else -0.6
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
                "description": "Core beta satellite fixture.",
                "timeframe": "daily",
                "universe": ["QQQ", "TQQQ", "SQQQ", "SMH", "NVDA"],
                "lifecycle": "draft",
                "entry": {"all": ["close > sma(close, 20)"], "any": []},
                "exit": {"all": [], "any": ["close < sma(close, 20)"]},
                "risk": {"max_position_weight": 1.0, "max_trades_per_day": 5},
                "portfolio": {
                    "mode": "core_beta_satellite_router",
                    "selected_route_label": (
                        "core_beta_sat:coreactive75_usemiconductor_sat0.1_mom20_conf5_top2_"
                        "maxw0.1_scoreraw_gateSMH_gsma50_gmom20_gmin0_vol20_tvolnone"
                    ),
                    "max_symbols_per_day": 5,
                    "gross_exposure_limit": 1.0,
                    "max_symbol_weight": 1.0,
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
