from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from itertools import product
from math import log, prod, sqrt
from pathlib import Path
from statistics import fmean, pstdev
from time import perf_counter
from typing import Any

import yaml

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.analytics.data_sanity import MIN_SIGNALS, MIN_TRADES
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.experiments import append_experiment_run, artifact_ref
from open_composer.expressions import validate_expression
from open_composer.json_utils import json_safe_payload
from open_composer.models.experiment import ExperimentRun, ExperimentTrial, ResearchMode
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.kernel import ResearchArtifactWriter
from open_composer.research.kernel.candidates import CandidateScore, CandidateSet, CandidateSpec
from open_composer.research.kernel.trials import TrialLedger, TrialRecord
from open_composer.research.kernel.workflow import ResearchRunIndexRecord
from open_composer.research.metadata import (
    frame_data_profile,
    research_run_manifest,
    runtime_payload,
    search_space,
    workspace_relative_path,
)
from open_composer.research.optimizer import _score_candidate
from open_composer.research.optimizers.random_search import select_random_combinations
from open_composer.research.research_brief import ensure_research_brief_for_sweep
from open_composer.research.search_policy import ObjectiveSet, SearchPolicy
from open_composer.strategy_versions import strategy_content_hash

ALLOWED_SWEEP_ROOTS = {"entry", "exit", "risk", "costs", "factors"}


@dataclass
class SweepCandidateResult:
    rank: int
    spec: StrategySpec
    params: dict[str, Any]
    artifacts: BacktestArtifacts
    score: float
    spec_path: Path | None = None
    stability: dict[str, Any] = field(default_factory=dict)


@dataclass
class ParameterSweepResult:
    report_path: Path
    json_path: Path
    candidates: list[SweepCandidateResult]
    written_specs: list[Path]

    @property
    def best(self) -> SweepCandidateResult:
        return self.candidates[0]


def parse_sweep_parameters(items: list[str]) -> dict[str, list[str]]:
    """Parse repeated PATH=value1,value2 or PATH=value1|value2 sweep arguments."""
    parameters: dict[str, list[str]] = {}
    for item in items:
        path, separator, raw_values = item.partition("=")
        if not separator:
            msg = f"sweep parameter must be PATH=values: {item}"
            raise ValueError(msg)
        path = path.strip()
        if not path:
            msg = f"sweep parameter path is empty: {item}"
            raise ValueError(msg)
        values = _split_values(raw_values)
        if not values:
            msg = f"sweep parameter has no values: {item}"
            raise ValueError(msg)
        if path in parameters:
            msg = f"duplicate sweep parameter path: {path}"
            raise ValueError(msg)
        parameters[path] = values
    return parameters


