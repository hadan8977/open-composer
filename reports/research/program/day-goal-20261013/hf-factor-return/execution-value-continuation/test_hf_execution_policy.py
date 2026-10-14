"""I1-I4 behavioral acceptance; synthetic prices only, no original book rerun."""

import math
import pickle
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from hf_accounts import run_funded  # noqa: E402
from hf_execution_policy import (  # noqa: E402
    POLICIES,
    Clock,
    MissingState,
    PassiveAnchor,
    ShareBook,
    dynamic_first_action,
    exhaustive_first_action,
    future_mu,
    neutral_weight_before_day,
    run_policy_book,
    signal_usable,
    target_quantity,
    variance_before_day,
)

CALENDAR = [
    "2017-01-03",
    "2017-01-04",
    "2017-01-05",
    "2017-01-06",
    "2017-01-09",
    "2017-01-10",
    "2017-01-11",
]


def seeded_book():
    book = ShareBook(2000, 0.002, CALENDAR)
    book.q, book.cash = 10, 1000
    return book


def test_label_expired_at_L1_execution_and_close_truncation():
    clock = Clock("2017-01-03", 630, 960)
    assert clock.feature_interval == (615, 630)
    assert clock.original_label_interval == (630, 645)
    assert clock.execution_minute == 645
    assert clock.payoff_intervals(1) == [(645, 660)]
    assert Clock("2017-01-03", 930, 960).payoff_intervals(16) == [(945, 960)]
    assert Clock("2017-01-03", 945, 960).payoff_intervals(16) == []
    assert Clock("2017-01-03", 750, 780).payoff_intervals(16) == [(765, 780)]
    assert Clock("2017-01-03", 765, 780).payoff_intervals(16) == []


def test_label_mask_does_not_enter_signal_eligibility():
    # Future maturity=False or a future label NaN cannot change these arguments.
    assert signal_usable(0.001, True, 630, 960)
    assert not signal_usable(0.001, True, 615, 960)
    assert not signal_usable(0.001, True, 945, 960)
    assert not signal_usable(float("nan"), True, 630, 960)
    assert not signal_usable(0.001, False, 630, 960)


def test_log_forecast_scale_and_L1_discount_are_explicit():
    mu = future_mu(0.01, 0.5, 3)
    assert mu == pytest.approx([math.expm1(0.005), math.expm1(0.0025), math.expm1(0.00125)])


@pytest.mark.parametrize("held,anchor", [(0, 0), (1, 1), (0.37, 0), (0.62, 0.97)])
@pytest.mark.parametrize("mu", [(0.003,), (0.005, -0.006), (0.001, 0.005, -0.002)])
def test_DP_first_action_and_value_match_exhaustive_paths(held, anchor, mu):
    variance = tuple(0.000016 * (i + 1) for i in range(len(mu)))
    expected = exhaustive_first_action(held, anchor, mu, variance, 0.002)
    actual = dynamic_first_action(held, anchor, mu, variance, 0.002)
    assert actual[0] == expected[0]
    assert actual[1] == pytest.approx(expected[1], abs=1e-13)


def test_full_cycle_cost_and_zero_DP_invariants():
    assert dynamic_first_action(0, 0, (0.003,), (0,), 0.002)[0] == 0
    assert dynamic_first_action(0, 0, (0.005,), (0,), 0.002)[0] == 1
    assert dynamic_first_action(0.97, 0.97, (0,) * 16, (0.000016,) * 16, 0.002) == (0.97, 0)


def test_partial_buy_fee_NAV_and_no_binary_substitution():
    book = seeded_book()
    pending = book.freeze_weight(0.75, 100, "t0", "t1", "forecast")
    assert pending.target_quantity == 14 and pending.quantity == 4
    order = book.attempt("t1", "2017-01-03", 100)
    assert order["status"] == "reference_filled"
    assert book.q == 14 and book.cash == pytest.approx(599.2)
    assert book.fees == pytest.approx(0.8)
    assert book.nav(100) == pytest.approx(1999.2)
    with pytest.raises(RuntimeError, match="Binary"):
        book.freeze(1, 100, "t2", "t3", "forbidden")


