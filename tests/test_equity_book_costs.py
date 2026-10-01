from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book import costs
from scripts import sample_equity_book_spreads as sp


def test_quote_half_spread_bp_formula_and_valid_quote_filter() -> None:
    bid = np.array([99.0, 99.0, 100.0, 0.0, -1.0, np.nan, 10.0])
    ask = np.array([101.0, 99.0, 99.0, 1.0, 5.0, 5.0, np.nan])
    hs = costs.quote_half_spread_bp(bid, ask)
    # (101 - 99) / 2 / 100 * 1e4 = 100 bp; locked, crossed, zero/negative bid, NaN dropped
    assert hs[0] == pytest.approx(100.0)
    assert np.isnan(hs[1:]).all()
    assert costs.quote_half_spread_bp(10.0, 10.01) == pytest.approx(0.5 * 0.01 / 10.005 * 1e4)


def test_quote_half_spread_is_scale_free() -> None:
    a = costs.quote_half_spread_bp(np.array([9.98]), np.array([10.02]))
    b = costs.quote_half_spread_bp(np.array([9.98 * 4]), np.array([10.02 * 4]))
    assert a == pytest.approx(b)


def _quote(t_ns: int) -> int:
    return t_ns


def test_window_stats_median_time_weight_and_invalid_rows() -> None:
    sec = 1_000_000_000
    t = np.array([0, 1, 2, 3, 4]) * sec
    bid = np.array([99.0, 99.0, 100.0, 99.5, 98.0])
    ask = np.array([101.0, 101.0, 100.0, 100.5, 102.0])  # third is locked -> dropped
    st = sp.window_stats(t, bid, ask, end_ns=10 * sec)
    assert st["n_all"] == 5 and st["n_valid"] == 4
    # half spreads: 100, 100, ~50, ~100 (4 valid quotes) -> median 100 (> 50)
    hs = costs.quote_half_spread_bp(bid, ask)
    valid = hs[np.isfinite(hs)]
    assert st["hs_med_bp"] == pytest.approx(float(np.median(valid)))
    assert st["hs_p25_bp"] <= st["hs_med_bp"] <= st["hs_p75_bp"]
    empty = sp.window_stats(t, np.zeros(5), np.zeros(5), end_ns=10 * sec)
    assert empty["n_valid"] == 0 and np.isnan(empty["hs_med_bp"])


def test_weighted_median_prefers_long_lived_quote() -> None:
    assert sp.weighted_median(np.array([1.0, 10.0]), np.array([1.0, 9.0])) == 10.0
    assert np.isnan(sp.weighted_median(np.array([np.nan]), np.array([1.0])))


def test_day_picker_is_seeded_stratified_and_skips_early_closes() -> None:
    days = [str(d.date()) for d in pd.bdate_range("2018-01-02", "2026-09-17")]
    a = sp.pick_days(days)
    assert a == sp.pick_days(list(reversed(days)))
    assert len(a) == 60 and len(set(a)) == 60
    assert sum(d.startswith("2026") for d in a) == 4
    assert all(not sp.is_early_close(pd.Timestamp(d).date()) for d in a)
    assert sp.is_early_close(pd.Timestamp("2018-11-23").date())  # Friday after Thanksgiving
    assert sp.is_early_close(pd.Timestamp("2019-12-24").date())
    assert not sp.is_early_close(pd.Timestamp("2018-11-30").date())


def test_deciles_are_equal_count_and_ordered() -> None:
    s = pd.Series(np.arange(1, 2201))
    d = sp.assign_deciles(s)
    assert d.min() == 0 and d.max() == 9
    assert (d.value_counts() == 220).all()
    assert d.is_monotonic_increasing


# ----- model --------------------------------------------------------------


