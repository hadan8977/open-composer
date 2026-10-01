"""D5 optimizer (design section 8): closed form, constraints, configurations, failure fallback, ETF
exposure regression, cost function and the ``make_decide`` adapter."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import optimize as op
from open_composer.research.equity_book.backtest import TBILL, BookConfig, run_book
from open_composer.research.equity_book.costfn import make_cost_fn, snapshot_for
from open_composer.research.equity_book.etf_risk import fit_etf_loadings, regress_etfs
from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.equity_book.risk import MARKET, STYLES

NO_CONSTRAINTS = op.OptConfig(
    sigma_annual=0.05,
    kappa=0.0,
    beta_cap=None,
    industry_cap=None,
    size_cap=None,
    style_cap=None,
    name_cap=None,
    gross_cap=None,
    dollar_neutral=False,
    participation=None,
)


def _factor_cov(rng: np.random.Generator, k: int, scale: float = 1e-4) -> np.ndarray:
    a = rng.normal(size=(k, k))
    return scale * (a @ a.T) / k + scale * 0.1 * np.eye(k)


def _data(
    n: int, seed: int, *, n_ind: int = 6, styles: tuple[str, ...] = ("size", "beta", "momentum")
) -> op.ProblemData:
    """Synthetic problem: market + ``n_ind`` industries (one-hot) + styles, no costs set up."""
    rng = np.random.default_rng(seed)
    k = 1 + n_ind + len(styles)
    x = np.zeros((n, k))
    x[:, 0] = 1.0
    ind = rng.integers(0, n_ind, n)
    x[np.arange(n), 1 + ind] = 1.0
    x[:, 1 + n_ind :] = rng.normal(size=(n, len(styles)))
    f = _factor_cov(rng, k)
    d = rng.uniform(1.0, 4.0, n) * 4e-4
    beta = rng.normal(1.0, 0.3, n)
    adv = np.exp(rng.normal(17.0, 1.0, n))
    vol = rng.uniform(0.01, 0.03, n)
    style_idx = np.arange(1 + n_ind, k)
    caps = np.array([0.10 if s == "size" else 0.25 for s in styles])
    return op.ProblemData(
        names=[f"S{i:03d}" for i in range(n)],
        alpha=op.alpha_from_scores(rng.normal(size=n), d, 0.03, 21),
        w0=np.zeros(n),
        x=x,
        f=f,
        d=d,
        beta=beta,
        half_spread_bp=rng.uniform(2.0, 12.0, n),
        impact_coef_bp=0.5 * vol * np.sqrt(1e6 / adv) * 1e4,
        borrow_bp_yr=np.full(n, 25.0),
        lo=np.full(n, -0.01),
        hi=np.full(n, 0.01),
        ind_idx=np.arange(1, 1 + n_ind),
        style_idx=style_idx,
        style_caps=caps,
        is_etf=np.zeros(n, dtype=bool),
    )


# ----------------------------------------------------------------------------------- 1. closed form


def test_closed_form_no_cost_no_constraint() -> None:
    d = _data(40, 1)
    d = op.ProblemData(**{**d.__dict__, "lo": np.full(40, -np.inf), "hi": np.full(40, np.inf)})
    res = op.solve(d, NO_CONSTRAINTS)
    assert res.ok
    sigma = d.x @ d.f @ d.x.T + np.diag(d.d)  # dense only in the test
    inv_a = np.linalg.solve(sigma, d.alpha)
    sig_d = 0.05 / np.sqrt(252.0)
    expect = sig_d * inv_a / np.sqrt(d.alpha @ inv_a)
    # the optimizer snaps weights below CLEAN_TOL to 0, so compare to the same cleanup
    assert np.allclose(res.w, expect, atol=2e-6, rtol=1e-3)
    assert op.ex_ante_vol_annual(d, res.w) == pytest.approx(0.05, rel=1e-4)
    # proportional to inv(Sigma) alpha
    cos = res.w @ inv_a / (np.linalg.norm(res.w) * np.linalg.norm(inv_a))
    assert cos == pytest.approx(1.0, abs=1e-6)


# ------------------------------------------------------------------ 2. every constraint holds


def test_all_constraints_hold_on_200_names() -> None:
    d = _data(200, 2)
    # a first book so costs and the drift matter
    rng = np.random.default_rng(3)
    d.w0 = np.where(rng.random(200) < 0.2, rng.normal(0, 0.004, 200), 0.0)
    d.w0 -= d.w0.sum() / 200
    cfg = op.OptConfig(kappa=1.0, participation=None)
    res = op.solve(d, cfg)
    assert res.ok, res.reason
    w = res.w
    assert abs(w.sum()) < 1e-5
    assert abs(d.beta @ w) <= 0.02 + 1e-5
    y = d.x.T @ w
    assert np.abs(y[d.ind_idx]).max() <= 0.01 + 1e-5
    assert np.abs(y[d.style_idx]) @ np.ones(len(d.style_idx)) > 0
    assert (np.abs(y[d.style_idx]) <= d.style_caps + 1e-5).all()
    assert np.abs(w).max() <= 0.01 + 1e-6
    assert np.abs(w).sum() <= 1.0 + 1e-5
    assert op.ex_ante_vol_annual(d, w) <= 0.05 + 1e-5
    v = op.constraint_violations(d, w, cfg)
    assert max(v[k] for k in v if k != "vol") <= 1e-5
    # the problem is not trivial: it trades, and the vol budget or gross binds
    assert (np.abs(w) > 1e-6).sum() > 20
    assert (op.ex_ante_vol_annual(d, w) > 0.049) or (np.abs(w).sum() > 0.99)


def test_quadratic_upper_bound_option_runs_and_is_feasible() -> None:
    d = _data(120, 4)
    cfg = op.OptConfig(impact_mode="quadratic_ub", participation=None)
    res = op.solve(d, cfg)
    assert res.ok
    assert op.max_violation(d, res.w, cfg) <= 1e-5


def test_participation_bounds_collapse_to_partial_exit() -> None:
    lo = np.array([0.0, -0.01, 0.0])
    hi = np.array([0.0, 0.01, 0.01])
    w0 = np.array([0.008, 0.0, 0.02])  # must exit; free; above the cap
    part = np.array([0.003, 0.003, 0.004])
    a, b = op._intersect_bounds(lo, hi, w0, part)
    assert (a[0], b[0]) == (pytest.approx(0.005), pytest.approx(0.005))  # partial exit
    assert (a[1], b[1]) == (pytest.approx(-0.003), pytest.approx(0.003))
    assert (a[2], b[2]) == (pytest.approx(0.016), pytest.approx(0.016))  # cannot reach 0.01


# --------------------------------------------------------------------- 3. configs B, short filters


def _assembly_inputs(n: int = 120, seed: int = 5) -> dict:
    rng = np.random.default_rng(seed)
    n_ind = 5
    groups = [f"g{i}" for i in range(n_ind)]
    factors = [MARKET, *groups, *STYLES]
    names = [f"S{i:03d}" for i in range(n)]
    x = pd.DataFrame(0.0, index=names, columns=factors)
    x[MARKET] = 1.0
    ind = rng.integers(0, n_ind, n)
    for i, g in enumerate(ind):
        x.loc[names[i], groups[g]] = 1.0
    for s in STYLES:
        x[s] = rng.normal(size=n)
    f = pd.DataFrame(_factor_cov(rng, len(factors)), index=factors, columns=factors)
    d = pd.Series(rng.uniform(1.0, 4.0, n) * 4e-4, index=names)
    attrs = pd.DataFrame(
        {
            "close": rng.uniform(20, 200, n),
            "dollar_adv_21": np.exp(rng.normal(18.0, 0.5, n)),
            "vol_21": rng.uniform(0.01, 0.03, n),
            "adv_rank": np.arange(1, n + 1),
        },
        index=names,
    )
    # one very expensive stock (cannot be shorted by whole shares at E = $100k)
    attrs.loc[names[0], "close"] = 5000.0
    scores = op.rank_normal(pd.Series(rng.normal(size=n), index=names))
    scores[names[0]] = -3.0  # would be a prime short candidate
    etf_names = ["SPY", "IWM"]
    etf_x = pd.DataFrame(0.0, index=etf_names, columns=factors)
    etf_x[MARKET] = 1.0
    etf_x.loc["SPY", groups] = 0.2
    etf_x.loc["IWM", groups] = 0.2
    etf_d = pd.Series([2e-6, 4e-6], index=etf_names)
    etf_beta = pd.Series([1.0, 1.1], index=etf_names)
    short_ok = pd.Series(True, index=names)
    short_ok[names[1:6]] = False  # not easy to borrow
    return dict(
        t=pd.Timestamp("2024-06-28"),
        scores=scores,
        attrs=attrs,
        in_universe=pd.Series(True, index=names),
        short_ok=short_ok,
        w0=pd.Series(dtype=float),
        x_stock=x,
        f=f,
        d_stock=d,
        beta_stock=pd.Series(rng.normal(1.0, 0.25, n), index=names),
        etf_x=etf_x,
        etf_d=etf_d,
        etf_beta=etf_beta,
        etf_adv=pd.Series([1e10, 1e9], index=etf_names),
        groups=groups,
    )


def test_config_b_has_no_stock_shorts_and_a_respects_filters() -> None:
    kw = _assembly_inputs()
    cfg = op.OptConfig(participation=None, tail_frac=0.5)
    for allow, label in ((False, "B"), (True, "A")):
        sel = op.assemble_problem(**kw, cfg=cfg, allow_stock_shorts=allow)
        res = op.solve(sel.data, cfg)
        assert res.ok, (label, res.reason)
        names = sel.data.names
        w = pd.Series(res.w, index=names)
        stocks = w[~sel.data.is_etf]
        if allow:
            shorts = stocks[stocks < -1e-9].index
            assert len(shorts) > 0  # A really shorts
            assert not set(shorts) & set(kw["short_ok"][~kw["short_ok"]].index)  # SE_t only
            assert "S000" not in set(shorts)  # whole-share filter: price 5000 > 0.01 * 100k
            assert "S000" not in set(sel.data.names[: sel.n_stocks]) or (
                sel.data.lo[names.index("S000")] == 0.0
            )
        else:
            assert (stocks >= -1e-9).all()  # B: stock weights >= 0
            assert (w[sel.data.is_etf] <= 1e-9).all()  # the hedge is a short ETF leg
            assert w[sel.data.is_etf].sum() < -0.05
        assert abs(w.sum()) < 1e-5


def test_short_tail_is_prefiltered_by_eligibility() -> None:
    kw = _assembly_inputs()
    cfg = op.OptConfig(participation=None, tail_frac=0.35)
    sel = op.assemble_problem(**kw, cfg=cfg, allow_stock_shorts=True)
    names = sel.data.names[: sel.n_stocks]
    ineligible = set(kw["short_ok"][~kw["short_ok"]].index) | {"S000"}
    # an ineligible name may be in the long tail but never has a short bound
    lo = pd.Series(sel.data.lo[: sel.n_stocks], index=names)
    assert (lo[[n for n in names if n in ineligible]] == 0.0).all()
    assert sel.n_etfs == 2


# -------------------------------------------------------------------------------- 4. failure


def test_failure_falls_back_to_w0() -> None:
    d = _data(30, 6)
    d.w0 = np.full(30, 0.0005)
    d.lo = np.full(30, 0.005)  # every name must be long ...
    d.hi = np.full(30, 0.01)
    res = op.solve(d, op.OptConfig(participation=None))  # ... but dollar neutral: infeasible
    assert not res.ok
    assert res.status != "optimal"
    assert np.array_equal(res.w, d.w0)
    bad = op.solve(d, op.OptConfig(solver="NO_SUCH_SOLVER"))
    assert not bad.ok and bad.status == "solver_error"
    assert np.array_equal(bad.w, d.w0)


# ----------------------------------------------------------------------------- 5. ETF exposures


def test_etf_regression_recovers_known_loadings() -> None:
    rng = np.random.default_rng(7)
    t, g, s = 400, 5, 3
    f_mkt = rng.normal(0, 0.01, t)
    f_g = rng.normal(0, 0.004, (t, g))
    f_s = rng.normal(0, 0.003, (t, s))
    b_g = np.array([0.3, 0.25, 0.2, 0.15, 0.05])  # industry weights, sum = market loading
    b_s = np.array([0.4, -0.3, 0.1])
    noise = rng.normal(0, 0.0005, t)
    y = b_g.sum() * f_mkt + f_g @ b_g + f_s @ b_s + noise
    bg, bs, bm, sv = fit_etf_loadings(y, f_mkt, f_g, f_s)
    assert np.allclose(bg, b_g, atol=0.03)
    assert np.allclose(bs, b_s, atol=0.05)
    assert bm == pytest.approx(b_g.sum(), abs=0.03)
    assert sv == pytest.approx(0.0005**2, rel=0.2)

    # same through the rolling wrapper on a date index
    idx = pd.bdate_range("2023-01-02", periods=t)
    groups = [f"g{i}" for i in range(g)]
    styles = [f"s{i}" for i in range(s)]
    fr = pd.DataFrame(
        np.column_stack([f_mkt, f_g, f_s]), index=idx, columns=[MARKET, *groups, *styles]
    )
    etf = pd.DataFrame({"AAA": y, "BBB": 2.0 * y}, index=idx)
    x, dv = regress_etfs(fr, etf, groups, styles, list(fr.columns), idx[-1], window=252)
    assert x.loc["AAA", groups].to_numpy() == pytest.approx(b_g, abs=0.05)
    assert x.loc["BBB", MARKET] == pytest.approx(2.0 * b_g.sum(), abs=0.06)
    assert dv["BBB"] == pytest.approx(4.0 * dv["AAA"], rel=1e-6)


# --------------------------------------------------------------------------- cost function, IC


def test_cost_fn_snapshot_and_etf_rates() -> None:
    assert snapshot_for("open") == "open" and snapshot_for("close") == "close"
    with pytest.raises(ValueError):
        snapshot_for("mid")
    trades = pd.DataFrame(
        {
            "symbol": ["ABC", "SPY"],
            "dollar_trade": [10_000.0, -50_000.0],
            "price": [30.0, 500.0],
            "prior_close": [30.0, 500.0],
            "dollar_adv_21": [5e6, 3e10],
            "vol_21": [0.02, 0.008],
            "trade_date": pd.Timestamp("2024-06-03"),
        }
    )
    c_open = make_cost_fn("open")(trades, None)
    c_close = make_cost_fn("close")(trades, None)
    assert c_open["spread"] > c_close["spread"] > 0  # open spreads are wider
    assert c_open["fees"] == pytest.approx(60_000.0 * 0.5 / 1e4)
    # the ETF leg is charged the flat 1 bp half spread: 50,000 * 1 bp = 5 dollars
    only_etf = make_cost_fn("close")(trades.iloc[[1]], None)
    assert only_etf["spread"] == pytest.approx(5.0)
    assert only_etf["impact"] == 0.0
    # a stock row without cost inputs is charged the missing-data spread, never zero
    miss = trades.iloc[[0]].copy()
    miss["dollar_adv_21"] = np.nan
    assert make_cost_fn("close")(miss, None)["spread"] == pytest.approx(10_000.0 * 40.0 / 1e4)


def test_trailing_ic_shrinks_toward_prior() -> None:
    rng = np.random.default_rng(8)
    idx = pd.bdate_range("2020-01-01", periods=900)
    cols = [f"S{i}" for i in range(80)]
    score = pd.DataFrame(rng.normal(size=(900, 80)), index=idx, columns=cols)
    fwd = 0.2 * score + pd.DataFrame(rng.normal(size=(900, 80)), index=idx, columns=cols)
    ic = op.trailing_rank_ic(score, fwd, idx[-1], months=36, horizon=21)
    realized = 0.2 / np.sqrt(1.0 + 0.2**2) * 0.95  # Spearman is a little below Pearson
    assert ic == pytest.approx(0.5 * realized + 0.5 * 0.03, abs=0.02)
    # too little history -> the prior
    assert op.trailing_rank_ic(score, fwd, idx[10], horizon=21) == pytest.approx(0.03)


# ----------------------------------------------------------------------------- 7. make_decide


class _FakeRisk:
    def __init__(self, x, f, d, groups):
        self._x, self._f, self._d = x, f, d
        self.groups = groups
        self.factors = list(x.columns)
        self.beta = pd.Series(np.linspace(0.7, 1.3, len(x)), index=x.index)

    def at(self, t):
        return self._x, self._f, self._d

    def predicted_beta(self, t, method="ewma"):
        return self.beta

    def caps(self, t):
        return pd.Series(1e9, index=self._x.index)


class _FakeAttrs:
    def __init__(self, frame):
        self.frame = frame

    def at(self, t):
        return self.frame


class _FakeETF:
    def __init__(self, x, d, adv):
        self.x, self.d, self._adv = x, d, adv

    def at(self, t):
        return self.x, self.d

    def adv(self, t):
        return self._adv


def _decide_fixture(n: int = 150, t_n: int = 330):
    kw = _assembly_inputs(n, seed=11)
    rng = np.random.default_rng(12)
    idx = pd.bdate_range("2023-01-02", periods=t_n)
    names = list(kw["x_stock"].index)
    etfs = ["SPY", "IWM", "SGOV"]
    syms = names + etfs
    mkt = rng.normal(0.0004, 0.008, t_n)
    close = {}
    for s in names:
        r = mkt * rng.uniform(0.6, 1.4) + rng.normal(0, 0.012, t_n)
        close[s] = 50.0 * np.cumprod(1.0 + r)
    close["SPY"] = 400.0 * np.cumprod(1.0 + mkt)
    close["IWM"] = 200.0 * np.cumprod(1.0 + mkt * 1.1 + rng.normal(0, 0.003, t_n))
    close["SGOV"] = 100.0 * np.cumprod(np.full(t_n, 1.0 + 0.05 / 252))
    c = pd.DataFrame(close, index=idx)[syms]
    o = c.shift(1).fillna(c.iloc[0]) * (1.0 + rng.normal(0, 0.002, c.shape))
    panel = PricePanel.from_frames(o, c)
    attrs = kw["attrs"].copy()
    attrs["close"] = c.iloc[-1][names]  # price near the panel's end; whole-share test below
    attrs.loc[names[0], "close"] = 5000.0
    attrs["in_u3000"] = True
    attrs["in_p1000"] = attrs["adv_rank"] <= 60
    risk = _FakeRisk(kw["x_stock"], kw["f"], kw["d_stock"], kw["groups"])
    etf_x = kw["etf_x"]
    spec_pool = {"SPY": 2e-6, "IWM": 4e-6}

    def alpha_source(t, state, universe):
        pos = state.pos
        cols = np.array([panel.col(s) for s in universe])
        mom = pd.Series(panel.close[pos - 21, cols] / panel.close[pos - 252, cols] - 1, universe)
        return op.rank_normal(mom)

    etf = _FakeETF(etf_x, pd.Series(spec_pool), pd.Series({"SPY": 1e10, "IWM": 1e9}))
    return panel, risk, _FakeAttrs(attrs), etf, alpha_source


def test_make_decide_overlay_plus_tbill_and_runs_in_backtest() -> None:
    panel, risk, attrs, etf, alpha_source = _decide_fixture()
    spec = op.BookSpec("A", op.OptConfig(participation=None, tail_frac=0.5))
    dec = op.make_decide(alpha_source, risk, spec, attrs=attrs, etf_risk=etf)
    cfg = BookConfig(
        freq="W",
        offset=0,
        exec_price="close",
        cost_fn=make_cost_fn("close"),
        trade_attrs=lambda d, syms: pd.DataFrame(
            {"dollar_adv_21": 5e7, "vol_21": 0.015, "prior_close": 60.0}, index=list(syms)
        ),
        start=str(panel.dates[270].date()),
    )
    res = run_book(panel, dec, cfg)
    assert len(dec.records) >= 8
    assert dec.failure_rate == 0.0
    # every target: dollar-neutral overlay plus the sleeve at exactly 1.0
    last_t, snap = list(res.holdings.items())[-1]
    assert snap.get("SGOV", 0.0) == pytest.approx(1.0, abs=0.06)  # drift of the sleeve only
    overlay = snap.drop("SGOV")
    assert abs(overlay.sum()) < 0.03  # neutral at the trade (up to drift of a close->close day)
    assert overlay.abs().sum() <= 1.05
    # a direct call returns the documented dict
    state_cls = type(res)  # noqa: F841
    from open_composer.research.equity_book.backtest import BookState

    i = 300
    empty = pd.Series(dtype=float)
    st = BookState(
        date=panel.dates[i],
        pos=i,
        equity=1.0,
        holdings=empty,
        weights=empty,
        cash=1.0,
        long_value=0.0,
        short_value=0.0,
        tbill_value=0.0,
        panel=panel,
    )
    tgt = dec(panel.dates[i], st)
    assert tgt is not None and tgt[TBILL] == 1.0
    assert sum(v for k, v in tgt.items() if k != TBILL) == pytest.approx(0.0, abs=1e-5)
    assert tgt.get("S000", 0.0) >= 0.0  # price 5000: whole-share filter forbids a short


def test_decide_returns_none_on_failure_when_book_nonempty() -> None:
    panel, risk, attrs, etf, alpha_source = _decide_fixture()
    bad = op.BookSpec("A", op.OptConfig(solver="NO_SUCH_SOLVER"))
    dec = op.make_decide(alpha_source, risk, bad, attrs=attrs, etf_risk=etf)
    from open_composer.research.equity_book.backtest import BookState

    i = 300
    held = pd.Series({"S010": 0.004, "S011": -0.004})
    st = BookState(
        date=panel.dates[i],
        pos=i,
        equity=1.0,
        holdings=held,
        weights=held,
        cash=1.0,
        long_value=0.0,
        short_value=0.0,
        tbill_value=0.0,
        panel=panel,
    )
    assert dec(panel.dates[i], st) is None  # hold the drifted book
    assert dec.failure_rate == 1.0
    empty = pd.Series(dtype=float)
    st2 = BookState(**{**st.__dict__, "holdings": empty, "weights": empty})
    assert dec(panel.dates[i], st2) == {TBILL: 1.0}  # empty book: just the sleeve


def test_ewma21_beta_option_recovers_known_beta() -> None:
    rng = np.random.default_rng(13)
    t_n = 400
    idx = pd.bdate_range("2023-01-02", periods=t_n)
    spy = rng.normal(0.0003, 0.009, t_n)
    close = pd.DataFrame(
        {
            "SPY": 400.0 * np.cumprod(1.0 + spy),
            "AAA": 50.0 * np.cumprod(1.0 + 1.5 * spy + rng.normal(0, 0.004, t_n)),
            "IWM": 200.0 * np.cumprod(1.0 + 1.1 * spy + rng.normal(0, 0.002, t_n)),
        },
        index=idx,
    )
    panel = PricePanel.from_frames(close, close)
    mret = op.market_returns(panel)
    bs, be = op.predicted_betas(
        "ewma21", idx[-1], t_n - 1, panel, None, ["AAA"], ["IWM"], None, None, None, None, mret
    )
    assert bs["AAA"] == pytest.approx(1.5, abs=0.25)
    assert be["IWM"] == pytest.approx(1.1, abs=0.1)
    with pytest.raises(ValueError):
        op.predicted_betas(
            "nope", idx[-1], t_n - 1, panel, None, ["AAA"], [], None, None, None, None, mret
        )


# ------------------------------------------------------------------- 8. robust solve path (ladder)


class _FailFirst:
    """Patch ``cp.Problem.solve`` so the first ``n_fail`` calls raise ``SolverError``; later calls
    run the real solver.  ``calls`` collects ``(solver name, options)`` of every call."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, n_fail: int) -> None:
        self.calls: list[tuple[str, dict]] = []
        real = op.cp.Problem.solve

        def fake(prob, *args, **kw):
            self.calls.append(
                (str(kw.get("solver")), {k: v for k, v in kw.items() if k != "solver"})
            )
            if len(self.calls) <= n_fail:
                raise op.cp.error.SolverError("forced failure")
            return real(prob, *args, **kw)

        monkeypatch.setattr(op.cp.Problem, "solve", fake)


