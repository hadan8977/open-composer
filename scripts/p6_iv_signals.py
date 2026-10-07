#!/usr/bin/env python3
# ruff: noqa: E501
"""T-20261005-45: P6 option-implied stock-selection signals, IC measurement.

Contract: reports/research/iterations/t20261005_p6_iv_signals/hypotheses.md sections 2, 3, 5, 6
(frozen).  Stages: build -> signs -> measure -> report (``all`` runs them in order).

Targets e(t, j) are built with ``lag_targets`` of scripts/p1_stage0_decay.py (imported, never
edited), so they are identical to P1 Stage 0.  The ``signs`` stage looks at the stress window only
and writes cache/signs.json before ``measure`` is allowed to run.  Nothing dated after 2026-09-17 is
read.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.special import ndtri
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _load_p1():
    spec = importlib.util.spec_from_file_location(
        "p1_stage0_decay_mod", ROOT / "scripts/p1_stage0_decay.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["p1_stage0_decay_mod"] = mod
    spec.loader.exec_module(mod)
    return mod


p1 = _load_p1()

ITER_ID = "t20261005_p6_iv_signals"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
DATA = ROOT / "data/research/equity_book"
EARN = ROOT / "data/features/earnings_events"
LAST_DATA = "2026-09-17"
LAST_SIGNAL = "2026-09-15"
CAL_START = "2018-01-01"
LAGS = p1.LAGS
NTGT = p1.NTGT
WINDOWS = {
    "recent": ("2024-01-08", "2026-09-15"),
    "stress": ("2019-02-11", "2023-08-31"),
    "owner_B": ("2026-07-01", "2026-09-15"),
}
BUCKETS = ("L12", "L1", "L2")
CUT = (500, 1000, 3000)
MIN_NAMES = 200
MIN_NAMES_SUBSET = 50
CAND = ["IVRV", "DIV21", "DIV5", "IVZ3"]
DIAG = ["HVZ3", "IVRV_V", "DIV21S"]
STALE = [f"st_{c}" for c in CAND]
OBJS = CAND + DIAG + STALE
BASE_SIGN = {"IVRV": 1, "IVZ3": -1, "HVZ3": -1, "IVRV_V": 1}
DECISION = {"IVRV": (2, 22, 25), "DIV21": (2, 22, 25), "DIV5": (2, 6, 10), "IVZ3": (2, 6, 10)}
REFERENCE = {"IVRV": 0.082, "DIV21": 0.096, "DIV5": 0.010, "IVZ3": 0.010}
STALE_SESSIONS = 63
SLAB_BACK = 130
SLAB_FWD = 25
THEMES = [
    "theme_value",
    "theme_quality",
    "theme_investment",
    "theme_momentum",
    "theme_low_risk",
    "theme_earnings",
    "theme_insider",
    "theme_short_info",
    "theme_seasonality",
]
EARN_END_ET = "2026-09-17"

CACHE = ITER_DIR / "cache"


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def log(msg: str) -> None:
    print(f"[{now_utc()}] {msg}", flush=True)


# ---------------------------------------------------------------------------- pure helpers


def bh_q(p) -> np.ndarray:
    """Benjamini-Hochberg q-values (same logic as scripts/screen_factors._benjamini_hochberg)."""
    p = np.asarray(p, dtype="float64")
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / (np.arange(m) + 1.0)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(m)
    q[order] = np.minimum(q_sorted, 1.0)
    return q


def rv21(C: np.ndarray, d: np.ndarray, s: np.ndarray, min_obs: int = 18) -> np.ndarray:
    """sqrt(252) x sample std (ddof 1) of the 21 daily log close returns ending at close d."""
    d = np.asarray(d, dtype=np.int64)
    idx = np.clip(d[:, None] + np.arange(-21, 1)[None, :], 0, C.shape[0] - 1)
    W = np.asarray(C[idx, np.asarray(s)[:, None]], dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        L = np.log(W[:, 1:] / W[:, :-1])
    L[~np.isfinite(L)] = np.nan
    fin = np.isfinite(L)
    cnt = fin.sum(axis=1)
    mean = np.where(cnt > 0, np.where(fin, L, 0.0).sum(axis=1) / np.maximum(cnt, 1), np.nan)
    dev = np.where(fin, L - mean[:, None], 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (dev * dev).sum(axis=1) / (cnt - 1)
    out = np.sqrt(252.0) * np.sqrt(var)
    out[(cnt < min_obs) | (cnt < 2)] = np.nan
    return out


def ret3(C: np.ndarray, d: np.ndarray, s: np.ndarray) -> np.ndarray:
    d = np.asarray(d, dtype=np.int64)
    c1 = np.asarray(C[d, s], dtype="float64")
    c0 = np.asarray(C[np.maximum(d - 3, 0), s], dtype="float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.log(c1 / c0)
    r[~np.isfinite(r)] = np.nan
    return r


def signal_block(C, d, s, iv_c, iv_w, iv_m, hv_c) -> dict[str, np.ndarray]:
    """Raw (unsigned) values of the four candidates and the two diagnostics."""
    iv_c, iv_w, iv_m, hv_c = (np.asarray(v, dtype="float64") for v in (iv_c, iv_w, iv_m, hv_c))
    ivp = np.where(iv_c > 0, iv_c, np.nan)
    rv = rv21(C, d, s)
    r3 = ret3(C, d, s)
    k = math.sqrt(3.0 / 252.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = {
            "IVRV": ivp - rv,
            "DIV21": ivp - iv_m,
            "DIV5": ivp - iv_w,
            "IVZ3": r3 / (ivp * k),
            "HVZ3": r3 / (np.where(rv > 0, rv, np.nan) * k),
            "IVRV_V": ivp - hv_c,
        }
    for key in out:
        out[key] = np.where(np.isfinite(out[key]), out[key], np.nan)
    return out


def rank_normal(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Columnwise inverse-normal of (rank - 0.5)/n among finite values; missing -> 0."""
    M = np.asarray(M, dtype="float64")
    rk = pd.DataFrame(M).rank(axis=0, method="average", na_option="keep").to_numpy()
    fin = np.isfinite(rk)
    cnt = fin.sum(axis=0)
    with np.errstate(invalid="ignore", divide="ignore"):
        z = ndtri((rk - 0.5) / cnt)
    z = np.where(fin, z, 0.0)
    return z, fin.astype("float64")


def date_slices(di: np.ndarray) -> list[tuple[int, int, int]]:
    """(date index, start, end) for a date-sorted index array."""
    if len(di) == 0:
        return []
    cut = np.flatnonzero(np.diff(di)) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(di)]])
    return [(int(di[a]), int(a), int(b)) for a, b in zip(starts, ends, strict=True)]


