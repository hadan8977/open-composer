from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from open_composer.config import ensure_dir, project_root
from open_composer.research.multiasset_momentum import ALL_ETF_SYMBOLS, _load_panels
from open_composer.research.multiasset_momentum_ai import (
    CHALLENGE_DATES,
    build_ai_factor_dataset,
    build_ai_folds,
    fit_predict_ai_model,
    make_ai_estimator,
    run_base_trial,
    select_fold_features,
)
from open_composer.research.multiasset_momentum_ml import _evaluate_ranking_predictions
from open_composer.storage import append_jsonl, write_json

ITER_ID = "mom_multiasset_multimodal_r3"
OUTPUT_DIR = Path("reports/research/iterations") / ITER_ID
SOURCE_ITER_DIR = Path("reports/research/iterations/mom_multiasset_r1")
CAPABILITY_PATH = OUTPUT_DIR / "multimodal-capability.json"
MAX_CANDIDATES = 24
TOP_N = 5
DAY_NIGHT_FEATURES = (
    "intraday_mom_21_rank",
    "intraday_mom_63_rank",
    "overnight_mom_21_rank",
    "overnight_mom_63_rank",
    "day_night_spread_21_rank",
    "day_night_agreement_63_rank",
)


@dataclass(frozen=True)
class MultimodalMomentumResult:
    report_path: Path
    markdown_path: Path
    trial_ledger_path: Path
    payload: dict[str, Any]


def multimodal_trial_specs() -> list[dict[str, Any]]:
    rows = [
        _trial("deterministic_12_1", "champion_and_text_ablations", "available"),
        _trial("quant_ranker_daynight", "champion_and_text_ablations", "available"),
        _trial("text_only", "champion_and_text_ablations", "historical_text"),
        _trial("quant_plus_text", "champion_and_text_ablations", "historical_text"),
        _trial("shuffled_text_placebo", "champion_and_text_ablations", "historical_text"),
        _trial("stale_text_placebo", "champion_and_text_ablations", "historical_text"),
    ]
    rows.extend(
        _trial(f"{role}_{strength}", "catalyst_and_risk_roles", "historical_text")
        for role in ("catalyst_confirm", "false_momentum_veto", "text_risk_gate")
        for strength in ("low", "high")
    )
    rows.extend(
        _trial(name, "regime_and_disagreement_meta", "available")
        for name in (
            "regime_train_median",
            "regime_train_upper_quartile",
            "disagreement_train_median",
            "disagreement_train_upper_quartile",
            "agreement_overlap3",
            "agreement_overlap4",
        )
    )
    rows.extend(
        _trial(f"shrink_{alpha:03d}_cost{cost}", "cost_aware_shrinkage", "available")
        for cost in (10, 20)
        for alpha in (25, 50, 75)
    )
    if len(rows) != MAX_CANDIDATES:
        raise AssertionError(f"multimodal matrix must contain exactly {MAX_CANDIDATES} trials")
    return rows


