"""D3: a simplified Barra-style equity risk model (design section 6).

Model.  Every session ``t+1`` a weighted cross-sectional regression of close-to-close returns of the
U3000 names on their exposures *at the close of t*::

    r_{i,t+1} = f_mkt + sum_g 1[i in g] f_g + sum_s x_{i,s,t} f_s + e_{i,t+1}

* Weights: ``sqrt(mcap)`` (observation weights of the WLS).
* Industry factors: FF48 merged to ~30 groups (an FF48 industry with fewer than 5 members in
  P1000 on average joins its FF12 parent group).  Cap-weighted industry factor returns sum to
  zero (``sum_g W_g f_g = 0``, ``W_g`` the group's market cap), which identifies the market factor.
* Styles (``STYLES``): ``size`` log mcap; ``beta`` Vasicek-shrunk 252-day beta; ``momentum`` 12-1;
  ``resid_vol`` 63-day idiosyncratic vol; ``liquidity`` log 63-day dollar ADV; ``value``
  book/mcap (``stockholders_equity``); ``profitability`` (``gross_profitability``);
  ``investment`` (``asset_growth``); ``reversal`` 21-day return.  Each is standardised per date:
  z-score (cap-weighted mean, equal-weighted std), clip at +-3, then cap-weighted mean 0 and
  equal-weighted std 1 again.  A missing exposure is set to 0.
* Factor covariance ``F``: uncentred EWMA second moments of the factor returns with Newey-West
  (2 lags); variances use a 126-session half-life, correlations 252.
* Specific variance ``D``: EWMA (63-session half-life) of squared residuals, shrunk 0.3 toward the
  mean of the name's market-cap decile, floored at ``0.1 x`` the cross-sectional median.  A name
  with fewer than 20 residuals takes the decile mean.

Everything stamped at date ``d`` uses data through the close of ``d`` only: exposures at ``d``,
factor returns and residuals realised up to ``d``.  They forecast the sessions after ``d``.

Output (``data/research/equity_book/risk/``)::

    meta.json                       factor list, industry grouping, parameters
    factor_returns_<year>.parquet   trade_date, factor, ret, long
    residuals_<year>.parquet        trade_date, symbol, resid, long (U3000 names)
    exposures_<year>.parquet        Friday / month-end dates: trade_date, symbol, industry, styles,
                                    beta_vasicek, spec_var, mcap, in_p1000
    cov_<year>.parquet              Friday / month-end dates: trade_date, factor_i, factor_j, value

:class:`RiskModel` reads those files: ``at(date) -> (X, F, D)``.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from open_composer.research.equity_book.panel import DEFAULT_DIR

RISK_DIR = DEFAULT_DIR / "risk"
STYLES = [
    "size",
    "beta",
    "momentum",
    "resid_vol",
    "liquidity",
    "value",
    "profitability",
    "investment",
    "reversal",
]
MARKET = "market"
MIN_IND_MEMBERS = 5
STYLE_CLIP = 3.0
HL_VAR = 126.0
HL_CORR = 252.0
HL_SPEC = 63.0
NW_LAGS = 2
SPEC_SHRINK = 0.3
SPEC_FLOOR_FRAC = 0.1
SPEC_MIN_OBS = 20
MIN_FACTOR_OBS = 126
RET_CLIP = 0.5  # |daily return| above this is not used in the regression (bad print)
MIN_NAMES = 300
BETA_HALFLIFE = 63.0  # beta style: exponentially weighted (half-life 63) over a 252-session window
BETA_WINDOW = 252


# ---------------------------------------------------------------------------
# industry grouping
# ---------------------------------------------------------------------------


def ff12_parent(sic_map: pd.DataFrame) -> dict[int, int]:
    """FF12 parent of each FF48 industry: the most frequent FF12 code among its SIC rows."""
    sub = sic_map.dropna(subset=["ff48", "ff12"])
    mode = sub.groupby("ff48")["ff12"].agg(lambda s: int(s.value_counts().idxmax()))
    return {int(k): int(v) for k, v in mode.items()}


def industry_groups(
    p1000_members: pd.Series, parent: dict[int, int], min_members: int = MIN_IND_MEMBERS
) -> dict[int, str]:
    """Map FF48 code -> group name.  ``p1000_members`` is the mean number of P1000 names per
    session indexed by FF48 code (a code absent from the index has 0 members).  An FF48 industry
    with fewer than ``min_members`` joins ``ff12_<parent>``; the others stay ``ff48_<code>``."""
    out: dict[int, str] = {}
    for code in range(1, 49):
        n = float(p1000_members.get(code, 0.0))
        if n >= min_members or code not in parent:
            out[code] = f"ff48_{code:02d}"
        else:
            out[code] = f"ff12_{parent[code]:02d}"
    return out


# ---------------------------------------------------------------------------
# style preparation
# ---------------------------------------------------------------------------


def standardize_style(x: np.ndarray, cap: np.ndarray, clip: float = STYLE_CLIP) -> np.ndarray:
    """Standardise one style on one date.

    1. clip the raw values at their 0.5% / 99.5% quantiles (one wild value must not set the scale);
    2. z-score: cap-weighted mean 0, equal-weighted std 1;
    3. winsorise at +-``clip``;
    4. z-score again (cap-weighted mean 0, equal-weighted std 1).

    A missing exposure becomes 0 (after the standardisation, on the valid names)."""
    x = np.asarray(x, dtype="float64")
    cap = np.asarray(cap, dtype="float64")
    ok = np.isfinite(x) & np.isfinite(cap) & (cap > 0)
    out = np.zeros_like(x)
    if ok.sum() < 3:
        return out

    def z(v: np.ndarray, c: np.ndarray) -> np.ndarray:
        m = float((v * c).sum() / c.sum())
        s = float(v.std(ddof=0))
        return (v - m) / s if s > 0 else v - m

    v = x[ok]
    lo, hi = np.quantile(v, [0.005, 0.995])
    v = z(np.clip(v, lo, hi), cap[ok])
    v = np.clip(v, -clip, clip)
    out[ok] = z(v, cap[ok])
    return out


def vasicek_beta(
    beta: np.ndarray, idio_vol: np.ndarray, cap: np.ndarray, market_var_daily: float
) -> np.ndarray:
    """Vasicek shrinkage of raw 252-day betas toward their cap-weighted cross-sectional mean.

    The sampling variance of beta_i is ``idio_vol_i^2 / (252 var_m)``; the prior variance is the
    cross-sectional variance of the (clipped) betas minus the mean sampling variance (floor 0.05).
    ``w_i = prior / (prior + se_i^2)``; ``beta_v = w b + (1 - w) mean``.  NaN where beta is NaN."""
    b = np.clip(np.asarray(beta, dtype="float64"), -1.0, 4.0)
    ok = np.isfinite(b) & np.isfinite(cap) & (cap > 0)
    out = np.full_like(b, np.nan)
    if ok.sum() < 3:
        return out
    se2 = np.where(np.isfinite(idio_vol), np.asarray(idio_vol, dtype="float64") ** 2, np.nan) / (
        252.0 * max(market_var_daily, 1e-12)
    )
    se2 = np.where(
        np.isfinite(se2), se2, np.nanmedian(se2[ok]) if np.isfinite(se2[ok]).any() else 0.2
    )
    mean = float((b[ok] * cap[ok]).sum() / cap[ok].sum())
    prior = max(float(b[ok].var(ddof=0)) - float(se2[ok].mean()), 0.05)
    w = prior / (prior + se2)
    out[ok] = (w * b + (1.0 - w) * mean)[ok]
    return out


# ---------------------------------------------------------------------------
# cross-sectional regression
# ---------------------------------------------------------------------------


def cross_section_regression(
    y: np.ndarray,
    group: np.ndarray,
    styles: np.ndarray,
    cap: np.ndarray,
    n_groups: int,
) -> tuple[np.ndarray, np.ndarray, float]:
    """One day's constrained WLS.

    ``y`` returns (N), ``group`` industry index 0..n_groups-1 (N), ``styles`` (N, S), ``cap`` market
    cap (N; the WLS observation weights are ``sqrt(cap)``).  Returns ``(f, resid, r2)``, ``f`` of
    length ``1 + n_groups + S`` ordered ``[market, groups..., styles...]``.  Cap-weighted group
    returns satisfy ``sum_g W_g f_g = 0``; a group with no member gets 0.
    """
    n, s = styles.shape
    present = np.unique(group)
    cap_g = np.bincount(group, weights=cap, minlength=n_groups)
    drop = int(present[np.argmax(cap_g[present])])
    free = [g for g in present if g != drop]
    ncol = 1 + len(free) + s
    x = np.zeros((n, ncol))
    x[:, 0] = 1.0
    for k, g in enumerate(free):
        x[:, 1 + k] = (group == g).astype(float)
    is_drop = (group == drop).astype(float)
    for k, g in enumerate(free):
        x[:, 1 + k] -= (cap_g[g] / cap_g[drop]) * is_drop
    x[:, 1 + len(free) :] = styles
    sw = np.sqrt(np.sqrt(cap))  # sqrt of the observation weights sqrt(cap)
    theta, *_ = np.linalg.lstsq(x * sw[:, None], y * sw, rcond=None)
    f = np.zeros(1 + n_groups + s)
    f[0] = theta[0]
    for k, g in enumerate(free):
        f[1 + g] = theta[1 + k]
    f[1 + drop] = -sum(cap_g[g] / cap_g[drop] * theta[1 + k] for k, g in enumerate(free))
    f[1 + n_groups :] = theta[1 + len(free) :]
    xfull = np.zeros((n, 1 + n_groups + s))
    xfull[:, 0] = 1.0
    xfull[np.arange(n), 1 + group] = 1.0
    xfull[:, 1 + n_groups :] = styles
    resid = y - xfull @ f
    w_obs = np.sqrt(cap)
    ybar = float((w_obs * y).sum() / w_obs.sum())
    ss_tot = float((w_obs * (y - ybar) ** 2).sum())
    r2 = 1.0 - float((w_obs * resid**2).sum()) / ss_tot if ss_tot > 0 else float("nan")
    return f, resid, r2


# ---------------------------------------------------------------------------
# covariances
# ---------------------------------------------------------------------------


def ewma_cov_nw(f: np.ndarray, halflife: float, lags: int = NW_LAGS) -> np.ndarray:
    """Uncentred EWMA second-moment matrix of ``f`` (rows = sessions, last row newest) with a
    Newey-West (Bartlett) correction of ``lags`` lags.  Weights ``0.5 ** (age / halflife)``,
    normalised to sum to one."""
    t_n = f.shape[0]
    w = 0.5 ** ((t_n - 1 - np.arange(t_n)) / halflife)
    w /= w.sum()
    out = (f * w[:, None]).T @ f
    for lag in range(1, lags + 1):
        g = (f[lag:] * w[lag:, None]).T @ f[:-lag]
        out = out + (1.0 - lag / (lags + 1.0)) * (g + g.T)
    return out


def factor_covariance(
    f: np.ndarray,
    hl_var: float = HL_VAR,
    hl_corr: float = HL_CORR,
    lags: int = NW_LAGS,
) -> np.ndarray:
    """``F = diag(sd) C diag(sd)``: variances from the ``hl_var`` EWMA, correlations from the
    ``hl_corr`` EWMA (both Newey-West), correlation matrix made positive semi-definite.  A factor
    with no variance (an industry that never had members) gets zero variance and zero
    correlation."""
    k = f.shape[1]
    s_var = ewma_cov_nw(f, hl_var, lags)
    g0 = ewma_cov_nw(f, hl_var, 0)
    var = np.maximum(np.diag(s_var), 0.5 * np.diag(g0))  # NW cannot shrink a variance below half
    sd = np.sqrt(np.maximum(var, 0.0))
    s_corr = ewma_cov_nw(f, hl_corr, lags)
    d = np.sqrt(np.maximum(np.diag(s_corr), 0.0))
    live = (d > 1e-14) & (sd > 0)
    c = np.eye(k)
    if live.any():
        idx = np.flatnonzero(live)
        sub = s_corr[np.ix_(idx, idx)] / np.outer(d[idx], d[idx])
        sub = (sub + sub.T) / 2.0
        vals, vecs = np.linalg.eigh(sub)
        vals = np.clip(vals, 1e-6, None)
        sub = (vecs * vals) @ vecs.T
        dd = np.sqrt(np.diag(sub))
        sub = sub / np.outer(dd, dd)
        c[np.ix_(idx, idx)] = sub
    return (sd[:, None] * c) * sd[None, :]


class SpecificVariance:
    """Incremental EWMA of squared residuals for every symbol column."""

    def __init__(self, n_symbols: int, halflife: float = HL_SPEC) -> None:
        self.lam = 0.5 ** (1.0 / halflife)
        self.num = np.zeros(n_symbols)
        self.den = np.zeros(n_symbols)
        self.count = np.zeros(n_symbols, dtype=np.int64)

    def update(self, cols: np.ndarray, resid: np.ndarray) -> None:
        self.num *= self.lam
        self.den *= self.lam
        self.num[cols] += resid**2
        self.den[cols] += 1.0
        self.count[cols] += 1

    def raw(self, cols: np.ndarray) -> np.ndarray:
        d = self.den[cols]
        out = np.where(d > 0, self.num[cols] / np.where(d > 0, d, 1.0), np.nan)
        return np.where(self.count[cols] >= SPEC_MIN_OBS, out, np.nan)


def shrink_specific(
    raw: np.ndarray,
    cap: np.ndarray,
    shrink: float = SPEC_SHRINK,
    floor_frac: float = SPEC_FLOOR_FRAC,
) -> np.ndarray:
    """Shrink raw specific variances 0.3 toward the mean of their market-cap decile, floor at
    ``floor_frac`` x the cross-sectional median.  A NaN raw value takes the decile mean."""
    n = len(raw)
    order = np.argsort(np.argsort(cap, kind="stable"), kind="stable")
    decile = np.minimum((order * 10) // max(n, 1), 9)
    out = np.empty(n)
    glob = float(np.nanmean(raw)) if np.isfinite(raw).any() else 1e-4
    for d in range(10):
        m = decile == d
        if not m.any():
            continue
        r = raw[m]
        mean = float(np.nanmean(r)) if np.isfinite(r).any() else glob
        out[m] = np.where(np.isfinite(r), (1.0 - shrink) * r + shrink * mean, mean)
    med = float(np.nanmedian(out)) if np.isfinite(out).any() else 1e-4
    return np.maximum(out, floor_frac * med)


# ---------------------------------------------------------------------------
# reader
# ---------------------------------------------------------------------------


@dataclass
class RiskModel:
    """Reader of the saved model.  ``at(date) -> (X, F, D)`` for a saved date (every Friday /
    last-session-of-week and every month-end); a date between saved dates uses the latest saved
    date before it (``exact=True`` raises instead)."""

    base: Path = RISK_DIR

    def __post_init__(self) -> None:
        self.base = Path(self.base)
        self.meta = json.loads((self.base / "meta.json").read_text())
        self.factors: list[str] = list(self.meta["factors"])
        self.groups: list[str] = list(self.meta["groups"])
        self._exp: dict[int, pd.DataFrame] = {}
        self._cov: dict[int, pd.DataFrame] = {}

    def _year(self, kind: str, year: int) -> pd.DataFrame:
        cache = self._exp if kind == "exposures" else self._cov
        if year not in cache:
            cache.clear()
            cache[year] = pd.read_parquet(self.base / f"{kind}_{year}.parquet")
        return cache[year]

    def saved_dates(self, year: int) -> pd.DatetimeIndex:
        e = self._year("exposures", year)
        return pd.DatetimeIndex(sorted(e["trade_date"].unique()))

    def resolve(self, date: pd.Timestamp | str, exact: bool = False) -> pd.Timestamp:
        """The saved date used for ``date``: ``date`` itself or the latest saved date before it."""
        d = pd.Timestamp(date)
        use = self._saved_before(d.year, d)
        if len(use) == 0 and not exact:
            # early January: no saved date yet this year, fall back to the previous year's last one
            use = self._saved_before(d.year - 1, d)
        if len(use) == 0 or (exact and use[-1] != d):
            raise KeyError(f"no saved risk model for {d.date()}")
        return use[-1]

    def _saved_before(self, year: int, d: pd.Timestamp) -> pd.DatetimeIndex:
        if not (self.base / f"exposures_{year}.parquet").exists():
            return pd.DatetimeIndex([])
        dates = self.saved_dates(year)
        return dates[dates <= d]

    def at(
        self, date: pd.Timestamp | str, exact: bool = False
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
        """``(X, F, D)``: exposures ``X`` (N x K, columns ``self.factors``), factor covariance ``F``
        (K x K) and specific variances ``D`` (N), all daily variance units."""
        d = self.resolve(date, exact)
        e = self._year("exposures", d.year)
        e = e[e["trade_date"] == d].set_index("symbol")
        x = pd.DataFrame(0.0, index=e.index, columns=self.factors)
        x[MARKET] = 1.0
        for g in self.groups:
            x[g] = (e["industry"] == g).astype(float)
        for s in STYLES:
            x[s] = e[s]
        cv = self._year("cov", d.year)
        cv = cv[cv["trade_date"] == d]
        f = cv.pivot(index="factor_i", columns="factor_j", values="value").reindex(
            index=self.factors, columns=self.factors
        )
        return x, f, e["spec_var"].rename("spec_var")

    def caps(self, date: pd.Timestamp | str) -> pd.Series:
        """Market caps of the names in ``at(date)`` (the U3000 cohort of that session)."""
        d = self.resolve(date)
        e = self._year("exposures", d.year)
        return e[e["trade_date"] == d].set_index("symbol")["mcap"]

    def predicted_beta(self, date: pd.Timestamp | str, method: str = "ewma") -> pd.Series:
        """Predicted beta of each name at the saved date.

        ``"ewma"`` (default): the exponentially weighted (half-life 63) 252-session time-series beta
        to SPY, clipped to [-1, 4] (``beta_ewma``); ``"vasicek"``: the same shrunk toward the
        cross-sectional mean (``beta_vasicek``, the beta style exposure before standardisation);
        ``"model"``: the factor-model implied beta to the cap-weighted U3000 portfolio,
        ``x_i' F x_m / (x_m' F x_m + sum w_i^2 D_i)``."""
        if method in ("ewma", "vasicek"):
            d = self.resolve(date)
            e = self._year("exposures", d.year)
            e = e[e["trade_date"] == d].set_index("symbol")
            col = "beta_ewma" if method == "ewma" else "beta_vasicek"
            return e[col].rename("beta_pred")
        if method != "model":
            raise ValueError(f"unknown beta method {method!r}")
        x, f, dvar = self.at(date)
        cap = self.caps(date).reindex(x.index).to_numpy()
        w = cap / cap.sum()
        xm = x.to_numpy().T @ w
        fm = f.to_numpy() @ xm
        var_m = float(xm @ fm + (w**2 * dvar.to_numpy()).sum())
        return pd.Series(x.to_numpy() @ fm / var_m, index=x.index, name="beta_pred")


def portfolio_variance(w: pd.Series, x: pd.DataFrame, f: pd.DataFrame, d: pd.Series) -> float:
    """``w'(X F X' + diag(D))w`` for weights aligned on the names of ``x`` (names missing from the
    model are ignored: callers must decide how to treat them)."""
    w = w.reindex(x.index).fillna(0.0).to_numpy()
    xw = x.to_numpy().T @ w
    return float(xw @ f.to_numpy() @ xw + (w**2 * d.reindex(x.index).to_numpy()).sum())


def factor_names(groups: Sequence[str]) -> list[str]:
    return [MARKET, *groups, *STYLES]


def ewma_beta(
    close: np.ndarray,
    pos: int,
    cols: np.ndarray,
    market_ret: np.ndarray,
    halflife: float = 63.0,
    window: int = 252,
    min_frac: float = 0.6,
) -> np.ndarray:
    """Exponentially weighted time-series beta of each column to ``market_ret`` over the ``window``
    sessions ending at ``pos`` (close to close, no padding across holes; a day with a missing return
    drops out of both the weights and the moments).  ``market_ret[i]`` is the market return of
    session ``i``.  NaN when fewer than ``min_frac * window`` valid days."""
    lo = pos - window
    if lo < 0:
        return np.full(len(cols), np.nan)
    c = close[lo : pos + 1][:, cols]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = c[1:] / c[:-1] - 1.0
    m = market_ret[lo + 1 : pos + 1]
    ok = np.isfinite(r) & np.isfinite(m)[:, None]
    age = np.arange(window - 1, -1, -1, dtype="float64")
    w = (0.5 ** (age / halflife))[:, None] * ok
    sw = w.sum(0)
    r0 = np.where(ok, r, 0.0)
    m0 = np.where(ok, m[:, None], 0.0)
    swn = np.where(sw > 0, sw, 1.0)
    ex, ey = (w * r0).sum(0) / swn, (w * m0).sum(0) / swn
    cov = (w * r0 * m0).sum(0) / swn - ex * ey
    var = (w * m0 * m0).sum(0) / swn - ey * ey
    with np.errstate(invalid="ignore", divide="ignore"):
        beta = np.where(var > 0, cov / var, np.nan)
    return np.where(ok.sum(0) >= min_frac * window, beta, np.nan)
