"""T-20261002-43: program allocation under a ~30% max drawdown budget, return first.

Implements `reports/research/program/allocation-dd30-2026-10-02/prereg.md` (frozen, commit 469ae13)
exactly: engines S3 / C2 / F1 / F2 / CASH, monthly rebalancing on session k of each month with
drift in between and 5 bp per unit of |weight change|, grid A (unlevered, step 0.05, sum 1) and
grid B (levered, sum of risky weights <= 1.5, borrowing at 6.50%/yr, approximate margin filter),
objective = anchor CAGR subject to full-window max drawdown >= -30%, delevered-S3 control,
out-of-window (select -> ytd2026) and stability guards.

All grid points are simulated together (vectorised over points), with per-window statistics kept
online so no NAV path matrix is stored. Chosen points are re-run with their full path.

Usage: uv run python scripts/run_program_dd30_allocation.py [OUT_DIR]
"""

from __future__ import annotations

import itertools
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

OUT_DIR = ROOT / "reports/research/program/allocation-dd30-2026-10-02"
ENGINES = ["S3", "C2", "F1", "F2", "CASH"]
RISKY = ["S3", "C2", "F1", "F2"]
STEP = 0.05
DD_LIMIT = -0.30
FRONTIER_LIMITS = [-0.25, -0.30, -0.35]
REBAL_COST = 0.0005
DEBIT_RATE = 0.065
MAX_RISKY_B = 1.5
OFFSETS = [0, 5, 10, 15]
WINDOWS = {
    "full": ("2017-10-02", "2026-09-15"),
    "stress": ("2017-10-02", "2023-09-15"),
    "select": ("2023-09-18", "2025-12-31"),
    "anchor": ("2024-01-08", "2026-09-15"),
    "ytd2026": ("2026-01-02", "2026-09-15"),
}
INIT_REQ = {"S3": 0.75, "other": 0.50}
MAINT_REQ = {"S3": 0.75, "other": 0.30}
CAGR_EDGE_MIN = 0.03
STABILITY_MAX = 0.05


# ---------------------------------------------------------------- data

#: The v1.2 book files are indexed by DECISION date t: the row's P&L is realized from the
#: close of t+1 (MOC fill) to the close of t+2. Verified 2026-10-02: the file's `spy_ret` at t
#: equals SIP SPY's close-to-close return at t+2 (correlation 1.000, 99.96% of rows within
#: 1e-4). S3 and C2 are indexed by realization date (lag-0 correlation with SPY 0.53, 0.86).
BOOK_REALIZATION_LAG = 2


def realization_dated(decision_dated: pd.Series, lag: int = BOOK_REALIZATION_LAG) -> pd.Series:
    """Re-index a decision-dated book series to the session on which it is realized.

    The value at decision date t moves to session t+lag of the same session calendar; the first
    `lag` sessions (book not yet invested) get 0.0 and the last `lag` values fall off the end.
    """
    out = decision_dated.shift(lag)
    out.iloc[:lag] = 0.0
    return out


