"""T-20261006-15 engines: ETF minute panels -> noise-band (A) and market-intraday-momentum (B).

Conventions (hypotheses.md section 0): signal on the close of bar t, fill at the open of bar t+1,
flat at the close of the last bar of the session. All arrays are sessions x 390 minute slots
(slot 0 = 09:30 bar).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/features/t15_minute"
RAW_DAILY = ROOT / "data/features/t15_raw_daily"
NSLOT = 390
RECENT_START = pd.Timestamp("2024-01-08")
DIAG_END = pd.Timestamp("2023-12-29")
PHASES = [
    ("P01", "2024-01-08", "2024-07-16"),
    ("P02", "2024-07-17", "2024-08-05"),
    ("P03", "2024-08-06", "2024-09-19"),
    ("P04", "2024-09-20", "2025-02-19"),
    ("P05", "2025-02-20", "2025-04-08"),
    ("P06", "2025-04-09", "2025-06-26"),
    ("P07", "2025-06-27", "2026-01-27"),
    ("P08", "2026-01-28", "2026-03-30"),
    ("P09", "2026-03-31", "2026-04-14"),
    ("P10", "2026-04-15", "2026-06-30"),
    ("P11", "2026-07-01", "2099-12-31"),
]
# quoted tick in cents used for the half-spread prior (unmeasured; hypotheses.md section 0)
TICK_CENTS = {
    "SPY": 1, "QQQ": 1, "IWM": 1, "DIA": 1, "XLK": 1, "XLF": 1, "XLE": 1, "XLV": 1, "XLY": 1,
    "XLP": 1, "XLI": 1, "XLU": 1, "TQQQ": 1, "XLB": 2, "XLRE": 2, "XLC": 2, "SPXL": 2,
}  # fmt: skip
SLIP_BP = 0.02
SEC_FEE_BP = 0.206
OPEN_ADD_BP = 1.0
OPEN_ADD_UNTIL_SLOT = 15  # fills at slots 0..14 (before 09:45)
COST_MULTS = (0.5, 1.0, 2.0, 4.0)


class Panel:
    """One symbol's minute matrices."""

    def __init__(self, symbol: str, frame: pd.DataFrame | None = None, start: str | None = None):
        """``frame`` (IEX check): raw-price minute frame with date, minute, OHLCV, vwap;
        the raw daily
        file is then not used and the factor is 1."""
        if frame is None:
            flt = [("date", ">=", pd.Timestamp(start))] if start else None
            d = pd.read_parquet(PANEL / f"{symbol}.parquet", filters=flt)
        else:
            d = frame
        self.symbol = symbol
        dates = np.sort(d["date"].unique())
        self.dates = pd.DatetimeIndex(dates)
        di = np.searchsorted(dates, d["date"].to_numpy())
        mi = (d["minute"].to_numpy() - 570).astype(int)
        shape = (len(dates), NSLOT)
        self.o, self.h, self.l, self.c, self.v, self.vw = (np.full(shape, np.nan) for _ in range(6))
        self.o[di, mi] = d["open"].to_numpy()
        self.h[di, mi] = d["high"].to_numpy()
        self.l[di, mi] = d["low"].to_numpy()
        self.c[di, mi] = d["close"].to_numpy()
        self.v[di, mi] = d["volume"].to_numpy()
        self.vw[di, mi] = d["vwap"].to_numpy()
        # forward-fill gaps inside the session for close/vwap (no trade in the minute)
        for arr in (self.c, self.vw):
            f = pd.DataFrame(arr).ffill(axis=1)
            arr[:] = f.to_numpy()
        self.o = np.where(np.isfinite(self.o), self.o, self.c)
        # last valid slot per session
        valid = np.isfinite(self.c)
        self.last_slot = np.where(valid.any(1), NSLOT - 1 - np.argmax(valid[:, ::-1], axis=1), -1)
        self.first_slot = np.argmax(valid, axis=1)
        n = len(dates)
        ar = np.arange(n)
        self.day_open = self.o[ar, self.first_slot]
        self.day_close = self.c[ar, np.maximum(self.last_slot, 0)]
        # unadjusted prices (hypotheses amendment 1): the minute archive is dividend-adjusted, the
        # SIP raw daily close gives the per-day factor raw/adjusted; intraday ratios are unchanged.
        if frame is None:
            raw = pd.read_parquet(RAW_DAILY / f"{symbol}.parquet")
            raw_close = pd.Series(
                raw["close"].to_numpy(),
                index=pd.DatetimeIndex(
                    pd.to_datetime(raw["timestamp"], utc=True).dt.tz_convert(None)
                ).normalize(),
            )
            raw_close = raw_close[~raw_close.index.duplicated()]
            rc = raw_close.reindex(self.dates).to_numpy()
        else:
            rc = self.day_close.copy()
        self.raw_close = rc
        fac = rc / self.day_close
        fac = np.where(np.isfinite(fac) & (fac > 0), fac, np.nan)
        self.factor = pd.Series(fac).ffill().bfill().to_numpy()
        prev_raw = np.concatenate([[np.nan], rc[:-1]])
        prev = prev_raw / self.factor  # previous raw close on today's adjusted scale
        gap = self.day_open / prev - 1.0
        # a split shows up as a huge overnight gap; anchor on the open then
        prev = np.where(np.abs(gap) > 0.25, np.nan, prev)
        self.prev_close = prev
        self.full_day = (self.last_slot == NSLOT - 1) & (self.first_slot == 0)
        dr = self.day_close / np.concatenate([[np.nan], self.day_close[:-1]]) - 1.0
        dr = np.where(np.abs(dr) > 0.25, np.nan, dr)
        self.daily_ret = dr
        # trailing 14-day std of daily returns known before the session
        s = pd.Series(dr).rolling(14, min_periods=10).std().shift(1)
        self.sigma_ret14 = s.to_numpy()


