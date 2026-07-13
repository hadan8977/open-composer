from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.ml_backend.model_factory import create_lightgbm_classifier
from open_composer.research.ml_backend.windows import ml_walk_forward_slices
from open_composer.research.mom_minute_lockbox import _position
from open_composer.research.mom_minute_round import (
    BASE_COST_BPS,
    _align_signal_and_trade,
    _load_bundle,
    _metrics,
    _required_pair,
    _strategy_returns,
)
from open_composer.storage import write_json
from open_composer.strategy_versions import strategy_content_hash

ITER_ID = "mom_minute_r3_ml"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
EXPECTED_SPEC_NAME = "us_mom_minute_p1_003_frozen"
FEATURES = (
    "qqq_roc_12_index_minus_1",
    "qqq_roc_36_index_minus_1",
    "qqq_roc_72_index_minus_1",
    "qqq_atr_ratio_72_index_minus_1",
    "qqq_realized_vol_26_index_minus_1",
    "tqqq_gap_1_index_minus_1",
)
MAX_EPISODE_BARS = 120
PURGE_BARS = MAX_EPISODE_BARS
EMBARGO_BARS = MAX_EPISODE_BARS
SEARCH_CAP = 12
MIN_ENTRY_EVENTS = 80
MIN_CLASS_EVENTS = 20
MIN_TEST_ENTRY_EVENTS = 30
RANDOM_SEED = 77


@dataclass(frozen=True)
class MomentumMLDesignResult:
    json_path: Path
    markdown_path: Path
    payload: dict[str, Any]


@dataclass(frozen=True)
class MomentumMLComparisonResult:
    json_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def write_momentum_ml_design(
    spec_path: Path,
    root: Path | None = None,
) -> MomentumMLDesignResult:
    base = root or project_root()
    spec_path = _resolve_spec_path(spec_path, base)
    spec, aligned, baseline_position = _load_frozen_candidate(spec_path, base)
    feature_frame = _feature_frame(aligned)
    events = _entry_events(aligned, baseline_position, feature_frame)
    eligible_windows = _eligible_windows(aligned, events, baseline_position)
    class_counts = events["label"].value_counts().to_dict() if not events.empty else {}
    gates = {
        "frozen_strategy_identity": {
            "actual": spec.name,
            "expected": EXPECTED_SPEC_NAME,
            "passed": spec.name == EXPECTED_SPEC_NAME,
        },
        "entry_events": {
            "actual": int(len(events)),
            "threshold": MIN_ENTRY_EVENTS,
            "passed": len(events) >= MIN_ENTRY_EVENTS,
        },
        "positive_events": {
            "actual": int(class_counts.get(1, 0)),
            "threshold": MIN_CLASS_EVENTS,
            "passed": class_counts.get(1, 0) >= MIN_CLASS_EVENTS,
        },
        "negative_events": {
            "actual": int(class_counts.get(0, 0)),
            "threshold": MIN_CLASS_EVENTS,
            "passed": class_counts.get(0, 0) >= MIN_CLASS_EVENTS,
        },
        "feature_completeness": {
            "actual": int(events[list(FEATURES)].dropna().shape[0]) if not events.empty else 0,
            "threshold": int(len(events)),
            "passed": bool(not events.empty and events[list(FEATURES)].notna().all(axis=None)),
        },
        "purge_and_embargo": {
            "actual": {"purge_bars": PURGE_BARS, "embargo_bars": EMBARGO_BARS},
            "threshold": MAX_EPISODE_BARS,
            "passed": (PURGE_BARS >= MAX_EPISODE_BARS and EMBARGO_BARS >= MAX_EPISODE_BARS),
        },
        "valid_walk_forward_folds": {
            "actual": len(eligible_windows),
            "threshold": 4,
            "passed": len(eligible_windows) >= 4,
        },
    }
    training_authorized = all(row["passed"] for row in gates.values())
    payload = {
        "report_type": "momentum_strategy_specific_ml_design",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "strategy_name": spec.name,
        "source_spec_path": str(spec_path.relative_to(base)),
        "spec_hash": strategy_content_hash(spec),
        "source_contract": spec.notes.research_design.get("source_contract", {}),
        "source_contract_sha256": spec.notes.research_design.get("source_contract_sha256"),
        "decision": "train_bounded_challengers" if training_authorized else "do_not_train",
        "training_authorized": training_authorized,
        "role": "entry_meta_label_advisory",
        "decision_scope": "accept_or_skip_frozen_rule_entry",
        "execution_scope": "research_only_no_target_weight_control",
        "fallback": "frozen_rule_identical",
        "rejected_roles": [
            "direct_buy_sell_prediction",
            "unconstrained_position_control",
            "deep_sequence_model",
            "reinforcement_learning",
        ],
        "feature_contract": {
            "features": list(FEATURES),
            "cutoff": "all values shifted one completed 30m bar before the rule entry decision",
            "signal_symbol": "QQQ",
            "target_symbol": "TQQQ",
        },
        "data_alignment": {
            "join": "exact_timestamp_inner_join_no_forward_fill",
            "aligned_rows": int(len(aligned)),
            "unmatched_qqq_timestamps": int(aligned.attrs.get("unmatched_qqq_timestamps", 0)),
            "unmatched_tqqq_timestamps": int(aligned.attrs.get("unmatched_tqqq_timestamps", 0)),
        },
        "label_contract": {
            "name": "tqqq_frozen_rule_episode_net_return_positive",
            "max_episode_bars": MAX_EPISODE_BARS,
            "round_trip_cost_bps": BASE_COST_BPS["30m"] * 2,
            "definition": (
                "1 when the complete frozen-rule TQQQ entry-to-exit episode compounds "
                "positive after round-trip cost"
            ),
        },
        "training_contract": {
            "models": ["frozen_rule", "regularized_logistic", "lightgbm_challenger"],
            "prediction_scope": "stitched_oos_only",
            "purge_bars": PURGE_BARS,
            "embargo_bars": EMBARGO_BARS,
            "search_cap": SEARCH_CAP,
            "random_seed": RANDOM_SEED,
        },
        "acceptance": {
            "ml_is_optional": True,
            "required": [
                "same stitched OOS bars for every challenger",
                "positive information ratio versus the frozen rule",
                "higher net return or Sharpe without worse max drawdown",
                "at least three fold wins versus both rule and logistic before any "
                "later shadow proposal",
            ],
        },
        "gates": gates,
        "blockers": [name for name, row in gates.items() if not row["passed"]],
    }
    output = base / OUTPUT_DIR
    ensure_dir(output)
    json_path = output / "ml-design.json"
    markdown_path = output / "ml-design.md"
    write_json(json_path, payload)
    markdown_path.write_text(_render_design_markdown(payload), encoding="utf-8")
    return MomentumMLDesignResult(json_path, markdown_path, payload)


