"""T-20260930-17 stage 1: model family x training window x horizon sweep.

Design is frozen in
``reports/research/iterations/t20260930_17_model_family_sweep/hypotheses.md``;
this script only executes it. Stage 1 measures walk-forward RankIC on the
cached T-20260928-10 monthly panel (stress period 2016-05..2023-08) for 24
cells: {LGBM, XGB, CAT, RIDGE, MLP, ENS} x {W3, WX} x {H21, H63}. The four ENS
cells are computed in ``aggregate`` from the 20 trained cells. No portfolio,
no costs (stage 2 is a separate later brief).

Stages
------
``spy``       (local, light) writes ``cache/spy_close.parquet`` -- the SPY close
              that ``kt.stage_panel`` adds after hygiene; the cached
              ``close_wide.parquet`` does not contain SPY and Modal has no
              ``data/sip``.
``cell``      (Modal, one non-ENS cell per shard) trains one cell and writes
              ``cache/cells/<cell>_{pred,ic}.parquet`` and ``<cell>.json``.
``aggregate`` (local) builds the ENS cells, all metrics, ``results_stage1.json``
              and ``report.md``.

Usage (Modal; see ``scripts/modal_run.py``)::

    python3 scripts/modal_run.py --job t20260930-17-cells --cpu 4 \\
        --memory-gib 4 --timeout-min 40 --shards 20 \\
        --data <kt cache>/panel_monthly.parquet --data <kt cache>/close_wide.parquet \\
        --data <kt cache>/candidate_B0.json \\
        --data <this iteration>/cache/spy_close.parquet \\
        --out reports/research/iterations/t20260930_17_model_family_sweep \\
        -- uv run --with xgboost --with catboost python \\
           scripts/run_t20260930_17_model_family_sweep.py cell \\
           --shard {shard} --nshards {nshards}
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

ITERATION_ID = "t20260930_17_model_family_sweep"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = ITER_DIR / "cache"
CELLS_DIR = CACHE_DIR / "cells"
SPY_PATH = CACHE_DIR / "spy_close.parquet"
RESULTS_PATH = ITER_DIR / "results_stage1.json"
REPORT_PATH = ITER_DIR / "report.md"
PREREG_STAMP_PATH = ITER_DIR / "prebacktest-validated-at.txt"
LEDGER_ACTUALS_PATH = ROOT / "reports/research/control/modal-ledger-actuals.jsonl"

FAMILIES: tuple[str, ...] = ("LGBM", "XGB", "CAT", "RIDGE", "MLP")
ENS_FAMILY = "ENS"
WINDOWS: tuple[str, ...] = ("W3", "WX")
HORIZON_TAGS: dict[str, int] = {"H21": 21, "H63": 63}
#: Fixed shard order: shard i (0-indexed) trains CELL_ORDER[i].
CELL_ORDER: tuple[str, ...] = tuple(
    f"{fam}_{win}_{hz}" for fam, win, hz in itertools.product(FAMILIES, WINDOWS, HORIZON_TAGS)
)
ALL_CELLS: tuple[str, ...] = CELL_ORDER + tuple(
    f"{ENS_FAMILY}_{win}_{hz}" for win, hz in itertools.product(WINDOWS, HORIZON_TAGS)
)
B0_CELL = "LGBM_W3_H21"
EXPANDING_TRAIN_YEARS = 50.0
NAN_FILL = 0.5
SEED = 20260930

# Frozen thresholds (hypotheses.md).
B0_RANKIC = 0.0200
B0_TOLERANCE = 0.0010
FAMILY_EFFECT_MIN_DIFF = 0.010
FAMILY_EFFECT_MIN_T = 3.0
STAGE2_MIN_T = 2.0
STAGE2_MAX_CELLS = 3
H21_TARGET_TOL = 1e-9
FLOAT_EPS = 1e-9
NW_LAG_BY_HORIZON = {21: 0, 63: 2}
TERCILES = ("T1_liquid", "T2_mid", "T3_illiquid")


def _log(message: str) -> None:
    print(f"[{datetime.now(UTC).strftime('%H:%M:%S')}] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")


# --------------------------------------------------------------------------
# cell naming, sharding, model factories (pure / light)
# --------------------------------------------------------------------------


def parse_cell(cell: str) -> tuple[str, str, int]:
    """``"XGB_WX_H63"`` -> ``("XGB", "WX", 63)``."""
    family, window, hz = cell.split("_")
    if family not in FAMILIES + (ENS_FAMILY,) or window not in WINDOWS or hz not in HORIZON_TAGS:
        raise ValueError(f"unknown cell {cell!r}")
    return family, window, HORIZON_TAGS[hz]


def cell_for_shard(shard: int, nshards: int) -> str:
    if nshards != len(CELL_ORDER):
        raise ValueError(f"nshards must be {len(CELL_ORDER)}, got {nshards}")
    if not 0 <= shard < nshards:
        raise ValueError(f"shard must be in [0, {nshards}), got {shard}")
    return CELL_ORDER[shard]


def needs_nan_fill(family: str) -> bool:
    """Ridge and MLP cannot take NaN; the tree families handle it natively."""
    return family in ("RIDGE", "MLP")


def fill_missing(X: np.ndarray, family: str) -> np.ndarray:
    if not needs_nan_fill(family):
        return X
    return np.where(np.isnan(X), NAN_FILL, X)


def _threads() -> int:
    # modal_run sets OC_NUM_THREADS = 2 * cpu; use the requested core count.
    return max(1, int(os.environ.get("OC_NUM_THREADS", "8")) // 2)


class FamilyModel:
    """fit(X, y) / predict(X) wrapper: NaN policy per family, MLP target scaling."""

    def __init__(self, family: str) -> None:
        self.family = family
        self._model: Any = None

    def _build(self) -> Any:
        threads = _threads()
        if self.family == "LGBM":
            import lightgbm as lgb

            from scripts import run_t20260928_10_ml_killtest as kt

            return lgb.LGBMRegressor(**dict(kt.LGBM_REG_PARAMS, n_jobs=threads))
        if self.family == "XGB":
            from xgboost import XGBRegressor

            return XGBRegressor(
                tree_method="hist",
                max_depth=6,
                learning_rate=0.05,
                n_estimators=400,
                subsample=0.8,
                colsample_bytree=0.8,
                min_child_weight=200,
                reg_lambda=1.0,
                random_state=SEED,
                n_jobs=threads,
            )
        if self.family == "CAT":
            from catboost import CatBoostRegressor

            return CatBoostRegressor(
                depth=6,
                learning_rate=0.05,
                iterations=400,
                loss_function="RMSE",
                rsm=0.8,
                bootstrap_type="Bernoulli",
                subsample=0.8,
                min_data_in_leaf=200,
                random_seed=SEED,
                verbose=0,
                thread_count=threads,
            )
        if self.family == "RIDGE":
            from sklearn.linear_model import Ridge

            return Ridge(alpha=1.0)
        if self.family == "MLP":
            from sklearn.neural_network import MLPRegressor

            return MLPRegressor(
                hidden_layer_sizes=(32, 16, 8),
                activation="relu",
                alpha=1e-4,
                learning_rate_init=1e-3,
                batch_size=2048,
                max_iter=100,
                early_stopping=True,
                validation_fraction=0.1,
                n_iter_no_change=5,
                random_state=SEED,
            )
        raise ValueError(f"no model for family {self.family!r}")

    def fit(self, X: np.ndarray, y: np.ndarray) -> None:
        X = fill_missing(X, self.family)
        y = np.asarray(y, dtype="float64")
        if self.family == "MLP":
            sd = float(y.std())
            y = (y - float(y.mean())) / (sd if sd > 0 else 1.0)
        self._model = self._build()
        self._model.fit(X, y)

    def predict(self, X: np.ndarray) -> np.ndarray:
        assert self._model is not None
        return np.asarray(self._model.predict(fill_missing(X, self.family)), dtype="float64")


# --------------------------------------------------------------------------
# pure metrics (aggregate side)
# --------------------------------------------------------------------------


def nw_lag_for_horizon(horizon: int) -> int:
    return NW_LAG_BY_HORIZON[horizon]


def newey_west_t(x: np.ndarray, lags: int) -> float:
    """Newey-West t (Bartlett weights); same formula as
    ``run_t20260929_35_overnight_persistence.newey_west_t`` (copied so the
    Modal cell stage does not import duckdb; a test asserts they agree)."""
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


def ic_stats(values: np.ndarray, lag: int) -> dict[str, Any]:
    v = np.asarray(values, dtype="float64")
    v = v[np.isfinite(v)]
    n = int(len(v))
    if n == 0:
        return {"mean_rankic": None, "t_nw": None, "n_dates": 0}
    t = newey_west_t(v, lag)
    return {
        "mean_rankic": float(v.mean()),
        "t_nw": None if not np.isfinite(t) else t,
        "n_dates": n,
    }


def rank_mean_ensemble(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Per formation date, percentile-rank each frame's ``pred`` and average.

    Inputs share (formation_date, symbol) keys; only the intersection is kept.
    Returns formation_date, symbol, pred (mean of ranks) plus target and
    adv_tercile carried from the first frame.
    """
    if not frames:
        raise ValueError("need at least one frame")
    keys = ["formation_date", "symbol"]
    base = frames[0][keys + ["target", "adv_tercile"]].copy()
    ranks = []
    for idx, frame in enumerate(frames):
        f = frame[keys + ["pred"]].copy()
        f["pred"] = f.groupby("formation_date")["pred"].rank(pct=True)
        ranks.append(f.rename(columns={"pred": f"r{idx}"}))
    merged = base
    for r in ranks:
        merged = merged.merge(r, on=keys, how="inner")
    rank_cols = [f"r{i}" for i in range(len(frames))]
    merged["pred"] = merged[rank_cols].mean(axis=1)
    return merged[keys + ["pred", "target", "adv_tercile"]]


