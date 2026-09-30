# ruff: noqa: E501
"""T-20260930-12 (corridor C1b): small-cap ($5-20M) gap-down long selected only with
information available before the 09:27 ET opening-auction deadline.

Design is frozen in ``reports/research/iterations/t20260930_12_smallcap_gap_auction/
hypotheses.md``; this script only executes it.

Stages:

* ``premarket``  scan the minute archive month by month (shard by shard, 4 threads) and
  write ``cache/premarket/<YYYY-MM>.parquet`` with, per (symbol, ET date): the last bar
  close/time starting in [04:00, 09:11] ET (X15), in [04:00, 09:26] ET (X0), the
  04:00-09:11 pre-market dollar volume, and the last regular-session bar close (start in
  [09:30, 15:59] ET).  Existing months are skipped (checkpoint).
* ``screen``     three calibers (X15, X0, LA) x 4 cells (K in {10, 5} x EW / 1/sigma21):
  daily basket gross returns, windows, t / Newey-West t, 100-seed same-pool random
  placebo, same-pool baseline, decision cells and verdict -> ``results.json``.
* ``book``       only when the X15_K10_EW decision cell passes all three conditions.

Time-zone rule: bar-start timestamps are UTC; converted to America/New_York exactly
(daylight saving), then minute-of-day compared: X15 last start 09:11 (inclusive),
X0 last start 09:26 (inclusive), regular bars start in [09:30, 15:59].
"""

from __future__ import annotations

import argparse
import gc
import glob
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

ITERATION_ID = "t20260930_12_smallcap_gap_auction"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
PM_DIR = CACHE_DIR / "premarket"
RESULTS_PATH = OUT_DIR / "results.json"
MINUTE_GLOB = str(ROOT / "data" / "sip" / "minute" / "*" / "*")
WIDE_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "t20260929_32_gap_fade_ls"
    / "cache"
    / "wide_matrices.parquet"
)

# ---- frozen constants (hypotheses.md) --------------------------------------
PM_FIRST_MIN = 4 * 60  # 04:00 ET
X15_LAST_MIN = (
    9 * 60 + 11
)  # bar starting 09:11 ET is the last visible at 09:12 (free plan, 15-min-delayed SIP)
X0_LAST_MIN = 9 * 60 + 26  # bar starting 09:26 ET (real-time SIP)
REG_FIRST_MIN = 9 * 60 + 30
REG_LAST_MIN = 15 * 60 + 59

POOL_LOW, POOL_HIGH = 5e6, 20e6
MIN_PREV_CLOSE = 5.0
KS = (10, 5)
WEIGHTS = ("EW", "IV")
CALIBERS = ("X15", "X0", "LA")
CONSISTENCY_LOG_TOL = 0.10
N_SEEDS = 100
PLACEBO_SEED_BASE = 20260930
CHUNK_SYMBOLS = 700

WINDOWS: dict[str, tuple[str, str]] = {
    "main": ("2024-01-08", "2026-09-29"),
    "short": ("2023-02-01", "2024-01-05"),
    "select": ("2023-09-18", "2025-12-31"),
    "y2026": ("2026-01-01", "2026-09-17"),
    "holdout": ("2026-09-18", "2026-09-29"),
}
LA_ONLY_WINDOWS = {"stress_daily_only": ("2016-05-02", "2023-08-31")}

GATE_MAIN_MEAN_BP = 20.0
GATE_MAIN_T = 2.0
GATE_PLACEBO_BEAT = 0.90
GATE_SHORT_MEAN_BP = 10.0
NW_LAGS = 5


def _log(msg: str) -> None:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"[{time.strftime('%H:%M:%S')}] (maxrss {rss:.0f} MB) {msg}", flush=True)


def _json_default(o: Any) -> Any:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.date().isoformat()
    raise TypeError(type(o))


# ==========================================================================
# stage premarket
# ==========================================================================


