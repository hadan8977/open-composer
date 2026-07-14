from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import ElasticNet, LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.config import ensure_dir, project_root
from open_composer.research.multiasset_momentum import (
    ALL_ETF_SYMBOLS,
    _load_panels,
    _relpath,
)
from open_composer.storage import append_jsonl, write_json

ITER_ID = "mom_multiasset_ml_r1"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
SOURCE_ITER_DIR = Path("reports/research/iterations/mom_multiasset_r1")
FEATURES = (
    "mom_21_rank",
    "mom_63_rank",
    "mom_126_skip21_rank",
    "mom_252_skip21_rank",
    "high_252_rank",
    "vol_21_rank",
    "downside_vol_63_rank",
    "drawdown_63_rank",
    "volume_surprise_rank",
    "relative_spy_126_rank",
    "sector_relative_126_rank",
    "trend_consistency_rank",
)
HORIZON_BARS = 21
EMBARGO_BARS = 21
LOCKBOX_DECISION_DATES = 6
TOP_N = 5
RANDOM_SEED = 77
BASE_COST_BPS = 10.0


class MultiassetMLResult:
    def __init__(
        self,
        report_path: Path,
        markdown_path: Path,
        trial_ledger_path: Path,
        payload: dict[str, Any],
    ) -> None:
        self.report_path = report_path
        self.markdown_path = markdown_path
        self.trial_ledger_path = trial_ledger_path
        self.payload = payload


