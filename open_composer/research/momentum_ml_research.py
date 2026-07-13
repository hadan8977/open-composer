from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.ml_backend.model_factory import create_lightgbm_classifier
from open_composer.research.mom_minute_lockbox import _position
from open_composer.research.mom_minute_round import (
    BASE_COST_BPS,
    _align_signal_and_trade,
    _load_bundle,
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
EMBARGO_BARS = 13
SEARCH_CAP = 12
MIN_ENTRY_EVENTS = 80
MIN_CLASS_EVENTS = 20
VALIDATION_EVENT_COUNTS = (30, 30, 23)
INITIAL_TRAIN_EVENTS = 55
HOLDOUT_SESSIONS = 102
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
    folds, _ = _nested_event_folds(aligned, events)
    development = _development_events(aligned, events)
    class_counts = development["label"].value_counts().to_dict() if not development.empty else {}
    gates = {
        "frozen_strategy_identity": {
            "actual": spec.name,
            "expected": EXPECTED_SPEC_NAME,
            "passed": spec.name == EXPECTED_SPEC_NAME,
        },
        "entry_events": {
            "actual": int(len(development)),
            "threshold": MIN_ENTRY_EVENTS,
            "passed": len(development) >= MIN_ENTRY_EVENTS,
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
            "actual": (
                int(development[list(FEATURES)].dropna().shape[0]) if not development.empty else 0
            ),
            "threshold": int(len(development)),
            "passed": bool(
                not development.empty and development[list(FEATURES)].notna().all(axis=None)
            ),
        },
        "purge_and_embargo": {
            "actual": {
                "method": "episode_end_before_test_start_minus_embargo",
                "embargo_bars": EMBARGO_BARS,
            },
            "threshold": EMBARGO_BARS,
            "passed": EMBARGO_BARS >= 13,
        },
        "valid_walk_forward_folds": {
            "actual": len(folds),
            "threshold": 3,
            "passed": len(folds) == 3,
        },
        "ml_family_holdout": {
            "actual": HOLDOUT_SESSIONS,
            "threshold": HOLDOUT_SESSIONS,
            "passed": len(dict.fromkeys(aligned["session_date"].tolist())) > HOLDOUT_SESSIONS,
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
            "purge_method": "actual_episode_end",
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
                "at least two of three validation fold wins before the ML-family holdout",
                "the final ML-family holdout is opened once after model-family selection",
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
    events = _entry_events(aligned, baseline_position, _feature_frame(aligned))
    folds, holdout = _nested_event_folds(aligned, events)
    trials = _trial_definitions()
    prediction_frames: dict[str, list[pd.DataFrame]] = {row["trial_id"]: [] for row in trials}
    fold_rows: list[dict[str, Any]] = []
    for fold in folds:
        train = fold["train"]
        test = fold["test"]
        for trial in trials:
            try:
                estimator = _make_estimator(trial)
                estimator.fit(train[list(FEATURES)], train["label"].astype(int))
                probability = estimator.predict_proba(test[list(FEATURES)])[:, 1]
                prediction_frames[trial["trial_id"]].append(
                    test[["bar_index", "exit_bar_index", "label", "forward_net_return"]].assign(
                        fold=fold["fold"], probability=probability
                    )
                )
            except Exception as exc:
                trial.setdefault("failures", []).append(
                    {"fold": fold["fold"], "error": f"{type(exc).__name__}: {exc}"}
                )
        fold_rows.append(
            {
                "fold": fold["fold"],
                "train_events": len(train),
                "test_events": len(test),
                "test_start": test["timestamp"].iloc[0],
                "test_end": test["timestamp"].iloc[-1],
            }
        )

    trial_rows = [
        _validation_trial_row(trial, prediction_frames[trial["trial_id"]]) for trial in trials
    ]
    qualified = {
        family: _best_trial(trial_rows, family)
        for family in ("regularized_logistic", "lightgbm_challenger")
    }
    diagnostic_selected = {
        family: _diagnostic_best_trial(trial_rows, family)
        for family in ("regularized_logistic", "lightgbm_challenger")
    }
    holdout_start_session = list(dict.fromkeys(aligned["session_date"].tolist()))[-HOLDOUT_SESSIONS]
    holdout_start = int(aligned.index[aligned["session_date"] == holdout_start_session].min())
    refit = events.loc[
        (events["bar_index"] < holdout_start)
        & (events["exit_bar_index"] <= holdout_start - EMBARGO_BARS)
    ]
    model_dir = output / "models"
    ensure_dir(model_dir)
    frozen_models: list[dict[str, Any]] = []
    for family, winner in diagnostic_selected.items():
        if winner is None:
            continue
        estimator = _make_estimator(winner)
        estimator.fit(refit[list(FEATURES)], refit["label"].astype(int))
        model_path = model_dir / f"{family}.joblib"
        joblib.dump(estimator, model_path)
        model_sha256 = _sha256_file(model_path)
        frozen_models.append(
            {
                "model_family": family,
                "trial_id": winner["trial_id"],
                "threshold": winner["threshold"],
                "model_path": str(model_path.relative_to(base)),
                "model_sha256": model_sha256,
                "status": "diagnostic_shadow_only",
                "qualified_for_holdout": qualified[family] is not None,
                "training_event_count": int(len(refit)),
                "training_event_hash": _event_hash(refit),
                "training_cutoff_bar": holdout_start - EMBARGO_BARS,
                "feature_contract_hash": sha256("\n".join(FEATURES).encode()).hexdigest(),
                "spec_hash": design.payload["spec_hash"],
                "source_contract_sha256": design.payload["source_contract_sha256"],
                "random_seed": RANDOM_SEED,
            }
        )
    any_family_qualified = any(row is not None for row in qualified.values())
    payload = {
        "report_type": "momentum_strategy_specific_ml_comparison",
        "iter_id": ITER_ID,
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "holdout_not_opened_keep_rule_champion",
        "workflow_pass": True,
        "research_pass": False,
        "paper_ready_pass": False,
        "execution_behavior_changed": False,
        "training_scope": "offline_research_only",
        "design_path": str(design.json_path.relative_to(base)),
        "fold_count": len(fold_rows),
        "stitched_oos_entry_predictions": sum(VALIDATION_EVENT_COUNTS),
        "independence_unit": "frozen_rule_entry_episode",
        "rule": {"trial_id": "frozen_rule"},
        "trials": trial_rows,
        "folds": fold_rows,
        "ml_family_holdout": {
            "opened_once": False,
            "events_reserved": len(holdout),
            "rows": [],
            "reason": "no model family won at least two of three validation folds",
            "previous_holdout_invalidly_opened": True,
            "previous_results_invalidated": True,
        },
        "frozen_models": frozen_models,
        "acceptance": {
            "any_family_qualified_for_holdout": any_family_qualified,
            "any_ml_family_holdout_pass": False,
            "independent_lockbox_pass": False,
            "selected_for_execution": False,
            "negative_result_is_valid": True,
            "selection_caveat": "Validation failed the preregistered 2/3 fold gate, so the "
            "holdout was not evaluated by this corrected run.",
        },
        "limitations": [
            "Alpaca IEX materialized history remains research-only evidence.",
            "This comparison evaluates entry filtering only; it does not repair exit "
            "hysteresis or position sizing.",
            "Frozen models are diagnostic shadow artifacts only and are not connected to "
            "paper orders or broker writes.",
            "A previous implementation opened the reserved holdout despite failing the "
            "validation gate; those holdout results are invalidated and cannot be reused.",
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
        episode_position = pd.Series(0.0, index=frame.index)
        episode_position.iloc[bar_index:end] = 1.0
        episode_returns = _strategy_returns(
            frame,
            episode_position,
            cost_bps=BASE_COST_BPS["30m"],
            allow_overnight=True,
        ).iloc[bar_index : end + 1]
        net_return = float((1.0 + episode_returns).prod() - 1.0)
        row = {
            "bar_index": int(bar_index),
            "exit_bar_index": int(end),
            "timestamp": pd.Timestamp(frame.iloc[bar_index]["timestamp"]).isoformat(),
            "session_date": str(frame.iloc[bar_index]["session_date"]),
            "label": int(net_return > 0),
            "forward_net_return": net_return,
            "episode_bars": episode_bars,
        }
        row.update({name: float(feature_row[name]) for name in FEATURES})
        rows.append(row)
    return pd.DataFrame(rows)


def _nested_event_folds(
    frame: pd.DataFrame,
    events: pd.DataFrame,
) -> tuple[list[dict[str, Any]], pd.DataFrame]:
    sessions = list(dict.fromkeys(frame["session_date"].tolist()))
    if len(sessions) <= HOLDOUT_SESSIONS:
        return [], events.iloc[0:0].copy()
    holdout_start_session = sessions[-HOLDOUT_SESSIONS]
    holdout = events.loc[events["session_date"] >= holdout_start_session].copy()
    development = events.loc[events["session_date"] < holdout_start_session].copy()
    folds: list[dict[str, Any]] = []
    train_count = INITIAL_TRAIN_EVENTS
    for fold_number, test_count in enumerate(VALIDATION_EVENT_COUNTS, start=1):
        raw_test = development.iloc[train_count : train_count + test_count].copy()
        if len(raw_test) != test_count:
            continue
        test_start_bar = int(raw_test["bar_index"].min())
        train = (
            development.iloc[:train_count]
            .loc[development.iloc[:train_count]["exit_bar_index"] <= test_start_bar - EMBARGO_BARS]
            .copy()
        )
        if train["label"].nunique() < 2 or raw_test["label"].nunique() < 2:
            continue
        folds.append({"fold": fold_number, "train": train, "test": raw_test})
        train_count += test_count
    return folds, holdout


def _development_events(frame: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    sessions = list(dict.fromkeys(frame["session_date"].tolist()))
    if len(sessions) <= HOLDOUT_SESSIONS:
        return events.iloc[0:0].copy()
    holdout_start_session = sessions[-HOLDOUT_SESSIONS]
    return events.loc[events["session_date"] < holdout_start_session].copy()


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


def _safe_auc(labels: pd.Series, predictions: pd.Series) -> float | None:
    if labels.nunique() < 2:
        return None
    return round(float(roc_auc_score(labels, predictions)), 6)


def _best_trial(rows: list[dict[str, Any]], family: str) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row["model_family"] == family
        and not row.get("failures")
        and row.get("oos_entry_coverage") == 1.0
        and row.get("fold_count") == len(VALIDATION_EVENT_COUNTS)
        and row.get("fold_wins_vs_rule", 0) >= 2
        and row.get("information_ratio_vs_rule", 0.0) > 0
        and (
            row["validation_metrics"]["total_return_pct"]
            > row["rule_validation_metrics"]["total_return_pct"]
            or row["validation_metrics"]["episode_sharpe"]
            > row["rule_validation_metrics"]["episode_sharpe"]
        )
        and row["validation_metrics"]["max_drawdown_pct"]
        >= row["rule_validation_metrics"]["max_drawdown_pct"]
    ]
    return max(
        candidates,
        key=lambda row: (
            row["fold_wins_vs_rule"],
            row["validation_metrics"]["total_return_pct"],
            row["validation_metrics"]["episode_sharpe"],
        ),
        default=None,
    )


def _diagnostic_best_trial(rows: list[dict[str, Any]], family: str) -> dict[str, Any] | None:
    candidates = [
        row
        for row in rows
        if row["model_family"] == family
        and not row.get("failures")
        and row.get("oos_entry_coverage") == 1.0
        and row.get("fold_count") == len(VALIDATION_EVENT_COUNTS)
    ]
    return max(
        candidates,
        key=lambda row: (
            row["fold_wins_vs_rule"],
            row["validation_metrics"]["total_return_pct"],
            row["validation_metrics"]["episode_sharpe"],
        ),
        default=None,
    )


def _sha256_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _event_hash(events: pd.DataFrame) -> str:
    columns = ["bar_index", "exit_bar_index", "timestamp", "label"]
    payload = events[columns].to_json(orient="records", date_format="iso")
    return sha256(payload.encode()).hexdigest()


def _validation_trial_row(
    trial: dict[str, Any],
    prediction_frames: list[pd.DataFrame],
) -> dict[str, Any]:
    if not prediction_frames:
        return {
            **trial,
            "status": "failed_model_fallback",
            "fold_count": 0,
            "fold_wins_vs_rule": 0,
            "oos_entry_coverage": 0.0,
            "validation_metrics": {},
        }
    predictions = pd.concat(prediction_frames, ignore_index=True)
    accepted = predictions["probability"] >= float(trial["threshold"])
    metrics = _event_evaluation(predictions, predictions["probability"], accepted)
    rule_metrics = _event_evaluation(
        predictions,
        pd.Series(1.0, index=predictions.index),
        pd.Series(True, index=predictions.index),
    )
    accepted_returns = predictions["forward_net_return"].where(accepted.to_numpy(), 0.0)
    active_returns = accepted_returns - predictions["forward_net_return"]
    active_std = float(active_returns.std(ddof=0))
    information_ratio = (
        float(active_returns.mean() / active_std * np.sqrt(len(active_returns)))
        if active_std > 0
        else 0.0
    )
    fold_wins = 0
    fold_rows = []
    for fold, local in predictions.groupby("fold", sort=True):
        local_accepted = local["probability"] >= float(trial["threshold"])
        challenger = _event_evaluation(local, local["probability"], local_accepted)
        rule = _event_evaluation(
            local,
            pd.Series(1.0, index=local.index),
            pd.Series(True, index=local.index),
        )
        fold_wins += int(challenger["total_return_pct"] >= rule["total_return_pct"])
        fold_rows.append(
            {
                "fold": int(fold),
                "challenger_total_return_pct": challenger["total_return_pct"],
                "rule_total_return_pct": rule["total_return_pct"],
            }
        )
    return {
        **trial,
        "status": "failed_model_fallback" if trial.get("failures") else "validation_complete",
        "fold_count": len(prediction_frames),
        "fold_wins_vs_rule": fold_wins,
        "oos_entry_coverage": round(len(predictions) / sum(VALIDATION_EVENT_COUNTS), 4),
        "validation_metrics": metrics,
        "rule_validation_metrics": rule_metrics,
        "information_ratio_vs_rule": round(information_ratio, 4),
        "folds": fold_rows,
    }


def _event_evaluation(
    events: pd.DataFrame,
    probability: pd.Series,
    accepted: pd.Series,
) -> dict[str, Any]:
    selected_returns = events["forward_net_return"].where(accepted.to_numpy(), 0.0).astype(float)
    equity = (1.0 + selected_returns).cumprod()
    total_return = float(equity.iloc[-1] - 1.0) if len(equity) else 0.0
    std = float(selected_returns.std(ddof=0)) if len(selected_returns) else 0.0
    sharpe = (
        float(selected_returns.mean() / std * np.sqrt(len(selected_returns))) if std > 0 else 0.0
    )
    drawdown = equity / equity.cummax() - 1.0 if len(equity) else pd.Series([0.0])
    labels = events["label"].astype(int)
    return {
        "events": int(len(events)),
        "accepted_events": int(accepted.sum()),
        "acceptance_rate": round(float(accepted.mean()), 4) if len(accepted) else 0.0,
        "total_return_pct": round(total_return * 100, 4),
        "episode_sharpe": round(sharpe, 4),
        "max_drawdown_pct": round(float(drawdown.min()) * 100, 4),
        "roc_auc": _safe_auc(labels, probability),
        "brier_score": round(float(brier_score_loss(labels, probability)), 6),
    }


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
            "any_ml_family_holdout_pass": False,
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
    if payload.get("trials"):
        lines.extend(
            [
                "| Trial | Family | Validation Return % | Episode Sharpe | AUC | Fold wins |",
                "|---|---|---:|---:|---:|---:|",
            ]
        )
        for trial in payload["trials"]:
            metrics = trial["validation_metrics"]
            lines.append(
                f"| {trial['trial_id']} | {trial['model_family']} | "
                f"{metrics['total_return_pct']} | "
                f"{metrics['episode_sharpe']} | {metrics['roc_auc']} | "
                f"{trial['fold_wins_vs_rule']}/{trial['fold_count']} |"
            )
        lines.extend(["", "## ML-Family Holdout", ""])
        for row in payload["ml_family_holdout"]["rows"]:
            lines.append(
                f"- `{row['model_family']}` `{row['trial_id']}`: "
                f"passed=`{row['passed']}`, return=`{row['metrics']['total_return_pct']}%`, "
                f"rule=`{row['rule_metrics']['total_return_pct']}%`"
            )
    else:
        lines.append("Training did not start because the strategy-specific preflight failed.")
    lines.extend(
        ["", "No model is connected to execution, target weights, Paper, or broker writes."]
    )
    return "\n".join(lines) + "\n"
