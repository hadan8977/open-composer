#!/usr/bin/env python3
# ruff: noqa: E501, E741
"""P1 stage 0 (T-20261005-01): fast-signal decay curves, trading speed vs net Sharpe, composites.

Contract: reports/research/iterations/t20261005_p1_s0_decay/hypotheses.md (all definitions).
Brief:    reports/research/control/briefs/T-20261005-01.md (mechanics).

Stages (each skips itself when its marker exists unless --force; ``all`` = in order):

``build``       dense price / panel grids, signal-store rows, seven new signals, the stress-window
                signs of ON5 and ID5 (written to ``signs.json`` before anything recent is touched).
``identity``    the new engine in the regimes convention against ``signal_ls_daily.parquet``.
``measure``     daily IC for lags 1..22 (+ overnight / intraday), persistence, and the three
                walk-forward / equal-weight composites with their own IC.
``speed``       trading-speed curves (7 speeds x MOC, MOO variant) for every object.
``composites``  placebo (20 seeds), blend with M0, DSR, for the three composites.
``report``      results.json, report.md, trial-ledger.json, mechanical status.

Measurement only: the script states numbers, never a verdict.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from scipy.optimize import curve_fit
from scipy.special import ndtri
from scipy.stats import norm

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import borrow, costs, evaluate  # noqa: E402
from open_composer.research.equity_book import signals as sg  # noqa: E402
from open_composer.research.equity_book.book_v12 import (  # noqa: E402
    restrict_shorts,
    target_weights,
)

ITER_ID = "t20261005_p1_s0_decay"
ITER_DIR = ROOT / "reports/research/iterations" / ITER_ID
OBJ_B = ["REV5", "IREV5", "RREV5", "RREV21", "ON5", "ID5", "VSHK"]
OBJ_C = ["FC_EW", "FC_WF252", "FC_WF63"]
BUCKETS = ("L12", "L1", "L2", "L3")
LAGS = 22
NTGT = LAGS + 2  # lags 1..22, overnight 1, intraday 1
PERS_LAGS = (1, 5, 21)
KAPPAS = (1.0, 0.5, 0.25, 0.1, 0.05)
M0_KAPPA = 0.2
MISSING_HALF_SPREAD_BP = 40.0


@dataclass
class Cfg:
    data: Path = ROOT / "data/research/equity_book"
    daily_broad: Path = ROOT / "data/features/daily_broad"
    regimes_ref: Path = ROOT / "data/research/equity_book/regimes/signal_ls_daily.parquet"
    iter_dir: Path = ITER_DIR
    cache: Path = ITER_DIR / "cache"
    cal_start: str = "2016-01-01"
    start: str = "2017-10-02"
    end: str = "2026-09-15"
    last_data: str = "2026-09-17"
    windows: dict = field(
        default_factory=lambda: {
            "recent": ("2024-01-08", "2026-09-15"),
            "stress": ("2017-10-02", "2023-08-31"),
            "owner_B": ("2026-07-01", "2026-09-15"),
        }
    )
    sign_window: tuple = ("2017-10-02", "2023-08-31")
    cut: tuple = (500, 1000, 3000)
    min_names: int = 50
    expected_lib: int = 53
    reb_periods: tuple = (5, 21)
    n_seeds: int = 20
    wf: dict = field(default_factory=lambda: {"FC_WF252": (252, 200), "FC_WF63": (63, 50)})
    identity_cols: tuple = ("m0_composite", "rev_21_ind", "a101_alpha016")
    identity_tol: float = 1e-9
    procs: int = 4
    force: bool = False
    schema_year: int = 2026
    dsr_window: tuple = ("2024-01-08", "2026-09-15")
    dsr_trials: tuple = (21, 193)
    blend_vol_window: int = 63


# ------------------------------------------------------------------------------ utilities


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def log(msg: str) -> None:
    print(f"[{now_utc()}] {msg}", flush=True)


def event(cfg: Cfg, name: str, **kw) -> None:
    cfg.cache.mkdir(parents=True, exist_ok=True)
    with open(cfg.cache / "events.jsonl", "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"event": name, "utc": now_utc(), **kw}) + "\n")


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, indent=1, default=_jdefault), encoding="utf-8")
    tmp.replace(path)


def _jdefault(o):
    if isinstance(o, (np.floating,)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return [None if (isinstance(v, float) and not math.isfinite(v)) else v for v in o.tolist()]
    if isinstance(o, (pd.Timestamp, datetime)):
        return str(o)
    raise TypeError(type(o))


def clean(o):
    """Replace non-finite floats by None recursively (strict JSON)."""
    if isinstance(o, dict):
        return {str(k): clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.ndarray):
        return clean(o.tolist())
    if isinstance(o, (float, np.floating)):
        return float(o) if math.isfinite(o) else None
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def read_dated(path: Path, columns: list[str], last: str) -> pd.DataFrame:
    """Read ``columns`` of a parquet file, never loading rows after ``last``."""
    ty = pq.read_schema(path).field("trade_date").type
    expr = pc.field("trade_date") <= pa.scalar(pd.Timestamp(last).to_pydatetime(), type=ty)
    df = pq.read_table(path, columns=columns, filters=expr).to_pandas()
    df["trade_date"] = df["trade_date"].astype("datetime64[ns]")
    return df


def year_files(d: Path, prefix: str = "") -> dict[int, Path]:
    out = {}
    for p in sorted(d.glob(f"{prefix}*.parquet")):
        tail = p.stem[len(prefix) :]
        if tail.isdigit():
            out[int(tail)] = p
    return out


def sharpe(x, min_n: int = 20) -> float:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    if len(x) < min_n:
        return float("nan")
    sd = x.std(ddof=1)
    if not sd > 0:
        return float("nan")
    return float(x.mean() / sd * math.sqrt(252.0))


def nw_stats(x, lags: int = 10) -> dict:
    """Mean, Newey-West t (same estimator as ``evaluate.newey_west_t``), NW and iid standard error."""
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    out = {"mean": float("nan"), "t": float("nan"), "se_nw": float("nan"), "se_iid": float("nan")}
    out["n"] = n
    if n < lags + 3:
        return out
    d = x - x.mean()
    s0 = float(d @ d) / n
    s = s0
    for lag in range(1, lags + 1):
        s += 2.0 * (1.0 - lag / (lags + 1.0)) * float(d[lag:] @ d[:-lag]) / n
    out["mean"] = float(x.mean())
    out["se_iid"] = math.sqrt(s0 / n) if s0 > 0 else float("nan")
    if s > 0:
        out["se_nw"] = math.sqrt(s / n)
        out["t"] = float(x.mean() / out["se_nw"])
    return out


def bh_qvalues(p) -> np.ndarray:
    """Benjamini-Hochberg adjusted p-values (q-values)."""
    p = np.asarray(p, dtype="float64")
    m = len(p)
    order = np.argsort(p)
    ranked = p[order] * m / (np.arange(m) + 1.0)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(m)
    q[order] = np.minimum(q_sorted, 1.0)
    return q


def half_life_np(means: np.ndarray) -> float:
    """Smallest m with sum_{j=2}^{1+m} IC_j >= 0.5 * CIC(2..22); NaN if CIC(2..22) <= 0."""
    y = np.asarray(means, dtype="float64")[1:LAGS]
    if not np.isfinite(y).all():
        return float("nan")
    cic = float(y.sum())
    if not cic > 0:
        return float("nan")
    hit = np.flatnonzero(np.cumsum(y) >= 0.5 * cic)
    return float(hit[0] + 1) if len(hit) else float("nan")


def half_life_exp(means: np.ndarray) -> float:
    """Fit IC_j = A exp(-lam (j - 2)) over lags 2..22; h = ln 2 / lam; NaN if lam <= 0 or no fit."""
    y = np.asarray(means, dtype="float64")[1:LAGS]
    x = np.arange(len(y), dtype="float64")
    if not np.isfinite(y).all() or not (y > 0).any():
        return float("nan")
    pos = y > 0
    if pos.sum() >= 2:
        slope, intercept = np.polyfit(x[pos], np.log(y[pos]), 1)
        p0 = (math.exp(intercept), max(-slope, 1e-3))
    else:
        p0 = (float(y[pos][0]), 0.1)
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            popt, _ = curve_fit(
                lambda xx, a, lam: a * np.exp(-lam * xx),
                x,
                y,
                p0=p0,
                maxfev=5000,
                xtol=1e-14,
                ftol=1e-14,
                gtol=1e-14,
            )
    except Exception:
        return float("nan")
    lam = float(popt[1])
    if not (lam > 0) or not math.isfinite(lam):
        return float("nan")
    return math.log(2.0) / lam


def rolling_sum_min_obs(x: np.ndarray, window: int, min_obs: int) -> np.ndarray:
    """Trailing sum of the finite values over ``window`` rows ending at t (inclusive); NaN below
    ``min_obs`` finite values."""
    ok = np.isfinite(x)
    z = np.where(ok, x, 0.0)
    cs = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(z, axis=0)])
    cc = np.vstack([np.zeros((1, x.shape[1])), np.cumsum(ok, axis=0)])
    hi = np.arange(1, x.shape[0] + 1)
    lo = np.maximum(hi - window, 0)
    s = cs[hi] - cs[lo]
    c = cc[hi] - cc[lo]
    return np.where(c >= min_obs, s, np.nan)


def rolling_ir(x: np.ndarray, window: int, min_obs: int) -> np.ndarray:
    """IR_k(t) = mean / sd (ddof 1) of ``x[s, k]`` over the ``window`` rows s in [t-window-1, t-2]
    (the most recent rows with s <= t-2); 0 where fewer than ``min_obs`` finite values."""
    t_n = x.shape[0]
    ok = np.isfinite(x)
    z = np.where(ok, x, 0.0)
    pad = np.zeros((1, x.shape[1]))
    cs = np.vstack([pad, np.cumsum(z, axis=0)])
    cs2 = np.vstack([pad, np.cumsum(z * z, axis=0)])
    cc = np.vstack([pad, np.cumsum(ok, axis=0)])
    t = np.arange(t_n)
    lo = np.clip(t - window - 1, 0, t_n)
    hi = np.clip(t - 1, 0, t_n)
    n = cc[hi] - cc[lo]
    s = cs[hi] - cs[lo]
    s2 = cs2[hi] - cs2[lo]
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s / n
        var = np.maximum((s2 - n * mean * mean) / (n - 1.0), 0.0)
        ir = mean / np.sqrt(var)
    return np.where((n >= min_obs) & (var > 0) & np.isfinite(ir), ir, 0.0)


def zrank(M: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Columnwise centred average ranks among the finite values; missing -> 0.  Returns (z, finite)."""
    rk = pd.DataFrame(M).rank(axis=0, method="average", na_option="keep").to_numpy()
    fin = np.isfinite(rk)
    cnt = fin.sum(axis=0)
    z = np.where(fin, rk - (cnt + 1.0) / 2.0, 0.0)
    return z, fin.astype("float64")


def rank_ic(Zx, Fx, Ze, Fe, min_names: int) -> np.ndarray:
    num = Zx.T @ Ze
    den = np.sqrt(np.outer((Zx * Zx).sum(axis=0), (Ze * Ze).sum(axis=0)))
    npair = Fx.T @ Fe
    with np.errstate(invalid="ignore", divide="ignore"):
        ic = num / den
    return np.where((npair >= min_names) & (den > 0), ic, np.nan)