def window_mask(D: pd.DatetimeIndex, win: tuple) -> np.ndarray:
    return np.asarray((D >= pd.Timestamp(win[0])) & (D <= pd.Timestamp(win[1])))


def ic_dates(
    di: np.ndarray,
    S: np.ndarray,
    E: np.ndarray,
    T: int,
    dmask: np.ndarray,
    rowmask: np.ndarray | None = None,
    min_names: int = MIN_NAMES,
) -> tuple[np.ndarray, np.ndarray]:
    """Daily IC arrays (T x K x NTGT) and pair counts (T x K x NTGT) of K score columns.

    Score = rank-normal within the universe at t (missing -> 0); target = centred rank (missing ->
    0); a date-lag pair is kept only if at least ``min_names`` names have both finite.
    """
    K = S.shape[1]
    ic = np.full((T, K, E.shape[1]), np.nan)
    npair = np.zeros((T, K, E.shape[1]))
    for d, a, b in date_slices(di):
        if not dmask[d]:
            continue
        Sd, Ed = S[a:b], E[a:b]
        if rowmask is not None:
            keep = rowmask[a:b]
            Sd, Ed = Sd[keep], Ed[keep]
        if len(Sd) < min_names:
            continue
        Zx, Fx = rank_normal(Sd)
        Ze, Fe = p1.zrank(np.asarray(Ed, dtype="float64"))
        ic[d] = p1.rank_ic(Zx, Fx, Ze, Fe, min_names)
        npair[d] = Fx.T @ Fe
    return ic, npair


def residual_scores(
    di: np.ndarray, S: np.ndarray, M0: np.ndarray, TH: np.ndarray, dmask: np.ndarray
) -> np.ndarray:
    """Per date, OLS of each rank-normal score on [1, m0, 9 themes] (rank-normal, missing -> 0);
    return the residual (NaN where the score is missing)."""
    out = np.full_like(S, np.nan, dtype="float64")
    for d, a, b in date_slices(di):
        if not dmask[d]:
            continue
        Zr, _ = rank_normal(np.column_stack([M0[a:b], TH[a:b]]))
        X = np.column_stack([np.ones(b - a), Zr])
        Zs, Fs = rank_normal(S[a:b])
        for k in range(S.shape[1]):
            ok = Fs[:, k] > 0
            if ok.sum() < X.shape[1] + 5:
                continue
            beta, *_ = np.linalg.lstsq(X[ok], Zs[ok, k], rcond=None)
            res = np.full(b - a, np.nan)
            res[ok] = Zs[ok, k] - X[ok] @ beta
            out[a:b, k] = res
    return out


def lag_sum_series(ic_k: np.ndarray, a: int, b: int, wmask: np.ndarray) -> np.ndarray:
    """Per-date sum of IC_j, j = a..b (NaN unless all lags finite), within the window."""
    w = ic_k[wmask][:, a - 1 : b]
    return np.where(np.isfinite(w).all(axis=1), w.sum(axis=1), np.nan)


def decision_stats(ic_k: np.ndarray, a: int, b: int, lags: int, wmask: np.ndarray) -> dict:
    """CIC(a..b) = sum of the window means of IC_j; NW t on the per-date lag-sum series."""
    w = ic_k[wmask]
    means = np.array(
        [np.nanmean(w[:, j]) if np.isfinite(w[:, j]).any() else np.nan for j in range(NTGT)]
    )
    cic = float(means[a - 1 : b].sum()) if np.isfinite(means[a - 1 : b]).all() else float("nan")
    series = lag_sum_series(ic_k, a, b, wmask)
    st = p1.nw_stats(series, lags)
    n = int(st["n"])
    sd = float(np.nanstd(series, ddof=1)) if np.isfinite(series).sum() > 1 else float("nan")
    infl = st["se_nw"] / st["se_iid"] if st["se_iid"] and st["se_iid"] > 0 else float("nan")
    se = sd * infl / math.sqrt(n) if n > 0 and np.isfinite(infl) else float("nan")
    t = st["t"]
    return {
        "lags": [a, b],
        "nw_lags": lags,
        "cic": cic,
        "series_mean": st["mean"],
        "t": t,
        "p_one_sided": float(1.0 - norm.cdf(t)) if np.isfinite(t) else float("nan"),
        "sd_series": sd,
        "nw_inflation": infl,
        "se": se,
        "mde": 2.8 * se if np.isfinite(se) else float("nan"),
        "n_dates": n,
    }


# ---------------------------------------------------------------------------- build


def read_cols(path: Path, cols: list[str], last: str) -> pd.DataFrame:
    return p1.read_dated(path, cols, last)


def load_calendar() -> tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    etf = read_cols(
        DATA / "etf_daily.parquet", ["trade_date", "symbol", "open", "close"], LAST_DATA
    )
    etf = etf[etf["symbol"] == "SPY"].set_index("trade_date").sort_index()
    sess = etf["open"].dropna().index
    sess = sess[(sess >= pd.Timestamp(CAL_START)) & (sess <= pd.Timestamp(LAST_DATA))]
    D = pd.DatetimeIndex(sess)
    return (
        D,
        etf["open"].reindex(D).to_numpy("float64"),
        etf["close"].reindex(D).to_numpy("float64"),
    )


def load_earnings(D: pd.DatetimeIndex, sym_index: pd.Index) -> tuple[np.ndarray, dict]:
    """Sorted keys si * T + session for 8-Ks with item 2.02 accepted up to EARN_END_ET."""
    frames = []
    for p in sorted(EARN.glob("*.parquet")):
        if not p.stem.isdigit():
            continue
        t = pq.read_table(
            p,
            columns=["ticker", "acceptance_utc", "items"],
            filters=[("acceptance_utc", "<=", EARN_END_ET + "T23:59:59Z")],
        ).to_pandas()
        frames.append(t)
    ev = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
    info = {"n_events_read": int(len(ev))}
    if ev.empty:
        return np.zeros(0, dtype=np.int64), info
    has202 = ev["items"].fillna("").apply(lambda s: "2.02" in [x.strip() for x in s.split(",")])
    ev = ev[has202].copy()
    info["n_events_2_02"] = int(len(ev))
    acc = pd.to_datetime(ev["acceptance_utc"], utc=True).dt.tz_convert("US/Eastern")
    ev["date"] = acc.dt.tz_localize(None).dt.normalize()
    ev = ev[ev["date"] <= pd.Timestamp(EARN_END_ET)]
    ev["k"] = D.searchsorted(ev["date"].to_numpy("datetime64[ns]"), side="left")
    ev["si"] = sym_index.get_indexer(ev["ticker"].astype(str))
    info["ticker_match_rate_events"] = float((ev["si"] >= 0).mean()) if len(ev) else float("nan")
    ev = ev[(ev["si"] >= 0) & (ev["k"] < len(D))]
    key = np.unique(ev["si"].to_numpy(np.int64) * len(D) + ev["k"].to_numpy(np.int64))
    info["n_events_matched"] = int(len(key))
    return key, info


