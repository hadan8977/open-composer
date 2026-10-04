# ruff: noqa: E501
"""Backtest core: SPY identity, hand-computed paths, financing (design section 1), label parity,
schedule parity with screen_lane, and the Stage-0 regression."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from open_composer.research.equity_book.backtest import (
    TBILL,
    BookConfig,
    run_book,
    signal_positions,
)
from open_composer.research.equity_book.panel import PricePanel
from open_composer.research.equity_book.returns import build_legs, forward_open_to_open

ROOT = Path(__file__).resolve().parents[1]
NAN = np.nan


def _panel(
    data: dict[str, tuple[list[float], list[float]]], start: str = "2024-01-02"
) -> PricePanel:
    """``data[symbol] = (open, close)`` lists on consecutive business days."""
    n = len(next(iter(data.values()))[0])
    idx = pd.bdate_range(start, periods=n)
    o = pd.DataFrame({s: v[0] for s, v in data.items()}, index=idx)
    c = pd.DataFrame({s: v[1] for s, v in data.items()}, index=idx)
    return PricePanel.from_frames(o, c)


def _rng_prices(n: int, seed: int, start: float = 100.0) -> tuple[list[float], list[float]]:
    rng = np.random.default_rng(seed)
    close = start * np.exp(np.cumsum(rng.normal(0.0003, 0.01, n)))
    open_ = close * np.exp(rng.normal(0, 0.004, n))
    return list(open_), list(close)


def _const(d: dict[str, float]):
    return lambda t, state: dict(d)


# ---------------------------------------------------------------- 1. SPY identity


def test_spy_only_book_reproduces_close_to_close_returns() -> None:
    p = _panel({"SPY": _rng_prices(60, 1, 400.0)})
    spy_c = pd.Series(p.close[:, 0], index=p.dates)
    ret = spy_c.pct_change()
    # already holding SPY at the first close, rebalanced weekly back to 100% (no trade is needed)
    res = run_book(
        p,
        _const({"SPY": 1.0}),
        BookConfig(freq="W", initial_weights={"SPY": 1.0}, cost_bp_per_side=10.0),
    )
    # first session has no previous close, so compare from the second one
    got = res.net.iloc[1:]
    assert float((got - ret.iloc[1:]).abs().max()) < 1e-12
    assert res.daily["turnover"].iloc[1:].max() < 1e-12  # holding SPY -> SPY trades nothing
    assert res.daily["is_trade_day"].sum() >= 5  # the weekly trade days really happened


def test_spy_entry_at_open_earns_open_to_close_on_the_trade_day() -> None:
    p = _panel({"SPY": _rng_prices(30, 2, 400.0)})
    sig = [p.dates[3]]
    res = run_book(p, _const({"SPY": 1.0}), BookConfig(signal_dates=sig, cost_bp_per_side=0.0))
    trade_day = p.dates[4]
    o, c = p.open[:, 0], p.close[:, 0]
    assert res.daily.loc[trade_day, "is_trade_day"]
    assert abs(res.net.loc[trade_day] - (c[4] / o[4] - 1.0)) < 1e-14
    # and from then on plain close-to-close
    spy_ret = pd.Series(c, index=p.dates).pct_change()
    assert float((res.net.iloc[5:] - spy_ret.iloc[5:]).abs().max()) < 1e-12
    # nothing before the trade
    assert float(res.net.iloc[:4].abs().max()) == 0.0


# ---------------------------------------------------------------- 2. hand-computed long-short


def test_two_stock_long_short_path_matches_hand_computation() -> None:
    a_o = [100, 101, 102, 101, 104, 105]
    a_c = [100, 102, 101, 103, 104, 106]
    b_o = [50, 49.5, 49, 50.5, 52, 51]
    b_c = [50, 49, 50, 52, 51, 50]
    p = _panel({"A": (a_o, a_c), "B": (b_o, b_c)})
    bp = 10.0
    res = run_book(
        p, _const({"A": 0.5, "B": -0.5}), BookConfig(signal_dates=[p.dates[1]], cost_bp_per_side=bp)
    )
    # days 0,1: all cash.  Day 2: trade at the open, costs 10 bp on 1.0 of notional
    e = 1.0
    cost = 1.0 * bp / 1e4
    e -= cost
    ha, hb = 0.5 * 1.0, -0.5 * 1.0  # dollars at the trade (weights x pre-cost equity E=1)
    # intraday leg of day 2
    ha_new = ha * a_c[2] / a_o[2]
    hb_new = hb * b_c[2] / b_o[2]
    e += (ha_new - ha) + (hb_new - hb)
    expect = {2: e}
    ha, hb = ha_new, hb_new
    for d in (3, 4, 5):  # close-to-close from here
        ra, rb = a_c[d] / a_c[d - 1] - 1, b_c[d] / b_c[d - 1] - 1
        e += ha * ra + hb * rb
        ha, hb = ha * (1 + ra), hb * (1 + rb)
        expect[d] = e
    eq = res.daily["equity"]
    for d, v in expect.items():
        assert abs(eq.iloc[d] - v) < 1e-14, d
    # trade-day split of the return and the cost breakdown
    r2 = res.daily.iloc[2]
    assert r2["turnover"] == pytest.approx(1.0)
    assert r2["cost_spread"] == pytest.approx(cost)
    assert r2["gross"] - r2["net"] == pytest.approx(cost)
    assert res.daily.iloc[3]["is_trade_day"] is np.False_ or not res.daily.iloc[3]["is_trade_day"]
    # exposures: long 0.5, short 0.5, no sleeve; cash = E - L + S
    d2 = res.daily.iloc[2]
    assert d2["cash_exp"] == pytest.approx(1 - d2["long_exp"] + d2["short_exp"])
    # snapshot weights are fractions of the post-cost equity
    assert res.holdings[p.dates[2]]["A"] == pytest.approx(0.5 / (1 - cost), abs=1e-12)


def test_trade_day_old_holdings_earn_overnight_before_the_trade() -> None:
    # hold A at the first close; on the trade day sell all of it at the open
    a_o = [100, 110, 111, 112]
    a_c = [100, 105, 108, 109]
    p = _panel({"A": (a_o, a_c)})
    res = run_book(
        p,
        _const({}),
        BookConfig(signal_dates=[p.dates[1]], initial_weights={"A": 1.0}, cost_bp_per_side=0.0),
    )
    # day 1: close-to-close 100->105 (open 110 is only the split of the day)
    assert res.net.iloc[1] == pytest.approx(105 / 100 - 1)
    # day 2 is the trade day: old holding earns close 105 -> open 111, then flat
    assert res.net.iloc[2] == pytest.approx(111 / 105 - 1)
    assert res.net.iloc[3] == 0.0
    assert res.daily["equity_open_pre"].iloc[2] == pytest.approx(111 / 100)


# ---------------------------------------------------------------- 3. cash / sleeve / margin (section 1)


def _fin_panel(n: int = 12) -> PricePanel:
    sgov_c = list(100 * 1.0001 ** np.arange(n))
    return _panel(
        {
            "A": _rng_prices(n, 3, 100.0),
            "B": _rng_prices(n, 4, 60.0),
            "SGOV": (sgov_c, sgov_c),
        },
        start="2024-01-04",  # Thursday: the Friday close -> Monday gap spans 3 calendar days
    )


def test_zero_funding_structure_cash_is_zero_and_sleeve_earns_its_return() -> None:
    p = _fin_panel()
    res = run_book(
        p,
        _const({"A": 0.5, "B": -0.5, TBILL: 1.0}),
        BookConfig(signal_dates=[p.dates[0]], cost_bp_per_side=0.0),
    )
    d = res.daily
    # right after the trade L = S = 0.5, Q = 1.0 -> C = E - L - Q + S = 0
    w = res.holdings[p.dates[1]]
    assert w["A"] == pytest.approx(0.5) and w["B"] == pytest.approx(-0.5)
    assert w["SGOV"] == pytest.approx(1.0)
    c0 = 1.0 - 0.5 - 1.0 + 0.5
    assert c0 == 0.0
    # identity holds every session
    for _, r in d.iterrows():
        assert r["cash_exp"] == pytest.approx(
            1 - r["long_exp"] - r["tbill_exp"] + r["short_exp"], abs=1e-12
        )
    # no margin, no borrow was charged and the book return is the sum of the three legs' returns
    assert d["cost_margin"].abs().sum() == 0.0
    a, b, s = (p.close[:, p.col(x)] for x in ("A", "B", "SGOV"))
    ao, bo, so = (p.open[:, p.col(x)] for x in ("A", "B", "SGOV"))
    e = 1.0
    ha, hb, hs = 0.5, -0.5, 1.0
    for i in range(1, len(a)):
        if i == 1:
            ha, hb, hs = ha * a[1] / ao[1], hb * b[1] / bo[1], hs * s[1] / so[1]
            e = e + (ha - 0.5) + (hb + 0.5) + (hs - 1.0)
        else:
            ra, rb, rs = a[i] / a[i - 1] - 1, b[i] / b[i - 1] - 1, s[i] / s[i - 1] - 1
            e += ha * ra + hb * rb + hs * rs
            ha, hb, hs = ha * (1 + ra), hb * (1 + rb), hs * (1 + rs)
        assert d["equity"].iloc[i] == pytest.approx(e, abs=1e-13)


def test_100_100_book_cash_is_a_non_earning_credit() -> None:
    p = _fin_panel()
    res = run_book(
        p,
        _const({"A": 1.0, "B": -1.0}),
        BookConfig(signal_dates=[p.dates[0]], cost_bp_per_side=0.0, margin_rate=0.065),
    )
    d = res.daily
    # C = E - L - Q + S = E - 1 + 1 > 0 (credit): earns nothing, charges nothing
    assert d["cash_exp"].iloc[1] == pytest.approx(
        1.0 - d["long_exp"].iloc[1] + d["short_exp"].iloc[1]
    )
    assert d["cash_exp"].iloc[1] > 0.9
    assert d["cost_margin"].abs().sum() == 0.0
    a, b = p.close[:, p.col("A")], p.close[:, p.col("B")]
    ao, bo = p.open[:, p.col("A")], p.open[:, p.col("B")]
    # first trade day: exactly rA_intra - rB_intra (no rf credit on the short proceeds)
    assert d["net"].iloc[1] == pytest.approx((a[1] / ao[1] - 1) - (b[1] / bo[1] - 1), abs=1e-14)


def test_negative_cash_pays_margin_interest_on_the_closing_balance() -> None:
    p = _fin_panel()
    rate = 0.065
    res = run_book(
        p,
        _const({"A": 1.5}),
        BookConfig(signal_dates=[p.dates[0]], cost_bp_per_side=0.0, margin_rate=rate),
    )
    d = res.daily
    assert d["cash_exp"].iloc[1] < -0.45  # C = E - L = -0.5 E
    for i in range(2, len(d)):
        days = (d.index[i] - d.index[i - 1]).days
        c_prev_dollars = d["cash_exp"].iloc[i - 1] * d["equity"].iloc[i - 1]
        expect = max(-c_prev_dollars, 0.0) * rate / 360.0 * days / d["equity"].iloc[i - 1]
        assert d["cost_margin"].iloc[i] == pytest.approx(expect, abs=1e-15)
    assert (d.index[3] - d.index[2]).days == 4 or any(
        (d.index[i] - d.index[i - 1]).days == 3 for i in range(1, len(d))
    )  # a weekend is in the sample
    assert d["cost_margin"].iloc[2:].min() > 0
    # gross adds the interest back
    assert (d["gross"] - d["net"]).iloc[2:].min() > 0


def test_borrow_charged_on_short_notional() -> None:
    p = _fin_panel()
    res = run_book(
        p,
        _const({"B": -0.5}),
        BookConfig(signal_dates=[p.dates[0]], cost_bp_per_side=0.0, borrow_bp_per_year=100.0),
    )
    d = res.daily
    i = 3
    days = (d.index[i] - d.index[i - 1]).days
    s_prev = d["short_exp"].iloc[i - 1] * d["equity"].iloc[i - 1]
    assert d["cost_borrow"].iloc[i] == pytest.approx(
        s_prev * 0.01 / 360.0 * days / d["equity"].iloc[i - 1], abs=1e-15
    )


def test_tbill_sleeve_uses_bil_before_sgov_exists() -> None:
    n = 10
    idx = pd.bdate_range("2024-01-02", periods=n)
    bil = pd.Series(90 * 1.0001 ** np.arange(n), index=idx)
    sgov = pd.Series(100 * 1.0001 ** np.arange(n), index=idx)
    sgov.iloc[:5] = np.nan
    o = pd.DataFrame({"BIL": bil, "SGOV": sgov})
    p = PricePanel.from_frames(o, o)
    res = run_book(p, _const({TBILL: 1.0}), BookConfig(freq="D", cost_bp_per_side=0.0))
    assert "BIL" in res.holdings[idx[1]].index
    assert "SGOV" in res.holdings[idx[8]].index and "BIL" not in res.holdings[idx[8]].index


# ---------------------------------------------------------------- delisting


def test_delisted_long_exits_at_last_close_with_optional_haircut() -> None:
    a_o = [100, 100, 110, NAN, NAN, NAN]
    a_c = [100, 100, 120, NAN, NAN, NAN]
    b_o = [50, 50, 50, 51, 52, 53]
    b_c = [50, 50, 50, 51, 52, 53]
    p = _panel({"A": (a_o, a_c), "B": (b_o, b_c)})
    cfg = dict(signal_dates=[p.dates[0]], cost_bp_per_side=0.0)
    base = run_book(p, _const({"A": 1.0}), BookConfig(**cfg))
    hair = run_book(p, _const({"A": 1.0}), BookConfig(**cfg, delist_long_haircut=-0.30))
    # position earns 100 -> 120 then sits in non-earning cash
    assert base.daily["equity"].iloc[-1] == pytest.approx(1.2)
    assert base.info["delist_exits"] == 1
    assert hair.daily["equity"].iloc[-1] == pytest.approx(1.2 - 0.30 * 1.2)
    # a short in the delisted name gets no haircut
    short = run_book(p, _const({"A": -1.0}), BookConfig(**cfg, delist_long_haircut=-0.30))
    assert short.daily["equity"].iloc[-1] == pytest.approx(1.0 - 0.2)


def test_trade_in_a_halted_name_is_frozen() -> None:
    a_o = [100, 100, NAN, 100, 100]
    a_c = [100, 100, NAN, 101, 102]
    p = _panel({"A": (a_o, a_c), "B": (10, 10) and ([10] * 5, [10] * 5)})
    res = run_book(
        p, _const({"A": 1.0}), BookConfig(signal_dates=[p.dates[1]], cost_bp_per_side=0.0)
    )
    assert res.info["frozen_halted_trades"] == 1  # cannot buy on the halted session
    assert res.daily["n_long"].iloc[2] == 0


# ---------------------------------------------------------------- exec price sensitivity


def test_exec_close_trades_at_the_next_close() -> None:
    p = _panel({"A": _rng_prices(10, 7, 100.0)})
    res = run_book(
        p,
        _const({"A": 1.0}),
        BookConfig(signal_dates=[p.dates[2]], exec_price="close", cost_bp_per_side=0.0),
    )
    c = p.close[:, 0]
    assert res.net.iloc[3] == 0.0  # bought at the close: no return that day
    assert res.net.iloc[4] == pytest.approx(c[4] / c[3] - 1)


def test_run_window_start_uses_prior_close_for_the_first_overnight_leg() -> None:
    p = _panel({"A": _rng_prices(20, 5, 100.0)})
    full = run_book(
        p,
        _const({"A": 1.0}),
        BookConfig(initial_weights={"A": 1.0}, signal_dates=[], cost_bp_per_side=0),
    )
    sub = run_book(
        p,
        _const({"A": 1.0}),
        BookConfig(
            initial_weights={"A": 1.0},
            signal_dates=[],
            cost_bp_per_side=0,
            start=str(p.dates[7].date()),
        ),
    )
    # starting mid-calendar the first session is a full close-to-close day, like in the full run
    assert sub.net.iloc[0] == pytest.approx(full.net.loc[p.dates[7]], abs=1e-14)


# ---------------------------------------------------------------- schedule parity with screen_lane


def test_signal_positions_match_screen_lane() -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import screen_lane as lane  # noqa: PLC0415

    idx = pd.bdate_range("2023-11-01", "2024-06-28")
    for freq, offs in (("M", (0, 3, 20)), ("W", (0, 2, 4))):
        for off in offs:
            got = [idx[i] for i in signal_positions(idx, freq, off)]
            assert got == lane.signal_dates(idx, freq, off)


# ---------------------------------------------------------------- 4. label / return parity


def test_label_equals_book_return_of_one_name_buy_and_hold() -> None:
    n = 80
    o, c = _rng_prices(n, 11, 40.0)
    o, c = np.array(o), np.array(c)
    o[45] = NAN  # stale-open session inside the span
    c[30:32] = NAN
    o[30:32] = NAN  # a hole inside the span
    o[46] = NAN  # missing open on the exit session (label falls back to the last close)
    p = _panel({"X": (list(o), list(c))})
    for t in (5, 12):
        entry_pos, exit_pos = t + 1, t + 1 + 21
        res = run_book(
            p,
            _const({"X": 1.0}),
            BookConfig(signal_dates=[p.dates[t], p.dates[exit_pos - 1]], cost_bp_per_side=0.0),
        )
        label = forward_open_to_open(p.open, p.close, entry_pos, exit_pos)[0]
        held = res.period_return(p.dates[entry_pos], p.dates[exit_pos])
        assert held == pytest.approx(label, abs=1e-12)
        # the same number from the compounded daily returns: entry-day close ... exit-day close - 1
        legs = build_legs(p.open, p.close)
        assert legs.priced[entry_pos, 0]
        daily = (1 + res.net.iloc[entry_pos:exit_pos]).prod() * (1 + legs.ov[exit_pos, 0])
        assert daily - 1 == pytest.approx(label, abs=1e-12)


# ---------------------------------------------------------------- 5. Stage-0 regression

S0_DIR = ROOT / "reports/research/program/stage0-hedged-books-2026-10-01"
HAVE_S0 = (S0_DIR / "cache/price_panel.parquet").exists() and (
    ROOT / "data/features/daily_broad"
).exists()


@pytest.mark.skipif(not HAVE_S0, reason="Stage-0 cache / daily_broad not available")
@pytest.mark.xfail(
    strict=False,
    reason="T-20261002-02 (10-04) swapped in daily_broad rebuilt from the repaired SIP archive "
    "(vendor re-based adjusted prices of restated symbols); the Stage-0 cache predates it "
    "(max abs diff 3.97e-3 over 106 months, T-22 report). Not a run_book regression.",
)
def test_stage0_ls_raw_mom_12_1_p1000_parity() -> None:
    """Rebuild Stage-0's LS_RAW MOM_12_1 P1000 book with run_book: monthly rebalance at the month-end
    close, equal weights per leg, $1 long / $1 short, no hedge, no costs.  Compounded daily returns
    between consecutive entry opens must equal Stage 0's monthly gross returns."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import diag_s0_hedged_books as s0  # noqa: PLC0415
    import duckdb  # noqa: PLC0415

    from open_composer.research.features import price_hygiene as ph  # noqa: PLC0415

    cache = S0_DIR / "cache"
    periods = pd.read_parquet(cache / "periods.parquet")
    panel = pd.read_parquet(cache / "price_panel.parquet")
    spy = pd.read_parquet(cache / "spy_daily.parquet")
    cal = pd.DatetimeIndex(spy.index)
    fdates = pd.DatetimeIndex(periods["formation_date"])
    con = duckdb.connect()
    con.execute("SET memory_limit='900MB'")
    mes = pd.DatetimeIndex(
        sorted(
            con.execute(f"select distinct month_end from read_parquet('{s0.UNIV_GLOB}')").df()[
                "month_end"
            ]
        )
    )
    fmap = pd.DataFrame(
        {"formation_date": fdates, "month_end": [mes[mes <= d].max() for d in fdates]}
    )
    con.register("fmap", fmap)
    uni = con.execute(
        f"select f.formation_date, u.symbol, u.adv_rank from read_parquet('{s0.UNIV_GLOB}') u "
        "join fmap f on u.month_end = f.month_end where u.adv_rank <= 3000 and u.close >= 5"
    ).df()
    uni["symbol"] = uni["symbol"].astype(str)
    df = uni.merge(panel, on=["formation_date", "symbol"], how="left")
    targets: dict[pd.Timestamp, dict[str, float]] = {}
    for fd, sub in df.groupby("formation_date"):
        sub = s0._eligible(sub, 1, 1000)
        score = sub["MOM_12_1"].to_numpy(dtype="float64")
        m = np.isfinite(score)
        if m.sum() < s0.MIN_NAMES:
            continue
        sub, score = sub[m], score[m]
        lg, sh = s0.select_legs(score, None, size_neutral=False)
        syms = sub["symbol"].to_numpy()
        w = {str(s): 1.0 / len(lg) for s in syms[lg]}
        w.update({str(s): -1.0 / len(sh) for s in syms[sh]})
        targets[pd.Timestamp(fd)] = w
    names = sorted({s for w in targets.values() for s in w})
    con.register("names", pd.DataFrame({"symbol": names}))
    raw = con.execute(
        f"select d.symbol, d.trade_date, d.open, d.close from read_parquet('{s0.DAILY_GLOB}') d "
        "semi join names n on d.symbol = n.symbol"
    ).df()
    raw = raw.drop_duplicates(["trade_date", "symbol"], keep="last")
    close_w = raw.pivot(index="trade_date", columns="symbol", values="close").reindex(cal)
    open_w = raw.pivot(index="trade_date", columns="symbol", values="open").reindex(cal)
    del raw
    close_s, open_s, _rep = ph.sanitize_price_matrices(
        close_w.astype("float64"), open_w.astype("float64")
    )
    prices = PricePanel.from_frames(open_s, close_s)
    del close_w, open_w
    res = run_book(
        prices,
        lambda t, state: targets.get(t),
        BookConfig(signal_dates=list(targets), cost_bp_per_side=0.0, start=str(fdates[0].date())),
    )
    s0m = pd.read_parquet(S0_DIR / "monthly_returns.parquet")
    s0m = s0m[
        (s0m["universe"] == "P1000") & (s0m["signal"] == "MOM_12_1") & (s0m["book"] == "LS_RAW")
    ]
    s0m = s0m.set_index("formation_date")["gross"]
    diffs = []
    for r in periods.itertuples():
        if r.partial or r.formation_date not in s0m.index or pd.isna(s0m[r.formation_date]):
            continue
        got = res.period_return(r.entry_date, r.exit_date)
        diffs.append(abs(got - s0m[r.formation_date]))
    assert len(diffs) >= 100
    print(
        f"stage0 parity: {len(diffs)} months, max abs diff {max(diffs):.3e}, mean {np.mean(diffs):.3e}"
    )
    assert max(diffs) < 1e-6, f"max abs diff {max(diffs):.3e} over {len(diffs)} months"
