from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import default_openai_model, ensure_dir, openai_api_key, project_root
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.ml_backend.training import MLTrainingRun, run_rolling_training
from open_composer.storage import append_jsonl, write_json


def explain_strategy_model(
    spec_path: Path,
    root: Path | None = None,
    *,
    top_n: int = 10,
    use_llm: bool = False,
) -> dict[str, Path]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if spec.model is None:
        raise ValueError("strategy explain requires StrategySpec.model")
    frame = load_ohlcv_for_spec(spec, base)
    training = run_rolling_training(spec, frame, base)
    out_dir = ensure_dir(base / "reports" / "research" / "ml" / spec.name)
    training_json = out_dir / "training.json"
    training_json.write_text(json.dumps(training.to_payload(), indent=2), encoding="utf-8")
    explanation = _build_explanation_payload(spec.name, training, top_n=top_n)
    llm_payload = _llm_advisory_payload(explanation, use_llm=use_llm)
    explanation.update(llm_payload)
    json_path = out_dir / "explain.json"
    md_path = out_dir / "explain.md"
    trace_path = out_dir / "trace.jsonl"
    write_json(json_path, explanation)
    md_path.write_text(_render_markdown(explanation), encoding="utf-8")
    append_jsonl(trace_path, [_trace_row(explanation, use_llm=use_llm)])
    return {"markdown": md_path, "json": json_path, "trace": trace_path}


def _build_explanation_payload(
    strategy_name: str,
    training: MLTrainingRun,
    *,
    top_n: int,
) -> dict[str, Any]:
    importance_rows = [
        {"feature": feature, "importance": float(importance)}
        for feature, importance in sorted(
            training.feature_importance_mean.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:top_n]
    ]
    worst_cases = _worst_prediction_cases(training, top_n=top_n)
    return {
        "strategy_name": strategy_name,
        "generated_at": datetime.now(UTC).isoformat(),
        "mode": "deterministic",
        "fold_count": len(training.folds),
        "prediction_count": int(training.full_predictions.notna().sum()),
        "feature_importance": importance_rows,
        "worst_prediction_cases": worst_cases,
        "advisory_summary": _deterministic_summary(importance_rows, worst_cases),
        "promotion_impact": "none_advisory_only",
        "paper_order_impact": "none",
    }


def _llm_advisory_payload(payload: dict[str, Any], *, use_llm: bool) -> dict[str, Any]:
    if not use_llm:
        return {
            "llm_requested": False,
            "llm_status": "not_requested",
            "llm_model": None,
            "llm_advisory": None,
        }
    if not openai_api_key():
        return {
            "llm_requested": True,
            "llm_status": "missing_api_key_fallback_to_deterministic",
            "llm_model": default_openai_model(),
            "llm_advisory": None,
        }
    return {
        "llm_requested": True,
        "llm_status": "not_called_safe_local_advisory_only",
        "llm_model": default_openai_model(),
        "llm_advisory": None,
    }


def _worst_prediction_cases(training: MLTrainingRun, *, top_n: int) -> list[dict[str, Any]]:
    joined = (
        training.full_predictions.rename("prediction")
        .to_frame()
        .join(training.labels.rename("label"))
        .dropna()
    )
    if joined.empty:
        return []
    joined["abs_error"] = (joined["prediction"] - joined["label"]).abs()
    rows = joined.sort_values("abs_error", ascending=False).head(top_n)
    return [
        {
            "timestamp": _stringify_index(index),
            "prediction": float(row["prediction"]),
            "label": float(row["label"]),
            "abs_error": float(row["abs_error"]),
        }
        for index, row in rows.iterrows()
    ]


def _deterministic_summary(
    importance_rows: list[dict[str, Any]],
    worst_cases: list[dict[str, Any]],
) -> str:
    if not importance_rows:
        return "No feature importance was produced; review training folds before using this model."
    top_feature = str(importance_rows[0]["feature"])
    return (
        f"Top feature by mean importance is {top_feature}. "
        f"Worst-case rows inspected: {len(worst_cases)}. "
        "This explanation is advisory and does not approve promotion or paper trading."
    )


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# ML Explain: {payload['strategy_name']}",
        "",
        f"- Mode: `{payload['mode']}`",
        f"- LLM status: `{payload['llm_status']}`",
        f"- Fold count: `{payload['fold_count']}`",
        f"- OOS predictions: `{payload['prediction_count']}`",
        f"- Promotion impact: `{payload['promotion_impact']}`",
        f"- Paper order impact: `{payload['paper_order_impact']}`",
        "",
        "## Advisory Summary",
        "",
        str(payload["advisory_summary"]),
        "",
        "## Feature Importance",
        "",
        "| feature | importance |",
        "|---|---:|",
    ]
    for row in payload["feature_importance"]:
        lines.append(f"| `{row['feature']}` | {float(row['importance']):.6f} |")
    lines.extend(
        [
            "",
            "## Worst Prediction Cases",
            "",
            "| timestamp | prediction | label | abs error |",
            "|---|---:|---:|---:|",
        ]
    )
    for row in payload["worst_prediction_cases"]:
        lines.append(
            f"| `{row['timestamp']}` | {float(row['prediction']):.6f} | "
            f"{float(row['label']):.6f} | {float(row['abs_error']):.6f} |"
        )
    lines.extend(
        [
            "",
            "This explanation is research-only. It does not modify the StrategySpec, "
            "promotion result, signal log, or paper order authorization.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _trace_row(payload: dict[str, Any], *, use_llm: bool) -> dict[str, Any]:
    input_text = json.dumps(
        {
            "strategy_name": payload["strategy_name"],
            "feature_importance": payload["feature_importance"],
            "worst_prediction_cases": payload["worst_prediction_cases"],
        },
        sort_keys=True,
    )
    prompt = "Explain ML feature importance and wrong-case examples for advisory review."
    return {
        "operation": "strategy_explain",
        "created_at": payload["generated_at"],
        "strategy_name": payload["strategy_name"],
        "llm_requested": use_llm,
        "llm_status": payload["llm_status"],
        "model": payload["llm_model"],
        "input_hash": hashlib.sha256(input_text.encode("utf-8")).hexdigest(),
        "prompt_hash": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "promotion_impact": "none_advisory_only",
        "paper_order_impact": "none",
    }


def _stringify_index(value: Any) -> str:
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)
