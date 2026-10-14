# ruff: noqa: E501
"""Local live-account shadow simulation (T-20261008-01). No broker, no orders.

A $20,000, whole-share, no-borrowing account that follows the owner's planned Schwab pilot:
sleeve targets are computed after the close, the owner places "market, day" orders before
the next open, and the simulation fills them at that official open plus a half spread.
Several comparison accounts run on the same data and rules. See reports/live-shadow/spec.md.

    scripts/run_capped.sh --mem 900M -- uv run python scripts/live_shadow.py backfill --start 2026-09-01
    scripts/run_capped.sh --mem 900M -- uv run python scripts/live_shadow.py daily
    scripts/run_capped.sh --mem 900M -- uv run python scripts/live_shadow.py replay --start 2024-01-08 --end latest --tag recent
    uv run python scripts/live_shadow.py replay-report
    uv run python scripts/live_shadow.py report

Targets come from the T-20261005-32 engine (scripts/p2_theme_budget.py) and the S3-TC10 cap
(scripts/s3_tc10.py); the same daily archive as the S3 paper job. Nothing here is imported by
a live paper job.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

OUT = ROOT / "reports/live-shadow"
START_DEFAULT = "2026-09-01"
START_CASH = 20000.0
MIN_ORDER_USD = 50.0
HALVE_DD, STOP_DD, SLEEVE_EXIT_DD = 0.257, 0.30, 0.25
Z_FROM_SESSION, Z_REVIEW, Z_STOP = 21, -2.8, -3.7
SEC_RATE = 20.60e-6  # per dollar of sales, effective 2026-04-04 (facts.md)
TAF_RATE, TAF_CAP = 0.000195, 9.79  # per share sold, per trade cap (2026)
COMMISSION = 0.0  # Schwab online US-listed ETF
Z_PARAM_FILE = OUT / "z-params.json"
T58_RESULTS = ROOT / "reports/research/iterations/t20261005_p4_alloc_v2/results.json"
Z_PANEL = ROOT / "reports/research/iterations/t20261005_p4_alloc_v2/cache/panel.parquet"
PAPER_FILLS = ROOT / "reports/paper/rehearsal/us_etf_levered_rotation_63_top2_monthly-fills.jsonl"

# NYSE full-day closures. 2028 and later: add before use (待核对).
NYSE_HOLIDAYS = {
    date.fromisoformat(d)
    for d in (
        "2026-01-01 2026-01-19 2026-02-16 2026-04-03 2026-05-25 2026-06-19 2026-07-03 "
        "2026-09-07 2026-11-26 2026-12-25 "
        "2027-01-01 2027-01-18 2027-02-15 2027-03-26 2027-05-31 2027-06-18 2027-07-05 "
        "2027-09-06 2027-11-25 2027-12-24"
    ).split()
}
NY, BJ = ZoneInfo("America/New_York"), ZoneInfo("Asia/Shanghai")

ONE_BP_NAMES = {"SPY", "QQQ", "SGOV", "SHV", "SHY", "BIL"}
CASH_ALIASES = {"SHY", "BIL"}  # sleeve cash instruments map onto the account's T-bill fund


def spread_bp(sym: str) -> float:
    """Half spread at the open in bp. 1 bp for SPY/QQQ/T-bill funds, 5 bp for everything else
    (leveraged ETFs by the task rule; other ETFs take the same conservative 5 bp, 待核对)."""
    return 1.0 if sym in ONE_BP_NAMES else 5.0


# --------------------------------------------------------------------------------------
# Calendar
# --------------------------------------------------------------------------------------
def next_session(d: date) -> date:
    x = d + timedelta(days=1)
    while x.weekday() >= 5 or x in NYSE_HOLIDAYS:
        x += timedelta(days=1)
    return x


def order_window(signal_day: date, next_day: date) -> dict[str, str]:
    """Beijing-time order window: from the evening-after-close data (16:30 ET of the signal
    day) to 5 minutes before the next regular open (09:30 ET)."""
    start = datetime.combine(signal_day, datetime.min.time().replace(hour=16, minute=30), NY)
    open_ = datetime.combine(next_day, datetime.min.time().replace(hour=9, minute=30), NY)
    end = open_ - timedelta(minutes=5)
    fmt = "%m月%d日 %H:%M"
    return {
        "start_bj": start.astimezone(BJ).strftime(fmt),
        "end_bj": end.astimezone(BJ).strftime(fmt),
        "open_bj": open_.astimezone(BJ).strftime(fmt),
        "open_et": open_.strftime("%H:%M"),
        "dst": "夏令时" if open_.dst() else "冬令时",
    }


# --------------------------------------------------------------------------------------
# Pure account simulation (unit-tested with fake data)
# --------------------------------------------------------------------------------------
@dataclass
class Params:
    start_cash: float = START_CASH
    min_order: float = MIN_ORDER_USD
    whole_shares: bool = True
    spread_mult: float = 1.0
    fees: bool = True
    delay: int = 0
    halve_dd: float | None = HALVE_DD
    stop_dd: float | None = STOP_DD
    sleeve_exit_dd: float | None = None  # S3 sub-strategy 25% exit: only the *-sleeve-exit accounts
    z_mu: float | None = None  # account-level daily mean excess return under the null
    z_sigma: float | None = None  # account-level daily sigma
    spread_fn: Callable[[str], float] = spread_bp


def cent_up(x: float) -> float:
    return math.ceil(round(x * 100.0, 6)) / 100.0 if x > 0 else 0.0


def sell_fees(gross: float, shares: float, p: Params) -> tuple[float, float]:
    if not p.fees:
        return 0.0, 0.0
    return cent_up(gross * SEC_RATE), cent_up(min(shares * TAF_RATE, TAF_CAP))


@dataclass
class Order:
    sym: str
    shares: float  # signed: + buy, - sell
    ref_px: float
    decided: int
    due: int


def simulate_account(
    dates: list[str],
    syms: list[str],
    opn: np.ndarray,
    cls: np.ndarray,
    target_fn: Callable[[int], tuple[dict[str, float], dict[str, float]]],
    p: Params,
    i0: int,
    i1: int,
    cash_sym: str,
    sleeve_ret: np.ndarray | None = None,
) -> dict[str, Any]:
    """Run sessions i0..i1. target_fn(j) -> (target weights, S3 risky part) for the open of
    session j, decided at the close of j-1. Orders are sized at the decision close, filled at
    the open of j (+ p.delay sessions) with a half spread, sells first, buys limited by cash."""
    n = len(dates)
    cash = p.start_cash
    shares: dict[str, float] = {}
    queue: list[Order] = []
    last_key: tuple | None = None
    peak = p.start_cash
    sleeve_nav, sleeve_peak = 1.0, 1.0
    dd_state, sleeve_out = "normal", False
    prev_equity = p.start_cash
    sum_ex, t_sess = 0.0, 0
    rows: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []

    ci = {s: k for k, s in enumerate(syms)}

    def px(arr: np.ndarray, i: int, s: str) -> float:
        return float(arr[i, ci[s]])

    def decide(c: int) -> None:
        nonlocal last_key
        j = c + 1
        if j >= n:
            return
        w_tot, w_s3 = target_fn(j)
        w = dict(w_tot)
        if dd_state == "stop":
            w = {cash_sym: 1.0}
        else:
            keep = 0.0 if sleeve_out else (0.5 if dd_state == "half" else 1.0)
            if keep < 1.0:
                for s, v in w_s3.items():
                    w[s] = w.get(s, 0.0) - (1.0 - keep) * v
                    w[cash_sym] = w.get(cash_sym, 0.0) + (1.0 - keep) * v
        key = tuple(sorted((s, round(v, 9)) for s, v in w.items() if abs(v) > 1e-12))
        info = {
            "decision_index": c,
            "decision_date": dates[c],
            "order_date": dates[j],
            "state": "stop" if dd_state == "stop" else ("sleeve_exit" if sleeve_out else dd_state),
            "s3_drawdown": 1.0 - sleeve_nav / sleeve_peak,
            "orders": [],
            "target": {s: v for s, v in key},
        }
        equity = cash + sum(h * px(cls, c, s) for s, h in shares.items() if h)
        info["equity_ref"] = equity
        if key != last_key:
            last_key = key
            proj = dict(shares)
            for o in queue:
                proj[o.sym] = proj.get(o.sym, 0.0) + o.shares
            for s in sorted(set(w) | {k for k, v in proj.items() if v}):
                ref = px(cls, c, s) if s in ci else float("nan")
                if not np.isfinite(ref) or ref <= 0:
                    continue
                tv = w.get(s, 0.0) * equity
                tgt = math.floor(tv / ref + 1e-9) if p.whole_shares else tv / ref
                d = tgt - proj.get(s, 0.0)
                if abs(d) * ref < p.min_order:
                    continue
                o = Order(s, d, ref, c, j + p.delay)
                queue.append(o)
                info["orders"].append(
                    {
                        "symbol": s,
                        "side": "buy" if d > 0 else "sell",
                        "shares": abs(d),
                        "ref_price": ref,
                        "est_usd": abs(d) * ref,
                        "fill_date": dates[min(j + p.delay, n - 1)],
                    }
                )
        decisions.append(info)

    def execute(i: int) -> list[dict[str, Any]]:
        nonlocal cash
        out: list[dict[str, Any]] = []
        due = [o for o in queue if o.due == i]
        for o in due:
            queue.remove(o)
        for o in sorted(due, key=lambda o: (o.shares > 0, -abs(o.shares) * o.ref_px)):
            o_px = px(opn, i, o.sym)
            rec = {"symbol": o.sym, "side": "buy" if o.shares > 0 else "sell"}
            if not np.isfinite(o_px) or o_px <= 0:
                out.append(
                    {**rec, "shares": 0.0, "fill_price": None, "fees": 0.0, "note": "no_price"}
                )
                continue
            hs = p.spread_fn(o.sym) * p.spread_mult / 1e4
            if o.shares < 0:
                n_sh = min(-o.shares, shares.get(o.sym, 0.0))
                if n_sh <= 0:
                    continue
                f_px = o_px * (1.0 - hs)
                gross = n_sh * f_px
                sec, taf = sell_fees(gross, n_sh, p)
                cash += gross - sec - taf
                shares[o.sym] = shares.get(o.sym, 0.0) - n_sh
                out.append({**rec, "shares": n_sh, "fill_price": f_px, "fees": sec + taf})
            else:
                f_px = o_px * (1.0 + hs)
                n_sh = o.shares
                afford = cash / f_px
                if n_sh > afford:
                    n_sh = math.floor(afford + 1e-12) if p.whole_shares else afford
                if n_sh <= 0:
                    out.append(
                        {**rec, "shares": 0.0, "fill_price": f_px, "fees": 0.0, "note": "no_cash"}
                    )
                    continue
                cash -= n_sh * f_px
                shares[o.sym] = shares.get(o.sym, 0.0) + n_sh
                out.append({**rec, "shares": n_sh, "fill_price": f_px, "fees": 0.0})
        return out

    decide(i0 - 1)
    for i in range(i0, i1 + 1):
        fills = execute(i)
        equity = cash + sum(h * px(cls, i, s) for s, h in shares.items() if h)
        peak = max(peak, equity)
        dd = 1.0 - equity / peak
        if p.stop_dd is not None and dd >= p.stop_dd:
            dd_state = "stop"
        elif p.halve_dd is not None and dd >= p.halve_dd and dd_state == "normal":
            dd_state = "half"
        if sleeve_ret is not None and i > i0:
            sleeve_nav *= 1.0 + float(sleeve_ret[i])
            sleeve_peak = max(sleeve_peak, sleeve_nav)
            if p.sleeve_exit_dd is not None and 1.0 - sleeve_nav / sleeve_peak >= p.sleeve_exit_dd:
                sleeve_out = True  # sticky
        t_sess += 1
        r_acc = equity / prev_equity - 1.0
        c_prev = px(cls, i - 1, cash_sym) if i > 0 else float("nan")
        r_cash = px(cls, i, cash_sym) / c_prev - 1.0 if np.isfinite(c_prev) and c_prev > 0 else 0.0
        sum_ex += r_acc - r_cash
        prev_equity = equity
        z = z_flag = None
        if p.z_mu is not None and p.z_sigma:
            z = (sum_ex - t_sess * p.z_mu) / (p.z_sigma * math.sqrt(t_sess))
            if t_sess >= Z_FROM_SESSION:
                z_flag = "stop" if z < Z_STOP else ("review" if z < Z_REVIEW else None)
        rows.append(
            {
                "date": dates[i],
                "orders": fills,
                "fees": sum(f["fees"] for f in fills),
                "equity": equity,
                "cash": cash,
                "drawdown": dd,
                "stop_state": "stop"
                if dd_state == "stop"
                else ("sleeve_exit" if sleeve_out else dd_state),
                "dd_state": dd_state,
                "sleeve_exit": sleeve_out,
                "s3_drawdown": 1.0 - sleeve_nav / sleeve_peak,
                "z": z,
                "z_flag": z_flag,
                "positions": {s: h for s, h in sorted(shares.items()) if h},
            }
        )
        decide(i)
    pend = [
        {
            "symbol": o.sym,
            "side": "buy" if o.shares > 0 else "sell",
            "shares": abs(o.shares),
            "ref_price": o.ref_px,
            "fill_date": dates[o.due] if o.due < n else None,
        }
        for o in queue
    ]
    return {"rows": rows, "decisions": decisions, "pending": pend, "cash": cash, "shares": shares}


# --------------------------------------------------------------------------------------
# Accounts
# --------------------------------------------------------------------------------------
@dataclass
class AccountDef:
    name: str
    desc: str
    parts: list[tuple[str, float]] = field(default_factory=list)  # (sleeve, fraction)
    hold: str | None = None  # buy-and-hold symbol
    s3_sleeve: str | None = None
    delay: int = 0
    sleeve_exit: bool = False  # S3 sub-strategy 25% exit (sensitivity accounts only)
    wait: bool = False  # open mid-month: stay in cash until the next month-end signal


ACCOUNTS: list[AccountDef] = [
    AccountDef(
        "P", "S3 加半导体主题上限，占五成，其余短期国债基金", [("S3C", 0.5)], s3_sleeve="S3C"
    ),
    AccountDef("P100", "S3 加半导体主题上限，占十成", [("S3C", 1.0)], s3_sleeve="S3C"),
    AccountDef("S3U", "S3 不加主题上限，占五成，其余短期国债基金", [("S3U", 0.5)], s3_sleeve="S3U"),
    AccountDef("S1", "S1 占五成，其余短期国债基金", [("S1", 0.5)]),
    AccountDef("S2", "S2 占五成，其余短期国债基金", [("S2", 0.5)]),
    AccountDef("C2", "C2 占五成，其余短期国债基金", [("C2", 0.5)]),
    AccountDef("SPY", "全仓持有 SPY", hold="SPY"),
    AccountDef("QQQ", "全仓持有 QQQ", hold="QQQ"),
    AccountDef(
        "P-delay", "账户 P，每张单晚一个交易日成交", [("S3C", 0.5)], s3_sleeve="S3C", delay=1
    ),
]
ACCOUNTS += [
    AccountDef(
        "P-sleeve-exit",
        "账户 P，另加 S3 自带的 25% 回撤退出（敏感性）",
        [("S3C", 0.5)],
        s3_sleeve="S3C",
        sleeve_exit=True,
    ),
    AccountDef(
        "P100-sleeve-exit",
        "账户 P100，另加 S3 自带的 25% 回撤退出（敏感性）",
        [("S3C", 1.0)],
        s3_sleeve="S3C",
        sleeve_exit=True,
    ),
]
# replay-only: account opened mid-month that waits in cash for the next month-end signal
REPLAY_ONLY: list[AccountDef] = [
    AccountDef(
        "P-open-wait",
        "账户 P，起点是月中时先持有现金基金，等下一个月末信号",
        [("S3C", 0.5)],
        s3_sleeve="S3C",
        wait=True,
    ),
]
SLEEVES_NEEDED = ("S3C", "S3U", "S1", "S2", "C2")


@dataclass
class Engine:
    dates: list[str]  # last entry = next session (no prices)
    syms: list[str]
    opn: np.ndarray
    cls: np.ndarray
    tb: str
    sleeve_w: dict[str, np.ndarray]  # name -> (n, m) effective weights over syms
    sleeve_ret: dict[str, np.ndarray]
    last_session: str
    meta: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, tuple[np.ndarray, list[str]]] = field(default_factory=dict)

    @property
    def n_real(self) -> int:
        return len(self.dates) - 1


def first_month_start(dates: list[str], i0: int) -> int:
    """First session after i0 that opens a new calendar month (= first rebalance start)."""
    for j in range(i0 + 1, len(dates)):
        if dates[j][:7] != dates[j - 1][:7]:
            return j
    return len(dates)


def make_target_fn(
    eng: Engine, acc: AccountDef, i0: int | None = None
) -> Callable[[int], tuple[dict, dict]]:
    tb = eng.tb
    wait_until = first_month_start(eng.dates, i0) if acc.wait and i0 is not None else -1

    def fn(j: int) -> tuple[dict[str, float], dict[str, float]]:
        if acc.hold:
            return {acc.hold: 1.0}, {}
        if j < wait_until:
            return {tb: 1.0}, {}
        w: dict[str, float] = {tb: 1.0 - sum(f for _, f in acc.parts)}
        w_s3: dict[str, float] = {}
        for sl, frac in acc.parts:
            row = eng.sleeve_w[sl][j]
            for k in np.flatnonzero(np.abs(row) > 1e-12):
                s = eng.syms[k]
                w[s] = w.get(s, 0.0) + frac * float(row[k])
                if sl == acc.s3_sleeve and s != tb:
                    w_s3[s] = w_s3.get(s, 0.0) + frac * float(row[k])
        return w, w_s3

    return fn


def z_params() -> dict[str, Any]:
    """Pilot-spec null for the forward z: account-level daily mean excess return (T-58
    scenario A, the DSR-haircut mean) and sigma (0.5 x daily sigma of the S3 pilot sleeve's
    excess over cash on the T-58 panel). Cached with sources in z-params.json."""
    if Z_PARAM_FILE.exists():
        return json.loads(Z_PARAM_FILE.read_text(encoding="utf-8"))
    import pandas as pd

    t58 = json.loads(T58_RESULTS.read_text(encoding="utf-8"))
    mu_a = float(t58["deployables"]["50k"]["cash"]["p0_s3"]["mu_daily"]["A"])
    panel = pd.read_parquet(Z_PANEL)
    ex = (panel["L1__S3"] - panel["CASH"]).dropna().to_numpy()
    sigma_sleeve = float(ex.std(ddof=1))
    res = {
        "account_s3_fraction": 0.5,
        "mu_daily_account": mu_a,
        "sigma_daily_sleeve": sigma_sleeve,
        "sigma_daily_account": 0.5 * sigma_sleeve,
        "sigma_ann_account": 0.5 * sigma_sleeve * math.sqrt(252),
        "sources": {
            "mu": f"{T58_RESULTS.relative_to(ROOT)} deployables.50k.cash.p0_s3.mu_daily.A",
            "sigma": f"{Z_PANEL.relative_to(ROOT)} column L1__S3 minus CASH, "
            f"{len(ex)} sessions, ddof=1",
            "definition": "reports/research/program/forward-stop-rules-2026-10-08/report.md s.1",
        },
    }
    OUT.mkdir(parents=True, exist_ok=True)
    Z_PARAM_FILE.write_text(json.dumps(res, indent=2) + "\n", encoding="utf-8")
    return res


def params_for(acc: AccountDef, zp: dict[str, Any] | None, **kw: Any) -> Params:
    p = Params(delay=acc.delay, **kw)
    if acc.s3_sleeve and zp:
        f = sum(fr for sl, fr in acc.parts if sl == acc.s3_sleeve)
        scale = f / zp["account_s3_fraction"]
        p.z_mu = zp["mu_daily_account"] * scale
        p.z_sigma = zp["sigma_daily_account"] * scale
    if not acc.s3_sleeve:
        p.halve_dd = p.stop_dd = None
    if acc.sleeve_exit and "sleeve_exit_dd" not in kw:
        p.sleeve_exit_dd = SLEEVE_EXIT_DD
    return p


def run_accounts(
    eng: Engine,
    i0: int,
    i1: int,
    names: list[str] | None = None,
    **kw: Any,
) -> dict[str, dict[str, Any]]:
    zp = z_params()
    res = {}
    for acc in ACCOUNTS + REPLAY_ONLY:
        if (names and acc.name not in names) or (not names and acc in REPLAY_ONLY):
            continue
        p = params_for(acc, zp, **kw)
        sret = eng.sleeve_ret.get(acc.s3_sleeve) if acc.s3_sleeve else None
        res[acc.name] = simulate_account(
            eng.dates,
            eng.syms,
            eng.opn,
            eng.cls,
            make_target_fn(eng, acc, i0),
            p,
            i0,
            i1,
            eng.tb,
            sret,
        )
    return res


# --------------------------------------------------------------------------------------
# Engine from the T-32 context (heavy; not used by the unit tests)
# --------------------------------------------------------------------------------------
def map_sleeve(raw: tuple[np.ndarray, list[str]], syms: list[str], tb: str) -> np.ndarray:
    """Effective sleeve weights over the account symbols; sleeve cash goes to the T-bill fund."""
    eff, cols = raw
    ci = {s: k for k, s in enumerate(syms)}
    out = np.zeros((len(eff), len(syms)))
    for j, col in enumerate(cols):
        out[:, ci[tb] if col in CASH_ALIASES else ci[col]] += eff[:, j]
    return out


def choose_tb(eng: Engine, i0: int, i1: int) -> str:
    """SGOV when it has data on every session needed, else SHV."""
    k = eng.syms.index("SGOV")
    return "SGOV" if np.isfinite(eng.cls[i0 - 1 : i1 + 1, k]).all() else "SHV"


def with_tb(eng: Engine, tb: str) -> Engine:
    if tb == eng.tb:
        return eng
    from dataclasses import replace

    sw = {k: map_sleeve(v, eng.syms, tb) for k, v in eng.raw.items()}
    return replace(eng, tb=tb, sleeve_w=sw)


def build_engine(last_session: str, start: str) -> Engine:
    import p2_theme_budget as p2
    import pandas as pd
    import run_h20260918_05_recent_menu as base
    import s3_tc10

    holder: dict[str, Any] = {}
    real_load = base.load_panel

    def patched(symbols: list[str]):
        close, open_ = real_load(symbols)
        holder["close"], holder["open"] = close.copy(), open_.copy()
        nxt = pd.Timestamp(next_session(close.index[-1].date()))
        close.loc[nxt] = close.iloc[-1]
        open_.loc[nxt] = open_.iloc[-1]
        return close, open_

    base.load_panel = patched
    try:
        ctx = p2.load_context(last_session)
        tb_close, tb_open = real_load(["SGOV", "SHV"])
    finally:
        base.load_panel = real_load
    idx = ctx.index
    n = len(idx)
    raw_c, raw_o = holder["close"], holder["open"]
    dates = [str(d.date()) for d in idx]
    extra = [s for s in ("SGOV", "SHV") if s not in raw_c.columns]
    syms = list(ctx.close.columns) + extra
    close = pd.concat([raw_c, tb_close.reindex(columns=extra)], axis=1).reindex(idx)
    opn_ = pd.concat([raw_o, tb_open.reindex(columns=extra)], axis=1).reindex(idx)
    close, opn_ = close[syms], opn_[syms]
    i_start = dates.index(start) if start in dates else None
    if i_start is None:
        raise SystemExit(f"start {start} is not a session in the panel")
    sg = close["SGOV"].to_numpy()[i_start - 1 : n - 1]
    tb = "SGOV" if np.isfinite(sg).all() else "SHV"

    s3 = ctx.insts["S3_0"]
    w_cap = s3_tc10.capped_targets(ctx, s3, 0.10, 0)["w"]
    sleeve_w, sleeve_ret, raw = {}, {}, {}
    variants = {
        "S3C": (s3, p2.eff_of(ctx, s3, w_cap)),
        "S3U": (s3, s3.eff0),
        "S1": (ctx.insts["S1"], ctx.insts["S1"].eff0),
        "S2": (ctx.insts["S2"], ctx.insts["S2"].eff0),
        "C2": (ctx.insts["C2"], ctx.insts["C2"].eff0),
    }
    for name, (inst, eff) in variants.items():
        raw[name] = (np.asarray(eff, dtype=float), list(inst.cols2))
        sleeve_w[name] = map_sleeve(raw[name], syms, tb)
        sleeve_ret[name] = np.asarray(p2.finish(ctx, eff, inst.cols2)["r10"], dtype=float)
    return Engine(
        dates=dates,
        syms=syms,
        opn=opn_.to_numpy(dtype=float),
        cls=close.to_numpy(dtype=float),
        tb=tb,
        sleeve_w=sleeve_w,
        sleeve_ret=sleeve_ret,
        last_session=last_session,
        meta={"code_commit": code_commit(), "built_utc": now_utc()},
        raw=raw,
    )


def _jd(o: Any) -> Any:
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(f"not JSON serializable: {type(o).__name__}")


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def code_commit() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def latest_session() -> str:
    import s3_tc10

    return s3_tc10.latest_session()


# --------------------------------------------------------------------------------------
# Metrics
# --------------------------------------------------------------------------------------
def series_metrics(
    equity: np.ndarray, start_cash: float, rf: np.ndarray | None = None
) -> dict[str, Any]:
    eq = np.concatenate([[start_cash], equity])
    r = eq[1:] / eq[:-1] - 1.0
    n = len(r)
    peak = np.maximum.accumulate(eq)
    dd = eq / peak - 1.0
    ex = r - (rf if rf is not None else 0.0)
    sd = float(ex.std(ddof=1)) if n > 1 else float("nan")
    trough = int(np.argmin(dd))
    rec = None
    if dd[trough] < 0:
        after = np.flatnonzero(eq[trough:] >= peak[trough])
        rec = int(after[0]) if len(after) else None
    return {
        "sessions": n,
        "total_return": float(eq[-1] / eq[0] - 1.0),
        "cagr": float((eq[-1] / eq[0]) ** (252.0 / n) - 1.0) if n else None,
        "sharpe_excess": float(ex.mean() / sd * math.sqrt(252)) if sd and sd > 0 else None,
        "max_drawdown": float(dd.min()),
        "recovery_sessions": rec,
        "recovered": rec is not None or dd[trough] == 0,
    }


def monthly_table(rows: list[dict[str, Any]], start_cash: float) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    prev = start_cash
    for r in rows:
        m = r["date"][:7]
        e = out.setdefault(m, {"month": m, "start": prev, "orders": 0})
        e["end"] = r["equity"]
        e["orders"] += sum(1 for f in r["orders"] if f["shares"] > 0)
        prev = r["equity"]
    for e in out.values():
        e["pnl_pct"] = e["end"] / e["start"] - 1.0
    return list(out.values())


def account_summary(
    rows: list[dict[str, Any]], start_cash: float, rf: np.ndarray | None
) -> dict[str, Any]:
    eq = np.array([r["equity"] for r in rows])
    m = series_metrics(eq, start_cash, rf)
    m["orders_filled"] = sum(1 for r in rows for f in r["orders"] if f["shares"] > 0)
    m["order_days"] = sum(1 for r in rows if any(f["shares"] > 0 for f in r["orders"]))
    m["fees_total"] = float(sum(r["fees"] for r in rows))
    m["final_equity"] = float(eq[-1])
    last = rows[-1]
    m["stop_state"] = last["stop_state"]
    m["z"] = last["z"]
    m["z_flag"] = last["z_flag"]
    m["max_dd_rule_first_trigger"] = next(
        (r["date"] for r in rows if r["dd_state"] != "normal"), None
    )
    m["sleeve_exit_first"] = next((r["date"] for r in rows if r["sleeve_exit"]), None)
    return m


def cash_returns(eng: Engine, i0: int, i1: int) -> np.ndarray:
    k = eng.syms.index(eng.tb)
    c = eng.cls[:, k]
    return c[i0 : i1 + 1] / c[i0 - 1 : i1] - 1.0


# --------------------------------------------------------------------------------------
# Order sheet (Chinese)
# --------------------------------------------------------------------------------------
def fmt_usd(x: float) -> str:
    return f"{x:,.0f} 美元"


def order_sheet(dec: dict[str, Any], acc_state: dict[str, Any], is_history: bool, tb: str) -> str:
    sig = date.fromisoformat(dec["decision_date"])
    nxt = date.fromisoformat(dec["order_date"])
    w = order_window(sig, nxt)
    lines = [
        f"# 下单清单（模拟，不需要你下单）：{dec['order_date']} 美股开盘（账户 P，信号日 {dec['decision_date']} 收盘后）",
        "",
    ]
    if is_history:
        lines += ["（历史回放生成：用于对照，当时没有真实下单。）", ""]
    orders = dec["orders"]
    lines += [
        "## 下单时间窗口（北京时间）",
        f"- 可以下单：{w['start_bj']} 起（收盘数据出来之后）到 {w['end_bj']} 止。",
        f"- 美股 {nxt.strftime('%m月%d日')} 开盘：北京时间 {w['open_bj']}（美东 {w['open_et']}，{w['dst']}）。"
        "11 月 1 日夏令时结束后开盘改为北京时间 22:30。",
        "",
    ]
    if not orders:
        lines += ["## 今天不用下单", ""]
        why = "目标没有变化，持仓不动。"
        if dec["state"] == "stop":
            why = "停止线已触发，持仓已全部换成短期国债基金，不再下新单。"
        lines += [why, ""]
    else:
        lines += [
            "## 要下的单（全部是：市价单，当日有效，常规时段）",
            "",
            "| 代码 | 买/卖 | 股数 | 预计金额 | 订单类型 |",
            "|---|---|---|---|---|",
        ]
        buys = sells = 0.0
        for o in sorted(orders, key=lambda o: (o["side"] != "sell", -o["est_usd"])):
            side = "买入" if o["side"] == "buy" else "卖出"
            sh = f"{o['shares']:.0f}"
            lines.append(
                f"| {o['symbol']} | {side} | {sh} | 约 {fmt_usd(o['est_usd'])} | 开盘成交的市价单（Day） |"
            )
            if o["side"] == "buy":
                buys += o["est_usd"]
            else:
                sells += o["est_usd"]
        lines += [
            "",
            "先下卖单，卖单成交后再下买单（买入金额不能超过账户现金，不借钱）。"
            "金额按信号日收盘价估算，实际按开盘价成交，可能略有出入。",
            "",
        ]
        cash_now = acc_state["cash"]
        lines += [
            "## 下单前核对",
            f"- 账户可用现金约 {fmt_usd(cash_now)}（模拟账户），卖出预计回款约 {fmt_usd(sells)}，"
            f"买入合计约 {fmt_usd(buys)}：{'够' if cash_now + sells >= buys else '不够，买单要按现金缩小股数'}。",
            "- 确认没有挂着的旧单（有就先撤）。",
            "- 现金账户式使用：不要用保证金借钱，买单总额不超过可用现金。",
            f"- 现金部分放在短期国债基金 {tb}。",
        ]
    lines += [
        "",
        f"当前停止线状态：{dec['state']}。账户权益（信号日收盘）约 {fmt_usd(dec['equity_ref'])}。",
        f"杠杆轮动部分从自身峰值的回撤：{dec.get('s3_drawdown', 0.0) * 100:.1f}%（只供参考，不触发任何交易，也不是新的复审线）。",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------------------
# Outputs: ledger, state, orders, summary (idempotent)
# --------------------------------------------------------------------------------------
def read_ledger(path: Path) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = json.loads(line)
                out[(r["date"], r["account"])] = r
    return out


def commit_outputs(
    results: dict[str, dict[str, Any]],
    eng: Engine,
    out: Path,
    start: str,
    i1: int,
) -> dict[str, Any]:
    """Append ledger rows that are not there yet, rewrite state/orders. Running twice with the
    same data changes nothing. Returns {appended, mismatches}."""
    out.mkdir(parents=True, exist_ok=True)
    led_path = out / "ledger.jsonl"
    existing = read_ledger(led_path)
    appended, mismatches = 0, []
    with led_path.open("a", encoding="utf-8") as fh:
        for acc in ACCOUNTS:
            if acc.name not in results:
                continue
            for r in results[acc.name]["rows"]:
                key = (r["date"], acc.name)
                if key in existing:
                    if abs(existing[key]["equity"] - r["equity"]) > 1e-6:
                        mismatches.append({"date": r["date"], "account": acc.name})
                    continue
                fh.write(json.dumps({"account": acc.name, **r}, default=_jd) + "\n")
                appended += 1
    state = {
        "start": start,
        "last_session": eng.dates[i1],
        "next_session": eng.dates[i1 + 1],
        "tbill": eng.tb,
        "code_commit": eng.meta.get("code_commit"),
        "accounts": {
            name: {
                "equity": res["rows"][-1]["equity"],
                "cash": res["cash"],
                "positions": {s: h for s, h in res["shares"].items() if h},
                "stop_state": res["rows"][-1]["stop_state"],
                "z": res["rows"][-1]["z"],
                "pending_orders": res["pending"],
            }
            for name, res in results.items()
        },
    }
    (out / "state.json").write_text(
        json.dumps(state, indent=2, default=_jd) + "\n", encoding="utf-8"
    )
    if "P" in results:
        od = out / "orders"
        od.mkdir(exist_ok=True)
        rows = {r["date"]: r for r in results["P"]["rows"]}
        for dec in results["P"]["decisions"]:
            is_hist = dec["order_date"] <= eng.dates[i1]
            acc_state = {
                "cash": rows[dec["decision_date"]]["cash"]
                if dec["decision_date"] in rows
                else START_CASH
            }
            (od / f"{dec['order_date']}.md").write_text(
                order_sheet(dec, acc_state, is_hist, eng.tb), encoding="utf-8"
            )
    return {"appended": appended, "mismatches": mismatches}


def paper_comparison(results: dict[str, dict[str, Any]]) -> list[str]:
    if not PAPER_FILLS.exists():
        return ["（没有找到主账户 S3 模拟盘成交记录：待核对。）"]
    fills = [
        json.loads(x) for x in PAPER_FILLS.read_text(encoding="utf-8").splitlines() if x.strip()
    ]
    model: dict[tuple[str, str, str], dict[str, Any]] = {}
    if "S3U" in results:
        for r in results["S3U"]["rows"]:
            for f in r["orders"]:
                if f["shares"] > 0:
                    model[(r["date"], f["symbol"], f["side"])] = f
    lines = [
        "| 日期 | 代码 | 买/卖 | 模拟盘成交股数 | 模拟盘成交均价 | 当日开盘价 | 本地模拟（S3U）股数 | 本地模拟成交价 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for f in fills:
        m = model.get((f["session"], f["symbol"], f["side"]))
        ms = f"{m['shares']:.0f}" if m else "无对应"
        mp = f"{m['fill_price']:.2f}" if m else "无对应"
        lines.append(
            f"| {f['session']} | {f['symbol']} | {f['side']} | {f['filled_qty']:.0f} | "
            f"{f['filled_avg_price']:.2f} | {f['official_open']:.2f} | {ms} | {mp} |"
        )
    return lines


def consistency_lines(cons: dict[str, Any] | None) -> list[str]:
    if not cons:
        return []
    L = [
        "## 子策略目标与模拟盘记录的一致性（只读 reports/paper/rehearsal）",
        "",
        f"比较各子策略模拟盘每天记录的目标权重和本地同一天的目标，差在 {cons['tolerance'] * 100:.0f} 个百分点以内算一致。"
        "按“天”（当天每个记录的代码都一致，且本地没有多出的持仓）和按“行”（日期×代码）各算一次。",
        "",
        "| 子策略 | 天数 | 一致天数 | 一致率（天） | 行数 | 一致行数 | 一致率（行） |",
        "|---|---|---|---|---|---|---|",
    ]
    for name, c in cons["sleeves"].items():
        rd = c["sessions_match"] / c["sessions"] if c["sessions"] else float("nan")
        rr = c["rows_match"] / c["rows"] if c["rows"] else float("nan")
        L.append(
            f"| {name} | {c['sessions']} | {c['sessions_match']} | {rd * 100:.0f}% | {c['rows']} | {c['rows_match']} | {rr * 100:.0f}% |"
        )
    notes = OUT / "consistency-notes.md"
    L += ["", notes.read_text(encoding="utf-8") if notes.exists() else "（差别原因待核对。）", ""]
    return L


def write_summary(
    results: dict[str, dict[str, Any]],
    eng: Engine,
    out: Path,
    start: str,
    i0: int,
    i1: int,
    sens: dict[str, dict[str, Any]] | None = None,
    cons: dict[str, Any] | None = None,
) -> None:
    rf = cash_returns(eng, i0, i1)
    names = {a.name: a for a in ACCOUNTS}
    lines = [
        f"# 实盘模拟账户汇总（{eng.dates[i0]} 至 {eng.dates[i1]}）",
        "",
        f"生成：{now_utc()}，代码提交 {eng.meta.get('code_commit')}，现金基金 {eng.tb}。起始资金 {START_CASH:,.0f} 美元。",
        "成交价是模型（次日官方开盘价加半价差），不是真实成交。",
        "",
        "| 账户 | 内容 | 期末权益 | 收益 | 最大回撤 | 买入笔数 | 费用合计 | 停止线 | 前向 z |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    summ = {}
    for name, res in results.items():
        s = account_summary(res["rows"], START_CASH, rf)
        summ[name] = s
        z = (
            ""
            if s["z"] is None
            else f"{s['z']:.2f}" + (f"（{s['z_flag']}）" if s["z_flag"] else "")
        )
        lines.append(
            f"| {name} | {names[name].desc} | {s['final_equity']:,.0f} | {s['total_return'] * 100:+.2f}% | "
            f"{s['max_drawdown'] * 100:.2f}% | {s['orders_filled']} | {s['fees_total']:.2f} | {s['stop_state']} | {z} |"
        )
    for name, res in (sens or {}).items():
        s = account_summary(res["rows"], START_CASH, rf)
        summ[f"{name}-cost2x"] = s
        lines.append(
            f"| {name}（成本加倍） | 半价差乘 2 的敏感性 | {s['final_equity']:,.0f} | "
            f"{s['total_return'] * 100:+.2f}% | {s['max_drawdown'] * 100:.2f}% | "
            f"{s['orders_filled']} | {s['fees_total']:.2f} | {s['stop_state']} | |"
        )
    lines += [
        "",
        "区间很短（几十个交易日），收益和回撤只能看作流程是否跑通，不能当作策略证据。",
        "",
        "## 与主账户 S3 模拟盘实际成交的对照（只读 reports/paper/rehearsal）",
        "",
        "主账户 S3 模拟盘从 2026-09-21 才开始，用 1.5 万美元预算、不加主题上限，现金基金是 SHY；"
        "本地模拟从 2026-09-01 开始、现金基金是 " + eng.tb + "。所以只能对照同一天同一代码的成交。",
        "",
        *paper_comparison(results),
        "",
        *consistency_lines(cons),
    ]
    (out / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    (out / "summary.json").write_text(
        json.dumps(summ, indent=2, default=_jd) + "\n", encoding="utf-8"
    )


PAPER_NAMES = {
    "S1": "us_etf_sector_rotation_252_top2_weekly",
    "S2": "us_etf_growth_rotation_blend_top2_monthly",
    "C2": "us_etf_eom_sector_blend_monthly",
    "S3U": "us_etf_levered_rotation_63_top2_monthly",
}
CONSISTENCY_TOL = 0.03
PAPER_REHEARSAL = ROOT / "reports/paper/rehearsal"


def paper_consistency(eng: Engine) -> dict[str, Any]:
    """Compare each paper sleeve's recorded daily target weights (rehearsal reports, read only)
    with the same-day sleeve target of this simulation. One row per (session, symbol)."""
    out: dict[str, Any] = {"tolerance": CONSISTENCY_TOL, "sleeves": {}}
    for sleeve, name in PAPER_NAMES.items():
        latest: dict[str, tuple[str, list[dict[str, Any]]]] = {}
        for f in sorted(PAPER_REHEARSAL.glob(f"{name}-2026-*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            sess, gen = d.get("session"), str(d.get("generated_at"))
            if sess and (sess not in latest or gen > latest[sess][0]):
                latest[sess] = (gen, d.get("orders") or [])
        eff, cols = eng.raw[sleeve]
        n_sess = m_sess = n_rows = m_rows = 0
        mism: list[dict[str, Any]] = []
        for sess, (_, orders) in sorted(latest.items()):
            if sess not in eng.dates or not orders:
                continue
            j = eng.dates.index(sess)
            local = {c: float(eff[j, k]) for k, c in enumerate(cols)}
            seen: set[str] = set()
            ok = True
            for o in orders:
                sym = o["symbol"]
                seen.add(sym)
                pw, lw = float(o.get("target_weight") or 0.0), local.get(sym, 0.0)
                n_rows += 1
                if abs(pw - lw) <= CONSISTENCY_TOL:
                    m_rows += 1
                else:
                    ok = False
                    mism.append(
                        {
                            "session": sess,
                            "symbol": sym,
                            "paper_weight": pw,
                            "local_weight": lw,
                            "rebalance_id": o.get("rebalance_id"),
                        }
                    )
            for sym, lw in local.items():
                if lw > CONSISTENCY_TOL and sym not in seen:
                    ok = False
                    mism.append(
                        {
                            "session": sess,
                            "symbol": sym,
                            "paper_weight": None,
                            "local_weight": lw,
                            "rebalance_id": None,
                        }
                    )
            n_sess += 1
            m_sess += ok
        out["sleeves"][sleeve] = {
            "paper_strategy": name,
            "sessions": n_sess,
            "sessions_match": m_sess,
            "rows": n_rows,
            "rows_match": m_rows,
            "mismatches": mism,
        }
    return out


def run_live(start: str, rebuild: bool) -> int:
    last = latest_session()
    eng = build_engine(last, start)
    i0 = eng.dates.index(start)
    i1 = eng.n_real - 1
    if eng.dates[i1] != last:
        raise SystemExit(f"engine last session {eng.dates[i1]} != archive last {last}")
    led = OUT / "ledger.jsonl"
    if led.exists() and rebuild:
        bak = OUT / f"ledger.jsonl.bak-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        led.rename(bak)
    results = run_accounts(eng, i0, i1)
    info = commit_outputs(results, eng, OUT, start, i1)
    sens = run_accounts(eng, i0, i1, names=["P", "P100"], spread_mult=2.0)
    cons = paper_consistency(eng)
    (OUT / "consistency.json").write_text(
        json.dumps(cons, indent=2, default=_jd) + "\n", encoding="utf-8"
    )
    write_summary(results, eng, OUT, start, i0, i1, sens, cons)
    print(json.dumps({"last_session": last, "next_session": eng.dates[i1 + 1], **info}, indent=2))
    return 0 if not info["mismatches"] else 3


# --------------------------------------------------------------------------------------
# Replay (research, one-off)
# --------------------------------------------------------------------------------------
REPLAY_WINDOWS = {
    "recent": ("2024-01-08", "latest"),
    "stress2018": ("2018-01-02", "2018-12-31"),
    "stress2020": ("2020-01-02", "2020-12-31"),
    "stress2022": ("2022-01-03", "2022-12-30"),
}


def replay_window(start: str, end: str, tag: str, base_eng: Engine | None = None) -> int:
    if base_eng is None:
        last = latest_session() if end == "latest" else end
        base_eng = build_engine(last, start)
    real = base_eng.dates[: base_eng.n_real]
    if start not in real:
        raise SystemExit(f"{start} is not a session")
    i0 = real.index(start)
    i1 = base_eng.n_real - 1 if end == "latest" else max(k for k, d in enumerate(real) if d <= end)
    eng = with_tb(base_eng, choose_tb(base_eng, i0, i1))
    keep = ["P", "P100", "P-sleeve-exit", "P100-sleeve-exit", "SPY", "QQQ", "P-open-wait"]
    out: dict[str, Any] = {
        "tag": tag,
        "start": eng.dates[i0],
        "end": eng.dates[i1],
        "tbill": eng.tb,
        "code_commit": eng.meta.get("code_commit"),
        "run_utc": now_utc(),
        "accounts": {},
        "ladder": {},
    }
    rf = cash_returns(eng, i0, i1)

    def add(label: str, res: dict[str, Any], **extra: Any) -> dict[str, Any]:
        s = account_summary(res["rows"], START_CASH, rf)
        s["monthly"] = monthly_table(res["rows"], START_CASH)
        s["worst_month"] = min(s["monthly"], key=lambda m: m["pnl_pct"]) if s["monthly"] else None
        s.update(extra)
        return s

    full = run_accounts(eng, i0, i1, names=keep)
    for name in keep:
        out["accounts"][name] = add(name, full[name])
    cost2 = run_accounts(eng, i0, i1, names=["P"], spread_mult=2.0)["P"]
    out["accounts"]["P-cost2x"] = add("P-cost2x", cost2)
    # the S3 part on its own (engine sleeve return, 10 bp), counted from the first session
    sr_s3 = eng.sleeve_ret["S3C"][i0 + 1 : i1 + 1]
    nav = np.cumprod(1.0 + sr_s3)
    dd_s3 = 1.0 - nav / np.maximum.accumulate(np.concatenate([[1.0], nav]))[1:]
    hit = np.flatnonzero(dd_s3 >= SLEEVE_EXIT_DD)
    out["s3_sleeve"] = {
        "max_drawdown": float(dd_s3.max()) if len(dd_s3) else 0.0,
        "max_drawdown_date": eng.dates[i0 + 1 + int(dd_s3.argmax())] if len(dd_s3) else None,
        "first_date_ge_25pct": eng.dates[i0 + 1 + int(hit[0])] if len(hit) else None,
    }
    # ladder for P: each step removes one friction; rules off so the steps isolate frictions
    off = dict(halve_dd=None, stop_dd=None)
    steps = {
        "A0_frac_nocost": dict(whole_shares=False, spread_mult=0.0, fees=False, **off),
        "A1_frac_cost": dict(whole_shares=False, **off),
        "A2_whole_cost": dict(**off),
    }
    for label, kw in steps.items():
        res = run_accounts(eng, i0, i1, names=["P"], **kw)["P"]
        out["ladder"][label] = account_summary(res["rows"], START_CASH, rf)
    out["ladder"]["A3_acct_lines"] = account_summary(full["P"]["rows"], START_CASH, rf)
    out["ladder"]["A4_acct_lines_and_sleeve_exit"] = account_summary(
        full["P-sleeve-exit"]["rows"], START_CASH, rf
    )
    # engine reference: offset-0 S3-TC10 sleeve with the T-32 10 bp cost, half in the T-bill fund
    sr = eng.sleeve_ret["S3C"][i0 : i1 + 1]
    e0 = START_CASH * np.cumprod(1.0 + 0.5 * sr + 0.5 * rf)
    out["ladder"]["E0_engine_offset0_10bp"] = series_metrics(e0, START_CASH, rf)
    p = OUT / "replay"
    p.mkdir(parents=True, exist_ok=True)
    (p / f"{tag}.json").write_text(json.dumps(out, indent=2, default=_jd) + "\n", encoding="utf-8")
    print(json.dumps({k: out["accounts"][k]["total_return"] for k in out["accounts"]}, indent=2))
    return 0


def replay_all() -> int:
    last = latest_session()
    eng = build_engine(last, "2024-01-08")
    for tag, (start, end) in REPLAY_WINDOWS.items():
        replay_window(start, end, tag, eng)
    return replay_report()


def replay_report() -> int:
    d = OUT / "replay"
    tags = sorted(d.glob("*.json")) if d.exists() else []
    if not tags:
        raise SystemExit("no replay/*.json")
    data = [json.loads(t.read_text(encoding="utf-8")) for t in tags]
    t58 = json.loads(T58_RESULTS.read_text(encoding="utf-8"))
    spec = t58["deployables"]["50k"]["cash"]["p0_s3"]
    all_out = {
        "windows": {x["tag"]: x for x in data},
        "spec_backtest": {
            "recent": spec["recent"],
            "full_maxdd": spec["full_maxdd"],
            "worst_month": spec["worst_month"],
            "source": str(T58_RESULTS.relative_to(ROOT)),
        },
    }
    (OUT / "replay.json").write_text(
        json.dumps(all_out, indent=2, default=_jd) + "\n", encoding="utf-8"
    )
    L = [
        "# 历史回放（研究用，一次性）",
        "",
        "规则、成本、整股与实盘模拟账户完全相同；数字由 `scripts/live_shadow.py replay-all` 算出，存于 `replay.json`。",
        "账户 P 的停止线只有原定实盘规格的两条：账户回撤 25.7% 减半、30% 全部换成现金基金（前向 z 值只用于实时跟踪）。"
        "S3 自带的 25% 子策略退出不在主线里，只作敏感性（P-sleeve-exit）。这个取舍是看到第一版回放之后定的，依据是 10-07 已定稿的原定实盘规格。",
        "",
    ]
    for x in data:
        s3s = x["s3_sleeve"]
        pse = x["accounts"]["P-sleeve-exit"]["sleeve_exit_first"]
        pw = x["accounts"]["P-open-wait"]
        note = [
            f"杠杆轮动部分单独看（引擎收益，计 10bp 成本，从窗口第一天起算）：最大回撤 {s3s['max_drawdown'] * 100:.1f}%（{s3s['max_drawdown_date']}），"
            f"首次回撤超过 25% 的日期：{s3s['first_date_ge_25pct'] or '无'}。账户 P 按原定实盘规格继续持有，不触发交易。",
            f"敏感性：如果加上 S3 自带的 25% 回撤退出（P-sleeve-exit），它在 {pse or '没有'} 触发并一直空仓，"
            f"收益 {x['accounts']['P-sleeve-exit']['total_return'] * 100:+.1f}% 对 P 的 {x['accounts']['P']['total_return'] * 100:+.1f}%。",
            f"开户规则：窗口起点是月中或月初时，若先持有现金基金、等下一个月末信号再进（P-open-wait），收益 {pw['total_return'] * 100:+.1f}%，"
            f"最大回撤 {pw['max_drawdown'] * 100:.1f}%；直接沿用上一个月末信号（P）收益 {x['accounts']['P']['total_return'] * 100:+.1f}%，"
            f"最大回撤 {x['accounts']['P']['max_drawdown'] * 100:.1f}%。",
            "",
        ]
        L += [
            f"## {x['tag']}（{x['start']} 至 {x['end']}，现金基金 {x['tbill']}）",
            "",
            "| 账户 | 收益 | 年化 | 夏普(超额) | 最大回撤 | 回撤恢复(交易日) | 最差月 | 买入笔数 | 费用 | 停止线首次触发 | 停用日 |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, s in x["accounts"].items():
            wm = s["worst_month"]
            rec = (
                "未恢复"
                if not s["recovered"]
                else (
                    str(s["recovery_sessions"]) if s["recovery_sessions"] is not None else "无回撤"
                )
            )
            sh = "" if s["sharpe_excess"] is None else f"{s['sharpe_excess']:.2f}"
            L.append(
                f"| {name} | {s['total_return'] * 100:+.1f}% | {s['cagr'] * 100:+.1f}% | {sh} | {s['max_drawdown'] * 100:.1f}% | {rec} | {(wm['month'] + ' ' + format(wm['pnl_pct'] * 100, '+.1f') + '%') if wm else ''} | {s['orders_filled']} | {s['fees_total']:.0f} | {s['max_dd_rule_first_trigger'] or ''} | {s['sleeve_exit_first'] or ''} |"
            )
        L += [
            "",
            *note,
            "### 账户 P 每月盈亏和下单笔数",
            "",
            "| 月份 | 盈亏 | 买入笔数 |",
            "|---|---|---|",
        ]
        for m in x["accounts"]["P"]["monthly"]:
            L.append(f"| {m['month']} | {m['pnl_pct'] * 100:+.2f}% | {m['orders']} |")
        lad = x["ladder"]
        L += [
            "",
            "### 账户 P 与原定实盘规格回测的差别（逐项）",
            "",
            "| 口径 | 年化 | 夏普(超额) | 最大回撤 |",
            "|---|---|---|---|",
        ]
        if x["tag"] == "recent":
            r = all_out["spec_backtest"]["recent"]
            L.append(
                f"| 原定实盘规格回测（五个调仓偏移平均，近期，10bp） | {r['cagr'] * 100:.1f}% | {r['sr']:.2f} | {r['maxdd'] * 100:.1f}% |"
            )
        for k, lab in (
            ("E0_engine_offset0_10bp", "同一引擎只用月末偏移 0（单一调仓日），10bp"),
            (
                "A0_frac_nocost",
                "账户模拟（停止线全关）：开盘成交、只在目标变化时调仓、碎股、零成本",
            ),
            ("A1_frac_cost", "再加半价差和卖出费"),
            ("A2_whole_cost", "再改整股（停止线全关）"),
            ("A3_acct_lines", "再加账户 25.7%/30% 停止线（=账户 P，主线）"),
            (
                "A4_acct_lines_and_sleeve_exit",
                "另列：再加 S3 子策略 25% 退出（=P-sleeve-exit，不属于主线）",
            ),
        ):
            s = lad[k]
            sh = "" if s["sharpe_excess"] is None else f"{s['sharpe_excess']:.2f}"
            L.append(f"| {lab} | {s['cagr'] * 100:.1f}% | {sh} | {s['max_drawdown'] * 100:.1f}% |")
        steps_txt = []
        chain = [
            (
                "E0_engine_offset0_10bp",
                "A0_frac_nocost",
                "引擎的 10bp 成本换成账户成交（此步不计成本）并改成只在目标变化时调仓",
            ),
            ("A0_frac_nocost", "A1_frac_cost", "加半价差和卖出费（成本）"),
            ("A1_frac_cost", "A2_whole_cost", "改整股"),
            ("A2_whole_cost", "A3_acct_lines", "加账户 25.7%/30% 停止线"),
        ]
        if x["tag"] == "recent":
            r = all_out["spec_backtest"]["recent"]
            steps_txt.append(
                f"- 单一调仓日（月末偏移 0）对五个偏移平均：年化 {(lad['E0_engine_offset0_10bp']['cagr'] - r['cagr']) * 100:+.1f} 个百分点（这是调仓日运气，不是成本）"
            )
        for a_, b_, lab in chain:
            d = lad[b_]["cagr"] - lad[a_]["cagr"]
            steps_txt.append(f"- {lab}：年化 {d * 100:+.1f} 个百分点")
        d4 = lad["A4_acct_lines_and_sleeve_exit"]["cagr"] - lad["A3_acct_lines"]["cagr"]
        steps_txt.append(
            f"- 另列（不在主线里）：S3 自带的 25% 退出的代价：年化 {d4 * 100:+.1f} 个百分点"
        )
        L += ["逐项差别（年化，每一步在上一步基础上）：", "", *steps_txt, ""]
        L.append("")
    L += [
        "## 原定实盘规格回测数字的来源",
        "",
        f"`{all_out['spec_backtest']['source']}`：近期年化、夏普、最大回撤为 `recent`；十年最大回撤 {spec['full_maxdd'] * 100:.1f}%，最差月 {spec['worst_month'] * 100:.1f}%。",
        "",
    ]
    (OUT / "replay.md").write_text("\n".join(L), encoding="utf-8")
    print("wrote replay.md / replay.json")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("backfill")
    b.add_argument("--start", default=START_DEFAULT)
    b.add_argument("--rebuild", action="store_true")
    d = sub.add_parser("daily")
    d.add_argument("--start", default=START_DEFAULT)
    r = sub.add_parser("replay")
    r.add_argument("--start", required=True)
    r.add_argument("--end", required=True)
    r.add_argument("--tag", required=True)
    sub.add_parser("replay-report")
    sub.add_parser("replay-all")
    sub.add_parser("report")
    a = ap.parse_args(argv)
    if a.cmd in ("backfill", "daily"):
        return run_live(a.start, getattr(a, "rebuild", False))
    if a.cmd == "replay":
        return replay_window(a.start, a.end, a.tag)
    if a.cmd == "replay-all":
        return replay_all()
    if a.cmd == "replay-report":
        return replay_report()
    if a.cmd == "report":
        print((OUT / "summary.md").read_text(encoding="utf-8"))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
