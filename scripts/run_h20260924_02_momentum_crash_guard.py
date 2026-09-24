#!/usr/bin/env python3
"""H-20260924-02: does a DAILY crash guard on the T1 12-1 momentum book clear
the frozen G1-G5 gates and beat a calendar-shift placebo of its own multiplier
series?

Card: ``reports/research/hypotheses/H-20260924-02-momentum-crash-guard.md``.
Dossier: ``reports/research/iterations/h20260924_02_momentum_crash_guard/``.

The T1 book (top 30 of the largest 500 names by 12-1 momentum, overlapping
20-session cohorts) is reproduced unchanged from
``open_composer.research.signal_card`` (``load_market``, ``load_signal``,
``topk_cohorts``, ``hold``, ``book_returns``); this script only adds a daily
[0,1] exposure multiplier on top of it, remainder in SHY. Window/cost/Sharpe
conventions (select/holdout/anchor, 10bp/20bp, RF=BIL excess Sharpe) are
reused unchanged from ``scripts/run_h20260918_05_recent_menu.py`` (imported
as ``base``, the same pattern ``scripts/run_h20260923_11_s3_bear_guard.py``
uses) for exact consistency with the rest of the frozen giants-sweep family.

Timing discipline (see decision-record.md for the full derivation): a guard
multiplier ``m[s]`` must be decided using information known strictly before
``open[s]`` (i.e. through ``close[s-1]``).

* Signals derived from an ordinary close-to-close series (SPY's own returns,
  for CG-DM and CG-MKT-STOP) use the standard 1-session settlement lag:
  ``close[s-1]`` is known at ``close[s-1]``.
* Signals derived from the T1 book's OWN return series use a 2-session
  settlement lag. The book's return series is open-to-open
  (``ret[i] = open[i+1]/open[i]-1``, per ``Market.next_open_returns``), so
  ``ret[i]`` (and thus ``gross[i] = held[i]*ret[i]``) is not actually known
  until ``open[i+1]`` -- one session later than a naive reading of "row i"
  suggests. The latest book-return observation safely known by
  ``close[s-1]`` is therefore ``gross[s-2]``, not ``gross[s-1]``.

Five candidates (candidate-manifest.json), one path
(``momentum_crash_guard_t1_daily``):

CG-DM         Daniel & Moskowitz (2016) bear+high-vol panic gate (binary).
CG-BSC-daily  Barroso & Santa-Clara (2015) realized-vol scaling, updated
              daily on the book's own returns, capped at 1.0.
CG-STOP       Book-level drawdown circuit breaker, fixed SMA-50 re-entry.
CG-DM-BSC     Product of CG-DM and CG-BSC-daily.
CG-MKT-STOP   SEC's published 7% Level-1 market-wide-circuit-breaker trigger
              on SPY, fixed-duration re-entry.

Every threshold is either a published value or computed ONLY on the
2016-01-04..2023-09-15 development window (intersected with the book's own
return history, which starts 2017-01-03 -- disclosed, never extended into
select/holdout/anchor).

    scripts/run_capped.sh --mem 1.5G -- uv run python \\
        scripts/run_h20260924_02_momentum_crash_guard.py
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import run_h20260918_05_recent_menu as base  # noqa: E402

from open_composer.research.signal_card import (  # noqa: E402
    Market,
    book_returns,
    hold,
    load_market,
    load_signal,
    topk_cohorts,
)

ITER_ID = "h20260924_02_momentum_crash_guard"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
CACHE_DIR = OUT_DIR / "cache"

TOP_N = 500  # tier-1 upper edge; loading exactly top_n=500 gives the same
# tier-1 universe/prices as top_n=3000 (adv_rank is precomputed upstream and
# unaffected by this filter) with far less memory -- verified in report.md.
TOP_K = 30
HOLD_SESSIONS = 20
PRIMARY_BPS = 10.0
STRESS_BPS = 20.0

DEV_START = "2016-01-04"
DEV_END = "2023-09-15"

PANEL_START = "2013-06-03"  # >504 sessions before DEV_START, for the 24-month lookback
PANEL_END = base.HOLD_END

BEAR_WINDOW_SESSIONS = 504  # ~24 months, Daniel & Moskowitz (2016)
VOL_WINDOW_SESSIONS = 126  # Barroso & Santa-Clara (2015); also DM's market variance window
SMA_REENTRY_SESSIONS = 50
MWCB_LEVEL1 = -0.07  # published, SEC/NYSE Level-1 market-wide circuit breaker
MWCB_FALLBACK_REENTRY_SESSIONS = 5
STOP_DD_MULT = 1.5
STOP_DD_SCALE = 0.5
STOP_DD_MIN = 0.12
STOP_DD_MAX = 0.30

N_SHIFTS = 20

GATE_G1_CAGR = 0.50
GATE_G1_MAXDD = -0.35
GATE_G1ALT_SHARPE = 2.0
GATE_G1ALT_CAGR = 0.30
GATE_G2_SHARPE = 1.0
GATE_G3_PLACEBO = 0.10

NOTES_ANCHOR_CAGR = 0.598
NOTES_ANCHOR_MAXDD = -0.416
CARD_FULLWINDOW_CAGR = 0.265
CARD_FULLWINDOW_MAXDD = -0.502
REPRO_TOL = 0.01


# --------------------------------------------------------------------- data


def load_book() -> tuple[Market, np.ndarray, np.ndarray, np.ndarray]:
    """Reproduce the T1 book unchanged. Returns (market, held, ret, signal)."""
    market = load_market(top_n=TOP_N)
    signal = load_signal(
        market, source="data/features/daily_broad", column="momentum_252_21", lag=0
    )
    member = market.member((1, TOP_N))
    cohorts = topk_cohorts(signal, member, TOP_K)
    held = hold(cohorts, HOLD_SESSIONS)
    ret = market.next_open_returns()
    return market, held, ret, signal


def load_side_panel(symbols: list[str], start: str, end: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Open/close panel for a small symbol set from the SIP daily archive."""
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='500MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, open, close, volume, trade_count
        FROM read_parquet('data/sip/daily/*/*.parquet')
        WHERE symbol IN ({in_list}) AND timestamp::DATE >= DATE '{start}'
              AND timestamp::DATE <= DATE '{end}'
        ORDER BY symbol, d
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    close = frame.pivot(index="d", columns="symbol", values="close").sort_index()
    open_ = frame.pivot(index="d", columns="symbol", values="open").sort_index()
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    return close, open_


