"""Plumbing smoke run of the D5 optimizer (T-20261001-06).  NOT a research result.

Runs the weekly book (mom_12_1 score, rank-normal inside the universe, close execution) for the
configurations A / B / C over the stress sample 2019 and the anchor sample 2024, for each beta
method, and writes ``results.json`` (resumable: finished runs are skipped).  The spans exist only
to look at hedging mechanics (beta, vol, exposures, solve time); no performance claim is made.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_optimizer_smoke_v1.py \
        --configs A --methods ewma vasicek model ewma21
    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/run_optimizer_smoke_v1.py --bench
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.research.equity_book import optimize as op
from open_composer.research.equity_book.backtest import TBILL, run_book
from open_composer.research.equity_book.etf_risk import ETFRisk
from open_composer.research.equity_book.panel import PanelAttributes, PricePanel
from open_composer.research.equity_book.risk import STYLES, RiskModel

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/research/program/optimizer-v1-2026-10-01"
SPANS = {
    "stress_2019": ("2017-10-02", "2019-01-01", "2019-12-31"),  # load start, run start, run end
    "anchor_2024": ("2023-01-02", "2024-01-01", "2024-12-31"),
}
SLEEVES = ("SGOV", "BIL")


def hwm_reset() -> None:
    try:
        with open("/proc/self/clear_refs", "w") as fh:
            fh.write("5")
    except OSError:
        pass


def vmhwm_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmHWM"):
            return float(line.split()[1]) / 1024.0
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def vmrss_mb() -> float:
    for line in Path("/proc/self/status").read_text().splitlines():
        if line.startswith("VmRSS"):
            return float(line.split()[1]) / 1024.0
    return float("nan")


def make_alpha_source(panel: PricePanel):
    def alpha_source(t: pd.Timestamp, state: Any, universe: pd.Index) -> pd.Series:
        pos = state.pos
        names = [s for s in universe if panel.has(s)]
        cols = np.array([panel.col(s) for s in names], dtype=int)
        with np.errstate(invalid="ignore", divide="ignore"):
            mom = panel.close[pos - 21, cols] / panel.close[pos - 252, cols] - 1.0
        s = pd.Series(mom, index=names).replace([np.inf, -np.inf], np.nan)
        return op.rank_normal(s)  # rank-normal within the universe

    return alpha_source


def pct(x: list[float], q: float) -> float:
    return float(np.percentile(np.asarray(x, dtype=float), q)) if len(x) else float("nan")


def summarise(
    name: str, dec: op.BookDecider, res: Any, panel: PricePanel, rm: RiskModel, wall: float
) -> dict[str, Any]:
    recs = dec.records
    daily = res.daily
    spy = pd.Series(op.market_returns(panel), index=panel.dates).reindex(daily.index)
    # T-bill sleeve return: SGOV when priced else BIL, on the previous closing exposure
    sleeve_ret = pd.Series(0.0, index=panel.dates)
    for s in reversed(SLEEVES):
        if panel.has(s):
            c = panel.close[:, panel.col(s)]
            r = pd.Series(np.r_[np.nan, c[1:] / c[:-1] - 1.0], index=panel.dates)
            sleeve_ret = r.where(r.notna(), sleeve_ret)
    sl = sleeve_ret.reindex(daily.index).fillna(0.0)
    overlay = daily["net"] - daily["tbill_exp"].shift(1).fillna(1.0) * sl
    ok = spy.notna() & overlay.notna()
    y, x = overlay[ok].to_numpy(), spy[ok].to_numpy()
    xc = x - x.mean()
    beta = float((xc * (y - y.mean())).sum() / (xc**2).sum())
    resid = (y - y.mean()) - beta * xc
    se = float(np.sqrt((resid**2).sum() / (len(y) - 2) / (xc**2).sum()))
    realized_vol = float(y.std(ddof=1) * np.sqrt(252.0))
    good = [r for r in recs if r["ok"]]
    solve = [r["solve_s"] + r["build_s"] for r in good]
    solver = [r["solver_s"] for r in good if np.isfinite(r["solver_s"])]
    wall_l = [r["wall_s"] for r in recs]
    factors = rm.factors
    ind_k = [factors.index(g) for g in rm.groups]
    y_t = np.array([r["exposures_target"] for r in good]) if good else np.zeros((0, len(factors)))
    y_0 = np.array([r["exposures_w0"] for r in good[1:]]) if len(good) > 1 else y_t[:0]

    def mean_abs(arr: np.ndarray, ks: list[int]) -> float:
        return float(np.abs(arr[:, ks]).mean()) if len(arr) else float("nan")

    def style_map(arr: np.ndarray) -> dict[str, float]:
        return {
            s: float(np.abs(arr[:, factors.index(s)]).mean()) if len(arr) else float("nan")
            for s in STYLES
        }

    etf_sum: dict[str, float] = {}
    for r in good:
        for k, v in r["etf_weights"].items():
            etf_sum[k] = etf_sum.get(k, 0.0) + v
    etf_mean = {k: v / max(len(good), 1) for k, v in etf_sum.items()}
    costs = {
        c: float(daily[c].sum()) * 1e4 for c in ("cost_spread", "cost_impact", "cost_fees")
    } | {c: float(daily[c].sum()) * 1e4 for c in ("cost_borrow", "cost_margin")}
    days = len(daily)
    return {
        "label": name,
        "n_rebalances": len(recs),
        "n_failed": sum(1 for r in recs if not r["ok"]),
        "failure_rate": dec.failure_rate,
        "failure_reasons": sorted({r["reason"] for r in recs if not r["ok"]}),
        "solve_s_median": pct(solve, 50),
        "solve_s_p95": pct(solve, 95),
        "solver_s_median": pct(solver, 50),
        "solver_s_p95": pct(solver, 95),
        "decide_wall_s_median": pct(wall_l, 50),
        "decide_wall_s_p95": pct(wall_l, 95),
        "n_assets_median": pct([r["n_assets"] for r in good], 50),
        "n_assets_max": max([r["n_assets"] for r in good], default=0),
        "run_wall_s": wall,
        "n_long_mean": float(np.mean([r["n_long"] for r in good])) if good else float("nan"),
        "n_short_mean": float(np.mean([r["n_short"] for r in good])) if good else float("nan"),
        "long_gross_mean": float(np.mean([r["long_gross"] for r in good])) if good else None,
        "short_gross_mean": float(np.mean([r["short_gross"] for r in good])) if good else None,
        "etf_hedge_mean_weight": etf_mean,
        "etf_hedge_share_of_rebalances": {
            k: sum(1 for r in good if k in r["etf_weights"]) / max(len(good), 1) for k in etf_mean
        },
        "ex_ante_vol_target_mean": float(np.mean([r["vol_target"] for r in good]))
        if good
        else None,
        "ex_ante_vol_pre_rebalance_mean": float(np.mean([r["vol_w0"] for r in good[1:]]))
        if len(good) > 1
        else None,
        "realized_vol_overlay": realized_vol,
        "realized_beta_to_spy": beta,
        "realized_beta_se_ols": se,
        "n_days": int(ok.sum()),
        "overlay_ann_return_diag": float(y.mean() * 252.0),
        "pred_beta_target_mean_abs": float(np.mean([abs(r["beta_target"]) for r in good]))
        if good
        else None,
        "pred_beta_pre_rebalance_mean": float(np.mean([r["beta_w0"] for r in good[1:]]))
        if len(good) > 1
        else None,
        "industry_exposure_mean_abs_target": mean_abs(y_t, ind_k),
        "industry_exposure_mean_abs_pre_rebalance": mean_abs(y_0, ind_k),
        "industry_exposure_max_abs_target": float(np.abs(y_t[:, ind_k]).max())
        if len(y_t)
        else None,
        "style_exposure_mean_abs_target": style_map(y_t),
        "style_exposure_mean_abs_pre_rebalance": style_map(y_0),
        "status_counts": {
            k: sum(1 for r in recs if r["status"] == k) for k in sorted({r["status"] for r in recs})
        },
        "traded_notional_over_equity_per_year": float(daily["turnover"].mean() * 252.0),
        "turnover_one_sided_annualized": float(
            np.mean([r["turnover_one_sided"] for r in good]) * 52.0
        )
        if good
        else None,
        "turnover_one_sided_per_rebalance_mean": float(
            np.mean([r["turnover_one_sided"] for r in good])
        )
        if good
        else None,
        "costs_bp_of_equity_over_span": costs,
        "costs_bp_per_year": {k: v * 252.0 / days for k, v in costs.items()},
        "max_constraint_violation": max([r["max_violation"] for r in good], default=0.0),
        "rss_peak_mb_process": vmhwm_mb(),
        "reg_t_violation_days": res.info.get("reg_t_violation_days"),
        "n_forced_exits_total": int(sum(r.get("forced_exits", 0) for r in good)),
        "sample_rebalance_dates": [str(r["date"].date()) for r in recs[:3]],
    }


def run_config(
    panel: PricePanel,
    alpha_source: Any,
    elig: Any,
    rm: RiskModel,
    attrs: PanelAttributes,
    etf: ETFRisk,
    span: str,
    config: str,
    method: str,
    **opt_overrides: Any,
) -> tuple[op.BookDecider, Any]:
    """One weekly-book run of configuration ``config`` ('A'/'B'/'C') with beta method ``method``
    over ``SPANS[span]``; shared with ``check_optimizer_robustness_v1.py``.  Returns the decider
    (its ``records``) and the ``run_book`` result."""
    _, start, end = SPANS[span]
    spec = op.BookSpec(config, op.OptConfig(beta_method=method, snapshot="close", **opt_overrides))
    dec = op.make_decide(alpha_source, rm, spec, attrs=attrs, etf_risk=etf, eligibility=elig)
    cfg = op.book_config(
        spec,
        attrs,
        freq="W",
        offset=0,
        exec_price="close",
        start=start,
        end=end,
        initial_weights={TBILL: 1.0},
        snapshots=False,
    )
    return dec, run_book(panel, dec, cfg)


def run_all(args: argparse.Namespace) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "results.json"
    results: dict[str, Any] = json.loads(path.read_text()) if path.exists() else {}
    rm = RiskModel()
    attrs = PanelAttributes()
    etf = ETFRisk(rm)
    for span in args.spans:
        load_start, _, end = SPANS[span]
        todo = [
            (c, m)
            for c in args.configs
            for m in args.methods
            if f"{span}|{c}|{m}" not in results.get("runs", {})
        ]
        if not todo:
            continue
        panel = PricePanel.from_dir(start=load_start, end=end)
        alpha_source = make_alpha_source(panel)
        elig = op.ShortEligibility(panel)
        for c, m in todo:
            t0 = time.time()
            dec, res = run_config(panel, alpha_source, elig, rm, attrs, etf, span, c, m)
            out = summarise(f"{span}|{c}|{m}", dec, res, panel, rm, time.time() - t0)
            results.setdefault("runs", {})[f"{span}|{c}|{m}"] = out
            path.write_text(json.dumps(results, indent=1, default=str))
            etf.flush()
            print(
                f"{span} {c} {m}: beta {out['realized_beta_to_spy']:+.3f} "
                f"vol {out['realized_vol_overlay']:.3f} fail {out['failure_rate']:.2f} "
                f"solve p50 {out['solve_s_median']:.2f}s  {out['run_wall_s']:.0f}s",
                flush=True,
            )
        del panel
    results["meta"] = {
        "note": "plumbing smoke; not a performance claim",
        "score": "mom_12_1 = close[t-21]/close[t-252]-1, rank-normal within the universe",
        "exec_price": "close (spread snapshot close)",
        "freq": "W offset 0",
        "ic": op.DEFAULT_IC,
        "opt_defaults": {k: getattr(op.OptConfig(), k) for k in op.OptConfig.__dataclass_fields__},
    }
    path.write_text(json.dumps(results, indent=1, default=str))


def bench(args: argparse.Namespace) -> None:
    """Single-solve timing and memory at 2024-06-28 for several pre-filter widths (own
    process)."""
    OUT.mkdir(parents=True, exist_ok=True)
    rm = RiskModel()
    attrs = PanelAttributes()
    etf = ETFRisk(rm)
    panel = PricePanel.from_dir(start="2023-01-02", end="2024-12-31")
    alpha_source = make_alpha_source(panel)
    elig = op.ShortEligibility(panel)
    i = int(panel.dates.searchsorted(pd.Timestamp("2024-06-28")))
    t = panel.dates[i]
    from open_composer.research.equity_book.backtest import BookState

    empty = pd.Series(dtype=float)
    st = BookState(t, i, 1.0, empty, empty, 1.0, 0.0, 0.0, 0.0, panel)
    out = []
    for tail, mode in (
        (0.35, "exact"),
        (0.35, "quadratic_ub"),
        (0.9, "exact"),
        (0.9, "quadratic_ub"),
    ):
        spec = op.BookSpec("A", op.OptConfig(tail_frac=tail, impact_mode=mode))
        dec = op.make_decide(alpha_source, rm, spec, attrs=attrs, etf_risk=etf, eligibility=elig)
        dec(t, st)  # warm the caches (attribute year, risk year)
        hwm_reset()
        rss0 = vmrss_mb()
        dec.records.clear()
        for _ in range(3):
            dec(t, st)
        r = dec.records[-1]
        out.append(
            {
                "tail_frac": tail,
                "impact_mode": mode,
                "n_assets": r["n_assets"],
                "solve_s_runs": [x["solve_s"] + x["build_s"] for x in dec.records],
                "solver_s_runs": [x["solver_s"] for x in dec.records],
                "decide_wall_s_runs": [x["wall_s"] for x in dec.records],
                "rss_before_mb": rss0,
                "rss_peak_mb": vmhwm_mb(),
                "rss_peak_increment_mb": vmhwm_mb() - rss0,
                "status": r["status"],
            }
        )
        print(out[-1], flush=True)
    (OUT / "bench.json").write_text(json.dumps(out, indent=1, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--spans", nargs="+", default=list(SPANS))
    ap.add_argument("--configs", nargs="+", default=["A"])
    ap.add_argument("--methods", nargs="+", default=["ewma", "vasicek", "model", "ewma21"])
    ap.add_argument("--bench", action="store_true")
    args = ap.parse_args()
    os.environ.setdefault("POLARS_SKIP_CPU_CHECK", "1")
    bench(args) if args.bench else run_all(args)


if __name__ == "__main__":
    main()
