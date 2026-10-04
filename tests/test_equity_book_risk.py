# ruff: noqa: E501
"""Risk model (design section 6): style prep, constrained WLS, covariances, specific variance, reader."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import risk as rk


def test_standardize_style_properties() -> None:
    rng = np.random.default_rng(0)
    n = 2000
    x = rng.standard_t(3, n) * 2 + 5
    x[:10] = np.nan
    x[10] = 1e6  # an outlier is winsorised, not allowed to dominate
    cap = np.exp(rng.normal(20, 1.5, n))
    z = rk.standardize_style(x, cap)
    ok = np.isfinite(x)
    assert np.all(z[~ok] == 0.0)
    assert abs((z[ok] * cap[ok]).sum() / cap[ok].sum()) < 1e-12  # cap-weighted mean 0
    assert z[ok].std(ddof=0) == pytest.approx(1.0, abs=1e-12)  # equal-weighted std 1
    assert np.abs(z).max() < 4.0  # clip at 3 then re-scaled
    # ranks are preserved
    assert np.corrcoef(np.argsort(np.argsort(x[ok])), np.argsort(np.argsort(z[ok])))[0, 1] > 0.999


def test_cross_section_regression_recovers_factors_and_constraint() -> None:
    rng = np.random.default_rng(1)
    n, g, s = 1500, 6, 3
    group = rng.integers(0, g, n)
    cap = np.exp(rng.normal(20, 1.0, n))
    styles = rng.normal(size=(n, s))
    cap_g = np.bincount(group, weights=cap, minlength=g)
    ind = rng.normal(0, 0.01, g)
    ind -= (cap_g @ ind) / cap_g.sum()  # cap-weighted sum zero
    ind[1:] += 0.0
    # enforce exactly sum_g W_g f_g = 0
    ind = ind - (cap_g @ ind) / cap_g.sum()
    true = np.concatenate([[0.002], ind, [0.003, -0.002, 0.001]])
    xfull = np.zeros((n, 1 + g + s))
    xfull[:, 0] = 1
    xfull[np.arange(n), 1 + group] = 1
    xfull[:, 1 + g :] = styles
    y = xfull @ true + rng.normal(0, 0.002, n)
    f, resid, r2 = rk.cross_section_regression(y, group, styles, cap, g)
    np.testing.assert_allclose(f, true, atol=2e-3)
    assert abs(cap_g @ f[1 : 1 + g]) < 1e-9 * cap_g.sum()  # constraint holds exactly
    assert r2 > 0.2
    # residual definition: y - X f
    np.testing.assert_allclose(resid, y - xfull @ f, atol=1e-12)
    # weighted residuals are orthogonal to every free regressor (sqrt(cap) weights)
    w = np.sqrt(cap)
    assert abs((w * resid).sum()) < 1e-6 * w.sum() * 0.01
    # a group with no members gets a zero return
    f2, _, _ = rk.cross_section_regression(
        y[group != 3], group[group != 3], styles[group != 3], cap[group != 3], g
    )
    assert f2[1 + 3] == 0.0


def test_ewma_cov_recovers_known_covariance_and_lags0_is_plain_weighted() -> None:
    rng = np.random.default_rng(2)
    cov = np.array([[4.0, 1.0, 0.0], [1.0, 1.0, 0.2], [0.0, 0.2, 0.25]]) * 1e-4
    f = rng.multivariate_normal(np.zeros(3), cov, 6000)
    est = rk.ewma_cov_nw(f, halflife=2000.0, lags=2)
    np.testing.assert_allclose(est, cov, rtol=0.2, atol=2e-5)
    w = 0.5 ** ((len(f) - 1 - np.arange(len(f))) / 126.0)
    w /= w.sum()
    plain = (f * w[:, None]).T @ f
    np.testing.assert_allclose(rk.ewma_cov_nw(f, 126.0, lags=0), plain, rtol=1e-12)


def test_factor_covariance_is_psd_scale_equivariant_and_handles_dead_factor() -> None:
    rng = np.random.default_rng(3)
    f = rng.normal(0, 0.01, (800, 5))
    f[:, 2] = 0.0  # an industry that never had members
    f[:, 4] = 0.7 * f[:, 3] + 0.3 * f[:, 4]
    cov = rk.factor_covariance(f)
    assert np.linalg.eigvalsh(cov).min() > -1e-12
    assert cov[2, 2] == 0.0 and np.all(cov[2, [0, 1, 3, 4]] == 0.0)
    cov2 = rk.factor_covariance(f * 3.0)
    np.testing.assert_allclose(cov2, cov * 9.0, rtol=1e-8)
    # correlations stay in [-1, 1]
    sd = np.sqrt(np.diag(cov))
    live = sd > 0
    corr = cov[np.ix_(live, live)] / np.outer(sd[live], sd[live])
    assert np.abs(corr).max() <= 1.0 + 1e-9


def test_specific_variance_ewma_shrink_floor() -> None:
    rng = np.random.default_rng(4)
    n = 500
    sv = rk.SpecificVariance(n, halflife=63.0)
    true_sd = np.where(np.arange(n) < 250, 0.01, 0.03)
    for _ in range(400):
        sv.update(np.arange(n), rng.normal(0, 1, n) * true_sd)
    raw = sv.raw(np.arange(n))
    assert np.nanmean(raw[:250]) == pytest.approx(1e-4, rel=0.25)
    assert np.nanmean(raw[250:]) == pytest.approx(9e-4, rel=0.25)
    # fewer than 20 observations -> NaN
    sv2 = rk.SpecificVariance(3)
    sv2.update(np.array([0]), np.array([0.01]))
    assert np.isnan(sv2.raw(np.array([0, 1, 2]))).all()
    # shrink 0.3 toward the decile mean; NaN takes the decile mean; floor binds
    cap = np.arange(1.0, 101.0)
    raw = np.full(100, 4e-4)
    raw[0] = 1e-12  # below the floor (0.1 x median)
    raw[5] = np.nan
    out = rk.shrink_specific(raw, cap)
    assert out[0] >= 0.1 * np.median(out) - 1e-18
    assert out[5] == pytest.approx(np.nanmean(raw[:10]))
    raw2 = np.where(np.arange(100) % 2 == 0, 2e-4, 6e-4)
    out2 = rk.shrink_specific(raw2, cap)
    dec = np.arange(10)
    # first decile contains 5 even / 5 odd names: mean 4e-4; 0.7 * 2e-4 + 0.3 * 4e-4 = 2.6e-4
    assert out2[0] == pytest.approx(0.7 * 2e-4 + 0.3 * 4e-4)
    assert dec.size == 10


def test_industry_groups_merge_small_into_ff12_parent() -> None:
    members = pd.Series({1: 30.0, 2: 3.0, 3: 4.9, 4: 5.0})
    parent = {1: 1, 2: 1, 3: 1, 4: 1, 6: 2}
    g = rk.industry_groups(members, parent)
    assert g[1] == "ff48_01" and g[4] == "ff48_04"
    assert g[2] == "ff12_01" and g[3] == "ff12_01"  # merged into one parent group
    assert g[6] == "ff12_02"  # absent from the index = 0 members
    sic = pd.DataFrame({"ff48": [6, 6, 6, 7], "ff12": [2, 2, 1, 12]})
    assert rk.ff12_parent(sic) == {6: 2, 7: 12}


def test_vasicek_beta_shrinks_noisy_betas_more() -> None:
    rng = np.random.default_rng(5)
    n = 3000
    true = rng.normal(1.0, 0.3, n)
    idio = np.where(np.arange(n) % 2 == 0, 0.01, 0.06)
    raw = true + rng.normal(0, 1, n) * idio * 6.0
    cap = np.exp(rng.normal(20, 1, n))
    v = rk.vasicek_beta(raw, idio, cap, market_var_daily=1e-4)
    err_raw = np.abs(raw - true)
    err_v = np.abs(v - true)
    assert err_v.mean() < np.clip(err_raw, 0, None).mean()
    noisy = idio > 0.03
    assert np.var(v[noisy]) < np.var(raw[noisy])  # the noisy half is shrunk harder


def _write_tiny_model(base: Path) -> tuple[list[str], np.ndarray]:
    groups = ["ff48_01", "ff48_02"]
    factors = rk.factor_names(groups)
    base.mkdir(parents=True)
    (base / "meta.json").write_text(json.dumps({"factors": factors, "groups": groups}))
    d1, d2 = pd.Timestamp("2024-03-01"), pd.Timestamp("2024-03-08")
    rng = np.random.default_rng(6)
    syms = [f"S{i}" for i in range(40)]
    rows = []
    for d in (d1, d2):
        e = pd.DataFrame(
            {
                "trade_date": d,
                "symbol": syms,
                "industry": ["ff48_01" if i % 2 == 0 else "ff48_02" for i in range(40)],
                **{s: rng.normal(size=40) for s in rk.STYLES},
                "beta_vasicek": 1.0,
                "beta_ewma": 1.1,
                "spec_var": 1e-10,
                "mcap": np.exp(rng.normal(20, 1, 40)),
                "in_p1000": True,
            }
        )
        rows.append(e)
    pd.concat(rows).to_parquet(base / "exposures_2024.parquet")
    k = len(factors)
    a = rng.normal(size=(k, k))
    f = (a @ a.T) * 1e-6
    cov = []
    for d in (d1, d2):
        ii, jj = np.meshgrid(range(k), range(k), indexing="ij")
        cov.append(
            pd.DataFrame(
                {
                    "trade_date": d,
                    "factor_i": np.array(factors)[ii.ravel()],
                    "factor_j": np.array(factors)[jj.ravel()],
                    "value": f.ravel(),
                }
            )
        )
    pd.concat(cov).to_parquet(base / "cov_2024.parquet")
    return factors, f


def test_risk_model_reader_roundtrip_and_predicted_beta(tmp_path: Path) -> None:
    factors, f = _write_tiny_model(tmp_path / "risk")
    rm = rk.RiskModel(tmp_path / "risk")
    x, fcov, d = rm.at("2024-03-08")
    assert x.shape == (40, len(factors)) and fcov.shape == (len(factors),) * 2 and len(d) == 40
    np.testing.assert_allclose(fcov.to_numpy(), f)
    assert (x["market"] == 1.0).all() and x[["ff48_01", "ff48_02"]].sum(axis=1).eq(1.0).all()
    # as-of: a date between saved dates uses the earlier one; exact=True refuses
    assert rm.resolve("2024-03-05") == pd.Timestamp("2024-03-01")
    with pytest.raises(KeyError):
        rm.at("2024-03-05", exact=True)
    with pytest.raises(KeyError):
        rm.at("2024-02-01")
    # the cap-weighted market portfolio has beta 1 to itself (specific variance ~ 0)
    assert (rm.predicted_beta("2024-03-08") == 1.1).all()
    assert (rm.predicted_beta("2024-03-08", method="vasicek") == 1.0).all()
    b = rm.predicted_beta("2024-03-08", method="model")
    cap = rm.caps("2024-03-08").reindex(b.index)
    assert float((cap / cap.sum() * b).sum()) == pytest.approx(1.0, abs=1e-6)
    # portfolio variance helper
    w = pd.Series(1.0 / 40, index=x.index)
    v = rk.portfolio_variance(w, x, fcov, d)
    xw = x.to_numpy().T @ w.to_numpy()
    assert v == pytest.approx(float(xw @ f @ xw + (w**2 * d).sum()))


def _write_prev_year(base: Path, src_year: int = 2024, new_year: int = 2023) -> None:
    """A second synthetic year: copy the 2024 files, shifted to the last two sessions of 2023."""
    for kind in ("exposures", "cov"):
        df = pd.read_parquet(base / f"{kind}_{src_year}.parquet")
        shift = {
            pd.Timestamp("2024-03-01"): pd.Timestamp("2023-12-22"),
            pd.Timestamp("2024-03-08"): pd.Timestamp("2023-12-29"),
        }
        df["trade_date"] = df["trade_date"].map(shift)
        df.to_parquet(base / f"{kind}_{new_year}.parquet")


def test_resolve_falls_back_to_previous_year_in_early_january(tmp_path: Path) -> None:
    _write_tiny_model(tmp_path / "risk")
    _write_prev_year(tmp_path / "risk")
    rm = rk.RiskModel(tmp_path / "risk")
    # before the first 2024 saved date: previous year's last saved date
    assert rm.resolve("2024-01-02") == pd.Timestamp("2023-12-29")
    assert rm.resolve("2024-02-29") == pd.Timestamp("2023-12-29")
    # the whole reader path follows the resolved date into the older year's files
    x, f, d = rm.at("2024-01-02")
    assert x.shape[0] == 40 and f.shape[0] == len(rm.factors) and len(d) == 40
    assert len(rm.caps("2024-01-02")) == 40
    assert len(rm.predicted_beta("2024-01-02")) == 40
    # within the year nothing changes
    assert rm.resolve("2024-03-05") == pd.Timestamp("2024-03-01")
    # exact=True is unchanged: no fallback
    with pytest.raises(KeyError):
        rm.resolve("2024-01-02", exact=True)
    with pytest.raises(KeyError):
        rm.at("2024-01-02", exact=True)


def test_resolve_without_previous_year_file_still_raises(tmp_path: Path) -> None:
    _write_tiny_model(tmp_path / "risk")
    rm = rk.RiskModel(tmp_path / "risk")
    with pytest.raises(KeyError):
        rm.resolve("2024-01-02")
    # a year with no file at all falls back to the last year that has one only if it is adjacent
    with pytest.raises(KeyError):
        rm.resolve("2026-01-02")
    assert rm.resolve("2025-01-02") == pd.Timestamp("2024-03-08")


def test_ewma_beta_recovers_time_varying_beta() -> None:
    rng = np.random.default_rng(7)
    t_n, n = 400, 6
    mkt = rng.normal(0, 0.01, t_n)
    true_beta = np.array([0.5, 1.0, 1.5, 2.0, 1.0, 1.0])
    r = mkt[:, None] * true_beta + rng.normal(0, 0.004, (t_n, n))
    # the last name doubles its beta in the final 60 sessions: a fast estimator must see it
    r[-60:, 5] = mkt[-60:] * 2.0 + rng.normal(0, 0.004, 60)
    close = 100 * np.cumprod(1 + r, axis=0)
    market = np.concatenate([[np.nan], mkt[1:]])
    cols = np.arange(n)
    fast = rk.ewma_beta(close, t_n - 1, cols, market, halflife=21.0)
    slow = rk.ewma_beta(close, t_n - 1, cols, market, halflife=1e9)
    np.testing.assert_allclose(fast[:5], true_beta[:5], atol=0.3)
    assert fast[5] > slow[5] + 0.15  # reacts to the regime change
    # a hole in the prices drops those days instead of padding them
    close2 = close.copy()
    close2[300:310, 0] = np.nan
    b2 = rk.ewma_beta(close2, t_n - 1, cols, market, halflife=63.0)
    assert np.isfinite(b2[0]) and abs(b2[0] - 0.5) < 0.3
    # too little history -> NaN
    assert np.isnan(rk.ewma_beta(close, 100, cols, market)).all()