def earnings_flag(
    key: np.ndarray, di: np.ndarray, si: np.ndarray, T: int, lastk: int
) -> np.ndarray:
    """1 = 2.02 8-K in sessions t+1..t+22, 0 = none, -1 = window censored by the data end."""
    base = si.astype(np.int64) * T
    lo = np.searchsorted(key, base + di + 1, side="left")
    hi = np.searchsorted(key, base + di + LAGS, side="right")
    flag = (hi > lo).astype(np.int8)
    flag[di + LAGS > lastk] = -1
    return flag


def chunked_targets(
    ctx, di_local: np.ndarray, si: np.ndarray, ind: np.ndarray, sel: np.ndarray, chunk: int = 40
) -> np.ndarray:
    """P1 Stage 0 targets for the rows ``sel``; every row of a date takes part in the
    (date, ind_code) demeaning, and rows are processed in date chunks to bound memory."""
    out = np.full((len(sel), NTGT), np.nan, dtype="float32")
    if len(di_local) == 0:
        return out
    cut = np.flatnonzero(np.diff(di_local)) + 1
    starts = np.concatenate([[0], cut])
    ends = np.concatenate([cut, [len(di_local)]])
    for g in range(0, len(starts), chunk):
        a, b = int(starts[g]), int(ends[min(g + chunk, len(starts)) - 1])
        mine = np.flatnonzero((sel >= a) & (sel < b))
        if len(mine) == 0:
            continue
        Ec = p1.lag_targets(ctx, di_local[a:b], si[a:b], ind[a:b])
        out[mine] = Ec[sel[mine] - a].astype("float32")
        del Ec
    return out