def run_momentum_ml_comparison(
    spec_path: Path,
    root: Path | None = None,
) -> MomentumMLComparisonResult:
    base = root or project_root()
    spec_path = _resolve_spec_path(spec_path, base)
    design = write_momentum_ml_design(spec_path, base)
    output = base / OUTPUT_DIR
    json_path = output / "model-comparison.json"
    markdown_path = output / "model-comparison.md"
    ledger_path = output / "trial-ledger.jsonl"
    if not design.payload["training_authorized"]:
        payload = _blocked_comparison(design.payload)
        _write_comparison_artifacts(payload, json_path, markdown_path, ledger_path, [])
        return MomentumMLComparisonResult(json_path, markdown_path, ledger_path, payload)

    _, aligned, baseline_position = _load_frozen_candidate(spec_path, base)
    features = _feature_frame(aligned)
    events = _entry_events(aligned, baseline_position, features)
    windows = _eligible_windows(aligned, events, baseline_position)
    trials = _trial_definitions()
    trial_rows: list[dict[str, Any]] = []
    stitched_positions: dict[str, pd.Series] = {
        trial["trial_id"]: pd.Series(np.nan, index=aligned.index, dtype="float64")
        for trial in trials
    }
    oos_event_predictions: dict[str, list[pd.DataFrame]] = {
        trial["trial_id"]: [] for trial in trials
    }
    rule_position = pd.Series(np.nan, index=aligned.index, dtype="float64")
    fold_rows: list[dict[str, Any]] = []
    prediction_rows = 0

    for window in windows:
        train = events.loc[
            (events["bar_index"] >= window.train_start_idx)
            & (events["bar_index"] < window.train_end_idx)
        ]
        test = events.loc[
            (events["bar_index"] >= window.test_start_idx)
            & (events["bar_index"] < window.test_end_idx)
        ]
        if (
            len(train) < 30
            or len(test) < MIN_TEST_ENTRY_EVENTS
            or train["label"].nunique() < 2
            or test["label"].nunique() < 2
        ):
            continue
        test_slice = slice(window.test_start_idx, window.test_end_idx)
        rule_position.iloc[test_slice] = baseline_position.iloc[test_slice]
        X_train = train[list(FEATURES)]
        y_train = train["label"].astype(int)
        X_test = test[list(FEATURES)]
        fold_predictions: dict[str, pd.Series] = {}
        for trial in trials:
            try:
                estimator = _make_estimator(trial)
                estimator.fit(X_train, y_train)
                probabilities = pd.Series(
                    estimator.predict_proba(X_test)[:, 1], index=test.index, dtype="float64"
                )
            except Exception as exc:  # model failure is a recorded negative result
                trial.setdefault("failures", []).append(
                    {"fold": window.fold, "error": f"{type(exc).__name__}: {exc}"}
                )
                stitched_positions[trial["trial_id"]].iloc[test_slice] = baseline_position.iloc[
                    test_slice
                ].to_numpy()
                continue
            accepted = probabilities >= float(trial["threshold"])
            fold_predictions[trial["trial_id"]] = probabilities
            oos_event_predictions[trial["trial_id"]].append(
                test[["bar_index", "label"]].assign(probability=probabilities.to_numpy())
            )
            gated = _gate_position(
                baseline_position.iloc[test_slice],
                test,
                accepted,
                offset=window.test_start_idx,
                initially_active=bool(
                    window.test_start_idx > 0
                    and baseline_position.iloc[window.test_start_idx - 1] > 0
                ),
            )
            stitched_positions[trial["trial_id"]].iloc[test_slice] = gated.to_numpy()
        prediction_rows += len(test)
        fold_rows.append(
            _fold_summary(
                aligned,
                rule_position,
                stitched_positions,
                fold_predictions,
                test,
                window.test_start_idx,
                window.test_end_idx,
                window.fold,
            )
        )

    valid_mask = rule_position.notna()
    rule_returns = _strategy_returns(
        aligned.loc[valid_mask].reset_index(drop=True),
        rule_position.loc[valid_mask].reset_index(drop=True),
        cost_bps=BASE_COST_BPS["30m"],
        allow_overnight=True,
    )
    rule_metrics = _metrics(rule_returns)
    for trial in trials:
        trial_id = trial["trial_id"]
        position = stitched_positions[trial_id].loc[valid_mask].reset_index(drop=True)
        returns = _strategy_returns(
            aligned.loc[valid_mask].reset_index(drop=True),
            position,
            cost_bps=BASE_COST_BPS["30m"],
            allow_overnight=True,
        )
        metrics = _metrics(returns)
        active = returns - rule_returns
        information_ratio = _information_ratio(active)
        relevant_folds = [fold for fold in fold_rows if trial_id in fold["challengers"]]
        fold_wins = sum(
            1
            for fold in relevant_folds
            if fold["challengers"][trial_id]["total_return_pct"] > fold["rule"]["total_return_pct"]
        )
        row = {
            **trial,
            "status": "failed_model_fallback" if trial.get("failures") else "diagnostic_only",
            "stitched_oos_metrics": metrics,
            "information_ratio_vs_rule": information_ratio,
            "fold_wins_vs_rule": fold_wins,
            "fold_count": len(relevant_folds),
            "beats_rule_return": metrics["total_return_pct"] > rule_metrics["total_return_pct"],
            "beats_rule_sharpe": metrics["sharpe"] > rule_metrics["sharpe"],
            "maxdd_not_worse": metrics["max_drawdown_pct"] >= rule_metrics["max_drawdown_pct"],
            "mean_oos_auc": _mean_fold_metric(relevant_folds, trial_id, "roc_auc"),
            "non_overlap_oos_auc": _non_overlap_auc(oos_event_predictions[trial_id]),
            "oos_prediction_count": sum(len(frame) for frame in oos_event_predictions[trial_id]),
            "oos_entry_coverage": round(
                sum(len(frame) for frame in oos_event_predictions[trial_id])
                / max(prediction_rows, 1),
                4,
            ),
            "worst_fold_return_delta_pct": _worst_fold_return_delta(relevant_folds, trial_id),
        }
        trial_rows.append(row)

    logistic_best = _best_trial(trial_rows, "regularized_logistic")
    lightgbm_best = _best_trial(trial_rows, "lightgbm_challenger")
    ml_beats_rule_and_linear = bool(
        lightgbm_best
        and logistic_best
        and lightgbm_best["stitched_oos_metrics"]["total_return_pct"]
        > max(
            rule_metrics["total_return_pct"],
            logistic_best["stitched_oos_metrics"]["total_return_pct"],
        )
        and lightgbm_best["information_ratio_vs_rule"] > 0
        and lightgbm_best["maxdd_not_worse"]
        and lightgbm_best["fold_count"] >= 4
        and lightgbm_best["fold_wins_vs_rule"] >= 3
        and lightgbm_best["mean_oos_auc"] > 0.52
        and lightgbm_best["non_overlap_oos_auc"] > 0.52
        and lightgbm_best["worst_fold_return_delta_pct"] >= 0
    )
    payload = {
        "report_type": "momentum_strategy_specific_ml_comparison",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "offline_challenger_promising_requires_lockbox"
        if ml_beats_rule_and_linear
        else "keep_rule_champion",
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "execution_behavior_changed": False,
        "training_scope": "offline_research_only",
        "design_path": str(design.json_path.relative_to(base)),
        "fold_count": len(fold_rows),
        "stitched_oos_entry_predictions": prediction_rows,
        "independence_unit": "frozen_rule_entry_episode",
        "rule": {"trial_id": "frozen_rule", "stitched_oos_metrics": rule_metrics},
        "trials": trial_rows,
        "folds": fold_rows,
        "acceptance": {
            "ml_gate_beats_rule_and_linear": ml_beats_rule_and_linear,
            "independent_lockbox_pass": False,
            "selected_for_execution": False,
            "negative_result_is_valid": True,
            "selection_caveat": (
                "trial ranking uses the stitched OOS comparison and cannot authorize deployment "
                "without a newly frozen forward shadow test"
            ),
            "failed_gates": _comparison_failed_gates(lightgbm_best, logistic_best),
        },
        "limitations": [
            "Alpaca IEX materialized history remains research-only evidence.",
            "This comparison evaluates entry filtering only; it does not repair exit "
            "hysteresis or position sizing.",
            "No model artifact is connected to target weights, shadow decisions, "
            "paper orders, or broker writes.",
            "Entry episodes are the independent evaluation unit; overlapping bar labels "
            "are not counted as independent samples.",
        ],
    }
    _write_comparison_artifacts(payload, json_path, markdown_path, ledger_path, trial_rows)
    return MomentumMLComparisonResult(json_path, markdown_path, ledger_path, payload)


