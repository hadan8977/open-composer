"""Join frozen episode evidence; no fitting, inference, checkpoint selection or stitched NAV."""

import csv
import json
import math
import sys
import time
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[6]
HERE = Path(__file__).resolve().parent
PROGRAM = ROOT / "reports/research/program/day-goal-20261011-2"
TRAIN = PROGRAM / "dlsa-first-training-batch-runtime"
F0 = TRAIN / "fold00-sixfits"
F10 = TRAIN / "modal-next-fold-continuation"
sys.path.insert(0, str(F10 / "result-preparation"))
from matched_baseline_accounting import reconcile_baselines  # noqa: E402
from result_bindings import checked, sha  # noqa: E402


def read(p):
    return json.loads(p.read_text())


def bind(p):
    p = p.resolve()
    return {"path": str(p.relative_to(ROOT)), "bytes": p.stat().st_size, "sha256": sha(p)}


def load_accepted(acceptance, fit_id):
    accepted = read(acceptance)
    snap = ROOT / accepted["snapshot"]["path"]
    assert sha(snap) == accepted["snapshot"]["sha256"]
    snapshot = read(snap)
    artifacts = snapshot["artifacts"]
    for row in artifacts:
        checked({**row, "path": str(snap.parent / row["path"])})
    ledger = next(x for x in artifacts if x["path"].endswith("episode-daily-ledger.csv"))
    science = snap.parent / ledger["path"]
    return science, [bind(acceptance), bind(snap), bind(science)]


def summarize(key, rows):
    fold, stream, profile, cost = key
    means = {
        field: float(np.mean([float(r[field]) for r in rows]))
        for field in (
            "gross",
            "net",
            "charged_turnover",
            "short_notional",
            "transaction_cost",
            "short_cost",
        )
    }
    net = np.array([float(r["net"]) for r in rows])
    assert np.isfinite(net).all()
    nav = np.cumprod(1 + net)
    dd = nav / np.maximum.accumulate(np.r_[1.0, nav])[1:] - 1
    losing = underwater = max_losing = max_underwater = 0
    for n, d in zip(net, dd, strict=True):
        losing = losing + 1 if n < 0 else 0
        underwater = underwater + 1 if d < 0 else 0
        max_losing, max_underwater = max(max_losing, losing), max(max_underwater, underwater)
    return {
        "fold": fold,
        "stream": stream,
        "profile": profile,
        "cost": cost,
        "rows": len(rows),
        "independent_acceptance": "pending_independent_acceptance"
        if fold == 10 and stream in {"A09", "A10"}
        else "previously_accepted",
        "daily_means": means,
        "mean_net_bps": means["net"] * 10000,
        "method_episode_return": float(nav[-1] - 1),
        "method_episode_max_drawdown": float(dd.min()),
        "longest_negative_run_rows": max_losing,
        "longest_underwater_run_rows": max_underwater,
        "end_unrecovered_drawdown": float(dd[-1]),
        "source_native_break_even_turnover_bps": (
            (means["gross"] - 0.0001 * means["short_notional"]) / means["charged_turnover"] * 10000
            if means["charged_turnover"] > 0
            else None
        ),
        "market_or_account_performance": False,
    }, net


