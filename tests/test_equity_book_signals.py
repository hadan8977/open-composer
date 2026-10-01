from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from scipy.stats import norm

from open_composer.research.equity_book import signals as sg

# ---------------------------------------------------------------------------
# point-in-time
# ---------------------------------------------------------------------------


def test_filing_on_t_is_usable_from_t_plus_1_only() -> None:
    facts = pd.DataFrame(
        {
            "cik": [1, 1],
            "period_end": pd.to_datetime(["2022-12-31", "2023-12-31"]),
            "val": [100.0, 150.0],
            "filed": pd.to_datetime(["2023-02-15", "2024-02-15"]),
            "usable_session": pd.to_datetime(["2023-02-16", "2024-02-16"]),
        }
    )
    events, dropped = sg.annual_flow_events(facts)
    assert dropped == 0
    days = pd.Series(pd.to_datetime(["2024-02-14", "2024-02-15", "2024-02-16", "2024-02-20"]))
    got = sg.annual_flow_asof(events, pd.Series([1, 1, 1, 1]), days)
    # the 10-K filed on 2024-02-15 is not in force at the close of 2024-02-15, only from 02-16
    assert got.tolist() == [100.0, 100.0, 150.0, 150.0]


def test_fact_not_usable_after_filing_date_is_dropped() -> None:
    facts = pd.DataFrame(
        {
            "cik": [1, 1],
            "period_end": pd.to_datetime(["2022-12-31", "2023-12-31"]),
            "val": [100.0, 150.0],
            "filed": pd.to_datetime(["2023-02-15", "2024-02-15"]),
            "usable_session": pd.to_datetime(["2023-02-16", "2024-02-15"]),  # same day: violation
        }
    )
    events, dropped = sg.annual_flow_events(facts)
    assert dropped == 1
    got = sg.annual_flow_asof(events, pd.Series([1]), pd.Series(pd.to_datetime(["2024-02-15"])))
    assert got.tolist() == [100.0]


def test_annual_flow_late_restatement_of_old_year_does_not_regress() -> None:
    facts = pd.DataFrame(
        {
            "cik": [1, 1, 1],
            "period_end": pd.to_datetime(["2021-12-31", "2022-12-31", "2021-12-31"]),
            "val": [10.0, 20.0, 99.0],  # third: a late (first-filed) row for the older year
            "filed": pd.to_datetime(["2022-02-01", "2023-02-01", "2023-06-01"]),
            "usable_session": pd.to_datetime(["2022-02-02", "2023-02-02", "2023-06-02"]),
        }
    )
    events, _ = sg.annual_flow_events(facts)
    got = sg.annual_flow_asof(
        events, pd.Series([1, 1]), pd.Series(pd.to_datetime(["2023-03-01", "2023-07-01"]))
    )
    assert got.tolist() == [20.0, 20.0]


def test_annual_flow_asof_missing_cik_and_no_event_yet_are_nan() -> None:
    events = pd.DataFrame(
        {"cik": [1], "usable_session": pd.to_datetime(["2023-01-10"]), "val": [5.0]}
    )
    got = sg.annual_flow_asof(
        events,
        pd.Series([1, 2, np.nan]),
        pd.Series(pd.to_datetime(["2023-01-09", "2023-02-01", "2023-02-01"])),
    )
    assert np.isnan(got).all()


def _insider_frame(visible: list[str], dates: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "visible_at": pd.to_datetime(visible, utc=True),
            "cmp_opportunistic_buy_60d": [3.0] * len(dates),
            "net_buy_usd_nonplan_60d": [1000.0] * len(dates),
        }
    )