def _load_frozen_candidate(spec_path: Path, root: Path):
    spec = load_strategy_spec(spec_path)
    if spec.name != EXPECTED_SPEC_NAME:
        raise ValueError(f"momentum ML research requires {EXPECTED_SPEC_NAME}")
    bundle = _load_bundle(root, "30m")
    qqq, tqqq = _required_pair(bundle, "30m")
    qqq_timestamps = set(pd.to_datetime(qqq["timestamp"], utc=True))
    tqqq_timestamps = set(pd.to_datetime(tqqq["timestamp"], utc=True))
    aligned = _align_signal_and_trade(qqq, tqqq)
    aligned.attrs["unmatched_qqq_timestamps"] = int(len(qqq_timestamps - tqqq_timestamps))
    aligned.attrs["unmatched_tqqq_timestamps"] = int(len(tqqq_timestamps - qqq_timestamps))
    baseline_position = _position(aligned, lookback_bars=72, atr_filter_multiplier=2.5)
    return spec, aligned, baseline_position


def _resolve_spec_path(spec_path: Path, root: Path) -> Path:
    resolved = spec_path.resolve() if spec_path.is_absolute() else (root / spec_path).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError("momentum ML spec must be inside the project root") from exc
    return resolved


def _feature_frame(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["signal_close"].astype(float)
    previous_close = close.shift(1)
    true_range = pd.concat(
        [
            frame["signal_high"] - frame["signal_low"],
            (frame["signal_high"] - previous_close).abs(),
            (frame["signal_low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    tqqq_previous_close = frame["trade_close"].shift(1)
    features = pd.DataFrame(index=frame.index)
    for lookback in (12, 36, 72):
        features[f"qqq_roc_{lookback}_index_minus_1"] = (close / close.shift(lookback) - 1).shift(1)
    features["qqq_atr_ratio_72_index_minus_1"] = (
        true_range.rolling(72, min_periods=72).mean() / close
    ).shift(1)
    features["qqq_realized_vol_26_index_minus_1"] = (
        close.pct_change().rolling(26, min_periods=26).std(ddof=0)
    ).shift(1)
    features["tqqq_gap_1_index_minus_1"] = (frame["trade_open"] / tqqq_previous_close - 1).shift(1)
    return features.replace([np.inf, -np.inf], np.nan)


def _entry_events(
    frame: pd.DataFrame,
    baseline_position: pd.Series,
    features: pd.DataFrame,
) -> pd.DataFrame:
    entry_mask = (baseline_position > 0) & (baseline_position.shift(1).fillna(0) <= 0)
    rows: list[dict[str, Any]] = []
    round_trip_cost = BASE_COST_BPS["30m"] * 2 / 10000.0
    for bar_index in np.flatnonzero(entry_mask.to_numpy()):
        end = bar_index
        while end < len(baseline_position) and baseline_position.iloc[end] > 0:
            end += 1
        episode_bars = end - bar_index
        if end >= len(frame) or episode_bars > MAX_EPISODE_BARS:
            continue
        feature_row = features.iloc[bar_index]
        if feature_row.isna().any():
            continue
        path = frame["next_trade_return"].iloc[bar_index:end].astype(float)
        net_return = float((1.0 + path).prod() - 1.0 - round_trip_cost)
        row = {
            "bar_index": int(bar_index),
            "timestamp": pd.Timestamp(frame.iloc[bar_index]["timestamp"]).isoformat(),
            "label": int(net_return > 0),
            "forward_net_return": net_return,
            "episode_bars": episode_bars,
        }
        row.update({name: float(feature_row[name]) for name in FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)


def _eligible_windows(
    frame: pd.DataFrame,
    events: pd.DataFrame,
    baseline_position: pd.Series,
):
    windows = ml_walk_forward_slices(
        frame.assign(timestamp=pd.to_datetime(frame["timestamp"], utc=True)),
        window_bars=1300,
        test_window_bars=1300,
        retrain_every_bars=1300,
        horizon_bars=MAX_EPISODE_BARS,
        embargo_bars=EMBARGO_BARS,
    )
    eligible = []
    for window in windows:
        starts_flat = (
            window.test_start_idx == 0 or baseline_position.iloc[window.test_start_idx - 1] <= 0
        )
        ends_flat = baseline_position.iloc[window.test_end_idx - 1] <= 0
        train = events.loc[
            (events["bar_index"] >= window.train_start_idx)
            & (events["bar_index"] < window.train_end_idx)
        ]
        test = events.loc[
            (events["bar_index"] >= window.test_start_idx)
            & (events["bar_index"] < window.test_end_idx)
        ]
        if (
            len(train) >= 30
            and len(test) >= MIN_TEST_ENTRY_EVENTS
            and train["label"].nunique() >= 2
            and test["label"].nunique() >= 2
            and starts_flat
            and ends_flat
        ):
            eligible.append(window)
    return eligible


def _trial_definitions() -> list[dict[str, Any]]:
    trials: list[dict[str, Any]] = []
    for c_value in (0.1, 1.0):
        for threshold in (0.5, 0.6):
            trials.append(
                {
                    "trial_id": f"logistic_c{c_value:g}_t{threshold:g}",
                    "model_family": "regularized_logistic",
                    "hyperparameters": {"C": c_value},
                    "threshold": threshold,
                }
            )
    for leaves in (7, 15):
        for threshold in (0.5, 0.6):
            trials.append(
                {
                    "trial_id": f"lightgbm_l{leaves}_t{threshold:g}",
                    "model_family": "lightgbm_challenger",
                    "hyperparameters": {"num_leaves": leaves, "max_depth": 3},
                    "threshold": threshold,
                }
            )
    if len(trials) > SEARCH_CAP:
        raise ValueError("momentum ML search cap exceeded")
    return trials


def _make_estimator(trial: dict[str, Any]):
    if trial["model_family"] == "regularized_logistic":
        return make_pipeline(
            StandardScaler(),
            LogisticRegression(
                C=float(trial["hyperparameters"]["C"]),
                max_iter=1000,
                random_state=RANDOM_SEED,
            ),
        )
    return create_lightgbm_classifier(
        seed=RANDOM_SEED,
        hyperparameters={
            **trial["hyperparameters"],
            "n_estimators": 100,
            "min_child_samples": 20,
        },
    )


def _gate_position(
    baseline_slice: pd.Series,
    test_events: pd.DataFrame,
    accepted: pd.Series,
    *,
    offset: int,
    initially_active: bool = False,
) -> pd.Series:
    gated = pd.Series(0.0, index=baseline_slice.index, dtype="float64")
    decisions = {
        int(row.bar_index) - offset: bool(accepted.loc[index])
        for index, row in test_events.iterrows()
    }
    active = initially_active
    previous = 1.0 if initially_active else 0.0
    for local_index, value in enumerate(baseline_slice.astype(float).to_numpy()):
        if value > 0 and previous <= 0:
            active = decisions.get(local_index, True)
        if value <= 0:
            active = False
        gated.iloc[local_index] = value if active else 0.0
        previous = value
    return gated


def _fold_summary(
    frame: pd.DataFrame,
    rule_position: pd.Series,
    positions: dict[str, pd.Series],
    probabilities: dict[str, pd.Series],
    test_events: pd.DataFrame,
    start: int,
    end: int,
    fold: int,
) -> dict[str, Any]:
    local_frame = frame.iloc[start:end].reset_index(drop=True)
    rule_returns = _strategy_returns(
        local_frame,
        rule_position.iloc[start:end].reset_index(drop=True),
        cost_bps=BASE_COST_BPS["30m"],
        allow_overnight=True,
    )
    challengers: dict[str, Any] = {}
    labels = test_events["label"].astype(int)
    for trial_id, position in positions.items():
        if trial_id not in probabilities:
            continue
        returns = _strategy_returns(
            local_frame,
            position.iloc[start:end].reset_index(drop=True),
            cost_bps=BASE_COST_BPS["30m"],
            allow_overnight=True,
        )
        probability = probabilities[trial_id]
        challengers[trial_id] = {
            **_metrics(returns),
            "roc_auc": _safe_auc(labels, probability),
            "brier_score": round(float(brier_score_loss(labels, probability)), 6),
        }
    return {
        "fold": fold,
        "entry_events": int(len(test_events)),
        "rule": _metrics(rule_returns),
        "challengers": challengers,
    }


def _safe_auc(labels: pd.Series, predictions: pd.Series) -> float | None:
    if labels.nunique() < 2:
        return None
    return round(float(roc_auc_score(labels, predictions)), 6)


def _information_ratio(active_returns: pd.Series) -> float:
    clean = active_returns.dropna().astype(float)
    if clean.empty or float(clean.std(ddof=0)) <= 0:
        return 0.0
    return round(float(clean.mean() / clean.std(ddof=0) * np.sqrt(252 * 13)), 4)


def _best_trial(rows: list[dict[str, Any]], family: str) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row["model_family"] == family
        and not row.get("failures")
        and row.get("oos_entry_coverage") == 1.0
    ]
    return max(
        candidates,
        key=lambda row: (
            row["stitched_oos_metrics"]["total_return_pct"],
            row["stitched_oos_metrics"]["sharpe"],
        ),
        default=None,
    )


def _mean_fold_metric(
    folds: list[dict[str, Any]],
    trial_id: str,
    metric: str,
) -> float:
    values = [
        fold["challengers"][trial_id].get(metric)
        for fold in folds
        if fold["challengers"][trial_id].get(metric) is not None
    ]
    return round(float(np.mean(values)), 4) if values else 0.0


def _worst_fold_return_delta(folds: list[dict[str, Any]], trial_id: str) -> float:
    deltas = [
        fold["challengers"][trial_id]["total_return_pct"] - fold["rule"]["total_return_pct"]
        for fold in folds
    ]
    return round(float(min(deltas)), 4) if deltas else 0.0


def _non_overlap_auc(rows: list[pd.DataFrame]) -> float:
    if not rows:
        return 0.0
    combined = pd.concat(rows, ignore_index=True).sort_values("bar_index")
    selected_indices: list[int] = []
    last_bar = -MAX_EPISODE_BARS
    for index, row in combined.iterrows():
        bar_index = int(row["bar_index"])
        if bar_index - last_bar >= MAX_EPISODE_BARS:
            selected_indices.append(index)
            last_bar = bar_index
    selected = combined.loc[selected_indices]
    value = _safe_auc(selected["label"].astype(int), selected["probability"])
    return float(value or 0.0)


def _comparison_failed_gates(
    lightgbm_best: dict[str, Any] | None,
    logistic_best: dict[str, Any] | None,
) -> list[str]:
    if lightgbm_best is None or logistic_best is None:
        return ["missing_model_family_result"]
    checks = {
        "four_valid_folds": lightgbm_best["fold_count"] >= 4,
        "three_fold_wins": lightgbm_best["fold_wins_vs_rule"] >= 3,
        "mean_auc_above_0_52": lightgbm_best["mean_oos_auc"] > 0.52,
        "non_overlap_auc_above_0_52": lightgbm_best["non_overlap_oos_auc"] > 0.52,
        "positive_ir": lightgbm_best["information_ratio_vs_rule"] > 0,
        "worst_fold_not_worse": lightgbm_best["worst_fold_return_delta_pct"] >= 0,
        "beats_logistic_return": (
            lightgbm_best["stitched_oos_metrics"]["total_return_pct"]
            > logistic_best["stitched_oos_metrics"]["total_return_pct"]
        ),
    }
    return [name for name, passed in checks.items() if not passed]


def _blocked_comparison(design: dict[str, Any]) -> dict[str, Any]:
    return {
        "report_type": "momentum_strategy_specific_ml_comparison",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "blocked_preflight",
        "workflow_pass": False,
        "research_pass": False,
        "paper_ready_pass": False,
        "execution_behavior_changed": False,
        "training_scope": "not_started",
        "blockers": design["blockers"],
        "trials": [],
        "acceptance": {
            "ml_gate_beats_rule_and_linear": False,
            "selected_for_execution": False,
            "negative_result_is_valid": True,
        },
    }


def _write_comparison_artifacts(
    payload: dict[str, Any],
    json_path: Path,
    markdown_path: Path,
    ledger_path: Path,
    trials: list[dict[str, Any]],
) -> None:
    write_json(json_path, payload)
    markdown_path.write_text(_render_comparison_markdown(payload), encoding="utf-8")
    with ledger_path.open("w", encoding="utf-8") as handle:
        for trial in trials:
            handle.write(json.dumps(trial, sort_keys=True) + "\n")


def _render_design_markdown(payload: dict[str, Any]) -> str:
    gate_rows = "\n".join(
        f"| {name} | {row['actual']} | {'PASS' if row['passed'] else 'FAIL'} |"
        for name, row in payload["gates"].items()
    )
    return (
        f"# Momentum ML Design: {payload['strategy_name']}\n\n"
        f"- Decision: `{payload['decision']}`\n"
        f"- Role: `{payload['role']}`\n"
        f"- Scope: `{payload['decision_scope']}`\n"
        f"- Execution behavior changed: `false`\n\n"
        "| Gate | Actual | Result |\n|---|---:|---|\n"
        f"{gate_rows}\n"
    )


def _render_comparison_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Momentum Strategy-Specific ML Comparison",
        "",
        f"- Status: `{payload['status']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- Execution behavior changed: `{payload['execution_behavior_changed']}`",
        "",
    ]
    if "rule" in payload:
        rule = payload["rule"]["stitched_oos_metrics"]
        lines.extend(
            [
                "| Trial | Family | Return % | Sharpe | MaxDD % | IR vs rule | Fold wins |",
                "|---|---|---:|---:|---:|---:|---:|",
                (
                    f"| frozen_rule | rule | {rule['total_return_pct']} | "
                    f"{rule['sharpe']} | {rule['max_drawdown_pct']} | 0 | - |"
                ),
            ]
        )
        for trial in payload["trials"]:
            metrics = trial["stitched_oos_metrics"]
            lines.append(
                f"| {trial['trial_id']} | {trial['model_family']} | "
                f"{metrics['total_return_pct']} | "
                f"{metrics['sharpe']} | {metrics['max_drawdown_pct']} | "
                f"{trial['information_ratio_vs_rule']} | "
                f"{trial['fold_wins_vs_rule']}/{trial['fold_count']} |"
            )
    else:
        lines.append("Training did not start because the strategy-specific preflight failed.")
    lines.extend(
        ["", "No model is connected to execution, target weights, Paper, or broker writes."]
    )
    return "\n".join(lines) + "\n"
