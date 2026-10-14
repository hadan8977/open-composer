from hf_accounts import FundedBook, positive_target, run_funded

DATES = [
    "2016-01-04",
    "2016-01-05",
    "2016-01-06",
    "2016-01-07",
    "2016-01-08",
    "2016-01-11",
    "2016-01-12",
    "2016-01-13",
    "2016-01-14",
]


def test_gap_expires_whole_buy_without_future_downsize():
    b = FundedBook(1000, 0.002, DATES)
    b.freeze(1, 10, "signal", "fill", "test")
    assert b.pending.quantity == 99
    b.attempt("fill", DATES[0], 10.2)
    assert b.q == 0 and b.cash == 1000 and b.pending is None
    assert b.orders[-1]["status"] == "no_fill_cash_gap_whole_buy_skip"


def test_delayed_first_price_is_unavailable_for_buy_and_sell_at_nominal_time():
    b = FundedBook(1000, 0.002, DATES)
    b.freeze(1, 10, "signal", "fill", "test")
    b.attempt("fill", DATES[0], 10, 1)
    assert b.q == 0 and b.pending is None
    b.q = 99
    b.freeze(0, None, "signal2", "fill2", "test")
    b.attempt("fill2", DATES[0], 10, 1)
    assert b.q == 99 and b.pending is None
    assert all(r["status"] == "no_fill_reference_not_available_at_scheduled_time" for r in b.orders)


def test_dividend_is_priorclose_entitlement_and_actual_payable_proxy_cash():
    b = FundedBook(100, 0.002, DATES)
    b.q = 100
    a = dict(
        symbol="SPY",
        id="realfield",
        type="cash_dividends",
        ex_date=DATES[0],
        payable_date=DATES[2],
        amount=2,
    )
    b.begin_day(DATES[0], [a])
    assert b.cash == 100 and b.nav(10) == 1300
    assert b.dividends[0]["due"] == DATES[3]
    b.begin_day(DATES[2], [])
    assert b.cash == 100
    b.begin_day(DATES[3], [])
    assert b.cash == 300 and not b.dividends


def test_sale_is_not_available_for_reentry_before_four_eligible_dates():
    b = FundedBook(100, 0.002, DATES)
    b.q = 90
    b.freeze(0, None, "before", "sell", "test")
    b.attempt("sell", DATES[0], 10)
    assert b.cash == 100 and b.unsettled[0]["due"] == DATES[4]
    b.freeze(1, 10, "after", "buy", "test")
    assert b.pending.quantity == 9
    b.pending = None
    b.begin_day(DATES[3], [])
    assert b.cash == 100
    b.begin_day(DATES[4], [])
    assert abs(b.cash - 998.2) < 1e-10 and not b.unsettled


def test_bil_odd_split_only_affected_physical_book_and_metrics_are_unknown():
    a = dict(symbol="BIL", id="actualsplit", type="reverse_splits", ex_date=DATES[0], ratio=0.5)
    for q, expected in [(219, True), (218, False), (0, False)]:
        b = FundedBook(100, 0.002, DATES, "BIL")
        b.q = q
        b.begin_day(DATES[0], [a])
        assert b.q == q // 2 and b.cash == 100 and b.cash_in_lieu_unknown == expected
        assert (b.nav(100) is None) == expected


def test_thresholds_keep_actual_holding_and_missing_is_explicit_zero():
    assert positive_target(0.002, 0.002, True) == 1
    assert positive_target(-0.002, 0.002, True) == 1
    assert positive_target(0.00201, 0.002, False) == 1
    assert positive_target(-0.00201, 0.002, True) == 0
    assert positive_target(None, 0.002, True) == 0


def test_night_uses_preceding_known_bar_and_absent_lastbar_expires_without_fake_close():
    days = [dict(date=DATES[0], regular15_windows=6), dict(date=DATES[1], regular15_windows=6)]
    bars = {DATES[1]: {k: dict(open=10, close=10, first_price_age_minutes=0) for k in range(5)}}
    r = run_funded(
        days, bars, {d: 10 for d in DATES}, {}, [], DATES, 0.002, 1000, mode="overnight_only"
    )
    assert r["daily"][-1]["nav"] == 1000 and r["daily"][-1]["q"] == 0
    assert r["orders"][-1]["reason"] == "night_priority_known_lot"
    assert r["orders"][-1]["known_sizing_reference"] == 10
    assert r["orders"][-1]["status"] == "no_fill_reference_not_available_at_scheduled_time"