def test_insider_form4_visible_after_the_close_is_masked() -> None:
    dates = pd.Series(pd.to_datetime(["2024-01-10", "2024-01-10", "2024-07-10", "2024-07-10"]))
    f = _insider_frame(
        [
            "2024-01-10 14:30",  # open of t: visible
            "2024-01-10 21:30",  # 16:30 EST, after the close: masked
            "2024-07-10 19:30",  # 15:30 EDT: visible
            "2024-07-10 20:30",  # 16:30 EDT: masked (a fixed 21:00 UTC cut would let it through)
        ],
        list(dates),
    )
    out = sg.insider_raw(f, np.array([1e6] * 4), dates)
    assert out["cmp_opp_buy_60d"].notna().tolist() == [True, False, True, False]
    assert out["nonplan_buy_mcap_60d"].iloc[0] == pytest.approx(1000.0 / 1e6)
    assert out["nonplan_buy_mcap_60d"].iloc[1] != out["nonplan_buy_mcap_60d"].iloc[1]  # NaN


def test_session_close_utc_handles_dst() -> None:
    got = sg.session_close_utc(pd.Series(pd.to_datetime(["2024-01-10", "2024-07-10"])))
    assert got.iloc[0] == pd.Timestamp("2024-01-10 21:00", tz="UTC")
    assert got.iloc[1] == pd.Timestamp("2024-07-10 20:00", tz="UTC")


def test_short_volume_visible_date_t_plus_1_is_masked() -> None:
    t = pd.Series(pd.to_datetime(["2024-03-04", "2024-03-04", "2024-03-04"]))
    f = pd.DataFrame(
        {
            "visible_date": pd.to_datetime(["2024-03-04", "2024-03-05", None]),
            "short_volume_ratio_mean_21": [0.4, 0.4, 0.4],
        }
    )
    got = sg.short_volume_raw(f, t)
    assert got[0] == pytest.approx(-0.4)  # visible on t
    assert np.isnan(got[1])  # visible only at t + 1
    assert got[2] == pytest.approx(-0.4)  # carried row without a record: built from earlier ones


def test_short_interest_and_news_visibility_and_as_filed_share_ratio() -> None:
    t = pd.Series(pd.to_datetime(["2024-03-04", "2024-03-04"]))
    si = pd.DataFrame(
        {
            "visible_date": pd.to_datetime(["2024-03-04", "2024-03-05"]),
            "short_interest_shares": [2_000_000.0, 2_000_000.0],
        }
    )
    got = sg.short_interest_raw(si, np.array([100e6, 100e6]), t)
    assert got[0] == pytest.approx(-0.02)
    assert np.isnan(got[1])
    news = pd.DataFrame(
        {
            "visible_at": pd.to_datetime(["2024-03-04 14:30", "2024-03-05 14:30"], utc=True),
            "attention_surge_5d": [1.5, 2.5],
        }
    )
    ng = sg.news_raw(news, t)
    assert ng[0] == 1.5 and np.isnan(ng[1])


def test_missing_visible_timestamp_is_not_visible() -> None:
    v = pd.Series(pd.to_datetime([None, "2024-01-10 14:30"], utc=True))
    d = pd.Series(pd.to_datetime(["2024-01-10", "2024-01-10"]))
    assert sg.visible_ts_by_close(v, d).tolist() == [False, True]


def test_momentum_and_residual_momentum_ignore_the_last_21_sessions() -> None:
    rng = np.random.default_rng(0)
    close = 50 * np.cumprod(1 + rng.normal(0, 0.01, (400, 3)), axis=0)
    base = sg.momentum_matrix(close)
    t = 330
    changed = close.copy()
    changed[t - 20 :] *= 3.0  # the last 20 sessions up to and including t
    assert sg.momentum_matrix(changed)[t] == pytest.approx(base[t])
    assert not np.allclose(sg.momentum_matrix(changed)[t + 1 : t + 6], base[t + 1 : t + 6])
    assert base[t] == pytest.approx(close[t - 21] / close[t - 252] - 1.0)
    r = rng.normal(0, 0.01, (400, 3))
    v0, _ = sg.resid_momentum(r, np.full_like(r, np.nan))
    r2 = r.copy()
    r2[t - 20 : t + 1] += 0.5
    v1, _ = sg.resid_momentum(r2, np.full_like(r, np.nan))
    assert v1[t] == pytest.approx(v0[t])
    r3 = r.copy()
    r3[t - 252] += 0.5  # the day before the window starts is not in it either
    v3, _ = sg.resid_momentum(r3, np.full_like(r, np.nan))
    assert v3[t] == pytest.approx(v0[t])
    r4 = r.copy()
    r4[t - 251] += 0.5  # the first day of the window is in it
    v4, _ = sg.resid_momentum(r4, np.full_like(r, np.nan))
    assert v4[t] != pytest.approx(v0[t])