def bucket_mask(advr: np.ndarray, bucket: str, cut: tuple) -> np.ndarray:
    a = np.asarray(advr, dtype="float64")
    with np.errstate(invalid="ignore"):
        if bucket == "L1":
            m = a <= cut[0]
        elif bucket == "L2":
            m = (a > cut[0]) & (a <= cut[1])
        elif bucket == "L3":
            m = (a > cut[1]) & (a <= cut[2])
        elif bucket == "L12":
            m = a <= cut[1]
        else:
            raise ValueError(bucket)
    return m & np.isfinite(a)


# ------------------------------------------------------------------------------ context


class Ctx:
    """Dense (sessions x symbols) grids and row caches written by the build stage."""

    def __init__(self, cfg: Cfg):
        c = cfg.cache
        self.cfg = cfg
        meta = json.loads((c / "meta.json").read_text())
        self.meta = meta
        self.D = pd.DatetimeIndex(np.load(c / "D.npy").astype("datetime64[ns]"))
        self.symbols = np.array(meta["symbols"])
        self.T, self.N = len(self.D), len(self.symbols)
        self.years = meta["years"]
        spy = np.load(c / "spy.npz")
        self.spy_o, self.spy_c = spy["o"], spy["c"]

        def mm(name: str):
            f = c / f"{name}.npy"
            return np.load(f, mmap_mode="r") if f.exists() else None

        # the report stage can run from the small ``intermediate`` export without the grids
        self.O, self.C, self.beta = mm("O"), mm("C"), mm("beta")
        self.advr, self.dadv, self.vol = mm("advr"), mm("dadv"), mm("vol")
        self.pclose, self.ind, self.se = mm("pclose"), mm("ind"), mm("se")
        self.i0 = int(self.D.searchsorted(pd.Timestamp(cfg.start)))
        self.i1 = int(self.D.searchsorted(pd.Timestamp(cfg.end), side="right")) - 1

    def rows(self, y: int) -> dict:
        z = np.load(self.cfg.cache / f"rows_{y}.npz")
        return {"di": z["di"], "si": z["si"], "ind": z["ind"]}

    def window_mask(self, win: tuple) -> np.ndarray:
        a, b = pd.Timestamp(win[0]), pd.Timestamp(win[1])
        return np.asarray((self.D >= a) & (self.D <= b))


def object_names(ctx_or_meta) -> dict:
    meta = ctx_or_meta.meta if hasattr(ctx_or_meta, "meta") else ctx_or_meta
    a = list(meta["lib"])
    d = ["m0_composite"] + [f"theme_{t}" for t in meta["themes"]]
    return {"A": a, "B": OBJ_B, "C": OBJ_C, "D": d}


def base_columns(meta: dict) -> list[str]:
    n = object_names(meta)
    return n["A"] + n["B"] + n["D"]


def candidates_and_m0(meta: dict) -> list[str]:
    return OBJ_B + OBJ_C + ["m0_composite"]


def load_signs(cfg: Cfg) -> dict:
    return json.loads((cfg.cache / "signs.json").read_text())


def year_matrix(cfg: Cfg, y: int, signs: dict | None) -> tuple[np.ndarray, list[str]]:
    """(n x 70) float32 [A, B (ON5/ID5 signed), D] for year y, and the column names."""
    meta = json.loads((cfg.cache / "meta.json").read_text())
    A = np.load(cfg.cache / f"A_{y}.npy")
    B = np.load(cfg.cache / f"B_{y}.npy").astype(np.float32)
    Dm = np.load(cfg.cache / f"D_{y}.npy")
    if signs is not None:
        for nm in ("ON5", "ID5"):
            B[:, OBJ_B.index(nm)] *= np.float32(signs[nm]["sign"])
    return np.hstack([A, B, Dm]), base_columns(meta)


# ------------------------------------------------------------------------------ build


def discover_columns(cfg: Cfg) -> tuple[list[str], list[str], dict]:
    sig_dir = cfg.data / "signals"
    files = year_files(sig_dir)
    path = files[cfg.schema_year] if cfg.schema_year in files else files[max(files)]
    names = pq.read_schema(path).names
    cov = {n[: -len("_cov")] for n in names if n.endswith("_cov")}
    lib = [n for n in names if n in cov and n.startswith(("a101_", "g191_"))]
    lib += [n for n in ("rev_21_ind", "on252") if n in cov]
    themes = list(sg.THEME_SIGNALS.keys())
    members = {t: list(v) for t, v in sg.THEME_SIGNALS.items()}
    return lib, themes, members


def stage_build(cfg: Cfg) -> None:
    c = cfg.cache
    c.mkdir(parents=True, exist_ok=True)
    if (c / "build.done").exists() and not cfg.force:
        log("build: done marker present, skipping")
        return
    event(cfg, "build_start")
    maxd: dict[str, str] = {}

    def track(tag: str, df: pd.DataFrame) -> None:
        if len(df):
            m = str(df["trade_date"].max().date())
            maxd[tag] = max(maxd.get(tag, m), m)

    lib, themes, members = discover_columns(cfg)
    log(f"library columns found: {len(lib)} (expected {cfg.expected_lib})")
    if len(lib) != cfg.expected_lib:
        raise RuntimeError(f"library column count {len(lib)} != {cfg.expected_lib}")

    etf = read_dated(
        cfg.data / "etf_daily.parquet", ["trade_date", "symbol", "open", "close"], cfg.last_data
    )
    track("etf_daily", etf)
    etf = etf[etf["symbol"] == "SPY"].set_index("trade_date").sort_index()
    sess = etf["open"].dropna().index
    sess = sess[(sess >= pd.Timestamp(cfg.cal_start)) & (sess <= pd.Timestamp(cfg.last_data))]
    D = pd.DatetimeIndex(sess)
    T = len(D)
    spy_o = etf["open"].reindex(D).to_numpy("float64")
    spy_c = etf["close"].reindex(D).to_numpy("float64")

    # ---- symbols = every name that ever appears in the signal store
    sig_files = year_files(cfg.data / "signals")
    years = sorted(sig_files)
    syms: set[str] = set()
    for y in years:
        df = read_dated(sig_files[y], ["trade_date", "symbol"], cfg.last_data)
        syms.update(df["symbol"].unique().tolist())
    symbols = sorted(syms)
    sym_index = pd.Index(symbols)
    N = len(symbols)
    log(f"sessions {T}, symbols {N}")

    # ---- dense prices
    O = np.full((T, N), np.nan)
    C = np.full((T, N), np.nan)
    for _y, p in year_files(cfg.data / "prices").items():
        df = read_dated(p, ["trade_date", "symbol", "open", "close"], cfg.last_data)
        track("prices", df)
        di = D.get_indexer(df["trade_date"])
        si = sym_index.get_indexer(df["symbol"])
        m = (di >= 0) & (si >= 0)
        O[di[m], si[m]] = df["open"].to_numpy("float64")[m]
        C[di[m], si[m]] = df["close"].to_numpy("float64")[m]
        del df
    # ---- dense panel
    advr = np.full((T, N), np.nan, dtype="float32")
    dadv = np.full((T, N), np.nan)
    vol = np.full((T, N), np.nan)
    pclose = np.full((T, N), np.nan)
    beta = np.full((T, N), np.nan)
    pcols = ["trade_date", "symbol", "adv_rank", "dollar_adv_21", "vol_21", "beta_252_spy", "close"]
    for _y, p in year_files(cfg.data / "panel").items():
        df = read_dated(p, pcols, cfg.last_data)
        track("panel", df)
        di = D.get_indexer(df["trade_date"])
        si = sym_index.get_indexer(df["symbol"])
        m = (di >= 0) & (si >= 0)
        advr[di[m], si[m]] = df["adv_rank"].to_numpy("float64")[m].astype("float32")
        dadv[di[m], si[m]] = df["dollar_adv_21"].to_numpy("float64")[m]
        vol[di[m], si[m]] = df["vol_21"].to_numpy("float64")[m]
        beta[di[m], si[m]] = df["beta_252_spy"].to_numpy("float64")[m]
        pclose[di[m], si[m]] = df["close"].to_numpy("float64")[m]
        del df
    # ---- residuals
    R = np.full((T, N), np.nan)
    for _y, p in year_files(cfg.data / "risk", "residuals_").items():
        df = read_dated(p, ["trade_date", "symbol", "resid"], cfg.last_data)
        track("risk_residuals", df)
        di = D.get_indexer(df["trade_date"])
        si = sym_index.get_indexer(df["symbol"])
        m = (di >= 0) & (si >= 0)
        R[di[m], si[m]] = df["resid"].to_numpy("float64")[m]
        del df
    # ---- volume shock proxy
    V = np.full((T, N), np.nan, dtype="float32")
    for _y, p in year_files(cfg.daily_broad).items():
        df = read_dated(p, ["symbol", "trade_date", "dollar_adv_21_over_63"], cfg.last_data)
        track("daily_broad", df)
        di = D.get_indexer(df["trade_date"])
        si = sym_index.get_indexer(df["symbol"])
        m = (di >= 0) & (si >= 0)
        V[di[m], si[m]] = df["dollar_adv_21_over_63"].to_numpy("float64")[m].astype("float32")
        del df

    # ---- new signals (dense)
    with np.errstate(invalid="ignore", divide="ignore"):
        r5 = np.full((T, N), np.nan)
        ok = (C[5:] > 0) & (C[:-5] > 0)
        r5[5:] = np.where(ok, C[5:] / C[:-5] - 1.0, np.nan)
        ov = sg.overnight_matrix(O, C)
        idm = np.where((O > 0) & (C > 0), C / O - 1.0, np.nan)
    on5 = sg.rolling_mean_min_obs(ov, 5, 4)
    id5 = sg.rolling_mean_min_obs(idm, 5, 4)
    rr5 = -rolling_sum_min_obs(R, 5, 4)
    rr21 = -rolling_sum_min_obs(R, 21, 17)
    del ov, idm, R

    # ---- reverse splits and the short-eligible grid
    flags = borrow.detect_reverse_splits(pd.DataFrame(O, copy=False), pd.DataFrame(C, copy=False))
    rs = borrow.reverse_split_in_window(flags)
    se = borrow.short_eligible(
        {
            "adv_rank": pd.DataFrame(advr, copy=False),
            "price": pd.DataFrame(pclose, copy=False),
            "reverse_split_252": rs,
        }
    ).to_numpy(bool)
    del flags, rs

    # ---- per-year rows
    ind_dense = np.full((T, N), -2, dtype="int16")
    vshk_cov: dict[str, float] = {}
    row_counts: dict[str, int] = {}
    adv_samples: dict[str, list] = {b: [] for b in ("L1", "L2", "L3")}
    theme_cov_cols = sorted({f"{m}_cov" for t in themes for m in members[t]})
    lib_cov = [f"{n}_cov" for n in lib]
    scols = (
        ["trade_date", "symbol", "ind_code", "m0_composite", "m0_n_themes"]
        + lib
        + lib_cov
        + [f"theme_{t}" for t in themes]
        + theme_cov_cols
    )
    for y in years:
        df = read_dated(sig_files[y], scols, cfg.last_data)
        track("signals", df)
        di = D.get_indexer(df["trade_date"])
        si = sym_index.get_indexer(df["symbol"])
        keep = (di >= 0) & (si >= 0)
        df = df[keep].reset_index(drop=True)
        di, si = di[keep], si[keep]
        order = np.lexsort((si, di))
        df = df.iloc[order].reset_index(drop=True)
        di, si = di[order].astype(np.int32), si[order].astype(np.int32)
        ind = df["ind_code"].to_numpy("int16")
        n = len(df)
        A = np.full((n, len(lib)), np.nan, dtype="float32")
        for k, nm in enumerate(lib):
            v = df[nm].to_numpy(np.float32)
            cov = df[f"{nm}_cov"].fillna(False).to_numpy(bool)
            A[:, k] = np.where(cov & np.isfinite(v), v, np.nan)
        Dm = np.full((n, 1 + len(themes)), np.nan, dtype="float32")
        v = df["m0_composite"].to_numpy(np.float32)
        okm = (df["m0_n_themes"].to_numpy() > 0) & np.isfinite(v)
        Dm[:, 0] = np.where(okm, v, np.nan)
        for k, t in enumerate(themes):
            v = df[f"theme_{t}"].to_numpy(np.float32)
            cov = np.zeros(n, bool)
            for mname in members[t]:
                cov |= df[f"{mname}_cov"].fillna(False).to_numpy(bool)
            Dm[:, 1 + k] = np.where(cov & np.isfinite(v), v, np.nan)
        # new signals for these rows
        dates_s = pd.Series(D[di])
        r5r = r5[di, si]
        gmr = sg.group_mean(pd.Series(r5r), dates_s, ind, sg.MIN_INDUSTRY_MEMBERS)
        Bm = np.column_stack(
            [
                -r5r,
                -(r5r - gmr),
                rr5[di, si],
                rr21[di, si],
                on5[di, si],
                id5[di, si],
                V[di, si].astype("float64"),
            ]
        ).astype("float32")
        vshk_cov[str(y)] = float(np.isfinite(Bm[:, 6]).mean()) if n else float("nan")
        row_counts[str(y)] = int(n)
        np.savez(c / f"rows_{y}.npz", di=di, si=si, ind=ind)
        np.save(c / f"A_{y}.npy", A)
        np.save(c / f"B_{y}.npy", Bm)
        np.save(c / f"D_{y}.npy", Dm)
        ind_dense[di, si] = ind
        # advr samples for the monotonicity check (every 10th date)
        ar = advr[di, si]
        dd = dadv[di, si]
        sel = (di % 10) == 0
        for b in adv_samples:
            mb = bucket_mask(ar, b, cfg.cut) & sel & np.isfinite(dd)
            adv_samples[b].append(dd[mb])
        log(f"build: signals {y} rows {n}")
        del df, A, Dm, Bm
    med = {
        b: float(np.median(np.concatenate(v))) if v else float("nan")
        for b, v in adv_samples.items()
    }
    mono = bool(med["L1"] > med["L2"] > med["L3"])
    log(f"median dollar_adv_21 by bucket {med} monotone={mono}")
    if not mono:
        raise RuntimeError(f"adv_rank direction check failed: {med}")

    # ---- write grids
    np.save(c / "D.npy", D.to_numpy().astype("datetime64[ns]"))
    np.savez(c / "spy.npz", o=spy_o, c=spy_c)
    for name, arr in (
        ("O", O),
        ("C", C),
        ("beta", beta),
        ("advr", advr),
        ("dadv", dadv),
        ("vol", vol),
        ("pclose", pclose),
        ("ind", ind_dense),
        ("se", se),
    ):
        np.save(c / f"{name}.npy", arr)
    meta = {
        "symbols": symbols,
        "years": years,
        "lib": lib,
        "themes": themes,
        "n_lib": len(lib),
        "vshk_coverage_by_year": vshk_cov,
        "rows_by_year": row_counts,
        "max_trade_date_read": maxd,
        "adv_median_by_bucket": med,
        "adv_monotone": mono,
        "built_utc": now_utc(),
    }
    write_json(c / "meta.json", meta)
    event(cfg, "build_grids_done")
    # ---- fix the ON5 / ID5 signs from the stress window only, before anything recent
    ctx = Ctx(cfg)
    fix_signs(cfg, ctx)
    (c / "build.done").write_text(now_utc())
    log("build: done")


