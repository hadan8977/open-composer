"""Credential-free, synthetic diagnostic example of the reusable research facade."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.lab.ablation import Ablation, check_ablations
from open_composer.lab.adapters import book_engine, spec_engine
from open_composer.lab.batch import Variant, run_batch, write_evidence
from open_composer.lab.metrics import DSRConfig
from open_composer.lab.models import Experiment
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.equity_book.backtest import BookConfig


def synthetic_spec(timeframe="daily", **risk) -> StrategySpec:
    """Validated sample policy shared by examples and parity/branch tests."""
    return StrategySpec.model_validate(
        {
            "name": "lab_sample_branch_test",
            "description": "Synthetic branch and accounting fixture only",
            "timeframe": timeframe,
            "universe": ["AAA"],
            "lifecycle": "draft",
            "entry": {"all": ["close > 0"]},
            "exit": {"any": ["close < 0"]},
            "risk": {"max_position_weight": 0.7, **risk},
            "costs": {"commission_pct": 0.1, "slippage_bps": 5},
            "execution": {
                "mode": "manual_signal",
                "signal_on": "bar_close",
                "fill_assumption": "next_bar_open",
                "broker": "none",
            },
            "data": {"source": "sample", "symbol": "AAA"},
        }
    )


def synthetic_bars(timeframe="daily") -> pd.DataFrame:
    close = np.array([100, 100, 91, 115, 98, 121, 93, 116], dtype=float)
    # Daily shocks deliberately trigger the risk rules. Minute parity uses basis-point
    # moves, avoiding an economically meaningless annualization of daily-size shocks.
    if timeframe != "daily":
        close = 100 + (close - 100) * 0.001
    spread = 1.0 if timeframe == "daily" else 0.01
    return pd.DataFrame(
        {
            "timestamp": pd.date_range(
                "2024-01-02 14:30",
                periods=len(close),
                freq="D" if timeframe == "daily" else "min",
                tz="UTC",
            ),
            "open": close,
            "high": close + spread,
            "low": close - spread,
            "close": close,
            "volume": 1_000_000,
        }
    )


def run_ablation_example(root: Path) -> list[dict]:
    """Actual condition-triggered native runs; synthetic diagnostic evidence only."""
    config = {"stop_loss_pct": 99, "take_profit_pct": 99, "commission_pct": 0, "weight": 0.7}

    def observe(parameters, bars):
        spec = synthetic_spec(
            stop_loss_pct=parameters["stop_loss_pct"],
            take_profit_pct=parameters["take_profit_pct"],
            max_position_weight=parameters["weight"],
        )
        raw = spec.model_dump()
        raw["costs"]["commission_pct"] = parameters["commission_pct"]
        result = spec_engine(
            StrategySpec.model_validate(raw), bars, root=root, run_id="synthetic-ablation"
        )
        return {
            "profit": result.net_profit_usd,
            "fees": result.native["run"]["total_fees"],
            "signals": result.native["run"]["signals"],
        }

    frame = synthetic_bars()
    return check_ablations(
        config,
        [
            Ablation("stop_loss_pct", 5, frame, "91 close breaches the entry's 5% stop"),
            Ablation("take_profit_pct", 5, frame, "115 close crosses the entry's 5% take-profit"),
            Ablation("commission_pct", 0.2, frame, "The first next-open entry pays a fee"),
            Ablation("weight", 0.3, frame, "A nonzero position is opened"),
        ],
        observe,
    )


def run_example(root: Path, *, batch_id: str):
    """Requires installed authority; never installs or changes control.json itself."""
    dates = pd.bdate_range("2024-01-02", periods=80)
    close = pd.DataFrame(
        {"FIXTURE": 100 * np.exp(np.arange(80) * 0.0002 + np.sin(np.arange(80)) * 0.02)},
        index=dates,
    )
    close.attrs["data_source_mode"] = "fixture"
    open_ = close.shift(1).fillna(close.iloc[0])
    config = BookConfig(freq="D", initial_equity=10_000, cost_bp_per_side=10)

    def evaluate(weight):
        return book_engine(close, open_, lambda date, state: {"FIXTURE": weight}, config=config)

    batch = run_batch(
        root,
        experiment=Experiment(
            direction="lab_example",
            kind="diagnostic",
            data_and_exposure="80 synthetic seen sessions; accounting fixture, no market evidence",
            costs="Native book flat_cost: 10 bp per side, no borrowing or margin usage",
            baseline="Non-interest-bearing USD cash, zero return",
            baseline_net_profit_usd=0,
            limitations=("Synthetic numbers establish plumbing only; no profit claim",),
        ),
        batch_id=batch_id,
        variants=[
            Variant(
                "weight_60",
                {"weight": 0.6},
                lambda: evaluate(0.6),
                exposure_note="Synthetic configurable variant; fixture exposure only",
            ),
            Variant(
                "weight_35",
                {"weight": 0.35},
                lambda: evaluate(0.35),
                exposure_note="Synthetic configurable variant; fixture exposure only",
            ),
        ],
        dsr_config=DSRConfig(
            method="campaign_statistics",
            benchmark=pd.Series(0.0, index=dates),
            benchmark_note="Synthetic non-interest-bearing cash on the exact observed calendar",
            hac_lag=5,
            assumptions=(
                "All starts in this fixture direction count, including previous batches; "
                "native HAC lag 5. Synthetic data has no economic interpretation."
            ),
        ),
        selected_id="weight_60",
    )
    write_evidence(batch.folder / "ablations.json", run_ablation_example(root))
    return batch
