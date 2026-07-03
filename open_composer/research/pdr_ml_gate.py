from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.models.strategy_spec import StrategySpec
from open_composer.research.ml_backend.model_factory import create_lightgbm_classifier
from open_composer.research.ml_backend.windows import MLWindowSlice, ml_walk_forward_slices
from open_composer.research.post_drawdown_reentry_router import (
    PostDrawdownReentryParams,
    _route_decisions,
)
from open_composer.research.post_drawdown_reentry_router import (
    _features as pdr_features,
)
from open_composer.research.router_common import RouterFrameDataset

PDR_ML_GATE_FAMILY = "pdr_defensive_exit_ml_gate"
PDR_ML_GATE_HORIZONS = (10, 20)
PDR_ML_GATE_THRESHOLDS_PCT = (0.0, 2.0)
PDR_ML_GATE_PROBABILITY_THRESHOLDS = (0.6, 0.7, 0.8)
PDR_ML_GATE_FEATURE_COLUMNS = (
    "qqq_mom20",
    "qqq_mom60",
    "qqq_mom120",
    "qqq_vol60",
    "qqq_dd20",
    "qqq_dd60",
    "tqqq_mom20",
    "tqqq_mom60",
    "tqqq_mom120",
    "tqqq_vol60",
    "tqqq_dd20",
    "tqqq_dd60",
    "gld_mom20",
    "gld_mom60",
    "gld_mom120",
    "gld_vol60",
    "gld_dd20",
    "gld_dd60",
    "canary_breadth",
    "vol_rank",
)

_TOKEN_RE = re.compile(
    r"^mlgate_h(?P<horizon>\d+)_t(?P<threshold>m?\d+(?:p\d+)?)_p(?P<probability>\d+)$"
)


@dataclass(frozen=True)
class PDRMLGateConfig:
    horizon_bars: int
    threshold_return_pct: float
    probability_threshold: float

    @property
    def token(self) -> str:
        return (
            f"mlgate_h{self.horizon_bars}"
            f"_t{_encode_number(self.threshold_return_pct)}"
            f"_p{int(round(self.probability_threshold * 100))}"
        )

    @property
    def cache_key(self) -> str:
        return (
            f"h{self.horizon_bars}_t{_encode_number(self.threshold_return_pct)}"
            f"_p{int(round(self.probability_threshold * 100))}"
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "family": PDR_ML_GATE_FAMILY,
            "horizon_bars": self.horizon_bars,
            "threshold_return_pct": self.threshold_return_pct,
            "probability_threshold": self.probability_threshold,
            "token": self.token,
            "cache_key": self.cache_key,
        }


def pdr_ml_gate_from_token(token: str) -> PDRMLGateConfig:
    match = _TOKEN_RE.fullmatch(token)
    if match is None:
        raise ValueError(f"unsupported PDR ML gate token: {token}")
    config = PDRMLGateConfig(
        horizon_bars=int(match.group("horizon")),
        threshold_return_pct=_decode_number(match.group("threshold")),
        probability_threshold=int(match.group("probability")) / 100,
    )
    if config not in pdr_ml_gate_search_space():
        raise ValueError(f"PDR ML gate token is outside the bounded search space: {token}")
    return config


def pdr_ml_gate_search_space() -> tuple[PDRMLGateConfig, ...]:
    return tuple(
        PDRMLGateConfig(horizon, threshold, probability)
        for horizon in PDR_ML_GATE_HORIZONS
        for threshold in PDR_ML_GATE_THRESHOLDS_PCT
        for probability in PDR_ML_GATE_PROBABILITY_THRESHOLDS
    )


def validate_pdr_ml_gate_training_config(*, horizon_bars: int, embargo_bars: int) -> None:
    if embargo_bars < horizon_bars:
        raise ValueError(
            "PDR ML gate requires embargo_bars >= horizon_bars "
            f"(got embargo_bars={embargo_bars}, horizon_bars={horizon_bars})"
        )


