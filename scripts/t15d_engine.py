# ruff: noqa: E501, E741
"""T-20261006-15-D engine: Reversal Trend (owner's Pine indicator) on 1-hour and 1-minute bars.

Conventions (amendment-2026-10-06-main-grid.md and hypotheses.md section 0):
* indicator = ``open_composer.research.pine_port.reversal_trend.compute_reversal_trend`` with default
  parameters, run on one continuous bar series per symbol (regular session only, bars chained across
  days as on a TradingView chart);
* signal on the close of bar t, fill at the open of bar t+1; a symbol never holds two positions, a
  signal at or before the exit bar of the open position is skipped (same rule as the old hourly module);
* exit ``time_stop`` after H bars (exit fill = open of bar entry+H); 1h trades may run overnight, 1m
  trades are flat at the close of the last bar of the session at the latest;
* basket P&L = mean over the basket's N slots of the per-symbol trade P&L on one unit of capital.

Everything here is pure numpy/pandas so it can be unit-tested without the data archives.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import t15_engine as E  # noqa: E402

WORK = ROOT / "data/features/t15_work"
D_MIN = WORK / "d_min"
SIG_DIR = WORK / "d_sig"
UNIVERSE = ROOT / "data/features/intraday5m/universe.parquet"
NSLOT = 390
FLAGS = ("f_bull", "f_recl", "f_bear", "f_recs")
CHUNK = 150_000
WARM = 15_000
BORROW_BP_YEAR = 25.0
STOCK_FEE_BP = 0.5
IMPACT_NOTIONAL = 2000.0  # $100k sleeve / 50 slots
MISSING_HS_BP = 40.0
SPLIT_FWD = (2, 3, 4, 5, 6, 7, 8, 10, 15, 20, 25, 30, 40, 50)
SPLIT_REV = (2, 3, 4, 5, 8, 10, 15, 20, 25, 30, 40, 50)

_master_cache: dict[str, pd.DatetimeIndex] = {}


def master() -> pd.DatetimeIndex:
    if "m" not in _master_cache:
        _master_cache["m"] = pd.DatetimeIndex(np.load(WORK / "ab_QQQ.npz")["dates"])
    return _master_cache["m"]


# ----------------------------------------------------------------------------- data hygiene
def clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Sort, drop non-positive / non-finite prices, bad prints (1-minute jump > 20% or range > 20%)."""
    df = df.sort_values(["date", "minute"], kind="mergesort").reset_index(drop=True)
    p = df[["open", "high", "low", "close"]].to_numpy("float64")
    ok = np.isfinite(p).all(axis=1) & (p > 0).all(axis=1) & (p[:, 1] >= p[:, 2] * 0.999999)
    df = df[ok].reset_index(drop=True)
    c = df["close"].to_numpy("float64")
    d = df["date"].to_numpy()
    prev = np.r_[np.nan, c[:-1]]
    same = np.r_[False, d[1:] == d[:-1]]
    with np.errstate(invalid="ignore", divide="ignore"):
        jump = same & (np.abs(c / prev - 1.0) > 0.2)
        wide = (df["high"].to_numpy("float64") / df["low"].to_numpy("float64") - 1.0) > 0.2
    return df[~(jump | wide)].reset_index(drop=True)


