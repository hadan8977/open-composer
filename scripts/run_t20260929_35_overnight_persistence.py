# ruff: noqa: E501
"""T-20260929-35 (corridor C2a): overnight-return persistence held close auction -> next open.

Design is frozen in ``reports/research/iterations/t20260929_35_overnight_persistence/
hypotheses.md`` (written before any overnight number was computed). This script only
executes that design; it changes no pool, signal, candidate, window, gate or cost.

Stages (argparse sub-commands):

* ``panel``  -- DuckDB (1 GB) finds every non-fund, non-OTC symbol that ever ranks in the
  dv21 top 2000, builds float wide matrices from ``data/sip/daily`` plus
  ``data/sip-delisted/by_year``, applies ``price_hygiene.sanitize_price_matrices`` (open
  passed too) and the T-32 split-like filter on open_t / close_{t-1}, recomputes dv21 and
  the pools on the cleaned data and caches the long panel to ``cache/panel.parquet``.
* ``screen`` -- 5 signals x 2 pools x {LS decile, LO top 20} nightly series, five windows,
  ordinary and Newey-West t, 100-seed same-pool random placebo, six cost contracts,
  diagnostics (a)-(f), by-year table, mechanical tier; writes ``results.json`` and
  ``report.md``.

Conventions fixed here where hypotheses.md leaves a detail open (all documented in the report):

* pool rank is taken on dv21 among all non-fund non-OTC names with a valid dv21, then the
  $5 / 63-session filters are applied (the literal order of the pool text);
* decile leg size k = floor(0.10 * n_valid), a night needs k >= 5; LO takes the 20 best;
* signal ties are broken by the stable row order (symbol ascending);
* AR spread NaN is filled with that night's pool median before it is used as a cost;
* the past-intraday signal of diagnostic (b) is mean(ID_{t-21..t-1}), the same
  information set as the intraday leg of TOW_21;
* a night is a Friday night when the signal date is a Friday.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from open_composer.research.features import price_hygiene as ph  # noqa: E402
from scripts import run_t20260928_30_smallcap_ml_book as ml30  # noqa: E402
from scripts import run_t20260929_32_gap_fade_ls as t32  # noqa: E402

ITERATION_ID = "t20260929_35_overnight_persistence"
OUT_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = OUT_DIR / "cache"
PANEL_PATH = CACHE_DIR / "panel.parquet"
SPY_PATH = CACHE_DIR / "spy_overnight.parquet"
META_PATH = CACHE_DIR / "panel_meta.json"
RESULTS_PATH = OUT_DIR / "results.json"
REPORT_PATH = OUT_DIR / "report.md"
PREBACKTEST_STAMP = OUT_DIR / "prebacktest-validated-at.txt"

DAILY_GLOB = str(ROOT / "data" / "sip" / "daily" / "*" / "*.parquet")
DELISTED_GLOB = str(ROOT / "data" / "sip-delisted" / "by_year" / "*" / "*.parquet")
ASSET_METADATA = ROOT / "data" / "features" / "universe" / "_asset_metadata.parquet"

DV_WINDOW = 21
CANDIDATE_TOP_N = 2000
POOL_SIZES = {"P1500": 1500, "P500": 500}
MIN_CLOSE = 5.0
MIN_HISTORY = 63
DECILE_FRAC = 0.10
MIN_LEG = 5
LO_N = 20
PLACEBO_SEEDS = 100
NW_LAGS = 5
TRADING_DAYS = 252.0

SIGNALS = ("ON5", "ON21", "ON63", "ON252", "TOW21")
SIGNAL_LOOKBACK = {"ON5": 5, "ON21": 21, "ON63": 63, "ON252": 252, "TOW21": 21}
SIGNAL_MIN_OBS = {"ON5": 4, "ON21": 17, "ON63": 51, "ON252": 200}
ID_MIN_OBS = 17
FORMS = ("LS", "LO")

DECISION_CELL = "ON21_P1500_LS"
SECONDARY_CELL = "ON5_P1500_LS"
DECISION_T_MIN = 2.0
SECONDARY_T_MIN = 2.5
ROUND_TRIP_1X_BP = 8.0  # two legs x two auction sides x 2 bp
PASS_MEAN_BP = 16.0
BEAT_MIN = 0.90

WINDOWS: dict[str, tuple[str, str]] = {
    "main": ("2024-01-08", "2026-09-29"),
    "selection": ("2023-09-18", "2025-12-31"),
    "stress": ("2016-05-02", "2023-08-31"),
    "contaminated": ("2026-01-02", "2026-09-17"),
    "new_holdout": ("2026-09-18", "2026-09-29"),
}

AUCTION_SIDE_BP = 2.0
COST_CONTRACTS = (
    "auction_1x",
    "auction_2x",
    "continuous_1x",
    "continuous_2x",
    "frozen_10",
    "frozen_20",
)
BORROW_TIERS = t32.ADV_BUCKETS  # dv21 bounds -> annual rate
BORROW_DEFAULT_RATE = 0.05  # names below the $5M lowest tier
BORROW_DAYCOUNT = t32.BORROW_DAYCOUNT
DTC_ETB_MAX = t32.DTC_TOP_DECILE  # DTC cross-sectional quantile < 0.90 = easy-to-borrow proxy


def _log(msg: str) -> None:
    import resource

    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    print(f"[{time.strftime('%H:%M:%S')}] (maxrss {rss:.0f} MB) {msg}", flush=True)


def _json_default(o: Any) -> Any:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if not math.isfinite(float(o)) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return o.date().isoformat()
    raise TypeError(type(o))


def _clean(obj: Any) -> Any:
    """Replace non-finite floats by None so results.json is strict JSON."""
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (float, np.floating)):
        return float(obj) if math.isfinite(float(obj)) else None
    return obj


# ==========================================================================
# pure helpers (unit tested)
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
    """mean (bp), ordinary t, Newey-West(5) t, annualised Sharpe (252 nights), n."""
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


def net_stats(x: pd.Series | np.ndarray) -> dict[str, float]:
    s = series_stats(x)
    return {"mean_bp": s["mean_bp"], "sharpe": s["sharpe"], "t_nw5": s["t_nw5"], "n": s["n"]}


def signal_min_obs(name: str) -> int:
    return SIGNAL_MIN_OBS[name]


def overnight_intraday_returns(
    open_w: pd.DataFrame, close_w: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """``ON_t = ln(open_t / close_{t-1})`` and ``ID_t = ln(close_t / open_t)``.

    ON_t is known at the 09:30 open of t; ID_t only at the 16:00 close of t.
    """
    on = np.log(open_w / close_w.shift(1))
    id_ = np.log(close_w / open_w)
    return on, id_


def rolling_signals(on: pd.DataFrame, id_: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """The five ranking signals as known at the close of t.

    ON_L uses ON_{t-L+1..t} (includes tonight's already-known overnight), TOW_21 =
    mean(ON_{t-20..t}) - mean(ID_{t-21..t-1}); the intraday part is shifted one session
    because ID_t is only known at the close.
    """
    out: dict[str, pd.DataFrame] = {}
    for name in ("ON5", "ON21", "ON63", "ON252"):
        window = SIGNAL_LOOKBACK[name]
        out[name] = on.rolling(window, min_periods=SIGNAL_MIN_OBS[name]).mean()
    id_past = id_.shift(1).rolling(21, min_periods=ID_MIN_OBS).mean()
    out["TOW21"] = out["ON21"] - id_past
    out["ID21"] = id_past  # diagnostic (b) only
    return out


def next_night_return(open_w: pd.DataFrame, close_w: pd.DataFrame) -> pd.DataFrame:
    """r_t = open_{t+1} / close_t - 1: bought at the close of t, sold at the next open."""
    return open_w.shift(-1) / close_w - 1.0


def next_day_intraday_return(open_w: pd.DataFrame, close_w: pd.DataFrame) -> pd.DataFrame:
    """close_{t+1} / open_{t+1} - 1 (diagnostic (a))."""
    return close_w.shift(-1) / open_w.shift(-1) - 1.0


def leg_size(n_valid: int, frac: float = DECILE_FRAC, min_leg: int = MIN_LEG) -> int:
    k = int(math.floor(frac * n_valid))
    return k if k >= min_leg else 0


def decile_long_short(signal: np.ndarray, ret: np.ndarray) -> dict[str, float] | None:
    """Equal-weight top-decile long minus bottom-decile short on one night.

    ``signal`` and ``ret`` must already be restricted to valid names, in stable order.
    Returns ``None`` when the night has fewer than MIN_LEG names per leg.
    """
    k = leg_size(len(signal))
    if k == 0:
        return None
    order = np.argsort(signal, kind="stable")
    short_idx = order[:k]
    long_idx = order[-k:]
    long_mean = float(np.mean(ret[long_idx]))
    short_mean = float(np.mean(ret[short_idx]))
    return {
        "ls": long_mean - short_mean,
        "long": long_mean,
        "short": short_mean,
        "k": k,
        "long_idx": long_idx,
        "short_idx": short_idx,
    }


def days_to_next_session(dates: pd.DatetimeIndex) -> np.ndarray:
    """Calendar days to the next session: a Friday night counts 3 days of borrow."""
    d = pd.DatetimeIndex(dates)
    nxt = d[1:]
    days = np.asarray((nxt - d[:-1]).days, dtype="float64")
    return np.append(days, np.nan)


def borrow_rate_from_dv21(dv21: np.ndarray) -> np.ndarray:
    """T-32 tiered annual borrow rate by dv21 (5% / 2% / 0.5%; names below $5M pay 5%)."""
    rate = np.full(dv21.shape, BORROW_DEFAULT_RATE, dtype="float64")
    for lo, hi, r in BORROW_TIERS.values():
        rate[(dv21 >= lo) & (dv21 < hi)] = r
    rate[~np.isfinite(dv21)] = np.nan
    return rate


def borrow_cost_bp(rate: float, days: float) -> float:
    """Borrow charged for one short night: annual rate * calendar days / 360, in bp."""
    return float(rate * days / BORROW_DAYCOUNT * 1e4)


def tier_from_stats(mean_bp: float, t_nw: float, beat: float, t_min: float) -> str:
    """Mechanical tier from hypotheses.md: closed / marginal / pass.

    closed if m < 8 bp or t_nw < t_min or beat < 0.90; pass if additionally m >= 16 bp;
    otherwise (8 <= m < 16 with t and beat passing) marginal. Non-finite inputs close.
    """
    if not (math.isfinite(mean_bp) and math.isfinite(t_nw) and math.isfinite(beat)):
        return "closed"
    if mean_bp < ROUND_TRIP_1X_BP or t_nw < t_min or beat < BEAT_MIN:
        return "closed"
    if mean_bp >= PASS_MEAN_BP:
        return "pass"
    return "marginal"


def stress_class_from_stats(mean_bp: float, t_nw: float) -> str:
    """Stress-period class: robust if m >= 8 bp and t >= 2 in 2016-05..2023-08, else recent_only."""
    if math.isfinite(mean_bp) and math.isfinite(t_nw) and mean_bp >= 8.0 and t_nw >= 2.0:
        return "robust"
    return "recent_only"


def window_mask(index: pd.DatetimeIndex, window: tuple[str, str]) -> np.ndarray:
    return (index >= pd.Timestamp(window[0])) & (index <= pd.Timestamp(window[1]))


def cell_ids() -> list[str]:
    return [f"{s}_{p}_{f}" for s in SIGNALS for p in POOL_SIZES for f in FORMS]


# ==========================================================================
# stage panel
# ==========================================================================


def _load_metadata() -> pd.DataFrame:
    meta = pd.read_parquet(
        ASSET_METADATA, columns=["symbol", "exchange", "is_probable_fund_or_etf"]
    )
    return meta.drop_duplicates("symbol")


def _bar_columns() -> list[str]:
    con = duckdb.connect()
    cols = con.execute(f"DESCRIBE SELECT * FROM read_parquet('{DAILY_GLOB}')").df()["column_name"]
    con.close()
    return [str(c) for c in cols]


CAND_PATH = CACHE_DIR / "candidates.json"


def find_candidate_symbols(excluded: pd.DataFrame) -> dict[str, Any]:
    """Symbols that ever rank in the dv21 top 2000 among non-fund, non-OTC names.

    Runs in its own process (see ``build_panel``) so DuckDB's allocator does not stay
    resident while the wide matrices are built.
    """
    ghost = ph.ghost_bar_sql_predicate(_bar_columns())
    ghost_clause = f"AND NOT {ghost}" if ghost else ""
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2;")
    tmp = CACHE_DIR / "duck_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET temp_directory='{tmp.as_posix()}';")
    con.register("excluded_symbols", excluded[["symbol"]])
    con.execute(
        f"""
        CREATE TEMP VIEW bars AS
        SELECT symbol, CAST(timezone('America/New_York', "timestamp") AS DATE) AS date,
               close, volume
        FROM read_parquet(['{DAILY_GLOB}', '{DELISTED_GLOB}'], union_by_name=true)
        WHERE open > 0 AND high > 0 AND low > 0 AND close > 0 {ghost_clause}
          AND symbol NOT IN (SELECT symbol FROM excluded_symbols)
        """
    )
    _log("DuckDB: dv21 window + daily top-2000 rank ...")
    cand = con.execute(
        f"""
        WITH w AS (
            SELECT symbol, date,
                   avg(close * volume) OVER win AS dv21, count(*) OVER win AS c
            FROM bars
            WINDOW win AS (PARTITION BY symbol ORDER BY date ROWS BETWEEN {DV_WINDOW} PRECEDING AND 1 PRECEDING)
        ), r AS (
            SELECT symbol, date, rank() OVER (PARTITION BY date ORDER BY dv21 DESC) AS rk
            FROM w WHERE c = {DV_WINDOW} AND dv21 IS NOT NULL
        )
        SELECT DISTINCT symbol FROM r WHERE rk <= {CANDIDATE_TOP_N}
        """
    ).df()["symbol"]
    delisted_syms = set(
        con.execute(f"SELECT DISTINCT symbol FROM read_parquet('{DELISTED_GLOB}')")
        .df()["symbol"]
        .tolist()
    )
    daily_syms = set(
        con.execute(f"SELECT DISTINCT symbol FROM read_parquet('{DAILY_GLOB}')").df()["symbol"]
    )
    dates = (
        con.execute(
            f"""SELECT DISTINCT CAST(timezone('America/New_York', "timestamp") AS DATE) AS date
            FROM read_parquet(['{DAILY_GLOB}', '{DELISTED_GLOB}'], union_by_name=true)
            ORDER BY date"""
        )
        .df()["date"]
        .astype(str)
        .tolist()
    )
    con.close()
    out = {
        "symbols": sorted(cand.tolist()),
        "n_symbols_daily_root": len(daily_syms),
        "n_symbols_delisted_root": len(delisted_syms),
        "delisted_only_symbols": sorted(delisted_syms - daily_syms),
        "all_symbols": sorted(delisted_syms | daily_syms),
        "dates": dates,
    }
    CAND_PATH.write_text(json.dumps(out), encoding="utf-8")
    return out


def load_wide_float32(symbols: list[str], dates: list[str]) -> dict[str, pd.DataFrame]:
    """Wide open/high/low/close/volume float32 matrices, filled year by year.

    The delisted root is written first and the live root second, so a (symbol, date) present
    in both keeps the live-root bar; overlapping cells are counted.
    """
    ghost = ph.ghost_bar_sql_predicate(_bar_columns())
    ghost_clause = f"AND NOT {ghost}" if ghost else ""
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    cols = pd.Index(symbols)
    shape = (len(idx), len(cols))
    arrays = {
        c: np.full(shape, np.nan, dtype="float32")
        for c in ("open", "high", "low", "close", "volume")
    }
    overlap = 0
    years = sorted({d[:4] for d in dates})
    for year in years:
        for root_glob, tag in (
            (str(ROOT / "data" / "sip-delisted" / "by_year" / year / "*.parquet"), "delisted"),
            (str(ROOT / "data" / "sip" / "daily" / year / "*.parquet"), "live"),
        ):
            if not list(Path(root_glob).parent.glob("*.parquet")):
                continue
            con = duckdb.connect()
            con.execute("SET memory_limit='1GB'; SET threads=2;")
            con.register("cand", pd.DataFrame({"symbol": symbols}))
            df = con.execute(
                f"""
                SELECT symbol, CAST(timezone('America/New_York', "timestamp") AS DATE) AS date,
                       open, high, low, close, volume
                FROM read_parquet('{root_glob}')
                WHERE open > 0 AND high > 0 AND low > 0 AND close > 0 {ghost_clause}
                  AND symbol IN (SELECT symbol FROM cand)
                """
            ).df()
            con.close()
            if df.empty:
                continue
            ri = idx.get_indexer(pd.DatetimeIndex(pd.to_datetime(df["date"])))
            ci = cols.get_indexer(df["symbol"])
            ok = (ri >= 0) & (ci >= 0)
            ri, ci = ri[ok], ci[ok]
            if tag == "live":
                overlap += int(np.isfinite(arrays["close"][ri, ci]).sum())
            for name, arr in arrays.items():
                arr[ri, ci] = df[name].to_numpy("float32")[ok]
            _log(f"loaded {year} {tag}: {len(df):,} rows")
            del df
    _log(f"cells present in both roots (live overwrote delisted): {overlap:,}")
    out = {name: pd.DataFrame(arr, index=idx, columns=cols) for name, arr in arrays.items()}
    out["_overlap"] = overlap  # type: ignore[assignment]
    return out


def rank_desc(values: pd.DataFrame) -> pd.DataFrame:
    return values.rank(axis=1, ascending=False, method="first")


def build_panel() -> None:
    import gc
    import subprocess

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    t_start = time.time()
    meta = _load_metadata()
    is_fund = meta["is_probable_fund_or_etf"].fillna(False).astype(bool)
    is_otc = meta["exchange"].astype(str).str.contains("OTC", na=False)
    _log(
        f"metadata: {len(meta):,} rows, fund/ETF {int(is_fund.sum()):,}, OTC {int(is_otc.sum()):,}"
    )

    if CAND_PATH.exists():
        _log(f"candidates checkpoint found: {CAND_PATH}")
    else:
        excluded = meta.loc[is_fund | is_otc, ["symbol"]]
        excl_path = CACHE_DIR / "excluded_symbols.parquet"
        excluded.to_parquet(excl_path, index=False)
        subprocess.run([sys.executable, str(Path(__file__).resolve()), "candidates"], check=True)
    info = json.loads(CAND_PATH.read_text(encoding="utf-8"))
    symbols = info["symbols"]
    _log(f"candidate symbols (ever dv21 top {CANDIDATE_TOP_N}): {len(symbols):,}")
    all_syms = pd.Series(info["all_symbols"])
    fund_excluded_in_data = int(all_syms.isin(meta.loc[is_fund, "symbol"]).sum())
    otc_excluded_in_data = int(all_syms.isin(meta.loc[is_otc & ~is_fund, "symbol"]).sum())
    delisted_only = set(info["delisted_only_symbols"])

    spy = _load_spy()
    wide = load_wide_float32(symbols, info["dates"])
    overlap = int(wide.pop("_overlap"))  # type: ignore[arg-type]
    open_w, high_w, low_w = wide["open"], wide["high"], wide["low"]
    close_w, vol_w = wide["close"], wide["volume"]
    del wide
    raw_valid_cells = int(close_w.notna().to_numpy().sum())

    _log("price_hygiene.sanitize_price_matrices (defaults, open passed)")
    close_s, open_s, report = ph.sanitize_price_matrices(close_w, open_w)
    assert open_s is not None
    masked = close_s.isna() & close_w.notna()
    high_s = high_w.mask(masked | open_s.isna())
    low_s = low_w.mask(masked | open_s.isna())
    vol_s = vol_w.mask(close_s.isna())
    del close_w, open_w, high_w, low_w, vol_w, masked
    close_s = close_s.astype("float32")
    open_s = open_s.astype("float32")
    gc.collect()
    hygiene = {
        "symbols_masked": int(report.symbols_masked),
        "symbols_masked_for_jump": int(report.symbols_masked_for_jump),
        "symbols_masked_for_gap": int(report.symbols_masked_for_gap),
        "price_cells_masked": int(report.price_cells_masked),
        "raw_valid_close_cells": raw_valid_cells,
    }
    _log(f"hygiene: {hygiene}")

    # split-like trigger filter on open_t / close_{t-1}
    prev_close = close_s.shift(1)
    gap_ratio = open_s / prev_close
    split_like = pd.DataFrame(
        t32.is_split_like_ratio(gap_ratio.to_numpy()),
        index=gap_ratio.index,
        columns=gap_ratio.columns,
    )
    split_filtered_rows = int(split_like.to_numpy().sum())
    _log(f"split-like open/close_prev rows filtered: {split_filtered_rows:,}")
    del gap_ratio
    split_next = split_like.shift(-1, fill_value=False)  # r_t uses the ratio at t+1

    # pools recomputed on the cleaned data
    dv21 = (close_s * vol_s).shift(1).rolling(DV_WINDOW, min_periods=DV_WINDOW).mean()
    del vol_s
    history = close_s.notna().shift(1, fill_value=False).cumsum()
    is_delisted_col = pd.Series(close_s.columns.isin(delisted_only), index=close_s.columns)
    base_ok = (prev_close >= MIN_CLOSE) & (history >= MIN_HISTORY) & dv21.notna()
    del history, prev_close
    pools: dict[str, pd.DataFrame] = {}
    rk = rank_desc(dv21)
    for name, n in POOL_SIZES.items():
        pools[name] = base_ok & (rk <= n)
    del rk
    dv21_surv = dv21.loc[:, ~is_delisted_col.to_numpy()]
    rk = rank_desc(dv21_surv).reindex(columns=close_s.columns)
    del dv21_surv
    for name, n in POOL_SIZES.items():
        pools[name + "_s"] = base_ok & (rk <= n)
    del rk, base_ok
    gc.collect()

    any_pool = pools["P1500"] | pools["P1500_s"]
    rows, cols = np.where(any_pool.to_numpy())
    del any_pool
    dates = close_s.index.to_numpy()[rows]
    syms = np.asarray(close_s.columns)[cols]

    def pick(m: pd.DataFrame) -> np.ndarray:
        return m.to_numpy()[rows, cols]

    panel = pd.DataFrame(
        {
            "date": dates,
            "symbol": pd.Categorical(syms),
            "delisted": np.asarray(is_delisted_col.to_numpy())[cols],
            "p1500": pick(pools["P1500"]),
            "p500": pick(pools["P500"]),
            "p1500_s": pick(pools["P1500_s"]),
            "p500_s": pick(pools["P500_s"]),
            "dv21": pick(dv21).astype("float32"),
        }
    )
    del pools, dv21
    gc.collect()

    # overnight / intraday returns, signals one block at a time
    on, id_ = overnight_intraday_returns(open_s, close_s)
    on = on.where(~split_like)
    sig = rolling_signals(on, id_)
    for name, col in (
        ("ON5", "on5"),
        ("ON21", "on21"),
        ("ON63", "on63"),
        ("ON252", "on252"),
        ("TOW21", "tow21"),
        ("ID21", "id21"),
    ):
        panel[col] = pick(sig[name]).astype("float32")
    del sig, on, id_
    gc.collect()
    r = next_night_return(open_s, close_s).where(~split_next)
    panel["r"] = pick(r).astype("float32")
    del r
    idn = next_day_intraday_return(open_s, close_s)
    panel["idn"] = pick(idn).astype("float32")
    del idn, open_s, split_like, split_next
    gc.collect()

    _log("AR spread per symbol")
    spread = pd.DataFrame(
        {
            s: ml30.spread_estimate_from_ohlc(close_s[s], high_s[s], low_s[s]).astype("float32")
            for s in close_s.columns
        },
        index=close_s.index,
    )
    panel["spread21"] = pick(spread).astype("float32")
    del spread, high_s, low_s
    _log("DTC (T-32 load_dtc) as a forward-filled wide matrix")
    dtc = t32.load_dtc()
    dtc = dtc[dtc["symbol"].isin(close_s.columns)].drop_duplicates(
        ["visible_date", "symbol"], keep="last"
    )
    dtc_w = dtc.pivot(index="visible_date", columns="symbol", values="dtc_cross_sectional_pct")
    cal = close_s.index
    dtc_w = dtc_w.reindex(dtc_w.index.union(cal)).ffill().reindex(cal)  # backward as-of
    dtc_w = dtc_w.reindex(columns=close_s.columns).astype("float32")
    dtc_pick = dtc_w.to_numpy()[rows, cols]
    del dtc, dtc_w, close_s
    gc.collect()

    # fill AR spread NaN with the night's pool median (documented convention)
    med = panel.groupby("date")["spread21"].transform("median")
    panel["spread_nan_filled"] = panel["spread21"].isna()
    panel["spread21"] = panel["spread21"].fillna(med).astype("float32")
    del med
    panel["borrow_rate"] = borrow_rate_from_dv21(panel["dv21"].to_numpy("float64")).astype(
        "float32"
    )

    assert panel["date"].is_monotonic_increasing
    panel["dtc_cross_sectional_pct"] = dtc_pick.astype("float32")
    del dtc_pick
    panel.to_parquet(PANEL_PATH, index=False)
    _log(f"panel written: {len(panel):,} rows -> {PANEL_PATH}")
    spy.to_parquet(SPY_PATH)

    # data report
    in_p = panel["p1500"].to_numpy()
    in_s = panel["p1500_s"].to_numpy()
    p1500_rows = panel.loc[in_p]
    meta_syms = set(meta["symbol"])
    pool_symbols_all = set(p1500_rows["symbol"].unique())
    pool_symbols_surv = set(panel.loc[in_s, "symbol"].unique())
    data = {
        "n_symbols_daily_root": info["n_symbols_daily_root"],
        "n_symbols_delisted_root": info["n_symbols_delisted_root"],
        "candidate_symbols_ever_top2000": len(symbols),
        "symbols_total": len(pool_symbols_all),
        "symbols_in_p1500_with_delisted": len(pool_symbols_all),
        "symbols_in_p1500_survivors_only": len(pool_symbols_surv),
        "delisted_symbols_in_p1500": len(pool_symbols_all & delisted_only),
        "delisted_share_in_pool": float(p1500_rows["delisted"].mean()),
        "delisted_share_of_pool_symbols": float(
            len(pool_symbols_all & delisted_only) / max(1, len(pool_symbols_all))
        ),
        "mean_daily_pool_size_p1500": float(p1500_rows.groupby("date").size().mean()),
        "mean_daily_pool_size_p1500_survivors_only": float(
            panel.loc[in_s].groupby("date").size().mean()
        ),
        "fund_excluded": fund_excluded_in_data,
        "otc_excluded": otc_excluded_in_data,
        "missing_metadata": int(len(pool_symbols_all - meta_syms)),
        "missing_metadata_candidates": int(len(set(symbols) - meta_syms)),
        "split_filtered_rows": split_filtered_rows,
        "cells_in_both_roots": overlap,
        "hygiene": hygiene,
        "panel_rows": int(len(panel)),
        "panel_date_min": str(panel["date"].min().date()),
        "panel_date_max": str(panel["date"].max().date()),
        "spread_nan_filled_share": float(panel["spread_nan_filled"].mean()),
        "panel_seconds": round(time.time() - t_start, 1),
    }
    META_PATH.write_text(json.dumps(_clean(data), indent=2) + "\n", encoding="utf-8")
    _log(f"panel meta: {json.dumps(_clean(data))[:600]}")


def _load_spy() -> pd.DataFrame:
    con = duckdb.connect()
    df = con.execute(
        f"""
        SELECT CAST(timezone('America/New_York', "timestamp") AS DATE) AS date, open, close
        FROM read_parquet('{DAILY_GLOB}') WHERE symbol = 'SPY' AND open > 0 AND close > 0
        ORDER BY date
        """
    ).df()
    con.close()
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates("date").set_index("date")
    out = pd.DataFrame({"r": df["open"].shift(-1) / df["close"] - 1.0}, index=df.index)
    return out


# ==========================================================================
# stage screen
# ==========================================================================

SIG_COL = {"ON5": "on5", "ON21": "on21", "ON63": "on63", "ON252": "on252", "TOW21": "tow21"}
SERIES_COLS = [
    "gross",
    "long",
    "short",
    "pool_ew",
    "n_valid",
    "k",
    "cont1_bp",
    "cont2_bp",
    "borrow_bp",
    "idn_ls",
    "gross_etb",
    "borrow_etb_bp",
]


def run_cell_series(
    panel: pd.DataFrame,
    pool_col: str,
    signal_col: str,
    form: str,
    dates_all: pd.DatetimeIndex,
    days_next: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
    keep_valid_r: dict[int, np.ndarray] | None = None,
) -> pd.DataFrame:
    """Nightly series for one (signal, pool, form) cell. Rows are dates of ``dates_all``."""
    pool = panel[pool_col].to_numpy()
    sig = panel[signal_col].to_numpy("float64")
    ret = panel["r"].to_numpy("float64")
    idn = panel["idn"].to_numpy("float64")
    spr = panel["spread21"].to_numpy("float64") * 1e4
    rate = panel["borrow_rate"].to_numpy("float64")
    dtc = panel["dtc_cross_sectional_pct"].to_numpy("float64")
    n_dates = len(dates_all)
    out = {c: np.full(n_dates, np.nan) for c in SERIES_COLS}
    for i in range(n_dates):
        s, e = starts[i], ends[i]
        m = pool[s:e] & np.isfinite(sig[s:e]) & np.isfinite(ret[s:e])
        if m.sum() < 40:
            continue
        idx = np.nonzero(m)[0] + s
        x, rr = sig[idx], ret[idx]
        out["pool_ew"][i] = rr.mean()
        out["n_valid"][i] = len(idx)
        if keep_valid_r is not None:
            keep_valid_r[i] = rr
        order = np.argsort(x, kind="stable")
        if form == "LS":
            k = leg_size(len(x))
            if k == 0:
                continue
            li, si = idx[order[-k:]], idx[order[:k]]
            out["k"][i] = k
            lm, sm = ret[li].mean(), ret[si].mean()
            out["long"][i], out["short"][i], out["gross"][i] = lm, sm, lm - sm
            c1 = 0.5 * spr[idx] + AUCTION_SIDE_BP
            c2 = 1.0 * spr[idx] + 2 * AUCTION_SIDE_BP
            lj, sj = order[-k:], order[:k]
            out["cont1_bp"][i] = 2.0 * (c1[lj].mean() + c1[sj].mean())
            out["cont2_bp"][i] = 2.0 * (c2[lj].mean() + c2[sj].mean())
            d = days_next[i]
            out["borrow_bp"][i] = float(np.nanmean(rate[si])) * d / BORROW_DAYCOUNT * 1e4
            # (a) next-day intraday of the same LS book
            il, is_ = idn[li], idn[si]
            if np.isfinite(il).any() and np.isfinite(is_).any():
                out["idn_ls"][i] = np.nanmean(il) - np.nanmean(is_)
            # (e) easy-to-borrow proxy: shorts only among names with DTC quantile < 0.90
            etb = np.isfinite(dtc[idx]) & (dtc[idx] < DTC_ETB_MAX)
            if etb.sum() >= k:
                oe = np.argsort(np.where(etb, x, np.inf), kind="stable")[:k]
                se = idx[oe]
                out["gross_etb"][i] = lm - ret[se].mean()
                out["borrow_etb_bp"][i] = float(np.nanmean(rate[se])) * d / BORROW_DAYCOUNT * 1e4
        else:  # LO top 20
            if len(x) < LO_N:
                continue
            li = idx[order[-LO_N:]]
            out["k"][i] = LO_N
            lm = ret[li].mean()
            out["long"][i], out["gross"][i] = lm, lm
            c1 = 0.5 * spr[li] + AUCTION_SIDE_BP
            c2 = 1.0 * spr[li] + 2 * AUCTION_SIDE_BP
            out["cont1_bp"][i] = 2.0 * c1.mean()
            out["cont2_bp"][i] = 2.0 * c2.mean()
    df = pd.DataFrame(out, index=dates_all)
    df["excess"] = df["long"] - df["pool_ew"] if form == "LO" else np.nan
    return df


def net_series(df: pd.DataFrame, form: str) -> dict[str, pd.Series]:
    """Six cost contracts. LS: 4 auction sides (two legs); LO: 2 sides. Borrow deducted on shorts."""
    legs = 2 if form == "LS" else 1
    borrow = df["borrow_bp"].fillna(0.0) / 1e4 if form == "LS" else 0.0
    out = {}
    out["auction_1x"] = df["gross"] - legs * 2 * AUCTION_SIDE_BP / 1e4 - borrow
    out["auction_2x"] = df["gross"] - legs * 2 * 2 * AUCTION_SIDE_BP / 1e4 - borrow
    out["continuous_1x"] = df["gross"] - df["cont1_bp"] / 1e4 - borrow
    out["continuous_2x"] = df["gross"] - df["cont2_bp"] / 1e4 - borrow
    out["frozen_10"] = df["gross"] - legs * 2 * 10.0 / 1e4 - borrow
    out["frozen_20"] = df["gross"] - legs * 2 * 20.0 / 1e4 - borrow
    return out


def placebo_series(valid_r: dict[int, np.ndarray], n_dates: int, seed: int) -> np.ndarray:
    """Same-pool random long/short: same k as the real book, drawn without replacement."""
    rng = np.random.default_rng(seed)
    out = np.full(n_dates, np.nan)
    for i in range(n_dates):
        rr = valid_r.get(i)
        if rr is None:
            continue
        k = leg_size(len(rr))
        if k == 0:
            continue
        perm = rng.permutation(len(rr))
        out[i] = rr[perm[:k]].mean() - rr[perm[k : 2 * k]].mean()
    return out


def window_block(
    df: pd.DataFrame,
    form: str,
    placebo_means: dict[str, np.ndarray] | None,
) -> dict[str, Any]:
    idx = df.index
    block: dict[str, Any] = {}
    nets = net_series(df, form)
    for wname, win in WINDOWS.items():
        m = window_mask(idx, win)
        g = df["gross"].to_numpy()[m]
        stats = series_stats(g)
        entry: dict[str, Any] = {"gross": stats}
        if form == "LO":
            entry["excess"] = series_stats(df["excess"].to_numpy()[m])
        entry["pool_ew_mean_bp"] = (
            float(np.nanmean(df["pool_ew"].to_numpy()[m]) * 1e4) if m.any() else float("nan")
        )
        entry["nets"] = {c: net_stats(nets[c].to_numpy()[m]) for c in COST_CONTRACTS}
        if form == "LS":
            entry["borrow_mean_bp"] = (
                float(np.nanmean(df["borrow_bp"].to_numpy()[m])) if m.any() else float("nan")
            )
        if placebo_means is not None:
            pm = placebo_means[wname]
            real = stats["mean_bp"] / 1e4
            ok = np.isfinite(pm)
            entry["placebo_beat"] = (
                float(np.mean(real > pm[ok])) if ok.any() and np.isfinite(real) else float("nan")
            )
            entry["placebo_mean_bp"] = float(np.nanmean(pm) * 1e4) if ok.any() else float("nan")
        block[wname] = entry
    return block


def by_year_table(df: pd.DataFrame) -> dict[str, Any]:
    out = {}
    for year, g in df.groupby(df.index.year):
        s = series_stats(g["gross"].to_numpy())
        out[str(year)] = {"mean_bp": s["mean_bp"], "t_nw5": s["t_nw5"], "n": s["n"]}
    return out


def screen() -> None:
    t0 = time.time()
    if not PREBACKTEST_STAMP.exists():
        raise SystemExit("prebacktest-validated-at.txt missing: run the pre-backtest gate first")
    meta = json.loads(META_PATH.read_text(encoding="utf-8"))
    panel = pd.read_parquet(PANEL_PATH)
    panel = panel.sort_values(["date", "symbol"], kind="stable").reset_index(drop=True)
    dates_all = pd.DatetimeIndex(np.sort(panel["date"].unique()))
    days_next = days_to_next_session(dates_all)
    codes = panel["date"].searchsorted(dates_all, side="left")
    starts = np.asarray(codes)
    ends = np.append(starts[1:], len(panel))
    _log(f"panel {len(panel):,} rows, {len(dates_all)} dates")
    pools = {"P1500": "p1500", "P500": "p500"}

    cells: dict[str, Any] = {}
    series: dict[str, pd.DataFrame] = {}
    valid_r_store: dict[str, dict[int, np.ndarray]] = {}
    by_year: dict[str, Any] = {}
    for sig in SIGNALS:
        for pool_name, pool_col in pools.items():
            for form in FORMS:
                cid = f"{sig}_{pool_name}_{form}"
                store: dict[int, np.ndarray] = {}
                df = run_cell_series(
                    panel,
                    pool_col,
                    SIG_COL[sig],
                    form,
                    dates_all,
                    days_next,
                    starts,
                    ends,
                    keep_valid_r=store,
                )
                series[cid] = df
                if form == "LS":
                    valid_r_store[cid] = store
                _log(f"series {cid}: n_nights {int(df['gross'].notna().sum())}")

    _log("placebos (100 seeds, LS cells)")
    placebo_means: dict[str, dict[str, np.ndarray]] = {}
    for cid, store in valid_r_store.items():
        wm = {w: window_mask(dates_all, win) for w, win in WINDOWS.items()}
        arr = {w: np.full(PLACEBO_SEEDS, np.nan) for w in WINDOWS}
        for seed in range(PLACEBO_SEEDS):
            ps = placebo_series(store, len(dates_all), seed)
            for w, m in wm.items():
                v = ps[m]
                v = v[np.isfinite(v)]
                if len(v):
                    arr[w][seed] = v.mean()
        placebo_means[cid] = arr
        _log(f"placebo {cid} done")

    for cid, df in series.items():
        form = cid.rsplit("_", 1)[1]
        cells[cid] = window_block(df, form, placebo_means.get(cid))
        by_year[cid] = by_year_table(df)

    # decision and secondary cell
    def cell_summary(cid: str, t_min: float) -> dict[str, Any]:
        main = cells[cid]["main"]
        stress = cells[cid]["stress"]
        g, beat = main["gross"], main["placebo_beat"]
        s_stats = stress["gross"]
        return {
            "id": cid,
            "main_mean_bp": g["mean_bp"],
            "t": g["t"],
            "t_nw5": g["t_nw5"],
            "n": g["n"],
            "placebo_beat": beat,
            "t_min": t_min,
            "tier": tier_from_stats(g["mean_bp"], g["t_nw5"], beat, t_min),
            "stress_mean_bp": s_stats["mean_bp"],
            "stress_t_nw5": s_stats["t_nw5"],
            "stress_class": stress_class_from_stats(s_stats["mean_bp"], s_stats["t_nw5"]),
            "auction_2x_net_mean_bp": main["nets"]["auction_2x"]["mean_bp"],
        }

    decision = cell_summary(DECISION_CELL, DECISION_T_MIN)
    secondary = cell_summary(SECONDARY_CELL, SECONDARY_T_MIN)
    secondary["enabled_by_rule"] = decision["tier"] != "pass"
    secondary["rule_note"] = (
        "hypotheses.md: the second cell is used when the decision cell does not pass; lead reads which tiers count."
    )

    diagnostics = build_diagnostics(panel, series, cells, dates_all, days_next, starts, ends)

    results = {
        "iteration_id": ITERATION_ID,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prebacktest_validated_at": PREBACKTEST_STAMP.read_text(encoding="utf-8").strip(),
        "design": "reports/research/iterations/t20260929_35_overnight_persistence/hypotheses.md",
        "windows": WINDOWS,
        "data": meta,
        "decision_cell": decision,
        "secondary_cell": secondary,
        "cells": cells,
        "diagnostics": diagnostics,
        "by_year": by_year,
        "screen_seconds": round(time.time() - t0, 1),
    }
    RESULTS_PATH.write_text(json.dumps(_clean(results), indent=1) + "\n", encoding="utf-8")
    _log(f"results.json written ({RESULTS_PATH})")
    write_report(results)


def build_diagnostics(
    panel: pd.DataFrame,
    series: dict[str, pd.DataFrame],
    cells: dict[str, Any],
    dates_all: pd.DatetimeIndex,
    days_next: np.ndarray,
    starts: np.ndarray,
    ends: np.ndarray,
) -> dict[str, Any]:
    diag: dict[str, Any] = {}
    ls_cells = [c for c in series if c.endswith("_LS")]

    # (a) next-day intraday of the same LS book; (e) ETB-proxy shorts; (d) legs vs pool EW
    a, d, e, c = {}, {}, {}, {}
    for cid in ls_cells:
        df = series[cid]
        a[cid] = {
            w: series_stats(df["idn_ls"].to_numpy()[window_mask(dates_all, win)])
            for w, win in WINDOWS.items()
        }
        e[cid] = {
            w: {
                **series_stats(df["gross_etb"].to_numpy()[window_mask(dates_all, win)]),
                "borrow_etb_mean_bp": float(
                    np.nanmean(df["borrow_etb_bp"].to_numpy()[window_mask(dates_all, win)])
                )
                if np.isfinite(df["borrow_etb_bp"].to_numpy()[window_mask(dates_all, win)]).any()
                else float("nan"),
            }
            for w, win in WINDOWS.items()
        }
        long_ex = df["long"] - df["pool_ew"]
        short_ex = df["short"] - df["pool_ew"]
        d[cid] = {
            w: {
                "long_minus_pool": series_stats(long_ex.to_numpy()[window_mask(dates_all, win)]),
                "short_minus_pool": series_stats(short_ex.to_numpy()[window_mask(dates_all, win)]),
            }
            for w, win in WINDOWS.items()
        }
        # (c) Friday nights vs other nights
        fri = np.asarray(dates_all.dayofweek == 4)
        c[cid] = {}
        for w, win in WINDOWS.items():
            m = window_mask(dates_all, win)
            g = df["gross"].to_numpy()
            c[cid][w] = {
                "friday_nights": series_stats(g[m & fri]),
                "other_nights": series_stats(g[m & ~fri]),
            }
    diag["a_next_day_intraday_of_same_ls"] = a
    diag["c_friday_vs_other_nights"] = c
    diag["d_legs_vs_pool_equal_weight"] = d
    diag["e_etb_proxy_short_leg"] = e

    # (b) LS sorted on past 21-day intraday, next overnight
    b: dict[str, Any] = {}
    for pool_name, pool_col in (("P1500", "p1500"), ("P500", "p500")):
        df = run_cell_series(panel, pool_col, "id21", "LS", dates_all, days_next, starts, ends)
        b[pool_name] = {
            w: series_stats(df["gross"].to_numpy()[window_mask(dates_all, win)])
            for w, win in WINDOWS.items()
        }
    diag["b_past_intraday_ls_next_overnight"] = b

    # (f) SPY close -> next open
    spy = pd.read_parquet(SPY_PATH)["r"].reindex(dates_all)
    diag["f_spy_overnight"] = {
        w: series_stats(spy.to_numpy()[window_mask(dates_all, win)]) for w, win in WINDOWS.items()
    }

    # survivorship: decision and second cell with survivors-only pools
    surv: dict[str, Any] = {}
    for cid, sig, pool_col in (
        (DECISION_CELL, "ON21", "p1500_s"),
        (SECONDARY_CELL, "ON5", "p1500_s"),
    ):
        df = run_cell_series(
            panel, pool_col, SIG_COL[sig], "LS", dates_all, days_next, starts, ends
        )
        surv[cid + "_survivors_only"] = {
            w: series_stats(df["gross"].to_numpy()[window_mask(dates_all, win)])
            for w, win in WINDOWS.items()
        }
    diag["survivorship_pool_without_delisted"] = surv
    return diag


def _fmt(x: Any, nd: int = 2) -> str:
    if x is None:
        return "n/a"
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return str(x)
    return "n/a" if not math.isfinite(xf) else f"{xf:.{nd}f}"


def write_report(res: dict[str, Any]) -> None:
    dc, sc = res["decision_cell"], res["secondary_cell"]
    cells = res["cells"]
    diag = res["diagnostics"]
    lines = [
        f"# {ITERATION_ID} report",
        "",
        f"Generated {res['generated_at']} from `results.json` (pre-backtest gate stamp {res['prebacktest_validated_at']}). Design frozen in `hypotheses.md`. No conclusion is drawn here; tiers are computed mechanically.",
        "",
        "## Decision and pre-specified second cell (main window 2024-01-08 to 2026-09-29)",
        "",
        "| cell | mean bp/night | t | t_nw5 | n | placebo beat | t_min | tier | stress mean bp | stress t_nw5 | stress class | auction 2x net bp |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in (dc, sc):
        lines.append(
            f"| {c['id']} | {_fmt(c['main_mean_bp'])} | {_fmt(c['t'])} | {_fmt(c['t_nw5'])} | {c['n']} | {_fmt(c['placebo_beat'])} | {c['t_min']} | {c['tier']} | {_fmt(c['stress_mean_bp'])} | {_fmt(c['stress_t_nw5'])} | {c['stress_class']} | {_fmt(c['auction_2x_net_mean_bp'])} |"
        )
    lines += [
        "",
        f"Second cell enabled by rule (decision tier != pass): {sc['enabled_by_rule']}.",
        "",
    ]

    lines += [
        "## All 20 candidates, main window, gross (LS: long minus short decile; LO: top-20 absolute)",
        "",
        "| cell | mean bp | t | t_nw5 | Sharpe | n | placebo beat | auction 1x net | auction 2x net | cont 1x net | cont 2x net | frozen 10 net | frozen 20 net | LO excess bp |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for cid in cell_ids():
        w = cells[cid]["main"]
        g = w["gross"]
        nets = w["nets"]
        ex = _fmt(w["excess"]["mean_bp"]) if "excess" in w else ""
        lines.append(
            f"| {cid} | {_fmt(g['mean_bp'])} | {_fmt(g['t'])} | {_fmt(g['t_nw5'])} | {_fmt(g['sharpe'])} | {g['n']} | {_fmt(w.get('placebo_beat'))} | "
            + " | ".join(_fmt(nets[k]["mean_bp"]) for k in COST_CONTRACTS)
            + f" | {ex} |"
        )

    lines += [
        "",
        "## Windows for the decision and second cells (gross mean bp / t_nw5 / n)",
        "",
        "| cell | " + " | ".join(WINDOWS) + " |",
        "|---|" + "---|" * len(WINDOWS),
    ]
    for cid in (DECISION_CELL, SECONDARY_CELL):
        lines.append(
            f"| {cid} | "
            + " | ".join(
                f"{_fmt(cells[cid][w]['gross']['mean_bp'])} / {_fmt(cells[cid][w]['gross']['t_nw5'])} / {cells[cid][w]['gross']['n']}"
                for w in WINDOWS
            )
            + " |"
        )

    lines += ["", "## Diagnostics (not in the decision), main window", ""]
    for cid in (DECISION_CELL, SECONDARY_CELL):
        a = diag["a_next_day_intraday_of_same_ls"][cid]["main"]
        d = diag["d_legs_vs_pool_equal_weight"][cid]["main"]
        e = diag["e_etb_proxy_short_leg"][cid]["main"]
        c = diag["c_friday_vs_other_nights"][cid]["main"]
        lines += [
            f"- {cid} (a) next-day intraday of same LS: {_fmt(a['mean_bp'])} bp, t_nw5 {_fmt(a['t_nw5'])}, n {a['n']}",
            f"- {cid} (c) Friday nights {_fmt(c['friday_nights']['mean_bp'])} bp (n {c['friday_nights']['n']}), other nights {_fmt(c['other_nights']['mean_bp'])} bp (n {c['other_nights']['n']})",
            f"- {cid} (d) long minus pool {_fmt(d['long_minus_pool']['mean_bp'])} bp, short minus pool {_fmt(d['short_minus_pool']['mean_bp'])} bp",
            f"- {cid} (e) ETB-proxy short leg LS gross {_fmt(e['mean_bp'])} bp, t_nw5 {_fmt(e['t_nw5'])}, n {e['n']}",
        ]
    for pool_name, v in diag["b_past_intraday_ls_next_overnight"].items():
        lines.append(
            f"- (b) {pool_name} LS on past-21d intraday, next overnight: {_fmt(v['main']['mean_bp'])} bp, t_nw5 {_fmt(v['main']['t_nw5'])}, n {v['main']['n']}"
        )
    f = diag["f_spy_overnight"]["main"]
    lines.append(
        f"- (f) SPY close to next open: {_fmt(f['mean_bp'])} bp, t_nw5 {_fmt(f['t_nw5'])}, n {f['n']}"
    )
    for k, v in diag["survivorship_pool_without_delisted"].items():
        lines.append(
            f"- survivorship {k}: main {_fmt(v['main']['mean_bp'])} bp, t_nw5 {_fmt(v['main']['t_nw5'])}"
        )

    dat = res["data"]
    lines += [
        "",
        "## Data",
        "",
        "- "
        + "; ".join(
            f"{k}: {_fmt(dat[k], 4) if isinstance(dat[k], float) else dat[k]}"
            for k in (
                "symbols_total",
                "symbols_in_p1500_survivors_only",
                "delisted_symbols_in_p1500",
                "delisted_share_in_pool",
                "fund_excluded",
                "otc_excluded",
                "missing_metadata",
                "split_filtered_rows",
            )
        ),
        "",
        "Conventions and known biases: see the module docstring of `scripts/run_t20260929_35_overnight_persistence.py` and `hypotheses.md` (opening-price basis, earnings nights, survivorship).",
        "",
    ]
    lines += _report_extra_sections(res)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _report_extra_sections(res: dict[str, Any]) -> list[str]:
    """By-year gross means, the LO decision-cell counterpart and the fixed caveats."""
    cells, by_year = res["cells"], res["by_year"]
    years = sorted({y for v in by_year.values() for y in v})
    out = [
        "## Gross mean bp/night by calendar year (t_nw5 in brackets)",
        "",
        "| cell | " + " | ".join(years) + " |",
        "|---|" + "---|" * len(years),
    ]
    for cid in cell_ids():
        row = []
        for y in years:
            v = by_year[cid].get(y)
            row.append("" if v is None else f"{_fmt(v['mean_bp'], 1)} ({_fmt(v['t_nw5'], 1)})")
        out.append(f"| {cid} | " + " | ".join(row) + " |")
    lo = cells["ON21_P1500_LO"]["main"]
    out += [
        "",
        "## Long-only counterpart of the decision cell (ON21_P1500_LO, main window)",
        "",
        f"- absolute nightly mean {_fmt(lo['gross']['mean_bp'])} bp (t_nw5 {_fmt(lo['gross']['t_nw5'])}), excess over pool equal weight {_fmt(lo['excess']['mean_bp'])} bp (t_nw5 {_fmt(lo['excess']['t_nw5'])}), pool equal-weight night {_fmt(lo['pool_ew_mean_bp'])} bp.",
        "",
        "## Conventions, caveats and what this file does not say",
        "",
        "- Tier and stress class are the mechanical output of `tier_from_stats` and `stress_class_from_stats` (thresholds from hypotheses.md); the verdict is for the lead round. The second cell `enabled_by_rule` flag only records that the decision tier is not `pass`.",
        "- Placebo beat = fraction of 100 same-pool random long/short books (seeds 0..99, same k per night) whose window mean is below the real mean. The random books are market neutral by construction and have a much smaller nightly variance than the real decile book, so the beat fraction can be 1.00 for a small mean.",
        "- Costs: LS auction cost is 4 sides x 2 bp per night (1x) and 4 x 4 bp (2x); the borrow term (T-32 tiers, calendar days / 360, Friday nights 3 days) is deducted in every net column. The AR spread in the continuous columns is the repo estimator (median 38 bp over the P1500 main window, 61 bp in the top ON21 decile), which is known to overstate liquid-stock spreads; those columns are for the paper-account approximation only.",
        "- Not measured: official opening/closing auction prices (daily-bar open vs official open tail in high-overnight-volatility names), earnings nights (kept, diagnostic only), fill reliability of `cls` and `opg` on the paper account. Nights whose next-session open is missing (delisting or halt) have no return and are dropped, which is a residual survivorship bias.",
        "- Pool rank is taken on dv21 first and the $5 / 63-session filters are applied afterwards, so a night's pool can hold fewer than 1500 names (mean 1467). Decile leg size is floor(0.10 x valid names). Diagnostic (b) sorts on mean(ID_{t-21..t-1}).",
        "",
    ]
    return out


def regenerate_report() -> None:
    write_report(json.loads(RESULTS_PATH.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("panel", help="build cache/panel.parquet")
    sub.add_parser("candidates", help=argparse.SUPPRESS)
    sub.add_parser("report", help="rewrite report.md from results.json")
    sub.add_parser("screen", help="run the 20-cell screen and write results.json / report.md")
    args = parser.parse_args(argv)
    if args.stage == "candidates":
        excluded = pd.read_parquet(CACHE_DIR / "excluded_symbols.parquet")
        find_candidate_symbols(excluded)
    elif args.stage == "report":
        regenerate_report()
    elif args.stage == "panel":
        build_panel()
    else:
        screen()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
