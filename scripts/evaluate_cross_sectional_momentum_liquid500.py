"""Step 10 Wave 2: PIT-liquidity-filtered cross-sectional momentum, SIP daily
bars, research track (no product mapping this week).

Why: docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 5
extends the W6 feasibility probe (scripts/duckdb_cross_sectional_
feasibility.py) with a point-in-time liquidity filter -- at every month-end
rebalance date t, the tradable universe is the top 500 symbols by trailing
60-trading-day dollar ADV *as measured at t* (``close > 5`` also evaluated at
t), never a single latest-window ADV snapshot applied to the whole 2016-2026
history (that would use 2026 liquidity to pick which stocks existed in the
2016 universe -- look-ahead). Within that PIT-liquid universe, this month's
long book is the top ``top_fraction`` of names by trailing 12-1 momentum.

Two DuckDB passes keep memory bounded (plan's own guidance: "动量面板只对
并集里的 symbol 算 LAG"): pass 1 scans the full active daily archive ONCE to
build the liquid-500-filtered MONTHLY momentum panel (one row per symbol per
month, not per day); pass 2 -- after every grid candidate's monthly cohorts
are known -- pulls DAILY closes for only the union of symbols ever actually
selected across all cohorts (empirically far smaller than the 500-name
liquid universe itself, since each month only keeps the top 10-15% of it).
Peak RSS is tracked throughout and reported as-is; the plan explicitly
forbids tightening the filter after the fact just to hit an arbitrary memory
number ("超了如实记录，不加大过滤力度硬凑").

**Implementation choice** (not fully specified by the plan, decided and
recorded here): "月度选股、日度盯市的日收益序列（调仓日之间等权持仓逐日计价）"
is implemented as a FIXED-weight-until-next-rebalance portfolio -- every
selected name gets an equal weight (1 / count_selected) at the rebalance
date, held constant (not renormalized to price drift) until the next
rebalance, and marked to market daily. This is the same convention already
used and tested in open_composer.research.kernel.mechanisms.
cross_asset_trend_etf (Wave 1 F2) for consistency across this week's Step 10
candidates, not literal buy-and-hold-with-uncorrected-drift (which would
require tracking each name's own compounding wealth path independently and
differs from this only by a second-order within-period rebalancing effect).
There is no cash leg: unlike F1/F2, this mechanism is always fully invested
in its top_fraction selection (plan section 5 names no BIL fallback).

Same downstream method as scripts/evaluate_beta_exposure_family_sip.py and
scripts/evaluate_cross_asset_trend_sip.py (rolling-origin walk-forward,
embargo, DSR two-pass idiom, crisis-window + post-selection diagnostics,
vol-matched-benchmark new-contract verdict alongside the old contract for
reference only). Benchmark is SPY for both contracts (plan section 5 item 3:
"基准族 SPY").

DuckDB is not a pyproject.toml dependency -- run with:
    uv run --with duckdb python scripts/evaluate_cross_sectional_momentum_liquid500.py
"""

from __future__ import annotations

import json
import resource
import time
from pathlib import Path
from typing import Any

import duckdb
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
from open_composer.research.route_cross_source import CRISIS_WINDOWS
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
ACTIVE_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
OUTPUT_PATH = (
    ROOT / "reports" / "research" / "control" / "step10-w2-cross-sectional-liquid500-2026-09.json"
)
NEW_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "unlevered-family-paper-tier-gates.json"
OLD_GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"

LOOKBACK_DAYS = 252
SKIP_DAYS = 21
ADV_LOOKBACK_DAYS = 60
ADV_TOP_N = 500
FOLD_COUNT = 5
BASE_COST_BPS_PER_SIDE = 5.0
STRESS_COST_BPS_PER_SIDE = 20.0
DSR_HAC_LAG = 21
POST_SELECTION_START = "2026-07-09"
BENCHMARK_SYMBOL = "SPY"
DATA_START = "2016-01-04"
MEMORY_LIMIT = "900MB"
#: See scripts/evaluate_beta_exposure_family_sip.py's identical constant for
#: the full rationale (deflated_sharpe_probability requires trial_count>=2).
_MIN_DSR_TRIAL_COUNT = 2

