# ruff: noqa: E501
"""T-20260930-13 (corridor C2b): same-half-hour return periodicity (Heston-Korajczyk-Sadka)
with one auction leg per trade.

Design is frozen in ``reports/research/iterations/t20260930_13_intraday_periodicity/
hypotheses.md``; this script only executes it.

Stages:

* ``extract``  scan the minute archive month by month (2023-08 .. latest), both shard layouts
  (whole-year legacy shards ``minute/2023/shard-*.parquet`` and month directories), dedupe on
  (symbol, timestamp), and write ``cache/extract/<YYYY-MM>.parquet`` with, per (symbol, ET
  date): the last close of the bar starting in [T-5 min, T] ET for T in 09:59, 10:29, 14:59,
  15:29, 15:49, plus the last regular-session bar close (start <= 15:59 ET), the number of
  regular bars and the source layout.  Existing months are skipped (checkpoint).
* ``screen``   12 candidates (O/C x L in {1, 5, 20} x P1500/P500) x 4 windows, ordinary and
  Newey-West t, 100-seed same-pool placebo, adjacent-period control, closing-segment split,
  RT1 / 2x / frozen costs, by-year, mechanical tier -> ``results.json`` and ``report.md``.
* ``report``   rewrite ``report.md`` from an existing ``results.json``.

Time-zone rule: bar-start timestamps are UTC; converted exactly to America/New_York (daylight
saving) and then compared by minute of day.
"""

from __future__ import annotations

import argparse
import gc
import json
import math
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import polars as pl  # noqa: E402

ITERATION_ID = "t20260930_13_intraday_periodicity"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
EXTRACT_DIR = CACHE_DIR / "extract"
LEGACY_DIR = EXTRACT_DIR / "_legacy_fp"
RESULTS_PATH = OUT_DIR / "results.json"
REPORT_PATH = OUT_DIR / "report.md"
STAMP_PATH = OUT_DIR / "prebacktest-validated-at.txt"
MINUTE_ROOT = ROOT / "data" / "sip" / "minute"
PANEL_PATH = (
    ROOT
    / "reports"
    / "research"
    / "iterations"
    / "t20260929_35_overnight_persistence"
    / "cache"
    / "panel.parquet"
)

# ---- frozen constants (hypotheses.md) --------------------------------------
EXTRACT_START = (2023, 8)
WARM_START = "2023-07-01"  # daily calendar start (signals need L = 20 warm-up days)
SLOTS: dict[str, int] = {  # minute of day (ET) of the last minute of the window
    "p_0959": 9 * 60 + 59,
    "p_1029": 10 * 60 + 29,
    "p_1459": 14 * 60 + 59,
    "p_1529": 15 * 60 + 29,
    "p_1549": 15 * 60 + 49,
}
SLOT_LOOKBACK_MIN = 5
REG_FIRST_MIN = 9 * 60 + 30
REG_LAST_MIN = 15 * 60 + 59
CONSISTENCY_LOG_TOL = 0.10
PERIODS = ("O", "C")
LOOKBACKS = (1, 5, 20)
POOLS = ("P1500", "P500")
POOL_COL = {"P1500": "p1500", "P500": "p500"}
DECILE_FRAC = 0.10
MIN_LEG = 5
MIN_NAMES = 40
DTC_ETB_MAX = (
    0.90  # T-32 DTC_TOP_DECILE: cross-sectional DTC quantile < 0.90 = easy-to-borrow proxy
)
N_SEEDS = 100
NW_LAGS = 5
TRADING_DAYS = 252.0
BEAT_MIN = 0.90
T_MIN = 2.0
AUCTION_SIDE_BP = 2.0
CONT_EXTRA_BP = 2.0
WINDOWS: dict[str, tuple[str, str]] = {
    "main": ("2024-01-08", "2026-09-29"),
    "selection": ("2023-09-18", "2025-12-31"),
    "contaminated": ("2026-01-02", "2026-09-17"),
    "new_holdout": ("2026-09-18", "2026-09-29"),
}
DECISION_CELLS = ("C_L20_P1500", "O_L20_P1500")
RET_OF_PERIOD = {"O": "r_O", "C": "r_C"}
CONTROL_OF_PERIOD = {"O": "r_Op", "C": "r_Cp"}


def _log(msg: str) -> None:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"[{time.strftime('%H:%M:%S')}] (maxrss {rss:.0f} MB) {msg}", flush=True)


