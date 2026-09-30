"""T-20260930-19 (dossier t20260930_17b_model_family_book): stage 2 of the
model-family sweep -- cost-adjusted long-only monthly books from the three
stage-1 cells XGB_WX_H63, LGBM_WX_H63, CAT_WX_H63, judged by the frozen K1/K2
rules written in ``t20260930_17_model_family_sweep/hypotheses.md``.

Pre-registration: ``reports/research/iterations/t20260930_17b_model_family_book/
hypotheses.md``. This script only executes it. The two earlier scripts
(``run_t20260928_30_smallcap_ml_book`` = ``book``, ``run_t20260930_17_model_
family_sweep`` = ``sweep``) are imported, never edited.

Stages: cohort, liquidity (book's own, cache redirected to this dossier),
predict (per cell: daily out-of-fold predictions + validation-role RankIC),
portfolio (V1/V2 x 21 offsets x four cost tiers), placebo (shared by the three
WX_H63 cells), report (parity checks, K1/K2, DSR, verdict), cost (local: copy
the Modal cost from the ledger into results.json). ``all`` runs the first six.

Usage (Modal): see the brief ``reports/research/control/briefs/T-20260930-19.md``.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing
import sys
import time
import warnings
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import scripts.run_t20260928_30_smallcap_ml_book as book  # noqa: E402
import scripts.run_t20260930_17_model_family_sweep as sweep  # noqa: E402
from open_composer.research.campaign_statistics import deflated_sharpe_probability  # noqa: E402
from scripts import screen_lane  # noqa: E402

warnings.filterwarnings("ignore", message="X does not have valid feature names")
kt = book.kt
h02 = kt.h02
base = book.base

ITERATION_ID = "t20260930_17b_model_family_book"
ITER_DIR = ROOT / "reports" / "research" / "iterations" / ITERATION_ID
CACHE_DIR = ITER_DIR / "cache"
RESULTS_PATH = ITER_DIR / "results.json"
REPORT_PATH = ITER_DIR / "report.md"
STAGE1_RESULTS_PATH = (
    ROOT / "reports/research/iterations/t20260930_17_model_family_sweep/results_stage1.json"
)
PREREG_STAMP_PATH = ITER_DIR / "prebacktest-validated-at.txt"
LEDGER_ACTUALS_PATH = ROOT / "reports/research/control/modal-ledger-actuals.jsonl"

CELLS: tuple[str, ...] = ("XGB_WX_H63", "LGBM_WX_H63", "CAT_WX_H63")
PARITY_CELL = "LGBM_W3_H21"
ALL_PREDICT_CELLS: tuple[str, ...] = (*CELLS, PARITY_CELL)
VARIANTS: tuple[str, ...] = ("V1", "V2")
WINDOW_NAMES: tuple[str, ...] = ("stress", "select", "anchor", "holdout")
COST_TIERS: dict[str, tuple[float, float]] = {
    "flat10": (10.0, 0.0),
    "flat20": (20.0, 0.0),
    "base_ar": (10.0, 0.5),
    "stress_ar": (20.0, 1.0),
}
OFFSETS = book.OFFSETS
PLACEBO_SEEDS = 20

# Frozen rules (hypotheses.md, copied from the stage-1 dossier).
K1_STRESS_SHARPE_MIN = 0.65
K1_ANCHOR_SHARPE_MIN = 1.19
K2_EDGE_MIN = 0.05
DSR_TRIAL_COUNT = 30
PARITY_RANKIC_TOL = 0.002
PARITY_BOOK_TOL = 0.05
PARITY_STAGE1_START = pd.Timestamp("2016-05-02")
PARITY_STAGE1_END = pd.Timestamp("2023-08-31")
PARITY_B0_REF = {"stress": 0.462, "anchor": 0.327}
PARITY_B0_WINDOWS = {"stress": ("2017-07-03", "2023-08-31"), "anchor": ("2024-01-08", "2026-09-17")}
H21_TARGET_TOL = 1e-9

_T0 = time.time()
_CTX: dict[str, Any] = {}


def _log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')} +{time.time() - _T0:7.1f}s] {message}", flush=True)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=h02._json_default) + "\n"
    )


def _set_paths(smoke: bool) -> None:
    """Redirect every artefact of a smoke run; the real ones are never touched."""
    global CACHE_DIR, RESULTS_PATH, REPORT_PATH
    CACHE_DIR = ITER_DIR / ("cache_smoke" if smoke else "cache")
    RESULTS_PATH = ITER_DIR / ("results_smoke.json" if smoke else "results.json")
    REPORT_PATH = ITER_DIR / ("report_smoke.md" if smoke else "report.md")
    book.CACHE_DIR = CACHE_DIR


# --------------------------------------------------------------------------
# pure functions -- unit tested in tests/test_t20260930_17b_model_family_book.py
# --------------------------------------------------------------------------


def k1_pass(
    stress_sharpe_flat10: float,
    anchor_sharpe_flat10: float,
    stress_cagr_flat20: float,
    anchor_cagr_flat20: float,
) -> bool:
    """K1: flat-10bp offset-median Sharpe >= 0.65 (stress) and >= 1.19
    (anchor), and flat-20bp CAGR > 0 in both windows. NaN never passes."""
    return bool(
        stress_sharpe_flat10 >= K1_STRESS_SHARPE_MIN
        and anchor_sharpe_flat10 >= K1_ANCHOR_SHARPE_MIN
        and stress_cagr_flat20 > 0
        and anchor_cagr_flat20 > 0
    )


def k2_pass(stress_edge: float, anchor_edge: float) -> bool:
    return bool(stress_edge >= K2_EDGE_MIN and anchor_edge >= K2_EDGE_MIN)


def verdict(parity_all_ok: bool, any_k1: bool, any_k2: bool) -> str:
    if not parity_all_ok:
        return "parity_failed"
    if any_k1 or any_k2:
        return "pass_pending_spreads"
    return "refuted"


def parity_rankic_ok(stage2: float | None, stage1: float | None) -> tuple[float | None, bool]:
    """``(abs_diff, ok)`` for the stage-1 RankIC reproduction (<= 0.002)."""
    if stage2 is None or stage1 is None or not np.isfinite(stage2) or not np.isfinite(stage1):
        return None, False
    diff = abs(float(stage2) - float(stage1))
    return diff, bool(diff <= PARITY_RANKIC_TOL)


def parity_book_ok(stress: float, anchor: float) -> bool:
    """B0 book reproduction: both offset-median Sharpes within 0.05 of T-28-30."""
    return bool(
        np.isfinite(stress)
        and np.isfinite(anchor)
        and abs(stress - PARITY_B0_REF["stress"]) <= PARITY_BOOK_TOL
        and abs(anchor - PARITY_B0_REF["anchor"]) <= PARITY_BOOK_TOL
    )


def assert_same_panel_keys(panels: dict[str, pd.DataFrame]) -> None:
    """The placebo is shared, so every cell must cover the identical
    (trade_date, symbol) set. Raises AssertionError naming the first mismatch."""
    names = list(panels)
    ref = panels[names[0]][["trade_date", "symbol"]].drop_duplicates()
    ref_keys = pd.MultiIndex.from_frame(ref)
    for name in names[1:]:
        other = panels[name][["trade_date", "symbol"]].drop_duplicates()
        other_keys = pd.MultiIndex.from_frame(other)
        if len(ref_keys) != len(other_keys) or not ref_keys.sort_values().equals(
            other_keys.sort_values()
        ):
            raise AssertionError(
                f"prediction panels differ: {names[0]} has {len(ref_keys)} keys, "
                f"{name} has {len(other_keys)} (or different members)"
            )


def test_quarter_days(
    trading_calendar: pd.DatetimeIndex, test_dates: list[pd.Timestamp]
) -> pd.DatetimeIndex:
    """Every trading day of the calendar quarter that the fold's test role
    (its first test formation date) sits in."""
    quarter = pd.Timestamp(test_dates[0]).to_period("Q")
    return trading_calendar[trading_calendar.to_period("Q") == quarter]


def parity_stage2_mean(val_ic: pd.DataFrame) -> tuple[float | None, int]:
    """Mean validation-role RankIC over 2016-05-02..2023-08-31 (same window as
    stage 1) and the number of dates."""
    dates = pd.to_datetime(val_ic["formation_date"])
    sel = val_ic.loc[(dates >= PARITY_STAGE1_START) & (dates <= PARITY_STAGE1_END), "rho"]
    sel = sel.loc[np.isfinite(sel)]
    if sel.empty:
        return None, 0
    return float(sel.mean()), int(len(sel))


def win_rate(real_median: float, placebo_medians: list[float]) -> float:
    """Fraction of finite placebo seeds whose offset-median Sharpe the real
    book's offset-median Sharpe exceeds."""
    finite = [p for p in placebo_medians if np.isfinite(p)]
    if not finite or not np.isfinite(real_median):
        return float("nan")
    return float(np.mean([real_median > p for p in finite]))


