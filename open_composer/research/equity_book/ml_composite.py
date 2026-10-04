"""Pure helpers of the v1.4 ML-composite iteration (``t20261004_book_v14_ml``).

Everything here is deterministic and free of I/O: per-date rank standardization, the beta-hedged
forward labels (decision at the close of position ``p``, fill at the close of ``p + 1``, same
timing as ``scripts/realism_ladder_book_ls.py::Prices.returns``), industry demeaning,
random Fourier features and the DKKM ridge SDF solution (Didisheim, Ke, Kelly, Malamud 2024,
section 2.3), the validation rule for the ridge shrinkage ``z``, the within-date label permutation
used for the leak check, and the Stage A "simplified weekly gross" return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from open_composer.research.equity_book import optimize as op
from open_composer.research.equity_book.book_v12 import target_weights

EMBARGO_GAP = 43  # 21-session label + 1 fill session + 21-session isolation gap
MIN_WEEKS_FOR_VALIDATION = 104
VALIDATION_WEEKS = 52
VALIDATION_GAP_WEEKS = 1
DEFAULT_Z = 1.0
Z_GRID = (1e-3, 1e-2, 1e-1, 1.0, 10.0, 100.0, 1000.0)
BETA_CLIP = (-1.0, 4.0)


def rank_standardize(
    df: pd.DataFrame, cols: list[str], date_col: str = "trade_date"
) -> pd.DataFrame:
    """Per-date percentile rank minus 0.5 (range (-0.5, 0.5]); NaN stays NaN."""
    out = df.copy()
    ranked = df.groupby(date_col, sort=False)[cols].rank(pct=True, method="average")
    out[cols] = ranked - 0.5
    return out


def book_labels(C: np.ndarray, S: np.ndarray, beta: np.ndarray, p: int, horizon: int) -> np.ndarray:
    """Beta-hedged forward return from ``C[p+1]`` to ``C[p+1+horizon]`` for every column of ``C``.

    ``y = C[p+1+h]/C[p+1] - 1 - beta * (S[p+1+h]/S[p+1] - 1)``; ``beta`` is clipped to
    [-1, 4] and NaN beta counts as 1.0.  NaN prices give NaN labels; indices past the end give NaN.
    """
    n = C.shape[0]
    out = np.full(C.shape[1], np.nan)
    if p + 1 + horizon >= n or p + 1 < 0:
        return out
    b = np.clip(np.where(np.isnan(beta), 1.0, beta), *BETA_CLIP)
    with np.errstate(invalid="ignore", divide="ignore"):
        stock = C[p + 1 + horizon] / C[p + 1] - 1.0
        spy = S[p + 1 + horizon] / S[p + 1] - 1.0
    return stock - b * spy


def _codes(ind: pd.Series | np.ndarray) -> np.ndarray:
    """Integer group code per row; NaN industries share one group (as ``target_weights``)."""
    s = pd.Series(np.asarray(ind)).fillna(-1)
    return pd.factorize(s.to_numpy())[0]


def industry_demean(x: pd.Series | np.ndarray, ind: pd.Series | np.ndarray):
    """Subtract the within-industry mean (NaN ignored); accepts a vector or a (rows, cols) matrix.

    Returns the same container type as ``x``.  Rows with NaN ``x`` stay NaN; a group with no
    finite value stays NaN.
    """
    arr = np.asarray(x, dtype="float64")
    codes = _codes(ind)
    if len(codes) != arr.shape[0]:
        raise ValueError("x and ind must have the same number of rows")
    ngroups = int(codes.max()) + 1 if len(codes) else 0
    finite = np.isfinite(arr)
    filled = np.where(finite, arr, 0.0)
    two_d = arr.ndim == 2
    mat = filled if two_d else filled[:, None]
    cnt_in = finite.astype("float64") if two_d else finite.astype("float64")[:, None]
    sums = np.zeros((ngroups, mat.shape[1]))
    cnts = np.zeros((ngroups, mat.shape[1]))
    order = np.argsort(codes, kind="stable")
    sorted_codes = codes[order]
    starts = (
        np.flatnonzero(np.r_[True, sorted_codes[1:] != sorted_codes[:-1]]) if len(codes) else []
    )
    if len(codes):
        sums[sorted_codes[starts]] = np.add.reduceat(mat[order], starts, axis=0)
        cnts[sorted_codes[starts]] = np.add.reduceat(cnt_in[order], starts, axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        means = sums / cnts
    out = np.where(finite if two_d else finite[:, None], mat - means[codes], np.nan)
    if not two_d:
        out = out[:, 0]
    if isinstance(x, pd.Series):
        return pd.Series(out, index=x.index, name=x.name)
    if isinstance(x, pd.DataFrame):
        return pd.DataFrame(out, index=x.index, columns=x.columns)
    return out


def rff_draw(seed: int, n_features: int, n_freq: int, gammas: tuple[float, ...]):
    """The frozen random draw: omega ~ N(0, I) of shape (n_features, n_freq), gamma uniform on
    the grid per frequency."""
    rng = np.random.default_rng(seed)
    omega = rng.standard_normal((n_features, n_freq))
    gamma = rng.choice(np.asarray(gammas, dtype="float64"), size=n_freq)
    return omega, gamma


def rff(Z: np.ndarray, omega: np.ndarray, gamma: np.ndarray) -> np.ndarray:
    """Random Fourier features ``[sin(gamma * Z omega), cos(gamma * Z omega)]``, shape
    (rows, 2 * n_freq).  NaN in ``Z`` counts as 0 (the contract's missing-value rule)."""
    z = np.nan_to_num(np.asarray(Z, dtype="float64"), nan=0.0)
    arg = (z @ omega) * gamma[None, :]
    return np.concatenate([np.sin(arg), np.cos(arg)], axis=1)


def sdf_lambda(F: np.ndarray, z: float, s_bar: float) -> np.ndarray:
    """Ridge SDF weights ``(z * s_bar * I + F'F / T)^-1 mean(F)``; ``F`` has shape (T, P)."""
    T, P = F.shape
    gram = F.T @ F / T
    return np.linalg.solve(z * s_bar * np.eye(P) + gram, F.mean(axis=0))


def mean_gram_scale(F: np.ndarray) -> float:
    """``s_bar = tr(E[F F']) / P``."""
    T, P = F.shape
    return float(np.einsum("ij,ij->", F, F) / T / P)


def weekly_sharpe(x: np.ndarray, periods: int = 52) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if len(x) < 2:
        return float("nan")
    sd = x.std(ddof=1)
    if not sd > 0:
        return float("nan")
    return float(x.mean() / sd * np.sqrt(periods))


def choose_z(
    F: np.ndarray, z_grid: tuple[float, ...] = Z_GRID
) -> tuple[float, dict[str, float | None]]:
    """Section 4 rule: with >= 104 training weeks fit on the early weeks (1-week gap), score the
    SDF portfolio ``lambda'F`` on the last 52 weeks by weekly Sharpe and take the best z (ties go
    to the smaller z); fewer than 104 weeks: z = 1 and no validation Sharpes."""
    T = F.shape[0]
    if T < MIN_WEEKS_FOR_VALIDATION:
        return DEFAULT_Z, {}
    val = F[T - VALIDATION_WEEKS :]
    fit = F[: T - VALIDATION_WEEKS - VALIDATION_GAP_WEEKS]
    s_bar = mean_gram_scale(fit)
    sharpes: dict[str, float | None] = {}
    best_z, best = DEFAULT_Z, -np.inf
    for z in z_grid:
        lam = sdf_lambda(fit, z, s_bar)
        sh = weekly_sharpe(val @ lam)
        sharpes[repr(float(z))] = None if not np.isfinite(sh) else sh
        if np.isfinite(sh) and sh > best:
            best, best_z = sh, float(z)
    return best_z, sharpes


def permute_within_date(y: np.ndarray, date_codes: np.ndarray, seed: int = 1) -> np.ndarray:
    """Shuffle ``y`` among the rows of each date (each date keeps its label multiset)."""
    rng = np.random.default_rng(seed)
    y = np.asarray(y)
    out = y.copy()
    order = np.argsort(date_codes, kind="stable")
    sorted_codes = np.asarray(date_codes)[order]
    bounds = np.flatnonzero(np.r_[True, sorted_codes[1:] != sorted_codes[:-1], True])
    for a, b in zip(bounds[:-1], bounds[1:], strict=True):
        idx = order[a:b]
        out[idx] = y[idx[rng.permutation(len(idx))]]
    return out


def simplified_weekly_return(score: pd.Series, ind: pd.Series, r5: pd.Series) -> float:
    """Stage A weekly gross return ``sum_i w_i r5_i``, ``w = target_weights(rank_normal(score))``;
    a missing ``r5`` counts as 0 (the v1.2 rule for delisted names)."""
    w = target_weights(op.rank_normal(score), ind)
    r = r5.reindex(w.index).fillna(0.0)
    return float((w * r).sum())


def embargo_ok(train_pos: np.ndarray | list[int], refit_pos: int, gap: int = EMBARGO_GAP) -> bool:
    """True when every training decision position satisfies ``p <= refit_pos - gap``."""
    tp = np.asarray(train_pos)
    return bool(len(tp) == 0 or int(tp.max()) <= refit_pos - gap)
