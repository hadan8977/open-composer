"""Stage-0 diagnostic: do existing signals recover value as hedged long-short books?

DESIGN-ONLY DIAGNOSTIC on data the project has already seen. It is not a
preregistered iteration and promotes nothing. Frozen design (coordinator brief
R1001-0625-S0): monthly formation (last session of the month), signal at the
formation close, enter at the next session's open, exit at the open of the
session after the next formation date (open-to-open, one forward convention
everywhere), equal weight inside legs, 10 bp per side on traded notional of
every leg including the SPY hedge (20 bp reported too).

Subcommands::

    panel   build cache/price_panel.parquet (chunked, sanitized prices, signals,
            forward open-to-open returns)
    books   join universe / fundamentals / predictions, run every book, placebo,
            combination, write results.json and monthly_returns.parquet
    all     both

Heavy steps run through ``scripts/run_capped.sh --mem 1.8G -- uv run python``.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "reports/research/program/stage0-hedged-books-2026-10-01"
CACHE = OUT_DIR / "cache"
DAILY_GLOB = str(ROOT / "data/features/daily_broad/*.parquet")
UNIV_GLOB = str(ROOT / "data/features/universe_broad/*.parquet")
FUND_GLOB = str(ROOT / "data/features/sec_fundamentals_daily/*.parquet")
SIP_GLOB = str(ROOT / "data/sip/daily/*/shard-*.parquet")
T19 = ROOT / "reports/research/iterations/t20260930_17b_model_family_book/cache"
RF_PATH = T19 / "rf_series.parquet"
MODELS = {"CAT_H63": "CAT", "LGBM_H63": "LGBM", "XGB_H63": "XGB"}

FIRST_FORMATION = "2017-10-01"
LAST_FORMATION = "2026-08-31"
WINDOWS = {
    "stress": ("2017-10-01", "2023-07-31"),
    "gap": ("2023-08-01", "2023-12-31"),
    "anchor": ("2024-01-01", "2026-08-31"),
    "all": ("2017-10-01", "2026-08-31"),
}
SINGLE_SIGNALS = ["MOM_12_1", "ON252", "STR_21", "GP", "SUE", "CAT_H63", "LGBM_H63", "XGB_H63"]
SIGNALS = [*SINGLE_SIGNALS, "COMP4"]
UNIVERSES = {"P1000": (1, 1000), "Q2": (1001, 3000)}
BOOKS = ["LS_RAW", "LS_BH", "LS_SN_BH", "LONG_ONLY_TOP"]
MIN_PRICE = 5.0
DECILE = 0.10
MIN_NAMES = 50
N_BUCKETS = 5
COST_10 = 0.0010
COST_20 = 0.0020
BORROW_ANNUAL = 0.01  # supplementary sensitivity only, not part of the frozen design
NW_LAGS = 3
N_SEEDS = 100
SEED0 = 20261001
VOL_TARGET = 0.10
VOL_LOOKBACK = 24
VOL_MIN = 12
SPLIT_LIKE_RATIOS = (0.1, 0.2, 0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 1.5, 2.0, 3.0, 4.0, 5.0, 10.0)
SPLIT_LIKE_LOG_TOL = 0.03
BETA_FILL = 1.0
SPY_ALIGN_CORR_MAX = 0.5
SPY_ALIGN_BETA_MAX = 0.5


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# --------------------------------------------------------------------------
# pure helpers (unit-tested)
# --------------------------------------------------------------------------


def is_split_like_ratio(ratio: np.ndarray) -> np.ndarray:
    """True where ``ratio`` sits within ~3% (log space) of a common split multiple."""
    ratio = np.asarray(ratio, dtype="float64")
    valid = np.isfinite(ratio) & (ratio > 0)
    logr = np.full_like(ratio, np.nan)
    logr[valid] = np.log(ratio[valid])
    out = np.zeros(ratio.shape, dtype=bool)
    for c in SPLIT_LIKE_RATIOS:
        out |= valid & (np.abs(logr - math.log(c)) < SPLIT_LIKE_LOG_TOL)
    return out


def month_end_positions(calendar: pd.DatetimeIndex) -> np.ndarray:
    """Positions of the last session of each calendar month in ``calendar``."""
    s = pd.Series(np.arange(len(calendar)), index=calendar)
    return s.groupby([calendar.year, calendar.month]).max().to_numpy()


def open_to_open_returns(
    open_w: np.ndarray, close_w: np.ndarray, entry_pos: int, exit_pos: int
) -> tuple[np.ndarray, np.ndarray]:
    """Forward open-to-open return per column: ``open[exit_pos] / open[entry_pos] - 1``.

    The single forward convention for every stock and for SPY. When the exit
    open is missing (delisting, halt) the last valid close inside
    ``[entry_pos, exit_pos)`` is the exit price and the second output is True.
    A missing / non-positive entry open gives NaN.
    """
    entry = open_w[entry_pos].astype("float64")
    exit_open = open_w[exit_pos].astype("float64")
    fallback = ~np.isfinite(exit_open)
    if fallback.any() and exit_pos > entry_pos:
        blk = close_w[entry_pos:exit_pos].astype("float64")
        ok = np.isfinite(blk)
        last_idx = np.where(ok, np.arange(blk.shape[0])[:, None], -1).max(axis=0)
        last_close = np.where(
            last_idx >= 0, blk[np.maximum(last_idx, 0), np.arange(blk.shape[1])], np.nan
        )
        exit_px = np.where(fallback, last_close, exit_open)
    else:
        exit_px = exit_open
    ok_entry = np.isfinite(entry) & (entry > 0)
    ret = np.where(
        ok_entry & np.isfinite(exit_px), exit_px / np.where(ok_entry, entry, 1.0) - 1.0, np.nan
    )
    return ret, fallback & np.isfinite(ret)


def _order(score: np.ndarray) -> np.ndarray:
    """Deterministic ascending order (stable; ties broken by position)."""
    return np.argsort(score, kind="stable")


def _n_leg(n: int) -> int:
    return max(1, int(round(DECILE * n)))


def select_legs(
    score: np.ndarray, adv_rank: np.ndarray | None, size_neutral: bool
) -> tuple[np.ndarray, np.ndarray]:
    """Index arrays (long, short) of the top / bottom decile.

    ``size_neutral``: split the names into ``N_BUCKETS`` equal-count ADV-rank
    buckets and take the top / bottom decile of ``score`` inside each bucket.
    """
    n = len(score)
    if not size_neutral:
        order = _order(score)
        k = _n_leg(n)
        return order[-k:], order[:k]
    assert adv_rank is not None
    by_adv = np.argsort(adv_rank, kind="stable")
    longs, shorts = [], []
    for bucket in np.array_split(by_adv, N_BUCKETS):
        if len(bucket) == 0:
            continue
        order = bucket[_order(score[bucket])]
        k = _n_leg(len(bucket))
        longs.append(order[-k:])
        shorts.append(order[:k])
    return np.concatenate(longs), np.concatenate(shorts)


def build_weights(
    n_total: int,
    ids: np.ndarray,
    score: np.ndarray,
    adv_rank: np.ndarray,
    beta: np.ndarray,
    kind: str,
    spy_index: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Dense weight vector over ``n_total`` slots (stocks + SPY at ``spy_index``)
    plus the dense global ids of the long and short legs.

    Long leg sums to +1, short leg to -1 (dollar-neutral, $1 each side);
    ``LONG_ONLY_TOP`` is the +1 long leg only. ``*_BH`` adds SPY with weight
    ``-sum(w_i * beta_i)`` so the book's ex-ante beta is zero.
    """
    sn = kind == "LS_SN_BH"
    lg, sh = select_legs(score, adv_rank, size_neutral=sn)
    w = np.zeros(n_total)
    w[ids[lg]] = 1.0 / len(lg)
    if kind != "LONG_ONLY_TOP":
        w[ids[sh]] = -1.0 / len(sh)
    if kind in ("LS_BH", "LS_SN_BH"):
        w[spy_index] = -float(np.dot(w[ids], beta))
    return w, ids[lg], ids[sh]