def _synthetic(n: int = 4000, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    price = np.exp(rng.normal(3.5, 0.8, n))
    adv = np.exp(rng.normal(17.0, 1.5, n))
    vol = np.exp(rng.normal(np.log(0.02), 0.4, n))
    year = rng.choice([2018, 2019, 2020], n)
    eff = {2018: 0.0, 2019: 0.1, 2020: -0.2}
    eta = 12.0 + 0.3 * np.log(price) - 0.5 * np.log(adv) + 0.6 * np.log(vol)
    eta += np.array([eff[y] for y in year])
    hs = np.exp(eta + rng.normal(0, 0.2, n))
    return pd.DataFrame({"hs": hs, "price": price, "adv": adv, "vol": vol, "year": year})


def test_fit_recovers_coefficients_and_shapes() -> None:
    d = _synthetic()
    c = costs.fit_log_linear(d["hs"], d["price"], d["adv"], d["vol"], d["year"])
    assert c["a"] == pytest.approx(12.0, abs=0.35)
    assert c["b_log_price"] == pytest.approx(0.3, abs=0.03)
    assert c["c_log_dollar_adv_21"] == pytest.approx(-0.5, abs=0.03)
    assert c["d_log_vol_21"] == pytest.approx(0.6, abs=0.04)
    assert c["year_effects"]["2019"] == pytest.approx(0.1, abs=0.04)
    assert c["year_effects"]["2020"] == pytest.approx(-0.2, abs=0.04)
    assert c["n"] == len(d)
    c["smearing_factor"] = 1.0
    pred = costs.predict_half_spread_bp(c, d["price"], d["adv"], d["vol"], d["year"])
    assert pred.shape == (len(d),) and np.isfinite(pred).all()
    err = np.median(np.abs(np.log(pred / d["hs"])))
    assert err < 0.2


def _model() -> dict:
    coef = {
        "a": 9.0,
        "b_log_price": 0.3,
        "c_log_dollar_adv_21": -0.5,
        "d_log_vol_21": 0.5,
        "year_effects": {"2019": 0.1},
        "baseline_year": 2018,
        "smearing_factor": 1.0,
    }
    return {"snapshots": {s: dict(coef) for s in costs.SNAPSHOTS}}


def test_half_spread_vectorized_monotone_and_clipped() -> None:
    m = _model()
    adv = np.array([1e6, 1e7, 1e8, 1e9])
    hs = costs.half_spread_bp(np.full(4, 30.0), adv, np.full(4, 0.02), 2018, "open", m)
    assert hs.shape == (4,) and (np.diff(hs) < 0).all()  # more liquid -> tighter
    vol = costs.half_spread_bp(
        np.full(3, 30.0), np.full(3, 1e8), [0.01, 0.02, 0.04], 2018, "open", m
    )
    assert (np.diff(vol) > 0).all()  # more volatile -> wider
    # years: before baseline -> baseline effect, after the last fitted -> last effect
    y = costs.half_spread_bp(30.0, 1e8, 0.02, np.array([2015, 2018, 2019, 2026]), "open", m)
    assert y[0] == pytest.approx(y[1]) and y[3] == pytest.approx(y[2])
    assert y[2] / y[1] == pytest.approx(np.exp(0.1))
    # clip
    assert costs.half_spread_bp(1.0, 1e12, 0.0001, 2018, "open", m) >= costs.HS_BP_FLOOR
    assert costs.half_spread_bp(1e4, 1.0, 1.0, 2018, "open", m) <= costs.HS_BP_CAP
    with pytest.raises(ValueError):
        costs.half_spread_bp(30.0, 1e8, 0.02, 2018, "overnight", m)


def test_smearing_raises_the_mean_prediction() -> None:
    c = dict(_model()["snapshots"]["open"])
    c["smearing_factor"] = 1.25
    a = costs.predict_half_spread_bp(c, 30.0, 1e8, 0.02, 2018, smear=False)
    b = costs.predict_half_spread_bp(c, 30.0, 1e8, 0.02, 2018, smear=True)
    assert b / a == pytest.approx(1.25)


def test_shipped_model_json_loads_and_predicts() -> None:
    m = costs.load_model()
    assert set(m["snapshots"]) == set(costs.SNAPSHOTS)
    assert m["sample"]["n_days"] >= 20
    hs = costs.half_spread_bp(
        np.array([20.0, 20.0]), np.array([1e7, 1e9]), np.array([0.02, 0.02]), 2026, "open"
    )
    assert hs[0] > hs[1] > 0


# ----- impact, fees, borrow, hook ------------------------------------------


def test_impact_square_root_law() -> None:
    # Y * sigma * sqrt(Q / V): 0.5 * 0.02 * sqrt(0.01) = 0.001 = 10 bp
    assert costs.impact_bp(1e5, 1e7, 0.02) == pytest.approx(10.0)
    assert costs.impact_bp(4e5, 1e7, 0.02) == pytest.approx(20.0)  # sqrt scaling
    assert costs.impact_bp(-1e5, 1e7, 0.02) == pytest.approx(10.0)  # sells cost the same
    assert costs.impact_bp(1e5, 1e7, 0.02, Y=1.0) == pytest.approx(20.0)
    assert costs.impact_bp(0.0, 1e7, 0.02) == 0.0
    assert costs.impact_bp(1e5, 0.0, 0.02) == 0.0


def test_borrow_rates_and_stress() -> None:
    assert costs.FEES_BP_PER_SIDE == 0.5
    assert costs.borrow_bp_per_year(True) == 25.0
    assert costs.borrow_bp_per_year(True, stress=True) == 100.0
    arr = costs.borrow_bp_per_year(np.array([True, False]))
    assert arr[0] == 25.0 and np.isnan(arr[1])  # not short-eligible: poisoned, never cheap
    d = costs.borrow_cost_dollars_per_day(np.array([-1e6]), np.array([True]))
    assert d[0] == pytest.approx(1e6 * 25 / 1e4 / 252)


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": ["A", "B", "C"],
            "dollar_trade": [10_000.0, -20_000.0, 5_000.0],
            "price": [50.0, 20.0, 10.0],
            "dollar_adv_21": [1e8, 1e7, 1e6],
            "vol_21": [0.02, 0.03, 0.04],
            "trade_date": pd.to_datetime(["2024-03-04"] * 3),
        }
    )


