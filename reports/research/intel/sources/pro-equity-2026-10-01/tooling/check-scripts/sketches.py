import numpy as np, pandas as pd, cvxpy as cp
from sklearn.covariance import LedoitWolf, OAS
from sklearn.decomposition import PCA

rng = np.random.default_rng(0)
T, N, K = 500, 600, 8
R = pd.DataFrame(rng.standard_normal((T, N)) * 0.015)           # daily returns (T x N)

# ---- (1) covariance / risk model --------------------------------------
lw = LedoitWolf().fit(R.values)                                   # linear shrinkage, one line
oas = OAS().fit(R.values)
print("LW shrinkage", round(lw.shrinkage_, 3), "OAS", round(oas.shrinkage_, 3))
pca = PCA(n_components=K).fit(R.values)                           # statistical (PCA) factor model
F = pca.components_.T * np.sqrt(pca.explained_variance_)          # N x K loadings, factor cov = I
resid = R.values - pca.inverse_transform(pca.transform(R.values))
d = resid.var(axis=0, ddof=1)                                     # specific variance, N

# ---- (2) optimizer: neutral book, cap, linear + 3/2 cost, turnover ------
beta = rng.uniform(0.6, 1.5, N); sector = rng.integers(0, 11, N)
S = np.eye(11)[sector]                                            # N x 11 sector one-hot
alpha = rng.standard_normal(N) * 5e-4                             # daily expected return per name
w0 = np.zeros(N)                                                  # previous weights
adv, vol, book = rng.uniform(5e6, 2e8, N), np.full(N, 0.02), 2e7
half_spread, borrow_daily = 5e-4 / 2, 0.03 / 252
hard_to_borrow = rng.random(N) < 0.1                              # not ETB -> long only

w = cp.Variable(N); z = w - w0
impact = cp.sum(cp.multiply(vol * np.sqrt(book / adv), cp.power(cp.abs(z), 1.5)))
risk = cp.sum_squares(F.T @ w) + cp.sum_squares(cp.multiply(np.sqrt(d), w))
obj = cp.Maximize(alpha @ w - 5.0 * risk - half_spread * cp.norm1(z) - impact
                  - borrow_daily * cp.sum(cp.neg(w)))
cons = [cp.sum(w) == 0, beta @ w == 0, S.T @ w == 0,              # dollar-, beta-, sector-neutral
        cp.abs(w) <= 0.02, cp.norm1(w) <= 2.0, cp.norm1(z) <= 0.25,  # cap, gross, turnover limit
        w[np.where(hard_to_borrow)[0]] >= 0]
cp.Problem(obj, cons).solve(solver="CLARABEL")
print("status ok; gross", round(float(np.abs(w.value).sum()), 3), "net", float(w.value.sum()))

# ---- (3) purged / embargoed CPCV ---------------------------------------
from skfolio.model_selection import CombinatorialPurgedCV
H = 5                                                             # label horizon in days
cv = CombinatorialPurgedCV(n_folds=10, n_test_folds=2, purged_size=H, embargo_size=H)
X = pd.DataFrame(rng.standard_normal((1000, 3)))
n_splits = sum(1 for _ in cv.split(X))
print("splits", n_splits, "paths", cv.n_test_paths if hasattr(cv, "n_test_paths") else "?")
