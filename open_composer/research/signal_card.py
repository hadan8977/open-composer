"""Signal card: one standard health check for any per-stock signal.

``docs/plan-research-coverage-2026-09-23.zh.md`` section 6.1. A single stock
signal is not held to the strategy bar (G1, 50%/yr). The card asks whether it
predicts returns, whether that holds across years and liquidity tiers,
whether it survives costs in a long-only book we could trade, and whether it
beats placebos. Signals that pass go into the signal library; only
combinations of them face the strategy gates.

A signal is a table ``symbol, trade_date, value`` whose value is known by the
close of ``trade_date``; the caller owns point-in-time alignment (``--lag``
adds sessions of delay). Every statistic enters at the next session's open.

Universe: the point-in-time broad universe (``data/features/universe_broad``:
common stocks, funds and ETFs excluded, close >= $5), top ``top_n`` by dollar
ADV as ranked at the latest month-end on or before the formation date. Tiers
by that rank: 1-500, 501-1500, 1501-``top_n``.

Two modes:

``rank``
    Dense signals, ranked across the universe every day: rank IC by horizon,
    year and tier; decile excess returns; a long-only top-K book held h
    sessions (overlapping daily cohorts); decay; overlap with standard
    controls; placebos (the signal shuffled across stocks within each day;
    the signal a year stale).
``event``
    Sparse events (value present, and >= ``threshold`` when given): mean
    excess return after the event by horizon; a calendar-time book holding
    every event stock for h sessions, measured against the universe on the
    days it is invested; placebos with every event moved to a random session
    of the same stock within half a year.

Returns run open to open; a missing open (halt, delisting) earns zero from
then on, which flatters stocks that die, so the $5 floor matters. Excess is
against the universe equal weight. Costs: 10 and 20 bp per side on sum|dw|.

    uv run python -m open_composer.research.signal_card --name mom_12_1 \\
        --source data/features/daily_broad --column momentum_252_21 --mode rank
"""

from __future__ import annotations

import argparse
import json
import math
import time
import warnings
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from open_composer.research.features.price_hygiene import sanitize_price_matrices

ROOT = Path(__file__).resolve().parents[2]
FEATURES = ROOT / "data" / "features"
OUT_DIR = ROOT / "reports" / "research" / "signal-cards"
HORIZONS = (1, 5, 20, 60)
DECAY = (1, 2, 3, 5, 10, 20, 40, 60)
TIER_EDGES = ((1, 500), (501, 1500), (1501, None))
CONTROLS = {
    "momentum_12_1": "momentum_252_21",
    "reversal_5d": "ret_5",
    "size_dollar_adv_63": "dollar_adv_63",
    "volatility_63": "vol_63",
}
COSTS_BPS = (10.0, 20.0)
RECENT_START = "2024-01-01"
MIN_NAMES = 30
SHUFFLE_SEEDS = 10
EVENT_SEEDS = 20
EVENT_SHIFT = 126
STALE_SESSIONS = 252
TRADING_DAYS = 252


@dataclass
class Market:
    """Session x symbol matrices (float32, NaN where absent)."""

    dates: pd.DatetimeIndex
    symbols: pd.Index
    open_: np.ndarray
    close: np.ndarray
    adv_rank: np.ndarray  # rank at the latest month-end <= t; NaN outside the universe

    def member(self, tier: tuple[int, int | None] | None = None) -> np.ndarray:
        m = np.isfinite(self.adv_rank) & np.isfinite(self.close)
        if tier is not None:
            lo, hi = tier
            with np.errstate(invalid="ignore"):
                m &= self.adv_rank >= lo
                if hi is not None:
                    m &= self.adv_rank <= hi
        return m

    def next_open_returns(self) -> np.ndarray:
        """Return from the open of t to the open of t+1."""
        r = np.full_like(self.open_, np.nan)
        r[:-1] = self.open_[1:] / self.open_[:-1] - 1.0
        return r

    def forward_returns(self, h: int) -> np.ndarray:
        """Formation at the close of t: in at the open of t+1, out at the open of t+1+h."""
        o = self.open_
        f = np.full_like(o, np.nan)
        n = len(o) - 1 - h
        if n > 0:
            f[:n] = o[1 + h :] / o[1 : 1 + n] - 1.0
        return f


# --------------------------------------------------------------------------- data


def _connect(memory_limit: str) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"SET memory_limit='{memory_limit}'")
    con.execute("SET threads=2")
    return con


