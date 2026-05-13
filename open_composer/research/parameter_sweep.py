from __future__ import annotations

import copy
import json
from dataclasses import dataclass
from itertools import product
from math import prod
from pathlib import Path
from typing import Any

import yaml

from open_composer.adapters.data import load_ohlcv_for_spec
from open_composer.config import ensure_dir, project_root
from open_composer.engines.backtest_engine import BacktestArtifacts, backtest_frame
from open_composer.expressions import validate_expression
from open_composer.models.strategy_spec import StrategySpec, load_strategy_spec
from open_composer.research.optimizer import _score_candidate

ALLOWED_SWEEP_ROOTS = {"entry", "exit", "risk", "costs", "factors"}


@dataclass
class SweepCandidateResult:
    rank: int
    spec: StrategySpec
    params: dict[str, Any]
    artifacts: BacktestArtifacts
    score: float
    spec_path: Path | None = None


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
) -> ParameterSweepResult:
    base = root or project_root()
    source = load_strategy_spec(spec_path)
    if not parameters:
        msg = "parameter sweep requires at least one parameter"
        raise ValueError(msg)
    if max_candidates < 1:
        msg = "--max-candidates must be at least 1"
        raise ValueError(msg)
    total_candidates = prod(len(values) for values in parameters.values())
    if total_candidates > max_candidates:
        msg = (
            f"parameter sweep would create {total_candidates} candidates; "
            f"raise --max-candidates above {total_candidates} or narrow the grid"
        )
        raise ValueError(msg)

    frame = load_ohlcv_for_spec(source, base)
    candidate_results: list[SweepCandidateResult] = []
    for index, params in enumerate(_parameter_combinations(parameters), start=1):
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

    written_specs = _write_top_specs(base, candidate_results, write_top)
    report_path = base / "reports" / "research" / f"{source.name}-parameter-sweep.md"
    json_path = base / "reports" / "research" / f"{source.name}-parameter-sweep.json"
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
) -> Path:
    ensure_dir(path.parent)
    payload = {
        "strategy_name": source.name,
        "source_timeframe": source.timeframe,
        "source_symbol": source.primary_symbol,
        "candidate_count": len(candidates),
        "max_candidates": max_candidates,
        "parameters": parameters,
        "thresholds": {
            "min_return_pct": min_return_pct,
            "min_signals": min_signals,
            "min_sharpe": min_sharpe,
        },
        "written_specs": [str(path) for path in written_specs],
        "warning": (
            "Parameter sweep is in-sample research evidence only; run out-of-sample, "
            "walk-forward, cost sensitivity, and data-source comparison before promotion."
        ),
        "candidates": [_candidate_payload(candidate) for candidate in candidates],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


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
            "annualized_return_pct": run.annualized_return_pct,
            "sharpe_ratio": run.sharpe_ratio,
            "signals": run.signals,
            "trades": run.trades,
            "total_fees": run.total_fees,
        },
    }


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
        f"- Candidate cap: {max_candidates}",
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
        "## Grid",
        "",
    ]
    for path_name, values in parameters.items():
        lines.append(f"- `{path_name}`: {', '.join(str(value) for value in values)}")
    lines.extend(["", "## Top Candidates", ""])
    if shown:
        lines.extend(
            [
                (
                    "| Rank | Candidate | Score | Return | Annualized | Sharpe | Signals | "
                    "Trades | Params |"
                ),
                "|---:|---|---:|---:|---:|---:|---:|---:|---|",
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
            params = "; ".join(f"{key}={value}" for key, value in candidate.params.items())
            lines.append(
                f"| {candidate.rank} | `{candidate.spec.name}` | {candidate.score:.2f} | "
                f"{run.total_return_pct:.2f}% | {annualized} | {sharpe} | "
                f"{run.signals} | {run.trades} | `{params}` |"
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