def test_first_success_is_attempt_zero_and_default_ladder_is_on() -> None:
    assert op.OptConfig().retry_ladder
    d = _data(60, 21)
    res = op.solve(d, op.OptConfig(participation=None))
    assert res.ok and res.attempt == 0
    assert res.attempt_log == (f"first:{res.status}",)
    assert res.max_violation <= 1e-4


@pytest.mark.parametrize("n_fail", [1, 2, 3])
def test_ladder_rescues_forced_first_attempt_failures(
    monkeypatch: pytest.MonkeyPatch, n_fail: int
) -> None:
    d = _data(60, 22)
    cfg = op.OptConfig(participation=None)
    ref = op.solve(d, cfg)  # unpatched reference
    assert ref.ok and ref.attempt == 0
    patch = _FailFirst(monkeypatch, n_fail)
    res = op.solve(d, cfg)
    assert res.ok, res.reason
    assert res.attempt == n_fail  # the attempt that succeeded is recorded
    assert len(res.attempt_log) == n_fail + 1
    assert (
        res.attempt_log[:n_fail]
        == (
            "first:solver_error",
            "clarabel_max_iter:solver_error",
            "clarabel_relaxed:solver_error",
        )[:n_fail]
    )
    assert op.max_violation(d, res.w, cfg) <= 1e-4  # accepted solutions are checked
    assert np.abs(res.w - ref.w).max() < 5e-4  # same optimum, whichever step found it
    names = [c[0] for c in patch.calls]
    assert names[: n_fail + 1] == ["CLARABEL", "CLARABEL", "CLARABEL", "SCS"][: n_fail + 1]
    opts = [c[1] for c in patch.calls]
    assert opts[0] == {"verbose": False, "max_iter": cfg.max_iter}
    if n_fail >= 1:
        assert opts[1]["max_iter"] == cfg.retry_max_iter and "tol_gap_abs" not in opts[1]
    if n_fail >= 2:
        assert opts[2]["tol_gap_abs"] == cfg.retry_relaxed_tol == opts[2]["tol_feas"]
    if n_fail >= 3:
        assert opts[3]["max_iters"] == cfg.retry_scs_max_iters


