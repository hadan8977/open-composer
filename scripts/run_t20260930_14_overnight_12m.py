# ruff: noqa: E501
"""T-20260930-14 (corridor C2a-prime): one-year overnight persistence (ON252), out-of-sample band
(test A) and official auction-price pairing (test B), plus six diagnostics.

Design is frozen in ``reports/research/iterations/t20260930_14_overnight_persistence_12m/
hypotheses.md`` (written before any pool B or official-price number was computed). This script only
executes that design; it changes no pool, signal, window, gate, seed or cost.

Stages (argparse sub-commands):

* ``band``      -- test A. Symbols that ever rank in the dv21 top 3200 (non-fund, non-OTC), wide
  float32 matrices built in symbol chunks (same loader, ``price_hygiene`` defaults and split-like
  filter as T-20260929-35), pool B = dv21 rank 1501..3000 with the T-35 filters, ON252 decile
  long/short nightly series, Newey-West t, 100-seed same-pool placebo, by-year, next-day
  intraday leg. Cache: ``cache/band_panel.parquet``; result: ``cache/band_results.json``.
* ``official``  -- test B. 20 sampled days (numpy default_rng(20260930)), ON252_P500 long decile,
  short decile and LO top 20 from the T-35 panel; official closing print (day t) and opening print
  (day t+1) via the T-20260930-11 functions, put on the daily-bar (adjusted) basis with the raw
  daily close factor; Delta = r_official - r_daily. Resumable, <= 3 requests/s.
* ``diag``      -- diagnostics 1-6 on the T-35 panel (ON252, P500 and P1500), then merges the three
  stage results into ``results.json`` and ``report.md`` and computes ``gate_a`` / ``gate_b``.
* ``report``    -- rewrite report.md / results.json from the three stage results (no compute).

Conventions where hypotheses.md leaves a detail open (all echoed in the report):

* sample days are drawn from the main-window dates on which the ON252_P500 book has a valid night
  (>= 40 names with finite signal and finite next-night return; the last panel date has no next open);
* the ON252 signal is computed with the T-35 constants (252 window, >= 200 valid overnights) on one
  signal only to save memory (equal to ``t35.rolling_signals(...)['ON252']``, unit tested);
* 12-1 momentum = close_{t-21} / close_{t-252} - 1 from the daily-bar close read with the same
  loader and price_hygiene cleaning as the T-35 panel (source: daily bars, not derived returns);
* an ADR name is a symbol whose ``_asset_metadata`` name matches the frozen pattern; delisted
  symbols without metadata count as non-ADR (coverage reported); ex-ADR LS re-forms the deciles
  after dropping ADR names.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import subprocess
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

from open_composer.research.features import price_hygiene as ph  # noqa: E402
from scripts import run_t20260929_32_gap_fade_ls as t32  # noqa: E402
from scripts import run_t20260929_35_overnight_persistence as t35  # noqa: E402
from scripts import run_t20260930_11_gap_fade_auction as c1  # noqa: E402

ITERATION_ID = "t20260930_14_overnight_persistence_12m"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
CAND_PATH = CACHE_DIR / "candidates.json"
BAND_PANEL_PATH = CACHE_DIR / "band_panel.parquet"
BAND_META_PATH = CACHE_DIR / "band_meta.json"
BAND_RESULTS_PATH = CACHE_DIR / "band_results.json"
PICKS_PATH = CACHE_DIR / "official_picks.parquet"
OFFICIAL_PATH = CACHE_DIR / "official_prices.jsonl"
RAWBARS_PATH = CACHE_DIR / "raw_bars.jsonl"
TAPE_PATH = CACHE_DIR / "tape_by_symbol.json"
OFFICIAL_RESULTS_PATH = CACHE_DIR / "official_results.json"
MOM_PATH = CACHE_DIR / "mom.parquet"
DIAG_RESULTS_PATH = CACHE_DIR / "diag_results.json"
RESULTS_PATH = OUT_DIR / "results.json"
REPORT_PATH = OUT_DIR / "report.md"
PREBACKTEST_STAMP = OUT_DIR / "prebacktest-validated-at.txt"
T35_DIR = ROOT / "reports" / "research" / "iterations" / "t20260929_35_overnight_persistence"
T35_PANEL = T35_DIR / "cache" / "panel.parquet"
T35_SPY = T35_DIR / "cache" / "spy_overnight.parquet"
T35_CANDS = T35_DIR / "cache" / "candidates.json"
T35_RESULTS = T35_DIR / "results.json"
EARNINGS_GLOB = ROOT / "data" / "features" / "earnings_events"

POOL_B_LO, POOL_B_HI = 1501, 3000
CANDIDATE_TOP_N_B = 3200
CHUNK_SYMBOLS = 2000
SEED = 20260930
N_SAMPLE_DAYS = 20
LO_N = t35.LO_N
WINDOWS = {"main": t35.WINDOWS["main"], "stress": t35.WINDOWS["stress"]}
GATE_A_T_MIN = 2.0
GATE_B_DELTA_MIN_BP = -4.0
GATE_B_MISSING_MAX = 0.10
ADR_PATTERN = r"\bADR\b|American Depositary|Depositary Shares?"
MIN_NIGHT_NAMES = 40
ON252_WINDOW = t35.SIGNAL_LOOKBACK["ON252"]
ON252_MIN_OBS = t35.SIGNAL_MIN_OBS["ON252"]
BARS_URL = c1.BARS_URL


def _log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


# ==========================================================================
# pure helpers (unit tested)
# ==========================================================================


def pool_b_mask(rank: np.ndarray, lo: int = POOL_B_LO, hi: int = POOL_B_HI) -> np.ndarray:
    """dv21 rank band, both ends included (rank is 1-based, NaN = unranked)."""
    r = np.asarray(rank, dtype="float64")
    return np.isfinite(r) & (r >= lo) & (r <= hi)


def on252_signal(on: pd.DataFrame) -> pd.DataFrame:
    """T-35's ON252 (rolling mean of ON over 252 sessions, >= 200 valid)."""
    return on.rolling(ON252_WINDOW, min_periods=ON252_MIN_OBS).mean()


def sample_days(
    eligible: pd.DatetimeIndex | list[str], seed: int = SEED, n: int = N_SAMPLE_DAYS
) -> list[str]:
    """``n`` trading days drawn without replacement with numpy default_rng(seed), sorted."""
    days = sorted(str(pd.Timestamp(d).date()) for d in eligible)
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(days), size=min(n, len(days)), replace=False)
    return [days[i] for i in sorted(int(i) for i in pick)]


def adj_factor(local_close: float, raw_close: float) -> float:
    """f_d = daily-bar (adjusted) close / raw close of the same session."""
    if not (math.isfinite(local_close) and math.isfinite(raw_close)) or raw_close <= 0:
        return float("nan")
    return float(local_close / raw_close)


def official_return(o_next: float, c_t: float, f_next: float, f_t: float) -> float:
    """r_official = (official open_{t+1} * f_{t+1}) / (official close_t * f_t) - 1."""
    vals = (o_next, c_t, f_next, f_t)
    if not all(math.isfinite(v) for v in vals) or c_t <= 0 or f_t <= 0:
        return float("nan")
    return float((o_next * f_next) / (c_t * f_t) - 1.0)


def pair_delta(r_official: np.ndarray, r_daily: np.ndarray) -> np.ndarray:
    """Delta = r_official - r_daily (decimal returns, elementwise)."""
    return np.asarray(r_official, dtype="float64") - np.asarray(r_daily, dtype="float64")


def day_then_day_mean(delta: np.ndarray, days: np.ndarray) -> tuple[float, int]:
    """Mean over days of the within-day mean of finite deltas."""
    d = np.asarray(delta, dtype="float64")
    dd = np.asarray(days)
    means = [
        float(np.mean(d[(dd == u) & np.isfinite(d)]))
        for u in np.unique(dd)
        if np.isfinite(d[dd == u]).any()
    ]
    return (float(np.mean(means)) if means else float("nan"), len(means))