def modal_cost_from_ledger(lines: list[str], job: str) -> float | None:
    """Sum of ``actual_cost_usd_estimate`` over ledger rows of this exact job."""
    total = 0.0
    found = False
    for line in lines:
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("job") == job:
            total += float(row.get("actual_cost_usd_estimate", 0.0))
            found = True
    return total if found else None


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _workers() -> int:
    return max(1, sweep._threads())


def _pmap(func, jobs: list, workers: int) -> list:
    """Order-preserving map; fork pool so ``_CTX`` is shared copy-on-write."""
    if workers <= 1 or len(jobs) <= 1:
        return [func(j) for j in jobs]
    ctx = multiprocessing.get_context("fork")
    with ctx.Pool(processes=min(workers, len(jobs))) as pool:
        return pool.map(func, jobs, chunksize=1)


def _load_market() -> dict[str, Any]:
    close = pd.read_parquet(CACHE_DIR / "close_sanitized.parquet")
    open_ = pd.read_parquet(CACHE_DIR / "open_sanitized.parquet")
    close.index = h02._ns(close.index)
    open_.index = h02._ns(open_.index)
    trading_index = close.index
    prev_close = close.shift(1)
    return {
        "trading_index": trading_index,
        "leg_open": (open_ / prev_close - 1.0).fillna(0.0),
        "leg_close": (close / open_ - 1.0).fillna(0.0),
        "rf": book.get_rf_series(trading_index),
    }