# ------------------------------------------------------------------------------ targets and IC


def demean_cols(E: np.ndarray, di: np.ndarray, ind: np.ndarray) -> np.ndarray:
    """Demean each column within (date, ind_code) over the finite entries."""
    grp = di.astype(np.int64) * 10_000 + ind.astype(np.int64)
    g, _ = pd.factorize(grp)
    ng = int(g.max()) + 1 if len(g) else 0
    out = np.full_like(E, np.nan)
    for j in range(E.shape[1]):
        col = E[:, j]
        okc = np.isfinite(col)
        cnt = np.bincount(g, weights=okc.astype(float), minlength=ng)
        sm = np.bincount(g, weights=np.where(okc, col, 0.0), minlength=ng)
        out[:, j] = col - (sm / np.maximum(cnt, 1))[g]
        out[~okc, j] = np.nan
    return out


def _beta_rows(ctx: Ctx, di, si) -> np.ndarray:
    b = np.asarray(ctx.beta[di, si], dtype="float64")
    return np.clip(np.where(np.isfinite(b), b, 1.0), -0.5, 3.0)


def lag_targets(ctx: Ctx, di: np.ndarray, si: np.ndarray, ind: np.ndarray) -> np.ndarray:
    """(n x 24) hedged, (date, ind)-demeaned returns: lags 1..22 close-to-close, then overnight
    (close t -> open t+1) and intraday (open t+1 -> close t+1) of lag 1."""
    n = len(di)
    b = _beta_rows(ctx, di, si)
    C, O, so, sc = ctx.C, ctx.O, ctx.spy_o, ctx.spy_c
    E = np.full((n, NTGT), np.nan)
    di = di.astype(np.int64)
    with np.errstate(invalid="ignore", divide="ignore"):
        for j in range(1, LAGS + 1):
            ok = di + j < ctx.T
            d1 = np.where(ok, di + j, 0)
            d0 = np.where(ok, di + j - 1, 0)
            c1, c0 = np.asarray(C[d1, si]), np.asarray(C[d0, si])
            r = np.where((c1 > 0) & (c0 > 0), c1 / c0 - 1.0, np.nan)
            rs = sc[d1] / sc[d0] - 1.0
            E[:, j - 1] = np.where(ok, r - b * rs, np.nan)
        ok = di + 1 < ctx.T
        d1 = np.where(ok, di + 1, 0)
        o1, c0, c1 = np.asarray(O[d1, si]), np.asarray(C[di, si]), np.asarray(C[d1, si])
        ro = np.where((o1 > 0) & (c0 > 0), o1 / c0 - 1.0, np.nan)
        ri = np.where((c1 > 0) & (o1 > 0), c1 / o1 - 1.0, np.nan)
        E[:, LAGS] = np.where(ok, ro - b * (so[d1] / sc[di] - 1.0), np.nan)
        E[:, LAGS + 1] = np.where(ok, ri - b * (sc[d1] / so[d1] - 1.0), np.nan)
    E[~np.isfinite(E)] = np.nan
    return demean_cols(E, di, ind)


def open_e(ctx: Ctx, di: np.ndarray, si: np.ndarray, ind: np.ndarray) -> np.ndarray:
    """Regimes convention: hedged open(t+1) -> open(t+2) return, demeaned within (date, ind)."""
    di = di.astype(np.int64)
    b = _beta_rows(ctx, di, si)
    ok = di + 2 < ctx.T
    d1 = np.where(ok, di + 1, 0)
    d2 = np.where(ok, di + 2, 0)
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.asarray(ctx.O[d2, si]) / np.asarray(ctx.O[d1, si]) - 1.0
        rs = ctx.spy_o[d2] / ctx.spy_o[d1] - 1.0
        e = np.where(ok, r - b * rs, np.nan)
    e[~np.isfinite(e)] = np.nan
    return demean_cols(e[:, None], di, ind)[:, 0]


class ICAcc:
    """Daily rank IC (24 targets) and persistence for K score columns, by bucket."""

    def __init__(self, cfg: Cfg, ctx: Ctx, K: int, buckets, do_pers: bool = True):
        self.cfg, self.ctx, self.K = cfg, ctx, K
        self.buckets = list(buckets)
        self.do_pers = do_pers
        self.ic = {b: np.full((ctx.T, K, NTGT), np.nan) for b in self.buckets}
        self.pers = {b: np.full((ctx.T, K, len(PERS_LAGS)), np.nan) for b in self.buckets}
        self.hist: dict[int, tuple[np.ndarray, np.ndarray]] = {}

    def add_year(self, di, si, advr, X, E, date_ok: np.ndarray | None = None, lags=None) -> None:
        cfg = self.cfg
        cut = np.flatnonzero(np.diff(di)) + 1
        starts = np.concatenate([[0], cut])
        ends = np.concatenate([cut, [len(di)]])
        for a, b in zip(starts, ends, strict=True):
            d = int(di[a])
            if date_ok is not None and not date_ok[d]:
                continue
            Xd, Ed, sd, ad = X[a:b], E[a:b], si[a:b], advr[a:b]
            if self.do_pers:
                self.hist[d] = (sd.copy(), np.array(Xd, dtype="float32"))
                for old in [k for k in self.hist if k < d - max(PERS_LAGS)]:
                    del self.hist[old]
            for bk in self.buckets:
                sel = np.flatnonzero(bucket_mask(ad, bk, cfg.cut))
                if len(sel) < cfg.min_names:
                    continue
                Xb = np.asarray(Xd[sel], dtype="float64")
                Xb[~np.isfinite(Xb)] = np.nan
                Eb = Ed[sel] if lags is None else Ed[sel][:, lags]
                Zx, Fx = zrank(Xb)
                Ze, Fe = zrank(Eb)
                ic = rank_ic(Zx, Fx, Ze, Fe, cfg.min_names)
                if lags is None:
                    self.ic[bk][d] = ic
                else:
                    self.ic[bk][d][:, lags] = ic
                if self.do_pers:
                    for li, L in enumerate(PERS_LAGS):
                        prev = self.hist.get(d - L)
                        if prev is None:
                            continue
                        psi, pX = prev
                        pos = np.clip(np.searchsorted(psi, sd[sel]), 0, len(psi) - 1)
                        present = psi[pos] == sd[sel]
                        Bp = np.full(Xb.shape, np.nan)
                        Bp[present] = pX[pos[present]]
                        both = np.isfinite(Xb) & np.isfinite(Bp)
                        Aa = np.where(both, Xb, np.nan)
                        Bb = np.where(both, Bp, np.nan)
                        za, _ = zrank(Aa)
                        zb, _ = zrank(Bb)
                        num = (za * zb).sum(axis=0)
                        den = np.sqrt((za * za).sum(axis=0) * (zb * zb).sum(axis=0))
                        npair = both.sum(axis=0)
                        with np.errstate(invalid="ignore", divide="ignore"):
                            pr = num / den
                        self.pers[bk][d][:, li] = np.where(
                            (npair >= cfg.min_names) & (den > 0), pr, np.nan
                        )


def date_ok_mask(ctx: Ctx, win: tuple | None) -> np.ndarray | None:
    return None if win is None else ctx.window_mask(win)


