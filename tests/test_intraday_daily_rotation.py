from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml
from typer.testing import CliRunner

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.adapters.execution.adaptive_intraday_target_weights import (
    run_adaptive_intraday_target_weight_mapping,
)
from open_composer.adapters.execution.hybrid_target_weights import (
    run_hybrid_target_weight_mapping,
)
from open_composer.cli import app
from open_composer.research.adaptive_intraday_router import (
    LLMAdaptiveRouterChoice,
    run_adaptive_intraday_router_research,
    run_adaptive_intraday_router_scan,
    run_llm_adaptive_intraday_router_selection,
)
from open_composer.research.adaptive_intraday_router_core import (
    _base_kwargs,
    _parse_route_label,
)
from open_composer.research.hybrid_adaptive_router import (
    hybrid_params_from_label,
    run_hybrid_adaptive_router_research,
)
from open_composer.research.hybrid_news_evidence import (
    run_hybrid_news_marginal_lift_research,
)
from open_composer.research.intraday_daily_rotation import (
    IntradayDailyCandidate,
    IntradayDailyMetrics,
    IntradayDailyParams,
    LLMIntradayDailyChoice,
    _pass_status,
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


def _make_hybrid_frame(
    *,
    days: int,
    start_price: float,
    daily_return: float,
    intraday_return: float = 0.001,
) -> pd.DataFrame:
    rows = []
    sessions = pd.bdate_range("2024-01-02", periods=days, tz="America/New_York")
    open_price = start_price
    for session in sessions:
        close_price = open_price * (1 + intraday_return)
        timestamps = [
            session.replace(hour=9, minute=30).tz_convert("UTC"),
            session.replace(hour=9, minute=31).tz_convert("UTC"),
            session.replace(hour=15, minute=58).tz_convert("UTC"),
            session.replace(hour=15, minute=59).tz_convert("UTC"),
        ]
        prices = [
            open_price,
            open_price * (1 + intraday_return * 0.25),
            open_price * (1 + intraday_return * 0.75),
            close_price,
        ]
        for offset, (timestamp, price) in enumerate(zip(timestamps, prices, strict=True)):
            rows.append(
                {
                    "timestamp": timestamp,
                    "open": price,
                    "high": price * 1.001,
                    "low": price * 0.999,
                    "close": price,
                    "volume": 1000 + offset * 100,
                }
            )
        open_price *= 1 + daily_return
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


def test_intraday_daily_research_pass_respects_acceptance_gate() -> None:
    metrics = IntradayDailyMetrics(
        days=60,
        start_date="2026-01-01",
        end_date="2026-03-31",
        total_return_pct=12.0,
        annualized_return_pct=55.0,
        sharpe_ratio=1.2,
        max_drawdown_pct=-6.0,
        traded_days=40,
        round_trips=40,
        average_selected_count=1.0,
        win_day_pct=55.0,
        equal_weight_intraday_return_pct=2.0,
        equal_weight_intraday_annualized_pct=8.0,
        alpha_vs_equal_weight_annualized_pct=47.0,
        benchmark_symbol="TQQQ",
        benchmark_intraday_return_pct=1.0,
        benchmark_intraday_annualized_pct=5.0,
        alpha_vs_benchmark_intraday_annualized_pct=50.0,
        benchmark_buy_hold_return_pct=1.0,
        benchmark_buy_hold_annualized_pct=5.0,
        alpha_vs_benchmark_buy_hold_annualized_pct=50.0,
        universe_equal_weight_buy_hold_pct=2.0,
        best_symbol_buy_hold_pct=8.0,
        best_symbol="AAA",
        alpha_vs_best_symbol_buy_hold_pct=4.0,
    )
    candidate = IntradayDailyCandidate(
        rank=1,
        params=IntradayDailyParams(
            selection_style="opening_momentum",
            lookback_days=5,
            entry_after_bars=1,
            top_n=1,
            min_opening_return_pct=0.0,
            min_prior_momentum_pct=0.0,
            min_relative_volume=0.8,
        ),
        score=1.0,
        train=metrics,
        out_of_sample=metrics,
        full_window=metrics,
        quality_flags=[],
    )

    assert _pass_status(candidate, "equal_weight_alpha")["research_pass"] is True
    assert (
        _pass_status(candidate, "equal_weight_alpha", acceptance_passed=False)["research_pass"]
        is False
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


def test_adaptive_intraday_router_builds_internal_route_report(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.2),
        "BBB": _make_intraday_frame(days=42, symbol_factor=4.0, daily_drift=0.3, opening_boost=0.6),
        "CCC": _make_intraday_frame(
            days=42, symbol_factor=-2.0, daily_drift=0.05, opening_boost=0.1
        ),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.15, opening_boost=0.15
        ),
        "TQQQ": _make_intraday_frame(
            days=42, symbol_factor=2.0, daily_drift=0.25, opening_boost=0.2
        ),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = (
        sample_workspace / "strategy_specs" / "drafts" / "adaptive_intraday_router_fixture.yaml"
    )
    _write_spec(spec_path, llm_review=True)

    result = run_adaptive_intraday_router_research(
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
        selection_styles=["opening_momentum", "opening_reversal"],
        max_opening_return_pct=[-0.2],
        market_gates=["none"],
        top_per_family=1,
        max_route_candidates=4,
        max_base_candidates=4,
        walk_forward_folds=2,
    )

    assert result.report_path.exists()
    assert result.json_path.name == "adaptive_intraday_router_fixture-adaptive-intraday-router.json"
    assert result.report_path.name == "adaptive_intraday_router_fixture-adaptive-intraday-router.md"
    payload = result.json_path.read_text(encoding="utf-8")
    assert "adaptive_intraday_internal_router" in payload
    assert result.best.route.sub_strategies


def test_adaptive_intraday_router_cli_reports_research_cost(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.2),
        "BBB": _make_intraday_frame(days=42, symbol_factor=4.0, daily_drift=0.3, opening_boost=0.6),
        "CCC": _make_intraday_frame(
            days=42, symbol_factor=-2.0, daily_drift=0.05, opening_boost=0.1
        ),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.15, opening_boost=0.15
        ),
        "TQQQ": _make_intraday_frame(
            days=42, symbol_factor=2.0, daily_drift=0.25, opening_boost=0.2
        ),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr("open_composer.cli.project_root", lambda: sample_workspace)
    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "adaptive_router_cli.yaml"
    _write_spec(spec_path, llm_review=True)

    result = CliRunner().invoke(
        app,
        [
            "strategy",
            "adaptive-intraday-router",
            str(spec_path),
            "--symbols",
            "AAA,BBB,CCC",
            "--data-source",
            "alpaca",
            "--benchmark-symbol",
            "TQQQ",
            "--market-symbol",
            "QQQ",
            "--lookback-days",
            "5",
            "--entry-after-bars",
            "1",
            "--top-n",
            "1",
            "--min-opening-return-pct",
            "0",
            "--min-prior-momentum-pct",
            "0",
            "--min-relative-volume",
            "0.8",
            "--selection-style",
            "opening_momentum",
            "--selection-style",
            "opening_reversal",
            "--max-opening-return-pct",
            "-0.2",
            "--market-gate",
            "none",
            "--top-per-family",
            "1",
            "--max-route-candidates",
            "4",
            "--max-base-candidates",
            "4",
            "--walk-forward-folds",
            "2",
        ],
        catch_exceptions=False,
    )

    assert result.exit_code == 0
    assert "adaptive intraday router complete" in result.output
    assert "candidates=" in result.output
    assert "walk_forward_candidates=" in result.output
    assert "estimated_passes=" in result.output