def delta_ls_by_day(delta: np.ndarray, days: np.ndarray, leg: np.ndarray) -> tuple[float, int]:
    """mean over days of (mean Delta long - mean Delta short); days lacking a leg are dropped."""
    d = np.asarray(delta, dtype="float64")
    out = []
    for u in np.unique(days):
        m = days == u
        lg = d[m & (leg == "long") & np.isfinite(d)]
        sh = d[m & (leg == "short") & np.isfinite(d)]
        if len(lg) and len(sh):
            out.append(float(lg.mean() - sh.mean()))
    return (float(np.mean(out)) if out else float("nan"), len(out))


def gate_a(main_mean_bp: float, main_t: float, stress_mean_bp: float, stress_t: float) -> bool:
    """Both windows: mean > 0 and Newey-West t >= 2.0."""
    vals = (main_mean_bp, main_t, stress_mean_bp, stress_t)
    if not all(math.isfinite(v) for v in vals):
        return False
    return bool(
        main_mean_bp > 0
        and main_t >= GATE_A_T_MIN
        and stress_mean_bp > 0
        and stress_t >= GATE_A_T_MIN
    )


def gate_b(delta_ls_bp: float, delta_lo20_bp: float, missing_share: float) -> bool:
    """delta_LS >= -4 bp, delta_LO20 >= -4 bp, missing share <= 10 percent."""
    vals = (delta_ls_bp, delta_lo20_bp, missing_share)
    if not all(math.isfinite(v) for v in vals):
        return False
    return bool(
        delta_ls_bp >= GATE_B_DELTA_MIN_BP
        and delta_lo20_bp >= GATE_B_DELTA_MIN_BP
        and missing_share <= GATE_B_MISSING_MAX + 1e-12
    )


def _clean(obj: Any) -> Any:
    return t35._clean(obj)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_clean(obj), indent=1) + "\n", encoding="utf-8")


def _window_stats(series: pd.Series | np.ndarray, index: pd.DatetimeIndex) -> dict[str, Any]:
    a = np.asarray(series, dtype="float64")
    return {w: t35.series_stats(a[t35.window_mask(index, win)]) for w, win in WINDOWS.items()}


# ==========================================================================
# stage candidates / band
# ==========================================================================


def find_candidates() -> None:
    """Symbols that ever rank in the dv21 top 3200 (t35 finder, patched to this cache)."""
    t35.CANDIDATE_TOP_N = CANDIDATE_TOP_N_B
    t35.CACHE_DIR = CACHE_DIR
    t35.CAND_PATH = CAND_PATH
    excluded = pd.read_parquet(CACHE_DIR / "excluded_symbols.parquet")
    t35.find_candidate_symbols(excluded)


def _process_chunk(symbols: list[str], dates: list[str]) -> dict[str, Any]:
    """One symbol chunk through the T-35 cleaning; returns float32/bool matrices (dates x symbols)."""
    wide = t35.load_wide_float32(symbols, dates)
    overlap = int(wide.pop("_overlap"))  # type: ignore[arg-type]
    open_w, close_w, vol_w = wide["open"], wide["close"], wide["volume"]
    del wide
    raw_valid = int(close_w.notna().to_numpy().sum())
    close_s, open_s, report = ph.sanitize_price_matrices(close_w, open_w)
    assert open_s is not None
    vol_s = vol_w.mask(close_s.isna())
    del close_w, open_w, vol_w
    close_s = close_s.astype("float32")
    open_s = open_s.astype("float32")
    prev_close = close_s.shift(1)
    gap_ratio = open_s / prev_close
    split_like = pd.DataFrame(
        t32.is_split_like_ratio(gap_ratio.to_numpy()),
        index=gap_ratio.index,
        columns=gap_ratio.columns,
    )
    n_split = int(split_like.to_numpy().sum())
    del gap_ratio
    split_next = split_like.shift(-1, fill_value=False)
    dv21 = (close_s * vol_s).shift(1).rolling(t35.DV_WINDOW, min_periods=t35.DV_WINDOW).mean()
    del vol_s
    history = close_s.notna().shift(1, fill_value=False).cumsum()
    base_ok = (prev_close >= t35.MIN_CLOSE) & (history >= t35.MIN_HISTORY) & dv21.notna()
    del history, prev_close
    on, _id = t35.overnight_intraday_returns(open_s, close_s)
    del _id
    on = on.where(~split_like)
    on252 = on252_signal(on)
    del on
    r = t35.next_night_return(open_s, close_s).where(~split_next)
    idn = t35.next_day_intraday_return(open_s, close_s)
    out = {
        "dv21": dv21.astype("float32").to_numpy(),
        "base_ok": base_ok.to_numpy(),
        "on252": on252.astype("float32").to_numpy(),
        "r": r.astype("float32").to_numpy(),
        "idn": idn.astype("float32").to_numpy(),
        "n_split": n_split,
        "overlap": overlap,
        "raw_valid": raw_valid,
        "hygiene": {
            "symbols_masked": int(report.symbols_masked),
            "symbols_masked_for_jump": int(report.symbols_masked_for_jump),
            "symbols_masked_for_gap": int(report.symbols_masked_for_gap),
            "price_cells_masked": int(report.price_cells_masked),
        },
    }
    del close_s, open_s, dv21, base_ok, on252, r, idn, split_like, split_next
    gc.collect()
    return out


def build_band_panel() -> None:
    t_start = time.time()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    meta = t35._load_metadata()
    is_fund = meta["is_probable_fund_or_etf"].fillna(False).astype(bool)
    is_otc = meta["exchange"].astype(str).str.contains("OTC", na=False)
    if not CAND_PATH.exists():
        meta.loc[is_fund | is_otc, ["symbol"]].to_parquet(
            CACHE_DIR / "excluded_symbols.parquet", index=False
        )
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "candidates"], check=True)
    info = json.loads(CAND_PATH.read_text(encoding="utf-8"))
    symbols: list[str] = info["symbols"]
    dates: list[str] = info["dates"]
    delisted_only = set(info["delisted_only_symbols"])
    _log(
        f"candidate symbols (ever dv21 top {CANDIDATE_TOP_N_B}): {len(symbols):,}, dates {len(dates)}"
    )
    n_d, n_s = len(dates), len(symbols)
    dv21_all = np.full((n_d, n_s), np.nan, dtype="float32")
    on252_all = np.full((n_d, n_s), np.nan, dtype="float32")
    r_all = np.full((n_d, n_s), np.nan, dtype="float32")
    idn_all = np.full((n_d, n_s), np.nan, dtype="float32")
    base_all = np.zeros((n_d, n_s), dtype=bool)
    tot = {"n_split": 0, "overlap": 0, "raw_valid": 0}
    hyg = {
        "symbols_masked": 0,
        "symbols_masked_for_jump": 0,
        "symbols_masked_for_gap": 0,
        "price_cells_masked": 0,
    }
    for lo in range(0, n_s, CHUNK_SYMBOLS):
        chunk = symbols[lo : lo + CHUNK_SYMBOLS]
        _log(f"chunk {lo}-{lo + len(chunk)} of {n_s}")
        res = _process_chunk(chunk, dates)
        sl = slice(lo, lo + len(chunk))
        dv21_all[:, sl] = res["dv21"]
        on252_all[:, sl] = res["on252"]
        r_all[:, sl] = res["r"]
        idn_all[:, sl] = res["idn"]
        base_all[:, sl] = res["base_ok"]
        for k in tot:
            tot[k] += res[k]
        for k in hyg:
            hyg[k] += res["hygiene"][k]
        del res
        gc.collect()
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    cols = pd.Index(symbols)
    dv21_df = pd.DataFrame(dv21_all, index=idx, columns=cols)
    del dv21_all
    rk = t35.rank_desc(dv21_df).to_numpy()
    del dv21_df
    gc.collect()
    pool_b = base_all & pool_b_mask(rk)
    rows, colsi = np.where(pool_b)
    del base_all
    delisted_flag = np.asarray([s in delisted_only for s in symbols])
    panel = pd.DataFrame(
        {
            "date": idx.to_numpy()[rows],
            "symbol": pd.Categorical(np.asarray(symbols)[colsi]),
            "delisted": delisted_flag[colsi],
            "rank": rk[rows, colsi].astype("int16"),
        }
    )
    panel["on252"] = on252_all[rows, colsi]
    panel["r"] = r_all[rows, colsi]
    panel["idn"] = idn_all[rows, colsi]
    assert panel["date"].is_monotonic_increasing
    panel.to_parquet(BAND_PANEL_PATH, index=False)
    by_date = panel.groupby("date").size()
    pool_syms = set(panel["symbol"].astype(str).unique())
    data = {
        "pool": f"dv21 rank {POOL_B_LO}..{POOL_B_HI} (both ends included), non-fund non-OTC, close_(t-1) >= $5, >= 63 sessions, dv21 valid",
        "candidate_symbols_ever_top_n": len(symbols),
        "candidate_top_n": CANDIDATE_TOP_N_B,
        "n_symbols_daily_root": info["n_symbols_daily_root"],
        "n_symbols_delisted_root": info["n_symbols_delisted_root"],
        "symbols_in_pool_b": len(pool_syms),
        "delisted_symbols_in_pool_b": len(pool_syms & delisted_only),
        "delisted_share_of_pool_symbols": float(
            len(pool_syms & delisted_only) / max(1, len(pool_syms))
        ),
        "delisted_share_of_pool_rows": float(panel["delisted"].mean()),
        "mean_daily_pool_size_b": float(by_date.mean()),
        "panel_rows": int(len(panel)),
        "panel_date_min": str(panel["date"].min().date()),
        "panel_date_max": str(panel["date"].max().date()),
        "split_filtered_rows": tot["n_split"],
        "cells_in_both_roots": tot["overlap"],
        "raw_valid_close_cells": tot["raw_valid"],
        "hygiene": hyg,
        "panel_seconds": round(time.time() - t_start, 1),
    }
    _write_json(BAND_META_PATH, data)
    _log(f"band panel written: {len(panel):,} rows; {json.dumps(_clean(data))[:500]}")


