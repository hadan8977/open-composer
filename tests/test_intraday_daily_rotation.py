from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.intraday_daily_rotation import (
    LLMIntradayDailyChoice,
    run_intraday_daily_rotation_research,
    run_llm_intraday_daily_rotation_selection,
    write_intraday_product_reflection,
)


def _make_intraday_frame(
    *,
    days: int,
    symbol_factor: float,
    daily_drift: float,
    opening_boost: float,
) -> pd.DataFrame:
    rows = []
    sessions = pd.bdate_range("2024-01-02", periods=days, tz="America/New_York")
    for day_index, session in enumerate(sessions):
        day_base = 100 + day_index * daily_drift + symbol_factor
        timestamps = [
            session.replace(hour=9, minute=30).tz_convert("UTC"),
            session.replace(hour=9, minute=31).tz_convert("UTC"),
            session.replace(hour=9, minute=32).tz_convert("UTC"),
            session.replace(hour=15, minute=59).tz_convert("UTC"),
        ]
        opens = [
            day_base,
            day_base + opening_boost,
            day_base + opening_boost + 0.4,
            day_base + opening_boost + 0.8,
        ]
        closes = [
            day_base + opening_boost + 0.2,
            day_base + opening_boost + 0.6,
            day_base + opening_boost + 1.0,
            day_base + opening_boost + 1.8,
        ]
        highs = [value + 0.3 for value in closes]
        lows = [value - 0.4 for value in opens]
        volumes = [
            1000 + day_index * 5,
            1100 + day_index * 5,
            1200 + day_index * 5,
            1300 + day_index * 5,
        ]
        for timestamp, open_, high, low, close, volume in zip(
            timestamps, opens, highs, lows, closes, volumes, strict=True
        ):
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": open_,
                    "high": high,
                    "low": low,
                    "close": close,
                    "volume": volume,
                }
            )
    return normalize_ohlcv(pd.DataFrame(rows))


def _write_spec(path: Path, *, llm_review: bool) -> None:
    path.write_text(
        yaml.safe_dump(
            {
                "name": path.stem,
                "description": "Intraday NASDAQ daily rotation fixture.",
                "timeframe": "1m",
                "universe": ["AAA", "BBB", "CCC"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 8)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 8)"]},
                "risk": {
                    "max_trades_per_day": 1,
                    "max_position_weight": 0.15,
                    "stop_loss_pct": 0.9,
                    "take_profit_pct": 1.4,
                },
                "costs": {"commission_pct": 0.005, "slippage_bps": 2.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
                "llm_review": {"enabled": llm_review, "model": "gpt-5.5" if llm_review else None},
                "required_capabilities": ["market.alpaca_bars"],
            }
        ),
        encoding="utf-8",
    )


def test_intraday_daily_rotation_research_builds_reports(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=40, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.2),
        "BBB": _make_intraday_frame(days=40, symbol_factor=4.0, daily_drift=0.3, opening_boost=0.6),
        "CCC": _make_intraday_frame(
            days=40, symbol_factor=-2.0, daily_drift=0.05, opening_boost=0.1
        ),
        "QQQ": _make_intraday_frame(
            days=40, symbol_factor=1.0, daily_drift=0.15, opening_boost=0.15
        ),
        "TQQQ": _make_intraday_frame(
            days=40, symbol_factor=2.0, daily_drift=0.25, opening_boost=0.2
        ),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = (
        sample_workspace / "strategy_specs" / "drafts" / "intraday_daily_rotation_fixture.yaml"
    )
    _write_spec(spec_path, llm_review=False)

    result = run_intraday_daily_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        lookback_days=[5],
        entry_after_bars=[1],
        top_n_values=[1],
        min_opening_return_pct=[0.0],
        min_prior_momentum_pct=[0.0],
        min_relative_volume=[0.8],
        market_gates=["none"],
        max_candidates=1,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    payload = result.json_path.read_text(encoding="utf-8")
    assert "benchmark_symbol" in payload
    assert "TQQQ" in payload
    assert "equal_weight_alpha" in payload
    assert result.best.out_of_sample.days > 0
    assert result.best.out_of_sample.benchmark_symbol == "TQQQ"


def test_llm_intraday_daily_rotation_selection_and_reflection(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=40, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.2),
        "BBB": _make_intraday_frame(days=40, symbol_factor=4.0, daily_drift=0.3, opening_boost=0.6),
        "CCC": _make_intraday_frame(
            days=40, symbol_factor=-2.0, daily_drift=0.05, opening_boost=0.1
        ),
        "QQQ": _make_intraday_frame(
            days=40, symbol_factor=1.0, daily_drift=0.15, opening_boost=0.15
        ),
        "TQQQ": _make_intraday_frame(
            days=40, symbol_factor=2.0, daily_drift=0.25, opening_boost=0.2
        ),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    class MockResponses:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            choice = LLMIntradayDailyChoice(
                selected_label="lb5_entry1_top1_open0_mom0_rv0.8_none",
                confidence=0.9,
                rationale="BBB had the best prompt-visible training evidence.",
                expected_risks=["Synthetic fixture only."],
                rejected_labels=[],
            )
            return SimpleNamespace(
                output=[
                    SimpleNamespace(
                        type="message",
                        content=[SimpleNamespace(type="output_text", parsed=choice)],
                    )
                ]
            )

    spec_path = (
        sample_workspace / "strategy_specs" / "drafts" / "intraday_daily_rotation_llm_fixture.yaml"
    )
    _write_spec(spec_path, llm_review=True)

    result = run_llm_intraday_daily_rotation_selection(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        lookback_days=[5],
        entry_after_bars=[1],
        top_n_values=[1],
        min_opening_return_pct=[0.0],
        min_prior_momentum_pct=[0.0],
        min_relative_volume=[0.8],
        market_gates=["none"],
        max_candidates=1,
        client=SimpleNamespace(responses=MockResponses()),
        model="mock",
    )

    assert result.report_path.exists()
    assert result.prompt_path.exists()
    prompt = result.prompt_path.read_text(encoding="utf-8")
    assert "final out-of-sample and full-window metrics" in prompt
    assert result.choice.selected_label == "lb5_entry1_top1_open0_mom0_rv0.8_none"
    reflection_path = write_intraday_product_reflection(
        sample_workspace,
        pure_report=result.report_path,
        llm_report=result.report_path,
    )
    assert reflection_path.exists()
