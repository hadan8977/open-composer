# ruff: noqa: E501
"""T-20261004-75 (D1): concentration and market-regime diagnostic for S1/S2/S3/C2/F1/F2/T-43.

Diagnostic only: no strategy, pipeline or authorization is changed. All numbers are written to
`results.json`; `report.md` is rendered from it.

Stages (each is a separate process so the panel load can be memory capped):
  extract  load the ETF close/open panel once (duckdb over data/sip/daily, ETF symbols only) into
           /tmp/t75/{close,open}.parquet (about 2.7k rows x 26 columns).
  run      read the cache and compute items 1-5, write results.json and report.md.
            --item3 skip  writes "item3": "skipped_memory" instead of re-running the engines.

Conventions: daily returns to 2026-09-15 (the end of the v1.2 book files and T-43) for every
object so the tables are comparable; Sharpe = mean(r - BIL) / std(r - BIL) * sqrt(252); regime
states are computed from data known at the previous close (shifted one session).
"""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "scripts" / "screen_batches"))

CACHE = Path("/tmp/t75")
OUT_DIR = ROOT / "reports/research/program/concentration-regimes-2026-10-06"
PROGRAM_RET = ROOT / "reports/research/program/allocation-dd30-2026-10-02/program_returns.parquet"
C2_REPAIRED = (
    ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.sip-repaired-20261002.parquet"
)
C2_PRE_REPAIR = ROOT / "reports/research/screens/h20260928_20_recent_opt/returns.parquet"
RECORD_CSV = ROOT / "reports/research/program/forward-record-2026-10-06/record.csv"
VIX_CSV = ROOT / "data/live/vix/VIXCLS.csv"
DATA_END = "2026-09-15"
WINDOWS = {
    "full": ("2017-10-02", DATA_END),
    "recent": ("2024-07-01", DATA_END),
    "stress": ("2018-01-01", "2023-12-31"),
}
MIN_STATE_DAYS = 60
NW_LAGS = 5
PURE_SEMIS = ("SMH", "SOXX", "SOXL", "USD")
#: embedded semiconductor look-through: symbol -> leverage of the XLK-like exposure
LOOKTHROUGH = {"XLK": 1.0, "TECL": 3.0}
#: semis share of XLK (strict; excludes optical LITE/COHR), from the 2026-10-02 SSGA holdings file,
#: see HOLDINGS below. Applied to every window as an upper-bound proxy (historical share was lower).
F_XLK_SEMIS = 0.4595
F_SENSITIVITY = (0.20, 0.30, F_XLK_SEMIS)
T43_WEIGHTS = {"S3": 0.60, "C2": 0.335, "F1": 0.025, "F2": 0.12, "BORROW": -0.08}

HOLDINGS = {
    "XLK": {
        "source": "https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/"
        "etfs/us/holdings-daily-us-en-xlk.xlsx (SSGA daily holdings file, 'As of 02-Oct-2026')",
        "top10": "NVDA 15.52, AAPL 13.35, MSFT 10.54, AMD 5.14, AVGO 4.63, MU 4.42, INTC 3.29, "
        "CSCO 2.45, LRCX 2.41, PLTR 2.41",
        "semis_names_sum_pct": 46.85,
        "semis_strict_sum_pct": 45.95,
        "semis_note": "sum of NVDA AMD AVGO MU INTC LRCX AMAT KLAC TXN MRVL ADI QCOM MPWR TER NXPI "
        "MCHP ON SWKS (strict, 45.95%); +LITE +COHR optical = 46.85%; memory/storage hardware "
        "SNDK STX WDC not counted. Sum of all weights 99.99%.",
    },
    "SMH": {
        "source": "https://stockanalysis.com/etf/smh/holdings/ (as of 2026-10-03)",
        "top10": "NVDA 19.14, TSM 9.24, AMD 5.57, AVGO 5.07, MU 4.78, AMAT 4.73, KLAC 4.65, "
        "INTC 4.61, TXN 4.61, LRCX 4.52 (top 10 = 66.93%, 26 holdings)",
        "semis_note": "SMH is a pure semiconductor fund: share set to 1.0.",
    },
    "TECL": {
        "source": "https://stockanalysis.com/etf/tecl/holdings/ (as of 2026-10-02)",
        "top10": "swap legs plus NVDA 10.86, AAPL 9.37 of NAV (3x the XLK-index weights)",
        "semis_note": "TECL tracks the Technology Select Sector index = XLK index; XLK semis "
        "share used with leverage 3.",
    },
    "not_covered": "QQQ/TQQQ/SPY/UPRO and the other sector SPDRs also hold semiconductors; their "
    "look-through is not included (待核对), so semis shares for S3 and C2 are lower bounds.",
}

# --------------------------------------------------------------------------------------
# pure statistics helpers
# --------------------------------------------------------------------------------------


def max_drawdown(ret: pd.Series) -> float:
    if len(ret) == 0:
        return float("nan")
    nav = (1.0 + ret).cumprod()
    peak = np.maximum.accumulate(np.concatenate([[1.0], nav.to_numpy()]))[1:]
    return float((nav.to_numpy() / peak - 1.0).min())


def sharpe_excess(ret: pd.Series, rf: pd.Series) -> float | None:
    ex = (ret - rf.reindex(ret.index).fillna(0.0)).dropna()
    if len(ex) < 2 or ex.std(ddof=1) <= 0:
        return None
    return float(ex.mean() / ex.std(ddof=1) * np.sqrt(252.0))


def window_slice(s: pd.Series, window: tuple[str, str]) -> pd.Series:
    return s.loc[window[0] : window[1]].dropna()


def perf(ret: pd.Series, rf: pd.Series) -> dict[str, Any]:
    n = int(len(ret))
    if n < 2:
        return {"n": n, "cagr": None, "ann_vol": None, "sharpe": None, "max_dd": None}
    nav_end = float((1.0 + ret).prod())
    return {
        "n": n,
        "cagr": nav_end ** (252.0 / n) - 1.0 if nav_end > 0 else -1.0,
        "ann_vol": float(ret.std(ddof=1) * np.sqrt(252.0)),
        "sharpe": sharpe_excess(ret, rf),
        "max_dd": max_drawdown(ret),
    }


def orthogonalize(x: pd.Series, on: pd.Series) -> pd.Series:
    """Residual of x regressed on [1, on] (same sample)."""
    d = pd.concat([x, on], axis=1).dropna()
    xa, oa = d.iloc[:, 0].to_numpy(), d.iloc[:, 1].to_numpy()
    A = np.column_stack([np.ones(len(oa)), oa])
    coef, *_ = np.linalg.lstsq(A, xa, rcond=None)
    return pd.Series(xa - A @ coef, index=d.index)


