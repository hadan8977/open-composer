"""T-20261001-02: month-end cash-need footprint in the P500 momentum-loser cross section.

Mechanism measurement for the dash-for-cash line (not a candidate; no keep/refute verdict).
Definitions are copied from ``hypotheses.md`` ("横截面机制测量") of
``t20261001_01_dash_for_cash_settlement``. Stages: panel, measure, report, all.

Group timing (documented choice): a decile group formed at month-end tau_f (information up to
close tau_f) is active from day tau_f+4 through tau_{f+1}+3, so that the whole event window of
month m (pre window [b-5, b], post window [b+1, tau+3], and the open-to-open trade
b+1 open -> tau+4 open) uses one frozen group formed at the previous month-end.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ITER_ID = "t20261001_01_dash_for_cash_settlement"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITER_ID
CACHE_DIR = ITER_DIR / "cache"
PANEL_PATH = CACHE_DIR / "xs_panel.parquet"
EVENTS_PATH = CACHE_DIR / "xs_events.parquet"
SPY_PATH = CACHE_DIR / "xs_spy.parquet"
META_PATH = CACHE_DIR / "xs_meta.json"
RESULTS_PATH = ITER_DIR / "results_xs.json"
REPORT_PATH = ITER_DIR / "report_xs.md"
CAND_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "t20260929_35_overnight_persistence"
    / "cache"
    / "candidates.json"
)
PREREG_TS_PATH = ITER_DIR / "prebacktest-validated-at.txt"

REFORM_DATE = pd.Timestamp("2024-05-28")  # US T+1 effective
POST_START = pd.Timestamp("2024-06-01")
POOL_N = 500
DV_WINDOW = 63
MOM_SKIP = 21
MOM_LOOKBACK = 252
GROUP_LAG = 4  # a group formed at tau_f is used from day tau_f + 4
M1_T_BAR = -2.0
NW_M1 = 5
NW_M3 = 3
BP = 1e4

WINDOWS: dict[str, tuple[str | None, str | None]] = {
    "stress_2016_2023": ("2016-05-02", "2023-09-15"),
    "selection": ("2023-09-18", "2025-12-31"),
    "benchmark": ("2024-01-08", "2026-09-17"),
    "contaminated_2026": ("2026-01-02", "2026-09-17"),
    "all": (None, None),
}


def _log(msg: str) -> None:
    print(f"[{datetime.now(UTC):%H:%M:%S}] {msg}", flush=True)


# ==========================================================================
# pure helpers (unit-tested)
# ==========================================================================


def month_end_indices(dates: pd.DatetimeIndex) -> np.ndarray:
    """Index of the last trading day of every complete calendar month.

    The final calendar month of the calendar is never returned (its last day is unknown).
    """
    ym = np.asarray(dates.year * 100 + dates.month)
    return np.flatnonzero(ym[1:] != ym[:-1])


def settle_offset(tau_date: pd.Timestamp, fixed: int | None = None) -> int:
    """b = tau - offset: 4 before the 2024-05-28 T+1 reform, 3 after (or ``fixed``)."""
    if fixed is not None:
        return fixed
    return 4 if pd.Timestamp(tau_date) < REFORM_DATE else 3


def build_event_frame(dates: pd.DatetimeIndex, tau_idx: np.ndarray) -> pd.DataFrame:
    """Per-day labels. ``event`` m is the first month whose tau+3 >= day (-1 after the last).

    Columns: event, pre (b-5..b), post (b+1..tau+3), pos (offset to the nearest tau within
    tau-12..tau+8, post-window offsets +1..+3 take priority, NaN otherwise), seg ('pre' or
    'post' reform, by the event's tau).
    """
    n = len(dates)
    tau_idx = np.asarray(tau_idx)
    j = np.arange(n)
    event = np.searchsorted(tau_idx + 3, j, side="left")
    event = np.where(event >= len(tau_idx), -1, event)
    pre = np.zeros(n, dtype=bool)
    post = np.zeros(n, dtype=bool)
    for t in tau_idx:
        b = int(t) - settle_offset(dates[int(t)])
        pre[max(b - 5, 0) : b + 1] = True
        post[b + 1 : min(int(t) + 3, n - 1) + 1] = True
    pos = np.full(n, np.nan)
    nxt = np.searchsorted(tau_idx, j, side="left")  # first tau idx >= j
    prv = nxt - 1  # last tau idx < j
    for k in range(n):
        has_prv = prv[k] >= 0
        has_nxt = nxt[k] < len(tau_idx)
        d_prv = k - int(tau_idx[prv[k]]) if has_prv else None
        d_nxt = k - int(tau_idx[nxt[k]]) if has_nxt else None
        if d_prv is not None and 1 <= d_prv <= 3:
            pos[k] = d_prv
        elif d_nxt is not None and d_nxt >= -12:
            pos[k] = d_nxt
        elif d_prv is not None and d_prv <= 8:
            pos[k] = d_prv
    seg = np.empty(n, dtype=object)
    for k in range(n):
        if event[k] >= 0:
            tau_date = dates[int(tau_idx[event[k]])]
        else:
            tau_date = dates[k]
        seg[k] = "pre" if tau_date < REFORM_DATE else "post"
    return pd.DataFrame(
        {"event": event, "pre": pre, "post": post, "pos": pos, "seg": seg}, index=dates
    )


def assign_deciles(mom: np.ndarray, n_groups: int = 10) -> np.ndarray:
    """Equal-count rank groups 1..n_groups (1 = lowest momentum). NaN input -> NaN output."""
    mom = np.asarray(mom, dtype="float64")
    out = np.full(len(mom), np.nan)
    ok = np.flatnonzero(np.isfinite(mom))
    if len(ok) == 0:
        return out
    order = ok[np.argsort(mom[ok], kind="stable")]
    rank = np.empty(len(order), dtype=int)
    rank[:] = np.arange(len(order))
    out[order] = np.floor(rank * n_groups / len(order)) + 1
    return out


def formation_for_day(day_idx: int, formation_idx: np.ndarray) -> int:
    """Position in ``formation_idx`` of the group active on ``day_idx`` (-1 if none yet)."""
    return int(np.searchsorted(np.asarray(formation_idx) + GROUP_LAG, day_idx, side="right")) - 1


def group_daily(
    panel: pd.DataFrame, decile: int | None, weighting: str, ret_col: str = "ret_cc_adj"
) -> pd.Series:
    """Daily mean return of a decile (None = whole pool). Missing returns are dropped from the
    average (delisted names after their last price), never filled with zero."""
    sub = panel if decile is None else panel[panel["mom_decile"] == decile]
    sub = sub[sub[ret_col].notna()]
    if weighting == "dv":
        wr = (sub["weight_dv"] * sub[ret_col]).groupby(sub["date"]).sum()
        w = sub["weight_dv"].groupby(sub["date"]).sum()
        return wr / w
    return sub.groupby("date")[ret_col].mean()


def hac_ols(y: np.ndarray, x: np.ndarray, lags: int) -> tuple[np.ndarray, np.ndarray]:
    """OLS with Newey-West (Bartlett) covariance, no small-sample correction."""
    y = np.asarray(y, dtype="float64")
    x = np.asarray(x, dtype="float64")
    beta = np.linalg.lstsq(x, y, rcond=None)[0]
    e = y - x @ beta
    g = x * e[:, None]
    s = g.T @ g
    for lag in range(1, lags + 1):
        w = 1.0 - lag / (lags + 1.0)
        gam = g[lag:].T @ g[:-lag]
        s = s + w * (gam + gam.T)
    xtx_inv = np.linalg.inv(x.T @ x)
    return beta, xtx_inv @ s @ xtx_inv


def contrast_t(beta: np.ndarray, cov: np.ndarray, c: np.ndarray) -> tuple[float, float]:
    c = np.asarray(c, dtype="float64")
    est = float(c @ beta)
    var = float(c @ cov @ c)
    return est, (est / np.sqrt(var) if var > 0 else float("nan"))


def nw_t(x: np.ndarray, lags: int) -> float:
    from scripts import run_t20260929_35_overnight_persistence as t35

    return t35.newey_west_t(np.asarray(x, dtype="float64"), lags)


def m1_regression(
    y: np.ndarray, pre: np.ndarray, post: np.ndarray, lags: int = NW_M1
) -> dict[str, float]:
    """y on [1, pre, post]: the pre coefficient is mean(pre days) - mean(rest days)."""
    ok = np.isfinite(y)
    y, pre, post = y[ok], pre[ok].astype(float), post[ok].astype(float)
    if len(y) < lags + 10 or pre.sum() < 2:
        return {"coef_bp": float("nan"), "t_nw": float("nan"), "n_days": int(len(y))}
    x = np.column_stack([np.ones(len(y)), pre, post])
    beta, cov = hac_ols(y, x, lags)
    t = beta[1] / np.sqrt(cov[1, 1]) if cov[1, 1] > 0 else float("nan")
    return {"coef_bp": float(beta[1] * BP), "t_nw": float(t), "n_days": int(len(y))}


def m3_observations(d1: pd.Series, dates: pd.DatetimeIndex, tau_idx: np.ndarray) -> pd.DataFrame:
    """Three observations per month: D1 at tau-4, tau-3 and the mean over tau+5..tau+8."""
    vals = d1.reindex(dates).to_numpy(dtype="float64")
    rows = []
    for t in tau_idx:
        t = int(t)
        if t - 4 < 0 or t + 8 >= len(dates):
            continue
        r4, r3 = vals[t - 4], vals[t - 3]
        ctrl = vals[t + 5 : t + 9]
        if not (np.isfinite(r4) and np.isfinite(r3) and np.isfinite(ctrl).all()):
            continue
        tau_date = dates[t]
        rows.append((tau_date, "tm4", r4))
        rows.append((tau_date, "tm3", r3))
        rows.append((tau_date, "ctrl", float(ctrl.mean())))
    return pd.DataFrame(rows, columns=["tau", "obs", "r"])


def m3_estimate(obs: pd.DataFrame, post_mask: np.ndarray, lags: int = NW_M3) -> dict[str, Any]:
    """Equation 7 (Nathan-Suominen-Tasa): R on D4, D3, Post and their interactions."""
    d4 = (obs["obs"] == "tm4").to_numpy(dtype=float)
    d3 = (obs["obs"] == "tm3").to_numpy(dtype=float)
    po = np.asarray(post_mask, dtype=float)
    x = np.column_stack([np.ones(len(obs)), d4, d3, po, d4 * po, d3 * po])
    y = obs["r"].to_numpy(dtype="float64")
    beta, cov = hac_ols(y, x, lags)
    diff, diff_t = contrast_t(beta, cov, np.array([0, 0, 0, 0, 1, -1.0]))
    n_post = int(obs.loc[post_mask, "tau"].nunique())
    n_pre = int(obs.loc[~np.asarray(post_mask), "tau"].nunique())
    return {
        "theta4_bp": float(beta[4] * BP),
        "theta3_bp": float(beta[5] * BP),
        "diff_bp": float(diff * BP),
        "diff_t": float(diff_t),
        "n_pre_months": n_pre,
        "n_post_months": n_post,
    }


def m3_cell_means(obs: pd.DataFrame) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    post_flag = obs["tau"] >= POST_START
    pre_flag = obs["tau"] < pd.Timestamp("2024-05-01")
    for name in ("tm4", "tm3"):
        for seg, mask in (("pre", pre_flag), ("post", post_flag)):
            sub = obs[(obs["obs"] == name) & mask]
            out[f"{name}_{seg}"] = {
                "mean_bp": float(sub["r"].mean() * BP) if len(sub) else float("nan"),
                "n_months": int(sub["tau"].nunique()),
            }
    return out


def trade_stats(gross: np.ndarray, round_trip_bp: float) -> dict[str, float]:
    """Monthly trade statistics. ``round_trip_bp`` is the total cost of one month at 10 bp/side
    (the 20 bp/side case is exactly twice that)."""
    g = np.asarray(gross, dtype="float64")
    g = g[np.isfinite(g)]
    n = len(g)
    if n < 3:
        return {
            "gross_mean_bp": float("nan"),
            "gross_t": float("nan"),
            "net10_mean_bp": float("nan"),
            "net20_mean_bp": float("nan"),
            "sharpe_net10": float("nan"),
            "n_months": int(n),
        }
    net10 = g - round_trip_bp / BP
    sd = g.std(ddof=1)
    sd10 = net10.std(ddof=1)
    return {
        "gross_mean_bp": float(g.mean() * BP),
        "gross_t": float(g.mean() / (sd / np.sqrt(n))) if sd > 0 else float("nan"),
        "net10_mean_bp": float(net10.mean() * BP),
        "net20_mean_bp": float((g - 2.0 * round_trip_bp / BP).mean() * BP),
        "sharpe_net10": float(net10.mean() / sd10 * np.sqrt(12.0)) if sd10 > 0 else float("nan"),
        "n_months": int(n),
    }


def in_window(entry: pd.Series, exit_: pd.Series, lo: str | None, hi: str | None) -> pd.Series:
    ok = pd.Series(True, index=entry.index)
    if lo is not None:
        ok &= entry >= pd.Timestamp(lo)
    if hi is not None:
        ok &= exit_ <= pd.Timestamp(hi)
    return ok


# ==========================================================================
# stage panel
# ==========================================================================


def _load_spy() -> pd.DataFrame:
    import duckdb

    from scripts import run_t20260929_35_overnight_persistence as t35

    con = duckdb.connect()
    df = con.execute(
        f"""
        SELECT CAST(timezone('America/New_York', "timestamp") AS DATE) AS date, open, close
        FROM read_parquet('{t35.DAILY_GLOB}') WHERE symbol = 'SPY' AND open > 0 AND close > 0
        ORDER BY date
        """
    ).df()
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    return df.drop_duplicates("date").set_index("date")


def stage_panel() -> None:
    import gc

    from open_composer.research.features import price_hygiene as ph
    from scripts import run_t20260929_32_gap_fade_ls as t32
    from scripts import run_t20260929_35_overnight_persistence as t35

    t0 = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    info = json.loads(CAND_PATH.read_text(encoding="utf-8"))
    symbols, dates = info["symbols"], info["dates"]
    delisted_only = set(info["delisted_only_symbols"])
    _log(f"candidates: {len(symbols):,} symbols, {len(dates)} dates ({dates[0]}..{dates[-1]})")
    wide = t35.load_wide_float32(symbols, dates)
    wide.pop("_overlap")
    wide.pop("high", None)
    wide.pop("low", None)
    close_s, open_s, rep = ph.sanitize_price_matrices(wide["close"], wide["open"])
    assert open_s is not None
    vol = wide["volume"].where(close_s.notna())
    del wide
    close_s = close_s.astype("float32")
    open_s = open_s.astype("float32")
    gc.collect()
    _log(f"hygiene: masked symbols {int(rep.symbols_masked)}, cells {int(rep.price_cells_masked)}")

    cal = pd.DatetimeIndex(pd.to_datetime(dates))
    n = len(cal)
    spy = _load_spy().reindex(cal)
    spy_ret = (spy["close"] / spy["close"].shift(1) - 1.0).to_numpy(dtype="float64")
    spy.to_parquet(SPY_PATH)

    prev = close_s.shift(1)
    flag = t32.is_split_like_ratio((close_s / prev).to_numpy()) | t32.is_split_like_ratio(
        (open_s / prev).to_numpy()
    )
    ret = (close_s / prev - 1.0).to_numpy(dtype="float64")
    ret[flag] = np.nan
    ret_adj = (ret - spy_ret[:, None]).astype("float32")
    del ret, prev
    cum_flag = flag.cumsum(axis=0).astype("int32")
    _log(f"split-like trigger cells masked: {int(flag.sum()):,}")
    del flag
    c_arr = close_s.to_numpy()
    o_arr = open_s.to_numpy()
    v_arr = vol.to_numpy(dtype="float64")
    cols = close_s.columns.to_numpy()
    del vol
    gc.collect()

    tau_idx = month_end_indices(cal)
    form_idx = np.array([t for t in tau_idx if t >= MOM_LOOKBACK and t >= DV_WINDOW])
    _log(f"month-ends {len(tau_idx)}, formations {len(form_idx)}: first {cal[form_idx[0]].date()}")

    groups = []
    for f in form_idx:
        win = c_arr[f - DV_WINDOW : f].astype("float64") * v_arr[f - DV_WINDOW : f]
        valid_all = np.isfinite(win).all(axis=0)
        dv = np.full(win.shape[1], np.nan)
        dv[valid_all] = np.median(win[:, valid_all], axis=0)
        cand = np.flatnonzero(np.isfinite(dv))
        top = cand[np.argsort(-dv[cand], kind="stable")][:POOL_N]
        c_skip, c_look = c_arr[f - MOM_SKIP, top], c_arr[f - MOM_LOOKBACK, top]
        mom = np.where(np.isfinite(c_skip) & np.isfinite(c_look), c_skip / c_look - 1.0, np.nan)
        groups.append(
            {"f": int(f), "members": top, "dv": dv[top], "mom": mom, "dec": assign_deciles(mom)}
        )
    del v_arr
    gc.collect()

    # daily long table
    blocks = []
    for i, g in enumerate(groups):
        lo = g["f"] + GROUP_LAG
        hi = groups[i + 1]["f"] + GROUP_LAG - 1 if i + 1 < len(groups) else n - 1
        days = np.arange(lo, hi + 1)
        nm = len(g["members"])
        di = np.repeat(days, nm)
        ci = np.tile(g["members"], len(days))
        blocks.append(
            pd.DataFrame(
                {
                    "date": cal[di],
                    "symbol": pd.Categorical(cols[ci], categories=cols),
                    "mom_decile": np.tile(g["dec"], len(days)).astype("float32"),
                    "weight_dv": np.tile(g["dv"], len(days)),
                    "ret_cc_adj": ret_adj[di, ci],
                    "open": o_arr[di, ci],
                    "close": c_arr[di, ci],
                    "in_p500": True,
                    "form_date": cal[g["f"]],
                }
            )
        )
    panel = pd.concat(blocks, ignore_index=True)
    panel.to_parquet(PANEL_PATH, index=False)
    _log(f"wrote {PANEL_PATH} rows={len(panel):,}")

    # event legs: group formed at tau_{m-1}, trade b+1 open -> tau+4 open
    ev_blocks = []
    for i in range(len(groups) - 1):
        g = groups[i]
        tau = groups[i + 1]["f"]
        exit_i = tau + 4
        entry_era = tau - settle_offset(cal[tau]) + 1
        entry_fix = tau - 4 + 1
        legs = {}
        for tag, ent in (("era", entry_era), ("fix4", entry_fix)):
            o_in, o_out = o_arr[ent, g["members"]], o_arr[exit_i, g["members"]]
            leg = o_out / o_in - 1.0
            bad = (
                ~np.isfinite(leg)
                | ((cum_flag[exit_i, g["members"]] - cum_flag[ent, g["members"]]) > 0)
                | ((cum_flag[ent, g["members"]] - cum_flag[ent - 1, g["members"]]) > 0)
            )
            leg = np.where(bad, np.nan, leg)
            legs[tag] = leg
        ev_blocks.append(
            pd.DataFrame(
                {
                    "tau": cal[tau],
                    "symbol": cols[g["members"]],
                    "mom_decile": g["dec"].astype("float32"),
                    "weight_dv": g["dv"],
                    "r_open_era": legs["era"],
                    "r_open_fix4": legs["fix4"],
                    "entry_era": cal[entry_era],
                    "entry_fix4": cal[entry_fix],
                    "exit": cal[exit_i],
                }
            )
        )
    events = pd.concat(ev_blocks, ignore_index=True)
    events.to_parquet(EVENTS_PATH, index=False)
    _log(f"wrote {EVENTS_PATH} rows={len(events):,}")

    member_syms = {s for g in groups for s in cols[g["members"]]}
    meta = {
        "built_at": datetime.now(UTC).isoformat(),
        "n_candidate_symbols": len(symbols),
        "calendar_start": str(cal[0].date()),
        "calendar_end": str(cal[-1].date()),
        "formation_dates": [str(cal[g["f"]].date()) for g in groups],
        "pool_sizes": [int(len(g["members"])) for g in groups],
        "names_with_momentum": [int(np.isfinite(g["mom"]).sum()) for g in groups],
        "d1_sizes": [int((g["dec"] == 1).sum()) for g in groups],
        "p500_symbols_ever": len(member_syms),
        "delisted_symbols_in_pool": len(member_syms & delisted_only),
        "hygiene_symbols_masked": int(rep.symbols_masked),
        "hygiene_cells_masked": int(rep.price_cells_masked),
        "panel_rows": int(len(panel)),
    }
    META_PATH.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    _log(f"panel stage done in {time.time() - t0:.0f}s")


# ==========================================================================
# stage measure
# ==========================================================================


def _series_block(
    series: dict[str, pd.Series], frame: pd.DataFrame
) -> tuple[dict[str, Any], dict[str, Any], bool]:
    m1: dict[str, Any] = {}
    m2: dict[str, Any] = {}
    for name, s in series.items():
        s = s.reindex(frame.index)
        has_event = (frame["event"] >= 0).to_numpy()
        y = s.to_numpy(dtype="float64")
        entry: dict[str, Any] = {}
        m2e: dict[str, Any] = {}
        for seg in ("all", "pre", "post"):
            sel = has_event if seg == "all" else has_event & (frame["seg"] == seg).to_numpy()
            r = m1_regression(y[sel], frame["pre"].to_numpy()[sel], frame["post"].to_numpy()[sel])
            pm = sel & frame["post"].to_numpy()
            pv = y[pm]
            pv = pv[np.isfinite(pv)]
            m2_seg = {
                "mean_bp": float(pv.mean() * BP) if len(pv) else float("nan"),
                "t_nw": float(nw_t(pv, NW_M1)) if len(pv) > NW_M1 + 1 else float("nan"),
                "n_days": int(len(pv)),
            }
            if seg == "all":
                entry.update(r)
                m2e.update(m2_seg)
            else:
                entry[seg] = r
                m2e[seg] = m2_seg
        m1[name] = entry
        m2[name] = m2e
    d1 = m1["d1_dv"]
    m1_pass = bool(d1["coef_bp"] < 0 and d1["t_nw"] <= M1_T_BAR)
    return m1, m2, m1_pass


def _trade_table(events: pd.DataFrame, spy: pd.DataFrame, mode: str) -> dict[str, Any]:
    rcol = "r_open_era" if mode == "era" else "r_open_fix4"
    ecol = "entry_era" if mode == "era" else "entry_fix4"
    rows = []
    for tau, g in events.groupby("tau", sort=True):
        entry, exit_ = g[ecol].iloc[0], g["exit"].iloc[0]
        r = g[rcol]
        w = g["weight_dv"]
        rec: dict[str, Any] = {"tau": tau, "entry": entry, "exit": exit_}
        for name, dec in (("d1", 1.0), ("d10", 10.0)):
            sel = (g["mom_decile"] == dec) & r.notna()
            rec[f"{name}_dv"] = (
                float((w[sel] * r[sel]).sum() / w[sel].sum()) if sel.any() else np.nan
            )
            rec[f"{name}_ew"] = float(r[sel].mean()) if sel.any() else np.nan
        rec["p500_ew"] = float(r.mean()) if r.notna().any() else np.nan
        so_in, so_out = spy["open"].get(entry, np.nan), spy["open"].get(exit_, np.nan)
        rec["spy"] = float(so_out / so_in - 1.0)
        rows.append(rec)
    t = pd.DataFrame(rows)
    t["d1_dv_minus_spy"] = t["d1_dv"] - t["spy"]
    out: dict[str, Any] = {}
    for port in ("d1_dv", "d1_ew", "d1_dv_minus_spy", "d10_dv", "p500_ew"):
        rt = 40.0 if port.endswith("minus_spy") else 20.0  # round-trip bp at 10 bp/side
        out[port] = {}
        for wname, (lo, hi) in WINDOWS.items():
            sel = in_window(t["entry"], t["exit"], lo, hi)
            out[port][wname] = trade_stats(t.loc[sel, port].to_numpy(), rt)
    return out


def stage_measure() -> None:
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    panel = pd.read_parquet(
        PANEL_PATH, columns=["date", "symbol", "mom_decile", "weight_dv", "ret_cc_adj"]
    )
    events = pd.read_parquet(EVENTS_PATH)
    spy = pd.read_parquet(SPY_PATH)
    cal = pd.DatetimeIndex(sorted(panel["date"].unique()))
    form_dates = pd.to_datetime(meta["formation_dates"])
    event_tau = form_dates[1:]
    tau_idx = cal.get_indexer(event_tau)
    assert (tau_idx >= 0).all()
    frame = build_event_frame(cal, tau_idx)
    _log(f"panel days {len(cal)}, events {len(tau_idx)}")

    d1_dv = group_daily(panel, 1, "dv")
    series = {
        "d1_dv": d1_dv,
        "d1_ew": group_daily(panel, 1, "ew"),
        "d10_dv": group_daily(panel, 10, "dv"),
    }
    series["d1_minus_d10_dv"] = series["d1_dv"] - series["d10_dv"]
    m1, m2, m1_pass = _series_block(series, frame)

    # M3
    obs = m3_observations(d1_dv, cal, tau_idx)
    obs = obs[~((obs["tau"] >= pd.Timestamp("2024-05-01")) & (obs["tau"] < POST_START))]
    obs = obs.reset_index(drop=True)
    versions = {
        "overlap_2024_2025": (
            lambda t: (
                (t < pd.Timestamp("2024-05-01"))
                | ((t >= POST_START) & (t < pd.Timestamp("2026-01-01")))
            )
        ),
        "out_of_paper_2026": (
            lambda t: (t < pd.Timestamp("2024-05-01")) | (t >= pd.Timestamp("2026-01-01"))
        ),
        "combined": (lambda t: (t < pd.Timestamp("2024-05-01")) | (t >= POST_START)),
    }
    m3: dict[str, Any] = {}
    for vname, keep in versions.items():
        sub = obs[keep(obs["tau"])].reset_index(drop=True)
        post_mask = (sub["tau"] >= POST_START).to_numpy()
        est = m3_estimate(sub, post_mask)
        est["cell_means"] = m3_cell_means(sub)
        m3[vname] = est

    trade = {
        "era": _trade_table(events, spy, "era"),
        "fix4": _trade_table(events, spy, "fix4"),
    }
    daily = pd.DataFrame(series)
    daily = daily.join(frame[["event", "pre", "post", "pos", "seg"]])
    daily.to_parquet(CACHE_DIR / "xs_daily_series.parquet")

    results = {
        "generated_at": datetime.now(UTC).isoformat(),
        "preregistered_at": PREREG_TS_PATH.read_text(encoding="utf-8").strip(),
        "n_months": int(len(tau_idx)),
        "first_month": str(event_tau[0].date()),
        "last_month": str(event_tau[-1].date()),
        "pool_size_median": float(np.median(meta["pool_sizes"])),
        "d1_size_median": float(np.median(meta["d1_sizes"])),
        "delisted_symbols_in_pool": int(meta["delisted_symbols_in_pool"]),
        "p500_symbols_ever": int(meta["p500_symbols_ever"]),
        "panel_days": int(len(cal)),
        "m1": m1,
        "m1_pass": m1_pass,
        "m2": m2,
        "m3": m3,
        "trade": trade,
        "notes": {
            "group_timing": "group formed at tau_f is active from tau_f+4 to tau_{f+1}+3",
            "missing_returns": "delisted/missing returns dropped from group averages, not zero",
            "first_formable_month": "calendar starts 2016-01-04; 252-day momentum needs history",
            "windows": {k: list(v) for k, v in WINDOWS.items()},
        },
    }
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    _log(f"wrote {RESULTS_PATH}")


# ==========================================================================
# stage report
# ==========================================================================


def _f(x: Any, nd: int = 2) -> str:
    return "nan" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def stage_report() -> None:
    r = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    lines = [
        "# T-20261001-02 cross-section mechanism measurement (report_xs)",
        "",
        f"Generated {r['generated_at']} from `results_xs.json`. No verdict.",
        f"Months {r['n_months']} ({r['first_month']} .. {r['last_month']}), pool median "
        f"{r['pool_size_median']:.0f}, D1 median {r['d1_size_median']:.0f}, "
        f"delisted symbols ever in P500: {r['delisted_symbols_in_pool']}.",
        "",
        "## M1 / M2 / M3",
        "",
        "| item | series | coef/mean (bp) | t (NW) | n days |",
        "|---|---|---|---|---|",
    ]
    for name, e in r["m1"].items():
        for seg, d in (("all", e), ("pre", e["pre"]), ("post", e["post"])):
            lines.append(
                f"| M1 pre-window minus rest ({seg}) | {name} | {_f(d['coef_bp'])} | "
                f"{_f(d['t_nw'])} | {d['n_days']} |"
            )
    lines.append(f"| M1 pass (d1_dv coef<0, t<=-2.0) | d1_dv | {r['m1_pass']} | | |")
    for name, e in r["m2"].items():
        for seg, d in (("all", e), ("pre", e["pre"]), ("post", e["post"])):
            lines.append(
                f"| M2 post-window mean ({seg}) | {name} | {_f(d['mean_bp'])} | "
                f"{_f(d['t_nw'])} | {d['n_days']} |"
            )
    lines += [
        "",
        "| M3 version | theta4 (bp) | theta3 (bp) | theta4-theta3 (bp) | t | pre/post months |",
        "|---|---|---|---|---|---|",
    ]
    for v, e in r["m3"].items():
        lines.append(
            f"| {v} | {_f(e['theta4_bp'])} | {_f(e['theta3_bp'])} | {_f(e['diff_bp'])} | "
            f"{_f(e['diff_t'])} | {e['n_pre_months']}/{e['n_post_months']} |"
        )
    lines += ["", "M3 cell means (combined version, bp / months):", ""]
    for k, c in r["m3"]["combined"]["cell_means"].items():
        lines.append(f"- {k}: {_f(c['mean_bp'])} bp, {c['n_months']} months")
    lines += [
        "",
        "## Long-only trade economics (era b, b+1 open -> tau+4 open, once per month)",
        "",
        "| portfolio | window | gross bp | gross t | net10 bp | net20 bp | Sharpe net10 | months |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for port, wins in r["trade"]["era"].items():
        for w, s in wins.items():
            lines.append(
                f"| {port} | {w} | {_f(s['gross_mean_bp'])} | {_f(s['gross_t'])} | "
                f"{_f(s['net10_mean_bp'])} | {_f(s['net20_mean_bp'])} | "
                f"{_f(s['sharpe_net10'])} | {s['n_months']} |"
            )
    lines += [
        "",
        "Fixed tau-4 b-rule results are in `results_xs.json` under `trade.fix4`.",
        "Caveats: survivor handling drops missing delisted returns (favourable to long losers); "
        "formation history starts 2017-01 (calendar starts 2016-01-04).",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    _log(f"wrote {REPORT_PATH}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", choices=["panel", "measure", "report", "all"], default="all")
    args = ap.parse_args()
    if args.stage in ("panel", "all"):
        stage_panel()
    if args.stage in ("measure", "all"):
        stage_measure()
    if args.stage in ("report", "all"):
        stage_report()


if __name__ == "__main__":
    main()
