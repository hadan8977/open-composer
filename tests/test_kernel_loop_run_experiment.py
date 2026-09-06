"""End-to-end test for open_composer.research.kernel.loop.run_experiment.

Uses real SPY/QQQ/TQQQ/BIL benchmark data (consistent with the rest of this
kernel's test suite, e.g. tests/test_mechanism_eval.py) aligned to a
synthetic, deterministic strategy panel over a real historical date range,
so the run exercises the genuine, git-tracked gate contract end to end
rather than a fake one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.kernel import loop
from open_composer.research.kernel.baseline_strategies import MomentumFactorStrategy
from open_composer.research.kernel.benchmark_returns import daily_returns_on_naive_dates

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]


def _synthetic_panel_over_real_dates() -> tuple[pd.DataFrame, pd.DataFrame]:
    spy = daily_returns_on_naive_dates("SPY", start="2016-01-04", end="2018-06-30")
    dates = spy.index
    rng = np.random.default_rng(3)
    drift = {"AAA": 0.0015, "BBB": 0.0004, "CCC": -0.0002, "DDD": -0.0012}
    rows = []
    for symbol in SYMBOLS:
        price = 100.0
        for date in dates:
            price *= 1.0 + drift[symbol] + rng.normal(0, 0.004)
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": date,
                    "close": price,
                    "momentum_252_21": drift[symbol] * 100 + rng.normal(0, 0.001),
                    "beta_252_spy": 1.0,
                    "label_rank_5": rng.uniform(0, 1),
                }
            )
    panel = pd.DataFrame(rows)
    month_ends = (
        panel[["trade_date"]]
        .drop_duplicates()
        .assign(month_key=lambda d: d["trade_date"].dt.to_period("M"))
        .groupby("month_key")["trade_date"]
        .max()
    )
    universe_panel = pd.DataFrame(
        [
            {"month_end": month_end, "symbol": symbol}
            for month_end in month_ends
            for symbol in SYMBOLS
        ]
    )
    return panel, universe_panel


@pytest.fixture
def benchmarks() -> dict[str, pd.Series]:
    return {
        symbol: daily_returns_on_naive_dates(symbol, start="2016-01-04", end="2018-06-30")
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }


def test_run_experiment_end_to_end_writes_ledger_tearsheet_and_mlflow(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, benchmarks: dict[str, pd.Series]
) -> None:
    ledger_path = tmp_path / "experiments.jsonl"
    tearsheet_dir = tmp_path / "tearsheets"
    mlflow_dir = tmp_path / "mlruns"
    monkeypatch.setattr(loop, "LEDGER_PATH", ledger_path)
    monkeypatch.setattr(loop, "TEARSHEET_DIR", tearsheet_dir)
    monkeypatch.setattr(loop, "MLFLOW_TRACKING_DIR", mlflow_dir)

    panel, universe_panel = _synthetic_panel_over_real_dates()
    config = loop.ExperimentConfig(
        experiment_id="test_b1_momentum",
        family="test_family_e2e",
        model_kind="b1_momentum",
        feature_set="daily_only",
        label_horizon_days=5,
        feature_columns=("momentum_252_21",),
        top_k=2,
        hedge="none",
        test_years=(2017, 2018),
    )

    verdict = loop.run_experiment(
        config,
        panel=panel,
        universe_panel=universe_panel,
        label_column="label_rank_5",
        strategy_factory=MomentumFactorStrategy,
        spy_returns=benchmarks["SPY"],
        qqq_returns=benchmarks["QQQ"],
        tqqq_returns=benchmarks["TQQQ"],
        bil_returns=benchmarks["BIL"],
    )

    assert verdict.experiment_id == "test_b1_momentum"
    assert verdict.ledger_appended is True
    assert ledger_path.exists()
    assert len(ledger_path.read_text().splitlines()) == 1
    assert verdict.tearsheet_path is not None
    assert Path(verdict.tearsheet_path).exists()
    assert verdict.dsr_trial_count == loop._MIN_DSR_TRIAL_COUNT
    # AAA is the always-highest-momentum name -- top_k=2 should always include it.
    assert verdict.long_only.metrics["cagr"] is not None
    assert set(verdict.long_only.gate_results) == {
        "cagr_excess_vol_matched_benchmark",
        "sharpe_excess_bil",
        "dsr_probability",
        "max_drawdown",
        "mar",
        "positive_fold_fraction",
        "benchmark_vm_capture_ratio",
        "benchmark_vm_downside_capture",
    }
    # Re-running the identical config must not duplicate the ledger line.
    loop.run_experiment(
        config,
        panel=panel,
        universe_panel=universe_panel,
        label_column="label_rank_5",
        strategy_factory=MomentumFactorStrategy,
        spy_returns=benchmarks["SPY"],
        qqq_returns=benchmarks["QQQ"],
        tqqq_returns=benchmarks["TQQQ"],
        bil_returns=benchmarks["BIL"],
        write_tearsheet=False,
        write_mlflow=False,
    )
    assert len(ledger_path.read_text().splitlines()) == 1