def rank_autocorr(pred: pd.DataFrame) -> dict[str, Any]:
    """Turnover proxy: Spearman correlation of prediction ranks between
    consecutive formation dates over their common symbols, averaged."""
    dates = sorted(pred["formation_date"].unique())
    by_date = {d: g.set_index("symbol")["pred"] for d, g in pred.groupby("formation_date")}
    values = []
    for prev, cur in zip(dates[:-1], dates[1:], strict=True):
        a, b = by_date[prev], by_date[cur]
        common = a.index.intersection(b.index)
        if len(common) < 5:
            continue
        rho = a.loc[common].rank().corr(b.loc[common].rank())
        if np.isfinite(rho):
            values.append(float(rho))
    return {
        "mean": float(np.mean(values)) if values else None,
        "n_pairs": len(values),
    }


def b0_parity_ok(rankic: float | None) -> bool:
    if rankic is None or not np.isfinite(rankic):
        return False
    return bool(abs(rankic - B0_RANKIC) <= B0_TOLERANCE + 1e-12)


def is_material(diff: float | None, t: float | None) -> bool:
    if diff is None or t is None or not np.isfinite(diff) or not np.isfinite(t):
        return False
    return bool(diff >= FAMILY_EFFECT_MIN_DIFF - FLOAT_EPS and t >= FAMILY_EFFECT_MIN_T - FLOAT_EPS)


