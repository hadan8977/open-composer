"""T-20261006-21: linear models (ridge / LASSO chosen on a validation block) from per-day moment matrices.

A day's training rows (grid t = 11 + 3j, pool_rank <= N, finite label) are summarised by the augmented
moment matrix M = A'A with A = [1, X, y] (42 x 42), so a 12-month window is a sum of daily matrices and the
fit is exact (no row data needed).  Features are imputed and clipped by fixed rules (addendum-1 B3, B9).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from features import FEATURES

NS = (100, 300, 600)
HS = (15, 30, 60)
NF = len(FEATURES)
RIDGE_GRID = (1e-4, 1e-3, 1e-2, 1e-1, 1.0)
LASSO_GRID = (1e-5, 1e-4, 3e-4, 1e-3, 3e-3)
VAL_DAYS = 21

# fixed clip bounds (returns and ratios) frozen before any result; ranks are in [0, 1]
CLIP = {
    "r5": 0.1,
    "r15": 0.1,
    "r30": 0.1,
    "r60": 0.15,
    "r_open": 0.2,
    "gap": 0.3,
    "r_d1": 0.3,
    "r_d5": 0.5,
    "vol_ratio": 20.0,
    "rv30": 0.1,
    "vwap_dist": 0.1,
}
LABEL_CLIP = 0.05


def prep_x(df: pd.DataFrame) -> np.ndarray:
    """40 features as float64: fixed imputation (ranks 0.5, vol_ratio 1, others 0) and clipping."""
    out = np.empty((len(df), NF), dtype=np.float64)
    for i, f in enumerate(FEATURES):
        v = df[f].to_numpy("float64")
        if f.startswith("rk"):
            v = np.where(np.isfinite(v), v, 0.5)
        else:
            base = f[:-4] if f.endswith("_rel") else f
            fill = 1.0 if f == "vol_ratio" else 0.0
            v = np.where(np.isfinite(v), v, fill)
            if base in CLIP:
                c = CLIP[base]
                v = np.clip(v, -c if f != "vol_ratio" else 0.0, c)
        out[:, i] = v
    return out


def accumulate_month(panel: pd.DataFrame, pool_ranks: np.ndarray | None = None) -> dict:
    """Per-day moment matrices of one month's panel (training grid only): returns days and array
    M[d, n_i, h_i, 42, 42]."""
    t = panel["t"].to_numpy().astype(int)
    g0 = (t - 11) % 3 == 0
    p = panel[g0]
    x = prep_x(p)
    days = np.array(sorted(p["d"].unique()))
    M = np.zeros((len(days), len(NS), len(HS), NF + 2, NF + 2))
    didx = pd.Index(days).get_indexer(p["d"])
    pr = p["pool_rank"].to_numpy()
    for hi, h in enumerate(HS):
        y = np.clip(p[f"y{h}"].to_numpy("float64"), -LABEL_CLIP, LABEL_CLIP)
        fin = np.isfinite(y)
        for ni, n in enumerate(NS):
            msk = fin & (pr <= n)
            if not msk.any():
                continue
            A = np.column_stack([np.ones(msk.sum()), x[msk], y[msk]])
            dd = didx[msk]
            for di in np.unique(dd):
                a = A[dd == di]
                M[di, ni, hi] = a.T @ a
    return {"days": days, "M": M}


def _soft(x, a):
    return np.sign(x) * np.maximum(np.abs(x) - a, 0.0)


def lasso_gram(
    G: np.ndarray, c: np.ndarray, alpha: float, beta0: np.ndarray | None = None
) -> np.ndarray:
    b = np.zeros(len(c)) if beta0 is None else beta0.copy()
    for _ in range(2000):
        mx = 0.0
        for j in range(len(c)):
            r = c[j] - G[j] @ b + G[j, j] * b[j]
            nb = _soft(r, alpha) / G[j, j]
            mx = max(mx, abs(nb - b[j]))
            b[j] = nb
        if mx < 1e-9:
            break
    return b


def _stats(M: np.ndarray):
    n = M[0, 0]
    sx = M[0, 1:-1]
    sy = M[0, -1]
    xx = M[1:-1, 1:-1]
    xy = M[1:-1, -1]
    yy = M[-1, -1]
    return n, sx, sy, xx, xy, yy


def fit_window(
    Mfit: np.ndarray, Mval: np.ndarray | None, kind: str | None = None, param: float | None = None
) -> dict:
    """Fit on Mfit.  With kind=None choose ridge/LASSO and the parameter on Mval (min validation MSE)."""
    n, sx, sy, xx, xy, yy = _stats(Mfit)
    mu = sx / n
    my = sy / n
    cov = xx / n - np.outer(mu, mu)
    sd = np.sqrt(np.maximum(np.diag(cov), 1e-18))
    sdy = np.sqrt(max(yy / n - my * my, 1e-18))
    G = cov / np.outer(sd, sd)
    c = (xy / n - mu * my) / (sd * sdy)

    def solve(kd, pr):
        if kd == "ridge":
            return np.linalg.solve(G + pr * np.eye(NF), c)
        return lasso_gram(G, c, pr)

    def to_orig(bs):
        beta = bs * sdy / sd
        b0 = my - beta @ mu
        return b0, beta

    def val_mse(b0, beta, Mv):
        nv = Mv[0, 0]
        w = np.concatenate([[-b0], -beta, [1.0]])
        return float(w @ Mv @ w) / nv

    if kind is None:
        best = None
        for kd, grid in (("ridge", RIDGE_GRID), ("lasso", LASSO_GRID)):
            for pr in grid:
                b0, beta = to_orig(solve(kd, pr))
                e = val_mse(b0, beta, Mval)
                if best is None or e < best[0]:
                    best = (e, kd, pr)
        _, kind, param = best
    b0, beta = to_orig(solve(kind, param))
    return {
        "b0": b0,
        "beta": beta,
        "kind": kind,
        "param": param,
        "n": float(n),
        "nz": int(np.sum(np.abs(beta) > 0)),
    }


def predict_bp(model: dict, x: np.ndarray) -> np.ndarray:
    return 1e4 * (model["b0"] + x @ model["beta"])
