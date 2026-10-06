# ruff: noqa: E501  (report f-strings are table rows)
"""T-20261004-58 (P4): program allocation v2, contract t20261005_p4_alloc_v2 (+ amendment A2).

Stages: ``build`` (load series, identity checks, cache/panel.parquet + build.json), ``run``
(contract sections 3-8 plus the A2 reference P0-S3), ``report`` (report.md, trial-ledger.json,
weights-latest.json). The contract is the authority; nothing here changes a rule, window,
threshold or candidate. Mechanical statuses are written by code from `deltas`.

Usage: uv run python scripts/run_alloc_v2_t58.py --stage build|run|report
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import resource
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT))

import run_program_dd30_allocation as dd30  # noqa: E402

D = ROOT / "reports/research/iterations/t20261005_p4_alloc_v2"
CACHE = D / "cache"
T32 = ROOT / "reports/research/iterations/t20261005_p2_s1_theme_budget"
T31_PATH = ROOT / "reports/research/program/etf-dsr-2026-10-08/results.json"
T75_PATH = ROOT / "reports/research/program/concentration-regimes-2026-10-06/results.json"
T71_PATH = ROOT / "reports/research/program/capacity-live-2026-10-07/results.json"
T43_DIR = ROOT / "reports/research/program/allocation-dd30-2026-10-02"
C2_REPAIRED = (
    ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.sip-repaired-20261002.parquet"
)

SLEEVES = ["S1", "S2", "S3", "C2", "F1", "F2"]
ETF = ["S1", "S2", "S3", "C2"]
E4 = ["S1", "S2", "S3", "C2"]
E6 = ["S1", "S2", "S3", "C2", "F1", "F2"]
END = "2026-09-15"
WIN = {
    "recent": ("2024-01-08", END),
    "stress": ("2017-10-02", "2023-08-31"),
    "full": ("2017-10-02", END),
}
OFFS = [0, 4, 8, 12, 16]
OFF_KEYS = [f"o{o}" for o in OFFS]
DEBIT_D = 0.065 * 365 / 360 / 252
REBAL_COST = 0.0005
P0_W = {"S3": 0.642, "C2": 0.358}
CAP_LEVELS = [0.80, 0.70, 0.60, 0.50]
RULES = [f"T58_CAP2_{c:.2f}" for c in CAP_LEVELS] + [
    "T58_ERC_E4",
    "T58_IV_E4",
    "T58_ERC_E6",
    "T58_IV_E6",
]
SMALL_RULES = RULES[:6]
SEED = 20261005
COV_WIN = 126
VOL_WIN = 63
MIN_F_HISTORY = 63
DD_LIMIT = -0.30
K_GRID = [round(0.50 + 0.05 * i, 2) for i in range(31)]
TIERS = {"50k": 50_000, "100k": 100_000, "250k": 250_000, "1M": 1_000_000}
M_MAINT = {"S1": 0.30, "S2": 0.30, "S3": 0.75, "C2": 0.30, "F1": 0.30, "F2": 0.30}
M_INIT = {s: max(0.5, m) for s, m in M_MAINT.items()}
MIN_CAP = {"S1": 10_000, "S2": 10_000, "S3": 10_000, "C2": 10_000, "F1": 250_000, "F2": 250_000}
MAINT_LIMIT = 0.9
INIT_LIMIT = 1.0
N_BOOT = 10_000
HORIZONS = [126, 252]
MEAN_BLOCK = 21
N_PLACEBO = 200
TRADING_DAYS = 252


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ------------------------------------------------------------------ risk-budget solver


def risk_shares(w: np.ndarray, cov: np.ndarray) -> np.ndarray:
    """Euler risk contribution shares RC_i = w_i (Sigma w)_i / w' Sigma w."""
    w = np.asarray(w, float)
    marg = w * (cov @ w)
    return marg / marg.sum()


def rb_weights(
    cov: np.ndarray, budgets: np.ndarray, tol: float = 1e-10, max_sweeps: int = 200_000
) -> np.ndarray:
    """Risk-budget portfolio by cyclical coordinate descent (Griveau-Billion et al. 2013).

    Minimises 0.5 x'Sx - sum b_i ln x_i; w = x / sum x has RC share = b_i at the optimum.
    """
    cov = np.atleast_2d(np.asarray(cov, float))
    b = np.asarray(budgets, float)
    n = len(b)
    if n == 1:
        return np.ones(1)
    diag = np.diag(cov)
    x = np.sqrt(b / diag)
    for _ in range(max_sweeps):
        for i in range(n):
            s = float(cov[i] @ x - cov[i, i] * x[i])
            x[i] = (-s + math.sqrt(s * s + 4.0 * cov[i, i] * b[i])) / (2.0 * cov[i, i])
        w = x / x.sum()
        if np.max(np.abs(risk_shares(w, cov) - b)) <= tol:
            return w
    raise RuntimeError("risk-budget solver did not converge")


def cap2_weights(cov: np.ndarray, c: float, p0: np.ndarray) -> np.ndarray:
    """CAP2: P0 when its S3 (first asset) risk share <= c, else the (c, 1-c) risk budget."""
    s = float(risk_shares(p0, cov)[0])
    if s <= c:
        return np.asarray(p0, float)
    return rb_weights(cov, np.array([c, 1.0 - c]))


# ------------------------------------------------------------------ same-vol, stats


def samevol_x(ex_r: np.ndarray, ex_p: np.ndarray, rf: np.ndarray) -> tuple[np.ndarray, float]:
    """Same-volatility excess series x = k(r-rf) - max(k-1,0)(debit-rf); k = sd(P0)/sd(R)."""
    k = float(np.std(ex_p, ddof=1) / np.std(ex_r, ddof=1))
    x = k * ex_r - max(k - 1.0, 0.0) * (DEBIT_D - rf)
    return x, k