def premarket_aggregate(df: pl.DataFrame) -> pl.DataFrame:
    """Per (symbol, ET date) pre-market summary from minute bars.

    ``df`` needs columns symbol, timestamp (UTC, bar start), close, volume.
    """
    if df.is_empty():
        return df.clear()
    et = pl.col("timestamp").dt.convert_time_zone("America/New_York")
    df = (
        df.with_columns(et=et)
        .with_columns(
            date=pl.col("et").dt.date(),
            mod=pl.col("et").dt.hour().cast(pl.Int32) * 60
            + pl.col("et").dt.minute().cast(pl.Int32),
        )
        .filter((pl.col("mod") >= PM_FIRST_MIN) & (pl.col("mod") <= REG_LAST_MIN))
        .sort("symbol", "timestamp")
    )
    c15 = (pl.col("mod") >= PM_FIRST_MIN) & (pl.col("mod") <= X15_LAST_MIN)
    c0 = (pl.col("mod") >= PM_FIRST_MIN) & (pl.col("mod") <= X0_LAST_MIN)
    creg = (pl.col("mod") >= REG_FIRST_MIN) & (pl.col("mod") <= REG_LAST_MIN)
    return df.group_by("symbol", "date").agg(
        x15=pl.col("close").filter(c15).last(),
        x15_ts=pl.col("timestamp").filter(c15).last(),
        x0=pl.col("close").filter(c0).last(),
        x0_ts=pl.col("timestamp").filter(c0).last(),
        pm_dv=(pl.col("close") * pl.col("volume")).filter(c15).sum(),
        pm_n=c15.sum(),
        last_reg_close=pl.col("close").filter(creg).last(),
    )


def _shard(path: str, symbols: list[str]) -> pl.DataFrame | None:
    if pl.read_parquet_schema(path).get("close") is None:  # empty shards carry a null schema
        return None
    df = pl.read_parquet(path, columns=["symbol", "timestamp", "close", "volume"]).filter(
        pl.col("symbol").is_in(symbols)
    )
    if df.is_empty():
        return None
    return premarket_aggregate(df)


def daily_symbols() -> list[str]:
    return (
        pl.scan_parquet(WIDE_PATH)
        .select("symbol")
        .unique()
        .collect(engine="streaming")["symbol"]
        .to_list()
    )


def cmd_premarket(_args: argparse.Namespace) -> int:
    PM_DIR.mkdir(parents=True, exist_ok=True)
    symbols = daily_symbols()
    _log(f"{len(symbols):,} daily-panel symbols")
    months = sorted(glob.glob(str(ROOT / "data" / "sip" / "minute" / "*" / "*")))
    for mdir in months:
        p = Path(mdir)
        if not p.is_dir():
            continue
        tag = f"{p.parent.name}-{p.name}"
        out = PM_DIR / f"{tag}.parquet"
        if out.exists():
            _log(f"{tag}: exists, skip")
            continue
        t0 = time.time()
        files = sorted(glob.glob(str(p / "*.parquet")))
        with ThreadPoolExecutor(4) as ex:
            parts = [x for x in ex.map(lambda f: _shard(f, symbols), files) if x is not None]
        if not parts:
            _log(f"{tag}: no rows")
            continue
        month = pl.concat(parts)
        n_unique = month.select(pl.struct("symbol", "date").n_unique()).item()
        if n_unique != month.height:
            raise RuntimeError(f"{tag}: duplicate (symbol, date) rows across shards")
        tmp = out.with_suffix(".tmp")
        month.write_parquet(tmp)
        tmp.rename(out)
        _log(f"{tag}: {len(files)} shards -> {month.height:,} rows in {time.time() - t0:.0f}s")
    return 0


# ==========================================================================
# statistics helpers
# ==========================================================================


def newey_west_t(x: np.ndarray, lags: int = NW_LAGS) -> float:
    x = np.asarray(x, dtype="float64")
    n = len(x)
    if n < lags + 2:
        return float("nan")
    m = x.mean()
    e = x - m
    gamma0 = float(e @ e) / n
    var = gamma0
    for lag in range(1, lags + 1):
        g = float(e[lag:] @ e[:-lag]) / n
        var += 2.0 * (1.0 - lag / (lags + 1.0)) * g
    if var <= 0:
        return float("nan")
    return float(m / np.sqrt(var / n))