def simulate_book(
    weights: list[np.ndarray | None], rets: list[np.ndarray]
) -> tuple[np.ndarray, np.ndarray]:
    """Gross portfolio return and turnover per period.

    ``weights[k]`` / ``rets[k]`` are dense vectors over the same slots (stocks
    plus SPY); ``None`` means the period is skipped (NaN return, book flat).
    Turnover_k = sum |w_new - w_old_drifted| with
    ``w_old_drifted = w_old * (1 + r) / (1 + R_gross)``.
    """
    gross = np.full(len(weights), np.nan)
    turn = np.full(len(weights), np.nan)
    prev: np.ndarray | None = None
    for k, (w, r) in enumerate(zip(weights, rets, strict=True)):
        if w is None:
            prev = None
            continue
        if prev is None:
            turn[k] = float(np.abs(w).sum())
        else:
            turn[k] = float(np.abs(w - prev).sum())
        gross[k] = float(np.dot(w, r))
        prev = w * (1.0 + r) / (1.0 + gross[k])
    return gross, turn


def newey_west_t(x: np.ndarray, lags: int = NW_LAGS) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lags + 3:
        return float("nan")
    d = x - x.mean()
    g0 = float(np.dot(d, d) / n)
    s = g0
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        s += 2.0 * w * float(np.dot(d[lag:], d[:-lag]) / n)
    if s <= 0:
        return float("nan")
    return float(x.mean() / math.sqrt(s / n))


def max_drawdown(r: np.ndarray) -> float:
    r = np.asarray(r, dtype="float64")
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return float("nan")
    eq = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1.0).min())


def series_stats(r: np.ndarray) -> dict[str, float]:
    r = np.asarray(r, dtype="float64")
    r = r[np.isfinite(r)]
    n = len(r)
    if n < 3:
        return {"n": n}
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    sharpe = mu / sd * math.sqrt(12.0) if sd > 0 else float("nan")
    return {
        "n": n,
        "ann_return": mu * 12.0,
        "ann_vol": sd * math.sqrt(12.0),
        "sharpe": sharpe,
        "sharpe_se": math.sqrt((1.0 + 0.5 * sharpe**2) / (n / 12.0)) if sd > 0 else float("nan"),
        "mean_monthly_bp": mu * 1e4,
        "nw_t": newey_west_t(r),
        "max_dd": max_drawdown(r),
    }


def beta_corr(r: np.ndarray, spy: np.ndarray) -> tuple[float, float]:
    m = np.isfinite(r) & np.isfinite(spy)
    if m.sum() < 5 or np.var(spy[m]) == 0 or np.var(r[m]) == 0:
        return float("nan"), float("nan")
    c = np.cov(r[m], spy[m], ddof=1)
    return float(c[0, 1] / c[1, 1]), float(np.corrcoef(r[m], spy[m])[0, 1])


def zscore_winsor(x: np.ndarray, clip: float = 3.0) -> np.ndarray:
    """Cross-sectional z-score winsorized at +-clip; NaN stays NaN."""
    out = np.full(x.shape, np.nan)
    m = np.isfinite(x)
    if m.sum() < 3:
        return out
    sd = x[m].std(ddof=0)
    if sd == 0:
        return out
    out[m] = np.clip((x[m] - x[m].mean()) / sd, -clip, clip)
    return out


def comp4(mom: np.ndarray, on: np.ndarray, gp: np.ndarray, sue: np.ndarray) -> np.ndarray:
    """Equal-weight mean of winsorized z-scores; a missing value contributes 0.
    NaN where all four are missing."""
    z = np.vstack([zscore_winsor(v) for v in (mom, on, gp, sue)])
    have = np.isfinite(z).any(axis=0)
    score = np.where(np.isfinite(z), z, 0.0).sum(axis=0) / 4.0
    return np.where(have, score, np.nan)


def window_mask(dates: np.ndarray, name: str) -> np.ndarray:
    lo, hi = WINDOWS[name]
    d = pd.DatetimeIndex(dates)
    return np.asarray((d >= pd.Timestamp(lo)) & (d <= pd.Timestamp(hi)))


def trailing_scaled(net: np.ndarray, target: float = VOL_TARGET) -> np.ndarray:
    """Scale each month's return to ``target`` annual vol using the std of the
    ``VOL_LOOKBACK`` returns that ended before the previous period (periods
    k-2 .. k-25: the period k-1 exit open coincides with the period k entry,
    so it is not known at the formation close). NaN until ``VOL_MIN`` known."""
    n = len(net)
    out = np.full(n, np.nan)
    for k in range(n):
        hist = net[max(0, k - 1 - VOL_LOOKBACK) : max(0, k - 1)]
        hist = hist[np.isfinite(hist)]
        if len(hist) >= VOL_MIN and hist.std(ddof=1) > 0 and np.isfinite(net[k]):
            out[k] = net[k] * target / (hist.std(ddof=1) * math.sqrt(12.0))
    return out


