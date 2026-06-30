from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import backtest_frame
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.ml_backend.training import MLTrainingRun, run_rolling_training


@dataclass(frozen=True)
class MLArtifactPaths:
    training_json: Path
    training_md: Path
    comparison_json: Path | None = None
    comparison_md: Path | None = None


def train_strategy_model(
    spec_path: Path, root: Path | None = None
) -> tuple[MLTrainingRun, MLArtifactPaths]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if spec.model is None:
        raise ValueError("strategy train requires StrategySpec.model")
    frame = load_ohlcv_for_spec(spec, base)
    training = run_rolling_training(spec, frame, base)
    out_dir = ensure_dir(base / "reports" / "research" / "ml" / spec.name)
    training_json = out_dir / "training.json"
    training_md = out_dir / "training.md"
    training_json.write_text(json.dumps(training.to_payload(), indent=2), encoding="utf-8")
    training_md.write_text(_render_training_markdown(spec, training), encoding="utf-8")
    return training, MLArtifactPaths(training_json=training_json, training_md=training_md)


def compare_ml_to_baseline(
    spec_path: Path, root: Path | None = None
) -> tuple[dict[str, Any], MLArtifactPaths]:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    if spec.model is None:
        raise ValueError("ML comparison requires StrategySpec.model")
    frame = load_ohlcv_for_spec(spec, base)
    training = run_rolling_training(spec, frame, base)
    ml_artifacts = backtest_frame(
        spec,
        frame,
        root=base,
        run_id_value=f"ml-walk-forward-{spec.name}",
    )
    baseline_spec = _linear_baseline_spec(spec)
    baseline_artifacts = backtest_frame(
        baseline_spec,
        frame,
        root=base,
        run_id_value=f"linear-baseline-{spec.name}",
    )
    payload = {
        "strategy_name": spec.name,
        "status": _comparison_status(
            ml_artifacts.run.sharpe_ratio, baseline_artifacts.run.sharpe_ratio
        ),
        "ml": _run_metrics(ml_artifacts.run),
        "baseline": _run_metrics(baseline_artifacts.run),
        "fold_count": len(training.folds),
        "feature_importance_mean": training.feature_importance_mean,
        "interpretation": (
            "ML must beat the linear StrategySpec baseline after costs before promotion. "
            "This comparison is research-only and does not imply paper readiness."
        ),
    }
    out_dir = ensure_dir(base / "reports" / "research" / "ml" / spec.name)
    comparison_json = out_dir / "ml_vs_baseline.json"
    comparison_md = out_dir / "ml_vs_baseline.md"
    comparison_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    comparison_md.write_text(_render_comparison_markdown(payload), encoding="utf-8")
    training_json = out_dir / "training.json"
    training_md = out_dir / "training.md"
    training_json.write_text(json.dumps(training.to_payload(), indent=2), encoding="utf-8")
    training_md.write_text(_render_training_markdown(spec, training), encoding="utf-8")
    return payload, MLArtifactPaths(
        training_json=training_json,
        training_md=training_md,
        comparison_json=comparison_json,
        comparison_md=comparison_md,
    )


def explain_strategy_model(spec_path: Path, root: Path | None = None, top_n: int = 10) -> Path:
    training, paths = train_strategy_model(spec_path, root)
    spec = load_strategy_spec(spec_path)
    out_path = paths.training_json.parent / "explain.md"
    rows = sorted(training.feature_importance_mean.items(), key=lambda item: item[1], reverse=True)
    lines = [
        f"# ML Explain: {spec.name}",
        "",
        "## Feature Importance",
        "",
        "| feature | importance |",
        "|---|---:|",
    ]
    for feature, importance in rows[:top_n]:
        lines.append(f"| `{feature}` | {importance:.6f} |")
    lines.extend(
        [
            "",
            "This explanation is based on LightGBM split/gain-style feature importance from "
            "walk-forward training folds. It is advisory research output, not a trading approval.",
        ]
    )
    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out_path


def _linear_baseline_spec(spec: StrategySpec) -> StrategySpec:
    raw = spec.model_dump(mode="json")
    raw["name"] = f"{spec.name}_linear_baseline"
    raw["model"] = None
    return StrategySpec.model_validate(raw)


def _run_metrics(run: Any) -> dict[str, Any]:
    return {
        "run_id": run.run_id,
        "signals": run.signals,
        "trades": run.trades,
        "total_return_pct": run.total_return_pct,
        "annualized_return_pct": run.annualized_return_pct,
        "sharpe_ratio": run.sharpe_ratio,
        "max_drawdown_pct": run.max_drawdown_pct,
        "total_fees": run.total_fees,
    }


def _comparison_status(ml_sharpe: float | None, baseline_sharpe: float | None) -> str:
    ml = ml_sharpe if ml_sharpe is not None else float("-inf")
    baseline = baseline_sharpe if baseline_sharpe is not None else float("-inf")
    if ml >= baseline * 1.05:
        return "ok"
    if ml >= baseline * 0.95:
        return "warning"
    return "blocked"


def _render_training_markdown(spec: StrategySpec, training: MLTrainingRun) -> str:
    lines = [
        f"# ML Training: {spec.name}",
        "",
        f"- Fold count: `{len(training.folds)}`",
        f"- OOS predictions: `{int(training.full_predictions.notna().sum())}`",
        "",
        "## Folds",
        "",
        "| fold | train rows | test rows | train rank IC | test rank IC |",
        "|---:|---:|---:|---:|---:|",
    ]
    for fold in training.folds:
        lines.append(
            f"| {fold.fold} | {fold.train_rows} | {fold.test_rows} | "
            f"{_fmt(fold.train_metric)} | {_fmt(fold.test_metric)} |"
        )
    lines.extend(["", "## Feature Importance", "", "| feature | importance |", "|---|---:|"])
    for feature, importance in sorted(
        training.feature_importance_mean.items(), key=lambda item: item[1], reverse=True
    ):
        lines.append(f"| `{feature}` | {importance:.6f} |")
    return "\n".join(lines).rstrip() + "\n"


def _render_comparison_markdown(payload: dict[str, Any]) -> str:
    ml = payload["ml"]
    baseline = payload["baseline"]
    lines = [
        f"# ML vs Linear Baseline: {payload['strategy_name']}",
        "",
        f"- Status: `{payload['status']}`",
        f"- Fold count: `{payload['fold_count']}`",
        "",
        "| path | signals | trades | return % | ann % | sharpe | max dd % | fees |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        _comparison_row("ML", ml),
        _comparison_row("Linear baseline", baseline),
        "",
        payload["interpretation"],
    ]
    return "\n".join(lines).rstrip() + "\n"


def _comparison_row(label: str, row: dict[str, Any]) -> str:
    return (
        f"| {label} | {row['signals']} | {row['trades']} | "
        f"{_fmt(row['total_return_pct'])} | {_fmt(row['annualized_return_pct'])} | "
        f"{_fmt(row['sharpe_ratio'])} | {_fmt(row['max_drawdown_pct'])} | "
        f"{_fmt(row['total_fees'])} |"
    )


def _fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, int | float):
        return f"{float(value):.3f}"
    return str(value)
