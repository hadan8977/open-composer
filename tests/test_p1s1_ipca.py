from __future__ import annotations

import numpy as np

from scripts.p1s1_ipca import (
    cross_sectional_rank_map,
    fit_ipca_als,
    lagged_rank_features,
    neutralize_weights,
    project_factors,
    rank_features_with_constant,
    rank_features_with_reference,
)


def test_rank_map_uses_member_distribution_and_missing_zero() -> None:
    values = np.array([1.0, 2.0, 3.0, 2.5, np.nan])
    members = np.array([True, True, True, False, True])
    mapped = cross_sectional_rank_map(values, members, outside=np.ones(5, dtype=bool))
    assert np.allclose(mapped[:3], [-0.5, 0.0, 0.5])
    assert mapped[3] == 0.25  # interpolated between member values 2 and 3
    assert mapped[4] == 0.0


def test_lagged_rank_features_cannot_see_current_or_future_rows() -> None:
    rng = np.random.default_rng(11)
    features = rng.normal(size=(6, 5, 2))
    members = np.ones((6, 5), dtype=bool)
    ranked = lagged_rank_features(features, members)
    changed = features.copy()
    changed[4:] += 1000.0
    changed_ranked = lagged_rank_features(changed, members)
    assert np.array_equal(ranked[:4], changed_ranked[:4])
    assert np.all(ranked[0] == 0.0)


def test_rank_features_with_reference_does_not_rerank_outside_names() -> None:
    values = np.array([[1.0], [3.0], [2.0], [100.0]])
    m = np.array([True, True, True, False])
    e = np.ones(4, dtype=bool)
    mapped = rank_features_with_reference(values, e, m)[:, 0]
    assert np.allclose(mapped[:3], [-0.5, 0.5, 0.0])
    assert mapped[3] == 0.5


def test_rank_features_with_constant_adds_ipca_intercept() -> None:
    features = np.array([[1.0, 4.0], [2.0, 3.0], [3.0, 2.0]])
    ranked = rank_features_with_constant(features, np.ones(3, dtype=bool))
    assert ranked.shape == (3, 3)
    assert np.all(ranked[:, 0] == 1.0)


def test_ipca_als_recovers_synthetic_gamma_subspace() -> None:
    rng = np.random.default_rng(7)
    t, n, n_features, k = 80, 35, 5, 2
    z = rng.normal(size=(t, n, n_features))
    z[:, :, 0] = 1.0
    true_gamma, _ = np.linalg.qr(rng.normal(size=(n_features, k)))
    factors = rng.normal(size=(t, k))
    returns = np.einsum("tnl,lk,tk->tn", z, true_gamma, factors)
    fit = fit_ipca_als(z, returns, factors=k, max_iter=200)
    # Principal angles are invariant to IPCA's rotation and sign conventions.
    singular = np.linalg.svd(true_gamma.T @ fit.gamma, compute_uv=False)
    assert np.max(1.0 - singular) < 1e-6
    assert fit.iterations <= 200


def test_projection_residual_and_neutralization() -> None:
    rng = np.random.default_rng(3)
    n, n_features, k = 20, 4, 2
    z = rng.normal(size=(n, n_features))
    gamma, _ = np.linalg.qr(rng.normal(size=(n_features, k)))
    f = np.array([0.4, -0.7])
    returns = z @ gamma @ f + rng.normal(scale=0.01, size=n)
    members = np.ones(n, dtype=bool)
    projected, fitted, residual = project_factors(z, gamma, returns, members)
    assert np.allclose(projected, f, atol=0.03)
    assert np.allclose(fitted + residual, returns)
    weights = rng.normal(size=n)
    h = neutralize_weights(weights, z @ gamma)
    assert np.max(np.abs((z @ gamma).T @ h)) < 1e-10