def run_band_series(
    panel: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[int, np.ndarray], pd.DatetimeIndex]:
    """Nightly ON252 decile LS on pool B (t35.decile_long_short; same >= 40 valid names rule)."""
    panel = panel.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    dates = pd.DatetimeIndex(np.sort(panel["date"].unique()))
    starts = np.asarray(panel["date"].searchsorted(dates, side="left"))
    ends = np.append(starts[1:], len(panel))
    sig = panel["on252"].to_numpy("float64")
    ret = panel["r"].to_numpy("float64")
    idn = panel["idn"].to_numpy("float64")
    cols = ("gross", "long", "short", "pool_ew", "n_valid", "k", "idn_ls")
    out = {c: np.full(len(dates), np.nan) for c in cols}
    valid_r: dict[int, np.ndarray] = {}
    for i in range(len(dates)):
        s, e = starts[i], ends[i]
        m = np.isfinite(sig[s:e]) & np.isfinite(ret[s:e])
        if m.sum() < MIN_NIGHT_NAMES:
            continue
        idx = np.nonzero(m)[0] + s
        x, rr = sig[idx], ret[idx]
        out["pool_ew"][i] = rr.mean()
        out["n_valid"][i] = len(idx)
        valid_r[i] = rr
        res = t35.decile_long_short(x, rr)
        if res is None:
            continue
        out["gross"][i], out["long"][i], out["short"][i], out["k"][i] = (
            res["ls"],
            res["long"],
            res["short"],
            res["k"],
        )
        il, is_ = idn[idx[res["long_idx"]]], idn[idx[res["short_idx"]]]
        if np.isfinite(il).any() and np.isfinite(is_).any():
            out["idn_ls"][i] = np.nanmean(il) - np.nanmean(is_)
    return pd.DataFrame(out, index=dates), valid_r, dates


def band_stage() -> None:
    t0 = time.time()
    if not PREBACKTEST_STAMP.exists():
        raise SystemExit("prebacktest-validated-at.txt missing: run the pre-backtest gate first")
    if not BAND_PANEL_PATH.exists():
        build_band_panel()
    meta = json.loads(BAND_META_PATH.read_text(encoding="utf-8"))
    panel = pd.read_parquet(BAND_PANEL_PATH)
    df, valid_r, dates = run_band_series(panel)
    _log(f"series: {int(df['gross'].notna().sum())} nights of {len(dates)}")
    seeds = t35.PLACEBO_SEEDS
    wmask = {w: t35.window_mask(dates, win) for w, win in WINDOWS.items()}
    pmeans = {w: np.full(seeds, np.nan) for w in WINDOWS}
    for seed in range(seeds):
        ps = t35.placebo_series(valid_r, len(dates), seed)
        for w, m in wmask.items():
            v = ps[m]
            v = v[np.isfinite(v)]
            if len(v):
                pmeans[w][seed] = v.mean()
    test_a: dict[str, Any] = {}
    for w in WINDOWS:
        g = df["gross"].to_numpy()[wmask[w]]
        stats = t35.series_stats(g)
        real = stats["mean_bp"] / 1e4
        ok = np.isfinite(pmeans[w])
        beat = (
            float(np.mean(real > pmeans[w][ok])) if ok.any() and np.isfinite(real) else float("nan")
        )
        test_a[w] = {
            "mean_bp": stats["mean_bp"],
            "t_nw5": stats["t_nw5"],
            "t": stats["t"],
            "sharpe": stats["sharpe"],
            "n": stats["n"],
            "placebo_beat": beat,
            "placebo_mean_bp": float(np.nanmean(pmeans[w]) * 1e4),
            "long_mean_bp": float(np.nanmean(df["long"].to_numpy()[wmask[w]]) * 1e4),
            "short_mean_bp": float(np.nanmean(df["short"].to_numpy()[wmask[w]]) * 1e4),
            "pool_ew_mean_bp": float(np.nanmean(df["pool_ew"].to_numpy()[wmask[w]]) * 1e4),
            "mean_n_valid": float(np.nanmean(df["n_valid"].to_numpy()[wmask[w]])),
            "mean_k": float(np.nanmean(df["k"].to_numpy()[wmask[w]])),
        }
    test_a["by_year"] = t35.by_year_table(df)
    test_a["next_intraday"] = _window_stats(df["idn_ls"], dates)
    test_a["gate_a"] = gate_a(
        test_a["main"]["mean_bp"],
        test_a["main"]["t_nw5"],
        test_a["stress"]["mean_bp"],
        test_a["stress"]["t_nw5"],
    )
    _write_json(
        BAND_RESULTS_PATH,
        {"test_a": test_a, "data": meta, "band_seconds": round(time.time() - t0, 1)},
    )
    _log(
        f"band done: main {test_a['main']['mean_bp']:.2f} bp t {test_a['main']['t_nw5']:.2f}; stress {test_a['stress']['mean_bp']:.2f} bp t {test_a['stress']['t_nw5']:.2f}; gate_a {test_a['gate_a']}"
    )


# ==========================================================================
# stage official (test B)
# ==========================================================================


def _decile_books(sig: np.ndarray, ret: np.ndarray) -> dict[str, Any] | None:
    """Long/short decile and LO top-20 positions (indices into the given arrays)."""
    res = t35.decile_long_short(sig, ret)
    if res is None or len(sig) < LO_N:
        return None
    order = np.argsort(sig, kind="stable")
    return {
        "long": res["long_idx"],
        "short": res["short_idx"],
        "lo20": order[-LO_N:],
        "k": res["k"],
    }