def sharpe(x: np.ndarray) -> float:
    sd = float(np.std(x, ddof=1))
    return float(np.mean(x) / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else float("nan")


def es975(x: np.ndarray) -> float:
    """Expected shortfall at 97.5% as a positive loss (mean of the worst 2.5% days, sign flipped)."""
    q = np.quantile(x, 0.025)
    return float(-np.mean(x[x <= q]))


def maxdd(r: np.ndarray) -> float:
    nav = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    return float(np.min(nav / np.maximum.accumulate(nav) - 1.0))


def win_series(s: pd.Series, win: str) -> pd.Series:
    a, b = WIN[win]
    return s.loc[a:b]


def stat_block(r: pd.Series, rf: pd.Series, p0: pd.Series | None) -> dict[str, Any]:
    ex = (r - rf).to_numpy()
    out: dict[str, Any] = {
        "sr_raw": sharpe(ex),
        "ann_ret": float(np.prod(1.0 + r.to_numpy()) ** (TRADING_DAYS / len(r)) - 1.0),
        "ann_vol": float(r.std(ddof=1) * math.sqrt(TRADING_DAYS)),
        "maxdd": maxdd(r.to_numpy()),
    }
    if p0 is None:
        out.update(sr_samevol=out["sr_raw"], k=1.0, rho_vs_p0=1.0, es975_samevol=es975(ex))
    else:
        exp = (p0 - rf).to_numpy()
        x, k = samevol_x(ex, exp, rf.to_numpy())
        out.update(
            sr_samevol=sharpe(x),
            k=k,
            rho_vs_p0=float(np.corrcoef(ex, exp)[0, 1]),
            es975_samevol=es975(x),
        )
    return out


# ------------------------------------------------------------------ path engine


def run_path(
    wt: np.ndarray, ret: np.ndarray, rebal: np.ndarray, cost: float = REBAL_COST
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Drift-and-rebalance mechanics of run_program_dd30_allocation.path for time-varying targets.

    wt[t] is the target weight vector used on rebalance sessions (all columns incl. cash/borrow);
    ret[t] the per-column returns. Returns (daily return, end-of-day drifted weights, turnover).
    """
    n_t, n_c = ret.shape
    h = wt[0].copy()
    nav = 1.0
    out = np.zeros(n_t)
    hist = np.zeros((n_t, n_c))
    turn = np.zeros(n_t)
    for t in range(n_t):
        prev = nav
        if rebal[t] and t > 0:
            tu = float(np.abs(wt[t] - h).sum())
            turn[t] = tu
            nav *= 1.0 - cost * tu
            h = wt[t].copy()
        grown = h * (1.0 + ret[t])
        port = grown.sum()
        nav *= port
        h = grown / port
        out[t] = nav / prev - 1.0
        hist[t] = h
    return out, hist, turn


def run_static_multi(w: np.ndarray, ret: np.ndarray, rebal: np.ndarray) -> np.ndarray:
    """Vectorised run_path for P static weight vectors (no cash/borrow). Returns (T, P)."""
    n_t = ret.shape[0]
    h = w.copy()
    nav = np.ones(w.shape[0])
    out = np.empty((n_t, w.shape[0]))
    for t in range(n_t):
        prev = nav
        if rebal[t] and t > 0:
            nav = nav * (1.0 - REBAL_COST * np.abs(w - h).sum(axis=1))
            h = w.copy()
        grown = h * (1.0 + ret[t])
        port = grown.sum(axis=1)
        nav = nav * port
        h = grown / port[:, None]
        out[t] = nav / prev - 1.0
    return out


# ------------------------------------------------------------------ context


class Ctx:
    """Aligned sleeve returns for one series set (ORIG, selected, 2x-cost)."""

    def __init__(self, panel: pd.DataFrame, prefix: str, s3_col: str | None = None):
        cols = {s: panel[f"{prefix}__{s}"].to_numpy() for s in ETF}
        if s3_col is not None:
            cols["S3"] = panel[s3_col].to_numpy()
        for f in ("F1", "F2"):
            cols[f] = panel[f].to_numpy()
        self.dates = panel.index
        self.R = np.column_stack([cols[s] for s in SLEEVES])
        self.rf = panel["CASH"].to_numpy()
        self.G = np.column_stack([panel["G_F1"].to_numpy(), panel["G_F2"].to_numpy()])
        self.pos0 = int(self.dates.searchsorted(pd.Timestamp(WIN["full"][0])))
        self.pos1 = int(self.dates.searchsorted(pd.Timestamp(WIN["full"][1]), side="right"))
        self.pidx = self.dates[self.pos0 : self.pos1]
        self.fcnt = np.concatenate(
            [np.zeros((1, 2)), np.cumsum(~np.isnan(self.R[:, 4:6]), axis=0)], axis=0
        )
        self.rf_p = pd.Series(self.rf[self.pos0 : self.pos1], index=self.pidx)
        self.R0 = np.nan_to_num(self.R)

    def eligible(self, j: int, i: int) -> bool:
        return j < 4 or self.fcnt[i, j - 4] >= MIN_F_HISTORY

    def cov(self, members: list[int], i: int) -> np.ndarray | None:
        lo = max(0, i - COV_WIN)
        x = self.R[lo:i][:, members]
        x = x[~np.isnan(x).any(axis=1)]
        if len(x) < MIN_F_HISTORY:
            return None
        return np.atleast_2d(np.cov(x, rowvar=False, ddof=1))

    def vol(self, members: list[int], i: int) -> np.ndarray | None:
        x = self.R[max(0, i - VOL_WIN) : i][:, members]
        if len(x) < VOL_WIN or np.isnan(x).any():
            return None
        return x.std(axis=0, ddof=1)


def rule_spec(rule_id: str) -> dict[str, Any]:
    if rule_id.startswith("T58_CAP2_"):
        return {"kind": "CAP2", "c": float(rule_id[-4:]), "members": ["S3", "C2"]}
    if rule_id.endswith("_E4"):
        return {"kind": rule_id.split("_")[1], "members": E4}
    if rule_id.endswith("_E6"):
        return {"kind": rule_id.split("_")[1], "members": E6}
    if rule_id == "P0":
        return {"kind": "STATIC", "w": dict(P0_W), "members": ["S3", "C2"]}
    if rule_id == "P0_S3":
        return {"kind": "STATIC", "w": {"S3": 1.0}, "members": ["S3"]}
    raise KeyError(rule_id)


def solve_weights(
    ctx: Ctx, spec: dict[str, Any], i: int, members: list[str] | None = None
) -> dict[str, float]:
    """Target weights on session position i using data through i-1 only."""
    mem = [m for m in (members or spec["members"]) if ctx.eligible(SLEEVES.index(m), i)]
    if not mem:
        return {}
    if len(mem) == 1:
        return {mem[0]: 1.0}
    idx = [SLEEVES.index(m) for m in mem]
    kind = spec["kind"]
    if kind == "STATIC":
        tot = sum(spec["w"][m] for m in mem)
        return {m: spec["w"][m] / tot for m in mem}
    if kind == "IV":
        inv = 1.0 / ctx.vol(idx, i)
        return dict(zip(mem, (inv / inv.sum()).tolist(), strict=True))
    cov = ctx.cov(idx, i)
    if kind == "ERC":
        w = rb_weights(cov, np.full(len(mem), 1.0 / len(mem)))
    elif kind == "CAP2":
        p0 = np.array([P0_W[m] for m in mem])
        w = cap2_weights(cov, spec["c"], p0 / p0.sum())
    else:
        raise KeyError(kind)
    return dict(zip(mem, w.tolist(), strict=True))


def rc_vector(ctx: Ctx, w: dict[str, float], i: int) -> np.ndarray:
    """Ex-ante Euler risk shares over the 6 sleeves for weights w at position i."""
    out = np.zeros(len(SLEEVES))
    mem = [m for m, x in w.items() if x > 0]
    if not mem:
        return out
    if len(mem) == 1:
        out[SLEEVES.index(mem[0])] = 1.0
        return out
    idx = [SLEEVES.index(m) for m in mem]
    cov = ctx.cov(idx, i)
    if cov is None:
        return out
    out[idx] = risk_shares(np.array([w[m] for m in mem]), cov)
    return out


def rebal_positions(ctx: Ctx, offsets: list[int]) -> np.ndarray:
    pos = np.zeros(len(ctx.pidx), dtype=bool)
    for o in offsets:
        pos |= dd30.rebalance_mask(ctx.pidx, o)
    return np.flatnonzero(pos) + ctx.pos0


def build_targets(
    ctx: Ctx, spec: dict[str, Any], rows: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """(W, RC), each (T_full, 6), filled on the needed rows only."""
    w_all = np.full((len(ctx.dates), len(SLEEVES)), np.nan)
    rc_all = np.full_like(w_all, np.nan)
    for i in rows:
        w = solve_weights(ctx, spec, int(i))
        v = np.zeros(len(SLEEVES))
        for m, x in w.items():
            v[SLEEVES.index(m)] = x
        w_all[i] = v
        rc_all[i] = rc_vector(ctx, w, int(i))
    return w_all, rc_all


def paths_for(ctx: Ctx, w_full: np.ndarray, k: float = 1.0) -> dict[str, Any]:
    """Five offset paths (k scaling; cash below 1, borrowing above 1) from per-row targets."""
    n = len(ctx.pidx)
    wt = np.zeros((n, 8))
    wt[:, :6] = np.nan_to_num(w_full[ctx.pos0 : ctx.pos1]) * k
    wt[:, 6] = max(0.0, 1.0 - k)
    wt[:, 7] = -max(0.0, k - 1.0)
    ret = np.column_stack(
        [ctx.R0[ctx.pos0 : ctx.pos1], ctx.rf[ctx.pos0 : ctx.pos1], np.full(n, DEBIT_D)]
    )
    out = {}
    for o, key in zip(OFFS, OFF_KEYS, strict=True):
        reb = dd30.rebalance_mask(ctx.pidx, o)
        r, h, turn = run_path(wt, ret, reb)
        out[key] = {"ret": pd.Series(r, index=ctx.pidx), "h": h, "turn": turn, "reb": reb}
    out["_wt"] = wt
    return out


def blend(paths: dict[str, Any]) -> pd.Series:
    return pd.concat([paths[k]["ret"] for k in OFF_KEYS], axis=1).mean(axis=1)


def full_stats(paths: dict[str, Any], p0_paths: dict[str, Any] | None, rf: pd.Series) -> dict:
    out: dict[str, Any] = {}
    series = {k: paths[k]["ret"] for k in OFF_KEYS}
    series["blend"] = blend(paths)
    p0s = None
    if p0_paths is not None:
        p0s = {k: p0_paths[k]["ret"] for k in OFF_KEYS}
        p0s["blend"] = blend(p0_paths)
    for key, s in series.items():
        out[key] = {}
        for w in WIN:
            out[key][w] = stat_block(
                win_series(s, w),
                win_series(rf, w),
                None if p0s is None else win_series(p0s[key], w),
            )
    return out


# ------------------------------------------------------------------ deltas


def delta_sr(r: pd.Series, p0: pd.Series, rf: pd.Series, win: str) -> float:
    rr, pp, ff = win_series(r, win), win_series(p0, win), win_series(rf, win)
    x, _ = samevol_x((rr - ff).to_numpy(), (pp - ff).to_numpy(), ff.to_numpy())
    return sharpe(x) - sharpe((pp - ff).to_numpy())


def samevol_pair(
    r: pd.Series, p0: pd.Series, rf: pd.Series, win: str
) -> tuple[pd.Series, pd.Series]:
    """(same-vol excess of R, excess of P0) over `win`, k estimated on the same window."""
    rr, pp, ff = win_series(r, win), win_series(p0, win), win_series(rf, win)
    k = float(np.std((pp - ff).to_numpy(), ddof=1) / np.std((rr - ff).to_numpy(), ddof=1))
    return k * (rr - ff) - max(k - 1.0, 0.0) * (DEBIT_D - ff), pp - ff


def segment_changes(r: pd.Series, p0: pd.Series, rf: pd.Series, segs: dict[str, tuple[str, str]]):
    """Same-vol (full-window k) compounded excess return change vs P0 per segment, in pp."""
    rr, pp, ff = win_series(r, "full"), win_series(p0, "full"), win_series(rf, "full")
    k = float(np.std((pp - ff).to_numpy(), ddof=1) / np.std((rr - ff).to_numpy(), ddof=1))
    xr = k * (rr - ff) - max(k - 1.0, 0.0) * (DEBIT_D - ff)
    xp = pp - ff
    out = {}
    for sid, (a, b) in segs.items():
        out[sid] = float(
            (np.prod(1.0 + xr.loc[a:b].to_numpy()) - np.prod(1.0 + xp.loc[a:b].to_numpy())) * 100.0
        )
    return out


def samevol_sr_matrix(ex: np.ndarray, ex_p: np.ndarray, rf: np.ndarray) -> np.ndarray:
    """Same-vol Sharpe for each column of ex (n, P) vs P0 excess ex_p (n,)."""
    k = np.std(ex_p, ddof=1) / np.std(ex, axis=0, ddof=1)
    x = k[None, :] * ex - np.maximum(k - 1.0, 0.0)[None, :] * (DEBIT_D - rf)[:, None]
    return x.mean(axis=0) / x.std(axis=0, ddof=1) * math.sqrt(TRADING_DAYS)


def placebo_deltas(
    ctx: Ctx, members: list[str], p0_blend: pd.Series, n: int, rng: np.random.Generator
) -> np.ndarray:
    idx = [SLEEVES.index(m) for m in members]
    wd = rng.dirichlet(np.ones(len(members)), size=n)
    w = np.zeros((n, len(SLEEVES)))
    w[:, idx] = wd
    ret = ctx.R0[ctx.pos0 : ctx.pos1]
    acc = np.zeros((len(ctx.pidx), n))
    for o in OFFS:
        acc += run_static_multi(w, ret, dd30.rebalance_mask(ctx.pidx, o))
    acc /= len(OFFS)
    a, b = WIN["recent"]
    sel = (ctx.pidx >= pd.Timestamp(a)) & (ctx.pidx <= pd.Timestamp(b))
    rf = ctx.rf_p.to_numpy()[sel]
    ex_p = (p0_blend.to_numpy() - ctx.rf_p.to_numpy())[sel]
    sr = samevol_sr_matrix(acc[sel] - rf[:, None], ex_p, rf)
    return sr - sharpe(ex_p)


# ------------------------------------------------------------------ bootstrap, DD sim


def stationary_bootstrap_indices(
    n: int, horizon: int, n_paths: int, mean_block: float, rng: np.random.Generator
) -> np.ndarray:
    new = rng.random((n_paths, horizon)) < 1.0 / mean_block
    starts = rng.integers(0, n, size=(n_paths, horizon))
    idx = np.empty((n_paths, horizon), dtype=np.int64)
    idx[:, 0] = starts[:, 0]
    for t in range(1, horizon):
        idx[:, t] = np.where(new[:, t], starts[:, t], (idx[:, t - 1] + 1) % n)
    return idx


def scenario_base(ex: np.ndarray, mu: float, rf_bar: float) -> np.ndarray:
    """Demeaned excess plus the scenario mean plus the BIL mean (mean is exactly mu + rf_bar)."""
    return ex - ex.mean() + mu + rf_bar


def dd_quantiles(samples: np.ndarray) -> dict[str, float]:
    nav = np.cumprod(1.0 + samples, axis=1)
    peak = np.maximum(np.maximum.accumulate(nav, axis=1), 1.0)
    dd = (nav / peak - 1.0).min(axis=1)
    q = np.quantile(-dd, [0.50, 0.90, 0.95, 0.99])
    return {
        "q50": float(-q[0]),
        "q90": float(-q[1]),
        "q95": float(-q[2]),
        "q99": float(-q[3]),
        "p_dd_gt_30": float(np.mean(dd < DD_LIMIT)),
    }


# ------------------------------------------------------------------ decisions


def monotone(vals: list[float]) -> bool:
    d = np.diff(vals)
    return bool(np.all(d >= 0) or np.all(d <= 0))


def complexity(rule_id: str) -> tuple[int, int]:
    kind = 0 if "_IV_" in rule_id else 1 if "_ERC_" in rule_id else 2
    return kind, 1 if rule_id.endswith("_E6") else 0


def decide(deltas: dict[str, dict], candidates: list[str]) -> dict[str, Any]:
    """Mechanical D1/D2 status for one tier group from `deltas` (contract section 4)."""
    d1_flags, d1 = {}, []
    for r in candidates:
        d = deltas[r]
        c1 = d["blend_recent"] >= 0.10 and d["blend_stress"] >= 0.10
        c2 = d["median_recent"] >= 0.10 and d["median_stress"] >= 0.10
        c3 = d["offsets_positive_recent"] >= 4
        pq = d["placebo_quantile_recent"]
        c4 = pq is not None and pq >= 0.80
        c5 = d["cost2x_delta_recent"] >= 0.0
        d1_flags[r] = {
            "c1_blend": c1,
            "c2_median": c2,
            "c3_offsets": c3,
            "c4_placebo": c4,
            "c5_2x": c5,
        }
        if c1 and c2 and c3 and c4 and c5:
            d1.append(r)
    out: dict[str, Any] = {"d1_flags": d1_flags, "d1_passers": d1}
    d2_flags, adm = {}, []
    for r in candidates:
        if not r.startswith("T58_CAP2_"):
            continue
        d = deltas[r]
        a = d["blend_recent"] >= -0.10
        b = d["blend_stress"] >= -0.05
        c_seg = d["six_segment_mean_change_pp"] >= 1.0
        c_es = d["es975_stress_change"] < 0.0
        d2_flags[r] = {"a": a, "b": b, "c_segments": c_seg, "c_es": c_es}
        if a and b and (c_seg or c_es):
            adm.append(float(r[-4:]))
    out["d2_flags"] = d2_flags
    out["d2_admissible_levels"] = sorted(adm)
    if d1:
        best = max(deltas[r]["blend_recent"] for r in d1)
        near = [r for r in d1 if deltas[r]["blend_recent"] >= best - 0.01]
        pick = sorted(near, key=lambda r: (complexity(r), -deltas[r]["blend_recent"]))[0]
        out["status"] = f"d1_replace:{pick}"
        out["reason"] = (
            f"D1 passers {d1}; best within 0.01 of top blend dSR recent -> simplest {pick}"
        )
    elif adm:
        out["status"] = f"d2_cap:{min(adm):.2f}"
        out["reason"] = (
            f"no D1 passer; admissible CAP2 levels {sorted(adm)}; tightest {min(adm):.2f}"
        )
    else:
        out["status"] = "keep_p0"
        out["reason"] = "no D1 passer and no admissible CAP2 level"
    return out


# ------------------------------------------------------------------ deployables


def apply_mincap(
    ctx: Ctx, spec: dict[str, Any], w_row: np.ndarray, i: int, k: float, a: float
) -> tuple[np.ndarray, bool]:
    """Drop sleeves with 0 < k w A < m_i and re-solve on the rest (iterate until stable)."""
    members = [SLEEVES[j] for j in range(6) if w_row[j] > 0]
    dropped = False
    cur = w_row.copy()
    for _ in range(6):
        bad = [
            SLEEVES[j]
            for j in range(6)
            if cur[j] > 0.0 and k * cur[j] * a < MIN_CAP[SLEEVES[j]] - 1e-9
        ]
        if not bad:
            break
        dropped = True
        members = [m for m in members if m not in bad]
        cur = np.zeros(6)
        if not members:
            break
        for m, x in solve_weights(ctx, spec, i, members).items():
            cur[SLEEVES.index(m)] = x
    return cur, dropped


def margin_headroom(
    ctx: Ctx, h: np.ndarray, wt: np.ndarray, reb: np.ndarray
) -> tuple[float, float]:
    """Min headroom: maintenance (0.9 - sum m|pos|) every session; initial (1.0 - ...) on rebalances."""
    g = np.ones((len(h), 6))
    g[:, 4:6] = np.nan_to_num(ctx.G[ctx.pos0 : ctx.pos1])
    mm = np.array([M_MAINT[s] for s in SLEEVES])
    mi = np.array([M_INIT[s] for s in SLEEVES])
    maint = (np.abs(h[:, :6]) * g * mm).sum(axis=1)
    init = (np.abs(wt[:, :6]) * g * mi).sum(axis=1)
    return float(np.min(MAINT_LIMIT - maint)), float(np.min(INIT_LIMIT - init[reb]))


def deployable_k(
    ctx: Ctx, rule_id: str, a: float, w_base: np.ndarray, rows: np.ndarray, k: float
) -> dict[str, Any]:
    spec = rule_spec(rule_id)
    w = np.full_like(w_base, np.nan)
    dropped_rows = 0
    feasible = True
    for i in rows:
        row, dropped = apply_mincap(ctx, spec, w_base[i], int(i), k, a)
        dropped_rows += int(dropped)
        if row.sum() <= 0:
            feasible = False
        w[i] = row
    paths = paths_for(ctx, w, k)
    bl = blend(paths)
    wt = paths["_wt"]
    heads = [margin_headroom(ctx, paths[key]["h"], wt, paths[key]["reb"]) for key in OFF_KEYS]
    return {
        "paths": paths,
        "blend": bl,
        "maxdd_full": maxdd(win_series(bl, "full").to_numpy()),
        "min_head_maint": min(h[0] for h in heads),
        "min_head_init": min(h[1] for h in heads),
        "dropped_share": dropped_rows / max(1, len(rows)),
        "feasible": feasible,
        "wt_sleeve": wt[:, :6],
    }


def choose_k(
    ctx: Ctx, rule_id: str, a: float, account: str, w_base: np.ndarray, rows: np.ndarray
) -> tuple[dict, float, bool, list[dict]]:
    grid = [k for k in K_GRID if (account == "margin" or k <= 1.0 + 1e-9)]
    table, results = [], {}
    for k in grid:
        res = deployable_k(ctx, rule_id, a, w_base, rows, k)
        results[k] = res
        acct_ok = (
            (res["min_head_maint"] >= 0.0 and res["min_head_init"] >= 0.0)
            if account == "margin"
            else True
        )
        table.append(
            {
                "k": k,
                "maxdd_full": res["maxdd_full"],
                "dd_ok": res["maxdd_full"] >= DD_LIMIT,
                "account_ok": acct_ok,
                "mincap_ok": res["feasible"],
                "min_head_maint": res["min_head_maint"],
                "min_head_init": res["min_head_init"],
            }
        )
    ok_all = [t["k"] for t in table if t["dd_ok"] and t["account_ok"] and t["mincap_ok"]]
    if ok_all:
        k_star, unmet = max(ok_all), False
    else:
        ok2 = [t["k"] for t in table if t["account_ok"] and t["mincap_ok"]]
        k_star, unmet = (max(ok2) if ok2 else grid[0]), True
    return results[k_star], k_star, unmet, table


def sleeve_haircuts(ctx: Ctx, t31: dict, f_mode: str) -> dict[str, float]:
    """h_i = max(0, SR_i - SR0_i)/SR_i (ETF: T-31 n_eff and var_sr); F1/F2: T-71 factors."""
    from open_composer.research import scorecard_v2 as sc

    out = {}
    a, b = WIN["recent"]
    sel = (ctx.pidx >= pd.Timestamp(a)) & (ctx.pidx <= pd.Timestamp(b))
    f = json.loads(T71_PATH.read_text())["dsr_inputs"]
    for j, s in enumerate(SLEEVES):
        if s in ("F1", "F2"):
            out[s] = f["haircut_factor_program"] if f_mode == "main" else f["haircut_factor_family"]
            continue
        ex = (ctx.R0[ctx.pos0 : ctx.pos1, j] - ctx.rf_p.to_numpy())[sel]
        sr = sharpe(ex)
        sr0 = sc.expected_max_null(t31[s]["var_sr_annual"], t31[s]["n_eff"])
        out[s] = max(0.0, sr - sr0) / sr if sr > 0 else 0.0
    return out


def deployable_report(
    ctx: Ctx,
    rule_id: str,
    tier: str,
    account: str,
    t31: dict,
    boot_idx: dict[int, np.ndarray],
    segs: dict[str, tuple[str, str]],
) -> dict[str, Any]:
    spec = rule_spec(rule_id)
    a = TIERS[tier]
    rows = rebal_positions(ctx, OFFS)
    w_base, _ = build_targets(ctx, spec, rows)
    res, k, unmet, table = choose_k(ctx, rule_id, a, account, w_base, rows)
    bl, rf = res["blend"], ctx.rf_p
    members = spec["members"]
    rec = win_series(bl, "recent")
    exr = (rec - win_series(rf, "recent")).to_numpy()
    exs = (win_series(bl, "stress") - win_series(rf, "stress")).to_numpy()
    cal = {
        str(y): float(np.prod(1.0 + bl[bl.index.year == y].to_numpy()) - 1.0)
        for y in (2018, 2020, 2022)
    }
    seg_ret = {
        sid: float(np.prod(1.0 + bl.loc[aa:bb].to_numpy()) - 1.0) for sid, (aa, bb) in segs.items()
    }
    full = win_series(bl, "full")
    months = (1.0 + full).resample("ME").prod() - 1.0
    last_w = {}
    for key in OFF_KEYS:
        pos = np.flatnonzero(res["paths"][key]["reb"] & (ctx.pidx <= pd.Timestamp(END)))[-1]
        wrow = res["wt_sleeve"][pos]
        last_w[key] = {
            "date": str(ctx.pidx[pos].date()),
            "weights": {s: float(wrow[j]) for j, s in enumerate(SLEEVES) if wrow[j] > 0},
            "cash": float(max(0.0, 1.0 - k)),
            "borrow": float(max(0.0, k - 1.0)),
            "gross": float(wrow.sum()),
        }
    mean_w = {
        s: float(np.mean([last_w[key]["weights"].get(s, 0.0) for key in OFF_KEYS]))
        for s in SLEEVES
        if any(s in last_w[key]["weights"] for key in OFF_KEYS)
    }
    rs_rows = [
        int(i)
        for i in rows
        if pd.Timestamp(WIN["recent"][0]) <= ctx.dates[i] <= pd.Timestamp(WIN["recent"][1])
    ]
    shares = []
    for i in rs_rows:
        wv = {SLEEVES[j]: float(res["wt_sleeve"][i - ctx.pos0, j]) for j in range(6)}
        shares.append(rc_vector(ctx, {m: x for m, x in wv.items() if x > 0}, i))
    risk_share = {
        s: float(np.mean([r[j] for r in shares])) for j, s in enumerate(SLEEVES) if s in members
    }
    hc = sleeve_haircuts(ctx, t31, "main")
    hc_alt = sleeve_haircuts(ctx, t31, "alt")
    a_sel = (ctx.pidx >= pd.Timestamp(WIN["recent"][0])) & (
        ctx.pidx <= pd.Timestamp(WIN["recent"][1])
    )
    h_bar = np.mean([res["paths"][key]["h"][a_sel][:, :6].mean(axis=0) for key in OFF_KEYS], axis=0)
    mu_sleeve = (ctx.R0[ctx.pos0 : ctx.pos1] - ctx.rf_p.to_numpy()[:, None])[a_sel].mean(axis=0)
    pen = max(k - 1.0, 0.0) * float(np.mean(DEBIT_D - ctx.rf_p.to_numpy()[a_sel]))

    def mu_a(hcx: dict[str, float]) -> float:
        return float(
            sum(h_bar[j] * hcx.get(s, 0.0) * mu_sleeve[j] for j, s in enumerate(SLEEVES)) - pen
        )

    ex_full = (full - win_series(rf, "full")).to_numpy()
    rf_bar = float(win_series(rf, "recent").mean())
    mus = {"A": mu_a(hc), "B": float(exs.mean()), "C": 0.0}
    if any(s in ("F1", "F2") for s in mean_w):
        mus["A_alt"] = mu_a(hc_alt)
    dd = {
        name: {
            str(hz): dd_quantiles(scenario_base(ex_full, mu, rf_bar)[boot_idx[hz]])
            for hz in HORIZONS
        }
        for name, mu in mus.items()
    }
    l1 = all(t31[s]["passes_p1_dsr"] for s in members if s in ETF)
    return {
        "rule": rule_id,
        "members": members,
        "l1_eligible": bool(l1),
        "k_star": k,
        "dd_budget_unmet": bool(unmet),
        "gross": float(np.mean([last_w[key]["gross"] for key in OFF_KEYS])),
        "weights_last": mean_w,
        "weights_last_by_offset": last_w,
        "recent": {
            "cagr": float(np.prod(1.0 + rec.to_numpy()) ** (TRADING_DAYS / len(rec)) - 1.0),
            "vol": float(rec.std(ddof=1) * math.sqrt(TRADING_DAYS)),
            "sr": sharpe(exr),
            "maxdd": maxdd(rec.to_numpy()),
        },
        "stress": {"sr": sharpe(exs), "maxdd": maxdd(win_series(bl, "stress").to_numpy())},
        "full_maxdd": res["maxdd_full"],
        "worst_month": float(months.min()),
        "cal": cal,
        "segments": seg_ret,
        "risk_share_recent": risk_share,
        "margin_min_headroom": (
            {"maint": res["min_head_maint"], "init": res["min_head_init"]}
            if account == "margin"
            else None
        ),
        "months_with_dropped_sleeve_share": res["dropped_share"],
        "k_grid": table,
        "mu_daily": mus,
        "haircuts": {"main": hc, "alt": hc_alt},
        "dd_sim": dd,
    }


# ------------------------------------------------------------------ stages


def load_t31() -> dict[str, dict]:
    r = json.loads(T31_PATH.read_text())
    return {x["sleeve"]: x for x in r["results"]}


def t32_selection() -> dict[str, Any]:
    r = json.loads((T32 / "results.json").read_text())

    def cfg(pl):
        if not pl:
            return "ORIG", "ORIG"
        lvl = int(round(pl["c"] * 100))
        return f"{pl['version']}_{lvl}", f"CAP_{lvl}"

    c_p0, s12_p0 = cfg(r.get("pilot_limit"))
    c_s3, _ = cfg(r.get("pilot_limit_s3"))
    return {
        "pilot_limit": r.get("pilot_limit"),
        "pilot_limit_s3": r.get("pilot_limit_s3"),
        "cfg_p0": c_p0,
        "cfg_s12": s12_p0,
        "cfg_s3_l1": c_s3,
    }


def load_series_cols(selection: dict) -> tuple[pd.DataFrame, dict[str, str]]:
    ser = pd.read_parquet(T32 / "cache/series.parquet")
    ser.index = pd.to_datetime(ser.index)
    cols = {
        "sel__S3": f"S3__{selection['cfg_p0']}__r10",
        "sel__C2": f"C2__{selection['cfg_p0']}__r10",
        "sel__S1": f"S1__{selection['cfg_s12']}__r10",
        "sel__S2": f"S2__{selection['cfg_s12']}__r10",
        "L1__S3": f"S3__{selection['cfg_s3_l1']}__r10",
        "orig__S3": "S3__ORIG__r10",
        "orig__C2": "C2__ORIG__r10",
        "x2b__S3": "S3__ORIG__r20",
        "x2b__C2": "C2__ORIG__r20",
        "x2b__S1": "S1__ORIG__r20",
        "x2b__S2": "S2__ORIG__r20",
        "cacheS1": "S1__ORIG__r10",
        "cacheS2": "S2__ORIG__r10",
    }
    return pd.DataFrame({k: ser[v] for k, v in cols.items()}), cols


def stage_build() -> int:
    t0 = time.time()
    import run_h20260918_05_recent_menu as base
    import run_h20260927_01_sleeve_combination as comb

    sel = t32_selection()
    base.WARMUP_START = comb.PANEL_START
    close, open_ = base.load_panel(comb.salvage.symbols())
    leg_open, leg_close = comb.salvage.legs(close, open_)
    r10 = comb.sleeve_returns(close, leg_open, leg_close, base.COST_BPS_PRIMARY)
    r20 = comb.sleeve_returns(close, leg_open, leg_close, base.COST_BPS_STRESS)
    cash = (close[base.RF] / close[base.RF].shift(1) - 1.0).fillna(0.0)
    cash.index = pd.to_datetime(cash.index)
    cols_df, cols_map = load_series_cols(sel)
    rep = pd.read_parquet(C2_REPAIRED)
    rep.index = pd.to_datetime(rep.index)
    c2_10, c2_20 = rep["C2__o00__net10"], rep["C2__o00__net20"]

    def al(s: pd.Series) -> pd.Series:
        s = s.copy()
        s.index = pd.to_datetime(s.index)
        return s.reindex(cash.index)

    panel = pd.DataFrame(
        {
            "orig__S1": al(r10["s1"]),
            "orig__S2": al(r10["s2"]),
            "x2__S1": al(r20["s1"]),
            "x2__S2": al(r20["s2"]),
            "x2__S3": al(r20["s3"]),
            "x2__C2": al(c2_20),
            "CASH": cash,
        },
        index=cash.index,
    )
    for c in cols_df.columns:
        panel[c] = cols_df[c].reindex(panel.index)
    for f in ("F1", "F2"):
        d = pd.read_parquet(ROOT / f"data/research/book_v12/A1_M0_U3000_{f}.parquet")
        panel[f] = al(dd30.realization_dated(d["net_pnl"] / 1e6))
        panel[f"G_{f}"] = al(dd30.realization_dated(d["gross"] / 1e6))
    panel = panel.loc[: pd.Timestamp(END)]
    start, end = WIN["full"]
    in_win = (panel.index >= pd.Timestamp(start)) & (panel.index <= pd.Timestamp(end))
    need = [c for c in panel.columns if not c.startswith("G_")]
    etf_cols = [c for c in need if c not in ("F1", "F2")]
    na_by_col = panel.loc[in_win, need].isna().sum()
    drop_in = in_win & panel[need].isna().any(axis=1).to_numpy()
    drop_pre = (~in_win) & panel[etf_cols].isna().any(axis=1).to_numpy()
    panel = panel.loc[~(drop_in | drop_pre)].copy()
    panel[["G_F1", "G_F2"]] = panel[["G_F1", "G_F2"]].ffill()
    CACHE.mkdir(parents=True, exist_ok=True)
    panel.to_parquet(CACHE / "panel.parquet")

    ident: dict[str, Any] = {}
    del close, open_, leg_open, leg_close
    frame, _ = dd30.load_engines("net10")
    t43 = json.loads((T43_DIR / "results.json").read_text())["decision"]["weights"]
    w = np.array([t43[e] for e in dd30.ENGINES] + [-t43["BORROW"]], dtype=float)
    n = len(frame)
    ret = np.column_stack([frame.to_numpy(), np.full(n, dd30.DEBIT_RATE / 252.0)])
    mine, _, _ = run_path(np.tile(w, (n, 1)), ret, dd30.rebalance_mask(frame.index, 0))
    stored = pd.read_parquet(T43_DIR / "program_returns.parquet")["program_ret"]
    diff1 = float(np.max(np.abs(mine - stored.to_numpy())))
    ident["I1_max_abs_diff"] = diff1
    ident["I1_rows"] = int(n)
    ident["I1_pass"] = bool(diff1 <= 1e-12 and n == len(stored))
    ov = panel.index.intersection(c2_10.index)
    diff2 = float(
        np.max(np.abs(panel.loc[ov, "orig__C2"].to_numpy() - c2_10.reindex(ov).to_numpy()))
    )
    ident["I2_max_abs_diff"] = diff2
    ident["I2_overlap_rows"] = int(len(ov))
    ident["I2_pass"] = bool(diff2 <= 1e-10)
    ident["I3"] = "n/a (T-32 cache holds only the 5-offset S3 blend, no offset-0 series)"
    ident["I3_pass"] = None
    ident["info_cache_S1_vs_sleeve_returns_max_abs_diff"] = float(
        np.nanmax(np.abs(panel["cacheS1"].to_numpy() - panel["orig__S1"].to_numpy()))
    )
    ident["info_cache_S2_vs_sleeve_returns_max_abs_diff"] = float(
        np.nanmax(np.abs(panel["cacheS2"].to_numpy() - panel["orig__S2"].to_numpy()))
    )
    ident["pass"] = bool(ident["I1_pass"] and ident["I2_pass"])
    build = {
        "built_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "identity": ident,
        "t32_selection": sel,
        "t32_columns": cols_map,
        "t32_series_sha256": sha256(T32 / "cache/series.parquet"),
        "t32_results_sha256": sha256(T32 / "results.json"),
        "t31_results_sha256": sha256(T31_PATH),
        "t31_pending": False,
        "c2_repaired_sha256": sha256(C2_REPAIRED),
        "panel_rows": int(len(panel)),
        "panel_first": str(panel.index[0].date()),
        "panel_last": str(panel.index[-1].date()),
        "window_rows_dropped_for_na": int(drop_in.sum()),
        "pre_window_rows_dropped_for_na": int(drop_pre.sum()),
        "na_in_window_by_col": {k: int(v) for k, v in na_by_col.items() if v},
        "panel_columns": list(panel.columns),
        "runtime_s": round(time.time() - t0, 1),
        "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "code_sha256": sha256(Path(__file__)),
    }
    (D / "build.json").write_text(json.dumps(build, indent=1) + "\n", encoding="utf-8")
    print(json.dumps({"identity": ident}, indent=1))
    return 0 if ident["pass"] else 2


def segments_from_t75() -> dict[str, tuple[str, str]]:
    segs = json.loads(T75_PATH.read_text())["conventions"]["stress_segments"]
    return {s["id"]: (s["first_return_day"], s["last_return_day"]) for s in segs}


def rules_for_set(ctx: Ctx, rule_ids: list[str]) -> dict[str, Any]:
    """Paths, ex-ante shares and targets for P0 plus the rules on one context."""
    rows = rebal_positions(ctx, OFFS)
    out = {}
    for rid in ["P0"] + list(rule_ids):
        w, rc = build_targets(ctx, rule_spec(rid), rows)
        out[rid] = {"paths": paths_for(ctx, w), "w": w, "rc": rc}
    return out


def share_stats(ctx: Ctx, rc: np.ndarray, paths: dict) -> dict[str, Any]:
    out: dict[str, Any] = {"risk_share_mean": {}, "s3_share_gt_0p6": {}}
    valid = np.flatnonzero(~np.isnan(rc[:, 0]))
    for win in ("recent", "stress"):
        a, b = WIN[win]
        rows = [i for i in valid if pd.Timestamp(a) <= ctx.dates[i] <= pd.Timestamp(b)]
        m = rc[rows].mean(axis=0) if rows else np.full(6, np.nan)
        out["risk_share_mean"][win] = {s: float(m[j]) for j, s in enumerate(SLEEVES) if m[j] > 0}
        out["s3_share_gt_0p6"][win] = float(np.mean(rc[rows, 2] > 0.6)) if rows else None
    years = len(ctx.pidx) / TRADING_DAYS
    tu = float(np.mean([paths[k]["turn"].sum() for k in OFF_KEYS]) / years)
    out["turnover_per_yr"] = tu
    out["rebal_cost_bp_yr"] = tu * REBAL_COST * 1e4
    return out


def max_cap2_s3_share(ctx: Ctx, rr: dict[str, Any]) -> dict[str, float]:
    """Max ex-ante S3 risk share on all rebalance dates per CAP2 rule (acceptance 4)."""
    out = {}
    for c in CAP_LEVELS:
        rid = f"T58_CAP2_{c:.2f}"
        out[rid] = float(np.nanmax(rr[rid]["rc"][:, 2]))
    return out


def stage_run() -> int:
    from open_composer.research import scorecard_v2 as sc

    t0 = time.time()
    build = json.loads((D / "build.json").read_text())
    if not build.get("identity", {}).get("pass"):
        print("refusing to run: build.json identity.pass is not true")
        return 2
    panel = pd.read_parquet(CACHE / "panel.parquet")
    t31 = load_t31()
    segs = segments_from_t75()
    sets = {
        "selected": Ctx(panel, "sel"),
        "orig": Ctx(panel, "orig"),
        "x2": Ctx(panel, "x2"),
        "x2b": Ctx(panel, "x2b"),
    }
    ctx_l1 = Ctx(panel, "sel", "L1__S3")
    rf = sets["selected"].rf_p
    res_sets = {}
    for name, ctx in sets.items():
        res_sets[name] = rules_for_set(ctx, RULES)
        print(name, "paths done", round(time.time() - t0, 1), flush=True)
    rules_json: dict[str, Any] = {}
    p0_json: dict[str, Any] = {}
    for name in ("selected", "orig"):
        ctx, rr = sets[name], res_sets[name]
        p0p = rr["P0"]["paths"]
        p0_json[name] = {**full_stats(p0p, None, rf), **share_stats(ctx, rr["P0"]["rc"], p0p)}
        rules_json[name] = {}
        for r in RULES:
            rp = rr[r]["paths"]
            rules_json[name][r] = {
                **full_stats(rp, p0p, rf),
                **share_stats(ctx, rr[r]["rc"], rp),
            }
    max_share = {n: max_cap2_s3_share(sets[n], res_sets[n]) for n in ("selected", "orig")}
    placebo = {}
    for name in ("selected", "orig"):
        rng = np.random.default_rng(SEED)
        p0b = blend(res_sets[name]["P0"]["paths"])
        placebo[name] = {
            "E4": placebo_deltas(sets[name], E4, p0b, N_PLACEBO, rng),
            "E6": placebo_deltas(sets[name], E6, p0b, N_PLACEBO, rng),
            "E2": placebo_deltas(sets[name], ["S3", "C2"], p0b, N_PLACEBO, rng),
        }
    print("placebos done", round(time.time() - t0, 1), flush=True)
    deltas: dict[str, Any] = {}
    for name in ("selected", "orig"):
        rr = res_sets[name]
        p0p = rr["P0"]["paths"]
        p0b = blend(p0p)
        deltas[name] = {}
        for r in RULES:
            rp = rr[r]["paths"]
            bl = blend(rp)
            dr = {k: delta_sr(rp[k]["ret"], p0p[k]["ret"], rf, "recent") for k in OFF_KEYS}
            ds = {k: delta_sr(rp[k]["ret"], p0p[k]["ret"], rf, "stress") for k in OFF_KEYS}
            seg = segment_changes(bl, p0b, rf, segs)
            fam = "E2" if "CAP2" in r else "E4" if r.endswith("E4") else "E6"
            blr = delta_sr(bl, p0b, rf, "recent")
            xr, xp = samevol_pair(bl, p0b, rf, "stress")
            deltas[name][r] = {
                "blend_recent": blr,
                "blend_stress": delta_sr(bl, p0b, rf, "stress"),
                "median_recent": float(np.median(list(dr.values()))),
                "median_stress": float(np.median(list(ds.values()))),
                "offsets_positive_recent": int(sum(v > 0 for v in dr.values())),
                "per_offset_recent": dr,
                "per_offset_stress": ds,
                "placebo_family": fam,
                "placebo_quantile_recent": sc.placebo_percentile(blr, placebo[name][fam]),
                "six_segments": seg,
                "six_segment_mean_change_pp": float(np.mean(list(seg.values()))),
                "es975_stress_change": es975(xr.to_numpy()) - es975(xp.to_numpy()),
            }
            for tag, setn in (
                ("cost2x_delta_recent", "x2"),
                ("cost2x_delta_recent_cacheblend", "x2b"),
            ):
                r2 = res_sets[setn]
                deltas[name][r][tag] = delta_sr(
                    blend(r2[r]["paths"]), blend(r2["P0"]["paths"]), rf, "recent"
                )
        seq_r = [deltas[name][f"T58_CAP2_{c:.2f}"]["blend_recent"] for c in CAP_LEVELS]
        seq_s = [deltas[name][f"T58_CAP2_{c:.2f}"]["blend_stress"] for c in CAP_LEVELS]
        flag = {
            "recent": monotone(seq_r),
            "stress": monotone(seq_s),
            "seq_recent_c_0.80_to_0.50": seq_r,
            "seq_stress_c_0.80_to_0.50": seq_s,
        }
        for c in CAP_LEVELS:
            deltas[name][f"T58_CAP2_{c:.2f}"]["monotone_flag"] = flag
    decision = {
        "small": decide(deltas["selected"], SMALL_RULES),
        "1M": decide(deltas["selected"], RULES),
    }
    alt = {}
    for g, cands in (("small", SMALL_RULES), ("1M", RULES)):
        d_alt = {r: dict(deltas["selected"][r]) for r in cands}
        for r in cands:
            d_alt[r]["cost2x_delta_recent"] = deltas["selected"][r][
                "cost2x_delta_recent_cacheblend"
            ]
        alt[g] = decide(d_alt, cands)["status"]
    decision["cost2x_alternate_status"] = alt
    print("deltas done", round(time.time() - t0, 1), flush=True)

    sr8 = [rules_json["selected"][r]["blend"]["recent"]["sr_samevol"] for r in RULES]
    mat = pd.concat(
        [
            win_series(blend(res_sets["selected"][r]["paths"]), "recent") - win_series(rf, "recent")
            for r in RULES
        ],
        axis=1,
    ).corr()
    mean_corr = float((mat.to_numpy().sum() - 8) / 56)
    n_eff = sc.n_eff_from_corr(8, mean_corr)
    var_sr = float(np.var(sr8, ddof=1))

    def rule_of(status: str) -> str:
        if status.startswith("d1_replace"):
            return status.split(":")[1]
        if status.startswith("d2_cap"):
            return f"T58_CAP2_{status.split(':')[1]}"
        return "P0"

    dsr_sel = {}
    for g in ("small", "1M"):
        rid = rule_of(decision[g]["status"])
        s = blend(res_sets["selected"][rid]["paths"])
        ex = (win_series(s, "recent") - win_series(rf, "recent")).to_numpy()
        dsr_sel[g] = {
            "rule": rid,
            **sc.dsr(ex, var_sr_annual=var_sr, n_eff=n_eff),
            "n": 8,
            "n_eff": n_eff,
            "var_sr_annual": var_sr,
            "mean_pairwise_corr": mean_corr,
            "basis": "unlevered 5-offset blend, recent window, excess over BIL",
        }
    rng = np.random.default_rng(SEED)
    n_full = len(win_series(rf, "full"))
    boot_idx = {
        hz: stationary_bootstrap_indices(n_full, hz, N_BOOT, MEAN_BLOCK, rng) for hz in HORIZONS
    }
    chosen = {}
    for g, tiers in (("small", ["50k", "100k", "250k"]), ("1M", ["1M"])):
        for t in tiers:
            chosen[t] = rule_of(decision[g]["status"])
    deployables: dict[str, Any] = {}
    for t in TIERS:
        deployables[t] = {}
        for acct in ("cash", "margin"):
            entry = deployable_report(sets["selected"], chosen[t], t, acct, t31, boot_idx, segs)
            entry["p0_same_account"] = deployable_report(
                sets["selected"], "P0", t, acct, t31, boot_idx, segs
            )
            p0s3 = deployable_report(ctx_l1, "P0_S3", t, acct, t31, boot_idx, segs)
            p0s3["l1_eligible"] = bool(t31["S3"]["passes_p1_dsr"])
            p0s3["dsr_input"] = {
                "dsr_recent_t31_S3": t31["S3"]["dsr_recent"],
                "source": str(T31_PATH.relative_to(ROOT)),
                "t32_family_trial_rows": len(json.loads((T32 / "trial-ledger.json").read_text())),
                "s3_series": build["t32_columns"]["L1__S3"],
            }
            entry["p0_s3"] = p0s3
            deployables[t][acct] = entry
            print("deployable", t, acct, round(time.time() - t0, 1), flush=True)
    dd_sim = {t: {a: deployables[t][a]["dd_sim"] for a in deployables[t]} for t in deployables}
    results = {
        "meta": {
            "last_session": END,
            "t32_selection": build["t32_selection"],
            "inputs": {
                "t32_series_sha256": build["t32_series_sha256"],
                "t32_results_sha256": build["t32_results_sha256"],
                "t31_results_sha256": build["t31_results_sha256"],
                "t32_columns": build["t32_columns"],
            },
            "t31_pending": False,
            "runtime_s": round(time.time() - t0, 1),
            "peak_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "code_sha256": sha256(Path(__file__)),
            "dd_quantile_convention": "q = quantile of drawdown depth, reported as a negative number",
            "k_star_rule": (
                "largest k on the 0.50..2.00 grid (cash <= 1.00) with full-window 5-offset blend "
                "max DD >= -30%, the account constraint, and at least one sleeve left after the "
                "minimum-capital drop; if no k meets all three, the largest k meeting the last two "
                "and dd_budget_unmet = true"
            ),
            "chosen_rule_by_tier": chosen,
            "cap2_max_ex_ante_s3_share": max_share,
            "weights_note": "weights_last = mean over the five offsets of target weights at the last rebalance <= 2026-09-15",
        },
        "identity": build["identity"],
        "rules": rules_json,
        "p0": p0_json,
        "deltas": deltas,
        "placebo": {
            n: {
                f: {"n": len(v), "median": float(np.median(v)), "p80": float(np.quantile(v, 0.8))}
                for f, v in d.items()
            }
            for n, d in placebo.items()
        },
        "decision": decision,
        "deployables": deployables,
        "dd_sim": dd_sim,
        "dsr_selected": dsr_sel,
    }
    (D / "results.json").write_text(
        json.dumps(results, indent=1, default=float) + "\n", encoding="utf-8"
    )
    print("run done", round(time.time() - t0, 1), flush=True)
    return 0


# ------------------------------------------------------------------ report


def fmt(x: Any, nd: int = 3) -> str:
    return "n/a" if x is None else f"{x:.{nd}f}"


def _entries(e: dict) -> list[tuple[str, dict]]:
    return [("选中:" + e["rule"], e), ("P0", e["p0_same_account"]), ("P0-S3", e["p0_s3"])]


def stage_report() -> int:
    res = json.loads((D / "results.json").read_text())
    dec = res["decision"]
    L: list[str] = ["# 配置第二版 (P4) 结果报告 T-20261004-58", ""]
    L.append(
        "机械结果，不含保留或否定的结论。规则、窗口、门槛来自合同 t20261005_p4_alloc_v2 与修正案 A2。"
    )
    L += ["", "## 第一页：l1_eligible 的可部署版本（含 P0-S3）", ""]
    L.append(
        "| 档位 | 账户 | 版本 | k* | 权重（五偏移均值） | 近期夏普 | 全期最大回撤 | 减半线 252d | 停止线 252d | 减半线 126d | 停止线 126d |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for t, d in res["deployables"].items():
        for acct, e in d.items():
            for name, x in _entries(e):
                if not x["l1_eligible"]:
                    continue
                w = ", ".join(f"{s} {v:.3f}" for s, v in x["weights_last"].items())
                a2, a1 = x["dd_sim"]["A"]["252"], x["dd_sim"]["A"]["126"]
                L.append(
                    f"| {t} | {acct} | {name} | {x['k_star']:.2f} | {w} | {fmt(x['recent']['sr'])} | {fmt(x['full_maxdd'])} | {fmt(a2['q95'])} | {fmt(a2['q99'])} | {fmt(a1['q95'])} | {fmt(a1['q99'])} |"
                )
    L.append("")
    L.append("减半线 = 情景 A 的 95% 分位，停止线 = 情景 A 的 99% 分位（最大回撤深度，负数）。")
    L.append(
        "`l1_eligible = false` 的版本（含 S1 或 C2）只用于模拟盘组合，不进 L1 试点（T-31 `passes_p1_dsr`：S1 false、C2 false）。"
    )
    L += ["", "## 判定状态（代码按 deltas 写出）", ""]
    for g in ("small", "1M"):
        L.append(f"- {g}: `{dec[g]['status']}`；{dec[g]['reason']}")
    L.append(
        f"- 2 倍成本替代口径（T-32 缓存的 ORIG 5 偏移混合 r20）下的状态：{dec['cost2x_alternate_status']}"
    )
    L.append("")

    def grid(setname: str) -> list[str]:
        out = [
            "| 规则 | 混合ΔSR近期 | 混合ΔSR压力 | 中位数近期 | 中位数压力 | 偏移>0 | 安慰剂分位 | 2x成本ΔSR | 2x成本(缓存混合) | 六段平均pp | ES变化 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in RULES:
            d = res["deltas"][setname][r]
            out.append(
                f"| {r} | {fmt(d['blend_recent'])} | {fmt(d['blend_stress'])} | {fmt(d['median_recent'])} | {fmt(d['median_stress'])} | {d['offsets_positive_recent']}/5 | {fmt(d['placebo_quantile_recent'], 2)} | {fmt(d['cost2x_delta_recent'])} | {fmt(d['cost2x_delta_recent_cacheblend'])} | {fmt(d['six_segment_mean_change_pp'], 2)} | {fmt(d['es975_stress_change'], 4)} |"
            )
        return out

    L += ["## 1. 规则网格（选中集）", ""] + grid("selected") + [""]
    L += ["## 2. 规则网格（ORIG 集，只报告）", ""] + grid("orig") + [""]
    L += ["## 3. 可部署版本", ""]
    L.append(
        "| 档位 | 账户 | 版本 | l1_eligible | k* | 总敞口 | 近期年化 | 近期波动 | 近期夏普 | 近期最大回撤 | 压力期夏普 | 压力期最大回撤 | 全期最大回撤 | dd_budget_unmet |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for t, d in res["deployables"].items():
        for acct, e in d.items():
            for name, x in _entries(e):
                L.append(
                    f"| {t} | {acct} | {name} | {x['l1_eligible']} | {x['k_star']:.2f} | {x['gross']:.2f} | {fmt(x['recent']['cagr'])} | {fmt(x['recent']['vol'])} | {fmt(x['recent']['sr'])} | {fmt(x['recent']['maxdd'])} | {fmt(x['stress']['sr'])} | {fmt(x['stress']['maxdd'])} | {fmt(x['full_maxdd'])} | {x['dd_budget_unmet']} |"
                )
    L += ["", "## 4. 回撤分位数（5 万档，选中版本、P0、P0-S3；其余见 results.json）", ""]
    L.append("| 账户 | 版本 | 情景 | 期限 | q50 | q90 | q95 | q99 | P(回撤>30%) |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for acct in ("cash", "margin"):
        e = res["deployables"]["50k"][acct]
        for name, x in _entries(e):
            for scn, byh in x["dd_sim"].items():
                for hz, q in byh.items():
                    L.append(
                        f"| {acct} | {name} | {scn} | {hz} | {fmt(q['q50'])} | {fmt(q['q90'])} | {fmt(q['q95'])} | {fmt(q['q99'])} | {fmt(q['p_dd_gt_30'], 4)} |"
                    )
    L += ["", "## 5. 风险份额与换手（选中集）", ""]
    L.append(
        "| 规则 | 近期平均风险份额 | 压力期平均风险份额 | S3份额>0.6(近期) | 换手/年 | 调仓成本bp/年 |"
    )
    L.append("|---|---|---|---|---|---|")
    for r in ["P0"] + RULES:
        x = res["p0"]["selected"] if r == "P0" else res["rules"]["selected"][r]

        def rs(w: str, x=x) -> str:
            return ", ".join(f"{s} {v:.2f}" for s, v in x["risk_share_mean"][w].items())

        L.append(
            f"| {r} | {rs('recent')} | {rs('stress')} | {fmt(x['s3_share_gt_0p6']['recent'], 2)} | {fmt(x['turnover_per_yr'], 2)} | {fmt(x['rebal_cost_bp_yr'], 1)} |"
        )
    L += ["", "## DSR（选中规则，N = 8）", ""]
    for g, d in res["dsr_selected"].items():
        L.append(
            f"- {g}: 规则 {d['rule']}，DSR {fmt(d['dsr'])}，n_eff {fmt(d['n_eff'], 2)}，var_sr {fmt(d['var_sr_annual'], 4)}"
        )
    L.append("")
    (D / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")

    ledger = []
    for r in RULES:
        d = res["deltas"]["selected"][r]
        ledger.append(
            {
                "candidate_id": r,
                "rule": r,
                "group": "small,1M" if r in SMALL_RULES else "1M",
                "blend_dsr_recent": d["blend_recent"],
                "blend_dsr_stress": d["blend_stress"],
                "median_dsr_recent": d["median_recent"],
                "median_dsr_stress": d["median_stress"],
                "d1_pass": bool(r in dec["1M"]["d1_passers"] or r in dec["small"]["d1_passers"]),
                "d2_admissible": (
                    float(r[-4:]) in dec["1M"]["d2_admissible_levels"]
                    if r.startswith("T58_CAP2_")
                    else None
                ),
            }
        )
    (D / "trial-ledger.json").write_text(json.dumps(ledger, indent=1) + "\n", encoding="utf-8")
    wl: dict[str, Any] = {}
    for t, d in res["deployables"].items():
        wl[t] = {}
        for acct, e in d.items():
            wl[t][acct] = {
                key: {
                    "rule": x["rule"],
                    "k_star": x["k_star"],
                    "weights": x["weights_last"],
                    "weights_by_offset": x["weights_last_by_offset"],
                    "gross": x["gross"],
                    "dd_budget_unmet": x["dd_budget_unmet"],
                    "l1_eligible": x["l1_eligible"],
                }
                for key, x in (("selected", e), ("p0_s3", e["p0_s3"]), ("p0", e["p0_same_account"]))
            }
    (D / "weights-latest.json").write_text(json.dumps(wl, indent=1) + "\n", encoding="utf-8")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["build", "run", "report"], required=True)
    args = ap.parse_args()
    return {"build": stage_build, "run": stage_run, "report": stage_report}[args.stage]()


if __name__ == "__main__":
    raise SystemExit(main())
