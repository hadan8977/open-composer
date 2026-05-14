from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.rotation import run_rotation_research


def test_rotation_research_uses_point_in_time_universe_grid(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))
    sample["timestamp"] = pd.date_range("2024-01-01", periods=len(sample), freq="D", tz="UTC")

    def fake_fetch_ohlcv(**kwargs):
        frame = sample.copy()
        if kwargs["symbol"] == "BBB":
            frame["close"] = frame["close"] * pd.Series(
                [1 + index * 0.002 for index in range(len(frame))]
            )
            frame["open"] = frame["open"] * pd.Series(
                [1 + index * 0.002 for index in range(len(frame))]
            )
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "rotation_daily.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "rotation_daily",
                "description": "Daily rotation test.",
                "timeframe": "daily",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 3)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 5.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=1,
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.best.params.lookback_bars == 3
    assert result.best.full_window.rebalances > 0
    report = result.report_path.read_text(encoding="utf-8")
    assert "point-in-time" in report.lower()
    assert "equal-weight" in report

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["candidate_count"] == 1
    assert payload["mode"] == "pure_price_rotation"
    assert payload["research_cost"]["candidate_count"] == 1
    assert payload["research_cost"]["walk_forward_candidate_count"] == 1
    assert payload["runtime_seconds"]["total"] >= 0
    assert payload["data_profile"]["data_as_of"] is not None
    assert payload["search_space"]["candidate_count"] == 1
    assert "equal-weight" in payload["selection_objective"]
    assert isinstance(payload["acceptance_gate"]["passed"], bool)
    assert "out_of_sample" in payload["candidates"][0]
    assert (
        payload["candidates"][0]["out_of_sample"]["bars"]
        < payload["candidates"][0]["full_window"]["bars"]
    )


def test_rotation_research_walk_forward_top_k_reduces_reported_cost(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))
    sample["timestamp"] = pd.date_range("2024-01-01", periods=len(sample), freq="D", tz="UTC")

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(sample.copy())

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "rotation_top_k_daily.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "rotation_top_k_daily",
                "description": "Daily rotation top-k test.",
                "timeframe": "daily",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 3)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3, 4],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=2,
        walk_forward_folds=2,
        walk_forward_top_k=1,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["research_cost"]["candidate_count"] == 2
    assert payload["research_cost"]["walk_forward_candidate_count"] == 1
    assert payload["research_cost"]["walk_forward_top_k"] == 1
    assert payload["research_cost"]["estimated_total_backtest_passes"] == 12


def test_rotation_research_can_prioritize_primary_buy_hold_alpha(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    timestamps = pd.date_range("2024-01-01", periods=30, freq="D", tz="UTC")
    base = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index for index in range(30)],
            "high": [101.0 + index for index in range(30)],
            "low": [99.0 + index for index in range(30)],
            "close": [100.0 + index for index in range(30)],
            "volume": [1_000_000] * 30,
        }
    )

    def fake_fetch_ohlcv(**kwargs):
        frame = base.copy()
        if kwargs["symbol"] == "BBB":
            frame["open"] = [100.0] * 30
            frame["close"] = [100.0] * 30
            frame.loc[10:13, ["open", "close"]] = [145.0, 150.0]
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "primary_rotation_daily.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "primary_rotation_daily",
                "description": "Daily rotation primary-alpha objective test.",
                "timeframe": "daily",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 3)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[1, 10],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=2,
        objective="primary_alpha",
        start="2024-01-05",
        end="2024-01-25",
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["research_window"] == {"start": "2024-01-05", "end": "2024-01-25"}
    assert "primary symbol" in payload["selection_objective"]
    assert result.best.score == pytest.approx(
        result.best.train.alpha_vs_primary_pct
        + (result.best.train.sharpe_ratio or 0.0) * 10
        - abs(min(result.best.train.max_drawdown_pct, 0.0)) * 0.25
        - result.best.train.average_turnover_pct * 0.03
    )
    assert "oos_no_alpha_vs_primary" in payload["candidates"][0]["quality_flags"]


def test_rotation_research_can_anchor_primary_symbol(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    timestamps = pd.date_range("2024-01-01", periods=24, freq="D", tz="UTC")
    base = pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": [100.0 + index for index in range(24)],
            "high": [101.0 + index for index in range(24)],
            "low": [99.0 + index for index in range(24)],
            "close": [100.0 + index for index in range(24)],
            "volume": [1_000_000] * 24,
        }
    )

    def fake_fetch_ohlcv(**kwargs):
        frame = base.copy()
        if kwargs["symbol"] == "BBB":
            frame["open"] = frame["open"] * 1.01
            frame["close"] = frame["close"] * 1.01
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "anchored_rotation_daily.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "anchored_rotation_daily",
                "description": "Daily anchored rotation test.",
                "timeframe": "daily",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 3)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 0.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=1,
        objective="primary_alpha",
        primary_hold_margin_pct=[5.0],
        primary_min_momentum_pct=[0.0],
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["candidates"][0]["params"]["primary_hold_margin_pct"] == 5.0
    assert result.best.full_window.alpha_vs_primary_pct == pytest.approx(0.0, abs=0.2)


