URL: https://raw.githubusercontent.com/Jebel-Quant/shrinkage/main/README.md
FETCHED_UTC: 2026-10-01T06:20:05Z
----
# shrinkage

Linear and nonlinear shrinkage estimators for covariance matrices, following
Ledoit and Wolf.

Sample covariance matrices are noisy when the number of variables is large
relative to the number of observations. Shrinkage pulls the sample estimate
toward a structured target (linear shrinkage) or reshapes its entire eigenvalue
spectrum (nonlinear shrinkage), trading a little bias for a large reduction in
variance and producing a better-conditioned, invertible estimate.

## Installation

```bash +RHIZA_SKIP
pip install git+https://github.com/Jebel-Quant/shrinkage.git
```

## Usage

Both estimators take a raw data matrix of shape `(N, p)` — `N` observations on
`p` variables — and return a `(p, p)` covariance estimator. By default the data
is demeaned and the effective sample size is reduced by one; pass `k=0` to skip
demeaning, or `k=1` if `Y` is already demeaned.

### Linear shrinkage

`cov1para` implements the Ledoit-Wolf (2004) one-parameter estimator, which
shrinks the sample covariance toward a scaled identity (equal variances, zero
covariances):

```pycon
>>> import numpy as np

>>> from shrinkage.linear import cov1para

>>> rng = np.random.default_rng(0)
>>> Y = rng.standard_normal((250, 3))  # 250 observations, 3 variables

>>> estimator = cov1para(Y)
>>> print(estimator.shape)
(3, 3)
>>> print(np.allclose(estimator, estimator.T))  # symmetric
True
```

### Nonlinear shrinkage

`nonlinear_shrinkage` implements the Ledoit-Wolf quadratic-inverse shrinkage
(QIS) estimator. Instead of a single shrinkage intensity it reshapes the whole
eigenvalue spectrum, which is especially effective in the high-dimensional
regime where `p` is comparable to (or larger than) `N`:

```pycon
>>> import numpy as np

>>> from shrinkage.nonlinear import nonlinear_shrinkage

>>> rng = np.random.default_rng(0)
>>> Y = rng.standard_normal((200, 50))  # 200 observations, 50 variables

>>> estimator = nonlinear_shrinkage(Y)
>>> print(estimator.shape)
(50, 50)
>>> print(np.allclose(estimator, estimator.T))  # symmetric
True
```

## Documentation

See the [API reference](https://jebel-quant.github.io/shrinkage/api/) for the
full estimator documentation.

## References and acknowledgements

The estimators follow the work of Olivier Ledoit and Michael Wolf, and are ported
from their reference implementation at
[pald22/covShrinkage](https://github.com/pald22/covShrinkage):

- Ledoit, O. and Wolf, M. (2004). "A well-conditioned estimator for
  large-dimensional covariance matrices." *Journal of Multivariate Analysis*
  (the one-parameter `cov1para` estimator).
- Ledoit, O. and Wolf, M. (2022). "Quadratic shrinkage for large covariance
  matrices." *Bernoulli* (the `nonlinear_shrinkage` / QIS estimator).
