"""D5: the single-period portfolio optimizer of the equity book (design section 8).

Problem (weights ``w`` are fractions of equity ``E``; ``w0`` the *drifted* current weights)::

    max_w   alpha'w  -  kappa * [ sum_i hs_i |dw_i| + sum_i imp_i |dw_i|^1.5
                                   + sum_i borrow_i max(-w_i, 0) h/252 ]
    s.t.    annualised ex-ante vol <= sigma            (a constraint, not a penalty; no gamma)
            sum w = 0                                   (stocks plus hedge ETFs; T-bill sleeve is
                                                         set separately to 1.0 by ``make_decide``)
            |beta'w| <= 0.02,   |X_ind'w| <= 0.01 per industry,   |X_size'w| <= 0.10,
            |X_style'w| <= 0.25 (other styles),   |w_i| <= 0.01 (stocks),   sum|w| <= 1.0
            w_i < 0 only if i in SE_t (stocks) or i is a hedge ETF  (config B: ETFs only)
            short stocks need price <= 0.01 E  (whole-share rule, E = account equity parameter)
            |dw_i| E_cap <= 0.01 dollar_adv_21_i       (participation, E_cap = $1,000,000)

Units and horizons (all stated once, here).

* ``alpha_i = IC * sigma_res_i * score_i`` (Grinold-Kahn), ``sigma_res_i = sqrt(h * D_i)`` is the
  ``h = 21``-session residual volatility, ``D_i`` the *daily* specific variance of the risk model,
  ``score_i`` a standardised score (rank-normal, unit variance).  ``alpha`` is therefore an
  expected return over the next 21 sessions.
* Risk is in daily variance units: ``var_daily = y'Fy + sum_i D_i w_i^2`` with ``y = X'w``.  The
  annual volatility is ``sqrt(252 * var_daily)``; the constraint is ``sqrt(252 * var_daily) <=
  sigma_annual`` (default 5%), implemented as the second-order cone
  ``||[L'X'w ; sqrt(D) w]||_2 <= sigma_annual / sqrt(252)`` with ``F = L L'`` (no N x N matrix).
* Costs are one-sided trade costs of the rebalance (21-day alpha horizon: each name is assumed
  held for the horizon), in return units.  ``hs_i`` is the half spread in basis points from
  ``costs.half_spread_bp`` with the snapshot matching the execution price (open -> ``open``,
  close -> ``close``).  ``imp_i`` is the square-root law written for weights: cost in dollars
  ``|Q| * Y sigma sqrt(|Q| / V)`` with ``Q = |dw| E_cap`` gives
  ``Y sigma_i sqrt(E_cap / V_i) |dw|^1.5`` of equity.  Borrow ``borrow_i`` (bp/year, 25 for
  easy-to-borrow stocks, 0 for ETFs) is charged for ``h/252`` of a year.
  ``kappa`` (default 1.0) scales *all* cost terms in the objective: ``kappa > 1`` makes the
  optimizer trade less than the modelled cost implies (a turnover-damping knob that is *not*
  charged in the backtest, which always books the true cost through ``costfn.make_cost_fn``);
  ``kappa = 0`` removes costs and the ``|dw|`` machinery.
* ``impact_mode="exact"`` keeps the 3/2 power in the objective (power cone / SOC).  The documented
  fast option ``"quadratic_ub"`` replaces ``x^1.5`` by its tangent-at-``x = ref`` quadratic upper
  bound ``x^2/(2 s) + s x/2`` (``s = sqrt(ref)``, ``ref = impact_ref_dw``), a convex upper bound
  that is tight at ``|dw| = ref``.
* Internally the variable is ``v = 100 w`` (percent of equity) and the objective is in basis
  points of equity, for conditioning.  Results are converted back to fractions.

Speed.  Per date the universe is pre-filtered to the current holdings (that exist in the risk
model), the names with ``|score|`` in the top ``tail_frac`` (35%) of each tail (the short tail
only counts names that may be shorted), and the hedge ETFs (about 2,200 names for U3000).  The
problem is rebuilt for each date (its size changes with the held set, so a fixed-shape DPP
problem does not apply without padding; compile time is reported separately from solve time).

Failure.  A failed first solve is retried down a ladder (Clarabel with ``max_iter`` 2000, Clarabel
with tolerances 1e-6, SCS; ``OptConfig.retry_ladder``; ``SolveResult.attempt`` says which step
won).  If every step fails (solver error, an infeasible/unbounded status, a non-finite or
constraint-violating result) the result is ``w0`` (``SolveResult.ok = False``, reason logged);
``BookDecider`` then returns ``None`` (no trade, the
dollar holdings stay at ``w0``) unless the book is empty.  The failure rate is tracked.

Names of the current book that the risk model cannot see on the decision date (left the
U3000, no exposures) cannot enter the optimisation and are closed (``forced_exits``).
"""

from __future__ import annotations

import resource
import time
import warnings
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from typing import Any, Literal

import cvxpy as cp
import numpy as np
import pandas as pd
import scipy.sparse as sp

from open_composer.research.equity_book.backtest import TBILL, BookConfig, BookState
from open_composer.research.equity_book.borrow import (
    RS_WINDOW,
    detect_reverse_splits,
    short_eligible,
)
from open_composer.research.equity_book.costfn import make_cost_fn, snapshot_for
from open_composer.research.equity_book.costs import (
    BORROW_BP_PER_YEAR_BASE,
    IMPACT_Y,
    half_spread_bp,
    load_model,
)
from open_composer.research.equity_book.etf_risk import ETFRisk
from open_composer.research.equity_book.panel import PanelAttributes, PricePanel
from open_composer.research.equity_book.risk import (
    MARKET,
    STYLES,
    RiskModel,
    ewma_beta,
)