def test_partial_sell_receivable_and_delayed_cash():
    book = seeded_book()
    pending = book.freeze_weight(0.25, 100, "t0", "t1", "forecast")
    assert pending.target_quantity == 4 and pending.quantity == 6
    book.attempt("t1", "2017-01-03", 100)
    assert book.q == 4 and book.cash == 1000
    assert book.unsettled[0] == {
        "amount": pytest.approx(598.8),
        "due": "2017-01-09",
        "sale_date": "2017-01-03",
    }
    assert book.nav(100) == pytest.approx(1998.8)
    book.begin_day("2017-01-06", [])
    assert book.cash == 1000
    book.begin_day("2017-01-09", [])
    assert book.cash == pytest.approx(1598.8) and book.unsettled == []


def test_known_unsettled_cash_does_not_fund_a_partial_buy():
    book = ShareBook(2000, 0.002, CALENDAR)
    book.cash = 100
    book.unsettled = [{"amount": 1900, "due": "2017-01-09", "sale_date": "2017-01-03"}]
    pending = book.freeze_weight(0.5, 100, "t0", "t1", "forecast")
    assert pending.quantity == 9 and not pending.decision_cash_sufficient
    result = book.attempt("t1", "2017-01-04", 100)
    assert result["status"] == "no_fill_known_settled_cash_shortfall_whole_buy_skip"
    assert book.q == 0 and book.cash == 100 and book.fees == 0


def test_future_fill_gap_never_resizes_the_frozen_lot():
    book = ShareBook(1000, 0.002, CALENDAR)
    pending = book.freeze_weight(1, 100, "t0", "t1", "forecast")
    assert pending.quantity == 9
    result = book.attempt("t1", "2017-01-03", 120)
    assert result["quantity"] == 9 and result["status"] == "no_fill_cash_gap_whole_buy_skip"
    assert book.q == 0 and book.cash == 1000 and book.pending is None
    assert book.attempt("t2", "2017-01-03", 100) is None


def test_sizing_uses_postfee_weight_and_respects_integer_bounds():
    for q, nav in [(0, 2000), (3, 2000), (10, 2000), (19, 2000)]:
        for weight in [0, 0.25, 0.5, 0.75, 1]:
            desired = target_quantity(q, nav, 100, weight, 0.002)
            if desired == q:
                continue
            after_nav = nav - 0.002 * 100 * abs(desired - q)
            assert desired * 100 / after_nav <= weight + 1e-12
            next_nav = nav - 0.002 * 100 * abs(desired + 1 - q)
            assert (desired + 1) * 100 / next_nav > weight - 1e-12


def test_missing_packets_never_buy_back_to_long_anchor():
    missing = MissingState()
    assert missing.observe(None, True) == "structural_hold" and missing.consecutive == 0
    assert [missing.observe(None) for _ in range(4)] == [
        "missing_hold",
        "missing_hold",
        "missing_hold",
        "missing_reduce_only",
    ]
    book = seeded_book()
    assert book.freeze_weight(0.97, 100, "t0", "t1", "missing", reduction_only=True) is None
    assert book.q == 10 and book.cash == 1000
    pending = book.freeze_weight(0, 100, "t0", "t1", "missing", reduction_only=True)
    assert pending.side == "sell" and pending.quantity == 10
    assert missing.observe(0.0) == "forecast" and missing.consecutive == 0


def test_passive_anchor_tracks_fees_prices_and_dividend_receivables():
    passive = PassiveAnchor(2000, 0.002, CALENDAR, 1)
    passive.initialize(100, "previous close", "t0", "2017-01-03", 100)
    assert passive.book.q == 19 and passive.book.cash == pytest.approx(96.2)
    initial = passive.weight(100)
    assert passive.weight(120) > initial
    action = {
        "type": "cash_dividends",
        "symbol": "SPY",
        "ex_date": "2017-01-04",
        "payable_date": "2017-01-06",
        "amount": 1,
        "id": "synthetic",
    }
    passive.book.begin_day("2017-01-04", [action])
    assert passive.book.nav(99) == pytest.approx(1996.2)
    assert passive.book.dividends[0]["amount"] == 19
    assert passive.weight(99) == pytest.approx(1881 / 1996.2)


def test_unknown_split_CIL_remains_unknown_and_changes_frozen_inventory():
    book = seeded_book()
    book.freeze_weight(0, 100, "previous close", "t1", "sell")
    action = {
        "type": "split",
        "symbol": "SPY",
        "ex_date": "2017-01-04",
        "ratio": 0.333,
        "id": "synthetic",
    }
    book.begin_day("2017-01-04", [action])
    assert book.cash_in_lieu_unknown and book.nav(100) is None
    result = book.attempt("t1", "2017-01-04", 100)
    assert result["status"] == "no_fill_corporate_action_changed_frozen_inventory"