def split_adjust(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    """Back-adjust prices before a recognised split; return the adjusted frame and every
    'trigger session' (overnight gap beyond 25%, split-like or not) so trades through it are dropped.

    Split test: the first-open / previous-last-close ratio lies within 10% of 1/k (k:1 split, volume
    about x k) or k (reverse split, volume about / k). Anything else with a 25% gap is a real gap (kept
    in the series) but the session is still excluded from trading."""
    g = df.groupby("date", sort=True)
    first_open = g["open"].first()
    last_close = g["close"].last()
    vol = g["volume"].sum()
    ratio = (first_open / last_close.shift(1)).to_numpy("float64")
    dates = first_open.index
    vol_arr = vol.to_numpy("float64")
    trig = []
    adj = []  # (date, factor)
    for i in range(1, len(dates)):
        r = ratio[i]
        if not np.isfinite(r) or abs(r - 1.0) <= 0.25:
            continue
        trig.append(dates[i])
        lo = max(0, i - 5)
        base = np.median(vol_arr[lo:i]) if i > lo else np.nan
        vr = vol_arr[i] / base if np.isfinite(base) and base > 0 else np.nan
        hit = None
        for k in SPLIT_FWD:
            if abs(r * k - 1.0) < 0.10 and (not np.isfinite(vr) or vr >= 0.4 * k):
                hit = 1.0 / k
                break
        if hit is None:
            for k in SPLIT_REV:
                if abs(r / k - 1.0) < 0.10 and (not np.isfinite(vr) or vr <= 2.5 / k):
                    hit = float(k)
                    break
        if hit is not None:
            adj.append((dates[i], hit))
    if adj:
        df = df.copy()
        dts = df["date"].to_numpy()
        for dt, f in adj:
            m = dts < np.datetime64(dt)
            for c in ("open", "high", "low", "close"):
                df.loc[m, c] = df.loc[m, c] * f
    return df, pd.DatetimeIndex(trig)


def to_hourly(df: pd.DataFrame, phase: int = 0) -> pd.DataFrame:
    """09:30-anchored 60-minute buckets (bucket 0 starts at 09:30, later ones at 09:30 + phase + 60 k;
    the part of the session before the shifted anchor stays in bucket 0)."""
    off = df["minute"].to_numpy("int64") - 570
    b = np.maximum(0, (off - phase) // 60)
    g = df.groupby([df["date"].to_numpy(), b], sort=True)
    out = g.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        minute=("minute", "first"),
    )
    out.index.names = ["date", "bucket"]
    return out.reset_index()


# ----------------------------------------------------------------------------- indicator
def run_indicator(o, h, l, c, v=None) -> dict[str, np.ndarray]:
    """compute_reversal_trend in overlapping chunks (memory) -> the four final signals and ATR."""
    from open_composer.research.pine_port.reversal_trend import compute_reversal_trend

    n = len(o)
    out = {f: np.zeros(n, bool) for f in FLAGS}
    atr = np.full(n, np.nan, np.float32)
    frame = pd.DataFrame(
        {
            "open": o,
            "high": h,
            "low": l,
            "close": c,
            "volume": np.ones(n) if v is None else v,
        }
    )
    for start in range(0, n, CHUNK):
        lo = max(0, start - WARM)
        hi = min(n, start + CHUNK)
        res = compute_reversal_trend(frame.iloc[lo:hi].reset_index(drop=True))
        sl = slice(start - lo, None)
        for f in FLAGS:
            out[f][start:hi] = res[f].to_numpy(bool)[sl]
        atr[start:hi] = res["atr"].to_numpy(np.float32)[sl]
        del res
    out["atr"] = atr
    return out


# ----------------------------------------------------------------------------- trades
def last_row_of_day(day: np.ndarray) -> np.ndarray:
    n = len(day)
    ends = np.flatnonzero(np.r_[day[1:] != day[:-1], True])
    return ends[np.searchsorted(ends, np.arange(n))]


def _marks(e, xr, day_final, pe, px, o, c, day, lrd):
    """Daily marks (day, value) with value = price change / entry price, summing to (px-pe)/pe."""
    de = int(day[e])
    if day_final == de:
        return [(de, (px - pe) / pe)]
    out = []
    cur = pe
    r = e
    while True:
        lr = int(lrd[r])
        if lr >= xr:
            break
        out.append((int(day[lr]), (c[lr] - cur) / pe))
        cur = c[lr]
        r = lr + 1
    if int(day[xr]) != day_final:
        out.append((int(day[xr]), (c[xr] - cur) / pe))
        cur = c[xr]
    out.append((day_final, (px - cur) / pe))
    return out


def simulate(
    S: dict,
    long_flags: tuple[str, ...],
    short_flags: tuple[str, ...],
    H: int,
    intraday: bool,
    allow_day: np.ndarray | None = None,
    exit_rule: str = "time_stop",
    delay: int = 0,
    atr_mult: float = 2.0,
    bad_by_day: np.ndarray | None = None,
    entry_rows: np.ndarray | None = None,
    entry_sides: np.ndarray | None = None,
    no_block: bool = False,
) -> dict:
    """Trades of one symbol. ``allow_day`` (len D bool): decision days on which the symbol is tradeable.

    ``entry_rows``/``entry_sides`` replace the signal list (placebo entry points); same hold/exit machinery.
    Returns arrays: e, xr, side, pe, px, day_e, day_x, slot_e, slot_x, and flat marks (tid, day, val)."""
    o, h, l, c = S["o"], S["h"], S["l"], S["c"]
    day, slot = S["day"], S["slot"]
    n = len(o)
    lrd = last_row_of_day(day)
    if entry_rows is None:
        ls = np.zeros(n, bool)
        for f in long_flags:
            ls |= S[f]
        ss = np.zeros(n, bool)
        for f in short_flags:
            ss |= S[f]
        both = ls & ss
        cand = np.flatnonzero((ls | ss) & ~both)
        if allow_day is not None:
            cand = cand[allow_day[day[cand]]]
        sides = np.where(ls[cand], 1, -1)
    else:
        cand = np.asarray(entry_rows)
        sides = np.asarray(entry_sides)
        # placebo entries are the fill rows themselves: shift back one bar so the same code path applies
        cand = cand - 1 - delay
    rev_long = S["f_bear"]
    rev_short = S["f_bull"]
    atr = S["atr"]
    E_, XR, SIDE, PE, PX, DAY_E, DAY_X, SL_E, SL_X = ([] for _ in range(9))
    mt, md, mv, KEEP = [], [], [], []
    blocked = -1
    tid = 0
    for ci, (t, side) in enumerate(zip(cand.tolist(), sides.tolist(), strict=True)):
        if (t <= blocked and not no_block) or t < 0:
            continue
        e = t + 1 + delay
        if e >= n:
            continue
        if intraday and entry_rows is None and day[e] != day[t]:
            continue
        lastrow = int(lrd[e])
        ts_row = e + H - 1  # last held bar for a pure time stop
        pe = float(o[e])
        xr = None
        px = None
        at_close = False
        if exit_rule == "atr_trailing_2x":
            if side > 0:
                ref = c[e]
                stop = ref - atr_mult * atr[e]
            else:
                ref = c[e]
                stop = ref + atr_mult * atr[e]
            end = min(ts_row, lastrow) if intraday else min(ts_row, n - 1)
            for b in range(e, end + 1):
                if b > e:
                    if side > 0:
                        ref = max(ref, c[b])
                        stop = max(stop, ref - atr_mult * atr[b])
                    else:
                        ref = min(ref, c[b])
                        stop = min(stop, ref + atr_mult * atr[b])
                if np.isnan(stop):
                    continue
                if side > 0 and l[b] <= stop:
                    xr, px = b, (stop if o[b] > stop else float(o[b]))
                    break
                if side < 0 and h[b] >= stop:
                    xr, px = b, (stop if o[b] < stop else float(o[b]))
                    break
            if xr is not None:
                day_final = int(day[xr])
                x_slot = int(slot[xr])
                fill_row = xr
        if xr is None:
            if exit_rule == "time_stop_or_reverse":
                end = min(ts_row, lastrow) if intraday else min(ts_row, n - 1)
                rev = rev_long if side > 0 else rev_short
                seg = np.flatnonzero(rev[e : end + 1])
                dec = e + int(seg[0]) if len(seg) else ts_row
            else:
                dec = ts_row
            x = dec + 1
            if intraday and x > lastrow:
                xr, px, at_close = lastrow, float(c[lastrow]), True
            elif x >= n:
                continue
            else:
                xr, px = dec, float(o[x])
            day_final = int(day[xr]) if at_close else int(day[x])
            x_slot = int(slot[xr]) if at_close else int(slot[x])
            fill_row = xr if at_close else x
        if bad_by_day is not None:
            d0 = int(day[e])
            if bad_by_day[d0 : day_final + 1].any():
                continue
        ret = (px - pe) / pe
        if not np.isfinite(ret) or abs(ret) > 0.3:
            continue
        for d, v in _marks(e, xr, day_final, pe, px, o, c, day, lrd):
            mt.append(tid)
            md.append(d)
            mv.append(v)
        KEEP.append(ci)
        E_.append(e)
        XR.append(xr)
        SIDE.append(side)
        PE.append(pe)
        PX.append(px)
        DAY_E.append(int(day[e]))
        DAY_X.append(day_final)
        SL_E.append(int(slot[e]))
        SL_X.append(x_slot)
        tid += 1
        blocked = fill_row
    return {
        "e": np.array(E_, np.int64),
        "xr": np.array(XR, np.int64),
        "side": np.array(SIDE, np.int8),
        "pe": np.array(PE),
        "px": np.array(PX),
        "day_e": np.array(DAY_E, np.int32),
        "day_x": np.array(DAY_X, np.int32),
        "slot_e": np.array(SL_E, np.int16),
        "slot_x": np.array(SL_X, np.int16),
        "keep": np.array(KEEP, np.int64),
        "m_tid": np.array(mt, np.int64),
        "m_day": np.array(md, np.int32),
        "m_val": np.array(mv),
    }


# ----------------------------------------------------------------------------- costs
def trade_costs(tr: dict, ctx: dict) -> dict[str, np.ndarray]:
    """Per-trade cost parts in bp of notional: entry/exit variable (scaled by the cost multiplier)
    and fixed (fees, borrow, not scaled). ``ctx['kind']`` is 'etf' or 'stock'."""
    side = tr["side"].astype(int)
    n = len(side)
    if n == 0:
        z = np.zeros(0)
        return {"var_e": z, "fix_e": z, "var_x": z, "fix_x": z}
    out = {}
    held_years = (
        (tr["day_x"] + tr["slot_x"] / float(NSLOT)) - (tr["day_e"] + tr["slot_e"] / float(NSLOT))
    ).clip(min=0) / 252.0
    for leg, price, dayk, slotk, buy in (
        ("e", tr["pe"], "day_e", "slot_e", side > 0),
        ("x", tr["px"], "day_x", "slot_x", side < 0),
    ):
        d = tr[dayk]
        sl = tr[slotk]
        if ctx["kind"] == "etf":
            raw = price * ctx["factor"][d]
            var = ctx["tick_cents"] * 50.0 / raw + E.SLIP_BP
            var = var + np.where(sl < E.OPEN_ADD_UNTIL_SLOT, E.OPEN_ADD_BP, 0.0)
            var = var + np.where(buy, 0.0, E.SEC_FEE_BP)
            fix = np.zeros(n)
        else:
            from open_composer.research.equity_book.costs import half_spread_bp, impact_bp

            price_pc = ctx["prior_close"][d]
            adv = ctx["adv"][d]
            vol = ctx["vol21"][d]
            year = master().year.to_numpy()[d]
            hs = np.empty(n)
            snap = np.where(sl < 15, 0, np.where(sl >= 375, 2, 1))
            if ctx.get("snap_override") == "open":
                snap = np.zeros(n, int)
            for k, name in enumerate(("open", "mid", "close")):
                m = snap == k
                if m.any():
                    hs[m] = half_spread_bp(price_pc[m], adv[m], vol[m], year[m], name)
            hs = np.where(np.isfinite(hs), hs, MISSING_HS_BP)
            imp = impact_bp(np.full(n, IMPACT_NOTIONAL), adv, vol)
            imp = np.where(np.isfinite(imp), imp, 0.0)
            var = hs + imp
            fix = np.full(n, STOCK_FEE_BP)
        out["var_" + leg] = np.asarray(var, float)
        out["fix_" + leg] = np.asarray(fix, float)
    borrow = np.where(side < 0, BORROW_BP_YEAR * held_years, 0.0)
    out["fix_x"] = out["fix_x"] + borrow
    return out


# ----------------------------------------------------------------------------- aggregation
class TradeBook:
    """Concatenated trades of a basket (per-trade arrays + unit-long marks), N capital slots."""

    def __init__(self, n_slots: int):
        self.n = n_slots
        self.parts: list[dict] = []

    def add(self, tr: dict, cost: dict, sym: str):
        if len(tr["side"]) == 0:
            return
        self.parts.append({**tr, **cost, "sym": np.full(len(tr["side"]), sym)})

    def finalize(self):
        if not self.parts:
            self.T = None
            return self
        off = 0
        mt = []
        for p in self.parts:
            mt.append(p["m_tid"] + off)
            off += len(p["side"])
        self.m_tid = np.concatenate(mt)
        self.m_day = np.concatenate([p["m_day"] for p in self.parts])
        self.m_val = np.concatenate([p["m_val"] for p in self.parts])
        keys = (
            "side",
            "pe",
            "px",
            "day_e",
            "day_x",
            "slot_e",
            "slot_x",
            "var_e",
            "fix_e",
            "var_x",
            "fix_x",
            "sym",
        )
        self.T = {k: np.concatenate([p[k] for p in self.parts]) for k in keys}
        self.parts = []
        return self

    def ntr(self) -> int:
        return 0 if self.T is None else len(self.T["side"])

    def daily(self, D: int, mult: float = 1.0, sign: np.ndarray | None = None):
        """gross[d], cost[d] (fractions of one unit of total capital), entries[d] (trade count)."""
        if self.T is None:
            z = np.zeros(D)
            return z, z.copy(), z.copy()
        s = self.T["side"].astype(float) if sign is None else sign
        gross = np.bincount(self.m_day, weights=s[self.m_tid] * self.m_val, minlength=D) / self.n
        T = self.T
        cv = np.bincount(T["day_e"], weights=T["var_e"], minlength=D) + np.bincount(
            T["day_x"], weights=T["var_x"], minlength=D
        )
        cf = np.bincount(T["day_e"], weights=T["fix_e"], minlength=D) + np.bincount(
            T["day_x"], weights=T["fix_x"], minlength=D
        )
        cost = (mult * cv + cf) / 1e4 / self.n
        ent = np.bincount(T["day_e"], minlength=D).astype(float)
        return gross, cost, ent


# ----------------------------------------------------------------------------- series per symbol
def load_rows(sym: str, kind: str, start: str | None = None) -> pd.DataFrame:
    cols = ["date", "minute", "open", "high", "low", "close", "volume"]
    if kind == "etf":
        flt = [("date", ">=", pd.Timestamp(start))] if start else None
        return pd.read_parquet(E.PANEL / f"{sym}.parquet", columns=cols, filters=flt)
    files = sorted((D_MIN / sym).glob("*.parquet"))
    if not files:
        return pd.DataFrame(columns=cols)
    return pd.concat([pd.read_parquet(f, columns=cols) for f in files], ignore_index=True)


def build_series(
    sym: str, kind: str, period: str, phase: int = 0, force: bool = False, start: str | None = None
) -> dict | None:
    """Bars + signals of one symbol/period/phase, cached under data/features/t15_work/d_sig/."""
    path = SIG_DIR / f"{sym}_{period}_ph{phase}.npz"
    if path.exists() and not force and start is None:
        z = np.load(path)
        return {k: z[k] for k in z.files}
    rows = load_rows(sym, kind, start)
    if rows.empty:
        return None
    rows = clean_rows(rows)
    mdates = master()
    dcl_raw = np.full(len(mdates), np.nan)
    g = rows.groupby("date")["close"].last()
    ix = mdates.get_indexer(g.index)
    dcl_raw[ix[ix >= 0]] = g.to_numpy()[ix >= 0]
    rows, trig = split_adjust(rows)
    dcl_adj = np.full(len(mdates), np.nan)
    g2 = rows.groupby("date")["close"].last()
    ix2 = mdates.get_indexer(g2.index)
    dcl_adj[ix2[ix2 >= 0]] = g2.to_numpy()[ix2 >= 0]
    bars = rows if period == "1m" else to_hourly(rows, phase)
    di = mdates.get_indexer(pd.DatetimeIndex(bars["date"]))
    bars = bars[di >= 0].reset_index(drop=True)
    di = di[di >= 0]
    o = bars["open"].to_numpy("float64")
    h = bars["high"].to_numpy("float64")
    l = bars["low"].to_numpy("float64")
    c = bars["close"].to_numpy("float64")
    ind = run_indicator(o, h, l, c, bars["volume"].to_numpy("float64"))
    S = {
        "day": di.astype(np.int32),
        "slot": (bars["minute"].to_numpy("int64") - 570).astype(np.int16),
        "o": o,
        "h": h,
        "l": l,
        "c": c,
        "atr": ind["atr"],
        "trig": mdates.get_indexer(trig).astype(np.int32),
        "dcl_raw": dcl_raw,
        "dcl_adj": dcl_adj,
    }
    for f in FLAGS:
        S[f] = ind[f]
    if start is None:
        SIG_DIR.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp.npz")
        np.savez_compressed(tmp, **S)
        tmp.replace(path)
    return S


def bad_by_day(S: dict) -> np.ndarray:
    b = np.zeros(len(master()), bool)
    t = S["trig"]
    b[t[t >= 0]] = True
    return b


def etf_ctx(sym: str, S: dict) -> dict:
    raw = pd.read_parquet(E.RAW_DAILY / f"{sym}.parquet")
    rc = pd.Series(
        raw["close"].to_numpy(),
        index=pd.DatetimeIndex(
            pd.to_datetime(raw["timestamp"], utc=True).dt.tz_convert(None)
        ).normalize(),
    )
    rc = rc[~rc.index.duplicated()].reindex(master())
    fac = (rc.to_numpy() / S["dcl_adj"]).astype(float)
    fac = np.where(np.isfinite(fac) & (fac > 0), fac, np.nan)
    fac = pd.Series(fac).ffill().bfill().to_numpy()
    return {"kind": "etf", "tick_cents": E.TICK_CENTS[sym], "factor": fac}


def stock_ctx(sym: str, S: dict, universe: pd.DataFrame, topk: int = 50) -> tuple[dict, np.ndarray]:
    """Cost-model inputs by master day and the point-in-time pool flag (rank_in_pool <= 50)."""
    mdates = master()
    u = universe[universe["symbol"] == sym].set_index("month")
    months = mdates.strftime("%Y-%m")
    adv = (
        months.map(u["dollar_adv"]).to_numpy(dtype=float)
        if len(u)
        else np.full(len(mdates), np.nan)
    )
    rank = (
        months.map(u["rank_in_pool"]).to_numpy(dtype=float)
        if len(u)
        else np.full(len(mdates), np.nan)
    )
    pool = np.isfinite(rank) & (rank <= topk)
    dcl_raw = pd.Series(S["dcl_raw"])
    prior_close = dcl_raw.ffill().shift(1).to_numpy()
    ret = pd.Series(S["dcl_adj"]).pct_change(fill_method=None)
    vol21 = ret.rolling(21, min_periods=15).std().shift(1).to_numpy()
    return {"kind": "stock", "prior_close": prior_close, "adv": adv, "vol21": vol21}, pool