def _clean(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return f if math.isfinite(f) else None
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.date().isoformat()
    return obj


# ==========================================================================
# stage extract
# ==========================================================================


def aggregate_bars(df: pl.DataFrame) -> pl.DataFrame:
    """Per (symbol, ET date) slot prices from minute bars.

    ``df`` needs columns symbol, timestamp (UTC bar start), close.  Bars are first deduplicated
    on (symbol, timestamp).  Slot price for T = close of the *last* bar (by start time) whose ET
    start minute lies in [T - 5, T]; null when no such bar exists.  ``last_reg_close`` is the
    close of the last bar starting in [09:30, 15:59] ET; ``n_reg`` counts those bars.
    """
    cols = ["symbol", *SLOTS, "last_reg_close", "n_reg", "bar_fp"]
    if df.is_empty():
        return pl.DataFrame(
            schema={
                "symbol": pl.String,
                "date": pl.Date,
                **{c: pl.Float64 for c in [*SLOTS, "last_reg_close"]},
                "n_reg": pl.UInt32,
                "bar_fp": pl.UInt64,
            }
        ).select("symbol", "date", *cols[1:])
    et = pl.col("timestamp").dt.convert_time_zone("America/New_York")
    d = (
        df.unique(subset=["symbol", "timestamp"], keep="last", maintain_order=False)
        .with_columns(et=et)
        .with_columns(
            date=pl.col("et").dt.date(),
            mod=pl.col("et").dt.hour().cast(pl.Int32) * 60
            + pl.col("et").dt.minute().cast(pl.Int32),
        )
        .sort("symbol", "timestamp")
    )
    reg = (pl.col("mod") >= REG_FIRST_MIN) & (pl.col("mod") <= REG_LAST_MIN)
    aggs = [
        pl.col("close")
        .filter((pl.col("mod") >= t - SLOT_LOOKBACK_MIN) & (pl.col("mod") <= t))
        .last()
        .alias(name)
        for name, t in SLOTS.items()
    ]
    aggs.append(pl.col("close").filter(reg).last().alias("last_reg_close"))
    aggs.append(reg.sum().cast(pl.UInt32).alias("n_reg"))
    # order-free fingerprint of the deduplicated regular-session bar set (timestamp, close)
    fp = (pl.struct("timestamp", "close").hash() % 4294967296).cast(pl.UInt64)
    aggs.append(fp.filter(reg).sum().alias("bar_fp"))
    return d.group_by("symbol", "date").agg(aggs)


def _read_bars(
    path: str | Path,
    symbols: list[str],
    utc_lo: datetime | None = None,
    utc_hi: datetime | None = None,
) -> pl.DataFrame | None:
    if pl.read_parquet_schema(str(path)).get("close") is None:  # empty shards carry a null schema
        return None
    lf = (
        pl.scan_parquet(str(path))
        .select("symbol", "timestamp", "close")
        .filter(pl.col("symbol").is_in(symbols))
        # regular hours are 13:30-20:59 UTC in either offset; hour 13..20 covers both
        .filter(pl.col("timestamp").dt.hour().is_between(13, 20))
    )
    if utc_lo is not None:
        lf = lf.filter(pl.col("timestamp") >= pl.lit(utc_lo))
    if utc_hi is not None:
        lf = lf.filter(pl.col("timestamp") < pl.lit(utc_hi))
    df = lf.collect()
    return None if df.is_empty() else df


def _shard_agg(
    path: str | Path, symbols: list[str], utc_lo: datetime | None = None
) -> pl.DataFrame | None:
    df = _read_bars(path, symbols, utc_lo)
    return None if df is None else aggregate_bars(df)


def layout_paths(root: Path, year: int) -> tuple[list[str], dict[int, list[str]]]:
    """Legacy whole-year shard paths and month-directory shard paths for one year."""
    year_dir = root / str(year)
    if not year_dir.is_dir():
        return [], {}
    legacy = sorted(str(p) for p in year_dir.glob("shard-*.parquet"))
    months: dict[int, list[str]] = {}
    for mdir in sorted(year_dir.iterdir()):
        if mdir.is_dir() and mdir.name.isdigit():
            months[int(mdir.name)] = sorted(str(p) for p in mdir.glob("shard-*.parquet"))
    return legacy, months


def _tag(df: pl.DataFrame | None, src: str) -> pl.DataFrame | None:
    return None if df is None else df.with_columns(src=pl.lit(src))


def _month_filter(df: pl.DataFrame, year: int, month: int) -> pl.DataFrame:
    return df.filter((pl.col("date").dt.year() == year) & (pl.col("date").dt.month() == month))


def legacy_year_pass(
    root: Path, year: int, symbols: list[str], first_month: int, workers: int = 4
) -> dict[int, pl.DataFrame]:
    """Aggregate the whole-year legacy shards once; returns aggregated rows per month >= first_month."""
    legacy, _months = layout_paths(root, year)
    if not legacy:
        return {}
    lo = datetime(year, first_month, 1, tzinfo=UTC)
    with ThreadPoolExecutor(workers) as ex:
        parts = [x for x in ex.map(lambda f: _shard_agg(f, symbols, lo), legacy) if x is not None]
    if not parts:
        return {}
    allrows = pl.concat(parts)
    out: dict[int, pl.DataFrame] = {}
    for m in sorted(allrows["date"].dt.month().unique().to_list()):
        if m >= first_month:
            out[int(m)] = _month_filter(allrows, year, int(m))
    return out


def reaggregate_symbols(
    root: Path, year: int, month: int, symbols: list[str], chunk: int = 150
) -> pl.DataFrame:
    """Raw-bar re-aggregation (dedupe on (symbol, timestamp) across both layouts) of one month for
    a few symbols, in chunks to bound memory."""
    legacy, months = layout_paths(root, year)
    lo = datetime(year, month, 1, tzinfo=UTC)
    hi = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=UTC)
    out = []
    for i in range(0, len(symbols), chunk):
        part = symbols[i : i + chunk]
        frames = []
        for f in [*legacy, *months.get(month, [])]:
            df = _read_bars(f, part, lo, hi)
            if df is not None:
                frames.append(df)
        if frames:
            out.append(_month_filter(aggregate_bars(pl.concat(frames)), year, month))
    return pl.concat(out) if out else aggregate_bars(pl.DataFrame())


def combine_layouts(
    root: Path,
    year: int,
    month: int,
    month_rows: pl.DataFrame | None,
    legacy_rows: pl.DataFrame | None,
) -> pl.DataFrame:
    """Merge aggregated rows of the two layouts.

    A (symbol, date) present more than once is resolved by the fingerprint of its deduplicated
    regular-session (timestamp, close) bar set: identical sets keep one row (``src`` = both);
    different sets are rebuilt from the raw bars with (symbol, timestamp) dedupe."""
    parts = [p for p in (_tag(month_rows, "month"), _tag(legacy_rows, "legacy")) if p is not None]
    if not parts:
        return aggregate_bars(pl.DataFrame()).with_columns(src=pl.lit("month"))
    allrows = pl.concat(parts)
    value_cols = [c for c in allrows.columns if c not in ("symbol", "date", "src")]
    g = allrows.group_by("symbol", "date").agg(
        *[pl.col(c).first() for c in value_cols],
        nrows=pl.len(),
        nfp=pl.col("bar_fp").n_unique(),
        nsrc=pl.col("src").n_unique(),
        src1=pl.col("src").first(),
    )
    ok = g.filter(pl.col("nfp") == 1).with_columns(
        src=pl.when(pl.col("nsrc") > 1).then(pl.lit("both")).otherwise(pl.col("src1"))
    )
    conflict = g.filter(pl.col("nfp") > 1)
    resolved = ok.select("symbol", "date", *value_cols, "src")
    if conflict.is_empty():
        return resolved
    syms = sorted(conflict["symbol"].unique().to_list())
    fixed = reaggregate_symbols(root, year, month, syms).join(
        conflict.select("symbol", "date"), on=["symbol", "date"], how="semi"
    )
    fixed = fixed.with_columns(src=pl.lit("both"))
    return pl.concat([resolved, fixed.select(resolved.columns)])


def extract_month(
    root: Path,
    year: int,
    month: int,
    symbols: list[str],
    legacy_rows: pl.DataFrame | None,
    workers: int = 4,
) -> pl.DataFrame:
    _legacy, months = layout_paths(root, year)
    files = months.get(month, [])
    with ThreadPoolExecutor(workers) as ex:
        parts = [x for x in ex.map(lambda f: _shard_agg(f, symbols), files) if x is not None]
    month_rows = _month_filter(pl.concat(parts), year, month) if parts else None
    return combine_layouts(root, year, month, month_rows, legacy_rows)