def test_terminal_planning_cost_cannot_create_cash_or_force_final_liquidation():
    book = seeded_book()
    before = (book.cash, book.q, book.fees, book.nav(100))
    weight, value = dynamic_first_action(0.5, 0, (0.004,), (0,), 0.002)
    assert math.isfinite(value) and weight in [0, 0.25, 0.5, 0.75, 1]
    assert before == (book.cash, book.q, book.fees, book.nav(100))


def test_risk_and_exposure_histories_never_read_current_or_future_rows():
    history = {f"2017-{i // 28 + 1:02d}-{i % 28 + 1:02d}": [0.001] for i in range(63)}
    future = dict(history, **{"2020-01-01": [1.0]})
    assert variance_before_day(history, "2018-01-01") == pytest.approx(0.000001)
    assert variance_before_day(future, "2018-01-01") == pytest.approx(0.000001)
    exposure = {d: 0.4 for d in history}
    exposure["2020-01-01"] = 1
    assert neutral_weight_before_day(exposure, "2018-01-01", 1) == pytest.approx(0.4)


@pytest.mark.parametrize("anchor", [0, 1])
@pytest.mark.parametrize("policy", list(POLICIES.values()))
def test_complete_synthetic_ZERO_book_is_exact_cash_or_same_physical_buyhold(anchor, policy):
    dates = CALENDAR[:4]
    days = [{"date": d, "regular15_windows": 26} for d in dates]
    bars = {
        d: {
            k: {
                "open": 100 + j,
                "close": 100 + j,
                "first_price_age_minutes": 0,
                "last_price_age_to_window_end_minutes": 0,
            }
            for k in range(26)
        }
        for j, d in enumerate(dates)
    }
    marks = {d: 100 + j for j, d in enumerate(dates)}
    scores = {(d, 570 + 15 * k): 0.0 for d in dates for k in range(4, 26)}
    action = {
        "type": "cash_dividends",
        "symbol": "SPY",
        "ex_date": dates[2],
        "payable_date": dates[3],
        "amount": 0.5,
        "id": "synthetic",
    }
    result = run_policy_book(
        days, bars, marks, scores, [action], CALENDAR, policy, anchor, 0.002, capital=2000
    )
    reference = PassiveAnchor(2000, 0.002, CALENDAR, anchor)
    nav = [2000]
    for j, d in enumerate(dates[1:], 1):
        reference.book.begin_day(d, [action])
        if j == 1:
            reference.initialize(100, dates[0] + " close", d + " 09:30", d, 101)
        nav.append(reference.book.nav(marks[d]))
    assert [r["nav"] for r in result["daily"]] == nav
    assert result["orders"] == reference.book.orders
    assert result["terminal_forced_liquidation"] is False
    if anchor == 1:
        original = run_funded(
            days, bars, marks, {}, [action], CALENDAR, 0.002, capital=2000, mode="buy_hold"
        )
        for actual, expected in zip(result["daily"], original["daily"], strict=True):
            for field in ["nav", "cash", "q", "fees", "dividend_receivable", "unsettled"]:
                assert actual[field] == expected[field]


def test_native_snapshot_resume_preserves_entire_synthetic_event_path():
    days = [{"date": d, "regular15_windows": 26} for d in CALENDAR[:4]]
    bars = {
        r["date"]: {
            k: {
                "open": 100,
                "close": 100,
                "first_price_age_minutes": 0,
                "last_price_age_to_window_end_minutes": 0,
            }
            for k in range(26)
        }
        for r in days
    }
    marks = {r["date"]: 100 for r in days}
    scores = {(r["date"], 570 + 15 * k): 0.001 for r in days for k in range(4, 26)}
    captured = {}

    def capture(state):
        if state["next_day_index"] == 2:
            captured["state"] = pickle.dumps(state)

    original = run_policy_book(
        days,
        bars,
        marks,
        scores,
        [],
        CALENDAR,
        POLICIES["DP_H16_SLOW"],
        1,
        0.002,
        capital=2000,
        on_complete_day=capture,
    )
    resumed = run_policy_book(
        days,
        bars,
        marks,
        scores,
        [],
        CALENDAR,
        POLICIES["DP_H16_SLOW"],
        1,
        0.002,
        capital=2000,
        resume_state=pickle.loads(captured["state"]),
    )
    assert resumed == original