TRADING_DAYS = 252
SCALE = 100.0  # internal variable v = SCALE * w (percent of equity)
BP = 1e4
TBILL_SYMBOLS = frozenset({"SGOV", "BIL", "SHY"})
BETA_METHODS = ("ewma", "vasicek", "model", "ewma21")
DEFAULT_IC = 0.03
ETF_HALF_SPREAD_BP = 1.0
OK_STATUSES = ("optimal", "optimal_inaccurate")
CLEAN_TOL = 1e-6  # weights closer than this to w0 (or to 0) are snapped (interior-point dust)
TOL = 1e-5  # constraint-check tolerance in weight units


# ---------------------------------------------------------------------------
# configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class OptConfig:
    """Parameters of the single-period problem.  ``None`` disables a constraint."""

    sigma_annual: float | None = 0.05
    horizon_days: int = 21
    ic: float = DEFAULT_IC
    kappa: float = 1.0
    beta_cap: float | None = 0.02
    beta_method: str = "ewma"
    industry_cap: float | None = 0.01
    size_cap: float | None = 0.10
    style_cap: float | None = 0.25
    name_cap: float | None = 0.01
    etf_cap: float = 0.5
    gross_cap: float | None = 1.0
    dollar_neutral: bool = True
    allow_stock_shorts: bool = True
    equity: float = 100_000.0  # whole-share rule: short price <= 0.01 * equity
    e_cap: float = 1_000_000.0  # participation and impact
    participation: float | None = 0.01
    snapshot: str = "close"
    impact_y: float = IMPACT_Y
    impact_mode: Literal["exact", "quadratic_ub"] = "exact"
    impact_ref_dw: float = 0.003
    borrow_bp: float = BORROW_BP_PER_YEAR_BASE
    etf_half_spread_bp: float = ETF_HALF_SPREAD_BP
    tail_frac: float = 0.35
    solver: str = "CLARABEL"
    max_iter: int = 200
    clean_tol: float = CLEAN_TOL
    # robust solve path: retry a failed first attempt (exception, status outside OK_STATUSES,
    # non-finite weights or a violated constraint) down a fixed ladder
    retry_ladder: bool = True
    retry_max_iter: int = 2000  # attempt 1: Clarabel with more iterations
    retry_relaxed_tol: float = 1e-6  # attempt 2: Clarabel tol_gap_abs/tol_gap_rel/tol_feas
    retry_scs_max_iters: int = 20000  # attempt 3: SCS
    retry_scs_eps: float = 1e-5
    max_violation_tol: float | None = 1e-4  # accepted solutions above this count as failures

    def with_(self, **kw: Any) -> OptConfig:
        return replace(self, **kw)


@dataclass(frozen=True)
class BookSpec:
    """A configuration of the book: A (U3000, stock shorts in SE_t plus ETF shorts), B (U3000,
    shorts in ETFs only), C (P1000 only, stock shorts in SE_t plus ETFs)."""

    name: Literal["A", "B", "C"] = "A"
    opt: OptConfig = field(default_factory=OptConfig)

    def __post_init__(self) -> None:
        if self.name not in ("A", "B", "C"):
            raise ValueError("BookSpec.name must be 'A', 'B' or 'C'")

    @property
    def universe_col(self) -> str:
        return "in_p1000" if self.name == "C" else "in_u3000"

    @property
    def allow_stock_shorts(self) -> bool:
        return self.name != "B" and self.opt.allow_stock_shorts

    @property
    def borrow_bp_per_year(self) -> float:
        """Value for ``BookConfig.borrow_bp_per_year``: the backtest charges one rate on all short
        notional, so ETF shorts (borrow 0 in reality) are slightly overcharged in A and C."""
        return 0.0 if self.name == "B" else self.opt.borrow_bp


# ---------------------------------------------------------------------------
# problem data
# ---------------------------------------------------------------------------


@dataclass
class ProblemData:
    """Arrays of one date's problem (``n`` assets, ``K`` factors).  All weights are fractions of E.

    ``alpha`` is the expected 21-session return per unit weight (return units); ``lo``/``hi`` are
    the per-asset bounds on ``w`` (``+-inf`` = none), already intersected with participation;
    ``half_spread_bp``/``impact_coef_bp`` (bp of equity per ``|dw|`` and per ``|dw|^1.5``) and
    ``borrow_bp_yr`` are cost inputs; ``ind_idx``, ``style_idx`` index columns of ``x``;
    ``style_caps`` the cap of each style column."""

    names: list[str]
    alpha: np.ndarray
    w0: np.ndarray
    x: np.ndarray
    f: np.ndarray
    d: np.ndarray
    beta: np.ndarray
    half_spread_bp: np.ndarray
    impact_coef_bp: np.ndarray
    borrow_bp_yr: np.ndarray
    lo: np.ndarray
    hi: np.ndarray
    ind_idx: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    style_idx: np.ndarray = field(default_factory=lambda: np.array([], dtype=int))
    style_caps: np.ndarray = field(default_factory=lambda: np.array([], dtype="float64"))
    is_etf: np.ndarray | None = None

    @property
    def n(self) -> int:
        return len(self.names)


@dataclass
class SolveResult:
    w: np.ndarray
    ok: bool
    status: str
    build_s: float
    solve_s: float
    objective_bp: float = float("nan")
    reason: str = ""
    max_violation: float = float("nan")
    solver_s: float = float("nan")  # the interior-point time alone (``solve_s`` adds the compile)
    attempt: int = 0  # ladder step that produced the result (0 = first solve; on failure the last
    # step tried); see ``SOLVE_ATTEMPTS``
    attempt_log: tuple[str, ...] = ()  # one "<label>:<status>" entry per attempt tried
    iters: int = -1  # solver iterations of the accepted attempt (-1 if unknown)

    @property
    def total_s(self) -> float:
        return self.build_s + self.solve_s