def pool_symbols() -> list[str]:
    p = pl.scan_parquet(PANEL_PATH).filter(
        pl.col("p1500") & (pl.col("date") >= pl.lit(datetime(*EXTRACT_START, 1)))
    )
    return sorted(p.select(pl.col("symbol").cast(pl.String)).unique().collect()["symbol"].to_list())


def cmd_extract(_args: argparse.Namespace) -> int:
    EXTRACT_DIR.mkdir(parents=True, exist_ok=True)
    LEGACY_DIR.mkdir(parents=True, exist_ok=True)
    symbols = pool_symbols()
    _log(f"{len(symbols):,} symbols ever in P1500 since {EXTRACT_START[0]}-{EXTRACT_START[1]:02d}")
    years = sorted(int(p.name) for p in MINUTE_ROOT.iterdir() if p.is_dir() and p.name.isdigit())
    for year in years:
        legacy, months = layout_paths(MINUTE_ROOT, year)
        todo = [
            m
            for m in sorted(months)
            if (year, m) >= EXTRACT_START and not (EXTRACT_DIR / f"{year}-{m:02d}.parquet").exists()
        ]
        if not todo:
            continue
        legacy_by_month: dict[int, pl.DataFrame] = {}
        if legacy:
            need = [m for m in todo if not (LEGACY_DIR / f"{year}-{m:02d}.parquet").exists()]
            if need:
                t0 = time.time()
                legacy_by_month = legacy_year_pass(MINUTE_ROOT, year, symbols, min(need))
                for m, df in legacy_by_month.items():
                    df.write_parquet(LEGACY_DIR / f"{year}-{m:02d}.parquet")
                _log(
                    f"{year}: legacy pass over {len(legacy)} whole-year shards in {time.time() - t0:.0f}s, months {sorted(legacy_by_month)}"
                )
        for m in todo:
            t0 = time.time()
            lp = LEGACY_DIR / f"{year}-{m:02d}.parquet"
            lrows = pl.read_parquet(lp) if lp.exists() else None
            month = extract_month(MINUTE_ROOT, year, m, symbols, lrows)
            tmp = EXTRACT_DIR / f"{year}-{m:02d}.tmp"
            month.write_parquet(tmp)
            tmp.rename(EXTRACT_DIR / f"{year}-{m:02d}.parquet")
            srcs = (
                month.group_by("src").agg(pl.col("symbol").n_unique().alias("n_symbols")).to_dicts()
            )
            _log(
                f"{year}-{m:02d}: {len(months[m])} month shards -> {month.height:,} rows in {time.time() - t0:.0f}s, src {srcs}"
            )
        del legacy_by_month
        gc.collect()
    return 0


# ==========================================================================
# statistics helpers
# ==========================================================================


def newey_west_t(x: np.ndarray, lags: int = NW_LAGS) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < lags + 2:
        return float("nan")
    m = x.mean()
    e = x - m
    var = float(e @ e) / n
    for lag in range(1, lags + 1):
        g = float(e[lag:] @ e[:-lag]) / n
        var += 2.0 * (1.0 - lag / (lags + 1.0)) * g
    if var <= 0:
        return float("nan")
    return float(m / np.sqrt(var / n))


def plain_t(x: np.ndarray) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    sd = x.std(ddof=1) if n > 1 else 0.0
    return float(x.mean() / (sd / np.sqrt(n))) if sd > 0 else float("nan")


def series_stats(x: pd.Series | np.ndarray) -> dict[str, float]:
    """mean (bp), ordinary t, Newey-West(5) t, annualised Sharpe (252 sessions), n."""
    a = np.asarray(x, dtype="float64")
    a = a[np.isfinite(a)]
    n = len(a)
    if n == 0:
        return {
            "mean_bp": float("nan"),
            "t": float("nan"),
            "t_nw5": float("nan"),
            "sharpe": float("nan"),
            "n": 0,
        }
    sd = a.std(ddof=1) if n > 1 else float("nan")
    sharpe = float(a.mean() / sd * np.sqrt(TRADING_DAYS)) if sd and sd > 0 else float("nan")
    return {
        "mean_bp": float(a.mean() * 1e4),
        "t": plain_t(a),
        "t_nw5": newey_west_t(a),
        "sharpe": sharpe,
        "n": int(n),
    }


def min_obs(lookback: int) -> int:
    """At least 0.8 * L valid values (L = 1 needs the previous day)."""
    return int(math.ceil(round(0.8 * lookback, 9)))


def past_mean_signal(r: np.ndarray, lookback: int) -> np.ndarray:
    """S(t) = mean of r over sessions t-L .. t-1 (the row itself is excluded via shift(1))."""
    df = pd.DataFrame(r).shift(1).rolling(lookback, min_periods=min_obs(lookback)).mean()
    return df.to_numpy(dtype="float64")


def leg_size(n_valid: int, frac: float = DECILE_FRAC, min_leg: int = MIN_LEG) -> int:
    k = int(math.floor(frac * n_valid))
    return k if k >= min_leg else 0


def round_trip_bp(h_long_bp: float, h_short_bp: float, mult: float = 1.0) -> float:
    """Two legs, one continuous-auction side and one auction side each.

    1x: (h + 2 + 2) per leg = h + 4.  ``mult`` = 2 gives the 2x stress (2h + 4 continuous side,
    4 auction side -> 2h + 8 per leg)."""
    per_leg_fixed = mult * (AUCTION_SIDE_BP + CONT_EXTRA_BP)
    return mult * (h_long_bp + h_short_bp) + 2.0 * per_leg_fixed


def tier_from_stats(mean_bp: float, t_nw: float, beat: float, rt1_bp: float) -> str:
    """Mechanical tier from hypotheses.md: closed / marginal / pass.

    closed if m < RT1 or Newey-West t < 2.0 or placebo beat < 0.90 (or any input is not finite);
    pass if m >= 2 x RT1 and t, beat pass; otherwise marginal (RT1 <= m < 2 x RT1).
    """
    if not all(math.isfinite(v) for v in (mean_bp, t_nw, beat, rt1_bp)):
        return "closed"
    if mean_bp < rt1_bp or t_nw < T_MIN or beat < BEAT_MIN:
        return "closed"
    if mean_bp >= 2.0 * rt1_bp:
        return "pass"
    return "marginal"


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    return np.asarray((index >= pd.Timestamp(window[0])) & (index <= pd.Timestamp(window[1])))


def consistency_excluded(daily_close: np.ndarray, minute_close: np.ndarray) -> np.ndarray:
    """True where the daily close and the last regular minute bar of the same session disagree
    by more than 10% in log terms (adjustment mismatch).  Unknown (NaN) is not excluded."""
    with np.errstate(invalid="ignore", divide="ignore"):
        d = np.abs(np.log(minute_close / daily_close))
    return np.isfinite(d) & (d > CONSISTENCY_LOG_TOL)


