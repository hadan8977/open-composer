"""Vectorized OU-T diagnostic on the frozen PCA5 residual store.

This is a diagnostic bridge before the learned models: it reports directional
IC and a causal residual-space portfolio. It is not the contract's final
costed evaluation or a promotion artifact.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.p1s1_build import daily_returns, load_store, monthly_universes


def ou_scores(path: np.ndarray, previous: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    y = np.asarray(path, dtype=float)
    x, z = y[:-1], y[1:]
    ok = np.isfinite(y).all(axis=0)
    n = x.shape[0]
    sx, sz = x.sum(0), z.sum(0)
    sxx, sxz = (x * x).sum(0), (x * z).sum(0)
    den = n * sxx - sx * sx
    b = np.divide(n * sxz - sx * sz, den, out=np.full(y.shape[1], np.nan), where=den > 1e-14)
    a = (sz - b * sx) / n
    resid = z - (a[None, :] + b[None, :] * x)
    var = np.nanvar(resid, axis=0, ddof=1)
    sigma = np.sqrt(
        np.divide(var, 1.0 - b * b, out=np.full_like(b, np.nan), where=(b > 0) & (b < 1))
    )
    mean = np.divide(a, 1.0 - b, out=np.full_like(b, np.nan), where=np.abs(1.0 - b) > 1e-12)
    kappa = -np.log(b) * 252.0
    score = np.divide(y[-1] - mean, sigma, out=np.full_like(b, np.nan), where=sigma > 1e-12)
    valid = ok & (b > 0) & (b < 1) & (kappa > 252.0 / 30.0) & np.isfinite(score)
    score[~valid] = np.nan
    pos = previous.copy()
    flat = valid & (previous == 0)
    pos[flat & (score < -1.25)] = 1.0
    pos[flat & (score > 1.25)] = -1.0
    pos[(previous > 0) & valid & (score > -0.50)] = 0.0
    pos[(previous < 0) & valid & (score < 0.75)] = 0.0
    pos[~valid] = 0.0
    return score, pos


def run(store_path: Path, residual_path: Path, out: Path) -> dict:
    store = load_store(store_path)
    close = np.asarray(store.close, dtype=float)
    returns = daily_returns(close)
    _, trade, _ = monthly_universes(store)
    residual = np.load(residual_path / "residual.npy", mmap_mode="r")
    beta = np.load(residual_path / "beta_refresh.npy", mmap_mode="r")
    weights = np.load(residual_path / "weights_refresh.npy", mmap_mode="r")
    meta = json.loads((residual_path / "meta.json").read_text())
    start = int(meta["successful_refresh_indices"][0]) + 60
    end = min(returns.shape[0] - 2, int(meta["successful_refresh_indices"][-1]))
    prev = np.zeros(returns.shape[1], dtype=float)
    gross = np.full(returns.shape[0], np.nan)
    ics = []
    active = []
    for t in range(start, end):
        path = np.cumsum(np.asarray(residual[t - 59 : t + 1], dtype=float), axis=0)
        score, prev = ou_scores(path, prev)
        prev = np.where(trade[t], prev, 0.0)
        w = np.where(np.isfinite(score), prev, 0.0)
        scale = np.sum(np.abs(w))
        if scale <= 0:
            continue
        w /= scale
        ridx = t - int(meta["successful_refresh_indices"][0])
        b = np.nan_to_num(np.asarray(beta[ridx], dtype=float), nan=0.0)
        W = np.nan_to_num(np.asarray(weights[ridx], dtype=float), nan=0.0)
        h = w - W.T @ (b.T @ w)
        future = returns[t + 2]
        valid_h = np.isfinite(h) & np.isfinite(future)
        gross[t] = float(h[valid_h] @ future[valid_h]) if valid_h.any() else np.nan
        fwd = returns[t + 1]
        ok = np.isfinite(score) & np.isfinite(fwd) & trade[t]
        if ok.sum() >= 20:
            xr = np.argsort(np.argsort(score[ok])).astype(float)
            yr = np.argsort(np.argsort(fwd[ok])).astype(float)
            ics.append(float(np.corrcoef(xr, yr)[0, 1]))
        active.append(int(np.sum(np.abs(h) > 0)))
    recent = (
        np.arange(len(gross)) >= np.searchsorted(store.dates, np.datetime64("2024-01-08"))
    ) & np.isfinite(gross)
    x = gross[recent]
    result = {
        "contract": "t20261008_p1_s1_dlsa",
        "diagnostic": "OU-T PCA5 residual-space; no full cost model, no learned model",
        "sessions": int(x.size),
        "gross_ann_return": float(np.mean(x) * 252) if x.size else None,
        "gross_sharpe_recent": (
            float(np.mean(x) / np.std(x, ddof=1) * np.sqrt(252))
            if x.size > 1 and np.std(x, ddof=1) > 0
            else None
        ),
        "mean_daily_rank_ic": float(np.nanmean(ics)) if ics else None,
        "ic_days": len(ics),
        "mean_active_names": float(np.mean(active)) if active else None,
        "costed_final_evaluation": False,
        "returns_published": False,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "ou_diagnostic.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=Path("data/research/t22_streversal"))
    ap.add_argument("--residual", type=Path, default=Path("data/research/p1s1_dlsa/pca5_full"))
    ap.add_argument(
        "--out", type=Path, default=Path("reports/research/iterations/t20261008_p1_s1_dlsa")
    )
    args = ap.parse_args()
    print(json.dumps(run(args.store, args.residual, args.out), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