def get_targets(cfg: Cfg, ctx: Ctx, y: int, rows: dict) -> np.ndarray:
    p = cfg.cache / f"tgt_{y}.npy"
    if p.exists():
        return np.load(p)
    E = lag_targets(ctx, rows["di"], rows["si"], rows["ind"])
    np.save(p, E)
    return E


def fix_signs(cfg: Cfg, ctx: Ctx) -> None:
    """ON5 / ID5: sign of the stress-window mean CIC(2..6) on L12, fixed and stamped before any
    recent-window number is computed."""
    out = cfg.cache / "signs.json"
    if out.exists() and not cfg.force:
        return
    lo, hi = pd.Timestamp(cfg.sign_window[0]), pd.Timestamp(cfg.sign_window[1])
    wmask = ctx.window_mask(cfg.sign_window)
    acc = ICAcc(cfg, ctx, 2, ["L12"], do_pers=False)
    cols = [OBJ_B.index("ON5"), OBJ_B.index("ID5")]
    for y in ctx.years:
        rows = ctx.rows(y)
        if len(rows["di"]) == 0 or ctx.D[rows["di"][0]] > hi or ctx.D[rows["di"][-1]] < lo:
            continue
        B = np.load(cfg.cache / f"B_{y}.npy")[:, cols]
        E = get_targets(cfg, ctx, y, rows)
        advr = np.asarray(ctx.advr[rows["di"], rows["si"]])
        acc.add_year(rows["di"], rows["si"], advr, B, E, date_ok=wmask, lags=[1, 2, 3, 4, 5])
    res = {}
    for k, nm in enumerate(("ON5", "ID5")):
        ic = acc.ic["L12"][:, k, 1:6]
        means = np.nanmean(np.where(wmask[:, None], ic, np.nan), axis=0)
        cic = float(np.nansum(means))
        res[nm] = {"stress_cic_2_6_mean": cic, "sign": 1 if cic > 0 else -1}
    res["window"] = list(cfg.sign_window)
    res["fixed_at"] = now_utc()
    write_json(out, res)
    event(cfg, "signs_fixed", signs=res)
    log(f"signs fixed: {res}")


# ------------------------------------------------------------------------------ identity


def regimes_ls(ctx: Ctx, cfg: Cfg, names_cols: dict[str, tuple[str, int]]) -> pd.DataFrame:
    """Regimes-convention daily long-short returns (open t+1 -> open t+2, weights s - mean over the
    coverage mask scaled to gross 2, all signal-store names with a return, no cost)."""
    parts = []
    lo, hi = pd.Timestamp(cfg.start), pd.Timestamp(cfg.end)
    for y in ctx.years:
        rows = ctx.rows(y)
        di, si, ind = rows["di"], rows["si"], rows["ind"]
        dts = ctx.D[di]
        m = np.asarray((dts >= lo) & (dts <= hi))
        if not m.any():
            continue
        di, si, ind = di[m], si[m], ind[m]
        e = open_e(ctx, di, si, ind)
        fin = np.isfinite(e)
        di, si, ind, e = di[fin], si[fin], ind[fin], e[fin]
        if len(di) == 0:
            continue
        mats = {}
        for kind in {k for k, _ in names_cols.values()}:
            mats[kind] = np.load(cfg.cache / f"{kind}_{y}.npy")[m][fin]
        codes, dates = pd.factorize(di, sort=True)
        nd = len(dates)
        out = {}
        for nm, (kind, col) in names_cols.items():
            s = mats[kind][:, col].astype("float64")
            mask = np.isfinite(s)
            sm = np.where(mask, s, 0.0)
            cnt = np.bincount(codes, weights=mask.astype(float), minlength=nd)
            mean = np.bincount(codes, weights=sm, minlength=nd) / np.maximum(cnt, 1)
            w = np.where(mask, s - mean[codes], 0.0)
            gross = np.bincount(codes, weights=np.abs(w), minlength=nd)
            ok_day = (cnt >= cfg.min_names) & (gross > 0)
            w = np.where(ok_day[codes], 2.0 * w / np.where(gross > 0, gross, 1.0)[codes], 0.0)
            f = np.bincount(codes, weights=w * e, minlength=nd)
            out[nm] = np.where(ok_day, f, np.nan)
        parts.append(pd.DataFrame(out, index=ctx.D[dates]))
    return pd.concat(parts).sort_index()


def identity_columns(meta: dict, cols: tuple) -> dict[str, tuple[str, int]]:
    n = object_names(meta)
    out = {}
    for nm in cols:
        if nm in n["A"]:
            out[nm] = ("A", n["A"].index(nm))
        elif nm in n["D"]:
            out[nm] = ("D", n["D"].index(nm))
        else:
            raise KeyError(nm)
    return out


def stage_identity(cfg: Cfg) -> None:
    c = cfg.cache
    if (c / "identity.done").exists() and not cfg.force:
        log("identity: done marker present, skipping")
        return
    event(cfg, "recent_window_first_touch", stage="identity")
    ctx = Ctx(cfg)
    nc = identity_columns(ctx.meta, cfg.identity_cols)
    mine = regimes_ls(ctx, cfg, nc)
    ref = pd.read_parquet(cfg.regimes_ref, columns=list(cfg.identity_cols))
    if not isinstance(ref.index, pd.DatetimeIndex):
        raise RuntimeError(f"reference index is {type(ref.index).__name__}, expected dates")
    ref.index = pd.DatetimeIndex(ref.index).astype("datetime64[ns]")
    ref = ref[(ref.index >= pd.Timestamp(cfg.start)) & (ref.index <= pd.Timestamp(cfg.end))]
    res = {}
    passed = True
    for nm in cfg.identity_cols:
        a = mine[nm].reindex(ref.index.union(mine.index))
        b = ref[nm].reindex(a.index)
        fa, fb = np.isfinite(a.to_numpy()), np.isfinite(b.to_numpy())
        nan_mismatch = int((fa != fb).sum())
        both = fa & fb
        diff = (
            float(np.abs(a.to_numpy()[both] - b.to_numpy()[both]).max())
            if both.any()
            else float("nan")
        )
        ok = (nan_mismatch == 0) and (diff <= cfg.identity_tol)
        passed &= ok
        res[nm] = {
            "max_abs_diff": diff,
            "nan_pattern_mismatch_days": nan_mismatch,
            "n_compared_days": int(both.sum()),
            "n_ref_days": int(fb.sum()),
            "passed": bool(ok),
        }
    res["passed"] = bool(passed)
    res["tolerance"] = cfg.identity_tol
    write_json(cfg.iter_dir / "identity.json", res)
    log(f"identity: {res}")
    if not passed:
        write_json(
            cfg.iter_dir / "results.json",
            {"mechanical_status": "identity_failed", "identity": res, "generated_utc": now_utc()},
        )
        raise SystemExit(3)
    (c / "identity.done").write_text(now_utc())


# ------------------------------------------------------------------------------ measure


def stage_measure(cfg: Cfg) -> None:
    c = cfg.cache
    if (c / "measure.done").exists() and not cfg.force:
        log("measure: done marker present, skipping")
        return
    event(cfg, "measure_start")
    ctx = Ctx(cfg)
    signs = load_signs(cfg)
    base_cols = base_columns(ctx.meta)
    K = len(base_cols)
    sub_cols = [base_cols.index(n) for n in OBJ_B + ["m0_composite"]]
    acc_base = ICAcc(cfg, ctx, K, ["L12"])
    acc_sub = ICAcc(cfg, ctx, len(sub_cols), ["L1", "L2", "L3"])
    drop1 = np.zeros(ctx.T)
    drop2 = np.zeros(ctx.T)
    nrows = np.zeros(ctx.T)
    first_recent = ctx.window_mask(cfg.windows["recent"]).argmax()
    for y in ctx.years:
        rows = ctx.rows(y)
        di, si = rows["di"], rows["si"]
        if len(di) == 0:
            continue
        if int(di[-1]) >= first_recent and not (c / "recent_logged").exists():
            event(cfg, "recent_window_first_touch", stage="measure", year=y)
            (c / "recent_logged").write_text(now_utc())
        X, _ = year_matrix(cfg, y, signs)
        E = get_targets(cfg, ctx, y, rows)
        advr = np.asarray(ctx.advr[di, si])
        acc_base.add_year(di, si, advr, X, E)
        acc_sub.add_year(di, si, advr, X[:, sub_cols], E)
        np.add.at(drop1, di, ~np.isfinite(E[:, 0]))
        np.add.at(drop2, di, ~np.isfinite(E[:, 1]))
        np.add.at(nrows, di, 1)
        log(f"measure: base IC year {y} done")
        del X, E
    np.savez(
        c / "ic_base_L12.npz",
        ic=acc_base.ic["L12"],
        pers=acc_base.pers["L12"],
        names=np.array(base_cols),
    )
    sub_names = [base_cols[i] for i in sub_cols]
    for b in ("L1", "L2", "L3"):
        np.savez(
            c / f"ic_sub_{b}.npz", ic=acc_sub.ic[b], pers=acc_sub.pers[b], names=np.array(sub_names)
        )
    np.savez(c / "drops.npz", drop_lag1=drop1, drop_lag2=drop2, n_rows=nrows)
    del acc_sub
    build_composites(cfg, ctx, acc_base.ic["L12"], base_cols, signs)
    (c / "measure.done").write_text(now_utc())
    log("measure: done")


def build_composites(
    cfg: Cfg, ctx: Ctx, ic_base: np.ndarray, base_cols: list[str], signs: dict
) -> None:
    c = cfg.cache
    in_names = ctx.meta["lib"] + OBJ_B
    idx = [base_cols.index(n) for n in in_names]
    ic2 = ic_base[:, idx, 1]
    finite_any = np.isfinite(ic2).any(axis=1)
    first_ic = int(np.argmax(finite_any)) if finite_any.any() else ctx.T
    irs = {}
    valid_from = {}
    for nm, (w, mn) in cfg.wf.items():
        irs[nm] = rolling_ir(ic2, w, mn)
        valid_from[nm] = first_ic + w + 1
    acc = ICAcc(cfg, ctx, 3, list(BUCKETS))
    first_valid = {n: None for n in OBJ_C}
    for y in ctx.years:
        rows = ctx.rows(y)
        di, si = rows["di"], rows["si"]
        if len(di) == 0:
            continue
        X, _ = year_matrix(cfg, y, signs)
        n_a = len(ctx.meta["lib"])
        X60 = np.hstack([X[:, :n_a], X[:, n_a : n_a + len(OBJ_B)]]).astype("float64")
        comp = np.full((len(di), 3), np.nan, dtype="float32")
        cut = np.flatnonzero(np.diff(di)) + 1
        starts = np.concatenate([[0], cut])
        ends = np.concatenate([cut, [len(di)]])
        for a, b in zip(starts, ends, strict=True):
            d = int(di[a])
            rk = pd.DataFrame(X60[a:b]).rank(axis=0, method="average", na_option="keep").to_numpy()
            fin = np.isfinite(rk)
            cnt = fin.sum(axis=0)
            with np.errstate(invalid="ignore", divide="ignore"):
                z = np.where(fin, ndtri((rk - 0.5) / np.maximum(cnt, 1)), 0.0)
            comp[a:b, 0] = z.mean(axis=1)
            for k, nm in enumerate(("FC_WF252", "FC_WF63")):
                if d >= valid_from[nm]:
                    ir = irs[nm][d]
                    den = np.abs(ir).sum()
                    if den > 0:
                        comp[a:b, 1 + k] = (z @ ir) / den
        for k, nm in enumerate(OBJ_C):
            if first_valid[nm] is None:
                okc = np.isfinite(comp[:, k])
                if okc.any():
                    first_valid[nm] = str(ctx.D[int(di[np.argmax(okc)])].date())
        np.save(c / f"C_{y}.npy", comp)
        E = np.load(c / f"tgt_{y}.npy")
        advr = np.asarray(ctx.advr[di, si])
        acc.add_year(di, si, advr, comp, E)
        log(f"measure: composites year {y} done")
        del X, X60, E
    for b in BUCKETS:
        np.savez(c / f"ic_comp_{b}.npz", ic=acc.ic[b], pers=acc.pers[b], names=np.array(OBJ_C))
    write_json(
        c / "composite_meta.json", {"first_valid_date": first_valid, "first_ic_index": first_ic}
    )