def _load_liquidity_lookup() -> dict:
    liquidity = pd.read_parquet(CACHE_DIR / "liquidity.parquet")
    liquidity["trade_date"] = h02._ns(liquidity["trade_date"])
    return book._liquidity_lookup(liquidity)


def _read_predictions(cell: str) -> pd.DataFrame:
    pred = pd.read_parquet(CACHE_DIR / f"predictions_{cell}.parquet")
    pred["trade_date"] = h02._ns(pred["trade_date"])
    return pred


# --------------------------------------------------------------------------
# stage: predict
# --------------------------------------------------------------------------


def _cell_target(
    cell: str, monthly_panel: pd.DataFrame, close_sanitized: pd.DataFrame
) -> np.ndarray:
    _family, _window, horizon = sweep.parse_cell(cell)
    if horizon == 21:
        return monthly_panel["target_excess_21"].to_numpy(dtype="float64")
    built = kt.build_target(monthly_panel, close_sanitized, horizon)
    return built[f"target_excess_{horizon}"].to_numpy(dtype="float64")


def _check_h21_target(monthly_panel: pd.DataFrame, close_sanitized: pd.DataFrame) -> float:
    """The rebuilt H21 target must equal the panel's own column (sanity that
    build_target sees the same inputs here as in stage 1)."""
    rebuilt = kt.build_target(monthly_panel, close_sanitized, 21)["target_excess_21"].to_numpy()
    ref = monthly_panel["target_excess_21"].to_numpy()
    if (np.isnan(rebuilt) != np.isnan(ref)).any():
        raise SystemExit("h21 target check failed: NaN pattern differs")
    finite = ~np.isnan(ref)
    diff = float(np.max(np.abs(rebuilt[finite] - ref[finite]))) if finite.any() else 0.0
    if not diff < H21_TARGET_TOL:
        raise SystemExit(f"h21 target check failed: max abs diff {diff:.3e}")
    return diff


def _train_predict_cell(
    cell: str,
    panel: pd.DataFrame,
    features: list[str],
    trading_calendar: pd.DatetimeIndex,
    daily_cohort: pd.DataFrame,
    daily_dates: np.ndarray,
) -> dict[str, Any]:
    family, window, horizon = sweep.parse_cell(cell)
    train_years = kt.DEFAULT_TRAIN_YEARS if window == "W3" else sweep.EXPANDING_TRAIN_YEARS
    formation_dates = sorted(panel["formation_date"].unique())
    previous_embargo = h02.EMBARGO_DAYS
    h02.EMBARGO_DAYS = horizon
    try:
        folds = h02.build_folds(formation_dates, trading_calendar, train_years)
    finally:
        h02.EMBARGO_DAYS = previous_embargo
    _log(f"predict {cell}: {len(folds)} folds, train_years={train_years}, embargo={horizon}")

    pred_frames: list[pd.DataFrame] = []
    ic_records: list[dict[str, Any]] = []
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
            "train_rows": int(len(train_frame)),
        }
        if len(train_frame) < h02.MIN_TRAIN_ROWS or not fold.test_dates:
            meta["skipped"] = f"train_rows={len(train_frame)}, test_dates={len(fold.test_dates)}"
            fold_meta.append(meta)
            continue
        model = sweep.FamilyModel(family)
        model.fit(
            train_frame[features].to_numpy(dtype="float64"),
            train_frame["target"].to_numpy(dtype="float64"),
        )
        trained += 1
        # (b) validation-role monthly RankIC (same call as sweep._train_cell)
        val_frame = panel.loc[panel["formation_date"].isin(fold.validation_dates)].dropna(
            subset=["target"]
        )
        if not val_frame.empty:
            scored = val_frame[["formation_date", "symbol", "adv_tercile", "target"]].copy()
            scored["pred"] = model.predict(val_frame[features].to_numpy(dtype="float64"))
            for date, rho in h02.rank_ic_per_date(scored, "pred", "target"):
                ic_records.append({"formation_date": date, "rho": rho, "fold_id": fold.fold_id})
        # (a) daily predictions over the test-role quarter (same as book.stage_predict)
        coverage_days = test_quarter_days(trading_calendar, fold.test_dates)
        lo = np.searchsorted(daily_dates, np.datetime64(coverage_days[0]), side="left")
        hi = np.searchsorted(daily_dates, np.datetime64(coverage_days[-1]), side="right")
        day_panel = daily_cohort.iloc[lo:hi].dropna(subset=features, how="all")
        meta["coverage_days"] = int(len(coverage_days))
        if not day_panel.empty:
            out = day_panel[["trade_date", "symbol", "adv_tercile", "adv_rank"]].copy()
            out["prediction"] = model.predict(day_panel[features].to_numpy(dtype="float64"))
            out["fold_id"] = fold.fold_id
            pred_frames.append(out)
            meta["coverage_start"] = str(coverage_days[0].date())
            meta["coverage_end"] = str(coverage_days[-1].date())
        meta["seconds"] = round(time.time() - t0, 1)
        fold_meta.append(meta)
        _log(f"predict {cell}: fold {fold.fold_id} {meta['seconds']}s")

    predictions = (
        pd.concat(pred_frames, ignore_index=True)
        if pred_frames
        else pd.DataFrame(
            columns=[
                "trade_date",
                "symbol",
                "adv_tercile",
                "adv_rank",
                "prediction",
                "fold_id",
            ]
        )
    )
    predictions = predictions.sort_values(["trade_date", "symbol"]).reset_index(drop=True)
    predictions.to_parquet(CACHE_DIR / f"predictions_{cell}.parquet", index=False)
    ic_frame = pd.DataFrame(ic_records, columns=["formation_date", "rho", "fold_id"])
    ic_frame.to_parquet(CACHE_DIR / f"val_ic_{cell}.parquet", index=False)
    _write_json(CACHE_DIR / f"fold_meta_{cell}.json", fold_meta)
    _log(
        f"predict {cell}: wrote {len(predictions):,} prediction rows, "
        f"{len(ic_frame)} validation dates, {trained} folds trained"
    )
    return {"n_folds": trained, "n_fold_slots": len(folds)}


