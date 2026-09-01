"""Re-evaluate candidate VOL02 (discrete_beta_ladder_to_volatility_target) through
the mechanism-evaluation harness (``open_composer.research.kernel.mechanism_eval``,
Work Item P1b), on real SIP daily bars via ``open_composer.adapters.data.sip_parquet``.

This is a thin caller: everything mechanism-agnostic (rolling-origin folds, gate
recomputation, DSR, effective-trials clustering, report shape) lives in the
harness. This script supplies only VOL02's decision rule, its one preregistered
parameter vector, and the CLI.

VOL02's decision rule and parameters are read verbatim from
reports/research/iterations/mom_breadth_volatility_beta_r1/candidate-policy-contract.json
(mom_breadth_qd_r1.py's own discrete_beta_ladder branch); this script
reimplements only that pure, weekly-rebalance rule, deliberately bypassing
mom_breadth_qd_r1.py's runner and its sealed phase-one preregistration lock
(see docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md
Work Item C revision, section 9.4) so recalibration doesn't touch or need to
be consistent with that campaign's frozen, already-negative record.

Data source: this run reads SIP daily bars (data/sip/daily/), not the retired
IEX cache (data/cache/) the original recalibration used -- the user's SIP
migration decision (docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md
section 2.1) deprecates IEX outright. Absolute numbers therefore differ from
the earlier IEX-based run; what P1b's extraction must preserve is behavior,
i.e. that this harness-based path and a direct, unrefactored call of the same
primitives agree bit for bit (see tests/test_mechanism_eval.py).

Per the user's decision: the gate uses the full rolling-origin window (more
statistical power); 2024-2026 performance is reported separately as its own
"does this still work now" diagnostic, not blended into the gate.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.research.kernel.mechanism_eval import (
    DEFAULT_PROMOTION_GATES,
    Mechanism,
    evaluate_family,
    expand_mechanism,
    recent_window_diagnostic,
)
from open_composer.research.kernel.rolling_origin import returns_from_ohlcv
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "research" / "recalibrated" / "vol02-recalibrated-evaluation.json"

SYMBOLS = ("QQQ", "TQQQ", "QLD", "BIL")
FALLBACK_SYMBOL = "BIL"
PRIMARY_COST_BPS = 20.0
STRESS_COST_BPS = 40.0
FOLD_COUNT = 5
DSR_TRIAL_COUNT = 32
DSR_HAC_LAG = 21

# Verbatim from candidate-policy-contract.json's VOL02 entry.
SIGNAL_PARAMETERS: dict[str, Any] = {
    "annualization_sessions": 252,
    "otherwise": "QQQ",
    "qld_when_annualized_vol_lte": 0.2,
    "risk_off_when_trend_gap_200_lte": 0.0,
    "tqqq_when_annualized_vol_lte": 0.12,
}


def _is_week_end(decision: pd.Timestamp, execution: pd.Timestamp) -> bool:
    return tuple(decision.isocalendar()[:2]) != tuple(execution.isocalendar()[:2])


def _select_sleeve(trend: float, annualized_vol: float, params: Mapping[str, Any]) -> str:
    if not math.isfinite(trend) or trend <= params["risk_off_when_trend_gap_200_lte"]:
        return "BIL"
    if annualized_vol <= params["tqqq_when_annualized_vol_lte"]:
        return "TQQQ"
    if annualized_vol <= params["qld_when_annualized_vol_lte"]:
        return "QLD"
    return str(params["otherwise"])


def simulate_vol02(
    closes: dict[str, pd.Series],
    opens: dict[str, pd.Series],
    params: Mapping[str, Any],
) -> pd.Series:
    """Reimplement the discrete_beta_ladder rule and return daily portfolio returns.

    ``params`` carries the preregistered decision thresholds plus ``cost_bps``,
    the per-switch round-trip transaction cost assumption -- the mechanism's
    signal function is called once at ``PRIMARY_COST_BPS`` and once at
    ``STRESS_COST_BPS`` by the harness (see ``Mechanism.stress_signal_fn``).
    """
    common_index = closes["QQQ"].index
    for symbol in ("TQQQ", "QLD", "BIL"):
        common_index = common_index.intersection(closes[symbol].index)
    common_index = common_index.sort_values()

    qqq_close = closes["QQQ"].reindex(common_index)
    qqq_return = qqq_close.pct_change()
    trend_gap_200 = qqq_close / qqq_close.rolling(200, min_periods=200).mean() - 1.0
    realized_vol_20 = qqq_return.rolling(20, min_periods=20).std(ddof=1) * math.sqrt(
        params["annualization_sessions"]
    )
    # feature_lag_sessions=1: the feature "as of" session T is the value computed
    # through T-1's close, a one-day PIT safety buffer.
    trend_gap_200 = trend_gap_200.shift(1)
    realized_vol_20 = realized_vol_20.shift(1)

    sleeve_closes = {symbol: closes[symbol].reindex(common_index) for symbol in closes}
    sleeve_opens = {symbol: opens[symbol].reindex(common_index) for symbol in opens}

    dates = list(common_index)
    first_valid = max(
        trend_gap_200.first_valid_index(),
        realized_vol_20.first_valid_index(),
    )
    start_index = dates.index(first_valid) + 1  # need one full session of history past that

    current_sleeve = FALLBACK_SYMBOL
    returns: list[float] = []
    return_dates: list[pd.Timestamp] = []
    pending_switch_to: str | None = None
    cost_bps = float(params["cost_bps"])

    for i in range(start_index, len(dates) - 1):
        decision = dates[i]
        execution = dates[i + 1]
        if _is_week_end(decision, execution):
            trend = float(trend_gap_200.loc[decision])
            vol = float(realized_vol_20.loc[decision])
            if math.isfinite(trend) and math.isfinite(vol):
                pending_switch_to = _select_sleeve(trend, vol, params)

        target_sleeve = pending_switch_to if pending_switch_to is not None else current_sleeve
        switched = target_sleeve != current_sleeve
        if switched:
            # Enter at execution's open; hold to execution's close.
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

    series = pd.Series(returns, index=pd.DatetimeIndex(return_dates), name="VOL02")
    if series.isna().any():
        raise ValueError("VOL02 reconstructed return series contains non-finite values")
    return series


def _load_price_bundles() -> tuple[
    dict[str, pd.Series], dict[str, pd.Series], dict[str, pd.Series]
]:
    """Load SIP daily bars for every VOL02 symbol: close, open, and full-history returns."""
    frame = load_sip_bars(SYMBOLS, frequency="daily")
    closes: dict[str, pd.Series] = {}
    opens: dict[str, pd.Series] = {}
    benchmark_returns: dict[str, pd.Series] = {}
    for symbol in SYMBOLS:
        rows = frame.loc[frame["symbol"] == symbol].sort_values("timestamp")
        index = pd.DatetimeIndex(rows["timestamp"])
        closes[symbol] = pd.Series(
            pd.to_numeric(rows["close"], errors="raise").to_numpy(), index=index, name=symbol
        )
        opens[symbol] = pd.Series(
            pd.to_numeric(rows["open"], errors="raise").to_numpy(), index=index, name=symbol
        )
        benchmark_returns[symbol] = returns_from_ohlcv(rows)
    return closes, opens, benchmark_returns


def main() -> None:
    closes, opens, benchmark_returns = _load_price_bundles()

    mechanism = Mechanism(
        family="VOL02",
        signal_fn=lambda params: simulate_vol02(closes, opens, params),
        stress_signal_fn=lambda params: simulate_vol02(
            closes, opens, {**params, "cost_bps": STRESS_COST_BPS}
        ),
        param_space=[{**SIGNAL_PARAMETERS, "cost_bps": PRIMARY_COST_BPS}],
    )
    candidates = expand_mechanism(mechanism, fold_count=FOLD_COUNT)
    family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        annualization_sessions=SIGNAL_PARAMETERS["annualization_sessions"],
        dsr_trial_count=DSR_TRIAL_COUNT,
        dsr_hac_lag=DSR_HAC_LAG,
    )
    (verdict,) = family.candidates
    candidate = verdict.candidate
    stitched_index = pd.DatetimeIndex(candidate.oos_dates)
    stitched_vol02 = pd.Series(candidate.oos_return_stream, index=stitched_index)

    # 2024-2026-only diagnostic (not gated -- see user decision above).
    recent_diagnostic = recent_window_diagnostic(
        stitched_vol02, benchmark_returns["QQQ"], start="2024-01-01"
    )

    report = {
        "candidate_id": candidate.candidate_id,
        "mechanism_family": candidate.mechanism_family,
        "param_vector": candidate.param_vector,
        "generation": candidate.generation,
        "parent_id": candidate.parent_id,
        "method": "discrete_beta_ladder_to_volatility_target",
        "evaluation_methodology": "mechanism_eval_harness_p1b_sip",
        "note": (
            "Independent reimplementation of the candidate-policy-contract.json rule, "
            "bypassing mom_breadth_qd_r1.py's sealed runner, run through the P1b "
            "mechanism-evaluation harness against real SIP daily bars. Not a byte-"
            "identical replay of the original signal log; small feature/timing "
            "conventions may differ. Historical retuning was NOT performed -- the "
            "rule and its parameters are used exactly as originally preregistered."
        ),
        "fold_count": FOLD_COUNT,
        "family_effective_trial_count": DSR_TRIAL_COUNT,
        "dsr_hac_lag": DSR_HAC_LAG,
        "stitched_oos_row_count": len(candidate.oos_return_stream),
        "stitched_oos_start": candidate.oos_dates[0],
        "stitched_oos_end": candidate.oos_dates[-1],
        "metrics": verdict.metrics,
        "sharpe_excess_bil": verdict.sharpe_excess_bil,
        "dsr_probability": verdict.dsr_probability,
        "positive_fold_count": verdict.metrics["positive_fold_count"],
        "positive_fold_fraction": verdict.positive_fold_fraction,
        "qqq_correlation": verdict.metrics["qqq_correlation"],
        "orthogonal_to_qqq": verdict.orthogonal_to_qqq,
        "paper_tier_gates": DEFAULT_PROMOTION_GATES,
        "paper_tier_gate_results": verdict.gate_results,
        "all_paper_gates_pass": verdict.all_gates_pass,
        "recent_2024_2026_diagnostic": recent_diagnostic,
        "raw_candidate_count": family.raw_candidate_count,
        "effective_n": family.effective_n,
        "breadth_ratio": family.breadth_ratio,
    }
    write_json(OUTPUT_PATH, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
