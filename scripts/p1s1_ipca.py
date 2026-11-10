"""Small, auditable IPCA5-PV building blocks for the DLSA contract.

The functions in this module operate on arrays supplied by the caller.  They
do not load the research panel, run a backtest, or publish performance
statistics.  In particular, ``lagged_rank_features`` makes the information
timing explicit: the row used for return ``t`` is ranked from the features and
universe visible at ``t - 1``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _as_float_array(values: np.ndarray, *, ndim: int | None = None) -> np.ndarray:
    array = np.asarray(values, dtype=np.float64)
    if ndim is not None and array.ndim != ndim:
        raise ValueError(f"expected a {ndim}-D array, got shape {array.shape}")
    return array


def _average_ranks(values: np.ndarray) -> np.ndarray:
    """Return one-based average ranks for a finite, sorted-or-unsorted row."""
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(values.size, dtype=np.float64)
    sorted_values = values[order]
    start = 0
    while start < values.size:
        stop = start + 1
        while stop < values.size and sorted_values[stop] == sorted_values[start]:
            stop += 1
        ranks[order[start:stop]] = (start + 1 + stop) / 2.0
        start = stop
    return ranks


def cross_sectional_rank_map(
    values: np.ndarray,
    membership: np.ndarray,
    *,
    outside: np.ndarray | None = None,
) -> np.ndarray:
    """Map one feature row to ``[-0.5, 0.5]`` using a PIT universe.

    ``membership`` identifies the M universe used to form the empirical
    distribution.  Missing member values map to zero.  If ``outside`` is
    supplied, non-member finite values are interpolated through the member
    empirical distribution (rather than being re-ranked with M).  This is the
    E-universe behavior required by the contract.
    """
    x = _as_float_array(values, ndim=1)
    m = np.asarray(membership, dtype=bool)
    if m.shape != x.shape:
        raise ValueError("membership must have the same shape as values")
    if outside is None:
        target = m
        out = np.zeros(x.size, dtype=np.float64)
    else:
        target = np.asarray(outside, dtype=bool)
        if target.shape != x.shape:
            raise ValueError("outside must have the same shape as values")
        out = np.zeros(x.size, dtype=np.float64)

    valid_member = m & np.isfinite(x)
    member_values = x[valid_member]
    if member_values.size == 0:
        return out

    ranks = _average_ranks(member_values)
    n = member_values.size
    member_mapped = (ranks - 1.0) / max(n - 1, 1) - 0.5
    out[valid_member] = member_mapped

    if outside is None:
        return out
    valid_outside = target & ~m & np.isfinite(x)
    if not valid_outside.any():
        return out

    # Collapse ties before interpolation so a value equal to a member tie gets
    # that tie's average rank, independent of sort stability.
    order = np.argsort(member_values, kind="mergesort")
    sorted_values = member_values[order]
    sorted_mapped = member_mapped[order]
    unique_values, first = np.unique(sorted_values, return_index=True)
    last = np.r_[first[1:] - 1, sorted_values.size - 1]
    unique_mapped = (sorted_mapped[first] + sorted_mapped[last]) / 2.0
    out[valid_outside] = np.interp(
        x[valid_outside],
        unique_values,
        unique_mapped,
        left=unique_mapped[0],
        right=unique_mapped[-1],
    )
    return out


def rank_features(features: np.ndarray, membership: np.ndarray) -> np.ndarray:
    """Rank-map a ``(N, L)`` feature matrix column by column."""
    z = _as_float_array(features, ndim=2)
    m = np.asarray(membership, dtype=bool)
    if m.shape != (z.shape[0],):
        raise ValueError("membership must have shape (N,)")
    return np.column_stack([cross_sectional_rank_map(z[:, j], m) for j in range(z.shape[1])])


def rank_features_with_constant(features: np.ndarray, membership: np.ndarray) -> np.ndarray:
    """Rank-map features and prepend the IPCA intercept column of ones."""
    ranked = rank_features(features, membership)
    return np.column_stack([np.ones(ranked.shape[0], dtype=np.float64), ranked])


def rank_features_with_reference(
    features: np.ndarray, membership: np.ndarray, reference_membership: np.ndarray
) -> np.ndarray:
    """Rank-map E features using the empirical distribution of M.

    ``reference_membership`` is the M mask and ``membership`` is the output
    universe (typically E).  Keeping both masks prevents accidental re-ranking
    of names outside M.
    """
    z = _as_float_array(features, ndim=2)
    output_mask = np.asarray(membership, dtype=bool)
    reference_mask = np.asarray(reference_membership, dtype=bool)
    if output_mask.shape != (z.shape[0],) or reference_mask.shape != output_mask.shape:
        raise ValueError("membership masks must have shape (N,)")
    return np.column_stack(
        [
            cross_sectional_rank_map(z[:, j], reference_mask, outside=output_mask)
            for j in range(z.shape[1])
        ]
    )


def lagged_rank_features(features: np.ndarray, membership: np.ndarray) -> np.ndarray:
    """Create causal ranked features for a panel.

    Inputs have shapes ``features[T, N, L]`` and ``membership[T, N]``.  Row
    ``t`` is ranked from row ``t-1``; row zero is all zeros because no prior
    information exists.  The function intentionally does not fill or infer a
    universe from future rows.
    """
    raw = _as_float_array(features, ndim=3)
    mask = np.asarray(membership, dtype=bool)
    if mask.shape != raw.shape[:2]:
        raise ValueError("membership must have shape (T, N)")
    out = np.zeros_like(raw)
    for t in range(1, raw.shape[0]):
        out[t] = rank_features(raw[t - 1], mask[t - 1])
    return out


@dataclass(frozen=True)
class IPCAFit:
    """Auditable result of an IPCA ALS fit."""

    gamma: np.ndarray
    factor_returns: np.ndarray
    iterations: int
    converged: bool
    max_delta: float


def _valid_rows(
    z: np.ndarray, returns: np.ndarray, membership: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray]:
    if membership is None:
        member = np.ones((z.shape[0], z.shape[1]), dtype=bool)
    else:
        member = np.asarray(membership, dtype=bool)
        if member.shape != z.shape[:2]:
            raise ValueError("membership must have shape (T, N)")
    finite = np.isfinite(z).all(axis=2) & np.isfinite(returns)
    return member & finite, member


def _initial_gamma(
    z: np.ndarray, returns: np.ndarray, valid: np.ndarray, factors: int
) -> np.ndarray:
    n_features = z.shape[2]
    cross = np.zeros((n_features, n_features), dtype=np.float64)
    for t in range(z.shape[0]):
        names = np.flatnonzero(valid[t])
        if names.size == 0:
            continue
        q = z[t, names].T @ returns[t, names]
        cross += np.outer(q, q)
    if not np.any(cross):
        return np.eye(n_features, factors, dtype=np.float64)
    _, _, vt = np.linalg.svd(cross, full_matrices=False)
    return vt[: min(factors, n_features)].T.copy()


def _factor_step(
    z: np.ndarray, returns: np.ndarray, gamma: np.ndarray, valid: np.ndarray
) -> np.ndarray:
    out = np.full((z.shape[0], gamma.shape[1]), np.nan, dtype=np.float64)
    for t in range(z.shape[0]):
        names = np.flatnonzero(valid[t])
        if names.size < gamma.shape[1]:
            continue
        b = z[t, names] @ gamma
        out[t] = np.linalg.lstsq(b, returns[t, names], rcond=None)[0]
    return out


def _gamma_step(
    z: np.ndarray, returns: np.ndarray, factors_t: np.ndarray, valid: np.ndarray
) -> np.ndarray:
    n_features, k = z.shape[2], factors_t.shape[1]
    design_rows: list[np.ndarray] = []
    targets: list[float] = []
    for t in range(z.shape[0]):
        if not np.isfinite(factors_t[t]).all():
            continue
        for i in np.flatnonzero(valid[t]):
            # vec(z_i outer f_t) in row-major order, matching Gamma[L, K].
            design_rows.append(np.outer(z[t, i], factors_t[t]).ravel())
            targets.append(float(returns[t, i]))
    if not design_rows:
        return np.eye(n_features, k, dtype=np.float64)
    coef, *_ = np.linalg.lstsq(np.asarray(design_rows), np.asarray(targets), rcond=None)
    return coef.reshape(n_features, k)


def _orthogonalize(gamma: np.ndarray, factors_t: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Normalize Gamma and rotate factors to descending sample variance."""
    u, _, vt = np.linalg.svd(gamma, full_matrices=False)
    k = gamma.shape[1]
    g = u[:, :k] @ vt[:k]
    f = factors_t @ np.linalg.pinv(gamma) @ g if np.isfinite(factors_t).all() else factors_t
    # The line above is only used for complete arrays; factor rows are usually
    # complete after the ALS warm-up.  Re-estimation in the caller handles NaNs.
    if f.ndim == 2:
        variance = np.nanvar(f, axis=0)
        order = np.argsort(-variance, kind="stable")
        g = g[:, order]
        f = f[:, order]
        for j in range(k):
            valid = np.isfinite(f[:, j])
            if valid.any() and np.nanmean(f[valid, j]) < 0:
                g[:, j] *= -1.0
                f[:, j] *= -1.0
    return g, f