def family_effect(cells: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Per (window, horizon): best non-LGBM family vs same-group LGBM."""
    out: dict[str, dict[str, Any]] = {}
    for win, hz in itertools.product(WINDOWS, HORIZON_TAGS):
        group = f"{win}_{hz}"
        lgbm = cells.get(f"LGBM_{win}_{hz}")
        rivals = [
            (fam, cells[f"{fam}_{win}_{hz}"])
            for fam in ("XGB", "CAT", "RIDGE", "MLP", ENS_FAMILY)
            if f"{fam}_{win}_{hz}" in cells
            and cells[f"{fam}_{win}_{hz}"]["mean_rankic"] is not None
        ]
        if lgbm is None or lgbm["mean_rankic"] is None or not rivals:
            out[group] = {"status": "missing"}
            continue
        best_fam, best = max(rivals, key=lambda kv: kv[1]["mean_rankic"])
        diff = best["mean_rankic"] - lgbm["mean_rankic"]
        out[group] = {
            "lgbm_rankic": lgbm["mean_rankic"],
            "best_non_lgbm_family": best_fam,
            "best_non_lgbm_rankic": best["mean_rankic"],
            "diff": diff,
            "t_nw": best["t_nw"],
            "material": is_material(diff, best["t_nw"]),
            "all_non_lgbm": {
                fam: {
                    "rankic": c["mean_rankic"],
                    "diff": c["mean_rankic"] - lgbm["mean_rankic"],
                    "t_nw": c["t_nw"],
                }
                for fam, c in rivals
            },
        }
    return out


def answer_family(effects: dict[str, dict[str, Any]]) -> str:
    return "material" if any(e.get("material") for e in effects.values()) else "none"


def select_stage2_cells(cells: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Top 3 non-B0 cells by NW t, only t >= 2.0 (hypotheses.md); ties keep
    the ALL_CELLS order."""
    eligible = []
    for order, cell in enumerate(ALL_CELLS):
        if cell == B0_CELL or cell not in cells:
            continue
        t = cells[cell].get("t_nw")
        if t is None or not np.isfinite(t) or t < STAGE2_MIN_T - FLOAT_EPS:
            continue
        eligible.append((-float(t), order, cell))
    eligible.sort()
    return [
        {
            "cell": cell,
            "t_nw": cells[cell]["t_nw"],
            "mean_rankic": cells[cell]["mean_rankic"],
        }
        for _t, _o, cell in eligible[:STAGE2_MAX_CELLS]
    ]


# --------------------------------------------------------------------------
# stage: spy (local, light)
# --------------------------------------------------------------------------


def stage_spy(args: argparse.Namespace) -> None:
    from scripts import run_t20260928_10_ml_killtest as kt

    close_index = pd.read_parquet(kt.CACHE_DIR / "close_wide.parquet", columns=[]).index
    bench_close, _open = kt.h02._benchmark_prices(("SPY",))
    spy = bench_close.reindex(close_index)[["SPY"]]
    SPY_PATH.parent.mkdir(parents=True, exist_ok=True)
    spy.to_parquet(SPY_PATH)
    _log(f"spy: wrote {SPY_PATH} rows={len(spy)} non_null={int(spy['SPY'].notna().sum())}")


# --------------------------------------------------------------------------
# stage: cell (Modal)
# --------------------------------------------------------------------------


def _load_panel_and_targets(
    horizon: int,
) -> tuple[pd.DataFrame, list[str], pd.DatetimeIndex, float]:
    """Panel with the target for ``horizon`` and the h21 parity diff.

    Follows ``kt.stage_train``: the cached monthly panel already carries
    percentile-ranked features and ``adv_tercile``; only rows with a missing
    target are dropped later. h63 comes from ``kt.build_target`` on the
    hygiene-sanitized close (SPY added after hygiene, as in ``kt.stage_panel``).
    """
    import pyarrow.parquet as pq

    from open_composer.research.features import price_hygiene
    from scripts import run_t20260928_10_ml_killtest as kt

    h02 = kt.h02
    features = list(json.loads((kt.CACHE_DIR / "candidate_B0.json").read_text())["feature_columns"])
    cols = [
        "formation_date",
        "symbol",
        "adv_tercile",
        "dollar_adv",
        h02.BETA_COLUMN,
        "target_excess_21",
        *features,
    ]
    cols = list(dict.fromkeys(cols))
    have = set(pq.ParquetFile(kt.CACHE_DIR / "panel_monthly.parquet").schema_arrow.names)
    panel = pd.read_parquet(
        kt.CACHE_DIR / "panel_monthly.parquet", columns=[c for c in cols if c in have]
    )
    panel["formation_date"] = h02._ns(panel["formation_date"])
    for c in features:
        panel[c] = panel[c].astype("float64")

    close_wide = pd.read_parquet(kt.CACHE_DIR / "close_wide.parquet")
    trading_calendar = pd.DatetimeIndex(h02._ns(close_wide.index))
    close_sanitized, _o, report = price_hygiene.sanitize_price_matrices(close_wide, None)
    del close_wide
    _log(
        f"cell: hygiene masked {report.symbols_masked} symbols ({report.price_cells_masked} cells)"
    )
    if "SPY" not in close_sanitized.columns:
        spy = pd.read_parquet(SPY_PATH)
        close_sanitized["SPY"] = spy.reindex(close_sanitized.index)["SPY"]

    keep = ["formation_date", "symbol", "dollar_adv", h02.BETA_COLUMN]
    h21 = kt.build_target(panel[keep].copy(), close_sanitized, 21)["target_excess_21"].to_numpy()
    ref = panel["target_excess_21"].to_numpy()
    both_nan = np.isnan(h21) & np.isnan(ref)
    if np.isnan(h21).sum() != np.isnan(ref).sum() or (np.isnan(h21) != np.isnan(ref)).any():
        raise SystemExit("h21 target check failed: NaN pattern differs from panel target_excess_21")
    finite = ~both_nan
    max_diff = float(np.max(np.abs(h21[finite] - ref[finite]))) if finite.any() else 0.0
    if not max_diff < H21_TARGET_TOL:
        raise SystemExit(
            f"h21 target check failed: max abs diff {max_diff:.3e} >= {H21_TARGET_TOL}"
        )
    _log(f"cell: h21 target check max_abs_diff={max_diff:.3e} over {int(finite.sum()):,} rows")

    if horizon == 21:
        panel["target"] = ref
    else:
        target_col = f"target_excess_{horizon}"
        built = kt.build_target(panel[keep].copy(), close_sanitized, horizon)
        panel["target"] = built[target_col].to_numpy()
    del close_sanitized
    return panel, features, trading_calendar, max_diff


def _train_cell(
    cell: str,
    panel: pd.DataFrame,
    features: list[str],
    trading_calendar: pd.DatetimeIndex,
    smoke: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, Any]]]:
    from scripts import run_t20260928_10_ml_killtest as kt

    h02 = kt.h02
    family, window, horizon = parse_cell(cell)
    train_years = kt.DEFAULT_TRAIN_YEARS if window == "W3" else EXPANDING_TRAIN_YEARS
    formation_dates = sorted(panel["formation_date"].unique())
    previous_embargo = h02.EMBARGO_DAYS
    h02.EMBARGO_DAYS = horizon
    try:
        folds = h02.build_folds(formation_dates, trading_calendar, train_years)
    finally:
        h02.EMBARGO_DAYS = previous_embargo
    _log(f"cell {cell}: {len(folds)} folds, train_years={train_years}, embargo={horizon}")

    ic_records: list[dict[str, Any]] = []
    pred_frames: list[pd.DataFrame] = []
    fold_meta: list[dict[str, Any]] = []
    trained = 0
    for fold in folds:
        t0 = time.time()
        train_frame = panel.loc[panel["formation_date"].isin(fold.train_dates)].dropna(
            subset=["target"]
        )
        meta: dict[str, Any] = {
            "fold_id": fold.fold_id,
            "train_start": fold.train_start.date().isoformat(),
            "train_cutoff": fold.train_cutoff.date().isoformat(),
            "actual_train_years": round(fold.actual_train_years, 2),
            "train_rows": int(len(train_frame)),
            "validation_dates": len(fold.validation_dates),
        }
        if len(train_frame) < h02.MIN_TRAIN_ROWS:
            meta["skipped"] = f"train_rows {len(train_frame)} < {h02.MIN_TRAIN_ROWS}"
            fold_meta.append(meta)
            continue
        if smoke and trained >= 2:
            break
        model = FamilyModel(family)
        model.fit(
            train_frame[features].to_numpy(dtype="float64"),
            train_frame["target"].to_numpy(dtype="float64"),
        )
        val_frame = panel.loc[panel["formation_date"].isin(fold.validation_dates)].dropna(
            subset=["target"]
        )
        trained += 1
        if val_frame.empty:
            meta["validation_rankic_n_dates"] = 0
            fold_meta.append(meta)
            continue
        scored = val_frame[["formation_date", "symbol", "adv_tercile", "target"]].copy()
        scored["pred"] = model.predict(val_frame[features].to_numpy(dtype="float64"))
        pred_frames.append(scored)

        overall = h02.rank_ic_per_date(scored, "pred", "target")
        for date, rho in overall:
            ic_records.append({"formation_date": date, "rho": rho, "tercile": "all"})
        for tercile_name, sub in scored.groupby("adv_tercile"):
            for date, rho in h02.rank_ic_per_date(sub, "pred", "target"):
                ic_records.append({"formation_date": date, "rho": rho, "tercile": tercile_name})
        meta["validation_rankic_mean"] = (
            float(np.mean([r for _, r in overall])) if overall else None
        )
        meta["validation_rankic_n_dates"] = len(overall)
        meta["seconds"] = round(time.time() - t0, 1)
        fold_meta.append(meta)
        _log(
            f"cell {cell}: fold {fold.fold_id} rows={len(train_frame):,} "
            f"rankic={meta['validation_rankic_mean']} {meta['seconds']}s"
        )

    ic_frame = (
        pd.DataFrame(ic_records)
        if ic_records
        else pd.DataFrame(columns=["formation_date", "rho", "tercile"])
    )
    pred_frame = (
        pd.concat(pred_frames, ignore_index=True)
        if pred_frames
        else pd.DataFrame(columns=["formation_date", "symbol", "adv_tercile", "target", "pred"])
    )
    return pred_frame, ic_frame, fold_meta


