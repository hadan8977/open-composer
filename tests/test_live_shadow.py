"""T-20261008-01: fake-data tests for the live-account shadow simulation (no network)."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import live_shadow as ls  # noqa: E402

SYMS = ["AAA", "BBB", "SGOV"]


def _days(n: int) -> list[str]:
    out, d = [], date(2026, 9, 1)
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d = date.fromordinal(d.toordinal() + 1)
    return out


def _prices(n: int, aaa=None, bbb=None, gap: float = 0.0):
    close = np.full((n, 3), 100.0)
    close[:, 2] = 100.0
    if aaa is not None:
        close[:, 0] = aaa
    if bbb is not None:
        close[:, 1] = bbb
    opn = close.copy()
    opn[1:, :2] = close[:-1, :2] * (1.0 + gap)
    return opn, close


def _run(weights_by_j, n=12, delay=0, aaa=None, bbb=None, gap=0.0, start_cash=1000.0, **kw):
    dates = _days(n)
    opn, close = _prices(n, aaa, bbb, gap)
    p = ls.Params(start_cash=start_cash, delay=delay, fees=False, spread_mult=0.0, **kw)

    def fn(j):
        w = weights_by_j(j)
        return w, {k: v for k, v in w.items() if k != "SGOV"}

    res = ls.simulate_account(dates, SYMS, opn, close, fn, p, 1, n - 2, "SGOV")
    return dates, res


def test_whole_shares_and_no_borrowing_on_gap_up():
    # all-in AAA at 33.3; opens 10% above the sizing close -> fewer shares than sized, cash >= 0
    aaa = np.full(12, 33.3)
    dates, res = _run(lambda j: {"AAA": 1.0}, aaa=aaa, gap=0.10)
    first = res["rows"][0]
    sh = first["positions"]["AAA"]
    assert sh == int(sh)
    assert sh <= int(1000 / (33.3 * 1.10))
    assert first["cash"] >= 0.0
    assert all(r["cash"] >= -1e-9 for r in res["rows"])


def test_sells_fill_before_buys_and_fund_them():
    # hold AAA until session 4, then switch all to BBB: the buy is paid only by the sale
    dates, res = _run(lambda j: {"AAA": 1.0} if j < 4 else {"BBB": 1.0})
    day = next(r for r in res["rows"] if any(f["symbol"] == "BBB" for f in r["orders"]))
    sides = [f["side"] for f in day["orders"]]
    assert sides.index("sell") < sides.index("buy")
    bbb = next(f for f in day["orders"] if f["symbol"] == "BBB")
    assert bbb["shares"] > 0 and "note" not in bbb
    assert "AAA" not in day["positions"]
    assert day["cash"] >= 0.0


def test_orders_below_minimum_are_skipped():
    bbb = np.full(12, 10.0)
    _, small = _run(lambda j: {"BBB": 0.04, "SGOV": 0.96}, bbb=bbb)  # $40 of BBB
    assert all(f["symbol"] != "BBB" for r in small["rows"] for f in r["orders"])
    _, big = _run(lambda j: {"BBB": 0.06, "SGOV": 0.94}, bbb=bbb)  # $60 of BBB
    assert any(f["symbol"] == "BBB" and f["shares"] > 0 for r in big["rows"] for f in r["orders"])


def test_halve_at_25_7_and_stop_at_30():
    aaa = np.array([100, 100, 100, 73, 73, 73, 30, 30, 30, 30, 30, 30.0])
    _, res = _run(lambda j: {"AAA": 1.0}, aaa=aaa)
    rows = {r["date"]: r for r in res["rows"]}
    ds = _days(12)
    assert rows[ds[3]]["dd_state"] == "half"  # -27% at the close
    assert rows[ds[3]]["drawdown"] >= 0.257
    held_before = rows[ds[3]]["positions"]["AAA"]
    held_after = rows[ds[4]]["positions"]["AAA"]  # halved at the next open
    assert abs(held_after - held_before / 2) <= 1.0
    assert rows[ds[6]]["dd_state"] == "stop"  # account -48%
    assert "AAA" not in rows[ds[7]]["positions"]
    assert rows[ds[7]]["positions"].get("SGOV", 0) > 0
    assert rows[ds[9]]["stop_state"] == "stop"  # sticky


def test_one_day_delay_fills_a_session_later():
    dates, now = _run(lambda j: {"AAA": 1.0}, delay=0)
    _, late = _run(lambda j: {"AAA": 1.0}, delay=1)

    def first(res):
        return next(r["date"] for r in res["rows"] if any(f["shares"] > 0 for f in r["orders"]))

    assert dates.index(first(late)) == dates.index(first(now)) + 1


def test_z_flags_start_at_session_21():
    n = 40
    dates = _days(n)
    opn, close = _prices(n, aaa=np.linspace(100, 60, n))
    p = ls.Params(
        start_cash=1000.0,
        fees=False,
        spread_mult=0.0,
        halve_dd=None,
        stop_dd=None,
        sleeve_exit_dd=None,
        z_mu=0.0005,
        z_sigma=0.01,
    )
    res = ls.simulate_account(
        dates, SYMS, opn, close, lambda j: ({"AAA": 1.0}, {"AAA": 1.0}), p, 1, n - 2, "SGOV"
    )
    flags = [r["z_flag"] for r in res["rows"]]
    assert all(f is None for f in flags[:20])
    assert any(f in ("review", "stop") for f in flags[20:])


def test_calendar_and_window():
    assert ls.next_session(date(2026, 11, 25)) == date(2026, 11, 27)  # Thanksgiving closed
    assert ls.next_session(date(2026, 10, 9)) == date(2026, 10, 12)
    w_edt = ls.order_window(date(2026, 10, 8), date(2026, 10, 9))
    assert w_edt["open_bj"].endswith("21:30") and w_edt["dst"] == "夏令时"
    w_est = ls.order_window(date(2026, 10, 30), date(2026, 11, 2))
    assert w_est["open_bj"].endswith("22:30") and w_est["dst"] == "冬令时"


def _engine(n_real=12):
    dates = _days(n_real + 1)
    opn, close = _prices(n_real + 1, aaa=np.linspace(100, 110, n_real + 1))
    opn[-1], close[-1] = np.nan, np.nan
    w = np.zeros((n_real + 1, 3))
    w[:, 0], w[:, 2] = 0.5, 0.5
    w[6:, 0], w[6:, 2] = 0.0, 1.0
    return ls.Engine(
        dates, SYMS, opn, close, "SGOV", {"S3C": w}, {"S3C": np.zeros(n_real + 1)}, dates[-2]
    )


def test_rerun_leaves_ledger_unchanged(tmp_path):
    eng = _engine()
    acc = ls.AccountDef("P", "t", [("S3C", 0.5)], s3_sleeve="S3C")
    i1 = eng.n_real - 1
    p = ls.Params(start_cash=20000.0)

    def run():
        return {
            "P": ls.simulate_account(
                eng.dates, eng.syms, eng.opn, eng.cls, ls.make_target_fn(eng, acc), p, 1, i1, "SGOV"
            )
        }

    a = ls.commit_outputs(run(), eng, tmp_path, eng.dates[1], i1)
    text1 = (tmp_path / "ledger.jsonl").read_text()
    b = ls.commit_outputs(run(), eng, tmp_path, eng.dates[1], i1)
    assert a["appended"] == i1 and b["appended"] == 0 and not b["mismatches"]
    assert (tmp_path / "ledger.jsonl").read_text() == text1
    st = json.loads((tmp_path / "state.json").read_text())
    assert st["last_session"] == eng.dates[i1] and st["next_session"] == eng.dates[-1]
    sheet = (tmp_path / "orders" / f"{eng.dates[-1]}.md").read_text()
    assert "不用下单" in sheet or "下单前核对" in sheet


def _sleeve_exit_run(name: str):
    acc = next(a for a in ls.ACCOUNTS if a.name == name)
    n = 14
    dates = _days(n)
    opn, close = _prices(n, aaa=np.full(n, 100.0))
    sret = np.zeros(n)
    sret[5] = -0.30  # the S3 part loses 30% in one session
    p = ls.params_for(acc, None, fees=False, spread_mult=0.0)
    res = ls.simulate_account(
        dates,
        SYMS,
        opn,
        close,
        lambda j: ({"AAA": 0.5, "SGOV": 0.5}, {"AAA": 0.5}),
        p,
        1,
        n - 2,
        "SGOV",
        sret,
    )
    return acc, p, res


def test_pilot_account_ignores_sleeve_exit_but_shows_the_drawdown():
    acc, p, res = _sleeve_exit_run("P")
    assert p.sleeve_exit_dd is None and not acc.sleeve_exit
    assert not any(r["sleeve_exit"] for r in res["rows"])
    assert res["rows"][-1]["s3_drawdown"] > 0.29  # information only
    assert "AAA" in res["rows"][-1]["positions"]  # still held, no trade triggered
    assert res["decisions"][-1]["s3_drawdown"] > 0.29


def test_sleeve_exit_sensitivity_account_exits_and_stays_out():
    acc, p, res = _sleeve_exit_run("P-sleeve-exit")
    assert p.sleeve_exit_dd == ls.SLEEVE_EXIT_DD and acc.sleeve_exit
    rows = res["rows"]
    first = next(i for i, r in enumerate(rows) if r["sleeve_exit"])
    assert rows[first]["stop_state"] == "sleeve_exit"
    assert "AAA" not in rows[-1]["positions"] and rows[-1]["sleeve_exit"]