# ------------------------------------------------------------------------------ window stats


def ic_stats(ic: np.ndarray, pers: np.ndarray | None, wmask: np.ndarray) -> dict:
    """Preregistered per-object statistics of a (T x 24) IC array over a window."""
    w = ic[wmask]
    means = np.array(
        [np.nanmean(w[:, j]) if np.isfinite(w[:, j]).any() else np.nan for j in range(NTGT)]
    )
    ts = [nw_stats(w[:, j], 10)["t"] for j in range(LAGS)]
    cic26_daily = np.where(np.isfinite(w[:, 1:6]).all(axis=1), w[:, 1:6].sum(axis=1), np.nan)
    st = nw_stats(cic26_daily, 10)
    m = means[:LAGS]
    cic_2_22 = float(np.nansum(m[1:LAGS])) if np.isfinite(m[1:LAGS]).all() else float("nan")
    cic_1_22 = float(np.nansum(m)) if np.isfinite(m).all() else float("nan")
    cic_2_6 = float(m[1:6].sum()) if np.isfinite(m[1:6]).all() else float("nan")
    ic_id1 = float(means[LAGS + 1])
    f_moc = f_moo = float("nan")
    if np.isfinite(cic_1_22) and cic_1_22 > 0:
        f_moc = 1.0 - cic_2_22 / cic_1_22
        f_moo = 1.0 - (ic_id1 + cic_2_22) / cic_1_22
    pers_out = {}
    for li, L in enumerate(PERS_LAGS):
        if pers is None:
            pers_out[str(L)] = float("nan")
        else:
            col = pers[wmask][:, li]
            pers_out[str(L)] = float(np.nanmean(col)) if np.isfinite(col).any() else float("nan")
    sd = (
        float(np.nanstd(cic26_daily, ddof=1))
        if np.isfinite(cic26_daily).sum() > 1
        else float("nan")
    )
    return {
        "ic_mean": [float(v) for v in m],
        "ic_t": ts,
        "ic_on1": float(means[LAGS]),
        "ic_id1": ic_id1,
        "cic_2_6": cic_2_6,
        "cic_2_6_t": st["t"],
        "cic_2_22": cic_2_22,
        "cic_1_22": cic_1_22,
        "h_np": half_life_np(means),
        "h_exp": half_life_exp(means),
        "F_MOC": f_moc,
        "F_MOO": f_moo,
        "persistence": pers_out,
        "ic_sd_cic_2_6": sd,
        "mde_cic_2_6": 2.8 * st["se_nw"] if np.isfinite(st["se_nw"]) else float("nan"),
        "underpowered": bool(np.isfinite(st["se_nw"]) and 2.8 * st["se_nw"] > 0.01),
        "nw_inflation": (st["se_nw"] / st["se_iid"])
        if st["se_iid"] and st["se_iid"] > 0
        else float("nan"),
        "n_days": int(st["n"]),
    }


def load_ic_store(cfg: Cfg) -> dict:
    """{(object, bucket): (ic (T,24), pers (T,3))} from the measure outputs."""
    c = cfg.cache
    out = {}

    def add(path: Path, bucket: str):
        z = np.load(path)
        for k, nm in enumerate(z["names"]):
            out[(str(nm), bucket)] = (z["ic"][:, k, :], z["pers"][:, k, :])

    add(c / "ic_base_L12.npz", "L12")
    for b in ("L1", "L2", "L3"):
        add(c / f"ic_sub_{b}.npz", b)
    for b in BUCKETS:
        add(c / f"ic_comp_{b}.npz", b)
    return out


# ------------------------------------------------------------------------------ speed


class PathCtx:
    """Arrays for the path engine (memory-mapped, shared by workers)."""

    def __init__(self, cfg: Cfg, ctx: Ctx):
        c = cfg.cache
        self.cfg, self.ctx = cfg, ctx
        mm = {"mmap_mode": "r"}
        self.hs = {s: np.load(c / f"hs_{s}.npy", **mm) for s in ("close", "open")}
        self.e = {"close": np.load(c / "e_moc.npy", **mm), "open": np.load(c / "e_moo.npy", **mm)}
        self.ok = {
            "close": np.load(c / "ok_close.npy", **mm),
            "open": np.load(c / "ok_open.npy", **mm),
        }
        self.impk = np.load(c / "impk.npy", **mm)
        self.i0, self.i1 = ctx.i0, ctx.i1
        self.nT = self.i1 - self.i0 + 1
        self.N = ctx.N
        self.dates = ctx.D[self.i0 : self.i1 + 1]
        self.wmasks = {
            k: np.asarray((self.dates >= pd.Timestamp(a)) & (self.dates <= pd.Timestamp(b)))
            for k, (a, b) in cfg.windows.items()
        }