def test_overnight_mean_uses_data_through_t_and_requires_200_obs() -> None:
    rng = np.random.default_rng(1)
    c = 20 * np.cumprod(1 + rng.normal(0, 0.01, (300, 2)), axis=0)
    o = c * (1 + rng.normal(0, 0.002, c.shape))
    on = sg.overnight_matrix(o, c)
    assert np.isnan(on[0]).all()
    m = sg.rolling_mean_min_obs(on, 252, 200)
    assert np.isnan(m[150]).all()  # fewer than 200 valid
    assert m[290, 0] == pytest.approx(np.nanmean(on[290 - 251 : 291, 0]))
    on[:, 1] = np.nan
    on[250:, 1] = 0.001
    assert np.isnan(sg.rolling_mean_min_obs(on, 252, 200)[290, 1])  # only 41 valid in the window


def test_seasonality_uses_only_prior_years_and_needs_three() -> None:
    idx = pd.MultiIndex.from_tuples([(y, 6) for y in range(2018, 2025)], names=["year", "month"])
    m = pd.DataFrame({"A": [0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 9.0]}, index=idx)
    # target June 2024: 2019-2023 -> mean(0.02..0.06); the 2024 value itself (9.0) is not used
    assert sg.seasonality(m, 2024, 6)["A"] == pytest.approx(0.04)
    # target June 2021: only 2018-2020 exist -> three years, ok; target June 2020 -> two years
    assert sg.seasonality(m, 2021, 6)["A"] == pytest.approx(0.02)
    assert np.isnan(sg.seasonality(m, 2020, 6)["A"])


def test_month_end_closes_and_monthly_returns() -> None:
    dates = pd.bdate_range("2023-11-27", "2024-02-02")
    close = np.tile(np.arange(len(dates), dtype=float)[:, None] + 10.0, (1, 2))
    close[-3:, 1] = np.nan  # second column stops trading before the last month end
    me = sg.month_end_closes(close, dates)
    assert list(me.index) == [(2023, 11), (2023, 12), (2024, 1), (2024, 2)]
    assert me.loc[(2023, 12), 0] == close[dates.get_loc(pd.Timestamp("2023-12-29")), 0]
    ret = sg.monthly_returns(me)
    assert np.isnan(ret.iloc[0]).all()
    assert ret.loc[(2024, 1), 0] == pytest.approx(
        close[dates.get_loc(pd.Timestamp("2024-01-31")), 0]
        / close[dates.get_loc(pd.Timestamp("2023-12-29")), 0]
        - 1.0
    )


# ---------------------------------------------------------------------------
# processing
# ---------------------------------------------------------------------------


def test_rank_normal_known_values_ties_and_nan() -> None:
    z = sg.rank_normal(np.array([10.0, 30.0, 20.0, np.nan]))
    assert z[0] == pytest.approx(norm.ppf(0.5 / 3))
    assert z[2] == pytest.approx(0.0)
    assert z[1] == pytest.approx(norm.ppf(2.5 / 3))
    assert np.isnan(z[3])
    t = sg.rank_normal(np.array([1.0, 1.0, 2.0, 3.0]))
    assert t[0] == t[1]  # tied values share the average rank (1.5)
    assert t[0] == pytest.approx(norm.ppf(1.0 / 4))
    big = sg.rank_normal(np.random.default_rng(2).normal(size=5000))
    assert abs(big.mean()) < 1e-9 and big.std() == pytest.approx(1.0, abs=0.02)