# --------------------------------------------------------------------------
# stage 1: price panel
# --------------------------------------------------------------------------


def _duck():
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    con.execute(f"SET temp_directory='{CACHE}/duck_tmp'")
    con.execute("SET TimeZone='UTC'")
    return con


def stage_panel(chunk: int = 700) -> None:
    from open_composer.research.features import price_hygiene as ph

    CACHE.mkdir(parents=True, exist_ok=True)
    (CACHE / "duck_tmp").mkdir(exist_ok=True)
    con = _duck()
    syms = (
        con.execute(
            f"select distinct symbol from read_parquet('{UNIV_GLOB}') "
            "where adv_rank <= 3000 and month_end >= '2017-09-01' order by 1"
        )
        .df()["symbol"]
        .tolist()
    )
    cal_df = con.execute(
        f"select trade_date, count(*) n from read_parquet('{DAILY_GLOB}') group by 1 order by 1"
    ).df()
    cal = pd.DatetimeIndex(cal_df.loc[cal_df["n"] >= 500, "trade_date"])
    _log(
        f"symbols={len(syms)} sessions={len(cal)} {cal[0].date()}..{cal[-1].date()} "
        f"(dropped {int((cal_df['n'] < 500).sum())} thin sessions)"
    )
    spy = con.execute(
        f"select cast(timestamp as date) d, open, close from read_parquet('{SIP_GLOB}') "
        "where symbol = 'SPY' order by 1"
    ).df()
    assert spy["d"].is_unique, "duplicate SPY sessions"
    spy.index = pd.DatetimeIndex(spy.pop("d"))
    spy = spy.reindex(cal)
    spy.to_parquet(CACHE / "spy_daily.parquet")
    _log(f"SPY sessions on calendar: {int(spy['open'].notna().sum())} of {len(cal)}")
    spy_close = spy["close"].to_numpy()
    spy_ret = np.full(len(cal), np.nan)
    spy_ret[1:] = spy_close[1:] / spy_close[:-1] - 1.0

    me = month_end_positions(cal)
    fdates = cal[me]
    keep = (fdates >= pd.Timestamp(FIRST_FORMATION)) & (fdates <= pd.Timestamp(LAST_FORMATION))
    f_pos = me[keep]
    last = len(cal) - 1
    e_pos = f_pos + 1
    me_list = list(me)
    # exit = open of the session after the next month-end; the last formation's next
    # month-end is not in the data, so its period ends at the last available open
    x_pos = np.array(
        [
            min(me_list[me_list.index(int(p)) + 1] + 1, last)
            if me_list.index(int(p)) + 1 < len(me_list)
            else last
            for p in f_pos
        ]
    )
    partial = np.array(
        [
            not (
                me_list.index(int(p)) + 1 < len(me_list)
                and me_list[me_list.index(int(p)) + 1] + 1 <= last
            )
            for p in f_pos
        ]
    )
    _log(f"formations={len(f_pos)} partial_last={int(partial.sum())}")
    meta = pd.DataFrame(
        {
            "formation_date": cal[f_pos],
            "entry_date": cal[e_pos],
            "exit_date": cal[x_pos],
            "partial": partial,
        }
    )
    meta.to_parquet(CACHE / "periods.parquet")
    spy_open_w = spy[["open"]].to_numpy()
    spy_close_w = spy[["close"]].to_numpy()
    meta["spy_ret"] = [
        float(open_to_open_returns(spy_open_w, spy_close_w, int(e), int(x))[0][0])
        for e, x in zip(e_pos, x_pos, strict=True)
    ]
    meta.to_parquet(CACHE / "periods.parquet")

    parts: list[pd.DataFrame] = []
    hyg = {"symbols_masked": 0, "price_cells_masked": 0}
    for ci in range(0, len(syms), chunk):
        names = syms[ci : ci + chunk]
        con.register("chunk_syms", pd.DataFrame({"symbol": names}))
        df = con.execute(
            f"select d.symbol, d.trade_date, d.open, d.close from read_parquet('{DAILY_GLOB}') d "
            "semi join chunk_syms c on d.symbol = c.symbol"
        ).df()
        df = df.drop_duplicates(["trade_date", "symbol"], keep="last")
        close_w = df.pivot(index="trade_date", columns="symbol", values="close").reindex(cal)
        open_w = df.pivot(index="trade_date", columns="symbol", values="open").reindex(cal)
        del df
        close_s, open_s, rep = ph.sanitize_price_matrices(
            close_w.astype("float64"), open_w.astype("float64")
        )
        hyg["symbols_masked"] += int(rep.symbols_masked)
        hyg["price_cells_masked"] += int(rep.price_cells_masked)
        del close_w, open_w
        cols = list(close_s.columns)
        C = close_s.to_numpy()
        OPN = open_s.to_numpy()
        prev_c = np.vstack([np.full((1, C.shape[1]), np.nan), C[:-1]])
        gap = OPN / prev_c
        split_like = is_split_like_ratio(gap)
        on = np.where(split_like, np.nan, gap - 1.0)
        on_df = pd.DataFrame(on, index=cal, columns=cols)
        on252 = on_df.rolling(252, min_periods=200).mean().to_numpy()
        del on_df, on, gap
        # per-stock 252-day beta to SPY (close-to-close, no padding)
        R = np.vstack([np.full((1, C.shape[1]), np.nan), C[1:] / C[:-1] - 1.0])
        ok = np.isfinite(R)
        Y = np.where(ok, spy_ret[:, None], np.nan)
        Xd = pd.DataFrame(R, index=cal, columns=cols)
        Yd = pd.DataFrame(Y, index=cal, columns=cols)

        def rm(a: pd.DataFrame) -> np.ndarray:
            return a.rolling(252, min_periods=126).mean().to_numpy()

        ex, ey = rm(Xd), rm(Yd)
        exy, eyy = rm(Xd * Yd), rm(Yd * Yd)
        with np.errstate(invalid="ignore", divide="ignore"):
            beta_all = (exy - ex * ey) / (eyy - ey * ey)
        del Xd, Yd, R, Y, ex, ey, exy, eyy, ok
        rows = []
        for k in range(len(f_pos)):
            p, e, x = int(f_pos[k]), int(e_pos[k]), int(x_pos[k])
            ret, fb = open_to_open_returns(OPN, C, e, x)
            hold_split = (
                split_like[e + 1 : x + 1].any(axis=0) if x > e else np.zeros(len(cols), bool)
            )
            with np.errstate(invalid="ignore", divide="ignore"):
                mom = C[p - 21] / C[p - 252] - 1.0
                st = -(C[p] / C[p - 21] - 1.0)
            rows.append(
                pd.DataFrame(
                    {
                        "formation_date": cal[p],
                        "symbol": cols,
                        "MOM_12_1": mom,
                        "ON252": on252[p],
                        "STR_21": st,
                        "beta": beta_all[p],
                        "entry_open": OPN[e],
                        "ret_fwd": ret,
                        "exit_fallback": fb,
                        "split_hold": hold_split,
                    }
                )
            )
        part = pd.concat(rows, ignore_index=True)
        part = part[np.isfinite(part["entry_open"])]
        parts.append(part)
        _log(f"chunk {ci // chunk + 1}/{math.ceil(len(syms) / chunk)}: {len(part):,} rows")
        del C, OPN, close_s, open_s, split_like, on252, beta_all
    panel = pd.concat(parts, ignore_index=True)
    panel["symbol"] = panel["symbol"].astype(str)
    panel.to_parquet(CACHE / "price_panel.parquet")
    (CACHE / "panel_manifest.json").write_text(
        json.dumps(
            {
                "rows": len(panel),
                "symbols": len(syms),
                "hygiene": hyg,
                "sessions": len(cal),
                "calendar": [str(cal[0].date()), str(cal[-1].date())],
            },
            indent=1,
        )
    )
    _log(f"panel written: {len(panel):,} rows; hygiene {hyg}")


