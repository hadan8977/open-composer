from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from pathlib import Path

from open_composer.config import ensure_dir, project_root
from open_composer.models.experiment import ArtifactRef, ExperimentRun
from open_composer.storage import append_jsonl


def experiment_index_path(root: Path | None = None) -> Path:
    base = root or project_root()
    return base / "reports" / "experiments" / "index.jsonl"


def artifact_ref(
    path: Path,
    *,
    root: Path | None = None,
    kind: str,
    producer: str,
) -> ArtifactRef:
    base = root or project_root()
    resolved = path if path.is_absolute() else base / path
    label = _relative_label(resolved, base)
    digest = _sha256(resolved) if resolved.exists() and resolved.is_file() else None
    return ArtifactRef(path=label, kind=kind, sha256=digest, producer=producer)


def append_experiment_run(run: ExperimentRun, root: Path | None = None) -> Path:
    path = experiment_index_path(root)
    return append_jsonl(path, [run])


def read_experiment_runs(root: Path | None = None) -> list[ExperimentRun]:
    path = experiment_index_path(root)
    if not path.exists():
        return []
    runs: list[ExperimentRun] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                runs.append(ExperimentRun.model_validate(json.loads(line)))
    return runs


def find_experiment_run(run_id: str, root: Path | None = None) -> ExperimentRun:
    for run in read_experiment_runs(root):
        if run.run_id == run_id:
            return run
    raise FileNotFoundError(f"experiment run not found: {run_id}")


def compare_experiment_runs(
    left_run_id: str,
    right_run_id: str,
    root: Path | None = None,
) -> dict[str, object]:
    left = find_experiment_run(left_run_id, root)
    right = find_experiment_run(right_run_id, root)
    metrics: dict[str, dict[str, float | None]] = {}
    for key in sorted(set(left.metrics) | set(right.metrics)):
        left_value = _float_or_none(left.metrics.get(key))
        right_value = _float_or_none(right.metrics.get(key))
        delta = None if left_value is None or right_value is None else right_value - left_value
        metrics[key] = {"left": left_value, "right": right_value, "delta": delta}
    return {
        "left_run_id": left.run_id,
        "right_run_id": right.run_id,
        "left_status": left.status,
        "right_status": right.status,
        "metrics": metrics,
    }


def experiment_artifacts(run_id: str, root: Path | None = None) -> list[ArtifactRef]:
    return find_experiment_run(run_id, root).artifact_refs


def trace_experiment_runs(strategy_name: str, root: Path | None = None) -> list[ExperimentRun]:
    runs = [
        run
        for run in read_experiment_runs(root)
        if run.strategy_name.lower() == strategy_name.lower()
    ]
    return sorted(runs, key=lambda run: run.started_at)


def write_experiment_runs(runs: Iterable[ExperimentRun], root: Path | None = None) -> Path:
    path = experiment_index_path(root)
    ensure_dir(path.parent)
    if path.exists():
        path.unlink()
    return append_jsonl(path, runs)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_label(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _float_or_none(value: object) -> float | None:
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return None
