"""Residual-IC batch screen of candidate signals for book v1.1 (T-20261002-24).

Brief ``reports/research/control/briefs/T-20261002-24.md``; preregistration
``reports/research/program/signal-screen-2026-10-02/prereg.md`` (committed before any candidate IC).
No backtest.  Reuses the machinery that built ``alpha/book_v1/formation_ic.parquet``
(``scripts/build_book_v1_alpha.py``, ``scripts/run_book_v1_stage2.py``): the same price panel, risk
model, universe flags, residual target, rank IC and M0 / M1 composites.  Before any candidate is
looked at, the stored theme / M0 / M1 formation ICs are recomputed and must match to 1e-9.

    scripts/run_capped.sh --mem 1.8G -- uv run python scripts/screen_book_signal_candidates.py
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import optimize as op  # noqa: E402
from open_composer.research.equity_book.panel import PricePanel  # noqa: E402
from open_composer.research.equity_book.risk import RiskModel  # noqa: E402
from open_composer.research.equity_book.signals import THEMES  # noqa: E402
from scripts.build_book_v1_alpha import (  # noqa: E402
    HORIZON,
    MIN_NAMES,
    OUT_DIR,
    UNIVERSES,
    factor_return_matrix,
    rank_ic,
    residual_target,
)
from scripts.run_book_v1_stage2 import FormationIC  # noqa: E402
from scripts.summarize_book_residual_ic import WINDOWS, nw_t  # noqa: E402

OUT = ROOT / "reports/research/program/signal-screen-2026-10-02"
PRED_DIR = ROOT / "reports/research/iterations/t20260930_17b_model_family_book/cache"
MODELS = ("LGBM", "XGB", "CAT")
EMBARGO_SESSIONS = 63
ALPHA158_DIR = ROOT / "data/features/alpha158"
OSAP_DIR = ROOT / "data/features/osap_price_broad"
DAILY_DIR = ROOT / "data/features/daily_broad"
FACTOR_SCREEN = ROOT / "reports/research/factor_screen/step13f_screen.parquet"
ALPHA158_MIN_FACTORS = 15
NEAR_HIGH_WINDOW, NEAR_HIGH_MIN_OBS = 252, 200
IC_OUT = ROOT / "data/research/equity_book/alpha/v1_1/formation_ic_candidates.parquet"
PLACEBO_DRAWS, PLACEBO_SEED_BASE = 100, 20261002
IDENTITY_TOL = 1e-9
_DAY = 1 << 20  # sort-key stride for (symbol code, day) keys

# ---------------------------------------------------------------------------
# pure rules (tested without data)
# ---------------------------------------------------------------------------


def asof_latest(
    codes: np.ndarray,
    days: np.ndarray,
    values: np.ndarray,
    q_codes: np.ndarray,
    q_days: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Per query (symbol code, day): the value of that symbol's latest row with ``day <= q_day``;
    NaN (age -1) when the symbol has no row on or before the day.  Never uses a later row.
    Returns (values, age_in_days)."""
    key = codes.astype("int64") * _DAY + days.astype("int64")
    order = np.argsort(key, kind="stable")
    ks = key[order]
    qk = q_codes.astype("int64") * _DAY + q_days.astype("int64")
    idx = np.searchsorted(ks, qk, side="right") - 1
    ok = idx >= 0
    j = order[np.where(ok, idx, 0)]
    ok &= codes[j] == q_codes
    out = np.where(ok, values[j].astype("float64"), np.nan)
    age = np.where(ok, q_days.astype("int64") - days[j].astype("int64"), -1)
    return out, age


def uniform_rank(x: np.ndarray) -> np.ndarray:
    """``(rank - 0.5) / n`` over the finite entries (average ranks); NaN stays NaN."""
    s = pd.Series(np.asarray(x, dtype="float64"))
    n = int(s.notna().sum())
    return ((s.rank(method="average") - 0.5) / n).to_numpy() if n else s.to_numpy()