def stage_cell(args: argparse.Namespace) -> None:
    cell = cell_for_shard(args.shard, args.nshards)
    _family, _window, horizon = parse_cell(cell)
    t_start = time.time()
    _log(f"cell: shard {args.shard}/{args.nshards} -> {cell} smoke={args.smoke}")
    if args.smoke:
        import catboost
        import xgboost

        _log(f"smoke: xgboost {xgboost.__version__}, catboost {catboost.__version__}")
    panel, features, calendar, max_diff = _load_panel_and_targets(horizon)
    pred_frame, ic_frame, fold_meta = _train_cell(cell, panel, features, calendar, args.smoke)
    CELLS_DIR.mkdir(parents=True, exist_ok=True)
    # Predictions carry target and adv_tercile so the ENS aggregation needs no panel.
    pred_frame.to_parquet(CELLS_DIR / f"{cell}_pred.parquet", index=False)
    ic_frame.to_parquet(CELLS_DIR / f"{cell}_ic.parquet", index=False)
    trained_rows = [m["train_rows"] for m in fold_meta if "skipped" not in m]
    record = {
        "cell": cell,
        "shard": args.shard,
        "smoke": bool(args.smoke),
        "horizon": horizon,
        "n_folds": len(fold_meta),
        "n_folds_trained": len(trained_rows),
        "train_rows_mean": float(np.mean(trained_rows)) if trained_rows else None,
        "pred_rows": int(len(pred_frame)),
        "h21_target_check_max_abs_diff": max_diff,
        "feature_columns": features,
        "fold_meta": fold_meta,
        "seconds": round(time.time() - t_start, 1),
    }
    _write_json(CELLS_DIR / f"{cell}.json", record)
    _log(f"cell {cell}: done in {record['seconds']}s, pred_rows={record['pred_rows']:,}")