# --------------------------------------------------------------------------
# stage 2: join + books
# --------------------------------------------------------------------------


def load_joined_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = pd.read_parquet(CACHE / "price_panel.parquet")
    periods = pd.read_parquet(CACHE / "periods.parquet")
    fdates = pd.DatetimeIndex(periods["formation_date"])
    con = _duck()
    # universe: latest month_end <= formation date
    mes = con.execute(f"select distinct month_end from read_parquet('{UNIV_GLOB}')").df()[
        "month_end"
    ]
    mes = pd.DatetimeIndex(sorted(mes))
    fmap = pd.DataFrame(
        {"formation_date": fdates, "month_end": [mes[mes <= d].max() for d in fdates]}
    )
    con.register("fmap", fmap)
    uni = con.execute(
        f"select f.formation_date, u.symbol, u.adv_rank, u.close as uni_close "
        f"from read_parquet('{UNIV_GLOB}') u join fmap f on u.month_end = f.month_end "
        "where u.adv_rank <= 3000 and u.close >= 5"
    ).df()
    uni["symbol"] = uni["symbol"].astype(str)
    df = uni.merge(panel, on=["formation_date", "symbol"], how="left")
    con.register("fdates", pd.DataFrame({"trade_date": fdates}))
    fund = con.execute(
        "select s.symbol, s.trade_date as formation_date, "
        "s.gross_profitability as GP, s.sue_eps as SUE "
        f"from read_parquet('{FUND_GLOB}') s join fdates f on s.trade_date = f.trade_date"
    ).df()
    fund["symbol"] = fund["symbol"].astype(str)
    df = df.merge(fund, on=["formation_date", "symbol"], how="left")
    for sig, tag in MODELS.items():
        p = T19 / f"predictions_{tag}_WX_H63.parquet"
        pr = con.execute(
            f"select p.trade_date as formation_date, p.symbol, p.prediction as {sig} "
            f"from read_parquet('{p}') p join fdates f on p.trade_date = f.trade_date"
        ).df()
        pr["symbol"] = pr["symbol"].astype(str)
        df = df.merge(pr, on=["formation_date", "symbol"], how="left")
    return df, periods


def prediction_fold_check() -> dict[str, Any]:
    """Every prediction date's fold must have trained on data ending >= 63
    sessions before the date, and the date must lie inside the fold's coverage."""
    spy = pd.read_parquet(CACHE / "spy_daily.parquet")
    cal = pd.DatetimeIndex(spy.index)
    con = _duck()
    out: dict[str, Any] = {}
    for sig, tag in MODELS.items():
        meta = json.loads((T19 / f"fold_meta_{tag}_WX_H63.json").read_text())
        folds = {m["fold_id"]: m for m in meta if "coverage_start" in m}
        pairs = con.execute(
            "select fold_id, min(trade_date) lo, max(trade_date) hi, "
            "count(distinct trade_date) nd "
            f"from read_parquet('{T19}/predictions_{tag}_WX_H63.parquet') group by 1 order by 1"
        ).df()
        worst, bad, outside = None, [], []
        for r in pairs.itertuples():
            m = folds.get(int(r.fold_id))
            if m is None:
                bad.append(int(r.fold_id))
                continue
            cut = cal.searchsorted(pd.Timestamp(m["train_cutoff"]), side="right") - 1
            first = cal.searchsorted(pd.Timestamp(r.lo), side="left")
            gap = int(first - cut)
            worst = gap if worst is None else min(worst, gap)
            if gap < 63:
                bad.append(int(r.fold_id))
            if pd.Timestamp(r.lo) < pd.Timestamp(m["coverage_start"]) or pd.Timestamp(
                r.hi
            ) > pd.Timestamp(m["coverage_end"]):
                outside.append(int(r.fold_id))
        out[sig] = {
            "folds_checked": int(len(pairs)),
            "min_sessions_between_train_cutoff_and_first_prediction": worst,
            "folds_below_63": bad,
            "folds_outside_coverage": outside,
            "pass": bool(not bad and not outside and worst is not None and worst >= 63),
        }
    return out