def ols_nw(y: np.ndarray, X: np.ndarray, lags: int = NW_LAGS) -> dict[str, Any]:
    """OLS with intercept; Newey-West (Bartlett) t-values. X is (n, k) without the intercept."""
    n = len(y)
    X1 = np.column_stack([np.ones(n), X])
    k = X1.shape[1]
    if n <= k + lags:
        return {"n": n, "beta": None, "t": None, "r2": None}
    xtx_inv = np.linalg.inv(X1.T @ X1)
    beta = xtx_inv @ X1.T @ y
    e = y - X1 @ beta
    u = X1 * e[:, None]
    meat = u.T @ u
    for lag in range(1, lags + 1):
        gam = u[lag:].T @ u[:-lag]
        meat += (1.0 - lag / (lags + 1.0)) * (gam + gam.T)
    cov = xtx_inv @ meat @ xtx_inv
    se = np.sqrt(np.diag(cov))
    sst = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - float((e**2).sum()) / sst if sst > 0 else None
    return {
        "n": n,
        "alpha_daily": float(beta[0]),
        "alpha_t": float(beta[0] / se[0]),
        "beta": [float(b) for b in beta[1:]],
        "t": [float(b / s) for b, s in zip(beta[1:], se[1:], strict=True)],
        "r2": r2,
    }


def exposure_regression(
    ret: pd.Series, spy: pd.Series, qqq: pd.Series, smh: pd.Series, window: tuple[str, str]
) -> dict[str, Any]:
    """ret ~ SPY + QQQ + SMH_orth (SMH orthogonalised to SPY inside the window), HAC t-values."""
    y = window_slice(ret, window)
    d = pd.concat([y, spy, qqq, smh], axis=1, join="inner").dropna()
    d.columns = ["y", "spy", "qqq", "smh"]
    d = d.loc[window[0] : window[1]]
    if len(d) < 30:
        return {"n": int(len(d)), "beta": None, "t": None, "r2": None}
    smh_o = orthogonalize(d["smh"], d["spy"])
    X = np.column_stack([d["spy"].to_numpy(), d["qqq"].to_numpy(), smh_o.to_numpy()])
    out = ols_nw(d["y"].to_numpy(), X)
    out["names"] = ["SPY", "QQQ", "SMH_orth_to_SPY"]
    spy_only = ols_nw(d["y"].to_numpy(), d[["spy"]].to_numpy())
    out["spy_only_beta"] = spy_only["beta"][0] if spy_only["beta"] else None
    out["spy_only_r2"] = spy_only["r2"]
    return out


# --------------------------------------------------------------------------------------
# regime states
# --------------------------------------------------------------------------------------


def state_labels(spy: pd.Series, smh: pd.Series, vix: pd.Series) -> pd.DataFrame:
    """State label per session, using only data up to the PREVIOUS close (shift(1)).

    spy/smh are close levels, vix is the VIX close; all on the same session index."""
    vix = vix.reindex(spy.index).ffill(limit=1)
    sma200 = spy.rolling(200).mean()
    out = pd.DataFrame(index=spy.index)
    out["spy_200d"] = np.where(spy > sma200, "above", "below")
    out.loc[sma200.isna(), "spy_200d"] = None
    out["vix"] = pd.cut(
        vix, [-np.inf, 15.0, 25.0, np.inf], labels=["<15", "15-25", ">25"], right=False
    )
    out["vix"] = out["vix"].astype("object")
    out.loc[vix.isna(), "vix"] = None
    spy_dd = spy / spy.cummax() - 1.0
    out["spy_dd10"] = np.where(spy_dd < -0.10, "dd>10%", "dd<=10%")
    rel = smh.pct_change(126) - spy.pct_change(126)
    out["smh_rel_6m"] = np.where(rel > 0, "pos", "neg")
    out.loc[rel.isna(), "smh_rel_6m"] = None
    smh_dd = smh / smh.cummax() - 1.0
    out["smh_dd20"] = np.where(smh_dd < -0.20, "dd>20%", "dd<=20%")
    return out.shift(1)


def state_table(
    ret: pd.Series, rf: pd.Series, labels: pd.DataFrame, window: tuple[str, str]
) -> dict[str, dict[str, Any]]:
    r = window_slice(ret, window)
    lab = labels.reindex(r.index)
    out: dict[str, dict[str, Any]] = {}
    for col in labels.columns:
        cells: dict[str, Any] = {}
        for value in sorted(lab[col].dropna().unique()):
            sub = r[lab[col] == value]
            n = int(len(sub))
            cell = {
                "n": n,
                "ann_return_arith": float(sub.mean() * 252.0) if n else None,
                "sharpe": sharpe_excess(sub, rf) if n >= 2 else None,
                "small_sample": n < MIN_STATE_DAYS,
            }
            cells[str(value)] = cell
        out[col] = cells
    return out


# --------------------------------------------------------------------------------------
# stress segments
# --------------------------------------------------------------------------------------

SEGMENTS: list[dict[str, Any]] = [
    {"id": "2018-Q4", "peak": ("2018-08-15", "2018-10-15"), "trough": ("2018-11-15", "2019-01-15")},
    {
        "id": "2020-covid",
        "peak": ("2020-02-01", "2020-03-01"),
        "trough": ("2020-03-01", "2020-04-15"),
    },
    {"id": "2022", "calendar": ("2022-01-01", "2022-12-31")},
    {
        "id": "2024-07-08",
        "peak": ("2024-06-25", "2024-07-31"),
        "trough": ("2024-07-15", "2024-08-15"),
    },
    {
        "id": "2025-04-tariff",
        "peak": ("2025-02-01", "2025-03-15"),
        "trough": ("2025-03-15", "2025-05-01"),
    },
    {"id": "2026-07", "calendar": ("2026-07-01", "2026-07-31")},
]


def resolve_segments(spy_close: pd.Series) -> list[dict[str, Any]]:
    return resolve_segments_for(spy_close, SEGMENTS)