def half_spread_bp(symbol: str, price: np.ndarray) -> np.ndarray:
    return TICK_CENTS[symbol] * 50.0 / price


def side_cost_bp(
    symbol: str, price: np.ndarray, slot: np.ndarray | int, buy: np.ndarray
) -> np.ndarray:
    """Per-side cost in bp of notional at multiplier 1."""
    c = half_spread_bp(symbol, price) + SLIP_BP
    c = c + np.where(np.asarray(slot) < OPEN_ADD_UNTIL_SLOT, OPEN_ADD_BP, 0.0)
    return c + np.where(buy, 0.0, SEC_FEE_BP)


# ----------------------------------------------------------------------------- group A
def noise_sigma(p: Panel, lookback: int) -> np.ndarray:
    """sigma[d, m] = mean over previous `lookback` sessions of |close(m)/open(day) - 1|."""
    move = np.abs(p.c / p.day_open[:, None] - 1.0)
    move[np.abs(move) > 0.3] = np.nan
    df = pd.DataFrame(move)
    return df.rolling(lookback, min_periods=lookback).mean().shift(1).to_numpy()


def check_slots(interval: int, phase: int = 0) -> np.ndarray:
    """Signal slots m (close of bar m): (m + 1 - phase) % interval == 0, next bar exists.

    ``phase`` shifts the whole check grid by that many minutes (robustness d item)."""
    m = np.arange(NSLOT - 1)
    base = m[((m + 1) % interval == 0) & (m + 1 >= interval)]
    m = base + phase
    return m[m < NSLOT - 1]


def a_position_paths(
    p: Panel, sigma: np.ndarray, interval: int, mults, stops, shift: int = 0, phase: int = 0
) -> dict[tuple[float, str], np.ndarray]:
    """Return {(mult, stop): pos[d, j]} the position held after check j (fills at bar m_j + 1)."""
    ms = check_slots(interval, phase)
    px = p.c[:, ms]
    vw = p.vw[:, ms]
    sg = sigma[:, ms - shift] if shift else sigma[:, ms]
    hi_anchor = np.fmax(p.day_open, p.prev_close)
    lo_anchor = np.fmin(p.day_open, p.prev_close)
    hi_anchor = np.where(np.isfinite(p.prev_close), hi_anchor, p.day_open)
    lo_anchor = np.where(np.isfinite(p.prev_close), lo_anchor, p.day_open)
    nd, nj = px.shape
    out = {}
    live = np.isfinite(px) & np.isfinite(sg) & (ms[None, :] + 1 <= p.last_slot[:, None])
    for mult in mults:
        ub = hi_anchor[:, None] * (1.0 + mult * sg)
        lb = lo_anchor[:, None] * (1.0 - mult * sg)
        above, below = px > ub, px < lb
        for stop in stops:
            if stop == "band":
                lh, sh = above, below
                le, se = above, below
            elif stop == "vwap":
                lh, sh = px > vw, px < vw
                le, se = above & lh, below & sh
            elif stop == "both":
                lh, sh = px > np.fmax(ub, vw), px < np.fmin(lb, vw)
                le, se = lh, sh
            elif stop == "opp":  # paper base: exit only on the opposite boundary
                lh, sh = ~below, ~above
                le, se = above, below
            else:
                raise ValueError(stop)
            pos = np.zeros(nd)
            P = np.zeros((nd, nj))
            for j in range(nj):
                lv = live[:, j]
                new = pos.copy()
                flat = pos == 0
                new = np.where(flat & le[:, j], 1.0, new)
                new = np.where(flat & se[:, j], -1.0, new)
                lng = pos > 0
                new = np.where(lng & ~lh[:, j], np.where(se[:, j], -1.0, 0.0), new)
                sht = pos < 0
                new = np.where(sht & ~sh[:, j], np.where(le[:, j], 1.0, 0.0), new)
                new = np.where(lv, new, pos)
                P[:, j] = new
                pos = new
            out[(mult, stop)] = P
    return out