def run_parameter_sweep(
    spec_path: Path,
    parameters: dict[str, list[str]],
    root: Path | None = None,
    min_return_pct: float = 0.0,
    min_signals: int = 1,
    min_sharpe: float = 0.0,
    max_candidates: int = 200,
    top_n: int = 10,
    write_top: int = 1,
    search_strategy: str = "grid",
    random_seed: int | None = None,
    research_mode: ResearchMode = "audited",
) -> ParameterSweepResult:
    started_at = perf_counter()
    base = root or project_root()
    writer = ResearchArtifactWriter(base)
    source = load_strategy_spec(spec_path)
    if not parameters:
        msg = "parameter sweep requires at least one parameter"
        raise ValueError(msg)
    if max_candidates < 1:
        msg = "--max-candidates must be at least 1"
        raise ValueError(msg)
    total_candidates = prod(len(values) for values in parameters.values())
    if search_strategy not in {"grid", "random"}:
        msg = "--search-strategy must be one of: grid, random"
        raise ValueError(msg)
    search_policy = SearchPolicy(
        strategy=search_strategy,  # type: ignore[arg-type]
        candidate_budget=max_candidates,
        random_seed=random_seed,
        objective_set=ObjectiveSet(
            primary_metric="score",
            secondary_metrics=["total_return_pct", "sharpe_ratio", "signals"],
            constraints={
                "min_return_pct": min_return_pct,
                "min_signals": min_signals,
                "min_sharpe": min_sharpe,
            },
        ),
    )
    search_policy.validate()
    _validate_sweep_paths(source, parameters)
    if search_strategy == "grid" and total_candidates > max_candidates:
        msg = (
            f"parameter sweep would create {total_candidates} candidates; "
            f"raise --max-candidates above {total_candidates} or narrow the grid"
        )
        raise ValueError(msg)
    planned_candidates = (
        total_candidates if search_strategy == "grid" else min(total_candidates, max_candidates)
    )
    brief_validation = ensure_research_brief_for_sweep(
        spec_path,
        _planned_parameter_budget(parameters, planned_candidates),
        base,
    )

    frame = load_ohlcv_for_spec(source, base)
    data_profile = frame_data_profile(
        frame,
        symbol=source.primary_symbol,
        timeframe=source.timeframe,
        provider=source.data.source,
        feed=source.data.feed,
        source_mode=frame.attrs.get("data_source_mode") or source.data.source,
        path=frame.attrs.get("data_source_path") or source.data.path,
    )
    candidate_results: list[SweepCandidateResult] = []
    selected_params = _select_parameter_combinations(
        parameters,
        search_strategy=search_strategy,
        max_candidates=max_candidates,
        random_seed=random_seed,
    )
    for index, params in enumerate(selected_params, start=1):
        candidate, applied = _candidate_from_params(source, params, index, base)
        artifacts = backtest_frame(
            candidate,
            frame,
            root=base,
            run_id_value=f"sweep-{candidate.name}",
        )
        score = _score_candidate(artifacts, min_return_pct, min_signals, min_sharpe)
        candidate_results.append(
            SweepCandidateResult(
                rank=0,
                spec=candidate,
                params=applied,
                artifacts=artifacts,
                score=score,
            )
        )

    candidate_results.sort(key=lambda item: item.score, reverse=True)
    for rank, candidate in enumerate(candidate_results, start=1):
        candidate.rank = rank
    sweep_analysis = _sweep_analysis(
        candidate_results,
        parameters,
        min_return_pct,
        min_signals,
        min_sharpe,
    )
    runtime = runtime_payload(started_at, {})
    search_space_payload = search_space(
        family="parameter_sweep",
        candidate_count=len(candidate_results),
        parameter_ranges=parameters,
        filters=[
            f"min_return_pct={min_return_pct}",
            f"min_signals={min_signals}",
            f"min_sharpe={min_sharpe}",
            f"search_strategy={search_strategy}",
            f"search_budget={brief_validation.payload.get('search_budget')}",
        ],
    )
    manifest = research_run_manifest(
        root=base,
        strategy=source,
        source_path=spec_path,
        trial_count=len(candidate_results),
        search_space_payload=search_space_payload,
        data_profile=data_profile,
        runtime=runtime,
    )

    written_specs = _write_top_specs(base, candidate_results, write_top)
    report_path = base / "reports" / "research" / f"{source.name}-parameter-sweep.md"
    json_path = base / "reports" / "research" / f"{source.name}-parameter-sweep.json"
    ledger = _trial_ledger(
        source,
        candidate_results,
        max_candidates,
        search_strategy=search_strategy,
        random_seed=random_seed,
    )
    candidate_set = _candidate_set(source, spec_path, candidate_results)
    selection_decision = _selection_decision(candidate_results)
    index_record = ResearchRunIndexRecord(
        run_id=f"parameter-sweep-{source.name}-{strategy_content_hash(source)[:12]}",
        strategy_name=source.name,
        source_spec_path=workspace_relative_path(spec_path, base),
        spec_hash=strategy_content_hash(source),
        status="warning",
        kind="parameter_sweep",
        data_profile=data_profile,
        candidate_count=len(candidate_results),
        trial_count=len(candidate_results),
        runtime_seconds=runtime.get("total"),
        gate_status="warning",
        blocked_items=[],
        warning_items=["in_sample_only", "requires_oos_walk_forward_cost_and_benchmark_review"],
        report_path=workspace_relative_path(report_path, base),
        json_path=workspace_relative_path(json_path, base),
        source_artifacts={
            "trial_ledger": workspace_relative_path(json_path, base),
            "research_brief": workspace_relative_path(brief_validation.path, base),
        },
    )
    _write_sweep_json(
        json_path,
        source,
        candidate_results,
        parameters,
        min_return_pct,
        min_signals,
        min_sharpe,
        max_candidates,
        written_specs,
        data_profile,
        search_space_payload,
        sweep_analysis,
        manifest,
        ledger,
        candidate_set,
        selection_decision,
        index_record,
        search_strategy,
        random_seed,
        brief_validation.payload,
        search_policy,
        research_mode,
    )
    writer.append_index(index_record)
    _append_parameter_sweep_experiment(
        root=base,
        source=source,
        spec_path=spec_path,
        report_path=report_path,
        json_path=json_path,
        candidates=candidate_results,
        search_policy=search_policy,
        research_mode=research_mode,
        data_profile=data_profile,
        index_record=index_record,
    )
    _write_sweep_report(
        report_path,
        source,
        candidate_results,
        parameters,
        min_return_pct,
        min_signals,
        min_sharpe,
        max_candidates,
        top_n,
        written_specs,
        json_path,
        data_profile,
        search_space_payload,
        sweep_analysis,
        search_strategy,
    )
    return ParameterSweepResult(
        report_path=report_path,
        json_path=json_path,
        candidates=candidate_results,
        written_specs=written_specs,
    )


