import json
from pathlib import Path

import numpy as np
import pandas as pd
from evaluator import cash_due_date, make_signals, simulate

from open_composer.market_sessions import us_equity_session_dates


def path(prices, target, capital=1000, cost=0, actions=(), start="2026-09-28"):
    ix = pd.bdate_range(start, periods=len(prices))
    p = pd.Series(prices, index=ix, dtype=float)
    return simulate(p, p, pd.Series(target, index=ix), list(actions), capital, cost)


def test_ex_entitlement_and_actual_payable_cash_clock():
    action = {
        "id": "div",
        "type": "cash_dividends",
        "ex_date": "2026-09-29",
        "payable_date": "2026-09-30",
        "amount": 1,
    }
    f, o, e, s = path([100] * 5, [1] * 5, actions=[action])
    # Entry on ex-date does not earn it. No futureholding/reinvestment substitution.
    assert s["dividend_entitlements_dollars"] == 0
    action["ex_date"] = "2026-09-30"
    action["payable_date"] = "2026-10-01"
    f, o, e, s = path([100] * 6, [1] * 6, actions=[action])
    assert f.iloc[2].dividend_receivable == 9 and f.iloc[3].dividend_receivable == 9
    assert f.iloc[4].dividend_receivable == 0 and f.iloc[4].proxy_available_cash == 109


def test_sales_t2_and_t1_never_spend_unsettled_credit():
    for start, lag in [("2024-05-13", 3), ("2024-06-03", 2)]:
        f, o, e, s = path([100] * 7, [1, 0, 1, 1, 0, 0, 0], start=start)
        assert o[1]["side"] == "sell" and o[1]["date"] == str(f.index[2].date())
        assert f.iloc[2].unavailable_sales_credit == 900
        assert f.iloc[2 + lag].unavailable_sales_credit == 0
        if lag >= 2:
            assert f.iloc[3].unavailable_sales_credit == 900
        # Subsequententry size used yesterday's settledcash, neverfuture900 sale credit.
        assert all(
            x["quantity"] <= 1
            for x in o[2:]
            if x["side"] == "buy" and x["date"] < str(f.index[2 + lag].date())
        )


def test_frozen_quantity_gap_skips_whole_intent():
    f, o, e, s = path([100, 108, 100], [1, 0, 0])
    assert o[0]["accepted"] is False and o[0]["quantity"] == 9
    assert f.iloc[1].shares == 0 and f.iloc[1].nav == 1000


def test_stress_has_its_own_funded_integer_budget():
    f, o, e, s = path([100] * 3, [1] * 3, capital=1053, cost=0.002)
    g, p, a, t = path([100] * 3, [1] * 3, capital=1053, cost=0.004)
    assert o[0]["quantity"] == 10 and p[0]["quantity"] == 9
    assert f.proxy_available_cash.min() >= 0 and g.proxy_available_cash.min() >= 0


def test_split_transforms_overnight_frozen_lot_and_limit():
    a = {"id": "split", "type": "forward_splits", "ex_date": "2026-09-29", "ratio": 2}
    f, o, e, s = path([100, 50, 50], [1, 1, 1], actions=[a])
    assert o[0]["quantity"] == 18 and o[0]["limit"] == 52.5
    assert f.iloc[1].shares == 18 and f.iloc[1].nav == 1000


def test_prefix_invariance_and_holiday_phase():
    ix = pd.DatetimeIndex(
        us_equity_session_dates(
            pd.Timestamp("2024-01-02").date(), pd.Timestamp("2025-11-04").date()
        )
    )[:440]
    rng = np.random.default_rng(48)
    df = pd.DataFrame(
        {"SPY": 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(ix)))), "SSO": 100.0, "BIL": 100.0},
        index=ix,
    )
    ev = [{"date": "2024-12-18"}, {"date": "2025-01-29"}]
    a = make_signals(df, ev)
    changed = df.copy()
    changed.iloc[400:, 0] *= 2
    b = make_signals(changed, ev)
    pd.testing.assert_frame_equal(a.iloc[:399], b.iloc[:399])
    row = a.loc["2024-12-24"]
    assert row.next_phase == 6  # nextsession26Dec;25Dec counts as weekday


def test_three_clocks_federal_holiday_cash_exclusion():
    eligible = [
        pd.Timestamp(x)
        for x in json.loads((Path(__file__).parent / "cash-calendar.json").read_text())[
            "eligible_dates"
        ]
    ]
    assert cash_due_date("2026-10-09", eligible) == pd.Timestamp("2026-10-14")
    assert cash_due_date("2026-10-09", eligible, dividend=True) == pd.Timestamp("2026-10-13")
    assert cash_due_date("2016-10-07", eligible) == pd.Timestamp("2016-10-14")


def test_descriptive_source_state_excludes_current_day_label():
    from evaluator import lagged_wealth_excess

    ix = pd.bdate_range("2026-09-01", periods=8)
    m = pd.Series([0, 0, 0, 0, 0, -0.5, 0, 0], index=ix, dtype=float)
    rf = pd.Series(0.0, index=ix)
    feature = lagged_wealth_excess(m, rf, 5)
    assert feature.iloc[5] == 0 and feature.iloc[6] == -0.5


def test_dateonly_event_does_not_activate_same_meeting_close():
    ix = pd.DatetimeIndex(
        us_equity_session_dates(
            pd.Timestamp("2024-01-02").date(), pd.Timestamp("2025-02-28").date()
        )
    )
    df = pd.DataFrame({"SPY": 100.0, "SSO": 100.0, "BIL": 100.0}, index=ix)
    result = make_signals(
        df, [{"date": "2024-12-18", "replay_activation_at": "2024-12-19T21:00:00+00:00"}]
    )
    assert pd.isna(result.loc["2024-12-18", "anchor"])
    assert result.loc["2024-12-19", "anchor"] == pd.Timestamp("2024-12-18")
