"""Read fixed final99 artifacts: source H5 payoff, never a market NAV."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from matched_analysis import F0, HERE, bind, load_accepted, read


def main():
    start = time.process_time()
    records, bindings, paired = [], [bind(Path(__file__))], []
    costs = {"ZERO": (0, 0), "SOURCE_NATIVE": (0.0005, 0.0001), "DOUBLE_SOURCE": (0.001, 0.0002)}
    for fold in (0, 10):
        streams = {}
        for stream in ("A09", "A10"):
            accept = (
                F0 / f"root-{stream}-result-acceptance.json"
                if fold == 0
                else HERE / f"author-{stream}-accounting-verification.json"
            )
            ledger, items = load_accepted(accept, f"{stream}-fold{fold:02}")
            bindings.extend(items)
            replay = ledger.parent
            targets = np.load(replay / "final-stock-targets.npy", allow_pickle=False)
            assert targets.shape == (125, 2434) and np.isfinite(targets).all()
            data = read(replay / "SOURCE_H5-payoffs-nonNAV.json")
            bindings.extend(
                bind(replay / f)
                for f in ("SOURCE_H5-payoffs-nonNAV.json", "final-stock-targets.npy")
            )
            short = np.maximum(-targets, 0).sum(1)
            turn5 = np.abs(targets[5:] - targets[:-5]).sum(1)
            turn1 = np.abs(targets[1:] - targets[:-1]).sum(1)
            hhi = np.square(targets).sum(1)
            for cost, (tc, hc) in costs.items():
                v = np.asarray(data[cost])
                assert v.shape == (125,) and np.isfinite(v).all() and (v[:5] == 0).all()
                expected = np.asarray(data["ZERO"])[5:] - (tc * turn5 + hc * short[5:]) / 5
                assert np.allclose(v[5:], expected, atol=1e-9, rtol=0)
                phase = [v[i::5] * 5 for i in range(5)]
                phase_stats = [
                    {
                        "phase": i,
                        "rows": len(a),
                        "five_session_payoff_mean_bps": float(a.mean() * 10000),
                        "payoff_std_bps": float(a.std(ddof=1) * 10000),
                        "source_scaled_Sharpe": float(a.mean() / a.std(ddof=1) * np.sqrt(252 / 5)),
                    }
                    for i, a in enumerate(phase)
                ]
                records.append(
                    {
                        "fold": fold,
                        "stream": stream,
                        "cost": cost,
                        "rows": 125,
                        "initial_zero_rows_retained": 5,
                        "H5_payoff_per_day_scaled_mean_bps": float(v.mean() * 10000),
                        "gross_component_bps": float(np.mean(data["ZERO"]) * 10000),
                        "cost_component_bps": float((np.mean(data["ZERO"]) - v.mean()) * 10000),
                        "phases": phase_stats,
                        "native_phase_average_Sharpe": float(
                            np.mean([p["source_scaled_Sharpe"] for p in phase_stats])
                        ),
                        "market_or_NAV_or_comparable_H1_Sharpe": False,
                        "H1_mean_successive_target_turnover": float(turn1.mean()),
                        "H5_mean_lag5_target_difference_div5": float(turn5.mean() / 5),
                        "median_L1_Herfindahl_effective_positions": float(np.median(1 / hhi)),
                        "mean_short_notional": float(short.mean()),
                        "independent_acceptance": "previously_accepted"
                        if fold == 0
                        else "author_verified_pending",
                    }
                )
            streams[stream] = data
        for cost in costs:
            diff = np.asarray(streams["A10"][cost]) - np.asarray(streams["A09"][cost])
            gross_diff = np.asarray(streams["A10"]["ZERO"]) - np.asarray(streams["A09"]["ZERO"])
            paired.append(
                {
                    "fold": fold,
                    "contrast": "A10_minus_A09_fixed_H5_objective_cost_training",
                    "cost": cost,
                    "mean_payoff_per_day_scaled_delta_bps": float(diff.mean() * 10000),
                    "gross_component_delta_bps": float(gross_diff.mean() * 10000),
                    "cost_saving_delta_bps": float((diff - gross_diff).mean() * 10000),
                    "not_an_independent_125row_H5_sample": True,
                }
            )
    result = {
        "as_of_utc": datetime.now(UTC).isoformat(),
        "author": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
        "status": "author_verified_H5_nonNAV_diagnostic_pending_independent_acceptance",
        "source_convention": "Original H5 payoff series, "
        "first5zeros and five25row phases retained.",
        "hold_cost_limit": "Original source divides both turnover and daily short penalty by5; "
        "a real account must accrue borrow over actual holding days. No source-cost rewrite here.",
        "no_NAV": "Overlapping H5 payoffs are not self-financing daily account returns; "
        "no compounding, stitched fold curve, promoted annual return or whole-account claim.",
        "comparison": "Same-model H1 accounting is in matched-comparison.json; "
        "different horizon objectives can disagree without invalidating either fixed diagnostic.",
        "records": records,
        "paired": paired,
        "bindings": bindings,
        "new_fits": 0,
        "new_inference": 0,
        "CPU_seconds": time.process_time() - start,
    }
    with (HERE / "H5-nonNAV-comparison.json").open("x") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(json.dumps({"records": len(records), "CPU_seconds": result["CPU_seconds"]}))


if __name__ == "__main__":
    main()
