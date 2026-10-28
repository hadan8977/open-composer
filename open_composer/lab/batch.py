"""Sequential variants, durable exposure, immutable native evidence and Results writing."""

from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from open_composer.lab.ledger import TrialLedger
from open_composer.lab.metrics import DSRConfig, dsr_summary, return_metrics
from open_composer.lab.models import EngineResult, Experiment
from open_composer.research.agent_workflow import (
    Results,
    direction_lock,
    identifier,
    local_path,
    require_research,
)


def _json_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(v) for v in value]
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, np.generic):
        return _json_value(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        # Native nonfinites remain distinguishable from missing values in strict JSON.
        return {"native_nonfinite": str(value)}
    return value


def write_evidence(path: Path, value: Any) -> None:
    """Exclusive creation prevents an accidental rerun from replacing old evidence."""
    with path.open("x", encoding="utf-8") as stream:
        json.dump(_json_value(value), stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")


@dataclass(frozen=True)
class Variant:
    id: str
    parameters: dict[str, Any]
    evaluate: Callable[[], EngineResult]
    counts_as_trial: bool = True
    exposure_note: str = "Selectable research variant"


@dataclass(frozen=True)
class BatchResult:
    folder: Path
    results: dict[str, Path]
    failures: dict[str, str]
    n_trials: int


def run_batch(
    root: Path,
    *,
    experiment: Experiment,
    batch_id: str,
    variants: Sequence[Variant],
    dsr_config: DSRConfig | None = None,
    selected_id: str | None = None,
) -> BatchResult:
    """Run only with installed research authority. No provider, broker or parallel jobs.

    A batch writes one Results contract per success, with the final cumulative count,
    including failures and imported historical exposure. It never chooses a winner.
    ``selected_id`` explicitly publishes that result to direction/results.json.
    """
    root = Path(root).resolve()
    dsr_config = dsr_config or DSRConfig()
    identifier(experiment.direction)
    identifier(batch_id)
    variants = list(variants)
    ids = [identifier(v.id) for v in variants]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("A batch requires unique nonempty variant ids")
    if selected_id is not None and selected_id not in ids:
        raise ValueError("Selected result must be an explicitly declared batch variant")
    for variant in variants:
        if not variant.counts_as_trial and not variant.exposure_note.strip():
            raise ValueError("Nonselectable controls require an exposure explanation")
        json.dumps(variant.parameters, allow_nan=False)
    require_research(root)
    direction = local_path(root, f"research/{experiment.direction}")
    direction.mkdir(parents=True, exist_ok=True)
    with direction_lock(direction / ".lab.lock"):
        ledger = TrialLedger(direction / "trials.jsonl")
        existing = ledger.events()
        unresolved = [
            e.trial_id
            for e in existing
            if e.event == "started"
            and not any(r.event == "finished" and r.trial_id == e.trial_id for r in existing)
        ]
        if unresolved:
            raise ValueError(
                "Reconcile unfinished trials before new starts; exposure remains counted: "
                + ", ".join(unresolved)
            )
        folder = direction / "batches" / batch_id
        folder.mkdir(parents=True, exist_ok=False)
        write_evidence(
            folder / "manifest.json",
            {
                "experiment": experiment.__dict__,
                "variants": [
                    {
                        "id": v.id,
                        "parameters": v.parameters,
                        "counts_as_trial": v.counts_as_trial,
                        "exposure_note": v.exposure_note,
                    }
                    for v in variants
                ],
            },
        )
        outputs: dict[str, tuple[EngineResult, list[str]]] = {}
        failures: dict[str, str] = {}
        for variant in variants:
            require_research(root)
            trial_id = f"{batch_id}/{variant.id}"
            trial_folder = folder / variant.id
            trial_folder.mkdir()
            ledger.start(
                trial_id,
                batch=batch_id,
                candidate=variant.id,
                parameters=variant.parameters,
                counts_as_trial=variant.counts_as_trial,
                note=variant.exposure_note,
            )
            try:
                output = variant.evaluate()
                if output.return_frequency != "session":
                    raise ValueError("Aggregate native bar returns to explicit sessions first")
                native_path = trial_folder / "native.json"
                write_evidence(
                    native_path,
                    {"output": output.native, "adapter_metadata": output.metadata},
                )
                sources = [str(native_path.relative_to(root))]
                if output.ledger is not None:
                    path = trial_folder / "ledger.csv"
                    output.ledger.to_csv(path, index_label="timestamp")
                    sources.append(str(path.relative_to(root)))
                if output.net_returns is not None:
                    path = trial_folder / "returns.csv"
                    output.net_returns.rename("net").to_csv(path, index_label="timestamp")
                    sources.append(str(path.relative_to(root)))
                outputs[variant.id] = output, sources
                ledger.finish(trial_id, status="complete", evidence=sources)
            except BaseException as exc:
                path = trial_folder / "failure.json"
                write_evidence(path, {"type": type(exc).__name__, "message": str(exc)})
                ledger.finish(
                    trial_id,
                    status="interrupted" if not isinstance(exc, Exception) else "failed",
                    evidence=[str(path.relative_to(root))],
                    note=str(exc),
                )
                if not isinstance(exc, Exception):
                    raise
                failures[variant.id] = str(exc)
        snapshot = folder / "trials.snapshot.jsonl"
        n_trials = ledger.snapshot(snapshot)
        results = {}
        for candidate_id, (output, sources) in outputs.items():
            trial_folder = folder / candidate_id
            statistic = dsr_summary(output.net_returns, n_trials=n_trials, config=dsr_config)
            metrics = (
                return_metrics(output.net_returns, output.initial_equity_usd)
                if output.net_returns is not None
                else {"net_profit_usd": output.net_profit_usd}
            )
            metrics["dsr"] = statistic
            metrics_path = trial_folder / "metrics.json"
            write_evidence(metrics_path, metrics)
            evidence = [
                *sources,
                str(snapshot.relative_to(root)),
                str(metrics_path.relative_to(root)),
            ]
            limitations = [*experiment.limitations, *output.limitations]
            if output.net_returns is not None and len(output.net_returns) < 252:
                limitations.append("short_sample_caveat: fewer than 252 observed sessions")
            result = Results(
                direction=experiment.direction,
                kind=experiment.kind,
                engine=output.engine,
                source_artifacts=evidence,
                data_and_exposure=experiment.data_and_exposure,
                costs=experiment.costs,
                baseline=experiment.baseline,
                n_trials=n_trials,
                net_profit_usd=output.net_profit_usd,
                baseline_net_profit_usd=experiment.baseline_net_profit_usd,
                dsr=statistic["dsr"],
                dsr_note=json.dumps(statistic, ensure_ascii=False, allow_nan=False),
                limitations=limitations,
            )
            path = trial_folder / "results.json"
            write_evidence(path, result.model_dump())
            results[candidate_id] = path
        write_evidence(
            folder / "batch.json",
            {
                "n_trials": n_trials,
                "results": {key: str(path.relative_to(root)) for key, path in results.items()},
                "failures": failures,
            },
        )
        if selected_id is not None:
            if selected_id not in results:
                raise ValueError("Selected variant failed; existing direction result was preserved")
            target = direction / "results.json"
            temporary = direction / ".results.lab.tmp"
            temporary.write_bytes(results[selected_id].read_bytes())
            temporary.replace(target)
        return BatchResult(folder=folder, results=results, failures=failures, n_trials=n_trials)