def load_engines(cost: str = "net10") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Daily returns for S3/C2/F1/F2/CASH on common dates, plus F1/F2 gross per unit."""
    import run_h20260918_05_recent_menu as base
    import run_h20260927_01_sleeve_combination as comb

    base.WARMUP_START = comb.PANEL_START
    close, open_ = base.load_panel(comb.salvage.symbols())
    leg_open, leg_close = comb.salvage.legs(close, open_)
    bps = base.COST_BPS_PRIMARY if cost == "net10" else base.COST_BPS_STRESS
    s3 = comb.sleeve_returns(close, leg_open, leg_close, bps)["s3"]
    cash = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)

    screen = pd.read_parquet(
        ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.parquet"
    )
    c2 = screen[f"C2__o00__{cost}"]

    books = {}
    gross = {}
    for f in ("F1", "F2"):
        d = pd.read_parquet(ROOT / f"data/research/book_v12/A1_M0_U3000_{f}.parquet")
        books[f] = realization_dated(d["net_pnl"] / 1e6)
        gross[f] = realization_dated(d["gross"] / 1e6)

    series = {"S3": s3, "C2": c2, "F1": books["F1"], "F2": books["F2"], "CASH": cash}
    for s in series.values():
        s.index = pd.to_datetime(s.index)
    frame = pd.DataFrame(series)
    start, end = WINDOWS["full"]
    frame = frame.loc[start:end]
    missing = frame.isna().sum().to_dict()
    frame = frame.dropna()
    g = pd.DataFrame(gross).reindex(frame.index).ffill()
    meta = {"rows": int(len(frame)), "dropped_na_by_engine": missing}
    frame.attrs["meta"] = meta
    return frame, g


# ---------------------------------------------------------------- grids


def grid_a() -> np.ndarray:
    n = int(round(1 / STEP))
    pts = []
    for a, b, c, d in itertools.product(range(n + 1), repeat=4):
        s = a + b + c + d
        if s <= n:
            pts.append((a, b, c, d, n - s, 0))
    return np.array(pts, dtype=float) * STEP


def grid_b() -> np.ndarray:
    n = int(round(1 / STEP))
    cap = int(round(MAX_RISKY_B / STEP))
    pts = []
    for a, b, c, d in itertools.product(range(n + 1), repeat=4):
        s = a + b + c + d
        if s <= cap:
            pts.append((a, b, c, d, max(0, n - s), -max(0, s - n)))
    return np.array(pts, dtype=float) * STEP


def margin_ok(w: np.ndarray, gmax: dict[str, float]) -> np.ndarray:
    other = w[:, 1] + w[:, 2] * gmax["F1"] + w[:, 3] * gmax["F2"]
    init = INIT_REQ["S3"] * w[:, 0] + INIT_REQ["other"] * other
    maint = MAINT_REQ["S3"] * w[:, 0] + MAINT_REQ["other"] * other
    return (init <= 1.0 + 1e-9) & (maint <= 0.9 + 1e-9)


# ---------------------------------------------------------------- simulation


def rebalance_mask(index: pd.DatetimeIndex, offset: int) -> np.ndarray:
    """True on the session where weights are reset: the offset-th session of each month."""
    months = index.to_period("M")
    pos = pd.Series(np.arange(len(index)), index=index).groupby(months).cumcount().to_numpy()
    mask = pos == offset
    # months shorter than offset+1 sessions: no rebalance that month (never happens for <= 15)
    mask[0] = True  # start invested at target weights
    return mask


def simulate(
    weights: np.ndarray, rets: np.ndarray, index: pd.DatetimeIndex, offset: int
) -> dict[str, np.ndarray]:
    """Vectorised over points. Returns per-window CAGR, vol, Sharpe-like (mean/std), max DD."""
    n_pts = weights.shape[0]
    rebal = rebalance_mask(index, offset)
    debit_daily = DEBIT_RATE / 252.0
    full_rets = np.column_stack([rets, np.full(len(index), debit_daily)])  # 6th = borrowing
    w_target = weights
    h = w_target.copy()
    nav = np.ones(n_pts)
    win_masks = {
        k: ((index >= pd.Timestamp(a)) & (index <= pd.Timestamp(b)))
        for k, (a, b) in WINDOWS.items()
    }
    stats = {
        k: {
            "start": np.full(n_pts, np.nan),
            "end": np.full(n_pts, np.nan),
            "peak": np.full(n_pts, np.nan),
            "mdd": np.zeros(n_pts),
            "s1": np.zeros(n_pts),
            "s2": np.zeros(n_pts),
            "n": 0,
        }
        for k in WINDOWS
    }
    for t in range(len(index)):
        nav_prev = nav.copy()  # before the rebalance cost, so the day's return includes it
        if rebal[t] and t > 0:
            turnover = np.abs(w_target - h).sum(axis=1)
            nav = nav * (1.0 - REBAL_COST * turnover)
            h = w_target.copy()
        grown = h * (1.0 + full_rets[t])
        port = grown.sum(axis=1)
        nav = nav * port
        with np.errstate(divide="ignore", invalid="ignore"):
            h = np.where(port[:, None] != 0, grown / port[:, None], h)
        r_day = nav / nav_prev - 1.0
        for k, m in win_masks.items():
            if not m[t]:
                continue
            st = stats[k]
            if st["n"] == 0:
                st["start"] = nav_prev.copy()
                st["peak"] = nav_prev.copy()
            st["peak"] = np.maximum(st["peak"], nav)
            st["mdd"] = np.minimum(st["mdd"], nav / st["peak"] - 1.0)
            st["s1"] += r_day
            st["s2"] += r_day * r_day
            st["n"] += 1
            st["end"] = nav.copy()
    out: dict[str, np.ndarray] = {}
    for k, st in stats.items():
        n = st["n"]
        years = n / 252.0
        out[f"{k}_cagr"] = (st["end"] / st["start"]) ** (1.0 / years) - 1.0
        mean = st["s1"] / n
        var = np.maximum(st["s2"] / n - mean * mean, 0.0)
        out[f"{k}_vol"] = np.sqrt(var) * np.sqrt(252.0)
        with np.errstate(divide="ignore", invalid="ignore"):
            out[f"{k}_sharpe_raw"] = np.where(var > 0, mean / np.sqrt(var) * np.sqrt(252.0), 0.0)
        out[f"{k}_mdd"] = st["mdd"]
    return out


def path(weights: np.ndarray, rets: np.ndarray, index: pd.DatetimeIndex, offset: int) -> pd.Series:
    """Daily program returns for one point (same mechanics as `simulate`)."""
    rebal = rebalance_mask(index, offset)
    full_rets = np.column_stack([rets, np.full(len(index), DEBIT_RATE / 252.0)])
    h = weights.copy()
    nav = 1.0
    out = np.zeros(len(index))
    for t in range(len(index)):
        prev = nav  # before the rebalance cost, so the day's return includes it
        if rebal[t] and t > 0:
            nav *= 1.0 - REBAL_COST * np.abs(weights - h).sum()
            h = weights.copy()
        grown = h * (1.0 + full_rets[t])
        port = grown.sum()
        nav *= port
        h = grown / port
        out[t] = nav / prev - 1.0
    return pd.Series(out, index=index)


def window_stats(ret: pd.Series, rf: pd.Series) -> dict[str, Any]:
    res = {}
    for k, (a, b) in WINDOWS.items():
        r = ret.loc[a:b]
        f = rf.loc[a:b]
        nav = (1 + r).cumprod()
        years = len(r) / 252.0
        ex = r - f
        res[k] = {
            "cagr": float(nav.iloc[-1] ** (1 / years) - 1),
            "vol": float(r.std() * np.sqrt(252)),
            "sharpe_excess": float(ex.mean() / ex.std() * np.sqrt(252)) if ex.std() > 0 else None,
            "max_dd": float((nav / nav.cummax() - 1).min()),
            "worst_month": float(((1 + r).resample("ME").prod() - 1).min()),
        }
    cal = (1 + ret).groupby(ret.index.year).prod() - 1
    res["calendar"] = {str(y): float(v) for y, v in cal.items()}
    return res


# ---------------------------------------------------------------- selection


def choose(
    res: dict[str, np.ndarray], feasible: np.ndarray, objective: str, dd_limit: float
) -> int:
    ok = feasible & (res["full_mdd"] >= dd_limit) & np.isfinite(res[objective])
    if not ok.any():
        return -1
    obj = np.where(ok, res[objective], -np.inf)
    best = obj.max()
    ties = np.flatnonzero(ok & (obj >= best - 1e-12))
    return int(ties[np.argmax(res["full_mdd"][ties])])


def neighbours(w: np.ndarray, grid: np.ndarray, levered: bool) -> list[int]:
    """Feasible single-coordinate +-STEP moves of a risky weight, cash/borrow re-derived."""
    idx = {tuple(np.round(row, 4)): i for i, row in enumerate(grid)}
    out = []
    for j in range(4):
        for d in (-STEP, STEP):
            cand = w.copy()
            cand[j] = round(cand[j] + d, 4)
            if cand[j] < -1e-9 or cand[j] > 1 + 1e-9:
                continue
            s = cand[:4].sum()
            if levered:
                cand[4] = round(max(0.0, 1 - s), 4)
                cand[5] = round(-max(0.0, s - 1), 4)
            else:
                cand[4] = round(1 - s, 4)
                cand[5] = 0.0
                if cand[4] < -1e-9:
                    continue
            key = tuple(np.round(cand, 4))
            if key in idx:
                out.append(idx[key])
    return out


def describe(w: np.ndarray) -> dict[str, float]:
    d = {e: round(float(w[i]), 4) for i, e in enumerate(ENGINES)}
    d["BORROW"] = round(float(-w[5]), 4)
    return d


def inverse_vol_path(rets: pd.DataFrame, offset: int) -> pd.Series:
    risky = rets[RISKY]
    vol = risky.rolling(63).std().shift(1)
    rebal = rebalance_mask(rets.index, offset)
    h = None
    nav = 1.0
    out = np.zeros(len(rets))
    for t in range(len(rets)):
        prev = nav  # before the rebalance cost, so the day's return includes it
        if (rebal[t] or h is None) and np.isfinite(vol.iloc[t]).all():
            inv = 1.0 / vol.iloc[t].to_numpy()
            target = np.append(inv / inv.sum(), 0.0)
            if h is not None:
                nav *= 1.0 - REBAL_COST * np.abs(target - h).sum()
            h = target
        if h is None:
            out[t] = rets["CASH"].iloc[t]
            continue
        grown = h * (1.0 + rets.iloc[t].to_numpy())
        port = grown.sum()
        nav *= port
        h = grown / port
        out[t] = nav / prev - 1.0
    return pd.Series(out, index=rets.index)


def run_grid(name: str, grid: np.ndarray, levered: bool, rets: pd.DataFrame, gmax: dict) -> dict:
    feasible = margin_ok(grid, gmax) if levered else np.ones(len(grid), dtype=bool)
    res0 = simulate(grid, rets.to_numpy(), rets.index, OFFSETS[0])
    out: dict[str, Any] = {"n_points": int(len(grid)), "n_margin_feasible": int(feasible.sum())}
    star = choose(res0, feasible, "anchor_cagr", DD_LIMIT)
    sel = choose(res0, feasible, "select_cagr", DD_LIMIT)
    frontier = {}
    for lim in FRONTIER_LIMITS:
        i = choose(res0, feasible, "anchor_cagr", lim)
        frontier[str(lim)] = (
            None
            if i < 0
            else {
                "weights": describe(grid[i]),
                **{k: float(res0[k][i]) for k in res0},
            }
        )
    out["frontier"] = frontier
    if star < 0:
        out["w_star"] = None
        return out
    out["w_star"] = {
        "index": star,
        "weights": describe(grid[star]),
        **{k: float(res0[k][star]) for k in res0},
    }
    out["w_sel"] = (
        None
        if sel < 0
        else {
            "index": sel,
            "weights": describe(grid[sel]),
            **{k: float(res0[k][sel]) for k in res0},
        }
    )
    nb = neighbours(grid[star], grid, levered)
    nb = [i for i in nb if feasible[i]]
    out["neighbours"] = [
        {
            "weights": describe(grid[i]),
            "anchor_cagr": float(res0["anchor_cagr"][i]),
            "full_mdd": float(res0["full_mdd"][i]),
        }
        for i in nb
    ]
    offs = {}
    for k in OFFSETS:
        r = simulate(grid[[star]], rets.to_numpy(), rets.index, k)
        offs[str(k)] = {
            "anchor_cagr": float(r["anchor_cagr"][0]),
            "full_mdd": float(r["full_mdd"][0]),
        }
    out["offsets"] = offs
    ok = feasible & (res0["full_mdd"] >= DD_LIMIT)
    order = np.argsort(np.where(ok, -res0["anchor_cagr"], np.inf))[:10]
    out["top10"] = [
        {
            "weights": describe(grid[i]),
            "anchor_cagr": float(res0["anchor_cagr"][i]),
            "full_mdd": float(res0["full_mdd"][i]),
        }
        for i in order
        if ok[i]
    ]
    out["_star_w"] = grid[star]
    out["_sel_w"] = None if sel < 0 else grid[sel]
    out["_top10_mean"] = grid[order[ok[order]]].mean(axis=0) if ok.any() else None
    return out


def main() -> int:
    out_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else OUT_DIR
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    rets, gross = load_engines("net10")
    rets20, _ = load_engines("net20")
    gmax = {"F1": float(gross["F1"].max()), "F2": float(gross["F2"].max())}
    rf = rets["CASH"]

    # control: S3 + CASH, largest w_S3 on the grid with full DD >= -30%
    ctrl_grid = np.array([[a, 0, 0, 0, 1 - a, 0] for a in np.arange(0, 1 + 1e-9, STEP)])
    ctrl_res = simulate(ctrl_grid, rets.to_numpy(), rets.index, OFFSETS[0])
    ok = ctrl_res["full_mdd"] >= DD_LIMIT
    ci = int(np.flatnonzero(ok).max()) if ok.any() else -1
    control = {"weights": describe(ctrl_grid[ci]), **{k: float(ctrl_res[k][ci]) for k in ctrl_res}}

    results: dict[str, Any] = {
        "task": "T-20261002-43",
        "prereg": "reports/research/program/allocation-dd30-2026-10-02/prereg.md (commit 469ae13)",
        "generated_at_utc": started,
        "data": {
            **rets.attrs.get("meta", {}),
            "start": str(rets.index[0].date()),
            "end": str(rets.index[-1].date()),
            "gross_max": gmax,
        },
        "control_delevered_s3": control,
        "engine_stats": {e: window_stats(rets[e], rf) for e in ENGINES[:-1]},
        "engine_corr": {
            w: rets.loc[a:b, RISKY].corr().round(3).to_dict()
            for w, (a, b) in WINDOWS.items()
            if w in ("stress", "anchor")
        },
    }

    grids = {"A": (grid_a(), False), "B": (grid_b(), True)}
    chosen: dict[str, Any] = {}
    for name, (grid, levered) in grids.items():
        g = run_grid(name, grid, levered, rets, gmax)
        star_w, sel_w, top_mean = (
            g.pop("_star_w", None),
            g.pop("_sel_w", None),
            g.pop("_top10_mean", None),
        )
        if star_w is not None:
            star_path = path(star_w, rets.to_numpy(), rets.index, 0)
            star20 = path(star_w, rets20.loc[rets.index].to_numpy(), rets.index, 0)
            g["w_star_detail"] = window_stats(star_path, rf)
            g["w_star_stress_cost"] = window_stats(star20, rf)
            ctrl_path = path(ctrl_grid[ci], rets.to_numpy(), rets.index, 0)
            g["guard_i_edge"] = g["w_star"]["anchor_cagr"] - control["anchor_cagr"]
            g["guard_i_pass"] = bool(g["guard_i_edge"] >= CAGR_EDGE_MIN)
            if sel_w is not None:
                sel_path = path(sel_w, rets.to_numpy(), rets.index, 0)
                g["w_sel_ytd2026_cagr"] = window_stats(sel_path, rf)["ytd2026"]["cagr"]
                g["control_ytd2026_cagr"] = window_stats(ctrl_path, rf)["ytd2026"]["cagr"]
                g["guard_ii_pass"] = bool(g["w_sel_ytd2026_cagr"] >= g["control_ytd2026_cagr"])
            else:
                g["guard_ii_pass"] = False
            nb_dev = [abs(n["anchor_cagr"] - g["w_star"]["anchor_cagr"]) for n in g["neighbours"]]
            off_vals = [v["anchor_cagr"] for v in g["offsets"].values()]
            g["guard_iii_neighbour_max_dev"] = max(nb_dev) if nb_dev else None
            g["guard_iii_offset_range"] = max(off_vals) - min(off_vals)
            g["guard_iii_pass"] = bool(
                (not nb_dev or max(nb_dev) < STABILITY_MAX)
                and g["guard_iii_offset_range"] < STABILITY_MAX
            )
            if top_mean is not None:
                tm = top_mean.copy()
                tp = path(tm, rets.to_numpy(), rets.index, 0)
                g["robust_top10_mean"] = {"weights": describe(tm), "detail": window_stats(tp, rf)}
            chosen[name] = (star_w, star_path)
        results[f"grid_{name}"] = g

    iv = inverse_vol_path(rets, 0)
    results["inverse_vol_unlevered"] = window_stats(iv, rf)

    # decision (prereg rule 3-5): prefer B if feasible and better, else A
    pick = None
    for name in ("B", "A"):
        g = results.get(f"grid_{name}")
        if g and g.get("w_star"):
            if (
                pick is None
                or g["w_star"]["anchor_cagr"] > results[f"grid_{pick}"]["w_star"]["anchor_cagr"]
            ):
                pick = name
    decision: dict[str, Any] = {"grid": pick}
    if pick is None:
        decision["outcome"] = "control"
    else:
        g = results[f"grid_{pick}"]
        if not g["guard_i_pass"]:
            decision["outcome"] = "control"
            decision["weights"] = control["weights"]
        elif g["guard_ii_pass"] and g["guard_iii_pass"]:
            decision["outcome"] = "w_star"
            decision["weights"] = g["w_star"]["weights"]
        else:
            decision["outcome"] = "robust_top10_mean"
            decision["weights"] = g["robust_top10_mean"]["weights"]
            decision["robust_full_mdd"] = g["robust_top10_mean"]["detail"]["full"]["max_dd"]
    results["decision"] = decision

    out_dir.mkdir(parents=True, exist_ok=True)
    if pick is not None and decision["outcome"] != "control":
        w = np.array([decision["weights"][e] for e in ENGINES] + [-decision["weights"]["BORROW"]])
        prog = path(w, rets.to_numpy(), rets.index, 0)
        pd.DataFrame({"program_ret": prog}).to_parquet(out_dir / "program_returns.parquet")
        results["decision_detail"] = window_stats(prog, rf)
    (out_dir / "results.json").write_text(
        json.dumps(results, indent=1, default=float) + "\n", encoding="utf-8"
    )
    print(json.dumps({"decision": decision, "control": control["weights"]}, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
