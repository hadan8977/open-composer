"""T-20260929-81: IPO aftermarket calendar event study (A: quiet-period expiry
long window, B: post-first-week pop short window), per the frozen protocol in
``reports/research/iterations/h20260929_81_ipo_aftermarket/protocol-preregistration.md``
and ``direction-review.json``.

Reuses the T-21 event table, price loader (``load_event_stock_panel`` ->
``sanitize_price_matrices`` defaults), trading calendar and cost tiers from
``scripts/run_h20260929_21_lockup_books.py`` without modifying it.

Usage::

    scripts/run_capped.sh --mem 1.5G -- uv run python \\
        scripts/run_h20260929_81_ipo_aftermarket.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

ITER_ID = "h20260929_81_ipo_aftermarket"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
EVENTS_PATH = ROOT / "reports/research/iterations/h20260929_21_ipo_lockup_expiry/events.parquet"
DAILY_BROAD_DIR = ROOT / "data" / "features" / "daily_broad"
DAILY_GLOB = str(ROOT / "data/sip/daily/*/*.parquet")

# ---- frozen numbers (protocol-preregistration.md / queue block) -------------------------
QP_CALENDAR_DAYS = 26
D10_CALENDAR_DAYS = 11
MAX_FIRST_TRADE_LAG_DAYS = 7
MIN_FIRST_CLOSE = 5.0
MIN_MEDIAN_DOLLAR_VOLUME = 5_000_000.0
FIRST_WINDOW_SESSIONS = 10
MIN_VALID_VOLUME_SESSIONS = 5
ADV_LOOKBACK_SESSIONS = 21
ADV_POOL_RANK = 1500
R5_SHORT_MIN = 0.20
R5_LONG_MAX = -0.10
A_K = (2, 5)
B_HOLDS = (20, 40)
SPREAD_BPS_TIERS = [(500, 3.0), (1000, 6.0), (1500, 12.0), (float("inf"), 25.0)]
BORROW_TOP1500 = 0.03
BORROW_BEYOND = 0.25
BORROW_DAYCOUNT = 360.0
RECENT_START = pd.Timestamp("2024-01-01")
SHIFTS = (10, -10, 60, -60)
N_RANDOM = 200
RANDOM_SEED = 20260930
RANDOM_LOW, RANDOM_HIGH = 12, 250
# gates
A_POOLED_MEAN_MIN = 0.01
A_POOLED_T_MIN = 2.5
A_RECENT_N_MIN = 100
A_RECENT_MEAN_MIN = 0.01
A_PLACEBO_FRACTION_MAX = 0.5
B_RECENT_MEAN_MIN = 0.03
B_RECENT_T_MIN = 2.0
TRIALS_FOR_DSR = 12


def _log(msg: str, t0: float) -> None:
    print(f"[{ITER_ID}] {msg} ({time.monotonic() - t0:.0f}s)", flush=True)


# --------------------------------------------------------------------------
# pure helpers (unit tested)
# --------------------------------------------------------------------------


def qp_index(dates: pd.DatetimeIndex, first_idx: int, calendar_days: int = QP_CALENDAR_DAYS) -> int:
    """Index of the first session with date >= dates[first_idx] + calendar_days
    (Bradley-Jordan-Ritter day 0: the 26th calendar day or the first trading day
    thereafter). Returns -1 when the target is past the calendar end."""
    target = dates[first_idx] + pd.Timedelta(days=calendar_days)
    pos = int(dates.searchsorted(target, side="left"))
    return pos if pos < len(dates) else -1


def tier_bps(rank: float) -> float:
    if not np.isfinite(rank):
        return SPREAD_BPS_TIERS[-1][1]
    for threshold, bps in SPREAD_BPS_TIERS:
        if rank <= threshold:
            return bps
    return SPREAD_BPS_TIERS[-1][1]


def borrow_rate(rank: float) -> float:
    return BORROW_TOP1500 if np.isfinite(rank) and rank <= ADV_POOL_RANK else BORROW_BEYOND


def clustered_mean_t(values: np.ndarray, clusters: np.ndarray) -> dict:
    """Mean and cluster-robust t of the mean (one-way clusters, G/(G-1) correction)."""
    v = np.asarray(values, dtype=float)
    keep = np.isfinite(v)
    v = v[keep]
    c = np.asarray(clusters)[keep]
    n = len(v)
    if n == 0:
        return {"n": 0, "n_clusters": 0, "mean": None, "t": None}
    m = float(v.mean())
    codes, _ = pd.factorize(c)
    g = int(codes.max()) + 1 if n else 0
    if n < 2 or g < 2:
        return {"n": n, "n_clusters": g, "mean": m, "t": None}
    sums = np.bincount(codes, weights=v - m, minlength=g)
    se = float(np.sqrt((sums**2).sum()) / n * np.sqrt(g / (g - 1)))
    return {"n": n, "n_clusters": g, "mean": m, "t": (m / se) if se > 0 else None}


def window_returns(
    open_ev: np.ndarray,
    close_ev: np.ndarray,
    entry: np.ndarray,
    exit_: np.ndarray,
) -> np.ndarray:
    """Per-event open[entry] -> close[exit] return; NaN for out-of-range/missing."""
    n, t = open_ev.shape
    out = np.full(n, np.nan)
    ok = (entry >= 0) & (exit_ < t) & (exit_ >= entry) & (entry < t) & (exit_ >= 0)
    rows = np.flatnonzero(ok)
    with np.errstate(invalid="ignore", divide="ignore"):
        out[rows] = close_ev[rows, exit_[rows]] / open_ev[rows, entry[rows]] - 1.0
    out[~np.isfinite(out)] = np.nan
    return out


def bench_window_returns(
    bench_open: np.ndarray, bench_close: np.ndarray, entry: np.ndarray, exit_: np.ndarray
) -> np.ndarray:
    """Equal-weight QQQ/IWM open[entry] -> close[exit] return, per event."""
    t = bench_open.shape[1]
    out = np.full(len(entry), np.nan)
    ok = (entry >= 0) & (exit_ < t) & (exit_ >= entry) & (entry < t)
    idx = np.flatnonzero(ok)
    with np.errstate(invalid="ignore", divide="ignore"):
        legs = bench_close[:, exit_[idx]] / bench_open[:, entry[idx]] - 1.0
    out[idx] = legs.mean(axis=0)
    return out


def calendar_days_between(
    dates: pd.DatetimeIndex, entry: np.ndarray, exit_: np.ndarray
) -> np.ndarray:
    d = dates.values.astype("datetime64[D]")
    out = np.full(len(entry), np.nan)
    ok = (entry >= 0) & (exit_ < len(d)) & (exit_ >= entry)
    idx = np.flatnonzero(ok)
    out[idx] = (d[exit_[idx]] - d[entry[idx]]).astype(float)
    return out


def leave_out_top_winners(net_short: np.ndarray, n_drop: int = 3) -> float | None:
    v = np.sort(np.asarray(net_short, dtype=float)[np.isfinite(net_short)])
    if len(v) <= n_drop:
        return None
    return float(v[:-n_drop].mean())


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------


def load_volume(symbols: list[str], calendar: pd.DatetimeIndex) -> pd.DataFrame:
    import duckdb

    con = duckdb.connect()
    con.execute("SET memory_limit='600MB'")
    con.execute("SET threads=2")
    in_list = ",".join(f"'{s}'" for s in symbols)
    frame = con.execute(
        f"""
        SELECT symbol, timestamp::DATE AS d, volume, trade_count
        FROM read_parquet('{DAILY_GLOB}')
        WHERE symbol IN ({in_list})
        """
    ).df()
    con.close()
    ghost = (frame["volume"].fillna(0) <= 0) & (frame["trade_count"].fillna(0) <= 0)
    frame = frame.loc[~ghost]
    frame["d"] = pd.to_datetime(frame["d"])
    vol = frame.pivot_table(index="d", columns="symbol", values="volume", aggfunc="last")
    return vol.reindex(calendar)


def load_benchmarks(calendar: pd.DatetimeIndex) -> tuple[np.ndarray, np.ndarray, dict]:
    import run_h20260918_05_recent_menu as base
    import screen_lane

    from open_composer.research.features.price_hygiene import sanitize_price_matrices

    base.WARMUP_START = screen_lane.PANEL_START
    base.HOLD_END = "2026-09-30"
    close, open_ = base.load_panel(["QQQ", "IWM"])
    close, open_, report = sanitize_price_matrices(close, open_)
    close = close.reindex(calendar)
    open_ = open_.reindex(calendar)
    b_open = np.vstack([open_["QQQ"].to_numpy(), open_["IWM"].to_numpy()])
    b_close = np.vstack([close["QQQ"].to_numpy(), close["IWM"].to_numpy()])
    return b_open, b_close, {"breaks": len(report.breaks), "symbols_masked": report.symbols_masked}


def adv_cross_section_ranks(
    signal_dates: dict[pd.Timestamp, list[tuple[int, float]]],
) -> dict[tuple[int, pd.Timestamp], float]:
    """rank = 1 + #symbols with daily_broad dollar_adv_21 > proxy, on the date.
    ``signal_dates[date]`` = list of (key, proxy). Returns {(key, date): rank}."""
    out: dict[tuple[int, pd.Timestamp], float] = {}
    years = sorted({d.year for d in signal_dates})
    for year in years:
        f = pd.read_parquet(
            DAILY_BROAD_DIR / f"{year}.parquet", columns=["trade_date", "dollar_adv_21"]
        )
        f = f.dropna(subset=["dollar_adv_21"])
        wanted = {d for d in signal_dates if d.year == year}
        f = f.loc[f["trade_date"].isin(wanted)]
        for d, grp in f.groupby("trade_date"):
            arr = np.sort(grp["dollar_adv_21"].to_numpy())
            for key, proxy in signal_dates[pd.Timestamp(d)]:
                if np.isfinite(proxy):
                    out[(key, pd.Timestamp(d))] = float(
                        len(arr) - np.searchsorted(arr, proxy, side="right") + 1
                    )
        del f
    return out


# --------------------------------------------------------------------------
# main analysis
# --------------------------------------------------------------------------


def build_sample(events: pd.DataFrame, calendar, open_p, close_p, vol_p, counts: dict):
    """Attach first-trading-day index and eligibility; returns list of dict rows."""
    ev = events.loc[(events["method"] == "424b4_confirmed") & (~events["is_despac"])].copy()
    counts["events_total"] = int(len(events))
    counts["424b4_confirmed_non_despac"] = int(len(ev))
    dates = calendar
    rows = []
    drop = {
        "no_price_data_for_symbol": 0,
        "no_first_session_within_7d": 0,
        "first_close_below_5": 0,
        "median_dollar_volume_below_5m_or_missing": 0,
        "qp_past_data_end": 0,
    }
    for r in ev.itertuples(index=False):
        sym = r.symbol
        if sym not in close_p.columns:
            drop["no_price_data_for_symbol"] += 1
            continue
        c = close_p[sym].to_numpy()
        o = open_p[sym].to_numpy()
        start = int(dates.searchsorted(pd.Timestamp(r.ipo_date), side="left"))
        valid = np.flatnonzero(np.isfinite(c[start:]) & np.isfinite(o[start:]))
        if len(valid) == 0:
            drop["no_first_session_within_7d"] += 1
            continue
        f = start + int(valid[0])
        if (dates[f] - pd.Timestamp(r.ipo_date)).days > MAX_FIRST_TRADE_LAG_DAYS:
            drop["no_first_session_within_7d"] += 1
            continue
        if not c[f] >= MIN_FIRST_CLOSE:
            drop["first_close_below_5"] += 1
            continue
        v = (
            vol_p[sym].to_numpy()[f : f + FIRST_WINDOW_SESSIONS]
            if sym in vol_p.columns
            else np.array([])
        )
        dv = v * c[f : f + FIRST_WINDOW_SESSIONS][: len(v)]
        dv = dv[np.isfinite(dv)]
        if len(dv) < MIN_VALID_VOLUME_SESSIONS or np.median(dv) < MIN_MEDIAN_DOLLAR_VOLUME:
            drop["median_dollar_volume_below_5m_or_missing"] += 1
            continue
        q = qp_index(dates, f, QP_CALENDAR_DAYS)
        if q < 0:
            drop["qp_past_data_end"] += 1
            continue
        q10 = qp_index(dates, f, D10_CALENDAR_DAYS)
        rows.append(
            {
                "symbol": sym,
                "ipo_date": pd.Timestamp(r.ipo_date),
                "f": f,
                "q": q,
                "q10": q10,
                "first_close": float(c[f]),
                "is_first_session_lag_days": int((dates[f] - pd.Timestamp(r.ipo_date)).days),
            }
        )
    counts["drops"] = drop
    counts["eligible_events"] = len(rows)
    return pd.DataFrame(rows)


def main() -> None:
    from run_h20260929_21_lockup_books import load_event_stock_panel, load_trading_calendar

    t0 = time.monotonic()
    calendar = load_trading_calendar()
    T = len(calendar)
    events = pd.read_parquet(EVENTS_PATH)
    t21_summary = json.loads(
        (
            ROOT / "reports/research/iterations/h20260929_21_ipo_lockup_expiry/build_summary.json"
        ).read_text()
    )
    symbols = sorted(events.loc[events["method"] == "424b4_confirmed", "symbol"].unique())
    _log(f"{len(events)} events, {len(symbols)} confirmed symbols", t0)
    panel = load_event_stock_panel(symbols, calendar)
    close_p, open_p = panel["close"], panel["open"]
    hygiene = panel["hygiene_report"]
    vol_p = load_volume(symbols, calendar)
    b_open, b_close, bench_hygiene = load_benchmarks(calendar)
    _log("panels loaded", t0)

    counts: dict = {"t21_build_summary": t21_summary}
    sample = build_sample(events, calendar, open_p, close_p, vol_p, counts)
    n = len(sample)
    _log(f"eligible events {n}; drops {counts['drops']}", t0)

    # per-event matrices
    OPN = np.vstack([open_p[s].to_numpy() for s in sample["symbol"]])
    C = np.vstack([close_p[s].to_numpy() for s in sample["symbol"]])
    V = np.vstack(
        [
            vol_p[s].to_numpy() if s in vol_p.columns else np.full(T, np.nan)
            for s in sample["symbol"]
        ]
    )
    DV = C * V
    f = sample["f"].to_numpy()
    q = sample["q"].to_numpy()
    q10 = sample["q10"].to_numpy()
    ipo_dates = sample["ipo_date"].to_numpy()

    # R5
    r5 = window_returns(OPN, C, f, f + 4)

    # signal sessions per window type
    sig = {"A": q - 3, "A_ctl": q - 2, "D10": q10 - 3, "B": f + 4}

    def proxy_at(sig_idx: np.ndarray) -> np.ndarray:
        out = np.full(n, np.nan)
        for i in range(n):
            s = int(sig_idx[i])
            if s < 0 or s >= T:
                continue
            lo = max(int(f[i]), s - ADV_LOOKBACK_SESSIONS + 1)
            w = DV[i, lo : s + 1]
            w = w[np.isfinite(w)]
            if len(w):
                out[i] = float(np.median(w))
        return out

    proxies = {k: proxy_at(v) for k, v in sig.items()}
    want: dict[pd.Timestamp, list[tuple[int, float]]] = {}
    keyed = {"A": 0, "A_ctl": 1, "D10": 2, "B": 3}
    for kname, kidx in keyed.items():
        for i in range(n):
            s = int(sig[kname][i])
            if 0 <= s < T and np.isfinite(proxies[kname][i]):
                want.setdefault(calendar[s], []).append((kidx * 100000 + i, proxies[kname][i]))
    ranks_raw = adv_cross_section_ranks(want)
    _log(f"ADV ranks computed for {len(ranks_raw)} (event, window) pairs", t0)
    ranks = {k: np.full(n, np.nan) for k in sig}
    for kname, kidx in keyed.items():
        for i in range(n):
            s = int(sig[kname][i])
            if 0 <= s < T:
                ranks[kname][i] = ranks_raw.get((kidx * 100000 + i, calendar[s]), np.nan)

    cluster = pd.factorize(ipo_dates)[0]

    def year_of(idx: np.ndarray) -> np.ndarray:
        out = np.full(n, 0)
        ok = (idx >= 0) & (idx < T)
        out[ok] = calendar.year.to_numpy()[idx[ok]]
        return out

    def recent_mask(idx: np.ndarray) -> np.ndarray:
        ok = (idx >= 0) & (idx < T)
        m = np.zeros(n, dtype=bool)
        m[ok] = calendar.values[idx[ok]] >= np.datetime64(RECENT_START)
        return m

    bps = {k: np.array([tier_bps(x) for x in ranks[k]]) for k in ranks}
    borrow = {k: np.array([borrow_rate(x) for x in ranks[k]]) for k in ranks}
    pool_mask = {
        k: {
            "all": np.ones(n, dtype=bool),
            "adv1500": np.isfinite(ranks[k]) & (ranks[k] <= ADV_POOL_RANK),
        }
        for k in ranks
    }

    def stats(vals: np.ndarray, mask: np.ndarray) -> dict:
        m = mask & np.isfinite(vals)
        d = clustered_mean_t(vals[m], cluster[m])
        d["hit_rate"] = float((vals[m] > 0).mean()) if m.any() else None
        return d

    def by_year(
        vals_net: np.ndarray, vals_gross: np.ndarray, mask: np.ndarray, entry_idx: np.ndarray
    ) -> dict:
        ys = year_of(entry_idx)
        out = {}
        for y in sorted(set(ys[mask & np.isfinite(vals_net)])):
            mm = mask & np.isfinite(vals_net) & (ys == y)
            out[str(int(y))] = {
                "n": int(mm.sum()),
                "mean_gross_car": float(vals_gross[mm].mean()),
                "mean_net": float(vals_net[mm].mean()),
                "hit_rate_net": float((vals_net[mm] > 0).mean()),
            }
        return out

    # ---------------- A family --------------------------------------------------
    def a_car(sig_kind: str, k: int, shift: int = 0, q_override: np.ndarray | None = None):
        qq = q_override if q_override is not None else q
        entry_off = -2 if sig_kind == "A" else -1
        ent = qq + entry_off + shift
        ex = qq + k + shift
        stock = window_returns(OPN, C, ent, ex)
        bench = bench_window_returns(b_open, b_close, ent, ex)
        return stock - bench, ent, ex

    results: dict = {
        "iter_id": ITER_ID,
        "counts": counts,
        "hygiene": {
            "stock_panel_symbols_masked": int(hygiene.symbols_masked),
            "stock_panel_breaks": len(hygiene.breaks),
            "benchmark": bench_hygiene,
        },
    }
    results["n_eligible"] = n
    results["eligible_by_first_session_year"] = {
        str(int(y)): int(c_)
        for y, c_ in pd.Series(calendar.year.to_numpy()[f]).value_counts().sort_index().items()
    }
    a_res: dict = {}
    pooled_real_mean: dict[str, float] = {}
    for kind, kk, role in [("A", 2, "decision"), ("A", 5, "decision"), ("A_ctl", 2, "control")]:
        car, ent, ex = a_car(kind, kk)
        for pool in ("all", "adv1500"):
            cid = f"A_QP3_k{kk}_{pool}" if kind == "A" else f"A_QP2_k{kk}_{pool}_control"
            key = "A" if kind == "A" else "A_ctl"
            net = car - 2.0 * bps[key] / 1e4
            mask = pool_mask[key][pool] & np.isfinite(car)
            rec = recent_mask(ent)
            cell = {
                "role": role,
                "pooled_gross": stats(car, mask),
                "pooled_net": stats(net, mask),
                "recent_2024plus_net": stats(net, mask & rec),
                "recent_2024plus_gross": stats(car, mask & rec),
                "by_entry_year": by_year(net, car, mask, ent),
                "n_dropped_missing_price_or_beyond_end": int(
                    (pool_mask[key][pool] & ~np.isfinite(car)).sum()
                ),
            }
            # placebos for the pooled net mean
            pl = {}
            for s in SHIFTS:
                pcar, _, _ = a_car(kind, kk, shift=s)
                pnet = pcar - 2.0 * bps[key] / 1e4
                pl[f"shift_{s:+d}"] = stats(pnet, pool_mask[key][pool] & np.isfinite(pcar))
            rng = np.random.default_rng(RANDOM_SEED + kk)
            draws = []
            for _ in range(N_RANDOM):
                rq = f + rng.integers(RANDOM_LOW, RANDOM_HIGH + 1, size=n)
                pcar, _, _ = a_car(kind, kk, q_override=rq)
                pnet = pcar - 2.0 * bps[key] / 1e4
                mm = pool_mask[key][pool] & np.isfinite(pcar)
                draws.append(float(pnet[mm].mean()) if mm.any() else np.nan)
            d = np.array(draws)
            real_m = cell["pooled_net"]["mean"]
            pl["random_date"] = {
                "n_draws": N_RANDOM,
                "mean_of_means": float(np.nanmean(d)),
                "p95_of_means": float(np.nanpercentile(d, 95)),
                "fraction_draws_ge_real_pooled_net_mean": float(np.nanmean(d >= real_m))
                if real_m is not None
                else None,
            }
            cell["placebos"] = pl
            a_res[cid] = cell
            pooled_real_mean[cid] = real_m
    results["A"] = a_res

    # D10 diagnostic (non-gating): QP10 windows, k=2
    d10 = {}
    ent10 = q10 - 2
    ex10 = q10 + 2
    car10 = window_returns(OPN, C, ent10, ex10) - bench_window_returns(b_open, b_close, ent10, ex10)
    for pool in ("all", "adv1500"):
        net10 = car10 - 2.0 * bps["D10"] / 1e4
        mask = pool_mask["D10"][pool] & np.isfinite(car10)
        d10[pool] = {
            "pooled_gross": stats(car10, mask),
            "pooled_net": stats(net10, mask),
            "recent_2024plus_net": stats(net10, mask & recent_mask(ent10)),
            "by_entry_year": by_year(net10, car10, mask, ent10),
        }
    results["D10_diagnostic_non_gating"] = d10

    # ---------------- B and C ---------------------------------------------------
    b_res: dict = {}
    ent_b = f + 5
    for h in B_HOLDS:
        ex_b = f + 5 + h - 1
        stock = window_returns(OPN, C, ent_b, ex_b)
        bench = bench_window_returns(b_open, b_close, ent_b, ex_b)
        cal_days = calendar_days_between(calendar, ent_b, ex_b)
        cost = 2.0 * bps["B"] / 1e4
        brw = borrow["B"] * cal_days / BORROW_DAYCOUNT
        net_short = -stock - cost - brw  # raw short
        net_short_hedged = -(stock - bench) - cost - brw
        long_net = stock - cost  # for C
        long_net_hedged = (stock - bench) - cost
        for pool in ("all", "adv1500"):
            base_mask = pool_mask["B"][pool] & np.isfinite(stock) & np.isfinite(r5)
            popped = base_mask & (r5 >= R5_SHORT_MIN)
            rec = recent_mask(ent_b)
            cid = f"B_R5ge20_h{h}_{pool}"
            top3 = leave_out_top_winners(net_short[popped & rec], 3)
            b_res[cid] = {
                "role": "decision" if h == 20 else "informational_h40",
                "pooled_net_short_raw": stats(net_short, popped),
                "recent_2024plus_net_short_raw": stats(net_short, popped & rec),
                "recent_2024plus_net_short_hedged": stats(net_short_hedged, popped & rec),
                "recent_2024plus_gross_short_raw": stats(-stock, popped & rec),
                "recent_2024plus_mean_after_dropping_top3_winners": top3,
                "pooled_mean_after_dropping_top3_winners": leave_out_top_winners(
                    net_short[popped], 3
                ),
                "by_entry_year_raw": by_year(net_short, -stock, popped, ent_b),
                "mean_borrow_cost_recent": float(brw[popped & rec].mean())
                if (popped & rec).any()
                else None,
                "mean_round_trip_cost_recent": float(cost[popped & rec].mean())
                if (popped & rec).any()
                else None,
            }
            # baseline: all eligible shorted (no R5 filter)
            b_res[f"baseline_all_eligible_short_h{h}_{pool}"] = {
                "role": "baseline_non_candidate",
                "pooled_net_short_raw": stats(net_short, base_mask),
                "recent_2024plus_net_short_raw": stats(net_short, base_mask & rec),
            }
            # C mirror: R5 <= -10 long
            crash = base_mask & (r5 <= R5_LONG_MAX)
            b_res[f"C_mirror_R5le-10_long_h{h}_{pool}"] = {
                "role": "mirror_non_candidate",
                "pooled_net_long_raw": stats(long_net, crash),
                "recent_2024plus_net_long_raw": stats(long_net, crash & rec),
                "recent_2024plus_net_long_hedged": stats(long_net_hedged, crash & rec),
            }
    results["B_C"] = b_res

    # ---------------- gates ------------------------------------------------------
    gates: list[dict] = []

    def add(fam, cand, name, value, thr, op, passed):
        gates.append(
            {
                "family": fam,
                "candidate": cand,
                "condition": name,
                "value": value,
                "threshold": thr,
                "op": op,
                "passed": bool(passed),
            }
        )

    a_pass = {}
    for kk in A_K:
        for pool in ("all", "adv1500"):
            cid = f"A_QP3_k{kk}_{pool}"
            cell = a_res[cid]
            pm, pt = cell["pooled_net"]["mean"], cell["pooled_net"]["t"]
            rn, rm = cell["recent_2024plus_net"]["n"], cell["recent_2024plus_net"]["mean"]
            c1 = pm is not None and pm >= A_POOLED_MEAN_MIN
            c2 = pt is not None and pt >= A_POOLED_T_MIN
            c3 = rn >= A_RECENT_N_MIN
            c4 = rm is not None and rm >= A_RECENT_MEAN_MIN
            add("A", cid, "pooled 2016-2026 net mean CAR >= +1.0%", pm, A_POOLED_MEAN_MIN, ">=", c1)
            add("A", cid, "pooled clustered t >= 2.5", pt, A_POOLED_T_MIN, ">=", c2)
            add("A", cid, "entries from 2024 n >= 100", rn, A_RECENT_N_MIN, ">=", c3)
            add(
                "A", cid, "entries from 2024 net mean CAR >= +1.0%", rm, A_RECENT_MEAN_MIN, ">=", c4
            )
            c5 = True
            for s in (10, -10):
                pv = cell["placebos"][f"shift_{s:+d}"]["mean"]
                lim = A_PLACEBO_FRACTION_MAX * pm if pm is not None else None
                ok = pv is not None and lim is not None and pv <= lim
                add(
                    "A",
                    cid,
                    f"shift {s:+d} sessions placebo net mean <= 0.5 x real pooled net mean",
                    pv,
                    lim,
                    "<=",
                    ok,
                )
                c5 = c5 and ok
            a_pass[cid] = bool(c1 and c2 and c3 and c4 and c5)
    b_pass = {}
    for pool in ("all", "adv1500"):
        cid = f"B_R5ge20_h20_{pool}"
        cell = b_res[cid]
        rm, rt = (
            cell["recent_2024plus_net_short_raw"]["mean"],
            cell["recent_2024plus_net_short_raw"]["t"],
        )
        t3 = cell["recent_2024plus_mean_after_dropping_top3_winners"]
        c1 = rm is not None and rm >= B_RECENT_MEAN_MIN
        c2 = rt is not None and rt >= B_RECENT_T_MIN
        c3 = t3 is not None and t3 > 0
        add(
            "B",
            cid,
            "entries from 2024 20-session net short mean >= +3%",
            rm,
            B_RECENT_MEAN_MIN,
            ">=",
            c1,
        )
        add("B", cid, "entries from 2024 clustered t >= 2", rt, B_RECENT_T_MIN, ">=", c2)
        add("B", cid, "mean after dropping the 3 largest winners > 0", t3, 0.0, ">", c3)
        b_pass[cid] = bool(c1 and c2 and c3)
    results["gate_checks"] = gates
    results["candidate_pass"] = {"A": a_pass, "B": b_pass}
    results["family_pass"] = {"A": any(a_pass.values()), "B": any(b_pass.values())}
    results["registered_candidates"] = 10
    results["dsr_trials_if_any_family_passes"] = TRIALS_FOR_DSR
    results["verdict"] = (
        "IPO aftermarket calendar windows closed"
        if not any(results["family_pass"].values())
        else "at least one family cleared the event-study gate; screen that family only"
    )
    results["defects"] = {
        "r5_pop_proxy": (
            "R5 = first-session open to 5th-session close (no offer price locally); "
            "not the offer-to-close pop used in the literature"
        ),
        "adv_proxy_inflated_by_ipo_week_volume": True,
        "hedge_leg_cost_not_charged": True,
        "borrow_availability_for_new_issues_unknown": True,
        "windows_with_missing_exit_price_dropped_survivorship": True,
        "finra_2241_quiet_period_is_10_days_since_2015_12_24": True,
    }
    out = ITER_DIR / "results.json"
    out.write_text(
        json.dumps(results, indent=1, default=lambda o: None if o is None else float(o)) + "\n"
    )
    _log(f"wrote {out}; verdict: {results['verdict']}", t0)


if __name__ == "__main__":
    main()