def build_picks() -> pd.DataFrame:
    if PICKS_PATH.exists():
        return pd.read_parquet(PICKS_PATH)
    panel = pd.read_parquet(T35_PANEL, columns=["date", "symbol", "p500", "on252", "r", "dv21"])
    panel = panel[panel["p500"]].copy()
    panel["symbol"] = panel["symbol"].astype(str)
    panel = panel.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    win = t35.window_mask(pd.DatetimeIndex(panel["date"]), WINDOWS["main"])
    valid = np.isfinite(panel["on252"].to_numpy()) & np.isfinite(panel["r"].to_numpy())
    g = panel[win & valid].groupby("date").size()
    eligible = g[g >= MIN_NIGHT_NAMES].index
    days = sample_days(eligible)
    cal = json.loads(T35_CANDS.read_text(encoding="utf-8"))["dates"]
    cal_pos = {d: i for i, d in enumerate(cal)}
    rows = []
    for d in days:
        sub = panel[(panel["date"] == pd.Timestamp(d)) & valid & True]
        sub = sub[np.isfinite(sub["on252"]) & np.isfinite(sub["r"])]
        books = _decile_books(sub["on252"].to_numpy("float64"), sub["r"].to_numpy("float64"))
        if books is None:
            continue
        nxt = cal[cal_pos[d] + 1]
        legs = {"long": books["long"], "short": books["short"]}
        lo20 = set(int(i) for i in books["lo20"])
        for leg, ii in legs.items():
            for i in ii:
                rec = sub.iloc[int(i)]
                rows.append(
                    {
                        "date": d,
                        "next_date": nxt,
                        "symbol": rec["symbol"],
                        "leg": leg,
                        "lo20": bool(int(i) in lo20) and leg == "long",
                        "r_daily": float(rec["r"]),
                        "on252": float(rec["on252"]),
                        "dv21": float(rec["dv21"]),
                        "k": int(books["k"]),
                    }
                )
    picks = pd.DataFrame(rows)
    picks.to_parquet(PICKS_PATH, index=False)
    return picks


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _fetch_raw_bars(session: Any, picks: pd.DataFrame) -> dict[tuple[str, str], float]:
    """Unadjusted SIP daily close per (symbol, date) for t and t+1 of every sampled day."""
    done_days = {r["asked"] for r in _load_jsonl(RAWBARS_PATH) if r.get("kind") == "asked"}
    for day, g in picks.groupby("date"):
        nxt = g["next_date"].iloc[0]
        syms = sorted(g["symbol"].unique())
        for i in range(0, len(syms), 100):
            batch = syms[i : i + 100]
            key = f"{day}:{','.join(batch)[:60]}:{len(batch)}"
            if key in done_days:
                continue
            params: dict[str, Any] = {
                "symbols": ",".join(batch),
                "timeframe": "1Day",
                "start": f"{day}T00:00:00Z",
                "end": f"{nxt}T23:59:59Z",
                "adjustment": "raw",
                "feed": "sip",
                "limit": 10000,
            }
            token = None
            recs = []
            for _ in range(50):
                if token:
                    params["page_token"] = token
                data = session.get_url(BARS_URL, params)
                for sym, bars in (data.get("bars") or {}).items():
                    for b in bars:
                        recs.append(
                            {
                                "symbol": sym,
                                "date": str(b["t"])[:10],
                                "c": float(b["c"]),
                                "o": float(b["o"]),
                            }
                        )
                token = data.get("next_page_token")
                if not token:
                    break
            with RAWBARS_PATH.open("a") as fh:
                for rec in recs:
                    fh.write(json.dumps(rec) + "\n")
                fh.write(json.dumps({"kind": "asked", "asked": key}) + "\n")
            _log(f"raw bars {day} batch {i // 100}: {len(recs)} bars")
    return {(r["symbol"], r["date"]): r["c"] for r in _load_jsonl(RAWBARS_PATH) if "symbol" in r}


def _tape_for(session: Any, tapes: dict[str, str], symbol: str, next_day: str) -> str | None:
    if symbol in tapes:
        return tapes[symbol]
    z = c1._tape_hint(session, symbol, next_day)
    if z:
        tapes[symbol] = z
        TAPE_PATH.write_text(json.dumps(tapes))
    return z


def fetch_official(picks: pd.DataFrame, session: Any, budget_s: float | None = None) -> None:
    done = {(r["symbol"], r["date"]) for r in _load_jsonl(OFFICIAL_PATH)}
    tapes: dict[str, str] = json.loads(TAPE_PATH.read_text()) if TAPE_PATH.exists() else {}
    rows = picks.drop_duplicates(["symbol", "date"])
    todo = [r for _, r in rows.iterrows() if (r["symbol"], r["date"]) not in done]
    _log(f"official fetch: {len(rows)} rows, {len(todo)} to do, calls so far {session.calls}")
    t0 = time.time()
    with OFFICIAL_PATH.open("a") as fh:
        for n, row in enumerate(todo, 1):
            sym, day, nxt = row["symbol"], row["date"], row["next_date"]
            sid = f"{sym}_{day}"
            tape = _tape_for(session, tapes, sym, nxt)
            close_res = c1.fetch_window(
                session,
                sym,
                c1.et_to_utc(day, 16, 0, 0),
                c1.et_to_utc(day, 16, 10, 0),
                c1.make_close_stop(tape) if tape else None,
            )
            open_res = c1.fetch_window(
                session,
                sym,
                c1.et_to_utc(nxt, 9, 29, 0),
                c1.et_to_utc(nxt, 9, 45, 0),
                c1.make_open_stop(tape) if tape else None,
            )
            close_row = c1.summarize_official("close", close_res, tape, sym, day, sid)
            open_row = c1.summarize_official("open", open_res, tape, sym, nxt, sid)
            slim = lambda d: {  # noqa: E731
                k: d.get(k)
                for k in (
                    "status",
                    "reason",
                    "source",
                    "price",
                    "exchange",
                    "time",
                    "size",
                    "tape",
                    "n_trades",
                    "pages",
                    "truncated",
                    "primary_price_range_bp",
                )
            }
            fh.write(
                json.dumps(
                    {
                        "symbol": sym,
                        "date": day,
                        "next_date": nxt,
                        "close": slim(close_row),
                        "open": slim(open_row),
                    }
                )
                + "\n"
            )
            fh.flush()
            if tape is None:
                z = close_row.get("tape") or open_row.get("tape")
                if z:
                    tapes[sym] = z
            if n % 100 == 0:
                _log(
                    f"official {n}/{len(todo)}, calls {session.calls}, 429 {session.n429}, {time.time() - t0:.0f}s"
                )
            if budget_s is not None and time.time() - t0 > budget_s:
                _log("time budget reached; stopping (resumable)")
                break
    TAPE_PATH.write_text(json.dumps(tapes))


