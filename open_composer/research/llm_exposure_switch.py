from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from open_composer.adapters.data import fetch_ohlcv
from open_composer.config import (
    data_feed,
    default_openai_model,
    ensure_dir,
    openai_api_key,
    openai_base_url,
    project_root,
)
from open_composer.json_utils import json_safe_payload, json_safe_sorted_values
from open_composer.models.strategy_spec import load_strategy_spec
from open_composer.research.exposure_switch import (
    ExposureSwitchCandidate,
    ExposureSwitchMetrics,
    ExposureSwitchParams,
    _backtest_exposure_switch,
    _build_params_grid,
    _filter_time_window,
    _max_warmup,
    _normalize_timestamps,
    _quality_flags,
    _score_candidate,
    _split_index,
    _warmup,
)
from open_composer.research.metadata import (
    frame_data_profile,
    hypothesis_ledger,
    research_brief,
    search_space,
)
from open_composer.storage import write_json


class LLMExposureSwitchChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    selected_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    expected_risks: list[str] = Field(default_factory=list)
    rejected_labels: list[str] = Field(default_factory=list)


@dataclass(frozen=True)
class LLMExposureSwitchCandidate:
    rank: int
    params: ExposureSwitchParams
    train: ExposureSwitchMetrics
    validation: ExposureSwitchMetrics
    validation_folds: list[ExposureSwitchMetrics]
    score: float


@dataclass(frozen=True)
class LLMExposureSwitchResearchResult:
    report_path: Path
    json_path: Path
    prompt_path: Path
    choice: LLMExposureSwitchChoice
    selected: ExposureSwitchCandidate
    reviewed_candidates: list[LLMExposureSwitchCandidate]
    status: Literal[
        "written",
        "codex_local_choice",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
    ]
    status_message: str | None = None