def factor_cholesky(f: np.ndarray, rel_tol: float = 1e-12) -> np.ndarray:
    """``L`` with ``F = L L'`` from a clipped eigendecomposition (columns of null directions are
    dropped).  ``F`` is symmetrised first."""
    fs = (f + f.T) / 2.0
    vals, vecs = np.linalg.eigh(fs)
    keep = vals > rel_tol * max(float(vals.max()), 1e-300)
    return vecs[:, keep] * np.sqrt(vals[keep])


def ex_ante_vol_annual(data: ProblemData, w: np.ndarray) -> float:
    """``sqrt(252 (y'Fy + sum D w^2))`` of ``w`` under the problem's risk model."""
    y = data.x.T @ w
    var = float(y @ data.f @ y + (data.d * w * w).sum())
    return float(np.sqrt(max(TRADING_DAYS * var, 0.0)))


def exposures(data: ProblemData, w: np.ndarray) -> np.ndarray:
    """Factor exposures ``X'w`` (length K)."""
    return data.x.T @ w


def constraint_violations(data: ProblemData, w: np.ndarray, cfg: OptConfig) -> dict[str, float]:
    """Largest violation of each active constraint (<= 0 means satisfied; weight units except
    ``vol`` which is annual vol minus the budget)."""
    out: dict[str, float] = {}
    if cfg.dollar_neutral:
        out["dollar_neutral"] = abs(float(w.sum()))
    if cfg.beta_cap is not None:
        out["beta"] = abs(float(data.beta @ w)) - cfg.beta_cap
    y = exposures(data, w)
    if cfg.industry_cap is not None and len(data.ind_idx):
        out["industry"] = float(np.abs(y[data.ind_idx]).max()) - cfg.industry_cap
    if len(data.style_idx):
        out["style"] = float((np.abs(y[data.style_idx]) - data.style_caps).max())
    if cfg.gross_cap is not None:
        out["gross"] = float(np.abs(w).sum()) - cfg.gross_cap
    finite_lo, finite_hi = np.isfinite(data.lo), np.isfinite(data.hi)
    if finite_lo.any():
        out["lower_bound"] = float((data.lo - w)[finite_lo].max())
    if finite_hi.any():
        out["upper_bound"] = float((w - data.hi)[finite_hi].max())
    if cfg.sigma_annual is not None:
        out["vol"] = ex_ante_vol_annual(data, w) - cfg.sigma_annual
    return out


def max_violation(data: ProblemData, w: np.ndarray, cfg: OptConfig) -> float:
    v = constraint_violations(data, w, cfg)
    vol = v.pop("vol", 0.0) / max(cfg.sigma_annual or 1.0, 1e-12)  # relative
    return float(max([*v.values(), vol, 0.0]))


# ---------------------------------------------------------------------------
# solve
# ---------------------------------------------------------------------------


def _clean(w: np.ndarray, w0: np.ndarray, tol: float) -> np.ndarray:
    w = np.where(np.abs(w - w0) < tol, w0, w)
    return np.where(np.abs(w) < tol, 0.0, w)


SOLVE_ATTEMPTS = ("first", "clarabel_max_iter", "clarabel_relaxed", "scs")


def _attempt_plan(cfg: OptConfig) -> list[tuple[str, dict[str, Any]]]:
    """``(solver name, solver options)`` for ladder steps 0..3 (steps 1..3 only if enabled).

    Clarabel option names (cvxpy 1.9.3 passes them to ``clarabel.DefaultSettings``): ``max_iter``,
    ``tol_gap_abs``, ``tol_gap_rel``, ``tol_feas`` (defaults 1e-8).  SCS: ``max_iters``, ``eps``."""
    plan: list[tuple[str, dict[str, Any]]] = [(cfg.solver, {"max_iter": cfg.max_iter})]
    if cfg.retry_ladder:
        tol = cfg.retry_relaxed_tol
        plan += [
            ("CLARABEL", {"max_iter": cfg.retry_max_iter}),
            (
                "CLARABEL",
                {
                    "max_iter": cfg.retry_max_iter,
                    "tol_gap_abs": tol,
                    "tol_gap_rel": tol,
                    "tol_feas": tol,
                },
            ),
            ("SCS", {"max_iters": cfg.retry_scs_max_iters, "eps": cfg.retry_scs_eps}),
        ]
    return plan


def solve(data: ProblemData, cfg: OptConfig | None = None) -> SolveResult:
    """Solve one problem.  A first attempt that raises, ends outside ``OK_STATUSES``, returns
    non-finite weights or violates a constraint by more than ``cfg.max_violation_tol`` is retried
    down the ladder in :func:`_attempt_plan` (``cfg.retry_ladder``).  If every attempt fails the
    result carries ``w0`` with ``ok=False`` and the reasons; ``attempt`` records the step that
    succeeded (or the last step tried), ``attempt_log`` the status of each step."""
    cfg = cfg or OptConfig()
    t0 = time.perf_counter()
    n = data.n
    if n == 0:
        return SolveResult(np.zeros(0), True, "empty", 0.0, 0.0)
    try:
        prob, v = _build(data, cfg)
    except Exception as exc:  # pragma: no cover - defensive
        return SolveResult(
            data.w0.copy(), False, "build_error", time.perf_counter() - t0, 0.0, reason=repr(exc)
        )
    t1 = time.perf_counter()
    log: list[str] = []
    reasons: list[str] = []
    status = "solver_error"
    k = 0
    for k, (solver_name, opts) in enumerate(_attempt_plan(cfg)):
        label = SOLVE_ATTEMPTS[k]
        try:
            solver = getattr(cp, solver_name)
        except AttributeError as exc:  # unknown solver name: a configuration error, no retry
            log.append(f"{label}:solver_error")
            return SolveResult(
                data.w0.copy(),
                False,
                "solver_error",
                t1 - t0,
                time.perf_counter() - t1,
                reason=repr(exc),
                attempt=k,
                attempt_log=tuple(log),
            )
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Solution may be inaccurate")
                prob.solve(solver=solver, verbose=False, **opts)
        except Exception as exc:
            status = "solver_error"
            log.append(f"{label}:solver_error")
            reasons.append(f"{label}: {exc!r}")
            continue
        status = str(prob.status)
        log.append(f"{label}:{status}")
        if status not in OK_STATUSES or v.value is None or not np.isfinite(v.value).all():
            reasons.append(f"{label}: status {status}")
            continue
        w = _clean(np.asarray(v.value, dtype="float64") / SCALE, data.w0, cfg.clean_tol)
        viol = max_violation(data, w, cfg)
        if cfg.max_violation_tol is not None and not viol <= cfg.max_violation_tol:
            reasons.append(f"{label}: max_violation {viol:.3g}")
            status = "violation"
            continue
        stats = prob.solver_stats
        s_time = float(stats.solve_time) if stats is not None and stats.solve_time else float("nan")
        return SolveResult(
            w,
            True,
            status,
            t1 - t0,
            time.perf_counter() - t1,
            float(prob.value),
            "",
            viol,
            s_time,
            attempt=k,
            attempt_log=tuple(log),
            iters=int(stats.num_iters) if stats is not None and stats.num_iters else -1,
        )
    return SolveResult(
        data.w0.copy(),
        False,
        status,
        t1 - t0,
        time.perf_counter() - t1,
        reason="; ".join(reasons),
        attempt=k,
        attempt_log=tuple(log),
    )