# ==========================================================================
# books
# ==========================================================================


def select_books(sig: np.ndarray, elig: np.ndarray) -> tuple[np.ndarray, np.ndarray] | None:
    """Positions (into the valid-name arrays) of the long decile (top S) and the short decile
    (lowest S among easy-to-borrow names, excluding the long names).  None if a leg is too small."""
    n = len(sig)
    k = leg_size(n)
    if k == 0:
        return None
    order = np.argsort(sig, kind="stable")
    long_idx = order[-k:]
    in_long = np.zeros(n, dtype=bool)
    in_long[long_idx] = True
    cand = order[elig[order] & ~in_long[order]]
    if len(cand) < k:
        return None
    return long_idx, cand[:k]


def run_series(
    sig: np.ndarray,
    ret: np.ndarray,
    pool: np.ndarray,
    elig: np.ndarray,
    spread_bp: np.ndarray | None,
    keep: dict[int, tuple[np.ndarray, np.ndarray, int]] | None = None,
    picks: dict[int, tuple[np.ndarray, np.ndarray]] | None = None,
) -> dict[str, np.ndarray]:
    """Daily LS series for one signal / return / pool.  Inputs are wide (dates x symbols)."""
    n_dates = sig.shape[0]
    out = {
        c: np.full(n_dates, np.nan)
        for c in (
            "gross",
            "long",
            "short",
            "h_long_bp",
            "h_short_bp",
            "k",
            "n_valid",
            "pool_ew",
            "h_pool_bp",
        )
    }
    for i in range(n_dates):
        m = pool[i] & np.isfinite(sig[i]) & np.isfinite(ret[i])
        if m.sum() < MIN_NAMES:
            continue
        idx = np.nonzero(m)[0]
        x, rr, el = sig[i, idx], ret[i, idx], elig[i, idx]
        books = select_books(x, el)
        if books is None:
            continue
        li, si = books
        out["n_valid"][i] = len(idx)
        out["k"][i] = len(li)
        out["long"][i] = rr[li].mean()
        out["short"][i] = rr[si].mean()
        out["gross"][i] = out["long"][i] - out["short"][i]
        out["pool_ew"][i] = rr.mean()
        if spread_bp is not None:
            sp = spread_bp[i, idx]
            fill = np.nanmedian(sp) if np.isfinite(sp).any() else np.nan
            sp = np.where(np.isfinite(sp), sp, fill)
            out["h_long_bp"][i] = 0.5 * sp[li].mean()
            out["h_short_bp"][i] = 0.5 * sp[si].mean()
            out["h_pool_bp"][i] = 0.5 * sp.mean()
        if keep is not None:
            keep[i] = (rr, el, len(li))
        if picks is not None:
            picks[i] = (idx[li], idx[si])
    return out


def placebo_gross(
    keep: dict[int, tuple[np.ndarray, np.ndarray, int]], n_dates: int, seed: int
) -> np.ndarray:
    """Same-pool random long/short: same k; long drawn from all valid names, short drawn from the
    easy-to-borrow names not already long."""
    rng = np.random.default_rng(seed)
    out = np.full(n_dates, np.nan)
    for i, (rr, el, k) in keep.items():
        perm = rng.permutation(len(rr))
        lg = perm[:k]
        rest = perm[k:]
        cand = rest[el[rest]]
        if len(cand) < k:
            continue
        out[i] = rr[lg].mean() - rr[cand[:k]].mean()
    return out


def net_variants(series: dict[str, np.ndarray]) -> dict[str, np.ndarray]:
    hl, hs = series["h_long_bp"], series["h_short_bp"]
    g = series["gross"]
    rt1 = (hl + hs) + 2.0 * (AUCTION_SIDE_BP + CONT_EXTRA_BP)
    rt2 = 2.0 * (hl + hs) + 4.0 * (AUCTION_SIDE_BP + CONT_EXTRA_BP)
    return {
        "rt1": g - rt1 / 1e4,
        "rt2": g - rt2 / 1e4,
        "frozen_10": g - 4 * 10.0 / 1e4,
        "frozen_20": g - 4 * 20.0 / 1e4,
        "_rt1_bp": rt1,
        "_rt2_bp": rt2,
    }


def window_block(
    index: pd.DatetimeIndex,
    series: dict[str, np.ndarray],
    placebo: np.ndarray | None,
    with_costs: bool = True,
) -> dict[str, Any]:
    """placebo: array (n_seeds, n_dates) of placebo gross series."""
    nets = net_variants(series) if with_costs else {}
    out: dict[str, Any] = {}
    for wname, win in WINDOWS.items():
        m = window_mask(index, win)
        g = series["gross"][m]
        st = series_stats(g)
        entry: dict[str, Any] = {
            **st,
            "long_bp": float(np.nanmean(series["long"][m]) * 1e4)
            if np.isfinite(series["long"][m]).any()
            else float("nan"),
            "short_bp": float(np.nanmean(series["short"][m]) * 1e4)
            if np.isfinite(series["short"][m]).any()
            else float("nan"),
            "mean_k": float(np.nanmean(series["k"][m]))
            if np.isfinite(series["k"][m]).any()
            else float("nan"),
            "mean_n_valid": float(np.nanmean(series["n_valid"][m]))
            if np.isfinite(series["n_valid"][m]).any()
            else float("nan"),
        }
        if with_costs:
            ok = np.isfinite(g)
            rt1 = float(np.nanmean(nets["_rt1_bp"][m][ok])) if ok.any() else float("nan")
            entry["h_long_bp"] = (
                float(np.nanmean(series["h_long_bp"][m])) if ok.any() else float("nan")
            )
            entry["h_short_bp"] = (
                float(np.nanmean(series["h_short_bp"][m])) if ok.any() else float("nan")
            )
            entry["rt1_bp"] = rt1
            entry["pool_ew_bp"] = (
                float(np.nanmean(series["pool_ew"][m]) * 1e4) if ok.any() else float("nan")
            )
            entry["h_pool_bp"] = (
                float(np.nanmean(series["h_pool_bp"][m])) if ok.any() else float("nan")
            )
            entry["rt2_bp"] = (
                float(np.nanmean(nets["_rt2_bp"][m][ok])) if ok.any() else float("nan")
            )
            entry["net"] = {
                name: {
                    k2: v
                    for k2, v in series_stats(nets[name][m]).items()
                    if k2 in ("mean_bp", "sharpe", "t_nw5", "n")
                }
                for name in ("rt1", "rt2", "frozen_10", "frozen_20")
            }
        if placebo is not None:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", RuntimeWarning)
                pm = np.nanmean(np.where(m[None, :], placebo, np.nan), axis=1)
            real = st["mean_bp"] / 1e4
            okp = np.isfinite(pm)
            entry["placebo_beat"] = (
                float(np.mean(real > pm[okp])) if okp.any() and np.isfinite(real) else float("nan")
            )
            entry["placebo_mean_bp"] = float(np.nanmean(pm) * 1e4) if okp.any() else float("nan")
            entry["placebo_max_bp"] = float(np.nanmax(pm) * 1e4) if okp.any() else float("nan")
        out[wname] = entry
    return out