def test_winsorize_clips_at_one_and_ninety_nine_percent() -> None:
    x = np.arange(1.0, 101.0)
    x[-1] = 1e9
    x[0] = -1e9
    w = sg.winsorize(x)
    lo, hi = np.quantile(x, [0.01, 0.99])
    assert w.min() == pytest.approx(lo) and w.max() == pytest.approx(hi)
    assert np.isfinite(w).all()
    assert w[50] == x[50]
    out = sg.winsorize(np.array([1.0, np.inf, np.nan, 2.0, 3.0]))
    assert np.isnan(out[1]) and np.isnan(out[2])


def test_industry_demean_zero_group_means_small_groups_and_unclassified_untouched() -> None:
    z = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 10.0, 20.0, 7.0, np.nan, 8.0])
    codes = np.array([0, 0, 0, 0, 0, 1, 1, 2, 0, -1])
    out = sg.industry_demean(z, codes, min_members=3)
    assert out[:5].sum() == pytest.approx(0.0)  # group 0: the NaN is ignored, mean 3
    assert out[:5].tolist() == [-2.0, -1.0, 0.0, 1.0, 2.0]
    assert out[5] == 10.0 and out[6] == 20.0 and out[7] == 7.0  # groups of < 3: untouched
    assert np.isnan(out[8])
    assert out[9] == 8.0  # unclassified


def test_missing_becomes_zero_while_coverage_flag_stays_false() -> None:
    raw = np.array([1.0, np.nan, 3.0, np.inf, 2.0, 5.0, 4.0])
    score, cov = sg.process_signal(raw, np.zeros(7, dtype=int), demean=False)
    assert cov.tolist() == [True, False, True, False, True, True, True]
    assert score[1] == 0.0 and score[3] == 0.0
    assert (score[cov] != 0.0).sum() >= 4  # the covered names keep a real score


def test_process_signal_demean_only_when_asked() -> None:
    raw = np.arange(1.0, 13.0)
    codes = np.array([0] * 6 + [1] * 6)
    plain, _ = sg.process_signal(raw, codes, demean=False)
    dm, _ = sg.process_signal(raw, codes, demean=True)
    assert plain[:6].mean() < 0 < plain[6:].mean()
    assert dm[:6].mean() == pytest.approx(0.0) and dm[6:].mean() == pytest.approx(0.0)


def test_industry_codes_use_the_risk_groups_and_flag_unclassified() -> None:
    mapping = {1: "ff12_01", 2: "ff48_02", 3: "ff12_01"}
    groups = ["ff12_01", "ff48_02"]
    got = sg.industry_codes(pd.Series([1, 2, 3, np.nan, 49]), mapping, groups)
    assert got.tolist() == [0, 1, 0, -1, -1]


def test_load_industry_groups_matches_risk_model_meta() -> None:
    mapping, groups = sg.load_industry_groups()
    assert set(mapping) == set(range(1, 49))
    assert set(mapping.values()) <= set(groups) and groups == sorted(groups)


# ---------------------------------------------------------------------------
# signs, composite, formulas
# ---------------------------------------------------------------------------