def analyze_official(picks: pd.DataFrame, calls: int | None = None) -> dict[str, Any]:
    raw = {}
    for r in _load_jsonl(RAWBARS_PATH):
        if "symbol" in r:
            raw[(r["symbol"], r["date"])] = r["c"]
    off = {(r["symbol"], r["date"]): r for r in _load_jsonl(OFFICIAL_PATH)}
    syms = sorted(picks["symbol"].unique())
    dates = sorted(set(picks["date"]) | set(picks["next_date"]))
    wide = t35.load_wide_float32(syms, dates)
    wide.pop("_overlap")
    local = wide["close"]
    local.index = pd.DatetimeIndex(local.index).strftime("%Y-%m-%d")
    recs = []
    for _, p in picks.iterrows():
        key = (p["symbol"], p["date"])
        o = off.get(key)
        c_t = o_n = float("nan")
        if o is not None:
            if (o["close"] or {}).get("status") == "ok":
                c_t = float(o["close"]["price"])
            if (o["open"] or {}).get("status") == "ok":
                o_n = float(o["open"]["price"])
        lc_t = float(local.at[p["date"], p["symbol"]]) if p["date"] in local.index else float("nan")
        lc_n = (
            float(local.at[p["next_date"], p["symbol"]])
            if p["next_date"] in local.index
            else float("nan")
        )
        f_t = adj_factor(lc_t, raw.get((p["symbol"], p["date"]), float("nan")))
        f_n = adj_factor(lc_n, raw.get((p["symbol"], p["next_date"]), float("nan")))
        r_off = official_return(o_n, c_t, f_n, f_t)
        recs.append(
            {
                "symbol": p["symbol"],
                "date": p["date"],
                "leg": p["leg"],
                "lo20": bool(p["lo20"]),
                "r_daily": float(p["r_daily"]),
                "r_official": r_off,
                "delta": float(pair_delta(np.array([r_off]), np.array([p["r_daily"]]))[0]),
                "have_close": np.isfinite(c_t),
                "have_open": np.isfinite(o_n),
                "have_factor": bool(np.isfinite(f_t) and np.isfinite(f_n)),
                "f_ratio": (f_n / f_t)
                if np.isfinite(f_t) and np.isfinite(f_n) and f_t > 0
                else float("nan"),
                "attempted": o is not None,
            }
        )
    fr = pd.DataFrame(recs)
    uniq = fr.drop_duplicates(["symbol", "date"])
    n_rows = len(uniq)
    n_missing = int((~np.isfinite(uniq["delta"])).sum())

    def leg_mask(f: pd.DataFrame, leg: str) -> pd.DataFrame:
        return f[f["lo20"]] if leg == "lo20" else f[f["leg"] == leg]

    days_arr = fr["date"].to_numpy()
    dl, n_ls_days = delta_ls_by_day(fr["delta"].to_numpy(), days_arr, fr["leg"].to_numpy())
    lo = fr[fr["lo20"]]
    dlo, n_lo_days = day_then_day_mean(lo["delta"].to_numpy(), lo["date"].to_numpy())
    dl_long, _ = day_then_day_mean(
        leg_mask(fr, "long")["delta"].to_numpy(), leg_mask(fr, "long")["date"].to_numpy()
    )
    dl_short, _ = day_then_day_mean(
        leg_mask(fr, "short")["delta"].to_numpy(), leg_mask(fr, "short")["date"].to_numpy()
    )
    dd = fr["delta"].to_numpy()
    fin = dd[np.isfinite(dd)]
    fr_ok = fr[np.isfinite(fr["delta"])]

    def q(a: np.ndarray) -> dict[str, float]:
        return (
            {
                k: float(np.quantile(a, v) * 1e4)
                for k, v in (
                    ("p05", 0.05),
                    ("p25", 0.25),
                    ("p50", 0.5),
                    ("p75", 0.75),
                    ("p95", 0.95),
                )
            }
            if len(a)
            else {}
        )

    n_missing_close = int((~uniq["have_close"]).sum())
    n_missing_open = int((~uniq["have_open"]).sum())
    n_missing_factor = int((~uniq["have_factor"]).sum())
    fr_ratio = uniq["f_ratio"].to_numpy()
    fr_ratio = fr_ratio[np.isfinite(fr_ratio)]
    test_b = {
        "sample_days": sorted(picks["date"].unique().tolist()),
        "seed": SEED,
        "n_days": int(picks["date"].nunique()),
        "n_rows": n_rows,
        "n_pairs": int(len(uniq) - n_missing),
        "n_pairs_incl_leg_duplicates": int(len(fr_ok)),
        "n_missing": n_missing,
        "missing_share": float(n_missing / n_rows) if n_rows else float("nan"),
        "missing_close": n_missing_close,
        "missing_open": n_missing_open,
        "missing_factor": n_missing_factor,
        "not_attempted": int((~uniq["attempted"]).sum()),
        "delta_ls_bp": dl * 1e4,
        "delta_ls_days": n_ls_days,
        "delta_long_bp": dl_long * 1e4,
        "delta_short_bp": dl_short * 1e4,
        "delta_lo20_bp": dlo * 1e4,
        "delta_lo20_days": n_lo_days,
        "delta_quantiles_bp_all_rows": q(fin),
        "delta_abs_gt_50bp": int((np.abs(fin) > 0.005).sum()),
        "nights_factor_ratio_ne_1_1e-3": int((np.abs(fr_ratio - 1.0) > 1e-3).sum()),
        "nights_factor_ratio_ne_1_1e-2": int((np.abs(fr_ratio - 1.0) > 1e-2).sum()),
        "nights_with_factor": int(len(fr_ratio)),
        "gate_b": gate_b(
            dl * 1e4, dlo * 1e4, float(n_missing / n_rows) if n_rows else float("nan")
        ),
        "requests": calls,
        "basis": "official (Q/O open, M/6 close, listing exchange) prices multiplied by adjusted-close/raw-close factors of the same sessions; Delta = r_official - r_daily (panel)",
    }
    fr.to_parquet(CACHE_DIR / "official_pairs.parquet", index=False)
    return test_b


def official_stage(budget_s: float | None = None) -> None:
    if not PREBACKTEST_STAMP.exists():
        raise SystemExit("prebacktest-validated-at.txt missing: run the pre-backtest gate first")
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    picks = build_picks()
    _log(
        f"picks: {len(picks)} rows, {picks['date'].nunique()} days, {picks.drop_duplicates(['symbol', 'date']).shape[0]} unique (symbol, day)"
    )
    session = c1.DataSession()
    _fetch_raw_bars(session, picks)
    fetch_official(picks, session, budget_s)
    done = {(r["symbol"], r["date"]) for r in _load_jsonl(OFFICIAL_PATH)}
    todo = [
        1
        for _, r in picks.drop_duplicates(["symbol", "date"]).iterrows()
        if (r["symbol"], r["date"]) not in done
    ]
    if todo:
        _log(f"official fetch incomplete: {len(todo)} rows left; re-run to resume")
        return
    tb = analyze_official(picks, session.calls)
    _write_json(OFFICIAL_RESULTS_PATH, {"test_b": tb})
    _log(
        f"official done: delta_ls {tb['delta_ls_bp']:.2f} bp, delta_lo20 {tb['delta_lo20_bp']:.2f} bp, missing {tb['missing_share']:.3f}, gate_b {tb['gate_b']}"
    )


# ==========================================================================
# stage diag
# ==========================================================================


def build_momentum(panel_keys: pd.DataFrame) -> pd.DataFrame:
    """12-1 momentum close_{t-21} / close_{t-252} - 1 from daily bars (t35 loader and cleaning)."""
    if MOM_PATH.exists():
        return pd.read_parquet(MOM_PATH)
    info = json.loads(T35_CANDS.read_text(encoding="utf-8"))
    dates = info["dates"]
    symbols = sorted(panel_keys["symbol"].astype(str).unique())
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    out_parts = []
    for lo in range(0, len(symbols), CHUNK_SYMBOLS):
        chunk = symbols[lo : lo + CHUNK_SYMBOLS]
        wide = t35.load_wide_float32(chunk, dates)
        wide.pop("_overlap")
        close_w, open_w = wide["close"], wide["open"]
        del wide
        close_s, _o, _rep = ph.sanitize_price_matrices(close_w, open_w)
        del close_w, open_w, _o
        mom = (close_s.shift(21) / close_s.shift(252) - 1.0).astype("float32")
        del close_s
        long = mom.stack(future_stack=True).rename("mom").reset_index()
        long.columns = ["date", "symbol", "mom"]
        long = long[np.isfinite(long["mom"])]
        out_parts.append(long)
        _log(f"momentum chunk {lo}: {len(long):,} finite cells")
        del mom, long
        gc.collect()
    mom_all = pd.concat(out_parts, ignore_index=True)
    mom_all["symbol"] = mom_all["symbol"].astype(str)
    mom_all.to_parquet(MOM_PATH, index=False)
    del idx
    return mom_all


def earnings_night_keys(
    dates_all: pd.DatetimeIndex,
) -> tuple[set[tuple[str, pd.Timestamp]], dict[str, Any]]:
    """(ticker, signal date t) pairs whose 8-K acceptance falls in (t 16:00 ET, t+1 09:30 ET]."""
    parts = []
    for y in (2024, 2025, 2026):
        p = EARNINGS_GLOB / f"{y}.parquet"
        if p.exists():
            parts.append(pd.read_parquet(p, columns=["ticker", "acceptance_utc"]))
    ev = pd.concat(parts, ignore_index=True).dropna()
    ts = pd.to_datetime(ev["acceptance_utc"], utc=True)
    ev["ts_ns"] = ts.astype("int64").to_numpy()
    close_ns = np.asarray(
        [
            pd.Timestamp(d).tz_localize("America/New_York").replace(hour=16).tz_convert("UTC").value
            for d in dates_all
        ]
    )
    open_ns = np.asarray(
        [
            pd.Timestamp(d)
            .tz_localize("America/New_York")
            .replace(hour=9, minute=30)
            .tz_convert("UTC")
            .value
            for d in dates_all
        ]
    )
    keys: set[tuple[str, pd.Timestamp]] = set()
    j = np.searchsorted(close_ns, ev["ts_ns"].to_numpy(), side="right") - 1
    for tk, jj, e in zip(ev["ticker"].to_numpy(), j, ev["ts_ns"].to_numpy(), strict=True):
        if jj < 0 or jj + 1 >= len(dates_all):
            continue
        if e <= open_ns[jj + 1]:
            keys.add((str(tk), pd.Timestamp(dates_all[jj])))
    info = {
        "n_events": int(len(ev)),
        "n_tickers": int(ev["ticker"].nunique()),
        "n_night_keys": len(keys),
    }
    return keys, info


def _ls_from_mask(sig: np.ndarray, ret: np.ndarray, mask: np.ndarray) -> float:
    if mask.sum() < MIN_NIGHT_NAMES:
        return float("nan")
    res = t35.decile_long_short(sig[mask], ret[mask])
    return float("nan") if res is None else float(res["ls"])


