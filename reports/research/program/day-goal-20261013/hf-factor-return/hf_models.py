"""Source-normalized linear moments and frozen HGB algorithms (no automatic fits)."""

import numpy as np


class Moments:
    """Incremental raw sufficient statistics, with two common target columns."""

    def __init__(self, p):
        self.n = 0
        self.sx = np.zeros(p)
        self.xx = np.zeros((p, p))
        self.sy = np.zeros(2)
        self.yy = np.zeros(2)
        self.xy = np.zeros((p, 2))

    def add(self, x, y):
        assert x.ndim == 2 and y.shape == (len(x), 2)
        assert np.isfinite(x).all() and np.isfinite(y).all()
        self.n += len(x)
        self.sx += x.sum(axis=0)
        self.xx += x.T @ x
        self.sy += y.sum(axis=0)
        self.yy += np.square(y).sum(axis=0)
        self.xy += x.T @ y

    def standardized(self, columns, target):
        columns = np.asarray(columns)
        mean = self.sx[columns] / self.n
        var = self.xx.diagonal()[columns] / self.n - mean**2
        # Floating cancellation can produce tiny negatives; no outcome-dependent filtering.
        scale = np.sqrt(np.maximum(var, 0))
        constant = scale == 0
        scale[constant] = 1
        ym = self.sy[target] / self.n
        ys = np.sqrt(max(self.yy[target] / self.n - ym**2, 0))
        if ys == 0:
            ys = 1
        gram = self.xx[np.ix_(columns, columns)] / self.n - np.outer(mean, mean)
        gram /= np.outer(scale, scale)
        cross = (self.xy[columns, target] / self.n - mean * ym) / (scale * ys)
        gram[constant, :] = 0
        gram[:, constant] = 0
        cross[constant] = 0
        return (
            gram,
            cross,
            dict(
                mean=mean,
                scale=scale,
                target_mean=ym,
                target_scale=ys,
                constant=constant,
                n_train=self.n,
            ),
        )


def pls_prefix(gram, cross, max_components):
    """PLS1 NIPALS deflation through moments; checked against sklearn scale=False."""
    p = len(cross)
    g, c = gram.copy(), cross.copy()
    rotation = np.eye(p)
    coefficient = np.zeros(p)
    prefixes = []
    for _ in range(max_components):
        norm = np.linalg.norm(c)
        if norm <= np.finfo(float).eps:
            prefixes.append(coefficient.copy())
            continue
        w = c / norm
        gw = g @ w
        tvar = float(w @ gw)
        if tvar <= np.finfo(float).eps:
            prefixes.append(coefficient.copy())
            continue
        loading = gw / tvar
        q = float(w @ c) / tvar
        r = rotation @ w
        coefficient += r * q
        rotation -= np.outer(r, loading)
        c -= q * gw
        g -= np.outer(loading, gw) + np.outer(gw, loading) - tvar * np.outer(loading, loading)
        g = (g + g.T) / 2
        prefixes.append(coefficient.copy())
    return prefixes


def ridge_path(gram, cross, log_lambdas):
    """Objective SSE/n_train + lambda*||beta||^2; eigen solver uses normalized Gram."""
    values, vectors = np.linalg.eigh(gram)
    values = np.maximum(values, 0)
    projected = vectors.T @ cross
    return [vectors @ (projected / (values + np.exp(value))) for value in log_lambdas]


def ols(gram, cross):
    # Numerical rank convention is explicit, with no ridge penalty.
    return np.linalg.lstsq(gram, cross, rcond=None)[0]


def restored_prediction(x, coefficient, state):
    pred = ((x - state["mean"]) / state["scale"]) @ coefficient
    return pred * state["target_scale"] + state["target_mean"]


def hgb(depth, rate, trees, warm_start=False):
    from sklearn.ensemble import HistGradientBoostingRegressor

    return HistGradientBoostingRegressor(
        loss="squared_error",
        learning_rate=rate,
        max_iter=trees,
        max_leaf_nodes=None,
        max_depth=depth,
        min_samples_leaf=20,
        max_bins=255,
        l2_regularization=0,
        early_stopping=False,
        random_state=20261013,
        warm_start=warm_start,
    )


def train_scaling(x, y, block=4096):
    """Train-only scaling without a second full in-RAM X copy."""
    n, p = x.shape
    sx, xx = np.zeros(p), np.zeros(p)
    for start in range(0, n, block):
        part = x[start : start + block]
        sx += part.sum(0)
        xx += np.square(part).sum(0)
    mean = sx / n
    scale = np.sqrt(np.maximum(xx / n - mean**2, 0))
    constant = scale == 0
    scale[constant] = 1
    ys = float(np.std(y, ddof=0))
    return dict(
        mean=mean,
        scale=scale,
        constant=constant,
        target_mean=float(np.mean(y)),
        target_scale=ys if ys > 0 else 1.0,
        n_train=n,
    )