# --------------------------------------------------------------------------
# stage: aggregate (local)
# --------------------------------------------------------------------------


def _find_cell_dirs() -> list[Path]:
    dirs = [CELLS_DIR] + sorted(ITER_DIR.glob("shard_*/cache/cells"))
    return [d for d in dirs if d.is_dir()]


def _locate(cell: str, suffix: str) -> Path | None:
    for d in _find_cell_dirs():
        p = d / f"{cell}{suffix}"
        if p.is_file():
            return p
    return None


def _cell_metrics(pred: pd.DataFrame, horizon: int, meta: dict[str, Any]) -> dict[str, Any]:
    from scripts import run_t20260928_10_ml_killtest as kt

    h02 = kt.h02
    lag = nw_lag_for_horizon(horizon)
    pred = pred.copy()
    pred["formation_date"] = pd.to_datetime(pred["formation_date"])
    if pred.duplicated(["formation_date", "symbol"]).any():
        raise SystemExit("duplicate (formation_date, symbol) rows in predictions")
    rows = []
    for date, rho in h02.rank_ic_per_date(pred, "pred", "target"):
        rows.append({"formation_date": date, "rho": rho, "tercile": "all"})
    for tercile, sub in pred.groupby("adv_tercile"):
        for date, rho in h02.rank_ic_per_date(sub, "pred", "target"):
            rows.append({"formation_date": date, "rho": rho, "tercile": tercile})
    ic = pd.DataFrame(rows)
    allv = ic.loc[ic["tercile"] == "all"].sort_values("formation_date")
    stats = ic_stats(allv["rho"].to_numpy(), lag)
    plain = kt._summarize_ic(ic, "all")
    by_tercile = {
        t: ic_stats(ic.loc[ic["tercile"] == t].sort_values("formation_date")["rho"].to_numpy(), lag)
        for t in TERCILES
        if (ic["tercile"] == t).any()
    }
    by_year = {}
    allv = allv.assign(year=pd.to_datetime(allv["formation_date"]).dt.year)
    for year, sub in allv.groupby("year"):
        by_year[str(int(year))] = ic_stats(sub["rho"].to_numpy(), lag)
    return {
        "mean_rankic": stats["mean_rankic"],
        "t_nw": stats["t_nw"],
        "nw_lag": lag,
        "n_dates": stats["n_dates"],
        "t_plain_ddof1": plain["t_stat"],
        "by_tercile": by_tercile,
        "by_year": by_year,
        "rank_autocorr": rank_autocorr(pred),
        "train_rows_mean": meta.get("train_rows_mean"),
        "n_folds_trained": meta.get("n_folds_trained"),
        "horizon": horizon,
    }