def test_adaptive_intraday_router_maps_cli_candidate_limit() -> None:
    assert _base_kwargs({"max_base_candidates": 576})["max_candidates"] == 576
    assert _base_kwargs({"max_candidates": 32, "max_base_candidates": 576})["max_candidates"] == 32


def test_adaptive_intraday_router_parses_market_gate_route_labels() -> None:
    reversal = _parse_route_label(
        "open_momentum:lb3_entry1_top1_open0_mom0_rv1_qopen_positive_reversal_maxopen0_maxmomnone"
    )
    assert reversal.market_gate == "qqq_open_positive"
    assert reversal.selection_style == "opening_reversal"
    assert reversal.max_opening_return_pct == 0.0
    assert reversal.max_prior_momentum_pct is None

    prior_negative = _parse_route_label("lb5_entry1_top2_open0_mom2_rv0.8_qprior_negative")
    assert prior_negative.market_gate == "qqq_prior_negative"
    assert prior_negative.selection_style == "opening_momentum"

    mixed = _parse_route_label("lb5_entry1_top2_open0_mom2_rv0.8_qopen_positive_prior_negative")
    assert mixed.market_gate == "qqq_open_positive_prior_negative"

    combined = _parse_route_label("lb5_entry1_top2_open0_mom2_rv0.8_qopen_and_prior_positive")
    assert combined.market_gate == "qqq_open_and_prior_positive"