def _split_values(raw_values: str) -> list[str]:
    separator = "|" if "|" in raw_values else ","
    return [value.strip() for value in raw_values.split(separator) if value.strip()]


def _parameter_combinations(parameters: dict[str, list[str]]) -> list[dict[str, str]]:
    paths = list(parameters)
    return [
        dict(zip(paths, values, strict=True))
        for values in product(*(parameters[path] for path in paths))
    ]


def _select_parameter_combinations(
    parameters: dict[str, list[str]],
    *,
    search_strategy: str,
    max_candidates: int,
    random_seed: int | None,
) -> list[dict[str, str]]:
    combinations = _parameter_combinations(parameters)
    if search_strategy == "grid":
        return combinations
    return select_random_combinations(
        combinations,
        max_candidates=max_candidates,
        seed=random_seed,
    )


def _planned_parameter_budget(
    parameters: dict[str, list[str]],
    planned_candidates: int,
) -> dict[str, list[str]]:
    if len(parameters) <= 1:
        return parameters
    return {"candidate_sample": [str(index) for index in range(planned_candidates)]}


def _validate_sweep_paths(source: StrategySpec, parameters: dict[str, list[str]]) -> None:
    raw = source.model_dump(mode="json")
    for path, values in parameters.items():
        if not values:
            msg = f"sweep parameter has no values: {path}"
            raise ValueError(msg)
        _set_sweep_path(raw, path, values[0])


def _candidate_from_params(
    source: StrategySpec,
    params: dict[str, str],
    index: int,
    root: Path,
) -> tuple[StrategySpec, dict[str, Any]]:
    raw = copy.deepcopy(source.model_dump(mode="json"))
    applied: dict[str, Any] = {}
    for path, raw_value in params.items():
        applied[path] = _set_sweep_path(raw, path, raw_value)

    raw["name"] = f"{source.name}_sweep_{index:03d}"
    raw["description"] = f"{source.description} Parameter sweep candidate {index}."
    raw["lifecycle"] = "draft"
    raw["execution"] = {
        **raw["execution"],
        "mode": "manual_signal",
        "broker": "none",
    }
    raw["notes"] = {
        **raw.get("notes", {}),
        "parameter_sweep": {
            "source_strategy": source.name,
            "candidate_index": index,
            "params": applied,
            "promotion_note": (
                "In-sample sweep result only; require out-of-sample, walk-forward, "
                "cost sensitivity, and data-source comparison before paper promotion."
            ),
        },
    }
    candidate = StrategySpec.model_validate(raw)
    _validate_candidate_expressions(candidate, root)
    return candidate, applied


def _set_sweep_path(raw: dict[str, Any], path: str, raw_value: str) -> Any:
    parts = path.split(".")
    if not parts or parts[0] not in ALLOWED_SWEEP_ROOTS:
        allowed = ", ".join(sorted(ALLOWED_SWEEP_ROOTS))
        msg = f"unsupported sweep path {path!r}; allowed roots: {allowed}"
        raise ValueError(msg)

    target: Any = raw
    for part in parts[:-1]:
        target = _path_child(target, part, path)

    final = parts[-1]
    if isinstance(target, list):
        index = _path_index(final, path)
        if index >= len(target):
            msg = f"list index out of range in sweep path: {path}"
            raise ValueError(msg)
        current = target[index]
        value = _coerce_value(raw_value, current)
        target[index] = value
        return value
    if isinstance(target, dict):
        if final not in target:
            msg = f"unknown sweep path: {path}"
            raise ValueError(msg)
        current = target[final]
        value = _coerce_value(raw_value, current)
        target[final] = value
        return value
    msg = f"cannot set sweep path on non-container: {path}"
    raise ValueError(msg)