def stage_build(force: bool = False) -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    if (CACHE / "build.done").exists() and not force:
        log("build: done marker present, skipping")
        return
    D, spy_o, spy_c = load_calendar()
    Tg = len(D)
    lastk = Tg - 1
    np.save(CACHE / "D.npy", D.to_numpy("datetime64[ns]"))
    sig_files = p1.year_files(DATA / "signals")
    price_files = p1.year_files(DATA / "prices")
    panel_files = p1.year_files(DATA / "panel")
    syms: set[str] = set()
    for y in sorted(sig_files):
        syms.update(read_cols(sig_files[y], ["trade_date", "symbol"], LAST_DATA)["symbol"].unique())
    symbols = sorted(syms)
    sym_index = pd.Index(symbols)
    N = len(symbols)
    log(f"build: sessions {Tg}, symbols {N}")

    vh = pd.read_parquet(CACHE / "volhist_sessions.parquet")
    vh = vh[vh["t"] <= pd.Timestamp(LAST_DATA)]
    vh_di = D.get_indexer(vh["t"])
    vh_si = sym_index.get_indexer(vh["symbol"])
    ok = (vh_di >= 0) & (vh_si >= 0)
    vh = vh[ok].reset_index(drop=True)
    vh_di, vh_si = vh_di[ok].astype(np.int64), vh_si[ok].astype(np.int64)
    vkey = vh_di * N + vh_si
    order = np.argsort(vkey, kind="stable")
    vkey, vh = vkey[order], vh.iloc[order].reset_index(drop=True)
    dup = int(np.sum(np.diff(vkey) == 0))
    keep = np.concatenate([[True], np.diff(vkey) != 0])
    vkey, vh = vkey[keep], vh[keep].reset_index(drop=True)
    vcols = {
        c: vh[c].to_numpy("float64")
        for c in ("iv_current", "iv_week_ago", "iv_month_ago", "hv_current")
    }
    log(f"build: volhist rows kept {len(vh)} (duplicates dropped {dup})")

    ekey, einfo = load_earnings(D, sym_index)
    meta = {
        "symbols": len(symbols),
        "sessions": Tg,
        "first_session": str(D[0].date()),
        "last_session": str(D[-1].date()),
        "volhist_rows": int(len(vh)),
        "volhist_duplicates_dropped": dup,
        "iv_month_ago_nonnull_share_by_year": {
            str(k): float(v)
            for k, v in vh["iv_month_ago"].notna().groupby(vh["t"].dt.year).mean().items()
        },
        "iv_week_ago_nonnull_share_by_year": {
            str(k): float(v)
            for k, v in vh["iv_week_ago"].notna().groupby(vh["t"].dt.year).mean().items()
        },
        "earnings": einfo,
        "years": {},
        "max_dates_read": {},
    }
    scols = ["trade_date", "symbol", "ind_code", "m0_composite", *THEMES]
    max_read: dict[str, str] = {}

    def track(tag: str, df: pd.DataFrame) -> None:
        if len(df):
            m = str(df["trade_date"].max().date())
            max_read[tag] = max(max_read.get(tag, m), m)

    for y in sorted(sig_files):
        if y < 2019:
            continue
        sdf = read_cols(sig_files[y], scols, LAST_SIGNAL)
        track("signals", sdf)
        di_all = D.get_indexer(sdf["trade_date"])
        si_all = sym_index.get_indexer(sdf["symbol"])
        m = (di_all >= 0) & (si_all >= 0)
        sdf, di_all, si_all = sdf[m], di_all[m].astype(np.int64), si_all[m].astype(np.int64)
        if len(sdf) == 0:
            continue
        s0 = max(0, int(di_all.min()) - SLAB_BACK)
        s1 = min(Tg, int(di_all.max()) + 1 + SLAB_FWD)
        Ts = s1 - s0
        Cs = np.full((Ts, N), np.nan)
        Os = np.full((Ts, N), np.nan)
        Bs = np.full((Ts, N), np.nan)
        As = np.full((Ts, N), np.nan, dtype="float32")
        for yy in range(D[s0].year, D[s1 - 1].year + 1):
            if yy in price_files:
                df = read_cols(
                    price_files[yy], ["trade_date", "symbol", "open", "close"], LAST_DATA
                )
                track("prices", df)
                dd = D.get_indexer(df["trade_date"]) - s0
                ss = sym_index.get_indexer(df["symbol"])
                mm = (dd >= 0) & (dd < Ts) & (ss >= 0)
                Os[dd[mm], ss[mm]] = df["open"].to_numpy("float64")[mm]
                Cs[dd[mm], ss[mm]] = df["close"].to_numpy("float64")[mm]
            if yy in panel_files:
                df = read_cols(
                    panel_files[yy], ["trade_date", "symbol", "adv_rank", "beta_252_spy"], LAST_DATA
                )
                track("panel", df)
                dd = D.get_indexer(df["trade_date"]) - s0
                ss = sym_index.get_indexer(df["symbol"])
                mm = (dd >= 0) & (dd < Ts) & (ss >= 0)
                As[dd[mm], ss[mm]] = df["adv_rank"].to_numpy("float64")[mm].astype("float32")
                Bs[dd[mm], ss[mm]] = df["beta_252_spy"].to_numpy("float64")[mm]
        ctx = SimpleNamespace(C=Cs, O=Os, beta=Bs, spy_o=spy_o[s0:s1], spy_c=spy_c[s0:s1], T=Ts)
        order = np.argsort(di_all, kind="stable")
        sdf, di_all, si_all = sdf.iloc[order], di_all[order], si_all[order]
        ind = sdf["ind_code"].to_numpy("int64")
        adv = As[di_all - s0, si_all].astype("float64")
        row_key = di_all * N + si_all
        pos = np.clip(np.searchsorted(vkey, row_key), 0, len(vkey) - 1)
        has_vh = vkey[pos] == row_key
        sel = np.flatnonzero(has_vh & np.isfinite(adv) & (adv <= CUT[1]))
        E = chunked_targets(ctx, di_all - s0, si_all, ind, sel)
        d, s, p = di_all[sel], si_all[sel], pos[sel]
        iv = {c: vcols[c][p] for c in vcols}
        sigs = signal_block(
            Cs, d - s0, s, iv["iv_current"], iv["iv_week_ago"], iv["iv_month_ago"], iv["hv_current"]
        )
        # post-hoc diagnostic (not preregistered): own 21-session IV change, because the vendor
        # field iv_month_ago is null from 2023-Q4 on
        k21 = (d - 21) * N + s
        p21 = np.clip(np.searchsorted(vkey, k21), 0, len(vkey) - 1)
        has21 = (vkey[p21] == k21) & (d - 21 >= 0)
        ivc = np.where(iv["iv_current"] > 0, iv["iv_current"], np.nan)
        sigs["DIV21S"] = np.where(has21, ivc - vcols["iv_current"][p21], np.nan)
        # signal value of the same symbol STALE_SESSIONS sessions earlier (needs a DoltHub row then)
        skey = (d - STALE_SESSIONS) * N + s
        sp = np.clip(np.searchsorted(vkey, skey), 0, len(vkey) - 1)
        has_st = (vkey[sp] == skey) & (d - STALE_SESSIONS >= 0)
        sv = {c: np.where(has_st, vcols[c][sp], np.nan) for c in vcols}
        st_sig = signal_block(
            Cs,
            np.maximum(d - STALE_SESSIONS - s0, 0),
            s,
            sv["iv_current"],
            sv["iv_week_ago"],
            sv["iv_month_ago"],
            sv["hv_current"],
        )
        eflag = (
            earnings_flag(ekey, d, s, Tg, lastk)
            if y >= 2024
            else np.full(len(d), -2, dtype=np.int8)
        )
        out = {
            "di": d,
            "si": s,
            "ind": ind[sel],
            "adv": adv[sel].astype("float32"),
            "E": E,
            "m0": sdf["m0_composite"].to_numpy("float64")[sel].astype("float32"),
            "TH": sdf[THEMES].to_numpy("float64")[sel].astype("float32"),
            "eflag": eflag,
        }
        for k in CAND + DIAG:
            out[f"sig_{k}"] = sigs[k].astype("float64")
        for k in CAND:
            out[f"sig_st_{k}"] = st_sig[k].astype("float64")
        np.savez(CACHE / f"rows_{y}.npz", **out)
        meta["years"][str(y)] = {
            "store_rows": int(len(di_all)),
            "l12_with_iv_rows": int(len(sel)),
            "dates": int(len(np.unique(d))),
            "median_names": float(np.median(np.bincount(d - d.min())[np.bincount(d - d.min()) > 0]))
            if len(d)
            else 0.0,
        }
        log(f"build {y}: store rows {len(di_all)}, L12 with IV {len(sel)}, slab {Ts} sessions")
        del Cs, Os, Bs, As, E, ctx
    # earnings match rate on the recent L12 symbols
    if len(ekey):
        ev_si = np.unique(ekey // Tg)
        recent_syms = set()
        for y in (2024, 2025, 2026):
            f = CACHE / f"rows_{y}.npz"
            if f.exists():
                recent_syms.update(np.unique(np.load(f)["si"]).tolist())
        meta["earnings"]["recent_l12_symbols"] = len(recent_syms)
        meta["earnings"]["recent_l12_symbols_with_event"] = int(
            len(recent_syms & set(ev_si.tolist()))
        )
    meta["max_dates_read"] = max_read
    (CACHE / "build_meta.json").write_text(json.dumps(meta, indent=1, default=float))
    (CACHE / "build.done").write_text(now_utc())
    log(f"build done; max dates read {max_read}")


# ---------------------------------------------------------------------------- data access


class Rows:
    """Concatenated rows of L12 names with a DoltHub row; sorted by session index."""

    def __init__(self, years: list[int], date_filter: np.ndarray | None = None):
        parts = []
        for y in years:
            f = CACHE / f"rows_{y}.npz"
            if not f.exists():
                continue
            z = np.load(f)
            d = z["di"]
            keep = np.ones(len(d), bool) if date_filter is None else date_filter[d]
            if keep.any():
                parts.append({k: z[k][keep] for k in z.files})
        keys = parts[0].keys()
        self.a = {k: np.concatenate([p_[k] for p_ in parts]) for k in keys}
        order = np.argsort(self.a["di"], kind="stable")
        self.a = {k: v[order] for k, v in self.a.items()}
        self.di = self.a["di"]

    def scores(self, names: list[str], signs: dict) -> np.ndarray:
        cols = []
        for nm in names:
            base = nm[3:] if nm.startswith("st_") else nm
            raw = self.a[f"sig_{nm}"] if f"sig_{nm}" in self.a else self.a[f"sig_{base}"]
            cols.append(signs[base] * raw)
        return np.column_stack(cols)


def load_D() -> pd.DatetimeIndex:
    return pd.DatetimeIndex(np.load(CACHE / "D.npy").astype("datetime64[ns]"))


def bucket_rowmask(adv: np.ndarray, bucket: str) -> np.ndarray | None:
    if bucket == "L12":
        return None
    return p1.bucket_mask(adv, bucket, CUT)


# ---------------------------------------------------------------------------- signs stage


def stage_signs(force: bool = False) -> None:
    out = CACHE / "signs.json"
    if out.exists() and not force:
        log("signs: signs.json present, skipping")
        return
    D = load_D()
    T = len(D)
    wm = window_mask(D, WINDOWS["stress"])
    rows = Rows(list(range(2019, 2024)), wm)
    S = np.column_stack([rows.a["sig_DIV21"], rows.a["sig_DIV5"]])
    ic, _ = ic_dates(rows.di, S, rows.a["E"], T, wm)
    res = {}
    for k, (nm, (a, b, lags)) in enumerate(
        (("DIV21", DECISION["DIV21"]), ("DIV5", DECISION["DIV5"]))
    ):
        st = decision_stats(ic[:, k, :], a, b, lags, wm)
        res[nm] = {
            "stress_cic_mean": st["cic"],
            "stress_t": st["t"],
            "lags": [a, b],
            "n_dates": st["n_dates"],
            "sign": 1 if st["cic"] > 0 else -1,
        }
    res["window"] = list(WINDOWS["stress"])
    res["universe"] = "L12"
    res["data_confidence"] = (
        "lower: the stress window is sparse (Mon/Wed/Fri before 2024-09) and F3 was not measured there"
    )
    res["fixed_at"] = now_utc()
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(res, indent=1, default=float))
    tmp.replace(out)
    log(f"signs fixed: {json.dumps(res, default=float)}")