def cost_sensitivity(
    mean_bp: float, grid: tuple[float, ...] = (2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0)
) -> dict[str, Any]:
    """Diagnostic only (not in the tier): gross mean minus round trip 2h + 8 bp (1x) or 4h + 16 bp
    (2x) for a fixed per-leg half spread h, and the break-even h (equal h on both legs)."""
    return {
        "note": "diagnostic; the tier uses the frozen h = 0.5 x 21-day Abdi-Ranaldo spread of the selected names",
        "breakeven_h_bp_1x": (mean_bp - 8.0) / 2.0,
        "breakeven_h_bp_2x": (mean_bp - 16.0) / 4.0,
        "net_bp_1x": {str(int(h)): mean_bp - (2.0 * h + 8.0) for h in grid},
        "net_bp_2x": {str(int(h)): mean_bp - (4.0 * h + 16.0) for h in grid},
    }


def by_year_table(index: pd.DatetimeIndex, gross: np.ndarray) -> dict[str, Any]:
    out = {}
    years = np.asarray(index.year)
    for y in sorted(set(years.tolist())):
        s = series_stats(gross[years == y])
        out[str(y)] = {"mean_bp": s["mean_bp"], "t_nw5": s["t_nw5"], "n": s["n"]}
    return out


# ==========================================================================
# stage screen
# ==========================================================================


def load_extract() -> pl.DataFrame:
    files = sorted(EXTRACT_DIR.glob("*.parquet"))
    if not files:
        raise SystemExit("no extract cache; run the extract stage first")
    return pl.concat([pl.read_parquet(f) for f in files])


def wide_from_long(
    df: pd.DataFrame, value_cols: list[str], index: pd.DatetimeIndex, columns: pd.Index
) -> dict[str, np.ndarray]:
    ri = index.get_indexer(pd.DatetimeIndex(df["date"]))
    ci = columns.get_indexer(df["symbol"])
    ok = (ri >= 0) & (ci >= 0)
    out = {}
    for c in value_cols:
        arr = np.full((len(index), len(columns)), np.nan, dtype="float64")
        arr[ri[ok], ci[ok]] = df[c].to_numpy("float64")[ok]
        out[c] = arr
    return out


def period_returns(
    open_d: np.ndarray, close_d: np.ndarray, slots: dict[str, np.ndarray]
) -> dict[str, np.ndarray]:
    with np.errstate(invalid="ignore", divide="ignore"):
        return {
            "r_O": slots["p_0959"] / open_d - 1.0,
            "r_Op": slots["p_1029"] / slots["p_0959"] - 1.0,
            "r_C": close_d / slots["p_1529"] - 1.0,
            "r_Cp": slots["p_1529"] / slots["p_1459"] - 1.0,
            "r_C1": slots["p_1549"] / slots["p_1529"] - 1.0,
            "r_C2": close_d / slots["p_1549"] - 1.0,
        }


