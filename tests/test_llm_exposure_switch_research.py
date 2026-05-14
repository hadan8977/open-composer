from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import yaml

from open_composer.adapters.data.sample import normalize_ohlcv
from open_composer.research.llm_exposure_switch import (
    LLMExposureSwitchChoice,
    run_llm_exposure_switch_meta_selection,
)


class MockResponses:
    def parse(self, **kwargs: object) -> SimpleNamespace:
        choice = LLMExposureSwitchChoice(
            selected_label="f3_s8_m3_min0_v5_none_dd5_none_base1_on1.25_off1_fin5",
            confidence=0.7,
            rationale="Validation alpha and fold stability looked acceptable.",
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


def test_llm_exposure_switch_hides_final_oos_until_after_choice(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frame = _sample_frame()

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr(
        "open_composer.research.llm_exposure_switch.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "llm_exposure_fixture")

    result = run_llm_exposure_switch_meta_selection(
        spec_path,
        sample_workspace,
        symbol="AAOI",
        fast_bars=[3],
        slow_bars=[8],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        volatility_bars=[5],
        max_volatility_pct=[None],
        drawdown_bars=[5],
        max_drawdown_pct=[None],
        base_exposure=[1.0],
        risk_on_exposure=[1.25],
        risk_off_exposure=[1.0],
        financing_rate_pct=[5.0],
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
    assert "full_window" not in json.dumps(prompt["candidates"])
    assert "validation_fold_summary" in prompt["candidates"][0]

    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["mode"] == "llm_exposure_switch_meta_selection"
    assert payload["status"] == "written"
    assert payload["anti_leakage"]["llm_called_inside_backtest_loop"] is False
    assert "prior validation folds" in payload["anti_leakage"]["llm_visible_metrics"]
    assert payload["data_profile"]["data_as_of"] == "2024-03-20T00:00:00+00:00"
    assert payload["research_brief"]["objective"] == (
        "LLM selects from training-only dynamic exposure candidates"
    )
    assert payload["search_space"]["candidate_count"] == 1
    assert "final out-of-sample metrics" in payload["hypothesis_ledger"][0]["hidden_evidence"]
    assert payload["llm_contribution"]["llm_contribution_ok"] is False
    assert payload["llm_contribution"]["llm_contribution_level"] == "llm_assisted_selection_only"
    assert payload["acceptance_gate"]["llm_contribution_ok"] is False
    assert payload["choice"]["selected_label"] == (
        "f3_s8_m3_min0_v5_none_dd5_none_base1_on1.25_off1_fin5"
    )
    assert "out_of_sample" in payload["selected"]


def test_llm_exposure_switch_falls_back_on_api_error(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frame = _sample_frame()

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr(
        "open_composer.research.llm_exposure_switch.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "llm_exposure_fallback")

    result = run_llm_exposure_switch_meta_selection(
        spec_path,
        sample_workspace,
        symbol="AAOI",
        fast_bars=[3],
        slow_bars=[8],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        volatility_bars=[5],
        max_volatility_pct=[None],
        drawdown_bars=[5],
        max_drawdown_pct=[None],
        base_exposure=[1.0],
        risk_on_exposure=[1.25],
        risk_off_exposure=[1.0],
        financing_rate_pct=[5.0],
        max_candidates=1,
        client=SimpleNamespace(responses=FailingResponses()),
        model="mock",
    )

    assert result.status == "fallback_api_error"
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "fallback_api_error"
    assert payload["acceptance_gate"]["llm_status"] == "fallback_api_error"
    assert payload["llm_contribution"]["external_api_called"] is False
    assert payload["llm_contribution"]["llm_contribution_ok"] is False
    assert "external_llm_api_not_called" in payload["llm_contribution"]["counterevidence"]
    assert payload["acceptance_gate"]["passed"] is False


def test_llm_exposure_switch_accepts_local_codex_choice_after_hidden_oos_validation(
    sample_workspace: Path,
    monkeypatch,
) -> None:
    frame = _sample_frame()

    def fake_fetch_ohlcv(**kwargs):
        return normalize_ohlcv(frame.copy())

    monkeypatch.setattr(
        "open_composer.research.llm_exposure_switch.fetch_ohlcv",
        fake_fetch_ohlcv,
    )
    spec_path = _write_spec(sample_workspace, "llm_exposure_local_choice")

    result = run_llm_exposure_switch_meta_selection(
        spec_path,
        sample_workspace,
        symbol="AAOI",
        fast_bars=[3],
        slow_bars=[8],
        momentum_bars=[3],
        min_momentum_pct=[0.0],
        volatility_bars=[5],
        max_volatility_pct=[None],
        drawdown_bars=[5],
        max_drawdown_pct=[None],
        base_exposure=[1.0],
        risk_on_exposure=[1.25],
        risk_off_exposure=[1.0],
        financing_rate_pct=[5.0],
        max_candidates=1,
        local_choice=LLMExposureSwitchChoice(
            selected_label="f3_s8_m3_min0_v5_none_dd5_none_base1_on1.25_off1_fin5",
            confidence=0.5,
            rationale="Local Codex choice from prompt-only evidence.",
            expected_risks=["Short sample fixture."],
            rejected_labels=[],
        ),
    )

    assert result.status == "codex_local_choice"
    prompt = json.loads(result.prompt_path.read_text(encoding="utf-8"))
    assert "out_of_sample" not in json.dumps(prompt["candidates"])
    payload = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert payload["status"] == "codex_local_choice"
    assert payload["anti_leakage"]["external_api_called"] is False
    assert payload["acceptance_gate"]["llm_status"] == "codex_local_choice"
    assert payload["acceptance_gate"]["llm_contribution_level"] == "llm_assisted_selection_only"
    assert payload["llm_contribution"]["llm_contribution_ok"] is False
    assert "out_of_sample" in payload["selected"]


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
                "description": "LLM exposure switch fixture.",
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