def test_rotation_research_accepts_intraday_timeframe(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(sample.copy())

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "rotation_1h.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "rotation_1h",
                "description": "1h rotation test.",
                "timeframe": "1h",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "entry": {"all": ["close > ema(close, 3)"], "any": []},
                "exit": {"all": [], "any": ["close < ema(close, 3)"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 5.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=1,
    )

    assert result.best.full_window.bars == len(sample) - 3


def test_rotation_research_requires_explicit_feature_gate_for_llm_factors(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))
    sample["timestamp"] = pd.date_range("2024-01-01", periods=len(sample), freq="D", tz="UTC")

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(sample.copy())

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "llm_rotation_daily.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "llm_rotation_daily",
                "description": "Daily LLM-gated rotation test.",
                "timeframe": "daily",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "factors": {
                    "theme_score": {
                        "source": "llm_feature",
                        "path": "feature_logs/theme.jsonl",
                        "field": "theme_score",
                        "default": 0.0,
                    },
                },
                "entry": {"all": ["theme_score >= 0.7"], "any": []},
                "exit": {"all": [], "any": ["theme_score < 0.5"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 5.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="--feature-gate"):
        run_rotation_research(
            spec_path,
            sample_workspace,
            symbols=["AAA", "BBB"],
            lookback_bars=[3],
            rebalance_bars=[2],
            top_n_values=[1],
            min_momentum_pct=[0.0],
            max_candidates=1,
        )


def test_rotation_research_feature_gate_uses_symbol_specific_packets(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))
    sample = sample.head(12).copy()
    sample["timestamp"] = pd.date_range("2024-01-01", periods=len(sample), freq="D", tz="UTC")

    def fake_fetch_ohlcv(**kwargs):
        frame = sample.copy()
        if kwargs["symbol"] == "BBB":
            frame["close"] = frame["close"] * pd.Series(
                [1 + index * 0.02 for index in range(len(frame))]
            )
            frame["open"] = frame["open"] * pd.Series(
                [1 + index * 0.02 for index in range(len(frame))]
            )
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)
    feature_path = sample_workspace / "feature_logs" / "theme.jsonl"
    feature_path.parent.mkdir(parents=True, exist_ok=True)
    feature_path.write_text(
        "\n".join(
            [
                (
                    '{"timestamp":"2024-01-01T00:00:00Z",'
                    '"published_at":"2024-01-01T00:00:00Z",'
                    '"fetched_at":"2024-01-01T00:00:00Z",'
                    '"source":"llm","symbol":"AAA","dedupe_key":"aaa",'
                    '"schema_version":"1","features":{"theme_score":0.8}}'
                ),
                (
                    '{"timestamp":"2024-01-01T00:00:00Z",'
                    '"published_at":"2024-01-01T00:00:00Z",'
                    '"fetched_at":"2024-01-01T00:00:00Z",'
                    '"source":"llm","symbol":"BBB","dedupe_key":"bbb",'
                    '"schema_version":"1","features":{"theme_score":0.1}}'
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    spec_path = sample_workspace / "strategy_specs" / "drafts" / "feature_rotation_daily.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "feature_rotation_daily",
                "description": "Daily feature-gated rotation test.",
                "timeframe": "daily",
                "universe": ["AAA", "BBB"],
                "lifecycle": "draft",
                "factors": {
                    "theme_score": {
                        "source": "llm_feature",
                        "path": "feature_logs/theme.jsonl",
                        "field": "theme_score",
                        "default": 0.0,
                    },
                },
                "entry": {"all": ["theme_score >= 0.7"], "any": []},
                "exit": {"all": [], "any": ["theme_score < 0.5"]},
                "risk": {"max_position_weight": 1.0},
                "costs": {"commission_pct": 0.0, "slippage_bps": 5.0},
                "execution": {
                    "mode": "manual_signal",
                    "signal_on": "bar_close",
                    "fill_assumption": "next_bar_open",
                    "broker": "none",
                },
                "data": {"source": "alpaca", "symbol": "AAA", "feed": "iex"},
            }
        ),
        encoding="utf-8",
    )

    result = run_rotation_research(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=1,
        feature_gate=True,
    )

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "llm_feature_gated_rotation"
    assert result.best.full_window.rebalances > 0
    assert result.best.full_window.feature_eligible_bar_pct == pytest.approx(100.0)