def test_trade_cost_dollars_components() -> None:
    m = _model()
    t = _trades()
    bp = costs.trade_cost_bp(t, model=m)
    hs = costs.half_spread_bp(t["price"], t["dollar_adv_21"], t["vol_21"], 2024, "open", m)
    imp = costs.impact_bp(t["dollar_trade"], t["dollar_adv_21"], t["vol_21"])
    assert bp.to_numpy() == pytest.approx(hs + imp + costs.FEES_BP_PER_SIDE)
    dollars = costs.trade_cost_dollars(t, None, model=m)
    assert dollars == pytest.approx(float((t["dollar_trade"].abs() * bp / 1e4).sum()))
    no_imp = costs.trade_cost_dollars(t, None, model=m, include_impact=False)
    assert no_imp < dollars
    assert costs.trade_cost_dollars(t.iloc[0:0], None, model=m) == 0.0


def test_trade_cost_missing_inputs_are_not_free_and_columns_remap() -> None:
    m = _model()
    t = _trades()
    t.loc[1, "vol_21"] = np.nan
    cost = costs.trade_cost_dollars(t, model=m)
    floor_cost = 20_000.0 * (costs.HS_BP_CAP + costs.FEES_BP_PER_SIDE) / 1e4
    assert cost >= floor_cost
    r = _trades().rename(columns={"dollar_trade": "usd", "price": "px"})
    a = costs.trade_cost_dollars(r, model=m, columns={"dollar_trade": "usd", "price": "px"})
    assert a == pytest.approx(costs.trade_cost_dollars(_trades(), model=m))


def test_flat_and_tiered_comparators() -> None:
    assert costs.flat_cost_bp(10, 3).tolist() == [10.0] * 3
    t = costs.tiered_cost_bp([1, 500, 501, 1000, 1001, 1500, 1501, np.nan])
    assert t.tolist() == [3.0, 3.0, 6.0, 6.0, 12.0, 12.0, 25.0, 25.0]