def fit_ipca_als(
    features: np.ndarray,
    returns: np.ndarray,
    *,
    membership: np.ndarray | None = None,
    factors: int = 5,
    max_iter: int = 200,
    tol: float = 1e-6,
) -> IPCAFit:
    """Fit ``r[i,t] = z[i,t] @ Gamma @ f[t]`` by alternating least squares.

    The caller is responsible for passing lagged features (for example from
    :func:`lagged_rank_features`).  Only finite observations in the supplied
    membership mask are used.  The returned Gamma has orthonormal columns and
    factor columns sorted by descending variance.
    """
    z = _as_float_array(features, ndim=3)
    r = _as_float_array(returns, ndim=2)
    if z.shape[:2] != r.shape:
        raise ValueError("features and returns must agree on (T, N)")
    if factors < 1 or factors > z.shape[2]:
        raise ValueError("factors must be between 1 and the feature count")
    if max_iter < 1 or tol <= 0:
        raise ValueError("max_iter must be positive and tol must be positive")
    valid, _ = _valid_rows(z, r, membership)
    if valid.sum() < factors:
        raise ValueError("not enough finite member observations for IPCA")

    gamma = _initial_gamma(z, r, valid, factors)
    factors_t = _factor_step(z, r, gamma, valid)
    max_delta = float("inf")
    converged = False
    iterations = 0
    for iteration in range(1, max_iter + 1):
        candidate = _gamma_step(z, r, factors_t, valid)
        # QR gives a deterministic orthonormal basis while the next factor
        # step absorbs the corresponding scale.
        q, _ = np.linalg.qr(candidate, mode="reduced")
        if q.shape[1] < factors:
            raise ValueError("ALS design is rank deficient")
        candidate = q[:, :factors]
        max_delta = float(np.max(np.abs(candidate - gamma)))
        gamma = candidate
        factors_t = _factor_step(z, r, gamma, valid)
        if max_delta < tol:
            converged = True
            iterations = iteration
            break
    else:
        iterations = max_iter
    # Final deterministic orientation/order, followed by a fresh factor step.
    factors_t = _factor_step(z, r, gamma, valid)
    variances = np.nanvar(factors_t, axis=0)
    order = np.argsort(-variances, kind="stable")
    gamma = gamma[:, order]
    factors_t = factors_t[:, order]
    for j in range(factors):
        finite = np.isfinite(factors_t[:, j])
        if finite.any() and np.nanmean(factors_t[finite, j]) < 0:
            gamma[:, j] *= -1.0
            factors_t[:, j] *= -1.0
    return IPCAFit(gamma, factors_t, iterations, converged, max_delta)