def stage_predict(args: argparse.Namespace) -> None:
    manifest = json.loads((CACHE_DIR / "cohort_manifest.json").read_text())
    features: list[str] = manifest["kept_features"]
    monthly_panel = pd.read_parquet(CACHE_DIR / "monthly_panel.parquet")
    monthly_panel["formation_date"] = h02._ns(monthly_panel["formation_date"])
    close_sanitized = pd.read_parquet(CACHE_DIR / "close_sanitized.parquet")
    close_sanitized.index = h02._ns(close_sanitized.index)
    trading_calendar = pd.DatetimeIndex(close_sanitized.index)
    diff = _check_h21_target(monthly_panel, close_sanitized)
    _log(f"predict: h21 target rebuild max_abs_diff={diff:.3e}")

    daily_cohort = pd.read_parquet(CACHE_DIR / "daily_cohort.parquet")
    daily_cohort["trade_date"] = h02._ns(daily_cohort["trade_date"])
    daily_cohort = daily_cohort.sort_values("trade_date").reset_index(drop=True)
    daily_dates = daily_cohort["trade_date"].to_numpy(dtype="datetime64[ns]")

    summary: dict[str, Any] = {}
    targets: dict[int, np.ndarray] = {}
    for cell in ALL_PREDICT_CELLS:
        out_path = CACHE_DIR / f"predictions_{cell}.parquet"
        if out_path.exists() and not args.force:
            _log(f"predict {cell}: present -- reusing")
            meta = json.loads((CACHE_DIR / f"fold_meta_{cell}.json").read_text())
            summary[cell] = {"n_folds": sum(1 for m in meta if "seconds" in m)}
            continue
        horizon = sweep.parse_cell(cell)[2]
        if horizon not in targets:
            targets[horizon] = _cell_target(cell, monthly_panel, close_sanitized)
        panel = monthly_panel[["formation_date", "symbol", "adv_tercile", *features]].copy()
        panel["target"] = targets[horizon]
        summary[cell] = _train_predict_cell(
            cell, panel, features, trading_calendar, daily_cohort, daily_dates
        )
    _write_json(CACHE_DIR / "predict_summary.json", summary)


# --------------------------------------------------------------------------
# stage: portfolio
# --------------------------------------------------------------------------


def _offset_job(job: tuple[str, str, int, tuple[str, ...], dict]) -> dict[str, Any]:
    """One (cell, variant, offset): simulate the requested cost tiers."""
    cell, variant, offset, tiers, windows = job
    market = _CTX["market"]
    trading_index = market["trading_index"]
    holdings = book.build_signal_book(_CTX["predictions"][cell], variant, trading_index, offset)
    out: dict[str, Any] = {"cell": cell, "variant": variant, "offset": offset, "tiers": {}}
    for tier in tiers:
        flat_bps, spread_w = COST_TIERS[tier]
        ret, turn = book.simulate_book(
            holdings,
            trading_index,
            market["leg_open"],
            market["leg_close"],
            _CTX["liquidity"],
            flat_bps,
            spread_w,
        )
        if tier == "flat10":
            out["flat10_ret"] = ret
        per_window = {}
        for wname, (a, b) in windows.items():
            mask = (trading_index >= a) & (trading_index <= b)
            per_window[wname] = asdict(base.metrics(ret.loc[mask], market["rf"], turn.loc[mask]))
        out["tiers"][tier] = per_window
    return out


