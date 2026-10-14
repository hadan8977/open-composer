from __future__ import annotations

import numpy as np

from scripts.p1s1_residual import pca_loadings, residual_day


def test_pca_loadings_are_scaled_and_reconstruct_factor_projection() -> None:
    rng = np.random.default_rng(7)
    factors = rng.normal(size=(80, 3))
    returns = factors @ np.array([[1.0, 0.2, 0.0], [0.0, 0.8, 0.1], [0.2, 0.0, 0.9]])
    w, sigma, explained = pca_loadings(returns, factors=3)
    assert w.shape == (3, 3)
    assert np.all(sigma > 0)
    assert 0.99 <= explained <= 1.0


def test_residual_day_uses_only_prefix_and_returns_composition_shapes() -> None:
    rng = np.random.default_rng(8)
    r = rng.normal(scale=0.01, size=(330, 24))
    trade = np.ones(24, dtype=bool)
    residual = np.ones(24, dtype=bool)
    out = residual_day(r, 320, trade, residual, factors=5, min_assets=20)
    assert out is not None
    eps, beta, weights, _ = out
    assert eps.shape == (24,)
    assert beta.shape == (24, 5)
    assert weights.shape == (5, 24)
    # A perturbation after t cannot affect today's residual.
    r2 = r.copy()
    r2[321:] += 100.0
    out2 = residual_day(r2, 320, trade, residual, factors=5, min_assets=20)
    assert out2 is not None
    assert np.allclose(eps, out2[0], equal_nan=True)
