# ruff: noqa: E501
"""T-20261006-18 library batch-1, ETF / calendar rules (new rules only).

``scripts/t18_lane.py`` runs these together with the existing opex-week and pre-holiday batches
(imported unchanged) under the screen-lane contract (10/20 bp, next-open fill, excess over BIL,
vol-matched S3 control).  Every rule is long-only (the lane protocol): the original short legs are
dropped and the remainder sits in SHY.  Deviations from the QuantConnect originals are listed per
rule; none of them looks at a price after ``asof``.

Primary member per first-batch id (frozen before any result): TOM_SPY_H4, DYNBRK_SPY, ICHI_XLE,
CAPM_TOP2, JANBAR_SPY, OILEQ_USO.  The other members of a family are sensitivity and are counted as
trials.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import screen_lane as lane  # noqa: E402

EB = ROOT / "data/research/equity_book"
_CACHE: dict[tuple, object] = {}


def _cached(key: tuple, fn: Callable[[], object]):
    if key not in _CACHE:
        _CACHE[key] = fn()
    return _CACHE[key]


def month_end_dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    s = pd.Series(index, index=index)
    return list(s.groupby([index.year, index.month]).max())


# ---------------------------------------------------------------------------
# turn of the month
# ---------------------------------------------------------------------------
def tom_entries(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """Signal at the close of the session before the last session of a month (fill at the open of the
    last session)."""
    me = month_end_dates(index)
    pos = {d: i for i, d in enumerate(index)}
    return [index[pos[d] - 1] for d in me if pos[d] >= 1]


def tom_exits(index: pd.DatetimeIndex, k: int) -> list[pd.Timestamp]:
    """Signal at the close of the k-th session of the next month (fill at the next open)."""
    s = pd.Series(np.arange(len(index)), index=index)
    out = []
    for (y, m), g in s.groupby([index.year, index.month]):
        if len(g) >= k and (y, m) != (index[0].year, index[0].month):
            out.append(index[int(g.iloc[k - 1])])
    return out


def _tom(sym: str, k: int) -> lane.ScreenCandidate:
    def w(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if sym not in close.columns:
            return {}
        ent = _cached(
            ("tom_ent", lane.frame_key(close.index)), lambda: set(tom_entries(close.index))
        )
        return {sym: 1.0} if asof in ent else {}

    def dates(index: pd.DatetimeIndex) -> list[pd.Timestamp]:
        return sorted(set(tom_entries(index)) | set(tom_exits(index, k)))

    return lane.ScreenCandidate(
        id=f"TOM_{sym}_H{k}",
        name=f"Turn of the month {sym}: last session to session {k} of the next month",
        source_card="qc_turn_of_the_month_in_equity_indexes",
        universe=(sym,),
        freq="D",
        weights_fn=w,
        signal_dates_fn=dates,
    )


# ---------------------------------------------------------------------------
# Dynamic Breakout II (long only, ETF closes; QC: forex, long and short)
# ---------------------------------------------------------------------------
def dynbrk_position(close: pd.Series) -> pd.Series:
    """1 after a long entry until the exit, else 0.  Forward recursion only: value at t uses closes <= t.

    lookback N starts at 20, each day N = round(N * (1 + dvol)), dvol = (sd30_t - sd30_{t-1}) / sd30_t, clipped
    to [20, 60].  Long entry: close_t above the upper band (EMA_N + 2 sd_N) and above the highest close of the
    previous N sessions.  Exit: close_t below the N-session simple average."""
    c = close.to_numpy("float64")
    n = len(c)
    sd30 = pd.Series(c).rolling(30).std().to_numpy()
    pos = np.zeros(n)
    N = 20
    held = 0.0
    for t in range(n):
        if t > 0 and np.isfinite(sd30[t]) and np.isfinite(sd30[t - 1]) and sd30[t] > 0:
            d = (sd30[t] - sd30[t - 1]) / sd30[t]
            N = int(min(60, max(20, round(N * (1.0 + d)))))
        if t >= N + 1 and np.isfinite(c[t - N : t + 1]).all():
            win = c[t - N + 1 : t + 1]
            sma = win.mean()
            ema = pd.Series(c[max(0, t - 3 * N) : t + 1]).ewm(span=N, adjust=False).mean().iloc[-1]
            upper = ema + 2.0 * win.std(ddof=1)
            prev_high = c[t - N : t].max()
            if held == 0.0 and c[t] > upper and c[t] > prev_high:
                held = 1.0
            elif held == 1.0 and c[t] < sma:
                held = 0.0
        pos[t] = held
    return pd.Series(pos, index=close.index)


def _dynbrk(sym: str) -> lane.ScreenCandidate:
    def w(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if sym not in close.columns:
            return {}
        p = _cached(
            ("dynbrk", lane.frame_key(close), sym), lambda: dynbrk_position(close[sym].dropna())
        )
        v = p.get(asof, 0.0)
        return {sym: 1.0} if v > 0 else {}

    return lane.ScreenCandidate(
        id=f"DYNBRK_{sym}",
        name=f"Dynamic Breakout II long-only on {sym}",
        source_card="qc_the_dynamic_breakout_ii_strategy",
        universe=(sym,),
        freq="D",
        weights_fn=w,
    )


# ---------------------------------------------------------------------------
# Ichimoku (long only, energy ETFs; QC: ten largest energy stocks, long and short)
# ---------------------------------------------------------------------------
def ichimoku_position(close: pd.Series) -> pd.Series:
    """Close-only Ichimoku (9, 26, 52, shift 26): lines from closes.  Chikou span at t is close_t drawn at t-26, so
    the test compares close_t with the cloud displayed at t-26 (spans computed at t-52).  Long after the Chikou
    crosses from inside/below to above the cloud, cash after it crosses from inside/above to below."""
    c = close.to_numpy("float64")
    s = pd.Series(c)
    tenkan = (s.rolling(9).max() + s.rolling(9).min()) / 2
    kijun = (s.rolling(26).max() + s.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((s.rolling(52).max() + s.rolling(52).min()) / 2).shift(26)
    top = pd.concat([span_a, span_b], axis=1).max(axis=1)
    bot = pd.concat([span_a, span_b], axis=1).min(axis=1)
    top_d, bot_d = top.shift(26).to_numpy(), bot.shift(26).to_numpy()  # cloud displayed at t-26
    pos = np.zeros(len(c))
    held = 0.0
    for t in range(len(c)):
        if np.isfinite(top_d[t]) and np.isfinite(top_d[t - 1] if t else np.nan):
            above = c[t] > top_d[t]
            was_above = c[t - 1] > top_d[t - 1]
            below = c[t] < bot_d[t]
            was_below = c[t - 1] < bot_d[t - 1]
            if above and not was_above:
                held = 1.0
            elif below and not was_below:
                held = 0.0
        pos[t] = held
    return pd.Series(pos, index=close.index)


def _ichi(sym: str) -> lane.ScreenCandidate:
    def w(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if sym not in close.columns:
            return {}
        p = _cached(
            ("ichi", lane.frame_key(close), sym), lambda: ichimoku_position(close[sym].dropna())
        )
        return {sym: 1.0} if p.get(asof, 0.0) > 0 else {}

    return lane.ScreenCandidate(
        id=f"ICHI_{sym}",
        name=f"Ichimoku chikou/cloud long-only on {sym}",
        source_card="qc_ichimoku_clouds_in_the_energy_sector",
        universe=(sym,),
        freq="D",
        weights_fn=w,
    )


# ---------------------------------------------------------------------------
# CAPM alpha ranking on the 30 most liquid names (QC: Dow 30, top two by 21-day alpha vs SPY)
# ---------------------------------------------------------------------------
def top30_by_date() -> dict[pd.Timestamp, list[str]]:
    def build():
        out: dict[pd.Timestamp, list[str]] = {}
        for f in sorted((EB / "panel").glob("20*.parquet")):
            df = pd.read_parquet(f, columns=["trade_date", "symbol", "adv_rank"])
            df = df[df["adv_rank"] <= 30]
            for d, g in df.groupby("trade_date"):
                out[pd.Timestamp(d)] = sorted(g["symbol"])
        return out

    return _cached(("top30",), build)  # type: ignore[return-value]


def capm_universe() -> tuple[str, ...]:
    syms: set[str] = set()
    for v in top30_by_date().values():
        syms |= set(v)
    return tuple(sorted(syms))


def _capm(top_n: int) -> lane.ScreenCandidate:
    def w(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        members = [s for s in top30_by_date().get(asof, []) if s in close.columns]
        if "SPY" not in close.columns or len(members) < top_n:
            return {}
        hist = close.loc[:asof].iloc[-22:]
        ret = hist.pct_change().iloc[1:]
        if len(ret) < 21:
            return {}
        x = ret["SPY"].to_numpy()
        alphas: dict[str, float] = {}
        for s in members:
            y = ret[s].to_numpy()
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() < 15:
                continue
            b = np.cov(x[ok], y[ok], ddof=1)[0, 1] / np.var(x[ok], ddof=1)
            alphas[s] = float(y[ok].mean() - b * x[ok].mean())
        top = sorted(alphas, key=lambda k: (-alphas[k], k))[:top_n]
        return {s: 1.0 / top_n for s in top} if len(top) == top_n else {}

    return lane.ScreenCandidate(
        id=f"CAPM_TOP{top_n}",
        name=f"CAPM alpha ranking, 30 most liquid names, long top {top_n}, monthly",
        source_card="qc_capm_alpha_ranking_strategy_on_dow_30_companies",
        universe=("SPY", *capm_universe()),
        freq="M",
        weights_fn=w,
    )


# ---------------------------------------------------------------------------
# January barometer
# ---------------------------------------------------------------------------
def _janbar(sym: str) -> lane.ScreenCandidate:
    def w(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if sym not in close.columns:
            return {}
        c = close[sym].loc[:asof].dropna()
        if asof.month == 12:
            return {sym: 1.0}
        y = asof.year
        jan = c[(c.index.year == y) & (c.index.month == 1)]
        prev = c[(c.index.year == y - 1) & (c.index.month == 12)]
        if jan.empty or prev.empty:
            return {}
        if asof.month == 1 and asof != jan.index[-1]:
            return {}
        # January return known once January has closed; in January itself the signal fires at the Dec close
        ret = float(jan.iloc[-1] / prev.iloc[-1] - 1.0)
        return {sym: 1.0} if ret > 0 else {}

    return lane.ScreenCandidate(
        id=f"JANBAR_{sym}",
        name=f"January barometer on {sym}: long in January, rest of year only if January > 0",
        source_card="qc_january_barometer",
        universe=(sym,),
        freq="D",
        weights_fn=w,
        signal_dates_fn=month_end_dates,
    )


# ---------------------------------------------------------------------------
# Crude oil predicts equity returns (QC: OPEC basket; here USO / DBO ETF as the oil series)
# ---------------------------------------------------------------------------
def _oileq(oil: str) -> lane.ScreenCandidate:
    def w(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if oil not in close.columns or "SPY" not in close.columns or "BIL" not in close.columns:
            return {}
        me = [d for d in month_end_dates(close.loc[:asof].index)]
        m = close[["SPY", oil, "BIL"]].loc[me].dropna()
        r = m.pct_change().dropna()
        if len(r) < 25:
            return {}
        r = r.iloc[-25:]
        y = r["SPY"].to_numpy()[1:]  # SPY return of month t
        x = r[oil].to_numpy()[:-1]  # oil return of month t-1
        xm, ym = x.mean(), y.mean()
        vx = ((x - xm) ** 2).sum()
        if vx <= 0:
            return {}
        a1 = ((x - xm) * (y - ym)).sum() / vx
        a0 = ym - a1 * xm
        pred = a0 + a1 * float(r[oil].iloc[-1])
        rf_m = float(r["BIL"].iloc[-1])
        return {"SPY": 1.0} if pred > rf_m else {}

    return lane.ScreenCandidate(
        id=f"OILEQ_{oil}",
        name=f"Oil ({oil}) predicts SPY: 24-month regression, hold SPY when forecast > T-bill",
        source_card="qc_can_crude_oil_predict_equity_returns",
        universe=("SPY", oil, "BIL"),
        freq="D",
        weights_fn=w,
        signal_dates_fn=month_end_dates,
    )


CANDIDATES: list[lane.ScreenCandidate] = []
for _sym in ("SPY", "QQQ", "IWM", "DIA"):
    for _k in (3, 4):
        CANDIDATES.append(_tom(_sym, _k))
for _sym in ("SPY", "QQQ", "IWM", "DIA", "GLD", "TLT"):
    CANDIDATES.append(_dynbrk(_sym))
for _sym in ("XLE", "VDE", "XOP", "OIH"):
    CANDIDATES.append(_ichi(_sym))
for _n in (2, 3):
    CANDIDATES.append(_capm(_n))
for _sym in ("SPY", "QQQ", "IWM"):
    CANDIDATES.append(_janbar(_sym))
for _oil in ("USO", "DBO"):
    CANDIDATES.append(_oileq(_oil))

GROUPS: dict[str, dict[str, object]] = {
    "qc-option-expiration-week-effect": {
        "primary": "OPEX_SPY_WEEK",
        "prefix": ("OPEX_", "PLACEBO_W"),
    },
    "qc-pre-holiday-effect": {"primary": "PREHOL_SPY_H1", "prefix": ("PREHOL_",)},
    "qc-turn-of-the-month-in-equity-indexes": {"primary": "TOM_SPY_H4", "prefix": ("TOM_",)},
    "qc-the-dynamic-breakout-ii-strategy": {"primary": "DYNBRK_SPY", "prefix": ("DYNBRK_",)},
    "qc-ichimoku-clouds-in-the-energy-sector": {"primary": "ICHI_XLE", "prefix": ("ICHI_",)},
    "qc-capm-alpha-ranking-strategy-on-dow-30-companies": {
        "primary": "CAPM_TOP2",
        "prefix": ("CAPM_",),
    },
    "qc-january-barometer": {"primary": "JANBAR_SPY", "prefix": ("JANBAR_",)},
    "qc-can-crude-oil-predict-equity-returns": {"primary": "OILEQ_USO", "prefix": ("OILEQ_",)},
}
assert len({c.id for c in CANDIDATES}) == len(CANDIDATES) == 8 + 6 + 4 + 2 + 3 + 2