def load_market(top_n: int = 3000, memory_limit: str = "1200MB") -> Market:
    """Prices and PIT universe ranks for every stock ever in the top ``top_n``."""
    con = _connect(memory_limit)
    try:
        uni = con.execute(
            f"""
            SELECT month_end, symbol, adv_rank
            FROM read_parquet('{FEATURES}/universe_broad/*.parquet')
            WHERE adv_rank <= {int(top_n)} AND close >= 5
            """
        ).df()
        symbols = pd.Index(sorted(uni["symbol"].unique()))
        con.register("syms", pd.DataFrame({"symbol": symbols, "sid": np.arange(len(symbols))}))
        dates = pd.DatetimeIndex(
            con.execute(
                f"SELECT DISTINCT trade_date FROM read_parquet('{FEATURES}/daily_broad/*.parquet') "
                "ORDER BY 1"
            ).df()["trade_date"]
        )
        con.register("days", pd.DataFrame({"trade_date": dates, "tid": np.arange(len(dates))}))
        px = con.execute(
            f"""
            SELECT d.tid, s.sid, CAST(p.open AS FLOAT) AS open, CAST(p.close AS FLOAT) AS close
            FROM read_parquet('{FEATURES}/daily_broad/*.parquet') p
            JOIN syms s USING (symbol) JOIN days d USING (trade_date)
            """
        ).fetchnumpy()
    finally:
        con.close()
    shape = (len(dates), len(symbols))
    open_ = np.full(shape, np.nan, dtype=np.float32)
    close = np.full(shape, np.nan, dtype=np.float32)
    open_[px["tid"], px["sid"]] = px["open"]
    close[px["tid"], px["sid"]] = px["close"]
    del px
    c, o, _ = sanitize_price_matrices(
        pd.DataFrame(close, index=dates, columns=symbols),
        pd.DataFrame(open_, index=dates, columns=symbols),
    )
    close = c.to_numpy(dtype=np.float32)
    open_ = o.to_numpy(dtype=np.float32)
    del c, o
    month_ends = pd.DatetimeIndex(sorted(pd.to_datetime(uni["month_end"].unique())))
    by_month = np.full((len(month_ends), len(symbols)), np.nan, dtype=np.float32)
    by_month[
        month_ends.get_indexer(pd.to_datetime(uni["month_end"])),
        symbols.get_indexer(uni["symbol"]),
    ] = uni["adv_rank"].to_numpy(dtype=np.float32)
    latest = month_ends.searchsorted(dates, side="right") - 1
    adv_rank = np.where(latest[:, None] >= 0, by_month[np.clip(latest, 0, None)], np.nan)
    return Market(dates, symbols, open_, close, adv_rank.astype(np.float32))


def load_signal(
    market: Market,
    *,
    source: str | None = None,
    column: str | None = None,
    where: str | None = None,
    sql: str | None = None,
    lag: int = 0,
    memory_limit: str = "800MB",
) -> np.ndarray:
    """The signal as a session x symbol matrix, delayed by ``lag`` sessions."""
    if sql is None:
        if not (source and column):
            raise ValueError("give --sql, or --source and --column")
        path = Path(source)
        glob = str(path / "*.parquet") if path.is_dir() else str(path)
        sql = (
            f"SELECT symbol, trade_date, CAST({column} AS DOUBLE) AS value "
            f"FROM read_parquet('{glob}', union_by_name=true)"
            + (f" WHERE {where}" if where else "")
        )
    con = _connect(memory_limit)
    try:
        con.register(
            "syms", pd.DataFrame({"symbol": market.symbols, "sid": np.arange(len(market.symbols))})
        )
        con.register(
            "days", pd.DataFrame({"trade_date": market.dates, "tid": np.arange(len(market.dates))})
        )
        got = con.execute(
            f"""
            SELECT d.tid, s.sid, CAST(q.value AS FLOAT) AS value
            FROM ({sql}) q
            JOIN syms s USING (symbol)
            JOIN days d ON d.trade_date = CAST(q.trade_date AS TIMESTAMP)
            WHERE q.value IS NOT NULL
            """
        ).fetchnumpy()
    finally:
        con.close()
    out = np.full(market.open_.shape, np.nan, dtype=np.float32)
    out[got["tid"], got["sid"]] = got["value"]
    return shift_rows(out, lag)


def shift_rows(x: np.ndarray, n: int) -> np.ndarray:
    """Row t takes row t-n (NaN for the first n rows)."""
    if n <= 0:
        return x
    out = np.full_like(x, np.nan)
    out[n:] = x[:-n]
    return out


# --------------------------------------------------------------------- statistics


def _row_ranks(x: np.ndarray, chunk: int = 512) -> np.ndarray:
    """Average ranks (1..n) within each row over the finite entries; NaN elsewhere.

    argsort-based: pandas ``rank(axis=1)`` takes ~16 s on a 2,700 x 6,300 panel,
    this about 2 s."""
    x = np.asarray(x, dtype=np.float32)
    T, N = x.shape
    out = np.full((T, N), np.nan, dtype=np.float32)
    pos = np.arange(N, dtype=np.int32)
    for lo in range(0, T, chunk):
        hi = min(T, lo + chunk)
        order = np.argsort(x[lo:hi], axis=1, kind="stable")  # NaN sorts last
        srt = np.take_along_axis(x[lo:hi], order, axis=1)
        start = np.ones(srt.shape, dtype=bool)
        start[:, 1:] = srt[:, 1:] != srt[:, :-1]
        first = np.maximum.accumulate(np.where(start, pos, 0), axis=1)
        end = np.ones(srt.shape, dtype=bool)
        end[:, :-1] = start[:, 1:]
        last = np.minimum.accumulate(np.where(end, pos, N - 1)[:, ::-1], axis=1)[:, ::-1]
        avg = (first + last).astype(np.float32) / 2.0 + 1.0
        avg[~np.isfinite(srt)] = np.nan
        np.put_along_axis(out[lo:hi], order, avg, axis=1)
    return out