def _path_child(target: Any, part: str, path: str) -> Any:
    if isinstance(target, list):
        index = _path_index(part, path)
        if index >= len(target):
            msg = f"list index out of range in sweep path: {path}"
            raise ValueError(msg)
        return target[index]
    if isinstance(target, dict):
        if part not in target:
            msg = f"unknown sweep path: {path}"
            raise ValueError(msg)
        return target[part]
    msg = f"invalid sweep path: {path}"
    raise ValueError(msg)


def _path_index(part: str, path: str) -> int:
    try:
        index = int(part)
    except ValueError as exc:
        msg = f"expected list index in sweep path {path!r}, got {part!r}"
        raise ValueError(msg) from exc
    if index < 0:
        msg = f"negative list index is not supported in sweep path: {path}"
        raise ValueError(msg)
    return index


def _coerce_value(raw_value: str, current: Any) -> Any:
    lowered = raw_value.strip().lower()
    if lowered in {"none", "null"}:
        return None
    if isinstance(current, bool):
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
        msg = f"expected boolean sweep value, got {raw_value!r}"
        raise ValueError(msg)
    if isinstance(current, int) and not isinstance(current, bool):
        return int(raw_value)
    if isinstance(current, float):
        return float(raw_value)
    if current is None:
        return _infer_scalar(raw_value)
    return raw_value


def _infer_scalar(raw_value: str) -> Any:
    try:
        return int(raw_value)
    except ValueError:
        pass
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def _validate_candidate_expressions(candidate: StrategySpec, root: Path) -> None:
    for expression in candidate.all_expressions():
        validate_expression(expression, candidate.factors, root=root)


def _write_top_specs(
    base: Path,
    candidates: list[SweepCandidateResult],
    write_top: int,
) -> list[Path]:
    if write_top < 0:
        msg = "--write-top cannot be negative"
        raise ValueError(msg)
    written: list[Path] = []
    output_dir = ensure_dir(base / "strategy_specs" / "drafts")
    for candidate in candidates[:write_top]:
        path = output_dir / f"{candidate.spec.name}.yaml"
        path.write_text(
            yaml.safe_dump(candidate.spec.model_dump(mode="json"), sort_keys=False),
            encoding="utf-8",
        )
        candidate.spec_path = path
        written.append(path)
    return written