def inverse_normal(u: np.ndarray) -> np.ndarray:
    inv = NormalDist().inv_cdf
    return np.array([inv(float(v)) if np.isfinite(v) else np.nan for v in u])


def score_ml_pv(preds: np.ndarray) -> np.ndarray:
    """``preds`` (n_members, n_models) as-of predictions (NaN = missing).  Per model the uniform
    rank within the universe, the mean over the models present, then the inverse normal."""
    u = np.column_stack([uniform_rank(preds[:, k]) for k in range(preds.shape[1])])
    with np.errstate(all="ignore"):
        m = np.nanmean(u, axis=1)
    return inverse_normal(m)


def score_alpha158(values: np.ndarray, min_factors: int = ALPHA158_MIN_FACTORS) -> np.ndarray:
    """``values`` (n_members, n_factors) already multiplied by the fixed screen sign.  Per factor
    the rank-normal score within the universe, then the mean over the available factors; NaN
    when fewer than ``min_factors`` are available."""
    z = np.column_stack(
        [
            op.rank_normal(pd.Series(values[:, k].astype("float64"))).to_numpy()
            for k in range(values.shape[1])
        ]
    )
    cnt = np.isfinite(z).sum(axis=1)
    with np.errstate(all="ignore"):
        m = np.nanmean(z, axis=1)
    return np.where(cnt >= min_factors, m, np.nan)


def incremental_residual(cand: np.ndarray, base: np.ndarray) -> np.ndarray:
    """Residual of the candidate's rank-normal score regressed (OLS with intercept) on the base
    composite's score over the rows where both are finite; NaN elsewhere."""
    c = np.asarray(cand, dtype="float64")
    b = np.asarray(base, dtype="float64")
    ok = np.isfinite(c) & np.isfinite(b)
    out = np.full(len(c), np.nan)
    if ok.sum() < 3:
        return out
    cz = op.rank_normal(pd.Series(c[ok])).to_numpy()
    x = np.column_stack([np.ones(ok.sum()), b[ok]])
    beta, *_ = np.linalg.lstsq(x, cz, rcond=None)
    out[ok] = cz - x @ beta
    return out


def series_stats(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype="float64")
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 3:
        return {"n": n}
    sd = float(x.std(ddof=1))
    return {
        "n": n,
        "mean_ic": float(x.mean()),
        "sd_ic": sd,
        "t": float(x.mean() / sd * np.sqrt(n)) if sd > 0 else float("nan"),
        "t_nw2": nw_t(x),
        "share_positive": float((x > 0).mean()),
    }


def admission(
    u3000: dict, k: int, placebo_p95: float, *, z_crit: dict[int, float] | None = None
) -> dict:
    """Mechanical admission rule of the preregistration (U3000 only)."""
    z = (z_crit or {3: 2.394, 4: 2.498, 5: 2.576})[k]
    a = u3000["ic"]["anchor"].get("t_nw2", float("nan"))
    checks = {
        "a_anchor_nw_t_ge_bonferroni": bool(a >= z),
        "b_stress_mean_ic_ge_0": bool(u3000["ic"]["stress"].get("mean_ic", float("nan")) >= 0),
        "c_corr_m1_lt_0.5": bool(u3000["corr_m1"]["all"] < 0.5),
        "d_incremental_anchor_nw_t_ge_2": bool(
            u3000["incremental"]["anchor"].get("t_nw2", float("nan")) >= 2.0
        ),
        "e_real_t_above_placebo_p95": bool(a > placebo_p95),
    }
    failing = [name for name, ok in checks.items() if not ok]
    return {
        "k": k,
        "bonferroni_z": z,
        "checks": checks,
        "status": "admitted" if not failing else "rejected",
        "failing": failing,
    }


# ---------------------------------------------------------------------------
# candidate inputs
# ---------------------------------------------------------------------------