def diag_stage() -> None:
    t0 = time.time()
    if not PREBACKTEST_STAMP.exists():
        raise SystemExit("prebacktest-validated-at.txt missing: run the pre-backtest gate first")
    panel = pd.read_parquet(
        T35_PANEL,
        columns=[
            "date",
            "symbol",
            "delisted",
            "p1500",
            "p500",
            "dv21",
            "on252",
            "r",
            "idn",
            "borrow_rate",
            "dtc_cross_sectional_pct",
        ],
    )
    panel["symbol"] = panel["symbol"].astype(str)
    panel = panel.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    dates_all = pd.DatetimeIndex(np.sort(panel["date"].unique()))
    starts = np.asarray(panel["date"].searchsorted(dates_all, side="left"))
    ends = np.append(starts[1:], len(panel))
    days_next = t35.days_to_next_session(dates_all)

    mom_df = build_momentum(panel[["date", "symbol"]])
    mom = (
        panel[["date", "symbol"]]
        .merge(mom_df, on=["date", "symbol"], how="left")["mom"]
        .to_numpy("float64")
    )
    del mom_df
    meta = pd.read_parquet(t35.ASSET_METADATA, columns=["symbol", "name"]).drop_duplicates("symbol")
    adr_syms = set(
        meta.loc[meta["name"].str.contains(ADR_PATTERN, case=False, regex=True, na=False), "symbol"]
    )
    has_meta = set(meta["symbol"])
    sym_arr = panel["symbol"].to_numpy()
    adr_flag = np.asarray([s in adr_syms for s in sym_arr])
    codes, uniq_syms = pd.factorize(panel["symbol"])
    keys, ev_info = earnings_night_keys(dates_all)
    earn_flag = np.zeros(len(panel), dtype=bool)
    if keys:
        kdf = pd.DataFrame(list(keys), columns=["symbol", "date"])
        kdf["hit"] = True
        earn_flag = (
            panel[["date", "symbol"]]
            .merge(kdf, on=["date", "symbol"], how="left")["hit"]
            .fillna(False)
            .to_numpy(dtype=bool)
        )
    sig = panel["on252"].to_numpy("float64")
    ret = panel["r"].to_numpy("float64")
    dtc = panel["dtc_cross_sectional_pct"].to_numpy("float64")
    rate = panel["borrow_rate"].to_numpy("float64")
    spy = pd.read_parquet(T35_SPY)["r"].reindex(dates_all).to_numpy()
    n_dates = len(dates_all)
    mmask = {w: t35.window_mask(dates_all, win) for w, win in WINDOWS.items()}
    fri = np.asarray(dates_all.dayofweek == 4)  # noqa: F841
    keep_cols = (
        "gross",
        "pool_ew",
        "adr_share_long",
        "adr_share_short",
        "adr_share_pool",
        "gross_ex_adr",
        "rank_corr",
        "mom_ls",
        "gross_on_mom_names",
        "dbl_t1",
        "dbl_t2",
        "dbl_t3",
        "gross_ex_earn",
        "earn_share_books",
        "earn_share_pool",
        "gross_same_nights_earn",
        "lo20",
        "lo20_excess",
        "gross_etb",
        "borrow_etb_bp",
        "borrow_bp",
    )
    res: dict[str, Any] = {}
    for pool_name, pool_col in (("P500", "p500"), ("P1500", "p1500")):
        pool = panel[pool_col].to_numpy()
        S = {c: np.full(n_dates, np.nan) for c in keep_cols}
        contrib_main = np.zeros(len(uniq_syms))
        contrib_stress = np.zeros(len(uniq_syms))
        for i in range(n_dates):
            s, e = starts[i], ends[i]
            m = pool[s:e] & np.isfinite(sig[s:e]) & np.isfinite(ret[s:e])
            if m.sum() < MIN_NIGHT_NAMES:
                continue
            idx = np.nonzero(m)[0] + s
            x, rr = sig[idx], ret[idx]
            S["pool_ew"][i] = rr.mean()
            books = t35.decile_long_short(x, rr)
            if books is None:
                continue
            li, si = idx[books["long_idx"]], idx[books["short_idx"]]
            S["gross"][i] = books["ls"]
            k = books["k"]
            if mmask["main"][i]:
                np.add.at(contrib_main, codes[li], ret[li] / k)
                np.add.at(contrib_main, codes[si], -ret[si] / k)
            elif mmask["stress"][i]:
                np.add.at(contrib_stress, codes[li], ret[li] / k)
                np.add.at(contrib_stress, codes[si], -ret[si] / k)
            # 1 ADR
            S["adr_share_long"][i] = adr_flag[li].mean()
            S["adr_share_short"][i] = adr_flag[si].mean()
            S["adr_share_pool"][i] = adr_flag[idx].mean()
            S["gross_ex_adr"][i] = _ls_from_mask(x, rr, ~adr_flag[idx])
            # 2 momentum
            mm = np.isfinite(mom[idx])
            if mm.sum() >= MIN_NIGHT_NAMES:
                xs, ms, rs = x[mm], mom[idx][mm], rr[mm]
                rx = pd.Series(xs).rank().to_numpy()
                rm = pd.Series(ms).rank().to_numpy()
                S["rank_corr"][i] = float(np.corrcoef(rx, rm)[0, 1])
                lm = t35.decile_long_short(ms, rs)
                S["mom_ls"][i] = float("nan") if lm is None else lm["ls"]
                base = t35.decile_long_short(xs, rs)
                S["gross_on_mom_names"][i] = float("nan") if base is None else base["ls"]
                order = np.argsort(ms, kind="stable")
                for ti, part in enumerate(np.array_split(order, 3), start=1):
                    r2 = t35.decile_long_short(xs[part], rs[part])
                    S[f"dbl_t{ti}"][i] = float("nan") if r2 is None else r2["ls"]
            # 3 earnings nights
            ef = earn_flag[idx]
            S["earn_share_pool"][i] = ef.mean()
            S["earn_share_books"][i] = (earn_flag[li].sum() + earn_flag[si].sum()) / (2.0 * k)
            S["gross_ex_earn"][i] = _ls_from_mask(x, rr, ~ef)
            # 5 LO top 20
            if len(x) >= LO_N:
                top = np.argsort(x, kind="stable")[-LO_N:]
                S["lo20"][i] = rr[top].mean()
                S["lo20_excess"][i] = rr[top].mean() - rr.mean()
            # 6 easy-to-borrow proxy on the short leg
            etb = np.isfinite(dtc[idx]) & (dtc[idx] < t35.DTC_ETB_MAX)
            if etb.sum() >= k:
                oe = np.argsort(np.where(etb, x, np.inf), kind="stable")[:k]
                se = idx[oe]
                S["gross_etb"][i] = rr[np.argsort(x, kind="stable")[-k:]].mean() - ret[se].mean()
                S["borrow_etb_bp"][i] = (
                    float(np.nanmean(rate[se])) * days_next[i] / t35.BORROW_DAYCOUNT * 1e4
                )
            S["borrow_bp"][i] = (
                float(np.nanmean(rate[si])) * days_next[i] / t35.BORROW_DAYCOUNT * 1e4
            )
        df = pd.DataFrame(S, index=dates_all)

        def ws(col: str, d: pd.DataFrame = df) -> dict[str, Any]:
            return _window_stats(d[col].to_numpy(), dates_all)

        def wmean(col: str, d: pd.DataFrame = df) -> dict[str, float]:
            return {
                w: float(np.nanmean(d[col].to_numpy()[mmask[w]]))
                if np.isfinite(d[col].to_numpy()[mmask[w]]).any()
                else float("nan")
                for w in WINDOWS
            }

        def top10(contrib: np.ndarray) -> dict[str, Any]:
            tot = float(contrib.sum())
            order = np.argsort(-contrib)[:10]
            top = float(contrib[order].sum())
            return {
                "total_contrib": tot,
                "top10_contrib": top,
                "top10_share_of_total_ls_pnl": top / tot if tot else float("nan"),
                "top10_symbols": [str(uniq_syms[j]) for j in order],
                "top10_share_each": [
                    float(contrib[j] / tot) if tot else float("nan") for j in order
                ],
            }

        pool_syms = set(np.unique(sym_arr[pool]))
        res[pool_name] = {
            "baseline_ls": ws("gross"),
            "d1_adr": {
                "adr_share_long_decile": wmean("adr_share_long"),
                "adr_share_short_decile": wmean("adr_share_short"),
                "adr_share_pool": wmean("adr_share_pool"),
                "ls_ex_adr": ws("gross_ex_adr"),
                "metadata_coverage_of_pool_symbols": float(
                    len(pool_syms & has_meta) / max(1, len(pool_syms))
                ),
            },
            "d2_momentum": {
                "source": "daily-bar close, same loader and price_hygiene defaults as the T-35 panel (not derived from panel returns)",
                "mean_rank_corr_on252_vs_mom_12_1": wmean("rank_corr"),
                "mom_decile_ls_next_night": ws("mom_ls"),
                "on252_ls_same_names_with_mom": ws("gross_on_mom_names"),
                "double_sort_on252_ls_within_mom_tercile_low": ws("dbl_t1"),
                "double_sort_on252_ls_within_mom_tercile_mid": ws("dbl_t2"),
                "double_sort_on252_ls_within_mom_tercile_high": ws("dbl_t3"),
            },
            "d3_earnings": {
                "events": ev_info,
                "share_of_pool_rows_on_earnings_night": wmean("earn_share_pool"),
                "share_of_book_positions_on_earnings_night": wmean("earn_share_books"),
                "ls_ex_earnings_nights": ws("gross_ex_earn"),
                "note": "events only 2024-01..2026-09-17 and only part of the tickers; stress period has none, so its number equals the baseline",
            },
            "d4_concentration": {
                "main": top10(contrib_main),
                "stress": top10(contrib_stress),
                "by_year": t35.by_year_table(df),
            },
            "d5_lo20": {
                "lo20_gross": ws("lo20"),
                "lo20_excess_over_pool_ew": ws("lo20_excess"),
                "pool_ew_mean_bp": {
                    w: float(np.nanmean(df["pool_ew"].to_numpy()[mmask[w]]) * 1e4) for w in WINDOWS
                },
                "spy_close_to_open": _window_stats(spy, dates_all),
            },
            "d6_easy_to_borrow": {
                "ls_etb_short_leg_gross": ws("gross_etb"),
                "borrow_etb_mean_bp": wmean("borrow_etb_bp"),
                "borrow_tier_mean_bp_of_baseline_short_leg": wmean("borrow_bp"),
            },
        }
        _log(f"diag {pool_name} done")
        del df, S
        gc.collect()
    parity = {}
    if T35_RESULTS.exists():
        t35r = json.loads(T35_RESULTS.read_text(encoding="utf-8"))
        for pool_name in ("P500", "P1500"):
            ref = t35r["cells"][f"ON252_{pool_name}_LS"]["main"]["gross"]["mean_bp"]
            parity[pool_name] = {
                "mine_main_mean_bp": res[pool_name]["baseline_ls"]["main"]["mean_bp"],
                "t35_results_main_mean_bp": ref,
                "abs_diff_bp": abs(res[pool_name]["baseline_ls"]["main"]["mean_bp"] - ref),
            }
    _write_json(
        DIAG_RESULTS_PATH,
        {"diagnostics": res, "t35_parity": parity, "diag_seconds": round(time.time() - t0, 1)},
    )
    _log("diag done; merging")
    merge_and_report()


