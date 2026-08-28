"""Re-evaluate candidate VOL02 (discrete_beta_ladder_to_volatility_target) on
real market data through the new gate-recalibration methodology, using the
kernel's anchored rolling-origin walk-forward split (Work Items A2/B) instead
of a single frozen 2021-2023 development window.

VOL02's decision rule and parameters are read verbatim from
reports/research/iterations/mom_breadth_volatility_beta_r1/candidate-policy-contract.json
(mom_breadth_qd_r1.py's own discrete_beta_ladder branch); this script
reimplements only that pure, weekly-rebalance rule against
data/cache/{qqq,tqqq,qld,bil}_daily_iex.csv, deliberately bypassing
mom_breadth_qd_r1.py's runner and its sealed phase-one preregistration lock
(see docs/plan-gate-recalibration-and-research-velocity-2026-08-26.zh.md
Work Item C revision, section 9.4) so recalibration doesn't touch or need to
be consistent with that campaign's frozen, already-negative record.

Per the user's decision: the gate uses the full rolling-origin window (more
statistical power); 2024-2026 performance is reported separately as its own
"does this still work now" diagnostic, not blended into the gate.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.research.campaign import (
    QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD,
    recompute_candidate_promotion_metrics,
)
from open_composer.research.campaign_statistics import (
    annualized_sharpe,
    deflated_sharpe_probability,
)
from open_composer.research.kernel.rolling_origin import (
    returns_from_ohlcv,
    rolling_origin_folds,
)

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "cache"
OUTPUT_PATH = (
    ROOT
    / "reports"
    / "research"
    / "campaigns"
    / "mom_breadth_qd_r1"
    / "VOL02-recalibrated-evaluation.json"
)

# Verbatim from candidate-policy-contract.json's VOL02 entry.
SIGNAL_PARAMETERS = {
    "annualization_sessions": 252,
    "otherwise": "QQQ",
    "qld_when_annualized_vol_lte": 0.2,
    "risk_off_when_trend_gap_200_lte": 0.0,
    "tqqq_when_annualized_vol_lte": 0.12,
}
FALLBACK_SYMBOL = "BIL"
PRIMARY_COST_BPS = 20
STRESS_COST_BPS = 40
FOLD_COUNT = 5

# Paper-tier target gates (plan section 4).
PAPER_GATES = {
    "cagr_excess_qqq_minimum": 0.05,
    "sharpe_excess_bil_minimum": 1.00,
    "dsr_minimum": 0.50,
    "max_drawdown_minimum": -0.65,
    "mar_minimum": 0.60,
    "minimum_positive_fold_fraction": 3 / 5,
    "qqq_capture_ratio_minimum": 1.0,
    "qqq_downside_capture_maximum": 1.0,
}
DSR_TRIAL_COUNT = 32
DSR_HAC_LAG = 21
MIN_DSR_STREAM_ROWS = 1000


def _load_close(symbol: str) -> pd.Series:
    frame = pd.read_csv(CACHE / f"{symbol.lower()}_daily_iex.csv", parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates(subset="timestamp")
    close = pd.to_numeric(frame["close"], errors="raise")
    close.index = pd.DatetimeIndex(frame["timestamp"])
    return close


def _load_open(symbol: str) -> pd.Series:
    frame = pd.read_csv(CACHE / f"{symbol.lower()}_daily_iex.csv", parse_dates=["timestamp"])
    frame = frame.sort_values("timestamp").drop_duplicates(subset="timestamp")
    open_ = pd.to_numeric(frame["open"], errors="raise")
    open_.index = pd.DatetimeIndex(frame["timestamp"])
    return open_


def _is_week_end(decision: pd.Timestamp, execution: pd.Timestamp) -> bool:
    return tuple(decision.isocalendar()[:2]) != tuple(execution.isocalendar()[:2])


def _select_sleeve(trend: float, annualized_vol: float) -> str:
    params = SIGNAL_PARAMETERS
    if not math.isfinite(trend) or trend <= params["risk_off_when_trend_gap_200_lte"]:
        return "BIL"
    if annualized_vol <= params["tqqq_when_annualized_vol_lte"]:
        return "TQQQ"
    if annualized_vol <= params["qld_when_annualized_vol_lte"]:
        return "QLD"
    return str(params["otherwise"])


def simulate_vol02(closes: dict[str, pd.Series], opens: dict[str, pd.Series]) -> pd.Series:
    """Reimplement the discrete_beta_ladder rule and return daily portfolio returns."""
    common_index = closes["QQQ"].index
    for symbol in ("TQQQ", "QLD", "BIL"):
        common_index = common_index.intersection(closes[symbol].index)
    common_index = common_index.sort_values()

    qqq_close = closes["QQQ"].reindex(common_index)
    qqq_return = qqq_close.pct_change()
    trend_gap_200 = qqq_close / qqq_close.rolling(200, min_periods=200).mean() - 1.0
    realized_vol_20 = qqq_return.rolling(20, min_periods=20).std(ddof=1) * math.sqrt(
        SIGNAL_PARAMETERS["annualization_sessions"]
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

    for i in range(start_index, len(dates) - 1):
        decision = dates[i]
        execution = dates[i + 1]
        if _is_week_end(decision, execution):
            trend = float(trend_gap_200.loc[decision])
            vol = float(realized_vol_20.loc[decision])
            if math.isfinite(trend) and math.isfinite(vol):
                pending_switch_to = _select_sleeve(trend, vol)

        target_sleeve = pending_switch_to if pending_switch_to is not None else current_sleeve
        switched = target_sleeve != current_sleeve
        if switched:
            # Enter at execution's open; hold to execution's close.
            day_return = float(
                sleeve_closes[target_sleeve].loc[execution]
                / sleeve_opens[target_sleeve].loc[execution]
                - 1.0
            )
            day_return -= (PRIMARY_COST_BPS / 10_000.0) * 2.0
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
    if series.isna().any() or not np.isfinite(series.to_numpy()).all():
        raise ValueError("VOL02 reconstructed return series contains non-finite values")
    return series


def _stress_returns(closes: dict[str, pd.Series], opens: dict[str, pd.Series]) -> pd.Series:
    """Same simulation at the 40bps stress cost, for the stress_total_return metric."""
    global PRIMARY_COST_BPS
    original = PRIMARY_COST_BPS
    PRIMARY_COST_BPS = STRESS_COST_BPS
    try:
        return simulate_vol02(closes, opens)
    finally:
        PRIMARY_COST_BPS = original


def _annualized_cagr(returns: pd.Series) -> float:
    compounded = float(np.prod(1.0 + returns.to_numpy())) - 1.0
    years = len(returns) / 252.0
    return (1.0 + compounded) ** (1.0 / years) - 1.0


def _max_drawdown(returns: pd.Series) -> float:
    wealth = (1.0 + returns).cumprod()
    peak = wealth.cummax()
    return float((wealth / peak - 1.0).min())


def main() -> None:
    closes = {symbol: _load_close(symbol) for symbol in ("QQQ", "TQQQ", "QLD", "BIL")}
    opens = {symbol: _load_open(symbol) for symbol in ("QQQ", "TQQQ", "QLD", "BIL")}

    vol02_returns = simulate_vol02(closes, opens)
    vol02_stress_returns = _stress_returns(closes, opens)

    qqq_returns_full = returns_from_ohlcv(pd.read_csv(CACHE / "qqq_daily_iex.csv")).reindex(
        vol02_returns.index
    )
    tqqq_returns_full = returns_from_ohlcv(pd.read_csv(CACHE / "tqqq_daily_iex.csv")).reindex(
        vol02_returns.index
    )
    bil_returns_full = returns_from_ohlcv(pd.read_csv(CACHE / "bil_daily_iex.csv")).reindex(
        vol02_returns.index
    )

    folds, stitched_vol02 = rolling_origin_folds(vol02_returns, fold_count=FOLD_COUNT)
    stitched_index = stitched_vol02.index
    stitched_qqq = qqq_returns_full.reindex(stitched_index)
    stitched_tqqq = tqqq_returns_full.reindex(stitched_index)
    stitched_bil = bil_returns_full.reindex(stitched_index)
    stitched_stress = vol02_stress_returns.reindex(stitched_index)
    if stitched_qqq.isna().any() or stitched_tqqq.isna().any() or stitched_bil.isna().any():
        raise ValueError("benchmark alignment produced missing rows in the stitched window")

    fold_returns = [
        stitched_vol02.loc[
            pd.Timestamp(fold.train.test_start) : pd.Timestamp(fold.train.test_end)
        ].tolist()
        for fold in folds
    ]

    metrics = recompute_candidate_promotion_metrics(
        candidate_returns=stitched_vol02.tolist(),
        qqq_returns=stitched_qqq.tolist(),
        tqqq_returns=stitched_tqqq.tolist(),
        stress_returns=stitched_stress.tolist(),
        development_fold_returns=fold_returns,
        annualization_sessions=SIGNAL_PARAMETERS["annualization_sessions"],
    )

    excess_bil = (stitched_vol02 - stitched_bil).to_numpy()
    sharpe_excess_bil = annualized_sharpe(excess_bil)
    dsr_probability = deflated_sharpe_probability(
        excess_bil, trial_count=DSR_TRIAL_COUNT, hac_lag=DSR_HAC_LAG
    )
    positive_fold_fraction = metrics["positive_fold_count"] / len(fold_returns)

    orthogonal = abs(metrics["qqq_correlation"]) <= QQQ_ORTHOGONALITY_CORRELATION_THRESHOLD
    gate_results = {
        "cagr_excess_qqq": metrics["cagr_excess_qqq"] >= PAPER_GATES["cagr_excess_qqq_minimum"],
        "sharpe_excess_bil": sharpe_excess_bil > PAPER_GATES["sharpe_excess_bil_minimum"],
        "dsr_probability": (
            dsr_probability >= PAPER_GATES["dsr_minimum"]
            and len(stitched_vol02) >= MIN_DSR_STREAM_ROWS
        ),
        "max_drawdown": metrics["max_drawdown"] >= PAPER_GATES["max_drawdown_minimum"],
        "mar": metrics["mar"] >= PAPER_GATES["mar_minimum"],
        "positive_fold_fraction": positive_fold_fraction
        >= PAPER_GATES["minimum_positive_fold_fraction"],
        "qqq_capture_ratio": (
            True
            if orthogonal
            else metrics["qqq_capture_ratio"] >= PAPER_GATES["qqq_capture_ratio_minimum"]
        ),
        "qqq_downside_capture": (
            True
            if orthogonal
            else metrics["qqq_downside_capture"] <= PAPER_GATES["qqq_downside_capture_maximum"]
        ),
    }
    all_paper_gates_pass = all(gate_results.values())

    # 2024-2026-only diagnostic (not gated -- see user decision in section 9 of the plan).
    recent = vol02_returns.loc[vol02_returns.index >= pd.Timestamp("2024-01-01", tz="UTC")]
    recent_qqq = qqq_returns_full.reindex(recent.index).combine_first(
        returns_from_ohlcv(pd.read_csv(CACHE / "qqq_daily_iex.csv")).reindex(recent.index)
    )
    recent_diagnostic = {
        "row_count": int(len(recent)),
        "start": recent.index.min().date().isoformat() if len(recent) else None,
        "end": recent.index.max().date().isoformat() if len(recent) else None,
        "cagr": _annualized_cagr(recent) if len(recent) > 5 else None,
        "sharpe": annualized_sharpe(recent.to_numpy()) if len(recent) > 5 else None,
        "max_drawdown": _max_drawdown(recent) if len(recent) > 5 else None,
        "qqq_cagr": _annualized_cagr(recent_qqq.dropna())
        if recent_qqq.dropna().shape[0] > 5
        else None,
    }

    report = {
        "candidate_id": "VOL02",
        "method": "discrete_beta_ladder_to_volatility_target",
        "evaluation_methodology": "gate_recalibration_2026_08_26_rolling_origin",
        "note": (
            "Independent reimplementation of the candidate-policy-contract.json rule "
            "against real market data, bypassing mom_breadth_qd_r1.py's sealed runner. "
            "Not a byte-identical replay of the original signal log; small feature/timing "
            "conventions may differ. Historical retuning was NOT performed -- the rule "
            "and its parameters are used exactly as originally preregistered."
        ),
        "fold_count": FOLD_COUNT,
        "family_effective_trial_count": DSR_TRIAL_COUNT,
        "dsr_hac_lag": DSR_HAC_LAG,
        "stitched_oos_row_count": int(len(stitched_vol02)),
        "stitched_oos_start": stitched_vol02.index.min().date().isoformat(),
        "stitched_oos_end": stitched_vol02.index.max().date().isoformat(),
        "fold_test_windows": [
            {
                "fold": fold.fold,
                "test_start": fold.train.test_start,
                "test_end": fold.train.test_end,
            }
            for fold in folds
        ],
        "metrics": {k: (float(v) if isinstance(v, int | float) else v) for k, v in metrics.items()},
        "sharpe_excess_bil": float(sharpe_excess_bil),
        "dsr_probability": float(dsr_probability),
        "positive_fold_count": int(metrics["positive_fold_count"]),
        "positive_fold_fraction": float(positive_fold_fraction),
        "qqq_correlation": float(metrics["qqq_correlation"]),
        "orthogonal_to_qqq": bool(orthogonal),
        "paper_tier_gates": PAPER_GATES,
        "paper_tier_gate_results": gate_results,
        "all_paper_gates_pass": bool(all_paper_gates_pass),
        "recent_2024_2026_diagnostic": recent_diagnostic,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