def a_daily(p: Panel, interval: int, P: np.ndarray, phase: int = 0, detail: bool = False):
    """Gross and cost (bp-free fractions at multiplier 1) per session, trades per session.

    Returns gross[d] (unlevered fraction of capital), cost[d] (fraction, multiplier 1),
    entries[d] (number of position openings incl. flips).
    """
    ms = check_slots(interval, phase)
    nd, nj = P.shape
    fill_slot = ms + 1
    fills = p.o[:, fill_slot]  # open of the next bar
    idx = np.arange(nd)
    last_close = p.day_close
    # position held from fill j until fill j+1 (or end of day)
    X = np.concatenate([fills, last_close[:, None]], axis=1)  # price at the start of segment j
    # segment returns
    with np.errstate(invalid="ignore", divide="ignore"):
        seg = X[:, 1:] / X[:, :-1] - 1.0
    seg = np.where(np.isfinite(seg), seg, 0.0)
    gross = np.sum(P * seg, axis=1)
    # turnover: change at each fill; final close-out to flat
    prevP = np.concatenate([np.zeros((nd, 1)), P[:, :-1]], axis=1)
    dpos = P - prevP
    px_fill = np.where(np.isfinite(fills), fills, last_close[:, None]) * p.factor[:, None]
    buy = dpos > 0
    c_bp = side_cost_bp(p.symbol, px_fill, fill_slot[None, :], buy)
    cost = np.sum(np.abs(dpos) * c_bp, axis=1)
    # closing at the end of the session
    end_pos = P[:, -1]
    end_buy = end_pos < 0
    end_slot = np.maximum(p.last_slot, 0)
    c_end = side_cost_bp(p.symbol, last_close * p.factor, end_slot, end_buy)
    cost = cost + np.abs(end_pos) * c_end
    entries = np.sum((prevP == 0) & (P != 0), axis=1) + np.sum(
        (prevP != 0) & (P != 0) & (np.sign(P) != np.sign(prevP)), axis=1
    )
    ok = np.isfinite(last_close) & np.isfinite(p.day_open)
    gross = np.where(ok, gross, np.nan)
    if detail:
        segg = P * seg  # per-segment gross
        start = (P != 0) & ((prevP == 0) | (np.sign(P) != np.sign(prevP)))
        tid = np.cumsum(start, axis=1) - 1
        tid = np.where(P != 0, tid, -1)
        return gross, cost / 1e4, entries.astype(float), segg, tid
    return gross, cost / 1e4, entries.astype(float), idx


def vol_target_lev(p: Panel) -> np.ndarray:
    lev = np.minimum(4.0, 0.02 / p.sigma_ret14)
    return np.where(np.isfinite(lev), lev, 1.0)


# ----------------------------------------------------------------------------- group B
def b_features(p: Panel) -> dict[str, np.ndarray]:
    r1_intra = p.c[:, 29] / p.o[:, 0] - 1.0
    r1_over = p.c[:, 29] / p.prev_close - 1.0
    r1_over = np.where(np.isfinite(p.prev_close), r1_over, r1_intra)
    r12 = p.c[:, 359] / p.o[:, 330] - 1.0
    r13 = p.c[:, 389] / p.o[:, 360] - 1.0
    return {
        "r1_intraday": r1_intra,
        "r1_overnight": r1_over,
        "r1_plus_r12": r1_intra + r12,
        "r12": r12,
        "r13": r13,
    }


def b_daily(p: Panel, feats: dict, pred: str, thresh: float):
    x = feats[pred]
    sd = pd.Series(x).rolling(60, min_periods=40).std().shift(1).to_numpy()
    pos = np.where(np.abs(x) > thresh * sd, np.sign(x), 0.0)
    pos = np.where(np.isfinite(x) & np.isfinite(sd) & p.full_day, pos, 0.0)
    entry = p.o[:, 360]
    exitp = p.c[:, 389]
    gross = pos * (exitp / entry - 1.0)
    buy_in = pos > 0
    c_in = side_cost_bp(p.symbol, entry * p.factor, 360, buy_in)
    c_out = side_cost_bp(p.symbol, exitp * p.factor, 389, ~buy_in)
    cost = np.abs(pos) * (c_in + c_out) / 1e4
    gross = np.where(np.isfinite(gross), gross, 0.0)
    cost = np.where(np.isfinite(cost), cost, 0.0)
    return gross, cost, np.abs(pos), pos


# ----------------------------------------------------------------------------- stats
def window_masks(dates: pd.DatetimeIndex) -> dict[str, np.ndarray]:
    m = {
        "recent": dates >= RECENT_START,
        "diag_2016_2023": dates <= DIAG_END,
        "all": np.ones(len(dates), bool),
    }
    for name, a, b in PHASES:
        m[name] = (dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b))
    return m


def sharpe(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    if len(x) < 20 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * np.sqrt(252.0))


def net_series(gross, cost, lev, mult):
    return lev * (gross - mult * cost)
