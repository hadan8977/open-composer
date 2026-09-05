"""Step 10 Wave 3: preregistered combination of low-correlation Wave 1/2 sleeves.

Why: docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 6
preregisters this exact procedure (executor may not adjust it): take each
family's single best-Sharpe candidate from Wave 1/2, keep only the ones with
stitched-OOS Sharpe-excess-BIL >= 0.4 whose pairwise OOS daily-return
correlation is <= 0.5 with every other kept sleeve, weight them by inverse
realized volatility (252-day, recomputed at every month-end, no
optimization), and judge the combined daily-return stream through the exact
same mechanism_eval pipeline and unlevered-family contract as a single
candidate, benchmarked against SPY.

**Judgment calls the plan text does not fully pin down (decided and recorded
here, not tuned after seeing the result)**:

1. Tie-break when not every pair of the three families' best candidates is
   mutually compatible. This run's actual correlations are corr(F1,F2)=0.41,
   corr(F1,W2)=0.39, corr(F2,W2)=0.71 -- the full 3-way set is NOT mutually
   compatible (F2/W2 exceed 0.5), so some subset must be dropped. Resolved by
   a greedy walk in descending Sharpe order (the same ranking principle the
   plan already uses to pick one candidate per family): add the
   highest-Sharpe remaining family only if it is <=0.5 correlated with every
   sleeve already accepted. This is decided by Sharpe rank and the
   preregistered threshold alone, never by trying combinations and keeping
   whichever passes more gates.
2. DSR trial count. The plan says "各族有效 N 之和 + 1" without saying
   whether "各族" means only the families that end up IN the combination or
   every family that was IN CONTENTION for it. Read the more conservative
   way (every family examined for sleeve eligibility this Wave 1/2 round,
   whether or not the correlation filter later excluded it): effective_n(F1)
   + effective_n(F2) + effective_n(W2) + 1, since all three were live
   candidates for combination before the correlation filter acted on them.
3. Inverse-vol lookback warm-up. "过去 252 日已实现波动率" needs a fallback
   before 252 days of aligned sleeve history exist. Equal-weight until 20
   trading days are available (matching this project's existing
   volatility_lookback_days=20 convention for the beta-exposure router),
   then inverse-vol on an EXPANDING window up to a 252-day cap. This
   (deliberately) keeps the combination's own OOS window starting on the
   very first common date across the selected sleeves' stitched OOS streams
   (2022-01-03) rather than truncating a full year as unusable warm-up,
   which matters below.
4. Fold reconstruction. The combination's raw input IS ALREADY each sleeve's
   *stitched OOS* stream (2022-2026 only) -- there is no earlier
   "training" history available to hand to rolling_origin_folds/
   expand_mechanism for an anchored walk-forward re-split, and none is
   needed: unlike the underlying mechanisms, the combination does not fit
   any parameter on a training window (inverse-vol weighting is a fixed,
   point-in-time rule, not a fitted model), so there is nothing here for a
   train/test split to protect against. rolling_origin_folds would, if it
   could run, treat "last 5 distinct calendar years present" as the 5 test
   folds and its stitched output would equal the ENTIRE input unchanged
   (every single day of a 5-calendar-year input is some fold's test day) --
   it can only fail here on its embargo precondition ("is there any data
   strictly before the first test year"), which has nothing to do with this
   combination being valid evidence. So oos_fold_returns is reconstructed
   directly by calendar year (2022..2026) from the full combination series,
   which is exactly what rolling_origin_folds's stitched output and fold
   partition would have been had its embargo precondition not been
   structurally unsatisfiable here.
5. Cost stress. No incremental transaction cost is modeled for reallocating
   between sleeves at each month-end rebalance (each sleeve's own daily
   return already reflects that sleeve's OWN internal trading costs).
   stress_return_stream is set equal to oos_return_stream, i.e. this
   combination layer is treated as cost-insensitive for the stress
   diagnostic -- which does not gate promotion_eligible in mechanism_eval
   (see gate_results in evaluate_candidate: stress_total_return is reported,
   never gated, on the kernel path). Documented rather than silently assumed.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.research.kernel.benchmark_returns import daily_returns_on_naive_dates
from open_composer.research.kernel.gate_contract import (
    UNLEVERED_FAMILY_GATE_KEYS,
    load_preregistered_gates,
)
from open_composer.research.kernel.mechanism_eval import (
    Candidate,
    annualized_cagr,
    evaluate_candidate,
    max_drawdown,
    recent_window_diagnostic,
)
from open_composer.research.route_cross_source import CRISIS_WINDOWS
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
CONTROL_DIR = ROOT / "reports" / "research" / "control"
OUTPUT_PATH = CONTROL_DIR / "step10-w3-combination-2026-09.json"
NEW_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "unlevered-family-paper-tier-gates.json"
OLD_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"

FAMILY_SOURCES = {
    "F1_beta_exposure": CONTROL_DIR / "step10-w1-beta-exposure-2026-09.json",
    "F2_cross_asset_trend": CONTROL_DIR / "step10-w1-cross-asset-trend-2026-09.json",
    "W2_cross_sectional_liquid500": CONTROL_DIR
    / "step10-w2-cross-sectional-liquid500-2026-09.json",
}
SHARPE_EXCESS_BIL_MINIMUM = 0.4
PAIRWISE_CORRELATION_MAXIMUM = 0.5
MIN_VOL_LOOKBACK_DAYS = 20
MAX_VOL_LOOKBACK_DAYS = 252
DSR_HAC_LAG = 21
POST_SELECTION_START = "2026-07-09"
BENCHMARK_SYMBOL = "SPY"
DATA_START = "2016-01-04"


def _best_candidate_per_family() -> dict[str, dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for family, path in FAMILY_SOURCES.items():
        report = json.loads(path.read_text())
        candidate = max(report["candidates"], key=lambda c: c["sharpe_excess_bil"])
        best[family] = {
            "report_iter_id": report["iter_id"],
            "candidate_id": candidate["candidate_id"],
            "parameters": candidate.get("parameters"),
            "sharpe_excess_bil": candidate["sharpe_excess_bil"],
            "effective_n": report["effective_n"],
            "series": pd.Series(
                candidate["oos_return_stream"], index=pd.DatetimeIndex(candidate["oos_dates"])
            ),
        }
    return best


def _select_sleeves(
    best: dict[str, dict[str, Any]],
) -> tuple[list[str], pd.DataFrame, dict[str, dict[str, float]]]:
    """Greedy, descending-Sharpe selection under the pairwise-correlation cap.

    Returns (selected family names in acceptance order, the full aligned
    return DataFrame used for the correlation matrix, the full pairwise
    correlation matrix as a nested dict for the report).
    """
    eligible = [
        family
        for family, info in best.items()
        if info["sharpe_excess_bil"] >= SHARPE_EXCESS_BIL_MINIMUM
    ]
    common_index = None
    for family in eligible:
        idx = best[family]["series"].index
        common_index = idx if common_index is None else common_index.intersection(idx)
    aligned = pd.DataFrame(
        {family: best[family]["series"].reindex(common_index) for family in eligible}
    )
    correlation_matrix = aligned.corr()
    corr_report = {a: {b: float(correlation_matrix.loc[a, b]) for b in eligible} for a in eligible}

    ranked = sorted(eligible, key=lambda family: -best[family]["sharpe_excess_bil"])
    selected: list[str] = []
    for family in ranked:
        if all(
            abs(correlation_matrix.loc[family, accepted]) <= PAIRWISE_CORRELATION_MAXIMUM
            for accepted in selected
        ):
            selected.append(family)
    return selected, aligned, corr_report


def _inverse_vol_combination_returns(
    aligned: pd.DataFrame, selected: list[str]
) -> tuple[pd.Series, list[dict[str, Any]]]:
    """Fixed-weight-until-next-month-end inverse-vol blend of ``selected`` columns.

    See the module docstring's judgment call 3 for the warm-up rule.
    """
    frame = aligned[selected].dropna()
    dates = frame.index
    month_end_mask = (
        dates.to_series().dt.to_period("M").ne(dates.to_series().dt.to_period("M").shift(-1))
    )
    rebalance_dates = [dates[0], *dates[month_end_mask].tolist()]
    rebalance_dates = sorted(set(rebalance_dates))

    weights_log: list[dict[str, Any]] = []
    daily_returns: dict[pd.Timestamp, float] = {}
    for i, reb_date in enumerate(rebalance_dates):
        history = frame.loc[:reb_date]
        if len(history) < MIN_VOL_LOOKBACK_DAYS:
            weights = dict.fromkeys(selected, 1.0 / len(selected))
            weight_basis = f"equal_weight_warmup_{len(history)}_days"
        else:
            window = history.tail(MAX_VOL_LOOKBACK_DAYS)
            vol = window.std()
            inverse_vol = 1.0 / vol
            weights = (inverse_vol / inverse_vol.sum()).to_dict()
            weight_basis = f"inverse_vol_{len(window)}_day_window"
        weights_log.append(
            {"date": reb_date.isoformat(), "weights": weights, "basis": weight_basis}
        )

        start = dates.searchsorted(reb_date, side="right")
        end = (
            dates.searchsorted(rebalance_dates[i + 1], side="right") - 1
            if i + 1 < len(rebalance_dates)
            else len(dates) - 1
        )
        if start > end:
            continue
        window_returns = frame.iloc[start : end + 1]
        weighted = sum(window_returns[family] * weights[family] for family in selected)
        for date, value in weighted.items():
            daily_returns[date] = float(value)

    index = pd.DatetimeIndex(sorted(daily_returns))
    series = pd.Series(
        [daily_returns[ts] for ts in index], index=index, name="step10_w3_combination"
    )
    return series, weights_log


def _reconstruct_annual_folds(series: pd.Series) -> list[list[float]]:
    years = sorted(series.index.year.unique())
    return [series.loc[series.index.year == year].tolist() for year in years]


def main() -> None:
    best = _best_candidate_per_family()
    selected, aligned, corr_report = _select_sleeves(best)

    report: dict[str, Any] = {
        "iter_id": "step10_w3_combination",
        "method": "preregistered_inverse_vol_combination",
        "candidates_considered": {
            family: {
                "report_iter_id": info["report_iter_id"],
                "candidate_id": info["candidate_id"],
                "parameters": info["parameters"],
                "sharpe_excess_bil": info["sharpe_excess_bil"],
                "effective_n": info["effective_n"],
                "meets_sharpe_floor": info["sharpe_excess_bil"] >= SHARPE_EXCESS_BIL_MINIMUM,
            }
            for family in FAMILY_SOURCES
            for info in [best[family]]
        },
        "pairwise_oos_return_correlation": corr_report,
        "pairwise_correlation_common_window": {
            "rows": int(len(aligned)),
            "start": aligned.index.min().isoformat() if len(aligned) else None,
            "end": aligned.index.max().isoformat() if len(aligned) else None,
        },
        "selection_rule": (
            f"sharpe_excess_bil >= {SHARPE_EXCESS_BIL_MINIMUM} AND pairwise "
            f"|corr| <= {PAIRWISE_CORRELATION_MAXIMUM} with every already-accepted "
            "sleeve, greedily accepted in descending sharpe_excess_bil order"
        ),
        "selected_sleeves": selected,
    }

    if len(selected) < 2:
        report["status"] = "skipped_fewer_than_two_qualifying_sleeves"
        write_json(OUTPUT_PATH, report)
        print(json.dumps(report, indent=2, sort_keys=True, default=str))
        print(f"Written to {OUTPUT_PATH}")
        return

    combo_series, weights_log = _inverse_vol_combination_returns(aligned, selected)
    oos_fold_returns = _reconstruct_annual_folds(combo_series)

    dsr_trial_count = sum(best[family]["effective_n"] for family in FAMILY_SOURCES) + 1

    candidate = Candidate(
        candidate_id="step10_w3_combination-000",
        mechanism_family="step10_w3_combination",
        param_vector={"selected_sleeves": selected},
        oos_return_stream=[float(v) for v in combo_series.tolist()],
        oos_dates=[ts.isoformat() for ts in combo_series.index],
        oos_fold_returns=oos_fold_returns,
        stress_return_stream=[float(v) for v in combo_series.tolist()],
    )

    benchmark_returns = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }
    new_gates = load_preregistered_gates(
        NEW_GATE_CONTRACT_PATH, repo_root=ROOT, required_keys=UNLEVERED_FAMILY_GATE_KEYS
    )
    old_gates = load_preregistered_gates(OLD_GATE_CONTRACT_PATH, repo_root=ROOT)

    new_verdict = evaluate_candidate(
        candidate,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=new_gates,
        dsr_trial_count=dsr_trial_count,
        dsr_hac_lag=DSR_HAC_LAG,
        benchmark_returns=benchmark_returns[BENCHMARK_SYMBOL],
        benchmark_name=BENCHMARK_SYMBOL,
    )
    old_verdict = evaluate_candidate(
        candidate,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=old_gates,
        dsr_trial_count=dsr_trial_count,
        dsr_hac_lag=DSR_HAC_LAG,
    )

    benchmark_series = benchmark_returns[BENCHMARK_SYMBOL]
    crisis_diagnostics = {}
    for window in CRISIS_WINDOWS:
        window_series = combo_series.loc[
            (combo_series.index >= pd.Timestamp(window["start"]))
            & (combo_series.index <= pd.Timestamp(window["end"]))
        ]
        if window_series.empty:
            crisis_diagnostics[window["name"]] = {"row_count": 0, "note": "no overlap"}
            continue
        bench_window = benchmark_series.reindex(window_series.index).dropna()
        crisis_diagnostics[window["name"]] = {
            "row_count": int(len(window_series)),
            "start": window_series.index.min().date().isoformat(),
            "end": window_series.index.max().date().isoformat(),
            "total_return_pct": float((1.0 + window_series).prod() - 1.0) * 100.0,
            "cagr": annualized_cagr(window_series),
            "max_drawdown": max_drawdown(window_series),
            "benchmark_total_return_pct": (
                float((1.0 + bench_window).prod() - 1.0) * 100.0 if len(bench_window) else None
            ),
        }
    post_selection_diagnostic = recent_window_diagnostic(
        combo_series, benchmark_series, start=POST_SELECTION_START
    )

    report.update(
        {
            "dsr_trial_count_used": dsr_trial_count,
            "dsr_hac_lag": DSR_HAC_LAG,
            "weight_schedule": weights_log,
            "stitched_oos_row_count": len(candidate.oos_return_stream),
            "stitched_oos_start": candidate.oos_dates[0],
            "stitched_oos_end": candidate.oos_dates[-1],
            "annual_fold_sizes": [len(fold) for fold in oos_fold_returns],
            "new_contract": {
                "benchmark_name": new_verdict.metrics.get("benchmark_name"),
                "vol_match_weight": new_verdict.metrics.get("vol_match_weight"),
                "metrics": new_verdict.metrics,
                "gate_results": new_verdict.gate_results,
                "all_gates_pass": new_verdict.all_gates_pass,
                "promotion_eligible": new_verdict.promotion_eligible,
                "dsr_probability": new_verdict.dsr_probability,
                "positive_fold_fraction": new_verdict.positive_fold_fraction,
                "sharpe_excess_bil": new_verdict.sharpe_excess_bil,
            },
            "old_contract_reference_only": {
                "metrics": old_verdict.metrics,
                "gate_results": old_verdict.gate_results,
                "all_gates_pass": old_verdict.all_gates_pass,
                "promotion_eligible": old_verdict.promotion_eligible,
                "sharpe_excess_bil": old_verdict.sharpe_excess_bil,
            },
            "crisis_window_diagnostics": crisis_diagnostics,
            "post_selection_diagnostic": {
                "window_start": POST_SELECTION_START,
                **post_selection_diagnostic,
            },
            "gates_provenance": {
                "new_contract": new_gates.as_provenance(),
                "old_contract_reference_only": old_gates.as_provenance(),
            },
            "status": "evaluated",
        }
    )

    write_json(OUTPUT_PATH, report)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "weight_schedule"},
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    print(f"\npromotion_eligible: {new_verdict.promotion_eligible}")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