def _build(data: ProblemData, cfg: OptConfig) -> tuple[cp.Problem, cp.Variable]:
    n = data.n
    v = cp.Variable(n)
    w0s = data.w0 * SCALE
    cons: list[Any] = []
    lo_f, hi_f = np.isfinite(data.lo), np.isfinite(data.hi)
    if lo_f.any():
        idx = np.flatnonzero(lo_f)
        cons.append(v[idx] >= data.lo[idx] * SCALE)
    if hi_f.any():
        idx = np.flatnonzero(hi_f)
        cons.append(v[idx] <= data.hi[idx] * SCALE)

    # risk: a second-order-cone constraint, no N x N matrix
    if cfg.sigma_annual is not None:
        chol = factor_cholesky(data.f)
        m = chol.T @ data.x.T  # (K', n)
        risk_vec = cp.hstack([m @ v, cp.multiply(np.sqrt(data.d), v)])
        cons.append(cp.norm(risk_vec, 2) <= cfg.sigma_annual / np.sqrt(TRADING_DAYS) * SCALE)

    if cfg.dollar_neutral:
        cons.append(cp.sum(v) == 0)
    if cfg.beta_cap is not None:
        cons.append(cp.abs(data.beta @ v) <= cfg.beta_cap * SCALE)
    if cfg.industry_cap is not None and len(data.ind_idx):
        xi = sp.csr_matrix(data.x[:, data.ind_idx].T)
        cons.append(cp.abs(xi @ v) <= cfg.industry_cap * SCALE)
    if len(data.style_idx):
        xs = data.x[:, data.style_idx].T
        cons.append(cp.abs(xs @ v) <= data.style_caps * SCALE)
    if cfg.gross_cap is not None:
        cons.append(cp.norm1(v) <= cfg.gross_cap * SCALE)

    obj = (data.alpha * BP / SCALE) @ v
    if cfg.kappa > 0.0:
        u = cp.Variable(n, nonneg=True)  # |dv|
        cons += [u >= v - w0s, u >= w0s - v]
        cost = (data.half_spread_bp / SCALE) @ u
        imp = np.flatnonzero(data.impact_coef_bp > 0)
        if len(imp):
            if cfg.impact_mode == "exact":
                coef = data.impact_coef_bp[imp] / SCALE**1.5
                cost = cost + coef @ cp.power(u[imp], 1.5)
            else:  # quadratic upper bound of x^1.5 on x = u / SCALE, tight at x = ref
                s = np.sqrt(cfg.impact_ref_dw)
                c = data.impact_coef_bp[imp]
                cost = (
                    cost
                    + (c / (2.0 * s * SCALE**2)) @ cp.square(u[imp])
                    + (c * s / (2.0 * SCALE)) @ u[imp]
                )
        sh = np.flatnonzero((data.lo < 0) & (data.borrow_bp_yr > 0))
        if len(sh):
            sv = cp.Variable(len(sh), nonneg=True)
            cons.append(sv >= -v[sh])
            cost = cost + (data.borrow_bp_yr[sh] * cfg.horizon_days / TRADING_DAYS / SCALE) @ sv
        obj = obj - cfg.kappa * cost
    return cp.Problem(cp.Maximize(obj), cons), v


# ---------------------------------------------------------------------------
# alpha helpers
# ---------------------------------------------------------------------------


def alpha_from_scores(
    score: np.ndarray, spec_var_daily: np.ndarray, ic: float = DEFAULT_IC, horizon: int = 21
) -> np.ndarray:
    """Grinold-Kahn: ``IC * sqrt(horizon * D_i) * score_i`` (expected ``horizon``-session
    return per unit weight)."""
    return ic * np.sqrt(horizon * np.asarray(spec_var_daily, dtype="float64")) * score


def rank_normal(x: pd.Series) -> pd.Series:
    """Rank-normal transform within the series: ``Phi^-1((rank - 0.5) / n)``; NaN stays NaN."""
    from statistics import NormalDist

    s = x.dropna()
    if s.empty:
        return x.astype("float64")
    r = s.rank(method="average")
    inv = NormalDist().inv_cdf
    z = pd.Series([inv((float(k) - 0.5) / len(s)) for k in r], index=s.index)
    return z.reindex(x.index)