def test_raw_signs_follow_the_design_table() -> None:
    f = pd.DataFrame(
        {
            "mcap": [1000.0],
            "stockholders_equity": [500.0],
            "total_assets": [2000.0],
            "gross_profitability": [0.3],
            "roe": [0.1],
            "accruals": [0.05],
            "asset_growth": [0.2],
            "sue_eps": [1.2],
            "sue_rev": [0.7],
            "ni_a": [80.0],
            "rev_a": [3000.0],
            "ocf_a": [120.0],
            "opinc_a": [200.0],
        }
    )
    r = sg.fundamental_raw(f).iloc[0]
    assert r["bm"] == pytest.approx(0.5) and r["ep"] == pytest.approx(0.08)
    assert r["sp"] == pytest.approx(3.0) and r["cfp"] == pytest.approx(0.12)
    assert r["op_at"] == pytest.approx(0.1) and r["gp_at"] == 0.3 and r["roe"] == 0.1
    assert r["neg_accruals"] == pytest.approx(-0.05)  # high accruals are bearish
    assert r["neg_asset_growth"] == pytest.approx(-0.2)  # high asset growth is bearish
    assert r["sue_eps"] == 1.2 and r["sue_rev"] == 0.7
    bad = f.assign(mcap=-1.0, total_assets=0.0)
    rb = sg.fundamental_raw(bad).iloc[0]
    assert np.isnan(rb["bm"]) and np.isnan(rb["op_at"])


def test_lowrisk_signs_beta_and_idio_vol_are_negated() -> None:
    d = pd.Series(pd.to_datetime(["2024-03-04"] * 6))
    beta = np.array([0.5, 0.8, 1.0, 1.2, 1.5, 2.0])
    iv = np.array([0.01, 0.015, 0.02, 0.025, 0.03, 0.04])
    mv = pd.Series({pd.Timestamp("2024-03-04"): 1e-4})
    nb, niv = sg.lowrisk_raw(d, beta, iv, np.full(6, 1e9), mv)
    assert np.all(np.diff(nb) < 0)  # a higher beta gives a lower score
    assert niv.tolist() == (-iv).tolist()
    assert np.corrcoef(nb, -beta)[0, 1] > 0.99