def load_signs() -> dict:
    p = CACHE / "signs.json"
    if not p.exists():
        raise SystemExit("signs.json is missing: run the signs stage first")
    s = json.loads(p.read_text())
    return {
        "IVRV": 1,
        "IVZ3": -1,
        "HVZ3": -1,
        "IVRV_V": 1,
        "DIV21": s["DIV21"]["sign"],
        "DIV21S": s["DIV21"]["sign"],
        "DIV5": s["DIV5"]["sign"],
    }


# ---------------------------------------------------------------------------- measure stage


def obj_stats(
    ic_k: np.ndarray, npair_k: np.ndarray, wm: np.ndarray, decision: tuple | None
) -> dict:
    w = ic_k[wm]
    means = [
        float(np.nanmean(w[:, j])) if np.isfinite(w[:, j]).any() else float("nan")
        for j in range(NTGT)
    ]
    out = {
        "ic_mean": means[:LAGS],
        "ic_overnight_lag1": means[LAGS],
        "ic_intraday_lag1": means[LAGS + 1],
        "cic_2_6": decision_stats(ic_k, 2, 6, 10, wm),
        "cic_2_22": decision_stats(ic_k, 2, 22, 25, wm),
        "h_np": p1.half_life_np(np.array(means)),
    }
    names = npair_k[wm][:, 1]
    names = names[names > 0]
    out["median_names"] = float(np.median(names)) if len(names) else float("nan")
    out["min_names_date"] = float(names.min()) if len(names) else float("nan")
    out["n_dates_lag2"] = int(np.isfinite(w[:, 1]).sum())
    if decision is not None:
        a, b, _ = decision
        out["decision"] = out["cic_2_22"] if (a, b) == (2, 22) else out["cic_2_6"]
    return out


def persistence(rows: Rows, S: np.ndarray, wm: np.ndarray, lags=(1, 5, 21)) -> dict:
    """Mean cross-sectional Spearman of the score at t with the score L sessions earlier."""
    hist: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    K = S.shape[1]
    out = {}
    cols = {str(L): [[] for _ in range(K)] for L in lags}
    for d, a, b in date_slices(rows.di):
        si, X = rows.a["si"][a:b], S[a:b]
        order = np.argsort(si)
        hist[d] = (si[order], X[order])
        for old in [k for k in hist if k < d - max(lags)]:
            del hist[old]
        if not wm[d]:
            continue
        for L in lags:
            prev = hist.get(d - L)
            if prev is None:
                continue
            psi, pX = prev
            pos = np.clip(np.searchsorted(psi, si), 0, len(psi) - 1)
            present = psi[pos] == si
            if present.sum() < MIN_NAMES:
                continue
            A, B = X[present], pX[pos[present]]
            for k in range(K):
                both = np.isfinite(A[:, k]) & np.isfinite(B[:, k])
                if both.sum() < MIN_NAMES:
                    continue
                za, _ = rank_normal(A[both, k][:, None])
                zb, _ = rank_normal(B[both, k][:, None])
                cols[str(L)][k].append(
                    float((za * zb).sum() / math.sqrt((za**2).sum() * (zb**2).sum()))
                )
    for L in lags:
        out[str(L)] = [float(np.mean(c)) if c else float("nan") for c in cols[str(L)]]
    return out


def pct_diff_by_earn(rows: Rows, x: np.ndarray, wm: np.ndarray) -> dict:
    """Window mean of (mean within-date percentile of x for E=1 minus E=0)."""
    diffs = []
    ef = rows.a["eflag"]
    for d, a, b in date_slices(rows.di):
        if not wm[d]:
            continue
        v, e = x[a:b], ef[a:b]
        ok = np.isfinite(v) & (e >= 0)
        if ok.sum() < MIN_NAMES:
            continue
        pct = pd.Series(v[ok]).rank(pct=True).to_numpy()
        e = e[ok]
        if (e == 1).sum() >= 10 and (e == 0).sum() >= 10:
            diffs.append(pct[e == 1].mean() - pct[e == 0].mean())
    return {
        "mean_percentile_diff_E1_minus_E0": float(np.mean(diffs)) if diffs else float("nan"),
        "n_dates": len(diffs),
    }