def trailing_rank_ic(
    scores: pd.DataFrame,
    fwd_returns: pd.DataFrame,
    asof: pd.Timestamp | str,
    *,
    months: int = 36,
    horizon: int = 21,
    prior: float = DEFAULT_IC,
    weight_realized: float = 0.5,
    min_dates: int = 6,
) -> float:
    """Trailing realized rank IC shrunk toward ``prior``.

    ``scores`` and ``fwd_returns`` are dates x symbols; ``fwd_returns.loc[d]`` is the ``horizon``-
    session forward return from ``d``.  Only dates ``d`` with ``d <= asof`` shifted back by
    ``horizon`` sessions (the forward window has closed by ``asof``) and within the last
    ``months`` calendar months are used.  The IC of each date is the Spearman correlation (Pearson
    on cross-sectional ranks) over the names with both values.  Result =
    ``weight_realized * mean(IC) + (1 - weight_realized) * prior``; with fewer than ``min_dates``
    usable dates the prior is returned."""
    asof = pd.Timestamp(asof)
    idx = scores.index
    pos = int(idx.searchsorted(asof, "right")) - 1 - horizon
    if pos < 0:
        return float(prior)
    usable = idx[: pos + 1]
    usable = usable[usable > asof - pd.DateOffset(months=months)]
    ics = []
    for d in usable:
        a = scores.loc[d]
        b = fwd_returns.reindex(columns=scores.columns).loc[d] if d in fwd_returns.index else None
        if b is None:
            continue
        ok = a.notna() & b.notna()
        if ok.sum() < 30:
            continue
        ra, rb = a[ok].rank(), b[ok].rank()
        c = float(np.corrcoef(ra, rb)[0, 1])
        if np.isfinite(c):
            ics.append(c)
    if len(ics) < min_dates:
        return float(prior)
    return float(weight_realized * np.mean(ics) + (1.0 - weight_realized) * prior)


# ---------------------------------------------------------------------------
# short eligibility
# ---------------------------------------------------------------------------


class ShortEligibility:
    """``SE_t`` (borrow rule v1) from the price panel and the date's attributes.

    ``adv_rank``/``price`` come from the attribute frame; the reverse-split clause scans the past
    ``RS_WINDOW`` sessions of the panel's open/close.  The short-interest clause (top 5%) is not
    applied (no point-in-time short-interest series in the panel); the set is therefore a little
    wider than the full v1 rule."""

    def __init__(self, panel: PricePanel, rule: str = "v1") -> None:
        self.panel = panel
        self.rule = rule
        self._flags: np.ndarray | None = None

    def _rs_flags(self) -> np.ndarray:
        if self._flags is None:
            p = self.panel
            frame = detect_reverse_splits(p.frame("open"), p.frame("close"))
            self._flags = frame.to_numpy(dtype=bool)
        return self._flags

    def __call__(self, pos: int, attrs: pd.DataFrame) -> pd.Series:
        flags = self._rs_flags()
        lo = max(pos - RS_WINDOW + 1, 0)
        recent = flags[lo : pos + 1].any(axis=0)
        rs = pd.Series(recent, index=self.panel.symbols).reindex(attrs.index).fillna(False)
        frame = pd.DataFrame(
            {
                "adv_rank": attrs["adv_rank"],
                "price": attrs["close"],
                "reverse_split_252": rs.to_numpy(),
            },
            index=attrs.index,
        )
        return short_eligible(frame, self.rule)


# ---------------------------------------------------------------------------
# beta
# ---------------------------------------------------------------------------


def _model_beta(
    x_all: pd.DataFrame, f: pd.DataFrame, d_stock: pd.Series, caps: pd.Series, stock_x: pd.DataFrame
) -> pd.Series:
    """Factor-model beta to the cap-weighted U3000 portfolio, ``x_i'F x_m / var_m`` (same formula
    as :meth:`RiskModel.predicted_beta` ``"model"``), for every row of ``x_all``."""
    cap = caps.reindex(stock_x.index).to_numpy()
    w = cap / cap.sum()
    xm = stock_x.to_numpy().T @ w
    fm = f.to_numpy() @ xm
    var_m = float(xm @ fm + (w**2 * d_stock.reindex(stock_x.index).to_numpy()).sum())
    return pd.Series(x_all.to_numpy() @ fm / var_m, index=x_all.index, name="beta_pred")