def pdr_ml_gate_artifact_path(
    spec: StrategySpec,
    config: PDRMLGateConfig,
    *,
    root: Path | None = None,
) -> Path:
    base = root or project_root()
    return (
        base
        / "reports"
        / "research"
        / "ml"
        / spec.name
        / f"pdr_mlgate_oos_predictions_{config.cache_key}.json"
    )


def register_pdr_ml_gate_predictions(
    dataset: RouterFrameDataset,
    config: PDRMLGateConfig,
    predictions: dict[str, float] | pd.Series,
) -> None:
    if isinstance(predictions, pd.Series):
        mapping = {
            str(index): float(value)
            for index, value in predictions.dropna().items()
            if math.isfinite(float(value))
        }
    else:
        mapping = {
            str(date): float(value)
            for date, value in predictions.items()
            if _finite_or_none(value) is not None
        }
    dataset.runtime_cache[_prediction_cache_key(config)] = mapping


def pdr_ml_gate_probability(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    config: PDRMLGateConfig,
    index: int,
    *,
    root: Path | None = None,
) -> float | None:
    try:
        if index < 0 or index >= len(dataset.dates):
            return None
        mapping = _prediction_map(spec, dataset, config, root=root)
        value = mapping.get(dataset.dates[index])
        return _finite_or_none(value)
    except Exception:
        return None


def pdr_ml_gate_should_release(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    config: PDRMLGateConfig,
    index: int,
    *,
    root: Path | None = None,
) -> bool:
    probability = pdr_ml_gate_probability(spec, dataset, config, index, root=root)
    return probability is not None and probability >= config.probability_threshold


def build_pdr_ml_gate_feature_frame(dataset: RouterFrameDataset) -> pd.DataFrame:
    features = pdr_features(dataset)
    close = features["close"]
    payload: dict[str, Any] = {
        "timestamp": [pd.Timestamp(date).isoformat() for date in dataset.dates],
        "date": list(dataset.dates),
        "canary_breadth": pd.to_numeric(features["canary_breadth"], errors="coerce").to_numpy(),
        "vol_rank": pd.to_numeric(features["vol_rank"], errors="coerce").to_numpy(),
    }
    for symbol in ("QQQ", "TQQQ", "GLD"):
        lower = symbol.lower()
        if symbol not in close.columns:
            continue
        for lookback in (20, 60, 120):
            payload[f"{lower}_mom{lookback}"] = pd.to_numeric(
                features["momentum"][lookback][symbol], errors="coerce"
            ).to_numpy()
        payload[f"{lower}_vol60"] = pd.to_numeric(
            features["vol60"][symbol], errors="coerce"
        ).to_numpy()
        payload[f"{lower}_dd20"] = pd.to_numeric(
            features["dd20"][symbol], errors="coerce"
        ).to_numpy()
        payload[f"{lower}_dd60"] = pd.to_numeric(
            features["dd60"][symbol], errors="coerce"
        ).to_numpy()
    return pd.DataFrame(payload, index=pd.Index(dataset.dates, name="date_index"))


def build_pdr_ml_gate_label(
    dataset: RouterFrameDataset,
    config: PDRMLGateConfig,
) -> pd.Series:
    close = pdr_features(dataset)["close"][dataset.market_symbol]
    forward_return = close.shift(-config.horizon_bars) / close - 1.0
    threshold = config.threshold_return_pct / 100
    label = (forward_return >= threshold).astype(float)
    label[forward_return.isna()] = float("nan")
    return pd.Series(label.to_numpy(), index=pd.Index(dataset.dates, name="date_index"))