def plain_t(x: np.ndarray) -> float:
    x = np.asarray(x, dtype="float64")
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else 0.0
    return float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else float("nan")


def consistency_excluded(prev_close: np.ndarray, prev_minute_close: np.ndarray) -> np.ndarray:
    """True where the minute archive's last regular bar of the previous session and the
    daily prev_close disagree by more than 10% in log terms (adjustment mismatch).
    Unknown (NaN minute close) is *not* excluded."""
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.abs(np.log(prev_minute_close / prev_close))
    return np.isfinite(d) & (d > CONSISTENCY_LOG_TOL)


def sample_placebo_ranks(date_idx: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    """Random 1-based rank within each date group (rows are the qualified pool only)."""
    key = rng.random(len(date_idx))
    order = np.lexsort((key, date_idx))
    sorted_dates = date_idx[order]
    starts = np.r_[0, np.flatnonzero(np.diff(sorted_dates)) + 1]
    counts = np.diff(np.r_[starts, len(sorted_dates)])
    pos = np.arange(len(sorted_dates)) - np.repeat(starts, counts)
    rank = np.empty(len(date_idx), dtype=np.int64)
    rank[order] = pos + 1
    return rank


def basket_series(
    date_idx: np.ndarray,
    n_dates: int,
    r: np.ndarray,
    w: np.ndarray,
    mask: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Per-date weighted mean of r over ``mask`` rows; 0 and count 0 for empty dates."""
    num = np.bincount(date_idx[mask], weights=(w * r)[mask], minlength=n_dates)
    den = np.bincount(date_idx[mask], weights=w[mask], minlength=n_dates)
    cnt = np.bincount(date_idx[mask], minlength=n_dates)
    out = np.zeros(n_dates)
    nz = den > 0
    out[nz] = num[nz] / den[nz]
    return out, cnt


# ==========================================================================
# stage screen
# ==========================================================================


def sigma21_wide(close_m: pd.DataFrame, ph: Any) -> pd.DataFrame:
    """Same formula as ``build_signal_panel``: 21-session std of no-pad daily returns,
    shifted one session so the current day is excluded."""
    daily_ret = ph.daily_returns_no_pad(close_m)
    return daily_ret.rolling(21, min_periods=21).std(ddof=1).shift(1)


def _chunk_pool(
    chunk: list[str], dates_index: pd.DatetimeIndex, parent: Any, ph: Any
) -> pd.DataFrame:
    import pyarrow.parquet as pq

    tbl = pq.read_table(
        WIDE_PATH,
        columns=["symbol", "date", "open", "close", "volume"],
        filters=[("symbol", "in", chunk)],
    )
    df = tbl.to_pandas()
    df["date"] = pd.to_datetime(df["date"])
    wides = {
        c: df.pivot(index="date", columns="symbol", values=c).reindex(dates_index)
        for c in ("open", "close", "volume")
    }
    del df, tbl
    (close_m, open_m), _rep = ph.mask_regime_breaks(wides["close"], wides["open"])
    # eligibility (history >= 60, sigma21 > 0, prev_close >= $5, dv21 >= $1M, valid open/close)
    # exactly as T-32; the split-like filter is applied per caliber below on P / prev_close
    panel = parent.build_signal_panel(close_m, open_m, wides["volume"], filter_split_like=False)
    if panel.empty:
        return panel
    panel = panel[(panel["dv21"] >= POOL_LOW) & (panel["dv21"] < POOL_HIGH)].copy()
    if panel.empty:
        return panel
    panel["prev_close"] = parent.lookup_from_wide(close_m.shift(1), panel["date"], panel["symbol"])
    panel["sigma21"] = parent.lookup_from_wide(
        sigma21_wide(close_m, ph), panel["date"], panel["symbol"]
    )
    # previous session in the daily index (same convention as close.shift(1))
    prev_dates = pd.Series(dates_index[:-1], index=dates_index[1:])
    panel["prev_date"] = panel["date"].map(prev_dates)
    panel["date"] = panel["date"].astype("datetime64[ns]")
    panel["prev_date"] = panel["prev_date"].astype("datetime64[ns]")
    return panel[
        ["date", "prev_date", "symbol", "open", "close", "dv21", "prev_close", "sigma21"]
    ].reset_index(drop=True)


def load_pool() -> pd.DataFrame:
    import pyarrow.parquet as pq

    from open_composer.research.features import price_hygiene as ph
    from scripts import run_t20260929_32_gap_fade_ls as parent

    tbl = pq.read_table(WIDE_PATH, columns=["symbol", "date"])
    dates_index = pd.DatetimeIndex(sorted(pd.to_datetime(tbl.column("date").unique().to_pylist())))
    symbols = sorted(tbl.column("symbol").unique().to_pylist())
    del tbl
    parts = []
    for i in range(0, len(symbols), CHUNK_SYMBOLS):
        chunk = symbols[i : i + CHUNK_SYMBOLS]
        p = _chunk_pool(chunk, dates_index, parent, ph)
        _log(f"  chunk {i // CHUNK_SYMBOLS + 1}: {len(p):,} pool rows")
        parts.append(p)
    pool = pd.concat(parts, ignore_index=True)
    del parts
    assert not pool.duplicated(["date", "symbol"]).any(), "duplicate (date, symbol) pool rows"
    pool["symbol"] = pool["symbol"].astype("category")
    pool.attrs["dates_index"] = dates_index
    return pool


def attach_premarket(pool: pd.DataFrame) -> pd.DataFrame:
    """Left-join the per-month pre-market summaries onto the pool (minute-era rows only),
    plus the previous session's last regular minute-bar close for the adjustment check."""
    files = sorted(PM_DIR.glob("*.parquet"))
    if not files:
        raise SystemExit("run the premarket stage first")
    era_mask = (pool["date"] >= pd.Timestamp("2023-01-01")).to_numpy()
    pool_old = pool[~era_mask]
    pool_era = pool[era_mask].reset_index(drop=True)
    pool_era = pool_era.assign(symbol=pool_era["symbol"].astype(str))
    keys = pl.from_pandas(pool_era[["symbol", "date", "prev_date"]]).with_columns(
        pl.col("date").cast(pl.Datetime("ns")), pl.col("prev_date").cast(pl.Datetime("ns"))
    )
    cur_keys = keys.select("symbol", "date")
    prev_keys = keys.select("symbol", pl.col("prev_date").alias("date")).drop_nulls().unique()
    cur_parts, prev_parts = [], []
    for f in files:
        m = pl.read_parquet(f).with_columns(pl.col("date").cast(pl.Datetime("ns")))
        cur_parts.append(
            m.join(cur_keys, on=["symbol", "date"], how="semi").select(
                "symbol", "date", "x15", "x15_ts", "x0", "x0_ts", "pm_dv", "pm_n"
            )
        )
        prev_parts.append(
            m.join(prev_keys, on=["symbol", "date"], how="semi").select(
                "symbol",
                pl.col("date").alias("prev_date"),
                pl.col("last_reg_close").alias("prev_min_close"),
            )
        )
        del m
    # month files written before the aggregate was restricted to 04:00-15:59 ET contain
    # ghost groups (after-hours bars that fall on the next UTC day, i.e. the next month
    # file) with every field null; they would duplicate the pool row at month ends
    cur = pl.concat(cur_parts).filter(
        pl.col("x15").is_not_null() | pl.col("x0").is_not_null() | (pl.col("pm_n") > 0)
    )
    prev = pl.concat(prev_parts).filter(pl.col("prev_min_close").is_not_null())
    cur, prev = cur.to_pandas(), prev.to_pandas()
    assert not cur.duplicated(["symbol", "date"]).any()
    assert not prev.duplicated(["symbol", "prev_date"]).any()
    for frame in (cur, prev):
        for c in ("date", "prev_date"):
            if c in frame:
                frame[c] = frame[c].astype("datetime64[ns]")
    out = pool_era.merge(cur, on=["symbol", "date"], how="left").merge(
        prev, on=["symbol", "prev_date"], how="left"
    )
    out = pd.concat(
        [pool_old.assign(symbol=pool_old["symbol"].astype(str)), out], ignore_index=True
    )
    assert len(out) == len(pool), "pre-market join changed the number of pool rows"
    out["symbol"] = out["symbol"].astype("category")
    return out


def build_caliber_rows(
    pool: pd.DataFrame, caliber: str, parent: Any
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Qualified rows for one caliber with z, plus sequential exclusion counts."""
    df = pool
    # counts cover the minute-archive era only (main + short windows, 2023-02-01 on)
    era = (df["date"] >= pd.Timestamp(WINDOWS["short"][0])).to_numpy()
    counts: dict[str, int] = {"pool_rows_since_2023_02_01": int(era.sum())}
    if caliber == "LA":
        price = df["open"].to_numpy()
    else:
        col = "x15" if caliber == "X15" else "x0"
        price = df[col].to_numpy()
    has_p = np.isfinite(price) & (price > 0)
    counts["no_price_in_window"] = int((~has_p & era).sum())
    keep = has_p.copy()
    if caliber != "LA":
        excl = consistency_excluded(df["prev_close"].to_numpy(), df["prev_min_close"].to_numpy())
        counts["adjustment_inconsistent_excluded"] = int((excl & keep & era).sum())
        counts["consistency_check_unavailable_kept"] = int(
            (df["prev_min_close"].isna().to_numpy() & keep & era).sum()
        )
        keep &= ~excl
    ratio = price / df["prev_close"].to_numpy()
    split_like = parent.is_split_like_ratio(ratio)
    counts["split_like_trigger_excluded"] = int((split_like & keep & era).sum())
    keep &= ~split_like
    ts_col = {"X15": "x15_ts", "X0": "x0_ts"}.get(caliber)
    cols = ["date", "symbol", "sigma21", "prev_close", "open", "close"]
    if ts_col:
        cols += [ts_col, "pm_dv", "pm_n"]
    out = df.loc[keep, cols].copy()
    out["P"] = price[keep]
    out["z"] = (out["P"] / out["prev_close"] - 1.0) / out["sigma21"]
    out["oc"] = out["close"] / out["open"] - 1.0
    out = out.drop(columns=["prev_close", "open", "close"])
    out = out[np.isfinite(out["z"]) & np.isfinite(out["oc"])].reset_index(drop=True)
    counts["qualified_rows_since_2023_02_01"] = int(
        (out["date"] >= pd.Timestamp(WINDOWS["short"][0])).sum()
    )
    counts["qualified_rows_all_dates"] = int(len(out))
    return out, counts


def select_rows(rows: pd.DataFrame, k: int, parent: Any) -> pd.DataFrame:
    sel = parent.select_side(rows, pd.Series(True, index=rows.index), k, most_negative=True)
    return sel


def window_mask(dates: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    return np.asarray((dates >= pd.Timestamp(window[0])) & (dates <= pd.Timestamp(window[1])))


def series_stats(x: np.ndarray, cnt: np.ndarray) -> dict[str, Any]:
    return {
        "mean_bp": float(x.mean() * 1e4) if len(x) else float("nan"),
        "t": plain_t(x),
        "nw_t": newey_west_t(x),
        "n_days": int(len(x)),
        "n_empty_days": int((cnt == 0).sum()),
    }


def cmd_screen(_args: argparse.Namespace) -> int:
    from scripts import run_t20260929_32_gap_fade_ls as parent

    t0 = time.time()
    _log("building $5-20M pool (chunked, price hygiene defaults)")
    pool = load_pool()
    dates_index: pd.DatetimeIndex = pool.attrs["dates_index"]
    _log(f"pool rows {len(pool):,} in {time.time() - t0:.0f}s")
    pool = attach_premarket(pool)
    _log("premarket attached")

    windows_all = dict(WINDOWS)
    results: dict[str, Any] = {
        "iteration_id": ITERATION_ID,
        "generated_at": pd.Timestamp.now("UTC").isoformat(),
        "windows": {**WINDOWS, **LA_ONLY_WINDOWS},
        "n_seeds": N_SEEDS,
        "pool": {
            "dv21_low": POOL_LOW,
            "dv21_high": POOL_HIGH,
            "note": "dv21 is build_signal_panel's 21-session rolling MEDIAN of close*volume (shifted one session), imported unchanged from T-32",
        },
        "screen": {},
        "exclusions": {},
        "selected_row_premarket": {},
        "overlap_x15_la": {},
    }
    date_axis = dates_index[dates_index >= pd.Timestamp("2016-01-01")]
    date_pos = pd.Series(np.arange(len(date_axis)), index=date_axis)

    sel_store: dict[tuple[str, int], pd.DataFrame] = {}
    cal_rows: dict[str, pd.DataFrame] = {}
    for cal in CALIBERS:
        rows, counts = build_caliber_rows(pool, cal, parent)
        rows = rows[rows["date"].isin(date_pos.index)].reset_index(drop=True)
        cal_rows[cal] = rows
        # exclusion counts restricted to the minute-archive era for X calibers are reported in total
        results["exclusions"][cal] = counts
        _log(f"{cal}: {counts}")
    del pool
    gc.collect()

    for cal in CALIBERS:
        rows = cal_rows[cal]
        didx = date_pos.reindex(rows["date"]).to_numpy().astype("int64")
        n_dates = len(date_axis)
        r = rows["oc"].to_numpy()
        inv = 1.0 / rows["sigma21"].to_numpy()
        ones = np.ones(len(rows))
        # real selections
        real: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        for k in KS:
            sel = select_rows(rows, k, parent)
            sel_store[(cal, k)] = sel.merge(rows, on=["date", "symbol"], how="left")
            selmask = rows.set_index(["date", "symbol"]).index.isin(
                sel.set_index(["date", "symbol"]).index
            )
            for wname, w in (("EW", ones), ("IV", inv)):
                real[f"K{k}_{wname}"] = basket_series(didx, n_dates, r, w, selmask)
        pool_ew, pool_cnt = basket_series(didx, n_dates, r, ones, np.ones(len(rows), dtype=bool))
        pool_iv, _ = basket_series(didx, n_dates, r, inv, np.ones(len(rows), dtype=bool))
        # placebo
        placebo = {name: np.zeros((N_SEEDS, n_dates)) for name in real}
        for s in range(N_SEEDS):
            rng = np.random.default_rng(PLACEBO_SEED_BASE + s)
            rank = sample_placebo_ranks(didx, rng)
            for k in KS:
                m = rank <= k
                for wname, w in (("EW", ones), ("IV", inv)):
                    placebo[f"K{k}_{wname}"][s], _ = basket_series(didx, n_dates, r, w, m)
        wins = dict(windows_all)
        if cal == "LA":
            wins.update(LA_ONLY_WINDOWS)
        cal_res: dict[str, Any] = {}
        for name, (ser, cnt) in real.items():
            cell: dict[str, Any] = {}
            for wn, wb in wins.items():
                wm = window_mask(date_axis, wb)
                x = ser[wm]
                st = series_stats(x, cnt[wm])
                pl_means = placebo[name][:, wm].mean(axis=1) * 1e4
                st["placebo_beat_frac"] = float(np.mean(pl_means < st["mean_bp"]))
                st["placebo_seed_percentile"] = st["placebo_beat_frac"]
                st["placebo_mean_bp"] = float(pl_means.mean())
                st["placebo_p95_bp"] = float(np.quantile(pl_means, 0.95))
                pool_base = pool_iv if name.endswith("IV") else pool_ew
                st["pool_mean_bp"] = float(pool_ew[wm].mean() * 1e4)
                st["excess_bp"] = float(st["mean_bp"] - st["pool_mean_bp"])
                if name.endswith("IV"):
                    st["pool_iv_mean_bp"] = float(pool_base[wm].mean() * 1e4)
                    st["excess_vs_pool_iv_bp"] = float(st["mean_bp"] - st["pool_iv_mean_bp"])
                cell[wn] = st
            cal_res[name] = cell
        results["screen"][cal] = cal_res
        # keep daily series for the book stage
        pd.DataFrame(
            {f"{name}": ser for name, (ser, _c) in real.items()}
            | {"pool_ew": pool_ew, "n_pool": pool_cnt},
            index=date_axis,
        ).to_parquet(CACHE_DIR / f"daily_{cal}.parquet")
        _log(f"{cal} done ({time.time() - t0:.0f}s)")

    # selected-row premarket diagnostics (X15 / X0), main + short windows
    for cal in ("X15", "X0"):
        col_ts = "x15_ts" if cal == "X15" else "x0_ts"
        for k in KS:
            s = sel_store[(cal, k)]
            info: dict[str, Any] = {}
            for wn in ("main", "short"):
                sub = s[window_mask(pd.DatetimeIndex(s["date"]), WINDOWS[wn])]
                ts_et = pd.to_datetime(sub[col_ts], utc=True).dt.tz_convert("America/New_York")
                mod = ts_et.dt.hour * 60 + ts_et.dt.minute
                info[wn] = {
                    "n_rows": int(len(sub)),
                    "median_last_bar_minute_et": _fmt_mod(float(mod.median()))
                    if len(sub)
                    else None,
                    "p10_last_bar_minute_et": _fmt_mod(float(mod.quantile(0.1)))
                    if len(sub)
                    else None,
                    "median_pm_dollar_vol_0400_0911": float(sub["pm_dv"].median())
                    if len(sub)
                    else None,
                    "p10_pm_dollar_vol_0400_0911": float(sub["pm_dv"].quantile(0.1))
                    if len(sub)
                    else None,
                    "median_pm_bar_count": float(sub["pm_n"].median()) if len(sub) else None,
                }
            results["selected_row_premarket"][f"{cal}_K{k}"] = info
    for k in KS:
        a = sel_store[("X15", k)][["date", "symbol"]]
        b = sel_store[("LA", k)][["date", "symbol"]]
        ov: dict[str, Any] = {}
        for wn in ("main", "short"):
            am = a[window_mask(pd.DatetimeIndex(a["date"]), WINDOWS[wn])]
            bm = b[window_mask(pd.DatetimeIndex(b["date"]), WINDOWS[wn])]
            inter = am.merge(bm, on=["date", "symbol"], how="inner")
            ov[wn] = {
                "x15_rows": int(len(am)),
                "la_rows": int(len(bm)),
                "intersection_rows": int(len(inter)),
                "overlap_frac_of_x15": float(len(inter) / len(am)) if len(am) else None,
            }
        results["overlap_x15_la"][f"K{k}"] = ov

    # decision cells
    dec = {}
    for cal in ("X15", "X0"):
        c = results["screen"][cal]["K10_EW"]
        conds = {
            "main_mean_and_t": {
                "mean_bp": c["main"]["mean_bp"],
                "t": c["main"]["t"],
                "threshold": f"mean>={GATE_MAIN_MEAN_BP} bp and t>={GATE_MAIN_T}",
                "pass": bool(
                    c["main"]["mean_bp"] >= GATE_MAIN_MEAN_BP and c["main"]["t"] >= GATE_MAIN_T
                ),
            },
            "main_placebo_beat": {
                "value": c["main"]["placebo_beat_frac"],
                "threshold": f">={GATE_PLACEBO_BEAT}",
                "pass": bool(c["main"]["placebo_beat_frac"] >= GATE_PLACEBO_BEAT),
            },
            "short_mean": {
                "mean_bp": c["short"]["mean_bp"],
                "threshold": f">={GATE_SHORT_MEAN_BP} bp",
                "pass": bool(c["short"]["mean_bp"] >= GATE_SHORT_MEAN_BP),
            },
        }
        conds["all_pass"] = bool(all(v["pass"] for v in conds.values()))
        dec[f"{cal}_K10_EW"] = conds
    results["decision_cells"] = dec
    la_main = results["screen"]["LA"]["K10_EW"]["main"]["mean_bp"]
    if dec["X15_K10_EW"]["all_pass"]:
        verdict = "continue_book_and_forward_shadow"
    elif dec["X0_K10_EW"]["all_pass"]:
        verdict = "blocked_owner_paid_sip"
    elif la_main >= GATE_MAIN_MEAN_BP:
        verdict = "closed_lookahead"
    else:
        verdict = "closed_unstable"
    results["la_k10_ew_main_mean_bp"] = la_main
    results["verdict"] = verdict
    results["book"] = (
        "pending" if verdict == "continue_book_and_forward_shadow" else "not_run_gate_failed"
    )
    RESULTS_PATH.write_text(json.dumps(results, indent=2, default=_json_default) + "\n")
    _log(f"verdict {verdict}; wrote {RESULTS_PATH}")
    return 0


def _fmt_mod(m: float) -> str:
    m = int(round(m))
    return f"{m // 60:02d}:{m % 60:02d}"


def cmd_book(_args: argparse.Namespace) -> int:
    res = json.loads(RESULTS_PATH.read_text())
    if res.get("verdict") != "continue_book_and_forward_shadow":
        _log("gate failed: book not run")
        return 0
    raise SystemExit("book stage is implemented only if the gate passes")


def cmd_reconcile(_args: argparse.Namespace) -> int:
    """Diagnostic only (not part of the verdict): how the C1 T1 long picks (global top-10 by z
    over the >= $1M pool, then cut to dv21 in [5M, 20M)) sit inside this step's LA K10 picks
    (top-10 by z inside the $5-20M pool)."""
    from scripts import run_t20260929_32_gap_fade_ls as parent

    c1 = pd.read_parquet(
        ROOT
        / "reports"
        / "research"
        / "iterations"
        / "t20260930_11_gap_fade_auction"
        / "cache"
        / "picks.parquet"
    )
    pool = load_pool()
    rows, _counts = build_caliber_rows(pool, "LA", parent)
    del pool
    gc.collect()
    sel = select_rows(rows, 10, parent)
    la = sel.merge(rows[["date", "symbol", "oc", "z"]], on=["date", "symbol"], how="left")
    la["date"] = pd.to_datetime(la["date"]).astype("datetime64[ns]")
    lo, hi = pd.Timestamp(WINDOWS["main"][0]), pd.Timestamp(WINDOWS["main"][1])
    la = la[(la["date"] >= lo) & (la["date"] <= hi)]
    t1 = c1[(c1["leg"] == "long") & (c1["tier"] == "T1")].copy()
    t1["date"] = pd.to_datetime(t1["date"]).astype("datetime64[ns]")
    t1 = t1[(t1["date"] >= lo) & (t1["date"] <= hi)]
    t1["symbol"] = t1["symbol"].astype(str)
    la["symbol"] = la["symbol"].astype(str)
    key = ["date", "symbol"]
    inter = la.merge(t1[key], on=key, how="inner")
    rest = la.merge(t1[key].assign(_m=1), on=key, how="left")
    rest = rest[rest["_m"].isna()]
    out = {
        "window": WINDOWS["main"],
        "c1_t1_long_rows": int(len(t1)),
        "c1_t1_rows_inside_c1b_la_k10": int(len(inter)),
        "share_inside": float(len(inter) / len(t1)) if len(t1) else None,
        "c1b_la_k10_rows": int(len(la)),
        "mean_oc_bp_c1_t1_rows_inside": float(inter["oc"].mean() * 1e4) if len(inter) else None,
        "mean_oc_bp_other_la_k10_rows": float(rest["oc"].mean() * 1e4),
        "mean_oc_bp_all_la_k10_rows": float(la["oc"].mean() * 1e4),
        "c1_t1_long_e_bar_bp_from_c1_results": 42.173994320545475,
        "median_z_c1_t1_rows_inside": float(inter["z"].median()) if len(inter) else None,
        "median_z_other_rows": float(rest["z"].median()),
    }
    (OUT_DIR / "c1_reconciliation.json").write_text(
        json.dumps(out, indent=2, default=_json_default) + "\n"
    )
    _log(json.dumps(out))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (
        ("premarket", cmd_premarket),
        ("screen", cmd_screen),
        ("book", cmd_book),
        ("reconcile", cmd_reconcile),
    ):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
