"""Robustness check of the D5 solve path (T-20261001-06 follow-up, coordinator R1001-1035-D5FIX).
NOT a research result.

For the configurations of the smoke run that had solver failures, plus two controls, it

1. re-runs the weekly book with the retry ladder OFF and ``max_iter`` 200 (reproduces the smoke
   run, ``results.json``) and captures every decision problem (``ProblemData``);
2. re-solves every captured problem with the retry ladder (rescue attempt per failure) and with
   a first-attempt ``max_iter`` of 500 (ladder off) to measure status mix and solve time;
3. re-runs the weekly book with the ladder ON (default) to get the failure rate on the book's own
   trajectory;
4. solves ~20 sampled ``optimal_inaccurate`` problems with a high-precision Clarabel reference
   (``max_iter`` 5000, tolerances 1e-9) and compares objective, weights, vol and beta.

Problem construction is the smoke script's ``run_config`` (no duplicate logic).

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/check_optimizer_robustness_v1.py
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import time
from pathlib import Path
from typing import Any

import cvxpy as cp
import numpy as np

from open_composer.research.equity_book import optimize as op
from open_composer.research.equity_book.etf_risk import ETFRisk
from open_composer.research.equity_book.panel import PanelAttributes, PricePanel
from open_composer.research.equity_book.risk import RiskModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/research/program/optimizer-v1-2026-10-01"
_spec = importlib.util.spec_from_file_location(
    "run_optimizer_smoke_v1", ROOT / "scripts/run_optimizer_smoke_v1.py"
)
smoke = importlib.util.module_from_spec(_spec)  # type: ignore[arg-type]
_spec.loader.exec_module(smoke)  # type: ignore[union-attr]

# failing configurations of the smoke run, then the two controls
KEYS = [
    "anchor_2024|A|vasicek",
    "anchor_2024|A|model",
    "anchor_2024|A|ewma21",
    "anchor_2024|C|model",
    "anchor_2024|C|ewma21",
    "stress_2019|A|ewma",  # had 1 failure (also serves as a control for the 2019 span)
    "anchor_2024|A|ewma",  # control: no failure in the smoke run
]
REF_OPTS = {
    "max_iter": 5000,
    "tol_gap_abs": 1e-9,
    "tol_gap_rel": 1e-9,
    "tol_feas": 1e-9,
    "reduced_tol_gap_abs": 1e-8,
    "reduced_tol_gap_rel": 1e-8,
    "reduced_tol_feas": 1e-8,
}


def objective_bp(data: op.ProblemData, w: np.ndarray, cfg: op.OptConfig) -> float:
    """Objective of ``op._build`` (exact impact) evaluated in numpy at weights ``w``."""
    obj = float((data.alpha * op.BP) @ w)
    if cfg.kappa > 0.0:
        dw = np.abs(w - data.w0)
        cost = float(data.half_spread_bp @ dw) + float(data.impact_coef_bp @ dw**1.5)
        sh = (data.lo < 0) & (data.borrow_bp_yr > 0)
        cost += float(
            (data.borrow_bp_yr[sh] * cfg.horizon_days / op.TRADING_DAYS) @ np.maximum(-w[sh], 0.0)
        )
        obj -= cfg.kappa * cost
    return obj


def pct(x: list[float], qs=(50, 90, 95, 99, 100)) -> dict[str, float]:
    a = np.asarray([v for v in x if np.isfinite(v)], dtype=float)
    return {f"p{q}": float(np.percentile(a, q)) if len(a) else float("nan") for q in qs}


def capture_run(
    ctx: tuple, span: str, c: str, m: str, **overrides: Any
) -> tuple[list[dict], list[tuple[op.ProblemData, op.OptConfig]]]:
    """Run the book; return the decider records and (data, cfg) of every solve call."""
    panel, alpha_source, elig, rm, attrs, etf = ctx
    captured: list[tuple[op.ProblemData, op.OptConfig]] = []
    real_solve = op.solve

    def spy(data: op.ProblemData, cfg: op.OptConfig | None = None):
        captured.append((data, cfg or op.OptConfig()))
        return real_solve(data, cfg)

    op.solve = spy  # type: ignore[assignment]
    try:
        dec, _ = smoke.run_config(
            panel, alpha_source, elig, rm, attrs, etf, span, c, m, **overrides
        )
    finally:
        op.solve = real_solve  # type: ignore[assignment]
    return dec.records, captured


def timed_solve(data: op.ProblemData, cfg: op.OptConfig) -> tuple[op.SolveResult, float]:
    t = time.perf_counter()
    r = op.solve(data, cfg)
    return r, time.perf_counter() - t


def reference(data: op.ProblemData, cfg: op.OptConfig) -> tuple[np.ndarray | None, str, float]:
    prob, v = op._build(data, cfg)
    t = time.perf_counter()
    try:
        prob.solve(solver=cp.CLARABEL, verbose=False, **REF_OPTS)
    except Exception as exc:  # noqa: BLE001
        return None, f"error {exc!r}", time.perf_counter() - t
    if v.value is None:
        return None, str(prob.status), time.perf_counter() - t
    w = op._clean(np.asarray(v.value) / op.SCALE, data.w0, cfg.clean_tol)
    return w, str(prob.status), time.perf_counter() - t


def run(args: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    smoke_runs = json.loads((OUT / "results.json").read_text())["runs"]
    rm, attrs = RiskModel(), PanelAttributes()
    etf = ETFRisk(rm)
    cfgs: dict[str, Any] = {}
    sample_pool: list[tuple[str, int, op.ProblemData, op.OptConfig]] = []
    rng = np.random.default_rng(20261001)
    solve_before: list[float] = []
    solve_500: list[float] = []
    solve_after: list[float] = []
    for span in ("anchor_2024", "stress_2019"):
        keys = [k for k in KEYS if k.startswith(span)]
        if not keys:
            continue
        load_start, _, end = smoke.SPANS[span]
        panel = PricePanel.from_dir(start=load_start, end=end)
        ctx = (panel, smoke.make_alpha_source(panel), op.ShortEligibility(panel), rm, attrs, etf)
        for key in keys:
            _, c, m = key.split("|")
            t0 = time.time()
            # 1. ladder off, max_iter 200: reproduces the smoke run
            recs, caps = capture_run(ctx, span, c, m, retry_ladder=False)
            n = len(recs)
            before_fail = [i for i, r in enumerate(recs) if not r["ok"]]
            smoke_fail = smoke_runs[key]["n_failed"]
            status_before = {
                s: sum(r["status"] == s for r in recs) for s in {r["status"] for r in recs}
            }
            # 2a. same problems with the ladder
            rescued: list[dict] = []
            for i in before_fail:
                data, cfg = caps[i]
                r, wall = timed_solve(data, cfg.with_(retry_ladder=True))
                rescued.append(
                    {
                        "rebalance": i,
                        "date": str(recs[i]["date"].date()),
                        "n_assets": data.n,
                        "first_status": recs[i]["status"],
                        "ok": r.ok,
                        "attempt": r.attempt,
                        "attempt_name": op.SOLVE_ATTEMPTS[r.attempt],
                        "attempt_log": list(r.attempt_log),
                        "final_status": r.status,
                        "wall_s": wall,
                        "iters": r.iters,
                    }
                )
            # 2b. same problems, first attempt max_iter 500, ladder off
            st500: dict[str, int] = {}
            n500_fail_rescued = 0
            for i, (data, cfg) in enumerate(caps):
                r, wall = timed_solve(data, cfg.with_(max_iter=500, retry_ladder=False))
                st500[r.status] = st500.get(r.status, 0) + 1
                solve_500.append(wall)
                if i in before_fail and r.ok:
                    n500_fail_rescued += 1
            # timing of the legacy first attempt (from the recorded run)
            wall_before = [r["build_s"] + r["solve_s"] for r in recs]
            solve_before += wall_before
            inacc = [i for i, r in enumerate(recs) if r["status"] == "optimal_inaccurate"]
            for i in rng.choice(inacc, size=min(args.per_config, len(inacc)), replace=False):
                sample_pool.append((key, int(i), *caps[int(i)]))
            # 3. ladder on, own trajectory
            recs_on, _ = capture_run(ctx, span, c, m, retry_ladder=True)
            wall_on = [r["build_s"] + r["solve_s"] for r in recs_on]
            solve_after += wall_on
            att = {a: sum(r.get("attempt", 0) == a for r in recs_on if r["ok"]) for a in range(4)}
            cfgs[key] = {
                "n_rebalances": n,
                "smoke_run_n_failed": smoke_fail,
                "reproduced_n_failed_ladder_off": len(before_fail),
                "failure_rate_before": len(before_fail) / n,
                "failure_rate_after_same_problems": sum(not x["ok"] for x in rescued) / n,
                "failure_rate_after_own_trajectory": sum(not r["ok"] for r in recs_on)
                / len(recs_on),
                "status_counts_before": status_before,
                "status_counts_first_attempt_max_iter_500": st500,
                "failures_rescued_by_max_iter_500": n500_fail_rescued,
                "ladder_on_attempt_counts_own_trajectory": att,
                "ladder_on_status_counts_own_trajectory": {
                    s: sum(r["status"] == s for r in recs_on)
                    for s in {r["status"] for r in recs_on}
                },
                "rescues": rescued,
                "solve_s_before": pct(wall_before),
                "solve_s_ladder_on": pct(wall_on),
                "max_violation_before": max(
                    [r["max_violation"] for r in recs if r["ok"]], default=0.0
                ),
                "max_violation_ladder_on": max(
                    [r["max_violation"] for r in recs_on if r["ok"]], default=0.0
                ),
                "wall_s": time.time() - t0,
            }
            print(
                f"{key}: before {len(before_fail)}/{n} (smoke {smoke_fail}) -> own-trajectory "
                f"ladder {cfgs[key]['failure_rate_after_own_trajectory']:.3f}; "
                f"rescues {[x['attempt_name'] for x in rescued]}; {time.time() - t0:.0f}s",
                flush=True,
            )
            (OUT / "robustness.partial.json").write_text(json.dumps(cfgs, indent=1, default=str))
            etf.flush()
        del panel, ctx

    # 4. high-precision reference on sampled optimal_inaccurate problems
    pick = rng.choice(len(sample_pool), size=min(args.n_ref, len(sample_pool)), replace=False)
    ref_rows: list[dict] = []
    for j in sorted(pick):
        key, i, data, cfg = sample_pool[int(j)]
        first, _ = timed_solve(data, cfg.with_(retry_ladder=False))
        w_ref, ref_status, ref_s = reference(data, cfg)
        if not first.ok or w_ref is None:
            ref_rows.append(
                {"config": key, "rebalance": i, "first_ok": first.ok, "ref": ref_status}
            )
            continue
        o_f, o_r = objective_bp(data, first.w, cfg), objective_bp(data, w_ref, cfg)
        ref_rows.append(
            {
                "config": key,
                "rebalance": i,
                "n_assets": data.n,
                "first_status": first.status,
                "first_iters": first.iters,
                "ref_status": ref_status,
                "ref_wall_s": ref_s,
                "objective_first_bp": o_f,
                "objective_ref_bp": o_r,
                "objective_gap_bp": o_r - o_f,  # > 0: reference is better
                "objective_solver_value_first_bp": first.objective_bp,
                "max_abs_dw": float(np.abs(first.w - w_ref).max()),
                "l1_dw": float(np.abs(first.w - w_ref).sum()),
                "gross_ref": float(np.abs(w_ref).sum()),
                "vol_first": op.ex_ante_vol_annual(data, first.w),
                "vol_ref": op.ex_ante_vol_annual(data, w_ref),
                "abs_beta_first": abs(float(data.beta @ first.w)),
                "abs_beta_ref": abs(float(data.beta @ w_ref)),
                "viol_first": op.max_violation(data, first.w, cfg),
                "viol_ref": op.max_violation(data, w_ref, cfg),
            }
        )
        print("ref", ref_rows[-1].get("config"), ref_rows[-1].get("objective_gap_bp"), flush=True)
    good = [r for r in ref_rows if "objective_gap_bp" in r and r["ref_status"] == "optimal"]
    summary = {
        "n_sampled": len(ref_rows),
        "n_reference_optimal": len(good),
        "objective_gap_bp": pct([r["objective_gap_bp"] for r in good], (50, 90, 100)),
        "max_abs_dw": pct([r["max_abs_dw"] for r in good], (50, 90, 100)),
        "vol_change": pct([r["vol_first"] - r["vol_ref"] for r in good], (0, 50, 100)),
        "abs_beta_change": pct(
            [r["abs_beta_first"] - r["abs_beta_ref"] for r in good], (0, 50, 100)
        ),
    }
    out = {
        "meta": {
            "coordinator": "R1001-1035-D5FIX",
            "note": "robustness of the solve path; not a performance claim",
            "keys": KEYS,
            "reference_options": REF_OPTS,
            "opt_defaults": {
                k: getattr(op.OptConfig(), k) for k in op.OptConfig.__dataclass_fields__
            },
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "configs": cfgs,
        "solve_time_s_all": {
            "before_ladder_off_max_iter_200": pct(solve_before),
            "first_attempt_max_iter_500": pct(solve_500),
            "ladder_on_max_iter_200": pct(solve_after),
        },
        "reference_comparison": {"summary": summary, "rows": ref_rows},
    }
    (OUT / "robustness.json").write_text(json.dumps(out, indent=1, default=str))
    write_md(out)
    print("wrote robustness.json and robustness.md", flush=True)


def write_md(out: dict[str, Any]) -> None:
    """Short English report ``robustness.md`` from the ``robustness.json`` content."""
    L: list[str] = []
    L.append("# D5 optimizer solve-path robustness (R1001-1035-D5FIX)\n")
    L.append(f"Generated {out['meta']['timestamp_utc']}. Plumbing check, not a performance claim. ")
    L.append("Source: `robustness.json` (script `scripts/check_optimizer_robustness_v1.py`).\n")
    L.append("## Failure rate before / after the retry ladder\n")
    L.append(
        "before = ladder off, max_iter 200 (reproduces the smoke run); after (same problems) = "
        "the ladder applied to the problems that failed; after (own path) = full book re-run "
        "with the ladder on.\n"
    )
    L.append("| config | n | smoke failed | before | after (same problems) | after (own path) |")
    L.append("|---|---|---|---|---|---|")
    for k, c in out["configs"].items():
        L.append(
            f"| {k} | {c['n_rebalances']} | {c['smoke_run_n_failed']} | "
            f"{c['reproduced_n_failed_ladder_off']} ({c['failure_rate_before']:.3f}) | "
            f"{c['failure_rate_after_same_problems']:.3f} | "
            f"{c['failure_rate_after_own_trajectory']:.3f} |"
        )
    L.append("\n## Rescue attempt of every failed rebalance\n")
    L.append("| config | date | n assets | attempt log | ladder wall s |")
    L.append("|---|---|---|---|---|")
    for k, c in out["configs"].items():
        for r in c["rescues"]:
            L.append(
                f"| {k} | {r['date']} | {r['n_assets']} | {' > '.join(r['attempt_log'])} | "
                f"{r['wall_s']:.1f} |"
            )
    L.append("\n## Status mix of the first attempt\n")
    L.append(
        "| config | max_iter 200 | max_iter 500 | failures rescued by 500 | ladder-on 0/1/2/3 |"
    )
    L.append("|---|---|---|---|---|")
    for k, c in out["configs"].items():
        a = {str(x): v for x, v in c["ladder_on_attempt_counts_own_trajectory"].items()}
        L.append(
            f"| {k} | {c['status_counts_before']} | "
            f"{c['status_counts_first_attempt_max_iter_500']} | "
            f"{c['failures_rescued_by_max_iter_500']} | {a['0']}/{a['1']}/{a['2']}/{a['3']} |"
        )
    L.append("\n## Solve time (build + solve, seconds, all 7 configurations pooled)\n")
    L.append("| variant | p50 | p90 | p95 | p99 | max |")
    L.append("|---|---|---|---|---|---|")
    for k, t in out["solve_time_s_all"].items():
        L.append(
            f"| {k} | {t['p50']:.2f} | {t['p90']:.2f} | {t['p95']:.2f} | {t['p99']:.2f} | "
            f"{t['p100']:.2f} |"
        )
    rc = out["reference_comparison"]
    L.append("\n## optimal_inaccurate vs high-precision reference\n")
    L.append(
        f"Reference: Clarabel max_iter 5000, tol 1e-9. {rc['summary']['n_sampled']} sampled, "
        f"{rc['summary']['n_reference_optimal']} with reference status optimal (table). Gap = "
        "reference objective minus first-attempt objective, both evaluated at the cleaned weights "
        "(bp of equity per 21-session horizon, after costs); positive = reference better.\n"
    )
    L.append(
        "| config | n | iters | gap bp | max abs dw | vol first | vol ref | beta first | beta ref |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in rc["rows"]:
        if "objective_gap_bp" not in r:
            L.append(f"| {r['config']} | - | - | not comparable ({r.get('ref')}) | | | | | |")
            continue
        L.append(
            f"| {r['config']} #{r['rebalance']} | {r['n_assets']} | {r['first_iters']} | "
            f"{r['objective_gap_bp']:.4f} | {r['max_abs_dw']:.2e} | {r['vol_first']:.5f} | "
            f"{r['vol_ref']:.5f} | {r['abs_beta_first']:.5f} | {r['abs_beta_ref']:.5f} |"
        )
    L.append(f"\nSummary: `{json.dumps(rc['summary'])}`")
    (OUT / "robustness.md").write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-ref", type=int, default=20)
    ap.add_argument("--per-config", type=int, default=3)
    ap.add_argument("--md-only", action="store_true", help="rebuild robustness.md from the json")
    args = ap.parse_args()
    os.environ.setdefault("POLARS_SKIP_CPU_CHECK", "1")
    if args.md_only:
        write_md(json.loads((OUT / "robustness.json").read_text()))
        return
    run(args)


if __name__ == "__main__":
    main()