def resolve_segments_for(
    spy_close: pd.Series, segments: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Segment boundaries from SPY's own close: peak = argmax in the peak search window, trough =
    argmin in the trough search window after the peak. Calendar segments use their dates and
    report SPY's high/low inside them. The first return day is the session after the peak."""
    idx = spy_close.index
    out = []
    for seg in segments:
        if "calendar" in seg:
            a, b = seg["calendar"]
            sub = spy_close.loc[a:b]
            first = sub.index[0]
            last = sub.index[-1]
            info = {
                "id": seg["id"],
                "kind": "calendar",
                "first_return_day": str(first.date()),
                "last_return_day": str(last.date()),
                "spy_high_in_window": str(sub.idxmax().date()),
                "spy_low_in_window": str(sub.idxmin().date()),
            }
        else:
            pa, pb = seg["peak"]
            ta, tb = seg["trough"]
            peak = spy_close.loc[pa:pb].idxmax()
            trough_pool = spy_close.loc[max(pd.Timestamp(ta), peak + pd.Timedelta(days=1)) : tb]
            trough = trough_pool.idxmin()
            first = idx[idx.get_loc(peak) + 1]
            info = {
                "id": seg["id"],
                "kind": "spy_peak_to_trough",
                "spy_peak_close_date": str(peak.date()),
                "spy_trough_close_date": str(trough.date()),
                "first_return_day": str(first.date()),
                "last_return_day": str(trough.date()),
            }
        out.append(info)
    return out


def segment_stats(ret: pd.Series, spy_ret: pd.Series, seg: dict[str, Any]) -> dict[str, Any]:
    a, b = seg["first_return_day"], seg["last_return_day"]
    r = ret.loc[a:b].dropna()
    s = spy_ret.loc[a:b].dropna()
    if len(r) < 2:
        return {
            "n": int(len(r)),
            "return": None,
            "max_dd": None,
            "spy_return": None,
            "spy_max_dd": None,
        }
    return {
        "n": int(len(r)),
        "return": float((1 + r).prod() - 1.0),
        "max_dd": max_drawdown(r),
        "spy_return": float((1 + s).prod() - 1.0),
        "spy_max_dd": max_drawdown(s),
    }


# --------------------------------------------------------------------------------------
# engines and contributions (frozen engines, reused unchanged)
# --------------------------------------------------------------------------------------


def contributions(
    weights: pd.DataFrame,
    leg_open: pd.DataFrame,
    leg_close: pd.DataFrame,
    scale: np.ndarray,
    cost_bps: float,
    cash_col: str,
) -> tuple[pd.DataFrame, pd.Series, pd.DataFrame]:
    """Per-symbol daily gross contribution, daily cost, and the held weight frame.

    Mirrors `run_h20260922_05_salvage.simulate` line by line; the test checks that
    sum(contrib) - cost reproduces its return series."""
    cols = list(weights.columns)
    cash_i = cols.index(cash_col)
    wb = weights.to_numpy(dtype=float)
    lo = leg_open[cols].to_numpy(dtype=float)
    lc = leg_close[cols].to_numpy(dtype=float)
    n = len(wb)
    contrib = np.zeros((n, len(cols)))
    held = np.zeros((n, len(cols)))
    cost = np.zeros(n)
    w_prev = np.zeros(len(cols))
    for i in range(n):
        m = scale[i]
        row = wb[i]
        risk = row.copy()
        risk[cash_i] = 0.0
        w = risk * m
        w[cash_i] = row[cash_i] + (1.0 - m) * risk.sum()
        contrib[i] = w_prev * lo[i] + w * lc[i]
        cost[i] = float(np.abs(w - w_prev).sum()) * cost_bps / 10_000.0
        held[i] = w
        w_prev = w
    return (
        pd.DataFrame(contrib, index=weights.index, columns=cols),
        pd.Series(cost, index=weights.index),
        pd.DataFrame(held, index=weights.index, columns=cols),
    )


def semis_decomposition(
    contrib: pd.DataFrame,
    cost: pd.Series,
    held: pd.DataFrame,
    smh_lo: pd.Series,
    smh_lc: pd.Series,
    f: float,
) -> pd.DataFrame:
    """Daily gross contribution of pure semis ETFs and of embedded semis in XLK/TECL.

    Embedded part = f * leverage * (w_prev * SMH open leg + w * SMH close leg): the SMH legs are
    the proxy for the semiconductor component's return. Approximation, not holdings-exact."""
    pure_cols = [c for c in PURE_SEMIS if c in contrib.columns]
    out = pd.DataFrame(index=contrib.index)
    out["gross"] = contrib.sum(axis=1)
    out["cost"] = cost
    out["pure_semis"] = contrib[pure_cols].sum(axis=1) if pure_cols else 0.0
    look = pd.Series(0.0, index=contrib.index)
    exp_pure = held[pure_cols].sum(axis=1) if pure_cols else pd.Series(0.0, index=contrib.index)
    exp_look = pd.Series(0.0, index=contrib.index)
    for sym, lev in LOOKTHROUGH.items():
        if sym not in held.columns:
            continue
        w = held[sym]
        w_prev = w.shift(1).fillna(0.0)
        look += f * lev * (w_prev * smh_lo + w * smh_lc)
        exp_look += f * lev * w
    out["lookthrough"] = look
    out["exp_pure"] = exp_pure
    out["exp_look"] = exp_look
    return out


def semis_share(dec: pd.DataFrame, window: tuple[str, str]) -> dict[str, Any]:
    d = dec.loc[window[0] : window[1]]
    gross = float(d["gross"].sum())
    pure = float(d["pure_semis"].sum())
    look = float(d["lookthrough"].sum())
    out = {
        "n": int(len(d)),
        "gross_contrib_sum": gross,
        "cost_sum": float(d["cost"].sum()),
        "pure_semis_sum": pure,
        "lookthrough_sum": look,
        "mean_weight_pure_semis": float(d["exp_pure"].mean()),
        "mean_weight_lookthrough": float(d["exp_look"].mean()),
    }
    if gross > 0:
        out["share_pure"] = pure / gross
        out["share_pure_plus_lookthrough"] = (pure + look) / gross
        out["over_half_theme_pure_plus_lookthrough"] = bool((pure + look) / gross > 0.5)
    else:
        out["share_pure"] = out["share_pure_plus_lookthrough"] = None
        out["over_half_theme_pure_plus_lookthrough"] = None
        out["note"] = "gross contribution sum <= 0: share undefined"
    return out


# --------------------------------------------------------------------------------------
# engine construction (lazy imports: heavy modules only for the run stage)
# --------------------------------------------------------------------------------------


@contextmanager
def menus_without(remove: set[str]):
    import run_h20260918_05_recent_menu as base

    orig = {k: list(v) for k, v in base.MENUS.items()}
    try:
        for k in list(base.MENUS):
            base.MENUS[k] = [s for s in orig[k] if s not in remove]
        yield
    finally:
        for k, v in orig.items():
            base.MENUS[k] = v


def sleeve_runs(close: pd.DataFrame, open_: pd.DataFrame, cost_bps: float = 10.0):
    """S1/S2/S3 net returns (frozen overlay engine) plus per-sleeve contributions."""
    import run_h20260922_05_salvage as salvage
    import run_h20260927_01_sleeve_combination as comb

    leg_open, leg_close = salvage.legs(close, open_)
    rets = comb.sleeve_returns(close, leg_open, leg_close, cost_bps)
    boost = salvage.boost_window(salvage.dip_signal(close), comb.S3_BOOST_HOLD)
    detail: dict[str, Any] = {}
    for key, tgt in (("s1", None), ("s2", comb.S2_TARGET), ("s3", comb.S3_TARGET)):
        w, sig = salvage.sleeve_weights(close, key)
        gross, _ = salvage.simulate(w, leg_open, leg_close, np.ones(len(close.index)), 0.0)
        if key == "s3":
            sc = salvage.vol_scale(close.index, sig, gross, tgt, boost, comb.S3_BOOST_TARGET)
        else:
            sc = salvage.vol_scale(close.index, sig, gross, tgt)
        c, cost, held = contributions(w, leg_open, leg_close, sc, cost_bps, salvage.CASH)
        detail[key.upper()] = {"contrib": c, "cost": cost, "held": held, "scale": sc}
    return {k.upper(): v for k, v in rets.items()}, detail, leg_open, leg_close


def c2_candidate(drop: tuple[str, ...] = ()):
    import h20260928_05_batch2 as b2
    import h20260928_20_recent_opt as r
    import screen_lane as lane

    universe = tuple(s for s in r.SECTOR_ETFS if s not in drop)
    eom_fn = r.make_eom_reversal_fn()
    sec_fn = r.make_sector_seasonality_fn(universe=universe)

    def fn(close: pd.DataFrame, asof: pd.Timestamp) -> dict[str, float]:
        if not b2._is_month_end(close.index, asof):
            return {}
        e_w = eom_fn(close, asof) or {}
        s_w = sec_fn(close, asof) or {}
        out: dict[str, float] = {}
        for sym, w in e_w.items():
            out[sym] = out.get(sym, 0.0) + 0.5 * w
        for sym, w in s_w.items():
            out[sym] = out.get(sym, 0.0) + 0.5 * w
        return out

    return lane.ScreenCandidate(
        id="C2" + ("_ex_" + "_".join(drop) if drop else ""),
        name="C2 variant",
        source_card="t75_diagnostic",
        universe=("SPY", *universe),
        freq="D",
        weights_fn=fn,
        signal_dates_fn=b2.month_end_signal_dates,
    )


def c2_run(close, leg_open, leg_close, drop: tuple[str, ...] = (), cost_bps: float = 10.0):
    import run_h20260922_05_salvage as salvage
    import screen_lane as lane

    cand = c2_candidate(drop)
    weights, _ = lane.weights_frame(close, cand, 0)
    scale = np.ones(len(close.index))
    ret, _turn = salvage.simulate(weights, leg_open, leg_close, scale, cost_bps)
    c, cost, held = contributions(weights, leg_open, leg_close, scale, cost_bps, salvage.CASH)
    return ret, {"contrib": c, "cost": cost, "held": held}


# --------------------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------------------


def stage_extract() -> int:
    import run_h20260922_05_salvage as salvage
    import screen_lane as lane
    import shadow_forward as sf

    c2 = sf.find_candidate(
        sf.load_candidate_module("scripts/screen_batches/h20260928_20_recent_opt.py"), "C2"
    )
    syms = sorted(
        set(salvage.symbols())
        | set(lane.batch_symbols([c2]))
        | {"SOXX", "SMH", "XLK", "XLC", "XLRE", "SPY", "QQQ", "BIL", "SHY", "TECL"}
    )
    close, open_ = sf.load_forward_panel(syms)
    CACHE.mkdir(parents=True, exist_ok=True)
    close.to_parquet(CACHE / "close.parquet")
    open_.to_parquet(CACHE / "open.parquet")
    print(close.shape, close.index.min(), close.index.max())
    return 0


def pct(x: float | None, nd: int = 1) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x * 100:.{nd}f}%"