def _slow_frame(n: int = 80, dates: int = 3, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = np.repeat(pd.date_range("2024-03-04", periods=dates), n)
    df = pd.DataFrame(
        {
            "trade_date": d,
            "symbol": np.tile([f"S{i:03d}" for i in range(n)], dates),
            "ind_code": np.tile(np.arange(n) % 4, dates).astype("int16"),
            "resid_mom_fallback": False,
        }
    )
    for name in sg.SLOW_NAMES + tuple(s.name for s in sg.FAST_BASE_SIGNALS):
        df[name] = rng.normal(size=len(df))
    return df


def test_composite_has_equal_theme_weights_and_positive_signs() -> None:
    n = 40
    rng = np.random.default_rng(3)
    scores = {nm: rng.normal(size=n) for nm in sg.SLOW_NAMES}
    cov = {nm: np.ones(n, dtype=bool) for nm in sg.SLOW_NAMES}
    themes, comp, k = sg.theme_composite(scores, cov)
    for t in sg.THEMES:
        names = sg.THEME_SIGNALS[t]
        assert themes[t] == pytest.approx(np.mean([scores[x] for x in names], axis=0))
    assert comp == pytest.approx(np.mean([themes[t] for t in sg.THEMES], axis=0))
    assert (k == len(sg.THEMES)).all()
    # raising one signal of a 4-signal theme by 1 moves the composite by 1/4/9; a 1-signal... use
    # a 2-signal theme (investment) for 1/2/9 and the 4-signal value theme for 1/4/9
    s2 = {nm: v.copy() for nm, v in scores.items()}
    s2["neg_nsi_12m"] = s2["neg_nsi_12m"] + 1.0
    _, comp2, _ = sg.theme_composite(s2, cov)
    assert (comp2 - comp) == pytest.approx(np.full(n, 1.0 / 2 / 9))
    s3 = {nm: v.copy() for nm, v in scores.items()}
    s3["bm"] = s3["bm"] + 1.0
    _, comp3, _ = sg.theme_composite(s3, cov)
    assert (comp3 - comp) == pytest.approx(np.full(n, 1.0 / 4 / 9))
    # a bullish signal value raises the composite (all signs +1)
    assert (comp2 > comp).all() and (comp3 > comp).all()


def test_theme_composite_counts_covered_themes_and_missing_counts_as_zero() -> None:
    n = 10
    scores = {nm: np.zeros(n) for nm in sg.SLOW_NAMES}
    cov = {nm: np.zeros(n, dtype=bool) for nm in sg.SLOW_NAMES}
    scores["mom_12_1"] = np.ones(n)
    cov["mom_12_1"] = np.ones(n, dtype=bool)
    themes, comp, k = sg.theme_composite(scores, cov)
    assert themes["momentum"] == pytest.approx(
        np.full(n, 1.0 / 3)
    )  # mean over 3 signals, 2 missing
    assert comp == pytest.approx(np.full(n, 1.0 / 3 / 9))
    assert (k == 1).all()


def test_process_frame_end_to_end_flags_zeros_and_composite() -> None:
    df = _slow_frame()
    df.loc[df.index[:10], "bm"] = np.nan
    specs = sg.all_specs({})
    out = sg.process_frame(df, specs)
    assert len(out) == len(df)
    assert out["bm_raw"].dtype == np.float32 and out["bm"].dtype == np.float32
    assert out["bm_cov"].dtype == bool
    first = out.iloc[:10]
    assert (first["bm"] == 0.0).all() and not first["bm_cov"].any()
    assert out["bm_cov"].iloc[10:].all()
    assert (out["m0_n_themes"] == 9).all()
    expect = out[[f"theme_{t}" for t in sg.THEMES]].mean(axis=1)
    assert out["m0_composite"].to_numpy() == pytest.approx(expect.to_numpy(), abs=1e-6)
    # value signals are industry-demeaned: the covered members of a group sum to ~0 per date
    one = out[
        (out["trade_date"] == out["trade_date"].iloc[0]) & out["bm_cov"] & (out["ind_code"] == 1)
    ]
    assert one["bm"].sum() == pytest.approx(0.0, abs=1e-4)
    assert out["theme_value"].to_numpy() == pytest.approx(
        out[["bm", "ep", "sp", "cfp"]].mean(axis=1).to_numpy(), abs=1e-6
    )


def test_process_frame_drops_values_float32_cannot_hold() -> None:
    df = _slow_frame(n=60, dates=1)
    specs = sg.all_specs({})
    df.loc[df.index[0], "mom_12_1"] = 1e39
    out = sg.process_frame(df, specs)
    assert not out["mom_12_1_cov"].iloc[0]
    assert out["mom_12_1"].iloc[0] == 0.0


def test_spec_registry_matches_the_design_table() -> None:
    assert len(sg.SLOW_SIGNALS) == 22
    assert set(sg.THEMES) == {s.theme for s in sg.SLOW_SIGNALS}
    demeaned = {s.name for s in sg.SLOW_SIGNALS if s.demean}
    assert demeaned == {"bm", "ep", "sp", "cfp", "gp_at", "roe", "op_at", "neg_accruals"}
    assert all(s.theme == "fast" for s in sg.FAST_BASE_SIGNALS)
    alphas = sg.alpha_specs({"alpha101": ["alpha001"], "alpha191": ["gtja002"]})
    assert [a.name for a in alphas] == ["a101_alpha001", "g191_gtja002"]


def test_group_mean_needs_enough_members() -> None:
    d = pd.Series(pd.to_datetime(["2024-01-02"] * 6))
    v = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 9.0])
    g = np.array([0, 0, 0, 0, 1, -1])
    out = sg.group_mean(v, d, g, min_n=3)
    assert out[:4].tolist() == [2.5] * 4
    assert np.isnan(out[4]) and np.isnan(out[5])


def test_group_demeaned_returns_static_groups() -> None:
    ret = np.array([[0.1, 0.2, 0.3, 0.9, np.nan]])
    group = np.array([0, 0, 0, 1, -1])
    out = sg.group_demeaned_returns(ret, group, 3)
    assert out[0, :3].tolist() == pytest.approx([-0.1, 0.0, 0.1])
    assert np.isnan(out[0, 3]) and np.isnan(out[0, 4])


