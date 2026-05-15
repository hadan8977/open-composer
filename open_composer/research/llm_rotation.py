from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.config import (
    default_openai_model,
    ensure_dir,
    openai_api_key,
    openai_base_url,
    project_root,
)
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.rotation import (
    RotationCandidate,
    RotationMetrics,
    RotationObjective,
    RotationParams,
    _backtest_rotation,
    _build_params_grid,
    _load_universe_frame,
    _score_rotation_candidate,
)
from open_composer.storage import write_json
from open_composer.timeframes import STRATEGY_TIMEFRAMES


class LLMRotationChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    expected_risks: list[str] = Field(default_factory=list)
    rejected_labels: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LLMRotationCandidate:
    rank: int
    params: RotationParams
    train: RotationMetrics
    validation: RotationMetrics
    validation_folds: list[RotationMetrics]
    score: float


@dataclass(frozen=True)
class LLMRotationResearchResult:
    report_path: Path
    json_path: Path
    prompt_path: Path
    choice: LLMRotationChoice
    selected: RotationCandidate
    reviewed_candidates: list[LLMRotationCandidate]
    status: Literal[
        "written",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
    ]


def run_llm_rotation_meta_selection(
    spec_path: Path,
    root: Path | None = None,
    symbols: list[str] | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    lookback_bars: list[int] | None = None,
    rebalance_bars: list[int] | None = None,
    top_n_values: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    validation_ratio: float = 0.3,
    validation_folds: int = 3,
    out_of_sample_ratio: float = 0.3,
    max_candidates: int = 200,
    refresh_data: bool = False,
    client: Any | None = None,
    model: str | None = None,
    start: str | None = None,
    end: str | None = None,
    objective: RotationObjective = "equal_weight_alpha",
) -> LLMRotationResearchResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    universe = [item.upper() for item in (symbols or spec.universe)]
    if len(universe) < 2:
        raise ValueError("LLM rotation meta-selection requires at least two symbols")
    if spec.timeframe not in STRATEGY_TIMEFRAMES:
        supported = ", ".join(STRATEGY_TIMEFRAMES)
        raise ValueError(f"LLM rotation meta-selection supports these timeframes: {supported}")

    selected_feed = feed or spec.data.feed
    frame = _load_universe_frame(
        spec=spec,
        root=base,
        symbols=universe,
        data_source=data_source,
        feed=selected_feed or "iex",
        refresh_data=refresh_data,
        feature_gate=False,
        start=start,
        end=end,
    )
    params_grid = _build_params_grid(
        lookback_bars or [21, 42, 63, 126],
        rebalance_bars or [5, 10, 21],
        top_n_values or [1, 2, 3],
        min_momentum_pct or [0.0, 5.0, 10.0],
        max_candidates=max_candidates,
    )
    train_end = _split_for_oos(
        frame_len=len(frame), ratio=out_of_sample_ratio, params_grid=params_grid
    )
    train_validation_frame = frame.iloc[:train_end].copy().reset_index(drop=True)
    reviewed = _build_reviewed_candidates(
        spec=spec,
        frame=train_validation_frame,
        symbols=universe,
        params_grid=params_grid,
        validation_ratio=validation_ratio,
        validation_folds=validation_folds,
        objective=objective,
    )
    prompt = _selection_prompt(spec, universe, reviewed, objective)
    prompt_path = base / "reports" / "research" / f"{spec.name}-llm-rotation-selection-prompt.json"
    ensure_dir(prompt_path.parent)
    prompt_path.write_text(json.dumps(prompt, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    status: Literal[
        "written",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
    ] = "written"
    if client is None and not openai_api_key():
        choice = _deterministic_choice(reviewed)
        status = "fallback_no_api_key"
    else:
        try:
            choice = _call_llm_choice(
                client or _openai_client(), model or default_openai_model(), prompt
            )
            labels = {item.params.label for item in reviewed}
            if choice.selected_label not in labels:
                choice = _deterministic_choice(reviewed)
                status = "fallback_invalid_choice"
        except Exception:
            choice = _deterministic_choice(reviewed)
            status = "fallback_api_error"

    selected_params = _params_by_label(reviewed)[choice.selected_label]
    selected = _selected_candidate(
        spec=spec,
        frame=frame,
        symbols=universe,
        params=selected_params,
        train_end=train_end,
        objective=objective,
    )
    json_path = base / "reports" / "research" / f"{spec.name}-llm-rotation-selection.json"
    report_path = base / "reports" / "research" / f"{spec.name}-llm-rotation-selection.md"
    _write_selection_json(
        json_path,
        spec,
        universe,
        reviewed,
        choice,
        selected,
        status,
        prompt_path,
        start,
        end,
        objective,
    )
    _write_selection_report(
        report_path,
        json_path,
        prompt_path,
        spec,
        universe,
        reviewed,
        choice,
        selected,
        status,
        start,
        end,
        objective,
    )
    return LLMRotationResearchResult(
        report_path=report_path,
        json_path=json_path,
        prompt_path=prompt_path,
        choice=choice,
        selected=selected,
        reviewed_candidates=reviewed,
        status=status,
    )


def _split_for_oos(frame_len: int, ratio: float, params_grid: list[RotationParams]) -> int:
    max_lookback = max(item.lookback_bars for item in params_grid)
    split = int(frame_len * (1 - ratio))
    split = max(split, max_lookback + 3)
    return min(split, frame_len - 2)


def _build_reviewed_candidates(
    *,
    spec: StrategySpec,
    frame: Any,
    symbols: list[str],
    params_grid: list[RotationParams],
    validation_ratio: float,
    validation_folds: int,
    objective: RotationObjective,
) -> list[LLMRotationCandidate]:
    split = _split_for_oos(len(frame), validation_ratio, params_grid)
    fold_size = _validation_fold_size(frame, params_grid, validation_folds)
    rows: list[LLMRotationCandidate] = []
    for params in params_grid:
        train_frame = frame.iloc[:split].copy()
        validation_start = max(0, split - params.lookback_bars - 1)
        validation_frame = frame.iloc[validation_start:].copy().reset_index(drop=True)
        train = _backtest_rotation(spec, train_frame, symbols, params)
        validation = _backtest_rotation(
            spec,
            validation_frame,
            symbols,
            params,
            evaluation_start_index=split - validation_start,
        )
        folds = _validation_fold_metrics(
            spec=spec,
            frame=frame,
            symbols=symbols,
            params=params,
            folds=validation_folds,
            fold_size=fold_size,
        )
        score = _meta_score(train, validation, folds, objective)
        rows.append(
            LLMRotationCandidate(
                rank=0,
                params=params,
                train=train,
                validation=validation,
                validation_folds=folds,
                score=score,
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        LLMRotationCandidate(
            rank=index,
            params=item.params,
            train=item.train,
            validation=item.validation,
            validation_folds=item.validation_folds,
            score=item.score,
        )
        for index, item in enumerate(rows, start=1)
    ]


def _validation_fold_size(
    frame: Any,
    params_grid: list[RotationParams],
    validation_folds: int,
) -> int:
    max_lookback = max(item.lookback_bars for item in params_grid)
    return max((len(frame) - max_lookback) // (max(validation_folds, 1) + 1), 2)


def _validation_fold_metrics(
    *,
    spec: StrategySpec,
    frame: Any,
    symbols: list[str],
    params: RotationParams,
    folds: int,
    fold_size: int,
) -> list[RotationMetrics]:
    rows: list[RotationMetrics] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = params.lookback_bars + fold * fold_size
        test_end = min(len(frame), test_start + fold_size)
        if test_end - test_start < 2:
            continue
        warm_start = max(0, test_start - params.lookback_bars - 1)
        rows.append(
            _backtest_rotation(
                spec,
                frame.iloc[warm_start:test_end].copy().reset_index(drop=True),
                symbols,
                params,
                evaluation_start_index=test_start - warm_start,
            )
        )
    return rows


def _meta_score(
    train: RotationMetrics,
    validation: RotationMetrics,
    validation_folds: list[RotationMetrics],
    objective: RotationObjective,
) -> float:
    train_score = _score_rotation_candidate(train, objective)
    validation_score = _score_rotation_candidate(validation, objective)
    train_alpha = _objective_alpha(train, objective)
    validation_alpha = _objective_alpha(validation, objective)
    stability_penalty = abs(train_alpha - validation_alpha)
    fold_summary = _fold_summary(validation_folds, objective)
    return (
        min(train_score, validation_score) * 0.7
        + validation_alpha * 0.5
        + fold_summary["avg_objective_alpha_pct"] * 0.7
        + fold_summary["min_objective_alpha_pct"] * 0.8
        + fold_summary["positive_alpha_fold_count"] * 15
        + (validation.sharpe_ratio or 0.0) * 8
        + fold_summary["avg_sharpe_ratio"] * 5
        - stability_penalty * 0.2
        - abs(min(validation.max_drawdown_pct, 0.0)) * 0.2
        - abs(min(fold_summary["worst_max_drawdown_pct"], 0.0)) * 0.15
    )


def _selection_prompt(
    spec: StrategySpec,
    symbols: list[str],
    reviewed: list[LLMRotationCandidate],
    objective: RotationObjective,
    limit: int = 24,
) -> dict[str, Any]:
    return {
        "task": (
            "Select one optical communications sector rotation method from training-only "
            "evidence. Do not assume access to final out-of-sample returns."
        ),
        "strategy_name": spec.name,
        "symbols": symbols,
        "available_evidence": (
            "training window plus internal validation and prior validation folds only"
        ),
        "hidden_from_model": "final out-of-sample and full-window metrics",
        "selection_objective": _objective_label(objective),
        "selection_criteria": [
            _objective_criterion(objective),
            "prefer candidates with positive alpha across most prior validation folds",
            "penalize a negative worst validation-fold alpha",
            "prefer validation Sharpe above 0.5",
            "prefer lower drawdown and moderate turnover",
            "penalize large train/validation instability",
            "do not chase the highest training score alone",
        ],
        "candidates": [_candidate_summary(item, objective) for item in reviewed[:limit]],
        "required_json_schema": LLMRotationChoice.model_json_schema(),
    }


def _candidate_summary(
    item: LLMRotationCandidate,
    objective: RotationObjective = "equal_weight_alpha",
) -> dict[str, Any]:
    return {
        "rank": item.rank,
        "label": item.params.label,
        "params": item.params.__dict__,
        "meta_score": item.score,
        "train": _metrics_summary(item.train),
        "validation": _metrics_summary(item.validation),
        "validation_fold_summary": _fold_summary(item.validation_folds, objective),
        "validation_folds": [_metrics_summary(metric) for metric in item.validation_folds],
    }


def _metrics_summary(metrics: RotationMetrics) -> dict[str, Any]:
    return {
        "return_pct": metrics.total_return_pct,
        "alpha_vs_equal_weight_pct": metrics.alpha_vs_equal_weight_pct,
        "alpha_vs_primary_pct": metrics.alpha_vs_primary_pct,
        "sharpe_ratio": metrics.sharpe_ratio,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "rebalances": metrics.rebalances,
        "trades": metrics.trades,
        "average_turnover_pct": metrics.average_turnover_pct,
    }


def _fold_summary(
    metrics: list[RotationMetrics],
    objective: RotationObjective = "equal_weight_alpha",
) -> dict[str, Any]:
    if not metrics:
        return {
            "fold_count": 0,
            "positive_alpha_fold_count": 0,
            "avg_alpha_vs_equal_weight_pct": 0.0,
            "min_alpha_vs_equal_weight_pct": 0.0,
            "avg_alpha_vs_primary_pct": 0.0,
            "min_alpha_vs_primary_pct": 0.0,
            "avg_objective_alpha_pct": 0.0,
            "min_objective_alpha_pct": 0.0,
            "avg_sharpe_ratio": 0.0,
            "worst_max_drawdown_pct": 0.0,
        }
    equal_weight_alpha_values = [item.alpha_vs_equal_weight_pct for item in metrics]
    primary_alpha_values = [item.alpha_vs_primary_pct for item in metrics]
    objective_alpha_values = [_objective_alpha(item, objective) for item in metrics]
    sharpe_values = [item.sharpe_ratio or 0.0 for item in metrics]
    drawdowns = [item.max_drawdown_pct for item in metrics]
    return {
        "fold_count": len(metrics),
        "positive_alpha_fold_count": sum(value > 0 for value in objective_alpha_values),
        "avg_alpha_vs_equal_weight_pct": mean(equal_weight_alpha_values),
        "min_alpha_vs_equal_weight_pct": min(equal_weight_alpha_values),
        "avg_alpha_vs_primary_pct": mean(primary_alpha_values),
        "min_alpha_vs_primary_pct": min(primary_alpha_values),
        "avg_objective_alpha_pct": mean(objective_alpha_values),
        "min_objective_alpha_pct": min(objective_alpha_values),
        "avg_sharpe_ratio": mean(sharpe_values),
        "worst_max_drawdown_pct": min(drawdowns),
    }


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key(), base_url=openai_base_url())


def _call_llm_choice(client: Any, model: str, prompt: dict[str, Any]) -> LLMRotationChoice:
    messages = [
        {
            "role": "system",
            "content": (
                "You choose a trading research candidate from training-only evidence. "
                "Return schema-valid JSON. Do not claim live trading certainty."
            ),
        },
        {"role": "user", "content": json.dumps(prompt, indent=2, sort_keys=True)},
    ]
    try:
        response = client.responses.parse(
            model=model,
            input=messages,
            text_format=LLMRotationChoice,
        )
        parsed = _extract_choice(response)
        if parsed is not None:
            return parsed
    except TypeError:
        response = client.responses.create(
            model=model,
            input=messages,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "llm_rotation_choice",
                    "strict": True,
                    "schema": LLMRotationChoice.model_json_schema(),
                }
            },
        )
        return LLMRotationChoice.model_validate_json(response.output_text)
    raise ValueError("LLM returned no schema-valid rotation choice")


def _extract_choice(response: Any) -> LLMRotationChoice | None:
    for output in getattr(response, "output", []):
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", []):
            parsed = getattr(item, "parsed", None)
            if isinstance(parsed, LLMRotationChoice):
                return parsed
            if isinstance(parsed, dict):
                return LLMRotationChoice.model_validate(parsed)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, LLMRotationChoice):
        return parsed
    if isinstance(parsed, dict):
        return LLMRotationChoice.model_validate(parsed)
    return None