def test_ladder_off_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    d = _data(40, 23)
    patch = _FailFirst(monkeypatch, 1)
    res = op.solve(d, op.OptConfig(participation=None, retry_ladder=False))
    assert not res.ok and res.status == "solver_error"
    assert np.array_equal(res.w, d.w0)
    assert len(patch.calls) == 1 and res.attempt == 0


def test_infeasible_returns_w0_after_all_attempts() -> None:
    d = _data(30, 24)
    d.w0 = np.full(30, 0.0005)
    d.lo = np.full(30, 0.005)  # every name long, but dollar neutral: infeasible
    d.hi = np.full(30, 0.01)
    res = op.solve(d, op.OptConfig(participation=None))
    assert not res.ok
    assert np.array_equal(res.w, d.w0)
    assert res.attempt == 3 and len(res.attempt_log) == 4  # every step was tried
    assert res.reason.count(";") == 3


def test_violating_solution_is_rejected_and_ladder_continues(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    d = _data(40, 25)
    cfg = op.OptConfig(participation=None)
    calls = []
    real = op.max_violation

    def fake(data, w, c):
        calls.append(1)
        return 0.5 if len(calls) == 1 else real(data, w, c)

    monkeypatch.setattr(op, "max_violation", fake)
    res = op.solve(d, cfg)
    assert res.ok and res.attempt == 1  # attempt 0 was rejected for its violation
    assert res.attempt_log[0].startswith("first:")
    calls.clear()
    monkeypatch.setattr(op, "max_violation", lambda *a: 0.5)
    assert not op.solve(d, cfg).ok
    assert op.solve(d, cfg.with_(max_violation_tol=None)).ok  # gate can be switched off


def test_decide_record_carries_attempt() -> None:
    panel, risk, attrs, etf, alpha_source = _decide_fixture()
    dec = op.make_decide(alpha_source, risk, op.BookSpec("A"), attrs=attrs, etf_risk=etf)
    from open_composer.research.equity_book.backtest import BookState

    i = 300
    empty = pd.Series(dtype=float)
    st = BookState(
        date=panel.dates[i],
        pos=i,
        equity=1.0,
        holdings=empty,
        weights=empty,
        cash=1.0,
        long_value=0.0,
        short_value=0.0,
        tbill_value=0.0,
        panel=panel,
    )
    dec(panel.dates[i], st)
    assert dec.records[-1]["attempt"] == 0 and dec.records[-1]["attempt_log"]