def run_multiasset_momentum_ml(
    root: Path | None = None,
    *,
    cost_bps: float = BASE_COST_BPS,
) -> MultiassetMLResult:
    base = root or project_root()
    output = ensure_dir(base / OUTPUT_DIR)
    source_manifest_path = base / SOURCE_ITER_DIR / "universe-manifest.json"
    source_eval_path = base / SOURCE_ITER_DIR / "evaluation-report.json"
    if not source_manifest_path.exists() or not source_eval_path.exists():
        raise FileNotFoundError("complete mom_multiasset_r1 before the ML round")
    manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    stock_symbols = [str(symbol) for symbol in manifest["selected_symbols"]]
    sector_map = {
        str(row["symbol"]): str(row.get("sector") or "Unknown") for row in manifest["selected"]
    }
    data = _load_panels(base, list(dict.fromkeys((*stock_symbols, *ALL_ETF_SYMBOLS))))
    dataset, latest_features = _build_panel_dataset(data, stock_symbols, sector_map)
    dates = sorted(pd.to_datetime(dataset["decision_date"], utc=True).unique())
    if len(dates) < 24:
        raise ValueError("ML round requires at least 24 monthly decision dates")
    development_dates = dates[:-LOCKBOX_DECISION_DATES]
    lockbox_dates = dates[-LOCKBOX_DECISION_DATES:]
    folds = _build_folds(dataset, development_dates)
    if len(folds) != 4:
        raise ValueError("ML round requires exactly four valid development folds")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    ranking_trials = []
    ranking_predictions: dict[str, pd.DataFrame] = {}
    for trial in _ranking_trial_specs():
        row, predictions = _run_ranking_trial(trial, dataset, folds, cost_bps)
        ranking_trials.append({"run_id": run_id, "iter_id": ITER_ID, **row})
        ranking_predictions[str(trial["trial_id"])] = predictions

    risk_trials = []
    risk_predictions: dict[str, pd.DataFrame] = {}
    for trial in _risk_trial_specs():
        row, predictions = _run_risk_trial(trial, dataset, folds, cost_bps)
        risk_trials.append({"run_id": run_id, "iter_id": ITER_ID, **row})
        risk_predictions[str(trial["trial_id"])] = predictions

    best_linear = _best_trial(ranking_trials, family="elastic_net")
    best_tree = _best_tree_trial(ranking_trials)
    best_risk = _best_qualified_or_any(risk_trials)
    sizing_trials = _sizing_trials(
        dataset,
        ranking_predictions,
        risk_predictions,
        best_linear,
        best_tree,
        best_risk,
        cost_bps,
        run_id,
    )
    all_trials = [*ranking_trials, *risk_trials, *sizing_trials]
    if len(all_trials) != 16:
        raise AssertionError("registered ML search must contain exactly 16 trials")
    trial_ledger_path = output / "trial-ledger.jsonl"
    append_jsonl(trial_ledger_path, all_trials)

    qualified_ranking = [row for row in ranking_trials if row["qualified"]]
    qualified_risk = [row for row in risk_trials if row["qualified"]]
    lockbox_opened = bool(qualified_ranking or qualified_risk)
    lockbox_rows = []
    model_rows = []
    selected_trials = [
        *_family_winners(qualified_ranking),
        *_family_winners(qualified_risk),
    ]
    for selected in selected_trials:
        trial_id = str(selected["trial_id"])
        model = _make_estimator(selected)
        train = _purged_train_before(dataset, pd.Timestamp(lockbox_dates[0]))
        target = "downside_label" if selected["task"] == "downside_risk" else "forward_excess_21"
        model.fit(train[list(FEATURES)], train[target])
        lockbox = dataset[dataset["decision_date"].isin(_date_keys(lockbox_dates))].copy()
        predictions = _predict(model, lockbox[list(FEATURES)], selected["task"])
        lockbox_eval = (
            _evaluate_risk_predictions(lockbox, predictions, float(selected["threshold"]), cost_bps)
            if selected["task"] == "downside_risk"
            else _evaluate_ranking_predictions(lockbox, predictions, cost_bps)
        )
        if selected["task"] == "return_ranking":
            baseline_eval = _evaluate_ranking_predictions(
                lockbox,
                lockbox["baseline_score"].to_numpy(),
                cost_bps,
            )
            lockbox_eval["baseline"] = baseline_eval
            lockbox_eval["beats_deterministic_baseline"] = bool(
                lockbox_eval["portfolio_total_return_pct"]
                > baseline_eval["portfolio_total_return_pct"]
                and lockbox_eval["mean_rank_ic"] > baseline_eval["mean_rank_ic"]
            )
        lockbox_pass = bool(lockbox_eval.get("beats_deterministic_baseline", False))
        lockbox_rows.append({"trial_id": trial_id, **lockbox_eval})
        full_model = _make_estimator(selected)
        full_model.fit(dataset[list(FEATURES)], dataset[target])
        model_dir = ensure_dir(output / "models")
        model_path = model_dir / f"{trial_id}.joblib"
        joblib.dump(full_model, model_path)
        latest_prediction = _predict(full_model, latest_features[list(FEATURES)], selected["task"])
        model_rows.append(
            {
                "trial_id": trial_id,
                "task": selected["task"],
                "model_family": selected["model_family"],
                "model_path": _relpath(model_path, base),
                "model_sha256": _sha256_file(model_path),
                "feature_contract_sha256": sha256("\n".join(FEATURES).encode()).hexdigest(),
                "training_rows": len(dataset),
                "training_decision_dates": len(dates),
                "latest_decision_date": latest_features["decision_date"].iloc[0],
                "latest_predictions": _latest_prediction_rows(
                    latest_features, latest_prediction, selected["task"]
                ),
                "status": (
                    "lockbox_pass_shadow_candidate"
                    if lockbox_pass
                    else "lockbox_failed_diagnostic_shadow"
                ),
            }
        )

    payload = {
        "report_type": "multiasset_momentum_ml_evaluation",
        "iter_id": ITER_ID,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "llm_contribution_pass": False,
        "source_evaluation_path": _relpath(source_eval_path, base),
        "source_manifest_path": _relpath(source_manifest_path, base),
        "data_profile": {
            "provider": "longbridge",
            "feed": "nasdaq_basic",
            "data_as_of": data["data_as_of"],
            "universe_status": "frozen_current_snapshot_exploratory_history",
        },
        "feature_contract": {
            "features": list(FEATURES),
            "all_features_index_minus_1": True,
            "symbol_identity_feature": False,
            "label_horizon_bars": HORIZON_BARS,
            "embargo_bars": EMBARGO_BARS,
        },
        "dataset": {
            "rows": len(dataset),
            "symbols": len(stock_symbols),
            "decision_dates": len(dates),
            "development_dates": len(development_dates),
            "lockbox_dates": len(lockbox_dates),
            "positive_downside_events": int(dataset["downside_label"].sum()),
        },
        "folds": [
            {
                "fold": fold["fold"],
                "train_start": fold["train"]["decision_date"].min(),
                "train_end": fold["train"]["decision_date"].max(),
                "test_start": fold["test"]["decision_date"].min(),
                "test_end": fold["test"]["decision_date"].max(),
                "train_rows": len(fold["train"]),
                "test_rows": len(fold["test"]),
                "purge_embargo_pass": bool(
                    fold["train"]["label_end_position"].max()
                    <= fold["test"]["decision_position"].min() - EMBARGO_BARS
                ),
            }
            for fold in folds
        ],
        "ranking_trials": ranking_trials,
        "risk_trials": risk_trials,
        "sizing_trials": sizing_trials,
        "selection": {
            "qualified_ranking_trials": [row["trial_id"] for row in qualified_ranking],
            "qualified_risk_trials": [row["trial_id"] for row in qualified_risk],
            "lockbox_opened": lockbox_opened,
            "lockbox_pass_trials": [
                row["trial_id"]
                for row in lockbox_rows
                if row.get("beats_deterministic_baseline") is True
            ],
            "lockbox_reason": (
                "at_least_one_family_passed_three_of_four_development_folds"
                if lockbox_opened
                else "no_family_passed_three_of_four_development_folds"
            ),
        },
        "lockbox": {
            "opened_once": lockbox_opened,
            "decision_dates": [pd.Timestamp(date).isoformat() for date in lockbox_dates]
            if lockbox_opened
            else [],
            "rows": lockbox_rows,
        },
        "frozen_models": model_rows,
        "trial_ledger_path": _relpath(trial_ledger_path, base),
        "limitations": [
            "The current stock universe is survivorship-biased before its 2026-07-14 freeze date.",
            (
                "Monthly cross-sectional rows share market regimes and are not independent "
                "iid samples."
            ),
            (
                "Model qualification is research evidence for isolated virtual paper, not "
                "broker authorization."
            ),
            "No LLM-generated text or live model call participates in prediction or routing.",
        ],
    }
    report_path = output / "model-comparison.json"
    markdown_path = output / "model-comparison.md"
    write_json(report_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return MultiassetMLResult(report_path, markdown_path, trial_ledger_path, payload)


def _build_panel_dataset(
    data: dict[str, Any],
    stock_symbols: list[str],
    sector_map: dict[str, str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    close = data["close"][stock_symbols].shift(1)
    open_prices = data["open"][stock_symbols]
    volume = data["volume"][stock_symbols].shift(1)
    daily = close.pct_change(fill_method=None)
    mom21 = close.pct_change(21, fill_method=None)
    mom63 = close.pct_change(63, fill_method=None)
    mom126_skip = close.shift(21).div(close.shift(126)).sub(1)
    mom252_skip = close.shift(21).div(close.shift(252)).sub(1)
    high252 = close.div(close.rolling(252, min_periods=180).max()).sub(1)
    vol21 = daily.rolling(21, min_periods=15).std()
    downside63 = daily.clip(upper=0).rolling(63, min_periods=40).std()
    drawdown63 = close.div(close.rolling(63, min_periods=40).max()).sub(1)
    volume_surprise = (
        volume.rolling(21, min_periods=15).mean().div(volume.rolling(63, min_periods=40).mean())
    )
    spy_close = data["close"]["SPY"].shift(1)
    relative_spy = close.pct_change(126, fill_method=None).sub(
        spy_close.pct_change(126, fill_method=None), axis=0
    )
    sector_relative = mom63.copy()
    for sector in sorted(set(sector_map.values())):
        members = [symbol for symbol in stock_symbols if sector_map.get(symbol) == sector]
        if members:
            sector_relative[members] = mom63[members].sub(mom63[members].mean(axis=1), axis=0)
    monthly = close.pct_change(21, fill_method=None)
    trend_consistency = monthly.rolling(252, min_periods=180).apply(
        lambda values: float(np.mean(np.asarray(values) > 0)), raw=True
    )
    raw_features = {
        "mom_21": mom21,
        "mom_63": mom63,
        "mom_126_skip21": mom126_skip,
        "mom_252_skip21": mom252_skip,
        "high_252": high252,
        "vol_21": vol21,
        "downside_vol_63": downside63,
        "drawdown_63": drawdown63,
        "volume_surprise": volume_surprise,
        "relative_spy_126": relative_spy,
        "sector_relative_126": sector_relative,
        "trend_consistency": trend_consistency,
    }
    ranked = {f"{name}_rank": frame.rank(axis=1, pct=True) for name, frame in raw_features.items()}
    forward_return = open_prices.shift(-HORIZON_BARS).div(open_prices).sub(1)
    forward_excess = forward_return.sub(forward_return.mean(axis=1), axis=0)
    forward_paths = [open_prices.shift(-offset).div(open_prices).sub(1) for offset in range(1, 22)]
    forward_min = forward_paths[0]
    for path in forward_paths[1:]:
        forward_min = forward_min.combine(path, np.minimum)
    rows = []
    decision_positions = range(252, len(close) - HORIZON_BARS, HORIZON_BARS)
    for position in decision_positions:
        timestamp = close.index[position]
        for symbol in stock_symbols:
            row = {
                "decision_date": timestamp.isoformat(),
                "decision_position": position,
                "label_end_position": position + HORIZON_BARS,
                "symbol": symbol,
                "sector": sector_map.get(symbol, "Unknown"),
                "forward_return_21": forward_return.at[timestamp, symbol],
                "forward_excess_21": forward_excess.at[timestamp, symbol],
                "forward_drawdown_21": forward_min.at[timestamp, symbol],
                "downside_label": int(forward_min.at[timestamp, symbol] <= -0.10)
                if pd.notna(forward_min.at[timestamp, symbol])
                else np.nan,
                "baseline_score": mom252_skip.at[timestamp, symbol],
            }
            for feature, frame in ranked.items():
                row[feature] = frame.at[timestamp, symbol]
            rows.append(row)
    frame = pd.DataFrame(rows)
    frame = frame.dropna(
        subset=[*FEATURES, "forward_return_21", "forward_excess_21", "downside_label"]
    ).reset_index(drop=True)
    latest_position = _latest_feature_position(ranked)
    latest_timestamp = close.index[latest_position]
    latest_rows = []
    for symbol in stock_symbols:
        row = {
            "decision_date": latest_timestamp.isoformat(),
            "decision_position": latest_position,
            "symbol": symbol,
            "sector": sector_map.get(symbol, "Unknown"),
            "baseline_score": mom252_skip.at[latest_timestamp, symbol],
        }
        for feature, feature_frame in ranked.items():
            row[feature] = feature_frame.at[latest_timestamp, symbol]
        latest_rows.append(row)
    latest = pd.DataFrame(latest_rows).dropna(subset=list(FEATURES)).reset_index(drop=True)
    return frame, latest


def _latest_feature_position(ranked: dict[str, pd.DataFrame]) -> int:
    completeness = None
    for frame in ranked.values():
        current = frame.notna().sum(axis=1)
        completeness = current if completeness is None else np.minimum(completeness, current)
    assert completeness is not None
    valid = completeness[completeness >= 10]
    if valid.empty:
        raise ValueError("no current date has at least ten complete stock feature rows")
    return int(ranked[next(iter(ranked))].index.get_loc(valid.index[-1]))


def _build_folds(
    dataset: pd.DataFrame,
    development_dates: list[pd.Timestamp],
) -> list[dict[str, Any]]:
    test_size = max(3, len(development_dates) // 7)
    required = test_size * 4
    initial = len(development_dates) - required
    if initial < 8:
        test_size = max(2, (len(development_dates) - 8) // 4)
        required = test_size * 4
        initial = len(development_dates) - required
    folds = []
    for fold in range(4):
        start = initial + fold * test_size
        stop = start + test_size
        test_dates = development_dates[start:stop]
        if not test_dates:
            continue
        test = dataset[dataset["decision_date"].isin(_date_keys(test_dates))].copy()
        cutoff = int(test["decision_position"].min()) - EMBARGO_BARS
        train = dataset[
            (dataset["decision_date"].isin(_date_keys(development_dates[:start])))
            & (dataset["label_end_position"] <= cutoff)
        ].copy()
        if train.empty or test.empty:
            continue
        folds.append({"fold": fold + 1, "train": train, "test": test})
    return folds


def _ranking_trial_specs() -> list[dict[str, Any]]:
    return [
        {
            "trial_id": "rank_elastic_a0005",
            "task": "return_ranking",
            "model_family": "elastic_net",
            "params": {"alpha": 0.0005},
        },
        {
            "trial_id": "rank_elastic_a005",
            "task": "return_ranking",
            "model_family": "elastic_net",
            "params": {"alpha": 0.005},
        },
        {
            "trial_id": "rank_lgbm_l7",
            "task": "return_ranking",
            "model_family": "lightgbm",
            "params": {"num_leaves": 7, "max_depth": 3},
        },
        {
            "trial_id": "rank_lgbm_l15",
            "task": "return_ranking",
            "model_family": "lightgbm",
            "params": {"num_leaves": 15, "max_depth": 5},
        },
        {
            "trial_id": "rank_extra_leaf5",
            "task": "return_ranking",
            "model_family": "extra_trees",
            "params": {"min_samples_leaf": 5},
        },
        {
            "trial_id": "rank_extra_leaf15",
            "task": "return_ranking",
            "model_family": "extra_trees",
            "params": {"min_samples_leaf": 15},
        },
        {
            "trial_id": "rank_hist_leaf7",
            "task": "return_ranking",
            "model_family": "hist_gradient",
            "params": {"max_leaf_nodes": 7},
        },
        {
            "trial_id": "rank_hist_leaf15",
            "task": "return_ranking",
            "model_family": "hist_gradient",
            "params": {"max_leaf_nodes": 15},
        },
    ]


def _risk_trial_specs() -> list[dict[str, Any]]:
    return [
        {
            "trial_id": "risk_logistic_t04",
            "task": "downside_risk",
            "model_family": "logistic",
            "threshold": 0.4,
            "params": {"C": 0.5},
        },
        {
            "trial_id": "risk_logistic_t06",
            "task": "downside_risk",
            "model_family": "logistic",
            "threshold": 0.6,
            "params": {"C": 0.5},
        },
        {
            "trial_id": "risk_lgbm_t04",
            "task": "downside_risk",
            "model_family": "lightgbm_classifier",
            "threshold": 0.4,
            "params": {"num_leaves": 7},
        },
        {
            "trial_id": "risk_lgbm_t06",
            "task": "downside_risk",
            "model_family": "lightgbm_classifier",
            "threshold": 0.6,
            "params": {"num_leaves": 7},
        },
    ]


def _make_estimator(trial: dict[str, Any]) -> Any:
    family = str(trial["model_family"])
    params = dict(trial.get("params") or {})
    if family == "elastic_net":
        return make_pipeline(
            StandardScaler(),
            ElasticNet(
                alpha=float(params["alpha"]),
                l1_ratio=0.2,
                max_iter=10_000,
                random_state=RANDOM_SEED,
            ),
        )
    if family == "lightgbm":
        from lightgbm import LGBMRegressor

        return LGBMRegressor(
            n_estimators=120,
            learning_rate=0.03,
            num_leaves=int(params["num_leaves"]),
            max_depth=int(params["max_depth"]),
            min_child_samples=30,
            subsample=0.8,
            colsample_bytree=0.8,
            reg_lambda=1.0,
            random_state=RANDOM_SEED,
            verbosity=-1,
        )
    if family == "extra_trees":
        return ExtraTreesRegressor(
            n_estimators=200,
            max_features=0.7,
            min_samples_leaf=int(params["min_samples_leaf"]),
            random_state=RANDOM_SEED,
            n_jobs=-1,
        )
    if family == "hist_gradient":
        return HistGradientBoostingRegressor(
            max_iter=120,
            learning_rate=0.04,
            max_leaf_nodes=int(params["max_leaf_nodes"]),
            min_samples_leaf=25,
            l2_regularization=1.0,
            random_state=RANDOM_SEED,
        )
    if family == "logistic":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=float(params["C"]),
                class_weight="balanced",
                max_iter=2_000,
                random_state=RANDOM_SEED,
            ),
        )
    if family == "lightgbm_classifier":
        from lightgbm import LGBMClassifier

        return LGBMClassifier(
            n_estimators=120,
            learning_rate=0.03,
            num_leaves=int(params["num_leaves"]),
            max_depth=3,
            min_child_samples=30,
            class_weight="balanced",
            reg_lambda=1.0,
            random_state=RANDOM_SEED,
            verbosity=-1,
        )
    raise ValueError(f"unsupported model family: {family}")


def _run_ranking_trial(
    trial: dict[str, Any],
    dataset: pd.DataFrame,
    folds: list[dict[str, Any]],
    cost_bps: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    fold_rows = []
    predictions = []
    for fold in folds:
        model = _make_estimator(trial)
        train = fold["train"]
        test = fold["test"].copy()
        model.fit(train[list(FEATURES)], train["forward_excess_21"])
        predicted = model.predict(test[list(FEATURES)])
        evaluation = _evaluate_ranking_predictions(test, predicted, cost_bps)
        baseline = _evaluate_ranking_predictions(test, test["baseline_score"].to_numpy(), cost_bps)
        fold_win = bool(
            evaluation["portfolio_total_return_pct"] > baseline["portfolio_total_return_pct"]
            and evaluation["mean_rank_ic"] > baseline["mean_rank_ic"]
        )
        fold_rows.append(
            {"fold": fold["fold"], "fold_win": fold_win, **evaluation, "baseline": baseline}
        )
        test["prediction"] = predicted
        test["fold"] = fold["fold"]
        predictions.append(test)
    fold_wins = sum(bool(row["fold_win"]) for row in fold_rows)
    stitched = pd.concat(predictions, ignore_index=True)
    aggregate = _evaluate_ranking_predictions(stitched, stitched["prediction"].to_numpy(), cost_bps)
    cost_stress = {
        str(int(stress_cost)): _evaluate_ranking_predictions(
            stitched,
            stitched["prediction"].to_numpy(),
            stress_cost,
        )
        for stress_cost in [5.0, 10.0, 20.0]
    }
    qualified = bool(fold_wins >= 3 and aggregate["mean_rank_ic"] > 0)
    return (
        {
            **trial,
            "status": "validation_complete",
            "folds": fold_rows,
            "fold_wins": fold_wins,
            "aggregate": aggregate,
            "cost_stress_bps": cost_stress,
            "qualified": qualified,
        },
        stitched,
    )


def _run_risk_trial(
    trial: dict[str, Any],
    dataset: pd.DataFrame,
    folds: list[dict[str, Any]],
    cost_bps: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    fold_rows = []
    predictions = []
    for fold in folds:
        model = _make_estimator(trial)
        train = fold["train"]
        test = fold["test"].copy()
        model.fit(train[list(FEATURES)], train["downside_label"].astype(int))
        predicted = _predict(model, test[list(FEATURES)], "downside_risk")
        evaluation = _evaluate_risk_predictions(
            test, predicted, float(trial["threshold"]), cost_bps
        )
        fold_win = bool(
            evaluation["portfolio_total_return_pct"]
            >= evaluation["baseline_total_return_pct"] - 3.0
            and evaluation["selected_downside_event_rate"]
            < evaluation["baseline_downside_event_rate"]
            and evaluation["coverage"] >= 0.3
        )
        fold_rows.append({"fold": fold["fold"], "fold_win": fold_win, **evaluation})
        test["prediction"] = predicted
        test["fold"] = fold["fold"]
        predictions.append(test)
    fold_wins = sum(bool(row["fold_win"]) for row in fold_rows)
    stitched = pd.concat(predictions, ignore_index=True)
    aggregate = _evaluate_risk_predictions(
        stitched,
        stitched["prediction"].to_numpy(),
        float(trial["threshold"]),
        cost_bps,
    )
    cost_stress = {
        str(int(stress_cost)): _evaluate_risk_predictions(
            stitched,
            stitched["prediction"].to_numpy(),
            float(trial["threshold"]),
            stress_cost,
        )
        for stress_cost in [5.0, 10.0, 20.0]
    }
    qualified = bool(
        fold_wins >= 3
        and aggregate["coverage"] >= 0.3
        and aggregate["brier_score"] < aggregate["base_rate_brier"]
    )
    return (
        {
            **trial,
            "status": "validation_complete",
            "folds": fold_rows,
            "fold_wins": fold_wins,
            "aggregate": aggregate,
            "cost_stress_bps": cost_stress,
            "qualified": qualified,
        },
        stitched,
    )


def _evaluate_ranking_predictions(
    frame: pd.DataFrame,
    predictions: np.ndarray,
    cost_bps: float,
) -> dict[str, Any]:
    work = frame.copy()
    work["score"] = predictions
    rank_ics = []
    selections = []
    for decision_date, group in work.groupby("decision_date", sort=True):
        correlation = group["score"].rank().corr(group["forward_excess_21"].rank())
        if pd.notna(correlation):
            rank_ics.append(float(correlation))
        selected = group.nlargest(TOP_N, "score")
        selections.append(
            {
                "decision_date": decision_date,
                "symbols": selected["symbol"].tolist(),
                "gross_return": float(selected["forward_return_21"].mean()),
            }
        )
    net_returns, average_turnover = _selection_net_returns(selections, cost_bps)
    return {
        "decision_dates": len(selections),
        "mean_rank_ic": round(float(np.mean(rank_ics)), 6) if rank_ics else 0.0,
        "rank_ic_ir": _ratio(rank_ics, periods=12),
        "portfolio_total_return_pct": round(((1 + net_returns).prod() - 1) * 100, 4),
        "portfolio_sharpe": _ratio(net_returns.tolist(), periods=12),
        "average_one_way_turnover_pct": round(average_turnover * 100, 4),
        "positive_decision_ratio": round(float(np.mean(net_returns > 0)), 6),
    }


def _evaluate_risk_predictions(
    frame: pd.DataFrame,
    predictions: np.ndarray,
    threshold: float,
    cost_bps: float,
) -> dict[str, Any]:
    work = frame.copy()
    work["risk_probability"] = predictions
    labels = work["downside_label"].astype(int)
    auc = _safe_auc(labels, predictions)
    brier = brier_score_loss(labels, predictions)
    base_rate = float(labels.mean())
    baseline_selections = []
    filtered_selections = []
    selected_labels = []
    baseline_labels = []
    coverage_rows = []
    for decision_date, group in work.groupby("decision_date", sort=True):
        baseline = group.nlargest(TOP_N, "baseline_score")
        filtered = baseline[baseline["risk_probability"] <= threshold]
        baseline_selections.append(
            {
                "decision_date": decision_date,
                "symbols": baseline["symbol"].tolist(),
                "gross_return": float(baseline["forward_return_21"].mean()),
            }
        )
        filtered_selections.append(
            {
                "decision_date": decision_date,
                "symbols": filtered["symbol"].tolist(),
                "gross_return": float(filtered["forward_return_21"].mean())
                if len(filtered)
                else 0.0,
            }
        )
        baseline_labels.extend(baseline["downside_label"].astype(int).tolist())
        selected_labels.extend(filtered["downside_label"].astype(int).tolist())
        coverage_rows.append(len(filtered) / max(len(baseline), 1))
    baseline_returns, _ = _selection_net_returns(baseline_selections, cost_bps)
    filtered_returns, turnover = _selection_net_returns(filtered_selections, cost_bps)
    return {
        "decision_dates": len(filtered_selections),
        "roc_auc": round(auc, 6),
        "brier_score": round(float(brier), 6),
        "base_rate": round(base_rate, 6),
        "base_rate_brier": round(base_rate * (1 - base_rate), 6),
        "coverage": round(float(np.mean(coverage_rows)), 6),
        "baseline_downside_event_rate": round(float(np.mean(baseline_labels)), 6),
        "selected_downside_event_rate": (
            round(float(np.mean(selected_labels)), 6) if selected_labels else 0.0
        ),
        "baseline_total_return_pct": round(((1 + baseline_returns).prod() - 1) * 100, 4),
        "portfolio_total_return_pct": round(((1 + filtered_returns).prod() - 1) * 100, 4),
        "portfolio_sharpe": _ratio(filtered_returns.tolist(), periods=12),
        "average_one_way_turnover_pct": round(turnover * 100, 4),
    }


def _selection_net_returns(
    selections: list[dict[str, Any]],
    cost_bps: float,
    *,
    rank_weighted: bool = False,
) -> tuple[pd.Series, float]:
    returns = []
    turnovers = []
    previous: dict[str, float] = {}
    for row in selections:
        symbols = list(row["symbols"])
        if rank_weighted and symbols:
            raw = np.arange(len(symbols), 0, -1, dtype=float)
            weights = {
                symbol: float(weight) / raw.sum()
                for symbol, weight in zip(symbols, raw, strict=True)
            }
        else:
            weights = {symbol: 1 / len(symbols) for symbol in symbols} if symbols else {}
        turnover = (
            sum(
                abs(weights.get(symbol, 0.0) - previous.get(symbol, 0.0))
                for symbol in set(weights) | set(previous)
            )
            / 2
        )
        net = float(row["gross_return"]) - turnover * cost_bps / 10_000
        returns.append(net)
        turnovers.append(turnover)
        previous = weights
    return pd.Series(returns, dtype=float), float(np.mean(turnovers)) if turnovers else 0.0


def _sizing_trials(
    dataset: pd.DataFrame,
    ranking_predictions: dict[str, pd.DataFrame],
    risk_predictions: dict[str, pd.DataFrame],
    best_linear: dict[str, Any],
    best_tree: dict[str, Any],
    best_risk: dict[str, Any],
    cost_bps: float,
    run_id: str,
) -> list[dict[str, Any]]:
    del dataset
    rows = []
    definitions = [
        ("size_linear_equal", best_linear, False, None),
        ("size_linear_rank", best_linear, True, None),
        ("size_tree_equal", best_tree, False, None),
        ("size_tree_risk_capped", best_tree, True, best_risk),
    ]
    for trial_id, ranking, rank_weighted, risk in definitions:
        prediction_frame = ranking_predictions[str(ranking["trial_id"])].copy()
        risk_applied = False
        if risk is not None and risk["qualified"]:
            risk_frame = risk_predictions[str(risk["trial_id"])][
                ["decision_date", "symbol", "prediction"]
            ].rename(columns={"prediction": "risk_probability"})
            prediction_frame = prediction_frame.merge(
                risk_frame, on=["decision_date", "symbol"], how="left"
            )
            prediction_frame = prediction_frame[
                prediction_frame["risk_probability"] <= float(risk["threshold"])
            ]
            risk_applied = True
        selections = []
        for decision_date, group in prediction_frame.groupby("decision_date", sort=True):
            selected = group.nlargest(TOP_N, "prediction")
            selections.append(
                {
                    "decision_date": decision_date,
                    "symbols": selected["symbol"].tolist(),
                    "gross_return": float(selected["forward_return_21"].mean())
                    if len(selected)
                    else 0.0,
                }
            )
        net, turnover = _selection_net_returns(selections, cost_bps, rank_weighted=rank_weighted)
        rows.append(
            {
                "run_id": run_id,
                "iter_id": ITER_ID,
                "trial_id": trial_id,
                "task": "position_sizing",
                "model_family": "derived_policy",
                "params": {
                    "ranking_trial_id": ranking["trial_id"],
                    "rank_weighted": rank_weighted,
                    "risk_trial_id": risk["trial_id"] if risk_applied and risk else None,
                },
                "status": "validation_complete",
                "aggregate": {
                    "decision_dates": len(selections),
                    "portfolio_total_return_pct": round(((1 + net).prod() - 1) * 100, 4),
                    "portfolio_sharpe": _ratio(net.tolist(), periods=12),
                    "average_one_way_turnover_pct": round(turnover * 100, 4),
                },
                "qualified": bool(ranking["qualified"] and (risk is None or risk_applied)),
            }
        )
    return rows


def _predict(model: Any, features: pd.DataFrame, task: str) -> np.ndarray:
    if task == "downside_risk":
        return np.asarray(model.predict_proba(features)[:, 1], dtype=float)
    return np.asarray(model.predict(features), dtype=float)


def _best_trial(rows: list[dict[str, Any]], *, family: str) -> dict[str, Any]:
    family_rows = [row for row in rows if row["model_family"] == family]
    return max(family_rows, key=lambda row: (row["fold_wins"], row["aggregate"]["mean_rank_ic"]))


def _best_tree_trial(rows: list[dict[str, Any]]) -> dict[str, Any]:
    tree_rows = [row for row in rows if row["model_family"] != "elastic_net"]
    return max(tree_rows, key=lambda row: (row["fold_wins"], row["aggregate"]["mean_rank_ic"]))


def _best_qualified_or_any(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return max(
        rows,
        key=lambda row: (
            bool(row["qualified"]),
            row["fold_wins"],
            -row["aggregate"]["brier_score"],
        ),
    )


def _family_winners(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[str(row["model_family"])].append(row)
    winners = []
    for family_rows in grouped.values():
        if family_rows[0]["task"] == "downside_risk":
            winners.append(
                max(
                    family_rows,
                    key=lambda row: (row["fold_wins"], -row["aggregate"]["brier_score"]),
                )
            )
        else:
            winners.append(
                max(
                    family_rows,
                    key=lambda row: (row["fold_wins"], row["aggregate"]["mean_rank_ic"]),
                )
            )
    return winners


def _purged_train_before(dataset: pd.DataFrame, test_start: pd.Timestamp) -> pd.DataFrame:
    test_position = int(
        dataset.loc[dataset["decision_date"] == test_start.isoformat(), "decision_position"].min()
    )
    return dataset[dataset["label_end_position"] <= test_position - EMBARGO_BARS].copy()


def _date_keys(values: list[pd.Timestamp] | np.ndarray) -> list[str]:
    return [pd.Timestamp(value).isoformat() for value in values]


def _latest_prediction_rows(
    latest: pd.DataFrame,
    predictions: np.ndarray,
    task: str,
) -> list[dict[str, Any]]:
    work = latest[["symbol", "sector", "baseline_score"]].copy()
    key = "risk_probability" if task == "downside_risk" else "predicted_excess_return"
    work[key] = predictions
    ascending = task == "downside_risk"
    work = work.sort_values(key, ascending=ascending).head(10)
    return work.to_dict(orient="records")


def _safe_auc(labels: pd.Series, predictions: np.ndarray) -> float:
    if labels.nunique() < 2:
        return 0.5
    return float(roc_auc_score(labels, predictions))


def _ratio(values: list[float], *, periods: int) -> float:
    clean = np.asarray([value for value in values if np.isfinite(value)], dtype=float)
    if len(clean) < 2:
        return 0.0
    std = float(clean.std(ddof=1))
    return round(float(clean.mean()) / std * math.sqrt(periods), 6) if std else 0.0


def _sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Multi-Asset Momentum ML Comparison",
        "",
        f"- Run: `{payload['run_id']}`",
        f"- Dataset rows: `{payload['dataset']['rows']}`",
        f"- Decision dates: `{payload['dataset']['decision_dates']}`",
        f"- Lockbox opened: `{str(payload['selection']['lockbox_opened']).lower()}`",
        "",
        "## Return Ranking",
        "",
        "| Trial | Family | Fold wins | Rank IC | Return | Qualified |",
        "|---|---|---:|---:|---:|---|",
    ]
    for row in payload["ranking_trials"]:
        lines.append(
            f"| {row['trial_id']} | {row['model_family']} | {row['fold_wins']}/4 | "
            f"{row['aggregate']['mean_rank_ic']:.3f} | "
            f"{row['aggregate']['portfolio_total_return_pct']:.2f}% | "
            f"{str(row['qualified']).lower()} |"
        )
    lines.extend(
        [
            "",
            "## Downside Risk",
            "",
            "| Trial | Family | Fold wins | AUC | Brier | Coverage | Qualified |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
    )
    for row in payload["risk_trials"]:
        lines.append(
            f"| {row['trial_id']} | {row['model_family']} | {row['fold_wins']}/4 | "
            f"{row['aggregate']['roc_auc']:.3f} | {row['aggregate']['brier_score']:.3f} | "
            f"{row['aggregate']['coverage']:.2f} | {str(row['qualified']).lower()} |"
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    return "\n".join(lines).rstrip() + "\n"