def run_multiasset_multimodal_round(
    root: Path | None = None,
    *,
    cost_bps: float = 10.0,
) -> MultimodalMomentumResult:
    base = root or project_root()
    output = ensure_dir(base / OUTPUT_DIR)
    capability_path = base / CAPABILITY_PATH
    if not capability_path.exists():
        raise FileNotFoundError("run momentum-multimodal-capability before the round")
    capability = json.loads(capability_path.read_text(encoding="utf-8"))
    if not capability.get("pit_contract_pass"):
        raise ValueError("multimodal PIT contract is not ready")
    manifest_path = base / SOURCE_ITER_DIR / "universe-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    symbols = [str(symbol) for symbol in manifest["selected_symbols"]]
    sector_map = {
        str(row["symbol"]): str(row.get("sector") or "Unknown") for row in manifest["selected"]
    }
    data = _load_panels(base, list(dict.fromkeys((*symbols, *ALL_ETF_SYMBOLS))))
    dataset, latest, feature_groups = build_ai_factor_dataset(data, symbols, sector_map)
    dataset, latest, feature_groups = add_day_night_features(
        data, dataset, latest, feature_groups, symbols
    )
    eval_dates = sorted(dataset.loc[dataset["is_monthly_eval"], "decision_date"].unique().tolist())
    development_dates = eval_dates[:-CHALLENGE_DATES]
    folds = build_ai_folds(dataset, development_dates)
    if len(folds) != 4:
        raise ValueError("multimodal round requires four chronological development folds")

    quant_spec = {
        "trial_id": "quant_ranker_daynight",
        "model_family": "lightgbm_lambdarank",
        "feature_set": "expanded_quant",
    }
    quant_row, predictions = run_base_trial(quant_spec, folds, feature_groups, cost_bps=cost_bps)
    thresholds = _train_only_thresholds(folds, feature_groups)
    trial_rows = []
    for spec in multimodal_trial_specs():
        trial_id = str(spec["trial_id"])
        if spec["dependency"] == "historical_text" and not capability.get(
            "historical_multimodal_training_authorized"
        ):
            trial_rows.append(
                {
                    **spec,
                    "status": "skipped_dependency",
                    "reason": "real_historical_multimodal_packets_not_authorized",
                    "candidate_counted": True,
                }
            )
        elif trial_id == "deterministic_12_1":
            trial_rows.append(_deterministic_trial(spec, predictions, folds, cost_bps=cost_bps))
        elif trial_id == "quant_ranker_daynight":
            trial_rows.append({**spec, **quant_row, "candidate_counted": True})
        elif spec["path"] == "regime_and_disagreement_meta":
            trial_rows.append(_meta_trial(spec, predictions, folds, thresholds, cost_bps=cost_bps))
        elif spec["path"] == "cost_aware_shrinkage":
            alpha, candidate_cost = _shrink_params(trial_id)
            trial_rows.append(
                _score_trial(
                    spec,
                    predictions,
                    folds,
                    score=_rank_blend(predictions, alpha),
                    cost_bps=float(candidate_cost),
                    details={"ml_weight": alpha, "evaluation_cost_bps": candidate_cost},
                )
            )
        else:  # pragma: no cover - candidate registry is exhaustively tested
            raise AssertionError(f"unhandled multimodal candidate: {trial_id}")
    if len(trial_rows) != MAX_CANDIDATES:
        raise AssertionError("trial ledger row count escaped preregistered cap")

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    ledger_rows = [{"run_id": run_id, "iter_id": ITER_ID, **row} for row in trial_rows]
    trial_ledger_path = output / "trial-ledger.jsonl"
    append_jsonl(trial_ledger_path, ledger_rows)
    completed = [row for row in trial_rows if row["status"] == "validation_complete"]
    skipped = [row for row in trial_rows if row["status"] == "skipped_dependency"]
    best = max(completed, key=_selection_score)
    model_path, latest_rows, selected_features = _freeze_quant_model(
        output, dataset, latest, feature_groups
    )
    payload = {
        "schema_version": 1,
        "report_type": "multiasset_multimodal_momentum_evaluation",
        "iter_id": ITER_ID,
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "workflow_pass": True,
        "research_pass": False,
        "llm_contribution_pass": False,
        "paper_ready_pass": False,
        "candidate_count": len(trial_rows),
        "candidate_cap": MAX_CANDIDATES,
        "completed_candidate_count": len(completed),
        "skipped_candidate_count": len(skipped),
        "capability_path": _relpath(capability_path, base),
        "historical_multimodal_training_authorized": capability.get(
            "historical_multimodal_training_authorized", False
        ),
        "data_profile": {
            "provider": "longbridge",
            "data_as_of": data["data_as_of"],
            "universe_status": "frozen_current_snapshot_exploratory_history",
            "historical_challenge_reopened": False,
        },
        "feature_contract": {
            "day_night_features": list(DAY_NIGHT_FEATURES),
            "all_day_night_features_index_minus_1": True,
            "label_horizon_bars": 21,
            "embargo_bars": 21,
            "symbol_identity_feature": False,
        },
        "folds": [
            {
                "fold": fold["fold"],
                "train_end_position": fold["train_end_position"],
                "test_start_position": fold["test_start_position"],
                "purge_embargo_gap": fold["test_start_position"]
                - int(fold["train"]["label_end_position"].max()),
            }
            for fold in folds
        ],
        "trials": trial_rows,
        "selection": {
            "best_development_trial": best["trial_id"],
            "best_development_score": _selection_score(best),
            "quant_ranker_qualified": bool(quant_row["qualified"]),
            "formal_promotion": False,
            "reason": (
                "real historical text coverage is unavailable and the prior challenge "
                "is not reopened; completed quant roles remain diagnostic"
            ),
        },
        "frozen_quant_diagnostic": {
            "model_path": _relpath(model_path, base),
            "selected_features": selected_features,
            "latest_predictions": latest_rows,
            "status": "diagnostic_forward_observation_only",
        },
        "trial_ledger_path": _relpath(trial_ledger_path, base),
        "limitations": [
            "Ten text-dependent candidates were counted and skipped, not replaced by fixtures.",
            "Historical LLM contribution remains untested because real PIT coverage is absent.",
            "The exposed historical challenge was not reopened for model selection.",
            "The frozen current stock universe remains survivorship-biased before 2026-07-14.",
        ],
    }
    report_path = output / "evaluation-report.json"
    markdown_path = output / "evaluation-report.md"
    write_json(report_path, payload)
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return MultimodalMomentumResult(report_path, markdown_path, trial_ledger_path, payload)