# ------------------------------------------------------------- settlement


def settle_market(series: pd.Series) -> pd.Series:
    """1-session lag: value known at close(t-1) is available for a decision at open(t)."""
    return series.shift(1)


def settle_book(series: pd.Series) -> pd.Series:
    """2-session lag for a statistic built on the book's own open-to-open return
    series -- see the module docstring and decision-record.md."""
    return series.shift(2)


# ------------------------------------------------------------------ signals


def spy_bear_indicator(spy_close: pd.Series, window: int = BEAR_WINDOW_SESSIONS) -> pd.Series:
    """True (raw, unsettled) if SPY's trailing ``window``-session return < 0."""
    trailing_ret = spy_close / spy_close.shift(window) - 1.0
    return trailing_ret < 0.0


def realized_vol(returns: pd.Series, window: int = VOL_WINDOW_SESSIONS) -> pd.Series:
    """Annualized realized vol: sqrt(252 * mean(r^2)) over a trailing window,
    Barroso & Santa-Clara's (2015) formula (raw squared returns, no demeaning)."""
    return np.sqrt(252.0 * (returns**2).rolling(window, min_periods=window).mean())


def book_drawdown(net_returns: pd.Series) -> tuple[pd.Series, pd.Series]:
    equity = (1.0 + net_returns.fillna(0.0)).cumprod()
    dd = equity / equity.cummax() - 1.0
    return dd, equity