def _deterministic_choice(reviewed: list[LLMRotationCandidate]) -> LLMRotationChoice:
    selected = reviewed[0]
    return LLMRotationChoice(
        selected_label=selected.params.label,
        confidence=0.0,
        rationale="Fallback selected the highest training-only meta score.",
        expected_risks=["No LLM API key or invalid model choice; deterministic fallback used."],
        rejected_labels=[item.params.label for item in reviewed[1:4]],
    )


def _params_by_label(reviewed: list[LLMRotationCandidate]) -> dict[str, RotationParams]:
    return {item.params.label: item.params for item in reviewed}


def _selected_candidate(
    *,
    spec: StrategySpec,
    frame: Any,
    symbols: list[str],
    params: RotationParams,
    train_end: int,
    objective: RotationObjective,
) -> RotationCandidate:
    train_frame = frame.iloc[:train_end].copy()
    oos_start = max(0, train_end - params.lookback_bars - 1)
    oos_frame = frame.iloc[oos_start:].copy().reset_index(drop=True)
    train = _backtest_rotation(spec, train_frame, symbols, params)
    oos = _backtest_rotation(
        spec,
        oos_frame,
        symbols,
        params,
        evaluation_start_index=train_end - oos_start,
    )
    full = _backtest_rotation(spec, frame, symbols, params)
    return RotationCandidate(
        rank=1,
        params=params,
        score=_score_rotation_candidate(train, objective),
        train=train,
        out_of_sample=oos,
        full_window=full,
        quality_flags=_selection_flags(oos, full),
    )


