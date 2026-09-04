"""Step 10 Wave 1 F2: cross-asset ETF time-series momentum, SIP daily bars.

Why a standalone research-track script instead of a router evaluation:
docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 4.2 asks
to check whether core_beta_satellite_router can express this mechanism
first. It cannot -- see
open_composer.research.kernel.mechanisms.cross_asset_trend_etf's module
docstring for the specific structural reasons (hard-coded QQQ/TQQQ core leg,
satellite sleeve as a small additive tilt rather than the dominant portfolio
construction, non-functional universe_mode label, a single hard-coded theme
gate symbol). This is therefore **not** paper-account-executable this week;
the 12-candidate grid below is evaluated purely from daily return series
through the same P1b mechanism-evaluation harness every other Step 10
candidate goes through, so its evidence is directly comparable even though
its execution path does not exist yet.

The 12-candidate grid (lookback_months x top_n x weighting) is preregistered
in reports/research/iterations/step10_w1_cross_asset_trend/candidate-
manifest.json (generated via scripts/new_lightweight_iteration.py) *before*
this script runs; this script reads the grid from
cross_asset_trend_etf.PARAMETER_SPACE, which is the exact list the manifest
was generated from (single source of truth -- see that module's
PARAMETER_SPACE docstring comment), so no candidate can be added or removed
after the fact without also touching the mechanism module.

Same method as scripts/evaluate_champion_route_sip.py and scripts/evaluate_
beta_exposure_family_sip.py (rolling-origin walk-forward, embargo, DSR,
effective-independent-trials clustering via the two-pass idiom from
scripts/search_intraday_momentum_etf.py, crisis-window + post-selection
diagnostics, vol-matched-benchmark new-contract verdict alongside the old
contract for reference only). Benchmark family is SPY for both contracts
(plan section 4.2: "基准族 SPY"), the same benchmark for every candidate
(unlike F1, which selects QQQ or SPY per candidate's own market) since this
mechanism has no single natural "home" symbol -- SPY is the largest, most
liquid single proxy for the family's overall market exposure.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.research.campaign_statistics import annualized_sharpe
from open_composer.research.kernel.benchmark_returns import daily_returns_on_naive_dates
from open_composer.research.kernel.gate_contract import (
    UNLEVERED_FAMILY_GATE_KEYS,
    load_preregistered_gates,
)
from open_composer.research.kernel.mechanism_eval import (
    Mechanism,
    annualized_cagr,
    evaluate_family,
    expand_mechanism,
    max_drawdown,
    recent_window_diagnostic,
)
from open_composer.research.kernel.mechanisms.cross_asset_trend_etf import (
    ALL_SYMBOLS,
    CASH_SYMBOL,
    PARAMETER_SPACE,
    daily_cross_asset_trend_returns,
)
from open_composer.research.route_cross_source import CRISIS_WINDOWS
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "step10_w1_cross_asset_trend"
    / "candidate-manifest.json"
)
OUTPUT_PATH = ROOT / "reports" / "research" / "control" / "step10-w1-cross-asset-trend-2026-09.json"
NEW_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "unlevered-family-paper-tier-gates.json"
OLD_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"

DATA_START = "2016-01-04"
FOLD_COUNT = 5
BASE_COST_BPS_PER_SIDE = 5.0
STRESS_COST_BPS_PER_SIDE = 40.0
DSR_HAC_LAG = 21
POST_SELECTION_START = "2026-07-09"
BENCHMARK_SYMBOL = "SPY"
#: Minimum independent-trial floor -- see scripts/evaluate_beta_exposure_family_sip.py's
#: identical constant for the full rationale (deflated_sharpe_probability
#: requires trial_count >= 2; matches
#: open_composer.research.kernel.layered_search._MIN_DSR_TRIAL_COUNT).
_MIN_DSR_TRIAL_COUNT = 2


def _validate_manifest_matches_parameter_space() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows = manifest["candidates"]
    if len(rows) != len(PARAMETER_SPACE):
        raise ValueError(
            f"preregistered manifest has {len(rows)} candidates, "
            f"PARAMETER_SPACE has {len(PARAMETER_SPACE)}; they must match exactly"
        )
    for row, point in zip(rows, PARAMETER_SPACE, strict=True):
        if row["parameters"] != point:
            raise ValueError(
                f"manifest candidate {row['candidate_id']} parameters {row['parameters']} "
                f"do not match PARAMETER_SPACE point {point}"
            )


def _load_returns_panel() -> pd.DataFrame:
    series_by_symbol = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START) for symbol in ALL_SYMBOLS
    }
    panel = pd.concat(series_by_symbol, axis=1, join="inner")
    panel.columns = list(ALL_SYMBOLS)
    if panel.isna().any().any():
        raise ValueError("returns panel contains NaN after inner join -- symbol coverage mismatch")
    if panel.empty:
        raise ValueError("returns panel is empty -- no common trading dates across all 11 symbols")
    return panel


def _trading_activity_from_rebalances(
    panel_index: pd.DatetimeIndex, rebalance_sink: list[dict[str, Any]]
) -> dict[str, float]:
    """Derive time-in-market / turnover / holding-period stats from the exact
    rebalance decisions daily_cross_asset_trend_returns actually traded.

    A "position" is one symbol's one contiguous span of nonzero weight across
    one or more consecutive holding periods; "round trip" counts completed
    positions (opened and later closed, or open through the end of the data).
    """
    n = len(rebalance_sink)
    rebalance_positions = [int(panel_index.get_loc(entry["date"])) for entry in rebalance_sink]
    total_days = 0
    invested_days = 0
    open_since: dict[str, int] = {}
    last_period_end: dict[str, int] = {}
    completed_holding_days: list[int] = []
    for i, entry in enumerate(rebalance_sink):
        start = rebalance_positions[i] + 1
        end = rebalance_positions[i + 1] if i + 1 < n else len(panel_index) - 1
        selected = (
            {
                symbol
                for symbol, weight in entry["weights"].items()
                if symbol != CASH_SYMBOL and weight > 0
            }
            if start <= end
            else set()
        )
        for symbol in list(open_since):
            if symbol not in selected:
                completed_holding_days.append(last_period_end[symbol] - open_since.pop(symbol) + 1)
                last_period_end.pop(symbol, None)
        for symbol in selected:
            open_since.setdefault(symbol, start)
            last_period_end[symbol] = end
        if start <= end:
            span_days = end - start + 1
            total_days += span_days
            if selected:
                invested_days += span_days
    for symbol, opened_at in open_since.items():
        completed_holding_days.append(last_period_end[symbol] - opened_at + 1)

    round_trips = len(completed_holding_days)
    return {
        "exposure_pct": (invested_days / total_days * 100.0) if total_days else 0.0,
        "annualized_turnover_events": (round_trips / total_days * 252.0) if total_days else 0.0,
        "average_holding_period_days": (
            sum(completed_holding_days) / round_trips if round_trips else 0.0
        ),
        "total_days": total_days,
        "round_trips": round_trips,
    }


def _bounded_window_diagnostic(
    returns: pd.Series,
    benchmark: pd.Series,
    *,
    start: str,
    end: str,
    minimum_rows: int = 5,
) -> dict[str, float | int | str | None]:
    """Same shape as evaluate_champion_route_sip._bounded_window_diagnostic."""
    window = returns.loc[
        (returns.index >= pd.Timestamp(start)) & (returns.index <= pd.Timestamp(end))
    ]
    bench_window = benchmark.reindex(window.index).dropna()
    if len(window) <= minimum_rows:
        return {
            "row_count": int(len(window)),
            "start": start,
            "end": end,
            "total_return_pct": None,
            "cagr": None,
            "sharpe": None,
            "max_drawdown": None,
            "benchmark_total_return_pct": None,
        }
    total_return = float((1.0 + window).prod() - 1.0)
    benchmark_total = (
        float((1.0 + bench_window).prod() - 1.0) if len(bench_window) > minimum_rows else None
    )
    return {
        "row_count": int(len(window)),
        "start": window.index.min().date().isoformat(),
        "end": window.index.max().date().isoformat(),
        "total_return_pct": total_return * 100.0,
        "cagr": annualized_cagr(window),
        "sharpe": float(annualized_sharpe(window.to_numpy())),
        "max_drawdown": max_drawdown(window),
        "benchmark_total_return_pct": benchmark_total * 100.0 if benchmark_total else None,
    }


def main() -> None:
    _validate_manifest_matches_parameter_space()
    panel = _load_returns_panel()
    benchmark_returns = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }

    def _signal_fn(params: dict[str, Any]) -> pd.Series:
        return daily_cross_asset_trend_returns(panel, params)

    def _stress_signal_fn(params: dict[str, Any]) -> pd.Series:
        return daily_cross_asset_trend_returns(
            panel, {**params, "cost_bps_per_side": STRESS_COST_BPS_PER_SIDE}
        )

    mechanism = Mechanism(
        family="cross_asset_trend_etf_time_series_momentum",
        signal_fn=_signal_fn,
        stress_signal_fn=_stress_signal_fn,
        param_space=PARAMETER_SPACE,
    )
    candidates = expand_mechanism(mechanism, fold_count=FOLD_COUNT)

    old_gates = load_preregistered_gates(OLD_GATE_CONTRACT_PATH, repo_root=ROOT)
    new_gates = load_preregistered_gates(
        NEW_GATE_CONTRACT_PATH, repo_root=ROOT, required_keys=UNLEVERED_FAMILY_GATE_KEYS
    )

    probe_family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=old_gates,
        dsr_trial_count=len(candidates),
        dsr_hac_lag=DSR_HAC_LAG,
    )
    effective_trial_count = max(probe_family.effective_n, _MIN_DSR_TRIAL_COUNT)

    old_contract_family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=old_gates,
        dsr_trial_count=effective_trial_count,
        dsr_hac_lag=DSR_HAC_LAG,
    )
    new_contract_family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=new_gates,
        dsr_trial_count=effective_trial_count,
        dsr_hac_lag=DSR_HAC_LAG,
        benchmark_returns=benchmark_returns[BENCHMARK_SYMBOL],
        benchmark_name=BENCHMARK_SYMBOL,
    )

    per_candidate_reports = []
    passing_new_contract = []
    for params, old_verdict, new_verdict in zip(
        PARAMETER_SPACE, old_contract_family.candidates, new_contract_family.candidates, strict=True
    ):
        candidate = old_verdict.candidate
        rebalance_sink: list[dict[str, Any]] = []
        full_series = daily_cross_asset_trend_returns(panel, params, rebalance_sink=rebalance_sink)
        trading_activity = _trading_activity_from_rebalances(panel.index, rebalance_sink)
        benchmark_series = benchmark_returns[BENCHMARK_SYMBOL]

        crisis_diagnostics = {
            window["name"]: _bounded_window_diagnostic(
                full_series, benchmark_series, start=window["start"], end=window["end"]
            )
            for window in CRISIS_WINDOWS
        }
        post_selection_diagnostic = recent_window_diagnostic(
            full_series, benchmark_series, start=POST_SELECTION_START
        )

        row = {
            "candidate_id": candidate.candidate_id,
            "parameters": dict(params),
            "trading_activity": trading_activity,
            "stitched_oos_row_count": len(candidate.oos_return_stream),
            "stitched_oos_start": candidate.oos_dates[0],
            "stitched_oos_end": candidate.oos_dates[-1],
            "new_contract": {
                "benchmark_name": new_verdict.metrics.get("benchmark_name"),
                "vol_match_weight": new_verdict.metrics.get("vol_match_weight"),
                "metrics": new_verdict.metrics,
                "gate_results": new_verdict.gate_results,
                "gates_not_applicable": list(new_verdict.gates_not_applicable),
                "all_gates_pass": new_verdict.all_gates_pass,
                "promotion_eligible": new_verdict.promotion_eligible,
                "dsr_probability": new_verdict.dsr_probability,
                "positive_fold_fraction": new_verdict.positive_fold_fraction,
            },
            "old_contract_reference_only": {
                "metrics": old_verdict.metrics,
                "gate_results": old_verdict.gate_results,
                "all_gates_pass": old_verdict.all_gates_pass,
                "promotion_eligible": old_verdict.promotion_eligible,
                "dsr_probability": old_verdict.dsr_probability,
            },
            "crisis_window_diagnostics": crisis_diagnostics,
            "post_selection_diagnostic": {
                "window_start": POST_SELECTION_START,
                **post_selection_diagnostic,
            },
        }
        per_candidate_reports.append(row)
        if new_verdict.promotion_eligible:
            passing_new_contract.append(candidate.candidate_id)

    report = {
        "iter_id": "step10_w1_cross_asset_trend",
        "candidate_manifest_path": str(MANIFEST_PATH.relative_to(ROOT)),
        "method": "cross_asset_trend_etf_time_series_momentum",
        "evaluation_methodology": "mechanism_eval_harness_p1b_sip_vol_matched_standalone_kernel",
        "product_executable": False,
        "product_executable_reason": (
            "core_beta_satellite_router cannot express this mechanism -- see "
            "open_composer/research/kernel/mechanisms/cross_asset_trend_etf.py "
            "module docstring for the specific structural reasons (hard-coded "
            "QQQ/TQQQ core leg via core_route_label's literal f-string, "
            "universe_mode never read by _target_snapshot, satellite sleeve "
            "sized as a small additive tilt via satellite_budget rather than "
            "the dominant portfolio construction this mechanism needs, single "
            "hard-coded theme-gate symbol SMH, and a 0%-return CASH leg "
            "instead of BIL's actual return). No product mapping exists this "
            "week; this evaluation is research-track only."
        ),
        "note": (
            "12 preregistered candidates crossing lookback_months in {6, 12}, "
            "top_n in {3, 5, all}, weighting in {equal, inverse_vol_60d} over "
            "SPY, QQQ, IWM, EFA, EEM, TLT, IEF, GLD, DBC, VNQ with a BIL cash "
            "overlay. Judged under config/promotion/unlevered-family-paper-"
            "tier-gates.json (new contract, vol-matched against SPY); the "
            "existing kernel-paper-tier-gates.json result is reported "
            "per-candidate under old_contract_reference_only for reference, "
            "never as the verdict."
        ),
        "data_source": "sip_parquet_via_daily_returns_on_naive_dates",
        "data_window": {
            "requested_start": DATA_START,
            "common_dates": len(panel),
            "first_common_date": panel.index[0].date().isoformat(),
            "last_common_date": panel.index[-1].date().isoformat(),
            "symbols": list(ALL_SYMBOLS),
        },
        "fold_count": FOLD_COUNT,
        "base_cost_bps_per_side": BASE_COST_BPS_PER_SIDE,
        "stress_cost_bps_per_side": STRESS_COST_BPS_PER_SIDE,
        "dsr_hac_lag": DSR_HAC_LAG,
        "benchmark_symbol": BENCHMARK_SYMBOL,
        "raw_candidate_count": probe_family.raw_candidate_count,
        "effective_n": probe_family.effective_n,
        "breadth_ratio": probe_family.breadth_ratio,
        "dsr_trial_count_used": effective_trial_count,
        "candidates": per_candidate_reports,
        "candidates_passing_new_contract": passing_new_contract,
        "gates_provenance": {
            "new_contract": new_gates.as_provenance(),
            "old_contract_reference_only": old_gates.as_provenance(),
        },
    }
    write_json(OUTPUT_PATH, report)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "candidates"},
            indent=2,
            sort_keys=True,
            default=str,
        )
    )
    print(f"\ncandidates_passing_new_contract: {passing_new_contract}")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