def run_llm_exposure_switch_meta_selection(
    spec_path: Path,
    root: Path | None = None,
    symbol: str | None = None,
    data_source: str = "alpaca",
    feed: str | None = None,
    fast_bars: list[int] | None = None,
    slow_bars: list[int] | None = None,
    momentum_bars: list[int] | None = None,
    min_momentum_pct: list[float] | None = None,
    volatility_bars: list[int] | None = None,
    max_volatility_pct: list[float | None] | None = None,
    drawdown_bars: list[int] | None = None,
    max_drawdown_pct: list[float | None] | None = None,
    base_exposure: list[float] | None = None,
    risk_on_exposure: list[float] | None = None,
    risk_off_exposure: list[float] | None = None,
    financing_rate_pct: list[float] | None = None,
    validation_ratio: float = 0.3,
    validation_folds: int = 3,
    out_of_sample_ratio: float = 0.3,
    max_candidates: int = 200,
    refresh_data: bool = False,
    client: Any | None = None,
    model: str | None = None,
    local_choice: LLMExposureSwitchChoice | None = None,
    start: str | None = None,
    end: str | None = None,
) -> LLMExposureSwitchResearchResult:
    base = root or project_root()
    spec = load_strategy_spec(spec_path)
    selected_symbol = (symbol or spec.primary_symbol).upper()
    selected_feed = feed or spec.data.feed or data_feed()
    frame = fetch_ohlcv(
        root=base,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        start=None,
        end=None,
        source=data_source,
        feed=selected_feed,
        use_cache=not refresh_data,
    )
    frame = _filter_time_window(_normalize_timestamps(frame), start, end)
    if len(frame) < 8:
        raise ValueError("LLM exposure switch meta-selection requires at least 8 bars")
    data_profile = frame_data_profile(
        frame,
        symbol=selected_symbol,
        timeframe=spec.timeframe,
        provider=data_source,
        feed=selected_feed,
        source_mode="cache" if not refresh_data else "live_fetch",
    )

    params_grid = _build_params_grid(
        fast_bars or [3, 5, 8],
        slow_bars or [13, 21, 34],
        momentum_bars or [3, 5, 10],
        min_momentum_pct or [0.0, 5.0],
        volatility_bars or [5, 10],
        max_volatility_pct or [None, 12.0, 18.0],
        drawdown_bars or [5, 10],
        max_drawdown_pct or [None, 18.0, 25.0],
        base_exposure or [1.0],
        risk_on_exposure or [1.25, 1.5],
        risk_off_exposure or [0.0, 0.5, 1.0],
        financing_rate_pct or [5.0, 8.0],
        max_candidates=max_candidates,
    )
    train_end = _split_index(frame, out_of_sample_ratio, _max_warmup(params_grid))
    train_validation_frame = frame.iloc[:train_end].copy().reset_index(drop=True)
    reviewed = _build_reviewed_candidates(
        frame=train_validation_frame,
        timeframe=spec.timeframe,
        params_grid=params_grid,
        validation_ratio=validation_ratio,
        validation_folds=validation_folds,
    )
    prompt = _selection_prompt(spec.name, selected_symbol, spec.timeframe, reviewed)
    prompt_path = base / "reports" / "research" / f"{spec.name}-llm-exposure-switch-prompt.json"
    ensure_dir(prompt_path.parent)
    prompt_path.write_text(
        json.dumps(json_safe_payload(prompt), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    status: Literal[
        "written",
        "codex_local_choice",
        "fallback_no_api_key",
        "fallback_invalid_choice",
        "fallback_api_error",
    ] = "written"
    status_message: str | None = None
    if local_choice is not None:
        choice = local_choice
        labels = {item.params.label for item in reviewed}
        if choice.selected_label not in labels:
            choice = _deterministic_choice(reviewed)
            status = "fallback_invalid_choice"
            status_message = "Local Codex choice selected a label outside the reviewed set"
        else:
            status = "codex_local_choice"
            status_message = (
                "Local Codex/operator supplied a structured choice from the prompt artifact; "
                "no external LLM API call was made"
            )
    elif client is None and not openai_api_key():
        choice = _deterministic_choice(reviewed)
        status = "fallback_no_api_key"
        status_message = "OPENAI_API_KEY is not set"
    else:
        try:
            choice = _call_llm_choice(
                client or _openai_client(), model or default_openai_model(), prompt
            )
            labels = {item.params.label for item in reviewed}
            if choice.selected_label not in labels:
                choice = _deterministic_choice(reviewed)
                status = "fallback_invalid_choice"
                status_message = "LLM selected a label outside the reviewed candidate set"
        except Exception as exc:
            choice = _deterministic_choice(reviewed)
            status = "fallback_api_error"
            status_message = _error_summary(exc)

    selected_params = _params_by_label(reviewed)[choice.selected_label]
    selected = _selected_candidate(
        frame=frame,
        timeframe=spec.timeframe,
        params=selected_params,
        train_end=train_end,
    )
    json_path = base / "reports" / "research" / f"{spec.name}-llm-exposure-switch.json"
    report_path = base / "reports" / "research" / f"{spec.name}-llm-exposure-switch.md"
    _write_selection_json(
        json_path,
        spec.name,
        selected_symbol,
        spec.timeframe,
        data_profile,
        params_grid,
        reviewed,
        choice,
        selected,
        status,
        status_message,
        prompt_path,
        start,
        end,
    )
    _write_selection_report(
        report_path,
        json_path,
        prompt_path,
        spec.name,
        selected_symbol,
        spec.timeframe,
        data_profile,
        params_grid,
        reviewed,
        choice,
        selected,
        status,
        status_message,
        start,
        end,
    )
    return LLMExposureSwitchResearchResult(
        report_path=report_path,
        json_path=json_path,
        prompt_path=prompt_path,
        choice=choice,
        selected=selected,
        reviewed_candidates=reviewed,
        status=status,
        status_message=status_message,
    )


def _build_reviewed_candidates(
    *,
    frame: Any,
    timeframe: str,
    params_grid: list[ExposureSwitchParams],
    validation_ratio: float,
    validation_folds: int,
) -> list[LLMExposureSwitchCandidate]:
    split = _split_index(frame, validation_ratio, _max_warmup(params_grid))
    rows: list[LLMExposureSwitchCandidate] = []
    for params in params_grid:
        train_frame = frame.iloc[:split].copy().reset_index(drop=True)
        validation_start = max(0, split - _warmup(params) - 1)
        validation = _backtest_exposure_switch(
            frame.iloc[validation_start:].copy().reset_index(drop=True),
            timeframe,
            params,
            evaluation_start_index=split - validation_start,
        )
        train = _backtest_exposure_switch(train_frame, timeframe, params)
        folds = _validation_fold_metrics(
            frame=frame,
            timeframe=timeframe,
            params=params,
            folds=validation_folds,
            fold_size=_validation_fold_size(frame, params_grid, validation_folds),
        )
        rows.append(
            LLMExposureSwitchCandidate(
                rank=0,
                params=params,
                train=train,
                validation=validation,
                validation_folds=folds,
                score=_meta_score(train, validation, folds),
            )
        )
    rows.sort(key=lambda item: item.score, reverse=True)
    return [
        LLMExposureSwitchCandidate(
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
    params_grid: list[ExposureSwitchParams],
    validation_folds: int,
) -> int:
    return max((len(frame) - _max_warmup(params_grid)) // (max(validation_folds, 1) + 1), 2)


def _validation_fold_metrics(
    *,
    frame: Any,
    timeframe: str,
    params: ExposureSwitchParams,
    folds: int,
    fold_size: int,
) -> list[ExposureSwitchMetrics]:
    rows: list[ExposureSwitchMetrics] = []
    for fold in range(1, max(folds, 1) + 1):
        test_start = _warmup(params) + fold * fold_size
        test_end = min(len(frame), test_start + fold_size)
        if test_end - test_start < 2:
            continue
        warm_start = max(0, test_start - _warmup(params) - 1)
        rows.append(
            _backtest_exposure_switch(
                frame.iloc[warm_start:test_end].copy().reset_index(drop=True),
                timeframe,
                params,
                evaluation_start_index=test_start - warm_start,
            )
        )
    return rows


def _meta_score(
    train: ExposureSwitchMetrics,
    validation: ExposureSwitchMetrics,
    validation_folds: list[ExposureSwitchMetrics],
) -> float:
    train_score = _score_candidate(train)
    validation_score = _score_candidate(validation)
    stability_penalty = abs(train.alpha_vs_buy_hold_pct - validation.alpha_vs_buy_hold_pct)
    fold_summary = _fold_summary(validation_folds)
    validation_sharpe = validation.sharpe_ratio or 0.0
    validation_buy_hold_sharpe = validation.buy_hold_sharpe_ratio or 0.0
    return (
        min(train_score, validation_score) * 0.7
        + validation.alpha_vs_buy_hold_pct * 0.6
        + fold_summary["avg_alpha_vs_buy_hold_pct"] * 0.7
        + fold_summary["min_alpha_vs_buy_hold_pct"] * 0.8
        + fold_summary["positive_alpha_fold_count"] * 15
        + validation_sharpe * 8
        + (validation_sharpe - validation_buy_hold_sharpe) * 12
        + fold_summary["avg_sharpe_ratio"] * 5
        - stability_penalty * 0.2
        - abs(min(validation.max_drawdown_pct, 0.0)) * 0.2
        - abs(min(fold_summary["worst_max_drawdown_pct"], 0.0)) * 0.15
    )


def _selection_prompt(
    strategy_name: str,
    symbol: str,
    timeframe: str,
    reviewed: list[LLMExposureSwitchCandidate],
    limit: int = 24,
) -> dict[str, Any]:
    return {
        "task": (
            "Select one point-in-time dynamic exposure method from training-only evidence. "
            "Do not assume access to final out-of-sample returns."
        ),
        "strategy_name": strategy_name,
        "symbol": symbol,
        "timeframe": timeframe,
        "available_evidence": (
            "training window plus internal validation and prior validation folds only"
        ),
        "hidden_from_model": "final out-of-sample and full-window metrics",
        "selection_objective": (
            "prefer stable Alpha versus unlevered buy-and-hold with Sharpe no worse than "
            "buy-and-hold and controlled drawdown"
        ),
        "selection_criteria": [
            "prefer positive validation Alpha versus buy-and-hold",
            "prefer positive Alpha across all prior validation folds",
            "prefer validation Sharpe above buy-and-hold Sharpe",
            "penalize drawdown expansion versus buy-and-hold",
            "penalize high train/validation instability",
            "do not chase the highest training score alone",
            "treat high leverage as useful only when validation evidence supports it",
        ],
        "candidates": [_candidate_summary(item) for item in reviewed[:limit]],
        "required_json_schema": LLMExposureSwitchChoice.model_json_schema(),
    }


def _candidate_summary(item: LLMExposureSwitchCandidate) -> dict[str, Any]:
    return {
        "rank": item.rank,
        "label": item.params.label,
        "params": item.params.__dict__,
        "meta_score": item.score,
        "train": _metrics_summary(item.train),
        "validation": _metrics_summary(item.validation),
        "validation_fold_summary": _fold_summary(item.validation_folds),
        "validation_folds": [_metrics_summary(metric) for metric in item.validation_folds],
    }


def _metrics_summary(metrics: ExposureSwitchMetrics) -> dict[str, Any]:
    return {
        "bars": metrics.bars,
        "return_pct": metrics.total_return_pct,
        "buy_hold_return_pct": metrics.buy_hold_return_pct,
        "alpha_vs_buy_hold_pct": metrics.alpha_vs_buy_hold_pct,
        "sharpe_ratio": metrics.sharpe_ratio,
        "buy_hold_sharpe_ratio": metrics.buy_hold_sharpe_ratio,
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "buy_hold_max_drawdown_pct": metrics.buy_hold_max_drawdown_pct,
        "average_exposure": metrics.average_exposure,
        "max_exposure": metrics.max_exposure,
        "exposure_changes": metrics.exposure_changes,
        "financing_cost_pct": metrics.financing_cost_pct,
    }


def _fold_summary(metrics: list[ExposureSwitchMetrics]) -> dict[str, Any]:
    if not metrics:
        return {
            "fold_count": 0,
            "positive_alpha_fold_count": 0,
            "avg_alpha_vs_buy_hold_pct": 0.0,
            "min_alpha_vs_buy_hold_pct": 0.0,
            "avg_sharpe_ratio": 0.0,
            "avg_relative_sharpe_ratio": 0.0,
            "worst_max_drawdown_pct": 0.0,
        }
    alpha_values = [item.alpha_vs_buy_hold_pct for item in metrics]
    sharpe_values = [item.sharpe_ratio or 0.0 for item in metrics]
    relative_sharpe_values = [
        (item.sharpe_ratio or 0.0) - (item.buy_hold_sharpe_ratio or 0.0) for item in metrics
    ]
    drawdowns = [item.max_drawdown_pct for item in metrics]
    return {
        "fold_count": len(metrics),
        "positive_alpha_fold_count": sum(value > 0 for value in alpha_values),
        "avg_alpha_vs_buy_hold_pct": mean(alpha_values),
        "min_alpha_vs_buy_hold_pct": min(alpha_values),
        "avg_sharpe_ratio": mean(sharpe_values),
        "avg_relative_sharpe_ratio": mean(relative_sharpe_values),
        "worst_max_drawdown_pct": min(drawdowns),
    }


def _openai_client() -> Any:
    from openai import OpenAI

    return OpenAI(api_key=openai_api_key(), base_url=openai_base_url())


def _call_llm_choice(client: Any, model: str, prompt: dict[str, Any]) -> LLMExposureSwitchChoice:
    messages = [
        {
            "role": "system",
            "content": (
                "You choose one trading research candidate from training-only evidence. "
                "Return schema-valid JSON. Do not claim live trading certainty."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(json_safe_payload(prompt), indent=2, sort_keys=True),
        },
    ]
    try:
        response = client.responses.parse(
            model=model,
            input=messages,
            text_format=LLMExposureSwitchChoice,
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
                    "name": "llm_exposure_switch_choice",
                    "strict": True,
                    "schema": LLMExposureSwitchChoice.model_json_schema(),
                }
            },
        )
        return LLMExposureSwitchChoice.model_validate_json(response.output_text)
    raise ValueError("LLM returned no schema-valid exposure-switch choice")


def _extract_choice(response: Any) -> LLMExposureSwitchChoice | None:
    for output in getattr(response, "output", []):
        if getattr(output, "type", None) != "message":
            continue
        for item in getattr(output, "content", []):
            parsed = getattr(item, "parsed", None)
            if isinstance(parsed, LLMExposureSwitchChoice):
                return parsed
            if isinstance(parsed, dict):
                return LLMExposureSwitchChoice.model_validate(parsed)
    parsed = getattr(response, "parsed", None)
    if isinstance(parsed, LLMExposureSwitchChoice):
        return parsed
    if isinstance(parsed, dict):
        return LLMExposureSwitchChoice.model_validate(parsed)
    return None


def _deterministic_choice(reviewed: list[LLMExposureSwitchCandidate]) -> LLMExposureSwitchChoice:
    selected = reviewed[0]
    return LLMExposureSwitchChoice(
        selected_label=selected.params.label,
        confidence=0.0,
        rationale="Fallback selected the highest training-only meta score.",
        expected_risks=["No usable LLM response; deterministic fallback used."],
        rejected_labels=[item.params.label for item in reviewed[1:4]],
    )


def _error_summary(exc: Exception) -> str:
    status_code = getattr(exc, "status_code", None)
    status = f" status={status_code}" if status_code is not None else ""
    return f"{type(exc).__name__}{status}: {str(exc)[:500]}"


def _params_by_label(
    reviewed: list[LLMExposureSwitchCandidate],
) -> dict[str, ExposureSwitchParams]:
    return {item.params.label: item.params for item in reviewed}


def _llm_contribution(
    status: str,
    choice: LLMExposureSwitchChoice,
    selected: ExposureSwitchCandidate,
    reviewed: list[LLMExposureSwitchCandidate],
) -> dict[str, Any]:
    top = reviewed[0]
    visible = next((item for item in reviewed if item.params.label == selected.params.label), None)
    distinctiveness = _strategy_distinctiveness(selected, top, visible)
    external_api_called = status == "written"
    contribution_ok = external_api_called and distinctiveness["strategy_distinctiveness_ok"]
    counterevidence: list[str] = []
    if not external_api_called:
        counterevidence.append("external_llm_api_not_called")
    if not distinctiveness["strategy_distinctiveness_ok"]:
        counterevidence.append("selected_candidate_not_distinct_from_deterministic_top")
    if selected.full_window.exposure_changes < 1:
        counterevidence.append("selected_exposure_path_has_no_switches")
    level = "independent_llm_selection_signal" if contribution_ok else "llm_assisted_selection_only"
    label = (
        "Independent LLM contribution demonstrated by an external schema-valid choice that differs "
        "from the deterministic top-ranked candidate."
        if contribution_ok
        else (
            "LLM-assisted selection workflow only; no independent LLM Alpha contribution is "
            "demonstrated."
        )
    )
    return {
        "llm_contribution_ok": contribution_ok,
        "llm_contribution_level": level,
        "llm_contribution_label": label,
        "external_api_called": external_api_called,
        "status": status,
        "selected_label": selected.params.label,
        "deterministic_top_label": top.params.label,
        "choice_confidence": choice.confidence,
        "strategy_distinctiveness": distinctiveness,
        "counterevidence": counterevidence,
    }


def _strategy_distinctiveness(
    selected: ExposureSwitchCandidate,
    top: LLMExposureSwitchCandidate,
    visible: LLMExposureSwitchCandidate | None,
) -> dict[str, Any]:
    selected_rank = visible.rank if visible is not None else None
    params_differ = selected.params != top.params
    rank_gap = (selected_rank - top.rank) if selected_rank is not None else None
    visible_score_gap = (top.score - visible.score) if visible is not None else None
    return {
        "strategy_distinctiveness_ok": bool(params_differ and selected_rank is not None),
        "selected_label": selected.params.label,
        "deterministic_top_label": top.params.label,
        "selected_prompt_rank": selected_rank,
        "deterministic_top_rank": top.rank,
        "rank_gap_vs_top": rank_gap,
        "params_differ_from_deterministic_top": params_differ,
        "visible_meta_score_gap_vs_top": visible_score_gap,
        "selected_exposure_changes": selected.full_window.exposure_changes,
    }


def _params_grid_ranges(params_grid: list[ExposureSwitchParams]) -> dict[str, list[Any]]:
    keys = [
        "fast_bars",
        "slow_bars",
        "momentum_bars",
        "min_momentum_pct",
        "volatility_bars",
        "max_volatility_pct",
        "drawdown_bars",
        "max_drawdown_pct",
        "base_exposure",
        "risk_on_exposure",
        "risk_off_exposure",
        "financing_rate_pct",
    ]
    return {
        key: json_safe_sorted_values({getattr(params, key) for params in params_grid})
        for key in keys
    }


def _selected_candidate(
    *,
    frame: Any,
    timeframe: str,
    params: ExposureSwitchParams,
    train_end: int,
) -> ExposureSwitchCandidate:
    train_frame = frame.iloc[:train_end].copy().reset_index(drop=True)
    oos_start = max(0, train_end - _warmup(params) - 1)
    oos_frame = frame.iloc[oos_start:].copy().reset_index(drop=True)
    train = _backtest_exposure_switch(train_frame, timeframe, params)
    oos = _backtest_exposure_switch(
        oos_frame,
        timeframe,
        params,
        evaluation_start_index=train_end - oos_start,
    )
    full = _backtest_exposure_switch(frame, timeframe, params)
    return ExposureSwitchCandidate(
        rank=1,
        params=params,
        score=_score_candidate(train),
        train=train,
        out_of_sample=oos,
        full_window=full,
        quality_flags=_quality_flags(train, oos, full),
    )


def _acceptance_gate(
    selected: ExposureSwitchCandidate,
    reviewed: list[LLMExposureSwitchCandidate],
    status: str,
    status_message: str | None,
    contribution: dict[str, Any],
) -> dict[str, Any]:
    visible = next(
        (item for item in reviewed if item.params.label == selected.params.label),
        None,
    )
    fold_summary = _fold_summary(visible.validation_folds if visible is not None else [])
    passed = (
        status in {"written", "codex_local_choice"}
        and selected.out_of_sample.alpha_vs_buy_hold_pct > 0
        and (selected.out_of_sample.sharpe_ratio or 0.0) >= 0.5
        and (
            selected.out_of_sample.buy_hold_sharpe_ratio is None
            or (selected.out_of_sample.sharpe_ratio or 0.0)
            >= selected.out_of_sample.buy_hold_sharpe_ratio
        )
        and fold_summary["fold_count"] > 0
        and fold_summary["positive_alpha_fold_count"] == fold_summary["fold_count"]
        and not {
            "oos_drawdown_expansion",
            "full_window_drawdown_expansion",
            "single_exposure_path",
        }.intersection(selected.quality_flags)
    )
    return {
        "passed": passed,
        "objective": "llm_selected_dynamic_exposure_alpha_vs_unlevered_buy_hold",
        "llm_status": status,
        "llm_status_message": status_message,
        "llm_contribution_ok": contribution["llm_contribution_ok"],
        "llm_contribution_level": contribution["llm_contribution_level"],
        "strategy_distinctiveness_ok": contribution["strategy_distinctiveness"][
            "strategy_distinctiveness_ok"
        ],
        "oos_alpha_vs_buy_hold_pct": selected.out_of_sample.alpha_vs_buy_hold_pct,
        "oos_sharpe_ratio": selected.out_of_sample.sharpe_ratio,
        "oos_buy_hold_sharpe_ratio": selected.out_of_sample.buy_hold_sharpe_ratio,
        "oos_max_drawdown_pct": selected.out_of_sample.max_drawdown_pct,
        "oos_buy_hold_max_drawdown_pct": selected.out_of_sample.buy_hold_max_drawdown_pct,
        "visible_validation_positive_alpha_folds": fold_summary["positive_alpha_fold_count"],
        "visible_validation_fold_count": fold_summary["fold_count"],
        "quality_flags": selected.quality_flags,
    }


def _write_selection_json(
    path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    data_profile: dict[str, Any],
    params_grid: list[ExposureSwitchParams],
    reviewed: list[LLMExposureSwitchCandidate],
    choice: LLMExposureSwitchChoice,
    selected: ExposureSwitchCandidate,
    status: str,
    status_message: str | None,
    prompt_path: Path,
    start: str | None,
    end: str | None,
) -> Path:
    contribution = _llm_contribution(status, choice, selected, reviewed)
    payload = {
        "strategy_name": strategy_name,
        "mode": "llm_exposure_switch_meta_selection",
        "status": status,
        "status_message": status_message,
        "symbol": symbol,
        "timeframe": timeframe,
        "prompt_path": str(prompt_path),
        "research_window": {"start": start, "end": end},
        "data_profile": data_profile,
        "research_brief": research_brief(
            strategy_name=strategy_name,
            objective="LLM selects from training-only dynamic exposure candidates",
            hypothesis=(
                "A model/operator can improve candidate selection discipline from hidden-OOS-safe "
                "training and validation summaries, but this alone is not independent LLM Alpha."
            ),
            constraints=[
                "No final OOS or full-window metrics are visible before selection.",
                "No LLM call is made inside the backtest loop.",
                "Fallback or local choices do not prove external LLM Alpha contribution.",
            ],
        ),
        "search_space": search_space(
            family="dynamic_exposure_switch",
            candidate_count=len(params_grid),
            parameter_ranges=_params_grid_ranges(params_grid),
            filters=["valid exposure ordering", "non-negative financing", "fast_bars < slow_bars"],
        ),
        "hypothesis_ledger": hypothesis_ledger(
            hypothesis=(
                "LLM-assisted selection creates distinct Alpha beyond pure parameter ranking."
            ),
            visible_evidence=[
                "training metrics",
                "internal validation metrics",
                "prior validation fold summaries",
                "structured rationale and rejected labels",
            ],
            hidden_evidence=["final out-of-sample metrics", "full-window metrics"],
            counterevidence=contribution["counterevidence"],
            conclusion=contribution["llm_contribution_label"],
        ),
        "selection_objective": (
            "LLM selects one dynamic exposure method from training-only evidence; "
            "final OOS/full-window metrics are computed only after selection"
        ),
        "acceptance_gate": _acceptance_gate(
            selected,
            reviewed,
            status,
            status_message,
            contribution,
        ),
        "llm_contribution": contribution,
        "anti_leakage": {
            "llm_visible_metrics": (
                "training plus internal validation and prior validation folds only"
            ),
            "llm_hidden_metrics": "final out-of-sample and full-window metrics",
            "llm_called_inside_backtest_loop": False,
            "external_api_called": status == "written",
            "signal_timing": (
                "exposure for each bar uses indicators available at the previous bar close; "
                "fill is current bar open"
            ),
        },
        "choice": choice.model_dump(mode="json"),
        "selected": {
            "params": selected.params.__dict__,
            "score": selected.score,
            "quality_flags": selected.quality_flags,
            "train": selected.train.__dict__,
            "out_of_sample": selected.out_of_sample.__dict__,
            "full_window": selected.full_window.__dict__,
        },
        "reviewed_candidates": [_candidate_summary(item) for item in reviewed],
    }
    return write_json(path, payload)


def _write_selection_report(
    path: Path,
    json_path: Path,
    prompt_path: Path,
    strategy_name: str,
    symbol: str,
    timeframe: str,
    data_profile: dict[str, Any],
    params_grid: list[ExposureSwitchParams],
    reviewed: list[LLMExposureSwitchCandidate],
    choice: LLMExposureSwitchChoice,
    selected: ExposureSwitchCandidate,
    status: str,
    status_message: str | None,
    start: str | None,
    end: str | None,
) -> Path:
    ensure_dir(path.parent)
    flags = ", ".join(selected.quality_flags) if selected.quality_flags else "none"
    contribution = _llm_contribution(status, choice, selected, reviewed)
    gate = _acceptance_gate(selected, reviewed, status, status_message, contribution)
    lines = [
        f"# LLM Exposure Switch Meta-Selection: {strategy_name}",
        "",
        f"- JSON report: `{json_path}`",
        f"- Prompt artifact: `{prompt_path}`",
        f"- Status: `{status}`",
        f"- Status message: `{status_message or 'none'}`",
        f"- Symbol: `{symbol}`",
        f"- Timeframe: `{timeframe}`",
        f"- Research window: `{start or 'cache start'}` -> `{end or 'cache end'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Data source/feed: `{data_profile.get('provider') or 'unknown'}` / "
        f"`{data_profile.get('feed') or 'unknown'}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        "- Mode: `llm_exposure_switch_meta_selection`",
        "- Anti-leakage: LLM saw training plus internal validation and prior-fold summaries only.",
        "- Hidden until after selection: final OOS and full-window metrics.",
        "- No LLM call is made inside the backtest loop.",
        f"- Search space candidates: `{len(params_grid)}`",
        "",
        "## Acceptance Gate",
        "",
        *[f"- {key}: `{value}`" for key, value in gate.items()],
        "",
        "## LLM Choice",
        "",
        f"- Selected: `{choice.selected_label}`",
        f"- Confidence: `{choice.confidence:.2f}`",
        f"- Rationale: {choice.rationale}",
        f"- Expected risks: {', '.join(choice.expected_risks) or 'none'}",
        f"- Rejected labels: {', '.join(choice.rejected_labels) or 'none'}",
        "",
        "## LLM Contribution",
        "",
        f"- Contribution OK: `{contribution['llm_contribution_ok']}`",
        f"- Level: `{contribution['llm_contribution_level']}`",
        f"- Label: {contribution['llm_contribution_label']}",
        (
            "- Strategy distinctiveness OK: "
            f"`{contribution['strategy_distinctiveness']['strategy_distinctiveness_ok']}`"
        ),
        (
            "- Selected rank gap versus deterministic top: "
            f"`{contribution['strategy_distinctiveness']['rank_gap_vs_top']}`"
        ),
        *[f"- Counterevidence: {item}" for item in contribution["counterevidence"]],
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
        fold_summary = _fold_summary(item.validation_folds)
        lines.append(
            f"| {item.rank} | `{item.params.label}` | {item.score:.2f} | "
            f"{item.train.alpha_vs_buy_hold_pct:.2f}% | "
            f"{item.validation.alpha_vs_buy_hold_pct:.2f}% | "
            f"{fold_summary['avg_alpha_vs_buy_hold_pct']:.2f}% | "
            f"{fold_summary['min_alpha_vs_buy_hold_pct']:.2f}% | "
            f"{fold_summary['positive_alpha_fold_count']}/{fold_summary['fold_count']} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _selected_metric_lines(label: str, metrics: ExposureSwitchMetrics) -> list[str]:
    return [
        f"- {label} return: `{metrics.total_return_pct:.2f}%`",
        f"- {label} buy-hold: `{metrics.buy_hold_return_pct:.2f}%`",
        f"- {label} Alpha vs buy-hold: `{metrics.alpha_vs_buy_hold_pct:.2f}%`",
        f"- {label} Sharpe: `{_fmt(metrics.sharpe_ratio)}`",
        f"- {label} buy-hold Sharpe: `{_fmt(metrics.buy_hold_sharpe_ratio)}`",
        f"- {label} max drawdown: `{metrics.max_drawdown_pct:.2f}%`",
        f"- {label} buy-hold max drawdown: `{metrics.buy_hold_max_drawdown_pct:.2f}%`",
        f"- {label} average exposure: `{metrics.average_exposure:.2f}`",
        f"- {label} max exposure: `{metrics.max_exposure:.2f}`",
        f"- {label} exposure changes: `{metrics.exposure_changes}`",
        f"- {label} financing cost: `{metrics.financing_cost_pct:.2f}%`",
    ]


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}"
