import math

import numpy as np
from hf_diagnostics import RULES, desired, diagnostic_inventory, run_fractional


def test_nonzero_cost_preserves_plain_entries_and_sufficient_hold():
    assert desired(0.001, 0.002, "Positive", 0) == 1
    assert desired(0.001, 0.002, "Sign", 0) == 1
    assert desired(0.001, 0.002, "SPositive", 0) == 0
    assert desired(0.001, 0.002, "SSign", 0) == 0
    assert desired(-0.001, 0.002, "Positive", 1) == 0
    assert desired(-0.001, 0.002, "SPositive", 1) == 1
    assert desired(-0.001, 0.002, "Sign", 1) == -1
    assert desired(-0.001, 0.002, "SSign", 1) == 1


def test_source_plain_zero_and_sufficient_inclusive_band_boundaries():
    for rule in ["Sign", "Positive"]:
        assert desired(0, 0.002, rule, 0) == 1
    for rule in ["SSign", "SPositive"]:
        assert desired(0.002, 0.002, rule, 0) == 0
        assert desired(-0.002, 0.002, rule, 1) == 1
        assert desired(0.0021, 0.002, rule, 0) == 1
    assert desired(-0.0021, 0.002, "SSign", 1) == -1
    assert desired(-0.0021, 0.002, "SPositive", 1) == 0
    for rule in RULES:
        assert desired(None, 0.002, rule, 1) == 0
        assert desired(math.nan, 0.002, rule, 1) == 0


def test_exact_800_inventory_includes_every_nonzero_cost_plain_path():
    inventory = diagnostic_inventory([f"pipeline{i}" for i in range(20)])
    assert len(inventory) == len(set(inventory)) == 800
    assert {r[2] for r in inventory} == set(RULES)
    for rule in RULES:
        assert sum(r[2] == rule for r in inventory) == 200
        assert sum(r[2] == rule and r[1] == 20 for r in inventory) == 40


def fixture():
    dates = ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-07"]
    days = [dict(date=d, regular15_windows=7) for d in dates[:3]]
    bars = {
        d: {k: dict(open=10.0, close=10.0, first_price_age_minutes=0) for k in range(7)}
        for d in dates[1:3]
    }
    bars[dates[2]][0]["open"] = 11.0
    scores = {(d, 630): 0.001 for d in dates[1:3]}
    return dates, days, bars, scores


def test_real_book_plain_vs_sufficient_orders_and_daily_attribution_identity():
    dates, days, bars, scores = fixture()
    books = {
        rule: run_fractional(days, bars, dict.fromkeys(dates, 10.0), scores, [], dates,
                             0.002, rule, True, 0)
        for rule in RULES
    }
    for rule in ["Sign", "Positive"]:
        event = books[rule]["events"]
        entry = event[(event["day"] == 1) & (event["minute"] == 630)]
        assert len(entry) == 1 and entry["q_after"][0] > 0 and entry["fee"][0] > 0
    for rule in ["SSign", "SPositive"]:
        event = books[rule]["events"]
        assert not np.any((event["day"] == 1) & (event["minute"] == 630))
    for book in books.values():
        net = book["nav"][1:] / book["nav"][:-1] - 1
        np.testing.assert_allclose(
            net, book["overnight_gross_daily"][1:] + book["intraday_net_daily"][1:], atol=1e-15
        )
        assert book["overnight_gross_daily"][2] > 0
        assert book["overnight_target"] == 1


def test_delayed_open_cannot_supply_attribution_and_scheduled_entry_expires():
    dates, days, bars, scores = fixture()
    bars[dates[1]][4]["first_price_age_minutes"] = 2
    bars[dates[2]][0]["first_price_age_minutes"] = 2
    book = run_fractional(days, bars, dict.fromkeys(dates, 10.0), scores, [], dates,
                          0.002, "Positive", True, 0)
    event = book["events"]
    entry = event[(event["day"] == 1) & (event["minute"] == 630)]
    assert len(entry) == 1 and entry["status"][0] == 0 and entry["q_after"][0] == 0
    assert np.isnan(book["overnight_gross_daily"][2])
    assert np.isfinite(book["nav"]).all()