#: 2 (top_fraction) x 2 (rebalance_stride_months) = 4-combination fixed grid,
#: per docs/plan-step-10-mechanism-supplementation-2026-09-03.zh.md section 5.
PARAMETER_SPACE: list[dict[str, Any]] = [
    {"top_fraction": top_fraction, "rebalance_stride_months": stride}
    for top_fraction in (0.10, 0.15)
    for stride in (1, 2)  # 1 = monthly, 2 = bimonthly
]


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _build_liquid_momentum_panel(con: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """One row per (symbol, month-end) for the point-in-time liquid-500
    universe: trailing 12-1 momentum and the month-end close. Identical
    ranking pipeline to scripts/duckdb_survivorship_bias_comparison_
    liquid500.py's _liquid_momentum_panel, active-universe-only (this is the
    official candidate, not the survivorship stress test -- that is a
    separate, already-run script, see the Wave 2 ledger section).
    """
    query = f"""
        WITH raw AS (
            SELECT symbol, timestamp, close, volume
            FROM read_parquet('{ACTIVE_GLOB}')
            WHERE close > 5.0 AND symbol NOT LIKE '%.%' AND symbol NOT LIKE '%/%'
        ),
        priced AS (
            SELECT
                symbol,
                CAST(timestamp AS DATE) AS trade_date,
                close,
                LAG(close, {SKIP_DAYS}) OVER w AS close_skip,
                LAG(close, {LOOKBACK_DAYS}) OVER w AS close_lookback,
                AVG(close * volume) OVER (
                    PARTITION BY symbol ORDER BY timestamp
                    ROWS BETWEEN {ADV_LOOKBACK_DAYS - 1} PRECEDING AND CURRENT ROW
                ) AS dollar_adv
            FROM raw
            WINDOW w AS (PARTITION BY symbol ORDER BY timestamp)
        ),
        monthly AS (
            SELECT *,
                   ROW_NUMBER() OVER (
                       PARTITION BY symbol, date_trunc('month', trade_date)
                       ORDER BY trade_date DESC
                   ) AS rank_in_month
            FROM priced
            WHERE close_skip IS NOT NULL AND close_lookback IS NOT NULL AND close_skip > 0
                  AND dollar_adv IS NOT NULL
        ),
        month_end AS (
            SELECT * FROM monthly WHERE rank_in_month = 1
        ),
        ranked AS (
            SELECT *,
                   RANK() OVER (
                       PARTITION BY date_trunc('month', trade_date) ORDER BY dollar_adv DESC
                   ) AS adv_rank
            FROM month_end
        )
        SELECT symbol, trade_date, close, (close_skip / close_lookback - 1.0) AS momentum_12_1
        FROM ranked
        WHERE adv_rank <= {ADV_TOP_N}
        ORDER BY trade_date, symbol
    """
    panel = con.execute(query).fetchdf()
    panel["trade_date"] = pd.to_datetime(panel["trade_date"])
    panel["month_key"] = panel["trade_date"].dt.to_period("M")
    return panel


def _monthly_cohorts(
    panel: pd.DataFrame, *, top_fraction: float, rebalance_stride_months: int
) -> list[dict[str, Any]]:
    """One dict per rebalance: {month_end_date, selected} -- selected symbols
    are the top ``top_fraction`` of that month's liquid-500 universe by
    momentum_12_1. ``rebalance_stride_months=2`` (bimonthly) keeps every
    other month-end from the full monthly sequence, so the skipped months'
    universes never influence selection (a real bimonthly trader simply does
    not look at the market on the skipped month-end).
    """
    month_keys = sorted(panel["month_key"].unique())
    rebalance_keys = month_keys[::rebalance_stride_months]
    month_end_date = panel.groupby("month_key")["trade_date"].max()
    cohorts = []
    for month_key in rebalance_keys:
        snapshot = panel.loc[panel["month_key"] == month_key].dropna(subset=["momentum_12_1"])
        if snapshot.empty:
            continue
        cutoff = max(1, round(len(snapshot) * top_fraction))
        selected = snapshot.nlargest(cutoff, "momentum_12_1")["symbol"].tolist()
        cohorts.append(
            {
                "month_end_date": month_end_date.loc[month_key],
                "liquid_universe_size": len(snapshot),
                "selected": selected,
            }
        )
    return cohorts


def _load_daily_returns_for_union(
    con: duckdb.DuckDBPyConnection, symbols: set[str]
) -> pd.DataFrame:
    """Daily returns (wide: index=date, columns=symbol) for exactly the
    union of symbols ever selected across every cohort -- never the full
    liquid-500 (or wider) universe, per the plan's memory-bounding guidance.
    """
    symbol_list = ", ".join(f"'{symbol}'" for symbol in sorted(symbols))
    query = f"""
        WITH raw AS (
            SELECT symbol, timestamp, close
            FROM read_parquet('{ACTIVE_GLOB}')
            WHERE symbol IN ({symbol_list})
        ),
        priced AS (
            SELECT symbol, CAST(timestamp AS DATE) AS trade_date,
                   close / LAG(close) OVER w - 1.0 AS daily_return
            FROM raw
            WINDOW w AS (PARTITION BY symbol ORDER BY timestamp)
        )
        SELECT symbol, trade_date, daily_return FROM priced WHERE daily_return IS NOT NULL
    """
    long_frame = con.execute(query).fetchdf()
    long_frame["trade_date"] = pd.to_datetime(long_frame["trade_date"])
    wide = long_frame.pivot(index="trade_date", columns="symbol", values="daily_return")
    return wide.sort_index()


def _cohort_daily_returns(
    daily_returns: pd.DataFrame,
    cohorts: list[dict[str, Any]],
    *,
    cost_bps_per_side: float,
    rebalance_sink: list[dict[str, Any]] | None = None,
) -> pd.Series:
    """Fixed-weight-until-next-rebalance daily portfolio returns -- see the
    module docstring's "Implementation choice" for the exact convention.
    """
    cost_rate = 2.0 * cost_bps_per_side / 10_000.0
    dates = daily_returns.index
    all_returns: dict[pd.Timestamp, float] = {}
    previous_weights: dict[str, float] = {}
    for i, cohort in enumerate(cohorts):
        selected = cohort["selected"]
        weight = 1.0 / len(selected)
        weights = dict.fromkeys(selected, weight)
        symbols_touched = set(weights) | set(previous_weights)
        turnover = sum(
            abs(weights.get(symbol, 0.0) - previous_weights.get(symbol, 0.0))
            for symbol in symbols_touched
        )
        cost = turnover * cost_rate
        if rebalance_sink is not None:
            rebalance_sink.append(
                {
                    "date": cohort["month_end_date"],
                    "selected_count": len(selected),
                    "liquid_universe_size": cohort["liquid_universe_size"],
                    "turnover": turnover,
                    "cost": cost,
                }
            )

        start = dates.searchsorted(cohort["month_end_date"], side="right")
        end = (
            dates.searchsorted(cohorts[i + 1]["month_end_date"], side="right") - 1
            if i + 1 < len(cohorts)
            else len(dates) - 1
        )
        if start > end:
            previous_weights = weights
            continue
        held_columns = [symbol for symbol in weights if symbol in daily_returns.columns]
        missing = set(weights) - set(held_columns)
        window = daily_returns.iloc[start : end + 1][held_columns]
        # A held name missing a return on a specific day (e.g. a trading
        # halt) contributes 0.0 for that one day rather than crashing the
        # whole candidate -- this is intentionally conservative (a real
        # position would carry its prior mark, not exactly zero), recorded
        # in the sink so the report can surface how often it happens.
        day_returns = (window.fillna(0.0) * weight).sum(axis=1)
        if missing and rebalance_sink is not None:
            rebalance_sink[-1]["missing_from_daily_panel"] = sorted(missing)
        for j, date in enumerate(window.index):
            value = float(day_returns.iloc[j])
            if j == 0:
                value -= cost
            all_returns[date] = value
        previous_weights = weights

    if not all_returns:
        raise ValueError("no holding period produced any returns")
    index = pd.DatetimeIndex(sorted(all_returns))
    return pd.Series(
        [all_returns[ts] for ts in index], index=index, name="cross_sectional_momentum_liquid500"
    )


def _bounded_window_diagnostic(
    returns: pd.Series, benchmark: pd.Series, *, start: str, end: str, minimum_rows: int = 5
) -> dict[str, float | int | str | None]:
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
    con = duckdb.connect(":memory:")
    con.execute(f"SET memory_limit='{MEMORY_LIMIT}'")
    con.execute("SET temp_directory='/tmp/duckdb_w10_liquid500_official'")

    started = time.time()
    panel = _build_liquid_momentum_panel(con)
    panel_elapsed = time.time() - started
    peak_after_panel = _peak_rss_mb()

    cohorts_by_params: dict[tuple[float, int], list[dict[str, Any]]] = {}
    union_symbols: set[str] = set()
    for params in PARAMETER_SPACE:
        cohorts = _monthly_cohorts(
            panel,
            top_fraction=params["top_fraction"],
            rebalance_stride_months=params["rebalance_stride_months"],
        )
        cohorts_by_params[(params["top_fraction"], params["rebalance_stride_months"])] = cohorts
        for cohort in cohorts:
            union_symbols.update(cohort["selected"])

    started = time.time()
    daily_returns = _load_daily_returns_for_union(con, union_symbols)
    daily_returns_elapsed = time.time() - started
    peak_after_daily = _peak_rss_mb()
    con.close()

    benchmark_returns = {
        symbol: daily_returns_on_naive_dates(symbol, start=DATA_START)
        for symbol in ("SPY", "QQQ", "TQQQ", "BIL")
    }

    def _signal_fn(params: dict[str, Any]) -> pd.Series:
        cohorts = cohorts_by_params[(params["top_fraction"], params["rebalance_stride_months"])]
        return _cohort_daily_returns(
            daily_returns, cohorts, cost_bps_per_side=BASE_COST_BPS_PER_SIDE
        )

    def _stress_signal_fn(params: dict[str, Any]) -> pd.Series:
        cohorts = cohorts_by_params[(params["top_fraction"], params["rebalance_stride_months"])]
        return _cohort_daily_returns(
            daily_returns, cohorts, cost_bps_per_side=STRESS_COST_BPS_PER_SIDE
        )

    mechanism = Mechanism(
        family="cross_sectional_momentum_liquid500",
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
        cohorts = cohorts_by_params[(params["top_fraction"], params["rebalance_stride_months"])]
        rebalance_sink: list[dict[str, Any]] = []
        full_series = _cohort_daily_returns(
            daily_returns,
            cohorts,
            cost_bps_per_side=BASE_COST_BPS_PER_SIDE,
            rebalance_sink=rebalance_sink,
        )
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
        avg_selected_count = sum(c["selected_count"] for c in rebalance_sink) / len(rebalance_sink)
        avg_liquid_universe_size = sum(c["liquid_universe_size"] for c in rebalance_sink) / len(
            rebalance_sink
        )
        annualized_turnover_events = (
            len(rebalance_sink) / (len(full_series) / 252.0) if len(full_series) else 0.0
        )

        row = {
            "candidate_id": candidate.candidate_id,
            "parameters": dict(params),
            "trading_activity": {
                "rebalance_count": len(rebalance_sink),
                "average_selected_count": avg_selected_count,
                "average_liquid_universe_size": avg_liquid_universe_size,
                "annualized_turnover_events": annualized_turnover_events,
                "total_days": len(full_series),
                "rebalances_with_missing_daily_data": sum(
                    1 for c in rebalance_sink if c.get("missing_from_daily_panel")
                ),
            },
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
            passing_new_contract.append(candidate.candidate_id)

    report = {
        "iter_id": "step10_w2_cross_sectional_liquid500",
        "method": "cross_sectional_momentum_liquid500",
        "evaluation_methodology": "mechanism_eval_harness_p1b_sip_vol_matched_duckdb_liquid_filter",
        "product_executable": False,
        "product_executable_reason": (
            "cross_sectional_momentum product mapping (target-weights identity "
            "for the daily paper cycle) is out of this week's scope per plan "
            "section 5; if this family passes, next week's ledger entry covers "
            "wiring it in."
        ),
        "note": (
            "4 preregistered candidates crossing top_fraction in {0.10, 0.15} "
            "and rebalance cadence in {monthly, bimonthly} over the point-in-"
            "time liquid-500 universe (top 500 by trailing 60-day dollar ADV, "
            "close>5, both measured at each rebalance date, never a single "
            "fixed window applied to all history). Judged under config/"
            "promotion/unlevered-family-paper-tier-gates.json (new contract, "
            "vol-matched against SPY); the existing kernel-paper-tier-"
            "gates.json result is reported per-candidate under "
            "old_contract_reference_only for reference, never as the verdict."
        ),
        "data_source": "sip_parquet_via_duckdb",
        "adv_lookback_days": ADV_LOOKBACK_DAYS,
        "adv_top_n": ADV_TOP_N,
        "lookback_days": LOOKBACK_DAYS,
        "skip_days": SKIP_DAYS,
        "monthly_panel_row_count": len(panel),
        "monthly_panel_month_count": panel["month_key"].nunique(),
        "union_selected_symbol_count": len(union_symbols),
        "daily_returns_shape": list(daily_returns.shape),
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
        "performance": {
            "panel_build_elapsed_seconds": round(panel_elapsed, 2),
            "daily_returns_load_elapsed_seconds": round(daily_returns_elapsed, 2),
            "peak_rss_mb_after_panel": round(peak_after_panel, 1),
            "peak_rss_mb_after_daily_returns": round(peak_after_daily, 1),
            "peak_rss_mb_final": round(_peak_rss_mb(), 1),
            "memory_budget_mb": 1000,
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