def main():
    started = time.process_time()
    bindings = [bind(Path(__file__)), bind(F10 / "accepted-native-gate-bindings.json")]
    for g in read(F10 / "accepted-native-gate-bindings.json")["gates"]:
        checked(g["receipt"])
    sources = []
    for i in range(5, 11):
        p, b = load_accepted(F0 / f"root-A{i:02}-result-acceptance.json", f"A{i:02}-fold00")
        sources.append((0, p, {f"A{i:02}"}))
        bindings.extend(b)
    p, b = load_accepted(F10 / "Root-A05-fold10-result-acceptance.json", "A05-fold10")
    sources.append((10, p, {"A05"}))
    bindings.extend(b)
    for stream in ("A06", "A07", "A08"):
        pending = HERE.parent / f"author-{stream}-accounting-verification.json"
        p, b = load_accepted(pending, f"{stream}-fold10")
        assert read(pending)["independent_Root_scientific_acceptance_pending"]
        sources.append((10, p, {stream}))
        bindings.extend(b)
    prior_acceptance = HERE.parent / "root-three-fit-acceptance.json"
    assert read(prior_acceptance)["accepted_fits_total"] == 10
    assert read(prior_acceptance)["accepted_updates_total"] == 8000
    bindings.append(bind(prior_acceptance))
    for stream in ("A09", "A10"):
        verification = HERE / f"author-{stream}-accounting-verification.json"
        p, b = load_accepted(verification, f"{stream}-fold10")
        assert read(verification)["optimizer_updates_completed_finite"] == 800
        assert read(verification)["independent_Root_scientific_acceptance_pending"]
        sources.append((10, p, {stream}))
        bindings.extend(b)
    base0 = (
        PROGRAM
        / "dlsa-modal-runtime/cpu-variant/attempts/dlsa-fold0-cpu-attempt02-20261011"
        / "fetched/science/daily-ledger.csv"
    )
    assert sha(base0) == "97837e1f81b170e7e0dfbf7f41273be437b2d6cdcf88ef94671279335d55fa7f"
    sources.append((0, base0, {"A00", "A01", "A02", "A03", "A04", "A11"}))
    bindings.append(bind(base0))
    baseline_binding = read(F10 / "matched-baseline-bindings.json")
    base10 = checked(baseline_binding["baseline_daily_ledger"])
    # Reuse the accepted flat-entry correction, retaining the original baseline file.
    correction = reconcile_baselines(F10)
    adjustments = {
        (r["stream"], r["cost"]): r
        for r in correction["first_row_continuous_adjustments_preserved"]
    }
    sources.append((10, base10, set(baseline_binding["baseline_targets"])))
    bindings.extend([bind(base10), bind(F10 / "matched-baseline-bindings.json")])
    groups = defaultdict(list)
    for fold, path, streams in sources:
        with path.open() as f:
            for original in csv.DictReader(f):
                if original["stream"] not in streams:
                    continue
                row = dict(original)
                if (
                    path == base10
                    and row["profile"] == "CONTINUOUS_TARGET_DIAGNOSTIC"
                    and int(row["sample_index"]) == 2250
                ):
                    a = adjustments[row["stream"], row["cost"]]
                    tc = {"ZERO": 0, "SOURCE_NATIVE": 0.0005, "DOUBLE_SOURCE": 0.001}[row["cost"]]
                    row["charged_turnover"] = str(a["matched_sparse_flat_entry_turnover"])
                    row["transaction_cost"] = str(tc * a["matched_sparse_flat_entry_turnover"])
                    row["net"] = str(a["flat_entry_adjusted_net"])
                groups[fold, row["stream"], row["profile"], row["cost"]].append(row)
    assert len(groups) == 144
    summaries, returns, means_by_key = [], {}, {}
    for key, rows in sorted(groups.items()):
        start = 1000 if key[0] == 0 else 2250
        assert [int(r["sample_index"]) for r in rows] == list(range(start, start + 125))
        for row in rows:
            assert math.isclose(
                float(row["net"]),
                float(row["gross"]) - float(row["transaction_cost"]) - float(row["short_cost"]),
                abs_tol=1e-9,
            )
        s, returns[key] = summarize(key, rows)
        summaries.append(s)
        means_by_key[key] = s["daily_means"]
    rng = np.random.default_rng(20261011)
    indices = {}
    for length in (5, 20):
        starts = rng.integers(0, 125, size=(1000, math.ceil(125 / length)))
        indices[length] = ((starts[:, :, None] + np.arange(length)) % 125).reshape(1000, -1)[
            :, :125
        ]
    contrasts = []
    pairs = {
        0: [
            ("A05", "A00"),
            ("A05", "A01"),
            ("A06", "A05"),
            ("A06", "A01"),
            ("A07", "A05"),
            ("A08", "A07"),
            ("A09", "A05"),
            ("A10", "A09"),
            ("A10", "A07"),
        ],
        10: [
            ("A05", "A00"),
            ("A05", "A01"),
            ("A06", "A00"),
            ("A06", "A01"),
            ("A06", "A05"),
            ("A07", "A00"),
            ("A07", "A01"),
            ("A07", "A05"),
            ("A08", "A00"),
            ("A08", "A01"),
            ("A08", "A05"),
            ("A08", "A07"),
            ("A09", "A05"),
            ("A10", "A09"),
            ("A10", "A07"),
            ("A09", "A00"),
            ("A09", "A01"),
            ("A10", "A00"),
            ("A10", "A01"),
        ],
    }
    for fold, pairlist in pairs.items():
        for model, base in pairlist:
            for profile in ("SOURCE_RESET", "CONTINUOUS_TARGET_DIAGNOSTIC"):
                for cost in ("ZERO", "SOURCE_NATIVE", "DOUBLE_SOURCE"):
                    mk, bk = (fold, model, profile, cost), (fold, base, profile, cost)
                    diff = returns[mk] - returns[bk]
                    intervals = []
                    for length, index in indices.items():
                        draws = diff[index].mean(1)
                        lo, hi = np.quantile(draws, [0.025, 0.975])
                        se = draws.std(ddof=1)
                        intervals.append(
                            {
                                "block_length": length,
                                "paired_mean_95pct_bps": [float(lo * 10000), float(hi * 10000)],
                                "MDE80_5pct_bps_normal_approx": float(
                                    2.801585218113968 * se * 10000
                                ),
                            }
                        )
                    m, b = means_by_key[mk], means_by_key[bk]
                    contrasts.append(
                        {
                            "fold": fold,
                            "model": model,
                            "baseline": base,
                            "profile": profile,
                            "cost": cost,
                            "paired_mean_net_delta_bps": float(diff.mean() * 10000),
                            "gross_delta_bps": (m["gross"] - b["gross"]) * 10000,
                            "transaction_cost_delta_bps": (
                                m["transaction_cost"] - b["transaction_cost"]
                            )
                            * 10000,
                            "short_cost_delta_bps": (m["short_cost"] - b["short_cost"]) * 10000,
                            "paired_correlation": float(
                                np.corrcoef(returns[mk], returns[bk])[0, 1]
                            ),
                            "intervals": intervals,
                            "independent_acceptance_pending": (
                                fold == 10 and model in {"A09", "A10"}
                            ),
                        }
                    )
    result = {
        "utc": datetime.now(UTC).isoformat(),
        "owner_agent_id": "ee7b92dc-c2dd-41e6-8cf2-9ec3d9cb51b3",
        "status": ("complete_twelve_fit_episode_comparison_A09_A10_pending_independent_acceptance"),
        "accepted_fits": 10,
        "accepted_updates": 8000,
        "recovered_pending_fits": [],
        "new_completed_pending_fits": ["A09-fold10", "A10-fold10"],
        "summaries": summaries,
        "paired_contrasts": contrasts,
        "bindings": bindings,
        "bootstrap": {
            "seed": 20261011,
            "replicates": 1000,
            "blocks": [5, 20],
            "resampling": "circular_within_one_fixed_episode",
            "descriptive_not_multiplicity_adjusted": True,
        },
        "fold10_flat_entry_adjustments": correction["first_row_continuous_adjustments_preserved"],
        "limits": [
            "Anonymous perturbed public method evidence, no dated security or account Alpha.",
            "No fold, epoch, cost or model selection; fixed final epoch99.",
            "Separate125-row episodes; no stitched250/406-row NAV or OOS declaration.",
            "H5 variants use common H1 ledger; "
            "overlapping H5 payoff remains separate nonNAV diagnostic.",
            "A08 versus A07 combines architecture and state; "
            "no same-architecture zero-state ablation exists in the original inventory.",
            "A06/A07/A08 independently accepted by bound Root receipt; "
            "A09/A10 author-verified pending.",
            "PBO/DSR for incomplete24fit family remain N/A; "
            "bootstrap intervals do not cover model/search multiplicity.",
        ],
        "new_model_fits": 0,
        "CPU_seconds": time.process_time() - started,
    }
    with (HERE / "matched-comparison.json").open("x") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "summaries": len(summaries),
                "contrasts": len(contrasts),
                "CPU_seconds": result["CPU_seconds"],
            }
        )
    )


if __name__ == "__main__":
    main()