def project_factors(
    features: np.ndarray,
    gamma: np.ndarray,
    returns: np.ndarray,
    membership: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Project one cross-section onto IPCA factors and return residuals.

    Returns ``(f, fitted, residual)``.  The factor regression uses only names
    in ``membership``; fitted and residual values outside that set are still
    returned when their features and returns are finite.
    """
    z = _as_float_array(features, ndim=2)
    g = _as_float_array(gamma, ndim=2)
    r = _as_float_array(returns, ndim=1)
    if z.shape[1] != g.shape[0] or z.shape[0] != r.size:
        raise ValueError("features, gamma, and returns dimensions disagree")
    if membership is None:
        m = np.ones(r.size, dtype=bool)
    else:
        m = np.asarray(membership, dtype=bool)
        if m.shape != r.shape:
            raise ValueError("membership must have shape (N,)")
    valid_m = m & np.isfinite(r) & np.isfinite(z).all(axis=1)
    b = z @ g
    valid_b = valid_m & np.isfinite(b).all(axis=1)
    if valid_b.sum() < g.shape[1]:
        f = np.full(g.shape[1], np.nan, dtype=np.float64)
    else:
        f = np.linalg.lstsq(b[valid_b], r[valid_b], rcond=None)[0]
    fitted = b @ f if np.isfinite(f).all() else np.full(r.size, np.nan)
    residual = r - fitted
    residual[~(np.isfinite(r) & np.isfinite(fitted))] = np.nan
    return f, fitted, residual


def neutralize_weights(weights: np.ndarray, exposures: np.ndarray) -> np.ndarray:
    """Remove the span of ``exposures`` from a portfolio weight vector."""
    w = _as_float_array(weights, ndim=1)
    b = _as_float_array(exposures, ndim=2)
    if b.shape[0] != w.size:
        raise ValueError("weights and exposures must agree on the asset count")
    valid = np.isfinite(w) & np.isfinite(b).all(axis=1)
    out = np.zeros_like(w)
    if valid.sum() == 0:
        return out
    basis, _, _ = np.linalg.svd(b[valid], full_matrices=False)
    rank = int(np.linalg.matrix_rank(b[valid]))
    q = basis[:, :rank]
    out[valid] = w[valid] - q @ (q.T @ w[valid])
    return out


__all__ = [
    "IPCAFit",
    "cross_sectional_rank_map",
    "fit_ipca_als",
    "lagged_rank_features",
    "neutralize_weights",
    "project_factors",
    "rank_features",
    "rank_features_with_constant",
    "rank_features_with_reference",
]