def independent_return_check(panel: pd.DataFrame, periods: pd.DataFrame) -> dict[str, Any]:
    """Recompute AAPL / MSFT forward open-to-open returns straight from the raw
    daily table (no sanitation, SQL row positions) and compare to the panel."""
    con = _duck()
    out: dict[str, Any] = {}
    worst = 0.0
    n = 0
    for sym in ("AAPL", "MSFT", "JPM"):
        raw = (
            con.execute(
                f"select trade_date, open from read_parquet('{DAILY_GLOB}') "
                f"where symbol = '{sym}' order by 1"
            )
            .df()
            .set_index("trade_date")["open"]
        )
        sub = panel[panel["symbol"] == sym].set_index("formation_date")
        for r in periods.itertuples():
            if r.formation_date not in sub.index:
                continue
            ref = raw.get(r.exit_date) / raw.get(r.entry_date) - 1.0
            got = sub.loc[r.formation_date, "ret_fwd"]
            if np.isfinite(ref) and np.isfinite(got):
                worst = max(worst, abs(ref - got))
                n += 1
    spy_raw = (
        con.execute(
            f"select cast(timestamp as date) d, open from read_parquet('{SIP_GLOB}') "
            "where symbol = 'SPY' order by 1"
        )
        .df()
        .set_index("d")["open"]
    )
    spy_raw.index = pd.DatetimeIndex(spy_raw.index)
    spy_worst = 0.0
    for r in periods.itertuples():
        ref = spy_raw[r.exit_date] / spy_raw[r.entry_date] - 1.0
        spy_worst = max(spy_worst, abs(ref - r.spy_ret))
    out["spy_max_abs_diff_vs_raw_sql"] = spy_worst
    out["max_abs_diff"] = worst
    out["n_compared"] = n
    out["pass"] = bool(n > 100 and worst < 1e-9 and spy_worst < 1e-12)
    return out


def _prepare_period_frames(
    df: pd.DataFrame, periods: pd.DataFrame
) -> tuple[list[pd.DataFrame], dict[str, int], int]:
    syms = sorted(df["symbol"].unique())
    sid = {s: i for i, s in enumerate(syms)}
    df = df.copy()
    df["gid"] = df["symbol"].map(sid)
    return [df[df["formation_date"] == d] for d in periods["formation_date"]], sid, len(syms)


def _eligible(sub: pd.DataFrame, lo: int, hi: int) -> pd.DataFrame:
    m = (sub["adv_rank"] >= lo) & (sub["adv_rank"] <= hi)
    m &= (
        np.isfinite(sub["entry_open"])
        & np.isfinite(sub["ret_fwd"])
        & ~sub["split_hold"].astype("boolean").fillna(True).to_numpy(dtype=bool)
    )
    return sub[m]