def cmd_screen(_args: argparse.Namespace) -> int:
    t_start = time.time()
    from open_composer.research.features import price_hygiene as ph
    from scripts import run_t20260928_30_smallcap_ml_book as ml30
    from scripts import run_t20260929_35_overnight_persistence as t35

    t32 = t35.t32
    if not STAMP_PATH.exists():
        raise SystemExit("prebacktest-validated-at.txt missing; run the pre-backtest gate first")
    stamp = STAMP_PATH.read_text(encoding="utf-8").strip()

    panel = pd.read_parquet(
        PANEL_PATH,
        columns=["date", "symbol", "p1500", "p500", "dtc_cross_sectional_pct"],
        filters=[("date", ">=", pd.Timestamp(WARM_START))],
    )
    panel["symbol"] = panel["symbol"].astype(str)
    calendar = pd.DatetimeIndex(sorted(panel["date"].unique()))
    ever = panel.loc[
        panel["p1500"]
        & (panel["date"] >= pd.Timestamp(f"{EXTRACT_START[0]}-{EXTRACT_START[1]:02d}-01")),
        "symbol",
    ]
    symbols = sorted(ever.unique().tolist())
    cols = pd.Index(symbols)
    _log(
        f"panel rows {len(panel):,}, calendar {len(calendar)} sessions {calendar[0].date()}..{calendar[-1].date()}, {len(symbols):,} symbols"
    )
    pw = wide_from_long(
        panel.assign(p1500=panel["p1500"].astype(float), p500=panel["p500"].astype(float)),
        ["p1500", "p500", "dtc_cross_sectional_pct"],
        calendar,
        cols,
    )
    pools = {"P1500": pw["p1500"] == 1.0, "P500": pw["p500"] == 1.0}
    dtc = pw["dtc_cross_sectional_pct"]
    elig = ~np.isfinite(dtc) | (dtc < DTC_ETB_MAX)  # missing DTC is not restricted
    del panel, ever, pw
    gc.collect()

    # ---- minute extract -> wide slots
    ex = load_extract().to_pandas()
    ex["date"] = pd.to_datetime(ex["date"])
    ex = ex[ex["symbol"].isin(set(symbols))]
    exw = wide_from_long(ex, [*SLOTS, "last_reg_close", "n_reg"], calendar, cols)
    src_2023 = ex[ex["date"].dt.year == 2023].groupby("symbol")["src"].agg(lambda s: set(s))
    n_legacy_syms_2023 = int(sum("legacy" in v or "both" in v for v in src_2023))
    n_legacy_only_syms_2023 = int(sum(v == {"legacy"} for v in src_2023))
    n_month_syms_2023 = int(sum("month" in v or "both" in v for v in src_2023))
    n_both_rows = int((ex["src"] == "both").sum())
    del ex
    gc.collect()

    # ---- daily open/close (sanitized) -> wide
    date_strs = [d.strftime("%Y-%m-%d") for d in calendar]
    wide = t35.load_wide_float32(symbols, date_strs)
    wide.pop("_overlap")
    open_w, high_w, low_w, close_w = wide["open"], wide["high"], wide["low"], wide["close"]
    del wide
    close_s, open_s, hyg = ph.sanitize_price_matrices(close_w, open_w)
    assert open_s is not None
    masked = close_s.isna() & close_w.notna()
    high_s = high_w.mask(masked | open_s.isna())
    low_s = low_w.mask(masked | open_s.isna())
    del close_w, open_w, high_w, low_w, masked
    _log(f"hygiene: symbols_masked {hyg.symbols_masked}, cells masked {hyg.price_cells_masked}")
    close_d = close_s.to_numpy("float64")
    open_d = open_s.to_numpy("float64")
    with np.errstate(invalid="ignore", divide="ignore"):
        gap = open_d[1:] / close_d[:-1]
    split_like = np.zeros_like(open_d, dtype=bool)
    split_like[1:] = t32.is_split_like_ratio(gap)
    del gap
    # trailing 21-session Abdi-Ranaldo half-spread source, shifted one session (data before t only)
    _log("Abdi-Ranaldo spread per symbol, shifted one session")
    spread = np.full(close_d.shape, np.nan)
    for j, s in enumerate(close_s.columns):
        est = ml30.spread_estimate_from_ohlc(close_s[s], high_s[s], low_s[s]).shift(1)
        spread[:, j] = est.to_numpy("float64")
    spread_bp = spread * 1e4
    del close_s, open_s, high_s, low_s, spread
    gc.collect()

    # ---- exclusions and returns
    incons = consistency_excluded(close_d, exw["last_reg_close"])
    slots = {k: exw[k] for k in SLOTS}
    rets = period_returns(open_d, close_d, slots)
    bad = split_like | incons
    for k in rets:
        rets[k] = np.where(bad, np.nan, rets[k])
    in_pool_any = pools["P1500"]
    in_window = calendar >= pd.Timestamp("2023-08-01")
    pool_days = in_pool_any & in_window[:, None]
    n_pool_days = int(pool_days.sum())
    years = np.asarray(calendar.year)
    coverage: dict[str, Any] = {}
    for y in sorted(set(years[in_window].tolist())):
        ym = pool_days & (years == y)[:, None]
        n = int(ym.sum())
        coverage[str(y)] = {
            "pool_days_p1500": n,
            "with_minute_bars_share": float((ym & np.isfinite(exw["last_reg_close"])).sum() / n)
            if n
            else float("nan"),
            "with_r_O_share": float((ym & np.isfinite(rets["r_O"])).sum() / n)
            if n
            else float("nan"),
            "with_r_C_share": float((ym & np.isfinite(rets["r_C"])).sum() / n)
            if n
            else float("nan"),
            "dtc_missing_share": float((ym & ~np.isfinite(dtc)).sum() / n) if n else float("nan"),
        }
    rows_incons_pool = int((incons & pool_days).sum())
    rows_split_pool = int((split_like & pool_days).sum())
    data_block = {
        "minute_coverage_by_year": coverage,
        "consistency_excluded_rows_pool_days": rows_incons_pool,
        "consistency_excluded_rows_all_symbol_days": int(incons.sum()),
        "split_like_excluded_rows_pool_days": rows_split_pool,
        "split_like_excluded_rows_all_symbol_days": int(split_like.sum()),
        "pool_days_p1500_total": n_pool_days,
        "symbols_ever_p1500_since_2023_08": len(symbols),
        "symbols_2023_with_legacy_shard_rows": n_legacy_syms_2023,
        "symbols_2023_legacy_only": n_legacy_only_syms_2023,
        "symbols_2023_with_month_dir_rows": n_month_syms_2023,
        "rows_both_layouts_after_dedupe": n_both_rows,
        "hygiene_symbols_masked": int(hyg.symbols_masked),
        "hygiene_price_cells_masked": int(hyg.price_cells_masked),
        "abs_return_gt_50pct_rows": {k: int((np.abs(rets[k]) > 0.5).sum()) for k in ("r_O", "r_C")},
        "notes": [
            "pool membership flags, dv21 and DTC quantile come from the T-20260929-35 panel cache (read only)",
            "daily open/close re-loaded from data/sip/daily + data/sip-delisted for 2023-07..2026-09 and sanitized with price_hygiene defaults on that window",
        ],
    }

    # ---- signals
    _log("signals")
    sigs: dict[tuple[str, int], np.ndarray] = {}
    for X in PERIODS:
        for L in LOOKBACKS:
            sigs[(X, L)] = past_mean_signal(rets[RET_OF_PERIOD[X]], L)
    ctrl_sigs = {X: past_mean_signal(rets[CONTROL_OF_PERIOD[X]], 20) for X in PERIODS}

    n_dates = len(calendar)
    cells: dict[str, Any] = {}
    series_by_cell: dict[str, dict[str, np.ndarray]] = {}
    by_year: dict[str, Any] = {}
    for X in PERIODS:
        for L in LOOKBACKS:
            for P in POOLS:
                cid = f"{X}_L{L}_{P}"
                t0 = time.time()
                keep: dict[int, tuple[np.ndarray, np.ndarray, int]] = {}
                picks: dict[int, tuple[np.ndarray, np.ndarray]] = {}
                ser = run_series(
                    sigs[(X, L)], rets[RET_OF_PERIOD[X]], pools[P], elig, spread_bp, keep, picks
                )
                if cid in DECISION_CELLS:
                    rows = [
                        (calendar[i], cid, leg, symbols[j])
                        for i, (lj, sj) in picks.items()
                        for leg, arr in (("long", lj), ("short", sj))
                        for j in arr
                        if calendar[i] >= pd.Timestamp(WINDOWS["main"][0])
                    ]
                    pd.DataFrame(rows, columns=["date", "cell", "leg", "symbol"]).to_parquet(
                        CACHE_DIR / f"picks_{cid}.parquet", index=False
                    )
                series_by_cell[cid] = ser
                plc = np.vstack([placebo_gross(keep, n_dates, seed) for seed in range(N_SEEDS)])
                blk = window_block(calendar, ser, plc)
                m = blk["main"]
                tier = tier_from_stats(m["mean_bp"], m["t_nw5"], m["placebo_beat"], m["rt1_bp"])
                cells[cid] = {
                    "period": X,
                    "lookback": L,
                    "pool": P,
                    "decision_cell": cid in DECISION_CELLS,
                    "windows": blk,
                    "tier_main": tier,
                }
                by_year[cid] = by_year_table(calendar, ser["gross"])
                _log(
                    f"{cid}: main mean {m['mean_bp']:.2f} bp, t_nw5 {m['t_nw5']:.2f}, beat {m['placebo_beat']:.2f}, rt1 {m['rt1_bp']:.2f}, tier {tier} ({time.time() - t0:.0f}s)"
                )

    # ---- adjacent-period control (signal from the adjacent segment, evaluated on the current one)
    controls: dict[str, Any] = {}
    for X in PERIODS:
        for P in POOLS:
            cid = f"{X}_L20_{P}"
            ser_c = run_series(ctrl_sigs[X], rets[RET_OF_PERIOD[X]], pools[P], elig, spread_bp)
            blk = window_block(calendar, ser_c, None, with_costs=False)
            same = series_by_cell[cid]["gross"]
            diff = same - ser_c["gross"]
            dwin = {}
            for wname, win in WINDOWS.items():
                mk = window_mask(calendar, win)
                dst = series_stats(diff[mk])
                dwin[wname] = {"mean_bp": dst["mean_bp"], "t_nw5": dst["t_nw5"], "n": dst["n"]}
            controls[f"{X}_ctrl_{P}"] = {
                "signal": f"S({'r_Op' if X == 'O' else 'r_Cp'}, L=20)",
                "evaluated_on": RET_OF_PERIOD[X],
                "windows": blk,
                "same_period_minus_control": dwin,
            }

    # ---- closing-segment split (same picks, restricted to rows with r_C, r_C1, r_C2 all valid)
    split: dict[str, Any] = {}
    allc = np.isfinite(rets["r_C"]) & np.isfinite(rets["r_C1"]) & np.isfinite(rets["r_C2"])
    for P in POOLS:
        sig = np.where(allc, sigs[("C", 20)], np.nan)
        res = {}
        for name in ("r_C", "r_C1", "r_C2"):
            ser_s = run_series(sig, rets[name], pools[P], elig, None)
            res[name] = window_block(calendar, ser_s, None, with_costs=False)
        split[f"C_L20_{P}"] = {
            "note": "signal S_C_L20; identical picks for r_C, r_C1 (15:30-15:50) and r_C2 (15:50-close incl. auction); rows restricted to all three returns valid",
            "returns": res,
        }

    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    decision_cells = {}
    for cid in DECISION_CELLS:
        m = cells[cid]["windows"]["main"]
        decision_cells[cid] = {
            "window": "main",
            "mean_bp": m["mean_bp"],
            "t": m["t"],
            "t_nw5": m["t_nw5"],
            "n": m["n"],
            "sharpe": m["sharpe"],
            "placebo_beat": m["placebo_beat"],
            "placebo_mean_bp": m["placebo_mean_bp"],
            "rt1_bp": m["rt1_bp"],
            "rt2_bp": m["rt2_bp"],
            "mean_over_rt1": m["mean_bp"] / m["rt1_bp"] if m["rt1_bp"] else float("nan"),
            "net": m["net"],
            "cost_sensitivity_diagnostic": cost_sensitivity(m["mean_bp"]),
            "tier": tier_from_stats(m["mean_bp"], m["t_nw5"], m["placebo_beat"], m["rt1_bp"]),
            "marginal_next_step": "measured Alpaca half spread on 200 selected (symbol, day) pairs, 2x cost >= 0"
            if tier_from_stats(m["mean_bp"], m["t_nw5"], m["placebo_beat"], m["rt1_bp"])
            == "marginal"
            else None,
        }

    results = {
        "iter_id": ITERATION_ID,
        "generated_at": generated_at,
        "prebacktest_validated_at": stamp,
        "screen_seconds": round(time.time() - t_start, 1),
        "windows": WINDOWS,
        "frozen": {
            "rule": "closed if m < RT1 or t_nw5 < 2.0 or placebo beat < 0.90; pass if m >= 2 x RT1 and gates pass; marginal RT1 <= m < 2 x RT1",
            "rt1": "long leg h + 4 bp plus short leg h + 4 bp, h = 0.5 x 21-day AR spread shifted one session, mean over selected names per day",
            "n_seeds": N_SEEDS,
            "short_leg": "easy-to-borrow proxy DTC quantile < 0.90, missing DTC not restricted, no borrow fee (intraday)",
        },
        "data": data_block,
        "decision_cells": decision_cells,
        "cells": cells,
        "controls": controls,
        "split": split,
        "by_year": by_year,
        "trial_count": len(cells),
    }
    RESULTS_PATH.write_text(json.dumps(_clean(results), indent=1) + "\n", encoding="utf-8")
    _log(f"results written {RESULTS_PATH}")
    write_report(json.loads(RESULTS_PATH.read_text(encoding="utf-8")))
    return 0