def _write_sweep_json(
    path: Path,
    source: StrategySpec,
    candidates: list[SweepCandidateResult],
    parameters: dict[str, list[str]],
    min_return_pct: float,
    min_signals: int,
    min_sharpe: float,
    max_candidates: int,
    written_specs: list[Path],
    data_profile: dict[str, Any],
    search_space_payload: dict[str, Any],
    sweep_analysis: dict[str, Any],
    manifest: dict[str, Any],
    ledger: TrialLedger,
    candidate_set: CandidateSet,
    selection_decision: dict[str, Any],
    index_record: ResearchRunIndexRecord,
    search_strategy: str,
    random_seed: int | None,
    research_brief_payload: dict[str, Any],
    search_policy: SearchPolicy,
    research_mode: ResearchMode,
) -> Path:
    ensure_dir(path.parent)
    payload = {
        "strategy_name": source.name,
        "source_timeframe": source.timeframe,
        "source_symbol": source.primary_symbol,
        "candidate_count": len(candidates),
        "trial_count": len(candidates),
        "max_candidates": max_candidates,
        "parameters": parameters,
        "search_strategy": search_strategy,
        "research_mode": research_mode,
        "random_seed": random_seed,
        "search_policy": {
            "strategy": search_policy.strategy,
            "candidate_budget": search_policy.candidate_budget,
            "random_seed": search_policy.random_seed,
            "objective_set": {
                "primary_metric": search_policy.objective_set.primary_metric
                if search_policy.objective_set
                else None,
                "secondary_metrics": search_policy.objective_set.secondary_metrics
                if search_policy.objective_set
                else [],
                "constraints": search_policy.objective_set.constraints
                if search_policy.objective_set
                else {},
                "tie_breakers": search_policy.objective_set.tie_breakers
                if search_policy.objective_set
                else [],
            },
            "prune_rules": search_policy.prune_rules,
            "requires_nested_validation": search_policy.requires_nested_validation,
        },
        "research_brief": research_brief_payload,
        "search_space": search_space_payload,
        "data_profile": data_profile,
        "research_manifest": manifest,
        "trial_ledger": ledger.model_dump(mode="json"),
        "candidate_set": {
            **candidate_set.model_dump(mode="json"),
            "candidate_count": candidate_set.candidate_count,
        },
        "selection_decision": selection_decision,
        "research_run_index_record": index_record.model_dump(mode="json"),
        "stability": sweep_analysis,
        "dsr_inputs": sweep_analysis.get("dsr_inputs", {}),
        "selection_bias_note": sweep_analysis.get("selection_bias_note"),
        "thresholds": {
            "min_return_pct": min_return_pct,
            "min_signals": min_signals,
            "min_sharpe": min_sharpe,
        },
        "written_specs": [path.as_posix() for path in written_specs],
        "warning": (
            "Parameter sweep is in-sample research evidence only; run out-of-sample, "
            "walk-forward, cost sensitivity, and data-source comparison before promotion."
        ),
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
    }
    path.write_text(
        json.dumps(json_safe_payload(payload), indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _append_parameter_sweep_experiment(
    *,
    root: Path,
    source: StrategySpec,
    spec_path: Path,
    report_path: Path,
    json_path: Path,
    candidates: list[SweepCandidateResult],
    search_policy: SearchPolicy,
    research_mode: ResearchMode,
    data_profile: dict[str, Any],
    index_record: ResearchRunIndexRecord,
) -> None:
    run_id = index_record.run_id
    append_experiment_run(
        ExperimentRun(
            run_id=run_id,
            name=f"Parameter Sweep: {source.name}",
            research_mode=research_mode,
            kind="parameter_sweep",
            strategy_name=source.name,
            source_spec_path=workspace_relative_path(spec_path, root),
            spec_hash=strategy_content_hash(source),
            dataset_hash=str(data_profile.get("input_hash") or data_profile.get("path") or ""),
            status="warning",
            gate_status="warning",
            params={
                "search_policy": {
                    "strategy": search_policy.strategy,
                    "candidate_budget": search_policy.candidate_budget,
                    "random_seed": search_policy.random_seed,
                }
            },
            metrics={
                "candidate_count": len(candidates),
                "best_score": candidates[0].score if candidates else None,
                "best_total_return_pct": candidates[0].artifacts.run.total_return_pct
                if candidates
                else None,
            },
            artifact_refs=[
                artifact_ref(report_path, root=root, kind="report", producer="parameter_sweep"),
                artifact_ref(json_path, root=root, kind="json", producer="parameter_sweep"),
            ],
            warning_reasons=[
                "parameter_sweep_is_in_sample_only",
                "requires_oos_walk_forward_cost_and_benchmark_review",
            ],
            trials=[
                ExperimentTrial(
                    trial_id=f"{source.name}-sweep-{candidate.rank:03d}",
                    run_id=run_id,
                    params=candidate.params,
                    metrics=_candidate_payload(candidate)["metrics"],
                    decision="kept" if candidate.rank == 1 else "rejected",
                    decision_reason="selected_best_score"
                    if candidate.rank == 1
                    else "lower_score_or_weaker_research_quality_than_selected_candidate",
                )
                for candidate in candidates
            ],
        ),
        root,
    )


def _candidate_set(
    source: StrategySpec,
    spec_path: Path,
    candidates: list[SweepCandidateResult],
) -> CandidateSet:
    return CandidateSet(
        family="parameter_sweep",
        candidates=[
            CandidateSpec(
                candidate_id=f"{source.name}-candidate-{candidate.rank:03d}",
                strategy_name=candidate.spec.name,
                params=candidate.params,
                source_spec_path=str(spec_path),
                spec_path=str(candidate.spec_path) if candidate.spec_path else None,
            )
            for candidate in candidates
        ],
        scores=[
            CandidateScore(
                candidate_id=f"{source.name}-candidate-{candidate.rank:03d}",
                rank=candidate.rank,
                score=candidate.score,
                metrics=_candidate_payload(candidate)["metrics"],
                quality_flags=_quality_flags(candidate),
                gate_status="warning",
            )
            for candidate in candidates
        ],
    )


def _selection_decision(candidates: list[SweepCandidateResult]) -> dict[str, Any]:
    selected = candidates[0] if candidates else None
    rejected = [
        {
            "rank": candidate.rank,
            "strategy_name": candidate.spec.name,
            "reason": "lower_score_or_weaker_research_quality_than_selected_candidate",
            "score": candidate.score,
            "quality_flags": _quality_flags(candidate),
        }
        for candidate in candidates[1:]
    ]
    return {
        "status": "warning",
        "selected_candidate": _candidate_payload(selected) if selected else None,
        "selection_basis": [
            "score_after_thresholds",
            "quality_flags",
            "trial_ledger_required_before_research_pass",
        ],
        "rejected_candidates": rejected,
        "promotion_blockers": [
            "selection_is_in_sample_only",
            "requires_oos_walk_forward_cost_capacity_and_benchmark_review",
        ],
    }


def _trial_ledger(
    source: StrategySpec,
    candidates: list[SweepCandidateResult],
    max_candidates: int,
    *,
    search_strategy: str,
    random_seed: int | None,
) -> TrialLedger:
    trials = [
        TrialRecord(
            trial_id=f"{source.name}-sweep-{candidate.rank:03d}",
            parent_trial_id=f"{source.name}-source",
            rank=candidate.rank,
            candidate_name=candidate.spec.name,
            params=candidate.params,
            changed_from=candidate.params,
            change_summary=_change_summary(candidate.params),
            score=candidate.score,
            status="warning",
            metrics=_candidate_payload(candidate)["metrics"],
            quality_flags=_quality_flags(candidate),
            lesson_tags=_lesson_tags(candidate),
            artifact_paths={
                "spec_path": str(candidate.spec_path) if candidate.spec_path else None,
                "backtest_report": str(candidate.artifacts.run.report_path)
                if candidate.artifacts.run.report_path
                else None,
            },
            optimizer_type=search_strategy,
            seed=random_seed,
            generation_or_iteration=candidate.rank,
            pruned=False,
            rejection_reason=None
            if candidate.rank == 1
            else "lower_score_or_weaker_research_quality_than_selected_candidate",
        )
        for candidate in candidates
    ]
    return TrialLedger.from_trials(
        strategy_name=source.name,
        family="parameter_sweep",
        trials=trials,
        max_candidates=max_candidates,
        random_seed=random_seed,
    )


def _change_summary(params: dict[str, Any]) -> str:
    if not params:
        return "baseline candidate"
    return "changed " + ", ".join(f"{key}={value}" for key, value in sorted(params.items()))


def _lesson_tags(candidate: SweepCandidateResult) -> list[str]:
    flags = _quality_flags(candidate)
    tags = list(flags)
    if candidate.rank == 1:
        tags.append("current_best_in_sample")
    if candidate.stability.get("neighbor_success_rate") is not None:
        tags.append("has_neighbor_stability")
    return sorted(set(tags))


def _candidate_payload(candidate: SweepCandidateResult) -> dict[str, Any]:
    run = candidate.artifacts.run
    return {
        "rank": candidate.rank,
        "strategy_name": candidate.spec.name,
        "params": candidate.params,
        "score": candidate.score,
        "spec_path": str(candidate.spec_path) if candidate.spec_path else None,
        "metrics": {
            "total_return_pct": run.total_return_pct,
            "buy_hold_return_pct": run.buy_hold_return_pct,
            "alpha_vs_buy_hold_pct": run.alpha_vs_buy_hold_pct,
            "annualized_return_pct": run.annualized_return_pct,
            "sharpe_ratio": run.sharpe_ratio,
            "signals": run.signals,
            "trades": run.trades,
            "total_fees": run.total_fees,
        },
        "quality_flags": _quality_flags(candidate),
        "stability": candidate.stability,
    }


def _sweep_analysis(
    candidates: list[SweepCandidateResult],
    parameters: dict[str, list[str]],
    min_return_pct: float,
    min_signals: int,
    min_sharpe: float,
) -> dict[str, Any]:
    paths = list(parameters)
    for candidate in candidates:
        neighbors = [
            other
            for other in candidates
            if other is not candidate
            and sum(candidate.params.get(path) != other.params.get(path) for path in paths) == 1
        ]
        successful_neighbors = [
            other
            for other in neighbors
            if _candidate_passes(other, min_return_pct, min_signals, min_sharpe)
        ]
        neighbor_success_rate = len(successful_neighbors) / len(neighbors) if neighbors else None
        candidate.stability = {
            "neighbor_count": len(neighbors),
            "successful_neighbor_count": len(successful_neighbors),
            "neighbor_success_rate": neighbor_success_rate,
            "stable_region_score": neighbor_success_rate,
        }

    best = candidates[0]
    scores = [candidate.score for candidate in candidates]
    best_neighbor_success_rate = best.stability.get("neighbor_success_rate")
    overfit_risk = _overfit_risk(
        trial_count=len(candidates),
        neighbor_success_rate=best_neighbor_success_rate,
    )
    return {
        "trial_count": len(candidates),
        "stable_region_score": best.stability.get("stable_region_score"),
        "neighbor_success_rate": best_neighbor_success_rate,
        "rank_correlation_train_oos": None,
        "top_decile_oos_retention": None,
        "overfit_risk": overfit_risk,
        "selection_bias_note": (
            f"{len(candidates)} in-sample trial(s) were compared. Treat the selected rank as "
            "hypothesis generation until out-of-sample, walk-forward, cost sensitivity, and "
            "benchmark-family checks pass."
        ),
        "dsr_inputs": {
            "trial_count": len(candidates),
            "best_score": best.score,
            "mean_score": fmean(scores) if scores else None,
            "score_stddev": pstdev(scores) if len(scores) > 1 else 0.0,
            "computed_dsr": _compute_dsr_proxy(
                trial_count=len(candidates),
                best_score=best.score,
                mean_score=fmean(scores) if scores else None,
                score_stddev=pstdev(scores) if len(scores) > 1 else 0.0,
            ),
            "computed_pbo": _compute_pbo_proxy(best_neighbor_success_rate),
            "note": (
                "DSR uses extreme-value proxy E[max]=μ+σ√(2·ln N) (Bailey & López de Prado 2014). "
                "PBO uses 1−neighbor_success_rate proxy. "
                "Values < 1 for DSR and < 0.10 for PBO suggest lower overfit risk."
            ),
        },
    }


def _compute_dsr_proxy(
    *,
    trial_count: int,
    best_score: float | None,
    mean_score: float | None,
    score_stddev: float,
) -> float | None:
    """Extreme-value proxy for Deflated Sharpe Ratio (Bailey & López de Prado 2014).

    Computes (best − mean) / E[max − mean] where E[max] ≈ μ + σ√(2·ln N).
    Values < 1 suggest the best trial is within the expected range (lower overfit risk).
    Values > 1 suggest the selected trial is an outlier (higher overfit risk).
    Returns None when trial_count ≤ 1 or scores have no spread.
    """
    if trial_count <= 1 or best_score is None or mean_score is None or score_stddev <= 0.0:
        return None
    expected_max = mean_score + score_stddev * sqrt(2.0 * log(float(trial_count)))
    excess_expected = expected_max - mean_score
    if excess_expected <= 0.0:
        return None
    return (best_score - mean_score) / excess_expected


def _compute_pbo_proxy(neighbor_success_rate: float | None) -> float | None:
    """Proxy for Probability of Backtest Overfitting based on neighbourhood stability.

    Returns 1 − neighbor_success_rate: low stability implies high PBO risk.
    Returns None when neighbor_success_rate is unavailable (single trial or no neighbours).
    """
    if neighbor_success_rate is None:
        return None
    return max(0.0, 1.0 - neighbor_success_rate)


def _candidate_passes(
    candidate: SweepCandidateResult,
    min_return_pct: float,
    min_signals: int,
    min_sharpe: float,
) -> bool:
    run = candidate.artifacts.run
    annualized_return = (
        run.annualized_return_pct if run.annualized_return_pct is not None else run.total_return_pct
    )
    return (
        (annualized_return or 0.0) >= min_return_pct
        and run.signals >= min_signals
        and (run.sharpe_ratio or 0.0) >= min_sharpe
    )


def _overfit_risk(
    *,
    trial_count: int,
    neighbor_success_rate: object,
) -> str:
    rate = neighbor_success_rate if isinstance(neighbor_success_rate, int | float) else None
    if trial_count >= 30 or rate is None or rate < 0.25:
        return "high"
    if trial_count >= 10 or rate < 0.5:
        return "moderate"
    return "low"


def _quality_flags(candidate: SweepCandidateResult) -> list[str]:
    run = candidate.artifacts.run
    flags = ["in_sample_only"]
    if run.data_sanity and run.data_sanity.status == "warning":
        flags.append("data_sanity_warning")
    if run.signals < MIN_SIGNALS:
        flags.append("low_signal_count")
    if run.trades < MIN_TRADES:
        flags.append("low_trade_count")
    if run.alpha_vs_buy_hold_pct is not None and run.alpha_vs_buy_hold_pct <= 0:
        flags.append("no_positive_alpha_vs_buy_hold")
    if run.total_fees == 0 and run.trades > 0:
        flags.append("zero_fee_assumption")
    return flags


def _write_sweep_report(
    path: Path,
    source: StrategySpec,
    candidates: list[SweepCandidateResult],
    parameters: dict[str, list[str]],
    min_return_pct: float,
    min_signals: int,
    min_sharpe: float,
    max_candidates: int,
    top_n: int,
    written_specs: list[Path],
    json_path: Path,
    data_profile: dict[str, Any],
    search_space_payload: dict[str, Any],
    sweep_analysis: dict[str, Any],
    search_strategy: str,
) -> Path:
    ensure_dir(path.parent)
    shown = candidates[: max(top_n, 0)]
    lines = [
        f"# Parameter Sweep: {source.name}",
        "",
        f"- Source strategy: `{source.name}`",
        f"- Symbol: `{source.primary_symbol}`",
        f"- Timeframe: `{source.timeframe}`",
        f"- Candidate count: {len(candidates)}",
        f"- Trial count: {sweep_analysis.get('trial_count')}",
        f"- Candidate cap: {max_candidates}",
        f"- Search strategy: `{search_strategy}`",
        f"- Data source mode: `{data_profile.get('source_mode') or 'unknown'}`",
        f"- Data as-of: `{data_profile.get('data_as_of') or 'unknown'}`",
        f"- Minimum return target: {min_return_pct:.2f}%",
        f"- Minimum signal target: {min_signals}",
        f"- Minimum Sharpe target: {min_sharpe:.2f}",
        f"- JSON report: `{json_path}`",
        "- Execution semantics: bar-close signal confirmation and next-bar-open fills.",
        "- Warning: this is in-sample research evidence, not paper promotion evidence.",
        (
            "- Required follow-up: out-of-sample, walk-forward, cost sensitivity, "
            "and data-source comparison."
        ),
        "",
        "## Search Grid",
        "",
    ]
    for path_name, values in parameters.items():
        lines.append(f"- `{path_name}`: {', '.join(str(value) for value in values)}")
    lines.extend(
        [
            "",
            "## Search Space",
            "",
            f"- Family: `{search_space_payload.get('family')}`",
            f"- Candidate count: `{search_space_payload.get('candidate_count')}`",
            f"- Filters: `{search_space_payload.get('filters')}`",
            "",
            "## Stability",
            "",
            f"- Stable region score: `{sweep_analysis.get('stable_region_score')}`",
            f"- Neighbor success rate: `{sweep_analysis.get('neighbor_success_rate')}`",
            f"- Rank correlation train/OOS: `{sweep_analysis.get('rank_correlation_train_oos')}`",
            f"- Top decile OOS retention: `{sweep_analysis.get('top_decile_oos_retention')}`",
            f"- Overfit risk: `{sweep_analysis.get('overfit_risk')}`",
            f"- Selection bias note: {sweep_analysis.get('selection_bias_note')}",
        ]
    )
    lines.extend(["", "## Top Candidates", ""])
    if shown:
        lines.extend(
            [
                (
                    "| Rank | Candidate | Score | Return | Buy/Hold | Alpha | Annualized | "
                    "Sharpe | Signals | Trades | Flags | Params |"
                ),
                "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
            ]
        )
        for candidate in shown:
            run = candidate.artifacts.run
            annualized = (
                f"{run.annualized_return_pct:.2f}%"
                if run.annualized_return_pct is not None
                else "n/a"
            )
            sharpe = f"{run.sharpe_ratio:.2f}" if run.sharpe_ratio is not None else "n/a"
            buy_hold = _format_pct(run.buy_hold_return_pct)
            alpha = _format_pct(run.alpha_vs_buy_hold_pct)
            flags = ", ".join(_quality_flags(candidate))
            params = "; ".join(f"{key}={value}" for key, value in candidate.params.items())
            lines.append(
                f"| {candidate.rank} | `{candidate.spec.name}` | {candidate.score:.2f} | "
                f"{run.total_return_pct:.2f}% | {buy_hold} | {alpha} | {annualized} | "
                f"{sharpe} | {run.signals} | {run.trades} | `{flags}` | `{params}` |"
            )
    else:
        lines.append("- No candidates shown because `top_n` is 0.")
    lines.extend(["", "## Written Specs", ""])
    if written_specs:
        lines.extend(f"- `{path}`" for path in written_specs)
    else:
        lines.append("- No candidate specs were written.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _format_pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.2f}%"