# ==========================================================================
# merge + report
# ==========================================================================


def merge_and_report() -> None:
    band = (
        json.loads(BAND_RESULTS_PATH.read_text(encoding="utf-8"))
        if BAND_RESULTS_PATH.exists()
        else {}
    )
    off = (
        json.loads(OFFICIAL_RESULTS_PATH.read_text(encoding="utf-8"))
        if OFFICIAL_RESULTS_PATH.exists()
        else {}
    )
    dg = (
        json.loads(DIAG_RESULTS_PATH.read_text(encoding="utf-8"))
        if DIAG_RESULTS_PATH.exists()
        else {}
    )
    test_a = band.get("test_a", {})
    test_b = off.get("test_b", {})
    res = {
        "iteration_id": ITERATION_ID,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prebacktest_validated_at": PREBACKTEST_STAMP.read_text(encoding="utf-8").strip(),
        "design": f"reports/research/iterations/{ITERATION_ID}/hypotheses.md",
        "windows": WINDOWS,
        "gate_a": test_a.get("gate_a"),
        "gate_b": test_b.get("gate_b"),
        "test_a": test_a,
        "test_b": test_b,
        "diagnostics": dg.get("diagnostics", {}),
        "t35_parity": dg.get("t35_parity", {}),
        "data": band.get("data", {}),
        "stage_seconds": {"band": band.get("band_seconds"), "diag": dg.get("diag_seconds")},
    }
    _write_json(RESULTS_PATH, res)
    write_report(res)
    _log(f"results.json and report.md written; gate_a {res['gate_a']} gate_b {res['gate_b']}")


def _f(x: Any, nd: int = 2) -> str:
    if x is None or (isinstance(x, float) and not math.isfinite(x)):
        return "n/a"
    if isinstance(x, bool):
        return str(x).lower()
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return f"{float(x):,.{nd}f}"