def _selection_flags(oos: RotationMetrics, full: RotationMetrics) -> list[str]:
    flags: list[str] = []
    if oos.alpha_vs_equal_weight_pct <= 0:
        flags.append("oos_no_alpha_vs_equal_weight")
    if oos.alpha_vs_primary_pct <= 0:
        flags.append("oos_no_alpha_vs_primary")
    if oos.sharpe_ratio is None or oos.sharpe_ratio < 0.5:
        flags.append("oos_low_sharpe")
    if full.alpha_vs_primary_pct <= 0:
        flags.append("full_window_no_alpha_vs_primary")
    if full.alpha_vs_best_symbol_pct <= 0:
        flags.append("does_not_beat_ex_post_best_symbol")
    return flags


def _write_selection_json(
    path: Path,
    spec: StrategySpec,
    symbols: list[str],
    reviewed: list[LLMRotationCandidate],
    choice: LLMRotationChoice,
    selected: RotationCandidate,
    status: str,
    prompt_path: Path,
    start: str | None,
    end: str | None,
    objective: RotationObjective,
) -> Path:
    payload = {
        "strategy_name": spec.name,
        "mode": "llm_training_meta_selection",
        "status": status,
        "symbols": symbols,
        "prompt_path": str(prompt_path),
        "research_window": {"start": start, "end": end},
        "selection_objective": _objective_label(objective),
        "anti_leakage": {
            "llm_visible_metrics": (
                "training plus internal validation and prior validation folds only"
            ),
            "llm_hidden_metrics": "final out-of-sample and full-window metrics",
            "llm_called_inside_backtest_loop": False,
        },
        "choice": choice.model_dump(mode="json"),
        "selected": {
            "params": selected.params.__dict__,
            "quality_flags": selected.quality_flags,
            "train": selected.train.__dict__,
            "out_of_sample": selected.out_of_sample.__dict__,
            "full_window": selected.full_window.__dict__,
        },
        "reviewed_candidates": [_candidate_summary(item, objective) for item in reviewed],
    }
    return write_json(path, payload)