def test_adaptive_intraday_router_long_short_uses_short_leg_returns(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.5),
        "BBB": _make_intraday_frame(
            days=42, symbol_factor=4.0, daily_drift=-0.3, opening_boost=-0.7
        ),
        "CCC": _make_intraday_frame(days=42, symbol_factor=2.0, daily_drift=0.0, opening_boost=0.1),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.05, opening_boost=0.05
        ),
        "TQQQ": _make_intraday_frame(
            days=42, symbol_factor=2.0, daily_drift=0.08, opening_boost=0.08
        ),
    }
    frames["BBB"]["close"] = frames["BBB"]["open"] - 0.8
    frames["BBB"]["high"] = frames["BBB"]["open"] + 0.1
    frames["BBB"]["low"] = frames["BBB"]["close"] - 0.1

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "adaptive_long_short.yaml"
    _write_spec(spec_path, llm_review=False)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["position_direction"] = "long_short"
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = run_adaptive_intraday_router_research(
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
        selection_styles=["opening_momentum"],
        market_gates=["none"],
        max_candidates=1,
        walk_forward_folds=2,
    )

    full = result.best.full_window.base
    assert full.average_selected_count == 2
    assert full.round_trips >= full.traded_days * 2
    assert full.total_return_pct > 0
    report = result.report_path.read_text(encoding="utf-8")
    assert "Long/short specs select a long basket and a separate short basket" in report


def test_adaptive_intraday_router_scan_emits_signed_long_short_signals(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.5),
        "BBB": _make_intraday_frame(
            days=42, symbol_factor=4.0, daily_drift=-0.3, opening_boost=-0.7
        ),
        "CCC": _make_intraday_frame(days=42, symbol_factor=2.0, daily_drift=0.0, opening_boost=0.1),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.05, opening_boost=0.05
        ),
    }
    frames["BBB"]["close"] = frames["BBB"]["open"] - 0.8
    frames["BBB"]["high"] = frames["BBB"]["open"] + 0.1
    frames["BBB"]["low"] = frames["BBB"]["close"] - 0.1

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "adaptive_scan_long_short.yaml"
    _write_spec(spec_path, llm_review=False)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["position_direction"] = "long_short"
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 2,
        "gross_exposure_limit": 0.4,
        "max_symbol_weight": 0.2,
        "same_day_flatten": True,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_momentum:lb5_entry1_top1_open0_mom0_rv0.8_none",
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = run_adaptive_intraday_router_scan(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="QQQ",
        market_symbol="QQQ",
        emit_news_packet=False,
    )

    assert len(result.signals) == 2
    assert {plan.side for plan in result.signal_plans} == {"long", "short"}
    short_signal = next(signal for signal in result.signals if signal.target_weight < 0)
    assert short_signal.side == "sell"
    assert "side=short" in short_signal.conditions
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    weights = [row["weight"] for row in payload["signal_plans"]]
    assert max(weights) > 0
    assert min(weights) < 0