def run_books() -> None:
    t0 = time.time()
    df, periods = load_joined_panel()
    _log(f"joined panel {len(df):,} rows")
    fold_check = prediction_fold_check()
    _log(f"fold check {fold_check}")
    ret_check = independent_return_check(pd.read_parquet(CACHE / "price_panel.parquet"), periods)
    _log(f"independent return check {ret_check}")
    frames, sid, n_sym = _prepare_period_frames(df, periods)
    spy_idx = n_sym
    n_total = n_sym + 1
    K = len(periods)
    fdates = periods["formation_date"].to_numpy()
    spy_ret = periods["spy_ret"].to_numpy()
    rf = pd.read_parquet(RF_PATH)["rf"]
    spy_daily = pd.read_parquet(CACHE / "spy_daily.parquet")
    cal = pd.DatetimeIndex(spy_daily.index)
    rf = rf.reindex(cal).fillna(0.0).to_numpy()
    rf_period = np.array(
        [
            rf[cal.get_loc(r.entry_date) + 1 : cal.get_loc(r.exit_date) + 1].sum()
            for r in periods.itertuples()
        ]
    )

    # dense per-period return vectors (NaN -> 0; held names always have finite returns)
    def dense_ret(sub: pd.DataFrame, k: int) -> np.ndarray:
        r = np.zeros(n_total)
        r[sub["gid"].to_numpy()] = np.where(np.isfinite(sub["ret_fwd"]), sub["ret_fwd"], 0.0)
        r[spy_idx] = spy_ret[k]
        return r

    rdense = [dense_ret(frames[k], k) for k in range(K)]
    counters = {"beta_filled": 0, "names": 0, "exit_fallback_held": 0}
    results: dict[str, Any] = {}
    series: dict[tuple[str, str, str], dict[str, np.ndarray]] = {}
    held_abs_ret_max = 0.0
    held_big = 0

    def prep(uni: str, k: int) -> dict[str, Any] | None:
        lo, hi = UNIVERSES[uni]
        sub = _eligible(frames[k], lo, hi)
        if len(sub) < MIN_NAMES:
            return None
        beta = sub["beta"].to_numpy(dtype="float64")
        nb = ~np.isfinite(beta)
        counters["beta_filled"] += int(nb.sum())
        counters["names"] += len(beta)
        beta = np.where(nb, BETA_FILL, beta)
        sigs = {s: sub[s].to_numpy(dtype="float64") for s in SINGLE_SIGNALS}
        sigs["COMP4"] = comp4(sigs["MOM_12_1"], sigs["ON252"], sigs["GP"], sigs["SUE"])
        return {
            "ids": sub["gid"].to_numpy(),
            "adv": sub["adv_rank"].to_numpy(dtype="float64"),
            "beta": beta,
            "sigs": sigs,
            "ret": sub["ret_fwd"].to_numpy(dtype="float64"),
            "fb": sub["exit_fallback"].to_numpy(dtype=bool),
        }

    prepped: dict[tuple[str, int], dict[str, Any] | None] = {
        (u, k): prep(u, k) for u in UNIVERSES for k in range(K)
    }
    _log(f"prepared eligibility ({time.time() - t0:.0f}s); beta filled {counters}")

    def book_series(
        uni: str, sig: str, kind: str, score_override: dict[int, np.ndarray] | None = None
    ) -> dict[str, np.ndarray]:
        nonlocal held_abs_ret_max, held_big
        w_list: list[np.ndarray | None] = []
        legs_l, legs_s = [], []
        nlong = np.zeros(K)
        nshort = np.zeros(K)
        exante = np.full(K, np.nan)
        for k in range(K):
            pp = prepped[(uni, k)]
            if pp is None:
                w_list.append(None)
                legs_l.append(np.nan)
                legs_s.append(np.nan)
                continue
            score = score_override[k] if score_override is not None else pp["sigs"][sig]
            m = np.isfinite(score)
            if m.sum() < MIN_NAMES:
                w_list.append(None)
                legs_l.append(np.nan)
                legs_s.append(np.nan)
                continue
            w, lg_ids, sh_ids = build_weights(
                n_total,
                pp["ids"][m],
                score[m],
                pp["adv"][m],
                pp["beta"][m],
                kind,
                spy_idx,
            )
            w_list.append(w)
            exante[k] = float(np.dot(w[pp["ids"][m]], pp["beta"][m]))
            rk = rdense[k]
            legs_l.append(float(rk[lg_ids].mean()))
            legs_s.append(float(rk[sh_ids].mean()) if kind != "LONG_ONLY_TOP" else np.nan)
            nlong[k] = len(lg_ids)
            nshort[k] = len(sh_ids) if kind != "LONG_ONLY_TOP" else 0
            if score_override is None:
                sel = np.concatenate([lg_ids, sh_ids]) if kind != "LONG_ONLY_TOP" else lg_ids
                a = np.abs(rk[sel])
                held_abs_ret_max = max(held_abs_ret_max, float(a.max()))
                held_big += int((a > 2.0).sum())
        gross, turn = simulate_book(w_list, rdense)
        # short notional for the borrow sensitivity: stocks only (the SPY hedge slot is excluded)
        short_notional = np.array(
            [0.0 if w is None else float(-np.minimum(w[:spy_idx], 0).sum()) for w in w_list]
        )
        out = {
            "gross": gross,
            "turn": turn,
            "net10": gross - COST_10 * turn,
            "net20": gross - COST_20 * turn,
            "net10_borrow": gross - COST_10 * turn - BORROW_ANNUAL / 12.0 * short_notional,
            "long": np.array(legs_l),
            "short": np.array(legs_s),
            "exante_beta_stocks": exante,
            "n_long": nlong,
            "n_short": nshort,
        }
        if kind == "LONG_ONLY_TOP":
            for key in ("gross", "net10", "net20", "net10_borrow"):
                out[key + "_xrf"] = out[key] - rf_period
            out["net10_xspy"] = out["net10"] - spy_ret
        return out

    # ---- key cell first: P1000 LS_SN_BH ----
    order = [("P1000", "LS_SN_BH")] + [
        (u, b) for u in UNIVERSES for b in BOOKS if not (u == "P1000" and b == "LS_SN_BH")
    ]
    for uni, kind in order:
        for sig in SIGNALS:
            series[(uni, sig, kind)] = book_series(uni, sig, kind)
        _log(f"books done: {uni} {kind} ({time.time() - t0:.0f}s)")

    # ---- per-window stats ----
    def stats_for(uni: str, sig: str, kind: str) -> dict[str, Any]:
        s = series[(uni, sig, kind)]
        res: dict[str, Any] = {}
        for w in WINDOWS:
            m = window_mask(fdates, w)
            if kind == "LONG_ONLY_TOP":
                g, n10, n20 = s["gross_xrf"][m], s["net10_xrf"][m], s["net20_xrf"][m]
                bor = s["net10_borrow_xrf"][m]
            else:
                g, n10, n20, bor = s["gross"][m], s["net10"][m], s["net20"][m], s["net10_borrow"][m]
            beta, corr = beta_corr(s["gross"][m], spy_ret[m])
            ex_l = s["long"][m] - spy_ret[m]
            ex_s = s["short"][m] - spy_ret[m]
            if kind == "LONG_ONLY_TOP":
                ex_s = np.array([np.nan])
            d: dict[str, Any] = {
                "gross": series_stats(g),
                "net10": series_stats(n10),
                "net20": series_stats(n20),
                "net10_borrow100bp_supplementary": series_stats(bor),
                "avg_monthly_turnover": float(np.nanmean(s["turn"][m])),
                "long_leg_excess_vs_spy_bp": float(np.nanmean(ex_l) * 1e4),
                "short_leg_excess_vs_spy_bp": (
                    float(np.nanmean(ex_s) * 1e4) if kind != "LONG_ONLY_TOP" else None
                ),
                "realized_beta_to_spy": beta,
                "corr_with_spy": corr,
                "avg_n_long": float(np.nanmean(s["n_long"][m])),
                "avg_n_short": float(np.nanmean(s["n_short"][m])),
            }
            if kind == "LONG_ONLY_TOP":
                d["net10_minus_spy"] = series_stats(s["net10_xspy"][m])
                d["note"] = (
                    "gross/net series are excess over rf; net10_minus_spy is vs SPY open-to-open"
                )
            res[w] = d
        return res

    for uni in UNIVERSES:
        results[uni] = {}
        for sig in SIGNALS:
            results[uni][sig] = {kind: stats_for(uni, sig, kind) for kind in BOOKS}

    # ---- alignment check (abort rule) ----
    s_chk = series[("P1000", "MOM_12_1", "LS_RAW")]
    m_st = window_mask(fdates, "stress")
    beta_chk, corr_chk = beta_corr(s_chk["gross"][m_st], spy_ret[m_st])
    lag = {}
    for shift in (-1, 1):
        r_s = np.roll(spy_ret, shift)
        mm = m_st.copy()
        mm[0 if shift == 1 else -1] = False
        lag[f"corr_with_spy_shifted_{shift:+d}"] = beta_corr(s_chk["gross"][mm], r_s[mm])[1]
    yr = pd.DatetimeIndex(fdates).year
    by_year = {
        int(y): beta_corr(s_chk["gross"][m_st & (yr == y)], spy_ret[m_st & (yr == y)])[0]
        for y in sorted(set(yr[m_st]))
    }
    align = {
        "book": "LS_RAW MOM_12_1 P1000, stress window",
        "mean_exante_stock_beta_of_book": float(np.nanmean(s_chk["exante_beta_stocks"][m_st])),
        "realized_beta_by_year": by_year,
        "lagged_spy_correlations": lag,
        "corr_with_spy_monthly": corr_chk,
        "realized_beta": beta_chk,
        "limits": {"abs_corr": SPY_ALIGN_CORR_MAX, "abs_beta": SPY_ALIGN_BETA_MAX},
        "pass": bool(abs(corr_chk) <= SPY_ALIGN_CORR_MAX and abs(beta_chk) <= SPY_ALIGN_BETA_MAX),
    }
    _log(f"alignment check {align}")

    # ---- correlation matrix of the 8 net LS_SN_BH P1000 books ----
    corr_out: dict[str, Any] = {}
    for w in ("anchor", "stress"):
        m = window_mask(fdates, w)
        mat = pd.DataFrame(
            {s: series[("P1000", s, "LS_SN_BH")]["net10"][m] for s in SINGLE_SIGNALS}
        )
        corr_out[w] = {
            "signals": SINGLE_SIGNALS,
            "matrix": mat.corr().round(4).to_numpy().tolist(),
            "mean_offdiag": float(
                (mat.corr().to_numpy().sum() - len(SINGLE_SIGNALS))
                / (len(SINGLE_SIGNALS) ** 2 - len(SINGLE_SIGNALS))
            ),
        }

    # ---- COMBO_EQRISK ----
    scaled = {s: trailing_scaled(series[("P1000", s, "LS_SN_BH")]["net10"]) for s in SINGLE_SIGNALS}
    scaled20 = {
        s: trailing_scaled(series[("P1000", s, "LS_SN_BH")]["net20"]) for s in SINGLE_SIGNALS
    }
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        combo = np.nanmean(np.vstack([scaled[s] for s in SINGLE_SIGNALS]), axis=0)
        combo20 = np.nanmean(np.vstack([scaled20[s] for s in SINGLE_SIGNALS]), axis=0)
    combo_stats = {}
    for w in WINDOWS:
        m = window_mask(fdates, w)
        bt, cr = beta_corr(combo[m], spy_ret[m])
        combo_stats[w] = {
            "net10": series_stats(combo[m]),
            "net20": series_stats(combo20[m]),
            "beta_to_spy": bt,
            "corr_with_spy": cr,
        }
    # equal-weight (no vol scaling) reference
    ew = np.nanmean(
        np.vstack([series[("P1000", s, "LS_SN_BH")]["net10"] for s in SINGLE_SIGNALS]), axis=0
    )
    ew_stats = {w: series_stats(ew[window_mask(fdates, w)]) for w in WINDOWS}

    # ---- placebo ----
    placebo: dict[str, Any] = {}
    for sig in ("COMP4", "CAT_H63"):
        pp_scores = {}
        for k in range(K):
            pp = prepped[("P1000", k)]
            if pp is not None:
                pp_scores[k] = pp["sigs"][sig]
        real = results["P1000"][sig]["LS_SN_BH"]
        draws = {w: {"gross": [], "net10": []} for w in ("stress", "anchor", "all")}
        for seed in range(N_SEEDS):
            rng = np.random.default_rng(SEED0 + seed)
            over = {}
            for k in range(K):
                if k in pp_scores:
                    base = pp_scores[k]
                    sc = np.where(np.isfinite(base), rng.random(len(base)), np.nan)
                    over[k] = sc
                else:
                    over[k] = np.array([])
            s = book_series("P1000", sig, "LS_SN_BH", score_override=over)
            for w in draws:
                m = window_mask(fdates, w)
                draws[w]["gross"].append(series_stats(s["gross"][m]).get("sharpe", np.nan))
                draws[w]["net10"].append(series_stats(s["net10"][m]).get("sharpe", np.nan))
        placebo[sig] = {}
        for w in draws:
            placebo[sig][w] = {}
            for basis in ("gross", "net10"):
                a = np.array(draws[w][basis], dtype="float64")
                r = real[w][basis].get("sharpe", np.nan)
                placebo[sig][w][basis] = {
                    "real_sharpe": r,
                    "placebo_mean": float(np.nanmean(a)),
                    "placebo_std": float(np.nanstd(a, ddof=1)),
                    "placebo_q05": float(np.nanquantile(a, 0.05)),
                    "placebo_q50": float(np.nanquantile(a, 0.50)),
                    "placebo_q95": float(np.nanquantile(a, 0.95)),
                    "beat_rate": float(np.nanmean(a < r)),
                    "n_seeds": int(np.isfinite(a).sum()),
                }
        _log(f"placebo {sig} done ({time.time() - t0:.0f}s)")

    # ---- eligibility counts ----
    elig = {}
    for u in UNIVERSES:
        ns = [0 if prepped[(u, k)] is None else len(prepped[(u, k)]["ids"]) for k in range(K)]
        elig[u] = {
            "mean_eligible_names": float(np.mean(ns)),
            "min": int(np.min(ns)),
            "max": int(np.max(ns)),
        }
    cov = {}
    for u in UNIVERSES:
        cov[u] = {}
        for s in SIGNALS:
            c = [
                int(np.isfinite(prepped[(u, k)]["sigs"][s]).sum())
                if prepped[(u, k)] is not None
                else 0
                for k in range(K)
            ]
            cov[u][s] = float(np.mean(c))

    out = {
        "status": (
            "ok" if (align["pass"] and ret_check["pass"]) else "alignment_rule_tripped_see_checks"
        ),
        "disclaimer": (
            "design-only diagnostic on contaminated data; "
            "not a preregistered iteration; promotes nothing"
        ),
        "coordinator_code": "R1001-0625-S0",
        "design": {
            "formations": [
                str(pd.Timestamp(fdates[0]).date()),
                str(pd.Timestamp(fdates[-1]).date()),
            ],
            "n_formations": int(K),
            "windows": WINDOWS,
            "decile": DECILE,
            "n_size_buckets": N_BUCKETS,
            "cost_per_side_bp": [COST_10 * 1e4, COST_20 * 1e4],
            "borrow_supplementary_bp_per_year": BORROW_ANNUAL * 1e4,
            "nw_lags": NW_LAGS,
            "n_placebo_seeds": N_SEEDS,
            "weights": "long leg +1, short leg -1 (dollar neutral), SPY hedge = -sum(w*beta)",
            "partial_last_period": bool(periods["partial"].iloc[-1]),
        },
        "checks": {
            "prediction_fold_no_lookahead": fold_check,
            "independent_forward_return_check": ret_check,
            "ls_raw_mom_p1000_stress_vs_spy": align,
            "beta_fill_counters": counters,
            "largest_abs_held_return": held_abs_ret_max,
            "held_returns_above_200pct_count": held_big,
            "mean_beta_clipping": "none (raw 252d beta; missing filled with 1.0)",
        },
        "eligibility": elig,
        "mean_signal_coverage": cov,
        "books": results,
        "correlation_p1000_ls_sn_bh_net10": corr_out,
        "placebo_p1000_ls_sn_bh": placebo,
        "combo_eqrisk": combo_stats,
        "combo_reference_equal_weight_no_vol_scaling_net10": ew_stats,
        "runtime_sec": time.time() - t0,
    }
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(json.dumps(_clean(out), indent=1) + "\n")
    # monthly returns cache
    rows = []
    for (uni, sig, kind), s in series.items():
        for k in range(K):
            rows.append(
                {
                    "universe": uni,
                    "signal": sig,
                    "book": kind,
                    "formation_date": fdates[k],
                    "gross": s["gross"][k],
                    "net10": s["net10"][k],
                    "net20": s["net20"][k],
                    "turnover": s["turn"][k],
                    "long_ret": s["long"][k],
                    "short_ret": s["short"][k],
                    "spy_ret": spy_ret[k],
                }
            )
    pd.DataFrame(rows).to_parquet(OUT_DIR / "monthly_returns.parquet")
    if not (align["pass"] and ret_check["pass"]):
        raise SystemExit(
            "ALIGNMENT CHECK FAILED: "
            + json.dumps(_clean({"align": align, "ret_check": ret_check}))
        )
    _log(f"done in {time.time() - t0:.0f}s")