def _modal_cost_usd(job_prefix: str = "t20260930-17") -> float | None:
    if not LEDGER_ACTUALS_PATH.is_file():
        return None
    total = 0.0
    seen = False
    for line in LEDGER_ACTUALS_PATH.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if str(row.get("job", "")).startswith(job_prefix):
            for key in ("actual_cost_usd_estimate", "actual_cost_usd", "cost_usd"):
                if key in row and row[key] is not None:
                    total += float(row[key])
                    seen = True
                    break
    return round(total, 4) if seen else None


def stage_aggregate(args: argparse.Namespace) -> None:
    cells: dict[str, dict[str, Any]] = {}
    preds: dict[str, pd.DataFrame] = {}
    metas: dict[str, dict[str, Any]] = {}
    missing: list[str] = []
    max_diffs: list[float] = []
    for cell in CELL_ORDER:
        p_pred, p_meta = _locate(cell, "_pred.parquet"), _locate(cell, ".json")
        if p_pred is None or p_meta is None:
            missing.append(cell)
            continue
        meta = json.loads(p_meta.read_text())
        if meta.get("smoke"):
            raise SystemExit(f"{cell} artefact is a smoke run; rerun the shard")
        preds[cell] = pd.read_parquet(p_pred)
        metas[cell] = meta
        max_diffs.append(float(meta["h21_target_check_max_abs_diff"]))
    if missing:
        raise SystemExit(f"missing cell artefacts (rerun those shards): {missing}")

    for cell in CELL_ORDER:
        _log(f"aggregate: {cell}")
        cells[cell] = _cell_metrics(preds[cell], parse_cell(cell)[2], metas[cell])
    for win, hz in itertools.product(WINDOWS, HORIZON_TAGS):
        frames = [preds[f"{fam}_{win}_{hz}"] for fam in FAMILIES]
        for f in frames:
            f["formation_date"] = pd.to_datetime(f["formation_date"])
        ens = rank_mean_ensemble(frames)
        cell = f"{ENS_FAMILY}_{win}_{hz}"
        _log(f"aggregate: {cell}")
        ens_meta = {
            "train_rows_mean": float(
                np.mean([metas[f"{fam}_{win}_{hz}"]["train_rows_mean"] for fam in FAMILIES])
            ),
            "n_folds_trained": int(
                np.mean([metas[f"{fam}_{win}_{hz}"]["n_folds_trained"] for fam in FAMILIES])
            ),
        }
        cells[cell] = _cell_metrics(ens, HORIZON_TAGS[hz], ens_meta)

    b0 = cells[B0_CELL]["mean_rankic"]
    parity = b0_parity_ok(b0)
    effects = family_effect(cells)
    stage2 = select_stage2_cells(cells)
    generated_at = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    result = {
        "task": "T-20260930-17",
        "stage": "1_stress_window_rankic",
        "generated_at": generated_at,
        "prebacktest_validated_at": PREREG_STAMP_PATH.read_text().strip()
        if PREREG_STAMP_PATH.is_file()
        else None,
        "window": "2016-05-02..2023-08-31 (validation-role dates only)",
        "cells": {c: cells[c] for c in ALL_CELLS},
        "b0_parity": parity,
        "b0_rankic": b0,
        "b0_target": B0_RANKIC,
        "b0_tolerance": B0_TOLERANCE,
        "h21_target_check_max_abs_diff": float(max(max_diffs)),
        "family_effect": effects,
        "answer_family": answer_family(effects) if parity else "not_evaluated_b0_parity_failed",
        "stage2_cells": stage2 if parity else [],
        "stage2_cells_note": None if parity else "B0 parity failed: no other cell is interpreted",
        "modal_cost_usd": _modal_cost_usd(),
    }
    _write_json(RESULTS_PATH, result)
    REPORT_PATH.write_text(render_report(result))
    _log(f"aggregate: wrote {RESULTS_PATH} and {REPORT_PATH}")