def _summarize_book(results: list[dict[str, Any]], windows: dict, tiers: tuple[str, ...]) -> dict:
    """``{window: {tier: {...offset summary...}}}`` plus judged offsets."""
    by_offset = {r["offset"]: r for r in results}
    out: dict[str, Any] = {}
    for wname in windows:
        cell_out: dict[str, Any] = {}
        for tier in tiers:
            summ = book.offset_metric_summary(
                {o: by_offset[o]["tiers"][tier][wname] for o in OFFSETS}
            )
            cell_out[tier] = {
                "sharpe_median": summ["sharpe"]["median"],
                "sharpe_min": summ["sharpe"]["min"],
                "sharpe_max": summ["sharpe"]["max"],
                "cagr_median": summ["cagr"]["median"],
                "max_dd_median": summ["max_dd"]["median"],
                "turnover_yr_median": summ["turnover_yr"]["median"],
            }
        sharpe_by_offset = {o: by_offset[o]["tiers"]["flat10"][wname]["sharpe"] for o in OFFSETS}
        cell_out["judged_offset_flat10"] = book._judged_offset(sharpe_by_offset)
        out[wname] = cell_out
    return out


def stage_portfolio(args: argparse.Namespace) -> None:
    out_path = CACHE_DIR / "portfolio_results.json"
    if out_path.exists() and not args.force:
        _log(f"portfolio: {out_path} present -- reusing")
        return
    market = _load_market()
    _CTX["market"] = market
    _CTX["liquidity"] = _load_liquidity_lookup()
    _CTX["predictions"] = {c: _read_predictions(c) for c in ALL_PREDICT_CELLS}
    latest = market["trading_index"][-1]
    first_predicted = {c: _CTX["predictions"][c]["trade_date"].min() for c in ALL_PREDICT_CELLS}
    windows = {
        c: book.resolve_windows(first_predicted[c], latest) for c in CELLS
    }  # per cell; the three WX cells share one panel so the windows coincide
    if len({json.dumps(w, sort_keys=True) for w in windows.values()}) != 1:
        raise SystemExit(f"portfolio: WX cell windows differ: {windows}")
    shared_windows = windows[CELLS[0]]
    _log(f"portfolio: windows {shared_windows}")
    workers = _workers()

    books: dict[str, Any] = {}
    for cell in CELLS:
        for variant in VARIANTS:
            key = f"{cell}_{variant}"
            _log(f"portfolio: {key} ({len(OFFSETS)} offsets, {workers} workers)")
            jobs = [(cell, variant, o, tuple(COST_TIERS), shared_windows) for o in OFFSETS]
            results = _pmap(_offset_job, jobs, workers)
            books[key] = {
                "windows": shared_windows,
                **_summ_and_save(results, cell, variant, shared_windows),
            }
    # B0 reproduction: V1, flat10 only, T-28-30's own windows
    _log("portfolio: LGBM_W3_H21_V1 parity book")
    jobs = [(PARITY_CELL, "V1", o, ("flat10",), PARITY_B0_WINDOWS) for o in OFFSETS]
    results = _pmap(_offset_job, jobs, workers)
    parity_book = {
        "windows": PARITY_B0_WINDOWS,
        **_summ_and_save(results, PARITY_CELL, "V1", PARITY_B0_WINDOWS, tiers=("flat10",)),
    }
    _write_json(
        out_path,
        {
            "windows": shared_windows,
            "first_predicted_by_cell": {c: str(t.date()) for c, t in first_predicted.items()},
            "latest_data_date": str(latest.date()),
            "books": books,
            "parity_book": parity_book,
        },
    )
    _log(f"portfolio: wrote {out_path}")


def _summ_and_save(
    results: list[dict[str, Any]],
    cell: str,
    variant: str,
    windows: dict,
    tiers: tuple[str, ...] = tuple(COST_TIERS),
) -> dict[str, Any]:
    for r in results:
        r["flat10_ret"].to_frame("ret").to_parquet(
            CACHE_DIR / f"ret_{cell}_{variant}_o{r['offset']}.parquet"
        )
    return {"summary": _summarize_book(results, windows, tiers)}


# --------------------------------------------------------------------------
# stage: placebo
# --------------------------------------------------------------------------