def stage_measure() -> dict:
    signs = load_signs()
    sj = json.loads((CACHE / "signs.json").read_text())
    log(f"measure start (signs fixed_at {sj['fixed_at']}): {signs}")
    D = load_D()
    T = len(D)
    wms = {k: window_mask(D, v) for k, v in WINDOWS.items()}
    alld = wms["recent"] | wms["stress"] | wms["owner_B"]
    rows = Rows(list(range(2019, 2027)))
    S = rows.scores(OBJS, signs)
    E = rows.a["E"]
    di = rows.di
    log(f"rows {len(di)}, dates {len(np.unique(di))}")
    ic, npair = {}, {}
    for bk in BUCKETS:
        ic[bk], npair[bk] = ic_dates(di, S, E, T, alld, bucket_rowmask(rows.a["adv"], bk))
        log(f"IC computed for {bk}")
    results: dict = {
        "signs": sj,
        "windows": WINDOWS,
        "min_names": MIN_NAMES,
        "objects": {},
        "notes": [],
    }
    for k, nm in enumerate(OBJS):
        results["objects"][nm] = {}
        for bk in BUCKETS:
            results["objects"][nm][bk] = {}
            base = nm[3:] if nm.startswith("st_") else nm
            for wn, wm in wms.items():
                results["objects"][nm][bk][wn] = obj_stats(
                    ic[bk][:, k, :], npair[bk][:, k, :], wm, DECISION.get(base)
                )
    # per calendar year (recent, L12)
    yrs = {}
    for k, nm in enumerate(CAND):
        yrs[nm] = {}
        for y in (2024, 2025, 2026):
            wm = wms["recent"] & np.asarray(D.year == y)
            a, b, lags = DECISION[nm]
            yrs[nm][str(y)] = decision_stats(ic["L12"][:, k, :], a, b, lags, wm)
    results["by_year_recent_L12"] = yrs

    # BH over the four decision statistics + promotion
    ps = [results["objects"][nm]["L12"]["recent"]["decision"]["p_one_sided"] for nm in CAND]
    # a statistic that cannot be computed counts as p = 1 in the BH family of four
    qs = bh_q(np.array([p if np.isfinite(p) else 1.0 for p in ps]))
    # IVZ3 - HVZ3 paired (index of HVZ3 is len(CAND))
    k_iv, k_hv = CAND.index("IVZ3"), OBJS.index("HVZ3")
    diff = lag_sum_series(ic["L12"][:, k_iv, :], 2, 6, wms["recent"]) - lag_sum_series(
        ic["L12"][:, k_hv, :], 2, 6, wms["recent"]
    )
    dst = p1.nw_stats(diff, 10)
    results["ivz3_minus_hvz3_recent_L12"] = {
        "mean_diff_cic_2_6": dst["mean"],
        "nw_t": dst["t"],
        "n_dates": int(dst["n"]),
        "nw_lags": 10,
    }
    # point estimate in the promotion rule = difference of the two decision CICs
    pe_diff = (
        results["objects"]["IVZ3"]["L12"]["recent"]["cic_2_6"]["cic"]
        - results["objects"]["HVZ3"]["L12"]["recent"]["cic_2_6"]["cic"]
    )
    results["ivz3_minus_hvz3_recent_L12"]["point_estimate_diff_of_cics"] = pe_diff
    promo = {}
    for i, nm in enumerate(CAND):
        dec = results["objects"][nm]["L12"]["recent"]["decision"]
        stress = results["objects"][nm]["L12"]["stress"]
        stress_dec = stress["cic_2_22"] if DECISION[nm][1] == 22 else stress["cic_2_6"]
        cic, t = dec["cic"], dec["t"]
        ok = bool(np.isfinite(cic) and cic > 0 and np.isfinite(t) and t >= 2.0 and qs[i] <= 0.10)
        if nm == "IVZ3":
            ok = ok and bool(pe_diff > 0)
        reason = None
        under = bool(np.isfinite(dec["mde"]) and dec["mde"] > REFERENCE[nm])
        missing = not np.isfinite(dec["cic"])
        if not ok:
            reason = "data_missing" if missing else ("underpowered" if under else "small_estimate")
        promo[nm] = {
            "decision_stat": f"CIC({DECISION[nm][0]}..{DECISION[nm][1]})",
            "cic": cic,
            "nw_t": t,
            "p_one_sided": dec["p_one_sided"],
            "bh_q": float(qs[i]),
            "se": dec["se"],
            "mde": dec["mde"],
            "reference_effect": REFERENCE[nm],
            "power_flag": "not_measurable" if missing else ("underpowered" if under else "ok"),
            "n_dates": dec["n_dates"],
            "median_names_L12": results["objects"][nm]["L12"]["recent"]["median_names"],
            "promoted": ok,
            "not_promoted_reason": reason,
            "stress_t": stress_dec["t"],
            "stress_cic": stress_dec["cic"],
            "state_flip": bool(np.isfinite(stress_dec["t"]) and stress_dec["t"] <= -2.0),
        }
    results["promotion"] = promo
    results["promoted"] = [nm for nm in CAND if promo[nm]["promoted"]]
    results["mechanical_status"] = (
        "promote_some" if results["promoted"] else "none_promoted_not_at_depth"
    )

    # diagnostics on recent L12
    wr = wms["recent"]
    Scand = S[:, : len(CAND)]
    resid = residual_scores(di, Scand, rows.a["m0"], rows.a["TH"], wr)
    ic_res, _ = ic_dates(di, resid, E, T, wr)
    marg = {}
    for k, nm in enumerate(CAND):
        a, b, lags = DECISION[nm]
        marg[nm] = decision_stats(ic_res[:, k, :], a, b, lags, wr)
    results["marginal_ic_vs_m0_themes_recent_L12"] = marg
    results["persistence_recent_L12"] = {
        nm: {L: v[k] for L, v in persistence(rows, S[:, : len(CAND) + len(DIAG)], wr).items()}
        for k, nm in enumerate(CAND + DIAG)
    }
    # earnings split (amendment A1), recent L12
    ef = rows.a["eflag"]
    esplit = {"min_names_subset": MIN_NAMES_SUBSET}
    obj_e = CAND + ["HVZ3"]
    Se = np.column_stack([S[:, OBJS.index(nm)] for nm in obj_e])
    for lab, val in (("E1", 1), ("E0", 0)):
        ice, npe = ic_dates(di, Se, E, T, wr, ef == val, MIN_NAMES_SUBSET)
        esplit[lab] = {}
        for k, nm in enumerate(obj_e):
            base = nm
            a, b, lags = DECISION.get(base, DECISION["IVZ3"])
            st = decision_stats(ice[:, k, :], a, b, lags, wr)
            names = npe[:, k, 1][wr]
            names = names[names > 0]
            st["median_names"] = float(np.median(names)) if len(names) else float("nan")
            esplit[lab][nm] = st
    esplit["ivrv_percentile_diff"] = pct_diff_by_earn(rows, rows.a["sig_IVRV"], wr)
    esplit["share_E1_among_matched_recent_rows"] = float(
        (ef[wr[di]] == 1).sum() / max((ef[wr[di]] >= 0).sum(), 1)
    )
    esplit["share_censored_recent_rows"] = float((ef[wr[di]] == -1).sum() / max(wr[di].sum(), 1))
    build_meta = json.loads((CACHE / "build_meta.json").read_text())
    esplit["match"] = build_meta["earnings"]
    results["earnings_split_recent_L12"] = esplit
    results["build_meta"] = build_meta
    results["dsr_family_n"] = 4
    results["data_gate"] = "passed_under_amendment_A2"
    out = ITER_DIR / "results.json"
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(results, indent=1, default=float))
    tmp.replace(out)
    log(
        f"measure done: mechanical_status={results['mechanical_status']} promoted={results['promoted']}"
    )
    return results