def market_returns(panel: PricePanel, symbol: str = "SPY") -> np.ndarray:
    """SPY close-to-close returns aligned to the panel dates (NaN for the first session)."""
    c = panel.close[:, panel.col(symbol)]
    out = np.full(len(c), np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[1:] = c[1:] / c[:-1] - 1.0
    return out


def predicted_betas(
    method: str,
    t: pd.Timestamp,
    pos: int,
    panel: PricePanel,
    risk_model: RiskModel,
    stock_names: Sequence[str],
    etf_names: Sequence[str],
    x_stock: pd.DataFrame,
    f: pd.DataFrame,
    d_stock: pd.Series,
    etf_x: pd.DataFrame,
    mret: np.ndarray,
) -> tuple[pd.Series, pd.Series]:
    """Predicted beta (to SPY) of the stock and ETF candidates.

    ``"ewma"`` / ``"vasicek"`` / ``"model"``: the risk model's :meth:`RiskModel.predicted_beta`;
    ``"ewma21"``: an exponentially weighted 252-session time-series beta with a 21-session
    half-life computed from the panel closes (this function).  ETFs: the same time-series beta
    (half-life 63 for ``ewma``/``vasicek``, 21 for ``ewma21``), or the model-implied
    ``x_etf'F x_m / var_m`` for ``"model"``."""
    if method not in BETA_METHODS:
        raise ValueError(f"beta method must be one of {BETA_METHODS}, got {method!r}")
    stocks = list(stock_names)
    etfs = list(etf_names)
    if method == "ewma21":
        cols = np.array([panel.col(s) for s in stocks], dtype=int)
        b = ewma_beta(panel.close, pos, cols, mret, halflife=21.0)
        bs = pd.Series(b, index=stocks)
    else:
        bs = risk_model.predicted_beta(t, method).reindex(stocks)
    if not etfs:
        return bs, pd.Series(dtype="float64")
    if method == "model":
        caps = risk_model.caps(t)
        be = _model_beta(etf_x.loc[etfs], f, d_stock, caps, x_stock)
    else:
        cols = np.array([panel.col(s) for s in etfs], dtype=int)
        hl = 21.0 if method == "ewma21" else 63.0
        be = pd.Series(ewma_beta(panel.close, pos, cols, mret, halflife=hl), index=etfs)
    return bs, be


# ---------------------------------------------------------------------------
# problem assembly
# ---------------------------------------------------------------------------


@dataclass
class Selection:
    """Result of assembling one date: the problem plus bookkeeping."""

    data: ProblemData
    n_stocks: int
    n_etfs: int
    n_long_tail: int
    n_short_tail: int
    forced_exits: list[str]


def _intersect_bounds(
    lo: np.ndarray, hi: np.ndarray, w0: np.ndarray, part: np.ndarray
) -> tuple[np.ndarray, np.ndarray]:
    """``[lo, hi] intersect [w0 - part, w0 + part]``.  An empty intersection (a position that must
    shrink but cannot reach the allowed range within the participation limit) collapses to the
    reachable point nearest the range: a partial exit."""
    a = np.maximum(lo, w0 - part)
    b = np.minimum(hi, w0 + part)
    empty = a > b
    too_big = empty & (w0 - part > hi)  # cannot come down to hi
    too_small = empty & (w0 + part < lo)  # cannot come up to lo
    a = np.where(too_big, w0 - part, np.where(too_small, w0 + part, a))
    b = np.where(too_big, w0 - part, np.where(too_small, w0 + part, b))
    return a, b


def assemble_problem(
    *,
    t: pd.Timestamp,
    scores: pd.Series,
    attrs: pd.DataFrame,
    in_universe: pd.Series,
    short_ok: pd.Series,
    w0: pd.Series,
    x_stock: pd.DataFrame,
    f: pd.DataFrame,
    d_stock: pd.Series,
    beta_stock: pd.Series,
    etf_x: pd.DataFrame,
    etf_d: pd.Series,
    etf_beta: pd.Series,
    etf_adv: pd.Series,
    groups: Sequence[str],
    cfg: OptConfig,
    allow_stock_shorts: bool,
    cost_model: Mapping[str, Any] | None = None,
) -> Selection:
    """Pre-filter the universe and build :class:`ProblemData`.

    ``attrs`` is indexed by symbol with ``close``, ``dollar_adv_21``, ``vol_21``; ``scores`` is the
    standardised score (index = symbols, NaN = no score); ``in_universe`` / ``short_ok`` are bool
    Series over ``attrs.index``; ``w0`` the drifted weights of stocks and ETFs (no T-bill
    sleeve)."""
    cost_model = cost_model if cost_model is not None else load_model()
    factors = list(x_stock.columns)
    # --- eligible stocks: in the risk model, attributes known, beta known
    a = attrs.reindex(x_stock.index)
    valid = (
        np.isfinite(a["close"])
        & (a["close"] > 0)
        & np.isfinite(a["dollar_adv_21"])
        & (a["dollar_adv_21"] > 0)
        & np.isfinite(a["vol_21"])
        & (a["vol_21"] > 0)
        & np.isfinite(d_stock.reindex(x_stock.index))
    )
    bs = beta_stock.reindex(x_stock.index)
    held_all = w0[(w0 != 0)]
    held_set = set(held_all.index)
    valid &= np.isfinite(bs) | x_stock.index.isin(held_set)
    stock_idx = x_stock.index[valid.to_numpy()]
    held_stocks = [s for s in held_all.index if s in set(stock_idx)]
    forced = [s for s in held_all.index if s not in set(stock_idx) and s not in set(etf_x.index)]

    uni = in_universe.reindex(stock_idx).fillna(False).astype(bool)
    sc = scores.reindex(stock_idx)
    scored = sc[uni & sc.notna()]
    can_short = (
        short_ok.reindex(stock_idx).fillna(False).astype(bool)
        & (a.loc[stock_idx, "close"] <= 0.01 * cfg.equity)
        & uni
    )
    if len(scored):
        q_hi = float(scored.quantile(1.0 - cfg.tail_frac))
        q_lo = float(scored.quantile(cfg.tail_frac))
        long_tail = scored[scored >= q_hi].index
        short_tail = (
            scored[(scored <= q_lo) & can_short.reindex(scored.index)].index
            if allow_stock_shorts
            else pd.Index([])
        )
    else:
        long_tail = short_tail = pd.Index([])
    stocks = list(dict.fromkeys([*held_stocks, *long_tail, *short_tail]))
    etfs = [e for e in etf_x.index if np.isfinite(etf_beta.get(e, np.nan)) and e in etf_d.index]
    names = stocks + etfs
    n_s, n_e = len(stocks), len(etfs)

    # --- arrays
    xs = x_stock.loc[stocks].to_numpy("float64") if stocks else np.zeros((0, len(factors)))
    xe = etf_x.loc[etfs].to_numpy("float64") if etfs else np.zeros((0, len(factors)))
    x = np.vstack([xs, xe])
    d = np.concatenate(
        [d_stock.reindex(stocks).to_numpy("float64"), etf_d.reindex(etfs).to_numpy("float64")]
    )
    beta = np.concatenate(
        [
            np.nan_to_num(bs.reindex(stocks).to_numpy("float64"), nan=1.0),
            etf_beta.reindex(etfs).to_numpy("float64"),
        ]
    )
    w0v = np.concatenate([w0.reindex(stocks).fillna(0.0).to_numpy(), w0.reindex(etfs).fillna(0.0)])
    score_v = np.concatenate([sc.reindex(stocks).fillna(0.0).to_numpy(), np.zeros(n_e)])
    alpha = alpha_from_scores(score_v, d, cfg.ic, cfg.horizon_days)
    alpha[n_s:] = 0.0

    ast = a.loc[stocks]
    px = ast["close"].to_numpy("float64")
    adv = ast["dollar_adv_21"].to_numpy("float64")
    vol = ast["vol_21"].to_numpy("float64")
    year = np.full(n_s, t.year)
    hs_s = half_spread_bp(px, adv, vol, year, cfg.snapshot, cost_model) if n_s else np.zeros(0)
    hs = np.concatenate([hs_s, np.full(n_e, cfg.etf_half_spread_bp)])
    imp_s = cfg.impact_y * vol * np.sqrt(cfg.e_cap / np.maximum(adv, 1.0)) * BP
    imp = np.concatenate([imp_s, np.zeros(n_e)])

    cap = cfg.name_cap if cfg.name_cap is not None else np.inf
    in_u = uni.reindex(stocks).fillna(False).to_numpy(bool)
    sh = can_short.reindex(stocks).fillna(False).to_numpy(bool) & allow_stock_shorts
    lo_s = np.where(sh, -cap, 0.0)
    hi_s = np.where(in_u, cap, 0.0)
    lo = np.concatenate([lo_s, np.full(n_e, -cfg.etf_cap)])
    hi = np.concatenate([hi_s, np.full(n_e, cfg.etf_cap)])
    if cfg.participation is not None:
        e_adv = etf_adv.reindex(etfs).fillna(0.0).to_numpy("float64")
        part = np.concatenate(
            [cfg.participation * adv / cfg.e_cap, cfg.participation * e_adv / cfg.e_cap]
        )
        lo, hi = _intersect_bounds(lo, hi, w0v, part)
    borrow = np.concatenate([np.where(sh, cfg.borrow_bp, 0.0), np.zeros(n_e)])

    # --- constraint column sets
    fac = {name: k for k, name in enumerate(factors)}
    ind_idx = np.array([fac[g] for g in groups], dtype=int)
    style_pairs = [
        (fac[s], cfg.size_cap if s == "size" else cfg.style_cap) for s in STYLES if s in fac
    ]
    style_pairs = [(k, c) for k, c in style_pairs if c is not None]
    style_idx = np.array([k for k, _ in style_pairs], dtype=int)
    style_caps = np.array([c for _, c in style_pairs], dtype="float64")
    data = ProblemData(
        names=names,
        alpha=alpha,
        w0=w0v,
        x=x,
        f=f.to_numpy("float64"),
        d=d,
        beta=beta,
        half_spread_bp=hs,
        impact_coef_bp=imp,
        borrow_bp_yr=borrow,
        lo=lo,
        hi=hi,
        ind_idx=ind_idx,
        style_idx=style_idx,
        style_caps=style_caps,
        is_etf=np.r_[np.zeros(n_s, dtype=bool), np.ones(n_e, dtype=bool)],
    )
    return Selection(data, n_s, n_e, len(long_tail), len(short_tail), forced)


# ---------------------------------------------------------------------------
# backtest adapter
# ---------------------------------------------------------------------------

AlphaSource = Callable[[pd.Timestamp, BookState, pd.Index], pd.Series]


def peak_rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


class BookDecider:
    """``decide(t, state)`` for :func:`backtest.run_book`.

    ``alpha_source(t, state, universe)`` returns the standardised score (rank-normal, unit
    variance) of the names in ``universe`` (a pandas Index of the date's universe members);
    NaN means no score.  The call returns the target weights of stocks and hedge ETFs (fractions
    of E) plus ``TBILL = 1.0``.  ``records`` collects one dict per call (solve time, status,
    counts, exposures, ex-ante vol, ...)."""

    def __init__(
        self,
        alpha_source: AlphaSource,
        risk_model: RiskModel,
        spec: BookSpec,
        *,
        attrs: PanelAttributes | None = None,
        etf_risk: ETFRisk | None = None,
        eligibility: Callable[[int, pd.DataFrame], pd.Series] | None = None,
    ) -> None:
        self.alpha_source = alpha_source
        self.rm = risk_model
        self.spec = spec
        self.attrs = attrs or PanelAttributes()
        self.etf_risk = etf_risk or ETFRisk(risk_model)
        self.eligibility = eligibility
        self.records: list[dict[str, Any]] = []
        self._mret: np.ndarray | None = None
        self._cost_model = load_model()

    # -- helpers -------------------------------------------------------------

    @property
    def n_failures(self) -> int:
        return sum(1 for r in self.records if not r["ok"])

    @property
    def failure_rate(self) -> float:
        return self.n_failures / len(self.records) if self.records else 0.0

    def _w0(self, state: BookState) -> pd.Series:
        w = state.weights
        return w[~w.index.isin(TBILL_SYMBOLS)]

    def __call__(self, t: pd.Timestamp, state: BookState) -> dict[str, float] | None:
        spec, cfg = self.spec, self.spec.opt
        t0 = time.perf_counter()
        panel = state.panel
        if self._mret is None:
            self._mret = market_returns(panel)
        elig = self.eligibility or ShortEligibility(panel)
        self.eligibility = elig
        w0 = self._w0(state)
        try:
            x_stock, f, d_stock = self.rm.at(t)
        except KeyError:
            return self._fail(t, w0, "no_risk_model", t0)
        attrs = self.attrs.at(t)
        if attrs.empty:
            return self._fail(t, w0, "no_attrs", t0)
        uni_mask = attrs[spec.universe_col].astype(bool)
        universe = attrs.index[uni_mask.to_numpy()].intersection(x_stock.index)
        scores = self.alpha_source(t, state, universe)
        short_ok = elig(state.pos, attrs)
        etf_x, etf_d = self.etf_risk.at(t)
        etf_adv = self.etf_risk.adv(t)
        etfs = [e for e in etf_x.index if panel.has(e)]
        beta_s, beta_e = predicted_betas(
            cfg.beta_method,
            t,
            state.pos,
            panel,
            self.rm,
            list(x_stock.index),
            etfs,
            x_stock,
            f,
            d_stock,
            etf_x,
            self._mret,
        )
        sel = assemble_problem(
            t=t,
            scores=scores,
            attrs=attrs,
            in_universe=uni_mask,
            short_ok=short_ok,
            w0=w0,
            x_stock=x_stock,
            f=f,
            d_stock=d_stock,
            beta_stock=beta_s,
            etf_x=etf_x.loc[etfs],
            etf_d=etf_d,
            etf_beta=beta_e,
            etf_adv=etf_adv,
            groups=self.rm.groups,
            cfg=replace(cfg, allow_stock_shorts=spec.allow_stock_shorts),
            allow_stock_shorts=spec.allow_stock_shorts,
            cost_model=self._cost_model,
        )
        data = sel.data
        res = solve(data, cfg)
        rec = self._record(t, sel, res, w0, t0)
        self.records.append(rec)
        if not res.ok:
            if len(w0) == 0:
                return {TBILL: 1.0}
            return None  # hold: dollar holdings stay at the drifted w0
        out = {nm: float(w) for nm, w in zip(data.names, res.w, strict=True) if w != 0.0}
        out[TBILL] = 1.0
        return out

    def _fail(self, t: pd.Timestamp, w0: pd.Series, reason: str, t0: float):
        self.records.append(
            {
                "date": t,
                "ok": False,
                "status": reason,
                "reason": reason,
                "wall_s": time.perf_counter() - t0,
                "build_s": 0.0,
                "solve_s": 0.0,
            }
        )
        return {TBILL: 1.0} if len(w0) == 0 else None

    def _record(
        self, t: pd.Timestamp, sel: Selection, res: SolveResult, w0: pd.Series, t0: float
    ) -> dict[str, Any]:
        data, cfg = sel.data, self.spec.opt
        w = res.w
        is_etf = data.is_etf if data.is_etf is not None else np.zeros(data.n, dtype=bool)
        stk = ~is_etf
        # exposures of the drifted book under today's model (held names the model sees)
        y_w0 = exposures(data, data.w0)
        y_t = exposures(data, w)
        etf_w = {
            nm: float(x) for nm, x, e in zip(data.names, w, is_etf, strict=True) if e and x != 0.0
        }
        return {
            "date": t,
            "ok": bool(res.ok),
            "status": res.status,
            "reason": res.reason,
            "build_s": res.build_s,
            "solve_s": res.solve_s,
            "solver_s": res.solver_s,
            "wall_s": time.perf_counter() - t0,
            "rss_mb": peak_rss_mb(),
            "n_assets": data.n,
            "n_long_tail": sel.n_long_tail,
            "n_short_tail": sel.n_short_tail,
            "n_long": int(((w > 0) & stk).sum()),
            "n_short": int(((w < 0) & stk).sum()),
            "long_gross": float(w[(w > 0) & stk].sum()),
            "short_gross": float(-w[(w < 0) & stk].sum()),
            "etf_weights": etf_w,
            "forced_exits": len(sel.forced_exits),
            "vol_target": ex_ante_vol_annual(data, w) if data.n else float("nan"),
            "vol_w0": ex_ante_vol_annual(data, data.w0) if data.n else float("nan"),
            "beta_target": float(data.beta @ w) if data.n else float("nan"),
            "beta_w0": float(data.beta @ data.w0) if data.n else float("nan"),
            "exposures_target": y_t.tolist(),
            "exposures_w0": y_w0.tolist(),
            "turnover_one_sided": float(np.abs(w - data.w0).sum() / 2.0),
            "objective_bp": res.objective_bp,
            "attempt": res.attempt,
            "attempt_log": list(res.attempt_log),
            "max_violation": res.max_violation,
            "ic": cfg.ic,
        }


def make_decide(
    alpha_source: AlphaSource,
    risk_model: RiskModel,
    cfg: BookSpec,
    *,
    attrs: PanelAttributes | None = None,
    etf_risk: ETFRisk | None = None,
    eligibility: Callable[[int, pd.DataFrame], pd.Series] | None = None,
) -> BookDecider:
    """Build the ``decide(t, state)`` callable for ``backtest.run_book`` (see
    :class:`BookDecider`)."""
    return BookDecider(
        alpha_source, risk_model, cfg, attrs=attrs, etf_risk=etf_risk, eligibility=eligibility
    )


def book_config(
    spec: BookSpec,
    attrs: PanelAttributes,
    *,
    freq: str = "W",
    offset: int = 0,
    exec_price: str = "close",
    start: str | None = None,
    end: str | None = None,
    stress_borrow: bool = False,
    **kw: Any,
) -> BookConfig:
    """``BookConfig`` for a book spec: the matching spread snapshot, true costs (spread, impact,
    fees) through ``make_cost_fn``, borrow (25 bp/year, 100 under ``stress_borrow``, 0 for B),
    prior-session trade attributes from the panel."""
    borrow = spec.borrow_bp_per_year
    if stress_borrow and borrow > 0:
        borrow = 100.0
    return BookConfig(
        freq=freq,  # type: ignore[arg-type]
        offset=offset,
        exec_price=exec_price,  # type: ignore[arg-type]
        cost_fn=make_cost_fn(snapshot_for(exec_price)),
        borrow_bp_per_year=borrow,
        trade_attrs=attrs.trade_attrs,
        start=start,
        end=end,
        **kw,
    )


__all__ = [
    "BETA_METHODS",
    "MARKET",
    "BookDecider",
    "BookSpec",
    "OptConfig",
    "ProblemData",
    "Selection",
    "ShortEligibility",
    "SOLVE_ATTEMPTS",
    "SolveResult",
    "alpha_from_scores",
    "assemble_problem",
    "book_config",
    "constraint_violations",
    "ex_ante_vol_annual",
    "factor_cholesky",
    "make_decide",
    "market_returns",
    "predicted_betas",
    "rank_normal",
    "solve",
    "trailing_rank_ic",
]