def _placebo_job(job: tuple[str, int, dict]) -> dict[str, float]:
    variant, seed, windows = job
    market = _CTX["market"]
    trading_index = market["trading_index"]
    sharpes: dict[str, dict[int, float]] = {w: {} for w in windows}
    for o in OFFSETS:
        holdings = book.build_random_book(_CTX["placebo_panel"], variant, trading_index, o, seed)
        ret, turn = book.simulate_book(
            holdings,
            trading_index,
            market["leg_open"],
            market["leg_close"],
            _CTX["liquidity"],
            *COST_TIERS["flat10"],
        )
        for wname, (a, b) in windows.items():
            mask = (trading_index >= a) & (trading_index <= b)
            sharpes[wname][o] = base.metrics(ret.loc[mask], market["rf"], turn.loc[mask]).sharpe
    out = {}
    for wname in windows:
        vals = [v for v in sharpes[wname].values() if np.isfinite(v)]
        out[wname] = float(np.median(vals)) if vals else float("nan")
    return out


def stage_placebo(args: argparse.Namespace) -> None:
    out_path = CACHE_DIR / "placebo_results.json"
    if out_path.exists() and not args.force:
        _log(f"placebo: {out_path} present -- reusing")
        return
    panels = {c: _read_predictions(c) for c in CELLS}
    assert_same_panel_keys(panels)
    _log("placebo: prediction panels of the three WX_H63 cells have identical (date, symbol) sets")
    portfolio = json.loads((CACHE_DIR / "portfolio_results.json").read_text())
    windows = {w: portfolio["windows"][w] for w in ("stress", "anchor")}
    market = _load_market()
    _CTX["market"] = market
    _CTX["liquidity"] = _load_liquidity_lookup()
    _CTX["placebo_panel"] = panels[CELLS[0]]
    workers = _workers()
    result: dict[str, Any] = {"seeds": PLACEBO_SEEDS, "windows": windows}
    for variant in VARIANTS:
        jobs = [(variant, seed, windows) for seed in range(PLACEBO_SEEDS)]
        medians = _pmap(_placebo_job, jobs, workers)
        result[variant] = {w: [m[w] for m in medians] for w in windows}
        _log(f"placebo: {variant} done")
    _write_json(out_path, result)


# --------------------------------------------------------------------------
# stage: report
# --------------------------------------------------------------------------


def _fmt(x: float | None, pct: bool = False, digits: int = 3) -> str:
    if x is None or not np.isfinite(x):
        return "NA"
    return f"{x * 100:.1f}%" if pct else f"{x:.{digits}f}"


def _parity(portfolio: dict) -> dict[str, Any]:
    stage1 = json.loads(STAGE1_RESULTS_PATH.read_text())["cells"]
    stage1_ic: dict[str, Any] = {}
    for cell in ALL_PREDICT_CELLS:
        val_ic = pd.read_parquet(CACHE_DIR / f"val_ic_{cell}.parquet")
        stage2_mean, n_dates = parity_stage2_mean(val_ic)
        ref = stage1[cell]["mean_rankic"]
        diff, ok = parity_rankic_ok(stage2_mean, ref)
        stage1_ic[cell] = {
            "stage2": stage2_mean,
            "stage1": ref,
            "abs_diff": diff,
            "n_dates": n_dates,
            "ok": ok,
        }
    pb = portfolio["parity_book"]["summary"]
    stress = pb["stress"]["flat10"]["sharpe_median"]
    anchor = pb["anchor"]["flat10"]["sharpe_median"]
    b0 = {
        "stress": stress,
        "anchor": anchor,
        "ref_stress": PARITY_B0_REF["stress"],
        "ref_anchor": PARITY_B0_REF["anchor"],
        "windows": PARITY_B0_WINDOWS,
        "ok": parity_book_ok(stress, anchor),
    }
    all_ok = bool(all(v["ok"] for v in stage1_ic.values()) and b0["ok"])
    return {"stage1_rankic": stage1_ic, "b0_book": b0, "all_ok": all_ok}