def _fmt(x: Any, nd: int = 4) -> str:
    return "n/a" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def render_report(result: dict[str, Any]) -> str:
    lines = [
        "# T-20260930-17 stage 1: model family x training window x horizon",
        "",
        f"Generated {result['generated_at']} by scripts/run_t20260930_17_model_family_sweep.py "
        "from results_stage1.json (all numbers below are copied from that file). Design frozen in "
        "hypotheses.md. Stress window only, RankIC only, no costs. The lead decides the verdict.",
        "",
        f"- b0_parity: {result['b0_parity']} (LGBM_W3_H21 RankIC {_fmt(result['b0_rankic'], 5)}, "
        f"target {result['b0_target']} +- {result['b0_tolerance']})",
        f"- h21_target_check_max_abs_diff: {result['h21_target_check_max_abs_diff']:.3e}",
        f"- answer_family: {result['answer_family']}",
        f"- modal_cost_usd: {result['modal_cost_usd']}",
        "",
        "## 24 cells",
        "",
        "| cell | RankIC | t_nw (lag) | dates | T1 liquid | T2 mid | T3 illiquid "
        "| rank autocorr | train rows |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for cell in ALL_CELLS:
        c = result["cells"][cell]
        bt = c["by_tercile"]
        terc = [_fmt(bt.get(t, {}).get("mean_rankic")) for t in TERCILES]
        lines.append(
            f"| {cell} | {_fmt(c['mean_rankic'], 5)} | {_fmt(c['t_nw'], 2)} ({c['nw_lag']}) "
            f"| {c['n_dates']} | {terc[0]} | {terc[1]} | {terc[2]} "
            f"| {_fmt(c['rank_autocorr']['mean'], 3)} | {_fmt(c['train_rows_mean'], 0)} |"
        )
    lines += [
        "",
        "## Family effect (best non-LGBM family vs same-group LGBM)",
        "",
        "| group | LGBM | best family | its RankIC | diff | t_nw "
        "| material (diff >= 0.010 and t >= 3.0) |",
        "|---|---|---|---|---|---|---|",
    ]
    for group, e in result["family_effect"].items():
        if e.get("status") == "missing":
            lines.append(f"| {group} | missing | | | | | |")
            continue
        lines.append(
            f"| {group} | {_fmt(e['lgbm_rankic'], 5)} | {e['best_non_lgbm_family']} "
            f"| {_fmt(e['best_non_lgbm_rankic'], 5)} | {_fmt(e['diff'], 5)} "
            f"| {_fmt(e['t_nw'], 2)} | {e['material']} |"
        )
    lines += ["", "## Stage-2 cells (top 3 non-B0 by NW t, t >= 2.0)", ""]
    if result["stage2_cells"]:
        lines += [
            f"- {s['cell']}: t_nw {_fmt(s['t_nw'], 2)}, RankIC {_fmt(s['mean_rankic'], 5)}"
            for s in result["stage2_cells"]
        ]
    else:
        lines.append("- none")
    lines += ["", "## Turnover proxy (mean rank autocorrelation of predictions)", ""]
    for hz in HORIZON_TAGS:
        vals = [
            result["cells"][c]["rank_autocorr"]["mean"]
            for c in ALL_CELLS
            if c.endswith(f"_{hz}") and result["cells"][c]["rank_autocorr"]["mean"] is not None
        ]
        lines.append(f"- {hz}: mean over cells {_fmt(float(np.mean(vals)) if vals else None, 3)}")
    lines += [
        "",
        "## By-year RankIC",
        "",
    ]
    years = sorted({y for c in result["cells"].values() for y in c["by_year"]})
    lines.append("| cell | " + " | ".join(years) + " |")
    lines.append("|---|" + "---|" * len(years))
    for cell in ALL_CELLS:
        by = result["cells"][cell]["by_year"]
        lines.append(
            f"| {cell} | "
            + " | ".join(_fmt(by.get(y, {}).get("mean_rankic")) for y in years)
            + " |"
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Hyperparameters fixed, not tuned; MLP is scikit-learn (not the GKX ensemble).",
        "- Prediction files carry target and adv_tercile besides formation_date, symbol, pred.",
        "- t_nw: Newey-West lag 0 for h21, lag 2 for h63; t_plain_ddof1 (kt convention) "
        "is in results_stage1.json.",
        "- Verdict (keep / refute) is the lead's; stage 2 is not run here.",
        "",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = parser.add_subparsers(dest="stage", required=True)
    sub.add_parser("spy")
    cell = sub.add_parser("cell")
    cell.add_argument("--shard", type=int, required=True)
    cell.add_argument("--nshards", type=int, default=len(CELL_ORDER))
    cell.add_argument(
        "--smoke",
        action="store_true",
        help="train only the first 2 trainable folds (environment/path check, not a result)",
    )
    sub.add_parser("aggregate")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    {"spy": stage_spy, "cell": stage_cell, "aggregate": stage_aggregate}[args.stage](args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
