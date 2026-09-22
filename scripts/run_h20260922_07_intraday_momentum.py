"""H-20260922-07: SPY intraday momentum (noise band), the half of H-20260918-02
that was approved and never run.

Published rule (Zarattini, Aziz, Barbon 2024, SSRN 4824172, "Beat the Market"):
a noise band around the session open, width set by how far price has typically
travelled from the open at that time of day over the past 14 sessions and
widened for the overnight gap; go long above the upper bound, short below the
lower bound, trail with the session VWAP, flat at the close. Reported 2007 ->
early 2024: 1985% cumulative, 19.6% annualized, Sharpe 1.33, described as net of
costs. The paper's sample ends where our true out-of-sample begins, so
2024-01-02 onward is untouched by the authors and by us.

Everything the ORB lesson (L-20260918-02) demanded is here: decisions are taken
on a completed minute and filled on the next one, costs are charged per side on
every position change at three levels, and the same three placebos that killed
ORB run against this strategy -- random entry direction, a time-of-day shifted
band, and random long-only days.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT / "data/features/minute_panel"
OUT_DIR = ROOT / "reports/research/iterations/h20260922_07_intraday_momentum"
IS_END = "2023-12-31"
OOS_START = "2024-01-02"
LOOKBACK = 14
COSTS_BPS = (1.0, 2.0, 5.0)
LEVERAGES = (1.0, 2.0, 4.0)


def load_matrices(symbol: str) -> dict:
    d = pd.read_parquet(PANEL / f"{symbol}.parquet")
    d = d.sort_values(["date", "minute"])
    minutes = np.arange(9 * 60 + 30, 16 * 60)
    piv = lambda col: d.pivot_table(index="date", columns="minute", values=col).reindex(  # noqa: E731
        columns=minutes
    )
    close = piv("close")
    dates = close.index
    sess_open = d.groupby("date")["open"].first().reindex(dates)
    last_close = close.ffill(axis=1).iloc[:, -1]
    prev_close = last_close.shift(1)
    return {
        "dates": dates,
        "close": close.to_numpy(float),
        "vwap": piv("vwap").to_numpy(float),
        "open": sess_open.to_numpy(float),
        "prev_close": prev_close.to_numpy(float),
        "minutes": minutes,
    }


def noise_profile(close: np.ndarray, sess_open: np.ndarray, lookback: int) -> np.ndarray:
    """sigma[d, t]: mean |close(t)/open(day) - 1| over the previous `lookback` sessions."""
    move = np.abs(close / sess_open[:, None] - 1.0)
    n, m = move.shape
    out = np.full((n, m), np.nan)
    frame = pd.DataFrame(move)
    roll = frame.rolling(lookback, min_periods=lookback).mean().shift(1)
    out[:] = roll.to_numpy()
    return out


def position_path(
    close: np.ndarray,
    vwap: np.ndarray,
    ub: np.ndarray,
    lb: np.ndarray,
    flip: np.ndarray | None = None,
    mode: str = "persist",
) -> np.ndarray:
    """Target position for each minute, decided on the previous minute's close.

    mode="persist": hold the signed position for as long as price sits outside the
    band, re-entering the moment it does (the literal reading of "long above the
    upper bound").
    mode="cross": enter only on a fresh crossing of the band, and treat the VWAP as
    a trailing stop -- once it fires, that side is locked out for the rest of the
    session until a new crossing event occurs. This is the trailing-stop semantics
    the paper describes and it is what keeps turnover down.
    """
    n, m = close.shape
    pos = np.zeros((n, m))
    for d in range(n):
        c = close[d]
        v = vwap[d]
        u = ub[d]
        low = lb[d]
        if not np.isfinite(u).any():
            continue
        cur = 0.0
        sign = 1.0 if flip is None else float(flip[d])
        above_prev = False
        below_prev = False
        locked_up = False
        locked_dn = False
        for t in range(m - 1):
            price = c[t]
            if not np.isfinite(price):
                break
            above = bool(np.isfinite(u[t]) and price > u[t])
            below = bool(np.isfinite(low[t]) and price < low[t])
            tgt = cur
            if mode == "persist":
                if above:
                    tgt = sign
                elif below:
                    tgt = -sign
            else:
                # a crossing event is an edge, not a level
                if above and not above_prev and not locked_up:
                    tgt = sign
                    locked_dn = False
                elif below and not below_prev and not locked_dn:
                    tgt = -sign
                    locked_up = False
            if tgt > 0 and np.isfinite(v[t]) and price < v[t]:
                tgt = 0.0
                if mode == "cross":
                    locked_up = True
            if tgt < 0 and np.isfinite(v[t]) and price > v[t]:
                tgt = 0.0
                if mode == "cross":
                    locked_dn = True
            pos[d, t + 1] = tgt
            cur = tgt
            above_prev, below_prev = above, below
        # flat at the last traded minute of the session
        valid = np.flatnonzero(np.isfinite(c))
        if len(valid):
            pos[d, valid[-1]] = 0.0
    return pos


def daily_returns(close: np.ndarray, pos: np.ndarray, cost_bps: float, lev: float) -> np.ndarray:
    n, m = close.shape
    r = np.zeros((n, m))
    with np.errstate(invalid="ignore", divide="ignore"):
        r[:, 1:] = close[:, 1:] / close[:, :-1] - 1.0
    r[~np.isfinite(r)] = 0.0
    turn = np.abs(np.diff(pos, axis=1, prepend=0.0))
    step = lev * pos * r - lev * turn * cost_bps / 10_000.0
    return np.prod(1.0 + step, axis=1) - 1.0


def stats(ret: pd.Series, pos: np.ndarray | None = None) -> dict:
    ret = ret.dropna()
    if ret.empty:
        return {}
    eq = (1.0 + ret).cumprod()
    years = len(ret) / 252.0
    vol = float(ret.std(ddof=1) * np.sqrt(252.0))
    out = {
        "days": int(len(ret)),
        "cagr": float(eq.iloc[-1] ** (1.0 / years) - 1.0),
        "vol": vol,
        "sharpe": float(ret.mean() / ret.std(ddof=1) * np.sqrt(252.0))
        if ret.std(ddof=1) > 0
        else np.nan,
        "max_dd": float((eq / eq.cummax() - 1.0).min()),
        "hit_day": float((ret > 0).mean()),
    }
    if pos is not None:
        out["exposure"] = float(np.mean(np.abs(pos) > 0))
        out["trades_day"] = float(
            np.mean(np.sum(np.abs(np.diff(pos, axis=1, prepend=0.0)) > 0, axis=1))
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", default="SPY")
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--entry-mode", default="persist", choices=["persist", "cross"])
    args = ap.parse_args(argv)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    m = load_matrices(args.symbol)
    dates = m["dates"]
    sigma = noise_profile(m["close"], m["open"], LOOKBACK)
    hi_anchor = np.maximum(m["open"], m["prev_close"])[:, None]
    lo_anchor = np.minimum(m["open"], m["prev_close"])[:, None]
    ub = hi_anchor * (1.0 + sigma)
    lb = lo_anchor * (1.0 - sigma)
    print(
        f"{args.symbol}: {len(dates)} sessions, band defined on {np.isfinite(ub).any(1).sum()}",
        flush=True,
    )

    is_mask = dates <= pd.Timestamp(IS_END)
    oos_mask = dates >= pd.Timestamp(OOS_START)

    pos = position_path(m["close"], m["vwap"], ub, lb, mode=args.entry_mode)
    rows = []
    for lev in LEVERAGES:
        for cost in COSTS_BPS:
            ret = pd.Series(daily_returns(m["close"], pos, cost, lev), index=dates)
            for name, mask in (("in_sample", is_mask), ("oos_2024plus", oos_mask)):
                rows.append(
                    {
                        "variant": "real",
                        "leverage": lev,
                        "cost_bps": cost,
                        "window": name,
                        **stats(ret[mask], pos[mask]),
                    }
                )

    # placebo 1: random entry direction per session
    pl = []
    for seed in range(args.seeds):
        rng = np.random.default_rng(20260922 + seed)
        flip = rng.choice([-1.0, 1.0], size=len(dates))
        p = position_path(m["close"], m["vwap"], ub, lb, flip=flip, mode=args.entry_mode)
        for lev in (1.0,):
            ret = pd.Series(daily_returns(m["close"], p, 1.0, lev), index=dates)
            for name, mask in (("in_sample", is_mask), ("oos_2024plus", oos_mask)):
                pl.append(
                    {
                        "placebo": "random_direction",
                        "seed": seed,
                        "window": name,
                        **stats(ret[mask]),
                    }
                )
        print(f"  placebo random_direction seed {seed} done", flush=True)

    # placebo 2: band profile shifted 30 minutes later in the day
    shift = 30
    sig_shift = np.roll(sigma, shift, axis=1)
    sig_shift[:, :shift] = np.nan
    p2 = position_path(
        m["close"],
        m["vwap"],
        hi_anchor * (1.0 + sig_shift),
        lo_anchor * (1.0 - sig_shift),
        mode=args.entry_mode,
    )
    for name, mask in (("in_sample", is_mask), ("oos_2024plus", oos_mask)):
        ret = pd.Series(daily_returns(m["close"], p2, 1.0, 1.0), index=dates)
        pl.append({"placebo": "band_shift_30min", "seed": 0, "window": name, **stats(ret[mask])})

    # placebo 3: long all day on a random subset of sessions matched to real exposure
    exposure = float(np.mean(np.abs(pos) > 0))
    for seed in range(args.seeds):
        rng = np.random.default_rng(777 + seed)
        take = rng.random(len(dates)) < exposure
        p3 = np.zeros_like(pos)
        p3[take, :-1] = 1.0
        ret = pd.Series(daily_returns(m["close"], p3, 1.0, 1.0), index=dates)
        for name, mask in (("in_sample", is_mask), ("oos_2024plus", oos_mask)):
            pl.append(
                {"placebo": "random_days_long", "seed": seed, "window": name, **stats(ret[mask])}
            )

    real = pd.DataFrame(rows)
    plc = pd.DataFrame(pl)
    real["entry_mode"] = args.entry_mode
    plc["entry_mode"] = args.entry_mode
    suffix = "" if args.entry_mode == "persist" else f"-{args.entry_mode}"
    real.to_parquet(OUT_DIR / f"cells{suffix}.parquet")
    plc.to_parquet(OUT_DIR / "placebo.parquet")

    base = real[(real.leverage == 1.0) & (real.cost_bps == 1.0)].set_index("window")
    beat = {}
    for kind in plc.placebo.unique():
        sub = plc[(plc.placebo == kind) & (plc.window == "oos_2024plus")]
        beat[kind] = float((sub.cagr > base.loc["oos_2024plus", "cagr"]).mean())
    summary = {
        "iter_id": "h20260922_07_intraday_momentum",
        "card_id": "H-20260922-07",
        "symbol": args.symbol,
        "sessions": int(len(dates)),
        "published": {
            "cagr": 0.196,
            "sharpe": 1.33,
            "sample": "2007..early 2024",
            "source": "SSRN 4824172",
        },
        "placebo_beat_oos": beat,
        "cells": real.to_dict("records"),
        "placebos": plc.to_dict("records"),
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, indent=2, default=float) + "\n")
    print(real.round(3).to_string(index=False))
    print("\nplacebo medians (leverage 1, 1 bp):")
    print(plc.groupby(["placebo", "window"]).cagr.median().round(4).to_string())
    print("\nplacebo beat fraction on OOS CAGR:", beat)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
