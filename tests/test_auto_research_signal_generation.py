"""Step 6.7: auto research generated specs must build IC-oriented signals."""

from __future__ import annotations

from pathlib import Path

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.auto_research import _draft_spec
from open_composer.research.factor_library import get_factor


def _fake_ic(rank_ic: float | None) -> dict[str, object]:
    return {
        "rank_ic": rank_ic,
        "ir": None if rank_ic is None else abs(rank_ic) * 10,
        "coverage_pct": 95.0,
        "observations": 500,
        "stability_score": 0.75,
    }


def test_draft_spec_orients_composite_by_ic_sign(sample_workspace: Path) -> None:
    positive = get_factor("volatility_rank_20_252")
    negative = get_factor("drawdown_guard_20_60")

    spec_path = _draft_spec(
        thesis="orientation test",
        run_id="t_orient",
        selected=[positive, negative],
        ic_scores={positive.id: _fake_ic(0.18), negative.id: _fake_ic(-0.07)},
        universe=["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        base=sample_workspace,
    )

    spec = load_strategy_spec(spec_path)
    composite_expr = spec.factors["composite_score"].expression or ""

    assert "zscore(volatility_rank_20_252_signal, 60)" in composite_expr
    assert "-1 * zscore(drawdown_guard_20_60_signal, 60)" in composite_expr
    assert spec.entry.all == ["composite_score > 0.3"]
    assert spec.entry.any == []
    assert spec.exit.all == []
    assert spec.exit.any == ["composite_score < -0.3"]


def test_draft_spec_keeps_weak_factor_out_of_composite(sample_workspace: Path) -> None:
    strong = get_factor("volatility_rank_20_252")
    weak = get_factor("drawdown_guard_20_60")

    spec_path = _draft_spec(
        thesis="weak factor skip",
        run_id="t_weak",
        selected=[strong, weak],
        ic_scores={strong.id: _fake_ic(0.18), weak.id: _fake_ic(0.005)},
        universe=["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        base=sample_workspace,
    )

    spec = load_strategy_spec(spec_path)
    composite_expr = spec.factors["composite_score"].expression or ""

    assert composite_expr.count("zscore(") == 1
    assert "volatility_rank_20_252_signal" in composite_expr
    assert "drawdown_guard_20_60_signal" not in composite_expr
    assert spec.factors["drawdown_guard_20_60_signal"].source == "factor_library"


def test_draft_spec_produces_signals_on_synthetic_data(sample_workspace: Path) -> None:
    strong = get_factor("volatility_rank_20_252")
    spec_path = _draft_spec(
        thesis="synthetic signal count",
        run_id="t_signals",
        selected=[strong],
        ic_scores={strong.id: _fake_ic(0.18)},
        universe=["SYN"],
        timeframe="daily",
        data_source="sample",
        data_path="data/sample/syn_daily.csv",
        base=sample_workspace,
    )

    spec = load_strategy_spec(spec_path)
    frame = load_ohlcv_for_spec(spec, sample_workspace)
    artifacts = backtest_frame(spec, frame, root=sample_workspace, run_id_value="t_signals")

    assert spec.research_design is not None
    assert spec.research_design.workflow_only_ungated_draft is True
    assert artifacts.run.signals >= 5
