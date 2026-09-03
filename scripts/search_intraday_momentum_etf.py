"""Evaluate the single-ETF intraday momentum mechanism (Zarattini/Aziz/Barbon-
derived, see open_composer.research.kernel.mechanisms.intraday_momentum_etf)
on real SIP 5-minute bars, through the P1b mechanism-evaluation harness, for
SPY and QQQ separately.

Memory discipline (docs/plan-goal-first-verification-2026-09-02.zh.md Wave
W4, and the machine limits recorded in docs/data-layer-pitfalls-and-
capabilities.zh.md item 22): minute bars are loaded and resampled to 5-minute
RTH bars ONE (symbol, year) PAIR AT A TIME, and the raw minute frame is
dropped before the next year loads. Only the resampled 5-minute bars (roughly
78 bars/session x ~252 sessions/year, a few hundred KB per symbol-year) are
kept resident for the full multi-year evaluation.

The SIP minute archive covers 2023-01 through 2026-08 (3.5 calendar years),
so rolling-origin folding uses fold_count=3 (test years 2024, 2025, 2026;
2023 serves only as trailing history for the noise band and the first
scored session's warm-up), not the kernel's usual 5-year default -- there are
not five distinct calendar years of minute data yet.
"""

from __future__ import annotations

import gc
import json
import resource
from pathlib import Path

import pandas as pd

from open_composer.adapters.data.sip_parquet import available_sip_years, load_sip_bars
from open_composer.research.kernel.benchmark_returns import daily_returns_on_naive_dates
from open_composer.research.kernel.gate_contract import load_preregistered_gates
from open_composer.research.kernel.mechanism_eval import (
    Mechanism,
    evaluate_family,
    expand_mechanism,
)
from open_composer.research.kernel.mechanisms.intraday_momentum_etf import (
    PARAMETER_SPACE,
    daily_intraday_momentum_returns,
)
from open_composer.research.kernel.resample import resample_rth_bars
from open_composer.storage import write_json

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = ROOT / "reports" / "research" / "search" / "intraday-momentum-etf-2026-09.json"
GATE_CONTRACT_PATH = ROOT / "config" / "promotion" / "kernel-paper-tier-gates.json"

SYMBOLS = ("SPY", "QQQ")
TARGET_MINUTES = 5
FOLD_COUNT = 3  # see module docstring: only 3.5 distinct years exist in the archive
DSR_HAC_LAG = 21


def _peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load_resampled_intraday_bars(symbol: str) -> pd.DataFrame:
    """Load every available minute year for ``symbol``, resampling year by year."""
    years = available_sip_years("minute")
    if not years:
        raise RuntimeError("no SIP minute years available")
    parts: list[pd.DataFrame] = []
    for year in years:
        raw = load_sip_bars(symbol, frequency="minute", start=f"{year}-01-01", end=f"{year}-12-31")
        resampled = resample_rth_bars(raw, target_minutes=TARGET_MINUTES)
        parts.append(resampled[["timestamp", "open", "high", "low", "close"]])
        del raw
        gc.collect()
        print(
            f"  {symbol} {year}: {len(resampled)} {TARGET_MINUTES}m bars, peak RSS so far "
            f"{_peak_rss_mb():.0f}MB"
        )
    combined = pd.concat(parts, ignore_index=True).sort_values("timestamp").reset_index(drop=True)
    return combined