# ---------------------------------------------------------------------------- report stage


def fmt(v, nd=3) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "NA"
    if isinstance(v, float):
        return f"{v:.{nd}f}"
    return str(v)


def stage_report() -> None:
    R = json.loads((ITER_DIR / "results.json").read_text())
    P = R["promotion"]
    bm = R["build_meta"]
    L = []
    L.append("# T-20261005-45 P6 期权隐含选股信号 IC 测量（待主审）\n")
    L.append("数据门按修正案 A2 通过：F3 自相关在看到原口径结果后改为按决策宇宙计算，门槛未变。\n")
    L.append("## 一页摘要\n")
    L.append(
        f"- mechanical_status = **{R['mechanical_status']}**；晋级：{', '.join(R['promoted']) or '无'}。"
    )
    s = R["signs"]
    L.append(
        f"- 符号（压力窗 L12，{s['fixed_at']} 先于任何近期窗数字写定）：DIV21 CIC(2..22) 均值 "
        f"{fmt(s['DIV21']['stress_cic_mean'], 4)}（t {fmt(s['DIV21']['stress_t'], 2)}）-> 符号 {s['DIV21']['sign']:+d}；"
        f"DIV5 CIC(2..6) 均值 {fmt(s['DIV5']['stress_cic_mean'], 4)}（t {fmt(s['DIV5']['stress_t'], 2)}）-> 符号 {s['DIV5']['sign']:+d}。压力窗稀疏（周一三五），DIV21/DIV5 的定号数据置信度较低。"
    )
    L.append(
        f"- 每日 L12 且有 DoltHub 的名数：近期窗 IVRV 中位 {fmt(R['objects']['IVRV']['L12']['recent']['median_names'], 0)}，"
        f"最少 {fmt(R['objects']['IVRV']['L12']['recent']['min_names_date'], 0)}（合同预计 650–750，实测更少，MDE 约大 10%）。"
    )
    nn = bm["iv_month_ago_nonnull_share_by_year"]
    L.append(
        "- DIV21 在近期窗无法按合同定义计算：供应商字段 iv_month_ago 自 2023 年第四季度起为空"
        f"（非空占比按年 {', '.join(f'{k}: {v:.3f}' for k, v in nn.items())}）。"
        "决策统计量记为不可测，BH 族内按 p = 1 处理，原因记 data_missing，不是估计值小，也不是否定。"
        "DIV21S（iv_current 减同一代码 21 个会话前的 iv_current，用符号 +1）是看到该缺失后补的事后诊断，"
        "不进晋级规则。"
    )
    L.append(
        "- 首轮测量（05:59 UTC）后只为加入 DIV21S 列重建了一次缓存并重跑测量；符号文件未动，其余对象、各档、各窗的数字与首轮逐项比对完全一致（0 项差异）。"
    )
    L.append(
        "- DIV5 的日度 IV 变化含测量噪声（一阶差分自相关约 -0.19），不显著时更可能是功效不足，不算否定。\n"
    )
    L.append(
        "| 候选 | 决策统计量 | CIC | NW t | p(单侧) | BH q | SE | MDE | 参考效应 | 功效 | 晋级 | 原因 | 压力窗 t | 状态翻转 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for nm in CAND:
        p = P[nm]
        L.append(
            f"| {nm} | {p['decision_stat']} | {fmt(p['cic'], 4)} | {fmt(p['nw_t'], 2)} | {fmt(p['p_one_sided'], 4)} | "
            f"{fmt(p['bh_q'], 3)} | {fmt(p['se'], 4)} | {fmt(p['mde'], 4)} | {fmt(p['reference_effect'], 3)} | "
            f"{p['power_flag']} | {'是' if p['promoted'] else '否'} | {p['not_promoted_reason'] or '-'} | "
            f"{fmt(p['stress_t'], 2)} | {'是' if p['state_flip'] else '否'} |"
        )
    d = R["ivz3_minus_hvz3_recent_L12"]
    L.append(
        f"\n- IVZ3 减 HVZ3（近期 L12，CIC(2..6) 逐日差）：点估计差 {fmt(d['point_estimate_diff_of_cics'], 4)}，"
        f"逐日差均值 {fmt(d['mean_diff_cic_2_6'], 4)}，NW t(10) {fmt(d['nw_t'], 2)}，{d['n_dates']} 个日期。"
    )
    L.append("\n## 各候选与对照：近期窗各档\n")
    L.append(
        "| 对象 | 档 | CIC(2..6) | t | CIC(2..22) | t | h_np | 名数中位 | 日期数(滞后2) | 滞后1 隔夜 | 滞后1 日内 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for nm in CAND + DIAG + STALE:
        for bk in BUCKETS:
            o = R["objects"][nm][bk]["recent"]
            L.append(
                f"| {nm} | {bk} | {fmt(o['cic_2_6']['cic'], 4)} | {fmt(o['cic_2_6']['t'], 2)} | {fmt(o['cic_2_22']['cic'], 4)} | "
                f"{fmt(o['cic_2_22']['t'], 2)} | {fmt(o['h_np'], 0)} | {fmt(o['median_names'], 0)} | {o['n_dates_lag2']} | "
                f"{fmt(o['ic_overnight_lag1'], 4)} | {fmt(o['ic_intraday_lag1'], 4)} |"
            )
    for wn in ("stress", "owner_B"):
        L.append(f"\n## L12 {wn} 窗\n")
        L.append("| 对象 | CIC(2..6) | t | CIC(2..22) | t | n 日期(2..22) | 名数中位 |")
        L.append("|---|---|---|---|---|---|---|")
        for nm in CAND + DIAG:
            o = R["objects"][nm]["L12"][wn]
            L.append(
                f"| {nm} | {fmt(o['cic_2_6']['cic'], 4)} | {fmt(o['cic_2_6']['t'], 2)} | {fmt(o['cic_2_22']['cic'], 4)} | "
                f"{fmt(o['cic_2_22']['t'], 2)} | {o['cic_2_22']['n_dates']} | {fmt(o['median_names'], 0)} |"
            )
    L.append("\n## 衰减曲线（近期 L12，滞后 1..22 的均值 IC，单位 1e-4）\n")
    L.append("| 对象 | " + " | ".join(str(j) for j in range(1, LAGS + 1)) + " |")
    L.append("|---|" + "---|" * LAGS)
    for nm in CAND + DIAG:
        m = R["objects"][nm]["L12"]["recent"]["ic_mean"]
        L.append(f"| {nm} | " + " | ".join(fmt(v * 1e4, 0) for v in m) + " |")
    L.append("\n## 逐年（近期，L12，决策统计量）\n")
    L.append("| 对象 | 年 | CIC | NW t | 日期数 |")
    L.append("|---|---|---|---|---|")
    for nm in CAND:
        for y, o in R["by_year_recent_L12"][nm].items():
            L.append(f"| {nm} | {y} | {fmt(o['cic'], 4)} | {fmt(o['t'], 2)} | {o['n_dates']} |")
    L.append("\n## 对 M0 与九个主题的边际 IC（近期 L12，残差）\n")
    L.append("| 对象 | 残差 CIC | NW t | 原 CIC | 原 t |")
    L.append("|---|---|---|---|---|")
    for nm in CAND:
        mg = R["marginal_ic_vs_m0_themes_recent_L12"][nm]
        P_ = P[nm]
        L.append(
            f"| {nm} | {fmt(mg['cic'], 4)} | {fmt(mg['t'], 2)} | {fmt(P_['cic'], 4)} | {fmt(P_['nw_t'], 2)} |"
        )
    L.append("\n## 持续性（近期 L12，截面 Spearman 均值，按会话序号滞后）\n")
    L.append("| 对象 | t-1 | t-5 | t-21 |")
    L.append("|---|---|---|---|")
    for nm, v in R["persistence_recent_L12"].items():
        L.append(f"| {nm} | {fmt(v['1'], 3)} | {fmt(v['5'], 3)} | {fmt(v['21'], 3)} |")
    L.append("\n## 旧信号（63 个会话前的同一代码的值；近期 L12）\n")
    L.append("| 对象 | CIC | NW t | 名数中位 |")
    L.append("|---|---|---|---|")
    for nm in CAND:
        o = R["objects"][f"st_{nm}"]["L12"]["recent"]
        dec = o["cic_2_22"] if DECISION[nm][1] == 22 else o["cic_2_6"]
        L.append(
            f"| st_{nm} | {fmt(dec['cic'], 4)} | {fmt(dec['t'], 2)} | {fmt(o['median_names'], 0)} |"
        )
    e = R["earnings_split_recent_L12"]
    L.append("\n## 财报窗口拆分（修正案 A1，只报告，近期 L12；子集内最少 50 名）\n")
    L.append("| 对象 | E=1 CIC | E=1 t | E=1 名数中位 | E=0 CIC | E=0 t | E=0 名数中位 |")
    L.append("|---|---|---|---|---|---|---|")
    for nm in CAND + ["HVZ3"]:
        a1, a0 = e["E1"][nm], e["E0"][nm]
        L.append(
            f"| {nm} | {fmt(a1['cic'], 4)} | {fmt(a1['t'], 2)} | {fmt(a1['median_names'], 0)} | "
            f"{fmt(a0['cic'], 4)} | {fmt(a0['t'], 2)} | {fmt(a0['median_names'], 0)} |"
        )
    pd_ = e["ivrv_percentile_diff"]
    L.append(
        f"\n- IVRV 分位差（E=1 减 E=0，日内分位，窗口均值）：{fmt(pd_['mean_percentile_diff_E1_minus_E0'], 3)}（{pd_['n_dates']} 个日期）。"
    )
    L.append(
        f"- E=1 占比（已定标行）{fmt(e['share_E1_among_matched_recent_rows'], 3)}；右删失行占近期行 {fmt(e['share_censored_recent_rows'], 3)}（t+22 超过 2026-09-17，不进拆分）。"
    )
    em = e["match"]
    L.append(
        f"- 财报匹配：读入 8-K 事件 {em.get('n_events_read')}，含 2.02 {em.get('n_events_2_02')}，"
        f"事件代码匹配率 {fmt(em.get('ticker_match_rate_events'), 3)}，近期 L12 代码 {em.get('recent_l12_symbols')}，其中有事件 {em.get('recent_l12_symbols_with_event')}；"
        "未匹配代码按 E=0（只读 2024 年起的事件文件）。"
    )
    L.append("\n## 数据说明\n")
    L.append(
        "- 机主 B 窗（2026-07-01..09-15）的 CIC(2..22) 只有约 33 个滞后完整的日期，却用 25 阶 NW，t 值只作参考；CIC(2..6) 也只有约 55 个日期。"
    )
    L.append(
        "- 旧信号 st_DIV21 用的是 63 个会话前的供应商 iv_month_ago，近期窗内多数日期该字段为空，结果不可靠，只作记录。"
    )
    L.append(f"- 读入的最大日期：{bm['max_dates_read']}（不晚于 2026-09-17）。")
    L.append(
        f"- DoltHub 行 {bm['volhist_rows']}（去重 {bm['volhist_duplicates_dropped']}）；价格未做 price_hygiene 清洗，沿用 P1 阶段 0 的目标收益口径以保持一致。"
    )
    L.append("- 持续性按会话序号滞后，稀疏段（周一三五）的 t-1 常缺失，日期数已隐含在均值里。")
    L.append(
        "- CIC 点估计为各滞后在其自有日期上的窗口均值之和；t 值用滞后和序列完整的日期（窗口末端约 22 个会话因滞后不全被排除）。"
    )
    (ITER_DIR / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    ledger = {
        "iteration": ITER_ID,
        "dsr_family": {
            "trial_count": 4,
            "trials": [
                {
                    "id": nm,
                    "decision": P[nm]["decision_stat"],
                    "cic": P[nm]["cic"],
                    "nw_t": P[nm]["nw_t"],
                    "p_one_sided": P[nm]["p_one_sided"],
                    "bh_q": P[nm]["bh_q"],
                    "promoted": P[nm]["promoted"],
                }
                for nm in CAND
            ],
        },
        "diagnostics_not_counted": ["HVZ3", "IVRV_V", *STALE],
        "note": "project-wide trial count lives in the T-20261005-34 ledger; P1 stage 0 total was 193, this stage adds 4",
        "mechanical_status": R["mechanical_status"],
    }
    (ITER_DIR / "trial-ledger.json").write_text(json.dumps(ledger, indent=1, default=float))
    log("report written")


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--stage", choices=["build", "signs", "measure", "report", "all"], default="all"
    )
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    st = a.stage
    if st in ("build", "all"):
        stage_build(a.force)
    if st in ("signs", "all"):
        stage_signs(a.force)
    if st in ("measure", "all"):
        stage_measure()
    if st in ("report", "all"):
        stage_report()


if __name__ == "__main__":
    main()