def _write_selection_report(
    path: Path,
    json_path: Path,
    prompt_path: Path,
    spec: StrategySpec,
    symbols: list[str],
    reviewed: list[LLMRotationCandidate],
    choice: LLMRotationChoice,
    selected: RotationCandidate,
    status: str,
    start: str | None,
    end: str | None,
    objective: RotationObjective,
) -> Path:
    ensure_dir(path.parent)
    flags = ", ".join(selected.quality_flags) if selected.quality_flags else "none"
    lines = [
        f"# LLM Rotation Meta-Selection: {spec.name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Prompt artifact: `{prompt_path}`",
        f"- Status: `{status}`",
        f"- Symbols: {', '.join(symbols)}",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        "- Mode: `llm_training_meta_selection`",
        f"- Selection objective: {_objective_label(objective)}",
        "- Anti-leakage: LLM saw training plus internal validation and prior-fold summaries only.",
        "- Hidden until after selection: final OOS and full-window metrics.",
        "- No LLM call is made inside the backtest loop.",
        "",
        "## LLM Choice",
        "",
        f"- Selected: `{choice.selected_label}`",
        f"- Confidence: `{choice.confidence:.2f}`",
        f"- Rationale: {choice.rationale}",
        f"- Expected risks: {', '.join(choice.expected_risks) or 'none'}",
        f"- Rejected labels: {', '.join(choice.rejected_labels) or 'none'}",
        "",
        "## Final Validation After Selection",
        "",
        f"- Quality flags: `{flags}`",
        *_selected_metric_lines("Train", selected.train),
        *_selected_metric_lines("Final OOS", selected.out_of_sample),
        *_selected_metric_lines("Full window", selected.full_window),
        "",
        "## Candidates Visible To LLM",
        "",
        (
            "| Rank | Label | Meta Score | Train Alpha | Validation Alpha | "
            "Fold Avg Alpha | Fold Min Alpha | Positive Folds |"
        ),
        "|---:|---|---:|---:|---:|---:|---:|---:|",
    ]
    for item in reviewed[:24]:
        fold_summary = _fold_summary(item.validation_folds, objective)
        lines.append(
            f"| {item.rank} | `{item.params.label}` | {item.score:.2f} | "
            f"{_objective_alpha(item.train, objective):.2f}% | "
            f"{_objective_alpha(item.validation, objective):.2f}% | "
            f"{fold_summary['avg_objective_alpha_pct']:.2f}% | "
            f"{fold_summary['min_objective_alpha_pct']:.2f}% | "
            f"{fold_summary['positive_alpha_fold_count']}/{fold_summary['fold_count']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _selected_metric_lines(label: str, metrics: RotationMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} Alpha vs equal-weight: `{metrics.alpha_vs_equal_weight_pct:.2f}%`",
        f"- {label} Alpha vs primary: `{metrics.alpha_vs_primary_pct:.2f}%`",
        f"- {label} Sharpe: `{_fmt(metrics.sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} rebalances/trades: `{metrics.rebalances}/{metrics.trades}`",
    ]


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"


def _objective_alpha(metrics: RotationMetrics, objective: RotationObjective) -> float:
    if objective == "primary_alpha":
        return metrics.alpha_vs_primary_pct
    return metrics.alpha_vs_equal_weight_pct


def _objective_label(objective: RotationObjective) -> str:
    if objective == "primary_alpha":
        return "prefer stable Alpha versus primary-symbol buy-and-hold"
    return "prefer stable Alpha versus equal-weight universe buy-and-hold"


def _objective_criterion(objective: RotationObjective) -> str:
    if objective == "primary_alpha":
        return "prefer positive validation alpha versus primary-symbol buy-and-hold"
    return "prefer positive validation alpha versus equal-weight buy-and-hold"
