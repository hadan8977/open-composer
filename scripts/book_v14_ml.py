#!/usr/bin/env python3
# ruff: noqa: E501
"""v1.4 ML composites (iteration ``t20261004_book_v14_ml``), Stage A: build / train / assemble / stage-a.

Contract (frozen): ``reports/research/iterations/t20261004_book_v14_ml/hypotheses.md`` sections 0-10.

``build``     (local)  features, weekly training table and refit schedule -> data/research/book_v14/inputs
``train``     (Modal)  one shard = one refit year; GBDT trio on y21_rank + DKKM random-feature SDF on r5,
                       plus the two within-date label-permutation leak checks
``assemble``  (local)  concatenate shards, build m2 / m0m2 / m0m3 -> data/research/book_v14/predictions.parquet
``stage-a``   (local)  simplified weekly gross long-short Sharpe gate -> stage_a.json / stage_a.md

Nothing is written under ``data/research/equity_book/`` (hash guarded).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from open_composer.research.equity_book import ml_composite as mc  # noqa: E402

EB = ROOT / "data/research/equity_book"
BASE = ROOT / "data/research/book_v14"
INPUTS = BASE / "inputs"
FEAT_DIR = INPUTS / "features"
PRED_DIR = BASE / "pred"
PRED_ALL = BASE / "predictions.parquet"
ITER = ROOT / "reports/research/iterations/t20261004_book_v14_ml"
CONTRACT_SHA256 = "af771470eaab998f0f2152d1f2e3e4cf8e9f45af5875a7bba0f8d71642fe99c0"

SIGNAL_COLS = [
    "bm",
    "ep",
    "sp",
    "cfp",
    "gp_at",
    "roe",
    "op_at",
    "neg_accruals",
    "neg_asset_growth",
    "neg_nsi_12m",
    "mom_12_1",
    "ind_mom_12_1",
    "resid_mom_12_1",
    "neg_beta_252",
    "neg_idio_vol_63",
    "sue_eps",
    "sue_rev",
    "cmp_opp_buy_60d",
    "nonplan_buy_mcap_60d",
    "neg_short_vol_ratio_21",
    "neg_si_shares",
    "seas_5y",
]
FEATURES = [*SIGNAL_COLS, "log_mcap"]  # K = 23
REFIT_YEARS = tuple(range(2019, 2027))
M3_SEED = 20261004
M3_N_FREQ = 2000
M3_GAMMAS = (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
PERM_SEED = 1
R5_CLIP = 0.5
LABEL_HORIZON = 21
WEEK = 5
WINDOWS = {
    "recent": ("2024-01-08", "2026-09-15"),
    "stress_ml": ("2019-01-02", "2023-08-31"),
    "full_ml": ("2019-01-02", "2026-09-15"),
}
CANDIDATES = ("m2", "m3", "m0m2", "m0m3")
BASELINE = "m0"
DIAGNOSTICS = ("lgbm", "xgb", "cat", "lgbm_perm", "m3_perm")
SCORES = (BASELINE, *CANDIDATES, *DIAGNOSTICS)
PERM_LIMITS = {"recent": 1.22, "stress_ml": 0.93}
PRED_COLS = ["lgbm", "xgb", "cat", "m3", "lgbm_perm", "m3_perm"]


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False, default=_json_default) + "\n")


def _json_default(o: Any) -> Any:
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.bool_):
        return bool(o)
    if isinstance(o, pd.Timestamp):
        return str(o.date())
    raise TypeError(type(o))


# --------------------------------------------------------------------------
# build
# --------------------------------------------------------------------------
def _beta_full(ctx: Any, t: pd.Timestamp) -> np.ndarray:
    px = ctx.px
    be, _ = ctx.ewma.at(t)
    out = np.full(px.N, np.nan)
    idx = px.symbols.get_indexer(be.index)
    ok = idx >= 0
    out[idx[ok]] = be.to_numpy("float64")[ok]
    return out


def _labels_for(ctx: Any, t: pd.Timestamp, p: int, symbols: pd.Index, horizon: int) -> np.ndarray:
    px = ctx.px
    full = mc.book_labels(px.C, px.spy_c, _beta_full(ctx, t), p, horizon)
    idx = px.symbols.get_indexer(symbols)
    return np.where(idx >= 0, full[np.clip(idx, 0, None)], np.nan)


def cmd_build(args: argparse.Namespace) -> None:
    import scripts.realism_ladder_book_ls as T25
    from scripts.run_book_v1_stage2 import AlphaSource

    ctx = T25.Context()
    px = ctx.px
    first = int(px.dates.searchsorted(pd.Timestamp(T25.START)))
    src = AlphaSource(ctx.themes, ctx.fic, "M0", "u3000")
    weekly = set(T25.decision_positions(px.T, first, px.T - 1, T25.WEEK, 0))
    last_label_pos = px.T - 1 - (LABEL_HORIZON + 1)
    years_arr = px.dates.year.to_numpy()
    FEAT_DIR.mkdir(parents=True, exist_ok=True)
    rows_per_year: dict[str, int] = {}
    members_by_year: dict[str, dict[str, float]] = {}
    coverage: dict[str, dict[str, float]] = {}
    weekly_parts: list[pd.DataFrame] = []
    last_date: pd.Timestamp | None = None
    all_members: list[int] = []
    members_from_2019: list[int] = []
    for year in sorted({int(y) for y in years_arr[first:]}):
        parts = []
        for p in range(first, px.T):
            if years_arr[p] != year:
                continue
            t = px.dates[p]
            th = ctx.themes.at(t)
            if th.empty:
                continue
            members = th.index[th["in_u3000"].to_numpy(bool)]
            state = type("S", (), {"pos": p})()
            m0 = src(t, state, members)
            parts.append(
                pd.DataFrame(
                    {
                        "trade_date": t,
                        "symbol": members.to_numpy(),
                        "m0": m0.to_numpy("float64"),
                        "pos": p,
                    }
                )
            )
        if not parts:
            continue
        base = pd.concat(parts, ignore_index=True)
        del parts
        n0 = len(base)
        sig = pd.read_parquet(
            EB / f"signals/{year}.parquet",
            columns=["trade_date", "symbol", "ind_code", *SIGNAL_COLS],
        ).drop_duplicates(["trade_date", "symbol"], keep="last")
        pan = pd.read_parquet(
            EB / f"panel/{year}.parquet", columns=["trade_date", "symbol", "mcap"]
        ).drop_duplicates(["trade_date", "symbol"], keep="last")
        df = base.merge(sig, on=["trade_date", "symbol"], how="left").merge(
            pan, on=["trade_date", "symbol"], how="left"
        )
        del sig, pan, base
        assert len(df) == n0
        df["log_mcap"] = np.log(df["mcap"].where(df["mcap"] > 0))
        df = df.drop(columns=["mcap"])
        df = mc.rank_standardize(df, FEATURES)
        df[FEATURES] = df[FEATURES].astype("float32")
        df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
        per_date = df.groupby("trade_date").size()
        members_by_year[str(year)] = {
            "min": int(per_date.min()),
            "median": float(per_date.median()),
            "n_dates": int(len(per_date)),
        }
        all_members.extend(per_date.tolist())
        if year >= 2019:
            members_from_2019.extend(per_date.tolist())
        rows_per_year[str(year)] = int(len(df))
        coverage[str(year)] = {c: float(df[c].notna().mean()) for c in FEATURES}
        last_date = df["trade_date"].max()
        out = df[["trade_date", "symbol", "ind_code", "m0", *FEATURES]]
        out.to_parquet(FEAT_DIR / f"{year}.parquet", index=False)
        sub = df[df["pos"].isin(weekly) & (df["pos"] <= last_label_pos)]
        for p, g in sub.groupby("pos", sort=True):
            t = g["trade_date"].iloc[0]
            y21 = _labels_for(ctx, t, int(p), pd.Index(g["symbol"]), LABEL_HORIZON)
            r5 = _labels_for(ctx, t, int(p), pd.Index(g["symbol"]), 5)
            y_dm = np.asarray(mc.industry_demean(y21, g["ind_code"].to_numpy()), dtype="float64")
            y_rank = pd.Series(y_dm).rank(pct=True, method="average").to_numpy()
            w = g[["trade_date", "pos", "symbol", "ind_code", *FEATURES]].copy()
            w["y21_rank"] = y_rank
            w["r5"] = np.clip(r5, -R5_CLIP, R5_CLIP)
            weekly_parts.append(w)
        log(f"build {year}: {len(df)} rows, {len(per_date)} dates")
        del df, out, sub
    tw = pd.concat(weekly_parts, ignore_index=True)
    tw.to_parquet(INPUTS / "train_weekly.parquet", index=False)
    # refit schedule
    dates = px.dates
    refits: dict[str, dict[str, Any]] = {}
    pos_by_year = {y: int(np.flatnonzero(years_arr == y)[0]) for y in REFIT_YEARS}
    for y in REFIT_YEARS:
        rp = pos_by_year[y]
        nxt = pos_by_year.get(y + 1)
        refits[str(y)] = {
            "refit_date": str(dates[rp].date()),
            "refit_pos": rp,
            "last_train_pos": rp - mc.EMBARGO_GAP,
            "predict_from": str(dates[rp].date()),
            "predict_from_pos": rp,
            "predict_to_exclusive": None if nxt is None else str(dates[nxt].date()),
            "predict_to_pos_exclusive": px.T if nxt is None else nxt,
        }
    write_json(INPUTS / "refits.json", refits)
    embargo = {}
    for y, r in refits.items():
        tp = tw.loc[tw["pos"] <= r["last_train_pos"], "pos"].to_numpy()
        embargo[y] = {
            "max_train_pos": int(tp.max()) if len(tp) else None,
            "refit_pos": r["refit_pos"],
            "embargo_ok": mc.embargo_ok(tp, r["refit_pos"]),
        }
    write_json(
        ITER / "build.json",
        {
            "last_session": str(last_date.date()) if last_date is not None else None,
            "rows_per_year": rows_per_year,
            "members_per_date_by_year": members_by_year,
            "members_per_date_min_all": int(min(all_members)),
            "members_per_date_median_all": float(np.median(all_members)),
            "members_per_date_min_from_2019": int(min(members_from_2019)),
            "members_per_date_median_from_2019": float(np.median(members_from_2019)),
            "train_weekly_rows": int(len(tw)),
            "train_weekly_dates": int(tw["trade_date"].nunique()),
            "label_nan_share_y21": float(tw["y21_rank"].isna().mean()),
            "label_nan_share_r5": float(tw["r5"].isna().mean()),
            "feature_coverage": coverage,
            "refits": refits,
            "embargo_ok": embargo,
            "embargo_ok_all": all(v["embargo_ok"] for v in embargo.values()),
            "features": FEATURES,
        },
    )
    log("build done")


# --------------------------------------------------------------------------
# train (one shard = one refit year)
# --------------------------------------------------------------------------
def cmd_train(args: argparse.Namespace) -> None:
    year = REFIT_YEARS[0] + int(args.shard)
    if year not in REFIT_YEARS:
        raise SystemExit(f"shard {args.shard} out of range")
    from scripts.run_t20260930_17_model_family_sweep import FamilyModel

    refits = json.loads((INPUTS / "refits.json").read_text())[str(year)]
    tw = pd.read_parquet(INPUTS / "train_weekly.parquet")
    tr = tw[tw["pos"] <= refits["last_train_pos"]].sort_values(["pos", "symbol"], kind="stable")
    del tw
    assert mc.embargo_ok(tr["pos"].to_numpy(), refits["refit_pos"]), "embargo violated"
    feats = pd.read_parquet(FEAT_DIR / f"{year}.parquet")
    lo, hi = pd.Timestamp(refits["predict_from"]), refits["predict_to_exclusive"]
    feats = feats[feats["trade_date"] >= lo]
    if hi is not None:
        feats = feats[feats["trade_date"] < pd.Timestamp(hi)]
    feats = feats.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
    if args.smoke:
        keep = sorted(feats["trade_date"].unique())[:5]
        feats = feats[feats["trade_date"].isin(keep)].reset_index(drop=True)
    meta: dict[str, Any] = {
        "year": year,
        "refit_date": refits["refit_date"],
        "last_train_date": str(tr["trade_date"].max().date()),
        "last_train_pos": int(tr["pos"].max()),
        "n_train_rows_all": int(len(tr)),
        "n_prediction_rows": int(len(feats)),
        "n_prediction_dates": int(feats["trade_date"].nunique()),
        "smoke": bool(args.smoke),
        "fit_seconds": {},
    }
    out = feats[["trade_date", "symbol"]].copy()
    for c in PRED_COLS:
        out[c] = np.nan

    # GBDT trio on y21_rank
    gb = tr[tr["y21_rank"].notna()]
    Xtr = gb[FEATURES].to_numpy(np.float32)
    ytr = gb["y21_rank"].to_numpy("float64")
    Xp = feats[FEATURES].to_numpy(np.float32)
    meta["n_train_rows"] = int(len(gb))
    meta["n_train_dates_gbdt"] = int(gb["pos"].nunique())
    families = (
        [("lgbm", "LGBM")] if args.smoke else [("lgbm", "LGBM"), ("xgb", "XGB"), ("cat", "CAT")]
    )
    for col, fam in families:
        t0 = time.time()
        m = FamilyModel(fam)
        m.fit(Xtr, ytr)
        out[col] = m.predict(Xp)
        meta["fit_seconds"][col] = round(time.time() - t0, 1)
        log(f"{year} {col} done {meta['fit_seconds'][col]}s")
        del m
    if not args.smoke:
        t0 = time.time()
        codes = pd.factorize(gb["pos"].to_numpy())[0]
        yperm = mc.permute_within_date(ytr, codes, PERM_SEED)
        m = FamilyModel("LGBM")
        m.fit(Xtr, yperm)
        out["lgbm_perm"] = m.predict(Xp)
        meta["fit_seconds"]["lgbm_perm"] = round(time.time() - t0, 1)
        del m
    del Xtr, ytr, gb

    # M3: DKKM random-feature ridge SDF on r5
    t0 = time.time()
    omega, gamma = mc.rff_draw(M3_SEED, len(FEATURES), M3_N_FREQ, M3_GAMMAS)
    X = tr[FEATURES].to_numpy(np.float32)
    ind = tr["ind_code"].to_numpy()
    r5 = tr["r5"].to_numpy("float64")
    pos = tr["pos"].to_numpy()
    r5_perm = mc.permute_within_date(r5, pd.factorize(pos)[0], PERM_SEED)
    bounds = np.flatnonzero(np.r_[True, pos[1:] != pos[:-1], True])
    F_real: list[np.ndarray] = []
    F_perm: list[np.ndarray] = []
    for a, b in zip(bounds[:-1], bounds[1:], strict=True):
        ok = np.isfinite(r5[a:b])
        n = int(ok.sum())
        if n < 100:  # a week with too few labels is dropped from both factor sets
            continue
        okp = np.isfinite(r5_perm[a:b])  # same count as ``ok``: the multiset is preserved
        S = mc.industry_demean(mc.rff(X[a:b], omega, gamma), ind[a:b])
        F_real.append(S[ok].T @ r5[a:b][ok] / np.sqrt(n))
        F_perm.append(S[okp].T @ r5_perm[a:b][okp] / np.sqrt(n))
    F_real_m, F_perm_m = np.asarray(F_real), np.asarray(F_perm)
    meta["n_train_weeks"] = int(len(F_real_m))
    lams: dict[str, np.ndarray] = {}
    meta["m3"] = {}
    for name, F in (("m3", F_real_m), ("m3_perm", F_perm_m)):
        if args.smoke and name == "m3_perm":
            continue
        z, val = mc.choose_z(F)
        lam = mc.sdf_lambda(F, z, mc.mean_gram_scale(F))
        lams[name] = lam
        meta["m3"][name] = {
            "z": z,
            "n_train_weeks": int(len(F)),
            "val_sharpe_by_z": val,
            "lambda_norm": float(np.linalg.norm(lam)),
            "in_sample_sharpe_weekly_x_sqrt52": mc.weekly_sharpe(F @ lam),
        }
    meta["fit_seconds"]["m3_fit"] = round(time.time() - t0, 1)
    del X, F_real, F_perm
    t0 = time.time()
    fX = feats[FEATURES].to_numpy(np.float32)
    find = feats["ind_code"].to_numpy()
    fdates = feats["trade_date"].to_numpy()
    fb = np.flatnonzero(np.r_[True, fdates[1:] != fdates[:-1], True])
    names = list(lams)
    L = np.column_stack([lams[n] for n in names])
    scores = np.full((len(feats), len(names)), np.nan)
    for a, b in zip(fb[:-1], fb[1:], strict=True):
        S = mc.industry_demean(mc.rff(fX[a:b], omega, gamma), find[a:b])
        scores[a:b] = S @ L
    for j, n in enumerate(names):
        out[n] = scores[:, j]
    meta["fit_seconds"]["m3_predict"] = round(time.time() - t0, 1)

    out_dir = BASE / ("pred_smoke" if args.smoke else "pred")
    out_dir.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_dir / f"pred_{year}.parquet", index=False)
    write_json(out_dir / f"meta_{year}.json", meta)
    log(f"train year {year} done")


# --------------------------------------------------------------------------
# assemble
# --------------------------------------------------------------------------
def _find_pred_files() -> dict[int, Path]:
    found: dict[int, Path] = {}
    for f in sorted(PRED_DIR.rglob("pred_*.parquet")):
        found[int(f.stem.split("_")[1])] = f
    return found


def _per_date_rank_mean(df: pd.DataFrame, cols: list[str]) -> pd.Series:
    r = df.groupby("trade_date", sort=False)[cols].rank(pct=True, method="average")
    return r.mean(axis=1)


def cmd_assemble(args: argparse.Namespace) -> None:
    from open_composer.research.equity_book import optimize as op

    files = _find_pred_files()
    missing = [y for y in REFIT_YEARS if y not in files]
    if missing:
        raise SystemExit(f"missing prediction files for years {missing}")
    writer: pq.ParquetWriter | None = None
    checks: dict[str, Any] = {"by_year": {}}
    worst_m2 = worst_m3 = 1.0
    for y in REFIT_YEARS:
        pred = pd.read_parquet(files[y])
        feats = pd.read_parquet(FEAT_DIR / f"{y}.parquet", columns=["trade_date", "symbol", "m0"])
        df = feats.merge(pred, on=["trade_date", "symbol"], how="inner")
        assert len(df) == len(pred), (y, len(df), len(pred))
        df = df.sort_values(["trade_date", "symbol"], kind="stable").reset_index(drop=True)
        df["m2"] = _per_date_rank_mean(df, ["lgbm", "xgb", "cat"])
        m0m2 = np.empty(len(df))
        m0m3 = np.empty(len(df))
        bounds = np.flatnonzero(
            np.r_[True, df["trade_date"].to_numpy()[1:] != df["trade_date"].to_numpy()[:-1], True]
        )
        for a, b in zip(bounds[:-1], bounds[1:], strict=True):
            g = df.iloc[a:b]
            rn0 = op.rank_normal(g["m0"])
            m0m2[a:b] = op.rank_normal(rn0 + op.rank_normal(g["m2"])).to_numpy()
            m0m3[a:b] = op.rank_normal(rn0 + op.rank_normal(g["m3"])).to_numpy()
        df["m0m2"], df["m0m3"] = m0m2, m0m3
        cols = ["trade_date", "symbol", "m0", "lgbm", "xgb", "cat", "m2", "m3", "m0m2", "m0m3"]
        df = df[[*cols, "lgbm_perm", "m3_perm"]]
        cov = df.groupby("trade_date").agg(
            n=("symbol", "size"),
            m2=("m2", lambda s: float(s.notna().mean())),
            m3=("m3", lambda s: float(s.notna().mean())),
        )
        worst_m2, worst_m3 = min(worst_m2, cov["m2"].min()), min(worst_m3, cov["m3"].min())
        checks["by_year"][str(y)] = {
            "dates": int(len(cov)),
            "first": str(df["trade_date"].min().date()),
            "last": str(df["trade_date"].max().date()),
            "min_finite_m2": float(cov["m2"].min()),
            "min_finite_m3": float(cov["m3"].min()),
            "min_members": int(cov["n"].min()),
        }
        table = pa.Table.from_pandas(df, preserve_index=False)
        if writer is None:
            writer = pq.ParquetWriter(PRED_ALL, table.schema)
        writer.write_table(table)
        log(f"assemble {y}: {len(df)} rows")
    assert writer is not None
    writer.close()
    # every session from 2019-01-02 to the end must be present
    all_dates = pd.concat(
        [pd.read_parquet(FEAT_DIR / f"{y}.parquet", columns=["trade_date"]) for y in REFIT_YEARS]
    )["trade_date"].drop_duplicates()
    got = pd.concat(
        [
            pq.ParquetFile(PRED_ALL).read_row_group(i, columns=["trade_date"]).to_pandas()
            for i in range(pq.ParquetFile(PRED_ALL).num_row_groups)
        ]
    )["trade_date"].drop_duplicates()
    all_dates = all_dates[all_dates >= pd.Timestamp("2019-01-02")]
    checks["sessions_expected"] = int(len(all_dates))
    checks["sessions_with_predictions"] = int(len(got))
    checks["all_sessions_covered"] = bool(set(all_dates) <= set(got))
    checks["min_finite_m2_all"] = float(worst_m2)
    checks["min_finite_m3_all"] = float(worst_m3)
    checks["coverage_ok"] = bool(
        checks["all_sessions_covered"] and worst_m2 >= 0.95 and worst_m3 >= 0.95
    )
    write_json(BASE / "assemble_check.json", checks)
    log(f"assemble done coverage_ok={checks['coverage_ok']}")


# --------------------------------------------------------------------------
# stage-a
# --------------------------------------------------------------------------
def sharpe52(x: pd.Series | np.ndarray) -> float:
    return mc.weekly_sharpe(np.asarray(x, dtype="float64"))


def _in_window(idx: pd.DatetimeIndex, win: tuple[str, str]) -> np.ndarray:
    return np.asarray((idx >= pd.Timestamp(win[0])) & (idx <= pd.Timestamp(win[1])))


def cmd_stage_a(args: argparse.Namespace) -> None:
    import scripts.realism_ladder_book_ls as T25
    from scripts.run_t20260930_17_model_family_sweep import newey_west_t

    sha = hashlib.sha256((ITER / "hypotheses.md").read_bytes()).hexdigest()
    if sha != CONTRACT_SHA256:
        raise SystemExit(f"contract changed: {sha}")
    ctx = T25.Context()
    px = ctx.px
    first_ml = int(px.dates.searchsorted(pd.Timestamp("2019-01-02")))
    last_week_pos = px.T - 1 - 6  # r5 needs C[p+6]
    ycols = ["trade_date", "symbol", "y21_rank"]
    tw = pd.read_parquet(INPUTS / "train_weekly.parquet", columns=ycols)
    tw = tw[tw["trade_date"] >= pd.Timestamp("2019-01-02")]
    y21_by_date = {d: g.set_index("symbol")["y21_rank"] for d, g in tw.groupby("trade_date")}
    del tw
    pf = pq.ParquetFile(PRED_ALL)
    rets: dict[str, dict[int, dict[pd.Timestamp, float]]] = {
        s: {o: {} for o in range(5)} for s in SCORES
    }
    rank_store: dict[str, dict[pd.Timestamp, pd.Series]] = {s: {} for s in SCORES}
    n_dates_used = 0
    for i in range(pf.num_row_groups):
        df = pf.read_row_group(i).to_pandas()
        for t, g in df.groupby("trade_date", sort=True):
            p = int(px.dates.get_loc(t))
            if p < first_ml or p > last_week_pos:
                continue
            o = p % T25.WEEK
            members = pd.Index(g["symbol"])
            r5 = pd.Series(_labels_for(ctx, t, p, members, 5), index=members)
            ind = ctx.sig.at(t)["ind_code"].reindex(members)
            n_dates_used += 1
            for s in SCORES:
                sc = pd.Series(g[s].to_numpy("float64"), index=members)
                rets[s][o][t] = mc.simplified_weekly_return(sc, ind, r5)
                if o == 0:
                    rank_store[s][t] = sc.rank(pct=True).astype("float32")
        log(f"stage-a group {i + 1}/{pf.num_row_groups} done ({n_dates_used} dates)")
        del df
    ser = {
        s: {o: pd.Series(rets[s][o]).sort_index() for o in range(5)} for s in SCORES
    }  # date -> weekly gross return

    def window_slice(x: pd.Series, win: tuple[str, str]) -> pd.Series:
        return x[_in_window(pd.DatetimeIndex(x.index), win)]

    scores_out: dict[str, Any] = {}
    for s in SCORES:
        sharpe: dict[str, Any] = {}
        ic: dict[str, Any] = {}
        ac: dict[str, Any] = {}
        corr: dict[str, Any] = {}
        # offset-0 IC series against y21 rank
        ic_dates, ic_vals = [], []
        for d in sorted(rank_store[s]):
            y = y21_by_date.get(d)
            if y is None:
                continue
            sc = rank_store[s][d]
            both = pd.concat([sc, y], axis=1, join="inner").dropna()
            if len(both) < 50:
                continue
            ic_dates.append(d)
            ic_vals.append(float(both.iloc[:, 0].rank().corr(both.iloc[:, 1].rank())))
        ic_series = pd.Series(ic_vals, index=pd.DatetimeIndex(ic_dates))
        dates0 = sorted(rank_store[s])
        ac_vals = []
        for a, b in zip(dates0[:-1], dates0[1:], strict=True):
            x, y = rank_store[s][a], rank_store[s][b]
            common = x.index.intersection(y.index)
            x, y = x.loc[common], y.loc[common]
            ok = x.notna() & y.notna()
            if ok.sum() < 50:
                continue
            ac_vals.append((b, float(x[ok].rank().corr(y[ok].rank()))))
        ac_series = pd.Series(
            [v for _, v in ac_vals], index=pd.DatetimeIndex([d for d, _ in ac_vals])
        )
        for w, win in WINDOWS.items():
            by_off = [sharpe52(window_slice(ser[s][o], win)) for o in range(5)]
            sharpe[w] = {"by_offset": by_off, "offset_median": float(np.nanmedian(by_off))}
            v = window_slice(ic_series, win)
            t = newey_west_t(v.to_numpy(), 4)
            ic[w] = {
                "mean": float(v.mean()) if len(v) else None,
                "nw_t": None if not np.isfinite(t) else float(t),
                "n": int(len(v)),
            }
            a = window_slice(ac_series, win)
            ac[w] = float(a.median()) if len(a) else None
            r_s = window_slice(ser[s][0], win)
            r_m = window_slice(ser[BASELINE][0], win)
            corr[w] = float(r_s.corr(r_m)) if len(r_s) > 2 else None
        scores_out[s] = {
            "simplified_gross_sharpe": sharpe,
            "rank_ic_y21": ic,
            "rank_autocorr_weekly_median": ac,
            "corr_with_m0_offset0": corr,
        }
    perm = {}
    perm_pass = True
    for s in ("lgbm_perm", "m3_perm"):
        for w, lim in PERM_LIMITS.items():
            v = scores_out[s]["simplified_gross_sharpe"][w]["offset_median"]
            ok = bool(np.isfinite(v) and abs(v) <= lim)
            perm.setdefault(s, {})[w] = {"offset_median": v, "limit": lim, "pass": ok}
            perm_pass &= ok
    base = scores_out[BASELINE]["simplified_gross_sharpe"]
    survivors = [
        c
        for c in CANDIDATES
        if all(
            scores_out[c]["simplified_gross_sharpe"][w]["offset_median"] > base[w]["offset_median"]
            for w in ("recent", "stress_ml")
        )
    ]
    if not perm_pass:
        status = "permutation_check_failed"
    elif not survivors:
        status = "no_candidate_beats_m0_gross_stage_a"
    else:
        status = "stage_b_authorized"
    build = json.loads((ITER / "build.json").read_text())
    metas = {y: json.loads(next(PRED_DIR.rglob(f"meta_{y}.json")).read_text()) for y in REFIT_YEARS}
    model_meta_dir = ITER / "model-meta"
    model_meta_dir.mkdir(parents=True, exist_ok=True)
    for y in REFIT_YEARS:
        shutil.copyfile(next(PRED_DIR.rglob(f"meta_{y}.json")), model_meta_dir / f"meta_{y}.json")
    result = {
        "contract": {"hypotheses_sha256": sha, "unchanged": sha == CONTRACT_SHA256},
        "windows": {k: list(v) for k, v in WINDOWS.items()},
        "window_basis": "decision date; weekly r5 requires C[p+6] (last decision date "
        f"{px.dates[last_week_pos].date()})",
        "n_decision_dates_used": n_dates_used,
        "scores": scores_out,
        "permutation_check": {"pass": perm_pass, "detail": perm},
        "stage_a_survivors": survivors,
        "mechanical_status_stage_a": status,
        "m3_meta": {
            str(y): {
                "z": metas[y]["m3"]["m3"]["z"],
                "n_train_weeks": metas[y]["m3"]["m3"]["n_train_weeks"],
                "val_sharpe_by_z": metas[y]["m3"]["m3"]["val_sharpe_by_z"],
                "perm_z": metas[y]["m3"]["m3_perm"]["z"],
            }
            for y in REFIT_YEARS
        },
        "gbdt_meta": {
            str(y): {
                "n_train_rows": metas[y]["n_train_rows"],
                "last_train_date": metas[y]["last_train_date"],
                "fit_seconds": metas[y]["fit_seconds"],
            }
            for y in REFIT_YEARS
        },
        "embargo_ok_all": bool(build["embargo_ok_all"]),
        "assemble_check": json.loads((BASE / "assemble_check.json").read_text()),
        "modal_cost_usd": args.modal_cost_usd,
        "implementation_choices": IMPLEMENTATION_CHOICES,
    }
    write_json(ITER / "stage_a.json", result)
    (ITER / "stage_a.md").write_text(render_md(result))
    log(f"stage-a done: {status} survivors={survivors}")


IMPLEMENTATION_CHOICES = [
    "Signal-library standardized columns carry a constant for missing values (no NaN remains; e.g. 17% of bm, 98% of cmp_opp_buy_60d tie at one value), so after the per-date rank the ties get their average rank; no further imputation was done.",
    "Windows are applied to the decision date p; a weekly decision needs a complete r5 "
    "(C[p+6] in the snapshot), so the last 4 sessions of the snapshot are not decision dates.",
    "Features are ranked within U3000 members per date (percentile rank - 0.5, average ties); "
    "log_mcap is ranked like the others (monotone in mcap > 0, else NaN).",
    "ind_code is used only for demeaning (labels, RFF columns, target weights), never as a model input.",
    "y21_rank = per-date percentile rank (0, 1] of the industry-demeaned hedged label; rows with "
    "missing forward prices have NaN label and are dropped from training.",
    "M3 RFF draw: omega ~ N(0, I_23) (2000 x 23), gamma_p uniform on {0.5..1.0} via "
    "default_rng(20261004) in the order omega, gamma; RFF columns are demeaned over all members of "
    "the date before dropping rows with a missing r5; N_t counts rows with finite r5; weeks with "
    "< 100 usable rows are skipped.",
    "z selection on the early weeks uses s_bar of that fit subset; the final refit uses s_bar of "
    "all training weeks; ties in validation Sharpe go to the smaller z.",
    "Permutation models: the GBDT permutation shuffles y21_rank among rows of each training date "
    "(rows with non-missing label); the M3 permutation shuffles r5 among all rows of each date, "
    "default_rng(1) in both cases; M3_perm runs the same z selection on its own factors.",
    "GBDT trio uses FamilyModel from run_t20260930_17_model_family_sweep unchanged (seeds, "
    "parameters, native NaN); m2 = mean of per-date average-rank percentiles of lgbm, xgb, cat.",
    "Rank IC against y21_rank uses Spearman on offset-0 dates that have a complete 21-session label; "
    "NW lag 4; autocorrelation is the median Spearman between consecutive offset-0 dates over "
    "common symbols; correlation with m0 uses offset-0 weekly simplified returns.",
    "Simplified returns use the unclipped beta-hedged r5 with beta from ctx.ewma.at(t) "
    "(NaN -> 1.0, clip [-1, 4]); NaN r5 -> 0; no short-eligibility, VIX or hedge-leg sizing.",
]


def _f(x: Any, nd: int = 3) -> str:
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def render_md(r: dict[str, Any]) -> str:
    sc = r["scores"]
    lines = [
        "# T-20261004-02 Stage A: ML composites vs M0 (simplified weekly gross, beta-hedged, no costs)",
        "",
        f"contract sha256 unchanged: {r['contract']['unchanged']}; status: "
        f"**{r['mechanical_status_stage_a']}**; survivors: {r['stage_a_survivors'] or 'none'}; "
        f"permutation check pass: {r['permutation_check']['pass']}; embargo ok: {r['embargo_ok_all']}; "
        f"Modal cost USD: {r['modal_cost_usd']}",
        "",
        "## Offset-median simplified gross Sharpe (all 5 offsets in brackets)",
        "",
        "| score | recent | stress_ml | full_ml | recent by offset |",
        "|---|---|---|---|---|",
    ]
    for s in SCORES:
        g = sc[s]["simplified_gross_sharpe"]
        offs = ", ".join(_f(v, 2) for v in g["recent"]["by_offset"])
        lines.append(
            f"| {s} | {_f(g['recent']['offset_median'])} | {_f(g['stress_ml']['offset_median'])} | "
            f"{_f(g['full_ml']['offset_median'])} | {offs} |"
        )
    lines += [
        "",
        "## Rank IC vs y21 (offset 0; mean / NW t lag 4), weekly rank autocorr median, corr with m0",
        "",
        "| score | IC recent | t | IC stress_ml | t | autocorr recent | autocorr stress | corr m0 recent | corr m0 stress |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for s in SCORES:
        i, a, c = (
            sc[s]["rank_ic_y21"],
            sc[s]["rank_autocorr_weekly_median"],
            sc[s]["corr_with_m0_offset0"],
        )
        lines.append(
            f"| {s} | {_f(i['recent']['mean'], 4)} | {_f(i['recent']['nw_t'], 2)} | "
            f"{_f(i['stress_ml']['mean'], 4)} | {_f(i['stress_ml']['nw_t'], 2)} | "
            f"{_f(a['recent'])} | {_f(a['stress_ml'])} | {_f(c['recent'])} | {_f(c['stress_ml'])} |"
        )
    lines += ["", "## Permutation check (|offset-median Sharpe| <= limit)", ""]
    for s, d in r["permutation_check"]["detail"].items():
        lines.append(
            f"- {s}: recent {_f(d['recent']['offset_median'])} (<= {d['recent']['limit']}, "
            f"{d['recent']['pass']}); stress_ml {_f(d['stress_ml']['offset_median'])} "
            f"(<= {d['stress_ml']['limit']}, {d['stress_ml']['pass']})"
        )
    lines += [
        "",
        "## Refits",
        "",
        "| year | train rows | last train date | M3 weeks | M3 z | M3_perm z |",
        "|---|---|---|---|---|---|",
    ]
    for y in REFIT_YEARS:
        g, m = r["gbdt_meta"][str(y)], r["m3_meta"][str(y)]
        lines.append(
            f"| {y} | {g['n_train_rows']} | {g['last_train_date']} | {m['n_train_weeks']} | {m['z']} | {m['perm_z']} |"
        )
    lines += [
        "",
        "Windows (decision date): "
        + "; ".join(f"{k} {v[0]}..{v[1]}" for k, v in r["windows"].items()),
    ]
    lines += ["Source: stage_a.json (same folder)."]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build").set_defaults(fn=cmd_build)
    t = sub.add_parser("train")
    t.add_argument("--shard", type=int, required=True)
    t.add_argument("--nshards", type=int, default=len(REFIT_YEARS))
    t.add_argument("--smoke", action="store_true")
    t.set_defaults(fn=cmd_train)
    sub.add_parser("assemble").set_defaults(fn=cmd_assemble)
    s = sub.add_parser("stage-a")
    s.add_argument("--modal-cost-usd", type=float, default=None)
    s.set_defaults(fn=cmd_stage_a)
    args = ap.parse_args(argv)
    args.fn(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