def write_report(res: dict[str, Any]) -> None:
    a, b, dg = res["test_a"], res["test_b"], res["diagnostics"]
    L: list[str] = [f"# {ITERATION_ID}: ON252 out-of-sample band and official-price check", ""]
    L += [
        f"Generated {res['generated_at']} (pre-backtest gate stamp {res['prebacktest_validated_at']}). Every number below is read from `results.json`. Design: `hypotheses.md` (frozen before any pool B or official-price number).",
        "",
        f"**gate_a = {_f(res['gate_a'])}, gate_b = {_f(res['gate_b'])}** (computed mechanically by the script).",
        "",
        "## Test A: pool B (dv21 rank 1501-3000), ON252 decile long/short, close to next open (gross)",
        "",
        "| window | mean bp/night | NW t (5) | plain t | n nights | placebo beat | placebo mean bp | long bp | short bp | pool EW bp | mean names | k |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for w in ("main", "stress"):
        x = a.get(w, {})
        L.append(
            f"| {w} {res['windows'][w][0]}..{res['windows'][w][1]} | {_f(x.get('mean_bp'))} | {_f(x.get('t_nw5'))} | {_f(x.get('t'))} | {_f(x.get('n'))} | {_f(x.get('placebo_beat'), 2)} | {_f(x.get('placebo_mean_bp'))} | {_f(x.get('long_mean_bp'))} | {_f(x.get('short_mean_bp'))} | {_f(x.get('pool_ew_mean_bp'))} | {_f(x.get('mean_n_valid'), 0)} | {_f(x.get('mean_k'), 1)} |"
        )
    ni = a.get("next_intraday", {})
    L += [
        "",
        f"Next-day intraday leg of the same book: main {_f(ni.get('main', {}).get('mean_bp'))} bp (t {_f(ni.get('main', {}).get('t_nw5'))}), stress {_f(ni.get('stress', {}).get('mean_bp'))} bp (t {_f(ni.get('stress', {}).get('t_nw5'))}).",
        "",
        "By year (mean bp, NW t, n):",
        "",
        "| year | mean bp | NW t | n |",
        "|---|---|---|---|",
    ]
    for y, v in (a.get("by_year") or {}).items():
        L.append(f"| {y} | {_f(v['mean_bp'])} | {_f(v['t_nw5'])} | {_f(v['n'])} |")
    d = res["data"]
    L += [
        "",
        f"Data: mean {_f(d.get('mean_daily_pool_size_b'), 0)} names per night in pool B, {_f(d.get('symbols_in_pool_b'))} symbols in total, delisted share {_f(d.get('delisted_share_of_pool_rows'), 3)} of pool rows and {_f(d.get('delisted_share_of_pool_symbols'), 3)} of pool symbols; candidates ever in dv21 top {_f(d.get('candidate_top_n'))}: {_f(d.get('candidate_symbols_ever_top_n'))}; split-like rows filtered {_f(d.get('split_filtered_rows'))}.",
        "",
        "## Test B: official auction prices on 20 seeded days (ON252_P500)",
        "",
        f"Sampled days ({_f(b.get('n_days'))}, default_rng({b.get('seed')}) over main-window dates with a valid ON252_P500 night): {', '.join(b.get('sample_days', []))}.",
        "",
        f"- rows (symbol, day): {_f(b.get('n_rows'))}; valid pairs {_f(b.get('n_pairs'))}; missing {_f(b.get('n_missing'))} = **{_f(b.get('missing_share'), 4)}** (missing official close {_f(b.get('missing_close'))}, missing official open {_f(b.get('missing_open'))}, missing adjustment factor {_f(b.get('missing_factor'))}).",
        f"- delta LS = mean(delta long decile) - mean(delta short decile): **{_f(b.get('delta_ls_bp'))} bp/night** over {_f(b.get('delta_ls_days'))} days (long {_f(b.get('delta_long_bp'))} bp, short {_f(b.get('delta_short_bp'))} bp).",
        f"- delta LO top 20: **{_f(b.get('delta_lo20_bp'))} bp/night** over {_f(b.get('delta_lo20_days'))} days.",
        f"- delta quantiles over all valid rows (bp): {json.dumps(b.get('delta_quantiles_bp_all_rows'))}; rows with |delta| > 50 bp: {_f(b.get('delta_abs_gt_50bp'))}.",
        f"- adjustment: nights with f_(t+1)/f_t differing from 1 by > 1e-3: {_f(b.get('nights_factor_ratio_ne_1_1e-3'))} of {_f(b.get('nights_with_factor'))} (by > 1e-2: {_f(b.get('nights_factor_ratio_ne_1_1e-2'))}). Basis: {b.get('basis')}.",
        f"- API requests in the final invocation: {_f(b.get('requests'))}.",
        "",
        "## Diagnostics (contaminated P500/P1500 panel, report only)",
        "",
    ]
    for pool in ("P500", "P1500"):
        g = dg.get(pool, {})
        if not g:
            continue
        bl = g["baseline_ls"]
        L += [
            f"### {pool}",
            "",
            f"Baseline ON252 LS: main {_f(bl['main']['mean_bp'])} bp (t {_f(bl['main']['t_nw5'])}), stress {_f(bl['stress']['mean_bp'])} bp (t {_f(bl['stress']['t_nw5'])}).",
            "",
        ]
        d1 = g["d1_adr"]
        L += [
            f"1. ADR: share in long decile {_f(d1['adr_share_long_decile']['main'], 4)}, short decile {_f(d1['adr_share_short_decile']['main'], 4)}, pool {_f(d1['adr_share_pool']['main'], 4)} (main window); LS ex-ADR main {_f(d1['ls_ex_adr']['main']['mean_bp'])} bp (t {_f(d1['ls_ex_adr']['main']['t_nw5'])}), stress {_f(d1['ls_ex_adr']['stress']['mean_bp'])} bp (t {_f(d1['ls_ex_adr']['stress']['t_nw5'])}). Metadata covers {_f(d1['metadata_coverage_of_pool_symbols'], 3)} of pool symbols.",
        ]
        d2 = g["d2_momentum"]
        L += [
            f"2. Momentum ({d2['source']}): mean rank corr ON252 vs 12-1 main {_f(d2['mean_rank_corr_on252_vs_mom_12_1']['main'], 3)}, stress {_f(d2['mean_rank_corr_on252_vs_mom_12_1']['stress'], 3)}; 12-1 decile LS next night main {_f(d2['mom_decile_ls_next_night']['main']['mean_bp'])} bp (t {_f(d2['mom_decile_ls_next_night']['main']['t_nw5'])}), stress {_f(d2['mom_decile_ls_next_night']['stress']['mean_bp'])} bp; double sort ON252 LS within momentum terciles (main): low {_f(d2['double_sort_on252_ls_within_mom_tercile_low']['main']['mean_bp'])}, mid {_f(d2['double_sort_on252_ls_within_mom_tercile_mid']['main']['mean_bp'])}, high {_f(d2['double_sort_on252_ls_within_mom_tercile_high']['main']['mean_bp'])} bp (stress: {_f(d2['double_sort_on252_ls_within_mom_tercile_low']['stress']['mean_bp'])} / {_f(d2['double_sort_on252_ls_within_mom_tercile_mid']['stress']['mean_bp'])} / {_f(d2['double_sort_on252_ls_within_mom_tercile_high']['stress']['mean_bp'])}).",
        ]
        d3 = g["d3_earnings"]
        L += [
            f"3. Earnings nights ({d3['events']['n_events']} events, {d3['events']['n_tickers']} tickers): flagged share of book positions main {_f(d3['share_of_book_positions_on_earnings_night']['main'], 4)} (pool rows {_f(d3['share_of_pool_rows_on_earnings_night']['main'], 4)}); LS ex-earnings main {_f(d3['ls_ex_earnings_nights']['main']['mean_bp'])} bp (t {_f(d3['ls_ex_earnings_nights']['main']['t_nw5'])}) versus baseline {_f(bl['main']['mean_bp'])} bp.",
        ]
        d4 = g["d4_concentration"]
        L += [
            f"4. Concentration: top-10 symbols carry {_f(d4['main']['top10_share_of_total_ls_pnl'], 3)} of LS PnL in the main window ({', '.join(d4['main']['top10_symbols'])}) and {_f(d4['stress']['top10_share_of_total_ls_pnl'], 3)} in the stress period.",
        ]
        d5 = g["d5_lo20"]
        L += [
            f"5. LO top 20: gross main {_f(d5['lo20_gross']['main']['mean_bp'])} bp (t {_f(d5['lo20_gross']['main']['t_nw5'])}), excess over pool EW {_f(d5['lo20_excess_over_pool_ew']['main']['mean_bp'])} bp (t {_f(d5['lo20_excess_over_pool_ew']['main']['t_nw5'])}); pool EW {_f(d5['pool_ew_mean_bp']['main'])} bp; SPY close-to-open {_f(d5['spy_close_to_open']['main']['mean_bp'])} bp (stress: LO {_f(d5['lo20_gross']['stress']['mean_bp'])}, SPY {_f(d5['spy_close_to_open']['stress']['mean_bp'])}).",
        ]
        d6 = g["d6_easy_to_borrow"]
        L += [
            f"6. Easy-to-borrow proxy on the short leg: LS main {_f(d6['ls_etb_short_leg_gross']['main']['mean_bp'])} bp (t {_f(d6['ls_etb_short_leg_gross']['main']['t_nw5'])}), stress {_f(d6['ls_etb_short_leg_gross']['stress']['mean_bp'])} bp (t {_f(d6['ls_etb_short_leg_gross']['stress']['t_nw5'])}); borrow tier cost of the baseline short leg main {_f(d6['borrow_tier_mean_bp_of_baseline_short_leg']['main'])} bp/night.",
            "",
        ]
    if res.get("t35_parity"):
        L += [
            "T-35 parity (same ON252 LS, main window): "
            + "; ".join(
                f"{k}: mine {_f(v['mine_main_mean_bp'])} bp vs T-35 results.json {_f(v['t35_results_main_mean_bp'])} bp (abs diff {_f(v['abs_diff_bp'], 3)})"
                for k, v in res["t35_parity"].items()
            )
            + ".",
            "",
        ]
    L += [
        "## Conventions and limits",
        "",
        "- Costs do not enter the gates (gross measurement); the 2 bp/side auction contract of the design applies later.",
        "- Sample days: main-window dates on which the ON252_P500 book has a valid night (the last panel date has no next open).",
        "- Official price adjustment: r_official = official open_(t+1) x f_(t+1) / (official close_t x f_t) - 1 with f_d = local daily close / raw SIP daily close.",
        "- Momentum, ADR, earnings and concentration diagnostics use the contaminated P500/P1500 panel and do not enter the gates.",
    ]
    REPORT_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("candidates", help=argparse.SUPPRESS)
    sub.add_parser("band", help="test A")
    off = sub.add_parser("official", help="test B")
    off.add_argument("--budget-seconds", type=float, default=None)
    sub.add_parser("diag", help="diagnostics, merge, report")
    sub.add_parser("report", help="merge stage results and rewrite results.json / report.md")
    args = parser.parse_args(argv)
    if args.stage == "candidates":
        find_candidates()
    elif args.stage == "band":
        band_stage()
    elif args.stage == "official":
        official_stage(args.budget_seconds)
    elif args.stage == "diag":
        diag_stage()
    else:
        merge_and_report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