def main() -> None:
    gates = load_preregistered_gates(GATE_CONTRACT_PATH, repo_root=ROOT)
    report: dict[str, object] = {
        "method": "intraday_momentum_etf_p1b_sip_5min",
        "note": (
            "Causal simplification of Zarattini/Aziz/Barbon's opening-range "
            "momentum, evaluated on real SIP 5-minute RTH bars via the P1b "
            "mechanism-evaluation harness. fold_count=3 because the SIP minute "
            "archive only spans 2023-2026 (3.5 distinct years), not the "
            "kernel's usual 5-year default."
        ),
        "target_minutes": TARGET_MINUTES,
        "fold_count": FOLD_COUNT,
        "parameter_space_size": len(PARAMETER_SPACE),
        "symbols": {},
    }
    benchmark_returns = {
        symbol: daily_returns_on_naive_dates(symbol, start="2023-01-01")
        for symbol in ("QQQ", "BIL")
    }
    tqqq_returns = daily_returns_on_naive_dates("TQQQ", start="2023-01-01")
    # The daily and minute SIP archives are refreshed independently and are not
    # always in lockstep -- e.g. minute may already have a session the daily
    # archive has not yet ingested (see docs/data-layer-pitfalls-and-
    # capabilities.zh.md item 15 on archive freshness). A signal date newer
    # than the benchmark's own coverage cannot be scored against it, so trim
    # to the common window rather than letting evaluate_candidate's benchmark
    # reindex fail on the trailing edge.
    benchmark_latest_date = min(
        series.index.max().date() for series in (*benchmark_returns.values(), tqqq_returns)
    )
    print(f"benchmark coverage ends {benchmark_latest_date}; intraday bars trimmed to match")

    for symbol in SYMBOLS:
        print(f"=== {symbol} ===")
        bars = _load_resampled_intraday_bars(symbol)
        bars = bars.loc[
            bars["timestamp"].dt.tz_convert("America/New_York").dt.date <= benchmark_latest_date
        ].reset_index(drop=True)
        print(
            f"{symbol}: {len(bars)} total {TARGET_MINUTES}m bars, peak RSS {_peak_rss_mb():.0f}MB"
        )

        mechanism = Mechanism(
            family=f"intraday_momentum_etf_{symbol.lower()}",
            signal_fn=lambda params, _bars=bars: daily_intraday_momentum_returns(_bars, params),
            stress_signal_fn=lambda params, _bars=bars: daily_intraday_momentum_returns(
                _bars, {**params, "cost_bps_per_side": 20.0}
            ),
            param_space=PARAMETER_SPACE,
        )
        candidates = expand_mechanism(mechanism, fold_count=FOLD_COUNT)
        # Two passes, per the SIP migration plan's effective-N methodology
        # (docs/plan-sip-migration-and-wide-search-2026-09-01.zh.md section 4):
        # effective_independent_trials clusters candidates' OOS return streams
        # independently of whatever dsr_trial_count is passed to evaluate_candidate,
        # so the first pass's trial count is a throwaway used only to read off
        # family.effective_n; the second pass charges DSR the honest,
        # correlation-clustered trial count instead of the raw 18-candidate count.
        scouting_pass = evaluate_family(
            candidates,
            qqq_returns=benchmark_returns["QQQ"],
            tqqq_returns=tqqq_returns,
            bil_returns=benchmark_returns["BIL"],
            gates=gates,
            dsr_trial_count=len(candidates),
            dsr_hac_lag=DSR_HAC_LAG,
        )
        effective_trial_count = max(scouting_pass.effective_n, 1)
        family = evaluate_family(
            candidates,
            qqq_returns=benchmark_returns["QQQ"],
            tqqq_returns=tqqq_returns,
            bil_returns=benchmark_returns["BIL"],
            gates=gates,
            dsr_trial_count=effective_trial_count,
            dsr_hac_lag=DSR_HAC_LAG,
        )
        promotable = [verdict for verdict in family.candidates if verdict.promotion_eligible]
        best = max(family.candidates, key=lambda verdict: verdict.sharpe_excess_bil)
        report["symbols"][symbol] = {  # type: ignore[index]
            "bar_count": len(bars),
            "raw_candidate_count": family.raw_candidate_count,
            "effective_n": family.effective_n,
            "dsr_trial_count_used": effective_trial_count,
            "breadth_ratio": family.breadth_ratio,
            "promotable_candidate_ids": [verdict.candidate.candidate_id for verdict in promotable],
            "best_by_sharpe_excess_bil": {
                "candidate_id": best.candidate.candidate_id,
                "param_vector": best.candidate.param_vector,
                "sharpe_excess_bil": best.sharpe_excess_bil,
                "dsr_probability": best.dsr_probability,
                "positive_fold_fraction": best.positive_fold_fraction,
                "gate_results": best.gate_results,
                "all_gates_pass": best.all_gates_pass,
                "promotion_eligible": best.promotion_eligible,
                "metrics": best.metrics,
                "stitched_oos_row_count": len(best.candidate.oos_return_stream),
                "stitched_oos_start": best.candidate.oos_dates[0],
                "stitched_oos_end": best.candidate.oos_dates[-1],
            },
        }
        del bars
        gc.collect()

    report["peak_rss_mb"] = round(_peak_rss_mb(), 1)
    write_json(OUTPUT_PATH, report)
    print(json.dumps(report, indent=2, sort_keys=True, default=str))
    print(f"\nWritten to {OUTPUT_PATH}")
    print(f"Peak RSS: {_peak_rss_mb():.0f}MB")


if __name__ == "__main__":
    main()