# ------------------------------------------------------------- thresholds


@dataclass
class Thresholds:
    dm_highvol: float
    bsc_target_vol: float
    stop_dd: float
    mkt_stop_reentry_sessions: int
    mkt_stop_reentry_from_data: bool


def dev_mask(index: pd.DatetimeIndex) -> np.ndarray:
    return (index >= DEV_START) & (index <= DEV_END)


def fit_thresholds(
    spy_close: pd.Series,
    base_net_10bp: pd.Series,
) -> Thresholds:
    dmask = dev_mask(spy_close.index)
    spy_vol_raw = realized_vol(spy_close.pct_change())
    dm_highvol = float(spy_vol_raw[dmask].dropna().median())

    book_vol_raw = realized_vol(base_net_10bp)
    bmask = dev_mask(book_vol_raw.index)
    bsc_target_vol = float(book_vol_raw[bmask].dropna().median())

    dd_raw, _ = book_drawdown(base_net_10bp)
    dmask_dd = dev_mask(dd_raw.index)
    dev_dd_series = dd_raw[dmask_dd].dropna()
    dev_max_dd_mag = float(abs(dev_dd_series.min())) if len(dev_dd_series) else 0.0
    stop_dd = float(
        np.clip(STOP_DD_MULT * dev_max_dd_mag * STOP_DD_SCALE, STOP_DD_MIN, STOP_DD_MAX)
    )

    spy_ret_raw = spy_close.pct_change()
    dmask_spy = dev_mask(spy_ret_raw.index)
    dev_spy_ret = spy_ret_raw[dmask_spy]
    trigger_dates = dev_spy_ret.index[dev_spy_ret <= MWCB_LEVEL1]
    recoveries: list[int] = []
    close_vals = spy_close
    for d in trigger_dates:
        i = close_vals.index.get_loc(d)
        if i == 0:
            continue
        pre_drop_close = close_vals.iloc[i - 1]
        after = close_vals.iloc[i + 1 :]
        recovered = after[after >= pre_drop_close]
        if len(recovered):
            j = close_vals.index.get_loc(recovered.index[0])
            recoveries.append(j - i)
    if len(recoveries) >= 3:
        n_sessions = int(round(float(np.median(recoveries))))
        n_sessions = max(1, n_sessions)
        from_data = True
    else:
        n_sessions = MWCB_FALLBACK_REENTRY_SESSIONS
        from_data = False

    return Thresholds(
        dm_highvol=dm_highvol,
        bsc_target_vol=bsc_target_vol,
        stop_dd=stop_dd,
        mkt_stop_reentry_sessions=n_sessions,
        mkt_stop_reentry_from_data=from_data,
    )


# ----------------------------------------------------------------- guards


def guard_cg_dm(spy_close: pd.Series, thresholds: Thresholds) -> np.ndarray:
    # Booleans are cast to float before shift()/fillna() so the first (NaN)
    # rows never force an object-dtype downcast warning.
    bear_raw = spy_bear_indicator(spy_close).astype(float)
    vol_raw = realized_vol(spy_close.pct_change())
    highvol_raw = (vol_raw > thresholds.dm_highvol).astype(float)
    bear_settled = settle_market(bear_raw).fillna(0.0).to_numpy()
    highvol_settled = settle_market(highvol_raw).fillna(0.0).to_numpy()
    panic = (bear_settled > 0.5) & (highvol_settled > 0.5)
    return np.where(panic, 0.0, 1.0)