def cost_grid(price, adv, vol, year, snap: str, model=None) -> np.ndarray:
    """Half spread in bp (``costs.half_spread_bp``); a missing input costs 40 bp (as ``costfn.py``)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        h = costs.half_spread_bp(price, adv, vol, year, snap, model)
    return np.where(np.isfinite(h), h, MISSING_HALF_SPREAD_BP)


def prepare_speed(cfg: Cfg, ctx: Ctx) -> None:
    c = cfg.cache
    if (c / "speed_prep.done").exists() and not cfg.force:
        return
    log("speed: preparing cost grids and return grids")
    model = costs.load_model()
    T, N = ctx.T, ctx.N
    yrs = ctx.D.year.to_numpy()
    yr_next = np.append(yrs[1:], yrs[-1])
    for snap in ("close", "open"):
        hs = np.empty((T, N))
        step = 250
        for a in range(0, T, step):
            b = min(a + step, T)
            hs[a:b] = cost_grid(
                np.asarray(ctx.pclose[a:b]),
                np.asarray(ctx.dadv[a:b]),
                np.asarray(ctx.vol[a:b]),
                yr_next[a:b, None],
                snap,
                model,
            )
        np.save(c / f"hs_{snap}.npy", hs)
        del hs
    # impact at a $1M trade; impact_bp(|dw| x $1M) = impk x sqrt(|dw|) (square-root law)
    impk = np.empty((T, N))
    for a in range(0, T, 250):
        b = min(a + 250, T)
        with np.errstate(invalid="ignore", divide="ignore"):
            v = costs.impact_bp(1e6, np.asarray(ctx.dadv[a:b]), np.asarray(ctx.vol[a:b]))
        impk[a:b] = np.where(np.isfinite(v), v, 0.0)
    np.save(c / "impk.npy", impk)
    del impk
    okc = np.zeros((T, N), dtype=bool)
    oko = np.zeros((T, N), dtype=bool)
    okc[:-1] = np.isfinite(np.asarray(ctx.C[1:]))
    oko[:-1] = np.isfinite(np.asarray(ctx.O[1:]))
    np.save(c / "ok_close.npy", okc)
    np.save(c / "ok_open.npy", oko)
    del okc, oko
    e_moc = np.zeros((T, N))
    e_moo = np.zeros((T, N))
    for y in ctx.years:
        rows = ctx.rows(y)
        di, si, ind = rows["di"], rows["si"], rows["ind"]
        if len(di) == 0:
            continue
        E = get_targets(cfg, ctx, y, rows)
        v = E[:, 1]
        e_moc[di, si] = np.where(np.isfinite(v), v, 0.0)
        v = open_e(ctx, di, si, ind)
        e_moo[di, si] = np.where(np.isfinite(v), v, 0.0)
        del E
    np.save(c / "e_moc.npy", e_moc)
    np.save(c / "e_moo.npy", e_moo)
    (c / "speed_prep.done").write_text(now_utc())


class WStar:
    def __init__(self, idx, val, valid):
        self.idx, self.val, self.valid = idx, val, valid


def wstar_from_dense(S: np.ndarray, ctx: Ctx, cfg: Cfg) -> WStar:
    """Target weights w*_t for t in [i0, i1] from a dense score grid (NaN outside the bucket):
    rank-normal -> ``target_weights`` (industry demeaned, gross 2) -> ``restrict_shorts``."""
    idxs, vals, valid = [], [], []
    for t in range(ctx.i0, ctx.i1 + 1):
        row = np.asarray(S[t])
        idx = np.flatnonzero(np.isfinite(row))
        if len(idx) < cfg.min_names:
            idxs.append(np.zeros(0, dtype=np.int64))
            vals.append(np.zeros(0))
            valid.append(False)
            continue
        z = sg.rank_normal(row[idx])
        s = pd.Series(z, index=idx)
        ind = pd.Series(np.asarray(ctx.ind[t, idx]), index=idx)
        w = target_weights(s, ind)
        w = restrict_shorts(w, pd.Series(np.asarray(ctx.se[t, idx]), index=idx))
        idxs.append(w.index.to_numpy().astype(np.int64))
        vals.append(w.to_numpy("float64"))
        valid.append(True)
    return WStar(idxs, vals, np.array(valid))


def run_path(ws: WStar, P: PathCtx, snap: str, mode: str, param, offset: int = 0) -> dict:
    """Daily path of one speed configuration.

    ``mode`` ``kappa`` (param = kappa) or ``reb`` (param = period, ``offset`` = first rebalance
    day).  The weight decided at close t (open t+1 for snap ``open``) is traded at t+1 and earns
    ``e(t, .)``; names with no price at t+1 are dropped at no cost; names with no return earn 0."""
    N, nT, i0 = P.N, P.nT, P.i0
    hs, e, ok = P.hs[snap], P.e[snap], P.ok[snap]
    borrow_daily = costs.BORROW_BP_PER_YEAR_BASE / 1e4 / costs.TRADING_DAYS_PER_YEAR
    fee = costs.FEES_BP_PER_SIDE
    out = {k: np.full(nT, np.nan) for k in ("gross", "tc", "bor", "to", "expo", "drop")}
    w_prev = np.zeros(N)
    for k in range(nT):
        t = i0 + k
        if not ws.valid[k]:
            w = w_prev.copy()
        elif mode == "kappa":
            w = w_prev * (1.0 - param)
            w[ws.idx[k]] += param * ws.val[k]
        else:
            if (k - offset) % param == 0:
                w = np.zeros(N)
                w[ws.idx[k]] = ws.val[k]
            else:
                w = w_prev.copy()
        bad = ~ok[t]
        out["drop"][k] = float(np.count_nonzero((w != 0) & bad))
        w[bad] = 0.0
        dw = w - w_prev
        dw[bad] = 0.0
        nz = np.flatnonzero(dw)
        if len(nz):
            q = np.abs(dw[nz])
            tc = float(q @ (hs[t, nz] + P.impk[t, nz] * np.sqrt(q) + fee)) / 1e4
            to = float(q.sum())
        else:
            tc, to = 0.0, 0.0
        short = float(-w[w < 0].sum())
        out["gross"][k] = float(w @ e[t])
        out["tc"][k] = tc
        out["bor"][k] = borrow_daily * short
        out["to"][k] = to
        out["expo"][k] = float(np.abs(w).sum())
        w_prev = w
    out["net"] = out["gross"] - out["tc"] - out["bor"]
    out["net2"] = out["gross"] - 2.0 * out["tc"] - out["bor"]
    inval = ~ws.valid
    for k in out:
        if k != "drop":
            out[k] = np.where(inval, np.nan, out[k])
    return out


def path_metrics(arr: dict, P: PathCtx, m0: np.ndarray | None) -> dict:
    res = {}
    for wn, mask in P.wmasks.items():
        net = arr["net"][mask]
        okd = np.isfinite(net)
        cm = float("nan")
        if m0 is not None:
            a, b = net, m0[mask]
            bo = np.isfinite(a) & np.isfinite(b)
            if bo.sum() >= 20 and a[bo].std() > 0 and b[bo].std() > 0:
                cm = float(np.corrcoef(a[bo], b[bo])[0, 1])
        res[wn] = {
            "gross": sharpe(arr["gross"][mask]),
            "net": sharpe(net),
            "net_2x": sharpe(arr["net2"][mask]),
            "turnover": float(np.nanmean(arr["to"][mask]) * 252.0 / 2.0)
            if okd.any()
            else float("nan"),
            "avg_gross": float(np.nanmean(arr["expo"][mask])) if okd.any() else float("nan"),
            "cost_bp_yr": float(np.nanmean((arr["tc"] + arr["bor"])[mask]) * 252.0 * 1e4)
            if okd.any()
            else float("nan"),
            "trade_cost_bp_yr": float(np.nanmean(arr["tc"][mask]) * 252.0 * 1e4)
            if okd.any()
            else float("nan"),
            "borrow_bp_yr": float(np.nanmean(arr["bor"][mask]) * 252.0 * 1e4)
            if okd.any()
            else float("nan"),
            "corr_m0": cm,
            "n_days": int(okd.sum()),
        }
    return res


METRIC_KEYS = (
    "gross",
    "net",
    "net_2x",
    "turnover",
    "avg_gross",
    "cost_bp_yr",
    "trade_cost_bp_yr",
    "borrow_bp_yr",
    "corr_m0",
)


def config_keys(cfg: Cfg) -> list[str]:
    return [f"k{k:g}" for k in KAPPAS] + [f"reb{p}" for p in cfg.reb_periods]


def run_config(ws: WStar, P: PathCtx, snap: str, key: str, m0: np.ndarray | None) -> dict:
    """One speed configuration (kappa path, or a periodic rebalance over all offsets)."""
    if key.startswith("k"):
        arr = run_path(ws, P, snap, "kappa", float(key[1:]))
        met = path_metrics(arr, P, m0)
        return {"metrics": met, "net": arr["net"], "drop": arr["drop"]}
    period = int(key[3:])
    offs, nets, drops = [], [], []
    for o in range(period):
        arr = run_path(ws, P, snap, "reb", period, o)
        offs.append(path_metrics(arr, P, m0))
        nets.append(arr["net"])
        drops.append(arr["drop"])
    med = {}
    for wn in P.wmasks:
        med[wn] = {
            mk: float(np.nanmedian([o[wn][mk] for o in offs]))
            if np.isfinite([o[wn][mk] for o in offs]).any()
            else float("nan")
            for mk in METRIC_KEYS
        }
        med[wn]["n_days"] = int(np.median([o[wn]["n_days"] for o in offs]))
    rec = np.array([o["recent"]["net"] for o in offs])
    fin = np.flatnonzero(np.isfinite(rec))
    pick = int(fin[np.argsort(rec[fin])[len(fin) // 2]]) if len(fin) else 0
    return {
        "metrics": med,
        "by_offset": {str(o): offs[o] for o in range(period)},
        "median_offset": pick,
        "net": nets[pick],
        "drop": drops[pick],
    }


def best_key(res: dict) -> str | None:
    best, bk = -np.inf, None
    for k, v in res.items():
        s = v["metrics"]["recent"]["net"]
        if np.isfinite(s) and s > best:
            best, bk = s, k
    return bk


# ---- object sources


def obj_column(cfg: Cfg, ctx: Ctx, obj: str, y: int, signs: dict) -> np.ndarray:
    names = object_names(ctx)
    if obj in names["A"]:
        return np.load(cfg.cache / f"A_{y}.npy", mmap_mode="r")[:, names["A"].index(obj)].astype(
            "float64"
        )
    if obj in names["B"]:
        v = np.load(cfg.cache / f"B_{y}.npy", mmap_mode="r")[:, names["B"].index(obj)].astype(
            "float64"
        )
        if obj in ("ON5", "ID5"):
            v = v * signs[obj]["sign"]
        return v
    if obj in names["D"]:
        return np.load(cfg.cache / f"D_{y}.npy", mmap_mode="r")[:, names["D"].index(obj)].astype(
            "float64"
        )
    if obj in names["C"]:
        return np.load(cfg.cache / f"C_{y}.npy", mmap_mode="r")[:, names["C"].index(obj)].astype(
            "float64"
        )
    raise KeyError(obj)


def dense_scores(cfg: Cfg, ctx: Ctx, obj: str, bucket: str, signs: dict) -> np.ndarray:
    S = np.full((ctx.T, ctx.N), np.nan)
    for y in ctx.years:
        rows = ctx.rows(y)
        di, si = rows["di"], rows["si"]
        if len(di) == 0:
            continue
        v = obj_column(cfg, ctx, obj, y, signs)
        m = bucket_mask(np.asarray(ctx.advr[di, si]), bucket, cfg.cut) & np.isfinite(v)
        S[di[m], si[m]] = v[m]
    return S


_W: dict = {}


def _init_worker(cfg: Cfg) -> None:
    ctx = Ctx(cfg)
    _W["cfg"], _W["ctx"] = cfg, ctx
    _W["P"] = PathCtx(cfg, ctx)
    _W["signs"] = load_signs(cfg)
    m0p = cfg.cache / "speed" / "m0_ref_k0.2.npy"
    _W["m0"] = np.load(m0p) if m0p.exists() else None


def speed_files(cfg: Cfg, obj: str, bucket: str) -> tuple[Path, Path]:
    d = cfg.cache / "speed"
    return d / f"{obj}__{bucket}.json", d / f"{obj}__{bucket}.npz"


def speed_job(args: tuple) -> str:
    obj, bucket = args
    cfg, ctx, P, signs, m0 = _W["cfg"], _W["ctx"], _W["P"], _W["signs"], _W["m0"]
    jpath, npath = speed_files(cfg, obj, bucket)
    if jpath.exists() and not cfg.force:
        return f"{obj}/{bucket}: cached"
    t0 = time.time()
    S = dense_scores(cfg, ctx, obj, bucket, signs)
    ws = wstar_from_dense(S, ctx, cfg)
    del S
    res = {k: run_config(ws, P, "close", k, m0) for k in config_keys(cfg)}
    star = best_key(res)
    out = {
        "configs": {
            k: {kk: vv for kk, vv in v.items() if kk in ("metrics", "by_offset", "median_offset")}
            for k, v in res.items()
        },
        "kappa_star": star,
        "valid_days": int(ws.valid.sum()),
    }
    nets = {f"net_{k}": v["net"] for k, v in res.items()}
    nets["drop_k1"] = res["k1"]["drop"]
    if bucket == "L12" and star is not None:
        moo = {}
        for k in dict.fromkeys(["k1", star]):
            r = run_config(ws, P, "open", k, m0)
            moo[k] = {
                kk: vv for kk, vv in r.items() if kk in ("metrics", "by_offset", "median_offset")
            }
            nets[f"moo_net_{k}"] = r["net"]
        out["moo"] = moo
    write_json(jpath, clean(out))
    np.savez(npath, **nets)
    return f"{obj}/{bucket}: {time.time() - t0:.0f}s star={star}"


def speed_jobs(cfg: Cfg, meta: dict) -> list[tuple[str, str]]:
    n = object_names(meta)
    all_obj = n["A"] + n["B"] + n["C"] + n["D"]
    jobs = [(o, "L12") for o in all_obj]
    extra = candidates_and_m0(meta)
    jobs += [(o, b) for b in ("L1", "L2", "L3") for o in extra]
    return jobs


def run_pool(cfg: Cfg, func, jobs: list, procs: int) -> list:
    if procs <= 1 or len(jobs) <= 1:
        _init_worker(cfg)
        return [func(j) for j in jobs]
    ctxm = mp.get_context("fork")
    with ctxm.Pool(procs, initializer=_init_worker, initargs=(cfg,)) as pool:
        return list(pool.imap_unordered(func, jobs))


def stage_speed(cfg: Cfg) -> None:
    c = cfg.cache
    if (c / "speed.done").exists() and not cfg.force:
        log("speed: done marker present, skipping")
        return
    event(cfg, "speed_start")
    ctx = Ctx(cfg)
    prepare_speed(cfg, ctx)
    (c / "speed").mkdir(exist_ok=True)
    # M0 reference path (L12, kappa 0.2, MOC) for the correlation column
    m0p = c / "speed" / "m0_ref_k0.2.npy"
    if not m0p.exists() or cfg.force:
        _init_worker(cfg)
        S = dense_scores(cfg, ctx, "m0_composite", "L12", _W["signs"])
        ws = wstar_from_dense(S, ctx, cfg)
        del S
        arr = run_path(ws, _W["P"], "close", "kappa", M0_KAPPA)
        np.save(m0p, arr["net"])
        log("speed: m0 reference path done")
    jobs = speed_jobs(cfg, ctx.meta)
    for msg in run_pool(cfg, speed_job, jobs, cfg.procs):
        log(f"speed: {msg}")
    (c / "speed.done").write_text(now_utc())


# ------------------------------------------------------------------------------ composites


def placebo_job(args: tuple) -> dict:
    comp, seed, key = args
    cfg, ctx, P, signs, m0 = _W["cfg"], _W["ctx"], _W["P"], _W["signs"], _W["m0"]
    S = dense_scores(cfg, ctx, comp, "L12", signs)
    perm = evaluate.permute_within_date(pd.DataFrame(S, copy=False), seed).to_numpy()
    del S
    ws = wstar_from_dense(perm, ctx, cfg)
    del perm
    r = run_config(ws, P, "close", key, m0)
    return {"comp": comp, "seed": seed, "recent_net": r["metrics"]["recent"]["net"]}


def blend_with_m0(
    m0: np.ndarray, comp: np.ndarray, dates: pd.DatetimeIndex, windows: dict, vol_window: int
) -> dict:
    """Monthly inverse 63-day-volatility blend of two daily net series (weights fixed on the first
    session of each month from the preceding ``vol_window`` observations)."""
    n = len(dates)
    w_m0 = np.full(n, 0.5)
    month = dates.year * 100 + dates.month
    cur = 0.5
    for i in range(n):
        if i == 0 or month[i] != month[i - 1]:
            lo = max(0, i - vol_window)
            a, b = m0[lo:i], comp[lo:i]
            a, b = a[np.isfinite(a)], b[np.isfinite(b)]
            if len(a) >= 30 and len(b) >= 30 and a.std() > 0 and b.std() > 0:
                ia, ib = 1.0 / a.std(), 1.0 / b.std()
                cur = ia / (ia + ib)
            else:
                cur = 0.5
        w_m0[i] = cur
    blend = w_m0 * m0 + (1.0 - w_m0) * comp
    out = {}
    for wn in ("recent", "stress"):
        a, b = windows[wn]
        mask = np.asarray((dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b)))
        okd = mask & np.isfinite(blend) & np.isfinite(m0) & np.isfinite(comp)
        if okd.sum() < 20:
            out[wn] = {
                "sharpe_blend": float("nan"),
                "sharpe_m0_scaled": float("nan"),
                "n_days": int(okd.sum()),
            }
            continue
        bl, mz = blend[okd], m0[okd]
        scale = bl.std(ddof=1) / mz.std(ddof=1)
        out[wn] = {
            "sharpe_blend": sharpe(bl),
            "sharpe_m0_scaled": sharpe(mz * scale),
            "sharpe_comp": sharpe(comp[okd]),
            "blend_vol_ann": float(bl.std(ddof=1) * math.sqrt(252.0)),
            "blend_mean_ann": float(bl.mean() * 252.0),
            "m0_scaled_mean_ann": float((mz * scale).mean() * 252.0),
            "mean_w_m0": float(w_m0[okd].mean()),
            "n_days": int(okd.sum()),
        }
    return out


def export_intermediate(cfg: Cfg) -> None:
    """Small copy of the measure / speed / composites outputs so the report can be rebuilt without
    the multi-GB grids (written to ``<iter_dir>/intermediate``; not a deliverable)."""
    import shutil

    dst = cfg.iter_dir / "intermediate"
    dst.mkdir(parents=True, exist_ok=True)
    c = cfg.cache
    for f in sorted(c.glob("ic_*.npz")) + [
        c / n
        for n in (
            "drops.npz",
            "signs.json",
            "events.jsonl",
            "meta.json",
            "composite_meta.json",
            "composites_post.json",
            "D.npy",
            "spy.npz",
        )
    ]:
        if f.exists():
            shutil.copy2(f, dst / f.name)
    if (c / "speed").exists():
        shutil.copytree(c / "speed", dst / "speed", dirs_exist_ok=True)


def stage_composites(cfg: Cfg) -> None:
    c = cfg.cache
    if (c / "composites.done").exists() and not cfg.force:
        log("composites: done marker present, skipping")
        return
    event(cfg, "composites_start")
    ctx = Ctx(cfg)
    P = PathCtx(cfg, ctx)
    m0 = np.load(c / "speed" / "m0_ref_k0.2.npy")
    cmeta = json.loads((c / "composite_meta.json").read_text())
    jobs, stars = [], {}
    for comp in OBJ_C:
        jp, _ = speed_files(cfg, comp, "L12")
        stars[comp] = json.loads(jp.read_text())["kappa_star"]
        if stars[comp] is None:
            continue
        for seed in range(1, cfg.n_seeds + 1):
            jobs.append((comp, seed, stars[comp]))
    res = run_pool(cfg, placebo_job, jobs, cfg.procs)
    out = {}
    for comp in OBJ_C:
        jp, npz = speed_files(cfg, comp, "L12")
        sj = json.loads(jp.read_text())
        key = stars[comp]
        entry = {"kappa_star": key, "first_valid_date": cmeta["first_valid_date"].get(comp)}
        if key is None:
            out[comp] = entry
            continue
        real = sj["configs"][key]["metrics"]["recent"]["net"]
        real = float("nan") if real is None else float(real)
        vals_arr = np.array(
            [
                np.nan if v is None else v
                for v in [
                    r["recent_net"]
                    for r in sorted((r for r in res if r["comp"] == comp), key=lambda r: r["seed"])
                ]
            ]
        )
        better = int(np.sum(vals_arr > real)) if np.isfinite(real) else None
        entry["placebo"] = {
            "seeds": list(range(1, len(vals_arr) + 1)),
            "recent_net_sharpe": [None if not np.isfinite(v) else float(v) for v in vals_arr],
            "real_recent_net_sharpe": real,
            "n_placebo_above_real": better,
            "rank_of_real": (1 + better) if better is not None else None,
            "of": int(len(vals_arr)) + 1,
            "real_above_all": bool(better == 0 and np.isfinite(vals_arr).all())
            if better is not None
            else False,
        }
        net = np.load(npz)[f"net_{key}"]
        entry["blend_with_m0"] = blend_with_m0(m0, net, P.dates, cfg.windows, cfg.blend_vol_window)
        s = pd.Series(net, index=P.dates)
        zero = pd.Series(0.0, index=P.dates)
        for tc in cfg.dsr_trials:
            try:
                dsr = evaluate.deflated_sharpe(s, zero, cfg.dsr_window, trial_count=tc)
            except Exception as exc:  # report, never hide
                dsr = f"error: {type(exc).__name__}: {exc}"
            entry[f"dsr_{tc}"] = dsr
        out[comp] = entry
    write_json(c / "composites_post.json", clean(out))
    (c / "composites.done").write_text(now_utc())
    export_intermediate(cfg)


# ------------------------------------------------------------------------------ report


def fmt(v, nd=3) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "NaN"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (int,)):
        return str(v)
    return f"{v:.{nd}f}"


def stage_report(cfg: Cfg) -> None:
    c = cfg.cache
    ctx = Ctx(cfg)
    names = object_names(ctx)
    signs = load_signs(cfg)
    store = load_ic_store(cfg)
    ident = json.loads((cfg.iter_dir / "identity.json").read_text())
    cmeta = json.loads((c / "composite_meta.json").read_text())
    post = json.loads((c / "composites_post.json").read_text())
    drops = np.load(c / "drops.npz")
    events = [
        json.loads(line) for line in (c / "events.jsonl").read_text().splitlines() if line.strip()
    ]
    cand = OBJ_B + OBJ_C
    full_buckets = set(candidates_and_m0(ctx.meta))
    all_obj = names["A"] + names["B"] + names["C"] + names["D"]
    group = {o: g for g, lst in names.items() for o in lst}

    objects, speed = {}, {}
    for o in all_obj:
        objects[o] = {"group": group[o], "windows": {}}
        buckets = list(BUCKETS) if o in full_buckets else ["L12"]
        for b in buckets:
            ic, pers = store[(o, b)]
            objects[o]["windows"][b] = {
                wn: ic_stats(ic, pers, ctx.window_mask(win)) for wn, win in cfg.windows.items()
            }
            jp, _ = speed_files(cfg, o, b)
            sj = json.loads(jp.read_text())
            speed.setdefault(o, {})[b] = sj

    # ---- promotion
    singles = []
    ps = []
    for o in OBJ_B:
        st = objects[o]["windows"]["L12"]["recent"]
        t = st["cic_2_6_t"]
        p = float(1.0 - norm.cdf(t)) if t is not None and np.isfinite(t) else 1.0
        ps.append(p)
        singles.append({"object": o, "cic_2_6": st["cic_2_6"], "t": t, "p_one_sided": p})
    qs = bh_qvalues(ps)
    for s, q in zip(singles, qs, strict=True):
        s["bh_q"] = float(q)
        s["promoted"] = bool(
            s["cic_2_6"] is not None
            and s["cic_2_6"] > 0
            and s["t"] is not None
            and s["t"] >= 2.0
            and q <= 0.10
        )
    comps = []
    for o in OBJ_C:
        st = objects[o]["windows"]["L12"]["recent"]
        info = bool(
            st["cic_2_6"] is not None
            and st["cic_2_6"] > 0
            and st["cic_2_6_t"] is not None
            and st["cic_2_6_t"] >= 2.0
        )
        pl = post[o].get("placebo")
        key = post[o].get("kappa_star")
        net_star = speed[o]["L12"]["configs"][key]["metrics"]["recent"]["net"] if key else None
        net_ok = bool(
            info
            and net_star is not None
            and net_star > 0
            and pl is not None
            and pl["real_above_all"]
        )
        comps.append(
            {
                "object": o,
                "information_ok": info,
                "net_ok": net_ok,
                "kappa_star": key,
                "recent_net_sharpe_at_kappa_star": net_star,
            }
        )
    flips = [
        o
        for o in all_obj
        if (
            objects[o]["windows"]["L12"]["stress"]["cic_2_6_t"] is not None
            and objects[o]["windows"]["L12"]["stress"]["cic_2_6_t"] <= -2.0
        )
    ]
    any_promo = any(s["promoted"] for s in singles) or any(cx["information_ok"] for cx in comps)
    status = "measured_promotions" if any_promo else "measured_no_promotion"
    promotion = {
        "singles": singles,
        "composites": comps,
        "stress_sign_flip": flips,
        "rule": "composite promoted when information_ok (net_ok is the stricter subset)",
    }

    # ---- data checks
    def stat_w(arr, mask):
        a = arr[mask]
        a = a[np.isfinite(a)]
        return {
            "median": float(np.median(a)) if len(a) else None,
            "max": float(a.max()) if len(a) else None,
        }

    dc = {
        "n_library_columns": len(names["A"]),
        "library_columns": names["A"],
        "adv_median_by_bucket": ctx.meta["adv_median_by_bucket"],
        "adv_monotone": ctx.meta["adv_monotone"],
        "vshk_coverage_by_year": ctx.meta["vshk_coverage_by_year"],
        "rows_by_year": ctx.meta["rows_by_year"],
        "max_trade_date_read": ctx.meta["max_trade_date_read"],
        "max_trade_date_read_overall": max(ctx.meta["max_trade_date_read"].values()),
        "no_return_names_per_day": {
            wn: {
                "lag1": stat_w(drops["drop_lag1"], ctx.window_mask(win)),
                "lag2": stat_w(drops["drop_lag2"], ctx.window_mask(win)),
            }
            for wn, win in cfg.windows.items()
        },
        "untradable_position_names_per_day_k1": {},
    }
    P_dates = ctx.D[ctx.i0 : ctx.i1 + 1]
    for wn, win in cfg.windows.items():
        wm = np.asarray((P_dates >= pd.Timestamp(win[0])) & (P_dates <= pd.Timestamp(win[1])))
        d = np.load(speed_files(cfg, "m0_composite", "L12")[1])["drop_k1"]
        dc["untradable_position_names_per_day_k1"][wn] = {"m0_composite": stat_w(d, wm)}
    dc["max_trade_date_ok"] = bool(dc["max_trade_date_read_overall"] <= cfg.last_data)

    first_touch = next(
        (e["utc"] for e in events if e["event"] == "recent_window_first_touch"), None
    )
    signs_out = dict(signs)
    signs_out["first_recent_window_touch_utc"] = first_touch
    signs_out["fixed_before_recent"] = bool(first_touch is None or signs["fixed_at"] < first_touch)

    m0ref = np.load(c / "speed" / "m0_ref_k0.2.npy")
    m0_reference = {
        wn: {
            "net_sharpe": sharpe(
                m0ref[
                    (np.asarray((P_dates >= pd.Timestamp(w[0])) & (P_dates <= pd.Timestamp(w[1]))))
                ]
            )
        }
        for wn, w in cfg.windows.items()
    }
    results = {
        "generated_utc": now_utc(),
        "m0_reference_L12_k0.2_MOC": m0_reference,
        "mechanical_status": status,
        "identity": ident,
        "signs": signs_out,
        "windows": cfg.windows,
        "objects": objects,
        "speed": speed,
        "composites": {
            o: {**post[o], "first_valid_date": cmeta["first_valid_date"].get(o)} for o in OBJ_C
        },
        "promotion": promotion,
        "data_checks": dc,
        "conventions": {
            "sharpe": "mean/sd(ddof=1)*sqrt(252), no risk-free deduction",
            "net_2x": "trading cost (spread+impact+fee) doubled, borrow unchanged",
            "reb_configs": "median over all offsets; by_offset lists every offset",
            "wf_warmup": "valid from first IC index + window + 1 sessions",
            "positions_outside_store": "names that left the signal store earn 0 return and keep decaying",
            "on5_id5_min_obs": "mean over 5 sessions with at least 4 finite",
        },
    }
    write_json(cfg.iter_dir / "results.json", clean(results))

    ledger = []
    for o in cand:
        for key in config_keys(cfg):
            m = speed[o]["L12"]["configs"][key]["metrics"]
            ledger.append(
                {
                    "candidate": o,
                    "speed": key,
                    "recent_net_sharpe": m["recent"]["net"],
                    "stress_net_sharpe": m["stress"]["net"],
                }
            )
    write_json(cfg.iter_dir / "trial-ledger.json", clean(ledger))
    write_report_md(cfg, results, cand, names, speed, objects, post)
    log(f"report: status {status}")


def write_report_md(cfg, R, cand, names, speed, objects, post) -> None:
    L = []
    add = L.append
    ob, sp = R["objects"], R["speed"]
    add("# P1 阶段 0：快信号衰减与交易速度（测量，不下结论）")
    add(
        f"生成：{R['generated_utc']}；状态 mechanical_status = {R['mechanical_status']}；数字来自 results.json。"
    )
    ident = R["identity"]
    add(
        "恒等检验（regimes 口径）最大绝对差："
        + "；".join(f"{k} {ident[k]['max_abs_diff']:.2e}" for k in cfg.identity_cols)
        + f"；通过 = {ident['passed']}"
    )
    add(
        f"符号（压力期 L12 CIC(2..6) 均值）：ON5 {R['signs']['ON5']['sign']:+d}（{fmt(R['signs']['ON5']['stress_cic_2_6_mean'], 4)}），"
        f"ID5 {R['signs']['ID5']['sign']:+d}（{fmt(R['signs']['ID5']['stress_cic_2_6_mean'], 4)}），固定于 {R['signs']['fixed_at']}"
    )

    def row(o, win):
        s = ob[o]["windows"]["L12"][win]
        sc = sp[o]["L12"]
        key = sc["kappa_star"]
        m = sc["configs"][key]["metrics"][win] if key else {}
        moo = (
            sc.get("moo", {}).get("k1", {}).get("metrics", {}).get(win, {}).get("net")
            if sc.get("moo")
            else None
        )
        prom = ""
        for sgl in R["promotion"]["singles"]:
            if sgl["object"] == o:
                prom = fmt(sgl["promoted"])
        for cx in R["promotion"]["composites"]:
            if cx["object"] == o:
                prom = f"信息 {fmt(cx['information_ok'])}/净值 {fmt(cx['net_ok'])}"
        return (
            f"| {o} | {fmt(s['cic_2_6'], 4)} | {fmt(s['cic_2_6_t'], 2)} | {fmt(s['h_np'], 0)} | "
            f"{fmt(s['F_MOC'], 2)} | {fmt(s['F_MOO'], 2)} | {key} | {fmt(m.get('net'), 2)} | "
            f"{fmt(m.get('net_2x'), 2)} | {fmt(m.get('corr_m0'), 2)} | {fmt(moo, 2)} | {prom} |"
        )

    hdr = "| 对象 | CIC(2..6) | NW t | h_np | F_MOC | F_MOO | κ* | 净夏普@κ* | 2倍成本 | 与M0相关 | MOO κ=1 净 | 晋级 |\n|---|---|---|---|---|---|---|---|---|---|---|---|"
    add("\n## 1 候选 10 个，近期窗 L12\n" + hdr)
    L.extend(row(o, "recent") for o in cand)
    add("\n## 2 候选 10 个，压力期 L12（诊断）\n" + hdr)
    L.extend(row(o, "stress") for o in cand)
    # 3 library
    hn = [ob[o]["windows"]["L12"]["recent"]["h_np"] for o in names["A"]]
    hn = np.array([np.nan if v is None else v for v in hn], dtype=float)
    stars = [sp[o]["L12"]["kappa_star"] for o in names["A"]]
    cnt = {}
    for s in stars:
        cnt[s] = cnt.get(s, 0) + 1
    add("\n## 3 快因子库 53 个（近期 L12）")
    add(
        f"h_np 中位数 {fmt(float(np.nanmedian(hn)) if np.isfinite(hn).any() else None, 1)}，"
        f"可算 {int(np.isfinite(hn).sum())}/{len(hn)}；κ* 分布 {cnt}"
    )

    def _t(o):
        v = ob[o]["windows"]["L12"]["recent"]["cic_2_6_t"]
        return v if v is not None and np.isfinite(v) else -99.0

    top = sorted(names["A"], key=lambda o: -_t(o))[:10]
    add("| 对象 | CIC(2..6) | t | h_np | κ* | 净夏普@κ* |\n|---|---|---|---|---|---|")
    for o in top:
        s = ob[o]["windows"]["L12"]["recent"]
        key = sp[o]["L12"]["kappa_star"]
        m = sp[o]["L12"]["configs"][key]["metrics"]["recent"] if key else {}
        add(
            f"| {o} | {fmt(s['cic_2_6'], 4)} | {fmt(s['cic_2_6_t'], 2)} | {fmt(s['h_np'], 0)} | {key} | {fmt(m.get('net'), 2)} |"
        )
    add(
        "\n## 4 m0_composite 与 9 个主题（近期 L12 净夏普）\n| 对象 | κ* | κ=1 | κ=0.25 | κ* 净 |\n|---|---|---|---|---|"
    )
    for o in names["D"]:
        sc = sp[o]["L12"]
        key = sc["kappa_star"]
        cf = sc["configs"]
        add(
            f"| {o} | {key} | {fmt(cf['k1']['metrics']['recent']['net'], 2)} | {fmt(cf['k0.25']['metrics']['recent']['net'], 2)} | "
            f"{fmt(cf[key]['metrics']['recent']['net'], 2) if key else 'NaN'} |"
        )
    add(
        "\n## 5 候选与 m0 按档（近期：CIC(2..6)/t/κ*/净夏普@κ*）\n| 对象 | L1 | L2 | L3 |\n|---|---|---|---|"
    )
    for o in cand + ["m0_composite"]:
        cells = []
        for b in ("L1", "L2", "L3"):
            s = ob[o]["windows"][b]["recent"]
            sc = sp[o][b]
            key = sc["kappa_star"]
            m = sc["configs"][key]["metrics"]["recent"] if key else {}
            cells.append(
                f"{fmt(s['cic_2_6'], 4)}/{fmt(s['cic_2_6_t'], 1)}/{key}/{fmt(m.get('net'), 2)}"
            )
        add(f"| {o} | " + " | ".join(cells) + " |")
    add(
        "\n## 6 合成：安慰剂、与 M0 组合、DSR\n| 合成 | 有效起始 | κ* | 真实净 | 安慰剂名次 | 近期 blend/M0同波动 | 压力 blend/M0同波动 | DSR21 | DSR193 |\n|---|---|---|---|---|---|---|---|---|"
    )
    for o in OBJ_C:
        p = post[o]
        pl = p.get("placebo", {})
        bl = p.get("blend_with_m0", {})
        add(
            f"| {o} | {p.get('first_valid_date')} | {p.get('kappa_star')} | {fmt(pl.get('real_recent_net_sharpe'), 2)} | "
            f"{pl.get('rank_of_real')}/{pl.get('of')} | "
            f"{fmt(bl.get('recent', {}).get('sharpe_blend'), 2)}/{fmt(bl.get('recent', {}).get('sharpe_m0_scaled'), 2)} | "
            f"{fmt(bl.get('stress', {}).get('sharpe_blend'), 2)}/{fmt(bl.get('stress', {}).get('sharpe_m0_scaled'), 2)} | "
            f"{fmt(p.get('dsr_21'), 3)} | {fmt(p.get('dsr_193'), 3)} |"
        )
    dc = R["data_checks"]
    add("\n## 7 数据检查")
    add(
        f"- 库列数 {dc['n_library_columns']}；各档 dollar_adv_21 中位数 {dc['adv_median_by_bucket']}；单调 = {dc['adv_monotone']}"
    )
    add(
        f"- 读到的最大交易日 {dc['max_trade_date_read_overall']}（各表 {dc['max_trade_date_read']}）"
    )
    add(
        f"- VSHK 覆盖率（按年）{ {k: round(v, 3) for k, v in dc['vshk_coverage_by_year'].items()} }"
    )
    add(f"- 每日无次日收益的名字数（中位数/最大）：{dc['no_return_names_per_day']}")
    add(f"- 持仓名字次日无价（κ=1，m0）：{dc['untradable_position_names_per_day_k1']}")
    pr = R["promotion"]
    add("\n## 8 机械状态")
    add(f"- mechanical_status = {R['mechanical_status']}")
    add(
        "- 单信号："
        + "；".join(
            f"{s['object']} t={fmt(s['t'], 2)} q={fmt(s['bh_q'], 3)} 晋级={fmt(s['promoted'])}"
            for s in pr["singles"]
        )
    )
    add(
        "- 合成："
        + "；".join(
            f"{c['object']} 信息={fmt(c['information_ok'])} 净值={fmt(c['net_ok'])}"
            for c in pr["composites"]
        )
    )
    add(f"- 压力期状态翻转（t<=-2）：{pr['stress_sign_flip']}")
    add(
        "- 未做：无。窗口内 MDE 超过 0.01 的对象见 results.json 的 mde_cic_2_6（功效不足不算否定）。"
    )
    (cfg.iter_dir / "report.md").write_text("\n".join(L[:150]) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------ main

STAGES = ["build", "identity", "measure", "speed", "composites", "report"]


def run_stage(cfg: Cfg, stage: str) -> None:
    t0 = time.time()
    log(f"=== stage {stage} ===")
    {
        "build": stage_build,
        "identity": stage_identity,
        "measure": stage_measure,
        "speed": stage_speed,
        "composites": stage_composites,
        "report": stage_report,
    }[stage](cfg)
    log(f"=== stage {stage} done in {time.time() - t0:.0f}s ===")


def main(argv=None) -> None:
    import warnings

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    warnings.filterwarnings("ignore", category=UserWarning, module="scipy")
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default="all", choices=STAGES + ["all"])
    ap.add_argument("--cache-dir", default=str(ITER_DIR / "cache"))
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    cfg = Cfg(cache=Path(a.cache_dir), procs=a.procs, force=a.force)
    stages = STAGES if a.stage == "all" else [a.stage]
    for s in stages:
        run_stage(cfg, s)


if __name__ == "__main__":
    main()