def num(x: float | None, nd: int = 2) -> str:
    return "n/a" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"


def build_object_block(
    name: str,
    ret: pd.Series,
    rf: pd.Series,
    mkt: dict[str, pd.Series],
    labels: pd.DataFrame,
    segs: list[dict[str, Any]],
) -> dict[str, Any]:
    ret = ret.loc[: WINDOWS["full"][1]]
    block: dict[str, Any] = {
        "first_date": str(ret.index[0].date()),
        "last_date": str(ret.index[-1].date()),
        "performance": {},
        "regression": {},
        "states": {},
    }
    for wname, win in WINDOWS.items():
        block["performance"][wname] = perf(window_slice(ret, win), rf)
        block["regression"][wname] = exposure_regression(
            ret, mkt["spy"], mkt["qqq"], mkt["smh"], win
        )
        block["states"][wname] = state_table(ret, rf, labels, win)
    block["stress_segments"] = {s["id"]: segment_stats(ret, mkt["spy"], s) for s in segs}
    return block


def stage_run(item3: str) -> int:
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    from run_program_dd30_allocation import path as t43_path
    from run_program_dd30_allocation import realization_dated

    close = pd.read_parquet(CACHE / "close.parquet")
    open_ = pd.read_parquet(CACHE / "open.parquet")
    close.index = pd.to_datetime(close.index)
    open_.index = pd.to_datetime(open_.index)
    rf = (close["BIL"] / close["BIL"].shift(1) - 1.0).fillna(0.0)
    mkt = {k: close[k.upper()].pct_change() for k in ("spy", "qqq", "smh")}
    vix = pd.read_csv(VIX_CSV, parse_dates=["observation_date"], index_col=0)["VIXCLS"]
    vix = pd.to_numeric(vix, errors="coerce").dropna()
    labels = state_labels(close["SPY"], close["SMH"], vix)
    segs = resolve_segments(close["SPY"])

    # ---- engines (net 10 bp, close signal -> next open fill) ----
    s_rets, s_detail, leg_open, leg_close = sleeve_runs(close, open_)
    c2_ret, c2_detail = c2_run(close, leg_open, leg_close)
    c2_repaired = pd.read_parquet(C2_REPAIRED)["C2__o00__net10"]
    c2_repaired.index = pd.to_datetime(c2_repaired.index)

    books = {}
    for f in ("F1", "F2"):
        d = pd.read_parquet(ROOT / f"data/research/book_v12/A1_M0_U3000_{f}.parquet")
        series = realization_dated(d["net_pnl"] / 1e6)
        series.index = pd.to_datetime(series.index)
        books[f] = series
    prog = pd.read_parquet(PROGRAM_RET)["program_ret"]
    prog.index = pd.to_datetime(prog.index)

    series = {
        "S1": s_rets["S1"],
        "S2": s_rets["S2"],
        "S3": s_rets["S3"],
        "C2": c2_repaired.loc[: WINDOWS["full"][1]],
        "F1": books["F1"],
        "F2": books["F2"],
        "T43": prog,
    }

    results: dict[str, Any] = {
        "task": "T-20261004-75",
        "generated_at_utc": started,
        "conventions": {
            "windows": WINDOWS,
            "data_end": DATA_END,
            "sharpe": "mean(r - BIL)/std(r - BIL)*sqrt(252), daily, ddof=1",
            "regression": "r ~ 1 + SPY + QQQ + SMH_orth (SMH residual on SPY, inside the window); "
            f"Newey-West t, {NW_LAGS} lags; close-to-close ETF returns; raw (not excess) returns",
            "states": "computed from data known at the previous close (shift 1 session); VIX = FRED "
            "VIXCLS data/live/vix/VIXCLS.csv; SMH relative strength = 126-session return of SMH "
            "minus SPY; drawdowns from the running max since 2016-01-04 (panel start)",
            "state_cell_ann_return": "arithmetic mean daily return * 252 (cells are not contiguous)",
            "min_state_days": MIN_STATE_DAYS,
            "stress_segments": segs,
            "stress_segment_rule": "SPY close peak/trough within preset search windows; first "
            "return day is the session after the peak close; calendar segments use calendar dates",
            "semis_pure": list(PURE_SEMIS),
            "semis_lookthrough": {k: v for k, v in LOOKTHROUGH.items()},
            "f_xlk_semis": F_XLK_SEMIS,
            "holdings_sources": HOLDINGS,
            "holdings_fetched_utc": started,
        },
        "item3": "run" if item3 == "run" else "skipped_memory",
    }

    # ---- checks ----
    checks: dict[str, Any] = {}
    chk = (c2_ret.loc[:"2026-09-17"] - c2_repaired.loc[:"2026-09-17"]).abs()
    checks["c2_recompute_vs_repaired_max_abs_diff_to_2026-09-17"] = float(chk.max())
    for key in ("S1", "S2", "S3"):
        d = s_detail[key]
        recon = d["contrib"].sum(axis=1) - d["cost"]
        checks[f"{key}_contrib_sum_minus_cost_vs_engine_max_abs"] = float(
            (recon - s_rets[key]).abs().max()
        )
    d = c2_detail
    checks["C2_contrib_sum_minus_cost_vs_engine_max_abs"] = float(
        ((d["contrib"].sum(axis=1) - d["cost"]) - c2_ret).abs().max()
    )

    def t43_from(s3_series: pd.Series, c2_series: pd.Series = c2_repaired) -> pd.Series:
        frame = pd.DataFrame(
            {"S3": s3_series, "C2": c2_series, "F1": books["F1"], "F2": books["F2"], "CASH": rf}
        )
        frame = frame.loc[WINDOWS["full"][0] : WINDOWS["full"][1]].dropna()
        w = np.array(
            [
                T43_WEIGHTS["S3"],
                T43_WEIGHTS["C2"],
                T43_WEIGHTS["F1"],
                T43_WEIGHTS["F2"],
                0.0,
                T43_WEIGHTS["BORROW"],
            ]
        )
        return t43_path(w, frame.to_numpy(), frame.index, 0)

    t43_base = t43_from(s_rets["S3"])
    both = pd.concat([t43_base, prog], axis=1, join="inner").dropna()
    checks["t43_reconstruction_vs_program_returns_max_abs_diff"] = float(
        (both.iloc[:, 0] - both.iloc[:, 1]).abs().max()
    )

    c2_pre = pd.read_parquet(C2_PRE_REPAIR)["C2__o00__net10"]
    c2_pre.index = pd.to_datetime(c2_pre.index)
    both = pd.concat([t43_from(s_rets["S3"], c2_pre), prog], axis=1, join="inner").dropna()
    checks["t43_reconstruction_with_c2_from_returns_parquet_vs_program_returns_max_abs_diff"] = (
        float((both.iloc[:, 0] - both.iloc[:, 1]).abs().max())
    )
    checks["c2_repaired_vs_returns_parquet_max_abs_diff"] = float(
        (c2_repaired - c2_pre).abs().max()
    )

    rec = pd.read_csv(RECORD_CSV, parse_dates=["date"])
    name_map = {
        "S1": "S1",
        "S2": "S2",
        "S3": "S3",
        "C2": "C2",
        "F1": "V12F1",
        "F2": "V12F2",
        "T43": "T43",
    }
    xchk = {}
    for obj, cand in name_map.items():
        sub = rec[rec["candidate"] == cand].set_index("date")
        sub = sub[sub["segment"] != "paper"]["shadow_return"]
        mine = series[obj].reindex(sub.index)
        xchk[obj] = {
            "rows": int(sub.notna().sum()),
            "max_abs_diff_vs_record_shadow_return": float((mine - sub).abs().max())
            if sub.notna().any()
            else None,
        }
    checks["record_csv_cross_check"] = xchk
    results["checks"] = checks

    # ---- items 1, 4, 5 ----
    results["objects"] = {}
    for obj, ret in series.items():
        results["objects"][obj] = build_object_block(obj, ret, rf, mkt, labels, segs)

    # ---- extras: segment entry states, correlations, T-43 risk shares ----
    results["segment_entry_states"] = {
        sg["id"]: {
            col: (None if pd.isna(v) else str(v))
            for col, v in labels.loc[pd.Timestamp(sg["first_return_day"])].items()
        }
        for sg in segs
    }
    frame7 = pd.DataFrame(series).loc[WINDOWS["full"][0] : WINDOWS["full"][1]]
    results["correlations"] = {
        w: frame7.loc[win[0] : win[1]].corr().round(3).to_dict() for w, win in WINDOWS.items()
    }
    eng = pd.DataFrame(
        {"S3": s_rets["S3"], "C2": c2_repaired, "F1": books["F1"], "F2": books["F2"]}
    ).loc[WINDOWS["full"][0] : WINDOWS["full"][1]]
    eng = eng.dropna()
    wvec = pd.Series({k: T43_WEIGHTS[k] for k in eng.columns})
    risk: dict[str, Any] = {}
    for w, win in WINDOWS.items():
        e = eng.loc[win[0] : win[1]]
        port = (e * wvec).sum(axis=1)
        var = float(port.var(ddof=1))
        risk[w] = {k: float(wvec[k] * np.cov(e[k], port, ddof=1)[0, 1] / var) for k in eng.columns}
    results["t43_risk_share_fixed_target_weights"] = {
        "note": "w_i*cov(r_i, r_p)/var(r_p), fixed target weights S3 .60 C2 .335 F1 .025 F2 .12 "
        "(borrow cash leg excluded, no drift); T-30 reported S3 = 89%",
        **risk,
    }

    # ---- item 2 ----
    smh_lo, smh_lc = leg_open["SMH"], leg_close["SMH"]
    item2: dict[str, Any] = {}
    decs: dict[str, pd.DataFrame] = {}
    for key, det in {**s_detail, "C2": c2_detail}.items():
        dec = semis_decomposition(
            det["contrib"], det["cost"], det["held"], smh_lo, smh_lc, F_XLK_SEMIS
        )
        decs[key] = dec
        entry: dict[str, Any] = {w: semis_share(dec, win) for w, win in WINDOWS.items()}
        sens = {}
        for f in F_SENSITIVITY:
            dd = semis_decomposition(det["contrib"], det["cost"], det["held"], smh_lo, smh_lc, f)
            sens[f"f={f}"] = semis_share(dd, WINDOWS["recent"]).get("share_pure_plus_lookthrough")
        entry["recent_share_sensitivity_to_xlk_semis_share"] = sens
        item2[key] = entry
    # T-43: constant target weights x engine contributions (drift ignored; borrow cost excluded)
    t43 = pd.DataFrame(index=decs["S3"].index)
    for col in ("gross", "cost", "pure_semis", "lookthrough", "exp_pure", "exp_look"):
        t43[col] = T43_WEIGHTS["S3"] * decs["S3"][col] + T43_WEIGHTS["C2"] * decs["C2"][col]
    t43_entry = {w: semis_share(t43, win) for w, win in WINDOWS.items()}
    # denominator = sleeves S3+C2 only; express against the program's own return sum as well
    for w, win in WINDOWS.items():
        ps = window_slice(prog, win)
        pure = t43_entry[w]["pure_semis_sum"]
        look = t43_entry[w]["lookthrough_sum"]
        tot = float(ps.sum())
        t43_entry[w]["program_return_sum"] = tot
        t43_entry[w]["share_of_program_return_pure"] = pure / tot if tot > 0 else None
        t43_entry[w]["share_of_program_return_pure_plus_lookthrough"] = (
            (pure + look) / tot if tot > 0 else None
        )
    t43_entry["note"] = (
        "approximation: fixed target weights S3 0.60 and C2 0.335 times each sleeve's contribution "
        "(no monthly drift or rebalance cost, borrow cost excluded); F1/F2 stock-book semis share "
        "待核对. 'share_pure'/'share_pure_plus_lookthrough' use the S3+C2 gross sum as the "
        "denominator; 'share_of_program_return_*' use the program_returns.parquet return sum."
    )
    item2["T43"] = t43_entry
    for f in ("F1", "F2"):
        item2[f] = {
            "status": "待核对",
            "reason": "F1/F2 are stock-level long/short books; the files read here "
            "(data/research/book_v12/A1_M0_U3000_F*.parquet, attrib_M0_U3000.parquet) hold "
            "daily P&L and risk-model factor attribution, not per-stock holdings. The "
            "semiconductor exposure is measured by the SMH_orth regression beta instead.",
        }
    results["item2_semis_contribution"] = item2

    # ---- item 3 ----
    item3_res: dict[str, Any] = {}
    if item3 == "run":
        base_perf = {
            k: {w: perf(window_slice(series[k], win), rf) for w, win in WINDOWS.items()}
            for k in ("S1", "S2", "S3", "C2")
        }
        variants = {
            "ex_semis_etfs": (set(PURE_SEMIS), ()),
            "ex_semis_and_tech": ({*PURE_SEMIS, "XLK", "TECL"}, ("XLK",)),
        }
        t43_variant_s3: dict[str, pd.Series] = {}
        c2_var: dict[str, pd.Series] = {}
        for vname, (remove, c2_drop) in variants.items():
            with menus_without(remove):
                v_rets, _, _, _ = sleeve_runs(close, open_)
            c2_v, _ = (
                c2_run(close, leg_open, leg_close, drop=c2_drop) if c2_drop else (c2_ret, None)
            )
            t43_variant_s3[vname] = v_rets["S3"]
            c2_var[vname] = c2_v
            for key, vser in (
                ("S1", v_rets["S1"]),
                ("S2", v_rets["S2"]),
                ("S3", v_rets["S3"]),
                ("C2", c2_v),
            ):
                ent = item3_res.setdefault(key, {})
                ent["baseline"] = base_perf[key]
                ent[vname] = {
                    w: {
                        **perf(window_slice(vser, win), rf),
                        "sharpe_delta_vs_baseline": _delta(
                            perf(window_slice(vser, win), rf)["sharpe"], base_perf[key][w]["sharpe"]
                        ),
                    }
                    for w, win in WINDOWS.items()
                }
        # T-43 recomputed with the S3 variant (C2 kept at baseline for ex_semis_etfs)
        base_t43 = {w: perf(window_slice(t43_base, win), rf) for w, win in WINDOWS.items()}
        ent = item3_res.setdefault("T43", {"baseline_reconstructed": base_t43})
        for vname in variants:
            tv = t43_from(t43_variant_s3[vname])
            ent[vname] = {
                w: {
                    **perf(window_slice(tv, win), rf),
                    "sharpe_delta_vs_baseline": _delta(
                        perf(window_slice(tv, win), rf)["sharpe"], base_t43[w]["sharpe"]
                    ),
                }
                for w, win in WINDOWS.items()
            }
        ent["note"] = (
            "T-43 weights fixed at the registered S3 0.60 / C2 0.335 / F2 0.12 / F1 0.025 / borrow 0.08; only the S3 sleeve is swapped (C2 baseline kept)"
        )
        for f in ("F1", "F2"):
            item3_res[f] = {
                "status": "not_applicable",
                "reason": "stock-level books built from a 3000-name universe; there is no ETF "
                "menu to remove semiconductors from",
            }
        item3_res["variant_definitions"] = {
            "ex_semis_etfs": "remove SMH, SOXX, SOXL, USD from every menu (S1 and C2 hold none: unchanged)",
            "ex_semis_and_tech": "also remove XLK (S1, S2, C2 sector list) and TECL (S3)",
            "rules": "all other rules, overlays, targets and costs unchanged",
        }
    results["item3_ex_semis"] = item3_res

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "results.json").write_text(
        json.dumps(results, indent=1, default=float) + "\n", encoding="utf-8"
    )
    render_report(results)
    print("done", OUT_DIR)
    return 0


