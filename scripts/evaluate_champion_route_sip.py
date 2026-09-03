"""Re-evaluate the frozen champion route through the P1b mechanism-evaluation
harness, on real SIP daily bars instead of the retired IEX cache its historical
evidence was built on.

Why: docs/finding-iex-cache-price-adjustment-defect-2026-09-01.zh.md section 6.1
found the IEX cache backing this candidate's 11-symbol universe carries 20
phantom single-day jumps over 30% (unadjusted leveraged-ETF splits and reverse
ETFs reacting to them) that SIP with adjustment=all does not have. The
candidate's own spec even declares data_assumptions.adjusted: false. Its
historical evidence must be rebuilt on clean data before anything about it can
be trusted -- not retuned, not re-optimized, replayed exactly as preregistered
(spec.portfolio.selected_route_label parses to the same route parameters,
spec.costs are read verbatim).

This is a thin caller: everything mechanism-agnostic (rolling-origin folds,
gate recomputation, DSR, effective-trials clustering, report shape) lives in
open_composer.research.kernel.mechanism_eval, following the same pattern as
scripts/evaluate_vol02_recalibrated.py (Work Item P1b). This script supplies
only: the route's decision function (built entirely from existing
hybrid_router_core / router_common primitives -- no new router logic is
written here), the frozen parameter vector, and three fixed historical crisis
windows plus a post-selection window as non-gated diagnostics (see
docs/plan-goal-first-verification-2026-09-02.zh.md Wave W3). The crisis
windows are imported from route_cross_source.CRISIS_WINDOWS rather than
redeclared, since that is where they already live in this repository.

No search, no retuning: this script takes no CLI parameters that could change
the route's behavior. The route parameters and costs are read verbatim from
the frozen spec's selected_route_label and costs block.

Gates come from the git-committed config/promotion/kernel-paper-tier-gates.json
contract (see open_composer.research.kernel.gate_contract), so a pass here
means the same thing a kernel-search pass means: promotion_eligible requires
that contract, not a bare-dict threshold that could have been edited after
seeing this result.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import load_sip_bars
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.campaign_statistics import annualized_sharpe
from open_composer.research.hybrid_router_core import (
    _backtest_hybrid_params,
    _effective_lookback,
    _load_daily_hybrid_dataset,
    hybrid_params_from_label,
)
from open_composer.research.kernel.gate_contract import load_preregistered_gates
from open_composer.research.kernel.mechanism_eval import (
    Mechanism,
    annualized_cagr,
    evaluate_family,
    expand_mechanism,
    max_drawdown,
    recent_window_diagnostic,
)
from open_composer.research.route_cross_source import CRISIS_WINDOWS
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = (
    ROOT
    / "strategy_specs"
    / "active"
    / "nasdaq_tqqq_post_drawdown_reentry_router_delayed30_offensive_paper_auto_candidate.yaml"
)
OUTPUT_PATH = (
    ROOT / "reports" / "research" / "control" / "champion-route-sip-revalidation-2026-09.json"
)
GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"

DATA_START = "2016-01-01"
FOLD_COUNT = 5
#: The route's own selected_route_label was picked from a 936-candidate
#: defensive/transition overlay search plus a 25-candidate fixed-live variant
#: check (spec research_design.anti_overfit_notes), both on the retired IEX
#: cache with no return-stream artifact left to cluster into an honest
#: effective-N here. Per the plan's explicit fallback ("找不到就保守取 32"),
#: this uses the kernel's standard single-mechanism ceiling rather than
#: pretending a single re-evaluated route has no multiple-testing history.
DSR_TRIAL_COUNT = 32
DSR_HAC_LAG = 21
STRESS_SLIPPAGE_BPS = 40.0
#: The date the route's ml-gate evaluation work (Step 7.R) made this route's
#: current numbers visible; used as the "does it still work since it was
#: selected" diagnostic start, per the plan.
POST_SELECTION_START = "2026-07-09"


def _benchmark_returns_on_router_dates(frame: pd.DataFrame, symbol: str) -> pd.Series:
    """Daily returns indexed the same way router_common.load_daily_dataset builds
    ``dataset.dates``: SIP timestamps collapsed to plain calendar-date strings,
    then parsed as naive midnight Timestamps.

    Router-produced return series (via ``_route_daily_returns`` below) are
    indexed from ``dataset.dates`` directly, which are plain "YYYY-MM-DD"
    strings -- the router pipeline drops SIP's tz-aware time-of-day component
    when it intersects sessions across symbols. A benchmark series built the
    "obvious" way (``rolling_origin.returns_from_ohlcv``, which keeps the raw
    tz-aware timestamp) has a different index type for the same calendar day,
    so ``Series.reindex`` cannot match them and every row comes back missing.
    """
    rows = frame.loc[frame["symbol"] == symbol].copy()
    rows["timestamp"] = pd.to_datetime(rows["timestamp"], utc=True)
    rows = rows.sort_values("timestamp")
    rows["date"] = rows["timestamp"].dt.date.astype(str)
    rows = rows.drop_duplicates("date", keep="last")
    prices = pd.Series(
        pd.to_numeric(rows["close"], errors="raise").to_numpy(),
        index=pd.DatetimeIndex(rows["date"]),
        name=symbol,
    )
    returns = prices.pct_change(fill_method=None).dropna()
    returns.name = symbol
    return returns


def _route_daily_returns(
    spec: StrategySpec,
    dataset,
    params,
    *,
    stress_slippage_bps: float | None,
) -> pd.Series:
    """Run the frozen route through backtest_router_params and return its daily series.

    ``dataset`` is independent of ``spec.costs`` (it only carries prices and
    dates), so swapping in a cost-stressed spec copy for the stress variant
    changes nothing else about the simulation -- same weights, same dates,
    only the per-switch friction assumption.
    """
    working_spec = spec
    if stress_slippage_bps is not None:
        working_spec = spec.model_copy(
            update={"costs": spec.costs.model_copy(update={"slippage_bps": stress_slippage_bps})}
        )
    lookback = _effective_lookback(params)
    metrics = _backtest_hybrid_params(
        working_spec,
        dataset,
        params,
        start_index=lookback,
        end_index=len(dataset.dates),
        capture_returns=True,
    )
    dates = dataset.dates[lookback : lookback + metrics.days]
    series = pd.Series(
        list(metrics.daily_returns), index=pd.DatetimeIndex(dates), name="champion_route_sip"
    )
    if series.isna().any():
        raise ValueError("champion route SIP return series contains non-finite values")
    return series


def _bounded_window_diagnostic(
    returns: pd.Series,
    benchmark: pd.Series,
    *,
    start: str,
    end: str,
    minimum_rows: int = 5,
) -> dict[str, float | int | str | None]:
    """Same shape as mechanism_eval.recent_window_diagnostic, but [start, end] bounded.

    Needed because the three historical crisis windows (2018, 2020) fall well
    before this route's 5-year rolling-origin OOS test window (the last 5
    calendar years present in the series), so they can only be read off the
    full raw return series computed here, not off candidate.oos_return_stream.
    """
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
    spec = load_strategy_spec(SPEC_PATH)
    label = spec.portfolio.selected_route_label
    if not label:
        raise ValueError(f"{SPEC_PATH} has no selected_route_label")
    params = hybrid_params_from_label(label)

    dataset = _load_daily_hybrid_dataset(
        spec=spec,
        root=ROOT,
        symbols=spec.universe,
        data_source="sip_parquet",
        feed=None,
        start=DATA_START,
        end=None,
        benchmark_symbol="TQQQ",
        market_symbol="QQQ",
        refresh_data=False,
    )

    benchmark_frame = load_sip_bars(("QQQ", "TQQQ", "BIL"), frequency="daily", start=DATA_START)
    benchmark_returns: dict[str, pd.Series] = {
        symbol: _benchmark_returns_on_router_dates(benchmark_frame, symbol)
        for symbol in ("QQQ", "TQQQ", "BIL")
    }

    # Computed once, directly -- this is what feeds the non-gated diagnostics
    # below. The mechanism harness below recomputes the identical primary
    # series internally (via the same signal_fn) for the gated OOS verdict.
    full_route_returns = _route_daily_returns(spec, dataset, params, stress_slippage_bps=None)

    mechanism = Mechanism(
        family="pdr_router_champion_sip",
        signal_fn=lambda _params: _route_daily_returns(
            spec, dataset, params, stress_slippage_bps=None
        ),
        stress_signal_fn=lambda _params: _route_daily_returns(
            spec, dataset, params, stress_slippage_bps=STRESS_SLIPPAGE_BPS
        ),
        param_space=[{"route_label": label}],
    )
    candidates = expand_mechanism(mechanism, fold_count=FOLD_COUNT)
    gates = load_preregistered_gates(GATE_CONTRACT_PATH, repo_root=ROOT)
    family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=gates,
        dsr_trial_count=DSR_TRIAL_COUNT,
        dsr_hac_lag=DSR_HAC_LAG,
    )
    (verdict,) = family.candidates
    candidate = verdict.candidate

    crisis_diagnostics = {
        window["name"]: _bounded_window_diagnostic(
            full_route_returns,
            benchmark_returns["QQQ"],
            start=window["start"],
            end=window["end"],
        )
        for window in CRISIS_WINDOWS
    }
    full_window_diagnostic = _bounded_window_diagnostic(
        full_route_returns,
        benchmark_returns["QQQ"],
        start=full_route_returns.index.min().date().isoformat(),
        end=full_route_returns.index.max().date().isoformat(),
    )
    post_selection_diagnostic = recent_window_diagnostic(
        full_route_returns, benchmark_returns["QQQ"], start=POST_SELECTION_START
    )

    report = {
        "candidate_id": candidate.candidate_id,
        "spec_path": str(SPEC_PATH.relative_to(ROOT)),
        "selected_route_label": label,
        "method": "hybrid_adaptive_router_defensive_transition_overlay_replay",
        "evaluation_methodology": "mechanism_eval_harness_p1b_sip",
        "note": (
            "Frozen route replayed on SIP daily bars (adjustment=all) instead of "
            "the retired IEX cache (data_assumptions.adjusted=false in the active "
            "spec). No parameter search, no retuning: route parameters parsed "
            "verbatim from spec.portfolio.selected_route_label, costs read "
            "verbatim from spec.costs. dsr_trial_count=32 is a conservative "
            "stand-in for this route's real multiple-testing history (936 + 25 "
            "candidate searches on now-retired data with no clusterable return "
            "artifact), not a claim that this is a 1-trial result."
        ),
        "data_source": "sip_parquet",
        "data_window": {
            "requested_start": DATA_START,
            "common_dates": len(dataset.dates),
            "first_common_date": dataset.dates[0],
            "last_common_date": dataset.dates[-1],
        },
        "fold_count": FOLD_COUNT,
        "dsr_trial_count": DSR_TRIAL_COUNT,
        "dsr_hac_lag": DSR_HAC_LAG,
        "stress_slippage_bps": STRESS_SLIPPAGE_BPS,
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
        "gates_provenance": verdict.gates_provenance,
        "gate_contract": verdict.gate_contract,
        "gate_results": verdict.gate_results,
        "gates_not_applicable": list(verdict.gates_not_applicable),
        "evaluated_gate_count": verdict.evaluated_gate_count,
        "all_gates_pass": verdict.all_gates_pass,
        "promotion_eligible": verdict.promotion_eligible,
        "full_window_diagnostic": full_window_diagnostic,
        "crisis_window_diagnostics": crisis_diagnostics,
        "post_selection_diagnostic": {
            "window_start": POST_SELECTION_START,
            **post_selection_diagnostic,
        },
        "raw_candidate_count": family.raw_candidate_count,
        "effective_n": family.effective_n,
        "breadth_ratio": family.breadth_ratio,
    }
    write_json(OUTPUT_PATH, report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(f"\nWritten to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
