from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.llm_rotation import LLMRotationChoice, run_llm_rotation_meta_selection


class MockResponses:
    def parse(self, **kwargs: object) -> SimpleNamespace:
        choice = LLMRotationChoice(
            selected_label="lb3_reb2_top1_min0",
            confidence=0.7,
            rationale="Validation alpha and drawdown looked acceptable in training-only evidence.",
            expected_risks=["Short sample fixture."],
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


class FailingResponses:
    def parse(self, **kwargs: object) -> None:
        raise RuntimeError("network unavailable")


def test_llm_rotation_meta_selection_hides_final_oos_until_after_choice(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))
    sample = sample.head(24).copy()
    sample["timestamp"] = pd.date_range("2024-01-01", periods=len(sample), freq="D", tz="UTC")

    def fake_fetch_ohlcv(**kwargs):
        frame = sample.copy()
        if kwargs["symbol"] == "BBB":
            frame["close"] = frame["close"] * pd.Series(
                [1 + index * 0.01 for index in range(len(frame))]
            )
            frame["open"] = frame["open"] * pd.Series(
                [1 + index * 0.01 for index in range(len(frame))]
            )
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "llm_meta_rotation.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "llm_meta_rotation",
                "description": "LLM meta-selection fixture.",
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

    result = run_llm_rotation_meta_selection(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=1,
        client=SimpleNamespace(responses=MockResponses()),
        model="mock",
    )

    assert result.report_path.exists()
    assert result.json_path.exists()
    assert result.prompt_path.exists()
    prompt = json.loads(result.prompt_path.read_text(encoding="utf-8"))
    assert prompt["hidden_from_model"] == "final out-of-sample and full-window metrics"
    assert "prior validation folds" in prompt["available_evidence"]
    assert "out_of_sample" not in json.dumps(prompt["candidates"])
    assert "validation_fold_summary" in prompt["candidates"][0]

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "llm_training_meta_selection"
    assert payload["anti_leakage"]["llm_called_inside_backtest_loop"] is False
    assert "prior validation folds" in payload["anti_leakage"]["llm_visible_metrics"]
    assert payload["choice"]["selected_label"] == "lb3_reb2_top1_min0"
    assert "out_of_sample" in payload["selected"]


def test_llm_rotation_meta_selection_falls_back_on_api_error(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    sample = normalize_ohlcv(pd.read_csv(sample_workspace / "data" / "sample" / "qqq_15m.csv"))
    sample = sample.head(24).copy()
    sample["timestamp"] = pd.date_range("2024-01-01", periods=len(sample), freq="D", tz="UTC")

    def fake_fetch_ohlcv(**kwargs):
        frame = sample.copy()
        if kwargs["symbol"] == "BBB":
            frame["close"] = frame["close"] * pd.Series(
                [1 + index * 0.01 for index in range(len(frame))]
            )
            frame["open"] = frame["open"] * pd.Series(
                [1 + index * 0.01 for index in range(len(frame))]
            )
        return normalize_ohlcv(frame)

    monkeypatch.setattr("open_composer.research.rotation.fetch_ohlcv", fake_fetch_ohlcv)

    spec_path = sample_workspace / "strategy_specs" / "drafts" / "llm_meta_fallback.yaml"
    spec_path.write_text(
        yaml.safe_dump(
            {
                "name": "llm_meta_fallback",
                "description": "LLM meta-selection fallback fixture.",
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

    result = run_llm_rotation_meta_selection(
        spec_path,
        sample_workspace,
        symbols=["AAA", "BBB"],
        lookback_bars=[3],
        rebalance_bars=[2],
        top_n_values=[1],
        min_momentum_pct=[0.0],
        max_candidates=1,
        client=SimpleNamespace(responses=FailingResponses()),
        model="mock",
        objective="primary_alpha",
    )

    assert result.status == "fallback_api_error"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fallback_api_error"
    assert "primary-symbol" in payload["selection_objective"]
    prompt = json.loads(result.prompt_path.read_text(encoding="utf-8"))
    assert prompt["selection_objective"].startswith("prefer stable Alpha versus primary")
