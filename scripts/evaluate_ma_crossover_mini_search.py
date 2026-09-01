"""Onboarding proof + mini parameter search for Work Item P1b.

A second, independent mechanism (dual moving-average crossover on SIP daily
QQQ, long QQQ vs BIL cash) run through the exact same
``open_composer.research.kernel.mechanism_eval`` harness as VOL02
(``scripts/evaluate_vol02_recalibrated.py``), at two parameter points. This is
simultaneously:

  * the "onboarding a new mechanism" proof (see plan section 5.4): only the
    signal function and its parameter space below are mechanism-specific,
    everything else is the harness;
  * the "2-candidate mini parameter search" acceptance check: both points
    share one mechanism template, go through ``expand_mechanism`` and
    ``evaluate_family`` exactly like a hand-written one-point mechanism would,
    and the family verdict reports ``effective_n`` / ``raw_candidate_count`` /
    ``breadth_ratio``.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.kernel.mechanism_eval import (
    Mechanism,
    evaluate_family,
    expand_mechanism,
)
from open_composer.research.kernel.rolling_origin import returns_from_ohlcv

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "research" / "recalibrated" / "ma-crossover-mini-search.json"
SYMBOLS = ("QQQ", "BIL")
STRESS_COST_BPS = 40.0
PARAM_SPACE: list[dict[str, Any]] = [
    {"fast_window": 20, "slow_window": 100, "cost_bps": 20.0},
    {"fast_window": 50, "slow_window": 200, "cost_bps": 20.0},
]


def simulate_ma_crossover(
    closes: dict[str, pd.Series], opens: dict[str, pd.Series], params: Mapping[str, Any]
) -> pd.Series:
    """Long QQQ when its fast SMA is above its slow SMA, else BIL; both MAs and
    the crossover decision are lagged one session (PIT safety buffer), then
    executed open-to-close the following session -- the same convention VOL02
    uses."""
    fast, slow, cost_bps = (
        int(params["fast_window"]),
        int(params["slow_window"]),
        float(params["cost_bps"]),
    )
    index = closes["QQQ"].index.intersection(closes["BIL"].index).sort_values()
    qqq_close = closes["QQQ"].reindex(index)
    bullish = (
        qqq_close.rolling(fast, min_periods=fast).mean()
        > qqq_close.rolling(slow, min_periods=slow).mean()
    ).shift(1)
    sleeve_closes = {symbol: closes[symbol].reindex(index) for symbol in SYMBOLS}
    sleeve_opens = {symbol: opens[symbol].reindex(index) for symbol in SYMBOLS}

    dates = list(index)
    start = dates.index(bullish.first_valid_index()) + 1
    current_sleeve = "BIL"
    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    for i in range(start, len(dates) - 1):
        decision, execution = dates[i], dates[i + 1]
        target_sleeve = "QQQ" if bool(bullish.loc[decision]) else "BIL"
        if target_sleeve != current_sleeve:
            day_return = float(
                sleeve_closes[target_sleeve].loc[execution]
                / sleeve_opens[target_sleeve].loc[execution]
                - 1.0
            )
            day_return -= (cost_bps / 10_000.0) * 2.0
            current_sleeve = target_sleeve
        else:
            day_return = float(
                sleeve_closes[current_sleeve].loc[execution]
                / sleeve_closes[current_sleeve].loc[decision]
                - 1.0
            )
        returns.append(day_return)
        return_dates.append(execution)

    series = pd.Series(returns, index=pd.DatetimeIndex(return_dates), name="MA_CROSS")
    if series.isna().any():
        raise ValueError("MA crossover reconstructed return series contains non-finite values")
    return series


def main() -> None:
    frame = load_sip_bars(SYMBOLS, frequency="daily")
    closes, opens, benchmark_returns = {}, {}, {}
    for symbol in SYMBOLS:
        rows = frame.loc[frame["symbol"] == symbol].sort_values("timestamp")
        index = pd.DatetimeIndex(rows["timestamp"])
        closes[symbol] = pd.Series(pd.to_numeric(rows["close"]).to_numpy(), index=index)
        opens[symbol] = pd.Series(pd.to_numeric(rows["open"]).to_numpy(), index=index)
        benchmark_returns[symbol] = returns_from_ohlcv(rows)
    tqqq_rows = load_sip_bars("TQQQ", frequency="daily").sort_values("timestamp")

    mechanism = Mechanism(
        family="MA_CROSS",
        signal_fn=lambda params: simulate_ma_crossover(closes, opens, params),
        stress_signal_fn=lambda params: simulate_ma_crossover(
            closes, opens, {**params, "cost_bps": STRESS_COST_BPS}
        ),
        param_space=PARAM_SPACE,
    )
    candidates = expand_mechanism(mechanism, fold_count=5)
    family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=returns_from_ohlcv(tqqq_rows),
        bil_returns=benchmark_returns["BIL"],
    )
    report = {
        "raw_candidate_count": family.raw_candidate_count,
        "effective_n": family.effective_n,
        "breadth_ratio": family.breadth_ratio,
        "candidates": [
            {
                "candidate_id": verdict.candidate.candidate_id,
                "param_vector": verdict.candidate.param_vector,
                "all_gates_pass": verdict.all_gates_pass,
                "dsr_probability": verdict.dsr_probability,
            }
            for verdict in family.candidates
        ],
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