def _clean(o: Any) -> Any:
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def _f(v: Any, nd: int = 2) -> str:
    return "n/a" if v is None else f"{v:.{nd}f}"


def render_tables() -> None:
    """Auto-generated markdown tables from results.json -> report_tables.md."""
    res = json.loads((OUT_DIR / "results.json").read_text())
    lines: list[str] = []
    for uni in UNIVERSES:
        for w in ("anchor", "stress", "gap"):
            lines.append(f"### {uni} / {w}\n")
            lines.append(
                "| signal | book | gross Sh | net10 Sh | net20 Sh | NW t (net10) | ann ret net10 "
                "| ann vol | maxDD | turnover/mo | long ex SPY bp | short ex SPY bp | beta |"
            )
            lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
            for sig in SIGNALS:
                for kind in BOOKS:
                    x = res["books"][uni][sig][kind][w]
                    n10 = x["net10"]
                    lines.append(
                        f"| {sig} | {kind} | {_f(x['gross'].get('sharpe'))} "
                        f"| {_f(n10.get('sharpe'))} "
                        f"| {_f(x['net20'].get('sharpe'))} | {_f(n10.get('nw_t'))} "
                        f"| {_f(n10.get('ann_return'), 3)} | {_f(n10.get('ann_vol'), 3)} "
                        f"| {_f(n10.get('max_dd'), 3)} | {_f(x['avg_monthly_turnover'])} "
                        f"| {_f(x['long_leg_excess_vs_spy_bp'], 0)} "
                        f"| {_f(x['short_leg_excess_vs_spy_bp'], 0)} "
                        f"| {_f(x['realized_beta_to_spy'])} |"
                    )
            lines.append("")
    lines.append("### LONG_ONLY_TOP minus SPY (P1000, net10 information-ratio style Sharpe)\n")
    lines.append("| signal | anchor | stress | gap |")
    lines.append("|---|---|---|---|")
    for sig in SIGNALS:
        row = [
            _f(res["books"]["P1000"][sig]["LONG_ONLY_TOP"][w]["net10_minus_spy"].get("sharpe"))
            for w in ("anchor", "stress", "gap")
        ]
        lines.append(f"| {sig} | " + " | ".join(row) + " |")
    lines.append("")
    for w, c in res["correlation_p1000_ls_sn_bh_net10"].items():
        lines.append(
            f"### Monthly net10 correlation, P1000 LS_SN_BH, {w} "
            f"(mean off-diagonal {_f(c['mean_offdiag'])})\n"
        )
        lines.append("| | " + " | ".join(c["signals"]) + " |")
        lines.append("|---|" + "---|" * len(c["signals"]))
        for name, row in zip(c["signals"], c["matrix"], strict=True):
            lines.append(f"| {name} | " + " | ".join(f"{v:.2f}" for v in row) + " |")
        lines.append("")
    lines.append("### Placebo (100 seeds of random ranks, P1000 LS_SN_BH)\n")
    lines.append(
        "| signal | window | basis | real Sh | placebo mean | q05 | q50 | q95 | beat rate |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for sig, v in res["placebo_p1000_ls_sn_bh"].items():
        for w, b in v.items():
            for basis, x in b.items():
                lines.append(
                    f"| {sig} | {w} | {basis} | {_f(x['real_sharpe'])} | {_f(x['placebo_mean'])} "
                    f"| {_f(x['placebo_q05'])} | {_f(x['placebo_q50'])} | {_f(x['placebo_q95'])} "
                    f"| {_f(x['beat_rate'])} |"
                )
    lines.append("")
    lines.append("### COMBO_EQRISK (8 single-signal P1000 LS_SN_BH net books, 10% vol each)\n")
    lines.append(
        "| window | n | net10 Sh | SE | ann ret | ann vol | NW t | maxDD | net20 Sh | beta "
        "| equal-weight unscaled net10 Sh |"
    )
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for w, c in res["combo_eqrisk"].items():
        n10 = c["net10"]
        ew = res["combo_reference_equal_weight_no_vol_scaling_net10"][w]
        lines.append(
            f"| {w} | {n10.get('n')} | {_f(n10.get('sharpe'))} | {_f(n10.get('sharpe_se'))} "
            f"| {_f(n10.get('ann_return'), 3)} | {_f(n10.get('ann_vol'), 3)} "
            f"| {_f(n10.get('nw_t'))} | {_f(n10.get('max_dd'), 3)} "
            f"| {_f(c['net20'].get('sharpe'))} "
            f"| {_f(c['beta_to_spy'])} | {_f(ew.get('sharpe'))} |"
        )
    (OUT_DIR / "report_tables.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stage", choices=["panel", "books", "all", "tables"])
    args = ap.parse_args()
    if args.stage in ("panel", "all"):
        stage_panel()
    if args.stage in ("books", "all"):
        run_books()
    if args.stage == "tables":
        render_tables()


if __name__ == "__main__":
    main()