def stage_report(args: argparse.Namespace) -> None:
    portfolio = json.loads((CACHE_DIR / "portfolio_results.json").read_text())
    placebo = json.loads((CACHE_DIR / "placebo_results.json").read_text())
    windows = portfolio["windows"]
    market = _load_market()
    rf = market["rf"]

    parity = _parity(portfolio)

    # K2: S3 combination (same calls as book.stage_report)
    base.WARMUP_START = screen_lane.PANEL_START
    etf_close, etf_open = base.load_panel(book.salvage.symbols())
    etf_leg_open, etf_leg_close = book.salvage.legs(etf_close, etf_open)
    etf_rf = (etf_close[screen_lane.RF] / etf_close[screen_lane.RF].shift(1) - 1.0).fillna(0.0)
    etf_shy_ret = (etf_close[screen_lane.CASH] / etf_close[screen_lane.CASH].shift(1) - 1.0).fillna(
        0.0
    )
    s3_ret10, _s3_turn10 = screen_lane.s3_incumbent(
        etf_close, etf_leg_open, etf_leg_close, screen_lane.COST_BPS_PRIMARY
    )

    k1_out: dict[str, Any] = {}
    k2_out: dict[str, Any] = {}
    placebo_out: dict[str, Any] = {}
    dsr_out: dict[str, Any] = {}
    for key, entry in portfolio["books"].items():
        cell, variant = key.rsplit("_", 1)
        summ = entry["summary"]
        s_sh = summ["stress"]["flat10"]["sharpe_median"]
        a_sh = summ["anchor"]["flat10"]["sharpe_median"]
        s_cg = summ["stress"]["flat20"]["cagr_median"]
        a_cg = summ["anchor"]["flat20"]["cagr_median"]
        k1_out[key] = {
            "stress_sharpe_flat10": s_sh,
            "anchor_sharpe_flat10": a_sh,
            "stress_cagr_flat20": s_cg,
            "anchor_cagr_flat20": a_cg,
            "pass": k1_pass(s_sh, a_sh, s_cg, a_cg),
        }
        edges: dict[str, float] = {}
        for wname in ("stress", "anchor"):
            vals = []
            for o in OFFSETS:
                ret = pd.read_parquet(CACHE_DIR / f"ret_{cell}_{variant}_o{o}.parquet")["ret"]
                vals.append(
                    screen_lane.diversifier_edge_for_offset(
                        s3_ret10, ret, etf_shy_ret, etf_rf, tuple(windows[wname])
                    )
                )
            edges[wname] = float(np.median(vals))
        k2_out[key] = {**edges, "pass": k2_pass(edges["stress"], edges["anchor"])}
        placebo_out[key] = {
            "stress_beat": win_rate(s_sh, placebo[variant]["stress"]),
            "anchor_beat": win_rate(a_sh, placebo[variant]["anchor"]),
            "seeds": placebo["seeds"],
        }
        judged = summ["anchor"]["judged_offset_flat10"]
        judged_ret = pd.read_parquet(CACHE_DIR / f"ret_{cell}_{variant}_o{judged}.parquet")["ret"]
        a, b = windows["anchor"]
        mask = (judged_ret.index >= a) & (judged_ret.index <= b)
        excess = (
            (judged_ret.loc[mask] - rf.reindex(judged_ret.index).fillna(0.0).loc[mask])
            .dropna()
            .to_numpy()
        )
        try:
            dsr_out[key] = float(
                deflated_sharpe_probability(
                    excess, trial_count=DSR_TRIAL_COUNT, hac_lag=screen_lane.DSR_HAC_LAG
                )
            )
        except ValueError as exc:
            dsr_out[key] = None
            _log(f"report: DSR failed for {key}: {exc}")
        _log(f"report: {key} k1={k1_out[key]['pass']} k2={k2_out[key]['pass']}")

    predict_summary = json.loads((CACHE_DIR / "predict_summary.json").read_text())
    verdict_str = verdict(
        parity["all_ok"],
        any(v["pass"] for v in k1_out.values()),
        any(v["pass"] for v in k2_out.values()),
    )
    results = {
        "task": "T-20260930-19",
        "generated_at": datetime.now(UTC).isoformat(),
        "prebacktest_validated_at": PREREG_STAMP_PATH.read_text().strip()
        if PREREG_STAMP_PATH.is_file()
        else None,
        "smoke": bool(args.smoke),
        "first_predicted": portfolio["first_predicted_by_cell"][CELLS[0]],
        "first_predicted_by_cell": portfolio["first_predicted_by_cell"],
        "latest_data_date": portfolio["latest_data_date"],
        "windows": windows,
        "n_folds": {c: predict_summary[c]["n_folds"] for c in ALL_PREDICT_CELLS},
        "parity": parity,
        "books": {k: v["summary"] for k, v in portfolio["books"].items()},
        "k1": k1_out,
        "k2": k2_out,
        "placebo": placebo_out,
        "dsr": dsr_out,
        "dsr_trial_count": DSR_TRIAL_COUNT,
        "verdict": verdict_str,
        "modal_cost_usd": None,
    }
    _write_json(RESULTS_PATH, results)
    _log(f"report: wrote {RESULTS_PATH}")
    _write_markdown(results)