def _read_rows(path: Path, columns: list[str], dates: list[pd.Timestamp]) -> pd.DataFrame:
    tbl = pq.read_table(path, columns=["symbol", "trade_date"] + columns)
    mask = pc.is_in(tbl["trade_date"], value_set=_ts_array(dates, tbl.schema.field("trade_date")))
    return tbl.filter(mask).to_pandas()


def _ts_array(dates: list[pd.Timestamp], field):
    import pyarrow as pa

    return pa.array(pd.DatetimeIndex(dates).to_numpy(), type=field.type)


def _by_year(dates: list[pd.Timestamp]) -> dict[int, list[pd.Timestamp]]:
    out: dict[int, list[pd.Timestamp]] = {}
    for d in dates:
        out.setdefault(d.year, []).append(d)
    return out


def load_ml_pv(
    fdates: list[pd.Timestamp], panel_dates: pd.DatetimeIndex
) -> tuple[pd.DataFrame, dict]:
    """As-of predictions of the three models on every formation date, plus the validity check:
    every fold's train_cutoff must be at least ``EMBARGO_SESSIONS`` sessions before the first date
    it predicts.  One model at a time (memory)."""
    meta: dict = {"models": {}, "valid": True, "invalid_reasons": []}
    ns_day = 86_400_000_000_000
    qd = np.array([d.value // ns_day for d in fdates], dtype="int64")
    all_codes: dict[str, int] = {}
    n_sym_by_model: dict[str, int] = {}
    # first pass: global symbol codes
    for m in MODELS:
        p = PRED_DIR / f"predictions_{m}_WX_H63.parquet"
        syms = pq.read_table(p, columns=["symbol"])["symbol"].unique().to_pylist()
        for s_ in syms:
            all_codes.setdefault(s_, len(all_codes))
        n_sym_by_model[m] = len(syms)
    n_sym = len(all_codes)
    q_codes = np.tile(np.arange(n_sym, dtype="int64"), len(fdates))
    q_days = np.repeat(qd, n_sym)
    inv = np.empty(n_sym, dtype=object)
    for s_, i in all_codes.items():
        inv[i] = s_
    out = pd.DataFrame(
        {
            "formation_date": np.repeat(pd.DatetimeIndex(fdates).to_numpy(), n_sym),
            "symbol": np.tile(inv, len(fdates)),
        }
    )
    for m in MODELS:
        p = PRED_DIR / f"predictions_{m}_WX_H63.parquet"
        tbl = pq.read_table(p, columns=["trade_date", "symbol", "prediction", "fold_id"])
        sym = tbl["symbol"].dictionary_encode().combine_chunks()
        gmap = np.array([all_codes[s_] for s_ in sym.dictionary.to_pylist()], dtype="int32")
        codes = gmap[sym.indices.to_numpy(zero_copy_only=False)]
        days = (
            tbl["trade_date"].cast("timestamp[ns]").to_numpy().astype("int64") // ns_day
        ).astype("int32")
        vals = tbl["prediction"].to_numpy().astype("float32")
        fold = tbl["fold_id"].to_numpy().astype("int32")
        del tbl, sym
        fm = json.loads((PRED_DIR / f"fold_meta_{m}_WX_H63.json").read_text())
        cutoff = {r["fold_id"]: pd.Timestamp(r["train_cutoff"]) for r in fm if "train_cutoff" in r}
        first = pd.Series(days).groupby(fold).min()
        gaps = {}
        for fid, d0 in first.items():
            c = cutoff.get(int(fid))
            if c is None:
                meta["valid"] = False
                meta["invalid_reasons"].append(f"{m}: fold {fid} has no fold_meta cutoff")
                continue
            d0 = pd.Timestamp(int(d0) * ns_day)
            gap = int(panel_dates.searchsorted(d0, "left") - panel_dates.searchsorted(c, "right"))
            gaps[int(fid)] = gap
            if gap < EMBARGO_SESSIONS:
                meta["valid"] = False
                meta["invalid_reasons"].append(
                    f"{m}: fold {fid} cutoff {c.date()} is {gap} < {EMBARGO_SESSIONS} sessions "
                    f"before its first date {d0.date()}"
                )
        meta["models"][m] = {
            "n_rows": int(len(vals)),
            "n_folds_used": len(gaps),
            "min_session_gap_cutoff_to_first_date": min(gaps.values()) if gaps else None,
            "date_min": str(pd.Timestamp(int(days.min()) * ns_day).date()),
            "date_max": str(pd.Timestamp(int(days.max()) * ns_day).date()),
        }
        v, age = asof_latest(codes, days, vals, q_codes, q_days)
        out[f"pred_{m}"] = v
        out[f"age_{m}"] = age
        del codes, days, vals, fold
    keep = np.isfinite(out[[f"pred_{m}" for m in MODELS]].to_numpy()).any(axis=1)
    out = out[keep].reset_index(drop=True)
    return out, meta


def alpha158_spec() -> tuple[list[str], dict[str, float]]:
    d = pd.read_parquet(FACTOR_SCREEN)
    p = d[d["fdr_pass"] & (d["library"] == "alpha158")]
    signs: dict[str, float] = {}
    for f, g in p.groupby("factor"):
        s = np.sign(g["ic_mean_full"].to_numpy())
        if not (s == s[0]).all():
            raise RuntimeError(f"alpha158 factor {f} has inconsistent screen signs")
        signs[str(f)] = float(s[0])
    return sorted(signs), signs


def load_alpha158(fdates: list[pd.Timestamp], signs: dict[str, float]) -> pd.DataFrame:
    parts = []
    for y, ds in _by_year(fdates).items():
        df = _read_rows(ALPHA158_DIR / f"{y}.parquet", sorted(signs), ds)
        for f, s in signs.items():
            df[f] = df[f].astype("float64") * s
        parts.append(df)
    return pd.concat(parts, ignore_index=True)


def load_low_max(fdates: list[pd.Timestamp]) -> pd.DataFrame:
    parts = []
    for y, ds in _by_year(fdates).items():
        df = _read_rows(OSAP_DIR / f"{y}.parquet", ["maxret"], ds)
        df["low_max"] = -df["maxret"].astype("float64")
        parts.append(df.drop(columns=["maxret"]))
    return pd.concat(parts, ignore_index=True)


def near_high_from_matrix(close: np.ndarray, p: int) -> np.ndarray:
    """``close[p] / max(close[p - 251 .. p])`` per column using rows <= p only; NaN with fewer
    than ``NEAR_HIGH_MIN_OBS`` finite closes in the window."""
    lo = max(0, p - NEAR_HIGH_WINDOW + 1)
    w = close[lo : p + 1]
    with np.errstate(all="ignore"):
        mx = np.nanmax(w, axis=0)
        out = close[p] / mx
    out[np.isfinite(w).sum(axis=0) < NEAR_HIGH_MIN_OBS] = np.nan
    return out


def load_near_high(
    fdates: list[pd.Timestamp], panel: PricePanel | None = None
) -> tuple[pd.DataFrame, dict]:
    """Close / 252-session max close from ``daily_broad`` close; also the same ratio from the
    research-panel close as a diagnostic."""
    files = sorted(DAILY_DIR.glob("[0-9]*.parquet"))
    cal = pd.DatetimeIndex(
        sorted(
            set(
                pd.DatetimeIndex(
                    np.concatenate(
                        [
                            pq.read_table(f, columns=["trade_date"])["trade_date"].to_numpy()
                            for f in files
                        ]
                    )
                )
            )
        )
    )
    codes: dict[str, int] = {}
    chunks = []
    for f in files:
        t = pq.read_table(f, columns=["symbol", "trade_date", "close"])
        sym = t["symbol"].dictionary_encode().combine_chunks()
        gmap = np.array(
            [codes.setdefault(s_, len(codes)) for s_ in sym.dictionary.to_pylist()], dtype="int32"
        )
        chunks.append(
            (
                gmap[sym.indices.to_numpy(zero_copy_only=False)],
                cal.get_indexer(pd.DatetimeIndex(t["trade_date"].to_numpy())).astype("int32"),
                t["close"].to_numpy().astype("float32"),
            )
        )
        del t, sym
    arr = np.full((len(cal), len(codes)), np.nan, dtype="float32")
    for c_, r_, v_ in chunks:
        arr[r_, c_] = v_
    del chunks
    syms = np.empty(len(codes), dtype=object)
    for s_, i in codes.items():
        syms[i] = s_
    rows = []
    for d in fdates:
        p = int(cal.get_indexer([d])[0])
        if p < 0:
            continue
        r = near_high_from_matrix(arr, p)
        rows.append(pd.DataFrame({"symbol": syms, "trade_date": d, "near_52w_high": r}))
    out = pd.concat(rows, ignore_index=True)
    del arr
    diag: dict = {"n_calendar_sessions": len(cal)}
    if panel is not None:
        pr_rows = []
        for d in fdates:
            p = int(panel.dates.get_indexer([d])[0])
            if p < 0:
                continue
            pr_rows.append(
                pd.DataFrame(
                    {
                        "symbol": panel.symbols,
                        "trade_date": d,
                        "panel": near_high_from_matrix(panel.close, p),
                    }
                )
            )
        pr = pd.concat(pr_rows, ignore_index=True)
        mg = out.merge(pr, on=["symbol", "trade_date"], how="inner").dropna()
        cors = [
            float(g["near_52w_high"].corr(g["panel"], method="spearman"))
            for _, g in mg.groupby("trade_date")
            if len(g) > 50
        ]
        diag["spearman_vs_panel_close_ratio_mean"] = float(np.mean(cors)) if cors else None
        diag["spearman_vs_panel_close_ratio_min"] = float(np.min(cors)) if cors else None
        diag["share_abs_diff_gt_1e-3"] = (
            float(((mg["near_52w_high"] - mg["panel"]).abs() > 1e-3).mean()) if len(mg) else None
        )
    return out, diag


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def _window_mask(dates: pd.DatetimeIndex, w: str) -> np.ndarray:
    a, b = WINDOWS[w]
    return (dates >= pd.Timestamp(a)) & (dates <= pd.Timestamp(b))


def window_stats(dates: pd.DatetimeIndex, ic: np.ndarray) -> dict:
    return {w: series_stats(ic[_window_mask(dates, w)]) for w in WINDOWS}


def window_means(dates: pd.DatetimeIndex, x: np.ndarray) -> dict:
    out = {"all": float(np.nanmean(x)) if np.isfinite(x).any() else float("nan")}
    for w in WINDOWS:
        v = x[_window_mask(dates, w)]
        out[w] = float(np.nanmean(v)) if np.isfinite(v).any() else float("nan")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT / "results.json"))
    ap.add_argument("--ic-out", default=str(IC_OUT))
    args = ap.parse_args()
    t_start = time.time()
    fic = pd.read_parquet(OUT_DIR / "formation_ic.parquet")
    fic["formation_date"] = pd.to_datetime(fic["formation_date"])
    fdates = sorted(fic["formation_date"].unique())
    fdates = [pd.Timestamp(d) for d in fdates]
    rm = RiskModel()
    panel = PricePanel.from_dir(start="2016-09-01")
    dates = panel.dates
    fr = factor_return_matrix(rm.factors)
    fic_obj = FormationIC(fic, dates)

    # ---- candidate raw inputs -------------------------------------------------------------
    t0 = time.time()
    ml_raw, ml_meta = load_ml_pv(fdates, dates)
    print(f"ml_pv loaded {time.time() - t0:.0f}s valid={ml_meta['valid']}", flush=True)
    names158, signs158 = alpha158_spec()
    a158_raw = load_alpha158(fdates, signs158)
    lm_raw = load_low_max(fdates)
    nh_raw, nh_diag = load_near_high(fdates, panel)
    print(f"raw inputs loaded {time.time() - t0:.0f}s", flush=True)
    raw = {
        "ml_pv": ml_raw.rename(columns={"formation_date": "trade_date"}),
        "alpha158_fdr": a158_raw,
        "low_max": lm_raw,
        "near_52w_high": nh_raw,
    }
    if not ml_meta["valid"]:
        raw.pop("ml_pv")
    grouped = {
        k: {d: g.set_index("symbol") for d, g in v.groupby("trade_date")} for k, v in raw.items()
    }
    del raw, ml_raw, a158_raw, lm_raw, nh_raw

    # ---- per formation date ---------------------------------------------------------------
    cand_names = list(grouped)
    store: dict[tuple[str, str], dict[str, list]] = {
        (u, c): {
            "date": [],
            "score": [],
            "y": [],
            "ic": [],
            "n": [],
            "cov": [],
            "m1": [],
            "m0": [],
            "inc": [],
        }
        for u in UNIVERSES
        for c in cand_names
    }
    ident: dict[str, list[float]] = {
        f"{u}/{s}": [] for u in UNIVERSES for s in ("value", "M0", "M1")
    }
    ident_theme_all: list[float] = []
    ml_age: list[float] = []
    me_ok = 0
    years = sorted({d.year for d in fdates})
    for year in years:
        th = pd.read_parquet(OUT_DIR / f"themes_{year}.parquet")
        th = th.sort_values(["trade_date", "symbol"], kind="stable")
        by_date = {d: g.set_index("symbol") for d, g in th.groupby("trade_date", sort=False)}
        del th
        for d in [x for x in fdates if x.year == year]:
            p = int(dates.get_indexer([d])[0])
            try:
                x_df, _, _ = rm.at(d, exact=True)
            except KeyError:
                continue
            gi = by_date.get(d)
            if gi is None:
                continue
            names = [s for s in x_df.index if panel.has(s)]
            cols = np.array([panel.col(s) for s in names], dtype=int)
            x = x_df.loc[names].to_numpy("float64")
            f_win = fr.reindex(dates[p + 1 : p + HORIZON]).to_numpy("float64")
            # sessions p + 1 .. p + 22 only; index -1 of the slice is the formation date p
            y = pd.Series(
                residual_target(
                    panel.open[p + 1 : p + HORIZON + 1][:, cols],
                    panel.close[p + 1 : p + HORIZON + 1][:, cols],
                    -1,
                    x,
                    f_win,
                ),
                index=names,
            )
            me_ok += 1
            for uname, ucol in UNIVERSES.items():
                members = gi.index[gi[ucol].to_numpy()].intersection(y.index)
                if len(members) < MIN_NAMES:
                    continue
                sub = gi.loc[members, list(THEMES)].astype("float64")
                yy = y.loc[members].to_numpy()
                eq = sub.mean(axis=1)
                m0z = op.rank_normal(eq).to_numpy()
                w, _, _ = fic_obj.m1_at(uname, p)
                m1z = op.rank_normal(pd.Series(sub.to_numpy() @ w, index=sub.index)).to_numpy()
                # identity check against the stored formation IC
                st = fic[(fic["formation_date"] == d) & (fic["universe"] == uname)].set_index(
                    "series"
                )["ic"]
                ident[f"{uname}/value"].append(
                    rank_ic(sub["value"].to_numpy(), yy)[0] - st["value"]
                )
                ident[f"{uname}/M0"].append(rank_ic(m0z, yy)[0] - st["M0"])
                ident[f"{uname}/M1"].append(rank_ic(m1z, yy)[0] - st["M1"])
                for t in THEMES:
                    ident_theme_all.append(rank_ic(sub[t].to_numpy(), yy)[0] - st[t])
                for c in cand_names:
                    rd = grouped[c].get(d)
                    if rd is None:
                        sc = np.full(len(members), np.nan)
                    else:
                        rr = rd.reindex(members)
                        if c == "ml_pv":
                            sc = score_ml_pv(rr[[f"pred_{m}" for m in MODELS]].to_numpy())
                            ages = rr[[f"age_{m}" for m in MODELS]].to_numpy()
                            ml_age.append(float(np.nanmean(np.where(ages >= 0, ages, np.nan))))
                        elif c == "alpha158_fdr":
                            sc = score_alpha158(rr[names158].to_numpy())
                        elif c == "low_max":
                            sc = op.rank_normal(rr["low_max"]).to_numpy()
                        else:
                            sc = op.rank_normal(rr["near_52w_high"]).to_numpy()
                    s = store[(uname, c)]
                    s["date"].append(d)
                    s["score"].append(sc)
                    s["y"].append(yy)
                    ic_, n_ = rank_ic(sc, yy)
                    s["ic"].append(ic_)
                    s["n"].append(n_)
                    s["cov"].append(float(np.isfinite(sc).mean()))
                    s["m1"].append(rank_ic(sc, m1z)[0])
                    s["m0"].append(rank_ic(sc, m0z)[0])
                    inc = incremental_residual(sc, m1z)
                    s["inc"].append(rank_ic(inc, yy)[0])
        print(f"{year}: done {time.time() - t_start:.0f}s", flush=True)
        del by_date

    ident_max = {k: float(np.nanmax(np.abs(v))) if v else None for k, v in ident.items()}
    ident_all_max = float(np.nanmax(np.abs(ident_theme_all)))
    identity = {
        "tolerance": IDENTITY_TOL,
        "max_abs_diff_vs_stored_formation_ic": ident_max,
        "max_abs_diff_all_nine_themes": ident_all_max,
        "n_formation_dates_recomputed": me_ok,
        "passed": bool(
            all(v is not None and v <= IDENTITY_TOL for v in ident_max.values())
            and ident_all_max <= IDENTITY_TOL
        ),
    }
    print("identity", json.dumps(identity), flush=True)
    results = {
        "generated_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "task": "T-20261002-24",
        "windows_formation_dates": WINDOWS,
        "identity_check": identity,
        "ml_pv_validity": ml_meta,
        "near_52w_high_diagnostic": nh_diag,
        "alpha158_factors_and_signs": signs158,
        "ml_pv_mean_age_days_of_asof_prediction": float(np.nanmean(ml_age)) if ml_age else None,
        "candidates": {},
    }
    if not identity["passed"]:
        results["status"] = "identity_check_failed_stop"
        Path(args.out).write_text(json.dumps(results, indent=1) + "\n")
        print("IDENTITY CHECK FAILED -- stopping", flush=True)
        return

    rows = [
        {"formation_date": d, "universe": u, "series": c, "ic": ic_, "n": int(n_)}
        for (u, c), s in store.items()
        for d, ic_, n_ in zip(s["date"], s["ic"], s["n"], strict=True)
    ]
    ic_df = pd.DataFrame(rows)
    ic_df["formation_date"] = pd.to_datetime(ic_df["formation_date"])
    ic_df["ic"] = ic_df["ic"].astype("float64")
    ic_df["n"] = ic_df["n"].astype("int64")
    ic_path = Path(args.ic_out)
    ic_path.parent.mkdir(parents=True, exist_ok=True)
    ic_df.to_parquet(ic_path, index=False)
    results["candidate_formation_ic_parquet"] = {
        "path": str(ic_path.relative_to(ROOT)),
        "rows": len(ic_df),
    }

    # ---- placebo --------------------------------------------------------------------------
    anchor_idx: dict[tuple[str, str], np.ndarray] = {}
    for key, s in store.items():
        dd = pd.DatetimeIndex(s["date"])
        anchor_idx[key] = np.flatnonzero(_window_mask(dd, "anchor"))
    placebo_t: dict[tuple[str, str], list[float]] = {k: [] for k in store}
    placebo_t_plain: dict[tuple[str, str], list[float]] = {k: [] for k in store}
    for s_ in range(PLACEBO_DRAWS):
        rng = np.random.default_rng(PLACEBO_SEED_BASE + s_)
        for key, s in store.items():
            ics = []
            for i in anchor_idx[key]:
                sc = s["score"][i]
                ics.append(rank_ic(sc[rng.permutation(len(sc))], s["y"][i])[0])
            st = series_stats(np.array(ics))
            placebo_t[key].append(st.get("t_nw2", float("nan")))
            placebo_t_plain[key].append(st.get("t", float("nan")))
    print(f"placebo done {time.time() - t_start:.0f}s", flush=True)

    # ---- assemble -------------------------------------------------------------------------
    tested = [c for c in cand_names]
    k = len(tested)
    for c in cand_names:
        entry: dict = {"status_input": "tested", "universes": {}}
        for uname in UNIVERSES:
            s = store[(uname, c)]
            dd = pd.DatetimeIndex(s["date"])
            ic = np.array(s["ic"], dtype="float64")
            inc = np.array(s["inc"], dtype="float64")
            pt = np.array(placebo_t[(uname, c)], dtype="float64")
            ptp = np.array(placebo_t_plain[(uname, c)], dtype="float64")
            real = series_stats(ic[_window_mask(dd, "anchor")])
            entry["universes"][uname] = {
                "n_formation_dates": len(dd),
                "ic": window_stats(dd, ic),
                "coverage": window_means(dd, np.array(s["cov"])),
                "corr_m1": window_means(dd, np.array(s["m1"])),
                "corr_m0": window_means(dd, np.array(s["m0"])),
                "incremental": window_stats(dd, inc),
                "placebo": {
                    "draws": PLACEBO_DRAWS,
                    "seed_base": PLACEBO_SEED_BASE,
                    "anchor_nw_t_p95": float(np.nanpercentile(pt, 95)),
                    "anchor_nw_t_mean": float(np.nanmean(pt)),
                    "anchor_nw_t_sd": float(np.nanstd(pt, ddof=1)),
                    "real_anchor_nw_t": real.get("t_nw2"),
                    "share_of_draws_below_real_nw_t": float(
                        np.mean(pt < real.get("t_nw2", np.nan))
                    ),
                    "anchor_plain_t_p95": float(np.nanpercentile(ptp, 95)),
                    "real_anchor_plain_t": real.get("t"),
                    "share_of_draws_below_real_plain_t": float(
                        np.mean(ptp < real.get("t", np.nan))
                    ),
                },
            }
        u = entry["universes"]["u3000"]
        entry["admission_u3000"] = admission(u, k, u["placebo"]["anchor_nw_t_p95"])
        results["candidates"][c] = entry
    results["k"] = k
    results["tested"] = tested
    results["not_tested"] = {
        "reg": "not_built: no implementation in scripts/ or open_composer/ (grep ben_rephael, "
        "earnings_gap, return_earnings_gap)"
    }
    if not ml_meta["valid"]:
        results["not_tested"]["ml_pv"] = "invalid: " + "; ".join(ml_meta["invalid_reasons"])
    results["elapsed_s"] = round(time.time() - t_start, 1)
    Path(args.out).write_text(json.dumps(results, indent=1) + "\n")
    print(
        json.dumps({c: v["admission_u3000"]["status"] for c, v in results["candidates"].items()}),
        flush=True,
    )


if __name__ == "__main__":
    main()
