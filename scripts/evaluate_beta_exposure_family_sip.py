"""Step 10 Wave 1 F1: volatility-managed beta exposure router family, SIP daily bars.

Why: docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 4.1
asks whether a trend/momentum/drawdown-gated, volatility-targeted long
position in a single liquid market ETF (QQQ or SPY) -- falling back to BIL
when risk-off -- can clear the new vol-matched-benchmark unlevered-family
promotion contract (config/promotion/unlevered-family-paper-tier-gates.json).
This is a router the daily paper cycle can already execute
(open_composer.research.beta_router_core.beta_target_weight_snapshot), unlike
a hand-rolled research-only mechanism.

The 24-candidate grid (market x trend_sma_days x target_volatility_annual_pct
x max_drawdown_pct) is preregistered in
reports/research/iterations/step10_w1_beta_exposure/candidate-manifest.json
(generated via scripts/new_lightweight_iteration.py, single-mechanism
lightweight path -- see open_composer/research/iteration_dossier.py) *before*
this script ever runs it; this script reads the grid from that committed
manifest rather than re-declaring it, so the preregistered set is
structurally the only set that can be evaluated -- no candidate can be added
or removed after the fact without also editing (and re-registering) the
manifest.

Same method as scripts/evaluate_champion_route_sip.py (rolling-origin walk-
forward, embargo, DSR, effective-independent-trials clustering, crisis-window
+ post-selection diagnostics), extended with two things specific to this
Wave:

1. Two-pass DSR trial-count idiom (see scripts/search_intraday_momentum_etf.py):
   a first "probe" pass reads ``effective_n`` off the full 24-candidate
   correlation clustering (which does not depend on which gate contract or
   benchmark was passed), then every candidate is re-scored at that honest
   effective N.
2. A per-candidate benchmark selection for the new contract's vol-matched
   evaluation: QQQ-market candidates are judged against a QQQ-vol-matched
   benchmark, SPY-market candidates against an SPY-vol-matched benchmark
   (config's benchmark_families.beta_exposure_router =
   "risk_on_symbol_buy_and_hold"). evaluate_family applies one shared
   benchmark_returns to every candidate, so the new-contract verdicts are
   computed with a manual per-candidate evaluate_candidate loop instead,
   reusing the exact same effective_trial_count from the probe pass.

The existing kernel-paper-tier-gates.json ("old") contract's result is also
reported, for reference only -- never as the verdict (plan section 4: "裁定
用 3.2 的新合同；同时报告现有 QQQ 合同的结果作为参照（不作裁定）").
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.beta_router_core import (
    BetaRouterDataset,
    BetaRouterParams,
    beta_params_from_label,
    beta_target_weight_snapshot,
    load_beta_router_dataset,
)
from open_composer.research.campaign_statistics import annualized_sharpe
from open_composer.research.kernel.benchmark_returns import daily_returns_on_naive_dates
from open_composer.research.kernel.gate_contract import (
    UNLEVERED_FAMILY_GATE_KEYS,
    load_preregistered_gates,
)
from open_composer.research.kernel.mechanism_eval import (
    Mechanism,
    annualized_cagr,
    evaluate_candidate,
    evaluate_family,
    expand_mechanism,
    max_drawdown,
    recent_window_diagnostic,
)
from open_composer.research.route_cross_source import CRISIS_WINDOWS
from open_composer.research.router_common import (
    RouterMetrics,
    backtest_router_params,
    effective_lookback,
)
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = ROOT / "strategy_specs" / "drafts" / "step10_w1_beta_exposure_router_family.yaml"
MANIFEST_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "step10_w1_beta_exposure"
    / "candidate-manifest.json"
)
OUTPUT_DIR = ROOT / "reports" / "research" / "control"
OUTPUT_PATH = OUTPUT_DIR / "step10-w1-beta-exposure-2026-09.json"
NEW_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "unlevered-family-paper-tier-gates.json"
OLD_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"

DATA_START = "2016-01-04"
FOLD_COUNT = 5
BASE_SLIPPAGE_BPS = 5.0
STRESS_SLIPPAGE_BPS = 40.0
DSR_HAC_LAG = 21
#: Same anchor as scripts/evaluate_champion_route_sip.py -- the date Step 7.R's
#: ml-gate evaluation work made this project's current numbers visible.
POST_SELECTION_START = "2026-07-09"
MARKETS = ("QQQ", "SPY")
#: Minimum independent-trial floor -- matches
#: ``open_composer.research.kernel.layered_search._MIN_DSR_TRIAL_COUNT``'s own
#: reasoning: deflated_sharpe_probability requires trial_count >= 2
#: (campaign_statistics.deflated_sharpe_probability raises below that), and 2
#: is the smallest, most conservative floor when clustering collapses
#: everything to very few effective trials. (scripts/search_intraday_momentum
#: _etf.py's max(effective_n, 1) does not apply this floor and would crash the
#: same way if its own grid ever clustered to effective_n == 1; not fixed here
#: since it is out of this Wave's scope.)
_MIN_DSR_TRIAL_COUNT = 2


def _load_candidate_rows() -> list[dict]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows = manifest["candidates"]
    if len(rows) != 24:
        raise ValueError(
            f"expected the preregistered grid to have exactly 24 candidates, found {len(rows)}"
        )
    return rows


def _validate_label_round_trip(params_by_id: dict[str, BetaRouterParams]) -> None:
    for candidate_id, params in params_by_id.items():
        label = params.label
        recovered = beta_params_from_label(label)
        if recovered != params:
            raise ValueError(
                f"{candidate_id}: beta_params_from_label round-trip mismatch for {label!r}: "
                f"{recovered!r} != {params!r}"
            )


def _route_backtest(
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    params: BetaRouterParams,
    *,
    stress_slippage_bps: float | None,
) -> tuple[pd.Series, RouterMetrics]:
    """Run one candidate through backtest_router_params; return (series, metrics).

    ``dataset`` carries only prices and dates, so swapping in a cost-stressed
    spec copy for the stress variant changes nothing else about the
    simulation -- same weights, same dates, only the per-switch friction
    assumption (same pattern as evaluate_champion_route_sip._route_daily_returns).
    """
    working_spec = spec
    if stress_slippage_bps is not None:
        working_spec = spec.model_copy(
            update={"costs": spec.costs.model_copy(update={"slippage_bps": stress_slippage_bps})}
        )
    lookback = effective_lookback(params)
    metrics = backtest_router_params(
        working_spec,
        dataset,
        params,
        snapshot=lambda _spec, data, route, index: beta_target_weight_snapshot(data, route, index),
        start_index=lookback,
        end_index=len(dataset.dates),
        capture_returns=True,
    )
    dates = dataset.dates[lookback : lookback + metrics.days]
    series = pd.Series(
        list(metrics.daily_returns), index=pd.DatetimeIndex(dates), name=params.label
    )
    if series.isna().any():
        raise ValueError(f"{params.label} return series contains non-finite values")
    return series, metrics


def _route_returns_series(
    spec: StrategySpec,
    dataset: BetaRouterDataset,
    params: BetaRouterParams,
    *,
    stress_slippage_bps: float | None,
) -> pd.Series:
    series, _ = _route_backtest(spec, dataset, params, stress_slippage_bps=stress_slippage_bps)
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

    Needed because the three fixed historical crisis windows (2018, 2020) fall
    well before this family's 5-year rolling-origin OOS test window, so they
    can only be read off the full raw return series computed here, not off
    candidate.oos_return_stream (same pattern as
    evaluate_champion_route_sip._bounded_window_diagnostic).
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


def _trading_activity(metrics: RouterMetrics) -> dict[str, float]:
    annualized_turnover_events = (metrics.round_trips / metrics.days * 252) if metrics.days else 0.0
    average_holding_period_days = (
        metrics.traded_days / metrics.round_trips
        if metrics.round_trips
        else float(metrics.traded_days)
    )
    return {
        "exposure_pct": metrics.exposure_pct,
        "annualized_turnover_events": annualized_turnover_events,
        "average_holding_period_days": average_holding_period_days,
        "traded_days": metrics.traded_days,
        "round_trips": metrics.round_trips,
        "total_days": metrics.days,
    }


def main() -> None:
    base_spec = load_strategy_spec(SPEC_PATH)
    spec = base_spec.model_copy(
        update={
            "costs": base_spec.costs.model_copy(
                update={"commission_pct": 0.0, "slippage_bps": BASE_SLIPPAGE_BPS}
            )
        }
    )

    candidate_rows = _load_candidate_rows()
    candidate_ids_in_order = [row["candidate_id"] for row in candidate_rows]
    params_by_id = {
        row["candidate_id"]: BetaRouterParams(**row["parameters"]) for row in candidate_rows
    }
    _validate_label_round_trip(params_by_id)

    datasets: dict[str, BetaRouterDataset] = {
        market: load_beta_router_dataset(
            root=ROOT,
            market_symbol=market,
            leverage_symbol="TQQQ",
            hedge_symbol=None,
            extra_symbols=["BIL"],
            timeframe="daily",
            data_source="sip_parquet",
            feed=None,
            start=DATA_START,
            end=None,
            refresh_data=False,
        )
        for market in MARKETS
    }

    benchmark_returns: dict[str, pd.Series] = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("QQQ", "SPY", "TQQQ", "BIL")
    }

    param_space = [dict(row["parameters"]) for row in candidate_rows]

    def _dataset_for_point(point: dict) -> BetaRouterDataset:
        return datasets[point["risk_on_symbol"]]

    def _signal_fn(point: dict) -> pd.Series:
        return _route_returns_series(
            spec, _dataset_for_point(point), BetaRouterParams(**point), stress_slippage_bps=None
        )

    def _stress_signal_fn(point: dict) -> pd.Series:
        return _route_returns_series(
            spec,
            _dataset_for_point(point),
            BetaRouterParams(**point),
            stress_slippage_bps=STRESS_SLIPPAGE_BPS,
        )

    mechanism = Mechanism(
        family="beta_exposure_router_volatility_managed",
        signal_fn=_signal_fn,
        stress_signal_fn=_stress_signal_fn,
        param_space=param_space,
    )
    candidates = expand_mechanism(mechanism, fold_count=FOLD_COUNT)
    if len(candidates) != len(candidate_ids_in_order):
        raise ValueError("expand_mechanism produced a different candidate count than the manifest")

    old_gates = load_preregistered_gates(OLD_GATE_CONTRACT_PATH, repo_root=ROOT)
    new_gates = load_preregistered_gates(
        NEW_GATE_CONTRACT_PATH, repo_root=ROOT, required_keys=UNLEVERED_FAMILY_GATE_KEYS
    )

    # Probe pass: effective_n from clustering does not depend on which gate
    # contract or benchmark is supplied (it only looks at the candidates' own
    # OOS return streams), so this pass both establishes the honest trial
    # count AND stands in as the old-contract *first-pass* scoring.
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

    # Old contract, re-scored at the honest effective N. Reference only.
    old_contract_family = evaluate_family(
        candidates,
        qqq_returns=benchmark_returns["QQQ"],
        tqqq_returns=benchmark_returns["TQQQ"],
        bil_returns=benchmark_returns["BIL"],
        gates=old_gates,
        dsr_trial_count=effective_trial_count,
        dsr_hac_lag=DSR_HAC_LAG,
    )

    # New contract, per-candidate vol-matched benchmark selection. This is the
    # verdict that decides promotion eligibility for this Wave.
    new_contract_verdicts = []
    for verdict in old_contract_family.candidates:
        candidate = verdict.candidate
        market = candidate.param_vector["risk_on_symbol"]
        new_contract_verdicts.append(
            evaluate_candidate(
                candidate,
                qqq_returns=benchmark_returns["QQQ"],
                tqqq_returns=benchmark_returns["TQQQ"],
                bil_returns=benchmark_returns["BIL"],
                gates=new_gates,
                dsr_trial_count=effective_trial_count,
                dsr_hac_lag=DSR_HAC_LAG,
                benchmark_returns=benchmark_returns[market],
                benchmark_name=market,
            )
        )

    per_candidate_reports = []
    passing_new_contract = []
    for candidate_id, old_verdict, new_verdict in zip(
        candidate_ids_in_order, old_contract_family.candidates, new_contract_verdicts, strict=True
    ):
        candidate = old_verdict.candidate
        params = params_by_id[candidate_id]
        market = params.risk_on_symbol
        dataset = datasets[market]
        full_series, full_metrics = _route_backtest(spec, dataset, params, stress_slippage_bps=None)
        benchmark_series = benchmark_returns[market]

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
            "candidate_id": candidate_id,
            "label": params.label,
            "market": market,
            "parameters": dict(candidate.param_vector),
            "trading_activity": _trading_activity(full_metrics),
            "stitched_oos_row_count": len(candidate.oos_return_stream),
            # Wave 3 (docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md
            # section 6) screens sleeves by sharpe_excess_bil >= 0.4 and pairwise
            # OOS-return correlation <= 0.5 -- persisted here so that screening
            # script can read it directly instead of re-running this whole
            # evaluation a second time just to recover one field per candidate.
            "sharpe_excess_bil": old_verdict.sharpe_excess_bil,
            "oos_dates": candidate.oos_dates,
            "oos_return_stream": candidate.oos_return_stream,
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
            passing_new_contract.append(candidate_id)

    report = {
        "iter_id": "step10_w1_beta_exposure",
        "candidate_manifest_path": str(MANIFEST_PATH.relative_to(ROOT)),
        "spec_path": str(SPEC_PATH.relative_to(ROOT)),
        "method": "beta_exposure_router_volatility_managed",
        "evaluation_methodology": "mechanism_eval_harness_p1b_sip_vol_matched",
        "note": (
            "24 preregistered candidates crossing market in {QQQ, SPY}, "
            "trend_sma_days in {100, 200}, target_volatility_annual_pct in "
            "{10, 15, none}, max_drawdown_pct in {none, -15}; leverage_* fixed "
            "to none for all candidates (no TQQQ overlay). Judged under "
            "config/promotion/unlevered-family-paper-tier-gates.json "
            "(new contract, vol-matched-benchmark); the existing kernel-"
            "paper-tier-gates.json result is reported per-candidate under "
            "old_contract_reference_only for reference, never as the verdict."
        ),
        "data_source": "sip_parquet",
        "data_window": {
            "requested_start": DATA_START,
            "by_market": {
                symbol: {
                    "common_dates": len(datasets[symbol].dates),
                    "first_common_date": datasets[symbol].dates[0],
                    "last_common_date": datasets[symbol].dates[-1],
                }
                for symbol in MARKETS
            },
        },
        "fold_count": FOLD_COUNT,
        "base_slippage_bps": BASE_SLIPPAGE_BPS,
        "stress_slippage_bps": STRESS_SLIPPAGE_BPS,
        "dsr_hac_lag": DSR_HAC_LAG,
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