def add_day_night_features(
    data: dict[str, Any],
    dataset: pd.DataFrame,
    latest: pd.DataFrame,
    feature_groups: dict[str, tuple[str, ...]],
    symbols: list[str],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, tuple[str, ...]]]:
    frames = day_night_feature_frames(data, symbols)
    work = dataset.copy()
    current = latest.copy()
    index = data["close"].index
    for name, frame in frames.items():
        work[name] = [
            frame.at[index[int(position)], symbol]
            for position, symbol in zip(work["decision_position"], work["symbol"], strict=True)
        ]
        current[name] = [
            frame.at[index[int(position)], symbol]
            for position, symbol in zip(
                current["decision_position"], current["symbol"], strict=True
            )
        ]
    groups = dict(feature_groups)
    groups["expanded_quant"] = tuple(
        dict.fromkeys((*feature_groups["expanded_quant"], *DAY_NIGHT_FEATURES))
    )
    groups["all"] = tuple(dict.fromkeys((*feature_groups["all"], *DAY_NIGHT_FEATURES)))
    return work, current, groups


def day_night_feature_frames(data: dict[str, Any], symbols: list[str]) -> dict[str, pd.DataFrame]:
    close = data["close"][symbols]
    open_prices = data["open"][symbols]
    intraday = close.div(open_prices).sub(1).shift(1)
    overnight = open_prices.div(close.shift(1)).sub(1).shift(1)

    def compound(frame: pd.DataFrame, window: int) -> pd.DataFrame:
        return (
            frame.add(1)
            .rolling(window, min_periods=max(15, window // 2))
            .apply(np.prod, raw=True)
            .sub(1)
        )

    intraday21 = compound(intraday, 21)
    intraday63 = compound(intraday, 63)
    overnight21 = compound(overnight, 21)
    overnight63 = compound(overnight, 63)
    spread21 = intraday21 - overnight21
    agreement63 = -(intraday63 - overnight63).abs()
    return {
        "intraday_mom_21_rank": intraday21.rank(axis=1, pct=True),
        "intraday_mom_63_rank": intraday63.rank(axis=1, pct=True),
        "overnight_mom_21_rank": overnight21.rank(axis=1, pct=True),
        "overnight_mom_63_rank": overnight63.rank(axis=1, pct=True),
        "day_night_spread_21_rank": spread21.rank(axis=1, pct=True),
        "day_night_agreement_63_rank": agreement63.rank(axis=1, pct=True),
    }


def _train_only_thresholds(
    folds: list[dict[str, Any]], feature_groups: dict[str, tuple[str, ...]]
) -> dict[int, dict[str, float]]:
    rows = {}
    for fold in folds:
        train = fold["train"].copy()
        selected, _ = select_fold_features(
            train,
            feature_set="expanded_quant",
            feature_groups=feature_groups,
        )
        model = make_ai_estimator("lightgbm_lambdarank")
        in_sample = fit_predict_ai_model(model, "lightgbm_lambdarank", train, train, selected)
        work = train[["decision_date", "baseline_score"]].copy()
        work["prediction"] = in_sample
        disagreement = (
            work.groupby("decision_date")["prediction"].rank(pct=True)
            - work.groupby("decision_date")["baseline_score"].rank(pct=True)
        ).abs()
        market = train.groupby("decision_date")["market_spy_mom_63"].first()
        rows[int(fold["fold"])] = {
            "regime_median": float(market.median()),
            "regime_upper_quartile": float(market.quantile(0.75)),
            "disagreement_median": float(disagreement.median()),
            "disagreement_upper_quartile": float(disagreement.quantile(0.75)),
        }
    return rows


def _deterministic_trial(
    spec: dict[str, Any],
    predictions: pd.DataFrame,
    folds: list[dict[str, Any]],
    *,
    cost_bps: float,
) -> dict[str, Any]:
    return _score_trial(
        spec,
        predictions,
        folds,
        score=predictions["baseline_score"],
        cost_bps=cost_bps,
        details={"role": "frozen_champion"},
        baseline_self=True,
    )


def _meta_trial(
    spec: dict[str, Any],
    predictions: pd.DataFrame,
    folds: list[dict[str, Any]],
    thresholds: dict[int, dict[str, float]],
    *,
    cost_bps: float,
) -> dict[str, Any]:
    trial_id = str(spec["trial_id"])
    scores = pd.Series(index=predictions.index, dtype=float)
    threshold_rows = []
    for fold in folds:
        fold_id = int(fold["fold"])
        part = predictions[predictions["fold"] == fold_id]
        model_rank = part.groupby("decision_date")["prediction"].rank(pct=True)
        baseline_rank = part.groupby("decision_date")["baseline_score"].rank(pct=True)
        if trial_id.startswith("regime_"):
            key = "regime_upper_quartile" if "upper" in trial_id else "regime_median"
            threshold = thresholds[fold_id][key]
            score = pd.Series(
                np.where(part["market_spy_mom_63"] > threshold, model_rank, baseline_rank),
                index=part.index,
            )
        elif trial_id.startswith("disagreement_"):
            key = "disagreement_upper_quartile" if "upper" in trial_id else "disagreement_median"
            threshold = thresholds[fold_id][key]
            disagreement = (model_rank - baseline_rank).abs()
            score = pd.Series(
                np.where(disagreement <= threshold, model_rank, baseline_rank),
                index=part.index,
            )
        else:
            overlap_required = 4 if trial_id.endswith("4") else 3
            threshold = float(overlap_required)
            score = baseline_rank.copy()
            for _decision_date, group in part.groupby("decision_date", sort=True):
                model_top = set(group.nlargest(TOP_N, "prediction")["symbol"])
                base_top = set(group.nlargest(TOP_N, "baseline_score")["symbol"])
                if len(model_top & base_top) >= overlap_required:
                    score.loc[group.index] = model_rank.loc[group.index]
        scores.loc[part.index] = score
        threshold_rows.append({"fold": fold_id, "threshold": threshold})
    return _score_trial(
        spec,
        predictions,
        folds,
        score=scores,
        cost_bps=cost_bps,
        details={"train_only_thresholds": threshold_rows},
    )


def _score_trial(
    spec: dict[str, Any],
    predictions: pd.DataFrame,
    folds: list[dict[str, Any]],
    *,
    score: pd.Series,
    cost_bps: float,
    details: dict[str, Any],
    baseline_self: bool = False,
) -> dict[str, Any]:
    work = predictions.copy()
    work["score"] = score
    aggregate = _evaluate_ranking_predictions(work, work["score"].to_numpy(), cost_bps)
    baseline = _evaluate_ranking_predictions(work, work["baseline_score"].to_numpy(), cost_bps)
    fold_rows = []
    for fold in folds:
        part = work[work["fold"] == fold["fold"]]
        model = _evaluate_ranking_predictions(part, part["score"].to_numpy(), cost_bps)
        base = _evaluate_ranking_predictions(part, part["baseline_score"].to_numpy(), cost_bps)
        fold_rows.append(
            {
                "fold": fold["fold"],
                "fold_win": False if baseline_self else _metrics_better(model, base),
                "model": model,
                "baseline": base,
            }
        )
    fold_wins = sum(bool(row["fold_win"]) for row in fold_rows)
    return {
        **spec,
        "status": "validation_complete",
        "candidate_counted": True,
        "folds": fold_rows,
        "fold_wins": fold_wins,
        "aggregate": aggregate,
        "baseline_aggregate": baseline,
        "qualified": bool(
            not baseline_self
            and fold_wins >= 3
            and not all(not row["fold_win"] for row in fold_rows[-2:])
            and _aggregate_not_worse(aggregate, baseline)
        ),
        **details,
    }


def _freeze_quant_model(
    output: Path,
    dataset: pd.DataFrame,
    latest: pd.DataFrame,
    feature_groups: dict[str, tuple[str, ...]],
) -> tuple[Path, list[dict[str, Any]], list[str]]:
    selected, _ = select_fold_features(
        dataset,
        feature_set="expanded_quant",
        feature_groups=feature_groups,
    )
    model = make_ai_estimator("lightgbm_lambdarank")
    predictions = fit_predict_ai_model(model, "lightgbm_lambdarank", dataset, latest, selected)
    model_path = ensure_dir(output / "models") / "quant_ranker_daynight.joblib"
    joblib.dump(
        {
            "model": model,
            "features": selected,
            "fill_values": dataset[selected].median().to_dict(),
            "status": "diagnostic_forward_observation_only",
        },
        model_path,
    )
    rows = latest[["symbol", "baseline_score"]].copy()
    rows["prediction"] = predictions
    rows["model_rank"] = rows["prediction"].rank(pct=True)
    rows["baseline_rank"] = rows["baseline_score"].rank(pct=True)
    rows = rows.sort_values("prediction", ascending=False)
    return model_path, rows.head(TOP_N).to_dict(orient="records"), selected


def _rank_blend(frame: pd.DataFrame, alpha: float) -> pd.Series:
    model_rank = frame.groupby("decision_date")["prediction"].rank(pct=True)
    baseline_rank = frame.groupby("decision_date")["baseline_score"].rank(pct=True)
    return baseline_rank * (1 - alpha) + model_rank * alpha


def _shrink_params(trial_id: str) -> tuple[float, int]:
    match = re.fullmatch(r"shrink_(\d{3})_cost(\d+)", trial_id)
    if match is None:
        raise ValueError(trial_id)
    return int(match.group(1)) / 100, int(match.group(2))


def _trial(trial_id: str, path: str, dependency: str) -> dict[str, Any]:
    return {"trial_id": trial_id, "path": path, "dependency": dependency}


def _metrics_better(model: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        model["portfolio_total_return_pct"] > baseline["portfolio_total_return_pct"]
        and model["mean_rank_ic"] >= baseline["mean_rank_ic"]
    )


def _aggregate_not_worse(model: dict[str, Any], baseline: dict[str, Any]) -> bool:
    return bool(
        model["portfolio_total_return_pct"] >= baseline["portfolio_total_return_pct"]
        and model["mean_rank_ic"] >= baseline["mean_rank_ic"]
    )


def _selection_score(row: dict[str, Any]) -> float:
    aggregate = row.get("aggregate") or {}
    return (
        float(aggregate.get("portfolio_total_return_pct", -1e9))
        + float(aggregate.get("mean_rank_ic", 0.0)) * 100
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Multiasset Multimodal Momentum R3",
        "",
        f"- Workflow pass: `{payload['workflow_pass']}`",
        f"- Research pass: `{payload['research_pass']}`",
        f"- LLM contribution pass: `{payload['llm_contribution_pass']}`",
        f"- Paper ready pass: `{payload['paper_ready_pass']}`",
        f"- Candidates: `{payload['candidate_count']}/{payload['candidate_cap']}`",
        (
            f"- Completed/skipped: `{payload['completed_candidate_count']}/"
            f"{payload['skipped_candidate_count']}`"
        ),
        f"- Best development diagnostic: `{payload['selection']['best_development_trial']}`",
        "",
        "## Trial Summary",
        "",
        "| Trial | Path | Status | Fold wins | Qualified |",
        "|---|---|---|---:|---|",
    ]
    for row in payload["trials"]:
        lines.append(
            f"| {row['trial_id']} | {row['path']} | {row['status']} | "
            f"{row.get('fold_wins', '-')} | {row.get('qualified', False)} |"
        )
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            "Real historical multimodal packets are not authorized. Text-dependent trials were "
            "counted and skipped rather than replaced by fixtures. Quantitative day/night, "
            "regime/disagreement and shrinkage variants remain diagnostic because the exposed "
            "historical challenge was not reopened.",
        ]
    )
    return "\n".join(lines) + "\n"


def _relpath(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()