def train_pdr_ml_gate_trials(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    base_params: PostDrawdownReentryParams,
    *,
    root: Path | None = None,
    window_bars: int = 756,
    test_window_bars: int = 126,
    retrain_every_bars: int = 63,
    seed: int = 42,
    hyperparameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base = root or project_root()
    out_dir = ensure_dir(base / "reports" / "research" / "ml" / spec.name)
    feature_frame = build_pdr_ml_gate_feature_frame(dataset)
    states = pd.Series(
        [state for _, state in _route_decisions(dataset, base_params)],
        index=feature_frame.index,
    )
    hard_stress_mask = states == "hard_stress_defensive"
    ledger_rows: list[dict[str, Any]] = []
    artifact_paths: list[str] = []
    for trial_id, config in enumerate(pdr_ml_gate_search_space(), start=1):
        trial = _train_single_trial(
            spec,
            dataset,
            config,
            feature_frame,
            hard_stress_mask,
            out_dir,
            trial_id=trial_id,
            window_bars=window_bars,
            test_window_bars=test_window_bars,
            retrain_every_bars=retrain_every_bars,
            seed=seed,
            hyperparameters=hyperparameters,
        )
        ledger_rows.append(trial["ledger"])
        if trial.get("artifact_path"):
            artifact_paths.append(str(trial["artifact_path"]))
    ledger_path = out_dir / "pdr_mlgate_trial_ledger.jsonl"
    ledger_path.write_text(
        "\n".join(json.dumps(row, sort_keys=True) for row in ledger_rows) + "\n",
        encoding="utf-8",
    )
    summary = {
        "report_type": "pdr_ml_gate_training",
        "strategy_name": spec.name,
        "family": PDR_ML_GATE_FAMILY,
        "trial_count": len(ledger_rows),
        "search_space": {
            "horizon_bars": list(PDR_ML_GATE_HORIZONS),
            "threshold_return_pct": list(PDR_ML_GATE_THRESHOLDS_PCT),
            "probability_threshold": list(PDR_ML_GATE_PROBABILITY_THRESHOLDS),
            "candidate_count": len(pdr_ml_gate_search_space()),
        },
        "feature_alignment": "index-1",
        "decision_scope": "base route state == hard_stress_defensive",
        "purged_embargo": "embargo_bars is set equal to horizon_bars for every trial",
        "trial_ledger_path": str(ledger_path),
        "prediction_artifacts": artifact_paths,
    }
    summary_path = out_dir / "pdr_mlgate_training_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def _train_single_trial(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    config: PDRMLGateConfig,
    feature_frame: pd.DataFrame,
    hard_stress_mask: pd.Series,
    out_dir: Path,
    *,
    trial_id: int,
    window_bars: int,
    test_window_bars: int,
    retrain_every_bars: int,
    seed: int,
    hyperparameters: dict[str, Any] | None,
) -> dict[str, Any]:
    embargo_bars = config.horizon_bars
    validate_pdr_ml_gate_training_config(
        horizon_bars=config.horizon_bars,
        embargo_bars=embargo_bars,
    )
    label = build_pdr_ml_gate_label(dataset, config)
    windows = ml_walk_forward_slices(
        feature_frame,
        window_bars=window_bars,
        test_window_bars=test_window_bars,
        retrain_every_bars=retrain_every_bars,
        horizon_bars=config.horizon_bars,
        embargo_bars=embargo_bars,
    )
    predictions = pd.Series(float("nan"), index=feature_frame.index, dtype="float64")
    folds: list[dict[str, Any]] = []
    try:
        for window in windows:
            fold = _fit_predict_gate_fold(
                config,
                feature_frame,
                label,
                hard_stress_mask,
                predictions,
                window,
                seed=seed,
                hyperparameters=hyperparameters,
            )
            folds.append(fold)
    except RuntimeError as exc:
        ledger = _trial_ledger_row(
            trial_id,
            config,
            status="blocked",
            status_reason=str(exc),
            windows=windows,
            folds=folds,
            predictions=predictions,
        )
        return {"ledger": ledger, "artifact_path": None}
    artifact_path = out_dir / f"pdr_mlgate_oos_predictions_{config.cache_key}.json"
    artifact_payload = {
        "report_type": "pdr_ml_gate_oos_predictions",
        "strategy_name": spec.name,
        "config": config.to_payload(),
        "feature_columns": list(PDR_ML_GATE_FEATURE_COLUMNS),
        "feature_alignment": "index-1",
        "decision_scope": "base route state == hard_stress_defensive",
        "folds": folds,
        "predictions": [
            {"date": str(date), "probability": float(value)}
            for date, value in predictions.dropna().items()
            if math.isfinite(float(value))
        ],
    }
    artifact_path.write_text(
        json.dumps(artifact_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    ledger = _trial_ledger_row(
        trial_id,
        config,
        status="ok",
        status_reason="trained stitched-OOS probabilities for hard_stress_defensive rows",
        windows=windows,
        folds=folds,
        predictions=predictions,
        artifact_path=artifact_path,
    )
    return {"ledger": ledger, "artifact_path": artifact_path}


def _fit_predict_gate_fold(
    config: PDRMLGateConfig,
    feature_frame: pd.DataFrame,
    label: pd.Series,
    hard_stress_mask: pd.Series,
    predictions: pd.Series,
    window: MLWindowSlice,
    *,
    seed: int,
    hyperparameters: dict[str, Any] | None,
) -> dict[str, Any]:
    train_rows = _joined_rows(
        feature_frame, label, hard_stress_mask, window.train_start_idx, window.train_end_idx
    )
    test_rows = _joined_rows(
        feature_frame, label, hard_stress_mask, window.test_start_idx, window.test_end_idx
    )
    if len(train_rows) < 30 or len(test_rows) < 5:
        return _fold_payload(
            window,
            train_rows,
            test_rows,
            status="skipped",
            reason="insufficient hard-stress rows",
            horizon_bars=config.horizon_bars,
            embargo_bars=config.horizon_bars,
        )
    if train_rows["__label__"].nunique(dropna=True) < 2:
        return _fold_payload(
            window,
            train_rows,
            test_rows,
            status="skipped",
            reason="single-class train labels",
            horizon_bars=config.horizon_bars,
            embargo_bars=config.horizon_bars,
        )
    estimator = create_lightgbm_classifier(seed=seed + window.fold, hyperparameters=hyperparameters)
    train_x = train_rows[list(PDR_ML_GATE_FEATURE_COLUMNS)]
    train_y = train_rows["__label__"].round().astype(int)
    test_x = test_rows[list(PDR_ML_GATE_FEATURE_COLUMNS)]
    test_y = test_rows["__label__"].round().astype(int)
    estimator.fit(train_x, train_y)
    probabilities = pd.Series(
        estimator.predict_proba(test_x)[:, 1],
        index=test_x.index,
        dtype="float64",
    )
    predictions.loc[probabilities.index] = probabilities
    return {
        **_fold_payload(
            window,
            train_rows,
            test_rows,
            status="ok",
            reason="trained",
            horizon_bars=config.horizon_bars,
            embargo_bars=config.horizon_bars,
        ),
        "test_rank_ic": _rank_ic(probabilities, test_y),
        "test_accuracy_at_threshold": _accuracy(
            probabilities >= config.probability_threshold, test_y
        ),
        "release_count": int((probabilities >= config.probability_threshold).sum()),
    }


def _joined_rows(
    feature_frame: pd.DataFrame,
    label: pd.Series,
    hard_stress_mask: pd.Series,
    start: int,
    end: int,
) -> pd.DataFrame:
    rows = feature_frame.iloc[start:end].copy()
    rows["__label__"] = label.iloc[start:end].to_numpy()
    rows["__hard_stress__"] = hard_stress_mask.iloc[start:end].to_numpy()
    rows = rows[rows["__hard_stress__"]]
    return rows.dropna(subset=[*PDR_ML_GATE_FEATURE_COLUMNS, "__label__"])


def _fold_payload(
    window: MLWindowSlice,
    train_rows: pd.DataFrame,
    test_rows: pd.DataFrame,
    *,
    status: str,
    reason: str,
    horizon_bars: int,
    embargo_bars: int,
) -> dict[str, Any]:
    return {
        "fold": window.fold,
        "status": status,
        "reason": reason,
        "train_rows": int(len(train_rows)),
        "test_rows": int(len(test_rows)),
        "train_start_idx": window.train_start_idx,
        "train_end_idx": window.train_end_idx,
        "test_start_idx": window.test_start_idx,
        "test_end_idx": window.test_end_idx,
        "purged_embargo": {
            "purged": True,
            "horizon_bars": horizon_bars,
            "embargo_bars": embargo_bars,
            "gap_bars": window.test_start_idx - window.train_end_idx,
        },
    }


def _trial_ledger_row(
    trial_id: int,
    config: PDRMLGateConfig,
    *,
    status: str,
    status_reason: str,
    windows: list[MLWindowSlice],
    folds: list[dict[str, Any]],
    predictions: pd.Series,
    artifact_path: Path | None = None,
) -> dict[str, Any]:
    valid_folds = [fold for fold in folds if fold.get("status") == "ok"]
    pred_count = int(predictions.notna().sum())
    return {
        "trial_id": trial_id,
        "family": PDR_ML_GATE_FAMILY,
        "config": config.to_payload(),
        "status": status,
        "status_reason": status_reason,
        "fold_count": len(valid_folds),
        "window_count": len(windows),
        "prediction_count": pred_count,
        "release_count": int((predictions.dropna() >= config.probability_threshold).sum()),
        "mean_test_rank_ic": _mean_or_none(
            [
                fold.get("test_rank_ic")
                for fold in valid_folds
                if fold.get("test_rank_ic") is not None
            ]
        ),
        "feature_columns": list(PDR_ML_GATE_FEATURE_COLUMNS),
        "feature_alignment": "index-1",
        "purged_embargo": {
            "horizon_bars": config.horizon_bars,
            "embargo_bars": config.horizon_bars,
            "train_end_rule": "train_end_idx <= test_start_idx - horizon_bars - embargo_bars",
        },
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
    }


def _prediction_map(
    spec: StrategySpec,
    dataset: RouterFrameDataset,
    config: PDRMLGateConfig,
    *,
    root: Path | None = None,
) -> dict[str, float]:
    key = _prediction_cache_key(config)
    cached = dataset.runtime_cache.get(key)
    if isinstance(cached, dict):
        return cached
    path = pdr_ml_gate_artifact_path(spec, config, root=root)
    if not path.exists():
        dataset.runtime_cache[key] = {}
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    mapping = {
        str(row["date"]): float(row["probability"])
        for row in payload.get("predictions", [])
        if _finite_or_none(row.get("probability")) is not None
    }
    dataset.runtime_cache[key] = mapping
    return mapping


def _prediction_cache_key(config: PDRMLGateConfig) -> str:
    return f"pdr_ml_gate_predictions:{config.cache_key}"


def _finite_or_none(value: object) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _rank_ic(prediction: pd.Series, label: pd.Series) -> float | None:
    joined = pd.DataFrame({"prediction": prediction, "label": label}).dropna()
    if len(joined) < 3:
        return None
    if joined["prediction"].nunique(dropna=True) <= 1 or joined["label"].nunique(dropna=True) <= 1:
        return None
    value = joined["prediction"].rank().corr(joined["label"].rank())
    return None if pd.isna(value) else float(value)


def _accuracy(prediction: pd.Series, label: pd.Series) -> float | None:
    joined = pd.DataFrame(
        {"prediction": prediction.astype(int), "label": label.astype(int)}
    ).dropna()
    if len(joined) == 0:
        return None
    return float((joined["prediction"] == joined["label"]).mean())


def _mean_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(sum(values) / len(values))


def _encode_number(value: float) -> str:
    text = f"{abs(value):g}".replace(".", "p")
    return f"m{text}" if value < 0 else text


def _decode_number(value: str) -> float:
    sign = -1.0 if value.startswith("m") else 1.0
    normalized = value.removeprefix("m").replace("p", ".")
    return sign * float(normalized)