def test_resid_momentum_falls_back_when_residuals_are_missing() -> None:
    rng = np.random.default_rng(4)
    r = rng.normal(0, 0.01, (300, 2))
    fb = rng.normal(0, 0.01, (300, 2))
    r[:, 1] = np.nan  # no risk-model residuals for column 1
    val, used = sg.resid_momentum(r, fb)
    assert np.isfinite(val[280, 0]) and not used[280, 0]
    assert np.isfinite(val[280, 1]) and used[280, 1]
    assert np.isnan(val[100]).all()  # not enough history


# ---------------------------------------------------------------------------
# measurement helpers
# ---------------------------------------------------------------------------


def test_rank_ic_perfect_inverse_and_nan_handling() -> None:
    x = np.arange(100.0)
    assert sg.rank_ic(x, x**3) == pytest.approx(1.0)
    assert sg.rank_ic(x, -x) == pytest.approx(-1.0)
    y = x.copy()
    y[:5] = np.nan
    assert sg.rank_ic(x, y) == pytest.approx(1.0)
    assert np.isnan(sg.rank_ic(x[:10], x[:10]))  # fewer than 30 names


def test_newey_west_t_matches_plain_t_for_iid_and_shrinks_for_persistent_series() -> None:
    rng = np.random.default_rng(5)
    iid = rng.normal(0.1, 1.0, 4000)
    assert sg.newey_west_t(iid, 0) == pytest.approx(
        iid.mean() / np.sqrt(np.var(iid) / len(iid)), rel=1e-9
    )
    assert abs(sg.newey_west_t(iid, 21) - sg.plain_t(iid)) < 0.5
    e = rng.normal(size=4000)
    ar = np.zeros(4000)
    for i in range(1, 4000):
        ar[i] = 0.9 * ar[i - 1] + e[i]
    ar += 0.3
    assert sg.newey_west_t(ar, 21) < 0.6 * sg.plain_t(ar)


# ---------------------------------------------------------------------------
# built files (skipped where the data is not present)
# ---------------------------------------------------------------------------

_BUILT = sg.SIGNALS_DIR / "2024.parquet"


@pytest.mark.skipif(not _BUILT.exists(), reason="signals/2024.parquet not built")
def test_built_year_file_invariants() -> None:
    import pyarrow.parquet as pq

    pf = pq.ParquetFile(_BUILT)
    names = [s.name for s in sg.SLOW_SIGNALS]
    cols = ["trade_date", "symbol", "ind_code", "m0_composite", "m0_n_themes"]
    cols += names + [f"{n}_raw" for n in names] + [f"{n}_cov" for n in names]
    df = pf.read_row_group(0, columns=cols).to_pandas()
    assert not df.duplicated(["trade_date", "symbol"]).any()
    for n in names:
        covered = df[f"{n}_cov"].to_numpy()
        assert np.array_equal(covered, np.isfinite(df[f"{n}_raw"].to_numpy()))
        assert (df.loc[~covered, n] == 0.0).all()
        assert df[n].dtype == np.float32 and df[f"{n}_raw"].dtype == np.float32
    # U3000 members only: the panel says so
    panel = pd.read_parquet(
        sg.DEFAULT_DIR / "panel/2024.parquet", columns=["trade_date", "symbol", "in_u3000"]
    )
    keys = set(
        zip(
            panel.loc[panel["in_u3000"], "trade_date"],
            panel.loc[panel["in_u3000"], "symbol"],
            strict=True,
        )
    )
    assert all(k in keys for k in zip(df["trade_date"], df["symbol"], strict=True))
    d0 = df[df["trade_date"] == df["trade_date"].iloc[0]]
    assert abs(d0["m0_composite"].mean()) < 0.1
