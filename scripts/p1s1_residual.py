"""PCA5 residual store for the frozen DLSA stage-1 contract.

The full job is intentionally resumable by refresh block.  ``--max-refresh``
and ``--smoke-symbols`` provide a bounded implementation check without
publishing strategy returns.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from scripts.p1s1_build import daily_returns, load_store, monthly_universes

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "data/research/t22_streversal"
OUT = ROOT / "data/research/p1s1_dlsa/pca5"


def pca_loadings(window: np.ndarray, factors: int = 5) -> tuple[np.ndarray, np.ndarray, float]:
    """Return ``W[K,N] = V/sigma``, sigma, and explained variance."""
    x = np.asarray(window, dtype=float)
    if x.ndim != 2 or x.shape[0] < 2:
        raise ValueError("window must be sessions x assets")
    if not np.isfinite(x).all():
        raise ValueError("PCA window contains missing returns")
    sigma = np.std(x, axis=0, ddof=0)
    if np.any(~np.isfinite(sigma) | (sigma <= 1e-10)):
        raise ValueError("PCA window contains zero-volatility assets")
    z = (x - x.mean(axis=0)) / sigma
    _, singular, vt = np.linalg.svd(z, full_matrices=False)
    k = min(factors, vt.shape[0])
    explained = float(np.sum(singular[:k] ** 2) / max(np.sum(singular**2), 1e-30))
    return (vt[:k] / sigma[None, :]).astype(np.float64), sigma, explained


def residual_day(
    returns: np.ndarray,
    t: int,
    trade_mask: np.ndarray,
    residual_mask: np.ndarray,
    *,
    lookback: int = 252,
    loading_window: int = 60,
    factors: int = 5,
    min_assets: int = 200,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float] | None:
    """Compute one causal residual row and the stored composition matrices."""
    if t < lookback + loading_window:
        return None
    selected = np.flatnonzero(trade_mask)
    selected = selected[np.isfinite(returns[t - lookback : t][:, selected]).all(axis=0)]
    if selected.size < min_assets:
        return None
    w, _, explained = pca_loadings(returns[t - lookback : t, selected], factors)
    factor_history = returns[t - loading_window : t, selected] @ w.T
    factor_today = returns[t, selected] @ w.T
    X = np.column_stack([np.ones(loading_window), factor_history])
    beta = np.full((returns.shape[1], factors), np.nan, dtype=np.float64)
    residual = np.full(returns.shape[1], np.nan, dtype=np.float64)
    valid_f = np.isfinite(factor_history).all(axis=1)
    if valid_f.sum() < max(20, factors + 2):
        return None
    for i in np.flatnonzero(residual_mask):
        y = returns[t - loading_window : t, i]
        valid = valid_f & np.isfinite(y)
        if valid.sum() < max(30, factors + 2) or not np.isfinite(returns[t, i]):
            continue
        coef, *_ = np.linalg.lstsq(X[valid], y[valid], rcond=None)
        beta[i] = coef[1:]
        residual[i] = returns[t, i] - float(coef[1:] @ factor_today)
    weights = np.zeros((factors, returns.shape[1]), dtype=np.float64)
    weights[:, selected] = w
    return residual, beta, weights, explained


def build(
    *,
    store_path: Path,
    out: Path,
    max_refresh: int | None = None,
    smoke_symbols: int | None = None,
    smoke_min_assets: int = 20,
) -> dict:
    store = load_store(store_path)
    returns = daily_returns(np.asarray(store.close, dtype=np.float64))
    _, trade, residual = monthly_universes(store)
    if smoke_symbols:
        chosen = np.flatnonzero((trade | residual).any(axis=0))[:smoke_symbols]
        returns = returns[:, chosen]
        trade = trade[:, chosen]
        residual = residual[:, chosen]
    T, N = returns.shape
    refreshes = list(range(252 + 60, T))
    if max_refresh is not None:
        refreshes = refreshes[:max_refresh]
    out.mkdir(parents=True, exist_ok=True)
    eps = np.lib.format.open_memmap(out / "residual.npy", mode="w+", dtype="float32", shape=(T, N))
    eps[:] = np.nan
    beta = np.lib.format.open_memmap(
        out / "beta_refresh.npy", mode="w+", dtype="float32", shape=(len(refreshes), N, 5)
    )
    weights = np.lib.format.open_memmap(
        out / "weights_refresh.npy", mode="w+", dtype="float32", shape=(len(refreshes), 5, N)
    )
    beta[:] = np.nan
    weights[:] = 0.0
    used = []
    explained = []
    for j, t in enumerate(refreshes):
        result = residual_day(
            returns,
            t,
            trade[t],
            residual[t],
            min_assets=smoke_min_assets if smoke_symbols else 200,
        )
        if result is None:
            continue
        row, b, w, ev = result
        eps[t] = row.astype("float32")
        beta[j] = b.astype("float32")
        weights[j] = w.astype("float32")
        used.append(t)
        explained.append(ev)
    eps.flush()
    beta.flush()
    weights.flush()
    meta = {
        "contract": "t20261008_p1_s1_dlsa",
        "method": "PCA5_252d_correlation_60d_loading_OLS",
        "store": str(store_path),
        "shape": [T, N],
        "refresh_count": len(refreshes),
        "successful_refresh_count": len(used),
        "successful_refresh_indices": used,
        "explained_variance_mean": float(np.mean(explained)) if explained else None,
        "smoke_symbols": smoke_symbols,
        "lookahead_check": "loadings use returns[t-252:t], residual uses t",
        "returns_published": False,
    }
    (out / "meta.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", type=Path, default=STORE)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--max-refresh", type=int)
    ap.add_argument("--smoke-symbols", type=int)
    ap.add_argument("--smoke-min-assets", type=int, default=20)
    args = ap.parse_args()
    print(
        json.dumps(
            build(
                store_path=args.store,
                out=args.out,
                max_refresh=args.max_refresh,
                smoke_symbols=args.smoke_symbols,
                smoke_min_assets=args.smoke_min_assets,
            ),
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