def _delta(a: float | None, b: float | None) -> float | None:
    return None if a is None or b is None else float(a - b)


# --------------------------------------------------------------------------------------
# report
# --------------------------------------------------------------------------------------

ORDER = ["S1", "S2", "S3", "C2", "F1", "F2", "T43"]


def render_report(res: dict[str, Any]) -> None:
    o = res["objects"]
    L: list[str] = []
    L.append("# 集中度和市场状态诊断（T-20261004-75，D1，半导体问题）\n")
    L.append(
        f"生成：{res['generated_at_utc']}。脚本 `scripts/concentration_regimes_t75.py`，数字全部来自同目录 "
        "`results.json`。只做诊断，不改任何策略、模拟盘或授权。\n"
    )
    L.append("## 数据口径\n")
    L.append(
        "- 日收益：S1/S2/S3 用冻结叠加层引擎（`run_h20260927_01_sleeve_combination.sleeve_returns`，"
        "净 10 bp、收盘信号次日开盘成交）在 SIP 修复后档案上重算；C2 用 "
        "`returns.sip-repaired-20261002.parquet` 的 `C2__o00__net10`；F1/F2 用 "
        "`data/research/book_v12/A1_M0_U3000_F*.parquet`（按实现日重新索引，与 T-43 同口径）；T-43 用 "
        "`allocation-dd30-2026-10-02/program_returns.parquet`。"
        "注意：brief 说 program_returns 含各子策略收益，实际只有 T-43 一列 `program_ret`，所以 S1–S3 要重算。\n"
        "- 窗口：全期 2017-10-02..2026-09-15，近期 2024-07-01..2026-09-15，压力期 2018-01-01..2023-12-31。"
        "所有对象截到 2026-09-15（v1.2 账本和 T-43 的末日），保证可比。\n"
        "- 夏普 = 日超额收益（减 BIL）均值/标准差×√252。状态用前一收盘已知的数据（滞后一个交易日）。"
        "VIX 取 FRED VIXCLS。回归：日收益对 SPY、QQQ 和对 SPY 正交化的 SMH，Newey-West（5 滞后）t 值。\n"
        f"- 持仓来源：XLK 取 SSGA 2026-10-02 官方持仓文件（半导体合计 {F_XLK_SEMIS * 100:.2f}%，严格口径，不含光模块 LITE/COHR）；"
        "SMH 取 stockanalysis.com 2026-10-03（前十大合计 66.93%）；TECL 为 XLK 指数三倍杠杆。"
        "该占比对全部窗口使用同一常数，对历史窗口偏高（上限）；近期窗口的占比敏感度见表 2 末列。"
        "QQQ/TQQQ/SPY/UPRO 和其他板块 ETF 里的半导体未计入（待核对），所以 S3、C2 的半导体占比是下限。\n"
    )
    c = res["checks"]
    L.append("### 自检\n")
    L.append(
        f"- C2 重算与修复后文件到 2026-09-17 的最大绝对差：{c['c2_recompute_vs_repaired_max_abs_diff_to_2026-09-17']:.2e}\n"
        f"- 贡献加总减成本与引擎收益的最大绝对差：S1 {c['S1_contrib_sum_minus_cost_vs_engine_max_abs']:.1e}，"
        f"S2 {c['S2_contrib_sum_minus_cost_vs_engine_max_abs']:.1e}，S3 {c['S3_contrib_sum_minus_cost_vs_engine_max_abs']:.1e}，"
        f"C2 {c['C2_contrib_sum_minus_cost_vs_engine_max_abs']:.1e}\n"
        "- T-43 用引擎收益重建与 program_returns 的最大绝对差："
        f"{c['t43_reconstruction_vs_program_returns_max_abs_diff']:.2e}（C2 取修复后文件）；C2 取 `returns.parquet` 时 "
        f"{c['t43_reconstruction_with_c2_from_returns_parquet_vs_program_returns_max_abs_diff']:.2e}。"
        "即 program_returns.parquet 里的 T-43 用的是 `returns.parquet` 的 C2，与修复后 C2 最大差 "
        f"{c['c2_repaired_vs_returns_parquet_max_abs_diff']:.4f}；T-43 行按该文件原样使用，表 3 的 T-43 变体用修复后 C2 重建，"
        "基线取同一重建，变化可比。\n"
        "- 与 T-70 `record.csv` 的 shadow_return 对照（最大绝对差）："
        + "，".join(
            f"{k} {v['max_abs_diff_vs_record_shadow_return']:.1e}"
            if v["max_abs_diff_vs_record_shadow_return"] is not None
            else f"{k} n/a"
            for k, v in c["record_csv_cross_check"].items()
        )
        + "\n"
    )

    L.append("## 表 1：暴露回归（r ~ SPY + QQQ + SMH 正交项；括号内为 NW t 值）\n")
    L.append(
        "| 对象 | 窗口 | 天数 | beta SPY | beta QQQ | beta SMH⊥ | R² | 仅 SPY 的 R² | 夏普 | CAGR | 最大回撤 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    for k in ORDER:
        for w in WINDOWS:
            g = o[k]["regression"][w]
            p = o[k]["performance"][w]
            if g.get("beta") is None:
                L.append(
                    f"| {k} | {w} | {g['n']} | n/a | n/a | n/a | n/a | n/a | n/a | n/a | n/a |"
                )
                continue
            b, t = g["beta"], g["t"]
            L.append(
                f"| {k} | {w} | {g['n']} | {b[0]:.2f} ({t[0]:.1f}) | {b[1]:.2f} ({t[1]:.1f}) | "
                f"{b[2]:.2f} ({t[2]:.1f}) | {g['r2']:.2f} | {g['spy_only_r2']:.2f} | "
                f"{num(p['sharpe'])} | {pct(p['cagr'])} | {pct(p['max_dd'])} |"
            )
    L.append("")

    L.append("## 表 2：按持仓算的半导体贡献（日收益算术加总，毛收益）\n")
    L.append(
        "纯半导体 = SMH/SOXX/SOXL/USD 的贡献；穿透 = XLK、TECL 里的半导体（占比×杠杆×SMH 收益近似）。"
        "占比 = 贡献加总 / 毛贡献加总。\n"
    )
    L.append(
        "| 对象 | 窗口 | 毛贡献加总 | 纯半导体 | 穿透 | 纯半导体占比 | 纯+穿透占比 | 超过一半 | 平均权重(纯) | 平均权重(穿透) | 近期占比对 XLK 半导体占比 0.20/0.30/0.46 的敏感度 |"
    )
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    it2 = res["item2_semis_contribution"]
    for k in ["S1", "S2", "S3", "C2", "T43"]:
        for w in WINDOWS:
            e = it2[k][w]
            sens = (
                it2[k].get("recent_share_sensitivity_to_xlk_semis_share", {}) if k != "T43" else {}
            )
            sens_s = "/".join(pct(v) for v in sens.values()) if (sens and w == "recent") else ""
            flag = e.get("over_half_theme_pure_plus_lookthrough")
            L.append(
                f"| {k} | {w} | {e['gross_contrib_sum']:.2f} | {e['pure_semis_sum']:.2f} | {e['lookthrough_sum']:.2f} | "
                f"{pct(e['share_pure'])} | {pct(e['share_pure_plus_lookthrough'])} | "
                f"{'是' if flag else ('否' if flag is not None else 'n/a')} | "
                f"{e['mean_weight_pure_semis']:.2f} | {e['mean_weight_lookthrough']:.2f} | {sens_s} |"
            )
    L.append("")
    L.append(
        "F1、F2：待核对（见 results.json `item2_semis_contribution.F1.reason`）。T-43 行是近似，见 `item2_semis_contribution.T43.note`。\n"
    )

    L.append("## 表 3：把半导体标的从可选菜单拿掉后的夏普变化\n")
    i3 = res["item3_ex_semis"]
    if res["item3"] != "run":
        L.append("item3: skipped_memory（本机可用内存不足，未重跑）。\n")
    else:
        L.append("| 对象 | 变体 | 窗口 | 基线夏普 | 变体夏普 | 变化 | 变体 CAGR | 变体最大回撤 |")
        L.append("|---|---|---|---|---|---|---|---|")
        for k in ["S1", "S2", "S3", "C2", "T43"]:
            ent = i3[k]
            basek = "baseline" if k != "T43" else "baseline_reconstructed"
            for v in ("ex_semis_etfs", "ex_semis_and_tech"):
                for w in WINDOWS:
                    b = ent[basek][w]["sharpe"]
                    x = ent[v][w]
                    L.append(
                        f"| {k} | {v} | {w} | {num(b)} | {num(x['sharpe'])} | {num(x['sharpe_delta_vs_baseline'])} | "
                        f"{pct(x['cagr'])} | {pct(x['max_dd'])} |"
                    )
        L.append("")
        L.append(
            "F1、F2：不适用（个股账本，没有可选菜单）。变体定义见 `item3_ex_semis.variant_definitions`。\n"
        )

    L.append("## 表 4：状态格夏普（天数 < 60 标“样本太小”；年化收益为算术均值×252）\n")
    labs = [
        ("spy_200d", "SPY 在 200 日线"),
        ("vix", "VIX 档"),
        ("spy_dd10", "SPY 回撤是否超 10%"),
        ("smh_rel_6m", "SMH 相对 SPY 6 个月强弱"),
        ("smh_dd20", "SMH 从高点回撤是否超 20%"),
    ]
    for w in WINDOWS:
        L.append(f"### 窗口 {w}\n")
        cols = ["对象"]
        cell_names: list[tuple[str, str]] = []
        for key, title in labs:
            vals = sorted(
                {v for k in ORDER for v in o[k]["states"][w][key].keys()},
                key=lambda s: {"<15": 0, "15-25": 1, ">25": 2}.get(s, 0) if key == "vix" else s,
            )
            for v in vals:
                cell_names.append((key, v))
                cols.append(f"{title}={v}")
        L.append("| " + " | ".join(cols) + " |")
        L.append("|" + "---|" * len(cols))
        for k in ORDER:
            row = [k]
            for key, v in cell_names:
                cell = o[k]["states"][w][key].get(v)
                if cell is None:
                    row.append("n/a")
                else:
                    tag = "样本太小" if cell["small_sample"] else ""
                    row.append(f"{num(cell['sharpe'])} ({cell['n']}d{', ' + tag if tag else ''})")
            L.append("| " + " | ".join(row) + " |")
        L.append("")

    L.append("## 表 5：压力片段\n")
    segs = res["conventions"]["stress_segments"]
    L.append("SPY 实际高低点（收盘）确定的片段边界：\n")
    for s in segs:
        if s["kind"] == "spy_peak_to_trough":
            L.append(
                f"- {s['id']}：SPY 高点收盘 {s['spy_peak_close_date']}，低点收盘 {s['spy_trough_close_date']}；"
                f"收益计自 {s['first_return_day']} 至 {s['last_return_day']}"
            )
        else:
            L.append(
                f"- {s['id']}：日历段 {s['first_return_day']} 至 {s['last_return_day']}；段内 SPY 最高收盘 "
                f"{s['spy_high_in_window']}，最低收盘 {s['spy_low_in_window']}"
            )
    L.append("")
    L.append(
        "| 片段 | SPY 收益 | SPY 最大回撤 | "
        + " | ".join(f"{k} 收益 / 最大回撤" for k in ORDER)
        + " |"
    )
    L.append("|" + "---|" * (3 + len(ORDER)))
    for s in segs:
        sid = s["id"]
        spy = o["S1"]["stress_segments"][sid]
        row = [sid, pct(spy["spy_return"]), pct(spy["spy_max_dd"])]
        for k in ORDER:
            st = o[k]["stress_segments"][sid]
            row.append(
                "无数据" if st["return"] is None else f"{pct(st['return'])} / {pct(st['max_dd'])}"
            )
        L.append("| " + " | ".join(row) + " |")
    L.append("")

    concl = Path("/tmp/t75/conclusion.md")
    L.append("## 结论\n")
    L.append(concl.read_text(encoding="utf-8") if concl.exists() else "（待写）\n")
    (OUT_DIR / "report.md").write_text("\n".join(L) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    if not argv or argv[0] not in ("extract", "run"):
        print(__doc__)
        return 2
    if argv[0] == "extract":
        return stage_extract()
    item3 = "skip" if "--item3" in argv and argv[argv.index("--item3") + 1] == "skip" else "run"
    return stage_run(item3)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
