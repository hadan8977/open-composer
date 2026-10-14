import numpy as np
from hf_models import Moments, hgb, ols, pls_prefix, restored_prediction, ridge_path
from sklearn.cross_decomposition import PLSRegression
from sklearn.linear_model import LinearRegression, Ridge


def fixture():
    rng = np.random.default_rng(501)
    x = rng.normal(size=(220, 12))
    x[:, 1] += 0.7 * x[:, 0]
    y = 0.05 + x @ rng.normal(size=12) + rng.normal(size=220)
    y /= 300
    return x, y


def moments(x, y):
    m = Moments(x.shape[1])
    m.add(x[:70], np.column_stack((y[:70], y[:70])))
    m.add(x[70:], np.column_stack((y[70:], y[70:])))
    return m.standardized(np.arange(x.shape[1]), 0)


def test_pls_all10_prefixes_equal_sklearn():
    x, y = fixture()
    gram, cross, state = moments(x, y)
    xs = (x - state["mean"]) / state["scale"]
    ys = (y - state["target_mean"]) / state["target_scale"]
    for k, beta in enumerate(pls_prefix(gram, cross, 10), 1):
        reference = PLSRegression(n_components=k, scale=False, tol=1e-12).fit(xs, ys)
        expected = reference.predict(xs).reshape(-1) * state["target_scale"] + state["target_mean"]
        np.testing.assert_allclose(
            restored_prediction(x, beta, state), expected, rtol=1e-9, atol=1e-12
        )


def test_ridge_100_lambda_points_use_n_times_lambda_and_normalized_gradient():
    x, y = fixture()
    gram, cross, state = moments(x, y)
    xs = (x - state["mean"]) / state["scale"]
    ys = (y - state["target_mean"]) / state["target_scale"]
    grid = np.linspace(-1, 8, 100)
    for value, beta in zip(grid, ridge_path(gram, cross, grid), strict=True):
        lam = np.exp(value)
        reference = Ridge(alpha=len(x) * lam, fit_intercept=False).fit(xs, ys)
        np.testing.assert_allclose(beta, reference.coef_, rtol=1e-9, atol=1e-12)
        np.testing.assert_allclose(xs.T @ (xs @ beta - ys) / len(x) + lam * beta, 0, atol=1e-12)
    wrong = Ridge(alpha=np.exp(-1), fit_intercept=False).fit(xs, ys)
    assert np.linalg.norm(wrong.coef_ - ridge_path(gram, cross, [-1])[0]) > 0.02


def test_ols_and_target_restoration_match_direct_ols():
    x, y = fixture()
    gram, cross, state = moments(x, y)
    actual = restored_prediction(x, ols(gram, cross), state)
    expected = LinearRegression().fit(x, y).predict(x)
    np.testing.assert_allclose(actual, expected, rtol=1e-10, atol=1e-12)


def test_constant_columns_are_scaled_one_and_coefficient_zero():
    x, y = fixture()
    x[:, 1] = 2
    gram, cross, state = moments(x, y)
    assert state["scale"][1] == 1 and state["constant"][1]
    for beta in pls_prefix(gram, cross, 3) + ridge_path(gram, cross, [-1, 8]):
        assert abs(beta[1]) < 1e-14


def test_hgb_50_150_350_warmstart_has_same_trees_as_cold350():
    x, y = fixture()
    shared = hgb(4, 0.1, 50, warm_start=True).fit(x, y)
    saved = []
    for trees in [50, 150, 350]:
        if trees != 50:
            shared.set_params(max_iter=trees).fit(x, y)
        saved.append(shared.predict(x).copy())
    cold = hgb(4, 0.1, 350).fit(x, y)
    np.testing.assert_array_equal(saved[-1], cold.predict(x))
    assert shared.n_iter_ == 350 and len(shared._predictors) == 350