def test_adaptive_intraday_target_weight_mapping_writes_long_short_artifacts(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.5),
        "BBB": _make_intraday_frame(
            days=42, symbol_factor=4.0, daily_drift=-0.3, opening_boost=-0.7
        ),
        "CCC": _make_intraday_frame(days=42, symbol_factor=2.0, daily_drift=0.0, opening_boost=0.1),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.05, opening_boost=0.05
        ),
    }
    frames["BBB"]["close"] = frames["BBB"]["open"] - 0.8
    frames["BBB"]["high"] = frames["BBB"]["open"] + 0.1
    frames["BBB"]["low"] = frames["BBB"]["close"] - 0.1

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "adaptive_target_long_short.yaml"
    _write_spec(spec_path, llm_review=False)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["position_direction"] = "long_short"
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 2,
        "gross_exposure_limit": 0.4,
        "max_symbol_weight": 0.2,
        "same_day_flatten": True,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "lb5_entry1_top1_open0_mom0_rv0.8_none",
    }
    spec_path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    result = run_adaptive_intraday_target_weight_mapping(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="QQQ",
        market_symbol="QQQ",
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.parity_status == "pass"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    weights = [row["target_weight"] for row in payload["target_weights"]]
    assert payload["mode"] == "adaptive_intraday_target_weight_mapping"
    assert payload["portfolio_mode"] == "adaptive_intraday_internal_router"
    assert max(weights) > 0
    assert min(weights) < 0
    assert payload["summary"]["max_gross_exposure"] <= 0.4
    assert payload["router_execution_artifacts"]["router_validation"].endswith(
        "-router-validation.json"
    )


def test_hybrid_adaptive_router_research_requires_positive_tqqq_alpha(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.006),
        "BBB": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.001),
        "CCC": _make_hybrid_frame(days=130, start_price=100.0, daily_return=-0.001),
        "QQQ": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.0015),
        "TQQQ": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.002),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "hybrid_router_fixture.yaml"
    _write_spec(spec_path, llm_review=True)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["name"] = "hybrid_router_fixture"
    raw["portfolio"] = {
        "mode": "hybrid_adaptive_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_to_open:lb5_top1_nogate_min0_w1",
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["risk"]["max_trades_per_day"] = 1
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    result = run_hybrid_adaptive_router_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        holding_modes=["open_to_open"],
        momentum_lookback_days=[5],
        top_n_values=[1],
        market_sma_days=[None],
        min_momentum_pct=[0.0],
        max_position_weight=[1.0],
        walk_forward_folds=2,
        walk_forward_top_k=1,
        max_candidates=1,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "hybrid_adaptive_router"
    assert payload["acceptance_gate"]["train_alpha_vs_tqqq_buy_hold_annualized_pct"] > 0
    assert payload["acceptance_gate"]["oos_alpha_vs_tqqq_buy_hold_annualized_pct"] > 0
    assert payload["acceptance_gate"]["full_alpha_vs_tqqq_buy_hold_annualized_pct"] > 0
    assert payload["candidates"][0]["train"]["market_symbol"] == "QQQ"
    assert payload["candidates"][0]["train"]["round_trips"] > 0
    assert "commission and slippage" in json.dumps(payload["search_space"])


def test_hybrid_route_label_parser_round_trips_selected_route() -> None:
    params = hybrid_params_from_label("open_to_open:lb20_top1_qsm100_min5_w1")

    assert params.label == "open_to_open:lb20_top1_qsm100_min5_w1"
    assert params.market_sma_days == 100
    assert params.min_momentum_pct == 5.0


def test_hybrid_route_label_parser_supports_risk_controls() -> None:
    label = (
        "open_to_open:lb20_top3_qsm100_min5_w0.25_g0.6_scoreradj_radj20_qoff0.5_"
        "vol20t20_mdd20p8s0.5"
    )
    params = hybrid_params_from_label(label)

    assert params.label == label
    assert params.top_n == 3
    assert params.max_position_weight == 0.25
    assert params.gross_exposure_limit == 0.6
    assert params.momentum_score_mode == "risk_adjusted"
    assert params.risk_adjustment_lookback_days == 20
    assert params.market_below_sma_scale == 0.5
    assert params.volatility_lookback_days == 20
    assert params.target_volatility_annual_pct == 20.0
    assert params.market_drawdown_lookback_days == 20
    assert params.market_drawdown_brake_pct == 8.0
    assert params.brake_exposure_scale == 0.5


def test_hybrid_news_marginal_lift_writes_pit_evidence(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.006),
        "BBB": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.001),
        "CCC": _make_hybrid_frame(days=130, start_price=100.0, daily_return=-0.001),
        "QQQ": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.0015),
        "TQQQ": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.002),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "hybrid_news_fixture.yaml"
    _write_spec(spec_path, llm_review=True)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["name"] = "hybrid_news_fixture"
    raw["portfolio"] = {
        "mode": "hybrid_adaptive_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_to_open:lb5_top1_nogate_min0_w1",
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["risk"]["max_trades_per_day"] = 1
    raw["required_capabilities"] = ["market.alpaca_bars", "news.gdelt"]
    raw["factors"] = {
        "news_sentiment_gate": {
            "source": "feature_packet",
            "path": "feature_logs/hybrid_news_fixture.jsonl",
            "field": "sentiment_score",
            "default": 0.0,
        }
    }
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    result = run_hybrid_news_marginal_lift_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        lookback_days=5,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.feature_packet_path.exists()
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "hybrid_news_marginal_lift"
    assert payload["marginal_lift"]["llm_contribution_pass"] is False
    assert payload["feature_packets"]["inspection"]["point_in_time_status"] == "complete"
    packet = json.loads(result.feature_packet_path.read_text(encoding="utf-8").splitlines()[0])
    assert packet["model"] == "local-rule-news-v1"
    assert packet["input_hash"].startswith("sha256:")
    assert packet["prompt_hash"].startswith("sha256:")
    assert packet["evidence"]["marginal_lift_metric"]
    assert packet["features"]["trial_news_only"] is True


def test_hybrid_target_weight_mapping_matches_python_reference(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.006),
        "BBB": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.001),
        "CCC": _make_hybrid_frame(days=130, start_price=100.0, daily_return=-0.001),
        "QQQ": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.0015),
        "TQQQ": _make_hybrid_frame(days=130, start_price=100.0, daily_return=0.002),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "hybrid_target_fixture.yaml"
    _write_spec(spec_path, llm_review=True)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["name"] = "hybrid_target_fixture"
    raw["portfolio"] = {
        "mode": "hybrid_adaptive_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 1.0,
        "max_symbol_weight": 1.0,
        "same_day_flatten": False,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_to_open:lb5_top1_nogate_min0_w1",
    }
    raw["risk"]["max_position_weight"] = 1.0
    raw["risk"]["max_trades_per_day"] = 1
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    result = run_hybrid_target_weight_mapping(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.parity_status == "pass"
    assert result.nonzero_target_rows == result.reference_metrics.round_trips
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "hybrid_target_weight_mapping"
    assert payload["portfolio_mode"] == "hybrid_adaptive_router"
    assert payload["parity_check"]["status"] == "pass"
    assert payload["summary"]["max_gross_exposure"] <= 1.0
    assert {"symbol", "target_weight", "rebalance_session"} <= set(payload["target_weights"][0])
    assert payload["rebalance_intents"]


def test_llm_adaptive_intraday_router_can_select_non_top_route(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.2),
        "BBB": _make_intraday_frame(days=42, symbol_factor=4.0, daily_drift=0.3, opening_boost=0.6),
        "CCC": _make_intraday_frame(
            days=42, symbol_factor=-2.0, daily_drift=0.05, opening_boost=0.1
        ),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.15, opening_boost=0.15
        ),
        "TQQQ": _make_intraday_frame(
            days=42, symbol_factor=2.0, daily_drift=0.25, opening_boost=0.2
        ),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    class MockResponses:
        def parse(self, **kwargs: object) -> object:
            prompt = kwargs["input"][1]["content"]  # type: ignore[index]
            route_label = json.loads(prompt)["candidates"][0]["route_label"]
            choice = LLMAdaptiveRouterChoice(
                selected_label=route_label,
                confidence=0.8,
                rationale="Selected the prompt-visible internal route.",
                news_usage_plan="No news adjustment without PIT packets.",
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

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "adaptive_intraday_router_llm.yaml"
    _write_spec(spec_path, llm_review=True)

    result = run_llm_adaptive_intraday_router_selection(
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
        selection_styles=["opening_momentum", "opening_reversal"],
        max_opening_return_pct=[-0.2],
        market_gates=["none"],
        top_per_family=1,
        max_route_candidates=4,
        max_base_candidates=4,
        client=SimpleNamespace(responses=MockResponses()),
        model="mock",
    )

    assert result.report_path.exists()
    assert result.prompt_path.exists()
    assert result.choice.news_usage_plan == "No news adjustment without PIT packets."


def test_adaptive_intraday_router_scan_writes_signals_and_news_packets(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frames = {
        "AAA": _make_intraday_frame(days=42, symbol_factor=0.0, daily_drift=0.2, opening_boost=0.2),
        "BBB": _make_intraday_frame(days=42, symbol_factor=4.0, daily_drift=0.3, opening_boost=0.6),
        "CCC": _make_intraday_frame(
            days=42, symbol_factor=-2.0, daily_drift=0.05, opening_boost=0.1
        ),
        "QQQ": _make_intraday_frame(
            days=42, symbol_factor=1.0, daily_drift=0.15, opening_boost=0.15
        ),
        "TQQQ": _make_intraday_frame(
            days=42, symbol_factor=2.0, daily_drift=0.25, opening_boost=0.2
        ),
    }

    def fake_fetch_ohlcv(**kwargs):
        return frames[kwargs["symbol"]].copy()

    monkeypatch.setattr(
        "open_composer.research.intraday_daily_rotation.fetch_ohlcv", fake_fetch_ohlcv
    )

    spec_path = (
        sample_workspace / "strategy_specs" / "drafts" / "adaptive_intraday_router_scan.yaml"
    )
    _write_spec(spec_path, llm_review=True)
    raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    raw["portfolio"] = {
        "mode": "adaptive_intraday_internal_router",
        "max_symbols_per_day": 1,
        "gross_exposure_limit": 0.15,
        "max_symbol_weight": 0.15,
        "same_day_flatten": True,
        "duplicate_signal_policy": "stable_signal_id",
        "selected_route_label": "open_momentum:lb5_entry1_top1_open0_mom0_rv0.8_none",
    }
    raw["factors"] = {
        "news_sentiment_gate": {
            "source": "feature_packet",
            "path": "feature_logs/adaptive_router_news.jsonl",
            "field": "sentiment_score",
            "default": 0.0,
            "description": "Replayable news sentiment gate.",
        }
    }
    spec_path.write_text(yaml.safe_dump(raw), encoding="utf-8")

    result = run_adaptive_intraday_router_scan(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB", "CCC"],
        data_source="alpaca",
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        scan_date="2024-02-28",
    )

    assert result.signal_log_path.exists()
    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.signals
    assert result.signals[0].symbol == "BBB"
    assert result.signals[0].source == "adaptive_router_scan"
    assert result.feature_packet_path is not None
    assert result.feature_packet_path.exists()
    packet = json.loads(result.feature_packet_path.read_text(encoding="utf-8").splitlines()[0])
    assert packet["features"]["trial_news_only"] is True
    assert packet["features"]["sentiment_score"] == 0.0
    assert packet["input_hash"].startswith("sha256:")