def masked_ranks(x: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return _row_ranks(np.where(mask & np.isfinite(x), x, np.nan))


def rank_corr(ra: np.ndarray, rb: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Per-session Pearson correlation of two rank matrices over ``mask``."""
    m = mask & np.isfinite(ra) & np.isfinite(rb)
    n = m.sum(axis=1)
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        a = np.where(m, ra, np.nan)
        b = np.where(m, rb, np.nan)
        a -= np.nanmean(a, axis=1, keepdims=True)
        b -= np.nanmean(b, axis=1, keepdims=True)
        num = np.nansum(a * b, axis=1, dtype=np.float64)
        den = np.sqrt(
            np.nansum(a * a, axis=1, dtype=np.float64) * np.nansum(b * b, axis=1, dtype=np.float64)
        )
        return np.where((n >= MIN_NAMES) & (den > 0), num / den, np.nan)


def rank_ic(signal: np.ndarray, fwd: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Spearman correlation across stocks, one value per session (both ranked
    over the stocks where both are known)."""
    m = mask & np.isfinite(signal) & np.isfinite(fwd)
    return rank_corr(masked_ranks(signal, m), masked_ranks(fwd, m), m)


def ic_summary(ic: np.ndarray, dates: pd.DatetimeIndex, h: int) -> dict:
    s = pd.Series(ic, index=dates).dropna()
    if s.empty:
        return {"days": 0}
    sub = s.iloc[::h]
    t = float(sub.mean() / (sub.std(ddof=1) / math.sqrt(len(sub)))) if len(sub) > 2 else None
    recent = s[s.index >= RECENT_START]
    return {
        "mean": float(s.mean()),
        "t_nonoverlap": t,
        "hit": float((s > 0).mean()),
        "days": int(len(s)),
        "recent_mean": float(recent.mean()) if len(recent) else None,
        "by_year": {str(y): float(v) for y, v in s.groupby(s.index.year).mean().items()},
    }


def decile_excess(
    signal_ranks: np.ndarray, fwd: np.ndarray, mask: np.ndarray, bins: int = 10
) -> list:
    """Mean excess return (vs the cross-sectional mean) of each signal decile,
    deciles from ranks taken over the universe that day."""
    m = mask & np.isfinite(signal_ranks) & np.isfinite(fwd)
    n = (mask & np.isfinite(signal_ranks)).sum(axis=1, keepdims=True)
    m &= n >= MIN_NAMES
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        b = np.ceil(signal_ranks / n * bins)
        ex = fwd - np.nanmean(np.where(m, fwd, np.nan), axis=1, keepdims=True)
        out = []
        for k in range(1, bins + 1):
            sel = m & (b == k)
            cnt = sel.sum(axis=1)
            per_day = np.where(
                cnt > 0, np.where(sel, ex, 0.0).sum(axis=1) / np.maximum(cnt, 1), np.nan
            )
            out.append(float(np.nanmean(per_day)) if np.isfinite(per_day).any() else None)
    return out


# ------------------------------------------------------------------------- books


def topk_cohorts(signal: np.ndarray, eligible: np.ndarray, k: int, chunk: int = 256) -> np.ndarray:
    """1/k on the k highest-signal eligible stocks of each session (0 if too few)."""
    T, N = signal.shape
    out = np.zeros((T, N), dtype=np.float32)
    if k >= N:
        return out
    for lo in range(0, T, chunk):
        hi = min(T, lo + chunk)
        ok = eligible[lo:hi] & np.isfinite(signal[lo:hi])
        s = np.where(ok, signal[lo:hi], -np.inf)
        idx = np.argpartition(-s, k - 1, axis=1)[:, :k]
        rows = np.nonzero(ok.sum(axis=1) >= max(MIN_NAMES, 2 * k))[0]
        out[lo + rows[:, None], idx[rows]] = 1.0 / k
    return out


def hold(cohorts: np.ndarray, h: int, normalize: bool = False, block: int = 1024) -> np.ndarray:
    """Weights held during session s: the cohorts formed at s-1 .. s-h.

    Averaged (each cohort 1/h of the book) or, with ``normalize``, summed and
    rescaled to 1 (calendar-time: every active position equal weight)."""
    T, N = cohorts.shape
    out = np.zeros((T, N), dtype=np.float32)
    for lo in range(0, N, block):
        hi = min(N, lo + block)
        cs = np.cumsum(cohorts[:, lo:hi], axis=0, dtype=np.float64)
        held = np.zeros((T, hi - lo), dtype=np.float64)
        held[1:] = cs[:-1]
        if T > h + 1:
            held[h + 1 :] -= cs[: T - h - 1]
        out[:, lo:hi] = held if normalize else held / h
    if normalize:
        tot = out.sum(axis=1, keepdims=True)
        out = np.where(tot > 0, out / np.where(tot > 0, tot, 1.0), 0.0).astype(np.float32)
    return out


def book_returns(
    held: np.ndarray, ret: np.ndarray, cost_bps: float
) -> tuple[np.ndarray, np.ndarray]:
    r = np.where(np.isfinite(ret), ret, 0.0)
    gross = (held * r).sum(axis=1)
    turnover = np.abs(np.diff(held, axis=0, prepend=np.zeros((1, held.shape[1]), held.dtype))).sum(
        axis=1
    )
    return gross - turnover * cost_bps / 1e4, turnover


def equal_weight(eligible: np.ndarray, ret: np.ndarray) -> np.ndarray:
    """Universe equal weight: formed at the close of s-1, earns session s."""
    out = np.zeros(len(ret))
    e = eligible[:-1]
    r = np.where(np.isfinite(ret[1:]), ret[1:], 0.0)
    cnt = e.sum(axis=1)
    out[1:] = np.where(cnt > 0, np.where(e, r, 0.0).sum(axis=1) / np.maximum(cnt, 1), 0.0)
    return out


def perf(r: pd.Series) -> dict:
    r = r.dropna()
    if len(r) < 20:
        return {"days": int(len(r))}
    cum = (1.0 + r).cumprod()
    years = len(r) / TRADING_DAYS
    sd = r.std()
    return {
        "days": int(len(r)),
        "cagr": float(cum.iloc[-1] ** (1.0 / years) - 1.0) if cum.iloc[-1] > 0 else -1.0,
        "sharpe": float(r.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else None,
        "max_dd": float((cum / cum.cummax() - 1.0).min()),
    }


def excess_summary(
    net: pd.Series, bench: pd.Series, turnover: pd.Series, active: pd.Series
) -> dict:
    """Book vs the universe; excess counted only on sessions the book is invested."""
    ex = (net - bench).where(active, 0.0)
    out = {"book": perf(net), "bench": perf(bench)}
    sd = ex.std()
    out["excess_ann"] = float(ex.mean() * TRADING_DAYS)
    out["info_ratio"] = float(ex.mean() / sd * math.sqrt(TRADING_DAYS)) if sd > 0 else None
    years = len(turnover) / TRADING_DAYS
    out["turnover_yr"] = float(turnover.sum() / years) if years else None
    out["invested_share"] = float(active.mean())
    out["by_year"] = {str(y): float(v) for y, v in ex.groupby(ex.index.year).sum().items()}
    return out


def book_block(
    market: Market,
    held: np.ndarray,
    bench: np.ndarray,
    ret: np.ndarray,
    start: pd.Timestamp,
) -> dict:
    idx = market.dates
    active = pd.Series(held.sum(axis=1) > 0, index=idx)
    keep = idx >= start
    out = {}
    for bps in COSTS_BPS:
        net, turn = book_returns(held, ret, bps)
        s_net = pd.Series(net, index=idx)[keep]
        s_b = pd.Series(bench, index=idx)[keep]
        s_t = pd.Series(turn, index=idx)[keep]
        a = active[keep]
        tag = f"{int(bps)}bp"
        out[tag] = excess_summary(s_net, s_b, s_t, a)
        recent = s_net.index >= RECENT_START
        out[f"{tag}_recent"] = excess_summary(s_net[recent], s_b[recent], s_t[recent], a[recent])
    return out


# -------------------------------------------------------------------------- cards


def _first_date(mask: np.ndarray, dates: pd.DatetimeIndex) -> pd.Timestamp:
    rows = np.nonzero(mask.any(axis=1))[0]
    return dates[rows[0]] if len(rows) else dates[-1]


def _log(msg: str, t0: list[float]) -> None:
    now = time.monotonic()
    print(f"[signal-card] {msg} ({now - t0[0]:.0f}s)", flush=True)


def rank_card(
    market: Market,
    signal: np.ndarray,
    *,
    top_k: int = 30,
    primary: int = 20,
    direction: int = 1,
    controls: dict[str, np.ndarray] | None = None,
    seeds: int = SHUFFLE_SEEDS,
) -> dict:
    """Ranks are taken across the whole universe each day; tier ICs correlate
    those ranks within the tier (close to, not exactly, a within-tier Spearman)."""
    t0 = [time.monotonic()]
    sig = signal * direction
    member = market.member()
    tiers = {f"t{i + 1}": market.member(t) for i, t in enumerate(TIER_EDGES)}
    ret = market.next_open_returns()
    rs = masked_ranks(sig, member)
    rs_stale = masked_ranks(shift_rows(sig, STALE_SESSIONS), member)
    card: dict = {"coverage": _coverage(sig, member, market.dates)}
    start = _first_date(member & np.isfinite(sig), market.dates)
    bench_all = equal_weight(member, ret)
    ic, deciles, stale, placebo = {}, {}, {}, []
    for h in DECAY:
        fwd = market.forward_returns(h)
        rf = masked_ranks(fwd, member)
        series = rank_corr(rs, rf, member)
        if h not in HORIZONS:
            ic[f"h{h}"] = {"mean": float(np.nanmean(series)) if np.isfinite(series).any() else None}
            continue
        ic[f"h{h}"] = ic_summary(series, market.dates, h)
        ic[f"h{h}"]["by_tier"] = {
            name: ic_summary(rank_corr(rs, rf, m), market.dates, h).get("mean")
            for name, m in tiers.items()
        }
        deciles[f"h{h}"] = decile_excess(rs, fwd, member)
        stale[f"h{h}"] = ic_summary(rank_corr(rs_stale, rf, member), market.dates, h).get("mean")
        if h == primary:
            for seed in range(1, seeds + 1):
                shuffled = shuffle_within_rows(rs, member, np.random.default_rng(seed))
                pic = rank_corr(shuffled, rf, member)
                held = hold(topk_cohorts(shuffled, member, top_k), primary)
                blk = book_block(market, held, bench_all, ret, start)["10bp"]
                placebo.append(
                    {"seed": seed, "ic": float(np.nanmean(pic)), "excess_ann": blk["excess_ann"]}
                )
        _log(f"horizon {h}d", t0)
    card["ic"] = ic
    card["decay"] = {str(h): ic[f"h{h}"].get("mean") for h in DECAY}
    card["deciles"] = deciles
    books = {}
    for name, m in {"all": member, **tiers}.items():
        cohorts = topk_cohorts(sig, m, top_k)
        bench = bench_all if name == "all" else equal_weight(m, ret)
        books[name] = {
            f"h{h}": book_block(market, hold(cohorts, h), bench, ret, start) for h in (5, 20, 60)
        }
    card["book"] = books
    _log("books", t0)
    card["placebo"] = {"primary_horizon": primary, "shuffle": placebo, "stale_252": stale}
    card["controls"] = {}
    for name, ctrl in (controls or {}).items():
        corr = rank_corr(rs, masked_ranks(ctrl, member), member)
        card["controls"][name] = float(np.nanmean(corr)) if np.isfinite(corr).any() else None
    _log("controls", t0)
    card["flags"] = rank_flags(card, primary)
    return card


def shuffle_within_rows(
    signal: np.ndarray, mask: np.ndarray, rng: np.random.Generator
) -> np.ndarray:
    out = np.full_like(signal, np.nan)
    ok = mask & np.isfinite(signal)
    for t in range(len(signal)):
        cols = np.nonzero(ok[t])[0]
        if len(cols):
            out[t, cols] = rng.permutation(signal[t, cols])
    return out


def rank_flags(card: dict, primary: int) -> dict:
    ic = card["ic"][f"h{primary}"]
    mean = ic.get("mean") or 0.0
    years = ic.get("by_year", {})
    shuffle = [p["ic"] for p in card["placebo"]["shuffle"]]
    stale = card["placebo"]["stale_252"].get(f"h{primary}")
    tiers = card["book"]
    tradable = [
        name
        for name in ("t1", "t2")
        if (tiers[name][f"h{primary}"]["20bp"].get("excess_ann") or 0) > 0
        and (tiers[name][f"h{primary}"]["20bp_recent"].get("excess_ann") or 0) > 0
    ]
    ctrl = [abs(v) for v in card["controls"].values() if v is not None]
    return {
        "predictive": bool(abs(ic.get("t_nonoverlap") or 0) >= 3.0),
        "stable_years": bool(years)
        and sum(1 for v in years.values() if v * mean > 0) / len(years) >= 0.7,
        "beats_shuffle": bool(shuffle) and mean > max(shuffle),
        "timely": stale is None or abs(stale) < 0.5 * abs(mean),
        "tradable_tiers_20bp": tradable,
        "distinct_from_controls": not ctrl or max(ctrl) < 0.5,
    }


def event_card(
    market: Market,
    signal: np.ndarray,
    *,
    threshold: float | None = None,
    primary: int = 20,
    seeds: int = EVENT_SEEDS,
) -> dict:
    member = market.member()
    events = member & np.isfinite(signal)
    if threshold is not None:
        with np.errstate(invalid="ignore"):
            events &= signal >= threshold
    ret = market.next_open_returns()
    bench = equal_weight(member, ret)
    start = _first_date(events, market.dates)
    tiers = {f"t{i + 1}": market.member(t) for i, t in enumerate(TIER_EDGES)}
    card: dict = {
        "coverage": {
            "events": int(events.sum()),
            "symbols": int(events.any(axis=0).sum()),
            "event_days": int(events.any(axis=1).sum()),
            "first": str(start.date()),
        }
    }
    car = {}
    for h in HORIZONS:
        fwd = market.forward_returns(h)
        car[f"h{h}"] = car_summary(events, fwd, member, market.dates, h)
        car[f"h{h}"]["by_tier"] = {
            name: car_summary(events & m, fwd, member, market.dates, h).get("mean")
            for name, m in tiers.items()
        }
    card["car"] = car
    card["book"] = {
        f"h{h}": book_block(
            market, hold(events.astype(np.float32), h, normalize=True), bench, ret, start
        )
        for h in (5, 20, 60)
    }
    fwd = market.forward_returns(primary)
    placebo = []
    for seed in range(1, seeds + 1):
        moved = redate_events(events, member, np.random.default_rng(seed))
        c = car_summary(moved, fwd, member, market.dates, primary)
        held = hold(moved.astype(np.float32), primary, normalize=True)
        blk = book_block(market, held, bench, ret, start)["10bp"]
        placebo.append({"seed": seed, "car": c.get("mean"), "excess_ann": blk["excess_ann"]})
    card["placebo"] = {"primary_horizon": primary, "redated": placebo}
    real = card["car"][f"h{primary}"].get("mean") or 0.0
    moved_cars = [p["car"] for p in placebo if p["car"] is not None]
    book = card["book"][f"h{primary}"]
    card["flags"] = {
        "car_t_ge_3": bool(abs(card["car"][f"h{primary}"].get("t_dates") or 0) >= 3.0),
        "beats_redated": bool(moved_cars)
        and (real > max(moved_cars) if real > 0 else real < min(moved_cars)),
        "book_positive_20bp": (book["20bp"].get("excess_ann") or 0) > 0,
        "book_positive_20bp_recent": (book["20bp_recent"].get("excess_ann") or 0) > 0,
    }
    return card


def car_summary(
    events: np.ndarray, fwd: np.ndarray, member: np.ndarray, dates: pd.DatetimeIndex, h: int
) -> dict:
    """Mean excess return after events, averaged within each date, then across dates."""
    with warnings.catch_warnings(), np.errstate(invalid="ignore", divide="ignore"):
        warnings.simplefilter("ignore", RuntimeWarning)
        ex = fwd - np.nanmean(np.where(member, fwd, np.nan), axis=1, keepdims=True)
        e = events & np.isfinite(ex)
        cnt = e.sum(axis=1)
        per_day = np.where(cnt > 0, np.where(e, ex, 0.0).sum(axis=1) / np.maximum(cnt, 1), np.nan)
    s = pd.Series(per_day, index=dates).dropna()
    if len(s) < 3:
        return {"events": int(e.sum())}
    return {
        "events": int(e.sum()),
        "mean": float(s.mean()),
        "t_dates": float(s.mean() / (s.std(ddof=1) / math.sqrt(len(s)))),
        "hit": float((ex[e] > 0).mean()),
        "recent_mean": float(s[s.index >= RECENT_START].mean())
        if (s.index >= RECENT_START).any()
        else None,
        "by_year": {str(y): float(v) for y, v in s.groupby(s.index.year).mean().items()},
    }


def redate_events(events: np.ndarray, member: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Each event moved to a random session of the same stock within +-EVENT_SHIFT
    sessions where the stock is in the universe (dropped after 5 misses)."""
    T = len(events)
    rows, cols = np.nonzero(events)
    out = np.zeros_like(events)
    pending = np.arange(len(rows))
    for _ in range(5):
        if not len(pending):
            break
        new = rows[pending] + rng.integers(-EVENT_SHIFT, EVENT_SHIFT + 1, len(pending))
        inside = (new >= 0) & (new < T)
        ok = np.zeros(len(pending), dtype=bool)
        ok[inside] = member[new[inside], cols[pending[inside]]]
        out[new[ok], cols[pending[ok]]] = True
        pending = pending[~ok]
    return out


def _coverage(sig: np.ndarray, member: np.ndarray, dates: pd.DatetimeIndex) -> dict:
    per_day = (member & np.isfinite(sig)).sum(axis=1)
    live = per_day > 0
    return {
        "mean_names_per_day": float(per_day[live].mean()) if live.any() else 0.0,
        "universe_share": float(per_day[live].sum() / max(member[live].sum(), 1)),
        "first": str(dates[live][0].date()) if live.any() else None,
        "last": str(dates[live][-1].date()) if live.any() else None,
    }


# ------------------------------------------------------------------------ output


def _pct(v: float | None, digits: int = 1) -> str:
    return "n/a" if v is None else f"{v:.{digits}%}"


def _num(v: float | None, digits: int = 3) -> str:
    return "n/a" if v is None else f"{v:.{digits}f}"


def _row(cells: Iterable[object]) -> str:
    return "| " + " | ".join(str(c) for c in cells) + " |"


def _header(names: list[str]) -> list[str]:
    return [_row(names), "|---" * len(names) + "|"]


def render_markdown(card: dict) -> str:
    meta = card["meta"]
    lines = [
        f"# Signal card: {meta['name']}",
        "",
        f"- Source: `{meta['source']}`; mode `{meta['mode']}`; lag {meta['lag']} sessions; "
        f"direction {meta['direction']:+d}",
        f"- Universe: top {meta['top_n']} by dollar ADV, close >= $5, funds and ETFs excluded; "
        "entries at the next open; excess vs the universe equal weight",
        f"- Generated {meta['generated_at']}",
        f"- Flags: {json.dumps(card['flags'])}",
        "",
    ]
    lines += _rank_lines(card) if meta["mode"] == "rank" else _event_lines(card)
    lines += _book_lines(card)
    return "\n".join(lines) + "\n"


def _rank_lines(card: dict) -> list[str]:
    cov = card["coverage"]
    stale = card["placebo"]["stale_252"]
    lines = [
        f"Coverage {cov['first']}..{cov['last']}, {cov['mean_names_per_day']:.0f} names/day "
        f"({_pct(cov['universe_share'], 0)} of the universe).",
        "",
        *_header(["horizon", "mean IC", "t", "hit", "2024+", "T1", "T2", "T3", "stale 252"]),
    ]
    for h in HORIZONS:
        ic = card["ic"][f"h{h}"]
        tier = ic.get("by_tier", {})
        lines.append(
            _row(
                [
                    f"{h}d",
                    _num(ic.get("mean")),
                    _num(ic.get("t_nonoverlap"), 1),
                    _pct(ic.get("hit"), 0),
                    _num(ic.get("recent_mean")),
                    *(_num(tier.get(t)) for t in ("t1", "t2", "t3")),
                    _num(stale.get(f"h{h}")),
                ]
            )
        )
    decay = ", ".join(f"{h}d {_num(v)}" for h, v in card["decay"].items())
    lines += ["", "t: non-overlapping samples. Decay (mean IC): " + decay, ""]
    lines += ["Decile mean excess return per holding period (1 = lowest signal):", ""]
    lines += _header(["horizon", *(str(i) for i in range(1, 11))])
    for h in HORIZONS:
        lines.append(_row([f"{h}d", *(_pct(v, 2) for v in card["deciles"][f"h{h}"])]))
    sh = card["placebo"]["shuffle"]
    ics = [p["ic"] for p in sh]
    exs = [p["excess_ann"] for p in sh]
    ctrl = ", ".join(f"{k} {_num(v, 2)}" for k, v in card["controls"].items())
    return lines + [
        "",
        f"Shuffle placebo ({len(sh)} seeds, {card['placebo']['primary_horizon']}d): "
        f"IC {_num(min(ics))}..{_num(max(ics))}; "
        f"top-K excess {_pct(min(exs))}..{_pct(max(exs))}/yr.",
        f"Overlap with controls (mean rank corr): {ctrl or 'not run'}",
        "",
    ]


def _event_lines(card: dict) -> list[str]:
    cov = card["coverage"]
    lines = [
        f"{cov['events']} events on {cov['event_days']} days, {cov['symbols']} stocks, "
        f"from {cov['first']}.",
        "",
        *_header(["horizon", "mean excess", "t (dates)", "hit", "2024+", "T1", "T2", "T3"]),
    ]
    for h in HORIZONS:
        c = card["car"][f"h{h}"]
        tier = c.get("by_tier", {})
        lines.append(
            _row(
                [
                    f"{h}d",
                    _pct(c.get("mean"), 2),
                    _num(c.get("t_dates"), 1),
                    _pct(c.get("hit"), 0),
                    _pct(c.get("recent_mean"), 2),
                    *(_pct(tier.get(t), 2) for t in ("t1", "t2", "t3")),
                ]
            )
        )
    moved = [p["car"] for p in card["placebo"]["redated"] if p["car"] is not None]
    if moved:
        lines += [
            "",
            f"Redated placebo ({len(moved)} seeds, {card['placebo']['primary_horizon']}d): "
            f"mean excess {_pct(min(moved), 2)}..{_pct(max(moved), 2)}.",
        ]
    return lines + [""]


def _book_lines(card: dict) -> list[str]:
    rank = card["meta"]["mode"] == "rank"
    kind = "top-K, overlapping cohorts" if rank else "every event stock, calendar time"
    lines = [
        f"Long-only book ({kind}), 20 bp, excess vs the universe:",
        "",
        *_header(
            ["book", "hold", "CAGR", "Sharpe", "max DD", "excess/yr", "IR", "turnover/yr"]
            + ["invested", "excess/yr 2024+"]
        ),
    ]
    books = card["book"] if rank else {"events": card["book"]}
    for name, by_h in books.items():
        for h, blk in by_h.items():
            b, r = blk["20bp"], blk["20bp_recent"]
            lines.append(
                _row(
                    [
                        name,
                        f"{h[1:]}d",
                        _pct(b["book"].get("cagr")),
                        _num(b["book"].get("sharpe"), 2),
                        _pct(b["book"].get("max_dd")),
                        _pct(b.get("excess_ann")),
                        _num(b.get("info_ratio"), 2),
                        f"{b.get('turnover_yr') or 0:.0f}x",
                        _pct(b.get("invested_share"), 0),
                        _pct(r.get("excess_ann")),
                    ]
                )
            )
    return lines + [""]


def write_card(card: dict, out_dir: Path = OUT_DIR) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    name = card["meta"]["name"]
    js = out_dir / f"{name}.json"
    md = out_dir / f"{name}.md"
    js.write_text(json.dumps(card, indent=1, default=_json_default) + "\n", encoding="utf-8")
    md.write_text(render_markdown(card), encoding="utf-8")
    index = out_dir / "index.jsonl"
    rows = []
    if index.exists():
        rows = [json.loads(line) for line in index.read_text().splitlines() if line.strip()]
    rows = [r for r in rows if r.get("name") != name]
    rows.append(
        {
            "name": name,
            **{k: card["meta"][k] for k in ("mode", "source", "generated_at")},
            "flags": card["flags"],
        }
    )
    index.write_text(
        "".join(json.dumps(r, default=_json_default) + "\n" for r in rows), encoding="utf-8"
    )
    return js, md


def _json_default(o: object) -> object:
    if isinstance(o, np.generic):
        return o.item()
    if isinstance(o, (pd.Timestamp, datetime)):
        return o.isoformat()
    raise TypeError(type(o))


def load_controls(market: Market, names: Iterable[str] = CONTROLS) -> dict[str, np.ndarray]:
    return {
        name: load_signal(market, source=str(FEATURES / "daily_broad"), column=CONTROLS[name])
        for name in names
    }


SPEC_DEFAULTS = {
    "mode": "rank",
    "source": None,
    "column": None,
    "where": None,
    "sql": None,
    "lag": 0,
    "direction": 1,
    "threshold": None,
    "top_k": 30,
    "primary_horizon": 20,
    "controls": True,
}


def run_spec(
    market: Market, spec: dict, top_n: int, controls: dict[str, np.ndarray] | None
) -> dict:
    """One card from a spec dict (the CLI flags, or one entry of a batch manifest)."""
    spec = {**SPEC_DEFAULTS, **spec}
    signal = load_signal(
        market,
        source=spec["source"],
        column=spec["column"],
        where=spec["where"],
        sql=spec["sql"],
        lag=spec["lag"],
    )
    if spec["mode"] == "rank":
        card = rank_card(
            market,
            signal,
            top_k=spec["top_k"],
            primary=spec["primary_horizon"],
            direction=spec["direction"],
            controls=controls if spec["controls"] else None,
        )
    else:
        card = event_card(
            market, signal, threshold=spec["threshold"], primary=spec["primary_horizon"]
        )
    where = f" where {spec['where']}" if spec["where"] else ""
    meta = {
        "name": spec["name"],
        "mode": spec["mode"],
        "source": spec["sql"] or f"{spec['source']}:{spec['column']}{where}",
        "lag": spec["lag"],
        "direction": spec["direction"],
        "threshold": spec["threshold"],
        "top_n": top_n,
        "top_k": spec["top_k"],
        "primary_horizon": spec["primary_horizon"],
        "rationale": spec.get("rationale"),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    return {"meta": meta, **card}


def run_batch(manifest: Path, top_n: int, force: bool = False) -> int:
    """Every card in a preregistered manifest, one market load; finished cards
    (their JSON exists) are skipped unless ``force``, so a stopped batch resumes."""
    specs = json.loads(manifest.read_text(encoding="utf-8"))["signals"]
    todo = [s for s in specs if force or not (OUT_DIR / f"{s['name']}.json").exists()]
    print(f"[signal-card] batch {manifest.name}: {len(todo)} of {len(specs)} to run", flush=True)
    if not todo:
        return 0
    market = load_market(top_n)
    controls = load_controls(market) if any(s.get("mode", "rank") == "rank" for s in todo) else None
    for spec in todo:
        started = time.monotonic()
        try:
            card = run_spec(market, spec, top_n, controls)
        except Exception as exc:  # one bad spec must not stop the batch
            print(f"[signal-card] {spec['name']} FAILED: {exc!r}", flush=True)
            continue
        write_card(card)
        print(
            f"[signal-card] {spec['name']} done in {time.monotonic() - started:.0f}s: "
            f"{json.dumps(card['flags'])}",
            flush=True,
        )
    return 0


def admission(card: dict) -> str:
    """The preregistered library-v1 admission rule applied to one card."""
    meta, flags = card["meta"], card["flags"]
    h = meta["primary_horizon"]
    if meta["mode"] == "rank":
        best_t = max((card["ic"][f"h{x}"].get("t_nonoverlap") or 0.0) for x in HORIZONS)
        ok = (
            flags["stable_years"]
            and flags["beats_shuffle"]
            and bool(flags["tradable_tiers_20bp"])
            and best_t >= 2.5
        )
        return "admit" if ok else "reject"
    car = card["car"][f"h{h}"]
    t = car.get("t_dates") or 0.0
    if t >= 3 and flags["beats_redated"] and flags["book_positive_20bp"]:
        return "admit" if flags["book_positive_20bp_recent"] else "reject"
    if t <= -3 and flags["beats_redated"]:
        return "admit_exit"
    return "reject"


def library_summary(manifest: Path, out_dir: Path = OUT_DIR) -> str:
    """One table over every finished card of a manifest, with the verdicts."""
    spec = json.loads(manifest.read_text(encoding="utf-8"))
    head = [
        "signal",
        "mode",
        "h",
        "IC or excess",
        "t",
        "2024+",
        "best book tier: excess/yr full / 2024+ (20 bp)",
        "verdict",
    ]
    lines = [
        f"# {spec.get('library', manifest.stem)}: summary",
        "",
        f"Admission rule (preregistered {spec.get('preregistered_at')}): "
        + "; ".join(f"{k}: {v}" for k, v in spec.get("admission_rule", {}).items()),
        "",
        *_header(head),
    ]
    for sig in spec["signals"]:
        path = out_dir / f"{sig['name']}.json"
        if not path.exists():
            lines.append(
                _row([sig["name"], sig.get("mode", "rank"), "", "", "", "", "", "not run"])
            )
            continue
        card = json.loads(path.read_text(encoding="utf-8"))
        h = card["meta"]["primary_horizon"]
        if card["meta"]["mode"] == "rank":
            ic = card["ic"][f"h{h}"]
            books = [
                (
                    name,
                    card["book"][name][f"h{h}"]["20bp"].get("excess_ann"),
                    card["book"][name][f"h{h}"]["20bp_recent"].get("excess_ann"),
                )
                for name in ("all", "t1", "t2", "t3")
            ]
            name, full, recent = max(books, key=lambda b: b[1] if b[1] is not None else -9)
            cells = [
                _num(ic.get("mean")),
                _num(ic.get("t_nonoverlap"), 1),
                _num(ic.get("recent_mean")),
            ]
        else:
            car = card["car"][f"h{h}"]
            blk = card["book"][f"h{h}"]
            name, full, recent = (
                "events",
                blk["20bp"].get("excess_ann"),
                blk["20bp_recent"].get("excess_ann"),
            )
            cells = [
                _pct(car.get("mean"), 2),
                _num(car.get("t_dates"), 1),
                _pct(car.get("recent_mean"), 2),
            ]
        lines.append(
            _row(
                [
                    sig["name"],
                    card["meta"]["mode"],
                    f"{h}d",
                    *cells,
                    f"{name}: {_pct(full)} / {_pct(recent)}",
                    admission(card),
                ]
            )
        )
    text = "\n".join(lines) + "\n"
    (out_dir / f"{manifest.stem.replace('-manifest', '')}-summary.md").write_text(
        text, encoding="utf-8"
    )
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Signal card for a per-stock signal")
    ap.add_argument("--batch", type=Path, help="manifest JSON with a 'signals' list of specs")
    ap.add_argument("--force", action="store_true", help="batch: rerun finished cards")
    ap.add_argument("--summarize", type=Path, help="manifest JSON: table of finished cards")
    ap.add_argument("--name")
    ap.add_argument("--mode", choices=("rank", "event"), default="rank")
    ap.add_argument("--source", help="parquet file or directory with symbol, trade_date, <column>")
    ap.add_argument("--column")
    ap.add_argument("--where", help="SQL predicate on the source rows")
    ap.add_argument("--sql", help="query returning symbol, trade_date, value (instead of --source)")
    ap.add_argument("--lag", type=int, default=0, help="extra sessions of delay")
    ap.add_argument("--direction", type=int, choices=(1, -1), default=1)
    ap.add_argument(
        "--threshold", type=float, help="event mode: minimum value that counts as an event"
    )
    ap.add_argument("--top-n", type=int, default=3000)
    ap.add_argument("--top-k", type=int, default=30)
    ap.add_argument("--primary-horizon", type=int, default=20, choices=(5, 20, 60))
    ap.add_argument("--no-controls", action="store_true")
    args = ap.parse_args(argv)
    if args.summarize:
        print(library_summary(args.summarize))
        return 0
    if args.batch:
        return run_batch(args.batch, args.top_n, args.force)
    if not args.name:
        ap.error("--name is required without --batch")
    market = load_market(args.top_n)
    spec = {
        k: getattr(args, k)
        for k in ("name", "mode", "source", "column", "where", "sql", "lag", "direction")
        + ("threshold", "top_k", "primary_horizon")
    }
    spec["controls"] = not args.no_controls
    controls = load_controls(market) if args.mode == "rank" and spec["controls"] else None
    card = run_spec(market, spec, args.top_n, controls)
    js, md = write_card(card)
    print(md.read_text(encoding="utf-8"))
    print(f"written {js.relative_to(ROOT)} and {md.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