# ==========================================================================
# report
# ==========================================================================


def _f(x: Any, nd: int = 2) -> str:
    if x is None:
        return "n/a"
    if isinstance(x, (int, np.integer)):
        return f"{int(x):,}"
    return f"{x:.{nd}f}"


def write_report(res: dict[str, Any]) -> None:
    L: list[str] = []
    L.append(f"# {ITERATION_ID} results (numbers copied from results.json)")
    L.append("")
    L.append(
        f"Generated {res['generated_at']}; pre-backtest gate stamp {res['prebacktest_validated_at']}. Design frozen in hypotheses.md; tiers are mechanical, the verdict belongs to the lead round."
    )
    L.append("")
    L.append("## Decision cells (main window 2024-01-08..2026-09-29)")
    L.append("")
    L.append("| cell | mean bp | t | t_nw5 | n | placebo beat | RT1 bp | mean/RT1 | tier |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for cid, d in res["decision_cells"].items():
        L.append(
            f"| {cid} | {_f(d['mean_bp'])} | {_f(d['t'])} | {_f(d['t_nw5'])} | {_f(d['n'])} | {_f(d['placebo_beat'])} | {_f(d['rt1_bp'])} | {_f(d['mean_over_rt1'])} | {d['tier']} |"
        )
    L.append("")
    L.append("Net means (bp per day, annualised Sharpe) in the main window:")
    L.append("")
    L.append("| cell | RT1 net | RT2 (2x) net | frozen 10 bp/side | frozen 20 bp/side |")
    L.append("|---|---|---|---|---|")
    for cid, d in res["decision_cells"].items():
        n = d["net"]
        L.append(
            f"| {cid} | {_f(n['rt1']['mean_bp'])} ({_f(n['rt1']['sharpe'])}) | {_f(n['rt2']['mean_bp'])} ({_f(n['rt2']['sharpe'])}) | {_f(n['frozen_10']['mean_bp'])} ({_f(n['frozen_10']['sharpe'])}) | {_f(n['frozen_20']['mean_bp'])} ({_f(n['frozen_20']['sharpe'])}) |"
        )
    L.append("")
    L.append(
        "Cost sensitivity (diagnostic, not in the tier): break-even half spread per leg h (equal on both legs) at 1x = (m - 8) / 2 bp and at 2x = (m - 16) / 4 bp; pool-wide mean h of the frozen proxy and long-leg excess over the pool mean:"
    )
    L.append("")
    L.append(
        "| cell | break-even h 1x | break-even h 2x | mean h selected long / short | mean h whole valid pool | long minus pool mean bp |"
    )
    L.append("|---|---|---|---|---|---|")
    for cid, d in res["decision_cells"].items():
        w = res["cells"][cid]["windows"]["main"]
        cs = d["cost_sensitivity_diagnostic"]
        L.append(
            f"| {cid} | {_f(cs['breakeven_h_bp_1x'])} | {_f(cs['breakeven_h_bp_2x'])} | {_f(w['h_long_bp'])} / {_f(w['h_short_bp'])} | {_f(w['h_pool_bp'])} | {_f(w['long_bp'] - w['pool_ew_bp'])} |"
        )
    L.append("")
    L.append("## All 12 candidates, gross LS mean (bp), t_nw5, placebo beat, RT1 (main window)")
    L.append("")
    L.append("| cell | mean bp | t_nw5 | beat | RT1 bp | long bp | short bp | tier |")
    L.append("|---|---|---|---|---|---|---|---|")
    for cid, c in res["cells"].items():
        m = c["windows"]["main"]
        L.append(
            f"| {cid} | {_f(m['mean_bp'])} | {_f(m['t_nw5'])} | {_f(m['placebo_beat'])} | {_f(m['rt1_bp'])} | {_f(m['long_bp'])} | {_f(m['short_bp'])} | {c['tier_main']} |"
        )
    L.append("")
    L.append("## Other windows, decision cells (mean bp, t_nw5, n)")
    L.append("")
    L.append("| cell | selection | contaminated 2026 | new holdout |")
    L.append("|---|---|---|---|")
    for cid in res["decision_cells"]:
        w = res["cells"][cid]["windows"]
        L.append(
            "| "
            + cid
            + " | "
            + " | ".join(
                f"{_f(w[k]['mean_bp'])}, {_f(w[k]['t_nw5'])}, {_f(w[k]['n'])}"
                for k in ("selection", "contaminated", "new_holdout")
            )
            + " |"
        )
    L.append("")
    L.append("## Adjacent-period control (main window, L = 20)")
    L.append("")
    L.append(
        "| control | control mean bp | control t_nw5 | same-period minus control bp | diff t_nw5 |"
    )
    L.append("|---|---|---|---|---|")
    for cid, c in res["controls"].items():
        m = c["windows"]["main"]
        d = c["same_period_minus_control"]["main"]
        L.append(
            f"| {cid} | {_f(m['mean_bp'])} | {_f(m['t_nw5'])} | {_f(d['mean_bp'])} | {_f(d['t_nw5'])} |"
        )
    L.append("")
    L.append("## Closing-segment split (main window, signal S_C_L20)")
    L.append("")
    L.append("| pool | r_C mean bp (t_nw5) | r_C1 15:30-15:50 | r_C2 15:50-close |")
    L.append("|---|---|---|---|")
    for cid, s in res["split"].items():
        r = s["returns"]
        L.append(
            f"| {cid} | "
            + " | ".join(
                f"{_f(r[k]['main']['mean_bp'])} ({_f(r[k]['main']['t_nw5'])})"
                for k in ("r_C", "r_C1", "r_C2")
            )
            + " |"
        )
    L.append("")
    L.append("## By year, gross LS mean bp (t_nw5), decision cells")
    L.append("")
    for cid in res["decision_cells"]:
        L.append(
            f"- {cid}: "
            + "; ".join(
                f"{y} {_f(v['mean_bp'])} ({_f(v['t_nw5'])}, n {v['n']})"
                for y, v in res["by_year"][cid].items()
            )
        )
    L.append("")
    d = res["data"]
    L.append("## Data")
    L.append("")
    L.append("| year | P1500 pool-days | with minute bars | with r_O | with r_C | DTC missing |")
    L.append("|---|---|---|---|---|---|")
    for y, v in d["minute_coverage_by_year"].items():
        L.append(
            f"| {y} | {_f(v['pool_days_p1500'])} | {_f(v['with_minute_bars_share'], 3)} | {_f(v['with_r_O_share'], 3)} | {_f(v['with_r_C_share'], 3)} | {_f(v['dtc_missing_share'], 3)} |"
        )
    L.append("")
    L.append(
        f"- Consistency exclusions (daily close vs last regular minute bar, |ln ratio| > 0.10): {_f(d['consistency_excluded_rows_pool_days'])} P1500 pool-days ({_f(d['consistency_excluded_rows_all_symbol_days'])} symbol-days overall)."
    )
    L.append(
        f"- Split-like open/prev-close exclusions: {_f(d['split_like_excluded_rows_pool_days'])} pool-days ({_f(d['split_like_excluded_rows_all_symbol_days'])} overall)."
    )
    L.append(
        f"- 2023 legacy whole-year shards contribute {_f(d['symbols_2023_with_legacy_shard_rows'])} symbols ({_f(d['symbols_2023_legacy_only'])} only from legacy); month directories {_f(d['symbols_2023_with_month_dir_rows'])}; rows present in both layouts after dedupe: {_f(d['rows_both_layouts_after_dedupe'])}."
    )
    L.append(
        f"- Hygiene (2023-07..2026-09 window): {_f(d['hygiene_symbols_masked'])} symbols masked, {_f(d['hygiene_price_cells_masked'])} cells."
    )
    L.append(
        "- Choices not fixed by hypotheses.md: daily open/close re-loaded and sanitized on the 2023-07.. window (not the T-35 full-history run); split-like sessions and consistency exclusions blank all returns of that symbol-day; a day needs >= 40 valid names and legs of >= 5; missing DTC not restricted; spread NaN filled with the day's valid-name median; placebo short leg drawn from the easy-to-borrow names not already long."
    )
    REPORT_PATH.write_text("\n".join(L) + "\n", encoding="utf-8")
    _log(f"report written {REPORT_PATH}")


def cmd_report(_args: argparse.Namespace) -> int:
    write_report(json.loads(RESULTS_PATH.read_text(encoding="utf-8")))
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in (("extract", cmd_extract), ("screen", cmd_screen), ("report", cmd_report)):
        p = sub.add_parser(name)
        p.set_defaults(fn=fn)
    args = ap.parse_args(argv)
    return int(args.fn(args))


if __name__ == "__main__":
    raise SystemExit(main())