def guard_cg_bsc_daily(base_net_10bp: pd.Series, thresholds: Thresholds) -> np.ndarray:
    vol_raw = realized_vol(base_net_10bp)
    vol_settled = settle_book(vol_raw).to_numpy(dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        raw_ratio = thresholds.bsc_target_vol / vol_settled
    m = np.where(np.isfinite(raw_ratio), np.clip(raw_ratio, 0.0, 1.0), 1.0)
    return m


def guard_cg_stop(base_net_10bp: pd.Series, thresholds: Thresholds) -> np.ndarray:
    dd_raw, equity_raw = book_drawdown(base_net_10bp)
    sma_raw = equity_raw.rolling(SMA_REENTRY_SESSIONS, min_periods=SMA_REENTRY_SESSIONS).mean()
    dd_settled = settle_book(dd_raw).to_numpy(dtype=float)
    equity_settled = settle_book(equity_raw).to_numpy(dtype=float)
    sma_settled = settle_book(sma_raw).to_numpy(dtype=float)
    T = len(dd_settled)
    m = np.ones(T, dtype=float)
    triggered = False
    for t in range(T):
        if not np.isfinite(dd_settled[t]):
            m[t] = 1.0
            continue
        if not triggered:
            if dd_settled[t] <= -thresholds.stop_dd:
                triggered = True
        else:
            if np.isfinite(equity_settled[t]) and np.isfinite(sma_settled[t]):
                if equity_settled[t] >= sma_settled[t]:
                    triggered = False
        m[t] = 0.0 if triggered else 1.0
    return m


def guard_cg_mkt_stop(spy_close: pd.Series, thresholds: Thresholds) -> np.ndarray:
    spy_ret_raw = spy_close.pct_change()
    spy_ret_settled = settle_market(spy_ret_raw).to_numpy(dtype=float)
    T = len(spy_ret_settled)
    m = np.ones(T, dtype=float)
    cooldown = 0
    n = thresholds.mkt_stop_reentry_sessions
    for t in range(T):
        if np.isfinite(spy_ret_settled[t]) and spy_ret_settled[t] <= MWCB_LEVEL1:
            cooldown = n
        if cooldown > 0:
            m[t] = 0.0
            cooldown -= 1
        else:
            m[t] = 1.0
    return m


def guard_cg_dm_bsc(
    spy_close: pd.Series, base_net_10bp: pd.Series, thresholds: Thresholds
) -> np.ndarray:
    return guard_cg_dm(spy_close, thresholds) * guard_cg_bsc_daily(base_net_10bp, thresholds)


GUARD_BUILDERS = {
    "cg_dm": lambda spy_close, base_net_10bp, th: guard_cg_dm(spy_close, th),
    "cg_bsc_daily": lambda spy_close, base_net_10bp, th: guard_cg_bsc_daily(base_net_10bp, th),
    "cg_stop": lambda spy_close, base_net_10bp, th: guard_cg_stop(base_net_10bp, th),
    "cg_dm_bsc": lambda spy_close, base_net_10bp, th: guard_cg_dm_bsc(spy_close, base_net_10bp, th),
    "cg_mkt_stop": lambda spy_close, base_net_10bp, th: guard_cg_mkt_stop(spy_close, th),
}


# --------------------------------------------------------------- returns


def guarded_net_returns(
    held: np.ndarray, ret: np.ndarray, m: np.ndarray, cash_ret: np.ndarray, cost_bps: float
) -> tuple[np.ndarray, np.ndarray]:
    scaled_held = held * m[:, None]
    net, turnover = book_returns(scaled_held, ret, cost_bps)
    cash = np.where(np.isfinite(cash_ret), cash_ret, 0.0)
    final = net + (1.0 - m) * cash
    return final, turnover


def calendar_shift(m: np.ndarray, k: int) -> np.ndarray:
    """Shift by k sessions (k in 1..20), non-circular, padded with full
    exposure (1.0, i.e. no guard) at the leading edge."""
    if k <= 0:
        return m.copy()
    out = np.ones_like(m)
    out[k:] = m[: len(m) - k]
    return out


# --------------------------------------------------------------- metrics


def window_mask(index: pd.DatetimeIndex, start: str, end: str) -> np.ndarray:
    return (index >= start) & (index <= end)


def metrics_dict(m: base.Metrics) -> dict:
    return {
        "days": m.days,
        "cagr": m.cagr,
        "vol": m.vol,
        "sharpe": m.sharpe,
        "max_dd": m.max_dd,
        "turnover_yr": m.turnover_yr,
    }


def evaluate_series(
    net: np.ndarray, turnover: np.ndarray, index: pd.DatetimeIndex, rf: pd.Series
) -> dict:
    s_net = pd.Series(net, index=index)
    s_turn = pd.Series(turnover, index=index)
    out = {name: metrics_dict(m) for name, m in base.window_metrics(s_net, rf, s_turn).items()}
    dmask = window_mask(index, DEV_START, DEV_END)
    out["stress_dev"] = metrics_dict(base.metrics(s_net.loc[dmask], rf, s_turn.loc[dmask]))
    return out


# ----------------------------------------------------------------- gates


def apply_gates(metrics_10bp: dict, metrics_20bp: dict, g3_beat_frac: float) -> dict:
    a10 = metrics_10bp["anchor"]
    a20 = metrics_20bp["anchor"]
    h10 = metrics_10bp["holdout"]
    g1 = bool(
        a10["cagr"] is not None
        and a10["max_dd"] is not None
        and a10["cagr"] >= GATE_G1_CAGR
        and a10["max_dd"] >= GATE_G1_MAXDD
    )
    g1alt = bool(
        a10["sharpe"] is not None
        and a10["cagr"] is not None
        and a10["sharpe"] >= GATE_G1ALT_SHARPE
        and a10["cagr"] >= GATE_G1ALT_CAGR
    )
    g2 = bool(
        h10["sharpe"] is not None
        and h10["cagr"] is not None
        and h10["sharpe"] >= GATE_G2_SHARPE
        and h10["cagr"] > 0
    )
    g3 = bool(np.isfinite(g3_beat_frac) and g3_beat_frac <= GATE_G3_PLACEBO)
    g4 = bool(
        (
            a20["cagr"] is not None
            and a20["max_dd"] is not None
            and a20["cagr"] >= GATE_G1_CAGR
            and a20["max_dd"] >= GATE_G1_MAXDD
        )
        or (
            a20["sharpe"] is not None
            and a20["cagr"] is not None
            and a20["sharpe"] >= GATE_G1ALT_SHARPE
            and a20["cagr"] >= GATE_G1ALT_CAGR
        )
    )
    g5 = True
    passed = bool((g1 or g1alt) and g2 and g3 and g4 and g5)
    return {
        "G1": g1,
        "G1_alt": g1alt,
        "G2": g2,
        "G3": g3,
        "G4": g4,
        "G5": g5,
        "PASS": passed,
        "g3_beat_frac": g3_beat_frac,
    }


# ------------------------------------------------------------------- main


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Runs to completion in one pass (all vectorized numpy on a ~2700x500 "
            "matrix plus a handful of O(T) Python loops for the two stateful "
            "guards); there is no partial-cache resume mode to invoke."
        )
    )
    ap.parse_args(argv)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    print("[1/6] loading T1 book ...", flush=True)
    market, held, ret, signal = load_book()
    dates = market.dates
    print(
        f"  market: {len(dates)} sessions, {len(market.symbols)} symbols, "
        f"{dates[0].date()}..{dates[-1].date()}",
        flush=True,
    )

    print("[2/6] base book reproduction ...", flush=True)
    base_net_10bp, base_turn_10bp = book_returns(held, ret, PRIMARY_BPS)
    base_net_20bp, base_turn_20bp = book_returns(held, ret, STRESS_BPS)
    s_base10 = pd.Series(base_net_10bp, index=dates)
    s_base20 = pd.Series(base_net_20bp, index=dates)

    full_mask = np.isfinite(base_net_20bp) & (held.sum(axis=1) > 0)
    full_active = pd.Series(full_mask, index=dates)
    full_idx = full_active[full_active].index
    full_start, full_end = full_idx.min(), full_idx.max()
    rf_full = pd.Series(0.0, index=dates)  # signal card's own perf() has no rf term
    full_perf_20bp = base.metrics(
        s_base20.loc[full_start:full_end],
        rf_full,
        pd.Series(base_turn_20bp, index=dates).loc[full_start:full_end],
    )

    anchor_mask = window_mask(dates, base.ANCHOR_START, base.ANCHOR_END)
    anchor_idx = dates[anchor_mask]

    print("[3/6] loading SPY/SHY/BIL side panel ...", flush=True)
    close, open_ = load_side_panel(["SPY", "SHY", "BIL"], PANEL_START, PANEL_END)
    for sym in ("SPY", "SHY", "BIL"):
        missing = dates.difference(close.index)
        if len(missing):
            raise RuntimeError(
                f"{sym}: {len(missing)} market.dates sessions missing from the SIP daily "
                f"panel (e.g. {missing[:3].tolist()}); refusing to forward-fill "
                "(data_assumptions.forward_fill_allowed=false)."
            )
    spy_close_full = close["SPY"]
    spy_close = close["SPY"].reindex(dates)
    shy_open = open_["SHY"].reindex(dates)
    bil_close = close["BIL"].reindex(dates)
    shy_next_open = np.full(len(dates), np.nan)
    shy_open_vals = shy_open.to_numpy(dtype=float)
    shy_next_open[:-1] = shy_open_vals[1:] / shy_open_vals[:-1] - 1.0
    rf = bil_close.pct_change().fillna(0.0)

    print("[4/6] fitting development-window thresholds ...", flush=True)
    thresholds = fit_thresholds(spy_close_full.loc[:DEV_END], s_base10)
    print(f"  thresholds: {thresholds}", flush=True)

    print("[5/6] building guards and evaluating gates ...", flush=True)
    rows = []
    guard_multipliers = {}
    per_candidate_metrics = {}
    for cand_id, builder in GUARD_BUILDERS.items():
        m = builder(spy_close, s_base10, thresholds)
        guard_multipliers[cand_id] = m
        net10, turn10 = guarded_net_returns(held, ret, m, shy_next_open, PRIMARY_BPS)
        net20, turn20 = guarded_net_returns(held, ret, m, shy_next_open, STRESS_BPS)
        metrics10 = evaluate_series(net10, turn10, dates, rf)
        metrics20 = evaluate_series(net20, turn20, dates, rf)

        real_anchor_sharpe = metrics10["anchor"]["sharpe"]
        beats = 0
        valid_shifts = 0
        for k in range(1, N_SHIFTS + 1):
            m_shift = calendar_shift(m, k)
            snet10, sturn10 = guarded_net_returns(held, ret, m_shift, shy_next_open, PRIMARY_BPS)
            s_series = pd.Series(snet10, index=dates).loc[anchor_idx]
            s_turn_series = pd.Series(sturn10, index=dates).loc[anchor_idx]
            shifted_metrics = base.metrics(s_series, rf.loc[anchor_idx], s_turn_series)
            if shifted_metrics.sharpe is not None and not np.isnan(shifted_metrics.sharpe):
                valid_shifts += 1
                if real_anchor_sharpe is not None and shifted_metrics.sharpe >= real_anchor_sharpe:
                    beats += 1
        g3_beat_frac = beats / valid_shifts if valid_shifts else float("nan")

        gates = apply_gates(metrics10, metrics20, g3_beat_frac)
        per_candidate_metrics[cand_id] = {"10bp": metrics10, "20bp": metrics20, "gates": gates}
        rows.append(
            {
                "candidate_id": cand_id,
                "anchor_cagr_10bp": metrics10["anchor"]["cagr"],
                "anchor_max_dd_10bp": metrics10["anchor"]["max_dd"],
                "anchor_sharpe_10bp": metrics10["anchor"]["sharpe"],
                "anchor_cagr_20bp": metrics20["anchor"]["cagr"],
                "anchor_max_dd_20bp": metrics20["anchor"]["max_dd"],
                "anchor_sharpe_20bp": metrics20["anchor"]["sharpe"],
                "holdout_sharpe_10bp": metrics10["holdout"]["sharpe"],
                "holdout_cagr_10bp": metrics10["holdout"]["cagr"],
                "stress_dev_cagr_10bp": metrics10["stress_dev"]["cagr"],
                "stress_dev_max_dd_10bp": metrics10["stress_dev"]["max_dd"],
                "stress_dev_sharpe_10bp": metrics10["stress_dev"]["sharpe"],
                "g3_beat_frac": g3_beat_frac,
                **gates,
            }
        )
        print(
            f"  {cand_id}: anchor CAGR {metrics10['anchor']['cagr']:.1%} "
            f"DD {metrics10['anchor']['max_dd']:.1%} Sharpe {metrics10['anchor']['sharpe']:.2f} "
            f"| PASS={gates['PASS']}",
            flush=True,
        )

    print("[6/6] caching + writing results ...", flush=True)
    base_cache = pd.DataFrame(
        {
            "date": dates,
            "net_10bp": base_net_10bp,
            "net_20bp": base_net_20bp,
            "turnover_10bp": base_turn_10bp,
            "turnover_20bp": base_turn_20bp,
        }
    )
    base_cache.to_parquet(CACHE_DIR / "base_book_returns.parquet", index=False)

    mult_cache = pd.DataFrame({"date": dates, **guard_multipliers})
    mult_cache.to_parquet(CACHE_DIR / "guard_multipliers.parquet", index=False)

    results = {
        "iter_id": ITER_ID,
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "market": {
            "sessions": int(len(dates)),
            "symbols": int(len(market.symbols)),
            "date_range": [str(dates[0].date()), str(dates[-1].date())],
        },
        "base_book": {
            "full_window": {
                "start": str(full_start.date()),
                "end": str(full_end.date()),
                "20bp": metrics_dict(full_perf_20bp),
                "card_reference": {"cagr": CARD_FULLWINDOW_CAGR, "max_dd": CARD_FULLWINDOW_MAXDD},
                "within_tolerance": bool(
                    full_perf_20bp.cagr is not None
                    and abs(full_perf_20bp.cagr - CARD_FULLWINDOW_CAGR) <= REPRO_TOL
                    and full_perf_20bp.max_dd is not None
                    and abs(full_perf_20bp.max_dd - CARD_FULLWINDOW_MAXDD) <= REPRO_TOL
                ),
            },
            "anchor": {
                "10bp": metrics_dict(
                    base.metrics(
                        s_base10.loc[anchor_idx],
                        rf.loc[anchor_idx],
                        pd.Series(base_turn_10bp, index=dates).loc[anchor_idx],
                    )
                ),
                "20bp": metrics_dict(
                    base.metrics(
                        s_base20.loc[anchor_idx],
                        rf.loc[anchor_idx],
                        pd.Series(base_turn_20bp, index=dates).loc[anchor_idx],
                    )
                ),
                "notes_reference": {"cagr": NOTES_ANCHOR_CAGR, "max_dd": NOTES_ANCHOR_MAXDD},
            },
        },
        "thresholds": {
            "dm_highvol": thresholds.dm_highvol,
            "bsc_target_vol": thresholds.bsc_target_vol,
            "stop_dd": thresholds.stop_dd,
            "mkt_stop_reentry_sessions": thresholds.mkt_stop_reentry_sessions,
            "mkt_stop_reentry_from_data": thresholds.mkt_stop_reentry_from_data,
        },
        "candidates": per_candidate_metrics,
        "trial_ledger_rows": rows,
    }
    (OUT_DIR / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )
    pd.DataFrame(rows).to_parquet(CACHE_DIR / "trial_results.parquet", index=False)
    print("wrote", OUT_DIR / "results.json", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