def _write_markdown(results: dict[str, Any]) -> None:
    lines = [
        "# T-20260930-19 模型族扫描阶段 2：三个 WX_H63 格的扣成本只做多月度组合",
        "",
        "预注册：`hypotheses.md`（本目录）。只写数字，不写结论；裁定由主审轮给出。",
        f"流程结果 `verdict` = `{results['verdict']}`（按预注册规则机械得出）。",
        "",
        "## 核对",
        "",
        "| 格 | 阶段 2 RankIC | 阶段 1 RankIC | 绝对差 | 日期数 | ok |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for cell, v in results["parity"]["stage1_rankic"].items():
        lines.append(
            f"| {cell} | {_fmt(v['stage2'], digits=5)} | {_fmt(v['stage1'], digits=5)} "
            f"| {_fmt(v['abs_diff'], digits=5)} | {v['n_dates']} | {v['ok']} |"
        )
    b0 = results["parity"]["b0_book"]
    lines += [
        "",
        f"B0 组合复现（LGBM_W3_H21 V1 flat10 偏移中位数夏普，T-28-30 窗口）：压力期 "
        f"{_fmt(b0['stress'])}（参照 {b0['ref_stress']}），对标窗 {_fmt(b0['anchor'])}"
        f"（参照 {b0['ref_anchor']}），ok = {b0['ok']}。`all_ok` = {results['parity']['all_ok']}。",
        "",
        "## 六本书（偏移中位数；K2 = 10 bp 下与 S3 同波动对比的夏普增量）",
        "",
        f"窗口：压力期 {results['windows']['stress']}，对标窗 {results['windows']['anchor']}。",
        "",
        "| 书 | 窗口 | flat10 夏普 | flat20 年化 | K2 增量 | 安慰剂打赢比例 |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for key in results["books"]:
        for wname, tag in (("stress", "压力期"), ("anchor", "对标窗")):
            s = results["books"][key][wname]
            lines.append(
                f"| {key} | {tag} | {_fmt(s['flat10']['sharpe_median'])} "
                f"| {_fmt(s['flat20']['cagr_median'], pct=True)} "
                f"| {_fmt(results['k2'][key][wname])} "
                f"| {_fmt(results['placebo'][key][wname + '_beat'], pct=True)} |"
            )
    lines += ["", "## K1 / K2 / DSR（试验次数固定 30，只报告）", ""]
    for key in results["books"]:
        lines.append(
            f"- {key}: K1 = {results['k1'][key]['pass']}，K2 = {results['k2'][key]['pass']}，"
            f"DSR = {_fmt(results['dsr'][key])}"
        )
    lines += [
        "",
        "日线 AR 价差成本（base_ar / stress_ar）只在 `results.json` 的 `books` 里报告，"
        "偏高（数据坑 #58），不参与判定。2026 留出窗同样只在 `results.json` 里，受污染，只参考。",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    _log(f"report: wrote {REPORT_PATH}")


def _prune_heavy_cache() -> None:
    """Rebuildable multi-hundred-MB intermediates are dropped at the end of a
    full container run so the Modal output tarball stays small."""
    for name in (
        "daily_cohort.parquet",
        "monthly_panel.parquet",
        "close_sanitized.parquet",
        "open_sanitized.parquet",
        "liquidity.parquet",
    ):
        path = CACHE_DIR / name
        if path.exists():
            path.unlink()
            _log(f"prune: removed {path.name}")


def stage_cost(args: argparse.Namespace) -> None:
    """Local: write the Modal cost of the real job from the ledger into results.json."""
    job = "t20260930-19-smoke" if args.smoke else "t20260930-19-real"
    lines = LEDGER_ACTUALS_PATH.read_text().splitlines() if LEDGER_ACTUALS_PATH.is_file() else []
    cost = modal_cost_from_ledger(lines, job)
    results = json.loads(RESULTS_PATH.read_text())
    results["modal_cost_usd"] = cost
    results["modal_cost_job"] = job
    _write_json(RESULTS_PATH, results)
    print(f"{job}: modal_cost_usd={cost}")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        choices=[
            "cohort",
            "liquidity",
            "predict",
            "portfolio",
            "placebo",
            "report",
            "cost",
            "all",
        ],
        default="all",
    )
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--max-symbols", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--keep-heavy-cache",
        action="store_true",
        help="do not delete the large rebuildable intermediates after a full run",
    )
    return parser


def _book_args(args: argparse.Namespace) -> argparse.Namespace:
    book_args = book.build_parser().parse_args([])
    book_args.window_end = book._resolve_window_end(None)
    book_args.smoke = args.smoke
    book_args.max_symbols = args.max_symbols
    book_args.force = args.force
    return book_args


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    _set_paths(args.smoke)
    ITER_DIR.mkdir(parents=True, exist_ok=True)
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if args.smoke:
        import catboost  # noqa: F401
        import xgboost  # noqa: F401

        _log("smoke: xgboost and catboost import ok")
    stages = (
        ["cohort", "liquidity", "predict", "portfolio", "placebo", "report"]
        if args.stage == "all"
        else [args.stage]
    )
    for stage in stages:
        _log(f"=== stage {stage} ===")
        if stage == "cohort":
            book.stage_cohort(_book_args(args))
        elif stage == "liquidity":
            book.stage_liquidity(_book_args(args))
        elif stage == "predict":
            stage_predict(args)
        elif stage == "portfolio":
            stage_portfolio(args)
        elif stage == "placebo":
            stage_placebo(args)
        elif stage == "report":
            stage_report(args)
        elif stage == "cost":
            stage_cost(args)
    if args.stage == "all" and not args.keep_heavy_cache:
        _prune_heavy_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
